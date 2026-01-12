
import pandas as pd
import numpy as np
import os
import itertools
import sys
from datetime import datetime
import time
from multiprocessing import Pool, cpu_count, freeze_support

# Ensure imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rsi_strategy_backtest import get_kosdaq150_tickers

# Constants
START_DATE = '2010-01-01'
INITIAL_CAPITAL = 100000000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001
MAX_POSITIONS = 5

# Global variable for worker processes
worker_stock_data = {}
worker_valid_tickers = []

def init_worker(stock_data, valid_tickers):
    global worker_stock_data, worker_valid_tickers
    worker_stock_data = stock_data
    worker_valid_tickers = valid_tickers

def prepare_data_all_needed(tickers, start_date):
    """Pre-fetch data to cover the widest possible windows. Includes Indicator Pre-calc."""
    from rsi_strategy_backtest import prepare_data
    
    print("📥 Loading raw stock data...")
    # Fetch with max windows
    raw_data, valid = prepare_data(tickers, start_date, 14, 200)
    
    print("🔄 Pre-calculating indicators...")
    rsi_periods = [3, 5, 7]
    sma_periods = [20, 30, 50, 60, 90, 100, 120, 150, 200]
    
    for ticker, df in raw_data.items():
        # Pre-calc RSIs
        for r in rsi_periods:
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=r).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=r).mean()
            rs = gain / loss
            df[f'RSI_{r}'] = 100 - (100 / (1 + rs))
        
        # Pre-calc SMAs
        for s in sma_periods:
            df[f'SMA_{s}'] = df['Close'].rolling(window=s).mean()
            
    return raw_data, valid

def run_simulation_worker(rsi_period, sma_period, buy_threshold, sell_threshold, max_holding_days, max_positions):
    """Worker function that uses global data (copy-on-write friendly in fork)"""
    stock_data = worker_stock_data
    valid_tickers = worker_valid_tickers
    
    allocation_per_stock = 1.0 / max_positions
    rsi_col = f'RSI_{rsi_period}'
    sma_col = f'SMA_{sma_period}'
    
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0
    
    for date in all_dates:
        # 1. Sell Logic
        current_positions_value = 0
        tickers_to_remove = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                
                rsi = df.loc[date, rsi_col]
                days_held = (date - pos['buy_date']).days
                
                if rsi > sell_threshold:
                    tickers_to_remove.append(ticker)
                elif days_held >= max_holding_days:
                    tickers_to_remove.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append(total_equity)

        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            # Stats
            invested = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            profit = (sell_amt - cost) - invested
            if profit > 0: wins += 1
            trades_count += 1
            
        # 2. Buy Logic
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row[sma_col]) or pd.isna(row[rsi_col]): continue
                
                if row['Close'] > row[sma_col] and row[rsi_col] < buy_threshold:
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
                             'last_price': can['price'], 'buy_date': date
                         }

    # Final Stats
    final_equity = history[-1] if history else INITIAL_CAPITAL
    ret = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    # MDD
    equity_curve = np.array(history)
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    mdd = drawdown.min() * 100
    
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
    
    return {
        'RSI': rsi_period, 'SMA': sma_period, 'Buy': buy_threshold, 
        'Sell': sell_threshold, 'Hold': max_holding_days, 'MaxPos': max_positions,
        'Return': ret, 'MDD': mdd, 'WinRate': win_rate, 'Trades': trades_count
    }

def run_dense_optimization():
    print("🚀 Starting PARALLEL Dense Optimization for RSI 3, 5, 7...")
    tickers = get_kosdaq150_tickers()
    stock_data, valid_tickers = prepare_data_all_needed(tickers, START_DATE)
    

    # --- GRID DEFINITION ---
    # Total combinations = 3 * 9 * 9 * 6 * 8 * 4 = 46,656 approx.
    
    rsi_list = [3, 5, 7]
    sma_list = [20, 30, 50, 60, 90, 100, 120, 150, 200]
    buy_list = [5, 10, 15, 20, 25, 30, 35, 40, 45]
    sell_list = [55, 60, 65, 70, 75, 80]
    hold_list = [5, 10, 15, 20, 25, 30, 40, 50]
    pos_list = [3, 5, 10, 20]  # New: Optimization for Max Positions

    all_combs = list(itertools.product(rsi_list, sma_list, buy_list, sell_list, hold_list, pos_list))
    total_tests = len(all_combs)
    cpu_n = min(16, cpu_count()) # Limit to max 16 CPUs
    print(f"🧪 Total Combinations: {total_tests} | CPUs: {cpu_n}")
    
    start_time = time.time()
    
    # Run Parallel
    with Pool(processes=cpu_n, initializer=init_worker, initargs=(stock_data, valid_tickers)) as pool:
        # Use starmap to pass multiple arguments
        results = pool.starmap(run_simulation_worker, all_combs)
        
    elapsed = time.time() - start_time
    print(f"✅ Optimization Complete in {elapsed/60:.2f} mins!")

    # Save Results
    df = pd.DataFrame(results)

    
    # Filter
    df = df[df['Trades'] > 10]
    
    output_path = "reports/rsi_dense_opt_with_positions.csv"
    df.to_csv(output_path, index=False)
    print(f"Checking top 5 results preview: \n{df.sort_values(by='Return', ascending=False).head().to_markdown(index=False)}")

    # Generate Summary Report
    with open("reports/rsi_dense_report.md", "w") as f:
        f.write("# Dense Optimization Results (RSI 3, 5, 7)\n")
        f.write(f"Generated: {datetime.now()} | Time Taken: {elapsed/60:.1f} min\n\n")
        
        for rsi in rsi_list:
            f.write(f"## Top 10 Configurations for RSI {rsi}\n")
            sub_df = df[df['RSI'] == rsi].sort_values(by='Return', ascending=False).head(10)
            f.write(sub_df.to_markdown(index=False, floatfmt=".2f"))
            f.write("\n\n")
            
            f.write(f"### Best Stable Strategy (MDD > -40%) for RSI {rsi}\n")
            stable_df = df[(df['RSI'] == rsi) & (df['MDD'] > -40)].sort_values(by='Return', ascending=False).head(5)
            if not stable_df.empty:
                f.write(stable_df.to_markdown(index=False, floatfmt=".2f"))
            else:
                f.write("No strategy met stability criteria.")
            f.write("\n\n")

if __name__ == "__main__":
    freeze_support()
    run_dense_optimization()
