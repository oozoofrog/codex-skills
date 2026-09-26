# 작업 환경과 통합

독립 세션은 독립 작업 환경이 아니다. 실제 병렬 쓰기가 유리할 때만 격리 환경을 만든다. 단순 조사나 작은 순차 변경에 worktree·전담 Git 세션부터 만들지 않는다.

## 소유권과 공유 자원

- 한 worktree에는 한 시점에 한 writer만 둔다. 리더, 구현자, 통합 담당자 모두 포함한다. 다른 파일을 수정해도 같은 worktree의 병렬 writer는 허용하지 않는다.
- 병렬 구현에는 확인한 기준 ref와 별도 worktree·범위를 배정한다. 현재 dirty 입력이 필요하면 task 소유 변경만 명시적으로 전달하거나 기존 writer에서 순차 수행한다. 새 worktree는 미커밋 변경을 자동 복사하지 않는다.
- worktree를 나눠도 같은 repository의 refs/common-dir, Simulator·실기기, 데이터베이스, 포트, build cache, package lock, 대형 모델/GPU를 공유할 수 있다. 자원별 owner와 점유 종료 조건을 정한다. 격리가 불가능한 연산은 직렬화한다.
- Git 변경은 같은 common-dir의 연산 간 영향을 고려해 조정한다. 공유 포맷터·코드 생성·의존성 갱신도 writer다. 관련 파일을 읽는 검토에는 불변 snapshot 또는 쓰기 중단을 제공한다.
- 소유권을 넘기기 전에 기존 작업의 실제 정지, 남은 process, diff, 진행 중 Git 연산을 확인한다. 워커가 timeout/응답 불명이면 `unknown`으로 남기고 겹치는 writer를 시작하지 않는다.

## Git·통합의 권한

리더 또는 필요한 통합 담당자는 기존 staged/unstaged/untracked 변경과 branch·HEAD를 기준 상태로 보존한다. 변경 직전에 대상과 전제 상태를 확인하며, 같은 owner의 연속 작업에서는 직전 증거를 재사용한다. 예상 밖 변경을 자동 정리하지 않는다.

commit·push·배포는 사용자 요청 범위대로 수행한다. commit 요청은 push 요청이 아니다. 새 branch 이름을 선택해야 하면 repository 규칙을 따르며 별도 지정이 없으면 `task/`를 사용한다. branch/worktree 생성이 통합 목적지를 main으로 정하는 근거는 아니다.

승인된 파일/hunk만 stage하고 staged diff 전체를 확인한다. `git add .`/`git add -A`, 기본 stash/`--autostash`, 기존 사용자 commit의 amend를 편의 수단으로 사용하지 않는다. 같은 파일/index에 사용자 변경이 섞였으면 보존 가능한 인계·격리를 선택한다.

기존 변경을 버리는 reset/clean/checkout, branch 삭제, dirty worktree 강제 제거, 공유 history rewrite는 대상과 효과를 포함한 명시 사용자 권한이 필요하다. 역할 배정이나 리더 판단만으로 이 권한을 만들지 않는다. 원격 강제 갱신이 명시적으로 승인된 경우에도 실제 remote ref·예상 SHA에 묶인 `--force-with-lease=<ref>:<expected-SHA>`만 검토한다. 일반 `--force`/강제 refspec은 쓰지 않으며 lease 실패의 기대값을 자동 갱신하지 않는다.

## 결과 통합

1. 워커가 쓰기를 마친 뒤 실제 source/target, 변경 범위, 사용자 변경 보존, 검증 증거를 확인하고 owner를 넘긴다.
2. 허용된 방법으로 변경을 반영한다. diff/patch를 전달할 때도 base와 대상 상태를 대조한다. 이미 포함된 결과를 중복 적용하지 않는다. commit을 만들 필요가 없는 과제에 통합 편의를 이유로 commit을 강제하지 않는다.
3. conflict는 양쪽 의도를 보존한다. 전역 ours/theirs 선택으로 덮지 않는다. 제품 계약의 결정이 필요하면 관련 원문·양쪽 의도·영향을 리더에게 반환하고 구현/전문 역할에 좁게 배정한다.
4. 실제 통합 결과와 관련 dirty/untracked 파일을 포함해 필요한 검증을 한다. 워커 worktree의 PASS를 통합 결과의 PASS로 그대로 옮기지 않는다. Git 성공도 제품 완료 판정이 아니다.
5. 사용하지 않는 task 소유 환경은 산출물·증거가 보존되고 권한이 충족될 때 정리한다. 사용자 worktree·불명확한 소유권·dirty 환경은 보존한다.

긴 작업은 [전달·상태](packets-and-state.md)에 경로·owner·공유 자원·통합 결과를 기록한다. clean 여부만으로 성공을 판정하지 않는다. 예상된 사용자 변경이 남아도 요청 범위의 통합은 완료될 수 있다.
