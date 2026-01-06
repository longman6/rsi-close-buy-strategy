from pykrx import stock
from datetime import datetime

start_date = "20250101"
end_date = datetime.now().strftime("%Y%m%d")
print(f"Fetching KOSDAQ 150 (2203) from {start_date} to {end_date}...")
try:
    df = stock.get_index_ohlcv_by_date(start_date, end_date, "2203")
    print(df.head())
    print(f"Data points: {len(df)}")
except Exception as e:
    print(f"Error: {e}")
