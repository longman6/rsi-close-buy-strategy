import sys
import os
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.kis_client import KISClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

def check():
    kis = KISClient()
    if not kis.access_token:
        kis.get_access_token()
        
    logging.info(f"🧪 Testing get_outstanding_orders in {'Mock' if kis.is_mock else 'Real'} Mode...")
    
    orders = kis.get_outstanding_orders()
    logging.info(f"✅ Result: {orders}")
    
    if orders == [] and kis.is_mock:
        logging.info("✨ Success: Empty list returned (as expected for Mock Skipped).")
    elif isinstance(orders, list):
         logging.info(f"✨ Success: List returned with {len(orders)} items.")
    else:
        logging.error("❌ Failed: Unexpected return type.")

if __name__ == "__main__":
    check()
