#!/usr/bin/env python
"""
분할 매수 로직 테스트 스크립트
- get_today_filled_info 메서드 테스트
- 1차/2차 주문 체결 현황 조회 테스트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.kis_client import KISClient

def test_get_today_filled_info():
    """오늘 체결 정보 조회 테스트"""
    print("=" * 60)
    print("🧪 get_today_filled_info 메서드 테스트")
    print("=" * 60)
    
    kis = KISClient()
    
    # 테스트할 종목 코드들 (현재 보유 중인 종목 또는 오늘 거래한 종목)
    test_codes = ["085660", "171090", "178320"]  # 최근 거래 내역에서 가져온 종목들
    
    for code in test_codes:
        print(f"\n📊 종목: {code}")
        print("-" * 40)
        
        # 매수 체결 정보 조회
        buy_info = kis.get_today_filled_info(code, side="buy")
        print(f"  [매수]")
        print(f"    체결 수량: {buy_info['filled_qty']}주")
        print(f"    평균 체결가: {buy_info['avg_price']:,.0f}원")
        print(f"    총 체결 금액: {buy_info['total_amount']:,.0f}원")
        print(f"    미체결 수량: {buy_info['unfilled_qty']}주")
        
        # 매도 체결 정보 조회
        sell_info = kis.get_today_filled_info(code, side="sell")
        print(f"  [매도]")
        print(f"    체결 수량: {sell_info['filled_qty']}주")
        print(f"    평균 체결가: {sell_info['avg_price']:,.0f}원")
    
    print("\n" + "=" * 60)
    print("✅ 테스트 완료")
    print("=" * 60)

def test_outstanding_orders():
    """미체결 주문 조회 테스트"""
    print("\n" + "=" * 60)
    print("🧪 미체결 주문 조회 테스트")
    print("=" * 60)
    
    kis = KISClient()
    
    orders = kis.get_outstanding_orders()
    
    if not orders:
        print("ℹ️  미체결 주문 없음")
    else:
        print(f"📋 미체결 주문: {len(orders)}건")
        for i, order in enumerate(orders, 1):
            code = order.get('pdno', 'N/A')
            qty = order.get('ord_qty', 0)
            ccld_qty = order.get('ccld_qty', 0)
            price = order.get('ord_unpr', 0)
            print(f"  {i}. {code}: {qty}주 @ {price}원 (체결: {ccld_qty}주)")

def test_simulation():
    """분할 매수 시뮬레이션 (실제 주문 X)"""
    print("\n" + "=" * 60)
    print("🧪 분할 매수 로직 시뮬레이션")
    print("=" * 60)
    
    kis = KISClient()
    
    # 가상의 1차 주문 상황 가정
    test_target = {
        'code': '005930',  # 삼성전자
        'name': '삼성전자',
        'first_order_qty': 10
    }
    
    code = test_target['code']
    first_order_qty = test_target['first_order_qty']
    
    print(f"\n📌 테스트 종목: {test_target['name']} ({code})")
    print(f"   1차 주문 수량: {first_order_qty}주")
    
    # 체결 정보 조회
    filled_info = kis.get_today_filled_info(code, side="buy")
    filled_qty = filled_info.get('filled_qty', 0)
    unfilled_qty = filled_info.get('unfilled_qty', 0)
    avg_price = filled_info.get('avg_price', 0)
    
    print(f"\n📊 체결 현황:")
    print(f"   체결: {filled_qty}주")
    print(f"   미체결: {unfilled_qty}주")
    print(f"   평균가: {avg_price:,.0f}원")
    
    # 2차 주문 조건 확인
    fill_rate = (filled_qty / first_order_qty * 100) if first_order_qty > 0 else 0
    print(f"\n📈 체결률: {fill_rate:.1f}%")
    
    if first_order_qty > 0 and filled_qty < first_order_qty * 0.5:
        print("❌ 판정: 2차 주문 스킵 (체결률 50% 미만)")
    else:
        print("✅ 판정: 2차 주문 진행 가능")

if __name__ == "__main__":
    print("🚀 분할 매수 로직 테스트 시작\n")
    
    try:
        test_get_today_filled_info()
        test_outstanding_orders()
        test_simulation()
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
