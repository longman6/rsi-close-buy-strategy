from pykrx import stock

try:
    print("Fetching KOSDAQ 150 tickers (Code 2203)...")
    tickers = stock.get_index_portfolio_deposit_file("2203") # KOSDAQ 150
    print(f"Found {len(tickers)} tickers.")
    
    print("Sample (First 5):")
    for ticker in tickers[:5]:
        name = stock.get_market_ticker_name(ticker)
        print(f"{ticker}: {name}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
