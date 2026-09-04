# codex-skills

이 저장소는 Codex용 `gptpro` 패키지와 Swift 의미론 탐색용 `swift-intelligence` Plugin을 제공합니다.

## 현재 구조

| Package | 역할 |
|---|---|
| `gptpro` 0.3.x | 사용자가 호출하는 Desktop 전용 오케스트레이터입니다. |
| `gptpro-mcp` 0.2.x | immutable repository snapshot을 읽는 Secure MCP Tunnel companion입니다. |
| `swift-intelligence` 0.1.x | Xcode의 SourceKit-LSP로 Swift 정의, 참조, 구현, 타입, 심볼 및 진단을 읽기 전용으로 조회합니다. |

새 상담은 한 경로만 사용합니다.

```text
Codex $gptpro
  -> secret scan + immutable Schema 4 package
  -> package approval or bounded standing approval
  -> exact gptpro-mcp + Secure MCP Tunnel
  -> visible ChatGPT macOS app / new general Chat / Pro
  -> one visible Send
  -> read-only repository exploration
  -> one matching assistant response
  -> Codex independent evaluation
```

ChatGPT Web, Chrome handoff, browser fallback, CDP, remote debugging port, Electron renderer/IPC/private bridge는 새 실행 경로에서 지원하지 않습니다. 과거 receipt는 offline verification만 가능합니다.

`swift-intelligence`는 MCP 서버가 필요한 Plugin이므로 `plugins/swift-intelligence/`에만 제공합니다. Python 3 외의 Python 패키지나 외부 MCP 바이너리를 추가로 설치하지 않으며, macOS의 Xcode에 포함된 `sourcekit-lsp`를 사용합니다.

## 설치

검증 가능한 기본 설치는 checkout의 관리 도구를 사용합니다. `gptpro`를 설치하면 matching `gptpro-mcp` companion도 먼저 설치하고 owner-only component descriptor에 정확한 entrypoint와 tree hash를 기록합니다.

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

기본 위치는 `${CODEX_HOME:-~/.codex}/skills`입니다. 설치 전환과 레거시 MCP 상태가 있으면 관리 도구가 종료 증거나 residual ownership receipt 없이는 기존 코드를 제거하지 않습니다.

Plugin marketplace와 GitHub Skill 설치는 패키지 탐색에는 사용할 수 있지만, 두 component의 exact descriptor를 만들어 준다는 보장은 없습니다. 실제 Desktop consultation 전에 `desktop-doctor`와 component handshake를 통과해야 합니다. 자세한 내용은 [설치 문서](docs/selective-installation.md)와 [Plugin 문서](docs/plugin-installation.md)를 참고하세요.

Swift Intelligence는 marketplace 등록 후 Plugin으로 설치합니다.

```bash
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add swift-intelligence@codex-skills
```

설치 후 Codex를 다시 시작하고 새 작업을 여십시오. 자세한 요구 사항과 사용법은 [Swift Intelligence 설치 및 사용](plugins/swift-intelligence/docs/installation-and-usage.md)을 참고하세요.

## 첫 사용

사용자는 원하는 프로젝트에서 명시적으로 호출합니다.

```text
$gptpro review 모드로 현재 변경을 ChatGPT Pro와 함께 검토해주세요.
```

Codex는 다음을 수행합니다.

1. 관련 tracked 파일을 고르고 secret/exclude scan을 수행합니다.
2. immutable package와 최대 MCP 공개 범위를 보여줍니다.
3. exact package 승인 또는 일치하는 machine-global standing approval을 확인합니다.
4. foreground Tunnel을 활성화합니다.
5. Computer Use로 보이는 ChatGPT macOS 앱에서 Personal/승인 workspace, ChatGPT App `gptpro`, Pro 모델, 빈 새 general Chat을 확인합니다. `GPT Pro Collaborator`는 Codex 쪽 Skill 이름이며 ChatGPT App 이름이 아닙니다.
6. 승인된 prompt를 한 번만 Send합니다. 결과가 불확실하면 재전송하지 않습니다.
7. Pro는 고정된 read-only tools로 승인 snapshot만 검색·읽습니다.
8. 같은 대화의 다음 완료 assistant turn을 수집하고 Codex가 독립 검증합니다.

계정·App/Tunnel profile은 사용자 단위로 한 번 구성해 여러 로컬 Git repository에서 재사용합니다. 상담 package는 repository와 요청마다 새로 만들어집니다.

## 반복 승인 줄이기

`gptpro-standing-approval-v2`는 최대 30일 동안 transport, Desktop channel, Tunnel profile hash, app, workspace, model, modes, path patterns, dirty policy, 파일/바이트/tool budgets가 정확히 일치하는 상담만 승인합니다.

다음은 standing approval에 포함되지 않습니다.

- 선택된 untracked 파일
- 외부 evidence
- secret finding
- app/workspace/model/profile 변경
- 허용 범위나 예산 확대
- 자동 Send 또는 자동 재전송

## 저장소 밖 텍스트 파일

브라우저 업로드 대신 검토한 strict UTF-8 파일을 package에 immutable evidence로 포함합니다.

```text
$gptpro review 모드로 현재 저장소와 /absolute/path/requirements.md를 함께 검토해주세요.
```

구현은 `--evidence-file safe-id=/absolute/path`로 snapshot을 만들고, Pro에는 `gptpro_artifact_read`만 공개합니다. 원본 경로와 secret은 모델에 전달하지 않습니다.

## 보안 경계

- MCP tools는 read/fetch only입니다.
- live worktree가 아니라 approved immutable snapshot을 읽습니다.
- shell, build, test, Git mutation, repository write, credential access, arbitrary network/filesystem access가 없습니다.
- Tunnel은 foreground exact-child lifecycle로 관리됩니다.
- visible Desktop UI Send는 최대 한 번입니다.
- ChatGPT Pro 결과는 advisory이며 Codex가 검증 전에는 적용하지 않습니다.
- Electron 내부 구현을 사용하지 않으므로 앱 업데이트에 대한 private bridge 의존성이 없습니다.

사용자 매뉴얼은 [gptpro user manual](gptpro/references/user-manual.md), MCP 세부 계약은 [gptpro-mcp manual](gptpro-mcp/references/user-manual.md)에 있습니다.

## Maintainer validation

```bash
python3 scripts/build_gptpro_base.py --check
python3 gptpro/scripts/validate_structure.py
python3 gptpro-mcp/scripts/validate_structure.py
python3 -m unittest discover -s gptpro/tests -v
python3 -m unittest discover -s gptpro-mcp/tests -v
python3 -m unittest discover -s plugins/swift-intelligence/tests -v
python3 -m unittest discover -s scripts/tests -v
python3 scripts/sync_skill_mirrors.py
git diff --check
```

변경 기록은 [CHANGELOG.md](CHANGELOG.md)를 참고하세요.
