import os
import logging
from src.kis_client import KISClient
from src.strategy import Strategy
from src.trade_manager import TradeManager
import main 
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd

# Configure Logging to suppress output
logging.basicConfig(level=logging.CRITICAL)

class TestExclusion(unittest.TestCase):
    def setUp(self):
        # Create temporary exclude file
        with open("exclude_list.txt", "w") as f:
            f.write("005930\n") # Exclude Samsung Electronics
            f.write("035420\n") # Exclude Naver
            
        # Mock State
        main.state["exclude_list"] = main.load_exclusion_list()
        main.state["buy_targets"] = []
        
        self.kis = MagicMock(spec=KISClient)
        self.kis.is_mock = True
        self.slack = MagicMock()
        self.trade_manager = MagicMock(spec=TradeManager)
        self.strategy = MagicMock(spec=Strategy)
        
    def tearDown(self):
        if os.path.exists("exclude_list.txt"):
            os.remove("exclude_list.txt")

    def test_load_exclusion_list(self):
        excluded = main.load_exclusion_list()
        self.assertIn("005930", excluded)
        self.assertIn("035420", excluded)
        self.assertNotIn("000660", excluded)

    def test_morning_analysis_exclusion(self):
        # Setup Universe
        self.strategy.get_universe.return_value = ["005930", "000660"] # Excluded, Valid
        self.kis.get_balance.return_value = {'holdings': []}
        self.trade_manager.can_buy.return_value = True
        
        # Mock Data
        mock_df = pd.DataFrame({'close': [10000]})
        self.kis.get_daily_ohlcv.return_value = mock_df
        self.strategy.calculate_indicators.return_value = mock_df
        
        # Mock analyze_stock to return signal for valid stock
        def analyze_side_effect(code, df):
            if code == "000660":
                return {'code': '000660', 'rsi': 30, 'close': 10000}
            return None
        self.strategy.analyze_stock.side_effect = analyze_side_effect
        
        main.run_morning_analysis(self.kis, self.slack, self.strategy, self.trade_manager)
        
        # Verify result
        targets = main.state["buy_targets"]
        target_codes = [t['code'] for t in targets]
        
        self.assertIn("000660", target_codes)
        self.assertNotIn("005930", target_codes)
        print("✅ Morning Analysis Exclusion Verified")

    def test_pre_order_exclusion(self):
        # Setup Buy Targets
        main.state["buy_targets"] = [
            {"code": "005930", "rsi": 30, "close_yesterday": 60000, "target_qty": 10},
            {"code": "000660", "rsi": 30, "close_yesterday": 90000, "target_qty": 10}
        ]
        
        self.kis.get_balance.return_value = {'cash_available': 100000000}
        self.kis.get_current_price.return_value = {'antc_cnpr': '10000'}
        self.kis.get_valid_price.return_value = 10000
        self.kis.send_order.return_value = (True, "Success")
        
        main.run_pre_order(self.kis, self.slack, self.trade_manager)
        
        # Verify send_order called ONLY for 000660
        calls = self.kis.send_order.call_args_list
        sent_codes = [c[0][0] for c in calls] # Arg 0 is code
        
        self.assertIn("000660", sent_codes)
        self.assertNotIn("005930", sent_codes)
        print("✅ Pre-Order Exclusion Verified")

    def test_sell_execution_exclusion(self):
        # Setup Holdings
        self.kis.get_balance.return_value = {
            'holdings': [
                {'pdno': '005930', 'prdt_name': 'Samsung', 'hldg_qty': '10', 'prpr': '70000', 'pchs_avg_pric': '60000'},
                {'pdno': '000660', 'prdt_name': 'Hynix', 'hldg_qty': '10', 'prpr': '120000', 'pchs_avg_pric': '100000'}
            ]
        }
        
        # Mock Data
        mock_df = pd.DataFrame({'close': [10000], 'RSI': [80.0]}) # Add RSI column
        self.kis.get_daily_ohlcv.return_value = mock_df
        self.strategy.calculate_indicators.return_value = mock_df

        # Force Sell Signal for BOTH
        self.strategy.check_sell_signal.return_value = True
        self.trade_manager.check_forced_sell.return_value = False
        self.kis.send_order.return_value = (True, "Success")
        
        # Pass strategy dependency
        main.run_sell_execution(self.kis, self.slack, self.strategy, self.trade_manager)
        
        # Verify Sell Order
        calls = self.kis.send_order.call_args_list
        sent_codes = [c[0][0] for c in calls]
        
        self.assertIn("000660", sent_codes)
        self.assertNotIn("005930", sent_codes)
        print("✅ Sell Execution Exclusion Verified")

if __name__ == '__main__':
    unittest.main()

