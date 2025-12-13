import sys
import os
import logging
import time
# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.kis_client import KISClient

import config
# config module already loads .env and sets variables


# Setup basic logging
logging.basicConfig(level=logging.INFO)

def test_holiday_check():
    client = KISClient()
    
    # Test 1: Today (Saturday, 2025-12-13)
    # Should return False immediately without API call logic (no error logs)
    print("Testing 20251213 (Saturday)...")
    is_open_sat = client.is_trading_day("20251213")
    print(f"20251213 Open? {is_open_sat}")
    
    # Test 2: Next Monday (2025-12-15)
    # This will try to hit the API, which might fail if credentials are fake/mock is down.
    # But we just want to ensure it passes the local check.
    # We expect a network error or auth error here if credentials are bad, which is fine.
    # We mainly care about Test 1 passing silently.
    # print("\nTesting 20251215 (Monday)...")
    # We expect this to try API
    time.sleep(5)

    is_open_mon = client.is_trading_day("20251215")
    print(f"20251215 Open? {is_open_mon}")
    # try:
    #     is_open_mon = client.is_trading_day("20251211")
    #     print(f"20251215 Open? {is_open_mon}")
    # except Exception as e:
    #     print(f"Monday check failed as expected with bad creds/network: {e}")

if __name__ == "__main__":
    test_holiday_check()
