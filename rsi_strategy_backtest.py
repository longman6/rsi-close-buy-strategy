import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm
import os
import sys

# ---------------------------------------------------------
# 1. 한글 폰트 설정 (OS별 자동 감지 & Colab 자동 설치)
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
                # Colab용 폰트 설치
                font_path = '/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf'
                if not os.path.exists(font_path):
                    print("한글 폰트(Nanum) 설치 중... (약 10~20초 소요)")
                    os.system("sudo apt-get -qq install -y fonts-nanum")
                
                if os.path.exists(font_path):
                    fm.fontManager.addfont(font_path)
                    font_prop = fm.FontProperties(fname=font_path)
                    plt.rc('font', family=font_prop.get_name())
                else:
                    print("폰트 설치 실패, 기본 폰트 사용")
            else:
                plt.rc('font', family='NanumGothic')
            
        plt.rc('axes', unicode_minus=False)
    except Exception as e:
        print(f"폰트 설정 오류: {e}")

set_korean_font()

# ---------------------------------------------------------
# 2. 공통 설정
# ---------------------------------------------------------
START_DATE = '2020-01-01'
INITIAL_CAPITAL = 100000000  # 1억원
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020

# ---------------------------------------------------------
# 3. 데이터 준비 함수
# ---------------------------------------------------------
def get_kospi200_tickers():
    """KOSPI 200 종목 리스트 (시가총액 상위 200)"""
    try:
        import FinanceDataReader as fdr
        print("KOSPI 종목 리스트 가져오는 중...")
        df_krx = fdr.StockListing('KOSPI')
        col = 'Marcap' if 'Marcap' in df_krx.columns else 'Amount'
        if col in df_krx.columns:
            df = df_krx.sort_values(by=col, ascending=False).head(200)
        else:
            df = df_krx.head(200)
        return [code + '.KS' for code in df['Code'].tolist()]
    except ImportError:
        return ['005930.KS', '000660.KS', '005380.KS', '035420.KS', '000270.KS']

def get_kosdaq150_tickers():
    """KOSDAQ 150 종목 리스트 (시가총액 상위 150)"""
    try:
        import FinanceDataReader as fdr
        print("KOSDAQ 종목 리스트 가져오는 중...")
        df_krx = fdr.StockListing('KOSDAQ')
        col = 'Marcap' if 'Marcap' in df_krx.columns else 'Amount'
        if col in df_krx.columns:
            df = df_krx.sort_values(by=col, ascending=False).head(150)
        else:
            df = df_krx.head(150)
        return [code + '.KQ' for code in df['Code'].tolist()]
    except ImportError:
        return ['247540.KQ', '091990.KQ', '066970.KQ', '028300.KQ', '293490.KQ']

def calculate_rsi(data, window=4):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data_bulk(tickers, start_date):
    print(f"[{len(tickers)}개 종목] 데이터 다운로드 및 지표 계산...")
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
            if len(series) < 210: continue

            df = series.to_frame(name='Close')
            df['SMA200'] = df['Close'].rolling(window=200).mean()
            df['RSI4'] = calculate_rsi(df['Close'], window=4)
            df.dropna(inplace=True)
            
            if not df.empty:
                stock_data[ticker] = df
                valid_tickers.append(ticker)
        except: pass
            
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 4. 시뮬레이션 엔진
# ---------------------------------------------------------
def run_simulation(stock_data, valid_tickers, all_dates, name="Strategy"):
    """
    기본 전략 (No SL/TC) 실행
    """
    cash = INITIAL_CAPITAL
    positions = {} 
    history = []
    trades = []
    
    # 파라미터 고정 (기본 전략)
    stop_loss_pct = None
    time_stop_days = None
    
    for date in all_dates:
        # 1. 포지션 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []
        
        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI4']
                
                # 매도 조건: RSI > 55 (이익 실현만 적용)
                if rsi > 55:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']
            
            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})
        
        # 매도 실행
        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            df = stock_data[ticker]
            sell_price = df.loc[date, 'Close']
            
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE)
            cash += (sell_amt - cost)
            
            buy_cost = (pos['shares'] * pos['buy_price']) * TX_FEE_RATE
            net_return = ((sell_amt - cost) - (pos['shares'] * pos['buy_price'] + buy_cost)) / (pos['shares'] * pos['buy_price'] + buy_cost) * 100
            trades.append({'Return': net_return})
        
        # 2. 매수 실행
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                df = stock_data[ticker]
                if date not in df.index: continue
                
                row = df.loc[date]
                if pd.isna(row['SMA200']) or pd.isna(row['RSI4']): continue
                
                # 매수 조건: 200일 이평선 위 & RSI < 30
                if row['Close'] > row['SMA200'] and row['RSI4'] < 30:
                    buy_candidates.append({'ticker': ticker, 'rsi': row['RSI4'], 'price': row['Close']})
            
            if buy_candidates:
                buy_candidates.sort(key=lambda x: x['rsi']) # RSI 낮은 순
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

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)
    
    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100
    win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100 if len(trades_df) > 0 else 0
    
    return {
        'name': name,
        'equity_curve': hist_df['Equity'],
        'final_return': final_ret,
        'mdd': mdd,
        'win_rate': win_rate,
        'trades_count': len(trades_df)
    }

# ---------------------------------------------------------
# 5. 메인 비교 함수
# ---------------------------------------------------------
def run_market_comparison():
    print("="*60)
    print(f" [시장별 RSI 전략 성과 비교] (기간: {START_DATE} ~ 현재)")
    print(" 전략: RSI Power Zone (No Stop Loss, No Time Cut)")
    print("="*60)

    # 1. KOSPI 200 시뮬레이션
    print("\n>>> 1. KOSPI 200 유니버스 분석 시작")
    kospi_tickers = get_kospi200_tickers()
    kospi_data, kospi_valid = prepare_data_bulk(kospi_tickers, START_DATE)
    
    # 전체 날짜 기준 (KOSPI 데이터 기준)
    all_dates = sorted(list(set().union(*[df.index for df in kospi_data.values()])))
    
    res_kospi = run_simulation(kospi_data, kospi_valid, all_dates, name="KOSPI 200 전략")
    
    # 2. KOSDAQ 150 시뮬레이션
    print("\n>>> 2. KOSDAQ 150 유니버스 분석 시작")
    kosdaq_tickers = get_kosdaq150_tickers()
    kosdaq_data, kosdaq_valid = prepare_data_bulk(kosdaq_tickers, START_DATE)
    
    res_kosdaq = run_simulation(kosdaq_data, kosdaq_valid, all_dates, name="KOSDAQ 150 전략")

    # 3. 벤치마크 지수 (단순 보유)
    print("\n>>> 3. 벤치마크 데이터 로드")
    try:
        # KOSPI 200 지수
        bm_kospi = yf.download('^KS200', start=START_DATE, progress=False)['Close']
        if isinstance(bm_kospi, pd.DataFrame): bm_kospi = bm_kospi.iloc[:, 0]
        bm_kospi = bm_kospi.reindex(all_dates).ffill()
        bm_kospi_eq = (bm_kospi / bm_kospi.iloc[0]) * INITIAL_CAPITAL
        
        # KOSDAQ 150 (ETF: 229200.KS)
        bm_kosdaq = yf.download('229200.KS', start=START_DATE, progress=False)['Close']
        if isinstance(bm_kosdaq, pd.DataFrame): bm_kosdaq = bm_kosdaq.iloc[:, 0]
        bm_kosdaq = bm_kosdaq.reindex(all_dates).ffill()
        
        # 첫 유효값 찾아서 정규화
        first_idx = bm_kosdaq.first_valid_index()
        if first_idx:
            start_val = bm_kosdaq.loc[first_idx]
            bm_kosdaq_eq = (bm_kosdaq / start_val) * INITIAL_CAPITAL
            bm_kosdaq_eq = bm_kosdaq_eq.fillna(INITIAL_CAPITAL)
        else:
            bm_kosdaq_eq = None
            
    except Exception as e:
        print(f"벤치마크 로드 오류: {e}")
        bm_kospi_eq = None
        bm_kosdaq_eq = None

    # --- 결과 출력 ---
    print("\n" + "="*80)
    print(f" {'구분 (유니버스)':<20} | {'수익률(%)':<10} | {'MDD(%)':<10} | {'승률(%)':<10} | {'거래횟수':<5}")
    print("-" * 80)
    
    # 전략 결과
    print(f" {res_kospi['name']:<20} | {res_kospi['final_return']:10.2f} | {res_kospi['mdd']:10.2f} | {res_kospi['win_rate']:10.2f} | {res_kospi['trades_count']:<5}")
    print(f" {res_kosdaq['name']:<20} | {res_kosdaq['final_return']:10.2f} | {res_kosdaq['mdd']:10.2f} | {res_kosdaq['win_rate']:10.2f} | {res_kosdaq['trades_count']:<5}")
    print("-" * 80)
    
    # 벤치마크 결과
    if bm_kospi_eq is not None:
        ret = (bm_kospi_eq.iloc[-1]/INITIAL_CAPITAL - 1)*100
        mdd = ((bm_kospi_eq - bm_kospi_eq.cummax())/bm_kospi_eq.cummax()).min()*100
        print(f" {'KOSPI 200 (지수)':<20} | {ret:10.2f} | {mdd:10.2f} | {'-':<10} | {'-':<5}")
        
    if bm_kosdaq_eq is not None:
        ret = (bm_kosdaq_eq.iloc[-1]/INITIAL_CAPITAL - 1)*100
        mdd = ((bm_kosdaq_eq - bm_kosdaq_eq.cummax())/bm_kosdaq_eq.cummax()).min()*100
        print(f" {'KOSDAQ 150 (ETF)':<20} | {ret:10.2f} | {mdd:10.2f} | {'-':<10} | {'-':<5}")
    print("="*80)

    # --- 시각화 ---
    plt.figure(figsize=(14, 8))
    
    # 전략 성과
    plt.plot(res_kospi['equity_curve'], label=f"Strategy: KOSPI 200 ({res_kospi['final_return']:.0f}%)", color='blue', linewidth=2)
    plt.plot(res_kosdaq['equity_curve'], label=f"Strategy: KOSDAQ 150 ({res_kosdaq['final_return']:.0f}%)", color='red', linewidth=2)
    
    # 벤치마크 (점선)
    if bm_kospi_eq is not None:
        plt.plot(bm_kospi_eq, label='Index: KOSPI 200', color='blue', linestyle='--', alpha=0.4)
    if bm_kosdaq_eq is not None:
        plt.plot(bm_kosdaq_eq, label='Index: KOSDAQ 150', color='red', linestyle='--', alpha=0.4)

    plt.title(f'RSI Power Zone Strategy: KOSPI 200 vs KOSDAQ 150 ({START_DATE} ~ )')
    plt.ylabel('Portfolio Equity (KRW)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.show()

if __name__ == "__main__":
    run_market_comparison()