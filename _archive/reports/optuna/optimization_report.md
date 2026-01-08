# Optuna 파라미터 최적화 결과

**최적화 일시**: 2026-01-07 14:19:49
**분석 기간**: 2005-01-01 ~ 2025-12-31
**초기 자본**: 100,000,000원
**총 Trials**: 2500개

## 최적 파라미터

| 파라미터 | 값 |
|---------|-----|
| rsi_window | 3 |
| sma_window | 95 |
| buy_threshold | 39 |
| sell_threshold | 60 |
| max_holding_days | 39 |
| loss_cooldown_days | 75 |

## 성과

- **최고 수익률**: 32569.05%
- **평균 수익률 (상위 10%)**: 24637.38%
- **평균 수익률 (전체)**: 9625.73%

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
