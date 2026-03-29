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
6. ledger 기록 + state snapshot 갱신
7. experiment status(`keep / discard / crash`) 결정
8. control action(`pass / refine / pivot / rescope / escalate / stop`) 결정

## Decision layers

각 라운드는 아래 3개 층위로 닫습니다.

1. **hard gate result** — `pass / fail`
2. **experiment status** — `keep / discard / crash`
3. **control action** — `pass / refine / pivot / rescope / escalate / stop`

예를 들어 `hard gates: pass`, `experiment status: keep`, `control action: refine`는
“이번 결과는 채택하지만 아직 루프를 더 돈다”는 뜻입니다.

## Experiment status rules

### Keep

- hard gate 통과
- primary metric 개선
- 또는 동일 성능인데 더 단순함

### Discard

- hard gate 실패
- metric 악화
- 개선 폭이 미미한데 복잡도만 증가

### Crash

- 실행 자체가 무너짐
- 아이디어 이전에 조작/실행이 성립하지 않음

## Control action rules

### Refine

- 같은 계약 안에서 다음 가설을 계속 시도할 가치가 있음
- 이번 라운드의 keep/discard 이유가 다음 선택을 바로 안내함

### Pivot

- 2회 이상 비슷한 실패
- 개선이 정체됨
- 현재 가설군 자체가 잘못된 것 같음

### Rescope

- objective가 너무 넓음
- metric이 애매함
- mutable surface가 과도하게 큼

### Escalate

- 사람 판단이나 외부 승인 없이는 진행이 위험함
- evidence가 충돌해 keep/revert를 자신 있게 결정할 수 없음
- 새 mutable surface를 열어야 해서 계약을 그대로 유지할 수 없음

### Pass

- 목표 달성 또는 충분한 전진이 확인됨
- 현재 best-known state를 보고 종료해도 됨

### Stop

- 예산 소진
- 반복 정체
- 리스크 상승으로 추가 진행 이득이 낮음

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

## State continuity

루프가 여러 세션에 걸치면 아래를 매 라운드 끝에 갱신합니다.

- 현재 best-known state
- 최근 discard/crash 이유
- 지금 열려 있는 가설 1개
- 다음 후보 1~3개

이 정보가 없으면 루프는 쉽게 “조금씩 다른 중복 실험”으로 무너집니다.

## When to ask the user

아래에서만 다시 묻습니다.

- 평가 계약이 끝내 정의되지 않을 때
- 새 write surface를 열어야 할 때
- 고비용/고위험 리소스 사용이 필요할 때
- 연구 목표 자체를 바꿔야 할 때
- evidence 충돌로 사람이 keep/revert를 정해야 할 때
