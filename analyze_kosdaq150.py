
import logging
import time
import pandas as pd
import FinanceDataReader as fdr
from src.kis_client import KISClient
from src.strategy import Strategy

# Setup Basic Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

def analyze_kosdaq150():
    """
    Fetch KOSDAQ 150 tickers with NAMES, calculate RSI(3),
    and save to ticker.rsi.txt.
    """
    logging.info("Starting KOSDAQ 150 RSI(3) Analysis...")

    # Initialize Components
    kis = KISClient()
    strategy = Strategy()

    # 1. Get Universe AND Names
    try:
        # We need names, so we fetch the DF directly instead of just list
        df_krx = fdr.StockListing('KOSDAQ')
        
        # Filter Logic (Same as Strategy.get_universe)
        # Sort by Marcap
        col = 'Marcap' if 'Marcap' in df_krx.columns else 'Amount'
        if col in df_krx.columns:
            df_krx = df_krx.sort_values(by=col, ascending=False)
        
        # Exclude Admin Issues
        if 'Dept' in df_krx.columns:
             df_krx = df_krx[~df_krx['Dept'].astype(str).str.contains('관리', na=False)]
             
        # Take Top 150
        top_150_df = df_krx.head(150)
        
        # Create a mapping or list of dicts
        universe = []
        for idx, row in top_150_df.iterrows():
            universe.append({
                'code': str(row['Code']), # Ensure string
                'name': row['Name']
            })
            
        logging.info(f"Loaded {len(universe)} tickers with names.")
        
    except Exception as e:
        logging.error(f"Failed to get universe with names: {e}")
        return

    results = []

    # 2. Iterate and Calculate
    # KIS Rate Limit: 20 transactions / sec (Key dependent).
    # Error "EGW00201" means exceeding global transaction limit or account limit.
    # Increasing delay to 0.2s = 5 req/s (Safe).
    
    cnt = 0
    total = len(universe)
    
    # Retry configuration
    max_retries = 3
    retry_delay_base = 1.0

    for item in universe:
        code = item['code']
        name = item['name']
        
        # Retry loop
        df = pd.DataFrame()
        for attempt in range(max_retries):
            try:
                # Optimize: Fetch only necessary history (e.g. 250 days for SMA100 + RSI)
                from datetime import datetime, timedelta
                end_dt = datetime.now()
                start_dt = end_dt - timedelta(days=250)
                
                s_date = start_dt.strftime("%Y%m%d")
                e_date = end_dt.strftime("%Y%m%d")
                
                # Fetch Daily OHLCV with optimized range
                df = kis.get_daily_ohlcv(code, start_date=s_date, end_date=e_date)
                
                if not df.empty:
                    break # Success
            except KeyboardInterrupt:
                raise
            except Exception as e:
                if attempt < max_retries - 1:
                    sleep_time = retry_delay_base * (2 ** attempt)
                    logging.warning(f"[{code}] Retry {attempt+1}/{max_retries} due to error: {e}")
                    time.sleep(sleep_time)
                else:
                    logging.error(f"[{code}] Failed after {max_retries} attempts: {e}")

        if df.empty:
            logging.warning(f"[{code} {name}] No OHLCV data.")
            continue
            
        # Calculate Indicators
        try:
            df = strategy.calculate_indicators(df)
            
            if df.empty: continue
            
            # Get latest values
            latest = df.iloc[-1]
            
            rsi_val = latest.get('RSI', None)
            close_val = latest.get('Close', 0)
            date_val = latest.get('Date', pd.NaT)
            
            # Format Date
            if pd.notna(date_val):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = "N/A"
            
            results.append({
                'code': code,
                'name': name,
                'rsi': rsi_val,
                'close': close_val,
                'date': date_str
            })
            
        except Exception as e:
            logging.error(f"Error processing {code} {name}: {e}")
            
        cnt += 1
        if cnt % 10 == 0:
            logging.info(f"Processed {cnt}/{total}...")
        
        # Rate Limit Buffer
        # Condition: Mock (1.5s) vs Real (0.2s - KIS Rate limit is ~20/s usually)
        delay = 1.5 if kis.is_mock else 0.2
        time.sleep(delay) 

    # Sort by RSI ascending (Lowest RSI first), pushing NaNs to the end
    # Sort by RSI ascending (Lowest RSI first), pushing NaNs to the end
    # Fix: Ensure second element is always comparable. If RSI is None/NaN, use 0 (or anything, since first element handles order)
    results.sort(key=lambda x: (x['rsi'] is None or pd.isna(x['rsi']), x['rsi'] if x['rsi'] is not None and not pd.isna(x['rsi']) else 0))

    # 3. Save to File
    output_file = "ticker.rsi.txt"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            # Header
            f.write("Ticker,Name,RSI(3),Close,Date\n")
            for res in results:
                rsi_str = f"{res['rsi']:.2f}" if pd.notna(res['rsi']) else "NaN"
                close_str = f"{int(res['close'])}" # Raw number for CSV compatibility
                clean_name = res['name'].replace(',', '') 
                f.write(f"{res['code']},{clean_name},{rsi_str},{close_str},{res['date']}\n")
                
        logging.info(f"✅ Saved results to {output_file} ({len(results)} stocks)")
        
    except Exception as e:
        logging.error(f"Failed to write file: {e}")

if __name__ == "__main__":
    analyze_kosdaq150()
