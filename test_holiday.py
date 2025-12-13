from src.kis_client import KISClient
from datetime import datetime, timedelta
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)

def test_holiday():
    kis = KISClient()
    
    # Test Today (Fri)
    today = "20251212"
    is_open_today = kis.is_trading_day(today)
    print(f"Date {today} Open? {is_open_today}")
    
    # import time
    # time.sleep(2)
    
    # Test Tomorrow (Sat) -> Testing Monday to check API
    # tomorrow = "20251215"
    # is_open_tomorrow = kis.is_trading_day(tomorrow)
    # print(f"Date {tomorrow} Open? {is_open_tomorrow}")
    
    # Debug Raw
    path = "/uapi/domestic-stock/v1/quotations/chk-holiday"
    tr_id = "CTCA0903R"
    params = {"BASS_DT": tomorrow, "CTX_AREA_NK": "", "CTX_AREA_FK": ""}
    res = kis._send_request("GET", path, tr_id, params=params)
    import json
    print("--- Raw 20251213 ---")
    print(json.dumps(res.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test_holiday()
