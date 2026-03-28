# Loop Contract

연속 연구 루프는 시작 전에 반드시 **채점 가능한 계약**을 가져야 합니다.

## Contract checklist

1. **Objective**
   - 한 문장 목표
   - 성공 기준 1~3개
2. **Mode**
   - `design`
   - `guided-loop`
   - `autonomous-loop`
3. **Mutable surface**
   - 바꿀 수 있는 파일, 문서, 프롬프트, 실험 변수
4. **Immutable constraints**
   - 바꾸면 안 되는 파일, 정책, 의존성, 외부 조건
5. **Hard gates**
   - 반드시 통과해야 하는 결정적 검사
6. **Primary metric**
   - 최우선 숫자/판정 기준
7. **Tie-breakers**
   - 동점일 때 보는 2차 기준
8. **Baseline**
   - 현재 기준 상태
9. **Budget**
   - 최대 반복 수, 시간, 비용, 토큰, 컴퓨트
10. **Stop condition**
   - 종료 조건과 사람에게 넘길 조건
11. **Ledger path**
   - 실험 기록 위치 또는 표 형식

## Markdown template

```md
## Research Contract
- objective: ...
- mode: design | guided-loop | autonomous-loop
- mutable surface: ...
- immutable constraints: ...
- hard gates: ...
- primary metric: ...
- tie-breakers: ...
- baseline: ...
- budget: ...
- stop condition: ...
- ledger: ...
```

## Design notes

- hard gate가 없다면, 적어도 “실패하면 즉시 reject” 되는 최소 규칙을 먼저 만듭니다.
- primary metric은 가능한 한 **하나**로 유지합니다.
- subjective quality만 있는 작업은 rubric을 먼저 수치화하거나 등급화합니다.
- autonomous-loop에서는 contract가 비어 있거나 모호하면 시작하지 않습니다.
