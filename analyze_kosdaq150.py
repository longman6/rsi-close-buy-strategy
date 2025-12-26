import logging
import time
import pandas as pd
import FinanceDataReader as fdr
import config
from datetime import datetime, timedelta
from src.kis_client import KISClient
from src.strategy import Strategy
from src.gemini_client import GeminiClient
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
    """Fetch KOSDAQ 150 tickers with names."""
    try:
        df_krx = fdr.StockListing('KOSDAQ')
        if 'Marcap' in df_krx.columns:
            df_krx = df_krx.sort_values(by='Marcap', ascending=False)
            
        # Exclude Admin Issues
        if 'Dept' in df_krx.columns:
            df_krx = df_krx[~df_krx['Dept'].astype(str).str.contains('관리', na=False)]
            
        # Top 150
        top_150 = df_krx.head(150)
        
        universe = []
        for _, row in top_150.iterrows():
            universe.append({
                'code': str(row['Code']),
                'name': row['Name']
            })
        return universe
    except Exception as e:
        logging.error(f"Universe Fetch Error: {e}")
        return []

def analyze_kosdaq150():
    logging.info("🚀 Starting Daily KOSDAQ 150 Analysis...")
    
    # Initialize
    kis = KISClient()
    strategy = Strategy()
    db = DBManager()
    
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
            delay = 0.5 if kis.is_mock else 0.1 # Faster than before since we are just dumping
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
            date_val = latest.get('Date', pd.NaT)
            
            # Format Date if it exists in column, else use today
            # strategy.calculate_indicators might preserve index or columns. 
            # Usually KIS get_daily_ohlcv returns Date as index or column?
            # Based on previous code, let's assume we can get it or just use today.
            # Actually dashboard uses today_str usually.
            # Format Date if it exists
            # (date_val is not used in save_rsi_result as we pass today_str, but good to have)
            
            # Save to DB
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
