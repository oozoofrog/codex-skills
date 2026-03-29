# Fit Check and Mode Routing

## Quick fit check

아래 4개가 모두 성립할 때 `goal-research-loop`를 사용합니다.

1. **objective를 한 문장으로 말할 수 있다**
2. **baseline과 비교 가능한 결과**를 만들 수 있다
3. **hard gate 또는 proxy metric**을 정의할 수 있다
4. **budget과 stop rule**을 미리 고정할 수 있다

하나라도 비어 있으면 곧바로 루프를 돌리지 말고 `design` 또는 `rescope`부터 시작합니다.

## Adjacent skill boundaries

| 상황 | 사용할 스킬 | 이유 |
|---|---|---|
| 테스트/빌드/정해진 완료 신호가 나올 때까지 반복 실행 | `ralph-loop` | 실행 재시도와 completion loop가 중심 |
| 외부 GPT/deep research에 넘길 프롬프트와 컨텍스트 패키지 생성 | `gpt-research` | 산출물이 research prompt |
| 가설을 세우고 비교 실험하며 best state를 찾기 | `goal-research-loop` | baseline, ledger, keep/revert 판단이 중심 |

## Mode routing

### `design`

다음이면 먼저 `design`으로 시작합니다.

- metric이 아직 모호함
- mutable surface가 너무 넓음
- hard gate가 비어 있음
- 사용자 목표를 더 잘게 쪼개야 함

### `guided-loop`

기본값입니다.

- write surface가 있거나
- qualitative rubric이 들어가거나
- 각 라운드의 keep/revert 이유를 사용자와 공유하는 편이 안전할 때

### `autonomous-loop`

아래를 모두 만족할 때만 사용합니다.

- 사용자가 명시적으로 autonomous run을 요청함
- contract가 채점 가능하고 비어 있지 않음
- write surface와 budget이 작고 경계가 명확함
- stop condition이 deterministic하거나 매우 분명함
- 고비용/고위험/파괴적 작업이 포함되지 않음

## Escalation triggers

아래 중 하나면 `escalate`를 고려합니다.

- 새 mutable surface를 열어야 함
- 사람 정책 판단이나 외부 승인 없이는 진행이 위험함
- metric 자체가 신뢰되지 않음
- evidence가 서로 충돌해 keep/revert를 정할 수 없음

## Autonomous no-go examples

다음은 기본적으로 autonomous-loop에 넣지 않습니다.

- production deploy
- credential rotation
- irreversible data mutation
- 명시 예산 없는 유료 API 대량 사용
