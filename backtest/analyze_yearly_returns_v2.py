
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime, timedelta
from pykrx import stock

# Ensure we can import the sibling module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import rsi_strategy_backtest as sbt

# --- Configuration for Analysis ---
RSI_WINDOW = 3
SMA_WINDOW = 150
BUY_THRESHOLD = 24
SELL_THRESHOLD = 72
MAX_HOLDING_DAYS = 40
MAX_POSITIONS = 3
LOSS_COOLDOWN_DAYS = 90  # New Parameter
INITIAL_CAPITAL = 50_000_000  # 50 Million KRW base for each year
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

def get_benchmark_returns_yearly(years):
    """
    Fetch KODEX 200 (069500) returns as Benchmark.
    """
    import FinanceDataReader as fdr
    
    results = {y: {'KODEX 200': 0.0} for y in years}
    
    # KODEX 200 ETF Code
    symbol = '069500'
    name = 'KODEX 200'
    
    start_str = f"{years[0]}-01-01"
    end_str = f"{years[-1]}-12-31"
    
    try:
        print(f"📊 {name} ({symbol}) 데이터 로딩 중...")
        df = fdr.DataReader(symbol, start_str, end_str)
        
        if df.empty:
             print(f"⚠️ {symbol} 데이터 없음.")
            
        if not df.empty and 'Close' in df.columns:
            for year in years:
                y_s = f"{year}-01-01"
                y_e = f"{year}-12-31"
                sub = df.loc[y_s:y_e]
                if not sub.empty:
                    start_price = sub.iloc[0]['Close']
                    end_price = sub.iloc[-1]['Close']
                    ret = (end_price / start_price - 1) * 100
                    results[year][name] = ret
                else:
                    results[year][name] = 0.0
        else:
            print(f"❌ {name} 데이터 로드 실패 (Empty)")

    except Exception as e:
        print(f"❌ {name} Fetch Error: {e}")
            
    return results

def simulate_year(year, stock_data, valid_tickers):
    """
    Run simulation for a single year with reset capital.
    Includes Loss Cooldown Logic.
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    cash = INITIAL_CAPITAL
    positions = {} # {ticker: {shares, buy_price, buy_date, ...}}
    equity_curve = []
    trades_count = 0
    
    # Loss Cooldown Tracker: {ticker: unlock_date}
    cooldowns = {}
    
    # Collect all trading dates
    all_dates_set = set()
    for df in stock_data.values():
        dates = df.loc[start_date:end_date].index
        all_dates_set.update(dates)
    trading_days = sorted(list(all_dates_set))
    
    if not trading_days:
        return 0, 0, 0
    
    for date in trading_days:
        # 1. Valuation & Sell
        current_eq_val = 0
        tickers_to_remove = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                row = df.loc[date]
                curr_price = row['Close']
                rsi = row['RSI']
                
                # Check Sell Signal
                days_held = (date - pos['buy_date']).days 
                
                is_sell = False
                if rsi > SELL_THRESHOLD: is_sell = True
                elif days_held >= MAX_HOLDING_DAYS: is_sell = True
                
                if is_sell:
                    tickers_to_remove.append(ticker)
                
                pos['last_price'] = curr_price
            else:
                curr_price = pos['last_price']
                
            current_eq_val += pos['shares'] * curr_price
            
        equity = cash + current_eq_val
        equity_curve.append(equity)
        
        # Execute Sells
        for ticker in tickers_to_remove:
            pos = positions.pop(ticker)
            df = stock_data[ticker]
            sell_price = df.loc[date, 'Close']
            
            sell_amt = pos['shares'] * sell_price
            # Fee & Tax
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            net_proceeds = sell_amt - cost
            cash += net_proceeds
            trades_count += 1
            
            # Cooldown Logic
            buy_cost = pos['shares'] * pos['buy_price'] * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            pnl = net_proceeds - buy_cost
            
            if pnl < 0:
                unlock_date = date + timedelta(days=LOSS_COOLDOWN_DAYS)
                cooldowns[ticker] = unlock_date
                # print(f"🥶 {ticker} Cooldown until {unlock_date.date()} (Loss: {pnl:.0f})")

        # 2. Buy
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                
                # Check Cooldown
                if ticker in cooldowns:
                    if date <= cooldowns[ticker]:
                        continue
                    else:
                        del cooldowns[ticker] # Expired
                
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                # Logic: Close > SMA and RSI < Threshold
                if row['Close'] > row['SMA'] and row['RSI'] < BUY_THRESHOLD:
                    candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})
            
            # Sort by Lower RSI
            if candidates:
                candidates.sort(key=lambda x: x['rsi'])
                
                # Update equity for sizing
                curr_pos_val = sum(p['shares'] * p['last_price'] for p in positions.values())
                curr_equity = cash + curr_pos_val
                target_amt = curr_equity / MAX_POSITIONS
                
                for can in candidates[:open_slots]:
                    invest = min(target_amt, cash)
                    max_buy_val = invest / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    
                    if max_buy_val < 50000: continue
                    
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
    
    return ret_pct, mdd, trades_count

def main():
    print(f"🚀 Analyze Yearly Returns: RSI({RSI_WINDOW}) < {BUY_THRESHOLD} / > {SELL_THRESHOLD}")
    print(f"ℹ️  Conditions: SMA {SMA_WINDOW}, TimeCut {MAX_HOLDING_DAYS}d, Cooldown {LOSS_COOLDOWN_DAYS}d")
    print(f"ℹ️  Benchmark: KODEX 200 (069500)")
    
    tickers = sbt.get_kosdaq150_tickers()
    
    # Analysis Period
    start_year = 2018
    end_year = datetime.now().year
    years = range(start_year, end_year + 1)
    
    # Data Load (Fetch from 2017 for indicators)
    print("📥 Loading Stock Data...")
    stock_data, valid_tickers = sbt.prepare_data(tickers, f"{start_year-1}-01-01", RSI_WINDOW, SMA_WINDOW)
    
    print("📊 Loading Benchmark Data (KODEX 200)...")
    bm_data = get_benchmark_returns_yearly(years)
    
    print("\n" + "="*70)
    print(f"{'Year':<6} | {'Strategy %':<11} | {'MDD %':<8} | {'Trades':<6} | {'KODEX 200 %':<11}")
    print("="*70)
    
    summary_data = []
    
    for y in years:
        ret, mdd, cnt = simulate_year(y, stock_data, valid_tickers)
        bm = bm_data[y]['KODEX 200']
        
        print(f"{y:<6} | {ret:>10.2f}% | {mdd:>7.2f}% | {cnt:>6} | {bm:>10.2f}%")
        
        summary_data.append({
            'Year': y,
            'Strategy': ret,
            'MDD': mdd,
            'Trades': cnt,
            'KODEX 200': bm
        })
        
    # Stats Summary
    df = pd.DataFrame(summary_data)
    avg_strat = df['Strategy'].mean()
    avg_bm = df['KODEX 200'].mean()
    
    print("-" * 70)
    print(f"{'AVG':<6} | {avg_strat:>10.2f}% | {'-':>8} | {'-':>6} | {avg_bm:>10.2f}%")
    print("=" * 70)
    
    # Save Report
    output_path = "../reports/rsi3_optimization_yearly.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 📅 연도별 RSI 최적화 전략 성과\n\n")
        f.write(f"- 생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 파라미터:\n")
        f.write(f"  - RSI({RSI_WINDOW}) < {BUY_THRESHOLD} (매수), > {SELL_THRESHOLD} (매도)\n")
        f.write(f"  - SMA {SMA_WINDOW} (추세 필터)\n")
        f.write(f"  - 최대 보유일: {MAX_HOLDING_DAYS}일\n")
        f.write(f"  - 손절 쿨다운: {LOSS_COOLDOWN_DAYS}일 (손실 매도 종목 재진입 금지)\n")
        f.write(f"  - 최대 포지션: {MAX_POSITIONS}개\n\n")
        
        f.write("### 연도별 수익률 비교\n")
        f.write(df.to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n### 요약\n")
        f.write(f"- **전략 평균 수익률**: {avg_strat:.2f}%\n")
        f.write(f"- **KODEX 200 평균**: {avg_bm:.2f}%\n")
        
    print(f"\n✅ Report Saved: {output_path}")

if __name__ == "__main__":
    main()
