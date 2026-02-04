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

def init_worker(u_map_data, all_dates_data, stock_data_in):
    global universe_map, all_dates, stock_data_ref
    universe_map = u_map_data
    all_dates = all_dates_data
    stock_data_ref = stock_data_in

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
    # Wilder's Smoothing
    avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
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
    query = f"SELECT symbol, date, open, close FROM ohlcv_daily WHERE symbol IN ({symbols_str}) AND date >= '{fetch_start}' ORDER BY symbol, date"
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
def run_backtest_core(args):
    rsi_window, sma_window, buy_threshold, sell_threshold, max_hold, max_pos = args
    
    # Use global data
    # stock_data_ref is dict of dicts: {symbol: {date: row_dict}}
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0
    lockout_until = {}

    pending_buys = []
    pending_sells = []
    
    current_year = 0
    relevant_data = {}
    sma_key = f'SMA_{sma_window}'
    
    for current_date in all_dates:
        year = current_date.year
        if year != current_year:
            current_year = year
            symbols = universe_map.get(year, [])
            # Filter relevant data for this year's symbols AND currently held positions
            held_symbols = list(positions.keys())
            target_symbols = set(symbols + held_symbols)
            relevant_data = {s: stock_data_ref[s] for s in target_symbols if s in stock_data_ref}
        
        # 1. Sell Execution (Next Open)
        for s in pending_sells:
            if s not in positions: continue
            if s not in relevant_data or current_date not in relevant_data[s]: continue
            
            open_price = relevant_data[s][current_date]['open']
            if pd.isna(open_price) or open_price == 0: continue
            
            pos = positions.pop(s)
            sell_val = pos['shares'] * open_price
            cost = sell_val * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_val - cost)
            
            if (sell_val - cost) > (pos['shares'] * pos['buy_price'] * (1+TX_FEE_RATE+SLIPPAGE_RATE)):
                wins += 1
            else:
                lockout_until[s] = current_date + timedelta(days=90)
            trades_count += 1
        pending_sells = []
        
        # Buy Execution
        open_slots = max_pos - len(positions)
        for cand in pending_buys[:open_slots]:
            s = cand['s']
            if s in positions: continue
            if s not in relevant_data or current_date not in relevant_data[s]: continue
            
            open_price = relevant_data[s][current_date]['open']
            if pd.isna(open_price) or open_price == 0: continue
            
            target = (cash + sum(p['shares']*p['last_price'] for p in positions.values())) / max_pos
            buy_amt = min(target, cash) / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            if open_price > 0:
                shares = int(buy_amt / open_price)
            else:
                shares = 0
            if shares > 0:
                cost = shares * open_price * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                cash -= cost
                positions[s] = {'shares': shares, 'buy_price': open_price, 'last_price': open_price, 'held': 0}
        pending_buys = []
        
        # 2. Update Positions (Close)
        curr_positions_val = 0
        for s, pos in positions.items():
            if s not in relevant_data or current_date not in relevant_data[s]:
                curr_positions_val += pos['shares'] * pos['last_price']
                continue
            
            row = relevant_data[s][current_date]
            close = row['close']
            pos['last_price'] = close
            pos['held'] += 1
            curr_positions_val += pos['shares'] * close
        
        total_equity = cash + curr_positions_val
        history.append(total_equity)
        
        # 3. Generate Signals (Close)
        # Sell Signal
        for s, pos in positions.items():
            if s not in relevant_data or current_date not in relevant_data[s]: continue
            row = relevant_data[s][current_date]
            rsi = row[f'RSI_{rsi_window}']
            if pd.isna(rsi): continue
            
            if rsi >= sell_threshold or pos['held'] >= max_hold:
                pending_sells.append(s)
        
        # Buy Signal
        open_slots_next = max_pos - len(positions) + len(pending_sells)
        if open_slots_next > 0:
            candidates = []
            for s, d_map in relevant_data.items():
                if s in positions or current_date not in d_map: continue
                if s in lockout_until:
                    if current_date <= lockout_until[s]: continue
                    else: del lockout_until[s]
                
                row = d_map[current_date]
                sma_val = row.get(sma_key, np.nan)
                if pd.isna(sma_val) or pd.isna(row[f'RSI_{rsi_window}']): continue
                
                if row[f'RSI_{rsi_window}'] <= buy_threshold and row['close'] > sma_val:
                    candidates.append({'s': s, 'rsi': row[f'RSI_{rsi_window}']})
            
            candidates.sort(key=lambda x: x['rsi'])
            pending_buys = candidates[:open_slots_next]

    final_ret = (history[-1] / INITIAL_CAPITAL - 1) * 100 if history else 0
    mdd = ((pd.Series(history) - pd.Series(history).cummax()) / pd.Series(history).cummax()).min() * 100 if history else 0
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
    # Fetch base data with RSI calculated
    stock_data_base = fetch_all_data(conn, u_map, rsi_windows)
    
    # 데이터 로드 완료 후 DB 연결 즉시 해제 (다른 프로세스가 DB에 접근할 수 있도록)
    conn.close()
    
    sma_grids = [30, 50, 70, 90, 110, 130, 150]
    buy_grids = [20, 22, 24, 26, 28, 30, 32]
    sell_grids = [70, 72, 74, 76, 78, 80]
    hold_grids = [10, 15, 20, 25, 30, 40]
    pos_grids = [3, 5, 7, 10]
    
    results = []
    total_start = time.time()
    
    for rsi_w in rsi_windows:
        print(f"\n[Optimizing RSI {rsi_w}] Preparing data...")
        
        # Prepare data: Calculate ALL SMAs and convert to optimized dict structure
        # Use a localized dict for this RSI window to save memory
        # stock_data_base[rsi_w] is {symbol: DF}
        
        # Pre-calculate SMAs
        optimized_data = {}
        for s, df in stock_data_base[rsi_w].items():
            df_copy = df.copy()
            for sma_w in sma_grids:
                df_copy[f'SMA_{sma_w}'] = df_copy['close'].rolling(window=sma_w).mean()
            optimized_data[s] = df_copy.to_dict('index')
            
        print(f"[Optimizing RSI {rsi_w}] Data ready. Starting pool...")
        combinations = list(itertools.product(sma_grids, buy_grids, sell_grids, hold_grids, pos_grids))
        # work_args no longer includes stock_data
        work_args = [(rsi_w, c[0], c[1], c[2], c[3], c[4]) for c in combinations]
        
        with Pool(processes=20, initializer=init_worker, initargs=(u_map, dates, optimized_data)) as pool:
            start_time = time.time()
            batch_results = pool.map(run_backtest_core, work_args)
        
        elapsed = time.time() - start_time
        print(f"[Optimizing RSI {rsi_w}] Done in {elapsed:.1f}s. Results: {len(batch_results)}")
        
        results.extend(batch_results)
        
        temp_df = pd.DataFrame(results)
        report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
        os.makedirs(report_dir, exist_ok=True)
        csv_path = os.path.join(report_dir, 'optimization_rsi_results_survivorship_free_cooldown.csv')
        temp_df.to_csv(csv_path, index=False)
        print(f"Intermediate results saved to {csv_path}")

    # Final Save
    df = pd.DataFrame(results)
    report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(report_dir, exist_ok=True)
    csv_path = os.path.join(report_dir, 'optimization_rsi_results_survivorship_free_cooldown.csv')
    df.to_csv(csv_path, index=False)
    
    top_each = df.sort_values('Ret', ascending=False).groupby('RSI_W').head(1)
    print("\nBest for each RSI Window (With 90d Cooldown, Next Day Open):")
    print(top_each.to_markdown())

if __name__ == "__main__":
    run_optimization()
