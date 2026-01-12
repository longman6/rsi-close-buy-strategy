import sqlite3
import os
import sys

# Paths
OLD_DB_FILE = "data/stock_analysis.db"
NEW_USER_DB_FILE = "data/user_data.db"

def migrate():
    if not os.path.exists(OLD_DB_FILE):
        print(f"❌ Old DB not found at: {OLD_DB_FILE}")
        return

    print(f"🚀 Starting Migration: {OLD_DB_FILE} -> {NEW_USER_DB_FILE}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(NEW_USER_DB_FILE), exist_ok=True)

    try:
        # 1. Connect to both DBs
        old_conn = sqlite3.connect(OLD_DB_FILE)
        old_conn.row_factory = sqlite3.Row
        old_cursor = old_conn.cursor()

        new_conn = sqlite3.connect(NEW_USER_DB_FILE)
        new_cursor = new_conn.cursor()

        # 2. Check source tables
        tables_to_migrate = ["trade_history", "users", "trading_journal"]
        
        for table in tables_to_migrate:
            print(f"📦 Migrating table: {table}...")
            
            # Check if table exists in source
            old_cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not old_cursor.fetchone():
                print(f"   ⚠️ Source table '{table}' not found. Skipping.")
                continue

            # In New DB, create table if not exists (Schema Copy)
            # We rely on DBManager to have created schemas, OR we copy schema from old DB
            # Ideally, we should ensure schema exists. Let's copy schema from old DB.
            old_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'")
            schema_row = old_cursor.fetchone()
            if schema_row:
                create_sql = schema_row['sql']
                # Create in new DB
                new_cursor.execute(create_sql)
            
            # Copy Data
            old_cursor.execute(f"SELECT * FROM {table}")
            rows = old_cursor.fetchall()
            
            if not rows:
                print(f"   ℹ️ No data in '{table}'.")
                continue
                
            print(f"   ➡️ Copying {len(rows)} rows...")
            
            # Get column names
            col_names = rows[0].keys()
            cols_str = ", ".join(col_names)
            placeholders = ", ".join(["?"] * len(col_names))
            
            insert_sql = f"INSERT OR IGNORE INTO {table} ({cols_str}) VALUES ({placeholders})"
            
            count = 0
            for row in rows:
                new_cursor.execute(insert_sql, tuple(row))
                count += 1
            
            print(f"   ✅ Copied {count} rows.")

        new_conn.commit()
        print("\n🎉 Migration Complete!")
        
    except Exception as e:
        print(f"\n❌ Migration Failed: {e}")
    finally:
        if 'old_conn' in locals(): old_conn.close()
        if 'new_conn' in locals(): new_conn.close()

if __name__ == "__main__":
    migrate()
