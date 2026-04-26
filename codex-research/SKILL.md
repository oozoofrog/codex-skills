---
name: codex-research
description: 기존 `.codex-research/` 상태 디렉터리와 Codex CLI 기반 반복 연구 runner를 운영·재개·점검할 때 사용합니다. 새 연구 루프를 설계할 때는 `goal-research-loop`를 우선 사용하고, 이 스킬은 기존 `codex-research` runner 호환이 필요할 때 사용합니다.
---

# Codex Research

Codex CLI를 반복 호출하여 목표 지향 연구 루프를 운영하는 legacy-compatible runner입니다. 새 루프 계약을 처음 설계하는 작업은 `goal-research-loop`가 기본이고, 이 스킬은 `.codex-research/` 상태를 가진 기존 작업을 재개하거나 `codex-research.sh` runner를 직접 써야 할 때 사용합니다.

## When to use
- 기존 workspace에 `.codex-research/`가 있고 상태 확인, 재개, run이 필요할 때
- 사용자가 `codex-research`, `.codex-research`, `codex-research.sh`를 명시적으로 언급할 때
- 이전 codex-research runner가 만든 `program.md`, `contract.md`, `state_snapshot.md`, `ledger.tsv`를 이어서 운영해야 할 때

## Do not use when
- 새 목표 연구 루프를 처음 설계해야 할 때 → `goal-research-loop`
- 단발 Codex CLI 위임이나 세컨드 오피니언이면 → `hey-codex`
- 단순 요약/조사/구현이면 현재 세션에서 직접 처리합니다.

## Quick start
1. `~/.codex/skills/codex-research/scripts/preflight.sh`로 `codex` CLI를 확인합니다.
2. workspace의 `.codex-research/contract.md`와 `state_snapshot.md`를 읽어 hard gate, metric, stop condition을 확인합니다.
3. 상태가 꼬였으면 `codex-research.sh status`를 먼저 실행하고, 필요하면 `ledger.tsv`와 `state_snapshot.md`를 직접 대조합니다.
4. bounded 실행이 기본입니다. 명시 동의 없이 `--loop-forever`를 사용하지 않습니다.
5. 라운드 후 `ledger.tsv`, `state_snapshot.md`, `rounds/*/evidence.md`를 근거로 결과를 보고합니다.

## CLI usage

전역 설치 기준 경로를 사용합니다.

```bash
~/.codex/skills/codex-research/scripts/codex-research.sh init <workspace> "objective"
~/.codex/skills/codex-research/scripts/codex-research.sh status <workspace>
~/.codex/skills/codex-research/scripts/codex-research.sh run <workspace> --max-rounds 3 --search --full-auto
```

Python runner를 직접 호출해야 하면:

```bash
python3 ~/.codex/skills/codex-research/scripts/codex-research.py run \
  --workspace <workspace> \
  --max-rounds 3 \
  --search \
  --full-auto
```

## State directory

```
.codex-research/
├── program.md
├── contract.md
├── state_snapshot.md
├── ledger.tsv
├── runtime/
└── rounds/
```

## Result model

hard gate, experiment status, control action을 한 칸에 섞지 않습니다.

| 층위 | 값 | 의미 |
|---|---|---|
| hard gate result | pass / fail | 최소 통과선. fail이면 metric 개선과 무관하게 reject |
| experiment status | keep / discard / crash | best-known state 대비 결과 유지 여부 |
| control action | pass / refine / pivot / rescope / escalate / stop | 다음 라운드 방향 |

## Use resources
- `references/loop-contract.md`
- `scripts/preflight.sh`
- `scripts/codex-research.sh`
- `scripts/codex-research.py`
- `templates/codex-research/`

## Review Harness
- mode: optional
- 공통 기준: `../../../docs/review-harness.md`
- generator: Codex CLI runner가 라운드별 hypothesis/change/verification을 실행한다
- evaluator: 부모 세션이 ledger, state snapshot, evidence, git diff를 검토한다
- 평가축: contract 준수, hard gate 신뢰성, 상태 파일 일관성, keep/discard 판단 안전성
- artifacts/evidence: `ledger.tsv`, `state_snapshot.md`, `rounds/*/evidence.md`, git diff, runner output
- pass condition: hard gate가 통과하고 best-known state가 명확할 때만 keep 또는 종료로 판단한다
- 자동 다음 행동: `pass`면 종료, `refine`이면 bounded 재실행, `pivot/rescope/escalate`면 사용자에게 다음 결정을 보고한다

## Output expectation
- 선택한 모드와 실행 명령
- 현재 best state와 metric 변화
- 최근 라운드의 hard gate / experiment status / control action
- 남은 budget, 다음 후보, 중단 사유
