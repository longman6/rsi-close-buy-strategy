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
RSI_WINDOW = 4
BUY_THRESHOLD = 22
SELL_THRESHOLD = 80
SMA_WINDOW = 30
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
            # 종목코드 컬럼 확인 (종목코드 또는 'Symbol' 등)
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
# 3. 백테스트 시뮬레이터
# ---------------------------------------------------------
def run_backtest():
    universe_map = load_universe_map(UNIVERSE_DIR)
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    all_dates = conn.execute("SELECT DISTINCT date FROM ohlcv_daily WHERE date >= '2016-01-01' ORDER BY date").df()['date'].tolist()
    all_dates = pd.to_datetime(all_dates)
    
    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    lockout_until = {}
    
    # 익일 시가 매매를 위한 시그널 저장
    pending_buys = []
    pending_sells = []
    
    current_year = 0
    stock_data = {}
    
    print(f"Starting backtest from {START_DATE}...")

    for i, current_date in enumerate(all_dates):
        year = current_date.year
        
        if year != current_year:
            print(f"--- Entering Year {year} ---")
            current_year = year
            symbols = universe_map.get(year, [])
            if not symbols:
                print(f"Warning: No universe found for year {year}. Using previous year's universe.")
            else:
                # 보유 중인 종목도 포함하여 데이터 로드
                held_symbols = list(positions.keys())
                fetch_symbols = list(set(symbols + held_symbols))
                stock_data = get_ohlcv_data(conn, fetch_symbols, START_DATE)
        
        # 1. 전일 시그널 기반 매매 집행 (당일 시가)
        # 매도 집행
        for symbol, reason in pending_sells:
            if symbol not in positions: continue
            if symbol not in stock_data or current_date not in stock_data[symbol].index: continue
            
            open_price = stock_data[symbol].loc[current_date]['open']
            if pd.isna(open_price): continue
            
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
        
        # 매수 집행
        open_slots = MAX_POSITIONS - len(positions)
        for cand in pending_buys[:open_slots]:
            symbol = cand['symbol']
            if symbol in positions: continue
            if symbol not in stock_data or current_date not in stock_data[symbol].index: continue
            
            open_price = stock_data[symbol].loc[current_date]['open']
            
            # Debugging check
            if pd.isna(open_price) or open_price == 0:
                continue
            
            current_equity = cash + sum(p['shares']*p['last_price'] for p in positions.values())
            buy_unit = current_equity / MAX_POSITIONS
            if cash < buy_unit:
                buy_unit = cash
            
            buy_amount = buy_unit / (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            shares = int(buy_amount / open_price)
            
            if shares > 0:
                total_cost = shares * open_price * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
                cash -= total_cost
                positions[symbol] = {
                    'shares': shares,
                    'buy_price': open_price,
                    'last_price': open_price,
                    'buy_date': current_date,
                    'held_days': 0
                }
        pending_buys = []
        
        # 2. 포지션 업데이트 및 자산 평가 (당일 종가 기준)
        current_equity = cash
        for symbol, pos in positions.items():
            if symbol not in stock_data or current_date not in stock_data[symbol].index:
                current_equity += pos['shares'] * pos['last_price']
                continue
            
            row = stock_data[symbol].loc[current_date]
            close_price = row['close']
            pos['last_price'] = close_price
            pos['held_days'] += 1
            current_equity += pos['shares'] * close_price
        
        history.append({'date': current_date, 'equity': current_equity})
        
        # 3. 당일 종가 기준 시그널 생성 (익일 시가 매매용)
        # 매도 시그널
        for symbol, pos in positions.items():
            if symbol not in stock_data or current_date not in stock_data[symbol].index: continue
            row = stock_data[symbol].loc[current_date]
            rsi = row['RSI']
            if pd.isna(rsi): continue
            
            sell_reason = None
            if rsi >= SELL_THRESHOLD:
                sell_reason = 'RSI_EXIT'
            elif pos['held_days'] >= MAX_HOLDING_DAYS:
                sell_reason = 'TIME_EXIT'
            
            if sell_reason:
                pending_sells.append((symbol, sell_reason))
        
        # 매수 시그널
        open_slots_next = MAX_POSITIONS - len(positions) + len(pending_sells)
        if open_slots_next > 0:
            candidates = []
            for symbol, data in stock_data.items():
                if symbol in positions: continue
                if current_date not in data.index: continue
                
                if symbol in lockout_until:
                    if current_date <= lockout_until[symbol]: continue
                    else: del lockout_until[symbol]
                
                row = data.loc[current_date]
                
                if row['RSI'] <= BUY_THRESHOLD and row['close'] > row['SMA']:
                    candidates.append({'symbol': symbol, 'rsi': row['RSI']})
            
            candidates = sorted(candidates, key=lambda x: x['rsi'])
            pending_buys = candidates[:open_slots_next]

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

    # 연도별 수익률 마크다운 테이블 생성 (tabulate 의존성 제거)
    yearly_returns_table = "| 연도 | 수익률 |\n| :--- | :--- |\n"
    for year, ret in yearly_returns.items():
        yearly_returns_table += f"| {year} | {ret:.2f}% |\n"

    report = f"""
# 백테스트 결과 리포트 (생존자 편향 제거 - 필터 없음)

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
- 매수 조건: RSI({RSI_WINDOW}) < {BUY_THRESHOLD}, 종가 > SMA({SMA_WINDOW})
- 매도 조건: RSI({RSI_WINDOW}) > {SELL_THRESHOLD} 또는 {MAX_HOLDING_DAYS}일 보유
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
    plt.title('Survivorship-Bias-Free Backtest: RSI 4 Strategy (No Filter)')
    plt.xlabel('Date')
    plt.ylabel('Equity (KRW)')
    plt.grid(True)
    plt.legend()
    plt.savefig(os.path.join(report_dir, 'backtest_equity_curve.png'))
    print("Chart saved as backtest_equity_curve.png")

if __name__ == "__main__":
    hist, trades = run_backtest()
    generate_report(hist, trades)
