# gptpro v0.5 Electron inline implementation directive

> 상태: v0.5의 inline 전송 계약 기록입니다. v0.6은 전송 계약을 유지하되, 평소의 ChatGPT 앱 대신 전용 profile과 loopback port 9223을 사용하는 두 번째 signed ChatGPT process를 Runner로 실행합니다. 기본 ChatGPT 앱의 종료·재실행은 요구하지 않습니다.

문서 상태: 구현 기준

## 목표

어느 로컬 Git 저장소에서든 사용자가 `$gptpro`를 명시적으로 호출하면 Codex가 로그인된 ChatGPT Desktop의 exact Pro 모델과 상담한다. Codex가 선택·검사한 코드 원문은 하나의 승인된 inline message로 전달하고, Codex는 응답을 독립 검증한 뒤에만 repository를 수정한다.

## 단일 실행 경로

```text
Schema 6 inline immutable package
  -> exact/standing approval v4
  -> loopback CDP
  -> exact app://-/index.html renderer
  -> Desktop-owned auth/DeviceCheck
  -> exact gpt-5-6-pro
  -> one normal-Chat user message
  -> response receipt/import/evaluation
```

Browser, Computer Use, visible/manual handoff, custom ChatGPT App, Developer Mode, MCP, Secure MCP Tunnel, separate `gptpro-mcp`, local function, server tool은 사용하지 않는다. 현재 release는 Schema 6만 검증·전송하며 Schema 3/4/5 파일은 변경하지 않는다.

## 핵심 불변식

1. Approval은 exact manifest, outbound/system hashes, channel, history mode, inline format, exact model에 결속한다.
2. CDP는 current-user ChatGPT process의 loopback endpoint와 exact renderer만 허용한다.
3. Credential/session extraction을 하지 않는다.
4. ChatGPT에 보내는 유일한 repository context는 secret/path 검사를 통과한 exact `outbound.md`이며 최대 262,144 bytes다.
5. 초과 context는 요약·분할·누락하지 않고 파일 선택을 줄인다.
6. Request에는 local function signature가 없고 모든 tool route를 거부한다.
7. POST 이후 모호한 실패는 자동 재전송하지 않는다.
8. Raw response와 deterministic wrapper를 별도 hash로 보존한다.
9. Pro는 advisory이고 Codex가 현재 파일과 tests로 검증한다.
10. Private Desktop contract mismatch는 E2E와 release blocker다.
11. 자동 수집이 끊겼을 때 사람이 기존 대화를 확인할 수 있도록 normal Chat을 사용한다.
12. 대화 continuation은 지원하지 않으며 후속 질문도 새 package로 준비한다.
