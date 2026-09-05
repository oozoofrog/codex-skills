# codex-skills

이 저장소는 Codex가 로그인된 macOS ChatGPT 앱의 ChatGPT Pro를 인라인 코드 분석 파트너로 호출하는 `$gptpro`와 Swift 의미론 탐색용 `swift-intelligence` Plugin을 제공합니다. `$gptpro`는 사용자가 명시적으로 요청한 plan, ask, review, debug, architecture 작업에만 실행되며 일반 Codex 작업이나 OpenAI API 호출에서는 자동 호출되지 않습니다.

## v0.6 흐름

```text
Codex $gptpro
  -> directed file selection + secret/path scan
  -> immutable Schema 6 package
  -> exact outbound.md, maximum 256 KiB
  -> exact or bounded standing approval v4
  -> isolated gptpro Runner profile + loopback-only CDP
  -> exact ChatGPT renderer while the ordinary app remains untouched
  -> exact gpt-5-6-pro, normal Chat
  -> one user-message POST with no tool definitions or capabilities
  -> signed WebSocket handoff, completion, and import
  -> conditional exact current-branch proof when compact branch provenance is ambiguous
  -> Codex independent verification
```

`gptpro`는 Browser, Chrome, Computer Use, 수동 Send/Copy, custom ChatGPT App, Developer Mode, MCP, Secure MCP Tunnel, `gptpro-mcp`, local function, server-tool fallback을 사용하지 않습니다. ChatGPT Pro는 승인된 `outbound.md` 원문만 보며 live worktree, shell, 파일 쓰기, build/test, Git 변경, 임의 filesystem/network 권한은 없습니다.

`swift-intelligence`는 Xcode의 SourceKit-LSP로 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 읽기 전용으로 조회합니다. MCP 서버가 필요한 Plugin이므로 `plugins/swift-intelligence/`에만 제공합니다. Python 3 외의 Python 패키지나 외부 MCP 바이너리를 추가로 설치하지 않습니다.

## 설치

Node.js 22 이상, Python 3.11 이상, `/Applications/ChatGPT.app`이 필요합니다. npm 설치는 없습니다.

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기존 `gptpro-mcp` 설치본이 있으면 installer는 `--legacy-handoff-dir`로 지정한 정확한 package와 terminal authorization, non-live controller, exact-child stop 증거가 모두 확인될 때만 레거시 companion과 descriptor를 Trash로 옮깁니다. 과거 package/receipt는 지우지 않습니다.

자세한 설치는 [standalone 설치](docs/selective-installation.md)와 [Plugin 설치](docs/plugin-installation.md)를 참고하세요.

Swift Intelligence는 marketplace 등록 후 Plugin으로 설치합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add swift-intelligence@codex-skills
```

Swift Intelligence 설치 후 Codex를 다시 시작하고 새 작업을 여십시오. 자세한 요구 사항과 사용법은 [Swift Intelligence 설치 및 사용](plugins/swift-intelligence/docs/installation-and-usage.md)을 참고하세요.

## 첫 사용

```text
$gptpro review 모드로 src와 tests의 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

처음에는 `desktop-launch` 또는 설치된 `gptpro Launcher.app`으로 전용 Runner를 연 뒤 `desktop-doctor`를 실행합니다. Runner는 별도 owner-only 프로필과 포트 9223을 사용하므로 평소의 ChatGPT 앱을 종료하거나 디버그 옵션으로 다시 열 필요가 없습니다. 이후 exact `outbound.md`는 한 번만 POST되고, 응답은 POST가 반환한 signed WebSocket topic의 `recovered`/`catchups`/`delta`/`done`과 최종 assistant 증거로 자동 저장됩니다. tool-role 후보 또는 pre-handoff assistant/delta 연속 상태로 branch provenance가 불명확하면 signed 완료 후 알려진 conversation의 current branch를 최대 30초 GET으로 교차검증하며 응답 자체는 signed stream에서만 가져옵니다. Handoff 없는 직접 completion fallback은 없습니다. 2026-09-05 Desktop `26.901.31953`에서 새 승인 canary의 단일 POST, signed 완료, 조건부 branch proof, 자동 import와 독립 evaluation을 통과했습니다. 별도 `collect-response`는 사용하지 않았으며, 이 결과는 한 번의 중단 없는 첫 응답에 대한 증거입니다. 수집이 끊기면 `collect-response`가 같은 메시지 ID와 원문을 가진 기존 대화만 GET으로 읽으며 prompt를 재전송하지 않습니다.

Private Electron/ChatGPT endpoint는 공개 OpenAI API가 아니므로 앱 업데이트로 깨질 수 있습니다. Runtime은 exact renderer, bridge, DeviceCheck, dynamic model catalog가 다르면 fail closed하고 다른 transport나 model로 fallback하지 않습니다.

## 검증

```bash
python3 -m unittest discover -s gptpro/tests -v
python3 -m unittest discover -s plugins/swift-intelligence/tests -v
python3 -m unittest discover -s scripts/tests -v
node --test gptpro/tests/*.test.js
python3 gptpro/scripts/validate_structure.py \
  --skill-dir gptpro --mirror plugins/gptpro/skills/gptpro --json
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py gptpro
python3 scripts/manage_skills.py install gptpro --dry-run
git diff --check
```

변경 기록은 [CHANGELOG.md](CHANGELOG.md), source/licensing 판단은 [source inventory](docs/gptpro-source-inventory.md)에 있습니다.
