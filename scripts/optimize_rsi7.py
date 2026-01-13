
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np
import os
import itertools
from datetime import datetime, timedelta

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

def prepare_data_batch(tickers, start_date):
    """Reuse logic but optimized for batch processing"""
    # RSI window 7, max SMA 200
    # Just reuse existing logic for simplicity, though slightly inefficient (re-downloads)
    # Ideally should cache. For this script, let's assume valid data fetching.
    from rsi_strategy_backtest import prepare_data
    # We need max SMA window to determine fetch date. Let's use 200 as max possible.
    return prepare_data(tickers, start_date, 7, 200) 

def run_simulation_optimized(stock_data, valid_tickers, 
                             max_holding_days, buy_threshold, sell_threshold, sma_window, max_positions, loss_lockout_days=90):
    
    allocation_per_stock = 1.0 / max_positions
    
    # Pre-calculate indicators for valid tickers based on current SMA window
    # Note: stock_data already has SMA and RSI based on initial call args (RSI 5, SMA 200).
    # IF we vary RSI or SMA, we must re-calculate columns dynamically.
    
    # Since we are varying SMA, we need to recalc SMA column.
    # RSI is fixed at 5, so that's fine.
    
    for ticker, df in stock_data.items():
        daily_close = df['Close']
        df['SMA_Dynamic'] = daily_close.rolling(window=sma_window).mean()
        # Ensure RSI 5 is accurate (it should be from prepare_data call)
        # We assume prepare_data was called with rsi_window=5.

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
            df = stock_data[ticker]
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
            sell_price = stock_data[ticker].loc[date, 'Close']
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
                
                df = stock_data[ticker]
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
    return ret, mdd, win_rate, trades_count

def run_optimization():
    print("🚀 Loading Data...")
    tickers = get_kosdaq150_tickers()
    # Pre-load data with max requirements (RSI 7, SMA 200)
    stock_data, valid_tickers = prepare_data_batch(tickers, START_DATE)
    
    # Grid Search Space (Dense) - Adjusted for RSI 7
    # RSI 7 is smoother, so buy threshold might need to be higher (25~45)
    sma_periods = [20, 50, 60, 100, 120, 200]
    buy_thresholds = [20, 25, 30, 35, 40, 45] # Shifted higher for RSI 7
    sell_thresholds = [60, 65, 70, 75, 80]
    max_holdings = [5, 10, 20, 40]
    # Fixed
    max_positions = 5
    
    combinations = list(itertools.product(sma_periods, buy_thresholds, sell_thresholds, max_holdings))
    total_tests = len(combinations)
    
    print(f"\n🔍 Starting Dense Optimization for RSI 7... ({total_tests} combinations)")
    
    results = []
    for i, (sma, buy, sell, hold) in enumerate(combinations):
        if i % 50 == 0: print(f"Processing... {i}/{total_tests}")
        
        ret, mdd, win, count = run_simulation_optimized(
            stock_data, valid_tickers, hold, buy, sell, sma, max_positions
        )
        
        results.append({
            'SMA': sma, 'Buy': buy, 'Sell': sell, 'Hold': hold,
            'Return': ret, 'MDD': mdd, 'Win': win, 'Trades': count
        })
        
    # To DataFrame
    df = pd.DataFrame(results)
    df = df.sort_values(by='Return', ascending=False)
    
    top_10 = df.head(10)
    print("\n🏆 Top 10 Configurations (RSI 7):")
    print(top_10.to_markdown(index=False, floatfmt=".2f"))
    
    # Save to CSV
    csv_file = "reports/rsi7_optimization_results.csv" # Save directly to reports
    df.to_csv(csv_file, index=False)
    print(f"\n✅ All results saved to {csv_file}")
    
    # Generate MD Report
    md_report = f"""
# RSI 7 Strategy Optimization Results
Generated: {datetime.now()}

## Top 10 Performers
{top_10.to_markdown(index=False, floatfmt=".2f")}

## Best Stable Strategy (MDD > -40% & Highest Return)
"""
    stable_df = df[df['MDD'] > -40].sort_values(by='Return', ascending=False)
    if not stable_df.empty:
        md_report += stable_df.head(5).to_markdown(index=False, floatfmt=".2f")
    else:
        md_report += "No strategy met MDD > -40% criteria."
        
    with open("reports/rsi7_optimization_report.md", "w") as f: # Save directly to reports
        f.write(md_report)

if __name__ == "__main__":
    run_optimization()
