import pandas as pd
import numpy as np
import duckdb
import os
import glob
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import platform

# ---------------------------------------------------------
# 1. 설정 및 경로
# ---------------------------------------------------------
DB_PATH = '/home/longman6/projects/stock-collector/data/stock.duckdb'
UNIVERSE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'kosdaq150'))
START_DATE = '2016-01-01'
INITIAL_CAPITAL = 100_000_000
MAX_POSITIONS = 3
MAX_HOLDING_DAYS = 20
RSI_WINDOW = 5
BUY_THRESHOLD = 28
SELL_THRESHOLD = 72
SMA_WINDOW = 70
LOSS_COOLDOWN_DAYS = 90

# 수수료율 설정
TX_FEE_RATE = 0.00015   # 0.015%
TAX_RATE = 0.0020       # 0.2%
SLIPPAGE_RATE = 0.001   # 0.1%

def set_korean_font():
    system_name = platform.system()
    try:
        if system_name == 'Windows':
            plt.rc('font', family='Malgun Gothic')
        elif system_name == 'Darwin':
            plt.rc('font', family='AppleGothic')
        else:
            plt.rc('font', family='NanumGothic')
        plt.rc('axes', unicode_minus=False)
    except:
        pass

set_korean_font()

# ---------------------------------------------------------
# 2. 데이터 유틸리티
# ---------------------------------------------------------
def load_universe_map(directory):
    """연도별 코스닥 150 구성 종목 로드"""
    universe_map = {}
    files = glob.glob(os.path.join(directory, "*.csv"))
    for f in files:
        year = os.path.basename(f).split('.')[0]
        try:
            df = pd.read_csv(f)
            code_col = '종목코드' if '종목코드' in df.columns else df.columns[0]
            codes = df[code_col].astype(str).str.zfill(6).tolist()
            universe_map[int(year)] = codes
            print(f"Loaded {len(codes)} symbols for year {year}")
        except Exception as e:
            print(f"Error loading {f}: {e}")
    return universe_map

def calculate_rsi(prices, window=3):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_ohlcv_data(conn, symbols, start_date):
    """DuckDB에서 OHLCV 데이터 로드 및 지표 계산"""
    fetch_start = (pd.to_datetime(start_date) - timedelta(days=400)).strftime('%Y-%m-%d')
    
    symbols_str = ", ".join([f"'{s}'" for s in symbols])
    query = f"""
    SELECT symbol, date, open, close
    FROM ohlcv_daily
    WHERE symbol IN ({symbols_str}) AND date >= '{fetch_start}'
    ORDER BY symbol, date
    """
    df = conn.execute(query).df()
    
    stock_data = {}
    for symbol, group in df.groupby('symbol'):
        group = group.sort_values('date').set_index('date')
        group.index = pd.to_datetime(group.index)
        
        # 지표 계산
        group['SMA'] = group['close'].rolling(window=SMA_WINDOW).mean()
        group['RSI'] = calculate_rsi(group['close'], window=RSI_WINDOW)
        
        # 실제 백테스트 시작일부터 필터링
        stock_data[symbol] = group[group.index >= pd.to_datetime(start_date)]
        
    return stock_data

# ---------------------------------------------------------
# 3. 백테스트 시뮬레이터 (종가 매수 / 시가 매매 하이브리드)
# ---------------------------------------------------------
def run_backtest():
    universe_map = load_universe_map(UNIVERSE_DIR)
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # KOSDAQ 150 전체 종목 리스트 추출
    all_symbols = set()
    for codes in universe_map.values():
        all_symbols.update(codes)
        
    print(f"Loading data for {len(all_symbols)} symbols from DuckDB...")
    stock_data_ref = get_ohlcv_data(conn, list(all_symbols), START_DATE)
    
    all_dates = sorted(list(set().union(*[df.index for df in stock_data_ref.values()])))
    all_dates = [d for d in all_dates if d >= pd.to_datetime(START_DATE)]
    conn.close()
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    lockout_until = {}
    
    pending_sells = []
    
    print(f"Starting optimized hybrid backtest from {START_DATE}...")

    for i, current_date in enumerate(all_dates):
        year = current_date.year
        
        # 1. 전일 종가 시그널 기반 매도 집행 (당일 시가)
        for symbol, reason in pending_sells:
            if symbol not in positions: continue
            if symbol not in stock_data_ref or current_date not in stock_data_ref[symbol].index: continue
            
            row = stock_data_ref[symbol].loc[current_date]
            open_price = row['open']
            
            if pd.isna(open_price) or open_price == 0: continue
            
            pos = positions.pop(symbol)
            sell_val = pos['shares'] * open_price
            fee_tax = sell_val * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_val - fee_tax)
            
            pnl_perc = ((sell_val - fee_tax) / (pos['shares'] * pos['buy_price'] * (1+TX_FEE_RATE+SLIPPAGE_RATE)) - 1) * 100
            
            if pnl_perc < 0:
                lockout_until[symbol] = current_date + timedelta(days=LOSS_COOLDOWN_DAYS)
                
            trades.append({
                'symbol': symbol,
                'buy_date': pos['buy_date'],
                'sell_date': current_date,
                'buy_price': pos['buy_price'],
                'sell_price': open_price,
                'pnl_perc': pnl_perc,
                'reason': reason,
                'held_days': pos['held_days']
            })
        pending_sells = []

        # 2. 기존 포지션 업데이트 (보유일 증가 및 가격 갱신)
        curr_pos_val = 0
        for symbol, pos in positions.items():
            if symbol in stock_data_ref and current_date in stock_data_ref[symbol].index:
                row = stock_data_ref[symbol].loc[current_date]
                pos['last_price'] = row['close']
                pos['held_days'] += 1
            curr_pos_val += pos['shares'] * pos['last_price']

        # 3. 당일 종가 매수 분석 및 집행
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            universe = universe_map.get(year, [])
            candidates = []
            for symbol in universe:
                if symbol in positions or symbol not in stock_data_ref or current_date not in stock_data_ref[symbol].index:
                    continue
                
                if symbol in lockout_until and current_date <= lockout_until[symbol]:
                    continue
                
                row = stock_data_ref[symbol].loc[current_date]
                if pd.isna(row['RSI']) or pd.isna(row['SMA']): continue
                
                if row['RSI'] <= BUY_THRESHOLD and row['close'] > row['SMA']:
                    candidates.append({'symbol': symbol, 'rsi': row['RSI'], 'close': row['close']})
            
            candidates = sorted(candidates, key=lambda x: x['rsi'])
            for cand in candidates[:open_slots]:
                symbol = cand['symbol']
                close_price = cand['close']
                
                current_equity_est = cash + curr_pos_val
                buy_unit = current_equity_est / MAX_POSITIONS
                if cash < buy_unit: buy_unit = cash
                
                buy_amount = buy_unit / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                shares = int(buy_amount / close_price)
                
                if shares > 0:
                    total_cost = shares * close_price * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                    cash -= total_cost
                    positions[symbol] = {
                        'shares': shares,
                        'buy_price': close_price,
                        'last_price': close_price,
                        'buy_date': current_date,
                        'held_days': 0  # 오늘 샀으므로 보유일 0
                    }
                    curr_pos_val += shares * close_price

        # 4. 장 마감 매도 시그널 생성 (익일 시가용)
        for symbol, pos in positions.items():
            if symbol in stock_data_ref and current_date in stock_data_ref[symbol].index:
                row = stock_data_ref[symbol].loc[current_date]
                
                sell_reason = None
                if row['RSI'] >= SELL_THRESHOLD:
                    sell_reason = 'RSI_EXIT'
                elif pos['held_days'] >= MAX_HOLDING_DAYS:
                    sell_reason = 'TIME_EXIT'
                
                if sell_reason:
                    pending_sells.append((symbol, sell_reason))

        history.append({'date': current_date, 'equity': cash + curr_pos_val})

    history_df = pd.DataFrame(history).set_index('date')
    trades_df = pd.DataFrame(trades)
    
    return history_df, trades_df

def generate_report(history_df, trades_df):
    final_equity = history_df['equity'].iloc[-1]
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100
    
    # MDD 계산
    history_df['peak'] = history_df['equity'].cummax()
    history_df['drawdown'] = (history_df['equity'] - history_df['peak']) / history_df['peak']
    mdd = history_df['drawdown'].min() * 100
    
    # 승률
    win_rate = (len(trades_df[trades_df['pnl_perc'] > 0]) / len(trades_df) * 100) if not trades_df.empty else 0
    
    # 연도별 수익률
    history_df['year'] = history_df.index.year
    yearly_returns = history_df.groupby('year')['equity'].last().pct_change() * 100
    # 첫 해는 초기 자본 대비
    first_year = history_df['year'].iloc[0]
    yearly_returns.loc[first_year] = (history_df.groupby('year')['equity'].last().loc[first_year] / INITIAL_CAPITAL - 1) * 100

    yearly_returns_table = "| 연도 | 수익률 |\n| :--- | :--- |\n"
    for year, ret in yearly_returns.items():
        yearly_returns_table += f"| {year} | {ret:.2f}% |\n"

    report = f"""
# 백테스트 결과 리포트 (종가 매수 / 시가 매도 하이브리드)

- **기간**: {history_df.index[0].strftime('%Y-%m-%d')} ~ {history_df.index[-1].strftime('%Y-%m-%d')}
- **초기 자본**: {INITIAL_CAPITAL:,}원
- **최종 자산**: {final_equity:,.0f}원
- **누적 수익률**: {total_return:.2f}%
- **MDD**: {mdd:.2f}%
- **승률**: {win_rate:.2f}%
- **총 거래 횟수**: {len(trades_df)}회

## 연도별 수익률
{yearly_returns_table}

## 전략 설정
- 유니버스: 코스닥 150 (연도별 구성 종목 변경)
- 매수 조건: RSI({RSI_WINDOW}) < {BUY_THRESHOLD}, 종가 > SMA({SMA_WINDOW}) -> **매수 시점: 당일 종가**
- 매도 조건: RSI({RSI_WINDOW}) > {SELL_THRESHOLD} 또는 {MAX_HOLDING_DAYS}일 보유 -> **매도 시점: 익일 시가**
- 비중: 최대 {MAX_POSITIONS}종목, 동일 비중

---
*Generated by Antigravity*
"""
    report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reports'))
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, 'backtest_report_survivorship_free.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(report)
    
    # 차트 저장
    plt.figure(figsize=(12, 6))
    plt.plot(history_df.index, history_df['equity'], label='Portfolio Equity')
    plt.title('Hybrid Close-Buy / Open-Sell Backtest: RSI 5 Strategy')
    plt.xlabel('Date')
    plt.ylabel('Equity (KRW)')
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(report_dir, 'backtest_equity_curve.png'))
    print("Chart saved as backtest_equity_curve.png")

if __name__ == "__main__":
    hist, trades = run_backtest()
    generate_report(hist, trades)
