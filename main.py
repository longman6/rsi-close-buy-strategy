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
import ast


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
    "sell_analysis_done": False,
    "sell_exec_done": False,
    "buy_analysis_done": False,
    "buy_exec_done": False,
    "trade_sync_done": False,
    "buy_targets": [], # List of dict: {code, rsi, close_price, name}
    "sell_targets": [], # List of dict: {code, name, reason}
    "last_reset_date": None,
    "is_holiday": False,
    "exclude_list": set(),
    "last_sent_hour": -1 
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
        logging.info("🔄 Resetting Daily State (RSI 5 Close-Buy Mode)...")
        state["sell_analysis_done"] = False
        state["sell_exec_done"] = False
        state["buy_analysis_done"] = False
        state["buy_exec_done"] = False
        state["trade_sync_done"] = False
        state["buy_targets"] = []
        state["sell_targets"] = []
        state["exclude_list"] = load_exclusion_list(kis)
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

def get_kosdaq150_universe():
    """Fetch KOSDAQ 150 tickers. Prioritizes local file."""
    fallback_file = "data/kosdaq150_list.txt"
    if os.path.exists(fallback_file):
        universe = []
        try:
            with open(fallback_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.endswith(','): line = line[:-1]
                    if not line: continue
                    try:
                        item = ast.literal_eval(line)
                        universe.append(item)
                    except: pass
            if universe: return universe
        except Exception as e:
            logging.error(f"File Load Error: {e}")

    try:
        from pykrx import stock
        tickers = stock.get_index_portfolio_deposit_file("2203") # KOSDAQ 150
        universe = []
        for ticker in tickers:
            name = stock.get_market_ticker_name(ticker)
            universe.append({'code': ticker, 'name': name})
        return universe
    except Exception as e:
        logging.error(f"PyKRX Universe Fetch Error: {e}")
        return []


def display_holdings_status(kis, telegram, strategy, trade_manager, db_manager, force=False):
    """주기적으로 현재 잔고 및 포지션 상태를 출력 (매시 10분 또는 force=True)"""
    now = get_now_kst()
    if not force and now.minute != 10:
        return

    # 중복 전송 방지 (같은 시간에 한 번만)
    current_hour_str = now.strftime("%Y-%m-%d %H")
    if not force and state.get('last_sent_hour') == current_hour_str:
        return
        
    logging.info("📊 Fetching Holdings Status...")
    balance = kis.get_balance()
    if not balance:
        logging.error("Failed to fetch balance for status display.")
        return

    holdings = balance.get('holdings', [])
    total_asset = float(balance.get('total_amt', 0))
    cash_balance = float(balance.get('dnca_tot_amt', 0)) # 예수금총액 or prvs_rcdl_excg_amt(가수도)
    
    # KIS API 필드명에 따라 다를 수 있음. 안전하게 처리
    real_total = float(balance.get('tot_evlu_amt', 0)) # 총평가금액
    if real_total == 0: real_total = total_asset

    msg = f"💰 [Status] Total: {real_total:,.0f} KRW | Cash: {cash_balance:,.0f} KRW\n📦 Holdings: {len(holdings)} stocks"
    
    for h in holdings:
        name = h['prdt_name']
        code = h['pdno']
        qty = int(h['hldg_qty'])
        profit_rate = float(h['evlu_pfls_rt'])
        current_price = float(h['prpr'])
        
        entry = trade_manager.get_trade(code)
        days_held = "?"
        if entry:
             from datetime import datetime
             buy_date = datetime.strptime(entry['buy_date'], "%Y%m%d")
             days_held = (now - pytz.timezone('Asia/Seoul').localize(buy_date)).days

        msg += f"\n• {name}: {qty}주 | {profit_rate:+.2f}% | D+{days_held}"

    logging.info(msg)
    telegram.send_message(msg)
    
    if not force:
        state['last_sent_hour'] = current_hour_str


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
    logging.info(f"📅 Daily State: Sell(Anal={state['sell_analysis_done']}, Exec={state['sell_exec_done']}) | Buy(Anal={state['buy_analysis_done']}, Exec={state['buy_exec_done']})")

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

            if not state["is_holiday"]:
                # 1. 08:30 Morning Sell Analysis (Yesterday's signals)
                if current_time >= config.TIME_MORNING_ANALYSIS and current_time < config.TIME_PRE_ORDER:
                    if not state["sell_analysis_done"]:
                        run_morning_sell_analysis(kis, telegram, strategy, trade_manager)
                        state["sell_analysis_done"] = True

                # 2. 08:50 Morning Sell Execution (Market Sell at Open)
                if current_time >= config.TIME_PRE_ORDER and current_time < config.TIME_ORDER_CHECK:
                    if not state["sell_exec_done"]:
                        run_morning_sell_execution(kis, telegram, trade_manager)
                        state["sell_exec_done"] = True

                # 3. Evening Buy Analysis (Analyze for Close Buy)
                # 모의투자(kis.is_mock)일 경우 Rate Limit 대응을 위해 분석 시간을 15:00으로 앞당김
                buy_anal_start_time = "15:00" if kis.is_mock else config.TIME_SELL_CHECK
                if current_time >= buy_anal_start_time and current_time < config.TIME_SELL_EXEC:
                    if not state["buy_analysis_done"]:
                        run_evening_buy_analysis(kis, telegram, strategy, trade_manager, db_manager)
                        state["buy_analysis_done"] = True

                # 4. 15:20 Evening Buy Execution (Execute Market/Best Buy for Close)
                if current_time >= config.TIME_SELL_EXEC and current_time < config.TIME_TRADE_SYNC:
                    if not state["buy_exec_done"]:
                        run_evening_buy_execution(kis, telegram, trade_manager)
                        state["buy_exec_done"] = True

                # 5. 15:40 Sync Trades
                if current_time >= config.TIME_TRADE_SYNC and not state["trade_sync_done"]:
                    sync_trades_at_close(kis, telegram, trade_manager)
                    state["trade_sync_done"] = True
            
            # Periodic Holdings Display (XX:10)
            display_holdings_status(kis, telegram, strategy, trade_manager, db_manager)
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            logging.info("🛑 Bot Stopped by User.")
            logging.error(f"⚠️ Main Loop Error: {e}")
            time.sleep(5)

def run_morning_sell_analysis(kis, telegram, strategy, trade_manager):
    """08:30: 전일 종가 기준 매도 조건 체크"""
    logging.info("🔍 [08:30] Morning Sell Analysis Starting...")
    
    balance = kis.get_balance()
    if not balance: return

    for h in balance['holdings']:
        qty = int(h['hldg_qty'])
        if qty <= 0: continue
        
        code = h['pdno']
        name = h['prdt_name']
        
        if code in state["exclude_list"]: continue

        # 전일 종가 데이터 확인
        df = kis.get_daily_ohlcv(code)
        if df.empty: continue
            
        df = strategy.calculate_indicators(df)
        
        # 신호 체크
        forced_sell = trade_manager.check_forced_sell(code, df=df)
        sell_signal = strategy.check_sell_signal(code, df)
        
        if sell_signal or forced_sell:
            reason = "RSI_EXIT" if sell_signal else "TIME_EXIT"
            state["sell_targets"].append({"code": code, "name": name, "reason": reason, "qty": qty})
            logging.info(f"🔻 Sell identified: {name} ({code}) - {reason}")

    msg = f"✅ Sell Analysis Done. Targets: {len(state['sell_targets'])} stocks."
    if state["sell_targets"]:
        msg += "\n📋 Targets: " + ", ".join([f"{t['name']}({t['reason']})" for t in state["sell_targets"]])
    logging.info(msg)
    telegram.send_message(msg)

def run_morning_sell_execution(kis, telegram, trade_manager):
    """08:50: 매도 타겟 시장가(시가) 매도 주문"""
    if not state["sell_targets"]:
        logging.info("No targets to sell this morning.")
        return

    logging.info(f"💸 [08:50] Executing Market Sells for {len(state['sell_targets'])} targets...")
    
    for target in state["sell_targets"]:
        code = target['code']
        name = target['name']
        qty = target['qty']
        
        success, msg = kis.send_order(code, qty, side="sell", price=0, order_type="01")
        if success:
            logging.info(f"👋 Sell Order: {name} ({qty}주)")
            telegram.send_message(f"👋 Sell Order: {name}\nQty: {qty}")
            trade_manager.update_sell(code, name, get_now_kst().strftime("%Y%m%d"), 0, qty, 0)
        else:
            logging.error(f"❌ Sell Failed {name}: {msg}")
            telegram.send_message(f"❌ Sell Failed: {name}\nMsg: {msg}")
        time.sleep(0.2)

def run_evening_buy_analysis(kis, telegram, strategy, trade_manager, db_manager):
    """15:10: 코스닥 150 전 종목 스캔 및 매수 조건 체크 (실시간 RSI/SMA)"""
    logging.info("🔍 [15:10] Evening Full Market Scan Starting...")
    
    balance = kis.get_balance()
    if not balance: return
    
    num_holdings = len([h for h in balance['holdings'] if int(h['hldg_qty']) > 0])
    slots_open = config.MAX_POSITIONS - num_holdings
    
    if slots_open <= 0:
        logging.info("Portfolio Full. Skipping Scan.")
        return

    universe = get_kosdaq150_universe()
    if not universe:
        logging.error("Failed to load KOSDAQ 150 universe.")
        return

    final_candidates = []
    total = len(universe)
    
    logging.info(f"Scanning {total} stocks for Buy Signal...")
    for i, item in enumerate(universe):
        code = item['code']
        name = item['name']
        
        # 1. Basic Filters
        if code in state["exclude_list"]: continue
        if any(h['pdno'] == code for h in balance['holdings'] if int(h['hldg_qty']) > 0): continue
        if not trade_manager.can_buy(code): continue
        
        # 2. Fetch OHLCV & Indicators
        # OHLCV fetching includes rate limit delay internally
        df = kis.get_daily_ohlcv(code)
        if df.empty: continue
        
        # 실시간 현재가 반영 (장 마감 전이므로 마지막 봉 업데이트)
        curr_info = kis.get_current_price(code)
        if curr_info:
            curr_p = float(curr_info['stck_prpr'])
            df.loc[df.index[-1], 'Close'] = curr_p
            
        df = strategy.calculate_indicators(df)
        if len(df) < strategy.sma_window: continue
        
        latest = df.iloc[-1]
        rsi = latest['RSI']
        sma = latest['SMA']
        close = latest['Close']
        
        # 3. Strategy Conditions (RSI <= threshold AND Close > SMA)
        if not pd.isna(rsi) and not pd.isna(sma):
            if rsi <= config.RSI_BUY_THRESHOLD and close > sma:
                # 4. Dangerous stock check (Final filter)
                is_dangerous, reason = kis.check_dangerous_stock(code)
                if not is_dangerous:
                    final_candidates.append({"code": code, "name": name, "rsi": rsi})
                    logging.info(f"🎯 Found: {name} ({code}) RSI: {rsi:.1f}, Close: {close:,.0f} > SMA: {sma:,.0f}")
                else:
                    logging.info(f"🚫 Skipping {name} ({code}): {reason}")

        if (i+1) % 10 == 0:
            logging.info(f"Progress: {i+1}/{total}...")

    # Sort by RSI (ascending)
    final_candidates.sort(key=lambda x: x['rsi'])
    state["buy_targets"] = final_candidates[:slots_open]
    
    msg = f"✅ Market Scan Done. Found {len(final_candidates)} signals. Targets: {len(state['buy_targets'])}."
    if state["buy_targets"]:
        msg += "\n📋 Targets: " + ", ".join([f"{t['name']}({t['rsi']:.1f})" for t in state["buy_targets"]])
    logging.info(msg)
    telegram.send_message(msg)

def run_evening_buy_execution(kis, telegram, trade_manager):
    """15:20: 종가 매수 주문 집행"""
    if not state["buy_targets"]: return

    balance = kis.get_balance()
    cash = float(balance.get('max_buy_amt', 0))
    amt_per_stock = config.BUY_AMOUNT_KRW
    
    logging.info(f"🛒 [15:20] Executing Close Buys...")
    for target in state["buy_targets"]:
        if cash < amt_per_stock * 0.5: break
        
        curr = kis.get_current_price(target['code'])
        if not curr: continue
        price = float(curr['stck_prpr'])
        
        qty = int(amt_per_stock / price)
        if qty < 1: continue
        
        # [Patch] Check Buyable Cash
        try:
            buyable = kis.get_buyable_cash()
            max_amt = float(buyable.get('max_buy', 0))
            expected_needed = qty * price
            
            if expected_needed > max_amt:
                logging.warning(f"⚠️ Insufficient Cash for {target['name']}. Needed: {expected_needed:.0f}, Max: {max_amt:.0f}. Adjusting qty.")
                qty = int(max_amt / price)
        except Exception as e:
            logging.error(f"⚠️ Failed to check buying power: {e}")

        if qty < 1: 
            logging.warning(f"⚠️ Qty adjusted to 0. Skipping {target['name']}.")
            continue

        success, msg = kis.send_order(target['code'], qty, side="buy", price=0, order_type="01")
        if success:
            logging.info(f"✅ Buy Order: {target['name']} ({qty}주)")
            telegram.send_message(f"✅ Buy Order: {target['name']}\nQty: {qty}")
            # cash -= (qty * price) # Recalculated nicely by get_buyable_cash each time effectively, though we might want to keep local tracking for speed if we didn't call API every time. 
            # But the patch calls API every time.
            cash -= (qty * price)
        time.sleep(0.2)

def sync_trades_at_close(kis, telegram, trade_manager):
    """15:40: 체결 기록 동기화"""
    logging.info("📝 [15:40] Syncing Trade History...")
    today_str = get_now_kst().strftime("%Y%m%d")
    trades = kis.get_period_trades(today_str, today_str) or []
    
    aggregated = {}
    for t in trades:
        code = t.get('pdno', '')
        filled_qty = int(t.get('tot_ccld_qty', 0))
        filled_amt = float(t.get('tot_ccld_amt', 0))
        if filled_qty == 0: continue
        side = 'sell' if t.get('sll_buy_dvsn_cd') == '01' else 'buy'
        if code not in aggregated: aggregated[code] = {'buy': {'qty': 0, 'amt': 0.0}, 'sell': {'qty': 0, 'amt': 0.0}, 'name': t.get('prdt_name')}
        aggregated[code][side]['qty'] += filled_qty
        aggregated[code][side]['amt'] += filled_amt

    for code, data in aggregated.items():
        if data['buy']['qty'] > 0:
            trade_manager.update_buy(code, data['name'], today_str, data['buy']['amt']/data['buy']['qty'], data['buy']['qty'])
        if data['sell']['qty'] > 0:
            trade_manager.update_sell(code, data['name'], today_str, data['sell']['amt']/data['sell']['qty'], data['sell']['qty'], 0.0)
            
    telegram.send_message("✅ Daily Trade Sync Complete.")

if __name__ == "__main__":
    main()

