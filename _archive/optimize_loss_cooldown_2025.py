"""
전략 B 손실 쿨다운 최적화 (2025년도만)
- 최신 시장 환경에서의 성과 측정
- RSI 5, SMA 50, 보유 60일 고정
- 쿨다운 기간 0~180일 테스트
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ---------------------------------------------------------
# 전략 설정
# ---------------------------------------------------------
START_DATE = '2025-01-01'  # 2025년도만
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

RSI_WINDOW = 5
BUY_THRESHOLD = 35
SELL_THRESHOLD = 70
SMA_WINDOW = 50
MAX_HOLDING_DAYS = 60

# 테스트할 쿨다운 기간 (일)
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

    # SMA 계산을 위해 충분한 과거 데이터 필요
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

            # 2025년 데이터만 필터링 (지표 계산은 과거 데이터 포함)
            df_2025 = df[df.index >= start_dt].copy()
            df_2025.dropna(inplace=True)

            if not df_2025.empty:
                stock_data[ticker] = df_2025
                valid_tickers.append(ticker)
        except:
            pass

    print(f"유효 종목 수: {len(valid_tickers)}개")
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 시뮬레이션 엔진
# ---------------------------------------------------------
def run_simulation_with_loss_cooldown(stock_data, valid_tickers, cooldown_days):
    """Run simulation with loss cooldown period."""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    loss_cooldown_tracker = {}  # {ticker: sell_date}

    for date in all_dates:
        # 1. 쿨다운 만료 체크
        expired_tickers = []
        for ticker, sell_date in loss_cooldown_tracker.items():
            if (date - sell_date).days >= cooldown_days:
                expired_tickers.append(ticker)
        for ticker in expired_tickers:
            del loss_cooldown_tracker[ticker]

        # 2. 평가 및 매도
        current_positions_value = 0
        tickers_to_sell = []

        for ticker, pos in positions.items():
            df = stock_data[ticker]
            if date in df.index:
                current_price = df.loc[date, 'Close']
                pos['last_price'] = current_price
                rsi = df.loc[date, 'RSI']

                holding_days = (date - pos['buy_date']).days

                if rsi > SELL_THRESHOLD or holding_days >= MAX_HOLDING_DAYS:
                    tickers_to_sell.append(ticker)
            else:
                current_price = pos['last_price']

            current_positions_value += pos['shares'] * current_price

        total_equity = cash + current_positions_value

        # 매도 실행
        for ticker in tickers_to_sell:
            pos = positions.pop(ticker)
            sell_price = stock_data[ticker].loc[date, 'Close']

            sell_amt = pos['shares'] * sell_price
            cost = sell_amt * (TX_FEE_RATE + TAX_RATE + SLIPPAGE_RATE)
            cash += (sell_amt - cost)

            buy_total_cost = (pos['shares'] * pos['buy_price']) * (1 + TX_FEE_RATE + SLIPPAGE_RATE)
            net_pnl = (sell_amt - cost) - buy_total_cost
            net_return = (net_pnl / buy_total_cost) * 100

            holding_days = (date - pos['buy_date']).days

            trades.append({
                'Ticker': ticker,
                'BuyDate': pos['buy_date'],
                'SellDate': date,
                'Return': net_return,
                'HoldingDays': holding_days
            })

            # 손실인 경우 쿨다운 추가
            if net_return < 0 and cooldown_days > 0:
                loss_cooldown_tracker[ticker] = date

        # 3. 매수
        open_slots = MAX_POSITIONS - len(positions)
        if open_slots > 0:
            buy_candidates = []
            for ticker in valid_tickers:
                if ticker in positions: continue
                if ticker in loss_cooldown_tracker: continue

                df = stock_data[ticker]
                if date not in df.index: continue

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
    final_equity = cash + sum(pos['shares'] * pos['last_price'] for pos in positions.values())
    total_return = ((final_equity / INITIAL_CAPITAL) - 1) * 100

    trades_df = pd.DataFrame(trades)

    # MDD 계산 (일별 equity 추적 필요하지만 간소화)
    mdd = 0  # 2025년만으로는 의미 있는 MDD 계산 어려움

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

        if not losses.empty:
            loss_counts = losses['Ticker'].value_counts()
            repeat_loss_count = len(loss_counts[loss_counts >= 2])

    return total_return, win_rate, len(trades_df), avg_holding, avg_win, avg_loss, repeat_loss_count

# ---------------------------------------------------------
# 최적화 실행
# ---------------------------------------------------------
def run_optimization():
    print("=" * 70)
    print("전략 B 손실 쿨다운 최적화 (2025년도만)")
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
        print(f"\n테스트 중: 쿨다운 = {label}")

        total_ret, win_rate, trades, avg_hold, avg_win, avg_loss, repeat_loss = \
            run_simulation_with_loss_cooldown(stock_data, valid_tickers, cooldown_days)

        results.append({
            'CooldownDays': cooldown_days,
            'Label': label,
            'Return': total_ret,
            'WinRate': win_rate,
            'Trades': trades,
            'AvgHoldingDays': avg_hold,
            'AvgWin': avg_win,
            'AvgLoss': avg_loss,
            'RepeatLossStocks': repeat_loss
        })

        print(f"  수익률: {total_ret:.2f}%")
        print(f"  승률: {win_rate:.2f}%, 거래: {trades}회, 반복손실: {repeat_loss}개")

    # 결과를 DataFrame으로 변환
    results_df = pd.DataFrame(results)

    # 보고서 생성
    report = f"""# 전략 B 손실 쿨다운 최적화 (2025년도)

**분석 기간:** 2025-01-01 ~ 현재
**분석 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**고정 파라미터:** RSI 5, SMA 50, 최대 보유 60일

## 1. 테스트 개요

**2025년도 데이터만 사용:**
- 최신 시장 환경에서의 성과 측정
- 과거 데이터 편향 제거
- Out-of-sample 테스트 효과

**테스트한 쿨다운 기간:** {', '.join([f"{d}일" if d > 0 else "없음" for d in COOLDOWN_DAYS_TO_TEST])}

## 2. 성과 비교표

| 쿨다운기간 | 수익률 | 승률 | 거래횟수 | 평균보유일 | 평균수익 | 평균손실 | 반복손실종목 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
"""

    for _, row in results_df.iterrows():
        report += f"| {row['Label']} | {row['Return']:.2f}% | {row['WinRate']:.2f}% | {row['Trades']}회 | {row['AvgHoldingDays']:.1f}일 | {row['AvgWin']:.2f}% | {row['AvgLoss']:.2f}% | {row['RepeatLossStocks']}개 |\n"

    # 최고 성과 지표
    best_return = results_df.loc[results_df['Return'].idxmax()]
    best_winrate = results_df.loc[results_df['WinRate'].idxmax()]
    min_repeat_loss = results_df.loc[results_df['RepeatLossStocks'].idxmin()]

    report += f"""
## 3. 주요 발견

### 3.1 최고 성과 지표

- **최고 수익률:** {best_return['Label']} - {best_return['Return']:.2f}%
- **최고 승률:** {best_winrate['Label']} - {best_winrate['WinRate']:.2f}%
- **최소 반복손실:** {min_repeat_loss['Label']} - {min_repeat_loss['RepeatLossStocks']}개

### 3.2 쿨다운 기간별 특징

"""

    # 쿨다운 없음
    no_cooldown = results_df[results_df['CooldownDays'] == 0].iloc[0]
    report += f"""**쿨다운 없음 (기준선):**
- 수익률: {no_cooldown['Return']:.2f}%
- 승률: {no_cooldown['WinRate']:.2f}%
- 거래: {no_cooldown['Trades']}회
- 반복 손실 종목: {no_cooldown['RepeatLossStocks']}개

"""

    # 그룹별 분석
    short_term = results_df[(results_df['CooldownDays'] > 0) & (results_df['CooldownDays'] <= 30)]
    mid_term = results_df[(results_df['CooldownDays'] > 30) & (results_df['CooldownDays'] <= 90)]
    long_term = results_df[results_df['CooldownDays'] > 90]

    if not short_term.empty:
        report += f"""**단기 쿨다운 (1-30일):**
- 평균 수익률: {short_term['Return'].mean():.2f}%
- 평균 승률: {short_term['WinRate'].mean():.2f}%
- 평균 반복 손실: {short_term['RepeatLossStocks'].mean():.1f}개

"""

    if not mid_term.empty:
        report += f"""**중기 쿨다운 (31-90일):**
- 평균 수익률: {mid_term['Return'].mean():.2f}%
- 평균 승률: {mid_term['WinRate'].mean():.2f}%
- 평균 반복 손실: {mid_term['RepeatLossStocks'].mean():.1f}개

"""

    if not long_term.empty:
        report += f"""**장기 쿨다운 (>90일):**
- 평균 수익률: {long_term['Return'].mean():.2f}%
- 평균 승률: {long_term['WinRate'].mean():.2f}%
- 평균 반복 손실: {long_term['RepeatLossStocks'].mean():.1f}개

"""

    # 상위 3개 권장사항
    top_3 = results_df.nlargest(3, 'Return')

    report += f"""## 4. 권장사항 (2025년 기준)

**수익률 기준 상위 3개:**
"""
    for idx, (_, row) in enumerate(top_3.iterrows(), 1):
        report += f"{idx}. {row['Label']}: 수익률 {row['Return']:.2f}%, 승률 {row['WinRate']:.2f}%, 반복손실 {row['RepeatLossStocks']}개\n"

    report += f"""
## 5. 결론

2025년도 데이터만으로 분석한 결과, 최신 시장 환경에서 최고 성과를 보인 설정은 **{best_return['Label']} (수익률 {best_return['Return']:.2f}%)**입니다.

**주의사항:**
- 1년 데이터만 사용하여 샘플 수가 적을 수 있음
- 전체 기간 분석 결과와 비교하여 종합 판단 필요
- 2025년 시장 특성이 반영된 결과임
"""

    # 파일 저장
    output_file = "reports/loss_cooldown_optimization_2025.md"
    os.makedirs("reports", exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # CSV도 저장
    csv_file = "reports/loss_cooldown_optimization_2025.csv"
    results_df.to_csv(csv_file, index=False, encoding='utf-8-sig')

    print(f"\n✅ 분석 완료!")
    print(f"📄 보고서: {output_file}")
    print(f"📊 CSV: {csv_file}")
    print(f"\n2025년 최고 수익률: {best_return['Label']} - {best_return['Return']:.2f}%")

if __name__ == "__main__":
    run_optimization()
