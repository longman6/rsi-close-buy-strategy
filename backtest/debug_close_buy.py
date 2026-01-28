import pandas as pd
import numpy as np
import duckdb
import os
import glob
from datetime import datetime, timedelta

# ---------------------------------------------------------
# CONSTANTS (From the "Winner" of optimize_close_buy.py)
# ---------------------------------------------------------
DB_PATH = '/home/longman6/projects/stock-collector/data/stock.duckdb'
UNIVERSE_DIR = '/home/longman6/codelab/RSI_POWER_ZONE/data/kosdaq150'
START_DATE = '2016-01-01'
INITIAL_CAPITAL = 100_000_000

TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

RSI_W = 5
SMA_W = 70
BUY_TH = 28
SELL_TH = 72
HOLD = 20
MAX_POS = 3

def load_universe_map(directory):
    universe_map = {}
    files = glob.glob(os.path.join(directory, "*.csv"))
    for f in files:
        year = os.path.basename(f).split('.')[0]
        try:
            df = pd.read_csv(f)
            code_col = '종목코드' if '종목코드' in df.columns else df.columns[0]
            codes = df[code_col].astype(str).str.zfill(6).tolist()
            universe_map[int(year)] = codes
        except: pass
    return universe_map

def calculate_rsi(prices, window):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def main():
    conn = duckdb.connect(DB_PATH, read_only=True)
    universe_map = load_universe_map(UNIVERSE_DIR)
    
    all_symbols = set()
    for codes in universe_map.values():
        all_symbols.update(codes)
    
    fetch_start = (pd.to_datetime(START_DATE) - timedelta(days=400)).strftime('%Y-%m-%d')
    symbols_str = ", ".join([f"'{s}'" for s in all_symbols])
    
    print(f"Loading data for {len(all_symbols)} symbols...")
    query = f"SELECT symbol, date, open, close FROM ohlcv_daily WHERE symbol IN ({symbols_str}) AND date >= '{fetch_start}' ORDER BY symbol, date"
    df = conn.execute(query).df()
    df['date'] = pd.to_datetime(df['date'])
    
    all_dates = sorted(df[df['date'] >= START_DATE]['date'].unique())
    all_dates = [pd.Timestamp(d) for d in all_dates]
    
    stock_data_ref = {}
    for symbol, group in df.groupby('symbol'):
        group = group.sort_values('date').set_index('date')
        group['RSI'] = calculate_rsi(group['close'], RSI_W)
        group['SMA'] = group['close'].rolling(window=SMA_W).mean()
        stock_data_ref[symbol] = group.to_dict('index')
    
    conn.close()
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    pending_sells = []
    lockout_until = {}

    print("Running Backtest...")
    logs = []
    for i, current_date in enumerate(all_dates):
        # 1. Sell Execution (Open)
        for s in pending_sells:
            if s not in positions: continue
            if s not in stock_data_ref or current_date not in stock_data_ref[s]: continue
            
            open_p = stock_data_ref[s][current_date]['open']
            if pd.isna(open_p) or open_p == 0: continue
            
            pos = positions.pop(s)
            sell_val = pos['shares'] * open_p
            cost = sell_val * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_val - cost)
            
            if (sell_val - cost) <= (pos['shares'] * pos['buy_price'] * (1+TX_FEE_RATE+SLIPPAGE_RATE)):
                lockout_until[s] = current_date + timedelta(days=90)
                
        pending_sells = []
        
        # 2. Update existing (ONLY existing!)
        curr_pos_val = 0
        for s, pos in positions.items():
            if s in stock_data_ref and current_date in stock_data_ref[s]:
                pos['last_p'] = stock_data_ref[s][current_date]['close']
                pos['held'] += 1
            curr_pos_val += pos['shares'] * pos.get('last_p', pos['buy_price'])
            
        # 3. Buy at Close
        open_slots = MAX_POS - len(positions)
        if open_slots > 0:
            universe = universe_map.get(current_date.year, [])
            cands = []
            for s in universe:
                if s in positions or s not in stock_data_ref or current_date not in stock_data_ref[s]: continue
                if s in lockout_until and current_date <= lockout_until[s]: continue
                
                row = stock_data_ref[s][current_date]
                if pd.isna(row['RSI']) or pd.isna(row['SMA']): continue
                
                if row['RSI'] <= BUY_TH and row['close'] > row['SMA']:
                    cands.append({'s': s, 'rsi': row['RSI'], 'close': row['close']})
            
            cands = sorted(cands, key=lambda x: x['rsi'])
            for cand in cands[:open_slots]:
                s = cand['s']
                cp = cand['close']
                
                equity_pre_buy = cash + curr_pos_val
                buy_unit = equity_pre_buy / MAX_POS
                buy_amt = min(buy_unit, cash) / (1+TX_FEE_RATE+SLIPPAGE_RATE)
                shares = int(buy_amt / cp)
                
                if shares > 0:
                    cost = shares * cp * (1+TX_FEE_RATE+SLIPPAGE_RATE)
                    cash -= cost
                    positions[s] = {'shares': shares, 'buy_price': cp, 'last_p': cp, 'held': 0}
                    curr_pos_val += shares * cp
        
        # 4. Signal Sells
        for s, pos in positions.items():
            if s in stock_data_ref and current_date in stock_data_ref[s]:
                row = stock_data_ref[s][current_date]
                if row['RSI'] >= SELL_TH or pos['held'] >= HOLD:
                    pending_sells.append(s)
        
        total_equity = cash + curr_pos_val
        history.append({'date': current_date, 'equity': total_equity})
        
        if i < 20:
            print(f"[{current_date.date()}] Equity: {total_equity:,.0f}, Cash: {cash:,.0f}, Pos: {len(positions)}")

    hist_df = pd.DataFrame(history).set_index('date')
    print(f"Final Return: {(hist_df['equity'].iloc[-1]/INITIAL_CAPITAL-1)*100:.2f}%")
    print(f"MDD: {((hist_df['equity'] - hist_df['equity'].cummax()) / hist_df['equity'].cummax()).min() * 100:.2f}%")

if __name__ == "__main__":
    main()
