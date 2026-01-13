
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import os
import itertools
from datetime import datetime
import time
from multiprocessing import Pool, cpu_count, freeze_support
import sys

# Append path to import backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rsi_strategy_backtest import get_kosdaq150_tickers, prepare_data

# Constants
START_DATE = '2010-01-01'
INITIAL_CAPITAL = 100000000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# Global variable for worker processes
worker_stock_data = {}
worker_valid_tickers = []

def init_worker(stock_data, valid_tickers):
    global worker_stock_data, worker_valid_tickers
    worker_stock_data = stock_data
    worker_valid_tickers = valid_tickers

def prepare_data_rsi3(tickers, start_date):
    """Load data dedicated for RSI 3 optimization"""
    # Load with RSI 3 pre-calculated from common module if possible
    # We load with enough window for SMA 200
    return prepare_data(tickers, start_date, 3, 200)

def run_simulation_worker(sma_period, buy_threshold, sell_threshold, max_holding_days, max_positions):
    """Worker function for parallel processing"""
    stock_data = worker_stock_data
    valid_tickers = worker_valid_tickers
    
    rsi_col = 'RSI' # Prepared by prepare_data with window=3
    # SMA needs to be calculated dynamically or we assume we only rely on Pre-calc?
    # prepare_data calculates ONE SMA based on sma_window passed.
    # But here we are Optimizing SMA period. So we MUST recalculate SMA inside worker 
    # OR pre-calculate all variants in main and pass them.
    # Calculating inside worker is safer for memory but slower. 
    # optimize_all_dense.py pre-calculates SMA_20, SMA_50 etc. Let's start with dynamic calc for simplicity of migration.
    
    allocation_per_stock = 1.0 / max_positions
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0

    # Optimization: Pre-calculate SMA for this period for all stocks once
    # This is better done outside the loop
    # NOTE: Since stock_data is shared via COW (Copy On Write), modifying it (adding col) might copy it.
    # To avoid huge memory usage, we can calculate SMA on the fly or just use a local dict.
    
    # Let's use a local dictionary for dataframes that have the specific SMA
    local_data = {}
    for ticker, df in stock_data.items():
        # Copy strictly needed
        d = df[['Close', rsi_col]].copy()
        d['SMA_Dynamic'] = d['Close'].rolling(window=sma_period).mean()
        local_data[ticker] = d

    for date in all_dates:
        # 1. Sell Logic
        current_positions_value = 0
        
        # Increment held_bars (Trading Days) - Trading Days Logic
        for ticker, pos in positions.items():
            pos['held_bars'] += 1
            
        tickers_to_remove = []

        for ticker, pos in positions.items():
            df = local_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, rsi_col]
                
                # Sell Conditions
                if rsi > sell_threshold: 
                    tickers_to_remove.append(ticker)
                elif pos['held_bars'] >= max_holding_days: 
                    tickers_to_remove.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append(total_equity) 

        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            sell_price = local_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            # Win Stats
            buy_cost = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            if (sell_amt - cost) > buy_cost: wins += 1
            trades_count += 1
            
        # 2. Buy Logic
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = local_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA_Dynamic']) or pd.isna(row[rsi_col]): continue # Skip NaN

                if row['Close'] > row['SMA_Dynamic'] and row[rsi_col] < buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row[rsi_col], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    target = total_equity * allocation_per_stock
                    invest = min(target, cash)
                    max_buy_val = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 10000: continue
                    shares = int(max_buy_val / can['price'])
                    if shares > 0:
                         buy_val = shares * can['price']
                         cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                         positions[can['ticker']] = {
                             'shares': shares, 'buy_price': can['price'],
                             'last_price': can['price'], 'buy_date': date,
                             'held_bars': 0
                         }

    # Results
    final_equity = history[-1] if history else INITIAL_CAPITAL
    ret = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    equity_curve = np.array(history)
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    mdd = drawdown.min() * 100
    
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
    return {
        'SMA': sma_period, 'Buy': buy_threshold, 'Sell': sell_threshold, 'Hold': max_holding_days, 'MaxPos': max_positions,
        'Return': ret, 'MDD': mdd, 'WinRate': win_rate, 'Trades': trades_count
    }

def run_optimization():
    print("🚀 [RSI 3 Optimized] Loading Data (Pool=10)...")
    tickers = get_kosdaq150_tickers()
    stock_data, valid_tickers = prepare_data_rsi3(tickers, START_DATE)
    
    # Parameter Grid (RSI 3 Fixed)
    # Trying variety of SMAs and Buy/Sell thresholds
    # Adjusted Parameters for reasonable runtime (~2600 combinations)
    sma_periods = [30, 50, 60, 100, 120, 200]
    buy_thresholds = [5, 10, 15, 20, 25, 30]
    sell_thresholds = [60, 70, 80]
    max_holdings = [5, 10, 15, 20, 30, 50]
    max_positions_list = [3, 5, 10, 20] # Variable Max Positions
    
    combinations = list(itertools.product(sma_periods, buy_thresholds, sell_thresholds, max_holdings, max_positions_list))
    # worker args: (sma, buy, sell, hold, max_positions)
    work_args = [(c[0], c[1], c[2], c[3], c[4]) for c in combinations]
    
    total_tests = len(combinations)
    cpu_n = 12 # Requested by User
    
    print(f"🧪 Total Combinations: {total_tests} | Cores: {cpu_n}")
    
    start_time = time.time()
    
    with Pool(processes=cpu_n, initializer=init_worker, initargs=(stock_data, valid_tickers)) as pool:
        results = pool.starmap(run_simulation_worker, work_args)
        
    elapsed = time.time() - start_time
    print(f"✅ Optimization Complete in {elapsed/60:.2f} mins!")

    # Save Results
    df = pd.DataFrame(results)
    df = df.sort_values(by='Return', ascending=False)
    
    # Filter for meaningful trades
    df_filtered = df[df['Trades'] > 10]

    output_csv = "reports/rsi3_extended_opt_results.csv"
    df.to_csv(output_csv, index=False)
    
    top_10 = df_filtered.head(10)
    print("\n🏆 Top 10 Configurations (Trades > 10):")
    print(top_10.to_markdown(index=False, floatfmt=".2f"))
    
    # Report MD
    md_report = f"""
# RSI 3 Extended Optimization Results
Generated: {datetime.now()} | Cores: {cpu_n}

## Top 10 Performers
{top_10.to_markdown(index=False, floatfmt=".2f")}

## Best Stable Strategy (MDD > -40%)
"""
    stable_df = df_filtered[df_filtered['MDD'] > -40].sort_values(by='Return', ascending=False)
    if not stable_df.empty:
        md_report += stable_df.head(5).to_markdown(index=False, floatfmt=".2f")
    else:
        md_report += "No stable strategy found."

    with open("reports/rsi3_parallel_report.md", "w") as f:
        f.write(md_report)

if __name__ == "__main__":
    freeze_support()
    run_optimization()
