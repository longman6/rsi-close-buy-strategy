# RSI Close-Buy Strategy Bot (KOSDAQ 150)

이 프로젝트는 한국투자증권(KIS) Open API를 활용하여 코스닥 150(KOSDAQ 150) 종목을 대상으로 **RSI(Relative Strength Index) 기반 평균회귀 전략**을 수행하는 자동매매 봇입니다. 

**핵심 전략**: 단기 과낙폭(RSI 과매도) 구간에서 매수하고, 반등(RSI 과매수) 시 매도하여 수익을 추구합니다.

## ✨ 주요 기능

*   **자동 매매**: 장중 실시간 시세 모니터링 및 조건 충족 시 자동 매수/매도 주문.
    *   **매수**: RSI(5) <= 28 (과매도) & 종가 > 70일 이동평균선 (상승 추세 필터).
    *   **매도**: RSI(5) >= 72 (과매수) 또는 보유기간 초과 시 강제 청산.
*   **분할 매수**: 1차, 2차 분할 매수 로직 지원 (설정 가능).
*   **리스크 관리**:
    *   손실 발생 종목에 대한 쿨다운(재진입 금지) 기간 설정 (`LOSS_COOLDOWN_DAYS`).
    *   최대 보유 종목 수 및 종목당 매수 금액 제한.
*   **대시보드**: Streamlit 기반 웹 대시보드를 통해 실시간 잔고, 매매 기록, RSI 현황, AI 매매 조언 확인 가능.
*   **알림**: 텔레그램(Telegram) 봇을 통한 실시간 매매 체결 및 에러 알림.
*   **데이터 관리**: SQLite 데이터베이스를 통한 매매 일지 및 AI 분석 결과 저장.

## 🛠 설치 및 설정

### 1. 필수 요구 사항
*   Python 3.10 이상
*   한국투자증권(KIS) 계좌 및 API 신청 (실전/모의투자)
*   텔레그램 봇 토큰 (알림 수신용)

### 2. 설치
```bash
# 저장소 클론
git clone https://github.com/longman6/rsi-close-buy-strategy.git
cd rsi-close-buy-strategy

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 의존성 패키지 설치
pip install -r requirements.txt
```

### 3. 환경 설정 (.env)
`.env.example` 파일을 복사하여 `.env` 파일을 생성하고, 본인의 API 정보를 입력하세요.

```bash
cp .env.example .env
vi .env
```

**주요 설정 항목 (.env):**
*   `KIS_APP_KEY`, `KIS_APP_SECRET`: 한국투자증권 API 인증 정보.
*   `KIS_CANO`: 종합계좌번호 (8자리).
*   `KIS_ACNT_PRDT_CD`: 계좌상품코드 (보통 "01").
*   `KIS_URL_BASE`: 실전 투자(`https://openapi.koreainvestment.com:9443`) 또는 모의 투자(`https://openapivts.koreainvestment.com:29443`) URL.
*   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: 텔레그램 알림 설정.
*   `RSI_WINDOW`, `RSI_BUY_THRESHOLD`: 전략 파라미터.

## 🚀 실행 방법

### 메인 봇 (자동매매) 실행
트레이딩 봇을 실행하여 장중 모니터링 및 매매를 시작합니다.
```bash
python main.py
```
*   봇은 설정된 스케줄(`TIME_MORNING_ANALYSIS`, `TIME_SELL_CHECK` 등)에 따라 동작합니다.
*   `logs/trade_log.txt`에 상세 로그가 기록됩니다.

### 대시보드 실행
웹 브라우저에서 현재 상태를 모니터링하려면 대시보드를 실행하세요.
```bash
streamlit run dashboard.py
```
*   브라우저가 자동으로 열리며 `http://localhost:8501`에서 접속 가능합니다.
*   **로그인**: 초기 실행 시 설정된 계정으로 로그인 (DB 초기화 시 기본 계정 생성될 수 있음).

### 백테스트 (Backtest)
과거 데이터를 기반으로 전략의 성과를 검증합니다.
```bash
python backtest/rsi_strategy_backtest.py
```
*   `reports/` 디렉토리에 결과 리포트가 생성됩니다.

## 📂 프로젝트 구조

```
rsi-close-buy-strategy/
├── main.py                 # 메인 실행 파일 (스케줄러, 봇 로직)
├── dashboard.py            # Streamlit 웹 대시보드
├── config.py               # 환경 변수 및 설정 로드
├── requirements.txt        # 의존성 패키지 목록
├── .env                    # 민감 정보 및 설정 (Git 제외)
├── src/                    # 소스 코드 디렉토리
│   ├── kis_client.py       # 한국투자증권 API 클라이언트
│   ├── strategy.py         # RSI/SMA 전략 및 기술적 지표 계산
│   ├── trade_manager.py    # 매매 내역 관리 및 쿨다운 로직
│   ├── db_manager.py       # SQLite DB 관리 (일지, AI 조언 등)
│   ├── telegram_bot.py     # 텔레그램 알림 발송
│   └── ...
├── data/                   # 데이터 파일 (DB, 제외 종목 리스트 등)
│   ├── stock_analysis.db   # 마켓 데이터 DB
│   ├── user_data.db        # 사용자 데이터 DB
│   └── trade_history.json  # (레거시) 매매 내역 JSON
├── logs/                   # 실행 로그 저장
├── reports/                # 백테스트 및 최적화 리포트
└── scripts/                # 유틸리티 스크립트 (로그 파싱, DB 마이그레이션 등)
```

## ⚠️ 주의사항

*   **투자 책임**: 본 프로그램은 투자를 돕는 도구일 뿐이며, **실제 투자의 책임은 전적으로 사용자 본인**에게 있습니다.
*   **모의 투자 권장**: 실전 투자 전 반드시 모의 투자 환경에서 충분히 테스트하세요.
*   **API 제한**: 한국투자증권 API의 초당 전송 제한(TPS)을 준수해야 합니다.