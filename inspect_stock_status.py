import sys
from src.kis_client import KISClient
import json
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO)

def inspect_stock(code):
    kis = KISClient()
    print(f"--- Inspecting {code} ---")
    
    # 1. inquire-price (FHKST01010100)
    # This is what get_current_price uses.
    res = kis.get_current_price(code)
    if res:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Failed to get price info.")

if __name__ == "__main__":
    # 005930 (Samsung - Normal)
    inspect_stock("005930")
    
    # 440110 (Fadu - Suspended/Issue?)
    inspect_stock("440110")
