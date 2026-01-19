#!/usr/bin/env python
"""
연도별 전략 비교 분석 (2010 ~ 현재)
4가지 전략 vs KOSPI 200 vs KOSDAQ 150
"""
import pandas as pd
import matplotlib.pyplot as plt
import FinanceDataReader as fdr
import os
import sys
from datetime import datetime
import numpy as np

# 상위 모듈 import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rsi_strategy_backtest import (
    get_kosdaq150_tickers, 
    prepare_data, 
    run_simulation,
    set_korean_font,
    INITIAL_CAPITAL
)

set_korean_font()

# ---------------------------------------------------------
# 전략 파라미터 정의
# ---------------------------------------------------------
STRATEGIES = [
    {
        'id': 'S1',
        'name': 'S1(Base)', 
        'desc': 'RSI3/SMA150/Pos7',
        'params': {
            'rsi_period': 3, 'rsi_buy_threshold': 20, 'rsi_sell_threshold': 75,
            'sma_period': 150, 'max_positions': 7, 'max_holding_days': 20, 'loss_lockout_days': 90
        }
    },
    {
        'id': 'S2',
        'name': 'S2(Pos3)', 
        'desc': 'RSI3/SMA70/Pos3',
        'params': {
            'rsi_period': 3, 'rsi_buy_threshold': 26, 'rsi_sell_threshold': 72,
            'sma_period': 70, 'max_positions': 3, 'max_holding_days': 15, 'loss_lockout_days': 90
        }
    },
    {
        'id': 'S3',
        'name': 'S3(Pos5)', 
        'desc': 'RSI3/SMA70/Pos5',
        'params': {
            'rsi_period': 3, 'rsi_buy_threshold': 26, 'rsi_sell_threshold': 72,
            'sma_period': 70, 'max_positions': 5, 'max_holding_days': 15, 'loss_lockout_days': 90
        }
    },
    {
        'id': 'S4',
        'name': 'S4(Pos7)', 
        'desc': 'RSI3/SMA70/Pos7',
        'params': {
            'rsi_period': 3, 'rsi_buy_threshold': 26, 'rsi_sell_threshold': 72,
            'sma_period': 70, 'max_positions': 7, 'max_holding_days': 15, 'loss_lockout_days': 90
        }
    },
    {
        'id': 'S5',
        'name': 'S5(Pos4)', 
        'desc': 'RSI3/SMA70/Pos4',
        'params': {
            'rsi_period': 3, 'rsi_buy_threshold': 26, 'rsi_sell_threshold': 72,
            'sma_period': 70, 'max_positions': 4, 'max_holding_days': 15, 'loss_lockout_days': 90
        }
    }
]

def get_year_returns(hist_df, initial_capital=INITIAL_CAPITAL):
    """
    일별 Equity DataFrame에서 연도별 수익률을 계산.
    hist_df: Index=Date, Columns=['Equity']
    """
    if hist_df.empty:
        return {}
        
    df = hist_df.copy()
    df['Year'] = df.index.year
    
    yearly_returns = {}
    years = sorted(df['Year'].unique())
    
    for year in years:
        year_data = df[df['Year'] == year]
        if year_data.empty: continue
        
        start_equity = year_data['Equity'].iloc[0]
        end_equity = year_data['Equity'].iloc[-1]
        
        # 전년도 마지막 equity가 있다면 그걸 기초로 쓰는게 더 정확 (오버나잇 수익률 반영)
        prev_year_data = df[df['Year'] == year - 1]
        if not prev_year_data.empty:
            base_capital = prev_year_data['Equity'].iloc[-1]
        else:
            # 첫 해
            if year == years[0]:
                base_capital = initial_capital
            else:
                base_capital = start_equity

        ret = (end_equity / base_capital - 1) * 100
        yearly_returns[year] = ret
        
    return yearly_returns

def get_benchmark_index(symbol, name, start_date, end_date):
    """지수 데이터 로드 및 연도별 수익률 계산"""
    print(f"📥 벤치마크({name}) 데이터 로드 중...")
    try:
        df = fdr.DataReader(symbol, start_date, end_date)
    except Exception as e:
        print(f"   [Error] {symbol} 로드 실패: {e}")
        return pd.DataFrame(), {}
    
    if hasattr(df, 'index'):
        df.index = pd.to_datetime(df.index)
        
    if df.empty:
        return pd.DataFrame(), {}

    first_close = df['Close'].iloc[0]
    df['Equity'] = (df['Close'] / first_close) * INITIAL_CAPITAL
    
    yearly_ret = get_year_returns(df[['Equity']], INITIAL_CAPITAL)
    return df[['Equity']], yearly_ret

def run_yearly_comparison():
    print("🚀 연도별 전략 분석 시작 (2010 ~ 현재)")
    
    tickers = get_kosdaq150_tickers()
    start_date = '2010-01-01'
    end_date = datetime.now()
    
    # 벤치마크 로드
    benchmarks = [
        {'symbol': 'KS200', 'name': 'KOSPI200'},
        {'symbol': 'KQ11', 'name': 'KOSDAQ'}
    ]
    
    bench_results = {}
    
    for b in benchmarks:
        hist, yearly = get_benchmark_index(b['symbol'], b['name'], start_date, end_date)
        bench_results[b['symbol']] = {'name': b['name'], 'hist': hist, 'yearly': yearly}

    # 전략 실행
    results = {}
    histories = {} 
    
    for strat in STRATEGIES:
        s_id = strat['id']
        name = strat['name']
        p = strat['params']
        print(f"\n👉 [{name}] 시뮬레이션...")
        
        stock_data, valid_tickers = prepare_data(tickers, start_date, p['rsi_period'], p['sma_period'])
        
        ret, mdd, win, cnt, hist, trades = run_simulation(
            stock_data, valid_tickers, 
            max_holding_days=p['max_holding_days'],
            buy_threshold=p['rsi_buy_threshold'],
            sell_threshold=p['rsi_sell_threshold'],
            max_positions=p['max_positions'],
            loss_lockout_days=p['loss_lockout_days']
        )
        
        y_ret = get_year_returns(hist, INITIAL_CAPITAL)
        
        results[s_id] = {
            'name': name,
            'desc': strat['desc'],
            'total_ret': ret,
            'mdd': mdd,
            'yearly': y_ret
        }
        histories[s_id] = hist
        print(f"   Done (Total: {ret:.0f}%, MDD: {mdd:.0f}%)")

    # -------------------------------------------------------------------------
    # 리포트 생성
    # -------------------------------------------------------------------------
    
    # 모든 연도 집합 (KOSPI 기준)
    all_years = sorted(list(bench_results['KS200']['yearly'].keys()))
    
    print("\n" + "="*120)
    print(f"📊 연도별 수익률 비교 (Unit: %)")
    print("="*120)
    
    # Header
    header = f"| {'Year':^6} "
    for b in benchmarks:
        header += f"| {b['name']:^10} "
    for strat in STRATEGIES:
         header += f"| {strat['name']:^12} "
    header += "|"
    
    print(header)
    sep_line = "|" + "-"*8 
    for _ in benchmarks: sep_line += "|" + "-"*12 
    for _ in STRATEGIES: sep_line += "|" + "-"*14 
    sep_line += "|"
    print(sep_line)
    
    rows_text = []
    
    # 누적 수익률 계산용
    cum_ret = {}
    for b in benchmarks: cum_ret[b['symbol']] = 1.0
    for s in STRATEGIES: cum_ret[s['id']] = 1.0
    
    for year in all_years:
        row = f"| {year:<6} "
        
        # Benchmarks
        for b in benchmarks:
            b_ret = bench_results[b['symbol']]['yearly'].get(year, 0.0)
            row += f"| {b_ret:>10.2f}% "
            cum_ret[b['symbol']] *= (1 + b_ret/100)
            
        # Strategies
        for strat in STRATEGIES:
            s_ret = results[strat['id']]['yearly'].get(year, 0.0)
            row += f"| {s_ret:>12.2f}% "
            cum_ret[strat['id']] *= (1 + s_ret/100)
        
        row += "|"
        print(row)
        rows_text.append(row)

    print("-" * 120)
    
    # Total Summary
    summ_row = f"| {'TOTAL':<6} "
    for b in benchmarks:
        summ_row += f"| {(cum_ret[b['symbol']]-1)*100:>10.2f}% "
    for strat in STRATEGIES:
         summ_row += f"| {(cum_ret[strat['id']]-1)*100:>12.2f}% "
    summ_row += "|"
    print(summ_row)
    
    # MDD Row
    mdd_row = f"| {'MDD':<6} "
    
    for b in benchmarks:
        bh = bench_results[b['symbol']]['hist']
        if not bh.empty:
            equity = bh['Equity']
            val = ((equity - equity.cummax()) / equity.cummax()).min() * 100
            mdd_row += f"| {val:>10.2f}% "
        else:
            mdd_row += f"| {'-':>10} "

    for strat in STRATEGIES:
         mdd_row += f"| {results[strat['id']]['mdd']:>12.2f}% "
    mdd_row += "|"
    
    print(mdd_row)
    print("=" * 120)
    
    # 시각화 (누적 수익률 로그 스케일)
    plt.figure(figsize=(14, 7))
    
    # Plot Benchmarks
    colors = {'KS200': 'grey', 'KQ150': 'blue'}
    styles = {'KS200': '--', 'KQ150': ':'}
    
    for b in benchmarks:
        sym = b['symbol']
        hist = bench_results[sym]['hist']
        if not hist.empty:
            final_ret = (cum_ret[sym]-1)*100
            plt.plot(hist.index, hist['Equity'], 
                     label=f"{b['name']} ({final_ret:.0f}%)", 
                     color=colors.get(sym, 'black'), 
                     linewidth=1.5, 
                     linestyle=styles.get(sym, '-'))
        
    for strat in STRATEGIES:
        h = histories[strat['id']]
        if h.empty: continue
        r = results[strat['id']]
        plt.plot(h.index, h['Equity'], label=f"{r['name']} ({(r['total_ret']):.0f}%)", alpha=0.8)
        
    plt.title("Cumulative Return Comparison (2010-2025)")
    plt.yscale('log') # 로그 스케일
    plt.grid(True, which="both", ls="-", alpha=0.2)
    plt.legend()
    
    chart_path = 'reports/yearly_options_comparison.png'
    plt.savefig(chart_path)
    print(f"\n✅ 차트 저장: {chart_path}")
    
    # MD 저장
    md_path = 'reports/yearly_options_comparison.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# 연도별 전략 성과 비교 (2010 ~ 현재)\n\n")
        f.write(f"**실행 일시:** {datetime.now()}\n\n")
        
        f.write("### 1. 연도별 수익률 (%)\n")
        f.write(header + "\n")
        # MD Table Separator
        sep = "| :--- " + "| :--- "*len(benchmarks) + "| :--- "*len(STRATEGIES) + "|"
        f.write(sep + "\n")
        
        for r in rows_text:
            f.write(r + "\n")
        f.write(summ_row + "\n")
        f.write(mdd_row + "\n")
        
        f.write("\n### 2. 전략 상세\n")
        for s in STRATEGIES:
            f.write(f"- **{s['name']}**: {s['desc']}\n")
            
    print(f"✅ 리포트 저장: {md_path}")

if __name__ == "__main__":
    run_yearly_comparison()
