
import pandas as pd
import numpy as np
import yfinance as yf
import os
import sys
from datetime import datetime, timedelta

# Ensure imports work from parent dir
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rsi_strategy_backtest import prepare_data, get_kosdaq150_tickers

# Configuration (RSI 3 Aggressive)
RSI_WINDOW = 3
SMA_WINDOW = 50
BUY_THRESHOLD = 20
SELL_THRESHOLD = 80
MAX_HOLDING_DAYS = 10
MAX_POSITIONS = 3
INITIAL_CAPITAL = 50000000  # 50 Million KRW
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

def get_benchmark_data(start_date, end_date):
    """Fetch Benchmark Data"""
    # Try fetching KOSPI 200 (^KS200) and KOSDAQ Composite (^KQ) as proxy if KOSDAQ150 (^KQ11) fails
    tickers = ["^KS200", "^KQ11", "^KQ"] 
    data = yf.download(tickers, start=start_date, end=end_date, progress=False)['Close']
    
    # Handle MultiIndex column if multiple tickers returned
    if isinstance(data.columns, pd.MultiIndex):
        # Flatten or access by level
        pass
        
    ks200 = data.get('^KS200', pd.Series(dtype=float))
    kq150 = data.get('^KQ11', pd.Series(dtype=float))
    kq_comp = data.get('^KQ', pd.Series(dtype=float))
    
    # Fill KOSDAQ 150 with Composite if empty (proxy for trend)
    if kq150.dropna().empty:
        kq150 = kq_comp
        
    return ks200, kq150

def simulate_year(year, stock_data, valid_tickers):
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    cash = INITIAL_CAPITAL
    positions = {} 
    equity_curve = []
    
    # Construct Master Calendar for the year from all stock data
    # (Union of all indices within the year range)
    all_dates = set()
    for df in stock_data.values():
         # Slice lightly to check dates
        dates = df.loc[start_date:end_date].index
        all_dates.update(dates)
    
    trading_days = sorted(list(all_dates))
    
    if not trading_days:
        return 0, 0, INITIAL_CAPITAL # No data
        
    for date in trading_days:
        # 1. Sell Logic
        current_positions_value = 0
        tickers_to_remove = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                
                # Logic
                rsi = df.loc[date, 'RSI']
                # Calendar days held
                days_held = (date - pos['buy_date']).days 
                
                if rsi > SELL_THRESHOLD:
                    tickers_to_remove.append(ticker)
                elif days_held >= MAX_HOLDING_DAYS:
                    tickers_to_remove.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price
            
        equity = cash + current_positions_value
        equity_curve.append(equity)
        
        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)
            
        # 2. Buy Logic
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                rsi_val = row['RSI']
                sma_val = row['SMA']
                
                if pd.isna(rsi_val) or pd.isna(sma_val): continue
                
                if row['Close'] > sma_val and rsi_val < BUY_THRESHOLD:
                    candidates.append({'ticker': ticker, 'rsi': rsi_val, 'price': row['Close']})
            
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                for can in candidates[:open_slots]:
                    curr_equity = cash + sum(p['shares'] * p['last_price'] for p in positions.values())
                    target_amt = curr_equity / MAX_POSITIONS
                    
                    invest = min(target_amt, cash)
                    max_buy_val = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 100000: continue
                    
                    shares = int(max_buy_val / can['price'])
                    if shares > 0:
                        buy_val = shares * can['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[can['ticker']] = {
                            'shares': shares, 
                            'buy_price': can['price'],
                            'last_price': can['price'], 
                            'buy_date': date
                        }

    final_equity = equity_curve[-1] if equity_curve else INITIAL_CAPITAL
    ret_pct = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    # MDD
    ec = np.array(equity_curve)
    peak = np.maximum.accumulate(ec)
    dd = (ec - peak) / peak
    mdd = dd.min() * 100
    
    return ret_pct, mdd, final_equity

def main():
    print(f"🚀 Analyze Annual Returns (RSI {RSI_WINDOW} Aggressive)")
    print(f"💰 Initial Annual Capital: {INITIAL_CAPITAL:,} KRW")
    
    # 1. Prepare Data
    tickers = get_kosdaq150_tickers()
    # Need data from 2011 to ensure 2012 start is safe (SMA 50 needs 50 days, prepare_data fetches appropriately)
    # Let's fetch from 2011-01-01 to cover 2012 onwards fully.
    stock_data, valid_tickers = prepare_data(tickers, '2011-01-01', RSI_WINDOW, SMA_WINDOW)
    
    # Manually calculate RSI_3 and SMA_50 because prepare_data might use defaults?
    # Check prepare_data implementation.. it uses arguments.
    # But wait, prepare_data in rsi_strategy_backtest.py takes rsi_window and sma_window as args.
    # So headers will be RSI_{rsi_window} (e.g. RSI_3)
    
    # 2. Benchmarks
    print("📊 Fetching Benchmark Data...")
    ks200, kq150 = get_benchmark_data('2012-01-01', '2025-12-31')
    
    years = range(2012, 2026)
    results = []
    
    print("\n📅 Starting Yearly Simulation...")
    print(f"{'Year':<6} | {'Strategy %':<10} | {'MDD %':<8} | {'Profit(KRW)':<15} | {'KOSPI200 %':<10} | {'KOSDAQ150 %':<10}")
    print("-" * 75)
    
    for y in years:
        # Benchmark Returns
        try:
            y_start = f"{y}-01-01"
            y_end = f"{y}-12-31"
            
            # Get first and last valid price for benchmark
            # Slice safely
            sub_ks = ks200.loc[y_start:y_end]
            sub_kq = kq150.loc[y_start:y_end]
            
            if sub_ks.empty or sub_kq.empty:
                ks_ret = 0
                kq_ret = 0
            else:
                ks_ret = (sub_ks.iloc[-1] / sub_ks.iloc[0] - 1) * 100
                kq_ret = (sub_kq.iloc[-1] / sub_kq.iloc[0] - 1) * 100
        except:
            ks_ret = 0
            kq_ret = 0
            
        # Strategy Simulation
        strat_ret, strat_mdd, final_eq = simulate_year(y, stock_data, valid_tickers)
        profit = final_eq - INITIAL_CAPITAL
        
        print(f"{y:<6} | {strat_ret:>9.2f}% | {strat_mdd:>7.2f}% | {int(profit):>14,} | {ks_ret:>9.2f}% | {kq_ret:>9.2f}%")
        
        results.append({
            'Year': y,
            'Strategy Return': strat_ret,
            'Strategy Profit': profit,
            'Strategy MDD': strat_mdd,
            'KOSPI200 Return': ks_ret,
            'KOSDAQ150 Return': kq_ret
        })
        
    # Save Report
    df = pd.DataFrame(results)
    
    report_path = "reports/rsi3_yearly_analysis.md"
    with open(report_path, "w") as f:
        f.write("# 📅 Hourly / Periodic Return Analysis (Yearly Reset)\n")
        f.write("### Strategy: RSI 3 Aggressive (Reset to 50M KRW every Jan 1st)\n")
        f.write(f"- RSI: {RSI_WINDOW}, SMA: {SMA_WINDOW}, Buy: {BUY_THRESHOLD}, Sell: {SELL_THRESHOLD}, Hold: {MAX_HOLDING_DAYS}, MaxPos: {MAX_POSITIONS}\n\n")
        
        f.write(df.to_markdown(index=False, floatfmt=".2f"))
        
        f.write("\n\n### Summary\n")
        avg_ret = df['Strategy Return'].mean()
        total_profit = df['Strategy Profit'].sum()
        f.write(f"- Average Annual Return: **{avg_ret:.2f}%**\n")
        f.write(f"- Total Cumulative Profit (Simple Sum): **{int(total_profit):,} KRW**\n")
        
    print(f"\n✅ Report Saved: {report_path}")

if __name__ == "__main__":
    main()
