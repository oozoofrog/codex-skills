# gptpro v0.6 source inventory

확인일: 2026-09-05

## Reference archive

- 파일: `TalkFile_chatgpt-web.zip.zip`
- SHA-256: `a5134d2a2936e33fa490f7d1d68654b1bdca17ea9c9c8f1ccacb57cbe7bcd52a`
- 관찰된 package: private `chatgpt-web-pi-extension` 1.0.0
- 포함 dependency: `ws` 8.21.3 (MIT)
- 비-`ws` source: provenance와 redistribution license 불명확

Archive source는 저장소에 복사하지 않았습니다. CDP target discovery, Desktop bridge request/stream, DeviceCheck, dynamic catalog, conversation 요청, signed topic subscription의 wire shape만 분석하고 clean-room으로 구현했습니다. Pi provider registration, Pi message types, subagent integration, vendored `ws`, `node_modules`는 포함하지 않습니다. CDP에는 Node.js 22 이상 내장 `WebSocket`을 사용하고 signed response topic은 ChatGPT renderer의 native `WebSocket`으로 연결합니다.

MIT-licensed [`miuuyy/codex-chatgpt-web`](https://github.com/miuuyy/codex-chatgpt-web) commit `985e0d91b73af2385b8c2142ccf58695b66297a5`의 turn identity와 `MutationObserver` 설계도 검토했지만, 2026-09-04 실제 ChatGPT Desktop `26.901.31953` outer renderer에는 해당 turn/Stop/Copy selectors가 없어 완료를 감지하지 못했습니다. 이 observer 실험은 제거했고 외부 launcher/runtime도 포함하거나 호출하지 않습니다.

## v0.4에서 확인한 한계

Reference archive는 `local_function_signatures`와 tool-result continuation을 사용하지만, 로그인된 현재 서비스에서 그 경로가 성공했다는 재현 가능한 receipt를 제공하지 않습니다.

2026-09-01 ChatGPT Desktop `26.825.51511`의 live `gpt-5-6-pro` catalog는 서버 도구 labels만 표시하고 local-function capability를 명시하지 않았습니다. 승인된 두 tool-loop 시도는 주입한 `gptpro_*` 함수 대신 서버 측 route를 선택해 중단됐습니다. 따라서 local-function 구조를 반복 조정하는 대신 v0.5에서 해당 경로를 제거했습니다.

현재 요청 payload에는 `local_function_signatures`가 없고 tool-result stdin/multi-round continuation도 없습니다. Codex가 비밀·경로 검사를 마친 선택 코드 원문을 `outbound.md` 하나에 넣어 한 번 전송합니다. 어떤 non-`all` recipient도 `UNEXPECTED_TOOL_ROUTE`로 중단합니다.

## Current private Desktop boundary

현재 ChatGPT Desktop은 archive에서 본 `sendMessageFromView` HTTP 경로를 `HTTP requests must use the HTTP fetch service.`로 거부했습니다. clean-room runtime은 renderer `connect-app-host` MessagePort와 app-host `httpFetch.fetch/cancel`, renderer-native WebSocket forwarding에 필요한 최소 RPC만 구현합니다. 성공한 `POST /f/conversation` 단일 전송 경로는 유지합니다. 현재 Desktop `26.901.31953` bundle과 handoff frame은 `turn_exchange_id`, `conversation-*` topic, `/celsius/ws/user`, authenticated `recovered`/`catchups`, `conversation-turn-stream`의 `stream-item`/`done` 계약을 사용합니다. 설치된 번들의 RPC result-release 순서, SSE content-type 및 60초 open/idle 경계, signed-topic 5초 initial-item/30초 idle 경계도 대조했습니다. 번들의 handler는 raw `stream_handoff`를 일반 compact payload decode보다 먼저 판별하므로 clean-room runtime과 fixture도 같은 순서를 사용합니다. 새 primary completion path는 signed stream만 검증하며 handoff 없는 직접 completion fallback은 없습니다. Tool-role 후보, pre-handoff assistant evidence, 또는 signed delta continuation으로 branch provenance가 불명확하면 signed `done` 뒤 이미 알려진 conversation 하나의 current branch를 최대 30초 GET으로 교차검증하며, 응답 내용과 completion source는 signed stream에 남습니다. 별도 `collect-response`는 명시적 GET-only recovery입니다. 앱 번들 코드는 복사하거나 저장소에 포함하지 않았습니다.

2026-09-05 로그인된 실제 실행에서 package `20260904T150045Z-ask-731e99b6`의 POST는 한 번만 수행됐고, ChatGPT UI에서 정확한 package/model metadata와 `gptpro signed-stream E2E complete` Pro 응답이 확인됐습니다. 같은 응답은 이후 GET-only `collect-response`로 exact message correlation 후 import/evaluation됐습니다. 그러나 그 실행의 `consult`는 signed `stream_handoff`를 자동 수집하지 못했고, 열린 parent stdin과 지연된 stderr drain이 실제 child terminal error를 숨겼습니다. 이 process-lifecycle 문제와 RPC result-release 순서는 이후 수정됐습니다. 이 package의 GET 복구는 signed 자동 완료 증거가 아니며 기존 package는 재전송하지 않습니다.

수정 후 새 package `20260904T153036Z-ask-ee8a09a5`도 POST 한 번으로 정확한 canary 응답을 생성했습니다. 이번에는 숨은 정체 없이 `response_stream`에서 `UNEXPECTED_TOOL_ROUTE`가 즉시 보고됐고, GET-only recovery가 같은 최종 branch의 `tool_routes=0`을 확인했습니다. Partial assistant 객체의 누락된 `recipient`를 non-`all`로 조기 판정하던 문제는 수정했지만, 그것만으로는 실제 실패 원인이 모두 설명되지 않았습니다. 이 package도 재전송하지 않았습니다.

다음 승인 package `20260904T154319Z-ask-aeb1c438`도 exact `gpt-5-6-pro`에 POST 한 번만 수행했고 UI와 GET-only recovery에서 정확한 `gptpro signed-stream E2E complete` 응답을 확인·import·evaluation했습니다. `consult`는 여전히 `response_stream`의 `UNEXPECTED_TOOL_ROUTE`로 중단됐습니다. 해당 conversation과 최근 동일 유형 대화의 mapping을 read-only로 대조하자 current branch는 user에서 `recipient=all` assistant final로 이어졌고, `role=tool`, `recipient=all`, 빈 text인 Pro 비동기 상태 node는 user의 off-current sibling이었습니다. Branch를 모르는 compact delta 단계에서 모든 tool-role snapshot을 즉시 거부한 것이 직접 원인이었습니다. Runtime은 이제 이 node를 metadata나 author 이름으로 allowlist하지 않고 후보로만 기록한 뒤, signed `done`이 있을 때만 exact current-branch GET으로 deterministic user message, zero-tool branch, signed assistant ID·visible text 일치를 요구합니다. Raw POST SSE를 보존하지 않았으므로 실제 channel 번호와 patch 경계는 미확인입니다. 이 package도 재전송하지 않았으며, 이때까지는 수정 코드의 로그인된 signed-stream E2E가 미확인 상태였습니다.

## Logged-in signed-stream canary passed

2026-09-05 00:15:10–00:15:33 UTC, 새 exact-approved Schema-6 package `20260904T163747Z-ask-ffe9bcc6`가 Desktop `26.901.31953`, exact `gpt-5-6-pro`/`standard`, normal Chat에서 성공했습니다. 공개 범위는 `.gitignore` 1개 38 bytes, diff 0 bytes, supplement 없음이며 outbound 2,689 bytes의 SHA-256은 `a394f0636a63ab3559d2898e77b72aa2d6c55c806107decf22cc389dd7c74f35`입니다.

- receipt: `submission_dispatching` 1회 → `submission_dispatched` 1회 → `response_captured` 1회 → `response_imported` 1회 → `evaluated` 1회.
- `consult` exit 0, `completion_source=signed-stream-handoff-v1`, `signed_assistant_evidence=true`, signed topic hash 있음.
- `tool_route_candidate_observed=true` 때문에 조건부 `authenticated-exact-message-readback-v1` current-branch proof 수행. Signed assistant ID·본문 일치, `tool_routes=0`, `pre_handoff_assistant_observed=false`, `signed_delta_continuation_observed=false`.
- raw response는 정확히 `gptpro signed-stream E2E complete`; SHA-256 `adc56a93df02b592340759625b35927bff02f969660cb76509d6234c5ed279c6`. 자동 import 뒤 독립 비교 평가 `accepted`, 최종 phase `evaluated`, response count 1.
- 별도 `collect-response`, 자동 재전송, 설치, commit, push 없음.

이는 runtime의 authenticated subscription, signed delta 및 terminal `done` 필수 gate를 통과한 중단 없는 첫 응답 1건의 실행·receipt 증거입니다. Raw WebSocket/SSE frame이나 개별 delta/catchup 개수는 보존하지 않았으므로 독립 packet trace 또는 non-empty catchup 실행 증거로 해석하지 않습니다. Catchup/recovery shape는 fixture로 검증하며 socket reconnect/offset resume, 다중 turn, 일반 답변 품질은 이번 canary의 검증 범위가 아닙니다.

`connect-app-host`, `httpFetch`, renderer WebSocket, `window.electronBridge`의 environment/DeviceCheck probe, private model/attestation/conversation/signing endpoints와 stream/conversation-detail format은 OpenAI public API가 아닙니다. 앱 업데이트나 WebSocket host 변경 시 probe, signed-stream validation 또는 recovery correlation이 명시적으로 실패할 수 있습니다.

설치된 Desktop의 signed-topic client는 마지막 offset을 보존하고 socket 단절 시 재구독할 수 있습니다. 현재 clean-room runtime은 terminal `done` 전 socket close를 ambiguous로 fail closed하며 offset resume은 구현하지 않았습니다. 이 경우에도 POST는 반복하지 않고 `collect-response`만 사용합니다. 중단 없는 signed-stream E2E와 별개로, transient disconnect resume은 남은 private-contract 호환성 위험입니다.

Cookies, login/session/OAuth token, Authorization value, password, MFA code, raw account secret를 읽거나 저장하기 위한 코드는 없습니다.

## v0.6 isolated Runner verification

macOS에서 평소의 ChatGPT 프로세스를 그대로 둔 채 `/Applications/ChatGPT.app`의 두 번째 프로세스를 전용 `--user-data-dir`와 loopback port 9223으로 실행할 수 있음을 확인했습니다. 두 프로세스는 동시에 유지됐고, 전용 프로세스에서 exact `app://-/index.html` target, Desktop bridge, DeviceCheck와 로그인된 dynamic model catalog를 확인했습니다.

따라서 v0.6은 ChatGPT renderer를 추출하거나 별도 로컬 웹서버로 복제하지 않습니다. 별도 process/profile이면 기본 앱 실행환경을 제한하지 않는다는 실제 요구를 충족하며, proprietary app assets와 private authentication/attestation을 다시 배포하는 더 큰 구조가 필요하지 않기 때문입니다. 이것은 OpenAI와 독립적인 ChatGPT 구현이 아니라, 설치된 signed ChatGPT app을 격리된 실행환경으로 여는 gptpro 전용 Runner입니다.

## 2026-09-05 implementation review and second live response

Exact-approved review package `20260905T003158Z-review-ac3b7c63` sent a 261,496-byte outbound containing ten selected current source files, their diff, and three bounded review supplements. The outbound SHA-256 was `5c574d970ae41d077e472711193db4363995b153a7cf4cc96f89d79f1fd445ce`. Runtime receipts recorded one dispatch boundary, one dispatch, signed completion, and automatic import; no standalone recovery or resend was used for primary completion. The 24,117-byte Korean Markdown response has SHA-256 `ea62251661970d58b8f55e271b85a724ef4ccbf2b090a018ffdf1cd641d89f85`.

A separate read-only verification then performed one list GET and one detail GET, with POST disabled in the verification harness. The completed assistant text, conversation/message identity hashes, and zero-tool branch matched the signed capture exactly. This verifies a realistic-length review response in addition to the earlier 33-byte canary. It is not an independent packet trace, a forced-interruption/reconnect test, or proof of an app-internal backend model implementation.

The external review correctly identified installer publication rollback data loss and mixed valid/malformed SSE being partially accepted. Both were independently reproduced before their fixes and covered by failure-injection regressions. This live review ran before those two fixes; subsequent approved post-fix and installed-Skill E2E results are recorded below.

The review also proposed equating POST `turn_exchange_id` and signed-stream `turn_id`. Read-only inspection of `/Applications/ChatGPT.app/Contents/Resources/app.asar` (SHA-256 `4b385ffce845bb319a1769a3cb59751e1a8f157bab79f5018ba51d83f9e6df4e`), entry `webview/assets/app-initial-caa927532ffb.js`, found the installed handler `pEr` validating the handoff and extracting only the subscription topic, then `mEr` consuming that topic. It did not establish an equality relation between those IDs. gptpro preserves this topic-based contract instead of adding an unsupported equality check. The private topic binding remains a service-compatibility assumption. No proprietary source was copied into this repository.

At this review checkpoint, exact legacy terminal evidence had been located and the real destination's read-only installation dry-run had passed, but actual installation and Launcher update had not yet been performed. They were completed in the subsequent verification below. The recent-20-conversation GET recovery limit and installation hard-kill window remain unresolved.

Codex recorded `partially-accepted` after the independent reproductions, local fixes, GET-only response comparison, and final automated checks. The review package is `evaluated` with exactly one response. This verdict accepts the demonstrated defects and validation limits, not the unsupported claim that the two private turn IDs must be equal or that every suggested extension is mandatory for this consultation.

## 2026-09-05 post-fix and installed-Skill verification

Two newly approved synthetic-repository consultations verified the unchanged final runtime after the review fixes. Package `20260905T024353Z-ask-2944ee79` sent 4,028 outbound bytes and automatically captured 462 response bytes through `signed-stream-handoff-v1`, with conditional exact-current-branch proof. Package `20260905T024353Z-ask-8342e5a8` sent 4,067 outbound bytes; the test then terminated only the controller-owned Node collector after the successful POST reached `stream_handoff`. The package became ambiguous, a repeat consultation was blocked before child creation, and explicit GET-only `collect-response` recovered the same 6,049-byte answer without another POST. Both packages have exactly one dispatch, capture, import, and accepted independent evaluation. Completed-package repeat consultation and collection were also rejected without child creation or package mutation.

The local Skill and Launcher were subsequently updated after exact legacy terminal authorization and child-stop evidence were verified. Source, Plugin mirror, and installed Skill matched tree SHA-256 `2d6937d7a72e7345a0f9d5d8d9046d6c9bfb02bb279d86abff1dc08fb71421ac`; Launcher status reported `current=true`. Ordinary ChatGPT and the isolated Runner remained running without an app restart.

A fresh Codex task then used only the installed Skill for approved package `20260905T032121Z-ask-e1a75ebf`: two tracked synthetic files, 3,750 outbound bytes, exact `gpt-5-6-pro`/`standard`, and normal Chat. One dispatch produced a 535-byte signed response, automatic import, zero current-branch tool routes, and accepted independent evaluation. Raw/wrapped hashes and the complete receipt chain were independently checked, and the installation tree hash was unchanged. No standalone recovery or resend was used in this installed-Skill consultation. Its fixture pinned a Git tree rather than a commit and had no diff, so it is not evidence for every repository shape.

On the same runtime tree, Python 3.14.7 and 3.11.15 each passed 67 Skill tests and 18 installer tests. Node 26.7.0 passed 55 tests in each standalone/mirror package. Structure, syntax/compile, Skill quick validation, mirror checks, and whitespace checks passed. Running all packaged Python tests from the installed directory still exposes one distribution-test limitation: it expects the repository-level `scripts/manage_skills.py` outside the installed Skill. The 64 installed runtime/failure-reporting tests and 55 installed Node tests passed; this packaging-test error is not represented as a fully passing installed suite.

Remaining boundaries: a hard kill between the installer's two directory renames can leave the target absent with its previous bytes retained in a backup; automatic crash recovery is not implemented. Legacy-retirement retry was exercised only in an isolated fixture. GET recovery searches the most recent 20 conversations. The controlled Node collector interruption does not prove ChatGPT app-crash, OS-restart, network-disconnect, or signed WebSocket reconnect/offset-resume behavior. Private Desktop compatibility remains specific to the observed contract.

## Repository-owned code

Git selection, secret/path scanning, exact inline snapshot construction and verification, approval, receipt, and advisory evaluation are repository-owned clean-room code. Schema 6 binds `inline-immutable-snapshot`, exact outbound/system hashes, 256 KiB maximum, `desktop-electron`, normal Chat, and exact model ID. 현재 release는 Schema 6만 검증·전송하며 Schema 3/4/5 파일은 변경하지 않습니다.
