
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
import os
import itertools
from datetime import datetime, timedelta
import time
from multiprocessing import Pool, cpu_count, freeze_support

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import functions from original backtest to reuse
from rsi_strategy_backtest import get_kosdaq150_tickers, calculate_rsi, get_kosdaq150_ticker_map

# Reuse global constants but allow overrides
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

def prepare_data_batch(tickers, start_date):
    """Reuse logic but optimized for batch processing"""
    # RSI window 7, max SMA 200
    from rsi_strategy_backtest import prepare_data
    return prepare_data(tickers, start_date, 7, 200) 

def run_simulation_worker(sma_window, buy_threshold, sell_threshold, max_holding_days, max_positions, loss_lockout_days=90):
    stock_data = worker_stock_data
    valid_tickers = worker_valid_tickers
    
    allocation_per_stock = 1.0 / max_positions
    
    # Local Data Optimization
    local_data = {}
    for ticker, df in stock_data.items():
        d = df[['Close', 'RSI']].copy()
        d['SMA_Dynamic'] = d['Close'].rolling(window=sma_window).mean()
        local_data[ticker] = d
        
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades_count = 0
    wins = 0
    
    # Loss Lockout Dictionary: {ticker: lockout_end_date}
    lockout_until = {}
    
    for date in all_dates:
        # 1. Sell Logic
        current_positions_value = 0
        
        # Increment held_bars (Trading Days)
        for ticker, pos in positions.items():
            pos['held_bars'] += 1
            
        tickers_to_remove = []

        for ticker, pos in positions.items():
            df = local_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']
                
                # Sell Conditions (RSI >= sell_threshold)
                if rsi >= sell_threshold: # Signal Sell
                    tickers_to_remove.append(ticker)
                elif pos['held_bars'] >= max_holding_days: # Force Sell
                    tickers_to_remove.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append(total_equity) # Just store equity value for speed

        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            # Sell execution logic simplified
            sell_price = local_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            # Win rate calc
            buy_cost = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_profit = (sell_amt - cost) - buy_cost
            if net_profit > 0: wins += 1
            trades_count += 1
            
            # Loss Lockout Logic (단순 가격 기준)
            price_return = sell_price - pos['buy_price']
            if price_return < 0 and loss_lockout_days > 0:
                from datetime import timedelta
                lockout_end = date + timedelta(days=loss_lockout_days)
                lockout_until[ticker] = lockout_end

        # 매도 후 total_equity 재계산
        current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
        total_equity = cash + current_positions_value
            
        # 2. Buy Logic
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                
                # Check Lockout
                if ticker in lockout_until:
                    if date <= lockout_until[ticker]:
                        continue
                    else:
                        del lockout_until[ticker]
                
                df = local_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA_Dynamic']): continue
                
                # 매수 조건 (RSI <= buy_threshold)
                if row['Close'] > row['SMA_Dynamic'] and row['RSI'] <= buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    # 매 매수 전 total_equity 재계산
                    current_positions_value = sum(p['shares'] * p['last_price'] for p in positions.values())
                    total_equity = cash + current_positions_value
                    
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
    
    # MDD Calc
    equity_curve = np.array(history)
    peak = np.maximum.accumulate(equity_curve)
    drawdown = (equity_curve - peak) / peak
    mdd = drawdown.min() * 100
    
    win_rate = (wins / trades_count * 100) if trades_count > 0 else 0
    return {
        'SMA': sma_window, 'Buy': buy_threshold, 'Sell': sell_threshold, 'Hold': max_holding_days, 'MaxPos': max_positions,
        'Return': ret, 'MDD': mdd, 'WinRate': win_rate, 'Trades': trades_count
    }

def run_optimization():
    print("🚀 [RSI 7 Optimized] Loading Data (Pool=10)...")
    tickers = get_kosdaq150_tickers()
    # Pre-load data with max requirements (RSI 7, SMA 200)
    stock_data, valid_tickers = prepare_data_batch(tickers, START_DATE)
    
    # Grid Search Space (Dense) - Adjusted for RSI 7
    # RSI 7 is smoother, so buy threshold might need to be higher (25~45)
    # Denser Parameter Grid (Within User Constraints)
    sma_periods = list(range(30, 151, 10)) # 30, 40, ... 150
    buy_thresholds = list(range(20, 34, 1)) # 20, 21, ... 33
    sell_thresholds = list(range(60, 81, 2)) # 60, 62, ... 80
    max_holdings = list(range(10, 51, 5)) # 10, 15, ... 50
    max_positions_list = [3, 5, 7, 10, 12, 15, 17, 20]
    
    combinations = list(itertools.product(sma_periods, buy_thresholds, sell_thresholds, max_holdings, max_positions_list))
    total_tests = len(combinations)
    cpu_n = 12 # Requested by User
    
    print(f"🧪 Total Combinations (RSI 7): {total_tests} | Cores: {cpu_n}")
    
    start_time = time.time()
    
    # worker args: (sma, buy, sell, hold, max_positions)
    work_args = [(c[0], c[1], c[2], c[3], c[4]) for c in combinations]
    
    with Pool(processes=cpu_n, initializer=init_worker, initargs=(stock_data, valid_tickers)) as pool:
        results = pool.starmap(run_simulation_worker, work_args)
        
    elapsed = time.time() - start_time
    print(f"✅ Optimization Complete in {elapsed/60:.2f} mins!")
    
    # Save Results
    df = pd.DataFrame(results)
    df = df.sort_values(by='Return', ascending=False)
    
    # Filter for meaningful trades
    df_filtered = df[df['Trades'] > 10]
    
    output_csv = "reports/rsi7_extended_opt_results.csv"
    df.to_csv(output_csv, index=False)
    
    top_10 = df_filtered.head(10)
    print("\n🏆 Top 10 Configurations (Trades > 10):")
    print(top_10.to_markdown(index=False, floatfmt=".2f"))
    
    # Report MD
    md_report = f"""
# RSI 7 Extended Optimization Results
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
        
    with open("reports/rsi7_parallel_report.md", "w") as f: # Save directly to reports
        f.write(md_report)

if __name__ == "__main__":
    freeze_support()
    run_optimization()
