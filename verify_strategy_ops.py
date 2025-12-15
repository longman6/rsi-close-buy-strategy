import sys
import os
import json
import unittest
from datetime import datetime, timedelta
import pytz

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

# Mock Config
import config
config.MAX_HOLDING_DAYS = 38
config.LOSS_COOLDOWN_DAYS = 40

# Point TradeManager to a test file
import src.trade_manager as tm
tm.HISTORY_FILE = "test_history.json"
from src.trade_manager import TradeManager

class TestTradeManager(unittest.TestCase):
    def setUp(self):
        # Create a fresh history
        self.history = {
            "holdings": {},
            "last_trade": {}
        }
        with open("test_history.json", 'w') as f:
            json.dump(self.history, f)
        
        self.tm = TradeManager()

    def tearDown(self):
        if os.path.exists("test_history.json"):
            os.remove("test_history.json")

    def test_max_holding_days(self):
        # Case 1: Held for 10 days (Safe)
        tz_kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(pytz.utc).astimezone(tz_kst)
        buy_date_safe = (today - timedelta(days=10)).strftime("%Y%m%d")
        
        self.tm.update_buy("000001", buy_date_safe)
        self.assertFalse(self.tm.check_forced_sell("000001"))
        
        # Case 2: Held for 40 days (Exceeds 38)
        buy_date_old = (today - timedelta(days=40)).strftime("%Y%m%d")
        self.tm.update_buy("000002", buy_date_old)
        
        # Verify
        # Reload to ensure persistence logic works
        tm2 = TradeManager()
        self.assertTrue(tm2.check_forced_sell("000002"))

    def test_loss_cooldown(self):
        # Case 1: Last trade was Profit
        self.tm.update_buy("P001", "20230101")
        self.tm.update_sell("P001", "20230105", 5.0) # +5%
        self.assertTrue(self.tm.can_buy("P001"))
        
        # Case 2: Last trade was Loss, but long ago (>40 days)
        tz_kst = pytz.timezone('Asia/Seoul')
        today = datetime.now(pytz.utc).astimezone(tz_kst)
        sell_date_old = (today - timedelta(days=50)).strftime("%Y%m%d")
        
        self.tm.update_buy("L001", "20230101")
        # In memory update doesn't care about buy date for sell history
        self.tm.update_sell("L001", sell_date_old, -5.0) # -5%
        self.assertTrue(self.tm.can_buy("L001"))
        
        # Case 3: Last trade was Loss, and recent (10 days ago)
        sell_date_recent = (today - timedelta(days=10)).strftime("%Y%m%d")
        
        self.tm.update_buy("L002", "20230101")
        self.tm.update_sell("L002", sell_date_recent, -10.0) # -10%
        self.assertFalse(self.tm.can_buy("L002"))

if __name__ == '__main__':
    unittest.main()
