# RSI POWER ZONE 🚀

한국투자증권 API를 활용한 KOSDAQ 150 종목 대상 자동매매 시스템

## 프로젝트 소개

RSI POWER ZONE은 RSI(3) 지표 기반의 단기 반등 전략을 자동으로 실행하는 트레이딩 봇입니다. Google Gemini AI를 활용하여 저평가 종목을 분석하고, 한국투자증권 API를 통해 실제 매매를 수행합니다.

### 주요 특징

- 📊 **RSI(3) + SMA(100) 전략**: 과매도 구간에서 매수, 과매수 구간에서 매도
- 🤖 **AI 기반 종목 선정**: Gemini AI가 뉴스 및 시장 상황을 분석하여 매수 추천
- ⏰ **완전 자동화**: 장 시작 전 분석부터 매매 실행, 모니터링까지 전 과정 자동화
- 📱 **Slack 알림**: 모든 매매 이벤트를 Slack으로 실시간 알림
- 🛡️ **리스크 관리**: 손실 종목 재매수 방지(40일 쿨다운), 최대 보유 기간 제한(38일)
- 📈 **Streamlit 대시보드**: 실시간 포트폴리오 상태 및 과거 거래 이력 시각화
- 🗄️ **영구 매매 기록**: 모든 BUY/SELL 내역을 SQLite DB에 저장하여 성과 분석 가능

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                     Daily Schedule (KST)                │
├─────────────────────────────────────────────────────────┤
│ 08:00  Cron Job: analyze_kosdaq150.py 실행               │
│        - KOSDAQ 150 전 종목 RSI 계산                     │
│        - RSI < 35 종목 대상 4개 LLM (Gemini, Claude 등) 분석 │
│        - 분석 결과 및 매수 추천 DB 저장                  │
├─────────────────────────────────────────────────────────┤
│ 08:30  Main Bot: 매수 후보 선정                          │
│        - DB에서 Low RSI & 4-LLM Consensus('YES') 조회    │
├─────────────────────────────────────────────────────────┤
│ 08:57  Pre-Market 지정가 주문 (예상체결가 + 5 Tick)       │
├─────────────────────────────────────────────────────────┤
│ 09:05  미체결 주문 모니터링 (현재가로 정정)               │
├─────────────────────────────────────────────────────────┤
│ 15:20  매도 신호 체크 (RSI > 70 or 보유 38일 초과)        │
├─────────────────────────────────────────────────────────┤
│ 15:26  시장가 매도 실행                                  │
└─────────────────────────────────────────────────────────┘
```

## 🗄️ Database Schema (`stock_analysis.db`)

SQLite를 사용하여 분석 데이터와 AI 추천 결과를 저장합니다.

### 1. `daily_rsi` (일일 RSI 분석 결과)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | PK |
| date | TEXT | 분석 날짜 (YYYY-MM-DD) |
| code | TEXT | 종목 코드 |
| name | TEXT | 종목명 |
| rsi | REAL | RSI(3) 값 |
| close_price | REAL | 종가 |
| created_at | TIMESTAMP | 생성 시간 |

### 2. `ai_advice` (AI 매수 추천)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | PK |
| date | TEXT | 분석 날짜 (YYYY-MM-DD) |
| code | TEXT | 종목 코드 |
| model | TEXT | AI 모델명 (Gemini, Claude, GPT, Grok) |
| recommendation | TEXT | 추천 결과 ('YES' or 'NO') |
| reasoning | TEXT | 추천 사유 |
| specific_model | TEXT | 상세 모델 버전 (e.g., gemini-1.5-flash) |
| prompt | TEXT | 사용된 프롬프트 내용 |
| created_at | TIMESTAMP | 생성 시간 |

### 3. `trade_history` (매매 체결 이력)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | PK |
| date | TEXT | 거래 날짜 (YYYY-MM-DD) |
| code | TEXT | 종목 코드 |
| name | TEXT | 종목명 |
| action | TEXT | 매매 구분 ('BUY' or 'SELL') |
| price | REAL | 체결 가격 |
| quantity | INTEGER | 체결 수량 |
| amount | REAL | 총 체결 금액 |
| pnl_amt | REAL | 수익금 (SELL 시 기록) |
| pnl_pct | REAL | 수익률 (SELL 시 기록) |
| created_at | TIMESTAMP | 생성 시간 |

## 📂 Project Structure

```
RSI_POWER_ZONE/
├── main.py                 # 🚀 Main Bot Entry Point
├── dashboard.py            # 📊 Streamlit Dashboard
├── analyze_kosdaq150.py    # 🧠 Daily AI Analysis (Cron Job @ 08:00 KST)
├── config.py               # ⚙️ Configuration
├── run.sh                  # 🏃 Execution Script
├── run_analysis.sh         # 🕒 Cron Execution Script
├── run_dashboard.sh        # 📊 Dashboard Launch Script
├── src/                    # 🧱 Core Modules
│   ├── kis_client.py       # KIS API Client
│   ├── db_manager.py       # Database Manager
│   ├── ai_manager.py       # AI Aggregation Manager (Multi-LLM)
│   ├── strategy.py         # Technical Indicators
│   ├── trade_manager.py    # Trade Execution Logic
│   └── utils.py            # Common Utilities (KST Time, etc)
├── scripts/                # 🛠️ Utility Scripts
│   ├── parse_trade_log.py  # Log Parser
│   └── ...
├── tests/                  # 🧪 Tests & Debugging
│   ├── debug/              # Debugging Scripts
│   ├── unit/               # Unit Tests (test_bot.py, etc)
│   └── integration/        # Integration Tests (verify_*.py)
└── stock_analysis.db       # 🗄️ SQLite Database
```

├── requirements.txt           # Python 의존성
├── .env.example              # 환경 변수 예시
├── exclude_list.txt          # 제외 종목 리스트
├── trade_history.json        # 거래 이력 (자동 생성)
└── trade_log.txt             # 실행 로그 (자동 생성)

```

## 사용 방법

### 1. 메인 트레이딩 봇 실행

```bash
# 쉘 스크립트 사용 (권장)
./run.sh

# 또는 직접 실행
source .venv/bin/activate
python3 main.py
```

봇이 실행되면 다음 작업들을 자동으로 수행합니다:
- 매일 설정된 시간에 분석 및 매매 수행
- 휴장일 자동 감지 및 스킵
- 모든 이벤트를 Slack으로 알림
- 실행 로그를 `trade_log.txt`에 기록

### 2. Daily AI 분석 실행 (수동)

일일 분석은 매일 아침 08:00 (KST)에 Cron에 의해 자동 실행되지만, 필요시 수동으로 실행할 수도 있습니다.

```bash
# 쉘 스크립트 사용 (권장)
./run_analysis.sh

# 또는 Python 직접 실행
python3 analyze_kosdaq150.py
```

- KOSDAQ 150 종목 중 RSI < 35인 종목을 필터링
- 각 종목의 저항선/지지선 및 기술적 지표 계산
- 4개의 LLM(Gemini, Claude, GPT, Grok)에 매수 적합성 분석 요청
- 분석 결과를 `stock_analysis.db`에 저장

### 3. 대시보드 실행

```bash
# 쉘 스크립트 사용 (권장)
./run_dashboard.sh

# 또는 Streamlit 직접 실행
streamlit run dashboard.py
```

브라우저에서 `http://localhost:8501`로 접속하여:
- 날짜별 AI 분석 결과 및 Consensus 확인
- 보유 종목 현황 및 수익률 실시간 모니터링
- 과거 거래 내역 시각화 (성과 지표, 수익 곡선 차트 등)
- 전체 KOSDAQ 150 종목 RSI 스크리닝 결과 조회

### 4. 백테스트 실행

```bash
python3 rsi_strategy_backtest.py
```

과거 데이터를 기반으로 전략의 성과를 시뮬레이션합니다.

## 매매 전략 상세

### 매수 조건

1. RSI(3) < 35 (과매도 구간)
2. 현재가 > SMA(100) (상승 추세)
3. 제외 종목 리스트에 없음
4. 관리종목/거래정지/투자경고 종목 아님
5. 손실 후 40일 경과 (또는 수익 실현 종목)
6. 현재 보유 종목 < 5개

### 매도 조건

1. RSI(3) > 70 (과매수 구간), 또는
2. 보유 기간 > 38일 (강제 청산)

### 리스크 관리

- **최대 보유 종목**: 5개로 분산 투자
- **포지션 사이즈**: 종목당 고정 금액 (기본 100만원)
- **손실 쿨다운**: 손실 종목은 40일간 재매수 금지
- **강제 청산**: 38일 이상 보유 시 무조건 매도

## 모의투자 vs 실전투자

### 모의투자로 시작하기 (권장)

`.env` 파일에서 URL을 모의투자 서버로 설정:

```env
KIS_URL_BASE="https://openapivts.koreainvestment.com:29443"
```

모의투자 모드에서는:

- 가상 계좌로 안전하게 테스트
- 자동으로 감지되어 Slack 알림 비활성화
- 모든 휴장일을 거래일로 간주 (테스트 용이)

### 실전투자 전환

충분한 테스트 후 실전투자로 전환:

```env
KIS_URL_BASE="https://openapi.koreainvestment.com:9443"
```

## 자주 묻는 질문 (FAQ)

### Q: 봇을 24시간 돌려야 하나요?

A: 예. 봇은 내부 스케줄러로 정해진 시간에만 작업을 수행하고, 나머지 시간은 대기합니다. 서버나 항상 켜져있는 PC에서 실행하는 것을 권장합니다.

### Q: 크론잡으로 특정 시간에만 실행할 수 있나요?

A: 가능하지만 권장하지 않습니다. 09:05-15:20 동안 1분마다 미체결 주문을 모니터링해야 하므로, 연속 실행이 적합합니다.

### Q: Gemini API 비용은 얼마나 드나요?

A: Gemini Flash 모델은 무료 티어에서도 충분히 사용 가능합니다. 하루 150개 종목을 분석해도 무료 한도 내에서 동작합니다.

### Q: 손실이 발생하면 어떻게 되나요?

A: 해당 종목은 40일간 자동으로 재매수가 차단되며, `trade_history.json`에 기록됩니다.

### Q: 특정 종목을 영구적으로 제외하고 싶어요

A: `exclude_list.txt` 파일에 종목 코드를 추가하면 매수/매도 대상에서 제외됩니다.

## 테스트

프로젝트는 여러 검증 스크립트를 포함합니다:

```bash
# KIS API 연결 테스트
python3 test_kis_ohlcv.py

# Slack 알림 테스트
python3 test_bot.py

# 휴장일 체크 테스트
python3 verify_holiday.py

# 제외 종목 필터링 테스트
python3 verify_exclusion.py

# 위험 종목 필터링 테스트
python3 verify_stock_filter.py
```

## 로그 확인

모든 거래 활동은 `trade_log.txt`에 기록됩니다:

```bash
# 실시간 로그 확인
tail -f trade_log.txt

# 오늘 날짜 로그만 확인
grep "$(date +%Y-%m-%d)" trade_log.txt
```

## 주의사항

⚠️ **투자 위험 경고**

- 이 봇은 교육 및 연구 목적으로 제작되었습니다
- 실전 투자 시 발생하는 손실에 대해 개발자는 책임지지 않습니다
- 반드시 모의투자로 충분히 테스트한 후 소액으로 시작하세요
- 투자 손실 위험을 충분히 이해하고 사용하세요

⚠️ **기술적 주의사항**

- KIS API는 초당 요청 횟수(TPS) 제한이 있습니다
- 모의투자 서버는 불안정할 수 있습니다 (500 에러 빈번)
- 네트워크 장애 시 거래가 실패할 수 있습니다
- 시스템 시계를 정확히 맞춰주세요 (KST 기준)

## 기여하기

버그 리포트, 기능 제안, 풀 리퀘스트를 환영합니다!

## 라이선스

이 프로젝트는 개인적 용도로 자유롭게 사용 가능합니다.

---

**면책 조항**: 본 소프트웨어는 "있는 그대로" 제공되며, 어떠한 명시적 또는 묵시적 보증도 하지 않습니다. 투자 결정은 사용자 본인의 책임입니다.
