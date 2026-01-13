import sys
import os
import time
import logging
import json
import pytz
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.kis_client import KISClient

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def debug_orders():
    kis = KISClient()
    if not kis.access_token:
        kis.get_access_token()
        
    logging.info("🕵️ Starting KIS Order API Debugging...")
    
    # 1. Place a fresh order to be sure
    code = "005930" # Samsung Elec
    curr = kis.get_current_price(code)
    current_price = int(curr['stck_prpr'])
    test_price = kis.get_valid_price(int(current_price * 0.95)) # -5% deep
    
    logging.info(f"🛒 Placing Debug Order: {code} @ {test_price} (Current: {current_price})")
    success, msg = kis.send_order(code, 1, "buy", test_price, "00")
    if success:
        logging.info("✅ Order Success.")
    else:
        logging.error(f"❌ Order Failed: {msg} (Proceeding anyway to check existing)")

    time.sleep(3)

    # Common Params
    tz_kst = pytz.timezone('Asia/Seoul')
    today_str = datetime.now(pytz.utc).astimezone(tz_kst).strftime("%Y%m%d")
    
    path = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
    tr_id = "VTTC8055R" if kis.is_mock else "TTTC8055R" # Inquire Daily Conclusion
    
    base_params = {
        "CANO": kis.account_no,
        "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
        "INQR_STRT_DT": today_str,
        "INQR_END_DT": today_str,
        "SLL_BUY_DVSN_CD": "00", 
        "INQR_DVSN": "00",
        "PDNO": "",
        "ORD_GNO_BRNO": "",
        # "PCOD": "", # Removing suspect param
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }

    # Test 1: Daily CCLD with CCLD_DVSN = 02 (Unfilled) - Current Logic
    logging.info("\n🧪 Test 1: Daily CCLD (02: Unfilled)")
    params1 = base_params.copy()
    params1["CCLD_DVSN"] = "02"
    res1 = kis._send_request("GET", path, tr_id, params=params1)
    print_res(res1)
    
    # Test 2: Daily CCLD with CCLD_DVSN = 00 (All)
    logging.info("\n🧪 Test 2: Daily CCLD (00: All)")
    params2 = base_params.copy()
    params2["CCLD_DVSN"] = "00"
    res2 = kis._send_request("GET", path, tr_id, params=params2)
    print_res(res2)

    # Test 3: Inquire Revise/Cancel Possible Orders (TTTC8036R / VTTC8036R)
    logging.info("\n🧪 Test 3: Revise/Cancel Possible Orders (VTTC8036R)")
    path_rvse = "/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
    tr_id_rvse = "VTTC8036R" if kis.is_mock else "TTTC8036R"
    
    params3 = {
        "CANO": kis.account_no,
        "ACNT_PRDT_CD": config.KIS_ACNT_PRDT_CD,
        "PDNO": "",
        "ORD_UNPR": "",
        "ORD_DVSN": "00", # Limit? No, documentation says 00: All? check docs
        # Docs: ORD_DVSN not used?
        # Let's check params for inquiry
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": "",
        "INQR_DVSN_1": "0", # 0: Order No Order, 1: Order No Reverse?
        "INQR_DVSN_2": "0" # 0: All, 1: Buy, 2: Sell
    }
    
    # Correction: Only required params
    # CANO, ACNT_PRDT_CD, CTX_AREA_FK100, CTX_AREA_NK100, INQR_DVSN_1, INQR_DVSN_2
    
    res3 = kis._send_request("GET", path_rvse, tr_id_rvse, params=params3)
    print_res(res3)
    
    # Cleanup
    # We will clear orders if Test 3 finds them
    if res3 and res3.status_code == 200:
        data = res3.json()
        orders = data.get('output', [])
        if orders:
            logging.info(f"\n🧹 Cleaning up {len(orders)} orders found in Test 3...")
            for o in orders:
                org_no = o['krx_fwdg_ord_orgno'] # Maybe different key? output1 vs output?
                # output structure for 8036R:
                # order list is in 'output1' usually? No, 'output' list usually.
                # Actually let's assume 'output' is list.
                # Check keys: 'odno' (Order No), 'orgn_odno' (Original Order No)
                
                # We need Org No and Order No to cancel
                odno = o['odno']
                org_no = o.get('krx_fwdg_ord_orgno', '') # Might be empty?
                if not org_no: org_no = o.get('ord_gno_brno', '') # Branch no?
                
                # Try cancel
                kis.revise_cancel_order(org_no, odno, 0, 0, is_cancel=True)

def print_res(res):
    if res and res.status_code == 200:
        data = res.json()
        count = data.get('output1_count', len(data.get('output', []))) # or just len list
        if 'output1' in data:
            items = data['output1']
        elif 'output' in data:
            items = data['output']
        else:
            items = []
            
        logging.info(f"✅ Status: {data['rt_cd']} | Msg: {data['msg1']} | Count: {len(items)}")
        if items:
            logging.info(f"   Sample: {items[0]}")
    else:
        logging.error(f"❌ Failed: {res.status_code if res else 'None'} | {res.text if res else ''}")

if __name__ == "__main__":
    debug_orders()
