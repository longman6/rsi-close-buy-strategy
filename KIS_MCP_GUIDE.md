# 한국투자증권(KIS) MCP 설치 및 활용 가이드

사용자님께서 요청하신 [한국투자증권 API Tools](https://apiportal.koreainvestment.com/tools-sample) 페이지를 분석한 결과, **KIS Code Assistant MCP**라는 유용한 도구를 발견했습니다.

이 도구는 Claude와 같은 AI 모델이 한국투자증권 API 문서를 실시간으로 참조하여, 개발자에게 **정확한 API 명세와 파라미터 정보**를 제공해주는 역할을 합니다.

## 1. MCP란 무엇인가요?
**MCP (Model Context Protocol)**는 AI 모델이 외부 데이터나 도구와 안전하게 연결되도록 돕는 표준 프로토콜입니다.
- **KIS Code Assistant MCP**: AI가 한투증권 API 문서를 학습/검색하여 코딩을 도와줍니다. "삼성전자 현재가 조회 API 어떻게 써?"라고 물으면 정확한 파라미터(`/uapi/...`)를 알려줍니다.
- **KIS Trading MCP**: AI가 직접 매매 주문을 실행할 수 있게 해줍니다. (현재 우리가 만든 `main.py`와 역할 중복, 보안상 권장하지 않음)

> **결론**: 우리는 이미 `kis_client.py`를 통해 매매 로직을 완성했으므로, 개발 과정에서 API 정보를 쉽게 찾을 수 있는 **'KIS Code Assistant MCP'**만 설정하는 것을 추천합니다.

## 2. 설치 방법 (사용자 로컬 환경)
이 MCP는 제가 있는 서버가 아니라, 사용자님께서 사용하시는 **Claude Desktop App** 또는 **MCP를 지원하는 IDE(Cursor 등)**에 설정해야 동작합니다.

### A. 사전 준비
1. **Node.js 설치**: 사용자님의 PC에 Node.js(v18 이상)가 설치되어 있어야 합니다.
2. **Claude Desktop**: 최신 버전의 Claude Desktop App이 필요합니다.

### B. 설정 파일 수정
Claude Desktop의 설정 파일(`claude_desktop_config.json`)을 열고 아래 내용을 추가해주세요.

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**추가할 내용:**
```json
{
  "mcpServers": {
    "kis-code-assistant": {
      "command": "npx",
      "args": [
        "-y",
        "@kis-open-api/kis-code-assistant-mcp"
      ]
    }
  }
}
```
*(참고: 패키지명은 `@kis-open-api/kis-code-assistant-mcp` 또는 `@smithery/cli`를 통한 실행 방식일 수 있으니, 공식 문서의 최신 커맨드를 확인하세요. 위 설정은 일반적인 npx 실행 예시입니다.)*

### C. Smithery를 이용한 간편 설치 (추천)
만약 Smithery CLI를 사용하신다면 터미널에서 아래 한 줄로 설치가 가능합니다:
```bash
npx -y @smithery/cli install @KISOpenAPI/kis-code-assistant-mcp --client claude
```

## 3. 활용 예시
설치가 완료되면 Claude에게 다음과 같이 질문할 수 있습니다:
> "한투 API로 해외주식 기간별 시세 가져오는 파라미터 알려줘"
> "주식 잔고 조회 API의 응답 필드 설명해줘"

그러면 MCP가 최신 API 포털의 문서를 바탕으로 **정확한 필드명(예: `output1`, `pdno`)과 설명**을 답변해줍니다. 이는 향후 봇 기능을 확장할 때 매우 유용할 것입니다.

---
**참고**: 현재 서버에 이 MCP를 설치하는 것은 의미가 없습니다. MCP는 **사용자님과 대화하는 AI(Claude)**에 지식을 주입하는 도구이기 때문입니다.
