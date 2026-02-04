import unittest
from unittest.mock import MagicMock, patch
import os
import pandas as pd
from src.kis_client import KISClient

class TestOHLCVRefresh(unittest.TestCase):
    def setUp(self):
        self.kis = KISClient()
        self.kis.is_mock = True

    @patch('os.remove')
    @patch('src.kis_client.os.path.exists')
    @patch('src.kis_client.pd.DataFrame.to_pickle')
    @patch('src.kis_client.KISClient.get_daily_ohlcv')
    def test_refresh_ohlcv_cache(self, mock_get_ohlcv, mock_to_pickle, mock_exists, mock_remove):
        # Setup
        universe = [{'code': '000660', 'name': 'SK Hynix'}]
        mock_exists.return_value = True # File exists to trigger delete
        
        # Mock DF return
        mock_df = pd.DataFrame({'Date': ['2024-01-01'], 'Close': [1000]})
        mock_get_ohlcv.return_value = mock_df

        # Execution
        self.kis.refresh_ohlcv_cache(universe)

        # Verification
        # 1. os.remove called?
        mock_remove.assert_called_with('data/ohlcv/000660.pkl')
        
        # 2. get_daily_ohlcv called?
        mock_get_ohlcv.assert_called()
        
        # 3. to_pickle called?
        mock_to_pickle.assert_called_with('data/ohlcv/000660.pkl')

if __name__ == '__main__':
    unittest.main()
