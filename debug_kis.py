from src.kis_client import KISClient
import logging
import datetime

# Setup basic logging to console
logging.basicConfig(level=logging.INFO)

def test():
    kis = KISClient()
    print(f"Base URL: {kis.base_url}")
    print(f"Is Mock: {kis.is_mock}")
    
    # Try Period Profit
    print("\n--- Testing Period Profit (TTTC8701R) ---")
    today = datetime.datetime.now().strftime("%Y%m%d")
    start = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y%m%d")
    
    try:
        # Force call regardless of is_mock check in the method (we will manually call _send_request logic if needed, 
        # but let's call the method first. 
        # Note: I modified get_period_profit to return [] if is_mock. 
        # So if is_mock is recognized as True, it returns [].
        res = kis.get_period_profit(start, today)
        print(f"Result: {len(res)} items")
    except Exception as e:
        print(f"Exception: {e}")

    # If it failed or returned empty, let's try raw request to see error if hidden
    if kis.is_mock:
         print("Skipping raw Real TR test because KISClient thinks it is Mock.")
    else:
         # Manually send to see error
         print("Sending Manual Request...")
         path = "/uapi/domestic-stock/v1/trading/inquire-period-profit"
         tr_id = "TTTC8701R"
         params = {
            "CANO": kis.account_no,
            "ACNT_PRDT_CD": "01",
            "PDNO": "",
            "INQR_STRT_DT": start,
            "INQR_END_DT": today,
            "WCRC_FWRD_DVSN_CD": "01",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": ""
        }
         res = kis._send_request("GET", path, tr_id, params=params)
         if res:
             print(f"Status: {res.status_code}")
             print(f"Body: {res.text}")

if __name__ == "__main__":
    test()
