import sys
import os
import time
import pandas as pd
import logging
import pytz
from datetime import datetime, timedelta
import config
from src.kis_client import KISClient
from src.telegram_bot import TelegramBot
from src.strategy import Strategy
from src.trade_manager import TradeManager
from src.db_manager import DBManager
            # 0. 07:00 Gemini Buy Advice (Removed - Replaced by Cron analyze_kosdaq150.py)
            # if current_time == "07:00": ...
from scripts import parse_trade_log

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
    "last_reset_date": None,
    "is_holiday": False,
    "exclude_list": set(),
    "gemini_advice_done": False,
    "last_sent_hour": -1 # Track hourly notifications
}

def load_exclusion_list(kis=None):
    """Load excluded stock codes from file and optionally log names"""
    exclude_file = "exclude_list.txt"
    excluded = set()
    if os.path.exists(exclude_file):
        try:
            with open(exclude_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    excluded.add(line)
            
            logging.info(f"🚫 Exclusion List Loaded: {len(excluded)} items.")
            
            # If KIS client is provided, fetch and display names
            if kis and excluded:
                logging.info("   [Excluded Stocks]")
                for code in excluded:
                    name = "Unknown"
                    try:
                        # Fetch price info to get name
                        time.sleep(0.1) 
                        # Use get_stock_info first (most reliable for name)
                        info = kis.get_stock_info(code)
                        if info:
                            name = info.get('prdt_name', "Unknown")
                        else:
                            # Fallback
                            curr = kis.get_current_price(code)
                            if curr:
                                name = curr.get('hts_kor_isnm') or "Unknown"
                    except Exception:
                        pass
                    logging.info(f"   - {code} : {name}")

        except Exception as e:
            logging.error(f"Failed to load exclusion list: {e}")
    return excluded

from src.utils import get_now_kst

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
        state["exclude_list"] = load_exclusion_list(kis)
        state["gemini_advice_done"] = False
        state["last_reset_date"] = today
        state["last_sent_hour"] = -1
        
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
    telegram = TelegramBot() # Changed from SlackBot
    strategy = Strategy()
    
    # 0. Initialize Trade Manager & Parse Logs (Startup)
    if not os.path.exists("trade_history.json"):
        logging.info("📜 trade_history.json not found. Parsing local trade logs...")
        parse_trade_log.parse_log()
    else:
        logging.info("📜 trade_history.json found. Loading existing history.")
    db_manager = DBManager()
    trade_manager = TradeManager(db=db_manager)

    # Disable Telegram in Mock Mode? User might still want logs.
    # User requested control via .env ENABLE_NOTIFICATIONS, so we respect that.
    if kis.is_mock and telegram.enabled:
         telegram.send_message("🤖 Bot Loop Started (Mock Mode). Waiting for schedule...")
    elif telegram.enabled:
         telegram.send_message("🤖 Bot Loop Started (Real Mode). Waiting for schedule...")

    # FORCE Initial State Reset (to load exclusion list and check holiday)
    reset_daily_state(kis)

    # Log Startup Time in KST
    startup_kst = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"⏰ KST Clock Check: {startup_kst}")
    logging.info(f"📅 Daily State: Analysis={state['analysis_done']}, PreOrder={state['pre_order_done']}")

            # Initial Status Display (Run once on startup)
    logging.info("📊 Checking Initial Holdings...")
    try:
        display_holdings_status(kis, telegram, strategy, trade_manager, force=True)
    except Exception as e:
        logging.error(f"Failed to display initial status (Network/API Error): {e}")

    while True:
        try:
            now = get_now_kst()
            current_time = now.strftime("%H:%M")
            reset_daily_state(kis)

            # Holiday Skip - Removed to allow Holdings Display
            # if state["is_holiday"]: ...

            # 1. 08:30 Analysis & Buy Candidate Selection
            # Window: 08:30 ~ 08:50
            if not state["is_holiday"]:
                if current_time >= config.TIME_MORNING_ANALYSIS and current_time <= "08:50":
                    if not state["analysis_done"]:
                        run_morning_analysis(kis, telegram, strategy, trade_manager)
                        state["analysis_done"] = True
                elif current_time > "08:50" and not state["analysis_done"]:
                    # If started late (after 08:50), skip analysis
                    logging.info(f"⏭️ [Skip] Morning Analysis window passed ({current_time}).")
                    state["analysis_done"] = True

            # 2. 08:57 Pre-Market Order
            # Window: 08:57 ~ 09:10
            if not state["is_holiday"]:
                if current_time >= config.TIME_PRE_ORDER and current_time <= "09:10":
                    if not state["pre_order_done"]:
                        run_pre_order(kis, telegram, trade_manager)
                        state["pre_order_done"] = True
                elif current_time > "09:10" and not state["pre_order_done"]:
                    # If started late, skip pre-order
                    logging.info(f"⏭️ [Skip] Pre-Order window passed ({current_time}).")
                    state["pre_order_done"] = True
                
            # 3. 09:05 ~ Order Verification & Correction Loop
            # This runs repeatedly every minute starting from 09:05 until ... say 15:00?
            if not state["is_holiday"]:
                if current_time >= config.TIME_ORDER_CHECK and current_time < config.TIME_SELL_CHECK:
                     monitor_and_correct_orders(kis, telegram, trade_manager)

            # Periodic Display of Holdings (Scheduled Hourly at XX:10)
            display_holdings_status(kis, telegram, strategy, trade_manager)

            # 4. 15:20 Sell Signal Check
            if not state["is_holiday"]:
                if current_time >= config.TIME_SELL_CHECK and not state["sell_check_done"]:
                    run_sell_check(kis, telegram, strategy, trade_manager)
                    state["sell_check_done"] = True

            # 5. 15:26 Sell Execution (Market/Best)
            if not state["is_holiday"]:
                if current_time >= config.TIME_SELL_EXEC and not state["sell_exec_done"]:
                    run_sell_execution(kis, telegram, strategy, trade_manager)
                    state["sell_exec_done"] = True
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            logging.info("🛑 Bot Stopped by User.")
            break
        except Exception as e:
            logging.error(f"⚠️ Main Loop Error: {e}")
            time.sleep(5)

def run_morning_analysis(kis, telegram, strategy, trade_manager):
    """08:30: Calculate RSI, Select Candidates using DB Consensus"""
    logging.info("🔍 [08:30] Starting Morning Analysis...")
    telegram.send_message("🔍 [08:30] Morning Analysis Started")

    balance = kis.get_balance()
    if not balance:
        logging.error("Failed to fetch balance.")
        return

    # Check Holdings Count
    current_holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    slots_open = config.MAX_POSITIONS - len(current_holdings)
    
    if slots_open <= 0:
        logging.info("Portfolio Full. No new buys.")
        telegram.send_message("ℹ️ Portfolio Full. No new buys.")
        return

    # NEW LOGIC: Query DB
    db = DBManager()
    today_str = get_now_kst().strftime("%Y-%m-%d")
    
    # 1. Get Low RSI Candidates
    rsi_threshold = config.RSI_BUY_THRESHOLD 
    
    low_rsi_candidates = db.get_low_rsi_candidates(today_str, threshold=rsi_threshold)
    logging.info(f"Found {len(low_rsi_candidates)} candidates with RSI < {rsi_threshold}")
    
    if not low_rsi_candidates:
        msg = f"ℹ️ No stocks with RSI < {rsi_threshold} found for {today_str}."
        logging.info(msg)
        telegram.send_message(msg)
        # We stop here because intersection will be empty anyway
        return

    # 2. Get Consensus Candidates
    consensus_codes = db.get_consensus_candidates(today_str, min_votes=4)
    logging.info(f"Found {len(consensus_codes)} candidates with 4-LLM Consensus")
    
    if not consensus_codes:
        msg = "ℹ️ No stocks with 4-LLM Consensus found."
        logging.info(msg)
        telegram.send_message(msg)
        return

    candidates = []
    
    # Intersect and Filter
    for item in low_rsi_candidates:
        code = item['code']
        name = item['name']
        
        # Check Exclusion
        if code in state["exclude_list"]:
            continue
            
        # Check Consensus
        if code not in consensus_codes:
            continue
            
        # Check Holdings
        if any(h['pdno'] == code for h in current_holdings): continue
        
        # Check Loss Cooldown
        if not trade_manager.can_buy(code):
            continue
            
        # Check Dangerous Status (API Check)
        is_dangerous, reason = kis.check_dangerous_stock(code)
        if is_dangerous:
             logging.info(f"🚫 Skipping {code}: {reason}")
             continue
        
        # If passed all checks
        candidates.append(item)
        logging.info(f"Candidate: {name} ({code}) RSI={item['rsi']:.2f}")

    # Sort by RSI (ascending)
    candidates.sort(key=lambda x: x['rsi'])
    final_buys = candidates[:slots_open]
    
    # Save to State
    for item in final_buys:
        state["buy_targets"].append({
            "code": item['code'],
            "name": item['name'],
            "rsi": item['rsi'],
            "close_yesterday": float(item['close_price']), # DB column name
            "target_qty": 0 # Calculated later
        })
    
    msg = f"✅ Analysis Done. Selected {len(final_buys)} candidates (RSI<{rsi_threshold} + 4-LLM Consensus)."
    
    if final_buys:
        msg += "\n\n📋 <b>Selected Candidates:</b>"
        for item in final_buys:
             # item keys: code, name, rsi, close_price
             msg += f"\n• {item['name']} ({item['code']}) | RSI: {item['rsi']:.2f} | Close: {item['close_price']:,.0f}"

    logging.info(msg)
    telegram.send_message(msg)

def run_pre_order(kis, telegram, trade_manager):
    """08:57: Place Limit Order"""
    logging.info("⏰ [08:57] Placing Pre-Orders...")
    telegram.send_message("⏰ [08:57] Placing Pre-Orders")
    
    if not state["buy_targets"]:
        logging.info("No targets to buy.")
        return

    balance = kis.get_balance()
    cash = balance['cash_available']
    count = len(state["buy_targets"])
    if count == 0: return

    # Use Fixed Amount from Config
    amt_per_stock = config.BUY_AMOUNT_KRW
    
    # Check if we have enough cash (Optional warning)
    total_needed = amt_per_stock * count
    if total_needed > cash:
        msg = f"⚠️ 예수금 부족! 필요: {total_needed:,.0f}원, 보유: {cash:,.0f}원. 일부 주문이 거부될 수 있습니다."
        logging.warning(msg)
        telegram.send_message(msg) 

    for target in state["buy_targets"]:
        code = target['code']
        if code in state["exclude_list"]:
            logging.info(f"🚫 Pre-Order Skipped {code} (Excluded)")
            continue

        # Fetch Expected Price
        curr = kis.get_current_price(code)
        
        if curr and int(curr.get('antc_cnpr', 0)) > 0:
            base_price = float(curr['antc_cnpr'])
        else:
            base_price = target['close_yesterday']
            
        # +1.5% as proxy for 5 ticks
        limit_price = int(base_price * 1.015) 
        limit_price = kis.get_valid_price(limit_price)
        
        qty = int(amt_per_stock / limit_price)
        if qty < 1: continue
        
        target['target_qty'] = qty # Update state
        
        # Place Order
        success, msg = kis.send_order(code, qty, side="buy", price=limit_price, order_type="00")
        if success:
            telegram.send_message(f"🚀 Pre-Order: {code} {qty}ea @ {limit_price}")
            # Update History (Assume filled later)
            trade_manager.update_buy(code, target['name'], get_now_kst().strftime("%Y%m%d"), limit_price, qty)
        else:
            telegram.send_message(f"❌ Pre-Order Failed {code}: {msg}")
            
        time.sleep(0.2)

last_monitor_time = 0
last_display_time = 0

def monitor_and_correct_orders(kis, telegram, trade_manager):
    """
    09:05 ~ Loop: Check Unfilled.
    """
    global last_monitor_time
    if time.time() - last_monitor_time < 60:
         return # Run every 1 min
    
    last_monitor_time = time.time()
    
    orders = kis.get_outstanding_orders()
    if not orders: return 
    
    for ord in orders:
        # Check if this is OUR buy order
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
            telegram.send_message(f"🗑️ Cancelled {code}: Price > +5%")
        else:
            # Modify to Current Price (Chase)
            order_price = float(ord['ord_unpr'])
            if order_price != current_price:
                 logging.info(f"✏️ Correcting {code} to Current Price {current_price}")
                 # Use Remainder Qty
                 rem_qty = int(ord['ord_qty']) - int(ord['ccld_qty'])
                 if rem_qty > 0:
                     kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'], rem_qty, current_price, is_cancel=False)
                     telegram.send_message(f"✏️ Modified {code} -> {current_price}")

def display_holdings_status(kis, telegram, strategy, trade_manager, force=False):
    """
    Schedule: Every hour at minute 10 (08:10, 09:10, ..., 18:10)
    """
    now = get_now_kst()
    hour = now.hour
    minute = now.minute
    
    # Condition: 
    # 1. Force (Startup) or
    # 2. Time is between 08:00 and 18:00 AND
    # 3. Minute is 10 AND
    # 4. We haven't sent for this hour yet.
    
    should_send = False
    
    if force:
        should_send = True
    elif 8 <= hour <= 18:
        if minute == 10:
             if state["last_sent_hour"] != hour:
                 should_send = True
    
    if not should_send:
        return

    # Update State
    if not force:
        state["last_sent_hour"] = hour

    # Fetch Data
    balance = kis.get_balance()
    if not balance: return
    
    holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    
    if not holdings:
        if force: logging.info("No holdings to display.")
        return
        
    msg_lines = [f"📊 Holdings Status ({now.strftime('%H:%M')})"]
    logging.info("-" * 60)
    
    # Optimization: Fetch shorter history for RSI(3) display
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
        
        days_held = trade_manager.get_holding_days(code)
        
        line = f"🔹 {name}: {curr:,.0f} (RSI: {rsi_val:.2f}) | P/L: {profit_pct:.2f}% ({days_held}d)"
        
        msg_lines.append(line)
        logging.info(line)
        
    # Send combined message
    full_msg = "\n".join(msg_lines)
    telegram.send_message(full_msg)

def run_sell_check(kis, telegram, strategy, trade_manager):
    """15:20 Sell Check"""
    logging.info("⚖️ [15:20] Checking Sell Signals...")
    telegram.send_message("⚖️ [15:20] Checking Sell Signals")
    
    balance = kis.get_balance()
    if not balance: return
    
    for h in balance['holdings']:
        qty = int(h['hldg_qty'])
        if qty == 0: continue
        
        code = h['pdno']
        name = h['prdt_name']
        
        df = kis.get_daily_ohlcv(code)
        
        # Check Exclusion
        if code in state["exclude_list"]:
             continue

        df = strategy.calculate_indicators(df)
        
        forced_sell = trade_manager.check_forced_sell(code)
        
        if strategy.check_sell_signal(code, df) or forced_sell:
             reason = "Forced (Max Holding)" if forced_sell else "Signal"
             logging.info(f"🔻 Sell Signal Identified for {name} ({code}) [{reason}]")

def run_sell_execution(kis, telegram, strategy, trade_manager):
    """15:26 Execute Market Sell for targets"""
    logging.info("💸 [15:26] Executing Market Sells...")
    telegram.send_message("💸 [15:26] Market Sell Execution")
    
    balance = kis.get_balance()
    
    for h in balance['holdings']:
        qty = int(h['hldg_qty'])
        if qty == 0: continue
        
        code = h['pdno']
        name = h['prdt_name']

        if code in state["exclude_list"]:
            logging.info(f"🚫 Sell Execution Skipped {name} ({code}) (Excluded)")
            continue
        
        # Get Data & RSI
        df = kis.get_daily_ohlcv(code)
        df = strategy.calculate_indicators(df)
        
        # Check RSI > 70 or Forced Sell
        forced_sell = trade_manager.check_forced_sell(code)
        
        if strategy.check_sell_signal(code, df) or forced_sell:
             reason = "Forced" if forced_sell else "Signal"
             # Execute Market Sell (01)
             success, msg = kis.send_order(code, qty, side="sell", price=0, order_type="01")
             if success:
                 telegram.send_message(f"👋 Sold {name} ({reason}): {msg}")
                 
                 # Calculate P/L for History
                 curr = float(h['prpr'])
                 avg = float(h['pchs_avg_pric'])
                 if avg > 0:
                     pnl_pct = (curr - avg) / avg * 100
                 else:
                     pnl_pct = 0.0
                     
                 trade_manager.update_sell(code, name, get_now_kst().strftime("%Y%m%d"), curr, qty, pnl_pct)
             else:
                 telegram.send_message(f"❌ Sell Failed {name}: {msg}")

if __name__ == "__main__":
    main()
