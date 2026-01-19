#!/usr/bin/env python3
"""
RSI 3 공격형 전략 검증 스크립트
파라미터: RSI 3, SMA 50, Buy 20, Sell 80, Hold 10, MaxPos 3
예상 결과: 수익률 17,385%, MDD -55.89%, 승률 58.15%, 거래수 2,220
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rsi_strategy_backtest import (
    prepare_data, run_simulation, get_kosdaq150_tickers,
    INITIAL_CAPITAL
)
from datetime import datetime

def main():
    print("=" * 60)
    print("🔍 RSI 3 공격형 전략 검증 백테스트")
    print("=" * 60)
    print("\n📋 검증 파라미터:")
    print("  - RSI Window: 3")
    print("  - SMA Window: 50")
    print("  - Buy Threshold: 20")
    print("  - Sell Threshold: 80")
    print("  - Max Holding Days: 10")
    print("  - Max Positions: 3")
    print("  - 기간: 2010-01-01 ~ 현재")
    print("-" * 60)
    
    # 파라미터 설정
    RSI_WINDOW = 3
    SMA_WINDOW = 50
    BUY_THRESHOLD = 20
    SELL_THRESHOLD = 80
    MAX_HOLDING_DAYS = 10
    MAX_POSITIONS = 3
    START_DATE = '2010-01-01'
    
    # 종목 로드
    tickers = get_kosdaq150_tickers()
    
    # 데이터 준비
    print(f"\n⏳ 데이터 준비 중 (RSI {RSI_WINDOW}, SMA {SMA_WINDOW})...")
    stock_data, valid_tickers = prepare_data(tickers, START_DATE, RSI_WINDOW, SMA_WINDOW)
    
    # 시뮬레이션 실행
    print(f"\n⏳ 시뮬레이션 실행 중...")
    ret, mdd, win_rate, count, hist, trades = run_simulation(
        stock_data, 
        valid_tickers, 
        use_filter=False,
        max_holding_days=MAX_HOLDING_DAYS,
        buy_threshold=BUY_THRESHOLD,
        sell_threshold=SELL_THRESHOLD,
        max_positions=MAX_POSITIONS,
        loss_lockout_days=90  # Dense Optimization 원본과 동일
    )
    
    # 결과 출력
    print("\n" + "=" * 60)
    print("📊 검증 결과")
    print("=" * 60)
    
    print(f"""
┌─────────────────┬──────────────────┬──────────────────┐
│      지표       │    검증 결과     │    기존 기록     │
├─────────────────┼──────────────────┼──────────────────┤
│  수익률 (%)     │  {ret:>14,.2f}% │      17,385.54%  │
│  MDD (%)        │  {mdd:>14.2f}% │        -55.89%   │
│  승률 (%)       │  {win_rate:>14.2f}% │         58.15%   │
│  거래수 (회)    │  {count:>14,}회 │          2,220회 │
└─────────────────┴──────────────────┴──────────────────┘
""")
    
    # 일치 여부 확인
    expected_ret = 17385.54
    expected_mdd = -55.89
    expected_win = 58.15
    expected_cnt = 2220
    
    ret_match = abs(ret - expected_ret) < 100  # 1% 허용
    mdd_match = abs(mdd - expected_mdd) < 1
    win_match = abs(win_rate - expected_win) < 1
    cnt_match = abs(count - expected_cnt) < 50
    
    print("\n✅ 검증 결과 일치 여부:")
    print(f"  - 수익률: {'✅ 일치' if ret_match else '❌ 불일치'} (차이: {ret - expected_ret:+.2f}%)")
    print(f"  - MDD: {'✅ 일치' if mdd_match else '❌ 불일치'} (차이: {mdd - expected_mdd:+.2f}%)")
    print(f"  - 승률: {'✅ 일치' if win_match else '❌ 불일치'} (차이: {win_rate - expected_win:+.2f}%)")
    print(f"  - 거래수: {'✅ 일치' if cnt_match else '❌ 불일치'} (차이: {count - expected_cnt:+d}회)")
    
    if all([ret_match, mdd_match, win_match, cnt_match]):
        print("\n🎉 모든 지표가 기존 기록과 일치합니다!")
    else:
        print("\n⚠️ 일부 지표가 일치하지 않습니다. 데이터 또는 계산 로직 차이 확인이 필요합니다.")
    
    print(f"\n⏰ 검증 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
