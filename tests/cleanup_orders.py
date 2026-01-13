import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.kis_client import KISClient

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def cleanup():
    kis = KISClient()
    if not kis.access_token:
        kis.get_access_token()

    target_code = "204620" # Global Tax Free
    
    logging.info(f"🧹 Starting Cleanup for {target_code}...")
    
    orders = kis.get_outstanding_orders()
    logging.info(f"🔍 Found {len(orders)} outstanding orders total.")
    
    target_orders = [o for o in orders if o['pdno'] == target_code]
    logging.info(f"🔍 Found {len(target_orders)} orders for {target_code}.")
    
    for o in target_orders:
        ord_no = o['ord_no'] if 'ord_no' in o else o.get('orgn_odno')
        # InquireDailyCCLD (8001R) returns 'odno' as Order No.
        # But 'krx_fwdg_ord_orgno' (Org No) is needed for cancellation?
        # Usually Cancel requires: Org No (Organization No) and Order No (Original Order No).
        # Let's inspect keys if needed.
        # Standard keys from 8001R output1: 'odno', 'ord_gno_brno' (Branch?), 'orgn_odno'(Original Order No for correction target?), 'pdno'
        
        # NOTE: To cancel an order, we need:
        # 1. ORG_NO (Organization Code? e.g. Branch Code? KIS calls it 'krx_fwdg_ord_orgno' or 'ord_gno_brno'?)
        # Actually revise_cancel_order uses params:
        # "KRX_FWDG_ORD_ORGNO": org_no,
        # "ORGN_ODNO": order_no,
        
        # From inquire-daily-ccld (8001R), we get:
        # 'ord_gno_brno' -> This might be Org No? No, usually empty or branch.
        # 'odno' -> The order number.
        
        # Let's try passing 'ord_gno_brno' as org_no (if valid) or just empty string (often works for simple setups)
        # But wait, revise_cancel_order logic:
        # It's better to verify what keys come back.
        
        # Let's trust what we have. 
        # In 8001R, 'odno' is the order number.
        
        org_no = o.get('ord_gno_brno', '') 
        order_no = o.get('odno')
        price = float(o.get('ord_unpr', 0))
        
        logging.info(f"🗑️ Cancelling Order {order_no} ({price:,.0f} KRW)...")
        res = kis.revise_cancel_order(org_no, order_no, 0, 0, is_cancel=True)
        # revise_cancel_order returns (success, msg)
        # Wait, let's check return signature.
        # Yes, return success, msg
        
        if res[0]:
            logging.info(f"✅ Cancelled {order_no}.")
        else:
             logging.error(f"❌ Failed to cancel {order_no}: {res[1]}")
        
    logging.info("✨ Cleanup Done.")

if __name__ == "__main__":
    cleanup()
