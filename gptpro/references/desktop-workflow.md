# Desktop consultation workflow

## 역할 분리

```text
Codex
  ├─ 파일 선택, secret 검사, package/hash/승인
  ├─ ChatGPT 앱의 보이는 UI 조작
  ├─ Pro 응답의 독립 검증과 실제 코드 변경
  └─ gptpro-mcp companion
       ├─ immutable repository snapshot
       ├─ Secure MCP Tunnel
       └─ read-only tools and audit
```

ChatGPT App과 Tunnel 프로필은 사용자 계정 단위 연결입니다. 저장소가 바뀔 때마다 다시 만들지 않습니다. 반면 package는 상담 단위 권한이므로 매 요청마다 새로 만들어 정확한 파일·Git SHA·hash·예산·만료를 고정합니다.

## 화면 이름 구분

- `GPT Pro Collaborator`: Codex에서 이 Skill/Plugin을 찾을 때 보이는 이름
- `gptpro`: ChatGPT Plugins와 composer pill에서 확인할 App 이름
- `gpt-pro-collaborator`: owner-only 로컬 binding의 내부 key이며 ChatGPT 화면 이름이 아님

Package의 `connector.app_name`과 submission observation은 ChatGPT 화면에 실제로 보이는 `gptpro`에 결속합니다. Codex Skill 이름이나 내부 key로 대신하지 않습니다.

## 준비와 전송

1. `desktop-doctor`로 ChatGPT 앱 설치, companion binding, 현재 작업의 Computer Use 확인 필요 여부를 관찰합니다. 이 명령은 앱을 열거나 prompt를 보내지 않습니다.
2. `consult`로 Schema 4 `mcp-research` package를 만듭니다. directed `--include` 또는 `--file-list`가 필수입니다.
3. exact-package 또는 유효한 standing approval을 적용합니다.
4. exact package의 Tunnel authorization을 활성화합니다. 활성화는 repository 도구 사용 가능성을 뜻할 뿐, prompt 전송 증거가 아닙니다.
5. `computer-use:computer-use` 지침을 로드한 뒤 macOS ChatGPT 앱을 조작합니다.
6. ChatGPT Plugins에서 `gptpro`를 선택하고 “채팅에서 사용해 보기”를 엽니다. `Work`로 이동했다면 `Chat`으로 전환하고 `gptpro` pill이 유지되는지 확인합니다.
7. 빈 새 general Chat에서 `Chat`, `Pro`, `gptpro`, workspace, model을 화면으로 확인합니다.
8. handoff plan의 exact outbound bytes를 composer에 넣고 SHA-256을 확인합니다.
9. Send를 최대 한 번 호출합니다. 결과가 불명확하면 `ambiguous`로 기록하고 재전송하지 않습니다.
10. visible user turn의 SHA-256이 outbound SHA-256과 같은 경우에만 submitted evidence를 기록합니다.

## 응답 회수

다음 assistant turn 하나만 대상입니다. generation 완료, Stop 버튼 부재, error card 부재, copy action 성공을 화면으로 확인합니다. 응답은 canonical text와 hash로 저장하고 package marker wrapper는 로컬에서 결정적으로 만듭니다.

응답이 아직 생성 중이면 같은 Chat을 읽는 collection만 재시도할 수 있습니다. prompt resend, 새 Chat 생성, 모델 변경, 다른 channel fallback은 허용되지 않습니다.

이 설계에는 숨은 응답 monitor나 heartbeat가 없습니다. Codex 작업이 종료된 뒤 ChatGPT 앱 이벤트로 자동 wake하는 계약도 없습니다. 현재 작업 안에서 60초 이하의 bounded poll을 사용하거나, 사람에게 Chat을 그대로 두고 다시 `$gptpro` 수집을 요청하도록 안내합니다.

## 사용하지 않는 기술

- Browser/Chrome/chatgpt.com 자동화
- CDP와 `--remote-debugging-port`
- Electron `app.asar`, renderer, preload, bridge, IPC
- private ChatGPT backend endpoints
- cookie/token/localStorage/session 추출
- 자동 로그인, MFA, CAPTCHA

Electron이라는 구현 세부는 화면에 보이는 ChatGPT 앱을 식별하는 데만 간접적으로 존재합니다. 내부 계약은 사용하지 않으므로 앱 업데이트가 renderer 구조를 바꿔도 credential 노출이나 조용한 오동작 대신 visible UI capability failure로 멈춥니다.
