
from pykrx import stock
import sys

def main():
    print("Fetching KOSDAQ 150 (Index 2203)...")
    try:
        tickers = stock.get_index_portfolio_deposit_file("2203")
        
        with open("kosdaq150_list.txt", "w", encoding="utf-8") as f:
            for ticker in tickers:
                name = stock.get_market_ticker_name(ticker)
                # Format: {'code': 'XXXXXX', 'name': 'YYYYVV'},
                line = f"{{'code': '{ticker}', 'name': '{name}'}},"
                print(line)
                f.write(line + "\n")
        
        print(f"\nSaved {len(tickers)} items to kosdaq150_list.txt")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
