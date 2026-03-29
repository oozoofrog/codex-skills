# Proxy Metric Patterns

정답 숫자가 바로 없는 작업은 **proxy metric**을 먼저 설계해야 합니다.

## Rules

- hard gate와 score를 섞지 않습니다
- rubric 축은 **3~5개**만 둡니다
- 각 축은 반드시 evidence source와 연결합니다
- baseline을 `round 0`으로 먼저 남깁니다
- rubric이 바뀌면 같은 루프를 계속하지 말고 `rescope`로 기록합니다

## Recommended scoring scale

간단한 qualitative 작업은 아래처럼 **0~2점**으로 두면 비교가 쉽습니다.

- `0` — 기준 미달 또는 부재
- `1` — 부분 충족
- `2` — 명확히 충족

primary metric은 총점 또는 핵심 축 통과 개수로 둡니다.

## Reusable rubric: skill / prompt / workflow improvement

| 축 | 질문 | evidence 예시 |
|---|---|---|
| trigger clarity | 언제 쓰고 언제 쓰지 말아야 하는가가 분명한가 | `description`, fit section, adjacent skill 구분 |
| operator routing | 운영자가 바로 시작하고 멈출 수 있는가 | `When to use`, `Do not use when`, `Quick start`, `Output expectation` 섹션 |
| contract readiness | 바로 contract를 쓸 수 있는가 | contract template, mode guide |
| evidence discipline | keep/revert 판단을 뒷받침할 기록 형식이 있는가 | ledger columns, status vocabulary |
| operator usability | 다음 라운드를 바로 이어갈 수 있는가 | quick start, example flow, escalation rule |

## Reusable rubric: code or config experimentation

| 축 | 질문 | evidence 예시 |
|---|---|---|
| hard gate pass | 결정적 검사에 통과했는가 | test, lint, build, schema |
| delta quality | baseline 대비 실제 개선이 있는가 | benchmark, failure count, latency |
| regression radius | 새 복잡도나 리스크가 작게 유지되는가 | changed files, rollback ease |
| repeatability | 같은 실험을 다시 재현할 수 있는가 | logged commands, inputs, seed |

## Tie-breaker patterns

동점이면 아래를 우선합니다.

1. 더 단순한 변경
2. 더 적은 top-level instruction 증가
3. 더 작은 write surface
4. 더 쉬운 rollback

## Anti-patterns

- “느낌상 더 좋아 보임”을 primary metric으로 삼기
- 여러 가설을 한 라운드에서 같이 바꾸기
- baseline 없이 첫 시도를 best state로 취급하기
- rubric을 바꾸고도 같은 score line에서 비교를 계속하기
