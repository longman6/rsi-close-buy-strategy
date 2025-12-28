import sys
import os
import sqlite3
import datetime

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.db_manager import DBManager
from src.trade_manager import TradeManager
from src.utils import get_now_kst

def verify_trade_db():
    print("🧪 Verifying Trade Logging to DB...")
    
    # Setup test DB
    test_db_file = "test_trade_logging.db"
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    db = DBManager(db_file=test_db_file)
    tm = TradeManager(db=db)
    
    # 1. Test Buy
    code = "005930"
    name = "삼성전자"
    date_str = get_now_kst().strftime("%Y%m%d")
    price = 70000.0
    qty = 10
    
    print(f"  - Testing update_buy for {name}...")
    tm.update_buy(code, name, date_str, price, qty)
    
    # Verify in DB
    with sqlite3.connect(test_db_file) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_history WHERE code = ? AND action = 'BUY'", (code,))
        row = cursor.fetchone()
        
        assert row is not None, "BUY record not found in DB"
        assert row['name'] == name
        assert row['price'] == price
        assert row['quantity'] == qty
        assert row['amount'] == price * qty
        print("  ✅ BUY record verified in DB.")

    # 2. Test Sell
    sell_price = 72000.0
    pnl_pct = 2.85
    
    print(f"  - Testing update_sell for {name}...")
    tm.update_sell(code, name, date_str, sell_price, qty, pnl_pct)
    
    # Verify in DB
    with sqlite3.connect(test_db_file) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_history WHERE code = ? AND action = 'SELL'", (code,))
        row = cursor.fetchone()
        
        assert row is not None, "SELL record not found in DB"
        assert row['price'] == sell_price
        assert row['pnl_pct'] == pnl_pct
        print("  ✅ SELL record verified in DB.")

    # Cleanup
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
    
    # Also cleanup JSON if created during test (TradeManager creates/updates trade_history.json)
    # But TradeManager inits with existing if it exists. 
    # To keep test clean, we might want to mock HISTORY_FILE but it's okay for a quick verification.
    
    print("🎉 Trade Logging Verification Passed!")

if __name__ == "__main__":
    try:
        verify_trade_db()
    except Exception as e:
        print(f"❌ Verification Failed: {e}")
        sys.exit(1)
