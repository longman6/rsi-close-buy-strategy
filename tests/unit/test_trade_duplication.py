import logging
import os
import sys
from datetime import datetime

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.db_manager import DBManager

def test_duplicate_check():
    # Use a temporary DB for testing
    test_db = "data/test_user_data.db"
    if os.path.exists(test_db):
        os.remove(test_db)
        
    db = DBManager(user_db=test_db)
    
    date = "2026-01-19"
    code = "005930"
    name = "삼성전자"
    action = "BUY"
    price = 70000.0
    qty = 10
    
    print(f"--- 1차 저장 시도 ({date}, {code}, {action}) ---")
    db.save_trade_record(date, code, name, action, price, qty)
    
    history = db.get_trade_history()
    print(f"현재 기록 수: {len(history)}")
    assert len(history) == 1, "기록이 기본적으로 1건 있어야 합니다."
    
    print(f"\n--- 2차 저장 시도 (중복 데이터) ---")
    db.save_trade_record(date, code, name, action, price, qty)
    
    history = db.get_trade_history()
    print(f"현재 기록 수 after second attempt: {len(history)}")
    assert len(history) == 1, "중복 데이터는 저장되지 않아야 합니다."
    
    print(f"\n--- 3차 저장 시도 (다른 액션: SELL) ---")
    db.save_trade_record(date, code, name, "SELL", price, qty)
    
    history = db.get_trade_history()
    print(f"현재 기록 수 after SELL attempt: {len(history)}")
    assert len(history) == 2, "다른 액션은 저장되어야 합니다."

    print(f"\n--- 4차 저장 시도 (다른 날짜) ---")
    db.save_trade_record("2026-01-20", code, name, action, price, qty)
    
    history = db.get_trade_history()
    print(f"현재 기록 수 after different date attempt: {len(history)}")
    assert len(history) == 3, "다른 날짜는 저장되어야 합니다."
    
    print(f"\n--- has_trade_history_for_date 검증 ---")
    exists_19 = db.has_trade_history_for_date("2026-01-19")
    exists_20 = db.has_trade_history_for_date("2026-01-20")
    exists_21 = db.has_trade_history_for_date("2026-01-21")
    
    print(f"2026-01-19 존재 여부: {exists_19}")
    print(f"2026-01-20 존재 여부: {exists_20}")
    print(f"2026-01-21 존재 여부: {exists_21}")
    
    assert exists_19 is True
    assert exists_20 is True
    assert exists_21 is False
    
    print("\n✅ 모든 테스트 통과!")
    
    # Clean up
    if os.path.exists(test_db):
        os.remove(test_db)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_duplicate_check()
