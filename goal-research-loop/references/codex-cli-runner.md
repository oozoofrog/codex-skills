# Codex CLI Runner

`goal-research-loop` 스킬에는 **Codex CLI를 반복 호출하는 host-managed runner**가 포함됩니다.

경로:

- `scripts/codex_goal_research_loop.py`
- `scripts/goal-research-loop.sh`
- `templates/program.md`
- `templates/contract.md`
- `templates/state_snapshot.md`
- `templates/ledger.tsv`
- `schemas/round-result.schema.json`

## 왜 필요한가

`karpathy/autoresearch`가 `program.md + results.tsv + keep/discard 루프`를 중심으로 돌아가듯,
이 runner는 `goal-research-loop`용으로 다음 아티팩트를 유지합니다.

- `program.md` — 사람이 유지하는 objective / scope / operator note
- `contract.md` — hard gates / metric / budget / stop condition
- `state_snapshot.md` — best-known state / active hypothesis / next candidates
- `ledger.tsv` — 라운드별 결과 기록
- `rounds/round-XXX/` — prompt / stdout / evidence / structured response 보관

차이점은 `goal-research-loop`의 핵심 규칙인
`hard gates / experiment status / control action` 분리를 구조적으로 강제한다는 점입니다.

## 스킬이 runner를 우선 선택해야 하는 때

아래면 `goal-research-loop`는 **runner 사용을 우선**하는 편이 좋습니다.

- 사용자가 repeatable / autonomous / overnight loop를 원할 때
- 다음 세션에서도 같은 objective를 이어받아야 할 때
- contract, snapshot, ledger를 파일로 유지해야 할 때
- 실험 결과를 round directory 단위로 재검토해야 할 때

아래면 runner 없이 contract 설계만 먼저 해도 됩니다.

- 아직 `design` 단계라 metric과 hard gate가 비어 있을 때
- 사용자가 실제 실행보다 전략 설계/초안만 원할 때
- 루프를 돌리기보다 adjacent skill 경계 정리가 먼저일 때

## 권장 명령 선택

가장 자주 쓰는 명령은 아래 3개입니다.

```bash
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh init /path/to/workspace "objective"
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh status /path/to/workspace
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh run /path/to/workspace --max-rounds 3 --search --full-auto
```

원칙:

1. 새 루프면 `init`
2. 이어받기 전 점검이면 `status`
3. bounded execution이면 `run --max-rounds`
4. explicit autonomous opt-in일 때만 Python runner의 `--loop-forever`

## 기본 흐름

### 1) 템플릿 초기화

간편 wrapper:

```bash
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh \
  init \
  /path/to/workspace \
  "Codex CLI를 이용해 목표 지향 연구 루프를 계속 개선한다"
```

직접 Python 실행:

```bash
python3 ~/.codex/skills/goal-research-loop/scripts/codex_goal_research_loop.py \
  init \
  --workspace /path/to/workspace \
  --objective "Codex CLI를 이용해 목표 지향 연구 루프를 계속 개선한다"
```

### 2) program / contract 수정

최소한 아래를 채우는 편이 좋습니다.

- mutable surface
- immutable constraints
- hard gates
- primary metric
- budget
- stop condition

### 3) bounded loop 실행

간편 wrapper:

```bash
~/.codex/skills/goal-research-loop/scripts/goal-research-loop.sh \
  run \
  /path/to/workspace \
  --max-rounds 5 \
  --search \
  --full-auto
```

직접 Python 실행:

```bash
python3 ~/.codex/skills/goal-research-loop/scripts/codex_goal_research_loop.py \
  run \
  --workspace /path/to/workspace \
  --max-rounds 5 \
  --search \
  --full-auto
```

### 4) 장시간 실행

사용자가 명시적으로 원할 때만:

```bash
python3 ~/.codex/skills/goal-research-loop/scripts/codex_goal_research_loop.py \
  run \
  --workspace /path/to/workspace \
  --loop-forever \
  --search \
  --full-auto
```

`goal-research-loop.sh`는 intentionally bounded flow에 집중합니다.
무기한 또는 특별한 플래그가 필요하면 Python runner를 직접 호출하는 편이 더 명시적입니다.

## Git keep/revert 동작

git 저장소에서 깨끗한 working tree로 시작하면 runner는 `autoresearch`처럼 동작합니다.

- `keep` → 기본적으로 자동 commit
- `discard` / `crash` → workspace를 `HEAD`로 되돌림

이렇게 하면 다음 라운드가 항상 **현재 best-known state**에서 시작됩니다.

원하지 않으면 `--no-commit-on-keep`로 끌 수 있지만,
그 경우 discard 시점의 자동 복구 안정성은 떨어집니다.

## Runner가 Codex에 요구하는 것

각 라운드에서 Codex는:

1. 스킬 문서와 references를 읽고
2. 가설 하나만 선택하고
3. 필요한 변경/검증을 수행하고
4. `state_snapshot.md`와 `rounds/round-XXX/evidence.md`를 갱신하고
5. JSON schema에 맞는 structured result를 반환합니다.

호스트 스크립트는 이 structured result를 기반으로 `ledger.tsv`를 append하고,
필요하면 keep/discard에 따라 git 상태를 관리합니다.

## Skill operator checklist

runner를 쓸 때는 응답에 아래를 함께 남기는 편이 좋습니다.

- 왜 script-first인지
- init / status / run 중 어떤 명령을 쓸지
- workspace 경로
- bounded인지 autonomous인지
- 예상 산출물 위치 (`.goal-research-loop/`)

## 추천 사용 조건

- objective가 한 문장으로 압축될 때
- baseline과 비교 가능한 metric 또는 proxy metric이 있을 때
- mutable surface가 좁을 때
- 한 라운드 한 가설 원칙을 지킬 수 있을 때

metric이 아직 비어 있으면 먼저 `design`처럼 contract를 보강하고,
`run`은 그 다음에 쓰는 편이 안전합니다.
