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
import os

# Setup Logging for Cron
# We will log to a file in the project directory
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'daily_analysis.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler() # Also print to stdout for cron capture
    ]
)



def get_kosdaq150_universe():
    """Fetch KOSDAQ 150 tickers using PyKRX (Index Code 2203)."""
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
        # Retain Fallback just in case
        return [
            {'code': '247540', 'name': '에코프로비엠'},
            {'code': '086520', 'name': '에코프로'},
            {'code': '028300', 'name': 'HLB'},
            {'code': '066970', 'name': '엘앤에프'},
            {'code': '403870', 'name': 'HPSP'},
            {'code': '035900', 'name': 'JYP Ent.'},
            {'code': '025980', 'name': '아난티'},
            {'code': '293490', 'name': '카카오게임즈'},
            {'code': '068270', 'name': '셀트리온제약'},
            {'code': '357780', 'name': '솔브레인'},
            {'code': '402280', 'name': '이랜텍'},
            {'code': '112040', 'name': '위메이드'}
        ]

def analyze_kosdaq150():
    # Market Day Check
    try:
        from pykrx import stock
        today_check = datetime.now().strftime("%Y%m%d")
        nearest_business_day = stock.get_nearest_business_day_in_a_week()
        
        if today_check == nearest_business_day:
            logging.info(f"Market Open Check: Today ({today_check}) is a trading day.")
            print(f"오늘은 개장일입니다. ({today_check})")
        else:
            logging.info(f"Market Closed Check: Today ({today_check}) is a holiday. Nearest: {nearest_business_day}")
            print(f"오늘은 휴장일입니다. 가장 가까운 영업일: {nearest_business_day}")
            return # Exit function
    except Exception as e:
        logging.error(f"Market Day Check Failed: {e}")
        # Proceed if check fails? Or exit? Usually safe to proceed or maybe fallback. 
        # But user wants to stop on holiday. If error, let's log and proceed or return?
        # Let's assume proceed on error to be safe, but logged.

    logging.info("🚀 Starting Daily KOSDAQ 150 Analysis (Multi-LLM)...")
    
    # Initialize
    kis = KISClient()
    strategy = Strategy()
    db = DBManager()
    ai_manager = AIManager() # New Manager
    
    universe = get_kosdaq150_universe()
    logging.info(f"Loaded {len(universe)} stocks from KOSDAQ 150.")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    for i, item in enumerate(universe):
        code = item['code']
        name = item['name']
        
        # Optimize: 250 days history
        start_dt = (datetime.now() - timedelta(days=250)).strftime("%Y%m%d")
        
        try:
            # 1. Fetch OHLCV
            # KIS Rate Limit handling
            delay = 0.5 if kis.is_mock else 0.1 
            time.sleep(delay)
            
            df = kis.get_daily_ohlcv(code, start_date=start_dt)
            if df.empty: continue
            
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
            
            # 3. AI Advice Logic
            # Query if RSI < 35
            if rsi_val is not None and rsi_val < 35:
                 logging.info(f"👀 Low RSI Candidate: {name}({code}) RSI={rsi_val:.2f}")
                 
                 # Check Danger before spending tokens
                 is_danger, reason = kis.check_dangerous_stock(code)
                 if is_danger:
                     logging.info(f"🚫 Removing Dangerous Candidate {code}: {reason}")
                     # Cleanly skipping AI calls
                 else:
                     # Prepare OHLCV Text (Last 30 days)
                     recent_df = df.tail(30)
                     ohlcv_text = recent_df[['Open', 'High', 'Low', 'Close', 'Volume', 'RSI']].to_string()

                     # Ask AI Manager (All Enabled Models)
                     logging.info(f"🤖 Asking AIs about {name}...")
                     advice_list = ai_manager.get_aggregated_advice(name, code, rsi_val, ohlcv_text)
                     
                     # Save individual advice to ai_advice table
                     for advice in advice_list:
                         model = advice.get('model')
                         specific_model = advice.get('specific_model')
                         rec = advice.get('recommendation')
                         reasoning = advice.get('reasoning')
                         prompt = advice.get('prompt')
                         
                         db.save_ai_advice(today_str, code, model, rec, reasoning, specific_model, prompt)
                         logging.info(f"   > {model} ({specific_model}): {rec}")

            # Save to DB (Main Record - Pure RSI)
            db.save_rsi_result(
                date=today_str,
                code=code,
                name=name,
                rsi=rsi_val,
                close_price=close_val
            )

            if i % 10 == 0:
                logging.info(f"Processed {i}/{len(universe)}: {name} RSI={rsi_val:.2f} (Saved to DB)")

        except Exception as e:
            logging.error(f"Error processing {code}: {e}")
            continue
            
    logging.info(f"✅ Analysis Completed. Results saved to DB for {today_str}.")

if __name__ == "__main__":
    analyze_kosdaq150()
