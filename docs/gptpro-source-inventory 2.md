# gptpro implementation source inventory

확인일: 2026-08-30

## 배포 코드의 출처

| Source | Identity | License | 사용 범위 |
|---|---|---|---|
| 이 저장소의 기존 `gptpro` 구현 | base `15caaba0c5e984277b84b7f43ad27dd46b1bdb62`와 이 feature diff | repository license | package governance, immutable archive, read-only MCP runtime, audit/lifecycle primitives를 재구성 |
| Python standard library | supported Python 3.11+ | Python Software Foundation License | CLI, hashing, JSON, filesystem safety, subprocess lifecycle, tests |
| Codex Computer Use capability | Codex runtime이 현재 task에 제공; source를 vendor하지 않음 | repository 재배포 대상 아님 | visible ChatGPT macOS app의 attended UI observation/control |
| OpenAI Secure MCP Tunnel | 사용자가 별도로 설치·선택하는 official runtime | repository 재배포 대상 아님 | local read-only MCP stdio와 ChatGPT App 사이의 foreground transport |

새 third-party Python/Node dependency와 vendored runtime source를 추가하지 않았습니다. `tunnel-client`는 자동 다운로드, 업데이트, downgrade하지 않습니다.

## Electron/CDP reference

과거 `TalkFile_chatgpt-web.zip`의 설계는 Desktop CDP, renderer bridge, private endpoints, streamed delta decoding 가능성을 검토하기 위한 참고였습니다.

이번 배포에는 해당 archive의 source, `ws`, CDP client, Electron bridge, private ChatGPT endpoint code를 포함하지 않습니다. 이유는 다음과 같습니다.

- non-`ws` source provenance/license가 확인되지 않음
- private Desktop contract가 안정적인 public API가 아님
- debug port와 renderer access가 사용자 보안 경계를 넓힘
- repository access라는 목적은 public read-only MCP 경로로 충족 가능함

따라서 Electron이라는 구현 사실은 앱 존재/visible UI 자동화 이상의 권한으로 사용하지 않습니다.

## 외부 구현 이름

AutoOPT handoff, ChatGPT Pro Line, Cross Review Bridge, `codex-chatgpt-control`, Codex Web GPT Automation, MCPX는 설계 비교 대상으로만 언급되었습니다. 이 feature는 그 프로젝트의 source를 복사하거나 dependency로 포함하지 않으며, 확인되지 않은 repository URL, commit, 또는 license를 배포 근거로 주장하지 않습니다.

## Private diagnostic boundary

Request-correlation의 private admin-log 진단은 기존 exact supported contract에서만 선택적으로 유지됩니다. 일반 read-only Tunnel compatibility와 분리되며 release E2E의 필수 조건이 아닙니다. Raw request IDs, Tunnel IDs, API keys, credentials, cookies, tokens는 저장하거나 출력하지 않습니다.
