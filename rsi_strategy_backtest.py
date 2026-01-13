#!pip install -q finance-datareader
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm
import os
import sys
from datetime import datetime, timedelta

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
START_DATE = '2010-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
MAX_HOLDING_DAYS = 40   # 최대 보유일 (영업일 기준 아님, 캘린더 일수)
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
    filename = 'data/kosdaq150_list.txt'
    tickers = []
    try:
        import ast
        if not os.path.exists(filename):
             print(f"[오류] {filename} 파일이 없습니다. 샘플 종목을 사용합니다.")
             return ['247540', '091990', '066970', '028300', '293490']

        print(f"'{filename}'에서 종목 리스트를 읽어옵니다...")
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    # Parse dictionary string: {'code': '...', 'name': '...'}
                    data = ast.literal_eval(line)
                    tickers.append(data['code']) # FDR uses code only (e.g. '000250')
                except:
                    pass
        
        print(f"총 {len(tickers)}개 종목 로드 완료.")
        return tickers

    except Exception as e:
        print(f"[주의] 파일 읽기 오류 ({e}). 샘플 종목 사용.")
        return ['247540', '091990', '066970', '028300', '293490']

def calculate_rsi(data, window):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    # Use SMA (Rolling Mean) instead of Wilder's Smoothing (EWM)
    # This matches the logic used in 'optimize_all_dense.py' which yielded superior results.
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(tickers, start_date, rsi_window, sma_window):
    # SMA 계산을 위한 충분한 데이터 확보 (약 6개월 전부터 로드)
    if isinstance(start_date, str):
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = start_date
        
    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")
    
def prepare_data(tickers, start_date, rsi_window, sma_window):
    # SMA 계산을 위한 충분한 데이터 확보 (약 6개월 전부터 로드)
    if isinstance(start_date, str):
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = start_date
        
    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")
    
    print(f"[{len(tickers)}개 종목] 데이터 준비 (PKL/로컬 최우선)...")
    
    stock_data = {}
    valid_tickers = []
    
    # 0. Check for Consolidated Pickle
    import glob
    historical_dir = 'data/historical'
    pkl_files = glob.glob(os.path.join(historical_dir, "kosdaq150_combined_*.pkl"))
    
    loaded_from_pkl = False
    
    if pkl_files:
        # Use the latest one if multiple? Just take first for now.
        pkl_path = pkl_files[0] 
        print(f"📂 통합 데이터 로드 중: {pkl_path}")
        try:
            combined_data = pd.read_pickle(pkl_path)
            loaded_from_pkl = True
            
            # combined_data is dict: {'000250': df, ...}
            # Need to map to requested tickers
            for ticker in tickers:
                code = ticker.split('.')[0]
                if code in combined_data:
                    df = combined_data[code]
                    
                    # Ensure formatting
                    if 'Date' in df.columns:
                        df['Date'] = pd.to_datetime(df['Date'])
                        df.set_index('Date', inplace=True)
                        
                    if not isinstance(df.index, pd.DatetimeIndex):
                         df.index = pd.to_datetime(df.index)
                    
                    df.sort_index(inplace=True)
                    df = df[df.index >= fetch_start_date]
                    
                    if not df.empty and len(df) >= sma_window + 10:
                        df['SMA'] = df['Close'].rolling(window=sma_window).mean()
                        df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
                        df = df[df.index >= start_dt]
                        
                        stock_data[ticker] = df # Store with full ticker name
                        valid_tickers.append(ticker)
                        
        except Exception as e:
            print(f"❌ Pickle Load Error: {e}")
            loaded_from_pkl = False

    if loaded_from_pkl:
        print(f"✅ 통합 데이터 로드 완료: {len(valid_tickers)}개 종목 (Source: {pkl_files[0]})")
        return stock_data, valid_tickers


    # 1. Attempt to load from data/historical CSVs if PKL failed or incomplete
    local_files = glob.glob(os.path.join(historical_dir, "*.csv"))
    code_to_file = {}
    for fpath in local_files:
        basename = os.path.basename(fpath)
        # Expecting format '000250_Name.csv'
        parts = basename.split('_')
        if len(parts) >= 2:
            code = parts[0]
            code_to_file[code] = fpath

    # Check which tickers need downloading
    tickers_to_download = []
    
    for ticker in tickers:
        # Ticker format '000250.KQ' -> code '000250'
        code = ticker.split('.')[0]
        
        df = None
        if code in code_to_file:
            try:
                # Load local
                fpath = code_to_file[code]
                df = pd.read_csv(fpath)
                
                # Standardize columns
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                    df.set_index('Date', inplace=True)
                
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                    
                df.sort_index(inplace=True)
                
                # Filter for fetch_start_date
                df = df[df.index >= fetch_start_date]
                
            except Exception as e:
                print(f"Failed to load local {fpath}: {e}")
                df = None
        
        if df is not None and not df.empty:
            # Process Indicators
            if len(df) >= sma_window + 10:
                df['SMA'] = df['Close'].rolling(window=sma_window).mean()
                df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
                
                # Filter start_date
                df = df[df.index >= start_dt]
                
                stock_data[ticker] = df
                if ticker not in valid_tickers:
                    valid_tickers.append(ticker)
        else:
            tickers_to_download.append(ticker)

    # 2. Download remaining if any (FinanceDataReader)
    if tickers_to_download:
        print(f"📥 다운로드 필요 종목: {len(tickers_to_download)}개 (Source: FinanceDataReader)")
        
        for ticker in tickers_to_download:
            try:
                code = ticker.split('.')[0]
                # FinanceDataReader Download
                df = fdr.DataReader(code, fetch_start_date)
                
                if df is None or df.empty: continue
                if len(df) < sma_window + 10: continue

                # FDR returns columns: Open, High, Low, Close, Volume, Change
                # Index is Date
                
                df['SMA'] = df['Close'].rolling(window=sma_window).mean()
                df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
                df = df[df.index >= start_dt]
                
                stock_data[ticker] = df
                if ticker not in valid_tickers:
                     valid_tickers.append(ticker)
            except Exception as e:
                print(f"Failed to download {ticker}: {e}")
                pass

    print(f"✅ 총 {len(valid_tickers)}개 종목 데이터 준비 완료.")
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 4. 시뮬레이션 엔진
# ---------------------------------------------------------
def run_simulation(stock_data, valid_tickers, market_data=None, use_filter=False, 
                   max_holding_days=MAX_HOLDING_DAYS, 
                   buy_threshold=BUY_THRESHOLD, 
                   sell_threshold=SELL_THRESHOLD, 
                   max_positions=MAX_POSITIONS,
                   loss_lockout_days=0):
    
    # Dynamic Allocation
    allocation_per_stock = 1.0 / max_positions

    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    # If using filter, ensure we have market data for these dates
    if use_filter and market_data is not None:
         market_data = market_data.reindex(all_dates).ffill()

    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    
    # Loss Lockout Dictionary: {ticker: lockout_end_date}
    lockout_until = {}

    for date in all_dates:
        # 0. Clean up expired lockouts
        # This is strictly not necessary if we check date > lockout_until, but good for memory if long simulation
        
        # 1. Update Holding Period (Trading Days)
        # Increment held_bars for all positions since we are in a valid trading day loop
        for ticker, pos in positions.items():
            pos['held_bars'] += 1

        # 2. 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']
                
                # 보유 기간 계산 (Calendar Days로 복귀)
                days_held = (date - pos['buy_date']).days

                # 매도 조건: RSI > SELL_THRESHOLD OR Max Holding Days Reached (Trading Days)
                if rsi >= sell_threshold:
                    tickers_to_sell.append({'ticker': ticker, 'reason': 'SIGNAL'})
                elif pos['held_bars'] >= max_holding_days:
                    tickers_to_sell.append({'ticker': ticker, 'reason': 'FORCE'})

            else:
                current_price = pos['last_price']

            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})

        for item in tickers_to_sell:
            ticker = item['ticker']
            reason = item['reason']
            
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']

            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)

            buy_total_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_total_cost) / buy_total_cost * 100

            trades.append({
                'Ticker': ticker, 
                'Return': net_return, 
                'Date': date,
                'Reason': reason,
                'Days': pos['held_bars']
            })
            
            # Loss Lockout Logic
            if net_return < 0 and loss_lockout_days > 0:
                lockout_end = date + timedelta(days=loss_lockout_days)
                lockout_until[ticker] = lockout_end

        # 3. 매수
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

        open_slots = max_positions - len(positions)
        if open_slots > 0 and market_condition_ok:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                
                # Check Lockout
                if ticker in lockout_until:
                    if date <= lockout_until[ticker]:
                        continue
                    else:
                        del lockout_until[ticker] # Lockout expired

                df = stock_data[ticker]
                if date not in df.index: continue

                row = df.loc[date]
                # 매수 조건: SMA선 위 & RSI <= BUY_THRESHOLD
                if row['Close'] > row['SMA'] and row['RSI'] <= buy_threshold:
                    buy_candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})

            if buy_candidates:
                buy_candidates.sort(key=lambda x: x['rsi'])
                for candidate in buy_candidates[:open_slots]:
                    # Dynamic Allocation Amount
                    target_amt = total_equity * allocation_per_stock
                    invest_amt = min(target_amt, cash)
                    max_buy_amt = invest_amt / (1 + TX_FEE_RATE + SLIPPAGE_RATE)

                    if max_buy_amt < 10000: continue
                    shares = int(max_buy_amt / candidate['price'])
                    if shares > 0:
                        buy_val = shares * candidate['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[candidate['ticker']] = {
                            'shares': shares, 'buy_price': candidate['price'],
                            'last_price': candidate['price'],
                            'buy_date': date,
                            'held_bars': 0 # Initialize holding period counter (trading days)
                        }

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)
    
    if hist_df.empty: return 0, 0, 0, 0, pd.DataFrame(), pd.DataFrame()

    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100

    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        
    return final_ret, mdd, win_rate, len(trades_df), hist_df, trades_df

def run_backtest():
    stock_data1, valid_tickers1 = prepare_data(tickers, START_DATE, 3, 100)
    print("\n>>> 전략 1 시뮬레이션 중...")
    ret1, mdd1, win1, cnt1, hist1, trades1 = run_simulation(stock_data1, valid_tickers1, use_filter=False)
    
    # --- Strategy 2: RSI 5, SMA 50 ---
    print("\n>>> 전략 2 데이터 준비: RSI 5, SMA 50")
    stock_data2, valid_tickers2 = prepare_data(tickers, START_DATE, 5, 50)
    print("\n>>> 전략 2 시뮬레이션 중...")
    ret2, mdd2, win2, cnt2, hist2, trades2 = run_simulation(stock_data2, valid_tickers2, use_filter=False)

    # 연도별 비교 데이터 생성
    hist1['Year'] = hist1.index.year
    hist2['Year'] = hist2.index.year
    
    if not trades1.empty: trades1['Year_Trade'] = pd.to_datetime(trades1['Date']).dt.year
    if not trades2.empty: trades2['Year_Trade'] = pd.to_datetime(trades2['Date']).dt.year

    years = sorted(list(set(hist1['Year'].unique()) | set(hist2['Year'].unique())))

    yearly_lines = []
    
    start_eq1 = INITIAL_CAPITAL
    start_eq2 = INITIAL_CAPITAL
    
    for year in years:
        row = f"| {year} |"
        
        # Strategy A Stats
        y1 = hist1[hist1['Year'] == year]
        if not y1.empty:
            end_eq1 = y1['Equity'].iloc[-1]
            ret_y1 = (end_eq1 / start_eq1 - 1) * 100
            
            # MDD
            norm_eq1 = y1['Equity'] / start_eq1
            local_dd1 = (norm_eq1 - norm_eq1.cummax()) / norm_eq1.cummax()
            mdd_y1 = local_dd1.min() * 100
            
            start_eq1 = end_eq1 # Set start for next year
        else:
            ret_y1, mdd_y1 = 0, 0
            
        # Win Rate & Count A
        if not trades1.empty:
            t1 = trades1[trades1['Year_Trade'] == year]
            cnt1 = len(t1)
            win1 = len(t1[t1['Return'] > 0])
            wr1 = (win1 / cnt1 * 100) if cnt1 > 0 else 0
        else: cnt1, wr1 = 0, 0
            
        row += f" {ret_y1:6.2f}% | {mdd_y1:6.2f}% | {wr1:6.2f}% | {cnt1}회 |"

        # Strategy B Stats
        y2 = hist2[hist2['Year'] == year]
        if not y2.empty:
            end_eq2 = y2['Equity'].iloc[-1]
            ret_y2 = (end_eq2 / start_eq2 - 1) * 100
            
            # MDD
            norm_eq2 = y2['Equity'] / start_eq2
            local_dd2 = (norm_eq2 - norm_eq2.cummax()) / norm_eq2.cummax()
            mdd_y2 = local_dd2.min() * 100
            
            start_eq2 = end_eq2 # Set start for next year
        else:
            ret_y2, mdd_y2 = 0, 0
            
        # Win Rate & Count B
        if not trades2.empty:
            t2 = trades2[trades2['Year_Trade'] == year]
            cnt2 = len(t2)
            win2 = len(t2[t2['Return'] > 0])
            wr2 = (win2 / cnt2 * 100) if cnt2 > 0 else 0
        else: cnt2, wr2 = 0, 0

        row += f" {ret_y2:6.2f}% | {mdd_y2:6.2f}% | {wr2:6.2f}% | {cnt2}회 |"
        
        yearly_lines.append(row)

    yearly_table = "\n".join(yearly_lines)

    summary = f"""
### [전략 파라미터 비교] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **비교 대상**: 
  1. **전략 A (기존)**: RSI 3, SMA 100
  2. **전략 B (공격)**: RSI 5, SMA 50

| 구분 | 전략 A (RSI 3, SMA 100) | 전략 B (RSI 5, SMA 50) |
| :--- | :--- | :--- |
| **수익률** | **{ret1:.2f}%** | **{ret2:.2f}%** |
| **MDD** | {mdd1:.2f}% | {mdd2:.2f}% |
| **승률** | {win1:.2f}% | {win2:.2f}% |
| **거래수** | {cnt1}회 | {cnt2}회 |

#### 연도별 상세 비교
| 연도 | A 수익률 | A MDD | A 승률 | A 횟수 | B 수익률 | B MDD | B 승률 | B 횟수 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
{yearly_table}

---
"""
    print(summary)
    
    with open("backtest_report.md", "a", encoding="utf-8") as f:
        f.write(summary)
    print("✅ 리포트 저장 완료.")

def get_kosdaq150_ticker_map():
    """Load KOSDAQ 150 tickers and names from local file 'kosdaq150_list.txt'."""
    filename = 'kosdaq150_list.txt'
    ticker_map = {}
    try:
        import ast
        if not os.path.exists(filename):
             return {}

        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    code = data['code'] + '.KQ'
                    name = data['name']
                    ticker_map[code] = name
                except:
                    pass
        return ticker_map
    except Exception as e:
        print(f"[Map Load Error] {e}")
        return {}

def run_2025_full_year_comparison():
    print("\n🚀 2025년 1월 1일 ~ 현재 (Full Year) 백테스트 비교 시작")
    tickers = get_kosdaq150_tickers()
    ticker_map = get_kosdaq150_ticker_map()
    start_date = '2025-01-01'
    
    # Strategy A: RSI 3, SMA 100
    print("\n>>> 전략 A: RSI 3, SMA 100")
    stock_data1, valid_tickers1 = prepare_data(tickers, start_date, 3, 100)
    ret1, mdd1, win1, cnt1, hist1, trades1 = run_simulation(stock_data1, valid_tickers1, use_filter=False)
    
    # Strategy B: RSI 5, SMA 50
    print("\n>>> 전략 B: RSI 5, SMA 50")
    stock_data2, valid_tickers2 = prepare_data(tickers, start_date, 5, 50)
    ret2, mdd2, win2, cnt2, hist2, trades2 = run_simulation(stock_data2, valid_tickers2, use_filter=False)
    
    # Generate Report
    report_filename = "backtest_2025_full_comparison.md"
    
    # Helper to clean trade df
    def format_trades(df):
        if df.empty: return "거래 없음"
        df = df.copy()
        df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
        df['Return'] = df['Return'].apply(lambda x: f"{x:.2f}%")
        
        # Add Stock Name
        def get_name(code):
            return ticker_map.get(code, code)
            
        df['Name'] = df['Ticker'].apply(get_name)
        
        # Markdown Table
        header = "| 날짜 | 종목명 | 코드 | 수익률 | 사유 | 보유일 |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        rows = ""
        for _, row in df.iterrows():
            reason = row.get('Reason', '-')
            days = row.get('Days', '-')
            rows += f"| {row['Date']} | {row['Name']} | {row['Ticker']} | {row['Return']} | {reason} | {days}일 |\n"
        return header + rows

    comparison_summary = f"""
# RSI 전략 상세 비교 (2025년 전체)

**기간:** 2025-01-01 ~ 현재
**생성일:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. 성과 요약
| 구분 | 전략 A (RSI 3, SMA 100) | 전략 B (RSI 5, SMA 50) |
| :--- | :--- | :--- |
| **수익률** | **{ret1:.2f}%** | **{ret2:.2f}%** |
| **MDD** | {mdd1:.2f}% | {mdd2:.2f}% |
| **승률** | {win1:.2f}% | {win2:.2f}% |
| **거래수** | {cnt1}회 | {cnt2}회 |

## 2. 상세 거래 내역

### 전략 A (RSI 3, SMA 100)
{format_trades(trades1)}

### 전략 B (RSI 5, SMA 50)
{format_trades(trades2)}
"""
    
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write(comparison_summary)
    
    print(comparison_summary)
    print(f"\n✅ 상세 리포트가 '{report_filename}'에 저장되었습니다.")


def run_comparative_backtest():
    import json
    
    config_file = 'backtest_config.json'
    if not os.path.exists(config_file):
        print(f"❌ {config_file} not found.")
        return

    with open(config_file, 'r', encoding='utf-8') as f:
        configs = json.load(f)

    tickers = get_kosdaq150_tickers()
    results = []

    print(f"\n🚀 Running Comparative Backtest for options: {list(configs.keys())}")
    
    for name, cfg in configs.items():
        print(f"\n>>> [Option {name}] Parameters: {cfg}")
        
        # Prepare Data
        stock_data, valid_tickers = prepare_data(
            tickers, 
            START_DATE, 
            cfg['rsi_window'], 
            cfg['sma_window']
        )
        
        # Run Simulation
        ret, mdd, win_rate, count, hist, trades = run_simulation(
            stock_data, 
            valid_tickers, 
            use_filter=False,
            max_holding_days=cfg['max_holding_days'],
            buy_threshold=cfg['buy_threshold'],
            sell_threshold=cfg['sell_threshold'],
            max_positions=cfg['max_positions'],
            loss_lockout_days=cfg.get('loss_lockout_days', 0)
        )
        
        results.append({
            "Name": name,
            "Return": ret,
            "MDD": mdd,
            "WinRate": win_rate,
            "Count": count,
            "Params": cfg
        })
        print(f"   👉 Result: Return {ret:.2f}%, MDD {mdd:.2f}%, WinRate {win_rate:.2f}%")

    # Generate Report
    print("\n--------------------------------------------------------------")
    print("📊 Comparative Backtest Results")
    print("--------------------------------------------------------------")
    
    header = f"| Option | Return | MDD | Win Rate | Trades | RSI | SMA | Hold | Pos |\n"
    header += f"| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    
    rows = []
    for r in results:
        p = r['Params']
        row = f"| **{r['Name']}** | **{r['Return']:.2f}%** | {r['MDD']:.2f}% | {r['WinRate']:.2f}% | {r['Count']} | "
        row += f"{p['rsi_window']} / {p['buy_threshold']}-{p['sell_threshold']} | {p['sma_window']} | {p['max_holding_days']}d | {p['max_positions']} |"
        rows.append(row)
    
    table = "\n".join(rows)
    final_report = f"\n{header}\n{table}\n"
    
    print(final_report)
    
    print(final_report)
    
    # Ensure directory exists
    report_path = "reports/comparative_backtest_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Consolidated Backtest Report\n")
        f.write(f"Generated at: {datetime.now()}\n\n")
        f.write(final_report)
        
    print(f"✅ Report saved to {report_path}")

if __name__ == "__main__":
    # run_backtest() 
    # run_2025_dec_comparison()
    # run_2025_full_year_comparison()
    run_comparative_backtest()