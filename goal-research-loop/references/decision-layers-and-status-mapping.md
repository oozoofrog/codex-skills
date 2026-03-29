# Decision Layers and Status Mapping

`goal-research-loop`에서는 서로 다른 성격의 판단을 **3개 층위**로 분리합니다.

하나의 칸에 다 넣으면 `pass`, `keep`, `refine` 같은 단어가 서로 다른 뜻으로 섞여 운영자가 쉽게 헷갈립니다.

## Layer 1: hard gate result

가설이 **최소 통과선**을 넘었는지 보는 결정적 검사입니다.

- 값: `pass` | `fail`
- 예시: 테스트 통과, lint 통과, 필수 정책 위반 없음

이 값은 “이 실험을 후보로 둘 자격이 있는가?”를 말합니다.

## Layer 2: experiment status

이번 가설이 **현재 best-known state와 비교해 채택되는지**를 나타냅니다.

- 값: `keep` | `discard` | `crash`

### meaning

- `keep` — 현재 best state로 채택
- `discard` — baseline 또는 직전 best보다 못함
- `crash` — 실행 자체가 무너짐

이 값은 “이번 가설 결과를 보존할 것인가?”를 말합니다.

## Layer 3: control action

루프가 **다음에 무엇을 할지**를 정하는 제어 신호입니다.

- 값: `pass` | `refine` | `pivot` | `rescope` | `escalate` | `stop`

### meaning

- `pass` — 목표 달성 또는 이번 루프 종료 가능
- `refine` — 같은 계약 안에서 다음 가설 계속
- `pivot` — 다른 접근 전략으로 전환
- `rescope` — 계약/범위를 다시 씀
- `escalate` — 사람 또는 별도 evaluator 필요
- `stop` — 예산/리스크/정체 때문에 종료

이 값은 “이제 루프를 어떻게 이어갈 것인가?”를 말합니다.

## Recommended recording format

ledger에는 아래처럼 **명시적 컬럼 이름**으로 씁니다.

```md
| round | hard gates | experiment status | control action | notes |
|---|---|---|---|---|
| 1 | pass | keep | refine | 현재 best로 채택, 다음 가설 진행 |
```

bare word만 쓰지 말고, 항상 필드 이름과 함께 씁니다.

나쁜 예:

- `status: pass`

좋은 예:

- `hard gates: pass`
- `experiment status: keep`
- `control action: refine`

## Typical mappings

### Case A — 좋은 실험, 아직 더 돌릴 가치 있음

- hard gates: `pass`
- experiment status: `keep`
- control action: `refine`

### Case B — 통과는 했지만 best보다 못함

- hard gates: `pass`
- experiment status: `discard`
- control action: `refine`

### Case C — 계약 자체를 다시 써야 함

- hard gates: `fail` 또는 애매
- experiment status: `discard`
- control action: `rescope`

### Case D — 실행은 무너졌고 접근도 바꿔야 함

- hard gates: `fail`
- experiment status: `crash`
- control action: `pivot`

### Case E — 목표 달성

- hard gates: `pass`
- experiment status: `keep`
- control action: `pass`

## Operator rule of thumb

판단 순서는 항상 아래입니다.

1. **hard gate**
2. **metric / evidence**
3. **experiment status**
4. **control action**

즉, `control action`은 마지막에 정합니다.
