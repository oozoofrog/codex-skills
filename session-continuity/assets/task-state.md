# Work State: {{TASK_ID}}

Updated: {{UPDATED_AT}}
Repository / Worktree: {{REPO_ROOT}}
Branch: {{BRANCH}}
Checkpoint HEAD: {{HEAD}}

## Goal

{{GOAL}}

## Definition of Done

- [ ] 목표에서 검증 가능한 완료 조건을 도출해 작성한다.

## Current Phase

초기 상태 확인 및 완료 조건 구체화

Status: not-started

사용 가능한 상태: not-started / in-progress / verification / blocked / complete

## Completed

- 작업 state 생성. 제품 구현이나 검증 완료를 뜻하지 않는다.

## Established Decisions

- 아직 없음. 확정 결정은 근거와 durable 문서 위치를 함께 기록한다.

## Do Not Repeat

- 아직 없음. 다시 시도할 가능성이 있는 폐기 접근과 이유만 남긴다.

## Verification Evidence

| 상태 | 검증 종류·범위 | 실제 실행 명령/절차 | 실행 시각·대상 HEAD/미커밋 변경 | 실제 결과·증거 위치 |
| --- | --- | --- | --- | --- |
| NOT RUN | 이 작업의 제품 검증 | 미실행 | 해당 없음 | 초기화는 테스트 실행이 아님 |

PASS는 실제 성공한 범위에만 사용한다. FAIL / INCOMPLETE / BLOCKED / NOT RUN을 구분한다.
자동 테스트·Simulator·실기기·사람 검토·설치/릴리스/외부 전송을 각각 기록한다.
기존 실행 증거는 원래 시각과 대상을 유지한다. 현재 코드에도 유효한지는 별도로 판단한다.

## Working Tree

아래는 state 생성 직전 `git status --short --untracked-files=all`의 관측값이다.
state 저장 이후의 변경은 포함하지 않는다. 재개 시 staged/unstaged diff와 untracked 내용도 확인한다.

{{GIT_STATUS}}

변경별 목적·소유 작업·완료도: 아직 미분류. 기존 변경을 내 작업으로 단정하지 않는다.
보존할 변경: 확인 전까지 모든 기존 변경을 보존한다.

## Current Technical State

관련 소스를 아직 확인하지 않았다. 관측 사실·추론·미확인을 구분해 갱신한다.

## Exact Next Action

1. 적용되는 `AGENTS.md`와 이 state를 읽고 실제 저장소/worktree·branch·HEAD·status·staged/unstaged diff를 대조한다. 목표에 직접 관련된 파일을 찾아 완료 조건과 첫 구현 또는 조사 행동을 구체화한다.

## Relevant Files

- 아직 미선정. 실제로 확인한 소스·테스트·계약 문서만 추가한다.

## Open Questions

- 없음. 진행을 막는 질문이 확인되면 작성한다.

## Completion / Durable Artifacts

- 아직 작업 미완료. 전체 완료 시 필요한 결론을 durable 문서로 승격하고 위치를 기록한다.
- state 삭제/보관은 승격과 필요한 검증을 확인한 다음 수행한다.

## Resume Hint

`AGENTS.md → 이 state → 실제 Git 상태/HEAD/diff → Relevant Files → Exact Next Action`.
이전 대화가 있다고 가정하지 않는다. 이 state는 사실·권한의 정본이 아니다.
