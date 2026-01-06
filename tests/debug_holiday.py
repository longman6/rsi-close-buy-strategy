
import logging
from src.kis_client import KISClient
from src.utils import get_now_kst
from pykrx import stock

logging.basicConfig(level=logging.INFO)

def test_holiday():
    today_str = get_now_kst().strftime("%Y%m%d")
    print(f"Testing for Date: {today_str}")

    # 1. PyKRX Check
    try:
        nearest = stock.get_nearest_business_day_in_a_week()
        print(f"[PyKRX] Nearest Business Day: {nearest}")
        print(f"[PyKRX] Is Today == Nearest? {today_str == nearest}")
    except Exception as e:
        print(f"[PyKRX] Error: {e}")

    # 2. KIS Client Check
    try:
        kis = KISClient()
        is_trading = kis.is_trading_day(today_str)
        print(f"[KIS] is_trading_day({today_str}): {is_trading}")
    except Exception as e:
        print(f"[KIS] Error: {e}")

if __name__ == "__main__":
    test_holiday()
