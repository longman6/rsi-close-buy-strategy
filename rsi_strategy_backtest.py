#!pip install -q finance-datareader
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm
import os
import sys

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
START_DATE = '2008-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020

# [파라미터 설정] 이곳의 값을 변경하여 테스트 가능
RSI_WINDOW = 3          # RSI 기간
BUY_THRESHOLD = 35      # 매수 기준 (RSI < 35)
SELL_THRESHOLD = 70     # 매도 기준 (RSI > 70)
SMA_WINDOW = 100        # 이동평균선 기간 (100일선)

# ---------------------------------------------------------
# 3. 데이터 준비
# ---------------------------------------------------------
def get_kosdaq150_tickers():
    """Fetch KOSDAQ 150 tickers using PyKRX (Index Code 2203)."""
    try:
        from pykrx import stock
        print("PyKRX를 통해 코스닥 150 종목 리스트 확보 중 (지수코드: 2203)...")
        # 2203 is KOSDAQ 150 index code in PyKRX
        tickers = stock.get_index_portfolio_deposit_file("2203") 
        
        if not tickers:
            raise Exception("No tickers returned from PyKRX")
            
        # yfinance format: append .KQ
        return [ticker + '.KQ' for ticker in tickers]
    except Exception as e:
        print(f"[주의] PyKRX 오류 ({e}). 샘플 종목 사용.")
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
def run_backtest():
    tickers = get_kosdaq150_tickers()
    stock_data, valid_tickers = prepare_data(tickers, START_DATE)

    if not valid_tickers:
        print("데이터 확보 실패")
        return

    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))
    print(f"\n시뮬레이션 시작 ({len(all_dates)}일)...")

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
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE)
            cash += (sell_amt - cost)

            buy_cost = (pos['shares'] * pos['buy_price']) * TX_FEE_RATE
            net_return = ((sell_amt - cost) - (pos['shares'] * pos['buy_price'] + buy_cost)) / (pos['shares'] * pos['buy_price'] + buy_cost) * 100

            trades.append({'Ticker': ticker, 'Return': net_return, 'Date': date})

        # 2. 매수
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
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
                    max_buy_amt = invest_amt / (1 + TX_FEE_RATE)

                    if max_buy_amt < 10000: continue
                    shares = int(max_buy_amt / candidate['price'])
                    if shares > 0:
                        buy_val = shares * candidate['price']
                        cash -= (buy_val + buy_val * TX_FEE_RATE)
                        positions[candidate['ticker']] = {
                            'shares': shares, 'buy_price': candidate['price'],
                            'last_price': candidate['price']
                        }

    # 결과 분석
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)

    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100

    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100

    # 벤치마크 (KODEX 코스닥150)
    try:
        bm = yf.download('229200.KS', start=START_DATE, progress=False)['Close']
        if isinstance(bm, pd.DataFrame): bm = bm.iloc[:, 0]
        bm = bm.reindex(all_dates).ffill()

        first_valid = bm.first_valid_index()
        if first_valid:
            start_val = bm.loc[first_valid]
            bm_equity = (bm / start_val) * INITIAL_CAPITAL
            bm_equity = bm_equity.fillna(INITIAL_CAPITAL)

            bm_ret = (bm_equity.iloc[-1] / INITIAL_CAPITAL - 1) * 100
            bm_mdd = ((bm_equity - bm_equity.cummax()) / bm_equity.cummax()).min() * 100
        else:
            bm_equity = None
            bm_ret = 0
            bm_mdd = 0
    except:
        bm_equity = None
        bm_ret = 0
        bm_mdd = 0

    # 출력
    print("\n" + "="*60)
    print(f" [KOSDAQ 150 - 최종 최적화 전략]")
    print(f" 설정: RSI({RSI_WINDOW}), SMA({SMA_WINDOW}), 매수 < {BUY_THRESHOLD}, 매도 > {SELL_THRESHOLD}")
    print("-" * 60)
    print(f" 기간: {START_DATE} ~ 현재")
    print(f" 전략 수익률 : {final_ret:6.2f}%  (MDD: {mdd:6.2f}%)")
    if bm_equity is not None:
        print(f" KOSDAQ 150 : {bm_ret:6.2f}%  (MDD: {bm_mdd:6.2f}%)")
    print(f" 총 거래 횟수: {len(trades_df)}회")
    print(f" 승률       : {win_rate:6.2f}%")
    print("="*60)

    # 시각화
    plt.figure(figsize=(12, 7))
    plt.plot(hist_df.index, hist_df['Equity'], label=f'RSI({RSI_WINDOW}) + SMA({SMA_WINDOW}) Strategy', color='red', linewidth=2)
    if bm_equity is not None:
        plt.plot(bm_equity.index, bm_equity, label='KOSDAQ 150 ETF', color='gray', linestyle='--', alpha=0.7)

    plt.title(f'Final Strategy: RSI({RSI_WINDOW}) Buy<{BUY_THRESHOLD} Sell>{SELL_THRESHOLD} (Above SMA {SMA_WINDOW})')
    plt.ylabel('Equity (KRW)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Save results as image
    output_file = "backtest_result.png"
    plt.savefig(output_file)
    print(f"\n📈 백테스트 결과 차트가 저장되었습니다: {output_file}")
    # plt.show()

if __name__ == "__main__":
    run_backtest()