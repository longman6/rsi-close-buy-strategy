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
        logging.FileHandler("logs/trade_log.txt", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Global State Variables (Reset daily)
state = {
    "analysis_done": False,
    "pre_order_done": False,
    "second_order_done": False,  # 2차 주문 완료 플래그
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
    exclude_file = "data/exclude_list.txt"
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
        state["second_order_done"] = False
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
    if not os.path.exists("data/trade_history.json"):
        logging.info("📜 trade_history.json not found. Parsing local trade logs...")
        parse_trade_log.parse_log()
    else:
        logging.info("📜 data/trade_history.json found. Loading existing history.")
    db_manager = DBManager()
    trade_manager = TradeManager(db=db_manager)

    # Disable Telegram in Mock Mode? User might still want logs.
    # User requested control via .env ENABLE_NOTIFICATIONS, so we respect that.
    if kis.is_mock and telegram.enabled:
         logging.info("🤖 Bot Loop Started (Mock Mode). Waiting for schedule...")
         telegram.send_message("🤖 Bot Loop Started (Mock Mode). Waiting for schedule...")
    elif telegram.enabled:
         logging.info("🤖 Bot Loop Started (Real Mode). Waiting for schedule...")
         telegram.send_message("🤖 Bot Loop Started (Real Mode). Waiting for schedule...")

    # FORCE Initial State Reset (to load exclusion list and check holiday)
    reset_daily_state(kis)

    # Log Startup Time in KST
    startup_kst = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"⏰ KST Clock Check: {startup_kst}")
    logging.info(f"📅 Daily State: Analysis={state['analysis_done']}, PreOrder={state['pre_order_done']}")

            # Initial Status Display (Run once on startup)
    logging.info("📊 Checking Initial Holdings...")
    logging.info("📊 Checking Initial Holdings...")
    try:
        display_holdings_status(kis, telegram, strategy, trade_manager, db_manager, force=True)
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
                if current_time >= config.TIME_MORNING_ANALYSIS and current_time <= config.TIME_MORNING_ANALYSIS_END:
                    if not state["analysis_done"]:
                        run_morning_analysis(kis, telegram, strategy, trade_manager)
                        state["analysis_done"] = True
                elif current_time > config.TIME_MORNING_ANALYSIS_END and not state["analysis_done"]:
                    # If started late (after 08:50), skip analysis
                    logging.info(f"⏭️ [Skip] Morning Analysis window passed ({current_time}).")
                    state["analysis_done"] = True

            # 2. 08:57 Pre-Market Order (1차 주문)
            # Window: 08:57 ~ 09:10
            if not state["is_holiday"]:
                if current_time >= config.TIME_PRE_ORDER and current_time <= config.TIME_PRE_ORDER_END:
                    if not state["pre_order_done"]:
                        run_pre_order(kis, telegram, trade_manager)
                        state["pre_order_done"] = True
                elif current_time > config.TIME_PRE_ORDER_END and not state["pre_order_done"]:
                    # If started late, skip pre-order
                    logging.info(f"⏭️ [Skip] Pre-Order window passed ({current_time}).")
                    state["pre_order_done"] = True

            # 2.5. 09:30 Second Order (2차 주문)
            if not state["is_holiday"]:
                if current_time >= config.SECOND_ORDER_TIME and not state["second_order_done"]:
                    if state["pre_order_done"]:  # Only if first order was placed
                        run_second_order(kis, telegram, trade_manager)
                        state["second_order_done"] = True
                    else:
                        logging.warning("⚠️  Skipping second order: First order not completed")
                        state["second_order_done"] = True  # Mark as done to prevent retrying

            # 3. 09:05 ~ Order Verification & Correction Loop
            # This runs repeatedly every minute starting from 09:05 until ... say 15:00?
            if not state["is_holiday"]:
                if current_time >= config.TIME_ORDER_CHECK and current_time < config.TIME_SELL_CHECK:
                     monitor_and_correct_orders(kis, telegram, trade_manager)

            # Periodic Display of Holdings (Scheduled Hourly at XX:10)
            # Periodic Display of Holdings (Scheduled Hourly at XX:10)
            display_holdings_status(kis, telegram, strategy, trade_manager, db_manager)

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
    
    low_rsi_candidates = db.get_low_rsi_candidates(today_str, threshold=rsi_threshold, min_sma_check=True)
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
    
    msg = f"✅ Analysis Done. Selected {len(final_buys)} candidates (RSI &lt; {rsi_threshold} + 4-LLM Consensus)."
    
    if final_buys:
        msg += "\n\n📋 <b>Selected Candidates:</b>"
        for item in final_buys:
             # item keys: code, name, rsi, close_price
             msg += f"\n• {item['name']} ({item['code']}) | RSI: {item['rsi']:.2f} | Close: {item['close_price']:,.0f}"

    logging.info(msg)
    telegram.send_message(msg)

def run_pre_order(kis, telegram, trade_manager):
    """08:57: Place First Stage Orders with lower premium (+0.3%)"""
    first_order_ratio = config.FIRST_ORDER_RATIO
    first_order_premium = config.FIRST_ORDER_PREMIUM
    logging.info(f"⏰ [08:57] 1차 주문 ({int(first_order_ratio*100)}%, +{first_order_premium*100:.1f}% 프리미엄)...")
    telegram.send_message(f"⏰ [08:57] 1차 주문 시작 (전체의 {int(first_order_ratio*100)}%, 낮은 가격 전략)")

    if not state["buy_targets"]:
        logging.info("No targets to buy.")
        return

    balance = kis.get_balance()
    cash = float(balance.get('max_buy_amt', 0))
    count = len(state["buy_targets"])
    if count == 0: return

    # Use Fixed Amount from Config
    amt_per_stock_config = config.BUY_AMOUNT_KRW
    amt_per_stock_first = int(amt_per_stock_config * first_order_ratio)

    current_cash = cash

    # Check if we have enough cash (Warning)
    total_needed = amt_per_stock_first * count
    if total_needed > current_cash:
        msg = f"⚠️ 1차 주문 예수금 부족 예측! 필요: {total_needed:,.0f}원, 보유: {current_cash:,.0f}원. 주문 금액을 자동으로 조정합니다."
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

        # Apply lower premium (+0.3% instead of +1.5%)
        limit_price = int(base_price * (1 + first_order_premium))
        limit_price = kis.get_valid_price(limit_price)

        # Store initial order price and time for gradual price increase monitoring
        target['initial_order_price'] = limit_price
        target['initial_order_time'] = time.time()
        
        # Check Cash for this Order (First Stage Amount)
        amt_to_use = amt_per_stock_first
        if current_cash < amt_to_use:
            amt_to_use = current_cash
            if amt_to_use < limit_price:
                telegram.send_message(f"❌ Skipping {code}: 1차 주문 예수금 절대 부족 ({int(amt_to_use):,}원)")
                continue
            logging.warning(f"📉 {code}: 예수금 부족으로 1차 주문 금액 조정 ({amt_per_stock_first:,} -> {int(amt_to_use):,}원)")

        qty = int(amt_to_use / limit_price)
        if qty < 1: continue

        # Store first order quantity separately
        target['first_order_qty'] = qty
        target['target_qty'] = qty  # Keep for compatibility

        # Place First Order
        success, msg = kis.send_order(code, qty, side="buy", price=limit_price, order_type="00")
        if success:
            telegram.send_message(
                f"🛒 1차 주문 완료 (낮은 가격 전략)\n"
                f"종목: {target['name']} ({code})\n"
                f"수량: {qty}주\n"
                f"가격: {limit_price:,}원 (+{first_order_premium*100:.1f}%)\n"
                f"기준가: {int(base_price):,}원\n"
                f"금액: {qty*limit_price:,}원"
            )
            # Update History (Assume filled later)
            trade_manager.update_buy(code, target['name'], get_now_kst().strftime("%Y%m%d"), limit_price, qty)

            # Update Local Cash Estimate (Approximate)
            order_amt = limit_price * qty
            current_cash -= order_amt
        else:
            telegram.send_message(f"❌ 1차 주문 실패 {code}: {msg}")
            
        time.sleep(0.2)

def run_second_order(kis, telegram, trade_manager):
    """09:30: Place Second Stage Orders with discount (-0.5%)"""
    if not state["buy_targets"]:
        logging.info("⏭️  No buy targets for second order")
        return

    first_order_ratio = config.FIRST_ORDER_RATIO
    second_order_ratio = 1.0 - first_order_ratio
    second_order_discount = config.SECOND_ORDER_DISCOUNT

    logging.info(f"🛒 2차 주문 ({int(second_order_ratio*100)}%, -{second_order_discount*100:.1f}% 할인)...")
    telegram.send_message(f"⏰ [{config.SECOND_ORDER_TIME}] 2차 주문 시작 (나머지 {int(second_order_ratio*100)}%, 할인 전략)")

    # Get current balance
    balance = kis.get_balance()
    if not balance:
        logging.error("❌ Failed to fetch balance for second order")
        telegram.send_message("❌ 2차 주문 실패: 잔고 조회 불가")
        return

    current_cash = float(balance.get('max_buy_amt', 0))
    logging.info(f"💰 Available Cash: {current_cash:,} KRW")

    amt_per_stock_config = config.BUY_AMOUNT_KRW
    amt_per_stock_second = int(amt_per_stock_config * second_order_ratio)

    for target in state["buy_targets"]:
        code = target['code']

        # Check if first order was placed
        if 'first_order_qty' not in target:
            logging.warning(f"⚠️  {code}: No first order found, skipping second order")
            continue

        # Fetch current price
        curr = kis.get_current_price(code)
        if not curr:
            logging.warning(f"⚠️  {code}: Failed to get current price")
            telegram.send_message(f"⚠️ {code} 2차 주문 실패: 현재가 조회 불가")
            continue

        current_price = float(curr.get('stck_prpr', 0))
        if current_price == 0:
            logging.warning(f"⚠️  {code}: Invalid current price")
            continue

        # Apply discount (-0.5%)
        discounted_price = int(current_price * (1 - second_order_discount))
        limit_price = kis.get_valid_price(discounted_price)

        # Store initial order price and time for gradual price increase monitoring
        target['second_order_initial_price'] = limit_price
        target['second_order_time'] = time.time()

        # Check if price has risen too much (>5% from yesterday)
        yesterday_close = target['close_yesterday']
        if current_price > yesterday_close * 1.05:
            pct_change = ((current_price / yesterday_close - 1) * 100)
            logging.info(f"🚫 Skipping {code} second order: Price rose >5% ({current_price:,} > {yesterday_close*1.05:,.0f})")
            telegram.send_message(
                f"🚫 2차 주문 취소\n"
                f"종목: {target['name']} ({code})\n"
                f"사유: 급등 (+{pct_change:.1f}%)\n"
                f"현재가: {int(current_price):,}원"
            )
            continue

        # Calculate second order amount
        amt_to_use = amt_per_stock_second
        if current_cash < amt_to_use:
            amt_to_use = current_cash
            if amt_to_use < limit_price:
                logging.warning(f"⚠️  {code}: Insufficient cash for second order")
                telegram.send_message(f"❌ {code} 2차 주문 불가: 예수금 부족 ({int(amt_to_use):,}원)")
                continue
            logging.warning(f"📉 {code}: 예수금 부족으로 2차 주문 금액 조정 ({amt_per_stock_second:,} -> {int(amt_to_use):,}원)")

        qty = int(amt_to_use / limit_price)
        if qty < 1:
            logging.warning(f"⚠️  {code}: Second order qty < 1")
            continue

        # Place second order
        time.sleep(0.2)
        success, msg = kis.send_order(code, qty, side="buy", price=limit_price, order_type="00")

        if success:
            target['second_order_qty'] = qty
            target['target_qty'] = target.get('first_order_qty', 0) + qty  # Update total

            telegram.send_message(
                f"🛒 2차 주문 완료 (할인 전략)\n"
                f"종목: {target['name']} ({code})\n"
                f"수량: {qty}주\n"
                f"가격: {limit_price:,}원 (현재가 대비 -{second_order_discount*100:.1f}%)\n"
                f"현재가: {int(current_price):,}원\n"
                f"총 주문: {target['target_qty']}주 (1차 {target.get('first_order_qty', 0)} + 2차 {qty})"
            )

            # Update trade manager
            trade_manager.update_buy(code, target['name'],
                                    get_now_kst().strftime("%Y%m%d"),
                                    limit_price, qty)

            current_cash -= (qty * limit_price)
            logging.info(f"✅ Second Order: {code} {qty}ea @ {limit_price:,} | Cash Left: {current_cash:,}")
        else:
            logging.error(f"❌ Second Order Failed: {code} - {msg}")
            telegram.send_message(f"❌ 2차 주문 실패: {code}\n사유: {msg}")

    state["second_order_done"] = True
    logging.info("✅ 2차 주문 완료")
    telegram.send_message("✅ 2차 주문 완료")

last_monitor_time = 0
last_display_time = 0

def monitor_and_correct_orders(kis, telegram, trade_manager):
    """
    Monitor and gradually increase unfilled order prices.
    Runs every 60 seconds.
    """
    global last_monitor_time
    now = time.time()

    if now - last_monitor_time < 60:
        return  # Run every 1 min

    last_monitor_time = now

    orders = kis.get_outstanding_orders()
    if not orders:
        # logging.info("No outstanding orders to monitor.")
        return

    logging.info(f"🔍 Monitoring {len(orders)} outstanding orders...")

    # Load price strategy settings
    increment_step = config.PRICE_INCREMENT_STEP  # +0.2%
    increment_interval = config.PRICE_INCREMENT_INTERVAL  # 300 seconds (5 min)
    max_increase = config.MAX_PRICE_INCREASE  # +2%

    for ord in orders:
        code = ord['pdno']
        order_price = float(ord['ord_unpr'])
        
        # Check current price first to get yesterday's close
        curr = kis.get_current_price(code)
        if not curr:
            logging.warning(f"⚠️ [Monitor] Failed to get price for {code}")
            continue

        current_price = float(curr.get('stck_prpr', 0))
        yesterday_close = float(curr.get('stck_sdpr', 0)) 
        
        if current_price == 0 or yesterday_close == 0:
            continue

        # Find matching target in state
        target = next((t for t in state["buy_targets"] if t['code'] == code), None)
        
        # [Recovery Logic] If target missing (e.g. Restart), create dummy target to manage it
        if not target:
            if code in state["exclude_list"]:
                continue
                
            logging.info(f"⚠️ Managing Orphaned Order for {code} (Recovered from API)")
            
            # Fetch name from current price info if possible
            name = curr.get('hts_kor_isnm', 'Unknown')
            
            target = {
                "code": code, 
                "name": name,
                "close_yesterday": yesterday_close,
                # No initial_price/time means it will hit the Fallback Logic (Chase Current Price)
            }
            state["buy_targets"].append(target) 

        # Cancel if price surged >5%
        if current_price > yesterday_close * 1.05:
            logging.info(f"🚫 {code} rose too much (>5%). Cancelling...")
            kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'], 0, 0, is_cancel=True)
            telegram.send_message(f"🗑️ Cancelled {code}: Price > +5%")
            continue

        # Determine which order this is (1st or 2nd)
        initial_price = target.get('initial_order_price')
        order_time = target.get('initial_order_time')

        # If this is a second order, use second order initial price
        if 'second_order_initial_price' in target:
            second_initial = target['second_order_initial_price']
            second_time = target.get('second_order_time')
            if abs(order_price - second_initial) < abs(order_price - initial_price):
                initial_price = second_initial
                order_time = second_time

        if not initial_price or not order_time:
            # Fallback Logic (Legacy/Orphaned if logic existed)
            rem_qty = int(ord['ord_qty']) - int(ord['ccld_qty'])
            if rem_qty > 0 and order_price != current_price:
                kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'],
                                       rem_qty, int(current_price), is_cancel=False)
                logging.info(f"✏️ Modified {code} -> {int(current_price):,} (Fallback Default)")
                telegram.send_message(f"✏️ Modified {code} -> {int(current_price):,}")
            else:
                 logging.info(f"ℹ️ [Monitor] {code}: Fallback condition not met (P:{order_price} vs C:{current_price})")
            continue

        # Calculate how many intervals have passed
        elapsed_time = now - order_time
        intervals_passed = int(elapsed_time / increment_interval)

        # Calculate target price based on intervals
        price_increase_pct = min(intervals_passed * increment_step, max_increase)
        target_price = int(initial_price * (1 + price_increase_pct))
        target_price = kis.get_valid_price(target_price)

        # Don't exceed current market price
        target_price = min(target_price, int(current_price))

        # Only revise if different from current order price
        rem_qty = int(ord['ord_qty']) - int(ord['ccld_qty'])
        
        # Debug Log
        logging.info(f"[Monitor] {code}: Ord:{order_price:.0f} Cur:{current_price:.0f} Tgt:{target_price} "
                     f"Init:{initial_price:.0f} Elast:{elapsed_time:.0f}s Inv:{intervals_passed} (+{price_increase_pct*100:.1f}%)")

        if rem_qty > 0 and target_price != int(order_price):
            logging.info(
                f"📈 Gradual increase {code}: "
                f"{int(order_price):,} → {target_price:,} "
                f"(+{price_increase_pct*100:.1f}%, interval {intervals_passed})"
            )
            kis.revise_cancel_order(ord['krx_fwdg_ord_orgno'], ord['orgn_odno'],
                                   rem_qty, target_price, is_cancel=False)

def display_holdings_status(kis, telegram, strategy, trade_manager, db_manager, force=False):
    """
    Schedule: 
      - Console Log: Every minute (approx)
      - Telegram: Every hour at minute 10 (08:10, 09:10, ..., 18:10)
    """
    now = get_now_kst()
    hour = now.hour
    minute = now.minute
    current_time_str = now.strftime("%H:%M")
    
    # --- 1. Control Console Logging Frequency (Every Minute) ---
    should_log = False
    if state.get("last_log_minute") != current_time_str:
        should_log = True
        state["last_log_minute"] = current_time_str
        
    if force: should_log = True
    
    # If we don't need to log AND don't need to send, return early
    # But wait, we need to check if we should send telegram.
    
    # --- 2. Control Telegram Frequency (Hourly at XX:10) ---
    should_send_telegram = False
    if force:
        should_send_telegram = True
    elif 8 <= hour <= 18:
        if minute == 10:
             if state["last_sent_hour"] != hour:
                 should_send_telegram = True
    
    # If neither, skip
    if not should_log and not should_send_telegram:
        return

    # Update Telegram State
    if should_send_telegram and not force:
        state["last_sent_hour"] = hour

    # Fetch Data
    balance = kis.get_balance()
    if not balance: return
    
    holdings = [h for h in balance['holdings'] if int(h['hldg_qty']) > 0]
    
    # If no holdings, maybe just return unless force?
    if not holdings:
        if force: logging.info("No holdings to display.")
        return
        
    msg_lines = [f"📊 Holdings Status ({now.strftime('%H:%M')})"]
    if should_log:
        logging.info("-" * 60)
    
    # Optimization: Fetch shorter history for RSI(3) display
    start_date = (get_now_kst() - timedelta(days=200)).strftime("%Y%m%d")
    
    for h in holdings:
        name = h['prdt_name']
        code = h['pdno']
        curr = float(h['prpr'])
        avg = float(h['pchs_avg_pric'])
        
        # Calculate RSI
        # Only fetch if we are going to log OR send
        time.sleep(0.2 if kis.is_mock else 0.1) # Brief delay
        df = kis.get_daily_ohlcv(code, start_date=start_date)
        rsi_val = 0.0
        if not df.empty:
            df = strategy.calculate_indicators(df)
            if not df.empty and 'RSI' in df.columns:
                logging.inf('df--------------------------------')
                rsi_val = df['RSI'].iloc[-1]
                logging.info(f"rsi_val  :{rsi_val}")

        
        # Profit
        profit_amt = (curr - avg) * int(h['hldg_qty'])
        profit_pct = (curr - avg) / avg * 100
        
        days_held = trade_manager.get_holding_days(code, df=df)
        
        line = f"🔹 {name}: {curr:,.0f} (RSI: {rsi_val:.2f}) | P/L: {profit_pct:.2f}% ({days_held}d) | ₩{int(profit_amt):,}"
        
        msg_lines.append(line)
        
        # LOGGING (Every Minute)
        if should_log:
            logging.info(line)
        
    # TELEGRAM (Hourly)
    if should_send_telegram:
        full_msg = "\n".join(msg_lines)
        telegram.send_message(full_msg)
        
        # Save to Trading Journal (Overwrite daily to keep latest)
        try:
             # Map KIS Totals to Journal
             # Note: 'daily_profit_loss' here will store TOTAL P/L because KIS gives Total.
             # 'daily_return_pct' stores Total Return %.
             # This is acceptable for a snapshot.
             
             db_manager.save_journal_entry(
                 date=now.strftime("%Y-%m-%d"),
                 total_balance=balance['total_asset'],
                 daily_profit_loss=balance['total_pnl'],
                 daily_return_pct=balance['total_return_rate'],
                 holdings_snapshot=full_msg
             )
        except Exception as e:
             logging.error(f"Failed to save journal entry: {e}")

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
        
        forced_sell = trade_manager.check_forced_sell(code, df=df)
        
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
        forced_sell = trade_manager.check_forced_sell(code, df=df)
        
        if strategy.check_sell_signal(code, df) or forced_sell:
             reason = "Forced" if forced_sell else "Signal"
             # Execute Market Sell (01)
             success, msg = kis.send_order(code, qty, side="sell", price=0, order_type="01")
             if success:
                 logging.info(f"👋 Sold {name} ({reason}): {msg}")
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
