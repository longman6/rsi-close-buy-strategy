
import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
from datetime import datetime

# Ensure imports work from parent dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rsi_strategy_backtest import get_kosdaq150_tickers

# Simulation Constants
START_DATE = '2010-01-01' # Extended History
INITIAL_CAPITAL = 100000000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

def calculate_indicators(df, rsi_window, sma_window):
    # SMA
    df[f'SMA'] = df['Close'].rolling(window=sma_window).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_window).mean()
    rs = gain / loss
    df[f'RSI'] = 100 - (100 / (1 + rs))
    return df

def run_simulation(strategy_name, params, stock_data, valid_tickers):
    print(f"🔄 Simulating: {strategy_name}...")
    
    rsi_window = params['RSI']
    sma_window = params['SMA']
    buy_threshold = params['Buy']
    sell_threshold = params['Sell']
    max_positions = params['MaxPos']
    max_holding_days = params['Hold']
    
    # Needs re-calc indicators if windows differ?
    # Yes. We will calculate locally or pre-calc.
    # Since windows differ (SMA 50 vs 100), we must calc per strategy.
    
    local_data = {}
    for t, df in stock_data.items():
        local_data[t] = calculate_indicators(df.copy(), rsi_window, sma_window)

    cash = INITIAL_CAPITAL
    positions = {}
    equity_curve = []
    trade_count = 0
    wins = 0
    
    # Generate Master Timeline
    all_dates = sorted(list(set().union(*[df.index for df in local_data.values()])))
    # Filter for start date
    all_dates = [d for d in all_dates if d >= pd.to_datetime(START_DATE)]
    
    for date in all_dates:
        # 1. Sell Logic
        current_positions_value = 0
        tickers_to_remove = []

        for ticker, pos in positions.items():
            df = local_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                
                rsi = df.loc[date, 'RSI']
                days_held = (date - pos['buy_date']).days
                
                if rsi > sell_threshold:
                    tickers_to_remove.append(ticker)
                elif days_held >= max_holding_days:
                    tickers_to_remove.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price

        equity = cash + current_positions_value
        equity_curve.append(equity)

        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            sell_price = local_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
            # Stats
            invested = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            profit = (sell_amt - cost) - invested
            if profit > 0: wins += 1
            trade_count += 1
            
        # 2. Buy Logic
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = local_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA']) or pd.isna(row['RSI']): continue
                
                if row['Close'] > row['SMA'] and row['RSI'] < buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    # Dynamic Equity Model
                    # Recalculate equity
                    curr_equity = cash + sum(p['shares'] * p['last_price'] for p in positions.values())
                    target = curr_equity / max_positions # Equal weight allocation
                    invest = min(target, cash)
                    
                    max_buy_val = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 100000: continue
                    shares = int(max_buy_val / can['price'])
                    if shares > 0:
                         buy_val = shares * can['price']
                         cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                         positions[can['ticker']] = {
                             'shares': shares, 'buy_price': can['price'],
                             'last_price': can['price'], 'buy_date': date
                         }
                         
    final_equity = equity_curve[-1] if equity_curve else INITIAL_CAPITAL
    ret = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    ec = np.array(equity_curve)
    peak = np.maximum.accumulate(ec)
    dd = (ec - peak) / peak
    mdd = dd.min() * 100
    
    win_rate = (wins / trade_count * 100) if trade_count > 0 else 0
    
    return {
        "Name": strategy_name,
        "Return": ret,
        "MDD": mdd,
        "FinalEquity": final_equity,
        "WinRate": win_rate,
        "Trades": trade_count
    }

def main():
    print("🚀 Comparing Strategies...")
    
    # 1. Strategies
    strategies = [
        {
            "Name": "Option E (Stability/WinRate)",
            "RSI": 3, "Buy": 35, "Sell": 75, "SMA": 100, "MaxPos": 7, "Hold": 20
        },
        {
            "Name": "Option H (Aggressive)",
            "RSI": 3, "Buy": 20, "Sell": 80, "SMA": 50, "MaxPos": 3, "Hold": 10
        }
    ]
    
    # 2. Data
    tickers = get_kosdaq150_tickers()
    print("📥 Loading Data (2009~)...")
    # Fetch raw data enough for SMA 100
    raw = yf.download(tickers, start="2009-06-01", progress=False)
    
    stock_data = {}
    valid_tickers = []
    
    # Process Raw Data to Dict
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw.xs('Close', axis=1, level=0)
    else:
        closes = raw['Close'] if 'Close' in raw.columns else raw
        
    for t in tickers:
        if t in closes.columns:
            s = closes[t].dropna()
            if len(s) > 200:
                stock_data[t] = s.to_frame(name='Close')
                valid_tickers.append(t)
                
    print(f"✅ Loaded {len(valid_tickers)} stocks.")
    
    results = []
    for s in strategies:
        res = run_simulation(s['Name'], s, stock_data, valid_tickers)
        results.append(res)
        
    # Table Output
    print(f"\n📊 Strategy Comparison Results ({START_DATE} ~ Now)\n")
    df = pd.DataFrame(results)
    print(df[['Name', 'Return', 'MDD', 'WinRate', 'Trades']].to_markdown(floatfmt=".2f"))
    
    print("\n💡 Key Differences:")
    diff_ret = df.iloc[1]['Return'] - df.iloc[0]['Return']
    diff_mdd = df.iloc[1]['MDD'] - df.iloc[0]['MDD']
    
    print(f"New Strategy Return: {'+' if diff_ret>0 else ''}{diff_ret:.2f}p")
    print(f"New Strategy MDD: {'Improvement' if diff_mdd > 0 else 'Worsened'} ({diff_mdd:.2f}p)")

if __name__ == "__main__":
    main()
