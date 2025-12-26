from pykrx import stock
import datetime

# 오늘 날짜를 YYYYMMDD 형식으로 가져오기
today = datetime.datetime.now().strftime("%Y%m%d")

# 가장 가까운 영업일 가져오기
nearest_business_day = stock.get_nearest_business_day_in_a_week()

if today == nearest_business_day:
    print(f"오늘은 개장일입니다. ({today})")
else:
    print(f"오늘은 휴장일입니다. 가장 가까운 영업일: {nearest_business_day}")