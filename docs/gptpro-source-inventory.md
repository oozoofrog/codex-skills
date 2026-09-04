# gptpro v0.6 source inventory

확인일: 2026-09-04

## Reference archive

- 파일: `TalkFile_chatgpt-web.zip.zip`
- SHA-256: `a5134d2a2936e33fa490f7d1d68654b1bdca17ea9c9c8f1ccacb57cbe7bcd52a`
- 관찰된 package: private `chatgpt-web-pi-extension` 1.0.0
- 포함 dependency: `ws` 8.21.3 (MIT)
- 비-`ws` source: provenance와 redistribution license 불명확

Archive source는 저장소에 복사하지 않았습니다. CDP target discovery, Desktop bridge request/stream, DeviceCheck, dynamic catalog와 conversation 요청 구조만 분석하고 clean-room으로 구현했습니다. Pi provider registration, Pi message types, subagent integration, vendored `ws`, `node_modules`는 포함하지 않습니다. CDP에는 Node.js 22 이상 내장 `WebSocket`을 사용합니다.

MIT-licensed [`miuuyy/codex-chatgpt-web`](https://github.com/miuuyy/codex-chatgpt-web) commit `985e0d91b73af2385b8c2142ccf58695b66297a5`의 turn identity와 `MutationObserver` 설계도 검토했지만, 2026-09-04 실제 ChatGPT Desktop `26.901.31953` outer renderer에는 해당 turn/Stop/Copy selectors가 없어 완료를 감지하지 못했습니다. 이 observer 실험은 제거했고 외부 launcher/runtime도 포함하거나 호출하지 않습니다.

## v0.4에서 확인한 한계

Reference archive는 `local_function_signatures`와 tool-result continuation을 사용하지만, 로그인된 현재 서비스에서 그 경로가 성공했다는 재현 가능한 receipt를 제공하지 않습니다.

2026-09-01 ChatGPT Desktop `26.825.51511`의 live `gpt-5-6-pro` catalog는 서버 도구 labels만 표시하고 local-function capability를 명시하지 않았습니다. 승인된 두 tool-loop 시도는 주입한 `gptpro_*` 함수 대신 서버 측 route를 선택해 중단됐습니다. 따라서 local-function 구조를 반복 조정하는 대신 v0.5에서 해당 경로를 제거했습니다.

현재 요청 payload에는 `local_function_signatures`가 없고 tool-result stdin/multi-round continuation도 없습니다. Codex가 비밀·경로 검사를 마친 선택 코드 원문을 `outbound.md` 하나에 넣어 한 번 전송합니다. 어떤 non-`all` recipient도 `UNEXPECTED_TOOL_ROUTE`로 중단합니다.

## Current private Desktop boundary

현재 ChatGPT Desktop은 archive에서 본 `sendMessageFromView` HTTP 경로를 `HTTP requests must use the HTTP fetch service.`로 거부했습니다. clean-room runtime은 renderer `connect-app-host` MessagePort와 app-host `httpFetch.fetch/cancel`에 필요한 최소 RPC만 구현합니다. 실제 E2E에서 동일 app-host 세션의 deterministic message ID 기반 conversation GET이 완성 응답을 정확히 회수했으므로, POST reader를 유지한 채 이 GET을 primary completion path로 사용합니다. 앱 번들 코드는 복사하거나 저장소에 포함하지 않았습니다.

`connect-app-host`, `httpFetch`, `window.electronBridge`의 environment/DeviceCheck probe, private model/attestation/conversation endpoints와 conversation-detail format은 OpenAI public API가 아닙니다. 앱 업데이트 시 probe 또는 exact response correlation이 명시적으로 실패할 수 있습니다.

Cookies, login/session/OAuth token, Authorization value, password, MFA code, raw account secret를 읽거나 저장하기 위한 코드는 없습니다.

## v0.6 isolated Runner verification

macOS에서 평소의 ChatGPT 프로세스를 그대로 둔 채 `/Applications/ChatGPT.app`의 두 번째 프로세스를 전용 `--user-data-dir`와 loopback port 9223으로 실행할 수 있음을 확인했습니다. 두 프로세스는 동시에 유지됐고, 전용 프로세스에서 exact `app://-/index.html` target, Desktop bridge, DeviceCheck와 로그인된 dynamic model catalog를 확인했습니다.

따라서 v0.6은 ChatGPT renderer를 추출하거나 별도 로컬 웹서버로 복제하지 않습니다. 별도 process/profile이면 기본 앱 실행환경을 제한하지 않는다는 실제 요구를 충족하며, proprietary app assets와 private authentication/attestation을 다시 배포하는 더 큰 구조가 필요하지 않기 때문입니다. 이것은 OpenAI와 독립적인 ChatGPT 구현이 아니라, 설치된 signed ChatGPT app을 격리된 실행환경으로 여는 gptpro 전용 Runner입니다.

## Repository-owned code

Git selection, secret/path scanning, exact inline snapshot construction and verification, approval, receipt, and advisory evaluation are repository-owned clean-room code. Schema 6 binds `inline-immutable-snapshot`, exact outbound/system hashes, 256 KiB maximum, `desktop-electron`, normal Chat, and exact model ID. 현재 release는 Schema 6만 검증·전송하며 Schema 3/4/5 파일은 변경하지 않습니다.
