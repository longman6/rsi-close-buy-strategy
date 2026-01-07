"""
Optuna를 사용한 전략 B 파라미터 최적화

최적화 파라미터:
- RSI_WINDOW: 3~20
- SMA_WINDOW: 20~200
- BUY_THRESHOLD: 20~40
- SELL_THRESHOLD: 60~80
- MAX_HOLDING_DAYS: 30~120
- LOSS_COOLDOWN_DAYS: 0~180

베이지안 최적화 (TPE 알고리즘)으로 효율적 탐색
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import pickle
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# ---------------------------------------------------------
# 전역 설정
# ---------------------------------------------------------
INITIAL_CAPITAL = 100000000
MAX_POSITIONS = 5
ALLOCATION_PER_STOCK = 0.20
TX_FEE_RATE = 0.00015
TAX_RATE = 0.0020
SLIPPAGE_RATE = 0.001

START_DATE = '2005-01-01'
END_DATE = '2025-12-31'

CACHE_DIR = 'data/cache'
os.makedirs(CACHE_DIR, exist_ok=True)

# ---------------------------------------------------------
# 데이터 캐싱 (최초 1회만 다운로드)
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

def load_or_download_data(tickers, start_date, end_date, max_rsi_window=20, max_sma_window=200):
    """데이터 캐싱: 최초 1회만 다운로드, 이후는 캐시 사용"""
    cache_file = f'{CACHE_DIR}/stock_data_{start_date}_{end_date}.pkl'

    if os.path.exists(cache_file):
        print(f"✅ 캐시에서 데이터 로드 중: {cache_file}")
        with open(cache_file, 'rb') as f:
            return pickle.load(f)

    print(f"📥 데이터 다운로드 중: {start_date} ~ {end_date}")
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    fetch_start_date = (start_dt - timedelta(days=300)).strftime("%Y-%m-%d")

    data = yf.download(tickers, start=fetch_start_date, end=end_date, progress=True)

    raw_stock_data = {}

    if isinstance(data.columns, pd.MultiIndex):
        try:
            closes = data.xs('Close', axis=1, level=0)
        except:
            if 'Close' in data.columns.get_level_values(0):
                closes = data['Close']
            else:
                return {}
    else:
        closes = data['Close'] if 'Close' in data.columns else data

    print("\n📊 기본 데이터 준비 중...")
    for i, ticker in enumerate(tickers, 1):
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()

            if len(series) < max_sma_window + 10: continue

            df = series.to_frame(name='Close')
            df_period = df[df.index >= start_dt].copy()

            if not df_period.empty:
                raw_stock_data[ticker] = df

            if i % 10 == 0:
                print(f"  진행 중: {i}/{len(tickers)} 종목")
        except Exception as e:
            pass

    print(f"✅ {len(raw_stock_data)}개 종목 데이터 준비 완료")

    # 캐시 저장
    with open(cache_file, 'wb') as f:
        pickle.dump(raw_stock_data, f)
    print(f"💾 캐시 저장 완료: {cache_file}\n")

    return raw_stock_data

def prepare_data_with_params(raw_stock_data, rsi_window, sma_window, start_date):
    """파라미터에 맞게 RSI/SMA 계산"""
    stock_data = {}
    valid_tickers = []
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    for ticker, df in raw_stock_data.items():
        try:
            df_copy = df.copy()
            df_copy['SMA'] = df_copy['Close'].rolling(window=sma_window).mean()
            df_copy['RSI'] = calculate_rsi(df_copy['Close'], window=rsi_window)

            df_period = df_copy[df_copy.index >= start_dt].copy()
            df_period.dropna(inplace=True)

            if not df_period.empty:
                stock_data[ticker] = df_period
                valid_tickers.append(ticker)
        except:
            pass

    return stock_data, valid_tickers

# ---------------------------------------------------------
# 백테스트 엔진
# ---------------------------------------------------------
def run_backtest(stock_data, valid_tickers, buy_threshold, sell_threshold,
                 max_holding_days, loss_cooldown_days):
    """백테스트 실행"""
    all_dates = sorted(list(set().union(*[df.index for df in stock_data.values()])))

    if not all_dates:
        return 0, 0, 0

    cash = INITIAL_CAPITAL
    positions = {}
    trades = []
    loss_cooldown_tracker = {}

    for date in all_dates:
        # 쿨다운 만료 체크
        expired_tickers = []
        for ticker, sell_date in loss_cooldown_tracker.items():
            if (date - sell_date).days >= loss_cooldown_days:
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

                if rsi > sell_threshold or holding_days >= max_holding_days:
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

            trades.append({'Return': net_return})

            if net_return < 0 and loss_cooldown_days > 0:
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
                if row['Close'] > row['SMA'] and row['RSI'] < buy_threshold:
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
    if not trades_df.empty:
        win_rate = len(trades_df[trades_df['Return'] > 0]) / len(trades_df) * 100

    return total_return, win_rate, len(trades_df)

# ---------------------------------------------------------
# Optuna Objective 함수
# ---------------------------------------------------------
# 전역 캐시 (모든 trial이 공유)
GLOBAL_RAW_DATA = None

def objective(trial):
    """Optuna objective 함수"""
    global GLOBAL_RAW_DATA

    # 파라미터 제안 (더 촘촘한 탐색)
    rsi_window = trial.suggest_int('rsi_window', 3, 20)
    sma_window = trial.suggest_int('sma_window', 20, 200, step=5)  # 10 → 5로 촘촘하게
    buy_threshold = trial.suggest_int('buy_threshold', 20, 40)
    sell_threshold = trial.suggest_int('sell_threshold', 60, 80)
    max_holding_days = trial.suggest_int('max_holding_days', 30, 120)  # step 제거 (1일 단위)
    loss_cooldown_days = trial.suggest_int('loss_cooldown_days', 0, 180, step=5)  # 10 → 5로 촘촘하게

    # 데이터 준비 (RSI/SMA 계산)
    stock_data, valid_tickers = prepare_data_with_params(
        GLOBAL_RAW_DATA, rsi_window, sma_window, START_DATE
    )

    if not stock_data:
        return 0

    # 백테스트 실행
    total_return, win_rate, trades = run_backtest(
        stock_data, valid_tickers,
        buy_threshold, sell_threshold,
        max_holding_days, loss_cooldown_days
    )

    # 로그 출력
    print(f"Trial {trial.number}: RSI={rsi_window}, SMA={sma_window}, "
          f"Buy={buy_threshold}, Sell={sell_threshold}, "
          f"Hold={max_holding_days}, Cool={loss_cooldown_days} "
          f"→ 수익률={total_return:.2f}%, 승률={win_rate:.2f}%, 거래={trades}회")

    return total_return

# ---------------------------------------------------------
# 메인 실행
# ---------------------------------------------------------
def main():
    global GLOBAL_RAW_DATA

    print("=" * 80)
    print("Optuna 파라미터 최적화 시작")
    print("=" * 80)
    print(f"분석 기간: {START_DATE} ~ {END_DATE}")
    print(f"초기 자본: {INITIAL_CAPITAL:,}원")
    print()

    # 1. 종목 로드
    tickers = get_kosdaq150_tickers()
    if not tickers:
        print("종목 리스트 로드 실패")
        return

    print(f"총 {len(tickers)}개 종목 로드 완료.\n")

    # 2. 데이터 캐싱 (최초 1회만 다운로드)
    GLOBAL_RAW_DATA = load_or_download_data(tickers, START_DATE, END_DATE)

    if not GLOBAL_RAW_DATA:
        print("데이터 준비 실패")
        return

    print(f"✅ {len(GLOBAL_RAW_DATA)}개 종목 준비 완료\n")

    # 3. Optuna Study 생성
    print("=" * 80)
    print("Optuna 최적화 설정")
    print("=" * 80)

    study = optuna.create_study(
        study_name='rsi_strategy_optimization',
        direction='maximize',
        sampler=TPESampler(seed=42),
        pruner=MedianPruner()
    )

    print("✅ Study 생성 완료")
    print(f"알고리즘: TPE (Tree-structured Parzen Estimator)")
    print(f"목표: 수익률 최대화")
    print()

    # 4. 최적화 실행
    n_trials = 2500  # 테스트 횟수 (더 촘촘하게)
    n_jobs = 32      # 병렬 처리 (32코어)

    print("=" * 80)
    print(f"최적화 실행: {n_trials} trials, {n_jobs} 병렬 처리")
    print("=" * 80)
    print("⏱️  예상 소요 시간: 3~4시간 (더 촘촘한 탐색)")
    print("💡 언제든 Ctrl+C로 중단 가능 (현재까지 결과 저장)")
    print("진행 상황을 실시간으로 확인하세요!\n")

    try:
        study.optimize(
            objective,
            n_trials=n_trials,
            n_jobs=n_jobs,
            show_progress_bar=True
        )
    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자 중단 - 현재까지 결과 저장 중...")

    # 5. 결과 출력
    print("\n" + "=" * 80)
    print("최적화 완료!")
    print("=" * 80)

    print(f"\n총 {len(study.trials)}개 trials 완료")
    print(f"최고 수익률: {study.best_value:.2f}%")
    print("\n최적 파라미터:")
    print("-" * 80)
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")

    # 6. 결과 저장
    os.makedirs("reports/optuna", exist_ok=True)

    # CSV 저장
    trials_df = study.trials_dataframe()
    csv_file = "reports/optuna/optimization_results.csv"
    trials_df.to_csv(csv_file, index=False, encoding='utf-8-sig')
    print(f"\n📊 전체 결과 저장: {csv_file}")

    # 최적 파라미터 저장
    best_params_file = "reports/optuna/best_params.txt"
    with open(best_params_file, 'w', encoding='utf-8') as f:
        f.write(f"최적화 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"분석 기간: {START_DATE} ~ {END_DATE}\n")
        f.write(f"총 trials: {len(study.trials)}\n")
        f.write(f"최고 수익률: {study.best_value:.2f}%\n\n")
        f.write("최적 파라미터:\n")
        for key, value in study.best_params.items():
            f.write(f"  {key} = {value}\n")

    print(f"📄 최적 파라미터 저장: {best_params_file}")

    # 7. 시각화
    print("\n📈 시각화 생성 중...")

    try:
        # 최적화 히스토리
        fig1 = optuna.visualization.plot_optimization_history(study)
        fig1.write_html("reports/optuna/optimization_history.html")
        print("  ✅ 최적화 히스토리: reports/optuna/optimization_history.html")

        # 파라미터 중요도
        fig2 = optuna.visualization.plot_param_importances(study)
        fig2.write_html("reports/optuna/param_importances.html")
        print("  ✅ 파라미터 중요도: reports/optuna/param_importances.html")

        # Parallel Coordinate Plot
        fig3 = optuna.visualization.plot_parallel_coordinate(study)
        fig3.write_html("reports/optuna/parallel_coordinate.html")
        print("  ✅ 병렬 좌표 플롯: reports/optuna/parallel_coordinate.html")

        # Contour Plot (상위 2개 파라미터)
        if len(study.best_params) >= 2:
            param_names = list(study.best_params.keys())[:2]
            fig4 = optuna.visualization.plot_contour(study, params=param_names)
            fig4.write_html("reports/optuna/contour_plot.html")
            print("  ✅ 등고선 플롯: reports/optuna/contour_plot.html")

    except Exception as e:
        print(f"  ⚠️ 시각화 오류: {e}")

    # 8. 마크다운 보고서 생성
    report = f"""# Optuna 파라미터 최적화 결과

**최적화 일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**분석 기간**: {START_DATE} ~ {END_DATE}
**초기 자본**: {INITIAL_CAPITAL:,}원
**총 Trials**: {len(study.trials)}개

## 최적 파라미터

| 파라미터 | 값 |
|---------|-----|
"""

    for key, value in study.best_params.items():
        report += f"| {key} | {value} |\n"

    report += f"""
## 성과

- **최고 수익률**: {study.best_value:.2f}%
- **평균 수익률 (상위 10%)**: {trials_df.nlargest(int(len(trials_df)*0.1), 'value')['value'].mean():.2f}%
- **평균 수익률 (전체)**: {trials_df['value'].mean():.2f}%

## 파라미터 탐색 범위 (촘촘한 탐색)

| 파라미터 | 최소 | 최대 | 간격 |
|---------|------|------|------|
| rsi_window | 3 | 20 | 1 |
| sma_window | 20 | 200 | 5 |
| buy_threshold | 20 | 40 | 1 |
| sell_threshold | 60 | 80 | 1 |
| max_holding_days | 30 | 120 | 1 |
| loss_cooldown_days | 0 | 180 | 5 |

## 시각화

- [최적화 히스토리](optimization_history.html)
- [파라미터 중요도](param_importances.html)
- [병렬 좌표 플롯](parallel_coordinate.html)
- [등고선 플롯](contour_plot.html)

## 다음 단계

1. 최적 파라미터로 백테스트 재실행 및 검증
2. 다른 기간(Out-of-sample)에서 성과 확인
3. 실전 적용 여부 결정
"""

    report_file = "reports/optuna/optimization_report.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n📄 최종 보고서: {report_file}")

    print("\n" + "=" * 80)
    print("✅ 모든 작업 완료!")
    print("=" * 80)
    print("\n브라우저에서 시각화를 확인하세요:")
    print("  file://" + os.path.abspath("reports/optuna/optimization_history.html"))

if __name__ == "__main__":
    main()
