# Agent-first vs Script-first Routing

`goal-research-loop`에서는 **mode**와 **execution substrate**를 분리해서 고릅니다.

- `mode` = `design | guided-loop | autonomous-loop`
- `execution substrate` = `agent-first | script-first`

핵심은 아래입니다.

- **mode**는 연구를 어떤 운영 방식으로 진행할지
- **execution substrate**는 누가 루프를 실제로 운용할지

즉, `guided-loop`라고 해서 항상 agent-first도 아니고,
`script-first`라고 해서 항상 autonomous-loop도 아닙니다.

## Quick rule

먼저 아래를 봅니다.

1. contract가 실행 가능한가?
2. 반복 실행 자체가 중요한가?
3. 상태 파일과 round artifacts를 세션 간 유지해야 하는가?
4. 지금 필요한 산출물이 실행 로그인가, 아니면 판단 기준/설계안인가?

## `agent-first`

아래면 `agent-first`가 기본값입니다.

- contract가 아직 비어 있거나 모호함
- hard gate / metric / budget / stop condition을 아직 설계 중임
- objective 압축, mutable surface 재절단, policy 판단이 먼저임
- 사용자가 각 라운드의 reasoning과 keep/revert 이유를 함께 보고 싶어 함
- 이번 요청의 핵심 결과물이 실행보다 **추천안, 비교, 판단 기준**에 가까움

### typical pairings

- `design + agent-first`
- `guided-loop + agent-first`

### why it helps

- scope를 너무 빨리 고정하는 실수를 줄임
- contract가 비어 있는 상태에서 무리하게 runner를 돌리는 일을 막음
- 사용자와 합의가 필요한 기준을 먼저 명시할 수 있음

## `script-first`

아래면 `script-first`가 더 적합합니다.

- 사용자가 repeatable / autonomous / overnight loop를 원함
- contract가 이미 채점 가능하고 비어 있지 않음
- mutable surface / budget / stop rule이 좁고 명확함
- `program / contract / snapshot / ledger / rounds`를 파일로 남겨야 함
- 사람이 매 라운드 프롬프트를 다시 조립하는 비용이 큼

### typical pairings

- `guided-loop + script-first`
- `autonomous-loop + script-first`

### why it helps

- round artifacts를 구조적으로 남길 수 있음
- 같은 objective를 나중에 재개하기 쉬움
- host-managed loop로 실행 discipline을 유지하기 쉬움

## Default mapping

- `design` → 기본적으로 `agent-first`
- `guided-loop` → 둘 다 가능
  - contract가 비어 있으면 `agent-first`
  - contract가 실행 가능하고 반복성이 중요하면 `script-first`
- `autonomous-loop` → 기본적으로 `script-first`

## Transition rules

### `agent-first`에서 `script-first`로 넘길 때

아래가 모두 어느 정도 만족되면 넘길 수 있습니다.

- objective가 한 문장으로 고정됨
- baseline 확보됨
- hard gates / primary metric / budget / stop rule이 채워짐
- mutable surface가 좁아짐
- 반복 실행 이득이 명확함

### `script-first`에서 다시 `agent-first`로 돌아올 때

- `rescope` 또는 `escalate`가 필요함
- 새 mutable surface를 열어야 함
- 정책 판단이나 conflicting evidence 때문에 사람 설명이 먼저임
- 더 이상 “반복 실행”보다 “계약 재설계”가 중요해짐

## Anti-patterns

### 나쁜 예 1 — contract가 비어 있는데 바로 script-first

- 결과: TODO contract를 억지로 끌고 가거나, 근거 없는 자동 실행이 됨

### 나쁜 예 2 — repeatable loop인데 계속 agent-first 수동 운영

- 결과: prompt 재조립 비용이 커지고 state continuity가 약해짐

### 나쁜 예 3 — mode와 substrate를 하나로 취급

- 결과: `design`이면 무조건 수동, `guided-loop`면 무조건 script처럼 오판하기 쉬움

## Recommended output phrasing

최종 응답에는 아래를 함께 남기는 편이 좋습니다.

- `mode: ...`
- `execution substrate: agent-first | script-first`
- `routing rationale: ...`
- script-first라면 사용할 명령

예:

```md
- mode: design
- execution substrate: agent-first
- routing rationale: contract가 비어 있고 이번 요청의 핵심 산출물이 판단 기준 설계이기 때문
```
