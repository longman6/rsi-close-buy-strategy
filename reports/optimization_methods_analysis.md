# 파라미터 최적화 방법 분석

**작성일**: 2026-01-07
**목적**: RSI 전략 파라미터를 촘촘하게 최적화하기 위한 방법 검토

## 시스템 환경

```
CPU: AMD Ryzen 9 7945HX (16코어 32쓰레드)
RAM: 30GB (13GB 사용 가능)
GPU: NVIDIA GeForce RTX 4060 (8GB VRAM)
```

**결론**: 멀티코어 병렬 처리와 GPU 가속 모두 사용 가능한 우수한 환경

---

## 최적화할 파라미터

### 현재 파라미터
```python
RSI_WINDOW = 5              # 범위: 3~20
SMA_WINDOW = 50             # 범위: 20~200
BUY_THRESHOLD = 35          # 범위: 20~40
SELL_THRESHOLD = 70         # 범위: 60~80
MAX_HOLDING_DAYS = 60       # 범위: 30~120
LOSS_COOLDOWN_DAYS = 60     # 범위: 0~180
```

### 탐색 공간 크기
- **현재 방식 (간격 10)**: 약 1,000~2,000 조합
- **촘촘한 방식 (간격 1)**: 약 **수백만 조합**

---

## 최적화 방법 비교

### 1. Grid Search (전수 조사) + Multiprocessing ⭐ 권장

**장점**:
- 모든 조합을 빠짐없이 테스트
- 결과의 확실성 보장
- 구현이 간단
- Python 내장 `multiprocessing`으로 32코어 활용

**단점**:
- 조합 수가 많으면 시간이 오래 걸림
- 비효율적 탐색 (명백히 나쁜 조합도 테스트)

**예상 시간** (백테스트 1회 = 5초 가정):
- 1,000 조합 × 5초 ÷ 32코어 = **약 2.6분**
- 10,000 조합 × 5초 ÷ 32코어 = **약 26분**
- 100,000 조합 × 5초 ÷ 32코어 = **약 4.3시간**

**추천 이유**:
- 32코어를 활용하면 충분히 현실적인 시간
- 결과의 신뢰성이 가장 높음
- GPU 없이도 충분히 빠름

### 2. Optuna (베이지안 최적화) ⭐⭐ 강력 권장

**장점**:
- **가장 효율적인 탐색** - TPE 알고리즘으로 좋은 영역 집중 탐색
- 이전 결과를 학습하여 다음 탐색 방향 결정
- Pruning - 명백히 나쁜 trial 조기 중단
- 병렬 처리 지원 (32코어 활용 가능)
- 실시간 모니터링 대시보드 제공
- 중간 저장/재개 가능

**단점**:
- 추가 라이브러리 설치 필요 (`pip install optuna`)
- Grid Search보다 구현이 약간 복잡

**예상 성능**:
- Grid Search 대비 **10~50배 빠르게** 최적값 근처 도달
- 1,000 trials로 수백만 조합 공간 효율적 탐색 가능

**추천 이유**:
- **산업 표준 하이퍼파라미터 튜닝 도구**
- 대규모 파라미터 공간 탐색에 최적
- 시각화 및 분석 도구 풍부

### 3. Ray Tune (분산 하이퍼파라미터 튜닝)

**장점**:
- 여러 머신에 분산 처리 가능
- 다양한 최적화 알고리즘 지원
- 대규모 클러스터 활용 시 매우 빠름

**단점**:
- 단일 머신에서는 Optuna보다 오버헤드 큼
- 설정이 복잡
- 추가 의존성 많음

**추천**: ❌ 단일 머신에서는 Optuna가 더 적합

### 4. Vectorbt (벡터화 백테스팅)

**장점**:
- NumPy 벡터화로 백테스트 **10~100배 고속화**
- 여러 파라미터 조합을 동시에 계산
- GPU 가속 지원 (CuPy)

**단점**:
- 기존 백테스트 코드 전면 재작성 필요
- 복잡한 거래 로직 구현이 어려움
- 학습 곡선이 가파름

**추천**: ⚠️ 시간이 충분하면 고려 (구현 1~2일 소요)

### 5. Numba JIT + GPU (CUDA)

**장점**:
- 백테스트 루프를 GPU에서 실행
- 단순 계산은 **수백 배 빠름**

**단점**:
- **이 프로젝트에 부적합**:
  - 백테스트는 날짜별 순차 처리 (병렬화 어려움)
  - 복잡한 if-else 로직 (GPU에 비효율적)
  - yfinance 데이터는 이미 메모리에 있음 (GPU 전송 오버헤드)

**추천**: ❌ 백테스팅에는 효과 미미

---

## 최종 권장 방법

### 🏆 1순위: Optuna + Multiprocessing

**이유**:
- 32코어를 모두 활용하여 병렬 탐색
- 베이지안 최적화로 효율적인 탐색
- 실시간 진행 상황 모니터링
- 중간 저장으로 언제든 중단/재개 가능

**예상 시간**:
- 1,000 trials (32 병렬) = **1~2시간**
- 충분히 촘촘한 탐색 가능

**구현 난이도**: ⭐⭐ (중간)

### 🥈 2순위: Grid Search + Multiprocessing

**이유**:
- 구현이 간단
- 모든 조합 확인 가능
- 32코어로 충분히 빠름

**예상 시간**:
- 10,000 조합 = **26분**
- 파라미터 범위를 좁히면 현실적

**구현 난이도**: ⭐ (쉬움)

### 💡 3순위 (장기): Vectorbt 전환

**이유**:
- 백테스트 자체를 10~100배 고속화
- 이후 모든 실험이 빨라짐

**예상 효과**:
- 백테스트 1회 5초 → 0.05초
- 100,000 조합도 1~2시간 내 가능

**구현 난이도**: ⭐⭐⭐⭐ (어려움, 1~2일 소요)

---

## 구체적 구현 계획

### 옵션 A: Optuna (추천)

```python
import optuna
from multiprocessing import Pool

def objective(trial):
    # 파라미터 제안
    rsi_window = trial.suggest_int('rsi_window', 3, 20)
    sma_window = trial.suggest_int('sma_window', 20, 200, step=10)
    buy_threshold = trial.suggest_int('buy_threshold', 20, 40)
    sell_threshold = trial.suggest_int('sell_threshold', 60, 80)
    max_holding = trial.suggest_int('max_holding', 30, 120, step=5)
    cooldown = trial.suggest_int('cooldown', 0, 180, step=10)

    # 백테스트 실행
    return_pct = run_backtest(rsi_window, sma_window, ...)

    return return_pct

# 최적화 실행 (32 병렬)
study = optuna.create_study(
    direction='maximize',
    sampler=optuna.samplers.TPESampler()
)
study.optimize(objective, n_trials=1000, n_jobs=32)

# 최적 파라미터
print(study.best_params)
print(f"최고 수익률: {study.best_value}%")

# 시각화
optuna.visualization.plot_optimization_history(study)
optuna.visualization.plot_param_importances(study)
```

**장점**:
- 자동으로 유망한 영역 집중 탐색
- 실시간 진행률 확인
- 파라미터 중요도 분석

### 옵션 B: Grid Search + Multiprocessing

```python
from itertools import product
from multiprocessing import Pool

# 파라미터 그리드
param_grid = {
    'rsi_window': range(3, 21, 1),      # 18개
    'sma_window': range(30, 201, 10),   # 18개
    'buy_threshold': range(25, 41, 1),  # 16개
    'sell_threshold': range(65, 76, 1), # 11개
    'max_holding': range(40, 91, 5),    # 11개
    'cooldown': range(40, 91, 10)       # 6개
}

# 총 조합: 18×18×16×11×11×6 = 약 373,248 조합
# 범위를 좁히면: 약 10,000~50,000 조합 추천

def run_single_backtest(params):
    rsi, sma, buy, sell, hold, cool = params
    return run_backtest(rsi, sma, buy, sell, hold, cool)

# 병렬 실행
with Pool(32) as pool:
    results = pool.map(run_single_backtest, all_combinations)

# 최적 파라미터 찾기
best_idx = np.argmax(results)
best_params = all_combinations[best_idx]
```

**장점**:
- 간단하고 직관적
- 모든 조합 완전 탐색
- 추가 라이브러리 불필요

---

## 추가 최적화 팁

### 1. 백테스트 속도 개선

#### 현재 병목점:
- yfinance 다운로드 (캐싱으로 해결)
- 일별 루프 (불가피)
- RSI/SMA 계산 (이미 최적화됨)

#### 개선 방법:
```python
# 1. 데이터 사전 다운로드 및 캐싱
import pickle

# 최초 1회만 다운로드
if not os.path.exists('data/cache/stock_data.pkl'):
    stock_data = download_all_data()
    pickle.dump(stock_data, open('data/cache/stock_data.pkl', 'wb'))
else:
    stock_data = pickle.load(open('data/cache/stock_data.pkl', 'rb'))

# 2. NumPy 배열로 변환 (pandas보다 빠름)
close_prices = df['Close'].values
rsi_values = df['RSI'].values
```

### 2. 메모리 최적화

```python
# 전체 결과를 메모리에 저장하지 말고 상위 N개만 유지
import heapq

top_results = []  # 상위 100개만 유지
for params in all_combinations:
    result = run_backtest(params)
    heapq.heappush(top_results, (result, params))
    if len(top_results) > 100:
        heapq.heappop(top_results)
```

### 3. 진행 상황 모니터링

```python
from tqdm import tqdm

# Grid Search
for params in tqdm(all_combinations, desc="백테스트 진행"):
    run_backtest(params)

# Optuna
study.optimize(
    objective,
    n_trials=1000,
    callbacks=[lambda study, trial: print(f"Trial {trial.number}: {trial.value}")]
)
```

---

## 실행 계획 요약

### 단계별 접근

#### Phase 1: Quick Win (1시간)
1. Grid Search로 범위 좁히기
   - 각 파라미터 3~5개 값만 테스트
   - 조합 수: ~1,000개
   - 시간: ~2분
2. 좋은 영역 확인

#### Phase 2: Fine-tuning (2~3시간)
1. Optuna 설치 및 구현
2. 좁힌 범위에서 1,000 trials 실행
3. 최적 파라미터 도출

#### Phase 3: Validation (1시간)
1. 최적 파라미터로 여러 기간 검증
2. 안정성 확인

---

## 다음 단계

1. **즉시 시작 가능**: Grid Search (좁은 범위)
2. **권장**: Optuna 설치 후 촘촘한 탐색
3. **장기 프로젝트**: Vectorbt 전환 (선택사항)

**예상 총 소요 시간**: 4~6시간 (Optuna 기준)
**예상 개선 효과**: 현재 대비 5~20% 수익률 향상 가능
