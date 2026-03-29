# Worked Example: Skill Improvement Loop

아래는 `goal-research-loop`를 **스킬 문서 개선 작업**에 적용하는 최소 예시입니다.

목적은 운영자가 contract, ledger, state snapshot이 **어떻게 이어지는지 한 번에 보는 것**입니다.

## Scenario

- objective: `goal-research-loop` 스킬의 operator confusion을 줄인다
- mode: `guided-loop`
- execution substrate: `agent-first`
- mutable surface: `SKILL.md`, `references/*.md`, `agents/openai.yaml`
- immutable constraints: explicit-only 유지, progressive disclosure 유지, copy 설치 구조 유지

## Example contract

```md
## Research Contract
- objective: goal-research-loop 스킬의 operator confusion을 줄인다
- mode: guided-loop
- execution substrate: agent-first
- routing rationale: 이번 라운드는 실행 자동화보다 용어 구조와 설명 개선이 목적이므로 agent-first
- mutable surface: SKILL.md, references/*.md, agents/openai.yaml
- immutable constraints: explicit-only 유지, progressive disclosure 유지, copy install 구조 유지
- hard gates: audit 통과, install dry-run 통과, copy install 통과
- primary metric: operator confusion 감소
- tie-breakers: 작은 write surface, 더 쉬운 handoff
- decision layers: hard gates=pass/fail, experiment status=keep/discard/crash, control action=pass/refine/pivot/rescope/escalate/stop
- baseline: decision vocabulary가 암묵적으로만 구분됨
- evidence sources: audit output, install dry-run, installed file tree, diff
- budget: 2 hypotheses
- stop condition: 혼동이 큰 핵심 지점 1개 이상 해소 시 종료 가능
- state snapshot: current best state와 next candidates 유지
- ledger: markdown table
```

## Example ledger

```md
| round | hypothesis | change | hard gates | metric | evidence | experiment status | control action | next step | notes |
|---|---|---|---|---|---|---|---|---|---|
| 0 | baseline | none | pass | mixed | file review | keep | refine | decision layer 명시화 | 용어 층위가 암묵적 |
| 1 | decision layers를 분리하면 혼동이 줄어든다 | decision-layer reference 추가, ledger/snapshot 보강 | pass | improved | audit + install dry-run | keep | refine | worked example 추가 | 개념은 정리됐지만 예시 없음 |
| 2 | worked example를 추가하면 first-time usability가 오른다 | contract→ledger→snapshot 예시 추가 | pass | improved | operator walkthrough + audit | keep | pass | 종료 또는 README 보강 | 처음 진입하는 운영자가 더 빠르게 따라올 수 있음 |
```

## Example state snapshot

```md
## State Snapshot
- objective: goal-research-loop 스킬의 operator confusion을 줄인다
- mode: guided-loop
- execution substrate: agent-first
- baseline: decision vocabulary가 암묵적으로만 구분됨
- best-known state: decision layers와 예시가 함께 제공됨
- current active hypothesis: README discoverability를 보강하면 invocation 연결이 더 쉬워질 수 있음
- most recent experiment status: keep
- most recent control action: pass
- open risks: repo-level discoverability는 아직 약할 수 있음
- next candidate hypotheses:
  - README에 skill blurb 추가
  - contract filled example를 하나 더 추가
  - 예시를 code/config 실험 시나리오로 확장
- handoff notes: 다음 라운드가 없다면 현재 best-known state를 요약하고 종료
```

## How to read this example

핵심은 아래 3가지를 분리해서 보는 것입니다.

1. **hard gates**
   - 이번 실험이 최소 기준을 넘었는가
2. **experiment status**
   - 이번 결과를 best-known state로 채택하는가
3. **control action**
   - 루프를 다음에 어떻게 움직일 것인가

예를 들어:

- `hard gates: pass`
- `experiment status: keep`
- `control action: refine`

는 “이번 결과는 채택하지만 루프는 계속”을 뜻합니다.

반대로:

- `hard gates: pass`
- `experiment status: keep`
- `control action: pass`

는 “이번 결과를 채택하고 이번 루프를 종료해도 됨”을 뜻합니다.

## Operator takeaway

처음 쓸 때는 아래 순서만 기억하면 됩니다.

1. contract를 쓴다
2. 한 라운드 한 가설만 기록한다
3. `hard gates / experiment status / control action`을 분리해 적는다
4. 매 라운드 끝에 state snapshot을 갱신한다
