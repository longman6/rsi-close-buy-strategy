#!/usr/bin/env python3
"""
KOSPI 200 RSI 전략 간단 최적화 스크립트
- RSI 기간, BUY/SELL 기준, SMA만 조정
- 나머지 파라미터는 고정 (max_positions=7, max_holding_days=20, loss_lockout_days=90)
"""
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import os
import ast
from datetime import datetime, timedelta
from itertools import product
from multiprocessing import Pool, cpu_count

# ---------------------------------------------------------
# 설정
# ---------------------------------------------------------
START_DATE = '2015-01-01'  # 최근 10년 데이터로 최적화
INITIAL_CAPITAL = 100000000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# 고정 파라미터
MAX_POSITIONS = 7
MAX_HOLDING_DAYS = 20
LOSS_LOCKOUT_DAYS = 90

# 최적화 범위 (RSI 기간 확장)
RSI_WINDOWS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14]
BUY_THRESHOLDS = [10, 15, 20, 25, 30, 35]
SELL_THRESHOLDS = [70, 75, 80, 85, 90]
SMA_WINDOWS = [100, 150, 200]

# ---------------------------------------------------------
# 데이터 준비 (한 번만 로드)
# ---------------------------------------------------------
def get_kospi200_tickers():
    """KOSPI 200 종목 로드"""
    filename = 'data/kospi200_list.txt'
    tickers = []
    names = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    code = data['code']
                    if not code.isdigit():
                        continue
                    tickers.append(code)
                    names[code] = data['name']
                except:
                    pass
        return tickers, names
    except Exception as e:
        print(f"[오류] {e}")
        return [], {}

def calculate_rsi(data, window):
    """RSI 계산"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def download_all_data(tickers):
    """모든 종목 데이터를 한 번에 다운로드"""
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
    fetch_start = (start_dt - timedelta(days=300)).strftime("%Y-%m-%d")
    
    print(f"📥 {len(tickers)}개 종목 데이터 다운로드 중...")
    raw_data = {}
    
    for i, ticker in enumerate(tickers):
        try:
            df = fdr.DataReader(ticker, fetch_start)
            if df is not None and not df.empty and len(df) > 200:
                raw_data[ticker] = df
            if (i + 1) % 50 == 0:
                print(f"   진행: {i+1}/{len(tickers)}")
        except:
            continue
    
    print(f"✅ {len(raw_data)}개 종목 다운로드 완료")
    return raw_data

def prepare_data_with_indicators(raw_data, rsi_window, sma_window):
    """지표 계산"""
    start_dt = datetime.strptime(START_DATE, "%Y-%m-%d")
    stock_data = {}
    valid_tickers = []
    
    for ticker, df in raw_data.items():
        try:
            df = df.copy()
            if len(df) < max(sma_window, rsi_window) + 10:
                continue
            
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
            df = df[df.index >= start_dt]
            
            if not df.empty:
                stock_data[ticker] = df
                valid_tickers.append(ticker)
        except:
            continue
    
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 시뮬레이션 (간소화)
# ---------------------------------------------------------
def run_simulation(stock_data, valid_tickers, buy_threshold, sell_threshold):
    """백테스트 실행"""
    allocation = 1.0 / MAX_POSITIONS
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    lockout_until = {}
    
    for date in all_dates:
        # 평가 & 매도
        current_value = 0
        to_sell = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                price = df.loc[date, 'Close']
                pos['last_price'] = price
                rsi = df.loc[date, 'RSI']
                
                if rsi >= sell_threshold:
                    to_sell.append({'ticker': ticker, 'reason': 'SIGNAL'})
                elif pos['held_bars'] >= MAX_HOLDING_DAYS:
                    to_sell.append({'ticker': ticker, 'reason': 'FORCE'})
            else:
                price = pos['last_price']
            current_value += pos['shares'] * price
        
        total_equity = cash + current_value
        history.append({'Date': date, 'Equity': total_equity})
        
        # 매도 실행
        for item in to_sell:
            ticker = item['ticker']
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            buy_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_cost) / buy_cost * 100
            trades.append({'Return': net_return})
            
            if (sell_price - pos['buy_price']) < 0 and LOSS_LOCKOUT_DAYS > 0:
                lockout_until[ticker] = date + timedelta(days=LOSS_LOCKOUT_DAYS)
        
        # 매수
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                if ticker in lockout_until and date <= lockout_until[ticker]: continue
                
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if row['Close'] > row['SMA'] and row['RSI'] <= buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for c in candidates[:open_slots]:
                    current_value = sum(p['shares'] * p['last_price'] for p in positions.values())
                    total_equity = cash + current_value
                    
                    target = total_equity * allocation
                    invest = min(target, cash)
                    max_buy = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy < 10000: continue
                    shares = int(max_buy / c['price'])
                    if shares > 0:
                        buy_val = shares * c['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[c['ticker']] = {
                            'shares': shares, 
                            'buy_price': c['price'],
                            'last_price': c['price'],
                            'held_bars': 0
                        }
        
        for pos in positions.values():
            pos['held_bars'] += 1
    
    # 결과 계산
    if not history:
        return 0, 0, 0, 0
    
    hist_df = pd.DataFrame(history).set_index('Date')
    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100
    
    trades_df = pd.DataFrame(trades)
    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
    
    return final_ret, mdd, win_rate, len(trades_df)

# ---------------------------------------------------------
# 최적화 워커
# ---------------------------------------------------------
def run_single_optimization(params):
    """단일 파라미터 조합 테스트"""
    rsi_window, buy_th, sell_th, sma_window, raw_data = params
    
    # 지표 계산
    stock_data, valid_tickers = prepare_data_with_indicators(raw_data, rsi_window, sma_window)
    if not stock_data:
        return None
    
    # 시뮬레이션
    ret, mdd, win_rate, count = run_simulation(stock_data, valid_tickers, buy_th, sell_th)
    
    return {
        'rsi_window': rsi_window,
        'buy_threshold': buy_th,
        'sell_threshold': sell_th,
        'sma_window': sma_window,
        'return': ret,
        'mdd': mdd,
        'win_rate': win_rate,
        'trades': count
    }

def main():
    print("="*60)
    print("🚀 KOSPI 200 RSI 전략 간단 최적화")
    print("="*60)
    print(f"테스트 기간: {START_DATE} ~ 현재")
    print(f"RSI 기간: {RSI_WINDOWS}")
    print(f"BUY 기준: {BUY_THRESHOLDS}")
    print(f"SELL 기준: {SELL_THRESHOLDS}")
    print(f"SMA 기간: {SMA_WINDOWS}")
    
    total_combinations = len(RSI_WINDOWS) * len(BUY_THRESHOLDS) * len(SELL_THRESHOLDS) * len(SMA_WINDOWS)
    print(f"\n📊 총 {total_combinations}개 조합 테스트 예정")
    print("="*60)
    
    # 데이터 다운로드
    tickers, names = get_kospi200_tickers()
    raw_data = download_all_data(tickers)
    
    # 모든 조합 테스트
    results = []
    completed = 0
    
    for rsi_window in RSI_WINDOWS:
        for sma_window in SMA_WINDOWS:
            # 지표 계산 (rsi_window, sma_window별로 한 번만)
            stock_data, valid_tickers = prepare_data_with_indicators(raw_data, rsi_window, sma_window)
            if not stock_data:
                continue
            
            for buy_th in BUY_THRESHOLDS:
                for sell_th in SELL_THRESHOLDS:
                    ret, mdd, win_rate, count = run_simulation(stock_data, valid_tickers, buy_th, sell_th)
                    
                    results.append({
                        'rsi_window': rsi_window,
                        'buy_threshold': buy_th,
                        'sell_threshold': sell_th,
                        'sma_window': sma_window,
                        'return': ret,
                        'mdd': mdd,
                        'win_rate': win_rate,
                        'trades': count
                    })
                    
                    completed += 1
                    if completed % 50 == 0:
                        print(f"   진행: {completed}/{total_combinations}")
    
    # 결과 정렬
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('return', ascending=False)
    
    print("\n" + "="*60)
    print("🏆 TOP 10 최적 파라미터 조합")
    print("="*60)
    
    top10 = results_df.head(10)
    print("\n| 순위 | RSI | BUY | SELL | SMA | 수익률 | MDD | 승률 | 거래수 |")
    print("|:---:|:---:|:---:|:---:|:---:|---:|---:|---:|---:|")
    
    for i, row in top10.iterrows():
        rank = top10.index.get_loc(i) + 1
        print(f"| {rank} | {int(row['rsi_window'])} | {int(row['buy_threshold'])} | {int(row['sell_threshold'])} | {int(row['sma_window'])} | {row['return']:.2f}% | {row['mdd']:.2f}% | {row['win_rate']:.1f}% | {int(row['trades'])} |")
    
    # 리포트 저장
    report_path = "reports/kospi200_optimization_result.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# KOSPI 200 RSI 전략 최적화 결과\n\n")
        f.write(f"**생성일:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**테스트 기간:** {START_DATE} ~ 현재\n\n")
        f.write(f"**테스트 조합:** {total_combinations}개\n\n")
        f.write("## TOP 20 최적 파라미터\n\n")
        f.write("| 순위 | RSI | BUY | SELL | SMA | 수익률 | MDD | 승률 | 거래수 |\n")
        f.write("|:---:|:---:|:---:|:---:|:---:|---:|---:|---:|---:|\n")
        
        for i, row in results_df.head(20).iterrows():
            rank = results_df.head(20).index.get_loc(i) + 1
            f.write(f"| {rank} | {int(row['rsi_window'])} | {int(row['buy_threshold'])} | {int(row['sell_threshold'])} | {int(row['sma_window'])} | {row['return']:.2f}% | {row['mdd']:.2f}% | {row['win_rate']:.1f}% | {int(row['trades'])} |\n")
    
    print(f"\n✅ 결과 저장: {report_path}")
    
    # CSV 저장
    csv_path = "reports/kospi200_optimization_all.csv"
    results_df.to_csv(csv_path, index=False)
    print(f"✅ 전체 결과 CSV: {csv_path}")

if __name__ == "__main__":
    main()
