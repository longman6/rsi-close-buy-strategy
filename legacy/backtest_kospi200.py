#!/usr/bin/env python3
"""
KOSPI 200 RSI 전략 백테스트 스크립트
- KOSDAQ 150에서 사용한 동일한 RSI 전략을 KOSPI 200에 적용
- FinanceDataReader를 사용하여 데이터 다운로드
"""
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import platform
import matplotlib.font_manager as fm
import os
import sys
import ast
import json
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
# 2. 전략 설정 (최적화 파라미터 적용 - KOSDAQ 150과 동일)
# ---------------------------------------------------------
START_DATE = '2010-01-01'
INITIAL_CAPITAL = 100000000  # 1억원
TX_FEE_RATE = 0.00015   # 0.015% (매수/매도 각각)
TAX_RATE = 0.0020       # 0.2% (매도 시)
SLIPPAGE_RATE = 0.001   # 0.1% (매수/매도 각각 슬리피지)

# ---------------------------------------------------------
# 3. 데이터 준비
# ---------------------------------------------------------
def get_kospi200_tickers():
    """Load KOSPI 200 tickers from local file 'data/kospi200_list.txt'."""
    filename = 'data/kospi200_list.txt'
    tickers = []
    names = {}
    try:
        if not os.path.exists(filename):
            print(f"[오류] {filename} 파일이 없습니다.")
            return [], {}

        print(f"'{filename}'에서 종목 리스트를 읽어옵니다...")
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    code = data['code']
                    # 잘못된 형식의 코드 필터링 (예: '0126Z0')
                    if not code.isdigit():
                        continue
                    tickers.append(code)
                    names[code] = data['name']
                except:
                    pass
        
        print(f"총 {len(tickers)}개 종목 로드 완료.")
        return tickers, names

    except Exception as e:
        print(f"[주의] 파일 읽기 오류 ({e}).")
        return [], {}

def calculate_rsi(data, window):
    """RSI 계산 (SMA 기반 - KOSDAQ 150과 동일)"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(tickers, start_date, rsi_window, sma_window, names=None):
    """KOSPI 200 종목 데이터 준비 (FinanceDataReader 활용)"""
    if isinstance(start_date, str):
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = start_date
        
    # SMA 계산을 위한 충분한 데이터 확보 (약 6개월 전부터 로드)
    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")
    
    print(f"[{len(tickers)}개 종목] 데이터 준비 중... (Source: FinanceDataReader)")
    
    stock_data = {}
    valid_tickers = []
    
    for i, ticker in enumerate(tickers):
        try:
            # FinanceDataReader Download
            df = fdr.DataReader(ticker, fetch_start_date)
            
            if df is None or df.empty: 
                continue
            if len(df) < sma_window + 10: 
                continue

            # FDR returns columns: Open, High, Low, Close, Volume, Change
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)
            df = df[df.index >= start_dt]
            
            stock_data[ticker] = df
            valid_tickers.append(ticker)
            
            if (i + 1) % 20 == 0:
                name = names.get(ticker, ticker) if names else ticker
                print(f"  진행: {i+1}/{len(tickers)} ({name})")
                
        except Exception as e:
            # API 에러 시 조용히 스킵
            continue
    
    print(f"✅ 총 {len(valid_tickers)}개 종목 데이터 준비 완료.")
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 4. 시뮬레이션 엔진 (KOSDAQ 150과 동일)
# ---------------------------------------------------------
def run_simulation(stock_data, valid_tickers, 
                   max_holding_days=20, 
                   buy_threshold=20, 
                   sell_threshold=75, 
                   max_positions=7,
                   loss_lockout_days=90):
    
    # Dynamic Allocation
    allocation_per_stock = 1.0 / max_positions

    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []
    
    # Loss Lockout Dictionary: {ticker: lockout_end_date}
    lockout_until = {}

    for date in all_dates:
        # 1. 평가 및 매도 (먼저!)
        current_positions_value = 0
        tickers_to_sell = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']

                # 매도 조건: RSI >= SELL_THRESHOLD OR Max Holding Days Reached
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
            
            # Loss Lockout Logic (단순 가격 기준)
            price_return = (sell_price - pos['buy_price']) / pos['buy_price']
            if price_return < 0 and loss_lockout_days > 0:
                lockout_end = date + timedelta(days=loss_lockout_days)
                lockout_until[ticker] = lockout_end

        # 매도 후 total_equity 재계산
        current_positions_value = sum(pos['shares'] * pos['last_price'] for pos in positions.values())
        total_equity = cash + current_positions_value

        # 3. 매수
        open_slots = max_positions - len(positions)
        if open_slots > 0:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                
                # Check Lockout
                if ticker in lockout_until:
                    if date <= lockout_until[ticker]:
                        continue
                    else:
                        del lockout_until[ticker]

                df = stock_data[ticker]
                if date not in df.index: continue

                row = df.loc[date]
                # 매수 조건: SMA선 위 & RSI <= BUY_THRESHOLD
                if row['Close'] > row['SMA'] and row['RSI'] <= buy_threshold:
                    buy_candidates.append({'ticker': ticker, 'rsi': row['RSI'], 'price': row['Close']})

            if buy_candidates:
                buy_candidates.sort(key=lambda x: x['rsi'])
                for candidate in buy_candidates[:open_slots]:
                    current_positions_value = sum(
                        pos['shares'] * pos['last_price'] for pos in positions.values()
                    )
                    total_equity = cash + current_positions_value
                    
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
                            'held_bars': 0
                        }

        # 4. 마지막에 held_bars 증가
        for ticker, pos in positions.items():
            pos['held_bars'] += 1

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)
    
    if hist_df.empty: 
        return 0, 0, 0, 0, pd.DataFrame(), pd.DataFrame()

    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100

    win_rate = 0
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        
    return final_ret, mdd, win_rate, len(trades_df), hist_df, trades_df

# ---------------------------------------------------------
# 5. 메인 백테스트 함수
# ---------------------------------------------------------
def run_kospi200_backtest():
    """KOSPI 200에 대해 backtest_config.json의 전략들을 테스트"""
    config_file = 'backtest_config.json'
    if not os.path.exists(config_file):
        print(f"❌ {config_file} not found.")
        return

    with open(config_file, 'r', encoding='utf-8') as f:
        configs = json.load(f)

    tickers, names = get_kospi200_tickers()
    if not tickers:
        print("❌ KOSPI 200 종목을 로드할 수 없습니다.")
        return
        
    results = []
    all_hist = {}
    all_trades = {}

    print(f"\n🚀 KOSPI 200 백테스트 시작: {list(configs.keys())}")
    print(f"   기간: {START_DATE} ~ 현재")
    print(f"   종목 수: {len(tickers)}개")
    print("="*60)
    
    for name, cfg in configs.items():
        print(f"\n>>> [전략 {name}] 실행 중...")
        print(f"    파라미터: RSI {cfg['rsi_window']}, Buy<{cfg['buy_threshold']}, Sell>{cfg['sell_threshold']}, SMA {cfg['sma_window']}, 최대보유 {cfg['max_holding_days']}일, 포지션 {cfg['max_positions']}개")
        
        # Prepare Data
        stock_data, valid_tickers = prepare_data(
            tickers, 
            START_DATE, 
            cfg['rsi_window'], 
            cfg['sma_window'],
            names
        )
        
        # Run Simulation
        ret, mdd, win_rate, count, hist, trades = run_simulation(
            stock_data, 
            valid_tickers, 
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
        all_hist[name] = hist
        all_trades[name] = trades
        
        print(f"    👉 결과: 수익률 {ret:.2f}%, MDD {mdd:.2f}%, 승률 {win_rate:.2f}%, 거래 {count}회")

    # ---------------------------------------------------------
    # 6. 리포트 생성
    # ---------------------------------------------------------
    print("\n" + "="*60)
    print("📊 KOSPI 200 백테스트 결과")
    print("="*60)
    
    # 테이블 헤더
    header = f"| 전략 | 수익률 | MDD | 승률 | 거래수 | RSI | SMA | 보유일 | 포지션 |\n"
    header += f"| :--- | ---: | ---: | ---: | ---: | :--- | :--- | :--- | :--- |"
    
    rows = []
    for r in results:
        p = r['Params']
        row = f"| **{r['Name']}** | **{r['Return']:.2f}%** | {r['MDD']:.2f}% | {r['WinRate']:.2f}% | {r['Count']} | "
        row += f"{p['rsi_window']} / {p['buy_threshold']}-{p['sell_threshold']} | {p['sma_window']} | {p['max_holding_days']}d | {p['max_positions']} |"
        rows.append(row)
    
    table = "\n".join(rows)
    final_report = f"\n{header}\n{table}\n"
    
    print(final_report)
    
    # 연도별 성과 추가
    yearly_report = generate_yearly_report(results, all_hist, all_trades)
    
    # 리포트 저장
    report_path = "reports/kospi200_backtest_report.md"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# KOSPI 200 RSI 전략 백테스트 리포트\n\n")
        f.write(f"**생성일:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**테스트 기간:** {START_DATE} ~ 현재\n\n")
        f.write(f"**초기 자본:** {INITIAL_CAPITAL:,}원\n\n")
        f.write("## 1. 전략별 성과 요약\n")
        f.write(final_report)
        f.write("\n## 2. 연도별 성과\n")
        f.write(yearly_report)
        
    print(f"\n✅ 리포트 저장 완료: {report_path}")
    
    return results, all_hist, all_trades


def generate_yearly_report(results, all_hist, all_trades):
    """연도별 성과 리포트 생성"""
    report = ""
    
    for r in results:
        name = r['Name']
        hist = all_hist.get(name)
        trades = all_trades.get(name)
        
        if hist is None or hist.empty:
            continue
            
        report += f"\n### 전략 {name}\n\n"
        
        hist['Year'] = hist.index.year
        if not trades.empty:
            trades['Year'] = pd.to_datetime(trades['Date']).dt.year
        
        years = sorted(hist['Year'].unique())
        
        report += "| 연도 | 수익률 | MDD | 승률 | 거래수 |\n"
        report += "| :--- | ---: | ---: | ---: | ---: |\n"
        
        start_eq = INITIAL_CAPITAL
        
        for year in years:
            y_hist = hist[hist['Year'] == year]
            if y_hist.empty:
                continue
                
            end_eq = y_hist['Equity'].iloc[-1]
            ret_y = (end_eq / start_eq - 1) * 100
            
            # MDD 계산
            norm_eq = y_hist['Equity'] / start_eq
            local_dd = (norm_eq - norm_eq.cummax()) / norm_eq.cummax()
            mdd_y = local_dd.min() * 100
            
            start_eq = end_eq
            
            # 승률 & 거래수
            if not trades.empty:
                y_trades = trades[trades['Year'] == year]
                cnt = len(y_trades)
                wins = len(y_trades[y_trades['Return'] > 0])
                wr = (wins / cnt * 100) if cnt > 0 else 0
            else:
                cnt, wr = 0, 0
            
            report += f"| {year} | {ret_y:+.2f}% | {mdd_y:.2f}% | {wr:.1f}% | {cnt} |\n"
    
    return report


if __name__ == "__main__":
    run_kospi200_backtest()
