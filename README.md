# RSI POWER ZONE 🚀

한국투자증권 API를 활용한 KOSDAQ 150 종목 대상 자동매매 시스템

## 프로젝트 소개

RSI POWER ZONE은 RSI(3) 지표 기반의 단기 반등 전략을 자동으로 실행하는 트레이딩 봇입니다. Gemini, Claude, GPT, Grok 등 다양한 LLM(Large Language Model)의 합의(Consensus)를 통해 매수 적합성을 분석하고, 한국투자증권 API를 통해 전 과정을 자동으로 수행합니다.

### 주요 특징

- 📊 **RSI(3) + SMA(100) 전략**: 과매도(RSI < 35) 구간 매수, 과매수(RSI > 70) 구간 매도
- � **Multi-LLM 합의 시스템**: Gemini, Claude, GPT, Grok 등 4개 이상의 AI 모델이 종목을 분석하여 다수결(Consensus)로 매수 여부 결정
- ⏰ **완전 자동화**: 장 시작 전 분석, 장전 시간 외 주문, 장중 모니터링, 장 마감 전 매도까지 자동 실행
- 📱 **Telegram 알림**: 매수/매도 체결, 분석 결과, 포트폴리오 상태 등 모든 중요 이벤트를 Telegram으로 실시간 수신
- 🛡️ **리스크 관리**:
  - 손실 종목 재매수 제한 (40일 쿨다운)
  - 최대 보유 기간 제한 (38일 강제 청산)
  - 종목당 투자금액 고정 및 예수금 부족 시 자동 조정
- � **보안 대시보드**: 로그인/비밀번호 인증이 적용된 Streamlit 대시보드 제공
- 🗄️ **영구 매매 기록**: SQLite DB에 모든 분석 및 매매 이력을 저장하여 성과 추적 가능

## 시스템 아키텍처

```text
┌─────────────────────────────────────────────────────────┐
│                     Daily Schedule (KST)                │
├─────────────────────────────────────────────────────────┤
│ 08:00  Cron Job: analyze_kosdaq150.py 실행               │
│        - KOSDAQ 150 전 종목 RSI 계산                     │
│        - RSI < 35 종목 대상 Multi-LLM 분석 요청          │
│        - 4개 이상 모델의 'YES' 합의 종목 선정            │
├─────────────────────────────────────────────────────────┤
│ 08:30  Main Bot: 매수 후보 로드                          │
│        - DB에서 분석 결과 조회                           │
│        - 보유 종목 수 및 예수금 체크                     │
├─────────────────────────────────────────────────────────┤
│ 08:57  Pre-Market 지정가 주문 (예상체결가 + 1.5%)         │
├─────────────────────────────────────────────────────────┤
│ 09:05  미체결 주문 모니터링 & 정정 (1분 주기)             │
│        - 급등 시 취소, 미체결 시 현재가로 정정 주문       │
├─────────────────────────────────────────────────────────┤
│ 15:20  매도 신호 체크 (RSI > 70 or 보유 38일 초과)        │
├─────────────────────────────────────────────────────────┤
│ 15:26  시장가 매도 실행                                  │
└─────────────────────────────────────────────────────────┘
```

## 🗄️ Database Schema (`stock_analysis.db`)

SQLite를 사용하여 데이터의 무결성을 보장하고 이력을 관리합니다.

### 1. `daily_rsi`
일일 주가 및 RSI 지표 저장
- `date`, `code`, `name`, `rsi`, `close_price` 등

### 2. `ai_advice`
각 AI 모델의 종목별 매수 추천 상세 내역
- `model`: AI 모델명 (Gemini, Claude, GPT-4o 등)
- `recommendation`: 'YES' 또는 'NO'
- `reasoning`: 추천 사유
- `prompt`: 사용된 프롬프트

### 3. `trade_history`
실제 매매 체결 내역
- `action`: 'BUY' / 'SELL'
- `price`, `quantity`, `amount`: 체결 정보
- `pnl_amt`, `pnl_pct`: 실현 손익 (SELL 시)

### 4. `users`
대시보드 접속을 위한 사용자 계정 정보 (ID, Password Hash)

## 📂 Project Structure

```text
RSI_POWER_ZONE/
├── main.py                 # 🚀 메인 봇 (스케줄링 및 매매 실행)
├── dashboard.py            # 📊 웹 대시보드 (Streamlit)
├── analyze_kosdaq150.py    # 🧠 AI 일일 분석 스크립트 (Cron)
├── rsi_strategy_backtest.py# 📉 백테스팅 스크립트
├── config.py               # ⚙️ 전역 설정
├── run.sh                  # 🏃 봇 실행 스크립트
├── run_dashboard.sh        # 📊 대시보드 실행 스크립트
├── src/                    # 🧱 핵심 모듈
│   ├── kis_client.py       # 한국투자증권 API 클라이언트
│   ├── db_manager.py       # DB CRUD 관리
│   ├── ai_manager.py       # Multi-LLM 통합 관리
│   ├── telegram_bot.py     # 텔레그램 알림 봇
│   ├── auth.py             # 대시보드 인증/보안
│   ├── strategy.py         # 기술적 지표 계산
│   └── trade_manager.py    # 매매 로직 및 상태 관리
├── scripts/                # 🛠️ 유틸리티
└── stock_analysis.db       # 🗄️ 데이터베이스 파일
```

## 설치 및 설정

### 1. 환경 설정 (.env)
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력해야 합니다.

```env
# 한국투자증권 API (실전/모의투자)
KIS_APP_KEY="your_app_key"
KIS_APP_SECRET="your_app_secret"
KIS_ACCOUNT_NO="12345678-01"
KIS_URL_BASE="https://openapivts.koreainvestment.com:29443" # 모의투자

# Telegram Bot
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"

# AI API Keys
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GOOGLE_API_KEY="AIza..."
XAI_API_KEY="xai-..."
```

### 2. 패키지 설치
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 사용 방법

### 1. 메인 봇 실행
봇은 백그라운드에서 실행되며 장중 내내 동작합니다.
```bash
./run.sh
# 또는
python main.py
```

### 2. 대시보드 접속
매매 현황과 분석 결과를 웹에서 확인합니다.
```bash
./run_dashboard.sh
```
- 브라우저 접속: `http://localhost:8501`
- 초기 로그인 계정이 설정되어야 하며, `auth.py`를 통해 관리됩니다.

### 3. 일일 분석 (수동 실행)
보통 오전 8시에 자동 실행되지만, 테스트를 위해 수동으로 실행 가능합니다.
```bash
./run_analysis.sh
```

### 4. 백테스트
과거 데이터를 기반으로 전략의 유효성을 검증합니다.
```bash
python rsi_strategy_backtest.py
```

## 주의사항

> [!WARNING]
> **투자 위험 안내**
> - 본 프로그램은 투자를 보조하는 도구일 뿐이며, 수익을 보장하지 않습니다.
> - 투자에 대한 최종 판단과 책임은 사용자 본인에게 있습니다.
> - 실전 투자 전 반드시 모의투자를 통해 시스템의 안정성을 충분히 검증하시기 바랍니다.

## 라이선스
MIT License
