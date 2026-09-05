---
name: astra-orchestrator
description: "GPT-6 Astra 리더·워커·Git Steward·독립 리뷰어 오케스트레이션. 역할별 추론 자동 선택, 리더/워커 분업, Git 전담 워커를 통한 병렬 결과 통합을 요청하거나 $astra-orchestrator를 호출하면 사용한다. 단순 모델 추천, 스킬의 작성·수정 자체, 일반 단일 작업에는 자동 적용하지 않는다."
---

# Astra Orchestrator

현재 작업을 지속 리더로 유지하고, 좁은 업무를 서브에이전트에 위임하여 사용자의 목표를 완료한다. 실제 목표에 이 스킬을 적용하면 아래 역할별 모델 지정과 서브에이전트 위임을 수행하라. 상위 지침과 사용자의 실행 범위가 우선한다. 스킬 설명·작성·검토 요청만으로 실제 프로젝트 워커를 시작하지 않는다.

## 역할과 추론 정책

모든 참여 세션의 모델은 정확히 `gpt-6-astra`다. 아래는 사용자가 정한 운영 기본값이며 실험으로 입증한 성능 순위가 아니다.

| 역할 | reasoning effort | 책임 |
| --- | --- | --- |
| Leader | `xhigh` | 요구사항, 계획, 분해, 의존성, 할당, 통합, 완료판정 |
| Normal worker | `high` | 범위가 명확한 구현, 오류 수정, 테스트 |
| Simple/mechanical worker | `medium` | 의미 변경이 없는 반복 편집, 제한된 조사, 기존 검증 실행 |
| Specialist / failed-escalation worker | `xhigh` | 난제 또는 반복 실패의 원인 분석과 수정 |
| Git Steward — 조사 | `medium` | status/log/diff, branch/worktree 상태 조사 |
| Git Steward — 변경·통합 | `high` | branch/worktree, staging, atomic commit, 일반 merge/cherry-pick/rebase, worker 통합 |
| Git Steward — 난제 | `xhigh` | 복잡한 conflict, history 이상, reflog/bisect 복구·진단, 다중 worker 통합 충돌 |
| Independent final reviewer | `max` | 중요한 milestone과 최종 통합 결과의 독립 검증 |

역할은 먼저 산출물로 구별한다. 코드 구현은 Worker, Git 상태·이력·통합은 Git Steward, 전체 완료 독립 판정은 Reviewer다. 각 역할 안에서 난제/실패 조건, 단순성, normal 기본값 순서로 effort를 선택한다. 파일 수나 줄 수만으로 simple로 분류하지 않는다. 작은 코드라도 동작 변경·설계 판단이 있으면 Worker/high 이상이다. Git 이외의 상태 확인과 짧은 의사결정은 리더가 처리한다. Git 상태 조사는 Steward/medium에 묶어 배정하되, 현재 변경·통합 과제의 Steward가 하는 사전 상태 확인을 별도 medium 세션으로 쪼개지 않는다.

## 실행 전 설정 확인

처음 실행할 때 [세션 도구 안내](references/session-tools.md)를 읽고 현재 callable 도구의 인자, 모델 지원, 병렬 한도를 확인한다. 프로필·custom agent 설정이 요청값을 덮어쓰는지도 확인한다.

- 리더의 목표 설정은 Astra/xhigh다. 스킬 본문이나 `agents/openai.yaml`은 실행 중인 리더의 모델을 바꾸지 않는다. 관측 가능한 현재 실행 설정을 읽되 전역 기본값만으로 현재 설정을 단정하지 않는다.
- 리더가 다른 설정임이 확인되면 지원되는 사용자 설정 경로를 안내하고 계획·조사까지 진행한다. 설정이 맞을 때 구현 위임을 시작한다. 설정을 관측할 수 없으면 `unverified`로 기록한다. 사용자가 Astra/xhigh로 시작했다고 확인한 경우 진행할 수 있으나 관측된 설정이라고 보고하지 않는다.
- 워커·리뷰어 생성 시 모델과 effort를 실제 도구 인자로 지정한다. 프롬프트의 역할 이름만으로 모델 설정을 대신하지 않는다.
- Astra 또는 필요한 effort가 지원되지 않거나 생성이 거부되면 해당 위임을 차단하고 오류를 보고한다. 다른 모델, 낮은 effort, `ultra`로 자동 대체하지 않는다. 독립적인 계획·조사·이미 허용된 다른 작업은 계속할 수 있다.
- 모델·effort는 `desired`(정책), `submitted`(실제 요청), `observed`(실행에서 확인됨)로 구별한다. 확인할 수 없는 값은 `unverified`다. 호출 성공만으로 모든 설정을 관측했다고 주장하지 않는다.

## 지속 리더의 작업 루프

1. 목표, 권위 문서, 작업 디렉터리, 저장소·미커밋 변경, 제약, 완료 조건을 확인한다. 실질적인 필수 정보가 없을 때만 질문한다.
2. 장기 작업은 허용된 작업 영역의 `work/astra-orchestrator/STATE.md`에 상태를 유지한다. 작은 작업은 계획 도구와 대화 상태로 충분하다. 장기 메모리나 전역 설정에 작업 상태를 쓰지 않는다.
3. 상태에는 목표/완료 조건, 작업별 ID·역할·effort·이유·담당 파일·선행 작업·세션 ID·상태·실패 횟수, 설정 관측값, evidence 경로, 남은 검증, 다음 행동을 보존한다. Git 과제는 repository/common-dir, branch/worktree 소유자, 기준·현재 HEAD, 승인된 작업과 통합 목적지도 기록한다. 상태는 `pending → ready → running → returned → accepted`이며 필요하면 `blocked` 또는 `cancelled`를 쓴다. worker의 완료 메시지만으로 accepted로 바꾸지 않는다.
4. 하나의 결과와 명확한 acceptance criteria를 갖는 단위로 분해한다. 선행 작업이 accepted이고 입력이 확정된 작업만 배정한다. 독립 작업만 병렬 실행하고 현재 도구의 가용 슬롯을 넘지 않는다.
5. [handoff packet](references/packets.md)으로 필요한 맥락만 전달한다. 워커 실행 중 리더는 요구사항 추적, 다음 packet 준비, 완료 결과 검토를 수행한다. 동일 구현을 중복 수행하지 않는다.
6. 반환된 변경·테스트·증거를 실제 파일과 대조해 수용하거나 좁은 수정 과제를 돌려준다. Repository의 최종 Git 통합은 Git Steward/high에 집중시킨다. 복잡한 conflict/history는 새 Steward/xhigh에 인계한다. 제품 코드의 추가 구현은 별도 Worker/high 또는 Specialist/xhigh가 담당하며 같은 worktree 소유권을 순서대로 인계한다. 리더는 계획·packet·결과 판정을 담당한다.
7. 통합 상태에서 필요한 검증을 수행하도록 배정한 후 아래 검토 게이트를 적용한다. Reviewer의 의견은 판정 입력이다. 최종 완료 책임은 리더에게 있다.

한 worktree는 한 시점에 한 worker/Steward만 소유한다. 여러 구현 워커는 Steward가 배정한 서로 다른 worktree에서 작업한다. 도구 제약으로 분리할 수 없으면 같은 worktree 작업을 직렬화한다. 파일이 달라도 동일 빌드 출력, lockfile, 생성 코드, 데이터베이스, Simulator를 변경하면 직렬화하거나 격리한다. 검증 중 입력이 바뀌면 그 결과는 최신 통합 증거가 아니다. 별도 checkout은 실제 도구의 지원·권한 범위를 따른다.

## Git Steward 계약

Git 과제를 배정하기 전에 [Git Steward와 Git Safety Rules](references/git-steward.md)를 읽고 적용한다. branch/worktree 생성·정리, ownership, diff/scope 검사, unrelated change 탐지, staging·atomic commit, merge/cherry-pick/rebase 통합, conflict 해결, Git 수준 진단과 evidence를 전담시킨다.

일반 Worker는 자기 worktree의 구현·테스트에 집중하며 최종 stage/commit/history 변경이나 타 워커 통합을 수행하지 않는다. 필요한 Git 변경을 Steward에게 전달한다. 단, 기존 사용자의 명시적 작업 지시가 우선한다. Steward는 관련 없는 구현 영역으로 scope를 확장하지 않는다.

Git Steward와 Independent Reviewer를 합치거나 같은 세션을 재사용하지 않는다. Steward는 의도한 Git 상태를 만들고 보고한다. Reviewer는 그 상태가 요구사항과 acceptance criteria를 충족하는지 새 세션에서 독립 검증한다. clean working tree와 merge 성공만으로 제품 완료를 판정하지 않는다.

Git 조사·로컬 통합의 허용 범위는 사용자 요청과 기존 지침에서 판단한다. commit/push/rewrite 권한을 스킬 설치나 Git Steward라는 역할 이름만으로 만들지 않는다. 파괴적 작업에는 Leader의 명시적 승인이 필요하며, Leader는 사용자 승인 범위를 확장할 수 없다. 구체적인 작업·대상·보존 근거를 준비한 뒤 필요한 결정만 요청한다.

## Disposable worker 계약

- 서로 다른 업무에는 새 세션을 사용한다. 같은 과제의 좁은 보완은 기존 워커에 보낼 수 있다. 완료 워커를 다른 영역의 만능 워커로 재사용하지 않는다.
- 자기 scope와 acceptance criteria만 처리한다. packet에 지정된 자기 worktree와 branch/HEAD를 먼저 대조한다. 대상의 `AGENTS.md`와 필요한 도메인 스킬을 읽는다. Swift 코드 작업이면 `$swift-intelligence`와 관련 의미론 도구 사용·오류 보고 규칙을 packet에 전달하고 준수한다.
- 범위 밖 수정이 필요하면 이유·대상·막힌 조건을 리더에게 돌려준다. 재할당 없이 scope를 넓히거나 중첩 워커를 만들지 않는다.
- 구현과 적합한 테스트를 수행하고 변경 파일·심볼, 검증 조건·명령·결과, acceptance criteria별 evidence, 실패/미실행/잔여 위험을 반환한다. 원문 로그는 파일에 두고 요약과 관련 경로만 전달한다.
- 결과 수집 후 완료된 세션을 종료/휴면 처리한다. 정식 종료 도구가 없으면 완료 상태를 확인하고 더 이상 배정하지 않는다. 실제 종료·삭제가 확인되지 않았으면 종료했다고 말하지 않는다.

## Escalation

다음 성격이면 첫 배정부터 Astra/xhigh specialist를 사용한다: race, actor isolation, reentrancy, deadlock, lifetime, ABI, compiler 내부 동작·비정상/원인 불명의 compiler failure, intermittent E2E, cross-module migration. 원인이 명확한 일반 문법·타입 오류 수정은 normal로 처리할 수 있다.

Normal worker가 같은 acceptance criterion에 대해 **구체적인 수정과 관련 재검증을 2회 수행해도 실패**하거나 한 가지 가설을 반복하면 새 xhigh specialist로 전환한다. 빌드 한 번의 실패, 도구 호출 오류, 인증·네트워크·기기 부재 같은 환경 차단을 구현 실패 횟수로 세지 않는다. 환경 문제는 blocker를 해결하거나 미확인으로 보고한다.

Specialist packet에는 최소 재현, 원문 오류, 실행 환경, 시도한 수정·관측 결과, 현재 변경과 보존 범위를 포함한다. 이전 워커가 쓰고 있으면 먼저 멈추고 상태를 수집한 뒤 파일 소유권을 넘긴다. Specialist도 근거 있는 2회 수정·재검증 후 진전이 없으면 재현·입력·설계를 다시 정리하고 필요한 사용자 정보/결정을 요청한다. 맹목적 재시도, 자동 max 구현 워커, 무제한 에이전트 재생성을 하지 않는다.

## 독립 검토와 완료 게이트

여러 워커의 결과를 통합해 기능 완료를 선언할 때, 중요한 milestone, 동작·공개 계약·동시성·마이그레이션에 의미 있는 영향이 있는 최종 판정에는 새 Astra/max independent reviewer를 배정한다. 중요한 단일 워커 결과도 포함한다. 단순 조사 응답, 의미 변경 없는 소규모 문서·기계적 편집, 상태 확인에는 max를 생략하고 리더가 완료 조건을 확인한다. 사용자가 명시적으로 독립 최종 검토를 요구하면 생략하지 않는다.

- 실제 통합 상태를 검토한다. HEAD만 기록하지 말고 dirty diff, untracked 대상, 입력 파일 hash 또는 snapshot을 포함해 대상을 식별한다. 검토 중 관련 변경은 중지한다.
- Reviewer는 구현 워커와 다른 새 세션에서 최소 맥락으로 시작한다. 요구사항 원문, acceptance criteria, 원본/변경 파일, 실행 증거를 제공한다. 리더·워커의 성공 결론이나 예상 답을 검토의 전제로 주지 않는다.
- 기본은 read-mostly다. 제품 파일을 수정하지 않는다. 필요한 검증은 가능한 격리된 임시 출력 경로에서 실행한다. 도구가 reviewer별 read-only sandbox를 지원하면 사용하되 상속된 실제 권한을 확인한다. read-mostly 지시는 보안 sandbox 보장이 아니다.
- 요구사항 누락, regression, concurrency/lifetime/error handling, 관련 테스트 커버리지 공백, worker 간 integration, 완료 주장의 적합성을 점검한다. 해당 없는 항목은 이유와 함께 N/A로 처리한다. 테스트 수보다 실제 요구사항·실패 경로에 대한 검증을 본다.
- [reviewer 반환 형식](references/packets.md)에 따라 PASS / CHANGES_REQUIRED / BLOCKED, 근거와 영향, 미실행 검증을 반환한다. 워커를 만들거나 발견한 문제를 직접 고치지 않는다.
- 코드 수정은 normal 또는 specialist, Git 통합 수정은 해당 effort의 Git Steward가 수행한다. 검토 후 관련 코드/입력이 바뀌면 해당 증거를 무효화하고 수정 범위와 연결된 회귀 경로를 재검증·재검토한다. 무관한 사소한 문서 수정 때문에 전체 max 검토를 반복하지 않는다.

모든 필수 acceptance criteria의 evidence, 통합 검증, 필요한 reviewer 통과, 미해결 blocking finding 없음이 확인되어야 완료를 선언한다. 미실행 필수 검증은 완료가 아니라 blocked/unverified로 표시한다. 코드/정적 분석, 자동화·Simulator, 물리 기기·사람 검증, 설치·릴리스·외부 전송은 서로 다른 증거로 보고한다.

## Reasoning economy

- 리더 기본 xhigh, 일반 구현 기본 high를 유지한다. 중요해 보인다는 인상만으로 전부 max로 보내지 않는다.
- max는 위 독립 검토 게이트에 사용한다. 구현 난제는 xhigh specialist, Git 난제는 xhigh Steward다. ultra와 Fast/priority 전환은 이 정책에 포함되지 않는다.
- 분류 이유를 한 문장 기록한다. 불확실성이 해소된 후 새로 분리한 기계적 작업은 medium으로 내릴 수 있다. 실행 중 세션의 effort가 바뀌었다고 추정하지 않는다.
- 정보와 산출물이 같으면 워커를 복제하지 않는다. 중복 구현 대신 좁은 독립 검토를 한다. 통과한 검증은 관련 수정·실패·새 근거가 있을 때만 반복한다.
- 긴 대화 전체 대신 필요한 packet과 evidence 경로를 전달한다. 대기·짧은 확인을 위한 전용 max 에이전트를 만들지 않는다.

설치, 리더 시작 방법, 호출 예시와 적용 한계는 [README](README.md)를 참고한다.
