from pykrx import stock
from datetime import datetime, timedelta

# Check if index code matches
print("Listing KOSDAQ Indices containing '150':")
try:
    for ticker in stock.get_index_ticker_list(market="KOSDAQ"):
        name = stock.get_index_ticker_name(ticker)
        if "150" in name:
            print(f"{ticker}: {name}")
except Exception as e:
    print(f"Error listing indices: {e}")

print("\nChecking universe size for past 7 days (Target: 2203):")
today = datetime.now()
for i in range(7):
    d = (today - timedelta(days=i)).strftime("%Y%m%d")
    try:
        tickers = stock.get_index_portfolio_deposit_file("2203", date=d)
        print(f"{d}: fetched {len(tickers)} tickers")
    except Exception as e:
        print(f"{d}: Failed with {e}")
