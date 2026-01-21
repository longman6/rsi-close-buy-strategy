import pandas as pd
import numpy as np
import duckdb
import os
import glob
import itertools
import time
from datetime import datetime, timedelta
from multiprocessing import Pool, Manager, cpu_count

# ---------------------------------------------------------
# 1. 설정 및 경로
# ---------------------------------------------------------
DB_PATH = '/home/longman6/projects/stock-collector/data/stock.duckdb'
UNIVERSE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'kosdaq150'))
START_DATE = '2016-01-01'
INITIAL_CAPITAL = 100_000_000
REPORT_INTERVAL = 600 # 10분 (600초)

# 수수료 및 슬리피지
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# 전역 변수 (Worker용)
worker_universe_map = {}
worker_all_dates = []

def init_worker(u_map, dates):
    global worker_universe_map, worker_all_dates
    worker_universe_map = u_map
    worker_all_dates = dates

# ---------------------------------------------------------
# 2. 데이터 유틸리티
# ---------------------------------------------------------
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

def fetch_all_data(conn, universe_map, rsi_windows):
    """모든 연도 종목의 데이터를 한 번에 로드 (메모리 주의)"""
    all_symbols = set()
    for codes in universe_map.values():
        all_symbols.update(codes)
    
    symbols_str = ", ".join([f"'{s}'" for s in all_symbols])
    # SMA 200과 RSI를 위해 시작일 이전 데이터 포함
    fetch_start = (pd.to_datetime(START_DATE) - timedelta(days=400)).strftime('%Y-%m-%d')
    
    print(f"Loading data for {len(all_symbols)} symbols from DuckDB...")
    query = f"SELECT symbol, date, close FROM ohlcv_daily WHERE symbol IN ({symbols_str}) AND date >= '{fetch_start}' ORDER BY symbol, date"
    df = conn.execute(query).df()
    
    stock_data_base = {}
    for rsi_w in rsi_windows:
        stock_data_base[rsi_w] = {}
        for symbol, group in df.groupby('symbol'):
            group = group.sort_values('date').set_index('date')
            group.index = pd.to_datetime(group.index)
            group[f'RSI_{rsi_w}'] = calculate_rsi(group['close'], rsi_w)
            stock_data_base[rsi_w][symbol] = group
            
    return stock_data_base

# ---------------------------------------------------------
# 3. 백테스트 코어 (병렬 호출용)
# ---------------------------------------------------------
def run_backtest_core(params):
    rsi_window, sma_window, buy_threshold, sell_threshold, max_hold, max_pos, stock_data_rsi = params
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0
    lockout_until = {} # {symbol: expiry_date}
    
    current_year = 0
    relevant_data = {}
    
    for current_date in worker_all_dates:
        year = current_date.year
        if year != current_year:
            current_year = year
            symbols = worker_universe_map.get(year, [])
            # 현재 연도/유니버스에 해당하는 데이터 및 SMA 계산
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
        history.append(total_equity)
        
        for s, price in to_sell:
            pos = positions.pop(s)
            sell_val = pos['shares'] * price
            cost = sell_val * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_val - cost)
            if (sell_val - cost) > (pos['shares'] * pos['buy_price'] * (1+TX_FEE_RATE+SLIPPAGE_RATE)):
                wins += 1
            else:
                # 손실 발생 시 90일 쿨다운 설정
                lockout_until[s] = current_date + timedelta(days=90)
            trades_count += 1
            
        # 2. 매수
        open_slots = max_pos - len(positions)
        if open_slots > 0:
            candidates = []
            for s, df in relevant_data.items():
                if s in positions or current_date not in df.index: continue
                # 쿨다운 체크
                if s in lockout_until:
                    if current_date <= lockout_until[s]:
                        continue
                    else:
                        del lockout_until[s]
                
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

    final_ret = (history[-1] / INITIAL_CAPITAL - 1) * 100
    mdd = ((pd.Series(history) - pd.Series(history).cummax()) / pd.Series(history).cummax()).min() * 100
    wr = (wins / trades_count * 100) if trades_count > 0 else 0
    
    return {
        'RSI_W': rsi_window, 'SMA_W': sma_window, 'Buy': buy_threshold, 'Sell': sell_threshold, 
        'Hold': max_hold, 'Pos': max_pos, 'Ret': final_ret, 'MDD': mdd, 'WR': wr, 'Trades': trades_count
    }

# ---------------------------------------------------------
# 4. 메인 최적화 로직
# ---------------------------------------------------------
def run_optimization():
    u_map = load_universe_map(UNIVERSE_DIR)
    conn = duckdb.connect(DB_PATH, read_only=True)
    dates = conn.execute(f"SELECT DISTINCT date FROM ohlcv_daily WHERE date >= '{START_DATE}' ORDER BY date").df()['date'].tolist()
    dates = pd.to_datetime(dates)
    
    rsi_windows = [3, 4, 5, 6, 7]
    stock_data_base = fetch_all_data(conn, u_map, rsi_windows)
    
    # 파라미터 그리드 (사용자 지정 범위)
    sma_grids = [30, 50, 70, 90, 110, 130, 150]
    buy_grids = [20, 22, 24, 26, 28, 30, 32]
    sell_grids = [70, 72, 74, 76, 78, 80]
    hold_grids = [10, 15, 20, 25, 30, 40]
    pos_grids = [3, 5, 7, 10]
    
    results = []
    total_start = time.time()
    
    for rsi_w in rsi_windows:
        print(f"\n[Optimizing RSI {rsi_w}]...")
        combinations = list(itertools.product(sma_grids, buy_grids, sell_grids, hold_grids, pos_grids))
        # 파라미터 패키징 (stock_data_rsi 포함)
        work_args = [(rsi_w, c[0], c[1], c[2], c[3], c[4], stock_data_base[rsi_w]) for c in combinations]
        
        with Pool(processes=16, initializer=init_worker, initargs=(u_map, dates)) as pool:
            # 10분 보고를 위해 imap_unordered 사용 고려 가능하나 일단 통합 결과만 예시
            # 실제 '10분마다 리포트'는 루프 중간에 시간을 체크하여 notify_user 호출
            start_time = time.time()
            batch_results = pool.map(run_backtest_core, work_args)
            results.extend(batch_results)
            print(f"RSI {rsi_w} Done. Time: {time.time()-start_time:.2f}s")
            
        # 여기에 10분 체크 로직 추가 가능 (하지만 현재 구조상 RSI별로 루프가 돎)
        # 더 세분화하려면 combinations를 쪼개서 수행해야 함.

    df = pd.DataFrame(results)
    report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(report_dir, exist_ok=True)
    
    csv_path = os.path.join(report_dir, 'optimization_rsi_results_survivorship_free_cooldown.csv')
    df.to_csv(csv_path, index=False)
    
    top_each = df.sort_values('Ret', ascending=False).groupby('RSI_W').head(1)
    print("\nBest for each RSI Window (With 90d Cooldown):")
    print(top_each.to_markdown())

if __name__ == "__main__":
    run_optimization()
