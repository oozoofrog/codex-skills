# 검증 기록

검증일: 2026-09-11 UTC

환경: macOS, Python 3.14.7, Git 2.55.0. 보조 도구는 Python 표준 라이브러리만 사용한다. Python 3.9 최소 버전 호환성은 사용 API를 기준으로 작성했으며 3.9 런타임에서는 실행하지 않았다.

## 실행한 자동 검사

| 검사 | 실제 실행과 결과 |
| --- | --- |
| 스킬 형식 | 제공된 skill-creator의 `quick_validate.py` 실행. exit 0, `Skill is valid!` |
| 보조 도구 동작 | `python3 scripts/test_bootstrap.py` 실행. 8 tests, `OK`, exit 0 |
| UI 메타데이터 | YAML 파싱, short_description 길이, default_prompt의 스킬명 검사 통과 |
| 설치 파일 복사 | 격리된 `.agents/skills/session-continuity`에 폴더 복사 후 파일 해시 확인 |
| 기존 설치 보존 | 같은 경로로 `copytree` 재실행 시 `FileExistsError`; 기존 파일 해시 동일 |
| 복사된 도구 실행 | 복사된 스킬의 helper로 임시 Git 저장소 `init` 및 `start` 실행, state 생성 확인 |

보조 도구의 8개 검사는 다음 동작을 확인했다.

1. 기존 문서 바이트와 CRLF를 보존하고 반복 초기화에서도 파일을 유지한다.
2. 기존 Continuity 섹션을 교체하지 않는다.
3. Git 제외는 선택 사항이며 선택 후 재실행해도 중복 추가하지 않는다.
4. 상위 ignore 패턴과 이미 추적 중인 state를 보존한다.
5. task state가 실제 저장소·Git 상태와 `NOT RUN`을 기록하고 중복 ID를 거부한다. 사용자 파일과 index도 보존한다.
6. 잘못된 task-id와 초기화되지 않은 상태에서는 파일을 생성하지 않는다.
7. 심볼릭 링크·worktree 루트가 아닌 위치를 거부해 잘못된 대상에 쓰지 않는다.
8. detached HEAD인 별도 worktree의 실제 경로와 HEAD를 기록한다.

검사는 임시 테스트 저장소에서만 Git fixture를 생성했다. 사용자의 제품 저장소에 commit하거나 전송하지 않았다.

## 독립 에이전트 사용 검증

별도 에이전트가 스킬과 템플릿을 읽고 격리 저장소에서 실제 초기화·task 생성·재개 절차를 수행했다. 실제 동작 로그와 생성된 state를 확인했으며 다음 결과를 얻었다.

- 기존 `AGENTS.md`, `.gitignore`, 사용자 staged/unstaged/untracked 변경을 보존했다.
- 반복 초기화, 같은 task-id 거부, 경로 이탈 ID 거부, 선택적 ignore를 확인했다.
- 사용자 수정 템플릿과 다른 task를 보존하고 새 task에 템플릿 변경이 반영됨을 확인했다.
- state가 기록한 이전 HEAD와 소스 관측이 현재 저장소와 다른 경우를 재개했다. 이미 끝난 구현을 반복하지 않고 관측값과 다음 행동을 정정했다.
- 소스가 목표를 충족해 보여도 실제 실행 전에는 `verification` / `NOT RUN`을 유지했다.
- 이어서 fixture의 단일 반환값 검사를 실제로 실행했다. `python3 -B -c "from app import value; assert value() == 4; print('PASS value()==4')"`는 2026-09-11T14:52:13+00:00에 exit 0으로 성공했다. **이 결과는 격리 fixture의 단일 검사만 증명하며 사용자 제품 테스트 결과가 아니다.**
- 최종 state에 실행 시각·환경·당시 HEAD·미커밋 소스·실제 결과를 남기고 다시 읽었다. 검사 전후 사용자 변경도 유지됐다.

이 범위에서 재현되는 결함은 발견하지 못했다. 문서 지침이 모든 향후 세션에서 준수된다는 보장은 아니다.

## 아직 실행하지 않은 검증

- 사용자 개인 스킬 디렉터리에 실제 설치하거나 Codex UI에서 새 스킬 인식을 확인하지 않았다.
- 실제 새 Codex 세션 생성과 세션 간 자동 인계를 실행하지 않았다. 재개 평가는 독립 에이전트와 격리 fixture를 사용했다.
- 사용자 제품 저장소의 테스트·빌드·Simulator·실기기·설치·릴리스 검증은 실행하지 않았다.
- 완료 후 durable 문서 승격과 state 삭제/보관은 지침으로 검토했으며 실제 사용자 작업 정리는 수행하지 않았다.
- Windows/Linux와 다른 Python/Git 버전에서 실행하지 않았다.
- 자동 압축 시점 감지, 자동 세션 종료·생성, 자동 commit/외부 전송은 구현 범위에 없다.

설치 후 보조 도구 검사는 `python3 scripts/test_bootstrap.py`로 재현할 수 있다. 그 성공도 실제 프로젝트의 테스트 통과나 Codex 새 세션 인식과는 구분해야 한다.

## 저장소 배포 통합 검증

2026-09-12 KST에 `oozoofrog/codex-skills`의 standalone 원본과 Plugin `0.1.0`, marketplace, 설치 문서, 미러 동기화 목록 및 배포 검사를 통합했다. 아래는 저장소 루트에서 실제 실행한 검사다.

| 실행 명령 | 결과 |
| --- | --- |
| `python3 -m py_compile scripts/sync_skill_mirrors.py scripts/tests/test_plugin_distribution.py session-continuity/scripts/bootstrap.py session-continuity/scripts/test_bootstrap.py` | 성공 |
| `python3 -m unittest discover -s scripts/tests -v` | 8 tests, OK |
| `python3 plugins/session-continuity/skills/session-continuity/scripts/test_bootstrap.py` | Plugin 배포 위치에서 8 tests, OK |
| `python3 scripts/sync_skill_mirrors.py --package session-continuity --write` | 원본/Plugin 파일 내용·모드 일치 확인 후 미러 생성 |
| `python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py session-continuity` | Skill is valid! |
| `python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/session-continuity` | Plugin validation passed |
| `git diff --check` | 성공 |

CLI의 `plugin add`와 `plugin marketplace upgrade` 도움말로 설치 명령 형식을 확인했다. 이 검증은 실제 사용자 Plugin 설치나 새 작업에서의 스킬 노출을 의미하지 않는다.
