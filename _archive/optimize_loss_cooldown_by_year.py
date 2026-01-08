"""
전략 B 손실 쿨다운 최적화 (연도별 개별 분석)
- 각 연도를 독립적으로 분석하여 최적 쿨다운 발견
- 2005~2025년 각 연도별 최적값 비교
- RSI 5, SMA 50, 보유 60일 고정
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ---------------------------------------------------------
# 전략 설정
# ---------------------------------------------------------
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

def prepare_data_for_year(tickers, year, rsi_window, sma_window):
    """Download and prepare stock data for specific year."""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    # SMA 계산을 위해 충분한 과거 데이터 필요
    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")

    data = yf.download(tickers, start=fetch_start_date, end=end_date, progress=False)

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

    for ticker in tickers:
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()

            if len(series) < sma_window + 10: continue

            df = series.to_frame(name='Close')
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)

            # 해당 연도 데이터만 필터링
            df_year = df[df.index >= start_dt].copy()
            df_year.dropna(inplace=True)

            if not df_year.empty:
                stock_data[ticker] = df_year
                valid_tickers.append(ticker)
        except:
            pass

    return stock_data, valid_tickers

# ---------------------------------------------------------
# 시뮬레이션 엔진
# ---------------------------------------------------------
def run_simulation_with_loss_cooldown(stock_data, valid_tickers, cooldown_days):
    """Run simulation with loss cooldown period."""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    if not all_dates:
        return 0, 0, 0, 0, 0, 0, 0

    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    loss_cooldown_tracker = {}

    for date in all_dates:
        # 쿨다운 만료 체크
        expired_tickers = []
        for ticker, sell_date in loss_cooldown_tracker.items():
            if (date - sell_date).days >= cooldown_days:
                expired_tickers.append(ticker)
        for ticker in expired_tickers:
            del loss_cooldown_tracker[ticker]

        # 평가 및 매도
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
                'Return': net_return,
                'HoldingDays': holding_days
            })

            if net_return < 0 and cooldown_days > 0:
                loss_cooldown_tracker[ticker] = date

        # 매수
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

    win_rate = 0
    avg_win = 0
    avg_loss = 0
    repeat_loss_count = 0

    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100

        wins = trades_df[trades_df['Return'] > 0]
        losses = trades_df[trades_df['Return'] < 0]

        avg_win = wins['Return'].mean() if len(wins) > 0 else 0
        avg_loss = losses['Return'].mean() if len(losses) > 0 else 0

        if not losses.empty:
            loss_counts = losses['Ticker'].value_counts()
            repeat_loss_count = len(loss_counts[loss_counts >= 2])

    return total_return, win_rate, len(trades_df), avg_win, avg_loss, repeat_loss_count

# ---------------------------------------------------------
# 연도별 최적화 실행
# ---------------------------------------------------------
def run_yearly_optimization():
    print("=" * 70)
    print("전략 B 손실 쿨다운 최적화 (연도별 개별 분석)")
    print("=" * 70)

    # 데이터 준비
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("종목 리스트 로드 실패")
        return

    print(f"총 {len(tickers)}개 종목 로드 완료.\n")

    # 2005~2025년 각 연도 분석
    current_year = datetime.now().year
    years = range(2005, current_year + 1)

    yearly_results = []

    for year in years:
        print(f"\n{'='*70}")
        print(f"{year}년 분석 중...")
        print(f"{'='*70}")

        # 해당 연도 데이터 준비
        stock_data, valid_tickers = prepare_data_for_year(tickers, year, RSI_WINDOW, SMA_WINDOW)

        if not stock_data:
            print(f"{year}년 데이터 없음, 스킵")
            continue

        print(f"유효 종목 수: {len(valid_tickers)}개")

        # 각 쿨다운 기간별 테스트
        year_results = []

        for cooldown_days in COOLDOWN_DAYS_TO_TEST:
            total_ret, win_rate, trades, avg_win, avg_loss, repeat_loss = \
                run_simulation_with_loss_cooldown(stock_data, valid_tickers, cooldown_days)

            year_results.append({
                'Year': year,
                'CooldownDays': cooldown_days,
                'Return': total_ret,
                'WinRate': win_rate,
                'Trades': trades,
                'AvgWin': avg_win,
                'AvgLoss': avg_loss,
                'RepeatLoss': repeat_loss
            })

        # 해당 연도 최고 성과
        year_df = pd.DataFrame(year_results)
        if not year_df.empty and year_df['Return'].max() > -100:
            best = year_df.loc[year_df['Return'].idxmax()]
            print(f"\n{year}년 최적: {best['CooldownDays']}일 쿨다운 → 수익률 {best['Return']:.2f}%, 승률 {best['WinRate']:.2f}%, 거래 {best['Trades']}회")

            yearly_results.extend(year_results)
        else:
            print(f"{year}년 거래 없음")

    # 전체 결과 DataFrame
    all_results_df = pd.DataFrame(yearly_results)

    if all_results_df.empty:
        print("분석 결과 없음")
        return

    # 연도별 최적 쿨다운 요약
    print(f"\n{'='*70}")
    print("연도별 최적 쿨다운 요약")
    print(f"{'='*70}\n")

    yearly_best = []
    for year in years:
        year_data = all_results_df[all_results_df['Year'] == year]
        if not year_data.empty:
            best_idx = year_data['Return'].idxmax()
            best = year_data.loc[best_idx]
            yearly_best.append({
                'Year': year,
                'BestCooldown': best['CooldownDays'],
                'Return': best['Return'],
                'WinRate': best['WinRate'],
                'Trades': best['Trades']
            })
            print(f"{year}년: {int(best['CooldownDays'])}일 (수익률 {best['Return']:.2f}%, 승률 {best['WinRate']:.2f}%, 거래 {int(best['Trades'])}회)")

    yearly_best_df = pd.DataFrame(yearly_best)

    # 보고서 생성
    report = f"""# 전략 B 손실 쿨다운 최적화 (연도별 개별 분석)

**분석 기간:** 2005-2025년 (각 연도 독립)
**분석 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**고정 파라미터:** RSI 5, SMA 50, 최대 보유 60일

## 1. 연도별 최적 쿨다운

| 연도 | 최적 쿨다운 | 수익률 | 승률 | 거래횟수 |
| :--- | ---: | ---: | ---: | ---: |
"""

    for _, row in yearly_best_df.iterrows():
        report += f"| {int(row['Year'])} | {int(row['BestCooldown'])}일 | {row['Return']:.2f}% | {row['WinRate']:.2f}% | {int(row['Trades'])}회 |\n"

    # 쿨다운별 빈도 분석
    cooldown_freq = yearly_best_df['BestCooldown'].value_counts().sort_index()

    report += f"""
## 2. 최적 쿨다운 빈도

| 쿨다운 기간 | 최적으로 선정된 횟수 | 비율 |
| :--- | ---: | ---: |
"""

    for cooldown, count in cooldown_freq.items():
        pct = (count / len(yearly_best_df)) * 100
        report += f"| {int(cooldown)}일 | {int(count)}회 | {pct:.1f}% |\n"

    # 가장 많이 선정된 쿨다운
    most_common_cooldown = cooldown_freq.idxmax()
    most_common_count = cooldown_freq.max()

    report += f"""
## 3. 주요 발견

### 3.1 가장 안정적인 쿨다운

**{int(most_common_cooldown)}일 쿨다운**이 {int(most_common_count)}년({most_common_count/len(yearly_best_df)*100:.1f}%)에서 최적으로 선정되었습니다.

### 3.2 연도별 트렌드

"""

    # 초기, 중기, 후기로 나누어 분석
    early_years = yearly_best_df[yearly_best_df['Year'] <= 2010]
    mid_years = yearly_best_df[(yearly_best_df['Year'] > 2010) & (yearly_best_df['Year'] <= 2017)]
    recent_years = yearly_best_df[yearly_best_df['Year'] > 2017]

    if not early_years.empty:
        avg_cooldown_early = early_years['BestCooldown'].mean()
        report += f"**초기 (2005-2010):** 평균 최적 쿨다운 {avg_cooldown_early:.1f}일\n"

    if not mid_years.empty:
        avg_cooldown_mid = mid_years['BestCooldown'].mean()
        report += f"**중기 (2011-2017):** 평균 최적 쿨다운 {avg_cooldown_mid:.1f}일\n"

    if not recent_years.empty:
        avg_cooldown_recent = recent_years['BestCooldown'].mean()
        report += f"**후기 (2018-2025):** 평균 최적 쿨다운 {avg_cooldown_recent:.1f}일\n"

    # 평균 수익률
    avg_return_by_cooldown = all_results_df.groupby('CooldownDays')['Return'].mean().sort_values(ascending=False)

    report += f"""
### 3.3 전 기간 평균 성과 (쿨다운별)

| 쿨다운 | 평균 수익률 |
| :--- | ---: |
"""

    for cooldown, avg_ret in avg_return_by_cooldown.items():
        report += f"| {int(cooldown)}일 | {avg_ret:.2f}% |\n"

    best_avg_cooldown = avg_return_by_cooldown.idxmax()

    report += f"""
## 4. 결론

### 연도별 개별 분석 결과:

1. **가장 많이 선정:** {int(most_common_cooldown)}일 ({int(most_common_count)}년, {most_common_count/len(yearly_best_df)*100:.1f}%)
2. **전 기간 평균 최고:** {int(best_avg_cooldown)}일 (평균 {avg_return_by_cooldown.iloc[0]:.2f}%)
3. **최근 추세 (2018-2025):** 평균 {avg_cooldown_recent:.1f}일

### 권장사항:

연도별로 최적값이 다르지만, **{int(most_common_cooldown)}일 쿨다운**이 가장 안정적으로 좋은 성과를 보입니다.
"""

    # 파일 저장
    output_file = "reports/loss_cooldown_optimization_by_year.md"
    os.makedirs("reports", exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)

    # CSV도 저장
    csv_file_yearly = "reports/loss_cooldown_by_year_best.csv"
    yearly_best_df.to_csv(csv_file_yearly, index=False, encoding='utf-8-sig')

    csv_file_all = "reports/loss_cooldown_by_year_all.csv"
    all_results_df.to_csv(csv_file_all, index=False, encoding='utf-8-sig')

    print(f"\n✅ 분석 완료!")
    print(f"📄 보고서: {output_file}")
    print(f"📊 연도별 최적: {csv_file_yearly}")
    print(f"📊 전체 데이터: {csv_file_all}")
    print(f"\n가장 안정적인 쿨다운: {int(most_common_cooldown)}일 ({int(most_common_count)}년 선정)")

if __name__ == "__main__":
    run_yearly_optimization()
