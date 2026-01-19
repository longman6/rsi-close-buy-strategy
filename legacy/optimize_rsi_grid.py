#!/usr/bin/env python3
"""
KOSDAQ 150 RSI 전략 그리드 서치 최적화
- 병렬 처리: 20 jobs
- 고정: RSI Window=3, Loss Cooldown=90 days
"""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import FinanceDataReader as fdr
from multiprocessing import Pool, cpu_count, freeze_support
import itertools
import time

# ============================================================
# 고정 설정
# ============================================================
DATA_START_DATE = '2008-01-01'
TEST_START_DATE = '2010-01-01'
RSI_WINDOW = 4
LOSS_LOCKOUT_DAYS = 90
INITIAL_CAPITAL = 100_000_000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001
N_JOBS = 20

# ============================================================
# 최적화 범위
# ============================================================
SMA_LIST = [30, 50, 70, 90, 110, 130, 150]          # 7개
BUY_LIST = [20, 22, 24, 26, 28, 30, 32]             # 7개
SELL_LIST = [70, 72, 74, 76, 78, 80]                # 6개
POS_LIST = [3, 5, 7, 10]                            # 4개
HOLD_LIST = [10, 15, 20, 25, 30, 40]                # 6개

# 글로벌 데이터 (워커 프로세스용)
worker_stock_data = {}
worker_valid_tickers = []

# ============================================================
# 함수 정의
# ============================================================
def get_kosdaq150_tickers():
    """KOSDAQ 150 종목 코드 로드"""
    filename = 'data/kosdaq150_list.txt'
    tickers = []
    try:
        import ast
        if not os.path.exists(filename):
            return []
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    tickers.append(data['code'])
                except:
                    pass
        return tickers
    except:
        return []

def calculate_rsi(close, window):
    """RSI 계산"""
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def download_stock_data(tickers, start_date):
    """주식 데이터 다운로드 및 지표 사전 계산"""
    stock_data = {}
    valid_tickers = []
    
    total = len(tickers)
    print(f"\n📥 {total}개 종목 데이터 다운로드 시작...")
    
    for i, ticker in enumerate(tickers, 1):
        try:
            df = fdr.DataReader(ticker, start_date)
            if df is None or df.empty or len(df) < 200:
                continue
            
            # RSI 계산
            df['RSI'] = calculate_rsi(df['Close'], RSI_WINDOW)
            
            # 모든 SMA 사전 계산
            for sma in SMA_LIST:
                df[f'SMA_{sma}'] = df['Close'].rolling(window=sma).mean()
            
            stock_data[ticker] = df
            valid_tickers.append(ticker)
            
            if i % 30 == 0:
                print(f"  진행: {i}/{total} ({i/total*100:.1f}%)")
        except:
            pass
    
    print(f"\n✅ 다운로드 완료: {len(valid_tickers)}개 종목")
    return stock_data, valid_tickers

def init_worker(stock_data, valid_tickers):
    """워커 프로세스 초기화"""
    global worker_stock_data, worker_valid_tickers
    worker_stock_data = stock_data
    worker_valid_tickers = valid_tickers

def run_simulation(params):
    """단일 파라미터 조합 시뮬레이션"""
    sma_window, buy_threshold, sell_threshold, max_positions, max_holding_days = params
    
    stock_data = worker_stock_data
    valid_tickers = worker_valid_tickers
    
    allocation_per_stock = 1.0 / max_positions
    sma_col = f'SMA_{sma_window}'
    
    # 모든 거래일 수집
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    test_start = pd.to_datetime(TEST_START_DATE)
    all_dates = [d for d in all_dates if d >= test_start]
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0
    lockout_until = {}
    
    for date in all_dates:
        # 보유일 증가
        for pos in positions.values():
            pos['held_bars'] += 1
        
        # 매도 로직
        current_positions_value = 0
        tickers_to_sell = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']
                
                if rsi >= sell_threshold or pos['held_bars'] >= max_holding_days:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price
        
        total_equity = cash + current_positions_value
        history.append(total_equity)
        
        # 매도 실행
        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            invested = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            profit = (sell_amt - cost) - invested
            if profit > 0: wins += 1
            trades_count += 1
            
            price_return = sell_price - pos['buy_price']
            if price_return < 0 and LOSS_LOCKOUT_DAYS > 0:
                lockout_until[ticker] = date + timedelta(days=LOSS_LOCKOUT_DAYS)
        
        # 자산 재계산
        current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
        total_equity = cash + current_positions_value
        
        # 매수 로직
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            
            for ticker in valid_tickers:
                if ticker in positions:
                    continue
                if ticker in lockout_until:
                    if date <= lockout_until[ticker]:
                        continue
                    else:
                        del lockout_until[ticker]
                
                df = stock_data[ticker]
                if date not in df.index:
                    continue
                
                row = df.loc[date]
                if pd.isna(row.get(sma_col)) or pd.isna(row['RSI']):
                    continue
                
                if row['Close'] > row[sma_col] and row['RSI'] <= buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
                    total_equity = cash + current_positions_value
                    
                    target = total_equity * allocation_per_stock
                    invest = min(target, cash)
                    max_buy_val = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 10000:
                        continue
                    
                    shares = int(max_buy_val / can['price'])
                    if shares > 0:
                        buy_val = shares * can['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[can['ticker']] = {
                            'shares': shares,
                            'buy_price': can['price'],
                            'last_price': can['price'],
                            'buy_date': date,
                            'held_bars': 0
                        }
    
    # 결과 계산
    if not history:
        return None
    
    final_equity = history[-1]
    ret = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    equity_curve = np.array(history)
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    mdd = drawdown.min() * 100
    
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
    
    return {
        'SMA': sma_window,
        'Buy': buy_threshold,
        'Sell': sell_threshold,
        'MaxPos': max_positions,
        'MaxHold': max_holding_days,
        'Return': ret,
        'MDD': mdd,
        'WinRate': win_rate,
        'Trades': trades_count
    }

def main():
    print("=" * 70)
    print("🚀 KOSDAQ 150 RSI 전략 일괄 최적화 (RSI 3, 4, 5, 6, 7)")
    print("=" * 70)
    
    # 데이터 다운로드 (1회 수행)
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("❌ 종목 로드 실패")
        return
    
    # RSI 계산은 루프 내에서 수행할 것이므로 다운로드 시에는 지표 계산 제외
    raw_stock_data = {}
    valid_tickers = []
    
    total = len(tickers)
    print(f"\n📥 {total}개 종목 데이터 다운로드 시작...")
    for i, ticker in enumerate(tickers, 1):
        try:
            df = fdr.DataReader(ticker, DATA_START_DATE)
            if df is None or df.empty or len(df) < 200:
                continue
            
            # 모든 SMA 사전 계산 (RSI와 무관하므로 1회만 수행)
            for sma in SMA_LIST:
                df[f'SMA_{sma}'] = df['Close'].rolling(window=sma).mean()
            
            raw_stock_data[ticker] = df
            valid_tickers.append(ticker)
            if i % 30 == 0:
                print(f"  진행: {i}/{total} ({i/total*100:.1f}%)")
        except:
            pass
    print(f"\n✅ 데이터 로드 완료: {len(valid_tickers)}개 종목")

    RSI_LIST = [3, 4, 5, 6, 7]
    for rsi_win in RSI_LIST:
        print("\n" + "#" * 70)
        print(f"📈 RSI Window = {rsi_win} 최적화 시작")
        print("#" * 70)
        
        # 해당 RSI에 맞춰 지표 재계산
        stock_data = {}
        for ticker, df in raw_stock_data.items():
            df_copy = df.copy()
            df_copy['RSI'] = calculate_rsi(df_copy['Close'], rsi_win)
            stock_data[ticker] = df_copy

        # 조합 수 계산
        all_combos = list(itertools.product(SMA_LIST, BUY_LIST, SELL_LIST, POS_LIST, HOLD_LIST))
        total_combos = len(all_combos)
        
        print(f"🧪 총 조합 수: {total_combos:,}개 | 병렬 처리: {N_JOBS} jobs")
        start_time = time.time()
        
        results = []
        completed = 0
        
        with Pool(processes=N_JOBS, initializer=init_worker, initargs=(stock_data, valid_tickers)) as pool:
            for result in pool.imap_unordered(run_simulation, all_combos):
                results.append(result)
                completed += 1
                if completed % 100 == 0 or completed == total_combos:
                    elapsed = time.time() - start_time
                    pct = completed / total_combos * 100
                    eta = (elapsed / completed) * (total_combos - completed) / 60 if completed > 0 else 0
                    print(f"  [RSI {rsi_win}] 📊 진행: {completed:,}/{total_combos:,} ({pct:.1f}%) | 경과: {elapsed/60:.1f}분 | 남은: {eta:.1f}분", flush=True)
        
        elapsed = time.time() - start_time
        print(f"\n✅ RSI {rsi_win} 최적화 완료! 소요 시간: {elapsed/60:.1f}분")
        
        # 결과 정리 및 저장
        results = [r for r in results if r is not None]
        df_res = pd.DataFrame(results)
        df_res = df_res[df_res['Trades'] > 10]
        df_res = df_res.sort_values('Return', ascending=False)
        
        os.makedirs('reports', exist_ok=True)
        # 파일명 결정
        if rsi_win == 3:
            csv_path = 'reports/rsi_optimization_results.csv'
            report_path = 'reports/rsi_optimization_report.md'
        elif rsi_win == 5:
            csv_path = 'reports/rsi5_optimization_results.csv'
            report_path = 'reports/rsi5_optimization_report.md'
        else:
            csv_path = f'reports/rsi{rsi_win}_optimization_results.csv'
            report_path = f'reports/rsi{rsi_win}_optimization_report.md'
            
        df_res.to_csv(csv_path, index=False)
        
        # 상위 결과 및 안정형 결과 추출
        top_10 = df_res.head(10)
        stable_df = df_res[df_res['MDD'] > -40].head(5)
        
        # 보고서 작성
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# KOSDAQ 150 RSI {rsi_win} 전략 최적화 결과\n")
            f.write(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"소요 시간: {elapsed/60:.1f}분\n\n")
            f.write(f"## 고정 파라미터\n- RSI Window: {rsi_win}\n- Loss Cooldown: {LOSS_LOCKOUT_DAYS} days\n\n")
            f.write(f"## 최적화 범위\n| 파라미터 | 값 |\n|:---|:---|\n")
            f.write(f"| SMA Window | {SMA_LIST} |\n| Buy Limit | {BUY_LIST} |\n| Sell Limit | {SELL_LIST} |\n")
            f.write(f"| Max Positions | {POS_LIST} |\n| Max Holding | {HOLD_LIST} |\n\n")
            f.write(f"## 총 조합: {total_combos:,}개\n\n---\n\n")
            f.write(f"## 🏆 Top 10 수익률 순위\n{top_10.to_markdown(index=False, floatfmt='.2f')}\n\n---\n\n")
            f.write(f"## 🛡️ 안정형 Top 5 (MDD > -40%)\n")
            f.write(f"{stable_df.to_markdown(index=False, floatfmt='.2f') if not stable_df.empty else '해당 없음'}\n")
        
        print(f"📁 결과 저장 완료: {csv_path}, {report_path}")

    print(f"\n✨ 모든 RSI 최적화 작업이 완료되었습니다! ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

if __name__ == "__main__":
    freeze_support()
    main()
