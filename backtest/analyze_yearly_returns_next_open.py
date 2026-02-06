
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# Ensure we can import the sibling module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import rsi_strategy_backtest as sbt

# --- Configuration (User Requested) ---
RSI_WINDOW = 3
SMA_WINDOW = 150
BUY_THRESHOLD = 24
SELL_THRESHOLD = 72
MAX_HOLDING_DAYS = 40
MAX_POSITIONS = 3
LOSS_COOLDOWN_DAYS = 90
INITIAL_CAPITAL = 50_000_000
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

def get_benchmark_returns_yearly(years):
    """
    Fetch KODEX 200 (069500) returns as Benchmark.
    """
    import FinanceDataReader as fdr
    
    results = {y: {'KODEX 200': 0.0} for y in years}
    symbol = '069500'
    
    start_str = f"{years[0]}-01-01"
    end_str = f"{years[-1]}-12-31"
    
    try:
        print(f"📊 KODEX 200 ({symbol}) 데이터 로딩 중...")
        df = fdr.DataReader(symbol, start_str, end_str)
        
        if not df.empty and 'Close' in df.columns:
            for year in years:
                y_s = f"{year}-01-01"
                y_e = f"{year}-12-31"
                sub = df.loc[y_s:y_e]
                if not sub.empty:
                    start_price = sub.iloc[0]['Close']
                    end_price = sub.iloc[-1]['Close']
                    ret = (end_price / start_price - 1) * 100
                    results[year]['KODEX 200'] = ret
    except Exception as e:
        print(f"❌ Benchmark Fetch Error: {e}")
            
    return results

def simulate_year_next_open(year, stock_data, valid_tickers):
    """
    Simulate trading for a year using [Next Day Open] execution.
    Signals are generated on Close, executed on Next Open.
    """
    start_date = pd.Timestamp(f"{year}-01-01")
    end_date = pd.Timestamp(f"{year}-12-31")
    
    # 0. Collect all trading dates
    all_dates = set()
    for df in stock_data.values():
        dates = df.loc[start_date:end_date].index
        all_dates.update(dates)
    trading_days = sorted(list(all_dates))
    
    if not trading_days: return 0, 0, 0

    cash = INITIAL_CAPITAL
    positions = {} # {ticker: {shares, buy_price, buy_date, held_bars, last_price}}
    history = []
    trades_count = 0
    cooldowns = {}
    
    pending_buys = []   # List of {ticker, rsi}
    pending_sells = []  # List of ticker
    
    for date in trading_days:
        # --- 1. Execution Phase (At Open) ---
        
        # A. Execute Sells
        leftover_sells = []
        for ticker in pending_sells:
            if ticker not in positions: continue
            
            df = stock_data[ticker]
            if date not in df.index: 
                leftover_sells.append(ticker) # Market closed for this stock? Keep pending
                continue
                
            open_price = df.loc[date]['Open']
            if open_price == 0: 
                leftover_sells.append(ticker)
                continue

            # Sell
            pos = positions.pop(ticker)
            sell_amt = pos['shares'] * open_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            net_proceed = sell_amt - cost
            cash += net_proceed
            trades_count += 1
            
            # Cooldown Check
            buy_cost = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            if net_proceed < buy_cost:
                cooldowns[ticker] = date + timedelta(days=LOSS_COOLDOWN_DAYS)
                
        pending_sells = leftover_sells
        
        # B. Execute Buys
        # Available Slots = Max - Held - Pending Sells (Conservative? No, Pending Sells clear slots)
        # Actually, Pending Sells just executed cleared the slots.
        # But if some sells failed (suspension), slots are still occupied.
        open_slots = MAX_POSITIONS - len(positions)
        
        for item in pending_buys[:open_slots]:
            ticker = item['ticker']
            if ticker in positions: continue
            
            # Re-check cooldown (sanity check)
            if ticker in cooldowns and date <= cooldowns[ticker]: continue
            
            df = stock_data[ticker]
            if date not in df.index: continue
            open_price = df.loc[date]['Open']
            if open_price == 0: continue
            
            # Sizing: Use Cash + Portfolio Value (Estimated)
            # Estimate Portfolio Value using Open Price (approx)
            curr_equity = cash + sum(p['shares'] * p['last_price'] for p in positions.values())
            target_alloc = curr_equity / MAX_POSITIONS
            amount = min(target_alloc, cash)
            
            # Skip insignificant amounts
            if amount < 100000: continue
            
            max_buy_val = amount / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            shares = int(max_buy_val / open_price)
            
            if shares > 0:
                cost = shares * open_price * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                cash -= cost
                positions[ticker] = {
                    'shares': shares,
                    'buy_price': open_price,
                    'last_price': open_price, # Initial value
                    'buy_date': date,
                    'held_bars': 0
                }
        
        pending_buys = [] # Clear daily orders
        
        # --- 2. Update & Signal Phase (At Close) ---
        curr_pos_val = 0
        
        # Update Positions & Check Exit Signals
        for ticker in list(positions.keys()):
            pos = positions[ticker]
            df = stock_data[ticker]
            
            if date in df.index:
                row = df.loc[date]
                close = row['Close']
                pos['last_price'] = close
                pos['held_bars'] += 1
                
                # Exit Signal (for Next Open)
                if ticker not in pending_sells:
                    rsi = row['RSI']
                    if rsi > SELL_THRESHOLD or pos['held_bars'] >= MAX_HOLDING_DAYS:
                        pending_sells.append(ticker)
            
            curr_pos_val += pos['shares'] * pos['last_price']
            
        history.append(cash + curr_pos_val)
        
        # Generate Entry Signals (for Next Open)
        future_slots = MAX_POSITIONS - len(positions) + len(pending_sells)
        if future_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                if ticker in cooldowns:
                    if date <= cooldowns[ticker]: continue
                    else: del cooldowns[ticker]
                
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                # Entry Condition
                if row['Close'] > row['SMA'] and row['RSI'] < BUY_THRESHOLD:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI']})
            
            candidates.sort(key=lambda x: x['rsi'])
            pending_buys = candidates[:future_slots]

    # Calculate Stats
    final_equity = history[-1] if history else INITIAL_CAPITAL
    ret_pct = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    ec = np.array(history)
    peak = np.maximum.accumulate(ec)
    dd = (ec - peak) / peak
    mdd = dd.min() * 100
    
    return ret_pct, mdd, trades_count

def main():
    print(f"🚀 Analyze Yearly Returns (Next Open Exec): RSI({RSI_WINDOW}) < {BUY_THRESHOLD} / > {SELL_THRESHOLD}")
    print(f"ℹ️  Conditions: SMA {SMA_WINDOW}, TimeCut {MAX_HOLDING_DAYS}d, Cooldown {LOSS_COOLDOWN_DAYS}d, MaxPos {MAX_POSITIONS}")
    
    tickers = sbt.get_kosdaq150_tickers()
    
    start_year = 2018
    end_year = datetime.now().year
    years = range(start_year, end_year + 1)
    
    print("📥 Loading Stock Data...")
    stock_data, valid_tickers = sbt.prepare_data(tickers, f"{start_year-1}-01-01", RSI_WINDOW, SMA_WINDOW)
    
    print("📊 Loading Benchmark Data (KODEX 200)...")
    bm_data = get_benchmark_returns_yearly(years)
    
    print("\n" + "="*80)
    print(f"{'Year':<6} | {'Strategy %':<11} | {'MDD %':<8} | {'Trades':<6} | {'KODEX 200 %':<11}")
    print("="*80)
    
    summary_data = []
    
    for y in years:
        ret, mdd, cnt = simulate_year_next_open(y, stock_data, valid_tickers)
        bm = bm_data[y].get('KODEX 200', 0.0)
        
        print(f"{y:<6} | {ret:>10.2f}% | {mdd:>7.2f}% | {cnt:>6} | {bm:>10.2f}%")
        
        summary_data.append({
            'Year': y,
            'Strategy': ret,
            'MDD': mdd,
            'Trades': cnt,
            'KODEX 200': bm
        })
        
    df = pd.DataFrame(summary_data)
    avg_strat = df['Strategy'].mean()
    avg_bm = df['KODEX 200'].mean()
    
    print("-" * 80)
    print(f"{'AVG':<6} | {avg_strat:>10.2f}% | {'-':>8} | {'-':>6} | {avg_bm:>10.2f}%")
    print("=" * 80)
    
    output_path = "../reports/rsi3_yearly_next_open.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 📅 연도별 RSI 전략 성과 (익일 시가 체결)\n\n")
        f.write(f"- 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("- **매매 로직 변경**: 신호 발생 익일 시가(Open)에 매수/매도 (기존 리포트와 동일 환경)\n")
        f.write(f"- 파라미터:\n")
        f.write(f"  - RSI({RSI_WINDOW}) < {BUY_THRESHOLD}, > {SELL_THRESHOLD}, SMA {SMA_WINDOW}\n")
        f.write(f"  - Hold {MAX_HOLDING_DAYS}d, Cooldown {LOSS_COOLDOWN_DAYS}d, Pos {MAX_POSITIONS}\n\n")
        
        f.write("### 연도별 수익률\n")
        f.write(df.to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n### 요약\n")
        f.write(f"- **전략 평균 수익률**: {avg_strat:.2f}%\n")
        f.write(f"- **KODEX 200 평균**: {avg_bm:.2f}%\n")
        
    print(f"\n✅ Report Saved: {output_path}")

if __name__ == "__main__":
    main()
