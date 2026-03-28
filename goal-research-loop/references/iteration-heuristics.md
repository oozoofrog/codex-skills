# Iteration Heuristics

## 기본 원칙

- **한 라운드 = 한 가설**
- 작은 변경을 선호하고, 결과를 비교 가능하게 만듭니다
- baseline 없이 개선 판단을 하지 않습니다
- 같은 실패가 반복되면 접근을 바꿉니다

## Suggested loop

1. baseline 또는 현재 best state 확인
2. 다음 가설 1개 선택
3. 필요한 최소 변경/조사 수행
4. hard gate 검사
5. metric 비교
6. ledger 기록
7. `keep / discard / crash / pivot / rescope` 중 하나 결정

## Keep / discard / pivot rules

### Keep

- hard gate 통과
- primary metric 개선
- 또는 동일 성능인데 더 단순함

### Discard

- hard gate 실패
- metric 악화
- 개선 폭이 미미한데 복잡도만 증가

### Pivot

- 2회 이상 비슷한 실패
- 개선이 정체됨
- 현재 가설군 자체가 잘못된 것 같음

### Rescope

- objective가 너무 넓음
- metric이 애매함
- mutable surface가 과도하게 큼

## Crash handling

- typo, import, 경로 문제처럼 사소한 실패는 빠르게 1회 수정 후 재시도합니다
- 아이디어 자체가 무너진 crash는 `crash`로 기록하고 넘어갑니다
- 반복 crash는 그 가설군을 폐기합니다

## Simplicity bias

동일하거나 근소한 개선이라면:

- 줄어든 코드
- 덜 복잡한 절차
- 더 적은 전제
- 더 쉬운 재현성

을 우선합니다.

## When to ask the user

아래에서만 다시 묻습니다.

- 평가 계약이 끝내 정의되지 않을 때
- 새 write surface를 열어야 할 때
- 고비용/고위험 리소스 사용이 필요할 때
- 연구 목표 자체를 바꿔야 할 때
