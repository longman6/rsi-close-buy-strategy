
import logging
import sys
import pandas as pd
from src.kis_client import KISClient

# Setup simple logging to see output
logging.basicConfig(level=logging.INFO)

def test_daily_ohlcv():
    print("Initializing KIS Client...")
    kis = KISClient()
    
    # Test with Samsung Electronics (005930) or a KOSDAQ leader like EcoPro BM (247540)
    # Using 005930 as a standard test case
    code = "005930" 
    # Stress Test: Call 20 times continuously
    print("\nStarting Stress Test (20 iterations)...")
    success_count = 0
    fail_count = 0
    
    import time
    
    for i in range(20):
        try:
            print(f"[{i+1}/20] Fetching...")
            # Use data range that triggers pagination (approx 2 years)
            df = kis.get_daily_ohlcv(code, start_date="20230101", end_date="20251209")
            
            if not df.empty and len(df) > 100:
                print(f"   ✅ Success. Rows: {len(df)}")
                success_count += 1
            else:
                print(f"   ❌ Failed or Empty. Rows: {len(df)}")
                fail_count += 1
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            fail_count += 1
            
        time.sleep(1.0)

    print(f"\nStress Test Finished. Success: {success_count}, Failed: {fail_count}")
                


if __name__ == "__main__":
    test_daily_ohlcv()
