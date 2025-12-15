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
tm.HISTORY_FILE = "test_history_default.json"
from src.trade_manager import TradeManager

class TestTradeManagerDefault(unittest.TestCase):
    def setUp(self):
        # Empty History (No holdings)
        self.history = { "holdings": {}, "last_trade": {} }
        with open("test_history_default.json", 'w') as f:
            json.dump(self.history, f)
        self.tm = TradeManager()

    def tearDown(self):
        if os.path.exists("test_history_default.json"):
            os.remove("test_history_default.json")

    def test_unknown_holding_is_safe(self):
        # "UNKNOWN" code is not in history
        # Should now return 0 days (Safe)
        days = self.tm.get_holding_days("UNKNOWN")
        print(f"Unknown holding days: {days}")
        
        self.assertEqual(days, 0)
        self.assertFalse(self.tm.check_forced_sell("UNKNOWN"))

if __name__ == '__main__':
    unittest.main()
