---
name: goal-research-loop
description: Use this skill when the user explicitly wants a goal-directed research loop that keeps proposing, testing, logging, and refining ideas toward a stated objective across repeated iterations or autonomous runs. Do not use it for one-shot summaries or when no evaluation signal can be defined.
---

# Goal Research Loop

특정 목적이 주어졌을 때 **반복 실험·검증·기록**을 통해 계속 개선하는 연구 루프를 설계하고 운영합니다.

## Important

- 이 스킬은 사용자가 **명시적으로** 지속 연구, 반복 개선, autonomous/overnight experimentation을 원할 때만 사용합니다.
- 시작 전에 반드시 **objective, mutable surface, evaluation contract, budget, stop condition**을 먼저 정합니다.
- 측정 가능한 신호가 없으면 바로 루프를 돌리지 말고, **hard gate + proxy metric**을 먼저 정의하거나 범위를 다시 잡습니다.
- 명시 요청이 없으면 기본은 **bounded loop (예: 3~5회)** 입니다. 무기한 루프는 explicit-only입니다.

## Modes

- `design` — 루프 계약과 평가식을 설계만 한다
- `guided-loop` — 각 라운드 결과를 공유하며 연구를 진행한다
- `autonomous-loop` — 중간 확인 없이 정해진 stop condition까지 계속 진행한다

## Use references

- `references/loop-contract.md`
- `references/iteration-heuristics.md`
- `references/result-ledger-template.md`

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
4. **Run one hypothesis at a time**
   - 한 라운드에는 가설 하나만 검증합니다.
   - 변경 → 실행/조사 → 평가 → 기록 → keep/revert를 한 덩어리로 끝냅니다.
5. **Decide with evidence**
   - hard gate 실패면 metric 개선이 있어도 기본적으로 reject합니다.
   - 개선 폭이 작다면 복잡도 증가 비용과 함께 판단합니다.
   - 2회 이상 같은 실패가 반복되면 `refine` 대신 `pivot` 또는 `rescope`로 전환합니다.
6. **Maintain a ledger**
   - 각 실험은 `result-ledger-template.md` 형식으로 남깁니다.
   - baseline, keep, discard, crash를 구분합니다.
7. **Stop cleanly**
   - 목표 달성, 예산 소진, 반복 정체, 사용자 중단, 리스크 증가 중 하나가 발생하면 종료합니다.
   - 마지막에는 현재 best state, 남은 리스크, 다음 실험 후보를 요약합니다.

## Decision rules

- **hard gates > primary metric > secondary metrics > simplicity**
- 가능한 한 **작은 변경 + 짧은 피드백 루프**를 우선합니다.
- write task에서는 되돌릴 수 있는 단위로 commit 또는 diff를 나눕니다.
- research-only task에서도 결과물은 표, 로그, 비교표처럼 누적 가능하게 남깁니다.

## Review Harness
- mode: required
- 공통 기준: `../../../docs/review-harness.md`
- planner: objective, metric, mutable surface, budget, stop rule을 계약으로 먼저 정한다
- generator: 가설을 하나씩 실행하고 결과를 ledger에 기록하며 keep/revert를 수행한다
- evaluator: contract 대비 hard gate, metric, evidence 품질, 반복 discipline을 독립적으로 점검한다
- 평가축: 목표 명확성, 평가 가능성, evidence 품질, keep/revert 정당성, 반복 전략의 건전성
- artifacts/evidence: loop contract, baseline, experiment ledger, 실행 로그 또는 조사 근거, 최종 delta summary
- pass condition: 목표를 실제로 전진시켰거나, 왜 중단했는지 evidence 기반으로 설명 가능한 상태여야 한다
- 자동 다음 행동: `pass`면 best state 요약 후 종료, `refine`이면 같은 계약으로 다음 가설 실행, `pivot`이면 접근 전략 변경, `rescope`면 계약 재작성, `stop`이면 남은 리스크와 다음 후보만 남기고 종료한다

## Output expectation

- 선택한 mode
- objective와 evaluation contract
- 현재 baseline / best-known state
- 최근 라운드 결과와 keep/revert 판단
- 다음 실험 또는 종료 사유
