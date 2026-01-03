#!pip install -q finance-datareader
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm
import os
import sys
from datetime import datetime

# ---------------------------------------------------------
# 1. 한글 폰트 설정
# ---------------------------------------------------------
def set_korean_font():
    system_name = platform.system()
    is_colab = 'google.colab' in sys.modules
    try:
        if system_name == 'Windows':
            plt.rc('font', family='Malgun Gothic')
        elif system_name == 'Darwin':
            plt.rc('font', family='AppleGothic')
        else:
            if is_colab:
                font_path = '/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf'
                if not os.path.exists(font_path):
                    os.system("sudo apt-get -qq install -y fonts-nanum")
                if os.path.exists(font_path):
                    fm.fontManager.addfont(font_path)
                    plt.rc('font', family='NanumBarunGothic')
            else:
                plt.rc('font', family='NanumGothic')
        plt.rc('axes', unicode_minus=False)
    except:
        pass

set_korean_font()

# ---------------------------------------------------------
# 2. 전략 설정 (최적화 파라미터 적용)
# ---------------------------------------------------------
START_DATE = '2005-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015   # 0.015% (매수/매도 각각)
TAX_RATE = 0.0020       # 0.2% (매도 시)
SLIPPAGE_RATE = 0.001   # 0.1% (매수/매도 각각 슬리피지 지연/체결오차)

# [파라미터 설정] 이곳의 값을 변경하여 테스트 가능
RSI_WINDOW = 5          # RSI 기간
BUY_THRESHOLD = 35      # 매수 기준 (RSI < 35)
SELL_THRESHOLD = 70     # 매도 기준 (RSI > 70)
SMA_WINDOW = 50        # 이동평균선 기간 (100일선 -> 50)

# ---------------------------------------------------------
# 3. 데이터 준비
# ---------------------------------------------------------
def get_kosdaq150_tickers():
    """Load KOSDAQ 150 tickers from local file 'kosdaq150_list.txt'."""
    filename = 'kosdaq150_list.txt'
    tickers = []
    try:
        import ast
        if not os.path.exists(filename):
             print(f"[오류] {filename} 파일이 없습니다. 샘플 종목을 사용합니다.")
             return ['247540.KQ', '091990.KQ', '066970.KQ', '028300.KQ', '293490.KQ']

        print(f"'{filename}'에서 종목 리스트를 읽어옵니다...")
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    # Parse dictionary string: {'code': '...', 'name': '...'}
                    data = ast.literal_eval(line)
                    tickers.append(data['code'] + '.KQ')
                except:
                    pass
        
        print(f"총 {len(tickers)}개 종목 로드 완료.")
        return tickers

    except Exception as e:
        print(f"[주의] 파일 읽기 오류 ({e}). 샘플 종목 사용.")
        return ['247540.KQ', '091990.KQ', '066970.KQ', '028300.KQ', '293490.KQ']

def calculate_rsi(data, window):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(tickers, start_date):
    print(f"[{len(tickers)}개 종목] 데이터 다운로드 및 지표 계산 (SMA {SMA_WINDOW}, RSI {RSI_WINDOW})...")
    data = yf.download(tickers, start=start_date, progress=True)

    stock_data = {}
    valid_tickers = []

    if isinstance(data.columns, pd.MultiIndex):
        try:
            closes = data.xs('Close', axis=1, level=0)
        except:
             if 'Close' in data.columns.get_level_values(0): closes = data['Close']
             else: return {}, []
    else:
        closes = data['Close'] if 'Close' in data.columns else data

    for ticker in tickers:
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()

            # SMA 계산을 위해 충분한 데이터가 있는지 확인 (SMA 기간 + 10일 여유)
            if len(series) < SMA_WINDOW + 10: continue

            df = series.to_frame(name='Close')

            # [지표 계산] 파라미터 변수 사용
            df['SMA'] = df['Close'].rolling(window=SMA_WINDOW).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=RSI_WINDOW)

            df.dropna(inplace=True)

            if not df.empty:
                stock_data[ticker] = df
                valid_tickers.append(ticker)
        except: pass

    return stock_data, valid_tickers

# ---------------------------------------------------------
# 4. 시뮬레이션 엔진
# ---------------------------------------------------------
# ---------------------------------------------------------
# 4. 시뮬레이션 엔진
# ---------------------------------------------------------
def run_simulation(stock_data, valid_tickers, market_data=None, use_filter=False):
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    # If using filter, ensure we have market data for these dates
    if use_filter and market_data is not None:
         market_data = market_data.reindex(all_dates).ffill()

    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []

    for date in all_dates:
        # 1. 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']

                # 매도 조건: RSI > SELL_THRESHOLD (70)
                if rsi > SELL_THRESHOLD:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']

            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})

        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']

            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)

            buy_total_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_total_cost) / buy_total_cost * 100

            trades.append({'Ticker': ticker, 'Return': net_return, 'Date': date})

        # 2. 매수
        # Market Filter Check
        market_condition_ok = True
        if use_filter and market_data is not None:
            if date in market_data.index:
                 mkt_close = market_data.loc[date, 'Close']
                 mkt_sma = market_data.loc[date, 'SMA_20']
                 if mkt_close < mkt_sma:
                     market_condition_ok = False
            else:
                 # If no market data, assume OK or Skip? Let's assume OK to be less restrictive on missing data
                 pass

        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0 and market_condition_ok:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = stock_data[ticker]
                if date not in df.index: continue

                row = df.loc[date]
                # 매수 조건: SMA선 위 & RSI < BUY_THRESHOLD (35)
                if row['Close'] > row['SMA'] and row['RSI'] < BUY_THRESHOLD:
                    buy_candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})

            if buy_candidates:
                buy_candidates.sort(key=lambda x: x['rsi'])
                for candidate in buy_candidates[:open_slots]:
                    target_amt = total_equity * ALLOCATION_PER_STOCK
                    invest_amt = min(target_amt, cash)
                    max_buy_amt = invest_amt / (1 + TX_FEE_RATE + SLIPPAGE_RATE)

                    if max_buy_amt < 10000: continue
                    shares = int(max_buy_amt / candidate['price'])
                    if shares > 0:
                        buy_val = shares * candidate['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[candidate['ticker']] = {
                            'shares': shares, 'buy_price': candidate['price'],
                            'last_price': candidate['price']
                        }

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)
    
    if hist_df.empty: return 0, 0, 0, 0, pd.DataFrame()

    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100

    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        
    return final_ret, mdd, win_rate, len(trades_df), hist_df

def run_backtest():
    tickers = get_kosdaq150_tickers()
    stock_data, valid_tickers = prepare_data(tickers, START_DATE)
    
    # Market Data for Filter (KODEX KOSDAQ150)
    print("시장 지수 데이터(KODEX 코스닥150) 다운로드 중...")
    market_df = yf.download('229200.KS', start=START_DATE, progress=False)
    # Handle yfinance structure
    if isinstance(market_df.columns, pd.MultiIndex):
        if 'Close' in market_df.columns.get_level_values(0): 
            market_df = market_df.xs('Close', axis=1, level=0)
            # If ticker name is column, select it, else take first
            if '229200.KS' in market_df.columns: market_df = market_df['229200.KS'].to_frame('Close')
            else: market_df = market_df.iloc[:, 0].to_frame('Close')
        else: market_df = market_df.iloc[:, 0].to_frame('Close')
    else: # Single Index
         if 'Close' not in market_df.columns: market_df = market_df.iloc[:, 0].to_frame('Close')
         else: market_df = market_df[['Close']]
    
    market_df['SMA_20'] = market_df['Close'].rolling(window=20).mean()

    print("\n--- 전략 1: 기존 전략 (필터 X) ---")
    ret1, mdd1, win1, cnt1, hist1 = run_simulation(stock_data, valid_tickers, market_data=market_df, use_filter=False)
    
    print("\n--- 전략 2: 마켓 필터 전략 (지수 > 20일선) ---")
    ret2, mdd2, win2, cnt2, hist2 = run_simulation(stock_data, valid_tickers, market_data=market_df, use_filter=True)

    # 연도별 비교 표 생성
    hist1['Year'] = hist1.index.year
    hist2['Year'] = hist2.index.year
    years = sorted(list(set(hist1['Year'].unique()) | set(hist2['Year'].unique())))

    yearly_lines = []
    
    start_eq1 = INITIAL_CAPITAL
    start_eq2 = INITIAL_CAPITAL
    
    for year in years:
        row = f"| {year} |"
        
        # Strategy 1
        y1 = hist1[hist1['Year'] == year]
        if not y1.empty:
            ret_y1 = (y1['Equity'].iloc[-1] / start_eq1 - 1) * 100
            start_eq1 = y1['Equity'].iloc[-1]
            row += f" {ret_y1:6.2f}% |"
        else: row += "   -   |"
            
        # Strategy 2
        y2 = hist2[hist2['Year'] == year]
        if not y2.empty:
            ret_y2 = (y2['Equity'].iloc[-1] / start_eq2 - 1) * 100
            start_eq2 = y2['Equity'].iloc[-1]
            row += f" {ret_y2:6.2f}% |"
        else: row += "   -   |"
        
        yearly_lines.append(row)

    yearly_table = "\n".join(yearly_lines)

    summary = f"""
### [마켓 필터 비교 리포트] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **설정**: RSI {RSI_WINDOW}, SMA {SMA_WINDOW}
- **비교**: 기존 전략 vs 마켓 필터(KOSDAQ 150 > 20일선) 적용

| 구분 | 전략 1 (기존) | 전략 2 (지수필터) |
| :--- | :--- | :--- |
| **수익률** | **{ret1:.2f}%** | **{ret2:.2f}%** |
| **MDD** | {mdd1:.2f}% | {mdd2:.2f}% |
| **승률** | {win1:.2f}% | {win2:.2f}% |
| **거래수** | {cnt1}회 | {cnt2}회 |

#### 연도별 수익률 비교
| 연도 | 기존 전략 | 필터 전략 |
| :--- | :--- | :--- |
{yearly_table}

---
"""
    print(summary)
    
    with open("backtest_report.md", "a", encoding="utf-8") as f:
        f.write(summary)
    print("✅ 리포트 저장 완료.")

if __name__ == "__main__":
    run_backtest()