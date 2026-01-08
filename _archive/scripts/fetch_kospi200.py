from pykrx import stock
import time

def fetch_kospi200():
    # KOSPI 200 Index Code is '1028' usually, let's try that.
    # Verify first if we can find it.
    
    target_code = "1028" # Common code for KOSPI 200
    
    try:
        # Check if 1028 is indeed KOSPI 200
        name = stock.get_index_ticker_name(target_code)
        print(f"Index {target_code}: {name}")
        
        if "200" not in name:
            print("Warning: 1028 might not be KOSPI 200. Searching...")
            tickers = stock.get_index_ticker_list(market='KOSPI')
            for t in tickers:
                n = stock.get_index_ticker_name(t)
                if n == "코스피 200":
                    target_code = t
                    print(f"Found correct code: {target_code}")
                    break
    except:
        pass

    print(f"Fetching tickers for KOSPI 200 ({target_code})...")
    
    from datetime import datetime, timedelta
    
    found_tickers = []
    success_date = ""
    
    # Try last 14 days backwards
    for i in range(14):
        d = datetime.now() - timedelta(days=i)
        check_date = d.strftime("%Y%m%d")
        
        try:
            print(f"Trying date: {check_date}...")
            tickers = stock.get_index_portfolio_deposit_file(target_code, check_date)
            if len(tickers) > 50: # Should be around 200
                found_tickers = tickers
                success_date = check_date
                print(f"✅ Success! Found {len(tickers)} tickers on {success_date}")
                break
            else:
                print(f"  - Empty or too few ({len(tickers)})")
        except Exception as e:
            print(f"  - Error on {check_date}: {e}")
            
    if not found_tickers:
        print("❌ Failed to find KOSPI 200 tickers in last 14 days.")
        return

    tickers = found_tickers
    print(f"Final Count: {len(tickers)}")
    
    output_lines = []
    for ticker in tickers:
        try:
            name = stock.get_market_ticker_name(ticker)
        except:
            name = "Unknown"
        # Format: {'code': '005930', 'name': '삼성전자'}
        line = f"{{'code': '{ticker}', 'name': '{name}'}}"
        output_lines.append(line)
        time.sleep(0.005) # rate limit check

    with open("kospi200_list.txt", "w", encoding="utf-8") as f:
        f.write(",\n".join(output_lines))
    
    print("Saved to kospi200_list.txt")

if __name__ == "__main__":
    fetch_kospi200()
