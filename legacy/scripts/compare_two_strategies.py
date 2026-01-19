#!/usr/bin/env python
"""
RSI 전략 비교 백테스트 (FDR 실시간 데이터 사용)
기간: 2025-01-02 ~ 현재
"""
import pandas as pd
import matplotlib.pyplot as plt
import FinanceDataReader as fdr
import os
import sys
from datetime import datetime, timedelta

# 상위 모듈 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rsi_strategy_backtest import (
    get_kosdaq150_tickers, 
    run_simulation,
    set_korean_font,
    calculate_rsi
)

set_korean_font()

# ---------------------------------------------------------
# 설정
# ---------------------------------------------------------
TEST_START_DATE = '2025-01-02'
SMA_LOOKBACK_DAYS = 250 # SMA 계산을 위한 여유 기간

# 전략 파라미터 정의
STRATEGIES = [
    {
        'name': 'Strategy 1 (Base)',
        'params': {
            'rsi_period': 3,
            'rsi_buy_threshold': 20,
            'rsi_sell_threshold': 75,
            'sma_period': 150,
            'max_positions': 7,
            'max_holding_days': 20,
            'loss_lockout_days': 90
        }
    },
    {
        'name': 'Strategy 2 (Optimized)',
        'params': {
            'rsi_period': 3,
            'rsi_buy_threshold': 26, 
            'rsi_sell_threshold': 72,
            'sma_period': 70,        
            'max_positions': 3,      
            'max_holding_days': 15,  
            'loss_lockout_days': 90
        }
    },
    {
        'name': 'Strategy 3 (MaxPos 5)',
        'params': {
            'rsi_period': 3,
            'rsi_buy_threshold': 26, # 20 -> 26
            'rsi_sell_threshold': 72, # 75 -> 72
            'sma_period': 70,        # 150 -> 70
            'max_positions': 5,      # 7 -> 5
            'max_holding_days': 15,  
            'loss_lockout_days': 90
        }
    }
]

def fetch_data_from_fdr(tickers, test_start_date):
    """
    FinanceDataReader를 사용하여 데이터를 직접 다운로드
    """
    start_dt = datetime.strptime(test_start_date, "%Y-%m-%d")
    fetch_start = (start_dt - timedelta(days=SMA_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    
    print(f"📥 데이터 다운로드 시작 (FDR): {fetch_start} ~ 현재")
    print(f"   대상 종목 수: {len(tickers)}개")
    
    stock_data_cache = {} # {ticker: df}
    
    # 전략별로 필요한 SMA/RSI가 다르므로, 원본 데이터(OHLCV)만 먼저 받고
    # 지표 계산은 전략 돌릴 때 수행하거나, 여기서 모든 지표를 미리 계산해둘 수도 있음.
    # 여기서는 Raw Data만 받아서 반환하고, 전략 실행 직전에 지표 추가.
    
    downloaded_cnt = 0
    for ticker in tickers:
        try:
            # FDR 종목 코드는 숫자만 or 거래소 코드 포함. KOSDAQ은 보통 그냥 숫자면 됨 (KRX)
            # FDR은 '005930' 형식 잘 인식함.
            code = ticker.split('.')[0]
            df = fdr.DataReader(code, fetch_start)
            
            if df is None or df.empty:
                continue
                
            # 컬럼 정리
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'])
                df.set_index('Date', inplace=True)
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            df.sort_index(inplace=True)
            
            # 최소 데이터 확인
            if len(df) < 10: 
                continue
                
            stock_data_cache[ticker] = df
            downloaded_cnt += 1
            if downloaded_cnt % 50 == 0:
                print(f"   ...{downloaded_cnt}개 완료")
                
        except Exception as e:
            print(f"   [Error] {ticker}: {e}")
            
    print(f"✅ 다운로드 완료: {len(stock_data_cache)}개 종목")
    return stock_data_cache

def prepare_strategy_data(raw_data_map, rsi_period, sma_period, start_date_str):
    """
    Raw 데이터에 지표 추가 및 날짜 필터링
    """
    processed_data = {}
    valid_tickers = []
    
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    
    for ticker, df_origin in raw_data_map.items():
        if len(df_origin) < sma_period + 5:
            continue
            
        df = df_origin.copy()
        
        # 지표 계산
        df['SMA'] = df['Close'].rolling(window=sma_period).mean()
        df['RSI'] = calculate_rsi(df['Close'], window=rsi_period)
        
        # 테스트 시작일 이후 데이터만 잘라내기
        df = df[df.index >= start_dt]
        
        if not df.empty:
            processed_data[ticker] = df
            valid_tickers.append(ticker)
            
    return processed_data, valid_tickers

def run_comparison():
    print("🚀 전략 비교 백테스트 (FDR 최신 데이터)")
    print(f"📅 테스트 기간: {TEST_START_DATE} ~ 현재")
    
    tickers = get_kosdaq150_tickers()
    
    # 1. Raw Data 다운로드 (한 번만 수행)
    raw_data = fetch_data_from_fdr(tickers, TEST_START_DATE)
    
    results = {}
    curves = {}
    
    for strat in STRATEGIES:
        name = strat['name']
        p = strat['params']
        print(f"\n👉 [{name}] 실행 중...")
        
        # 2. 전략별 지표 계산 및 데이터 준비
        stock_data, valid_tickers = prepare_strategy_data(
            raw_data, p['rsi_period'], p['sma_period'], TEST_START_DATE
        )
        
        # 3. 시뮬레이션
        ret, mdd, win, cnt, hist, trades = run_simulation(
            stock_data, valid_tickers, market_data=None, 
            max_holding_days=p['max_holding_days'],
            buy_threshold=p['rsi_buy_threshold'],
            sell_threshold=p['rsi_sell_threshold'],
            max_positions=p['max_positions'],
            loss_lockout_days=p['loss_lockout_days']
        )
        
        results[name] = {'ret': ret, 'mdd': mdd, 'win': win, 'cnt': cnt, 'trades': trades}
        curves[name] = hist
        print(f"   ✅ 완료: 수익률 {ret:.2f}%, MDD {mdd:.2f}%")

    # -----------------------------------------------------
    # 결과 비교 및 시각화
    # -----------------------------------------------------
    print("\n" + "="*80)
    print("📊 전략 비교 결과 (2025.01.02 ~ 현재)")
    print("="*80)
    
    # Header
    header = f"{'항목':<15}"
    for s in STRATEGIES:
        header += f" | {s['name']:<20}"
    print(header)
    print("-" * 80)
    
    # Rows
    row_ret = f"{'총 수익률':<15}"
    row_mdd = f"{'MDD':<15}"
    row_win = f"{'승률':<15}"
    row_cnt = f"{'거래 횟수':<15}"
    
    for s in STRATEGIES:
        r = results[s['name']]
        row_ret += f" | {r['ret']:>18.2f}%"
        row_mdd += f" | {r['mdd']:>18.2f}%"
        row_win += f" | {r['win']:>18.1f}%"
        row_cnt += f" | {r['cnt']:>18}회"
        
    print(row_ret)
    print(row_mdd)
    print(row_win)
    print(row_cnt)
    
    # 차트 저장
    plt.figure(figsize=(12, 6))
    for s in STRATEGIES:
        name = s['name']
        hist = curves[name]
        ret = results[name]['ret']
        if not hist.empty:
            plt.plot(hist.index, hist['Equity'], label=f"{name} ({ret:.1f}%)")
            
    plt.title(f"Equity Curve ({TEST_START_DATE} ~ Now)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    chart_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports', 'strategy_comparison_chart_fdr.png')
    plt.savefig(chart_path)
    print(f"\n✅ 차트 저장: {chart_path}")
    
    # 리포트 저장
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports', 'strategy_comparison_report_fdr.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# 전략 비교 분석 (FDR 데이터)\n\n")
        f.write(f"**기간:** {TEST_START_DATE} ~ {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**데이터 소스:** FinanceDataReader (실시간 다운로드)\n\n")
        
        f.write("## 1. 성과 요약\n")
        f.write("| 지표 | " + " | ".join([s['name'] for s in STRATEGIES]) + " |\n")
        f.write("| :--- | " + " | ".join([":---"] * len(STRATEGIES)) + " |\n")
        
        cols = ['수익률', 'MDD', '승률', '거래수']
        keys = ['ret', 'mdd', 'win', 'cnt']
        fmts = ['{:.2f}%', '{:.2f}%', '{:.1f}%', '{}회']
        
        for i, col in enumerate(cols):
            row = f"| {col} |"
            for s in STRATEGIES:
                val = results[s['name']][keys[i]]
                row += f" {fmts[i].format(val)} |"
            f.write(row + "\n")

    print(f"✅ 리포트 저장: {report_path}")

if __name__ == "__main__":
    run_comparison()
