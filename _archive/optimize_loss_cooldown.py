"""
전략 B (RSI 5, SMA 50, 최대 보유 60일) 손실 후 재진입 금지 기간 최적화
- 다양한 loss cooldown 기간으로 백테스트
- 반복 손실 방지 효과 분석
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ---------------------------------------------------------
# 전략 설정
# ---------------------------------------------------------
START_DATE = '2005-01-01'
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

# 전략 B 파라미터 (고정)
RSI_WINDOW = 5
BUY_THRESHOLD = 35
SELL_THRESHOLD = 70
SMA_WINDOW = 50
MAX_HOLDING_DAYS = 60  # 최적값으로 고정

# 테스트할 손실 후 재진입 금지 기간 (일)
COOLDOWN_DAYS_TO_TEST = [0, 10, 20, 30, 40, 60, 90, 120, 180]

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
    data = yf.download(tickers, start=fetch_start_date, progress=False)

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

    print("지표 계산 중...")
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
# 시뮬레이션 엔진 (손실 후 재진입 금지 기간 추가)
# ---------------------------------------------------------
def run_simulation_with_loss_cooldown(stock_data, valid_tickers, loss_cooldown_days):
    """
    Run simulation with loss cooldown period.

    매도 조건:
    1. RSI > 70
    2. 보유일수 >= 60일

    매수 제한:
    - 손실 매도 후 loss_cooldown_days 기간 동안 재진입 금지
    """
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    cash = INITIAL_CAPITAL
    positions = {}
    history = []
    trades = []

    # 손실 후 재진입 금지를 위한 딕셔너리 {ticker: last_loss_date}
    loss_cooldown_tracker = {}

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

                # 보유 기간 계산
                holding_days = (date - pos['buy_date']).days

                # 매도 조건: RSI > 70 OR 보유일수 >= 60일
                if rsi > SELL_THRESHOLD or holding_days >= MAX_HOLDING_DAYS:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']

            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value
        history.append({'Date': date, 'Equity': total_equity})

        # 매도 실행 및 손실 추적
        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']

            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)

            buy_total_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_return = ((sell_amt - cost) - buy_total_cost) / buy_total_cost * 100

            holding_days = (date - pos['buy_date']).days

            trades.append({
                'Ticker': ticker,
                'Return': net_return,
                'Date': date,
                'HoldingDays': holding_days
            })

            # 손실인 경우 쿨다운 추적
            if net_return < 0:
                loss_cooldown_tracker[ticker] = date

        # 2. 매수 (쿨다운 체크 포함)
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions:
                    continue

                # 쿨다운 체크: 손실 후 일정 기간 내라면 스킵
                if ticker in loss_cooldown_tracker:
                    last_loss_date = loss_cooldown_tracker[ticker]
                    days_since_loss = (date - last_loss_date).days
                    if days_since_loss < loss_cooldown_days:
                        continue  # 아직 쿨다운 기간 내

                df = stock_data[ticker]
                if date not in df.index:
                    continue

                row = df.loc[date]
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

                    if max_buy_amt < 10000:
                        continue
                    shares = int(max_buy_amt / candidate['price'])
                    if shares > 0:
                        buy_val = shares * candidate['price']
                        cash -= (buy_val + buy_val * (TX_FEE_RATE + SLIPPAGE_RATE))
                        positions[candidate['ticker']] = {
                            'shares': shares,
                            'buy_price': candidate['price'],
                            'buy_date': date,
                            'last_price': candidate['price']
                        }

    # 결과 정리
    hist_df = pd.DataFrame(history).set_index('Date')
    trades_df = pd.DataFrame(trades)

    if hist_df.empty:
        return 0, 0, 0, 0, 0, 0, 0, 0

    final_ret = (hist_df['Equity'].iloc[-1] / INITIAL_CAPITAL - 1) * 100
    peak = hist_df['Equity'].cummax()
    mdd = ((hist_df['Equity'] - peak) / peak).min() * 100

    win_rate = 0
    avg_holding = 0
    avg_win = 0
    avg_loss = 0
    repeat_loss_count = 0

    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        avg_holding = trades_df['HoldingDays'].mean()

        wins = trades_df[trades_df['Return'] > 0]
        losses = trades_df[trades_df['Return'] < 0]

        avg_win = wins['Return'].mean() if len(wins) > 0 else 0
        avg_loss = losses['Return'].mean() if len(losses) > 0 else 0

        # 반복 손실 계산 (2회 이상 손실 발생한 종목 수)
        if not losses.empty:
            loss_counts = losses['Ticker'].value_counts()
            repeat_loss_count = len(loss_counts[loss_counts >= 2])

    return final_ret, mdd, win_rate, len(trades_df), avg_holding, avg_win, avg_loss, repeat_loss_count

# ---------------------------------------------------------
# 최적화 실행
# ---------------------------------------------------------
def run_optimization():
    print("=" * 70)
    print("전략 B (RSI 5, SMA 50, 보유 60일) 손실 후 재진입 금지 기간 최적화")
    print("=" * 70)

    # 데이터 준비
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("종목 리스트 로드 실패")
        return

    stock_data, valid_tickers = prepare_data(tickers, START_DATE, RSI_WINDOW, SMA_WINDOW)

    if not stock_data:
        print("데이터 준비 실패")
        return

    # 각 쿨다운 기간별 백테스트
    results = []

    for cooldown_days in COOLDOWN_DAYS_TO_TEST:
        label = f"{cooldown_days}일" if cooldown_days > 0 else "없음"
        print(f"\n테스트 중: 손실 후 재진입 금지 기간 = {label}")

        ret, mdd, win_rate, trades, avg_hold, avg_win, avg_loss, repeat_loss = run_simulation_with_loss_cooldown(
            stock_data, valid_tickers, cooldown_days
        )

        results.append({
            'CooldownDays': cooldown_days,
            'Label': label,
            'Return': ret,
            'MDD': mdd,
            'WinRate': win_rate,
            'Trades': trades,
            'AvgHoldingDays': avg_hold,
            'AvgWin': avg_win,
            'AvgLoss': avg_loss,
            'RepeatLossStocks': repeat_loss
        })

        print(f"  수익률: {ret:.2f}%, MDD: {mdd:.2f}%, 승률: {win_rate:.2f}%")
        print(f"  거래: {trades}회, 반복손실종목: {repeat_loss}개")

    # 결과를 DataFrame으로 변환
    results_df = pd.DataFrame(results)

    # 보고서 생성
    report = generate_optimization_report(results_df)

    # 파일 저장
    output_file = "reports/loss_cooldown_optimization.md"
    os.makedirs("reports", exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # CSV 저장
    csv_file = "reports/loss_cooldown_optimization.csv"
    results_df.to_csv(csv_file, index=False, encoding='utf-8-sig')

    print(f"\n✅ 최적화 완료!")
    print(f"📄 보고서: {output_file}")
    print(f"📊 CSV: {csv_file}")

    # 최고 성과 출력
    best_return = results_df.loc[results_df['Return'].idxmax()]
    best_sharpe = results_df.copy()
    best_sharpe['Sharpe'] = best_sharpe['Return'] / abs(best_sharpe['MDD'])
    best_sharpe_row = best_sharpe.loc[best_sharpe['Sharpe'].idxmax()]

    print(f"\n🏆 최고 수익률: {best_return['Label']} ({best_return['Return']:.2f}%)")
    print(f"🏆 최고 샤프비율: {best_sharpe_row['Label']} (수익/MDD = {best_sharpe_row['Sharpe']:.2f})")

def generate_optimization_report(results_df):
    """Generate optimization report."""

    report = f"""# 전략 B 손실 후 재진입 금지 기간 최적화 분석

**분석 기간:** 2005-01-01 ~ 현재
**분석 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**고정 파라미터:** RSI 5, SMA 50, 최대 보유 60일

## 1. 테스트 개요

전략 B에서 **손실 매도 후 재진입 금지 기간**을 추가하여 반복 손실을 방지하는 효과를 분석했습니다.

**로직:**
- 손실(수익률 < 0) 매도 시 해당 종목을 기록
- 기록된 날짜로부터 N일 동안 해당 종목 매수 금지
- N일 경과 후 다시 매수 가능

테스트한 쿨다운 기간: {', '.join([f"{d}일" if d > 0 else "없음" for d in COOLDOWN_DAYS_TO_TEST])}

## 2. 성과 비교표

| 쿨다운기간 | 수익률 | MDD | 승률 | 거래횟수 | 평균보유일 | 평균수익 | 평균손실 | 반복손실종목 | 수익/MDD |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
"""

    for _, row in results_df.iterrows():
        sharpe = row['Return'] / abs(row['MDD']) if row['MDD'] != 0 else 0
        report += f"| {row['Label']} | {row['Return']:.2f}% | {row['MDD']:.2f}% "
        report += f"| {row['WinRate']:.2f}% | {row['Trades']}회 | {row['AvgHoldingDays']:.1f}일 "
        report += f"| {row['AvgWin']:.2f}% | {row['AvgLoss']:.2f}% | {row['RepeatLossStocks']}개 | {sharpe:.2f} |\n"

    # 최고 성과
    best_return = results_df.loc[results_df['Return'].idxmax()]
    best_win_rate = results_df.loc[results_df['WinRate'].idxmax()]
    results_df['Sharpe'] = results_df['Return'] / abs(results_df['MDD'])
    best_sharpe = results_df.loc[results_df['Sharpe'].idxmax()]
    min_repeat_loss = results_df.loc[results_df['RepeatLossStocks'].idxmin()]

    report += f"""
## 3. 주요 발견

### 3.1 최고 성과 지표

- **최고 수익률:** {best_return['Label']} - {best_return['Return']:.2f}%
- **최고 승률:** {best_win_rate['Label']} - {best_win_rate['WinRate']:.2f}%
- **최고 수익/MDD 비율:** {best_sharpe['Label']} - {best_sharpe['Sharpe']:.2f}
- **최소 반복손실:** {min_repeat_loss['Label']} - {min_repeat_loss['RepeatLossStocks']}개 종목

### 3.2 쿨다운 기간별 특징 분석

"""

    # 쿨다운 구간별 분석
    no_cooldown = results_df[results_df['CooldownDays'] == 0]
    short_cooldown = results_df[(results_df['CooldownDays'] > 0) & (results_df['CooldownDays'] <= 30)]
    mid_cooldown = results_df[(results_df['CooldownDays'] > 30) & (results_df['CooldownDays'] <= 90)]
    long_cooldown = results_df[results_df['CooldownDays'] > 90]

    if not no_cooldown.empty:
        report += f"**쿨다운 없음:**\n"
        report += f"- 수익률: {no_cooldown.iloc[0]['Return']:.2f}%\n"
        report += f"- 승률: {no_cooldown.iloc[0]['WinRate']:.2f}%\n"
        report += f"- 반복손실 종목: {no_cooldown.iloc[0]['RepeatLossStocks']}개\n\n"

    if not short_cooldown.empty:
        report += f"**단기 쿨다운 (1-30일):**\n"
        report += f"- 평균 수익률: {short_cooldown['Return'].mean():.2f}%\n"
        report += f"- 평균 승률: {short_cooldown['WinRate'].mean():.2f}%\n"
        report += f"- 평균 반복손실: {short_cooldown['RepeatLossStocks'].mean():.1f}개\n\n"

    if not mid_cooldown.empty:
        report += f"**중기 쿨다운 (31-90일):**\n"
        report += f"- 평균 수익률: {mid_cooldown['Return'].mean():.2f}%\n"
        report += f"- 평균 승률: {mid_cooldown['WinRate'].mean():.2f}%\n"
        report += f"- 평균 반복손실: {mid_cooldown['RepeatLossStocks'].mean():.1f}개\n\n"

    if not long_cooldown.empty:
        report += f"**장기 쿨다운 (>90일):**\n"
        report += f"- 평균 수익률: {long_cooldown['Return'].mean():.2f}%\n"
        report += f"- 평균 승률: {long_cooldown['WinRate'].mean():.2f}%\n"
        report += f"- 평균 반복손실: {long_cooldown['RepeatLossStocks'].mean():.1f}개\n\n"

    # 반복손실 감소 효과
    if not no_cooldown.empty:
        baseline_repeat = no_cooldown.iloc[0]['RepeatLossStocks']
        report += f"### 3.3 반복 손실 방지 효과\n\n"
        report += f"**기준 (쿨다운 없음): {baseline_repeat}개 종목에서 반복 손실**\n\n"

        for _, row in results_df[results_df['CooldownDays'] > 0].iterrows():
            reduction = baseline_repeat - row['RepeatLossStocks']
            reduction_pct = (reduction / baseline_repeat * 100) if baseline_repeat > 0 else 0
            report += f"- {row['Label']}: {row['RepeatLossStocks']}개 ({reduction}개 감소, -{reduction_pct:.1f}%)\n"

    # 권장사항
    report += f"""

## 4. 권장사항

"""

    # 수익률 기준 상위 3개
    top_3_return = results_df.nlargest(3, 'Return')
    report += "**수익률 기준 상위 3개 설정:**\n"
    for i, (_, row) in enumerate(top_3_return.iterrows(), 1):
        report += f"{i}. {row['Label']}: 수익률 {row['Return']:.2f}%, 반복손실 {row['RepeatLossStocks']}개\n"

    # 샤프비율 기준 상위 3개
    top_3_sharpe = results_df.nlargest(3, 'Sharpe')
    report += "\n**리스크 대비 수익 (수익/MDD) 기준 상위 3개:**\n"
    for i, (_, row) in enumerate(top_3_sharpe.iterrows(), 1):
        report += f"{i}. {row['Label']}: 비율 {row['Sharpe']:.2f}, 수익률 {row['Return']:.2f}%\n"

    report += """

## 5. 결론

손실 후 재진입 금지 기간을 통해 반복 손실을 방지하고 수익률을 개선할 수 있는지 확인했습니다.
너무 짧으면 반복 손실이 발생하고, 너무 길면 좋은 기회를 놓칠 수 있으므로 적절한 균형이 중요합니다.
"""

    return report

# ---------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------
if __name__ == "__main__":
    run_optimization()
