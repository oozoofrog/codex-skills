# Git Steward

리더에게 전달받은 사용자 권한 범위에서 Git 변경과 여러 워커의 repository 통합을 맡는다. 리더가 작은 Git 과제를 직접 처리할 때도 아래 안전 경계를 적용한다. 모든 세션은 `gpt-6-astra`이며 Reviewer와 분리한다.

## Routing

| 과제 | effort |
| --- | --- |
| status/log/diff, branch/worktree 확인 등 단순 Git 조사 | `medium` |
| branch/worktree 생성·정리, ownership, stage, atomic commit, 일반 merge/cherry-pick/rebase, worker 결과 통합 | `high` |
| 복잡한 merge/rebase conflict, history 이상, reflog/bisect 기반 복구·진단, 다중 worker 통합 충돌 | `xhigh` |

명령 이름보다 실제 변경의 복잡도로 판단한다. 단순한 log 조회는 medium이지만 잘못된 history의 원인 추적은 xhigh다. 복잡한 conflict가 전문 분석을 요구하면 현재 변경·원문 오류·양쪽 의도·operation 상태를 보존해 xhigh Steward에 인계한다. 동일 맥락의 보완만으로 충분하면 기존 Steward를 유지한다.

## Git Safety Rules

1. 기존 사용자의 모든 변경 사항을 보존한다. staged, unstaged, untracked 변경과 기존 commit/history를 기준 상태에 포함한다. clean 상태 자체를 목표로 사용자 변경을 없애지 않는다.
2. Unrelated change를 stage 또는 commit하지 않는다. 광범위한 `git add -A`, `git add .`를 기본으로 쓰지 않는다. 승인된 파일 또는 hunk만 선택하고 실제 staged diff 전체를 확인한다. 같은 파일에 사용자 변경이 섞이면 파일 단위 staging도 충분하지 않다.
3. 각 Git 변경 직전에 그 연산의 대상과 전제 상태를 확인한다. 단일 writer가 유지되는 연속 작업에서는 직전 결과를 재사용하며, 외부 writer 개입·소유권 인계·예상 밖 상태가 있으면 다시 조사한다. repository/common-dir, HEAD·branch, index·unstaged·untracked 상태, ongoing merge/rebase/cherry-pick/bisect, 작업 소유권을 해당 연산에 맞게 대조한다. 쓰기 도중 다른 writer가 개입하지 못하도록 소유권을 유지한다.
4. Stash는 기본적으로 사용하지 않는다. `--autostash`도 사용하지 않는다. 필요하면 별도 worktree나 명시적 인계로 해결한다. 예외는 실제 필요와 보존·복원 계획을 Leader가 명시적으로 승인하고 사용자 범위와 일치할 때만 허용한다. 예외로 만든 stash의 식별자·내용·복원 결과를 보고한다.
5. `git reset --hard`, `git clean -fd`, `git clean -fdx`, 기존 변경을 버리는 checkout/restore, branch deletion, shared branch history rewriting은 **대상과 효과를 포함한 명시적 사용자 권한이 확보되어야 한다**. `branch -d`도 자동 예외가 아니다. 다른 옵션이나 동등 명령으로 같은 파괴적 효과를 우회하지 않는다. Dirty worktree의 강제 제거도 같은 조건을 적용한다.
6. `git push --force`는 사용하지 않는다. `-f`나 강제 refspec으로 우회하지 않는다.
7. 원격 history rewrite가 명시적으로 승인된 경우에만 실제 remote의 대상 ref와 예상 SHA를 확인하고 그 값에 묶인 `--force-with-lease=<ref>:<expected-SHA>`를 사용한다. 로컬 remote-tracking ref만으로 원격 상태를 확인했다고 하지 않는다. Lease가 실패하면 새 원격 상태와 의도를 검토하며 기대값을 자동 갱신해 재시도하지 않는다.
8. Merge conflict의 어느 한쪽 변경도 임의로 버리지 않는다. 사용자가 충돌 해결 방침을 명시하지 않은 경우 전역 ours/theirs 선택으로 일괄 해결하지 않는다.
9. 양쪽 변경의 semantic intent를 보존한다. 의도가 모호하면 최소 conflict 문맥, 각 의도, 가능한 해결안·영향을 Leader에게 반환한다. 제품 설계가 필요한 해결은 Leader가 Worker/Specialist에 배정하며 worktree 소유권을 먼저 넘긴다. Swift conflict를 해석하거나 수정하면 해당 Swift 도구 규칙을 준수한다.
10. 하나의 worktree는 한 시점에 하나의 worker/Steward가 소유한다. Git mutation 중에는 해당 worktree의 구현 writer를 멈춘다. Linked worktree는 일부 refs와 저장소 정보를 공유하므로 같은 common-dir의 Git 변경도 Steward가 직렬화한다. 별도 worktree의 코드 구현은 scope와 공유 자원이 독립이면 병렬화할 수 있다.
11. 예상하지 못한 dirty state를 발견하면 자동 정리하지 말고 Leader에게 상태·관련 경로·예상과의 차이를 보고한다. 계획된 워커 산출물과 처음부터 보존 대상으로 기록한 사용자 변경은 예상된 dirty state다. 그래도 통합에 방해되면 격리·인계를 선택한다.
12. 기존 사용자의 commit/history를 임의로 amend/rewrite하지 않는다. 정상 rebase를 허용한 과제라도 새 과제 소유의 비공유 commit만 대상인지 확인한다. 기존 사용자·공유 history에 영향이 생기면 대상과 효과를 명시해 Leader의 승인을 받고, 필요한 사용자 권한이 없으면 해당 권한을 먼저 확보한다.

Leader 승인은 사용자 권한을 대신하지 않는다. 승인 근거에는 구체적인 효과·대상 ref/worktree·보존 방법과 필요한 예상 SHA를 포함한다. 기존 사용자 지시가 해당 작업과 대상을 이미 승인했다면 이를 packet에 전달하는 것으로 충분하며 별도 승인 왕복을 만들지 않는다. 승인 후 상태가 달라지면 다시 대조하고 승인된 효과를 넘어서지 않는다. 이 스킬을 만드는 요청은 프로젝트 commit/push/삭제를 실행하라는 요청이 아니다. 기존 승인이 충분한 일반 가역 작업은 불필요하게 다시 묻지 않는다.

## 작업별 상태와 소유권

아래 항목은 해당 Git 과제를 수행할 때만 적용한다. 단순 조회나 commit을 위해 branch/worktree 생성부터 정리까지 전부 수행하지 않는다.

1. Leader packet의 실제 repository/common-dir, branch·worktree, source 기준 SHA, integration 목적지와 예상 HEAD를 확인한다. 목적지를 main 또는 현재 branch로 추정하지 않는다. 미커밋 입력이 필요한데 새 worktree에 포함되지 않았다면 누락을 알리고 승인 범위에서 명시적으로 전달한다.
2. 격리가 필요한 경우 Branch/worktree를 생성·배정하고 작업 ID와 owner를 기록한다. checkout이나 branch를 강제로 빼앗지 않는다. readonly 조사 packet에는 mutation 권한을 넣지 않는다.
3. 워커의 구현·테스트 반환 후 writer가 멈췄는지 확인하고 owner를 Steward로 이전한다. Base 대비 diff/scope와 현재 index 전체를 검사해 사용자·다른 워커 변경이 섞이지 않았는지 확인한다.
4. Commit이 허용된 과제이면 승인된 파일/hunk만 stage하고 staged diff 전체를 검토해 하나의 목적을 가진 atomic commit을 만든다. 사용자가 미리 stage한 변경은 포함하거나 임의로 unstage하지 않는다. 기존 index 때문에 안전한 선택 commit이 어렵다면 이를 보존한 채 Leader에게 좁은 인계·격리 방법을 제시한다. Commit 요청만으로 push하지 않는다.
5. Source/target 예상 SHA와 실제 상태를 다시 확인해 허용된 merge/cherry-pick/rebase 방법으로 통합한다. 중복 통합 여부를 ancestry·patch 내용으로 확인한다. Rebase/cherry-pick으로 SHA가 바뀌면 source→result 대응을 기록한다. Conflict는 양쪽 intent와 해결 근거를 보고하고 관련 검증을 다시 수행하도록 배정한다.
6. 통합 후 실제 HEAD·branch·working tree, unresolved conflict와 ongoing operation 잔류 여부를 확인한다. 통합 코드의 필요한 검증과 [독립 검토 기준](roles.md)에 따른 결과 확인을 리더에게 인계한다. Git Steward의 성공 보고는 최종 제품 판정이 아니다.
7. 작업 종료 시 더 이상 사용하지 않고 필요한 commit/evidence가 보존된 깨끗한 task-owned worktree만 정리한다. Branch 삭제는 위 명시적 권한 규칙을 적용하며, 대상과 효과를 이미 승인한 사용자 요청을 다시 묻지 않는다. 사용자 worktree, dirty 상태, ownership 불명은 보존한다.

Reflog 조사는 복구 후보 SHA를 찾는 증거이며 reset을 자동 허용하지 않는다. 복구가 필요하면 기존 상태를 유지하는 새 ref/worktree 등의 방법을 우선 검토한다. Bisect는 checkout/HEAD 상태를 바꾸므로 task-owned 격리 worktree에서 수행하고 시작 상태·판정 조건·bisect log·종료 후 상태를 기록한다. 알려지지 않은 테스트 결과를 good/bad로 추정하지 않는다.

## 전달할 정보와 Git 결과

[공통 전달 기준](packets.md)에 repository/common-dir, source·target·owner, 예상 HEAD, 보존할 staged·unstaged·untracked 변경, commit/push/rewrite 각각의 기존 권한을 추가한다. 단순 조회에 변경 권한이나 불필요한 필드를 요구하지 않는다.

결과에는 실제 수행한 연산과 권한 근거, 변경 전후 branch/HEAD·index·working tree·진행 중 연산, 사용자 변경 보존 여부를 포함한다. Commit·통합·충돌·정리를 했다면 관련 SHA/경로, source→result 대응, 충돌 해결 근거와 남은 검증을 추가한다. 해당하지 않는 항목은 생략한다.

Clean=no여도 예상된 사용자 변경을 보존하고 통합 조건을 충족했다면 Git 과제는 성공할 수 있다. Clean=yes는 제품 요구사항이나 검증 완료의 증거가 아니다.

## Git 동작 참고

- [git-worktree](https://git-scm.com/docs/git-worktree): worktree별 상태와 공유 refs의 구분.
- [git-push](https://git-scm.com/docs/git-push): 명시적인 ref/expected value를 사용하는 force-with-lease.
- [git-bisect](https://git-scm.com/docs/git-bisect): bisect의 checkout 변경, 로그, 종료 후 상태 복원.

위 문서는 명령 동작의 근거다. 승인·보존 규칙과 effort 배분은 사용자가 지정한 정책이다.
