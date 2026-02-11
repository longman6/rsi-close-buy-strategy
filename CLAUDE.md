# CLAUDE.md - Developer Guide & Project Context

이 문서는 AI 어시스턴트(Claude, Antigravity 등)가 이 프로젝트를 이해하고 효율적으로 코딩을 지원하기 위한 가이드라인입니다.

## 🏗 프로젝트 아키텍처 개요

이 프로젝트는 **Python** 기반의 자동매매 봇으로, **한국투자증권(KIS) REST API**를 사용하여 주식 매매를 수행합니다.

*   **언어**: Python 3.10+
*   **프레임워크/라이브러리**:
    *   API 통신: `requests`
    *   데이터 처리: `pandas`, `numpy`
    *   대시보드: `streamlit`
    *   데이터베이스: `sqlite3`
    *   스케줄러: `main.py` 내 `while` 루프 및 `time.sleep` 기반 주기도 동작 ( `schedule` 라이브러리 미사용)

### 핵심 모듈 (`src/`)
1.  **`kis_client.py` (KISClient)**
    *   **역할**: KIS Open API와의 모든 통신 담당. 인증 토큰 관리, 시세 조회, 주문, 잔고 확인.
    *   **특징**: API Rate Limit(초당 요청 제한) 고려하여 `time.sleep` 적용됨. 토큰은 `token.json`에 캐싱하여 재사용.
2.  **`strategy.py` (Strategy)**
    *   **역할**: 매수/매도 로직 판단.
    *   **주요 지표**: RSI (Wilder's Smoothing), SMA (Simple Moving Average).
    *   **함수**: `analyze_stock(df)` -> 매수 신호 시 dict 반환, 없으면 None.
3.  **`trade_manager.py` (TradeManager)**
    *   **역할**: 매매 내역(`trade_history.json`) 관리, 보유 기간 계산, 재진입 쿨다운(`can_buy`) 체크.
    *   **특징**: JSON 파일과 DB를 동시에 업데이트하거나 동기화함.
4.  **`db_manager.py` (DBManager)**
    *   **역할**: SQLite DB (`stock_analysis.db`, `user_data.db`) CRUD 작업.
    *   **테이블**: 매매 일지, AI 조언, RSI 기록 등.

## 📝 코딩 컨벤션 및 규칙

1.  **언어**:
    *   사용자(User)와의 대화: **한국어 (Korean)** 필수.
    *   코드 주석: 한국어 권장, 영어 병기 가능.
    *   변수/함수명: **영어 (Snake Case)**, 클래스명: **Pascal Case**.

2.  **API 호출**:
    *   KIS API 호출 시 반드시 예외 처리(`try-except`)를 포함해야 함.
    *   루프 내에서 API 호출 시 `time.sleep()`을 사용하여 TPS 제한을 피할 것.

3.  **날짜/시간**:
    *   모든 로깅 및 DB 저장은 **KST (Asia/Seoul)** 시간대 기준.
    *   `src.utils.get_now_kst()` 활용 권장.

4.  **경로**:
    *   파일 경로는 프로젝트 루트(`rsi-close-buy-strategy/`) 기준 상대 경로 권장.
    *   설정 파일은 `config.py`를 통해 접근.

## 🚀 주요 명령어 (Cheat Sheet)

```bash
# 가상환경 활성화 (필수)
source .venv/bin/activate

# 메인 봇 실행
python main.py

# 대시보드 실행
streamlit run dashboard.py

# 백테스트 실행
python backtest/rsi_strategy_backtest.py

# 단위 테스트 (예시)
python -m unittest tests/unit/test_strategy.py
```

## ⚙️ 환경 변수 및 설정 (`config.py`)

*   `TIME_MORNING_ANALYSIS`: 아침 분석 시간 (기본 "08:30")
*   `TIME_SELL_EXEC`: 매도 실행 시간
*   `RSI_WINDOW`: RSI 계산 기간 (기본 5일)
*   `BUY_AMOUNT_KRW`: 종목당 매수 금액

## 🔍 디버깅 포인트

*   **로그**: `logs/trade_log.txt`에 실행 로그가 쌓임. 실시간 이슈 추적 시 `tail -f logs/trade_log.txt` 유용.
*   **토큰 만료**: API 호출 실패 시 `token.json` 삭제 후 재실행 시도.
*   **잔고 불일치**: `dashboard.py`와 실제 계좌(MTS/HTS) 간 차이가 발생할 경우, `main.py` 재시작을 통해 동기화 시도.

---
**Note for AI**: 위 내용을 숙지하고 코드를 작성하거나 수정할 때 일관성을 유지해주세요. 특히 API 호출 로직 수정 시 Rate Limit에 주의하십시오.
