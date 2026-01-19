import pandas as pd
import os
import glob
import ast

def get_kosdaq150_codes():
    filename = 'data/kosdaq150_list.txt'
    codes = []
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    codes.append(data['code'])
                except:
                    pass
    return codes

def compare_all():
    codes = get_kosdaq150_codes()
    print(f"Target Tickers: {len(codes)}")
    
    # Load PKL once
    pkl_files = glob.glob("data/historical/kosdaq150_combined_*.pkl")
    if not pkl_files:
        print("No PKL file found.")
        return
    
    pkl_path = pkl_files[0]
    print(f"Loading PKL: {pkl_path}")
    pkl_data = pd.read_pickle(pkl_path)
    
    mismatch_count = 0
    missing_csv = 0
    missing_pkl = 0
    
    csv_files = glob.glob("data/historical/*.csv")
    csv_map = {}
    for f in csv_files:
        basename = os.path.basename(f)
        code = basename.split('_')[0]
        csv_map[code] = f
        
    for code in codes:
        # Load CSV
        if code not in csv_map:
            # print(f"[{code}] Missing CSV")
            missing_csv += 1
            continue
            
        csv_path = csv_map[code]
        try:
            df_csv = pd.read_csv(csv_path)
        except:
             print(f"[{code}] CSV Load Error")
             continue

        if 'Date' in df_csv.columns:
            df_csv['Date'] = pd.to_datetime(df_csv['Date'])
            df_csv.set_index('Date', inplace=True)
            
        # Load PKL
        if code not in pkl_data:
            # print(f"[{code}] Missing in PKL")
            missing_pkl += 1
            continue
            
        df_pkl = pkl_data[code]
        if 'Date' in df_pkl.columns:
            df_pkl['Date'] = pd.to_datetime(df_pkl['Date'])
            df_pkl.set_index('Date', inplace=True)
            
        # Compare Close
        common_idx = df_csv.index.intersection(df_pkl.index)
        if common_idx.empty:
            print(f"[{code}] No overlapping dates")
            mismatch_count += 1
            continue
            
        s_csv = df_csv.loc[common_idx, 'Close']
        s_pkl = df_pkl.loc[common_idx, 'Close']
        
        diff = (s_csv - s_pkl).abs()
        max_diff = diff.max()
        
        # Check Length / Start Date
        len_csv = len(df_csv)
        len_pkl = len(df_pkl)
        start_csv = df_csv.index.min()
        start_pkl = df_pkl.index.min()
        
        if len_csv != len_pkl:
             print(f"[{code}] ⚠️ Length Mismatch! CSV: {len_csv}, PKL: {len_pkl}")
             mismatch_count += 1
        elif start_csv != start_pkl:
             print(f"[{code}] ⚠️ Start Date Mismatch! CSV: {start_csv}, PKL: {start_pkl}")
             mismatch_count += 1
        elif max_diff > 0.1: # Threshold
            print(f"[{code}] ❌ Max Diff: {max_diff:.4f} (CSV Last: {s_csv.iloc[-1]}, PKL Last: {s_pkl.iloc[-1]})")
            mismatch_count += 1
        else:
            # print(f"[{code}] ✅ Match")
            pass
            
    print(f"\nSummary:")
    print(f"Total Checked: {len(codes)}")
    print(f"Missing CSV: {missing_csv}")
    print(f"Missing PKL: {missing_pkl}")
    print(f"Mismatches: {mismatch_count}")

if __name__ == "__main__":
    compare_all()
