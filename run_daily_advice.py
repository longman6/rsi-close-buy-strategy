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

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
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

def run_daily_advice():
    # Initialize
    kis = KISClient()
    strategy = Strategy()
    gemini = GeminiClient()
    db = DBManager()
    
    universe = get_kosdaq150_universe()
    logging.info(f"Loaded {len(universe)} stocks from KOSDAQ 150.")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Threshold from config (e.g., 35)
    rsi_threshold = config.RSI_BUY_THRESHOLD
    
    count_asked = 0
    
    for item in universe:
        code = item['code']
        name = item['name']
        
        # 1. Calculate RSI
        # Fetch data
        # Optimize: 200 days history enough
        start_dt = (datetime.now() - timedelta(days=200)).strftime("%Y%m%d")
        
        try:
            # Add small delay if mock to avoid overload (though mock is fast, network errs happen)
            time.sleep(0.5 if kis.is_mock else 0.2)
            
            df = kis.get_daily_ohlcv(code, start_date=start_dt)
            if df.empty: continue
            
            df = strategy.calculate_indicators(df)
            if df.empty or 'RSI' not in df.columns: continue
            
            current_rsi = df['RSI'].iloc[-1]
            
            # 2. Filter: RSI < Threshold
            if current_rsi < rsi_threshold:
                logging.info(f"👀 Candidate Found: {name}({code}) RSI={current_rsi:.2f} < {rsi_threshold}")
                
                # Double Check Dangerous Status
                is_danger, reason = kis.check_dangerous_stock(code)
                if is_danger:
                    logging.info(f"🚫 Removing Dangerous Candidate {code}: {reason}")
                    continue
                
                # 3. Ask Gemini
                logging.info(f"🤖 Asking Gemini about {name}...")
                advice = gemini.get_buy_advice(name, code, current_rsi)
                
                recommendation = advice.get("recommendation", "NO")
                reasoning = advice.get("reasoning", "Analysis Failed")
                
                # 4. Save to DB
                db.save_advice(
                    date=today_str,
                    code=code,
                    name=name,
                    rsi=current_rsi,
                    recommendation=recommendation,
                    reasoning=reasoning
                )
                
                count_asked += 1
                
                # Sleep between Gemini calls to be polite/safe
                time.sleep(2)
                
        except Exception as e:
            logging.error(f"Error processing {code}: {e}")
            continue

    logging.info(f"✅ Daily Advice Job Completed. Gemini Consulted: {count_asked} times.")

if __name__ == "__main__":
    run_daily_advice()
