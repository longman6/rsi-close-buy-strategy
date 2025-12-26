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
- 📈 **Streamlit 대시보드**: Gemini 분석 결과를 시각적으로 확인

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                     Daily Schedule                       │
├─────────────────────────────────────────────────────────┤
│ 07:00  Gemini AI 분석 (저 RSI 종목 뉴스 분석)            │
│ 08:30  매수 후보 선정 (RSI < 35, Close > SMA100)         │
│ 08:57  Pre-Market 지정가 주문 (예상체결가 + 5 Tick)       │
│ 09:05  미체결 주문 모니터링 (현재가로 정정, +5% 초과 시 취소) │
│ 15:20  매도 신호 체크 (RSI > 70 or 보유 38일 초과)        │
│ 15:26  시장가 매도 실행                                  │
└─────────────────────────────────────────────────────────┘
```

## 설치 방법

### 1. 저장소 클론

```bash
git clone <repository-url>
cd RSI_POWER_ZONE
```

### 2. 가상환경 생성 및 활성화

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows
```

### 3. 의존성 패키지 설치

```bash
pip install -r requirements.txt
```

## 환경 설정

### 1. 환경 변수 파일 생성

`.env.example` 파일을 복사하여 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

### 2. API 키 설정

`.env` 파일을 열어 다음 항목들을 설정합니다:

#### 한국투자증권 API

1. [한국투자증권 OpenAPI](https://apiportal.koreainvestment.com/) 접속
2. 회원가입 및 앱 등록
3. 발급받은 키를 입력:

```env
KIS_APP_KEY="your_app_key_here"
KIS_APP_SECRET="your_app_secret_here"
KIS_CANO="12345678"  # 계좌번호 앞 8자리
KIS_ACNT_PRDT_CD="01"
KIS_URL_BASE="https://openapi.koreainvestment.com:9443"  # 실전투자
# KIS_URL_BASE="https://openapivts.koreainvestment.com:29443"  # 모의투자
```

#### Google Gemini API

1. [Google AI Studio](https://makersuite.google.com/app/apikey) 접속
2. API 키 발급
3. `.env` 파일에 추가:

```env
GEMINI_API_KEY="your_gemini_api_key_here"
```

#### Slack Webhook (선택사항)

1. [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks) 설정
2. Webhook URL 복사:

```env
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
SLACK_CHANNEL="#trading"
```

### 3. 전략 파라미터 조정 (선택사항)

```env
RSI_WINDOW=3              # RSI 계산 기간
SMA_WINDOW=100            # SMA 계산 기간
MAX_POSITIONS=5           # 최대 보유 종목 수
RSI_BUY_THRESHOLD=35      # 매수 RSI 임계값
RSI_SELL_THRESHOLD=70     # 매도 RSI 임계값
BUY_AMOUNT_KRW=1000000    # 종목당 매수 금액 (100만원)
MAX_HOLDING_DAYS=38       # 최대 보유 기간
LOSS_COOLDOWN_DAYS=40     # 손실 후 재매수 금지 기간
```

## 사용 방법

### 1. 메인 트레이딩 봇 실행

```bash
# 쉘 스크립트 사용
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

### 2. Gemini AI 분석만 실행

```bash
python3 run_daily_advice.py
```

- KOSDAQ 150 종목 중 RSI < 35인 종목을 필터링
- 각 종목의 최근 24시간 뉴스를 검색하여 Gemini AI에 분석 요청
- 분석 결과를 `stock_analysis.db`에 저장

### 3. 대시보드 실행

```bash
streamlit run dashboard.py
```

브라우저에서 `http://localhost:8501`로 접속하여:

- 날짜별 Gemini 분석 결과 확인
- YES/NO 추천 통계 확인
- 종목별 상세 분석 내용 확인

### 4. 백테스트 실행

```bash
python3 rsi_strategy_backtest.py
```

과거 데이터를 기반으로 전략의 성과를 시뮬레이션합니다.

## 제외 종목 관리

특정 종목을 매매에서 제외하려면 `exclude_list.txt` 파일을 편집합니다:

```txt
# 제외할 종목 코드를 한 줄에 하나씩 입력
005930  # 삼성전자
000660  # SK하이닉스
```

## 프로젝트 구조

```
RSI_POWER_ZONE/
├── main.py                    # 메인 트레이딩 봇
├── run_daily_advice.py        # Gemini 분석 작업
├── dashboard.py               # Streamlit 대시보드
├── config.py                  # 설정 로더
├── src/
│   ├── kis_client.py         # 한국투자증권 API 클라이언트
│   ├── strategy.py           # RSI 전략 로직
│   ├── trade_manager.py      # 거래 이력 관리
│   ├── gemini_client.py      # Gemini AI 클라이언트
│   ├── db_manager.py         # SQLite 데이터베이스 관리
│   └── slack_bot.py          # Slack 알림
├── requirements.txt           # Python 의존성
├── .env.example              # 환경 변수 예시
├── exclude_list.txt          # 제외 종목 리스트
├── trade_history.json        # 거래 이력 (자동 생성)
├── stock_analysis.db         # Gemini 분석 DB (자동 생성)
└── trade_log.txt             # 실행 로그 (자동 생성)
```

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
