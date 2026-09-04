# codex-skills

이 저장소는 Codex가 로그인된 macOS ChatGPT 앱의 ChatGPT Pro를 인라인 코드 분석 파트너로 호출하는 `$gptpro`를 제공합니다.

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
  -> one user-message POST, no tools
  -> exact authenticated conversation readback/import
  -> Codex independent verification
```

Browser, Chrome, Computer Use, 수동 Send/Copy, custom ChatGPT App, Developer Mode, MCP, Secure MCP Tunnel, `gptpro-mcp`, local function, server-tool fallback은 사용하지 않습니다. ChatGPT Pro는 승인된 `outbound.md` 원문만 보며 live worktree, shell, 파일 쓰기, build/test, Git 변경, 임의 filesystem/network 권한은 없습니다.

## 설치

Node.js 22 이상, Python 3.11 이상, `/Applications/ChatGPT.app`이 필요합니다. npm 설치는 없습니다.

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기존 `gptpro-mcp` 설치본이 있으면 installer는 `--legacy-handoff-dir`로 지정한 정확한 package와 terminal authorization, non-live controller, exact-child stop 증거가 모두 확인될 때만 레거시 companion과 descriptor를 Trash로 옮깁니다. 과거 package/receipt는 지우지 않습니다.

자세한 설치는 [standalone 설치](docs/selective-installation.md)와 [Plugin 설치](docs/plugin-installation.md)를 참고하세요.

## 첫 사용

```text
$gptpro review 모드로 src와 tests의 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

처음에는 `desktop-launch` 또는 설치된 `gptpro Launcher.app`으로 전용 Runner를 연 뒤 `desktop-doctor`를 실행합니다. Runner는 별도 owner-only 프로필과 포트 9223을 사용하므로 평소의 ChatGPT 앱을 종료하거나 디버그 옵션으로 다시 열 필요가 없습니다. 이후 exact `outbound.md` 전송과 응답 수집은 자동이며 ChatGPT 화면에서 App을 선택하거나 코드를 붙여넣을 필요가 없습니다. 실시간 수집이 끊겨도 `collect-response`가 같은 메시지 ID와 원문을 가진 기존 대화만 다시 읽으며 prompt를 재전송하지 않습니다.

Private Electron/ChatGPT endpoint는 공개 OpenAI API가 아니므로 앱 업데이트로 깨질 수 있습니다. Runtime은 exact renderer, bridge, DeviceCheck, dynamic model catalog가 다르면 fail closed하고 다른 transport나 model로 fallback하지 않습니다.

## 검증

```bash
python3 -m unittest discover -s gptpro/tests -v
python3 -m unittest discover -s scripts/tests -v
node --test gptpro/tests/*.test.js
python3 gptpro/scripts/validate_structure.py \
  --skill-dir gptpro --mirror plugins/gptpro/skills/gptpro --json
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py gptpro
python3 scripts/manage_skills.py install gptpro --dry-run
git diff --check
```

변경 기록은 [CHANGELOG.md](CHANGELOG.md), source/licensing 판단은 [source inventory](docs/gptpro-source-inventory.md)에 있습니다.
