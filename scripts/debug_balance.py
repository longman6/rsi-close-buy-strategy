import sys
import os

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.kis_client import KISClient
import config
import logging
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_balance():
    print("=== KIS API Balance Debug Tool ===")
    
    try:
        kis = KISClient()
    except Exception as e:
        logger.error(f"Failed to initialize KISClient: {e}")
        return

    print(f"Mode: {'Mock (Virtual)' if kis.is_mock else 'Real'}")
    print(f"Base URL: {kis.base_url}")
    print(f"Account: {kis.account_no}-{config.KIS_ACNT_PRDT_CD}")
    
    tr_id = "VTTC8434R" if kis.is_mock else "TTTC8434R"
    print(f"Target TR_ID: {tr_id}")

    # 1. Test Default get_balance()
    print("\n--- 1. Testing Default get_balance() ---")
    try:
        res = kis.get_balance()
        if res:
            print(">>> SUCCESS: get_balance() returned data.")
            print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            print(">>> FAILED: get_balance() returned None.")
    except Exception as e:
        print(f">>> ERROR: {e}")

    # 2. Test Manual Parameter Variations
    print("\n--- 2. Testing Parameter Variations ---")
    path = "/uapi/domestic-stock/v1/trading/inquire-balance"
    
    # Define variations to test
    variations = [
        {"INQR_DVSN": "01", "desc": "01: 대출일별"},
        {"INQR_DVSN": "02", "desc": "02: 종목별"},
        {"INQR_DVSN": "00", "desc": "00: (Possible Legacy/Default)"},
    ]

    base_params = {
        "CANO": kis.account_no,
        "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "N",
        # INQR_DVSN will be varied
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }

    for v in variations:
        inqr_dvsn = v["INQR_DVSN"]
        desc = v["desc"]
        print(f"\n[Test] INQR_DVSN='{inqr_dvsn}' ({desc})")
        
        params = base_params.copy()
        params["INQR_DVSN"] = inqr_dvsn
        
        # Manually call _send_request to bypass get_balance logic
        # Note: _send_request is internal, but Python allows access
        try:
            res = kis._send_request("GET", path, tr_id, params=params)
            print(f"Status Code: {res.status_code}")
            
            data = res.json()
            rt_cd = data.get('rt_cd')
            msg_cd = data.get('msg_cd')
            msg1 = data.get('msg1')
            
            print(f"Result Code (rt_cd): {rt_cd}")
            print(f"Message Code (msg_cd): {msg_cd}")
            print(f"Message (msg1): {msg1}")
            
            if rt_cd == '0':
                print(">>> SUCCESS! Valid parameter combination.")
            else:
                print(">>> FAILED.")
                
        except Exception as e:
            print(f">>> EXCEPTION: {e}")

if __name__ == "__main__":
    test_balance()
