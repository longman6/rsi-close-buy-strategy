"""
전략 비교: 빠른 반등 종목 추가 보유 효과 검증

전략 A (기존): RSI > 70 도달 시 즉시 매도
전략 B (새로운): 3일 내 RSI 70 도달 시 3일 추가 보유 후 매도
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
LOSS_COOLDOWN_DAYS = 60

START_DATE = '2005-01-01'
END_DATE = '2025-12-31'

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

def prepare_data(tickers, start_date, end_date, rsi_window, sma_window):
    """Download and prepare stock data."""
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    # SMA 계산을 위해 충분한 과거 데이터 필요
    fetch_start_date = (start_dt - timedelta(days=200)).strftime("%Y-%m-%d")

    print(f"데이터 다운로드 중: {fetch_start_date} ~ {end_date}")
    data = yf.download(tickers, start=fetch_start_date, end=end_date, progress=True)

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
    for i, ticker in enumerate(tickers, 1):
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()

            if len(series) < sma_window + 10: continue

            df = series.to_frame(name='Close')
            df['SMA'] = df['Close'].rolling(window=sma_window).mean()
            df['RSI'] = calculate_rsi(df['Close'], window=rsi_window)

            # 분석 기간 데이터만 필터링
            df_period = df[df.index >= start_dt].copy()
            df_period.dropna(inplace=True)

            if not df_period.empty:
                stock_data[ticker] = df_period
                valid_tickers.append(ticker)

            if i % 10 == 0:
                print(f"  진행 중: {i}/{len(tickers)} 종목")
        except Exception as e:
            pass

    print(f"✅ 유효 종목: {len(valid_tickers)}개\n")
    return stock_data, valid_tickers

# ---------------------------------------------------------
# 전략 A: 기존 전략 (RSI 70 도달 시 즉시 매도)
# ---------------------------------------------------------
def run_strategy_a(stock_data, valid_tickers):
    """전략 A: RSI > 70 도달 시 즉시 매도"""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    if not all_dates:
        return 0, 0, 0, 0, 0, 0

    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    loss_cooldown_tracker = {}

    for date in all_dates:
        # 쿨다운 만료 체크
        expired_tickers = []
        for ticker, sell_date in loss_cooldown_tracker.items():
            if (date - sell_date).days >= LOSS_COOLDOWN_DAYS:
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

                # 전략 A 매도 조건: RSI > 70 OR 60일 경과
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

            if net_return < 0:
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
    avg_hold_days = 0
    repeat_loss_count = 0

    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        avg_hold_days = trades_df['HoldingDays'].mean()

        wins = trades_df[trades_df['Return'] > 0]
        losses = trades_df[trades_df['Return'] < 0]

        avg_win = wins['Return'].mean() if len(wins) > 0 else 0
        avg_loss = losses['Return'].mean() if len(losses) > 0 else 0

        if not losses.empty:
            loss_counts = losses['Ticker'].value_counts()
            repeat_loss_count = len(loss_counts[loss_counts >= 2])

    return total_return, win_rate, len(trades_df), avg_hold_days, avg_win, avg_loss, repeat_loss_count

# ---------------------------------------------------------
# 전략 B: 새로운 전략 (3일 내 RSI 70 도달 시 3일 추가 보유)
# ---------------------------------------------------------
def run_strategy_b(stock_data, valid_tickers):
    """전략 B: 3일 내 RSI 70 도달 시 3일 추가 보유 후 매도"""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    if not all_dates:
        return 0, 0, 0, 0, 0, 0, 0

    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    loss_cooldown_tracker = {}
    fast_bounce_count = 0  # 3일 내 RSI 70 도달 종목 수

    for date in all_dates:
        # 쿨다운 만료 체크
        expired_tickers = []
        for ticker, sell_date in loss_cooldown_tracker.items():
            if (date - sell_date).days >= LOSS_COOLDOWN_DAYS:
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

                # RSI 70 도달 시점 기록
                if rsi > SELL_THRESHOLD and pos['rsi_70_reached_date'] is None:
                    pos['rsi_70_reached_date'] = date
                    pos['days_to_rsi_70'] = holding_days

                # 전략 B 매도 조건
                if pos['rsi_70_reached_date'] is not None:
                    # RSI 70 도달한 경우
                    days_since_reached = (date - pos['rsi_70_reached_date']).days

                    if pos['days_to_rsi_70'] <= 3:
                        # 3일 내 도달 → 3일 추가 보유
                        if days_since_reached >= 3:
                            tickers_to_sell.append(ticker)
                    else:
                        # 4일 이상 걸림 → 즉시 매도
                        tickers_to_sell.append(ticker)
                elif holding_days >= MAX_HOLDING_DAYS:
                    # RSI 70 미도달 → 60일 경과 시
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

            # 빠른 반등 종목 카운트
            if pos['days_to_rsi_70'] is not None and pos['days_to_rsi_70'] <= 3:
                fast_bounce_count += 1

            trades.append({
                'Ticker': ticker,
                'Return': net_return,
                'HoldingDays': holding_days,
                'DaysToRSI70': pos['days_to_rsi_70']
            })

            if net_return < 0:
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
                            'last_price': candidate['price'],
                            'rsi_70_reached_date': None,
                            'days_to_rsi_70': None
                        }

    # 결과 정리
    final_equity = cash + sum(pos['shares'] * pos['last_price'] for pos in positions.values())
    total_return = ((final_equity / INITIAL_CAPITAL) - 1) * 100

    trades_df = pd.DataFrame(trades)

    win_rate = 0
    avg_win = 0
    avg_loss = 0
    avg_hold_days = 0
    repeat_loss_count = 0

    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100
        avg_hold_days = trades_df['HoldingDays'].mean()

        wins = trades_df[trades_df['Return'] > 0]
        losses = trades_df[trades_df['Return'] < 0]

        avg_win = wins['Return'].mean() if len(wins) > 0 else 0
        avg_loss = losses['Return'].mean() if len(losses) > 0 else 0

        if not losses.empty:
            loss_counts = losses['Ticker'].value_counts()
            repeat_loss_count = len(loss_counts[loss_counts >= 2])

    return total_return, win_rate, len(trades_df), avg_hold_days, avg_win, avg_loss, repeat_loss_count, fast_bounce_count

# ---------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------
def main():
    print("=" * 70)
    print("전략 비교: 빠른 반등 종목 추가 보유 효과 검증")
    print("=" * 70)
    print(f"분석 기간: {START_DATE} ~ {END_DATE}")
    print(f"초기 자본: {INITIAL_CAPITAL:,}원")
    print(f"손실 쿨다운: {LOSS_COOLDOWN_DAYS}일\n")

    # 데이터 준비
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("종목 리스트 로드 실패")
        return

    print(f"총 {len(tickers)}개 종목 로드 완료.\n")

    stock_data, valid_tickers = prepare_data(tickers, START_DATE, END_DATE, RSI_WINDOW, SMA_WINDOW)

    if not stock_data:
        print("데이터 준비 실패")
        return

    # 전략 A 실행
    print("=" * 70)
    print("전략 A 실행 중 (기존: RSI 70 도달 시 즉시 매도)")
    print("=" * 70)

    ret_a, wr_a, trades_a, hold_a, win_a, loss_a, repeat_a = run_strategy_a(stock_data, valid_tickers)

    print(f"\n✅ 전략 A 완료")
    print(f"  수익률: {ret_a:.2f}%")
    print(f"  승률: {wr_a:.2f}%")
    print(f"  거래 횟수: {trades_a}회")
    print(f"  평균 보유: {hold_a:.1f}일")
    print(f"  평균 승리: {win_a:.2f}%")
    print(f"  평균 손실: {loss_a:.2f}%")
    print(f"  반복 손실: {repeat_a}개\n")

    # 전략 B 실행
    print("=" * 70)
    print("전략 B 실행 중 (새로운: 3일 내 RSI 70 도달 시 3일 추가 보유)")
    print("=" * 70)

    ret_b, wr_b, trades_b, hold_b, win_b, loss_b, repeat_b, fast_b = run_strategy_b(stock_data, valid_tickers)

    print(f"\n✅ 전략 B 완료")
    print(f"  수익률: {ret_b:.2f}%")
    print(f"  승률: {wr_b:.2f}%")
    print(f"  거래 횟수: {trades_b}회")
    print(f"  평균 보유: {hold_b:.1f}일")
    print(f"  평균 승리: {win_b:.2f}%")
    print(f"  평균 손실: {loss_b:.2f}%")
    print(f"  반복 손실: {repeat_b}개")
    print(f"  빠른 반등: {fast_b}회 ({fast_b/trades_b*100:.1f}%)\n")

    # 비교 결과
    print("=" * 70)
    print("전략 비교 결과")
    print("=" * 70)

    comparison = pd.DataFrame({
        '전략': ['A (기존)', 'B (추가보유)'],
        '수익률 (%)': [ret_a, ret_b],
        '승률 (%)': [wr_a, wr_b],
        '거래횟수': [trades_a, trades_b],
        '평균보유일': [hold_a, hold_b],
        '평균승리 (%)': [win_a, win_b],
        '평균손실 (%)': [loss_a, loss_b],
        '반복손실': [repeat_a, repeat_b]
    })

    print(comparison.to_string(index=False))
    print()

    # 차이 분석
    ret_diff = ret_b - ret_a
    wr_diff = wr_b - wr_a

    print("=" * 70)
    print("차이 분석")
    print("=" * 70)
    print(f"수익률 차이: {ret_diff:+.2f}%p")
    print(f"승률 차이: {wr_diff:+.2f}%p")
    print(f"빠른 반등 비율: {fast_b}/{trades_b} ({fast_b/trades_b*100:.1f}%)\n")

    # 보고서 생성
    report = f"""# 빠른 반등 종목 추가 보유 전략 비교

**분석 기간:** {START_DATE} ~ {END_DATE}
**분석 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**초기 자본:** {INITIAL_CAPITAL:,}원
**고정 파라미터:** RSI {RSI_WINDOW}, SMA {SMA_WINDOW}, 최대 보유 {MAX_HOLDING_DAYS}일, 손실 쿨다운 {LOSS_COOLDOWN_DAYS}일

## 1. 전략 정의

### 전략 A (기존 전략)
- **매수:** RSI < {BUY_THRESHOLD}, Close > SMA({SMA_WINDOW})
- **매도:** RSI > {SELL_THRESHOLD} 도달 시 **즉시 매도** OR {MAX_HOLDING_DAYS}일 경과

### 전략 B (새로운 전략)
- **매수:** RSI < {BUY_THRESHOLD}, Close > SMA({SMA_WINDOW})
- **매도:**
  - 3일 내 RSI {SELL_THRESHOLD} 도달 시 → **3일 추가 보유 후 매도**
  - 4일 이상 걸려 RSI {SELL_THRESHOLD} 도달 시 → 즉시 매도
  - RSI {SELL_THRESHOLD} 미도달 시 → {MAX_HOLDING_DAYS}일 경과 시 매도

## 2. 성과 비교

| 전략 | 수익률 | 승률 | 거래횟수 | 평균보유일 | 평균승리 | 평균손실 | 반복손실 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A (기존) | {ret_a:.2f}% | {wr_a:.2f}% | {trades_a}회 | {hold_a:.1f}일 | {win_a:.2f}% | {loss_a:.2f}% | {repeat_a}개 |
| B (추가보유) | {ret_b:.2f}% | {wr_b:.2f}% | {trades_b}회 | {hold_b:.1f}일 | {win_b:.2f}% | {loss_b:.2f}% | {repeat_b}개 |

## 3. 차이 분석

- **수익률 차이:** {ret_diff:+.2f}%p
- **승률 차이:** {wr_diff:+.2f}%p
- **빠른 반등 비율:** {fast_b}/{trades_b}회 ({fast_b/trades_b*100:.1f}%)

## 4. 주요 발견

### 빠른 반등 패턴
전체 거래 중 **{fast_b/trades_b*100:.1f}%**가 3일 이내에 RSI {SELL_THRESHOLD}에 도달했습니다.

### 전략 효과
"""

    if ret_diff > 0:
        report += f"""
전략 B(추가 보유)가 전략 A(기존)보다 **{ret_diff:.2f}%p 높은 수익률**을 기록했습니다.
빠르게 반등하는 종목을 3일 더 보유하는 것이 수익 향상에 효과적입니다.
"""
    else:
        report += f"""
전략 A(기존)가 전략 B(추가 보유)보다 **{abs(ret_diff):.2f}%p 높은 수익률**을 기록했습니다.
빠르게 반등하는 종목을 즉시 매도하는 것이 더 효과적입니다.
"""

    report += f"""
## 5. 결론

"""

    if ret_diff > 5:
        report += f"""**전략 B(추가 보유) 권장**

- 수익률이 {ret_diff:.2f}%p 개선되었습니다.
- 빠른 반등 종목의 추가 상승 모멘텀을 포착하는 것이 효과적입니다.
- 3일 추가 보유 전략을 실전에 적용할 것을 권장합니다.
"""
    elif ret_diff < -5:
        report += f"""**전략 A(기존) 유지 권장**

- 수익률이 {abs(ret_diff):.2f}%p 감소했습니다.
- 빠른 반등 종목을 즉시 매도하는 것이 더 안전합니다.
- 기존 전략을 유지하는 것이 좋습니다.
"""
    else:
        report += f"""**전략 간 유의미한 차이 없음**

- 수익률 차이가 {abs(ret_diff):.2f}%p로 미미합니다.
- 두 전략 모두 유사한 성과를 보입니다.
- 개인 선호에 따라 선택 가능합니다.
"""

    # 파일 저장
    os.makedirs("reports", exist_ok=True)

    report_file = "reports/hold_extension_strategy.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    csv_file = "reports/hold_extension_comparison.csv"
    comparison.to_csv(csv_file, index=False, encoding='utf-8-sig')

    print(f"✅ 분석 완료!")
    print(f"📄 보고서: {report_file}")
    print(f"📊 비교표: {csv_file}")

if __name__ == "__main__":
    main()
