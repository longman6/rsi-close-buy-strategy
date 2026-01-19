#!/usr/bin/env python3
"""
원본 Dense Optimization 스크립트의 시뮬레이션 함수를 직접 사용하여 검증
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))

from scripts.optimize_all_dense import (
    prepare_data_all_needed, run_simulation_worker, init_worker
)
from rsi_strategy_backtest import get_kosdaq150_tickers
from datetime import datetime

def main():
    print("=" * 60)
    print("🔍 Dense Optimization 원본 함수로 검증")
    print("=" * 60)
    print("\n📋 검증 파라미터:")
    print("  - RSI Window: 3")
    print("  - SMA Window: 50")
    print("  - Buy Threshold: 20")
    print("  - Sell Threshold: 80")
    print("  - Max Holding Days: 10")
    print("  - Max Positions: 3")
    print("  - Loss Lockout Days: 90 (기본값)")
    print("-" * 60)
    
    # 종목 로드
    tickers = get_kosdaq150_tickers()
    
    # 데이터 준비 (원본 함수 사용)
    print(f"\n⏳ 데이터 준비 중 (원본 prepare_data_all_needed 사용)...")
    stock_data, valid_tickers = prepare_data_all_needed(tickers, '2010-01-01')
    
    # Global Worker Data 초기화
    init_worker(stock_data, valid_tickers)
    
    # 시뮬레이션 실행 (원본 함수 사용)
    print(f"\n⏳ 시뮬레이션 실행 중 (원본 run_simulation_worker 사용)...")
    result = run_simulation_worker(
        rsi_period=3,
        sma_period=50,
        buy_threshold=20,
        sell_threshold=80,
        max_holding_days=10,
        max_positions=3,
        loss_lockout_days=90
    )
    
    # 결과 출력
    print("\n" + "=" * 60)
    print("📊 검증 결과")
    print("=" * 60)
    
    ret = result['Return']
    mdd = result['MDD']
    win_rate = result['WinRate']
    count = result['Trades']
    
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
    
    ret_match = abs(ret - expected_ret) < 100
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
        print("\n⚠️ 일부 지표가 일치하지 않습니다.")
    
    print(f"\n⏰ 검증 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
