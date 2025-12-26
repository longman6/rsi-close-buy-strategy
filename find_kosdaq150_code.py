from pykrx import stock

try:
    print("Listing KOSDAQ Indices:")
    for ticker in stock.get_index_ticker_list(market="KOSDAQ"):
        name = stock.get_index_ticker_name(ticker)
        print(f"{ticker}: {name}")
    
    print("\nListing KOSPI Indices (just in case):")
    for ticker in stock.get_index_ticker_list(market="KOSPI"):
        name = stock.get_index_ticker_name(ticker)
        # Print only if it looks like KOSDAQ in name (unlikely) or just first few
        if "KOSDAQ" in name: 
            print(f"{ticker}: {name}")
            
except Exception as e:
    print(f"Error: {e}")
