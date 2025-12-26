from src.kis_client import KISClient
import json
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)

def debug_balance():
    kis = KISClient()
    
    # We want to see the RAW response from inquire-balance
    # Replicating get_balance logic but dumping raw json
    
    path = "/uapi/domestic-stock/v1/trading/inquire-balance"
    # url = f"{kis.base_url}{path}"
    
    tr_id = "VTTC8434R" if kis.is_mock else "TTTC8434R"
    # headers = kis._get_headers(tr_id)
    
    # Need to access private method or just copy params
    # Using public method get_balance() first to see what it parses
    print("--- Current get_balance() ---")
    bal = kis.get_balance()
    print(bal)
    
    print("\n--- Raw Response Dump ---")
    # We will invoke _send_request manually if possible or just modify kis_client temporarily?
    # Better to manually request using requests to be sure, but need headers.
    # Let's use the internal method since we can access it in python
    
    import config
    params = {
        "CANO": kis.account_no,
        "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "N",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    res = kis._send_request("GET", path, tr_id, params=params)
    print("\n--- Checking Inquire Possible Order (Buying Power) ---")
    path_buy = "/uapi/domestic-stock/v1/trading/inquire-psbl-order"
    tr_id_buy = "VTTC8908R" if kis.is_mock else "TTTC8908R"
    
    params_buy = {
        "CANO": kis.account_no,
        "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
        "PDNO": "005930", # Dummy code (Samsung Elec) needed for calculation
        "ORD_UNPR": "0",
        "ORD_DVSN": "01",
        "CMA_EVLU_AMT_ICLD_YN": "Y",
        "OVRS_ICLD_YN": "N"
    }
    
    res_buy = kis._send_request("GET", path_buy, tr_id_buy, params=params_buy)
    if res_buy:
        data_buy = res_buy.json()
        print(json.dumps(data_buy, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    debug_balance()
