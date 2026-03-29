# Fit Check and Mode Routing

## Quick fit check

아래 4개가 모두 성립할 때 `goal-research-loop`를 사용합니다.

1. **objective를 한 문장으로 말할 수 있다**
2. **baseline과 비교 가능한 결과**를 만들 수 있다
3. **hard gate 또는 proxy metric**을 정의할 수 있다
4. **budget과 stop rule**을 미리 고정할 수 있다

하나라도 비어 있으면 곧바로 루프를 돌리지 말고 `design` 또는 `rescope`부터 시작합니다.

## Separate mode from execution substrate

`goal-research-loop`에서는 아래 2개를 분리해서 판단합니다.

1. **mode**
   - `design`
   - `guided-loop`
   - `autonomous-loop`
2. **execution substrate**
   - `agent-first`
   - `script-first`

`mode`는 **연구를 어떤 운영 방식으로 진행할지**를 말하고,
`execution substrate`는 **현재 세션의 에이전트가 직접 운영할지, runner script가 host-managed loop를 맡을지**를 말합니다.

이 둘을 섞어 쓰면,

- `design`인데도 무리하게 script-first로 가거나
- `guided-loop`인데도 반복 실행 니즈를 놓치거나
- `autonomous-loop`인데도 runner 없이 설명만 길어지는

문제가 생기기 쉽습니다.

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

## Execution substrate routing

### `agent-first`

아래면 먼저 `agent-first`로 갑니다.

- contract가 비어 있거나 모호함
- hard gate / metric / budget / stop rule 중 하나라도 아직 설계 단계임
- objective를 더 압축하거나 mutable surface를 다시 잘라야 함
- 정책 판단, 설명, 범위 협상, 사용자 의도 해석이 실행보다 중요함
- 이번 작업의 핵심 산출물이 실행 로그보다 **판단 기준 / 계약 / 추천안**에 가까움

권장 기본값:

- `design` → 보통 `agent-first`
- `guided-loop` → contract가 비어 있으면 먼저 `agent-first`

### `script-first`

아래면 `script-first`가 더 잘 맞습니다.

- 사용자가 repeatable / autonomous / overnight loop를 원함
- 같은 objective를 여러 세션에 걸쳐 이어받아야 함
- contract가 채점 가능하고 비어 있지 않음
- mutable surface / budget / stop rule이 좁고 명확함
- `program / contract / snapshot / ledger / rounds` 아티팩트를 파일로 유지하는 편이 유리함
- 사람이 매 라운드 프롬프트를 다시 조립하는 비용이 큼

권장 기본값:

- `autonomous-loop` → 사실상 `script-first`
- `guided-loop` → contract가 실행 가능하고 반복성이 중요하면 `script-first`

## Transition rules

- **agent-first → script-first**
  - contract가 채워졌고
  - baseline이 확보됐고
  - round artifacts 유지가 중요해졌고
  - 반복 실행 이득이 명확해질 때

- **script-first → agent-first**
  - `rescope` 또는 `escalate`가 필요하고
  - 새 mutable surface를 열어야 하거나
  - policy 판단 / conflicting evidence / operator 설명이 먼저일 때

## Default mapping

- `design + agent-first` — 기본 시작점
- `guided-loop + agent-first` — 계약 설계 또는 사용자 공유가 중요할 때
- `guided-loop + script-first` — 계약이 실행 가능하고 반복성/아티팩트 유지가 중요할 때
- `autonomous-loop + script-first` — 명시 opt-in일 때만

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
