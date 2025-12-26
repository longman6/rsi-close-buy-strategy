from pykrx import stock

from pykrx import stock
 
for index_v in stock.get_index_ticker_list(market='KOSDAQ'):
 
    print(index_v, stock.get_index_ticker_name(index_v))

# # 코스닥150 지수 구성종목 목록 가져오기 (2025년 12월 정기변경 기준)
# kosdaq150_list = stock.get_index_constituent_list("KOSDAQ150", "20251212") # 2025년 12월 12일 기준

# print(kosdaq150_list)

  
tickers = stock.get_index_portfolio_deposit_file("2203") # KOSDAQ 150

print(tickers)
