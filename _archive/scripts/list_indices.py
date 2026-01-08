from pykrx import stock
import sys

# Set stdout to utf-8 explicitly
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    print("Listing KOSPI Indices...")
    # Using a known valid recent business day just in case
    target_date = "20251219" 
    tickers = stock.get_index_ticker_list(target_date, market='KOSPI')
    
    for ticker in tickers:
        name = stock.get_index_ticker_name(ticker)
        print(f"[{ticker}] {name}")
        
    print("Listing Complete.")

except Exception as e:
    print(f"Error: {e}")
