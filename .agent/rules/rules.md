---
trigger: always_on
---

# 프로젝트 규칙

## 프로젝트 개요

RSI_POWER_ZONE은 KOSDAQ 150 종목을 대상으로 RSI 기반 평균회귀 전략을 구현한 자동 주식 매매 봇입니다.

- **주요 기술**: Python, KIS API, Multi-LLM (Gemini, Claude, GPT, Grok), Telegram, SQLite
- **전략**: RSI(3) < 35 매수, RSI(3) > 70 매도
- **핵심 파일**: `main.py` (트레이딩 루프), `analyze_kosdaq150.py` (AI 분석), `src/kis_client.py` (API 클라이언트)

## 가상환경 (Virtual Environment)

- **항상 가상환경을 사용할 것**
- 가상환경 경로: `.venv/`
- 활성화 명령어: `source .venv/bin/activate`
- 패키지 설치 시 반드시 가상환경 활성화 후 진행

## 명령어 실행 규칙

- 모든 Python 스크립트 실행: `.venv/bin/python <script.py>`
- 패키지 설치: `.venv/bin/pip install <package>`
- 테스트 실행: `.venv/bin/python tests/unit/test_*.py`
- 백테스트 실행: `.venv/bin/python rsi_strategy_backtest.py`

## 코드 스타일

- Python 3.10+ 문법 사용
- 타입 힌트 권장
- 로깅은 KST 타임존 사용 (`src/utils.py`의 `get_now_kst()` 활용)
- API 호출 시 반드시 rate limit 고려 (`time.sleep()` 포함)
- 에러 처리: try-except로 감싸고 적절한 로깅 수행

## 주요 디렉토리 구조

```text
src/           # 핵심 모듈 (kis_client, strategy, ai_manager 등)
tests/         # 테스트 코드 (unit/, integration/, debug/)
data/          # 데이터 파일 (exclude_list.txt, trade_history.json)
logs/          # 로그 파일
scripts/       # 유틸리티 스크립트
reports/       # 백테스트 결과 보고서
```

## 설정 파일

- `.env`: 환경변수 (API 키, 계좌정보, 전략 파라미터)
- `llm_config.json`: LLM 모델 설정
- `config.py`: 기본 설정값

## 언어 규칙

- 모든 대화와 응답은 **한국어**로 작성할 것
- 코드 주석은 한국어 또는 영어 가능
- 커밋 메시지는 한국어로 작성

## 주의사항

- KIS API는 TPS 제한이 엄격함 - 루프에서 API 호출 시 `time.sleep()` 필수
- Mock 모드(`openapivts`)와 Production 모드 구분 필요
- 토큰은 24시간마다 갱신됨 (`token.json` 캐시 사용)
- 위험 종목 필터링: `iscd_stat_cls_code`, `mrkt_warn_cls_code` 체크 필수

## 백테스트 및 최적화 

### 데이터 소스

- **DuckDB 경로**: `/home/longman6/projects/stock-collector/data/stock.duckdb`
- **스키마 문서**: `/home/longman6/projects/stock-collector/docs/01-DATABASE-SCHEMA.md`
- 데이터 조회 시 위 DuckDB에서 우선적으로 찾을 것

### 결과 저장

- **보고서 위치**: `reports/` 디렉토리에 마크다운(`.md`) 파일로 저장
- **요약본**: `reports/summary.md`에 요약 내용 작성
  - 각 보고서의 출처 파일 링크를 반드시 포함할 것
  - 예: `[RSI 최적화 결과](./optimization_report_2024-01-15.md)`

### 보고서 형식

```markdown
# 백테스트/최적화 보고서 - [날짜/제목]

## 요약
- 테스트 기간: YYYY-MM-DD ~ YYYY-MM-DD
- 총 수익률: X.XX%
- 최대 낙폭(MDD): X.XX%

## 상세 결과
...

## 관련 파일
- 데이터: stock.duckdb
- 설정: [파라미터 정보]
```