import logging
import time
import warnings
# Suppress pkg_resources warning from pykrx/setuptools
warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

import pandas as pd
import FinanceDataReader as fdr
import config
from datetime import datetime, timedelta
from src.kis_client import KISClient
from src.strategy import Strategy
from src.ai_manager import AIManager # New
from src.db_manager import DBManager
from src.utils import get_now_kst
import os
import ast

# Setup Logging for Cron
# We will log to a file in the project directory
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'daily_analysis.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler() # Also print to stdout for cron capture
    ]
)



def get_kosdaq150_universe():
    """Fetch KOSDAQ 150 tickers. Prioritizes local file."""
    fallback_file = "data/kosdaq150_list.txt"
    
    # 1. Try Local File First
    if os.path.exists(fallback_file):
        logging.info(f"📂 Loading universe from {fallback_file}...")
        universe = []
        try:
            with open(fallback_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.endswith(','): 
                        line = line[:-1] # Remove trailing comma
                    if not line: continue
                    
                    try:
                        item = ast.literal_eval(line)
                        universe.append(item)
                    except:
                        pass
            logging.info(f"Loaded {len(universe)} stocks from file.")
            if universe:
                return universe
        except Exception as e:
            logging.error(f"File Load Error: {e}")

    # 2. Fallback to PyKRX
    try:
        from pykrx import stock
        tickers = stock.get_index_portfolio_deposit_file("2203") # KOSDAQ 150
        
        universe = []
        for ticker in tickers:
            name = stock.get_market_ticker_name(ticker)
            universe.append({
                'code': ticker,
                'name': name
            })
            
        logging.info(f"Fetched {len(universe)} stocks from PyKRX (KOSDAQ 150).")
        return universe

    except Exception as e:
        logging.error(f"PyKRX Universe Fetch Error: {e}")

        return []



def analyze_kosdaq150():
    # Initialize KIS Client first
    kis = KISClient()
    
    # Market Day Check
    try:
        # Use KST
        today_check = get_now_kst().strftime("%Y%m%d")
        
        if kis.is_trading_day(today_check):
            logging.info(f"Market Open Check: Today ({today_check}) is a trading day.")
            print(f"오늘은 개장일입니다. ({today_check})")
        else:
            logging.info(f"Market Closed Check: Today ({today_check}) is a holiday.")
            print(f"오늘은 휴장일입니다. ({today_check})")
            return # Exit function
    except Exception as e:
        logging.error(f"Market Day Check Failed: {e}")
        # Send Emergency Telegram
        try:
            from src.telegram_bot import TelegramBot
            telegram = TelegramBot()
            telegram.send_message(f"🚨 [Urgent] Market Day Check Failed in Analysis: {e}")
        except:
            pass
        # Proceed if check fails? Or exit? Usually safe to proceed or maybe fallback. 
        # But user wants to stop on holiday. If error, let's log and proceed or return?
        # Let's assume proceed on error to be safe, but logged.

    logging.info("🚀 Starting Daily KOSDAQ 150 Analysis (Multi-LLM)...")
    
    # Initialize
    # kis = KISClient() # Already initialized above
    strategy = Strategy()
    db = DBManager()
    ai_manager = AIManager() # New Manager
    
    # Setup Telegram for Error Reporting
    from src.telegram_bot import TelegramBot
    telegram = TelegramBot()

    # [Clean Cache] Delete existing cache to ensure fresh data for new day
    import shutil
    cache_dir = "data/ohlcv"
    if os.path.exists(cache_dir):
        logging.info("🧹 Cleaning up old OHLCV cache...")
        try:
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to clean cache: {e}")
    else:
        os.makedirs(cache_dir, exist_ok=True)

    try:
        universe = get_kosdaq150_universe()
        logging.info(f"Loaded {len(universe)} stocks from KOSDAQ 150.")
        
        today_str = get_now_kst().strftime("%Y-%m-%d")
        
        for i, item in enumerate(universe):
            code = item['code']
            name = item['name']
            
            # Optimize: 250 days history
            start_dt = (get_now_kst() - timedelta(days=250)).strftime("%Y%m%d")
            
            try:
                # 1. Fetch OHLCV
                # KIS Rate Limit handling
                delay = 0.5 if kis.is_mock else 0.1 
                time.sleep(delay)
                
                df = kis.get_daily_ohlcv(code, start_date=start_dt)
                if df.empty: continue

                # [Save Cache] Save OHLCV to local file for later use
                # This drastically reduces API calls during trading hours (main.py, dashboard.py)
                try:
                    cache_dir = "data/ohlcv"
                    os.makedirs(cache_dir, exist_ok=True)
                    cache_path = os.path.join(cache_dir, f"{code}.pkl")
                    df.to_pickle(cache_path)
                except Exception as cache_err:
                    logging.warning(f"Failed to save cache for {code}: {cache_err}")
                
                # 2. Calculate Indicators
                df = strategy.calculate_indicators(df)
                if df.empty: continue
                
                # Get latest
                latest = df.iloc[-1]
                
                # Check if RSI exists
                if 'RSI' not in df.columns or pd.isna(latest['RSI']):
                    continue
                    
                # Get latest values and cast to Python native types (crucial for SQLite)
                rsi_val = float(latest.get('RSI', 0)) if pd.notna(latest.get('RSI')) else None
                close_val = float(latest.get('Close', 0))
                sma_val = float(latest.get('SMA', 0)) if pd.notna(latest.get('SMA')) else None
                
                is_above_sma = False
                if sma_val is not None and close_val > sma_val:
                    is_above_sma = True

                # Calculate is_low_rsi
                rsi_threshold = config.RSI_BUY_THRESHOLD
                is_low_rsi = False
                if rsi_val is not None and rsi_val < rsi_threshold:
                    is_low_rsi = True

                # 3. AI Advice Logic
                # Query if RSI < Threshold AND Price > SMA
                
                # DB Storage Condition: Any Low RSI (for logging/dashboard visibility)
                # But AI Cost Saving: Only high quality setups
                
                if is_low_rsi:
                     sma_status = "✅Above SMA" if is_above_sma else "❌Below SMA"
                     logging.info(f"👀 Low RSI Candidate (<{rsi_threshold}): {name}({code}) RSI={rsi_val:.2f} | {sma_status}")
                     
                     # Check Danger
                     is_danger, reason = kis.check_dangerous_stock(code)
                     if is_danger:
                         logging.info(f"🚫 Removing Dangerous Candidate {code}: {reason}")
                     
                     # Only query AI if Above SMA (User Request)
                     elif not is_above_sma:
                         logging.info(f"📉 Skipping AI Query for {name}: Below SMA")
                         
                     else:
                         # Prepare OHLCV Text (Last 30 days)
                         recent_df = df.tail(30)
                         ohlcv_text = recent_df[['Open', 'High', 'Low', 'Close', 'Volume', 'RSI', 'SMA']].to_string()

                         # 확장 지표 계산
                         extended_indicators = strategy.calculate_extended_indicators(df)

                         # Ask AI Manager (All Enabled Models)
                         logging.info(f"🤖 Asking AIs about {name}...")
                         advice_list = ai_manager.get_aggregated_advice(name, code, rsi_val, ohlcv_text, extended_indicators=extended_indicators)
                         
                         # Save individual advice to ai_advice table
                         for advice in advice_list:
                             model = advice.get('model')
                             specific_model = advice.get('specific_model')
                             rec = advice.get('recommendation')
                             reasoning = advice.get('reasoning')
                             prompt = advice.get('prompt')
                             
                             db.save_ai_advice(today_str, code, model, rec, reasoning, specific_model, prompt)
                             logging.info(f"   > {model} ({specific_model}): {rec}")

                # Save to DB (Main Record - Pure RSI + SMA + Low RSI Flag)
                db.save_rsi_result(
                    date=today_str,
                    code=code,
                    name=name,
                    rsi=rsi_val,
                    close_price=close_val,
                    sma=sma_val,
                    is_above_sma=is_above_sma,
                    is_low_rsi=is_low_rsi
                )

                if i % 10 == 0:
                    logging.info(f"Processed {i}/{len(universe)}: {name} RSI={rsi_val:.2f} (Saved to DB)")

            except Exception as e:
                logging.error(f"Error processing {code}: {e}")
                # We do NOT send telegram for individual stock errors to avoid spam, unless it's critical?
                # Usually per-stock errors are tolerable.
                continue
                
        logging.info(f"✅ Analysis Completed. Results saved to DB for {today_str}.")
        telegram.send_message(f"✅ Daily Analysis Completed for {today_str}. ({len(universe)} stocks scanned)")

    except Exception as fatal_e:
        logging.error(f"🚨 CRITICAL: Analysis Script Failed: {fatal_e}")
        try:
            telegram.send_message(f"🚨 [CRITICAL] Daily Analysis Failed!\nError: {fatal_e}")
        except:
            logging.error("Failed to send error telegram.")

if __name__ == "__main__":
    try:
        analyze_kosdaq150()
    except Exception as e:
        # Fallback for very outer scope
        logging.critical(f"Unhandled Exception: {e}")

