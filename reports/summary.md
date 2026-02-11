# 백테스트/최적화 보고서 요약

## [2026-02-11] 생존 편향 제거 최적화 (Survivorship-Free Optimization)

*   **테스트 기간**: 2016-01-01 ~ 2025-02-10 (KOSDAQ 150)
*   **주요 성과**:
    *   **Strategy D (Ultra)** 발굴: 누적 수익률 **308.09%** (MDD -50.69%)
*   **핵심 변경점**:
    *   생존 편향 제거 (Dynamic Universe) 적용
    *   RSI 계산 로직 정합성 확보 (Wilder's Smoothing)
    *   최적 파라미터 적용 (RSI 5 / SMA 90 / Buy 32 / Sell 74 / Hold 50)

👉 **상세 보고서 바로가기**: [optimization_survivorship_free_2026-02-11.md](./optimization_survivorship_free_2026-02-11.md)

## [2026-02-11] 전략 vs 벤치마크 연도별 성과 비교

*   **비교 대상**: Strategy A/B/C/D vs KODEX 200 / KODEX 150
*   **주요 결과**:
    *   **2022년 하락장**: Strategy D (-25.27%)가 KODEX 150 (-35.66%) 대비 방어력 우수.
    *   **2025년 상승장**: Strategy D (+96.63%)가 KODEX 150 (+37.33%) 대비 초과 수익 달성.
    *   **누적 성과**: Strategy D (308%) >> KODEX 150

👉 **연도별 비교 보고서 보기**: [comparative_backtest_yearly.md](./comparative_backtest_yearly.md)
