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

### 데이터 소스 (Data Source)
*   **Primary**: **DuckDB** (`/home/longman6/projects/stock-collector/data/stock.duckdb`)
    *   `ohlcv_daily`: 일봉 데이터
    *   `index_constituents`: 유니버스 구성 종목 (현재 로직은 최신 연도 기준 -> 2016~현재 소급 적용)
*   **Fallback**: `FinanceDataReader` (다운로드)

### 주요 설정
*   **파일**: `backtest/rsi_strategy_backtest.py`
*   **기간**: **2016-01-01** ~ 현재 (KOSDAQ 150 지수 산출 이후)
*   **생존 편향 제거 (Survivorship Free)**: 
    *   2025.02 업데이트: DB에서 연도별 유니버스(Index Constituents)를 동적 로드하여 적용.
    *   상장폐지 종목이 포함되어 수익률이 현실화됨.
*   **성능 우수 전략 (2016~2025 생존 편향 제거 기준)**:
    *   **Ultra Optimization (Strategy D)**: RSI 5 / SMA 90 / Buy < 32 / Sell > 74 / Hold 50
    *   **Performance**: Return **308.09%** / Win Rate **63.91%** / MDD **-50.69%**
    *   *비고: 기존 Strategy C(Optimal) 대비 수익률 3.8배 상승. 보유 기간 확대(30->50일)와 장기 추세 필터(SMA 90)가 주요인.*

### 실행 방법

```bash
# 가상환경 활성화 (필수)
source .venv/bin/activate

# 백테스트 실행 (비교 모드 권장)
python backtest/rsi_strategy_backtest.py

# 최적화 실행 (생존 편향 제거 ver)
python backtest/optimize_survivorship_free.py
```

### 주의사항 (Limitations)
*   **DuckDB Lock**: DB 파일이 다른 프로세스(DBeaver 등)에 의해 잠겨 있을 경우, 스크립트가 자동으로 **임시 파일(Temp Copy)**을 생성하여 우회 접근합니다.
*   **데이터 정합성**: 과거 유니버스 종목 중 상장폐지된 일부 종목의 데이터가 누락되어 있을 수 있습니다.
*   **슬리피지**: 매매 비용(0.015%)과 세금(0.2%)은 반영되어 있으나, 호가 공백 등에 의한 슬리피지는 보수적으로 접근해야 합니다.

## 2. 최적화 (Optimization) - Survivorship Free (Not Yet Integrated in backtest.py)

(이전 설명과 동일)
*   **파일**: `backtest/optimize_survivorship_free_v2.py`
*   **특징**: 상장폐지 종목 포함한 완전한 유니버스 사용 가능 (구현 필요)

## 3. 결과 리포트

모든 백테스트 및 최적화 결과는 `reports/` 디렉토리에 저장해야 합니다.

- **비교 리포트**: `reports/comparative_backtest_report.md` (A/B 전략 비교 결과)
- **상세 리포트**: `reports/backtest_report.md`
- **요약**: 작업 완료 후 중요 수치는 `reports/summary.md`에 한국어로 요약하여 기록합니다.

## 문제 해결

### A. DuckDB Lock Error
`duckdb.IOException` 발생 시:
1.  다른 프로세스(DBeaver 등) 종료 권장.
2.  현재 스크립트는 `shutil.copy2`를 이용해 임시 파일로 우회하도록 패치되었습니다.

### B. 데이터 부족
유니버스 정보를 DB에서 가져오지 못하면 기본 샘플 종목(5개)으로 동작합니다. DB 연결 로그를 확인하십시오.
