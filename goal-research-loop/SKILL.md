---
name: goal-research-loop
description: Use this skill when the user explicitly wants a goal-directed research loop that keeps proposing, testing, logging, and refining ideas toward a stated objective across repeated iterations or autonomous runs. Do not use it for one-shot summaries or when no evaluation signal can be defined.
---

# Goal Research Loop

특정 목적이 주어졌을 때 **반복 실험·검증·기록**을 통해 계속 개선하는 연구 루프를 설계하고 운영합니다.

## When it fits

- 사용자가 **명시적으로** 지속 연구, 반복 개선, autonomous/overnight experimentation을 원할 때
- objective를 한 문장으로 압축할 수 있고, baseline 대비 개선을 비교할 수 있을 때
- 한 라운드마다 **가설 1개 + 변경 1덩어리 + 평가 1회**로 닫을 수 있을 때

## Do not use when

- 한 번의 요약/정리면 충분한 작업
- 직접 목적은 “테스트/빌드가 통과할 때까지 반복 실행”인 작업 → `ralph-loop`
- 직접 목적은 외부 GPT/deep research에 넘길 **리서치 프롬프트 생성**인 작업 → `gpt-research`
- hard gate나 proxy metric을 끝내 정의할 수 없는 작업

## Important

- 이 스킬은 **explicit-only**입니다.
- 시작 전에 반드시 **objective, mutable surface, evaluation contract, budget, stop condition**을 먼저 정합니다.
- 측정 가능한 신호가 없으면 바로 루프를 돌리지 말고, **hard gate + proxy metric**을 먼저 정의하거나 범위를 다시 잡습니다.
- 사용자가 **실제로 반복 실행 가능한 Codex 연구 루프를 원하면** ad-hoc 수동 운영보다 `scripts/goal-research-loop.sh` 또는 `scripts/codex_goal_research_loop.py`를 우선 사용합니다.
- 스크립트 경로를 제안할 때는 전역 설치 기준으로 `~/.codex/skills/goal-research-loop/scripts/...` 경로를 우선 안내합니다.
- 명시 요청이 없으면 기본은 **bounded loop (예: 3~5회)** 입니다. 무기한 루프는 explicit-only입니다.
- `autonomous-loop`는 사용자 opt-in, bounded surface, 명확한 stop rule이 모두 있을 때만 사용합니다.
- 같은 실패 패턴이 2회 이상 반복되면 `refine` 대신 `pivot`, `rescope`, `escalate`를 우선 검토합니다.
- 반복 세션이나 `autonomous-loop`에서는 **baseline / best-known state / active hypothesis / next candidates**를 담은 state snapshot을 유지합니다.
- **hard gate 결과**, **실험 결과 상태**, **루프 제어 상태**를 한 칸에 섞어 쓰지 않습니다.

## Modes

- `design` — 루프 계약과 평가식을 설계만 한다
- `guided-loop` — 각 라운드 결과를 공유하며 연구를 진행한다
- `autonomous-loop` — 중간 확인 없이 정해진 stop condition까지 계속 진행한다
- 선택 기준은 `references/fit-and-mode-routing.md`를 먼저 봅니다.

## Use references

- `references/fit-and-mode-routing.md`
- `references/loop-contract.md`
- `references/decision-layers-and-status-mapping.md`
- `references/iteration-heuristics.md`
- `references/proxy-metric-patterns.md`
- `references/result-ledger-template.md`
- `references/state-snapshot-and-handoff.md`
- `references/worked-example-skill-improvement.md`
- `references/codex-cli-runner.md`
- `scripts/codex_goal_research_loop.py`
- `scripts/goal-research-loop.sh`
- `templates/program.md`
- `templates/contract.md`
- `templates/state_snapshot.md`
- `templates/ledger.tsv`
- `schemas/round-result.schema.json`

## Quick start

1. `fit-and-mode-routing.md`로 **이 스킬이 맞는지**와 mode를 먼저 고릅니다.
2. `loop-contract.md` 템플릿으로 계약을 쓰고 baseline을 확보합니다.
3. `decision-layers-and-status-mapping.md`로 **gate / experiment status / control action** 층위를 먼저 맞춥니다.
4. metric이 정량이 아니면 `proxy-metric-patterns.md`로 rubric을 먼저 고릅니다.
5. 반복 세션이면 `state-snapshot-and-handoff.md` 템플릿으로 best-known state와 다음 후보를 먼저 잡습니다.
6. 처음 운영하면 `worked-example-skill-improvement.md`로 contract → ledger → snapshot 연결 예시를 한번 봅니다.
7. 한 라운드에 가설 하나만 실행하고 `result-ledger-template.md` 형식으로 기록합니다.
8. 각 라운드는 **hard gate 결과 + experiment status + control action**으로 닫습니다.

### Codex CLI runner quick start

`karpathy/autoresearch`의 `program.md + results.tsv + keep/discard loop` 패턴을
`goal-research-loop` 규칙에 맞게 옮긴 host-managed runner가 포함되어 있습니다.

```bash
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh init /path/to/workspace "한 문장 objective"

~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh run /path/to/workspace --max-rounds 3 --search --full-auto

python3 ~/.codex/skills/goal-research-loop/scripts/codex_goal_research_loop.py \
  init \
  --workspace /path/to/workspace \
  --objective "한 문장 objective"

python3 ~/.codex/skills/goal-research-loop/scripts/codex_goal_research_loop.py \
  run \
  --workspace /path/to/workspace \
  --max-rounds 3 \
  --search \
  --full-auto
```

세부 동작은 `references/codex-cli-runner.md`를 참고하세요.

### Script-first routing

아래 조건이면 **script-first**로 운영합니다.

- 사용자가 “계속 돌려”, “반복 연구”, “overnight”, “자동으로 이어서”처럼 **반복 실행 자체**를 원할 때
- 같은 objective로 여러 세션에 걸쳐 `program / contract / snapshot / ledger`를 유지해야 할 때
- 사람이 직접 매 라운드 프롬프트를 다시 조립하는 것보다, **재현 가능한 host-managed loop**가 더 적합할 때

권장 우선순위:

1. 새 루프 시작 → `goal-research-loop.sh init`
2. 현재 상태 확인 → `goal-research-loop.sh status`
3. bounded 연구 실행 → `goal-research-loop.sh run --max-rounds N`
4. 사용자가 명시적으로 원할 때만 → `codex_goal_research_loop.py run --loop-forever`

반대로 아래는 수동 설계만 먼저 해도 됩니다.

- 아직 contract가 비어 있어 `design`부터 해야 할 때
- hard gate / metric / budget이 정의되지 않아 스크립트 실행이 이른 때
- 단순 one-shot 제안이나 contract 초안만 필요한 때

## Workflow

1. **Frame the objective**
   - 사용자의 목적을 한 문장 목표와 1~3개의 성공 기준으로 압축합니다.
   - 연구 대상, 변경 가능 범위, 변경 금지 범위를 분리합니다.
2. **Choose the operating mode**
   - `design / guided-loop / autonomous-loop` 중 하나를 고릅니다.
   - 사용자 요청이 없으면 보수적으로 `guided-loop` 또는 bounded `design`으로 시작합니다.
3. **Write the contract**
   - `loop-contract.md` 템플릿으로 hard gates, primary metric, tie-breaker, budget, stop condition을 명시합니다.
   - 가능하면 baseline을 먼저 확보합니다.
   - 반복 세션이면 state snapshot과 ledger 위치도 같이 정합니다.
   - 실행 가능한 반복 루프가 목적이면, 이 단계에서 `goal-research-loop.sh init`으로 템플릿 파일을 먼저 생성하는 편을 우선 검토합니다.
4. **Run one hypothesis at a time**
   - 한 라운드에는 가설 하나만 검증합니다.
   - 변경 → 실행/조사 → 평가 → 기록 → keep/revert를 한 덩어리로 끝냅니다.
   - script-first 상황이면 수동 운영보다 `goal-research-loop.sh run`으로 round artifacts를 남기며 진행하는 편을 우선합니다.
5. **Decide with evidence**
   - hard gate 실패면 metric 개선이 있어도 기본적으로 reject합니다.
   - 개선 폭이 작다면 복잡도 증가 비용과 함께 판단합니다.
   - 2회 이상 같은 실패가 반복되면 `refine` 대신 `pivot`, `rescope`, `escalate`를 우선 검토합니다.
6. **Maintain a ledger**
   - 각 실험은 `result-ledger-template.md` 형식으로 남깁니다.
   - hard gate는 `pass/fail`, experiment status는 `keep/discard/crash`, control action은 `pass/refine/pivot/rescope/escalate/stop`으로 분리합니다.
7. **Stop cleanly**
   - 목표 달성, 예산 소진, 반복 정체, 사용자 중단, 리스크 증가 중 하나가 발생하면 종료합니다.
   - 마지막에는 현재 best state, 남은 리스크, 다음 실험 후보를 요약합니다.

## Decision rules

- **hard gates > primary metric > secondary metrics > simplicity**
- 가능한 한 **작은 변경 + 짧은 피드백 루프**를 우선합니다.
- write task에서는 되돌릴 수 있는 단위로 commit 또는 diff를 나눕니다.
- research-only task에서도 결과물은 표, 로그, 비교표처럼 누적 가능하게 남깁니다.

## Operating artifacts

- **Research contract** — objective, metric, mutable surface, budget, stop rule
- **Result ledger** — 각 라운드의 hypothesis / evidence / hard gate / experiment status / control action
- **State snapshot** — baseline, current best state, active hypothesis, open risks, next candidates, most recent control action
- **Evidence bundle** — 실행 로그, 조사 링크, 비교표, diff 등 evaluator가 다시 읽을 수 있는 근거

장기 루프일수록 “무엇을 했는가”보다 **다음 세션이 바로 이어받을 수 있는 상태 표현**이 더 중요합니다.

## Review Harness
- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: objective, metric, mutable surface, budget, stop rule과 decision layer 구분을 계약으로 먼저 정한다
- generator: 가설을 하나씩 실행하고 결과를 ledger에 기록하며 experiment status와 control action을 분리한다
- evaluator: contract 대비 hard gate, metric, evidence 품질, 반복 discipline, decision layer 일관성, 상태 연속성을 독립적으로 점검한다
- 평가축: 목표 명확성, 평가 가능성, evidence 품질, keep/revert 정당성, 반복 전략의 건전성, decision layer 일관성, 세션 간 상태 연속성
- artifacts/evidence: loop contract, baseline, experiment ledger, state snapshot, 실행 로그 또는 조사 근거, 최종 delta summary
- pass condition: 목표를 실제로 전진시켰거나, 왜 중단했는지 evidence 기반으로 설명 가능한 상태여야 한다
- 자동 다음 행동: `pass`면 best state 요약 후 종료, `refine`이면 같은 계약으로 다음 가설 실행, `pivot`이면 접근 전략 변경, `rescope`면 계약 재작성, `escalate`면 사람 또는 별도 evaluator로 넘기고 block 이유를 남긴다, `stop`이면 남은 리스크와 다음 후보만 남기고 종료한다

## Output expectation

- 선택한 mode
- script-first 여부와 사용할 명령
- objective와 evaluation contract
- 현재 baseline / best-known state
- 최근 라운드의 hard gate 결과 / experiment status / control action
- state snapshot 또는 handoff 메모
- 다음 실험 또는 종료 사유
- 필요 시 ledger 발췌와 핵심 evidence
