---
name: Backtest & Optimization
description: RSI 전약 백테스팅 및 파라미터 최적화를 수행하는 스킬
---

# Backtest & Optimization Skill

이 스킬은 RSI 전략의 백테스팅과 파라미터 최적화를 수행하는 표준 방법을 정의합니다.

## 필수 환경

- **가상환경**: `.venv` 활성화 필수
- **실행 위치**: 프로젝트 루트 (`/home/longman6/codelab/RSI_POWER_ZONE`)

## 1. 백테스트 (Backtest)

기본 전략 검증 및 연도별 수익률 분석을 수행합니다.

### 주요 스크립트

- **파일**: `backtest/rsi_strategy_backtest.py`
- **데이터 소스**: 
  - `data/historical/*.pkl` (1순위)
  - `data/historical/*.csv` (2순위)
  - `FinanceDataReader` (3순위 - 다운로드)
- **대상**: KOSDAQ 150 (현재 기준 또는 `kosdaq150_list.txt`)

### 실행 방법

```bash
# 가상환경 활성화 (필수)
source .venv/bin/activate

# 백테스트 실행
python backtest/rsi_strategy_backtest.py
```

### 설정 변경
`backtest/rsi_strategy_backtest.py` 상단의 파라미터를 수정하여 전략을 변경합니다.
```python
RSI_WINDOW = 5
BUY_THRESHOLD = 35
SMA_WINDOW = 50 
```

## 2. 최적화 (Optimization) - 상장폐지 포함 (Survivorship Free)

과거 시점의 KOSDAQ 150 구성 종목 데이터를 사용하여 생존 편향(Survivorship Bias)을 제거한 최적화를 수행합니다.

### 주요 스크립트

- **파일**: `backtest/optimize_survivorship_free_v2.py`
- **데이터 소스**: **DuckDB** (`/home/longman6/projects/stock-collector/data/stock.duckdb`)
  - **주의**: DuckDB 연결 시 반드시 `read_only=True` 옵션을 사용해야 합니다.
  - Table: `ohlcv_daily`

### 실행 방법

```bash
# 최적화 실행 (멀티프로세싱 사용됨)
python backtest/optimize_survivorship_free_v2.py
```

### 주의사항 (Critical)
- **DB 잠금 방지**: 스크립트 내에서 `duckdb.connect(..., read_only=True)`가 사용되었는지 항상 확인하십시오.
- **메모리 사용**: 전체 데이터를 로드하므로 메모리 사용량에 주의하십시오.

## 3. 결과 리포트

모든 백테스트 및 최적화 결과는 `reports/` 디렉토리에 저장해야 합니다.

- **백테스트 리포트**: `reports/backtest_report.md` (자동 생성/추가됨)
- **최적화 결과**: `reports/optimization_rsi_results_*.csv`
- **요약**: 작업 완료 후 중요 수치는 `reports/summary.md`에 한국어로 요약하여 기록합니다.

## 문제 해결

### A. DuckDB Lock Error
`duckdb.IOException: IO Error: Could not set lock on file...` 에러 발생 시:
1. 다른 프로세스(수집기 등)가 DB를 점유 중인지 확인하십시오.
2. 스크립트가 `read_only=True`로 연결하는지 확인하십시오.

### B. 데이터 부족
`FinanceDataReader`가 데이터를 가져오지 못하는 경우, 티커 명이 변경되었거나 상장 폐지된 종목일 수 있습니다. 상장 폐지 종목 테스트는 `optimize_survivorship_free_v2.py` 사용을 권장합니다.
