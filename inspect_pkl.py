import pandas as pd
import os


files = [
    "data/historical/kosdaq150_combined_2010-01-01_2025-01-08.pkl",
    "data/historical/metadata.pkl"
]

for pkl_path in files:
    print(f"\n{'='*40}")
    if os.path.exists(pkl_path):
        print(f"Loading {pkl_path}...")
        data = pd.read_pickle(pkl_path)
        print("Type:", type(data))
        
        if isinstance(data, dict):
            keys = list(data.keys())
            print(f"Keys ({len(keys)} total):", keys[:5])
            if keys:
                first_val = data[keys[0]]
                print(f"Value type for '{keys[0]}':", type(data[keys[0]]))
                if isinstance(first_val, pd.DataFrame):
                    print(first_val.head())
                    print("Columns:", first_val.columns)
        elif isinstance(data, pd.DataFrame):
            print(data.head())
            print(data.info())
    else:
        print(f"File not found: {pkl_path}")
