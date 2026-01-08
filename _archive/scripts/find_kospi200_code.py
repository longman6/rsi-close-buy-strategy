import time
from pykrx import stock

try:
    # 1. KOSPI Index List
    tickers = stock.get_index_ticker_list(market='KOSPI')
    print("Available KOSPI Indices:")
    target_code = None
    for ticker in tickers:
        name = stock.get_index_ticker_name(ticker)
        if "200" in name and "코스피" in name:
            print(f"{ticker}: {name}")
            if name == "코스피 200":
                target_code = ticker
    
    if target_code:
        print(f"\nFOUND KOSPI 200 CODE: {target_code}")
    else:
        print("\nKOSPI 200 NOT FOUND in simple search.")

except Exception as e:
    print(f"Error: {e}")
