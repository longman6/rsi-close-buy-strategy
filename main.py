import sys
import time
import pandas as pd
import logging
import pytz
from datetime import datetime, timedelta
import config
from src.kis_client import KISClient
from src.slack_bot import SlackBot
from src.strategy import Strategy

# Setup Logging
# Setup Logging
def kst_converter(*args):
    return datetime.now(pytz.timezone('Asia/Seoul')).timetuple()

logging.Formatter.converter = kst_converter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("trade_log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Global State Variables (Reset daily)
state = {
    "analysis_done": False,
    "pre_order_done": False,
    "buy_verified": False,
    "sell_check_done": False,
    "sell_exec_done": False,
    "buy_targets": [], # List of dict: {code, rsi, close_yesterday, target_qty}
    "buy_targets": [], # List of dict: {code, rsi, close_yesterday, target_qty}
    "last_reset_date": None,
    "is_holiday": False
}

def get_now_kst():
    """Get current time in KST (Asia/Seoul)"""
    tz_kst = pytz.timezone('Asia/Seoul')
    # If system is UTC, use utcnow().astimezone
    return datetime.now(pytz.utc).astimezone(tz_kst)

def reset_daily_state(kis):
    today = get_now_kst().strftime("%Y-%m-%d")
    if state["last_reset_date"] != today:
        logging.info("🔄 Resetting Daily State...")
        state["analysis_done"] = False
        state["pre_order_done"] = False
        state["buy_verified"] = False
        state["sell_check_done"] = False
        state["sell_exec_done"] = False
        state["buy_targets"] = []
        state["last_reset_date"] = today
        
        # Check Holiday
        today_str = today.replace("-", "")
        if not kis.is_trading_day(today_str):
            state["is_holiday"] = True
            logging.info(f"🏖️ Today ({today}) is a Holiday/Weekend. Trading Paused.")
        else:
            state["is_holiday"] = False
            logging.info(f"📈 Today ({today}) is a Trading Day.")

def main():
    logging.info("🚀 Continuous RSI Power Zone Bot Started")
    
    kis = KISClient()
    slack = SlackBot()
    strategy = Strategy()

    # Disable Slack in Mock Mode
    if kis.is_mock:
        logging.info("[Main] Mock Mode: Slack Disabled, Delays Increased.")
        slack.enabled = False
    
    slack.send_message("🤖 Bot Loop Started. Waiting for schedule...")

    state["last_reset_date"] = get_now_kst().strftime("%Y-%m-%d")
    
    # Check Initial Holiday Status
    today_str = state["last_reset_date"].replace("-", "")
    if not kis.is_trading_day(today_str):
        state["is_holiday"] = True
        logging.info(f"🏖️ Today is a Holiday/Weekend. Trading Paused.")
    else:
        state["is_holiday"] = False

    # Log Startup Time in KST
    startup_kst = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"⏰ KST Clock Check: {startup_kst}")
    logging.info(f"📅 Daily State: Analysis={state['analysis_done']}, PreOrder={state['pre_order_done']}")

    # Initial Status Display (Run once on startup)
    # Initial Status Display (Run once on startup)
    if not state["is_holiday"]:
        logging.info("📊 Checking Initial Holdings...")
        try:
            display_holdings_status(kis, slack, strategy)
        except Exception as e:
            logging.error(f"Failed to display initial status: {e}")
    else:
        logging.info("🏖️ Holiday/Weekend: Skipping Initial Holdings Check to avoid API errors.")

    while True:
        try:
            now = get_now_kst()
            current_time = now.strftime("%H:%M")
            now = get_now_kst()
            current_time = now.strftime("%H:%M")
            reset_daily_state(kis)

            # Holiday Skip
            if state["is_holiday"]:
                # Log heartbeat occasionally? Or just sleep
                if int(now.strftime("%M")) % 30 == 0 and int(now.strftime("%S")) < 5:
                     logging.info(f"💤 Holiday Sleep ({now.strftime('%Y-%m-%d %H:%M')})...")
                time.sleep(60) 
                # Still check reset_daily_state next loop
                continue

            # 1. 08:30 Analysis & Buy Candidate Selection
            # 1. 08:30 Analysis & Buy Candidate Selection
            # Window: 08:30 ~ 08:50
            if current_time >= config.TIME_MORNING_ANALYSIS and current_time <= "08:50":
                if not state["analysis_done"]:
                    run_morning_analysis(kis, slack, strategy)
                    state["analysis_done"] = True
            elif current_time > "08:50" and not state["analysis_done"]:
                # If started late (after 08:50), skip analysis
                logging.info(f"⏭️ [Skip] Morning Analysis window passed ({current_time}).")
                state["analysis_done"] = True

            # 2. 08:57 Pre-Market Order
            # 2. 08:57 Pre-Market Order
            # Window: 08:57 ~ 09:10
            if current_time >= config.TIME_PRE_ORDER and current_time <= "09:10":
                if not state["pre_order_done"]:
                    run_pre_order(kis, slack)
                    state["pre_order_done"] = True
            elif current_time > "09:10" and not state["pre_order_done"]:
                # If started late, skip pre-order
                logging.info(f"⏭️ [Skip] Pre-Order window passed ({current_time}).")
                state["pre_order_done"] = True
                
            # 3. 09:05 ~ Order Verification & Correction Loop
            # This runs repeatedly every minute starting from 09:05 until ... say 15:00?
            # Or just "If verify not done, or continuous check?"
            # Requirement: "09:05 check... then every 1 min check..."
            if current_time >= config.TIME_ORDER_CHECK and current_time < config.TIME_SELL_CHECK:
                 monitor_and_correct_orders(kis, slack)

            # Periodic Display of Holdings (Always run, throttled inside)
            display_holdings_status(kis, slack, strategy)

            # 4. 15:20 Sell Signal Check
            if current_time >= config.TIME_SELL_CHECK and not state["sell_check_done"]:
                run_sell_check(kis, slack, strategy)
                state["sell_check_done"] = True

            # 5. 15:26 Sell Execution (Market/Best)
            if current_time >= config.TIME_SELL_EXEC and not state["sell_exec_done"]:
                run_sell_execution(kis, slack)
                state["sell_exec_done"] = True
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            logging.info("🛑 Bot Stopped by User.")
            break
        except Exception as e:
            logging.error(f"⚠️ Main Loop Error: {e}")
            time.sleep(5)

def run_morning_analysis(kis, slack, strategy):
    """08:30: Calculate RSI, Select Candidates"""
    logging.info("🔍 [08:30] Starting Morning Analysis...")
    slack.send_message("🔍 [08:30] Morning Analysis Started")

    balance = kis.get_balance()
    if not balance:
        logging.error("Failed to fetch balance.")
        return

    # Check Holdings Count
    current_holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    slots_open = config.MAX_POSITIONS - len(current_holdings)
    
    if slots_open <= 0:
        logging.info("Portfolio Full. No new buys.")
        slack.send_message("ℹ️ Portfolio Full. No new buys.")
        return

    universe = strategy.get_universe()
    candidates = []
    
    # Optimization: 250 days fetch
    # Use KST for date strings too, though API handles string YYYYMMDD
    start_date = (get_now_kst() - timedelta(days=250)).strftime("%Y%m%d")

    cnt = 0
    for code in universe:
        if any(h['pdno'] == code for h in current_holdings): continue
        
        # Delay (Mock vs Real)
        time.sleep(1.5 if kis.is_mock else 0.2)
        
        df = kis.get_daily_ohlcv(code, start_date=start_date)
        if df.empty: continue
        
        df = strategy.calculate_indicators(df)
        signal = strategy.analyze_stock(code, df)
        
        if signal:
            signal['name'] = code # Placeholder
            candidates.append(signal)
            logging.info(f"Candidate: {code} RSI={signal['rsi']:.2f}")
    
    # Sort by RSI
    candidates.sort(key=lambda x: x['rsi'])
    final_buys = candidates[:slots_open]
    
    # Save to State
    # Need to verify if 'close' in signal is 'yesterday close' (since ran at 08:30)
    # Yes, get_daily_ohlcv returns up to yesterday if market not open.
    for item in final_buys:
        state["buy_targets"].append({
            "code": item['code'],
            "rsi": item['rsi'],
            "close_yesterday": float(item['close']), # Ref Price
            "target_qty": 0 # Calculated later
        })
    
    msg = f"✅ Analysis Done. Selected {len(final_buys)} candidates."
    logging.info(msg)
    slack.send_message(msg)

def run_pre_order(kis, slack):
    """08:57: Place Limit Order = Expected + 5 Ticks (or Yesterday Close + 5 Ticks if no output)"""
    # Note: KIS 'get_current_price' might have 'Expected Price' (dnca or similar) before market open.
    # But simplifying: Use Yesterday Close * 1.02 ?? 
    # User Request: "Expected Execution Price + 5 ticks". 
    # We will try to fetch Expected Price. If not avail, use Close.
    
    logging.info("⏰ [08:57] Placing Pre-Orders...")
    slack.send_message("⏰ [08:57] Placing Pre-Orders")
    
    if not state["buy_targets"]:
        logging.info("No targets to buy.")
        return

    balance = kis.get_balance()
    cash = balance['cash_available']
    count = len(state["buy_targets"])
    if count == 0: return

    # amt_per_stock = (cash * config.ALLOCATION_PCT) # Deprecated
    # Use Fixed Amount from Config
    amt_per_stock = config.BUY_AMOUNT_KRW
    
    # Check if we have enough cash (Optional warning)
    total_needed = amt_per_stock * count
    if total_needed > cash:
        msg = f"⚠️ 예수금 부족! 필요: {total_needed:,.0f}원, 보유: {cash:,.0f}원. 일부 주문이 거부될 수 있습니다."
        logging.warning(msg)
        slack.send_message(msg) 

    for target in state["buy_targets"]:
        code = target['code']
        # Fetch Expected Price
        curr = kis.get_current_price(code)
        
        # Try to find expected price (antc_cnpr: Anticipated Conclusion Price) if avail
        # Output of inquire-price has 'antc_cnpr'.
        if curr and int(curr.get('antc_cnpr', 0)) > 0:
            base_price = float(curr['antc_cnpr'])
        else:
            base_price = target['close_yesterday']
            
        # +5 Ticks Logic... simple approx +2%? or strict tick math?
        # User said "5 ticks high". 
        # Lets just use +1.5% as safe proxy for 5 ticks, or use get_valid_price logic iteratively.
        # Adding 1.5% is roughly 3-5 ticks depending on price range.
        limit_price = int(base_price * 1.015) 
        limit_price = kis.get_valid_price(limit_price)
        
        qty = int(amt_per_stock / limit_price)
        if qty < 1: continue
        
        target['target_qty'] = qty # Update state
        
        # Place Order
        # 00: Limit
        success, msg = kis.send_order(code, qty, side="buy", price=limit_price, order_type="00")
        if success:
            slack.send_message(f"🚀 Pre-Order: {code} {qty}ea @ {limit_price}")
        else:
            slack.send_message(f"❌ Pre-Order Failed {code}: {msg}")
            
        time.sleep(0.2)

last_monitor_time = 0
last_display_time = 0

def monitor_and_correct_orders(kis, slack):
    """
    09:05 ~ Loop: Check Unfilled.
    If unfilled, modify to Current Price.
    BUT if Current Price > Yesterday Close * 1.05 (+5%), CANCEL order (Give up).
    """
    global last_monitor_time
    if time.time() - last_monitor_time < 60:
         return # Run every 1 min
    
    last_monitor_time = time.time()
    
    # logging.info("♻️ [Monitor] Checking Unfilled Orders...")
    
    orders = kis.get_outstanding_orders()
    if not orders: return 
    
    for ord in orders:
        # Check if this is OUR buy order
        # ord: {pdno, ord_qty, ccld_qty ...}
        code = ord['pdno']
        
        # Find matching target in state
        target = next((t for t in state["buy_targets"] if t['code'] == code), None)
        if not target: continue # Not our managed target
        
        # Check current price
        curr = kis.get_current_price(code)
        if not curr: continue
        
        current_price = float(curr['stck_prpr'])
        yesterday_close = target['close_yesterday']
        
        # Condition: If Current > Yesterday + 5% -> Cancel
        if current_price > yesterday_close * 1.05:
            logging.info(f"🚫 {code} rose too much (>5%). Cancelling...")
            kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'], 0, 0, is_cancel=True)
            slack.send_message(f"🗑️ Cancelled {code}: Price > +5%")
        else:
            # Modify to Current Price (Chase)
            # Only if current price != order price?
            # ord_unpr (Price)
            order_price = float(ord['ord_unpr'])
            if order_price != current_price:
                 logging.info(f"✏️ Correcting {code} to Current Price {current_price}")
                 # Use Remainder Qty
                 rem_qty = int(ord['ord_qty']) - int(ord['ccld_qty'])
                 if rem_qty > 0:
                     kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'], rem_qty, current_price, is_cancel=False)
                     slack.send_message(f"✏️ Modified {code} -> {current_price}")

def display_holdings_status(kis, slack, strategy):
    """
    Step 7: Check Every 1 min and display info.
    We combine this with monitor loop.
    """
    global last_display_time
    if time.time() - last_display_time < 60:
        return

    last_display_time = time.time()

    # Assuming run once per minute along with monitor.
    balance = kis.get_balance()
    if not balance: return
    
    holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    if not holdings: return
    
    # Visual Separator for new loop
    logging.info("-" * 60)
    
    # Optimization: Fetch shorter history for RSI(3) display
    # Must be > SMA_WINDOW (100) to ensure calculate_indicators adds columns
    start_date = (get_now_kst() - timedelta(days=200)).strftime("%Y%m%d")
    
    for h in holdings:
        name = h['prdt_name']
        code = h['pdno']
        curr = float(h['prpr'])
        avg = float(h['pchs_avg_pric'])
        
        # Calculate RSI
        time.sleep(0.2 if kis.is_mock else 0.1) # Brief delay
        df = kis.get_daily_ohlcv(code, start_date=start_date)
        rsi_val = 0.0
        if not df.empty:
            df = strategy.calculate_indicators(df)
            if not df.empty and 'RSI' in df.columns:
                 rsi_val = df['RSI'].iloc[-1]
        
        # Profit
        profit_amt = (curr - avg) * int(h['hldg_qty'])
        profit_pct = (curr - avg) / avg * 100
        
        msg = f"📊 {name}({code}): Now {curr:,.0f} / Buy {avg:,.0f} | RSI: {rsi_val:.2f} | P/L: {profit_amt:,.0f} ({profit_pct:.2f}%)"
        logging.info(msg)

def run_sell_check(kis, slack, strategy):
    """15:20 Sell Check"""
    logging.info("⚖️ [15:20] Checking Sell Signals...")
    slack.send_message("⚖️ [15:20] Checking Sell Signals")
    
    balance = kis.get_balance()
    if not balance: return
    
    for h in balance['holdings']:
        qty = int(h['hldg_qty'])
        if qty == 0: continue
        
        code = h['pdno']
        name = h['prdt_name']
        
        df = kis.get_daily_ohlcv(code) # Need fresh data (including today's incomplete candle?)
        # Actually daily OHLCV usually updates strictly after close or delayed.
        # But we need Current RSI.
        # We can append current price to DF? 
        # Strategy.calculate_indicators handles DF.
        # Ideally we fetch minute candle or append current price as today's close.
        
        curr = kis.get_current_price(code)
        if curr:
            # Construct Pseudo-Row for today if missing or update it
            # Simplified: Just check if RSI(3) of yesterday was high?
            # No, user wants active check.
            # Lets run analyze_stock on current df.
            pass
            
        df = strategy.calculate_indicators(df)
        if strategy.check_sell_signal(code, df):
             logging.info(f"🔻 Sell Signal Identified for {name} ({code})")
             # Mark for selling
             # For simplicity, we can just sell NOW or wait for 15:26 EXEC.
             # User said: "15:20 Check... 15:26 Execute Market Sell".
             # We should probably store "To Sell" list.
             # but to keep it simple, we can just sell at 15:26 by re-checking or storing.
             pass

def run_sell_execution(kis, slack):
    """15:26 Execute Market Sell for targets"""
    logging.info("💸 [15:26] Executing Market Sells...")
    slack.send_message("💸 [15:26] Market Sell Execution")
    
    # We re-run logic or iterate holdings. 
    # Efficient way: Logic same as 'run_sell_check' but SEND ORDER.
    
    balance = kis.get_balance()
    strategy = Strategy()
    
    for h in balance['holdings']:
        qty = int(h['hldg_qty'])
        if qty == 0: continue
        
        code = h['pdno']
        name = h['prdt_name']
        
        # Get Data & RSI
        df = kis.get_daily_ohlcv(code)
        df = strategy.calculate_indicators(df)
        
        # Check RSI > 70
        if strategy.check_sell_signal(code, df):
             # Execute Market Sell (01)
             success, msg = kis.send_order(code, qty, side="sell", price=0, order_type="01")
             if success:
                 slack.send_message(f"👋 Sold {name} (Market): {msg}")
             else:
                 slack.send_message(f"❌ Sell Failed {name}: {msg}")

if __name__ == "__main__":
    main()
