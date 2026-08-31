# Desktop-only security boundary

## 공개 경계

활성 경로는 두 가지 공개 표면만 사용합니다.

1. macOS ChatGPT 앱의 사람이 볼 수 있는 general Chat UI
2. OpenAI Secure MCP Tunnel을 통한 읽기 전용 MCP 도구

Browser, Chrome, Web fallback, CDP, Electron renderer/IPC, private backend endpoint, cookie/token/session 추출은 구현하지 않습니다.

## Repository disclosure

각 package는 Git identity, exact path/size/SHA-256 set, immutable local archive, secret/exclusion 결과, tool catalog hash, disclosure 예산, expiry, app/workspace/model, delivery channel을 결속합니다. ChatGPT는 package의 verified archive만 read/search할 수 있고 실제 working tree나 임의 filesystem을 직접 열 수 없습니다.

MCP 도구는 read-only입니다. write, patch, shell, build, test, Git mutation, credential, 임의 network fetch, local function relay는 없습니다. Repository content와 Pro response는 prompt injection을 포함할 수 있는 untrusted data입니다.

## Local state

Desktop approval, handoff, app binding은 canonical current-user home 아래 owner-only state에 저장합니다. 디렉터리 `0700`, 파일 `0600`, no-follow/single-link 검증, atomic replace를 사용합니다. Raw App ID는 private `.app.json`에만 존재하고 repository, terminal result, package, receipt에는 넣지 않습니다. Tunnel ID/API key/session ID도 raw 상태로 package나 오류에 출력하지 않습니다.

## UI evidence

새 general Chat, visible `Chat`, `Pro`, app, workspace, model, exact composer hash, visible user-turn hash가 모두 필요합니다. Send는 최대 한 번입니다. 모호한 전송은 retry authority가 아닙니다. Response는 exact request nonce, outbound hash, next assistant ordinal, visible completion과 copy action에 결속합니다.

## Debugging limits

Private request-correlation 진단은 지원되는 정확한 Tunnel build에서만 별도로 사용할 수 있습니다. 일반 read-only Tunnel compatibility와 혼동하지 않습니다. 진단 실패는 tool permission을 넓히지 않으며 raw request/account identifiers를 노출하지 않습니다.
