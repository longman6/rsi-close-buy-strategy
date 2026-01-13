import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import config
from src.kis_client import KISClient
from src.telegram_bot import TelegramBot

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def test_correction():
    logging.info("🧪 Starting Live Order Correction Test...")
    kis = KISClient()
    telegram = TelegramBot()
    
    if not kis.access_token:
        kis.get_access_token()

    # 1. Select Target (Global Tax Free for Real Test)
    code = "204620" 
    stock_name = "글로벌텍스프리"
    
    # 2. Get Price
    curr = kis.get_current_price(code)
    if not curr:
        logging.error("❌ Failed to get current price.")
        return

    current_price = int(curr['stck_prpr'])
    logging.info(f"💰 Current Price of {stock_name} ({code}): {current_price:,} KRW")
    
    # 3. Place Order at -2% (Likely unfilled)
    # Logic: Place it slightly lower so it doesn't fill immediately, 
    # but close enough that it's a valid order range.
    target_buy_price = kis.get_valid_price(int(current_price * 0.98))
    qty = 1
    
    logging.info(f"🛒 Placing Test Order: 1ea @ {target_buy_price:,} KRW (-2%)")
    success, msg = kis.send_order(code, qty, "buy", target_buy_price, "00")
    
    if not success:
        logging.error(f"❌ Failed to place order: {msg}")
        return

    logging.info("⏳ Waiting for order registration (Polling)...")
    
    my_order = None
    for i in range(5):
        time.sleep(2)
        orders = kis.get_outstanding_orders()
        logging.info(f"   [Attempt {i+1}] Outstanding Orders Count: {len(orders)}")
        
        # Debug: Print all orders briefly
        for o in orders:
            logging.info(f"    - {o['pdno']} : {o['ord_unpr']} (No: {o['ord_no'] if 'ord_no' in o else o.get('orgn_odno')})")
            
        my_order = next((o for o in orders if o['pdno'] == code), None)
        if my_order:
            break
    
    if not my_order:
        logging.error("❌ Order placed but NOT found in outstanding list after retries!")
        # Check holdings to see if filled
        balance = kis.get_balance()
        holding = next((h for h in balance['holdings'] if h['pdno'] == code), None)
        if holding:
             logging.warning("⚠️ Order was filled immediately. Cannot test correction.")
        return
        
    ord_no = my_order['ord_no'] if 'ord_no' in my_order else my_order.get('orgn_odno')
    ord_price = float(my_order['ord_unpr'])
    logging.info(f"✅ Order Found: No.{ord_no} @ {ord_price:,.0f} KRW")
    
    # 5. Trigger monitor_and_correct_orders
    # Reset timer in main module to bypass 60s check
    main.last_monitor_time = 0 
    
    # Clear state targets to simulate Restart (Orphan) behavior
    # This forces the bot to use the "Managing Orphaned Order" logic
    main.state["buy_targets"] = []
    
    logging.info("\n🚀 Executing `monitor_and_correct_orders`...")
    logging.info("   - Expectation: Detect Orphan -> Add to State -> Trigger Fallback Revision to Current Price")
    
    # Pass None for trade_manager as it is not used in this function
    main.monitor_and_correct_orders(kis, telegram, None) 
    
    logging.info("⏳ Waiting 3 seconds for revision processing...")
    time.sleep(3)
    
    # 6. Verify Revision
    orders_after = kis.get_outstanding_orders()
    my_order_after = next((o for o in orders_after if o['pdno'] == code), None)
    
    if not my_order_after:
        logging.info("⚠️ Order is gone! (Filled? Cancelled?)")
    else:
        new_price = float(my_order_after['ord_unpr'])
        logging.info(f"📜 Order Status After: {new_price:,.0f} KRW (Original: {ord_price:,.0f})")
        
        if new_price != ord_price:
             logging.info(f"✅ SUCCESS: Price modified! ({ord_price:,.0f} -> {new_price:,.0f})")
             if new_price == current_price: # Ideally exact match or close
                 logging.info("   (Matched Current Price)")
        else:
             logging.error("❌ FAILURE: Price was NOT modified.")

    # 7. Cleanup (Cancel Order)
    logging.info("\n🧹 Cleaning up (Cancelling Test Order)...")
    # Refresh order info (org_no might change after revision)
    orders_final = kis.get_outstanding_orders()
    target_order = next((o for o in orders_final if o['pdno'] == code), None)
    
    if target_order:
         kis.revise_cancel_order(target_order['krx_fwdg_ord_orgno'], target_order['orgn_odno'], 0, 0, is_cancel=True)
         logging.info("✅ Cleanup Complete.")
    else:
         logging.info("nothing to cancel.")

if __name__ == "__main__":
    test_correction()
