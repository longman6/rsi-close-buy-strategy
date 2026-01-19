import pandas as pd
import os
import glob

def compare_ticker_data(code):
    print(f"🔎 Comparing data for ticker: {code}")
    
    # 1. Load from CSV
    csv_pattern = f"data/historical/{code}_*.csv"
    csv_files = glob.glob(csv_pattern)
    if not csv_files:
        print("❌ CSV file not found.")
        return
    
    csv_path = csv_files[0]
    print(f"📄 Loading CSV: {csv_path}")
    df_csv = pd.read_csv(csv_path)
    df_csv['Date'] = pd.to_datetime(df_csv['Date'])
    df_csv.set_index('Date', inplace=True)
    
    # 2. Load from Pickle
    pkl_pattern = "data/historical/kosdaq150_combined_*.pkl"
    pkl_files = glob.glob(pkl_pattern)
    if not pkl_files:
        print("❌ Pickle file not found.")
        return
        
    pkl_path = pkl_files[0]
    print(f"🥒 Loading Pickle: {pkl_path}")
    pkl_data = pd.read_pickle(pkl_path)
    
    if code not in pkl_data:
        print(f"❌ Code {code} not found in pickle.")
        return
        
    df_pkl = pkl_data[code]
    if 'Date' in df_pkl.columns:
        df_pkl['Date'] = pd.to_datetime(df_pkl['Date'])
        df_pkl.set_index('Date', inplace=True)
    
    # 3. Compare Head/Tail and Sample
    print(f"\n--- Data Range ---")
    print(f"CSV: {df_csv.index.min()} ~ {df_csv.index.max()} (Count: {len(df_csv)})")
    print(f"PKL: {df_pkl.index.min()} ~ {df_pkl.index.max()} (Count: {len(df_pkl)})")
    
    print(f"\n--- Price Comparison (Close) ---")
    # Join on index
    merged = df_csv[['Close']].join(df_pkl[['Close']], lsuffix='_CSV', rsuffix='_PKL', how='inner')
    
    print(f"Overlapping Days: {len(merged)}")
    merged['Diff'] = merged['Close_CSV'] - merged['Close_PKL']
    merged['Diff_Abs'] = merged['Diff'].abs()
    
    # Show samples where diff is significant
    significant_diff = merged[merged['Diff_Abs'] > 0.1]
    
    if not significant_diff.empty:
        print(f"\n⚠️ Found {len(significant_diff)} rows with price mismatch!")
        print(significant_diff.head(10))
        print(significant_diff.tail(10))
        
        print("\nBiggest Difference:")
        print(significant_diff.loc[significant_diff['Diff_Abs'].idxmax()])
    else:
        print("\n✅ Prices match perfectly on overlapping dates.")
        
    # Check if Adjustments might be the cause
    # Usually yfinance provides Adjusted Close. Is 'Close' in one source raw and adjusted in other?
    


if __name__ == "__main__":
    import sys
    code = "000250"
    if len(sys.argv) > 1:
        code = sys.argv[1]
    compare_ticker_data(code)
