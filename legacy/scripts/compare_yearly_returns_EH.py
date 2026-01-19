
import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
from datetime import datetime

# Ensure imports work from parent dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rsi_strategy_backtest import get_kosdaq150_tickers

# Constants
RESET_CAPITAL = 50000000 # 50 Million KRW
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

def run_yearly_simulation(strategy_name, params, stock_data, valid_tickers, year):
    # Slice Indicators for that year only? 
    # Indicators should be pre-calculated on full data to ensure SMA/RSI are valid on Jan 1st.
    pass 

def simulate_year(strategy, stock_data, valid_tickers, year, indicators_cache):
    # Strategy Params
    buy_threshold = strategy['Buy']
    sell_threshold = strategy['Sell']
    max_positions = strategy['MaxPos']
    max_holding_days = strategy['Hold']
    name = strategy['Name']
    
    # Filter Dates for the Year
    start_date = pd.Timestamp(f"{year}-01-01")
    end_date = pd.Timestamp(f"{year}-12-31")
    
    # Get all trading days in this year according to data
    # (Union of all indices in that range)
    all_dates = set()
    for t in valid_tickers:
        df = stock_data[t]
        # Filter df for year
        dates = df[(df.index >= start_date) & (df.index <= end_date)].index
        all_dates.update(dates)
    
    if not all_dates:
        return 0, 0 # No data
        
    sorted_dates = sorted(list(all_dates))
    
    cash = RESET_CAPITAL
    positions = {}
    equity_curve = []
    
    for date in sorted_dates:
        # 1. Sell Logic
        current_positions_value = 0
        tickers_to_remove = []

        for ticker, pos in positions.items():
            df = indicators_cache[strategy['Name']][ticker] # Uses specific cache for strategy params
            
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
                current_price = pos['last_price'] # Use last known
            
            current_positions_value += pos['shares'] * current_price

        equity = cash + current_positions_value
        equity_curve.append(equity)

        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            # Fetch fresh price for sell execution to match logic
            df = indicators_cache[strategy['Name']][ticker]
            sell_price = df.loc[date, 'Close']
            
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
        # 2. Buy Logic
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = indicators_cache[strategy['Name']][ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA']) or pd.isna(row['RSI']): continue
                
                if row['Close'] > row['SMA'] and row['RSI'] < buy_threshold:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    curr_equity = cash + sum(p['shares'] * p['last_price'] for p in positions.values())
                    target = curr_equity / max_positions
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
    
    # Force sell at end of year for calculation?
    # Or just Mark-to-Market
    final_equity = equity_curve[-1] if equity_curve else RESET_CAPITAL
    
    ret = (final_equity / RESET_CAPITAL - 1) * 100
    
    # MDD
    if not equity_curve:
        mdd = 0.0
    else:
        ec = np.array(equity_curve)
        peak = np.maximum.accumulate(ec)
        dd = (ec - peak) / peak
        mdd = dd.min() * 100
        
    return ret, mdd

def main():
    print("🚀 Comparing Yearly Returns (E vs H)...")
    
    strategies = [
        {
            "Name": "Option E (Stable)",
            "RSI": 3, "Buy": 35, "Sell": 75, "SMA": 100, "MaxPos": 7, "Hold": 20
        },
        {
            "Name": "Option H (Aggr)",
            "RSI": 3, "Buy": 20, "Sell": 80, "SMA": 50, "MaxPos": 3, "Hold": 10
        }
    ]
    
    tickers = get_kosdaq150_tickers()
    print("📥 Loading Data (2009~)...")
    raw = yf.download(tickers, start="2009-06-01", progress=False)
    
    stock_data = {}
    valid_tickers = []
    
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
    
    # Pre-calculate indicators for each strategy (since SMA differ)
    indicators_cache = {} # {StratName: {Ticker: DF}}
    
    for s in strategies:
        print(f"⚙️  Calculating Indicators for {s['Name']}...")
        cache = {}
        for t, df in stock_data.items():
            cache[t] = calculate_indicators(df.copy(), s['RSI'], s['SMA'])
        indicators_cache[s['Name']] = cache
        
    
    print("\n📊 Yearly Simulation Running...")
    
    results = []
    years = range(2010, 2026)
    
    for year in years:
        # print(f"Processing {year}...")
        row = {"Year": year}
        
        for s in strategies:
            ret, mdd = simulate_year(s, stock_data, valid_tickers, year, indicators_cache)
            row[f"{s['Name']} Return"] = ret
            row[f"{s['Name']} MDD"] = mdd
        
        results.append(row)
        
    print("\n" + "="*80)
    print(f"YEARLY COMPARISON: {strategies[0]['Name']} vs {strategies[1]['Name']}")
    print("="*80)
    
    df_res = pd.DataFrame(results)
    
    # Format for display
    print(df_res.to_markdown(index=False, floatfmt=".2f"))
    
    # Summary
    avg_e = df_res[f"{strategies[0]['Name']} Return"].mean()
    avg_h = df_res[f"{strategies[1]['Name']} Return"].mean()
    mdd_avg_e = df_res[f"{strategies[0]['Name']} MDD"].mean()
    mdd_avg_h = df_res[f"{strategies[1]['Name']} MDD"].mean()
    
    print("-" * 50)
    print(f"AVG Return: Option E ({avg_e:.2f}%) vs Option H ({avg_h:.2f}%)")
    print(f"AVG MDD   : Option E ({mdd_avg_e:.2f}%) vs Option H ({mdd_avg_h:.2f}%)")
    
    # Count Winner
    e_wins = sum(df_res[f"{strategies[0]['Name']} Return"] > df_res[f"{strategies[1]['Name']} Return"])
    print(f"Option E Outperformed in {e_wins} out of {len(years)} years.")

if __name__ == "__main__":
    main()
