# gptpro Desktop-only 구현 지시서

문서 상태: 구현 기준

대상 저장소: `oozoofrog/codex-skills`

기준 commit: `15caaba0c5e984277b84b7f43ad27dd46b1bdb62`

## 목적

사용자가 어느 로컬 Git repository에서든 `$gptpro`를 명시적으로 호출하면 Codex가 로그인된 ChatGPT macOS 앱의 ChatGPT Pro와 읽기 전용으로 협업한다.

중심 요구사항은 Pro가 실제 코드 리소스를 탐색할 수 있다는 것이다. 코드를 prompt나 UI file upload로 모두 밀어 넣는 대신, Codex가 secret scan한 immutable Schema 4 package를 만들고 Secure MCP Tunnel을 통해 고정된 read-only tools만 공개한다.

## 확정 경로

```text
Codex
  -> gptpro Desktop orchestrator
  -> exact installed gptpro-mcp companion
  -> immutable repository package
  -> foreground Secure MCP Tunnel
  -> visible ChatGPT macOS app / ChatGPT plugin `gptpro`
  -> ChatGPT Pro read-only tool calls
  -> visible response
  -> Codex independent evaluation
```

새 실행 경로에는 ChatGPT Web, Chrome extension, browser fallback, CDP, remote debugging, Electron renderer/IPC/private bridge, private ChatGPT backend, cookie/token extraction이 없다.

## Component responsibilities

### gptpro 0.3.x

- explicit-only trigger
- friendly user workflow
- exact companion descriptor verification
- Desktop readiness diagnosis
- delegation to the companion
- independent final evaluation guidance

Base는 MCP runtime을 포함하거나 import하지 않는다.

### gptpro-mcp 0.2.x

- Git root and selected file resolution
- secret/exclude scan
- immutable archive and Git identity
- Schema 4 manifest/state/receipt
- exact approval or standing approval matching
- read-only tool catalog and disclosure budgets
- Tunnel activation/revoke/stop/recovery
- Desktop handoff and observation validation
- response import and evaluation receipt
- legacy offline receipt and migration evidence

## User-global state versus package state

One ChatGPT App/Tunnel profile is configured per user and reused across repositories. It is not recreated per project.

Each consultation creates a new immutable package bound to:

- repository identity and Git SHA
- selected tracked files and hashes
- task/mode/model
- exact app/workspace/profile
- disclosure/tool budgets
- request nonce and outbound hash

Machine-global state is owner-only under the platform state root. Directories use mode `0700`; files use `0600`.

## Approval

Manual exact-package approval remains supported. `gptpro-standing-approval-v2` may reduce prompts across local repositories only when all bounded fields match.

Standing approval never authorizes:

- selected untracked files
- external evidence
- secret findings
- larger path or byte/tool budgets
- changed profile/app/workspace/model
- automatic Send or resend

## Desktop UI contract

Computer Use may operate only the visible ChatGPT macOS app.

Before Send it must observe:

- correct account/workspace
- new general `Chat`, not Work/Project/custom GPT
- `Pro` and exact model/reasoning selection
- exact app
- zero prior turns
- exact prompt hash and request nonce

Send attempt limit is one. Ambiguous submission cannot be retried automatically. The response is the next completed assistant turn matching the nonce. Raw capture and deterministic marker wrapper hashes remain separate.

No hidden response supervisor, heartbeat, browser URL monitor, Electron event hook, or automatic Codex restart is used.

The Codex-facing Skill/Plugin display name `GPT Pro Collaborator`, the ChatGPT-visible plugin name `gptpro`, and the private local binding key `gpt-pro-collaborator` are distinct identities. Package approval and Desktop submission evidence bind the exact ChatGPT-visible name.

## Read-only MCP contract

The ChatGPT-visible catalog remains static:

- `gptpro_workspace_map`
- `gptpro_package_info`
- `gptpro_repo_read`
- `gptpro_repo_search`
- `gptpro_repo_diff`
- `gptpro_artifact_read`
- `gptpro_analysis_status`

There are no repository writes, shell/build/test execution, Git mutation, credentials, arbitrary network access, arbitrary filesystem access, or ChatGPT local-function relay.

External strict UTF-8 documents use explicit `--evidence-file` immutable snapshots. Their source path is not disclosed to ChatGPT.

## Installation

The default repository install command installs the companion first, then base, and records an owner-only exact component descriptor.

```bash
python3 scripts/manage_skills.py install gptpro --update
```

The local apps-only companion binding reads an App ID once from an absolute owner-only file. Raw App ID is stored only in private `.app.json`; repository and receipts contain hashes.

Legacy integrated installs require either exact terminal/child-stop evidence or an explicit residual ownership receipt. `ownership_transferred` never means `exact_child_stop_proven`.

## Acceptance

- Base and companion unit suites pass on current Python and Python 3.11.
- Structure validators and Skill quick validation pass.
- Standalone and Plugin mirrors are byte-identical.
- Tool schema hash is unchanged.
- No browser/CDP/Electron runtime remains.
- `desktop-doctor` is no-send and mutation-free.
- Real Desktop + Tunnel E2E requires a fresh harmless package and package-specific permission; unit tests never require a logged-in account.
- Commit, push, merge, local install, and external Send are separately authorized operations.
