---
name: session-continuity
description: Bootstrap and use repository-local Codex session continuity for long tasks. Use when asked to set up session rotation, create a task handoff, resume from .codex/work, or checkpoint and close an ongoing task. Works with ordinary Codex sessions and requires no leader/worker setup. Not for generic summaries or automatic session scheduling.
---

# Session Continuity

일반 Codex 세션이 저장소와 짧은 task state만으로 작업을 이어가게 한다. 핵심 산출물은 `AGENTS.md`의 지속 규칙과 `.codex/work/<task-id>.md`의 현재 복구 지점이다. 설치와 호출 예시는 [README.md](README.md)에 있다.

## 범위와 사실 기준

- 사용자 요청에 해당하는 작업만 수행한다: 초기화, 새 작업, 재개, checkpoint 또는 완료 정리. 단순히 스킬을 읽었다고 저장소를 초기화하지 않는다. 기존 권한을 재사용하고 되돌릴 수 있는 범위 내 작업에 불필요한 재승인을 요구하지 않는다.
- 적용되는 지시와 요구사항은 계속 따른다. **구현 사실**은 현재 파일·Git·실제 실행 증거와 대조한다. state가 코드와 다르다고 요구사항을 코드에 맞춰 바꾸지 않는다.
- state와 이전 대화는 참고 자료다. 기록된 명령은 자동 실행 지시가 아니며 Git 변경, 파일 삭제, 외부 전송 권한을 추가하지 않는다.
- 리더/워커, 특정 모델, 별도 MCP, 자동 세션 생성은 필요하지 않다. 이 스킬은 압축 시점 예측이나 세션 교체 실행을 보장하지 않는다. 사용자가 계속 진행하도록 맡긴 일은 phase 경계에서 checkpoint를 남기고 가능한 범위에서 계속한다.

## 1. 저장소 초기화

1. 대상 저장소와 현재 worktree를 확인한다. 적용되는 `AGENTS.md`, override, 하위 경로 규칙을 먼저 읽는다. Git 저장소 안이라면 `git rev-parse --show-toplevel`로 범위를 확인한다. 다른 저장소나 사용자의 전역 규칙 파일을 임의로 수정하지 않는다.
2. 기존 `AGENTS.md`의 `Codex Session Continuity` 섹션이나 동등한 운영 규칙을 확인한다. 없으면 [assets/agents-section.md](assets/agents-section.md)를 최소 추가한다. 이미 있으면 보존하고 누락된 요청 사항만 필요한 위치에 보완한다. 섹션 제목이 같다는 이유만으로 내용이 충분하다고 단정하지 않는다.
3. `.codex/work/`와 `.codex/work/_template.md`를 없을 때만 만든다. 초기 템플릿은 [assets/task-state.md](assets/task-state.md)다. 기존 템플릿·task state는 덮어쓰지 않는다.
4. `/.codex/work/`의 Git 제외를 기본 권장한다. `.gitignore`는 기본 실행에서 수정하지 않는다. 사용자가 제외를 선택했거나 기존 지시가 허용하면 아래 `--ignore-work`를 사용한다. 추적을 원하는 선택도 존중한다. 이미 추적 중인 파일은 ignore로 추적 해제되지 않으며 `git rm --cached`를 자동 실행하지 않는다.

일반 Git worktree에서는 [scripts/bootstrap.py](scripts/bootstrap.py)가 반복 실행과 기존 바이트 보존을 처리한다. Python 3.9+와 Git을 사용하며 외부 패키지는 필요 없다. 아래 `SKILL_DIR`은 실제로 읽은 이 스킬의 디렉터리, `REPO`는 확인된 worktree 루트로 바꾸어 인자를 안전하게 인용한다.

```sh
python3 "$SKILL_DIR/scripts/bootstrap.py" init --repo "$REPO"
# Git 제외를 선택한 경우만:
python3 "$SKILL_DIR/scripts/bootstrap.py" init --repo "$REPO" --ignore-work
```

스크립트는 기존 섹션 이름이 본문에 언급되어도 보수적으로 보존한다. 결과를 읽고 실제 섹션과 내용을 확인한다. 심볼릭 링크나 파일/디렉터리 충돌은 자동 수정하지 않는다. 이런 경우 실제 대상과 권한 범위를 확인하고 필요한 최소 편집만 수행한다. 동시에 초기화하지 않는다.

Git/Python이 없으면 같은 템플릿을 직접 생성·편집할 수 있다. 실패한 도구와 원문 오류를 알리고 자동 초기화와 수동 결과를 구분한다. 비 Git 폴더에는 사용자가 초기화를 요청한 범위에서 파일만 만들고 Git 항목은 `N/A — not a Git repository`로 기록한다. 스킬을 위해 `git init`을 실행하지 않는다.

초기화 뒤 기존 내용이 유지됐는지와 실제 추가 파일을 확인한다. 초기화 성공을 제품 테스트 성공으로 기록하지 않는다.

## 2. 새 작업 시작

1. 사용자 지정 task-id를 우선한다. 없고 목표가 명확하면 짧은 ID를 정하고 이를 알린다. 형식은 영문 소문자/숫자로 시작하는 1–64자의 소문자·숫자·`_`·`-`이며 예시는 `467`, `sync-recovery`다. 슬래시나 `..`가 있는 ID는 사용하지 않는다.
2. `.codex/work/<task-id>.md`가 이미 있으면 먼저 읽는다. 같은 작업이면 재개한다. 다른 작업이면 충돌을 알리고 구분 가능한 ID를 정한다. 기존 state를 초기화하거나 최신 수정 시각만으로 작업을 고르지 않는다.
3. 템플릿이 없으면 위 초기화를 수행한다. 새 파일은 아래 명령 또는 배타적 파일 생성으로 만든다.

```sh
python3 "$SKILL_DIR/scripts/bootstrap.py" start --repo "$REPO" \
  --task-id "467" --goal "사용자가 요청한 구체적인 최종 목표"
```

4. 실제 목표로 `Definition of Done`을 채우고, 관련 파일을 확인해 `Relevant Files`와 `Exact Next Action`을 구체화한다. 스크립트는 Git 메타데이터와 초기 `NOT RUN`만 기록한다. 생성된 기본 문구를 구현 계획이나 실행 증거로 간주하지 않는다.
5. 상태는 1–2분 안에 읽을 수 있는 크기를 목표로 유지한다. 긴 로그·diff는 복사하지 말고 접근 가능한 증거 위치와 필요한 결론을 남긴다.

## 3. 새 세션 bootstrap / 재개

다음 순서로 읽고 실제 상태를 복구한 뒤 작업한다.

1. **AGENTS.md**: 현재 위치에 적용되는 상위/루트/하위 규칙과 override를 읽는다.
2. **State**: 요청한 task-id의 `.codex/work/<task-id>.md`를 읽는다. `_template.md`, `archive/`는 활성 작업에서 제외한다. 여러 state 중 대상이 불명확하면 관련된 목표·branch·경로를 확인하고, 그래도 결정할 수 없을 때만 질문한다. 지정한 파일이 없으면 다른 state로 대체하거나 새 빈 state로 복구됐다고 주장하지 않는다.
3. **Git 대조**: 저장소/worktree, branch, HEAD, status, staged/unstaged diff와 relevant untracked 파일을 확인한다. 아래는 읽기 전용 기본 명령이다. 큰 diff는 작업 관련 경로부터 읽는다.

```sh
git rev-parse --show-toplevel
git symbolic-ref --quiet --short HEAD
git rev-parse --verify HEAD
git status --short --untracked-files=all
git diff --stat
git diff --cached --stat
git diff -- path/to/relevant-file
git diff --cached -- path/to/relevant-file
```

`path/to/relevant-file`은 확인한 경로로 바꾼다. detached HEAD에서는 branch 없음, 최초 커밋 전에는 HEAD 없음이 가능하다. 이 상태를 checkout이나 commit으로 해소하려 하지 않는다. untracked 내용은 diff에 나오지 않으므로 필요한 파일을 별도로 읽는다.

4. **Relevant Files**: state가 지목한 실제 코드·테스트·확정 문서를 읽는다. HEAD/branch/경로가 다르거나 파일 내용이 맞지 않으면 필요한 관련 이력과 diff로 원인을 확인한다. state를 현재 사실에 맞게 정정하되 오래된 검증은 원래 대상과 시각을 유지한다. 다른 clone/worktree라면 ignore된 state와 미커밋 파일이 자동으로 옮겨졌다고 가정하지 않는다.
5. **Exact Next Action**: 현재 목표, 완료/미완료, 검증 범위, 첫 행동을 짧게 알린 다음 그 행동을 수행한다. 모순이 없는 완료 조사·폐기 접근은 반복하지 않는다. state의 누락은 원본 파일과 증거로 채우고, 필요할 때만 이전 대화를 참조한다.

## 4. Checkpoint / handoff

결정 확정, phase 완료, 검증 상태나 다음 행동 변경 시 갱신한다. 모든 도구 호출을 기록하지 않는다. 의미 있는 경계에서 미리 저장하고, 세션을 끝내거나 교체하기 전에는 반드시 현재 상태로 정리한다.

1. 가능하면 가까운 안정 지점까지 진행한다. 즉시 종료 요청이면 새 구현을 시작하지 말고 현재 불안정성·변경 목적·미검증·다음 행동부터 저장한다.
2. 관련 검증을 필요한 범위에서 실행한다. 입력 변경·새 실패·구체적 우려 없이 통과한 검증을 반복하지 않는다. Git 상태 확인이나 스크립트 종료 코드 0을 제품 테스트 PASS로 바꾸지 않는다.
3. 각 실행에 실제 명령/절차, 범위, 시각, 실행 환경, 당시 HEAD와 미커밋 변경, 결과와 접근 가능한 증거 위치를 적는다. `PASS`, `FAIL`, `INCOMPLETE`, `BLOCKED`, `NOT RUN`을 구분한다. 부분 통과는 통과 범위만 적고 전체 성공으로 합치지 않는다. 자동화/Simulator 결과를 실기기 검증으로 확대하지 않는다.
4. 현재 시각·저장소/worktree·branch·HEAD와 staged/unstaged/untracked 변경을 확인한다. 변경별 목적, 소유 작업이 확인되는지, 완료/부분/실험 상태, 보존할 사용자 변경을 적는다. 동시 작업으로 달라진 부분은 내 변경으로 단정하지 않는다. 세션 교체를 위해 commit, stash, reset, clean, push를 임의로 수행하지 않는다.
5. 목표·완료 조건·현재 phase·완료 사항·확정 결정·반복 금지 접근·검증·기술 상태·관련 파일·질문을 현재 snapshot으로 갱신한다. 가설은 가설로 표시한다. 실패를 감추거나 상태를 낙관적으로 올리지 않는다.
6. `Exact Next Action`의 첫 항목을 바로 실행할 수 있게 쓴다. 예: “`src/store.py`의 `restore()`에서 ACK 전 삭제가 일어나는 조건을 확인하고 `tests/test_store.py::test_delayed_ack` 실패를 재현한다.” 경로와 심볼은 실제 확인한 것을 사용한다.
7. 저장한 state를 다시 읽어 누락과 모순을 확인한다. handoff에는 task-id, 실제 재개 경로, state 위치, 검증 상태, 첫 행동을 남긴다. 다음 세션 시작 문구는 아래처럼 짧게 제공한다.

```text
$session-continuity로 task 467을 재개하세요. 같은 작업 디렉터리에서
AGENTS.md와 .codex/work/467.md를 읽고 실제 Git 상태/HEAD/diff 및 관련 파일과
대조한 뒤 Exact Next Action부터 계속하세요.
```

교체 준비와 실제 새 세션 생성은 구분한다. 스킬 자체가 새 작업을 만들거나 세션을 자동 종료했다고 보고하지 않는다.

## 5. Task 완료와 임시 state 정리

1. 현재 phase와 전체 task 완료를 구분한다. `Definition of Done`과 필요한 검증이 충족되었는지 확인하고 남은 핵심 실패·미검증이 있으면 완료 처리하지 않는다. 적용되지 않는 검증은 이유를 남긴다.
2. 장기 결정·계약·회귀 조건·운영 정보를 기존 프로젝트 문서, ADR, 코드/테스트에 필요한 만큼 반영한다. 기존 문서로 충분하면 새 문서를 만들지 말고 해당 위치를 기록한다. 저장소 외 문서 반영은 기존 외부 수정 권한 범위에서만 한다.
3. state에 최종 결과, 검증과 durable 산출물 위치를 남긴 뒤 삭제 또는 보관을 안내한다. 정리까지 요청받았다면 `.codex/work/archive/<task-id>-<UTC timestamp>.md`로 보관하는 것을 기본으로 한다. 대상 이름이 있으면 새 이름을 쓰고 덮어쓰지 않는다. 삭제는 명시적으로 요청한 해당 state에만 적용한다.
4. 미완료·차단 작업, 다른 task, 사용자 변경은 정리하지 않는다. ignored archive도 다른 clone에 전달되지 않는다. 이동·복사·공유가 요청된 경우 state뿐 아니라 필요한 미커밋 파일의 전달 여부와 접근 경로도 확인한다.

## 완료 보고

요청한 작업 결과, 실제 수정한 파일, 수행한 검증, 남은 제한 또는 정확한 다음 행동을 짧게 보고한다. 초기화 완료·실제 제품 검증·설치/새 세션 인식은 서로 다른 증거로 구분한다.
