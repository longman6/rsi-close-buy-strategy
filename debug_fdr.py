import FinanceDataReader as fdr
import logging

logging.basicConfig(level=logging.INFO)

def test_fetch():
    print("Testing fdr.StockListing('KOSDAQ')...")
    try:
        df = fdr.StockListing('KOSDAQ')
        print(f"Success! Retrieved {len(df)} rows.")
        print(df.head())
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fetch()
