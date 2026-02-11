
import pandas as pd
import numpy as np
import datetime
import duckdb
import os
import shutil
import tempfile
import itertools
from multiprocessing import Pool, cpu_count
from datetime import timedelta

# Configuration
DUCKDB_PATH = "/home/longman6/projects/stock-collector/data/stock.duckdb"
START_DATE = '2016-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 1.0 / MAX_POSITIONS
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# Optimization Ranges (Expanded)
PARAM_GRID = {
    'rsi_window': [3, 4, 5],
    'sma_window': [40, 50, 60, 70, 80, 90, 100, 110,120],
    'buy_threshold': [20, 22, 24, 26, 28, 30, 32, 34],
    'sell_threshold': [66,68,70,72,74,76,78,80],
    'max_holding_days': [10, 20, 30, 40, 50] 
}

# ----------------------------------------------------
# 1. Data Loading (Shared)
# ----------------------------------------------------
def get_db_connection():
    try:
        conn = duckdb.connect(DUCKDB_PATH, read_only=True)
        conn.execute("SELECT 1").fetchone()
        return conn
    except Exception as e:
        print(f"⚠️ Direct DB Connection Failed (Lock?): {e}")
        try:
            temp_dir = tempfile.gettempdir()
            temp_db = os.path.join(temp_dir, f"stock_temp_opt_{os.getpid()}.duckdb")
            if not os.path.exists(temp_db):
                 shutil.copy2(DUCKDB_PATH, temp_db)
            conn = duckdb.connect(temp_db, read_only=True)
            return conn
        except Exception as e2:
            print(f"❌ Temp DB Connection Failed: {e2}")
            return None

def load_universe_and_data():
    conn = get_db_connection()
    if not conn: return None, None

    try:
        # 1. Load Universe History
        print("Loading Universe History...")
        u_query = "SELECT year, symbol FROM index_constituents WHERE index_code = 'KQ150' ORDER BY year"
        u_df = conn.execute(u_query).df()
        u_df['symbol'] = u_df['symbol'].astype(str).str.zfill(6)
        
        # Build Year Map: {2016: ['000250', ...], ...}
        year_map = u_df.groupby('year')['symbol'].apply(list).to_dict()
        all_tickers = u_df['symbol'].unique().tolist()
        
        # 2. Load Daily OHLCV for ALL tickers
        print(f"Loading OHLCV Data for {len(all_tickers)} tickers...")
        # Optimize: Fetch only necessary columns
        symbols_str = ",".join([f"'{t}'" for t in all_tickers])
        d_query = f"""
            SELECT symbol, date, close, open
            FROM ohlcv_daily
            WHERE symbol IN ({symbols_str})
              AND date >= '{START_DATE}'
            ORDER BY symbol, date
        """
        data_df = conn.execute(d_query).df()
        
        # Structure Data: Dictionary of DataFrames used in simulation
        # However, for optimization, we need fast access.
        # Let's pre-calculate indicators? No, indicators depend on window params.
        # So we store raw data dict.
        stock_data = {}
        grouped = data_df.groupby('symbol')
        for symbol, group in grouped:
            df = group.set_index('date').sort_index()
            # Ensure columns are float
            df['Close'] = df['close'].astype(float)
            df['Open'] = df['open'].astype(float)
            stock_data[symbol] = df[['Open', 'Close']]
            
        print(f"✅ Data Loaded: {len(stock_data)} tickers prepared.")
        return stock_data, year_map

    except Exception as e:
        print(f"❌ Data Load Error: {e}")
        return None, None
    finally:
        conn.close()

# ----------------------------------------------------
# 2. Simulation Logic (Worker)
# ----------------------------------------------------
def calculate_indicators(df, rsi_window, sma_window):
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # SMA
    df['SMA'] = df['Close'].rolling(window=sma_window).mean()
    return df

def run_single_backtest(params, stock_data_raw, year_map):
    # Unpack Params
    rsi_w = params['rsi_window']
    sma_w = params['sma_window']
    buy_th = params['buy_threshold']
    sell_th = params['sell_threshold']
    max_hold = params['max_holding_days']
    
    # 1. Prepare Data with Indicators (Only for valid universe?)
    # To speed up, we should only process tickers that are in universe at some point.
    # But indicators need history. 
    # Let's simple Copy & Calc for all (Memory heavy but safe)
    
    # Optimization: Calculate indicators only for active tickers? 
    # stock_data_raw is dict.
    
    stock_data = {}
    for t, df in stock_data_raw.items():
        if len(df) < sma_w: continue
        d = df.copy()
        # Fast indicator calc
        delta = d['Close'].diff()
        # Wilder's Smoothing for RSI is standard but simple rolling used in backtest.py?
        # backtest.py used simple rolling means for gain/loss per FinanceDataReader default?
        # Let's stick to simple rolling to match backtest.py logic:
        # up = delta.clip(lower=0)
        # down = -1 * delta.clip(upper=0)
        # ema_up = up.ewm(com=window-1, adjust=False).mean() ... No, backtest.py used rolling mean?
        # Wilder's Smoothing (Standard) - Matches backtest.py logic strictly
        # avg_gain = gain.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
        # avg_loss = loss.ewm(alpha=1/window, min_periods=window, adjust=False).mean()
        
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        
        avg_gain = up.ewm(alpha=1/rsi_w, min_periods=rsi_w, adjust=False).mean()
        avg_loss = down.ewm(alpha=1/rsi_w, min_periods=rsi_w, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        d['RSI'] = 100 - (100 / (1 + rs))
        d['SMA'] = d['Close'].rolling(window=sma_w).mean()
        stock_data[t] = d
    
    # 2. Simulation
    cash = INITIAL_CAPITAL
    positions = {} # {ticker: {shares, buy_price, buy_date, held_bars}}
    trades = []
    
    # All dates union
    all_dates = sorted(list(set().union(*[d.index for d in stock_data.values()])))
    date_to_year = {d: d.year for d in all_dates}
    
    alloc_per = 1.0 / MAX_POSITIONS

    for date in all_dates:
        # Dynamic Universe
        yr = date_to_year[date]
        if yr not in year_map:
             # Fallback
             avail = sorted(year_map.keys())
             if not avail: continue
             yr = avail[-1] if yr > avail[-1] else avail[0]
        
        daily_universe = year_map.get(yr, [])
        universe_set = set(daily_universe) # optimize lookup
        
        # A. Sell
        if positions:
            sell_list = []
            for t, pos in positions.items():
                if t not in stock_data or date not in stock_data[t].index:
                    continue
                
                row = stock_data[t].loc[date]
                # Conditions
                is_take_profit = (row['RSI'] > sell_th) if not pd.isna(row['RSI']) else False
                is_time_stop = (pos['held_bars'] >= max_hold)
                
                if is_take_profit or is_time_stop:
                    # Sell at NEXT DAY OPEN in backtest.py? 
                    # Wait, backtest.py logic:
                    # 1. Check sell condition based on TODAY close (RSI, etc)
                    # 2. Exec Sell:
                    #    - If logic said "Sell Tomorrow Open": price = next_open
                    #    - If logic said "Sell Today Close": price = close
                    # Checking backtest.py again...
                    # It iterates dates.
                    #   row = df.loc[date]
                    #   if row['RSI'] > sell_threshold:
                    #       sell_price = row['Close'] (Legacy) OR row['NextOpen']?
                    # The user reverted to "Current Day Close" earlier.
                    # So we use TODAY CLOSE for Simplicity and matching current logic.
                    
                    sell_price = row['Close'] # User reverted to Close-sell
                    
                    # Fee
                    gross = pos['shares'] * sell_price
                    fee = gross * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
                    net = gross - fee
                    ret = (net - (pos['shares'] * pos['buy_price'])) / (pos['shares'] * pos['buy_price']) * 100
                    
                    cash += net
                    sell_list.append(t)
                    trades.append(ret) # Store return %
            
            for t in sell_list:
                del positions[t]

        # B. Buy
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            candidates = []
            # Filter universe intersecting with data
            # Optimization: Pre-filter?
            # Creating candidate list
            for t in daily_universe:
                if t in positions: continue
                if t not in stock_data: continue
                df_t = stock_data[t]
                if date not in df_t.index: continue
                
                row = df_t.loc[date]
                if pd.isna(row['RSI']) or pd.isna(row['SMA']): continue
                
                # Signal: Close > SMA and RSI < Threshold
                if row['Close'] > row['SMA'] and row['RSI'] <= buy_th:
                    candidates.append((t, row['RSI'], row['Close']))
            
            # Sort by RSI asc
            candidates.sort(key=lambda x: x[1])
            
            for t, rsi, price in candidates[:open_slots]:
                # Position Sizing
                # Approx Equity = Cash + Sum(Shares * CurrentPrice)
                curr_val = 0
                for pt, pdata in positions.items():
                    # Get current price
                    if pt in stock_data and date in stock_data[pt].index:
                        p_price = stock_data[pt].loc[date]['Close']
                        # Update last_price for accurate equity calculation in next steps
                        pdata['last_price'] = p_price
                        curr_val += pdata['shares'] * p_price
                    else:
                        # Fallback to last known or buy price
                        price_to_use = pdata.get('last_price', pdata['buy_price'])
                        curr_val += pdata['shares'] * price_to_use
                
                total_eq = cash + curr_val
                target = total_eq * alloc_per
                invest = min(target, cash)
                
                real_buy = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                if real_buy < 10000: continue
                
                shares = int(real_buy / price)
                if shares > 0:
                    cost = shares * price * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    cash -= cost
                    positions[t] = {
                        'shares': shares,
                        'buy_price': price,
                        'last_price': price, # Initialize last_price
                        'buy_date': date,
                        'held_bars': 0
                    }
        
        # C. Update Hold Days
        for t in positions:
            positions[t]['held_bars'] += 1

    # End Simulation
    # Calculate Metrics
    final_eq = cash
    for t, p in positions.items():
        # Liquidate at last available price
        if t in stock_data:
            last_p = stock_data[t].iloc[-1]['Close']
            final_eq += p['shares'] * last_p
        else:
            final_eq += p['shares'] * p['buy_price'] # Fallback
            
    total_ret = (final_eq - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    win_rate = (sum(1 for r in trades if r > 0) / len(trades) * 100) if trades else 0
    
    # MDD? Calculating MDD requires daily equity curve. Expense.
    # Return basic metrics first.
    return {
        'params': params,
        'return': total_ret,
        'win_rate': win_rate,
        'trades': len(trades)
    }

# ----------------------------------------------------
# 3. Multiprocessing Wrapper
# ----------------------------------------------------
# Global stock data for workers? 
# Multiprocessing copies data. Large data copy is slow.
# Use 'initializer' to share data? Or just let copy happen (simple).
# Given 380 tickers, data size isn't Huge (maybe 100MB). RAM should hold.

def worker_task(args):
    params, data, universe = args
    return run_single_backtest(params, data, universe)

def run_optimization():
    # 1. Load Data
    stock_data, year_map = load_universe_and_data()
    if not stock_data:
        print("Data load failed.")
        return
        
    # 2. Generate Params
    keys, values = zip(*PARAM_GRID.items())
    param_combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"🚀 Starting Optimization for {len(param_combinations)} combinations...")
    print(f"CPU Cores: {cpu_count()}")
    
    tasks = [(p, stock_data, year_map) for p in param_combinations]
    
    # Run Pool
    # Note: Passed big data to each process. 
    # If too slow/OOM, consider using 'initializer' to load data in each worker 
    # or shared memory.
    with Pool(processes=20) as pool:
        results = pool.map(worker_task, tasks)
        
    # 3. Analyze
    res_df = pd.DataFrame(results)
    res_df['params_str'] = res_df['params'].apply(lambda x: str(x))
    
    # Sort by Return
    res_df = res_df.sort_values('return', ascending=False)
    
    print("\n🏆 Top 5 Results:")
    print(res_df.head(5)[['params', 'return', 'win_rate', 'trades']].to_markdown())
    
    # Save
    os.makedirs('reports', exist_ok=True)
    res_df.to_csv('reports/optimization_survivorship_free_result.csv', index=False)
    print("\n✅ Optimization Complete. Saved to reports/optimization_survivorship_free_result.csv")

if __name__ == '__main__':
    run_optimization()
