import pandas as pd
import numpy as np
import duckdb
import os
import glob
import itertools
import time
from datetime import datetime
import FinanceDataReader as fdr

# ---------------------------------------------------------
# 1. 설정 및 경로
# ---------------------------------------------------------
DB_PATH = '/home/longman6/projects/stock-collector/data/stock.duckdb'
UNIVERSE_DIR = '../data/kosdaq150'
START_DATE = '2016-01-01'
INITIAL_CAPITAL = 100_000_000

TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# 상위 3개 전략 파라미터
STRATEGIES = [
    {'name': 'RSI 6', 'rsi_w': 6, 'sma_w': 50, 'buy': 30, 'sell': 70, 'hold': 20, 'pos': 3},
    {'name': 'RSI 3', 'rsi_w': 3, 'sma_w': 110, 'buy': 22, 'sell': 80, 'hold': 15, 'pos': 3},
    {'name': 'RSI 5', 'rsi_w': 5, 'sma_w': 150, 'buy': 24, 'sell': 80, 'hold': 25, 'pos': 3}
]

def load_universe_map(directory):
    universe_map = {}
    files = glob.glob(os.path.join(directory, "*.csv"))
    for f in files:
        year = os.path.basename(f).split('.')[0]
        try:
            df = pd.read_csv(f)
            code_col = '종목코드' if '종목코드' in df.columns else df.columns[0]
            codes = df[code_col].astype(str).str.zfill(6).tolist()
            universe_map[int(year)] = codes
        except: pass
    return universe_map

def calculate_rsi(prices, window):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def fetch_data_for_strategies(conn, universe_map, rsi_windows):
    all_symbols = set()
    for codes in universe_map.values():
        all_symbols.update(codes)
    
    symbols_str = ", ".join([f"'{s}'" for s in all_symbols])
    # 넉넉하게 이전 데이터 포함
    fetch_start = '2015-01-01'
    
    print(f"Loading data from DuckDB...")
    query = f"SELECT symbol, date, close FROM ohlcv_daily WHERE symbol IN ({symbols_str}) AND date >= '{fetch_start}' ORDER BY symbol, date"
    df = conn.execute(query).df()
    
    data_map = {}
    for rsi_w in rsi_windows:
        data_map[rsi_w] = {}
        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('date').set_index('date')
            group.index = pd.to_datetime(group.index)
            group[f'RSI_{rsi_w}'] = calculate_rsi(group['close'], rsi_w)
            data_map[rsi_w][symbol] = group
    return data_map

def run_backtest_yearly(strategy, u_map, all_dates, stock_data_rsi):
    rsi_window = strategy['rsi_w']
    sma_window = strategy['sma_w']
    buy_threshold = strategy['buy']
    sell_threshold = strategy['sell']
    max_hold = strategy['hold']
    max_pos = strategy['pos']
    
    cash = INITIAL_CAPITAL
    positions = {}
    equity_curve = []
    
    current_year_cached = 0
    relevant_data = {}
    
    for current_date in all_dates:
        year = current_date.year
        if year != current_year_cached:
            current_year_cached = year
            symbols = u_map.get(year, [])
            relevant_data = {}
            for s in symbols:
                if s in stock_data_rsi:
                    df = stock_data_rsi[s].copy()
                    df['SMA'] = df['close'].rolling(window=sma_window).mean()
                    relevant_data[s] = df
        
        # 1. 매도
        curr_positions_val = 0
        to_sell = []
        for s, pos in positions.items():
            if s not in relevant_data or current_date not in relevant_data[s].index:
                curr_positions_val += pos['shares'] * pos['last_price']
                continue
            
            row = relevant_data[s].loc[current_date]
            close = row['close']
            rsi = row[f'RSI_{rsi_window}']
            pos['last_price'] = close
            pos['held'] += 1
            curr_positions_val += pos['shares'] * close
            
            if rsi >= sell_threshold or pos['held'] >= max_hold:
                to_sell.append((s, close))
        
        total_equity = cash + curr_positions_val
        equity_curve.append({'date': current_date, 'equity': total_equity})
        
        for s, price in to_sell:
            pos = positions.pop(s)
            sell_val = pos['shares'] * price
            cost = sell_val * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_val - cost)
            
        # 2. 매수
        open_slots = max_pos - len(positions)
        if open_slots > 0:
            candidates = []
            for s, df in relevant_data.items():
                if s in positions or current_date not in df.index: continue
                row = df.loc[current_date]
                if pd.isna(row['SMA']) or pd.isna(row[f'RSI_{rsi_window}']): continue
                
                if row[f'RSI_{rsi_window}'] <= buy_threshold and row['close'] > row['SMA']:
                    candidates.append({'s': s, 'rsi': row[f'RSI_{rsi_window}'], 'p': row['close']})
            
            candidates.sort(key=lambda x: x['rsi'])
            for cand in candidates[:open_slots]:
                target = (cash + sum(p['shares']*p['last_price'] for p in positions.values())) / max_pos
                buy_amt = min(target, cash) / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                shares = int(buy_amt / cand['p'])
                if shares > 0:
                    cost = shares * cand['p'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    cash -= cost
                    positions[cand['s']] = {'shares': shares, 'buy_price': cand['p'], 'last_price': cand['p'], 'held': 0}

    # 연도별 수익률 계산
    eq_df = pd.DataFrame(equity_curve).set_index('date')
    yearly_returns = {}
    years = eq_df.index.year.unique()
    for yr in years:
        yr_data = eq_df[eq_df.index.year == yr]
        if not yr_data.empty:
            start_val = yr_data['equity'].iloc[0]
            # 전년도 마지막 가치가 있으면 그것을 시작으로 사용 (더 정확함)
            prev_year_data = eq_df[eq_df.index.year == yr-1]
            if not prev_year_data.empty:
                start_val = prev_year_data['equity'].iloc[-1]
            else:
                # 데이터 시작 연도인 경우 초기 자본 대비
                if yr == years[0]:
                    start_val = INITIAL_CAPITAL
            
            end_val = yr_data['equity'].iloc[-1]
            yr_ret = (end_val / start_val - 1) * 100
            yearly_returns[yr] = yr_ret
            
    return yearly_returns

def main():
    u_map = load_universe_map(UNIVERSE_DIR)
    conn = duckdb.connect(DB_PATH, read_only=True)
    all_dates = conn.execute(f"SELECT DISTINCT date FROM ohlcv_daily WHERE date >= '{START_DATE}' ORDER BY date").df()['date'].tolist()
    all_dates = pd.to_datetime(all_dates)
    
    rsi_windows = list(set([s['rsi_w'] for s in STRATEGIES]))
    data_map = fetch_data_for_strategies(conn, u_map, rsi_windows)
    
    all_yearly_results = {}
    
    # 1. 전략별 연도별 수익률
    for strat in STRATEGIES:
        print(f"Analyzing {strat['name']}...")
        rets = run_backtest_yearly(strat, u_map, all_dates, data_map[strat['rsi_w']])
        all_yearly_results[strat['name']] = rets
        
    # 2. 코스피 200 및 코스닥 150 연도별 수익률
    print("Fetching Market Indices...")
    indices = {
        'KOSPI 200': 'KS200',
        'KOSDAQ 150': 'KQ150' # FDR에서 코스닥 150 인덱스 지원 여부 확인 필요, 안되면 KQ11 사용
    }
    
    for idx_name, idx_code in indices.items():
        try:
            print(f"Fetching {idx_name} ({idx_code})...")
            idx_df = fdr.DataReader(idx_code, START_DATE, '2026-01-16')
            if idx_df.empty:
                raise ValueError(f"{idx_code} data is empty")
        except Exception as e:
            print(f"Warning: Failed to fetch {idx_name} ({idx_code}): {e}")
            if idx_code == 'KQ150':
                print("Trying KOSDAQ Index (KQ11) as fallback...")
                try:
                    idx_df = fdr.DataReader('KQ11', START_DATE, '2026-01-16')
                    idx_name = 'KOSDAQ (Index)'
                except:
                    print("Failed to fetch KOSDAQ index as well.")
                    continue
            else:
                continue
                
        idx_yearly = {}
        years = idx_df.index.year.unique()
        for yr in years:
            yr_data = idx_df[idx_df.index.year == yr]
            prev_yr_data = idx_df[idx_df.index.year == yr-1]
            
            start_price = yr_data['Close'].iloc[0]
            if not prev_yr_data.empty:
                start_price = prev_yr_data['Close'].iloc[-1]
                
            end_price = yr_data['Close'].iloc[-1]
            idx_yearly[yr] = (end_price / start_price - 1) * 100
        all_yearly_results[idx_name] = idx_yearly
    
    # 결과 출력
    final_df = pd.DataFrame(all_yearly_results)
    print("\n### 연도별 수익률 비교 (Unit: %)")
    print(final_df.to_markdown())
    
    # 리포트 생성
    report_content = f"""
# 전략별 연도별 수익률 상세 분석 보고서

본 보고서는 상위 3개 RSI 최적화 전략의 연도별 성과를 코스피 200 및 코스닥 150 지수와 비교 분석한 결과입니다.

## 연도별 수익률 비교 (%)
{final_df.to_markdown()}

## 주요 분석 결과
- **시장 대비 성과**: 주력 전략들이 대부분의 연도에서 코스피 200 및 코스닥 150을 상회하는지 확인할 수 있습니다.
- **안정성**: 하락장(예: 2018, 2022)에서의 방어력을 확인할 수 있습니다.
- **장기 요약**: 누적 수익률뿐만 아니라 연도별 일관성 있는 수익 창출 능력을 보여줍니다.

*자료: DuckDB ohlcv_daily, FinanceDataReader (KS200, KQ150/KQ11)*
"""
    with open('../reports/yearly_returns_analysis.md', 'w', encoding='utf-8') as f:
        f.write(report_content)
    print("\nReport saved to reports/yearly_returns_analysis.md")

if __name__ == "__main__":
    main()
