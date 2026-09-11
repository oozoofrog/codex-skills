# Session Continuity

일반 Codex 세션용 **Session Rotation Protocol 부트스트랩 스킬**이다. 저장소에 지속 규칙과 task state를 만들고, 새 세션이 이전 대화 없이 현재 작업을 복구하도록 안내한다. 리더/워커나 별도 오케스트레이터는 필요 없다.

## 설치

### 저장소 Plugin 설치

`oozoofrog/codex-skills` marketplace의 `session-continuity` Plugin으로 설치할 수 있다.

```sh
codex plugin marketplace add oozoofrog/codex-skills --ref main
codex plugin add session-continuity@codex-skills
```

이미 marketplace가 등록되어 있으면 첫 명령 대신 `codex plugin marketplace upgrade codex-skills`로 목록을 갱신한다. 설치 후 새 작업에서 `$session-continuity` 또는 `$session-continuity:session-continuity`로 호출한다. 실제 설치 성공과 새 작업의 스킬 노출은 별도로 확인한다.

### Standalone 폴더 설치

Plugin 없이 사용하려면 이 저장소의 `session-continuity/` 폴더 전체를 아래 위치 중 **한 곳**에 복사한다. 별도로 받은 standalone ZIP이 있다면 압축을 푼 같은 이름의 폴더를 사용할 수도 있다. 최종 경로는 `…/session-continuity/SKILL.md` 형태여야 한다.

| 범위 | 설치할 폴더 |
| --- | --- |
| 모든 프로젝트에서 개인 사용 | `~/.agents/skills/session-continuity/` |
| 특정 Git 저장소에서 사용 | `<repository>/.agents/skills/session-continuity/` |

이는 2026-09-11에 확인한 [OpenAI 공식 로컬 스킬 경로](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)를 따른다. 기존 환경이 `~/.codex/skills/` 등 별도 경로에서 개인 스킬을 읽는 것으로 확인되어 있다면 그 경로를 사용할 수 있다. Plugin과 standalone을 중복 설치할 필요는 없다.

터미널을 사용한다면 이 저장소를 내려받은 **루트 폴더**에서 아래 명령으로 개인 경로에 복사할 수 있다. Python의 `copytree`는 대상 폴더가 이미 있으면 실패하므로 기존 설치를 덮어쓰지 않는다. Codex에서 스킬이 나타나지 않으면 다시 시작한다.

```sh
python3 - <<'PYTHON'
from pathlib import Path
import shutil

source = Path("session-continuity")
destination = Path.home() / ".agents" / "skills" / "session-continuity"
if not (source / "SKILL.md").is_file():
    raise SystemExit("session-continuity 폴더의 상위 위치에서 실행하세요.")
shutil.copytree(source, destination)
print(f"설치 파일 복사 완료: {destination}")
PYTHON
```

스킬 설치와 저장소 초기화는 별개다. 설치만으로 프로젝트의 `AGENTS.md`나 `.gitignore`를 수정하지 않는다. 호출은 `$session-continuity`를 포함한 프롬프트를 사용한다. 스킬 선택 UI가 있는 환경에서는 이름으로 선택할 수도 있다. [공식 스킬 사용 안내](https://learn.chatgpt.com/docs/build-skills#how-chatgpt-and-codex-use-skills)

## 바로 사용하기

아래 프롬프트에서 `467`과 목표만 자신의 작업에 맞게 바꾼다.

**저장소 최초 설정과 작업 시작**

```text
$session-continuity로 현재 저장소를 초기화하세요.
기존 AGENTS.md와 작업 상태는 보존하고 .codex/work/는 Git에서 제외하세요.
task-id는 467, 목표는 “재시작 후 누락되는 동기화 항목 복구”입니다.
관련 파일을 확인해 완료 조건과 정확한 다음 행동까지 채워주세요.
```

Git 제외를 선택하지 않으려면 두 번째 줄을 “기존 AGENTS.md와 .gitignore를 보존하고 .codex/work/의 Git 제외는 적용하지 마세요.”로 바꾼다. **스크립트 기본값도 `.gitignore` 무수정**이다.

**새 세션에서 재개**

```text
$session-continuity로 task 467을 재개하세요.
AGENTS.md와 .codex/work/467.md를 읽고 현재 저장소/worktree,
Git 상태·HEAD·diff 및 관련 파일과 대조한 뒤 Exact Next Action부터 계속하세요.
```

**세션 교체 전 checkpoint**

```text
$session-continuity로 task 467의 checkpoint를 갱신하고
이번 세션을 마무리할 handoff를 작성하세요.
실행한 검증, 실패, 미검증, 변경 목적과 정확한 다음 행동을 남겨주세요.
```

**전체 작업 완료와 정리**

```text
$session-continuity로 task 467의 전체 완료 조건과 검증을 확인하세요.
필요한 장기 결론을 기존 프로젝트 문서에 반영하고 위치를 기록한 뒤,
완료가 확인되면 state를 archive에 보관하세요.
```

## 만들어지는 구조

```text
repository/
├── AGENTS.md                       # 없던 Continuity 섹션만 추가
├── .gitignore                      # Git 제외를 선택한 경우만 최소 추가
└── .codex/work/
    ├── _template.md                # 저장소에서 조정할 수 있는 state 템플릿
    ├── 467.md                      # 현재 작업의 snapshot
    └── archive/                    # 완료 정리 시에만 생성
        └── 467-<UTC timestamp>.md
```

패키지의 `agents/openai.yaml`은 스킬 UI 메타데이터다. 저장소에 추가하는 `AGENTS.md` 규칙과 별개다.

## 보조 스크립트 직접 사용

필요 환경은 **Python 3.9 이상 + Git**이며 외부 Python 패키지가 필요 없다. `--repo`에는 실제 Git worktree의 루트를 지정한다. 아래 두 변수는 자신의 실제 경로로 바꾼다.

```sh
CONTINUITY_SKILL="$HOME/.agents/skills/session-continuity"
CONTINUITY_REPO="/absolute/path/to/repository"

python3 "$CONTINUITY_SKILL/scripts/bootstrap.py" init \
  --repo "$CONTINUITY_REPO"

python3 "$CONTINUITY_SKILL/scripts/bootstrap.py" start \
  --repo "$CONTINUITY_REPO" \
  --task-id "467" \
  --goal "재시작 후 누락되는 동기화 항목 복구"
```

Git 제외를 선택했다면 `init` 명령에 `--ignore-work`를 붙인다. 시작 후 Codex가 목표에 맞게 완료 조건, 관련 파일, 다음 행동을 구체화해야 한다. 도구는 제품 코드를 이해하거나 테스트를 실행하지 않는다.

| 동작 | 처리 |
| --- | --- |
| `init` | 없는 규칙 섹션·디렉터리·템플릿만 만든다. 기존 템플릿은 보존한다. |
| `init --ignore-work` | Git의 ignore 판정을 확인하고 필요하면 `/.codex/work/`를 추가한다. |
| `start` | task-id와 목표, UTC 시각, worktree 경로, branch, HEAD, 생성 직전 status를 새 state에 쓴다. |
| 같은 task-id 재사용 | 오류로 종료하고 기존 파일을 보존한다. 기존 state를 읽어 재개한다. |
| 다른 worktree | 그 worktree의 루트를 지정한다. 저장한 경로·HEAD를 다음 세션에서 다시 대조한다. |
| 초기 커밋 전 / detached HEAD | 해당 상태를 기록한다. commit이나 checkout을 만들지 않는다. |

task-id는 소문자/숫자로 시작하는 1–64자의 소문자·숫자·`_`·`-`다. `.codex/work/_template.md`는 활성 task가 아니다.

기존 문서에 `Codex Session Continuity` 문구가 있으면 스크립트는 보수적으로 섹션 추가를 생략한다. Codex가 실제 규칙인지 확인하고 누락된 내용만 보완한다. 동등한 규칙이 다른 이름으로 있으면 스크립트를 무조건 실행하기보다 최소 편집으로 통합한다.

심볼릭 링크나 예상과 다른 파일 유형은 자동 수정하지 않는다. 실제 대상을 확인해 수동으로 최소 편집한다. Git이 아닌 폴더나 Python이 없는 환경에서는 스킬이 템플릿을 직접 적용할 수 있고, Git 정보는 해당 없음으로 기록한다. 초기화 여러 개를 동시에 실행하지 않는다.

## 세션 운영의 기준

새 세션은 **AGENTS.md → state → 실제 Git 상태/HEAD/diff → 관련 파일 → Exact Next Action** 순서로 복구한다. state는 현재 사실의 정본이나 새 권한을 주는 지시문이 아니다. 요구사항은 사용자 지시와 확정 문서를 따르고, 구현 상태는 실제 파일과 검증 증거로 확인한다.

state에는 Goal, Definition of Done, Current Phase, Completed, Established Decisions, Do Not Repeat, Verification Evidence, Working Tree, Current Technical State, Exact Next Action, Relevant Files, Open Questions, Completion / Durable Artifacts가 들어간다. 긴 대화 기록 대신 현재 작업 지점을 유지한다.

검증 상태는 `PASS / FAIL / INCOMPLETE / BLOCKED / NOT RUN`으로 구분한다. **실제로 실행하지 않은 테스트는 PASS로 기록하지 않는다.** 과거의 성공에는 당시 시각·HEAD·미커밋 변경과 범위를 남긴다. 현재 코드에 그대로 적용되는지는 별도로 판단한다. Simulator와 실기기, 자동 테스트와 사람 검토, 설치와 릴리스도 구분한다.

phase 경계에서 checkpoint를 준비하며, 사용자가 계속 진행하도록 맡긴 작업은 가능한 범위에서 계속한다. 세션 교체를 요청하면 안정 지점에서 handoff를 남긴다. 이 패키지에는 자동 새 세션 생성, 예약 실행, 자동 commit, 압축 시점 감지가 없다. 갑작스러운 종료에 대비해 의미 있는 변경 시에도 state를 갱신하도록 한다.

`.codex/work/`를 ignore하면 다른 clone/worktree로 자동 전달되지 않는다. 같은 실제 작업 디렉터리에서 재개하거나, 이동이 필요한 경우 state와 미커밋 변경이 목적지에 있는지 확인해야 한다. ignore 추가는 이미 추적 중인 파일을 추적 해제하지 않는다.

## 완료 정리

전체 완료 조건과 필요한 검증을 확인한 다음 장기 결론을 기존 코드·테스트·프로젝트 문서·ADR에 반영한다. 승격 위치를 state에 남긴 뒤 삭제/보관을 안내한다. 정리까지 맡겼다면 보관을 기본으로 하고, 명시적인 삭제 요청에는 해당 state만 삭제한다. 미완료 작업과 다른 task의 기록은 정리하지 않는다.

## 패키지 구성과 검증

| 파일 | 용도 |
| --- | --- |
| [SKILL.md](SKILL.md) | 초기화부터 완료 정리까지 Codex 실행 지침 |
| [agents/openai.yaml](agents/openai.yaml) | 스킬 표시 이름·설명·기본 호출 프롬프트 |
| [assets/agents-section.md](assets/agents-section.md) | 저장소에 추가할 지속 규칙 |
| [assets/task-state.md](assets/task-state.md) | 새 task의 상태 템플릿 |
| [scripts/bootstrap.py](scripts/bootstrap.py) | 기존 파일을 보존하는 초기화·새 state 생성 |
| [scripts/test_bootstrap.py](scripts/test_bootstrap.py) | 임시 Git 저장소를 사용하는 동작 검증 |
| [VALIDATION.md](VALIDATION.md) | 제작 시 실제 실행한 검증과 미검증 범위 |

설치 후 보조 도구를 직접 검사하려면 스킬 폴더에서 아래를 실행한다. 테스트는 임시 저장소 안에서만 파일과 Git 테스트 커밋을 만들고 종료 시 정리한다. 제품 저장소에는 접근하지 않는다.

```sh
python3 scripts/test_bootstrap.py
```
