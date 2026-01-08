import sqlite3
import os
from src.db_manager import DBManager

def check_db_columns():
    db_file = "data/stock_analysis.db"
    
    # Trigger migration via DBManager init
    print("Initialize DBManager...")
    db = DBManager(db_file)
    
    # Check columns directly
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(daily_rsi)")
        columns = {info[1]: info for info in cursor.fetchall()}
        
        print(f"Columns in daily_rsi: {list(columns.keys())}")
        
        if 'sma' in columns and 'is_above_sma' in columns:
            print("✅ SUCCESS: 'sma' and 'is_above_sma' columns exist.")
        else:
            print("❌ FAILURE: Missing new columns.")

if __name__ == "__main__":
    check_db_columns()
