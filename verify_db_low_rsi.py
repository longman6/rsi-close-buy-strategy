import sqlite3
import os
from src.db_manager import DBManager

def check_db_columns():
    db_file = "data/stock_analysis.db"
    
    # Trigger migration
    print("Initialize DBManager...")
    DBManager(db_file)
    
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(daily_rsi)")
        columns = {info[1] for info in cursor.fetchall()}
        
        print(f"Columns: {columns}")
        
        if 'is_low_rsi' in columns:
            print("✅ SUCCESS: 'is_low_rsi' column exists.")
        else:
            print("❌ FAILURE: 'is_low_rsi' column missing.")

if __name__ == "__main__":
    check_db_columns()
