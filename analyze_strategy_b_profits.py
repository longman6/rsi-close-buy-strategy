"""
전략 B (RSI 5, SMA 50, 보유 60일, 쿨다운 60일) 수익 거래 분석 스크립트
- 전체 기간 (2005-01-01 ~ 현재) 백테스트
- 수익 거래 상위 200개 추출
- 패턴 및 특징 분석
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys

# ---------------------------------------------------------
# 전략 설정 (최적화된 파라미터)
# ---------------------------------------------------------
START_DATE = '2005-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015   # 0.015%
TAX_RATE = 0.0020       # 0.2%
SLIPPAGE_RATE = 0.001   # 0.1%

# 전략 B 최적 파라미터
RSI_WINDOW = 5
BUY_THRESHOLD = 35
SELL_THRESHOLD = 70
SMA_WINDOW = 50
MAX_HOLDING_DAYS = 60
LOSS_COOLDOWN_DAYS = 60

# ---------------------------------------------------------
# 데이터 준비 함수
# ---------------------------------------------------------
def get_kosdaq150_tickers():
    """Load KOSDAQ 150 tickers from local file."""
    filename = 'data/kosdaq150_list.txt'
    tickers = []
    try:
        import ast
        if not os.path.exists(filename):
            print(f"[오류] {filename} 파일이 없습니다.")
            return []

        print(f"'{filename}'에서 종목 리스트를 읽어옵니다...")
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                if line.endswith(','): line = line[:-1]
                try:
                    data = ast.literal_eval(line)
                    tickers.append(data['code'] + '.KQ')
                except:
                    pass

        print(f"총 {len(tickers)}개 종목 로드 완료.")
        return tickers

    except Exception as e:
        print(f"[오류] 파일 읽기 오류: {e}")
        return []

def get_kosdaq150_ticker_map():
    """Load ticker to name mapping."""
    filename = 'data/kosdaq150_list.txt'
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

def calculate_rsi(data, window):
    """Calculate RSI indicator."""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def prepare_data(tickers, start_date, rsi_window, sma_window):
    """Download and prepare stock data with indicators."""
    if isinstance(start_date, str):
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_dt = start_date

    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")

    print(f"\n[{len(tickers)}개 종목] 데이터 다운로드 ({fetch_start_date}~)...")
    data = yf.download(tickers, start=fetch_start_date, progress=True)

    stock_data = {}
    valid_tickers = []

    if isinstance(data.columns, pd.MultiIndex):
        try:
            closes = data.xs('Close', axis=1, level=0)
        except:
            if 'Close' in data.columns.get_level_values(0):
                closes = data['Close']
            else:
                return {}, []
    else:
        closes = data['Close'] if 'Close' in data.columns else data

    print("\n지표 계산 중...")
    for ticker in tickers:
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()

            if len(series) < sma_window + 10: continue

            df = series.to_frame(name='Close')
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)

            df = df[df.index >= start_dt]
            df.dropna(inplace=True)

            if not df.empty:
                stock_data[ticker] = df
                valid_tickers.append(ticker)
        except:
            pass

    print(f"유효 종목 수: {len(valid_tickers)}개")
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 상세 시뮬레이션 엔진 (최적 파라미터 적용)
# ---------------------------------------------------------
def run_detailed_simulation(stock_data, valid_tickers):
    """Run simulation with optimized parameters and return detailed trade information."""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    detailed_trades = []
    loss_cooldown_tracker = {}

    print(f"\n시뮬레이션 시작 (총 {len(all_dates)}일)")

    for idx, date in enumerate(all_dates):
        if idx % 500 == 0:
            print(f"진행률: {idx}/{len(all_dates)} ({idx/len(all_dates)*100:.1f}%)")

        # 1. 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']
                holding_days = (date - pos['buy_date']).days

                # 매도 조건: RSI > 70 OR 보유일수 >= 60일
                if rsi > SELL_THRESHOLD or holding_days >= MAX_HOLDING_DAYS:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']

            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})

        # 매도 실행 및 상세 정보 저장
        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']
            sell_rsi = stock_data[ticker].loc[date, 'RSI']

            # 매도 금액 및 비용
            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)

            # 매수 총 비용
            buy_total_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)

            # 손익 계산
            net_pnl = (sell_amt - cost) - buy_total_cost
            net_return = (net_pnl / buy_total_cost) * 100

            # 보유 기간
            holding_days = (date - pos['buy_date']).days

            # 상세 거래 정보 저장
            detailed_trades.append({
                'Ticker': ticker,
                'BuyDate': pos['buy_date'],
                'SellDate': date,
                'BuyPrice': pos['buy_price'],
                'SellPrice': sell_price,
                'Shares': pos['shares'],
                'BuyRSI': pos['buy_rsi'],
                'SellRSI': sell_rsi,
                'PnL_Amount': net_pnl,
                'PnL_Pct': net_return,
                'HoldingDays': holding_days
            })

            # 손실 쿨다운 추적
            if net_return < 0:
                loss_cooldown_tracker[ticker] = date

        # 2. 매수 (쿨다운 체크 포함)
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue

                # 쿨다운 체크
                if ticker in loss_cooldown_tracker:
                    last_loss_date = loss_cooldown_tracker[ticker]
                    days_since_loss = (date - last_loss_date).days
                    if days_since_loss < LOSS_COOLDOWN_DAYS:
                        continue

                df = stock_data[ticker]
                if date not in df.index: continue

                row = df.loc[date]
                # 매수 조건: Close > SMA & RSI < BUY_THRESHOLD (35)
                if row['Close'] > row['SMA'] and row['RSI'] < BUY_THRESHOLD:
                    buy_candidates.append({
                        'ticker': ticker,
                        'rsi': row['RSI'],
                        'price': row['Close']
                    })

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
                            'shares': shares,
                            'buy_price': candidate['price'],
                            'buy_date': date,
                            'buy_rsi': candidate['rsi'],
                            'last_price': candidate['price']
                        }

    print("\n시뮬레이션 완료!")

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(detailed_trades)

    return hist_df, trades_df

# ---------------------------------------------------------
# 수익 거래 분석
# ---------------------------------------------------------
def analyze_profits(trades_df, ticker_map):
    """Analyze profitable trades and identify patterns."""

    # 수익 거래만 필터링
    profits = trades_df[trades_df['PnL_Pct'] > 0].copy()

    if profits.empty:
        print("수익 거래가 없습니다!")
        return None

    print(f"\n총 수익 거래 수: {len(profits)}개")
    print(f"총 수익액: {profits['PnL_Amount'].sum():,.0f}원")

    # 수익률 기준으로 정렬
    profits_sorted = profits.sort_values('PnL_Pct', ascending=False)

    # 상위 200개 추출
    top_200 = profits_sorted.head(200).copy()

    # 종목명 추가
    top_200['Name'] = top_200['Ticker'].map(ticker_map)

    # 연도 정보 추가
    top_200['BuyYear'] = pd.to_datetime(top_200['BuyDate']).dt.year
    top_200['SellYear'] = pd.to_datetime(top_200['SellDate']).dt.year

    return top_200, profits

def generate_profit_report(top_200, profits):
    """Generate detailed profit analysis report."""

    report = f"""# 전략 B (RSI 5, SMA 50, 보유 60일, 쿨다운 60일) 수익률 상위 거래 분석

**분석 기준:** 수익률 (%) 기준 상위 200개
**분석 기간:** 2005-01-01 ~ 현재
**분석 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. 수익 거래 요약

- **전체 수익 거래 수:** {len(profits):,}개
- **총 수익액:** {profits['PnL_Amount'].sum():,.0f}원
- **평균 수익액:** {profits['PnL_Amount'].mean():,.0f}원
- **평균 수익률:** {profits['PnL_Pct'].mean():.2f}%
- **최대 수익액:** {profits['PnL_Amount'].max():,.0f}원
- **최대 수익률:** {profits['PnL_Pct'].max():.2f}%

## 2. 수익 상위 200개 거래

| 순위 | 매수일 | 매도일 | 종목명 | 코드 | 매수가 | 매도가 | 수익액 | 수익률 | 보유일수 |
| :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | ---: |
"""

    for idx, (_, row) in enumerate(top_200.iterrows(), 1):
        buy_date = pd.to_datetime(row['BuyDate']).strftime('%Y-%m-%d')
        sell_date = pd.to_datetime(row['SellDate']).strftime('%Y-%m-%d')
        name = row['Name'] if pd.notna(row['Name']) else row['Ticker']

        report += f"| {idx} | {buy_date} | {sell_date} | {name} | {row['Ticker']} "
        report += f"| {row['BuyPrice']:,.0f} | {row['SellPrice']:,.0f} "
        report += f"| {row['PnL_Amount']:,.0f} | {row['PnL_Pct']:.2f}% | {row['HoldingDays']}일 |\n"

    # 패턴 분석
    report += "\n\n## 3. 수익 거래 패턴 분석\n\n"

    # 3.1 연도별 분포
    report += "### 3.1 연도별 수익 거래 분포 (상위 200개)\n\n"
    year_dist = top_200['SellYear'].value_counts().sort_index()
    report += "| 연도 | 거래 수 | 비율 |\n| :--- | ---: | ---: |\n"
    for year, count in year_dist.items():
        report += f"| {year} | {count}개 | {count/len(top_200)*100:.1f}% |\n"

    # 3.2 보유 기간 분석
    report += "\n### 3.2 보유 기간 분석 (상위 200개)\n\n"
    report += f"- **평균 보유 기간:** {top_200['HoldingDays'].mean():.1f}일\n"
    report += f"- **최소 보유 기간:** {top_200['HoldingDays'].min()}일\n"
    report += f"- **최대 보유 기간:** {top_200['HoldingDays'].max()}일\n"
    report += f"- **중앙값:** {top_200['HoldingDays'].median():.1f}일\n\n"

    # 보유 기간 구간별 분포
    bins = [0, 10, 20, 30, 40, 50, 60, 999]
    labels = ['0-10일', '11-20일', '21-30일', '31-40일', '41-50일', '51-60일', '60일(상한)']
    top_200['HoldingRange'] = pd.cut(top_200['HoldingDays'], bins=bins, labels=labels, right=False)
    holding_dist = top_200['HoldingRange'].value_counts().sort_index()

    report += "**보유 기간 구간별 분포:**\n\n"
    report += "| 구간 | 거래 수 | 비율 |\n| :--- | ---: | ---: |\n"
    for range_name, count in holding_dist.items():
        report += f"| {range_name} | {count}개 | {count/len(top_200)*100:.1f}% |\n"

    # 3.3 수익률 분포
    report += "\n### 3.3 수익률 분포 (상위 200개)\n\n"
    report += f"- **평균 수익률:** {top_200['PnL_Pct'].mean():.2f}%\n"
    report += f"- **최대 수익률:** {top_200['PnL_Pct'].max():.2f}%\n"
    report += f"- **중앙값:** {top_200['PnL_Pct'].median():.2f}%\n\n"

    # 수익률 구간별 분포
    profit_bins = [0, 10, 20, 30, 40, 50, 100, 1000]
    profit_labels = ['0-10%', '10-20%', '20-30%', '30-40%', '40-50%', '50-100%', '100%+']
    top_200['ProfitRange'] = pd.cut(top_200['PnL_Pct'], bins=profit_bins, labels=profit_labels, right=False)
    profit_dist = top_200['ProfitRange'].value_counts().sort_index()

    report += "**수익률 구간별 분포:**\n\n"
    report += "| 구간 | 거래 수 | 비율 |\n| :--- | ---: | ---: |\n"
    for range_name, count in profit_dist.items():
        report += f"| {range_name} | {count}개 | {count/len(top_200)*100:.1f}% |\n"

    # 3.4 매수 시 RSI 분석
    report += "\n### 3.4 매수 시 RSI 분석 (상위 200개)\n\n"
    report += f"- **평균 매수 RSI:** {top_200['BuyRSI'].mean():.2f}\n"
    report += f"- **최소 매수 RSI:** {top_200['BuyRSI'].min():.2f}\n"
    report += f"- **최대 매수 RSI:** {top_200['BuyRSI'].max():.2f}\n"
    report += f"- **중앙값:** {top_200['BuyRSI'].median():.2f}\n\n"

    # RSI 구간별 분포
    rsi_bins = [0, 15, 20, 25, 30, 35]
    rsi_labels = ['0-15', '15-20', '20-25', '25-30', '30-35']
    top_200['RSIRange'] = pd.cut(top_200['BuyRSI'], bins=rsi_bins, labels=rsi_labels, right=False)
    rsi_dist = top_200['RSIRange'].value_counts().sort_index()

    report += "**매수 RSI 구간별 분포:**\n\n"
    report += "| RSI 구간 | 거래 수 | 비율 |\n| :--- | ---: | ---: |\n"
    for range_name, count in rsi_dist.items():
        report += f"| {range_name} | {count}개 | {count/len(top_200)*100:.1f}% |\n"

    # 3.5 반복 수익 종목
    report += "\n### 3.5 반복 수익 종목 (상위 200개 내 2회 이상)\n\n"
    ticker_counts = top_200['Ticker'].value_counts()
    repeat_profits = ticker_counts[ticker_counts >= 2]

    if len(repeat_profits) > 0:
        report += "| 종목명 | 코드 | 수익 횟수 | 총 수익액 | 평균 수익률 |\n| :--- | :--- | ---: | ---: | ---: |\n"
        for ticker, count in repeat_profits.head(20).items():
            ticker_data = top_200[top_200['Ticker'] == ticker]
            name = ticker_data.iloc[0]['Name']
            total_profit = ticker_data['PnL_Amount'].sum()
            avg_profit_pct = ticker_data['PnL_Pct'].mean()
            report += f"| {name} | {ticker} | {count}회 | {total_profit:,.0f}원 | {avg_profit_pct:.2f}% |\n"
    else:
        report += "반복 수익 종목 없음\n"

    # 3.6 주요 특징 요약
    report += "\n\n## 4. 주요 특징 요약\n\n"

    # 가장 수익이 많았던 연도
    year_profits = top_200.groupby('SellYear')['PnL_Amount'].sum().sort_values(ascending=False)
    best_year = year_profits.index[0]
    best_year_profit = year_profits.iloc[0]

    report += f"1. **가장 수익이 많았던 연도:** {best_year}년 (총 {best_year_profit:,.0f}원)\n"

    # 평균 보유 기간
    avg_holding = top_200['HoldingDays'].mean()
    report += f"2. **평균 보유 기간:** {avg_holding:.1f}일\n"

    # 60일 상한 도달 비율
    max_holding_count = len(top_200[top_200['HoldingDays'] >= 60])
    max_holding_pct = max_holding_count / len(top_200) * 100
    report += f"3. **60일 상한 도달:** {max_holding_count}개 ({max_holding_pct:.1f}%) - RSI 70 도달 전 강제 매도\n"

    # 수익률 분포
    avg_profit_pct = top_200['PnL_Pct'].mean()
    report += f"4. **평균 수익률:** {avg_profit_pct:.2f}%\n"

    # RSI 매수 시점
    avg_buy_rsi = top_200['BuyRSI'].mean()
    report += f"5. **평균 매수 시점 RSI:** {avg_buy_rsi:.2f} (기준: 35 미만)\n"

    # 반복 수익 종목
    if len(repeat_profits) > 0:
        report += f"6. **반복 수익:** {len(repeat_profits)}개 종목이 2회 이상 큰 수익 기록\n"
    else:
        report += "6. **반복 수익:** 없음\n"

    # 성공 패턴 인사이트
    report += "\n\n## 5. 성공 패턴 인사이트\n\n"

    # 극단적 과매도에서 매수한 경우
    very_low_rsi = top_200[top_200['BuyRSI'] < 20]
    if len(very_low_rsi) > 0:
        report += f"### 극단적 과매도 매수 (RSI < 20)\n"
        report += f"- 거래 수: {len(very_low_rsi)}개 ({len(very_low_rsi)/len(top_200)*100:.1f}%)\n"
        report += f"- 평균 수익률: {very_low_rsi['PnL_Pct'].mean():.2f}%\n"
        report += f"- 평균 보유일: {very_low_rsi['HoldingDays'].mean():.1f}일\n\n"

    # 빠른 수익 실현 (보유 20일 이하)
    quick_profit = top_200[top_200['HoldingDays'] <= 20]
    if len(quick_profit) > 0:
        report += f"### 빠른 수익 실현 (≤20일)\n"
        report += f"- 거래 수: {len(quick_profit)}개 ({len(quick_profit)/len(top_200)*100:.1f}%)\n"
        report += f"- 평균 수익률: {quick_profit['PnL_Pct'].mean():.2f}%\n"
        report += f"- 평균 보유일: {quick_profit['HoldingDays'].mean():.1f}일\n\n"

    # 장기 보유 후 수익 (보유 40일 이상)
    long_hold = top_200[top_200['HoldingDays'] >= 40]
    if len(long_hold) > 0:
        report += f"### 장기 보유 수익 (≥40일)\n"
        report += f"- 거래 수: {len(long_hold)}개 ({len(long_hold)/len(top_200)*100:.1f}%)\n"
        report += f"- 평균 수익률: {long_hold['PnL_Pct'].mean():.2f}%\n"
        report += f"- 평균 보유일: {long_hold['HoldingDays'].mean():.1f}일\n\n"

    return report

# ---------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------
def main():
    print("=" * 60)
    print("전략 B (최적 파라미터) 수익률 상위 거래 분석")
    print("=" * 60)

    # 1. 데이터 준비
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("종목 리스트 로드 실패")
        return

    ticker_map = get_kosdaq150_ticker_map()

    # 2. 백테스트 실행
    print(f"\n전략 B 백테스트 시작 (기간: {START_DATE} ~ 현재)")
    print(f"파라미터: RSI {RSI_WINDOW}, SMA {SMA_WINDOW}, 보유 {MAX_HOLDING_DAYS}일, 쿨다운 {LOSS_COOLDOWN_DAYS}일")
    stock_data, valid_tickers = prepare_data(tickers, START_DATE, RSI_WINDOW, SMA_WINDOW)

    if not stock_data:
        print("데이터 준비 실패")
        return

    hist_df, trades_df = run_detailed_simulation(stock_data, valid_tickers)

    if trades_df.empty:
        print("거래 내역이 없습니다")
        return

    print(f"\n총 거래 수: {len(trades_df)}개")

    # 3. 수익 거래 분석
    print("\n수익 거래 분석 중...")
    top_200, all_profits = analyze_profits(trades_df, ticker_map)

    if top_200 is None:
        return

    # 4. 보고서 생성
    print("\n보고서 생성 중...")
    report = generate_profit_report(top_200, all_profits)

    # 5. 파일 저장
    output_file = "reports/strategy_b_profit_by_pct_analysis.md"
    os.makedirs("reports", exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # CSV 파일도 저장
    csv_file = "reports/strategy_b_top_200_profits_by_pct.csv"
    top_200_export = top_200[[
        'BuyDate', 'SellDate', 'Name', 'Ticker',
        'BuyPrice', 'SellPrice', 'Shares',
        'PnL_Amount', 'PnL_Pct', 'HoldingDays',
        'BuyRSI', 'SellRSI'
    ]].copy()
    top_200_export.to_csv(csv_file, index=False, encoding='utf-8-sig')

    print(f"\n✅ 분석 완료!")
    print(f"📄 보고서: {output_file}")
    print(f"📊 CSV: {csv_file}")
    print(f"\n수익률 상위 10개 거래:")
    print("-" * 80)
    for idx, (_, row) in enumerate(top_200.head(10).iterrows(), 1):
        print(f"{idx}. {row['Name']} ({row['Ticker']})")
        print(f"   매수: {pd.to_datetime(row['BuyDate']).strftime('%Y-%m-%d')} ({row['BuyPrice']:,.0f}원)")
        print(f"   매도: {pd.to_datetime(row['SellDate']).strftime('%Y-%m-%d')} ({row['SellPrice']:,.0f}원)")
        print(f"   수익률: +{row['PnL_Pct']:.2f}% ({row['PnL_Amount']:,.0f}원) / {row['HoldingDays']}일 보유")
        print()

if __name__ == "__main__":
    main()
