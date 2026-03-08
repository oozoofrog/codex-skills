# Auth and Safety

## Current Local Reality Check

이 머신에서 스킬 생성 시점 기준 `claude auth status`는 `loggedIn: false`였다.
따라서 실제 사용 전 인증 상태를 다시 확인하기.

## 기본 안전 규칙

- `claude -p`는 신뢰 가능한 로컬 디렉터리에서만 사용하기.
- Claude가 수정했다고 끝내지 말고 Codex가 반드시 다시 검증하기.
- 범위가 큰 구현은 여러 번의 작은 호출로 나누기.
- 권한이 민감한 작업은 먼저 Codex가 범위를 잠그기.
- 같은 단계에서 Codex와 Claude가 동시에 구현하지 않기.
- 독립 리뷰는 구현했던 같은 Claude 세션에 맡기지 않기.
- iOS/Swift 작업이면 가능한 한 Task Brief 기반 구조화 입력을 사용하기.

## 인증이 안 되어 있을 때

다음 중 하나를 선택하기.
- 사용자가 `claude auth login`을 수행하게 안내하기.
- Codex 단독 흐름으로 fallback 하기.
- Claude 없이도 가능한 분석/구현만 진행하기.

## 실패 처리

다음을 완료처럼 보고하지 말기.
- auth failure
- CLI timeout
- 출력 형식 불량
- 너무 넓은 구현으로 인한 과도한 수정

실패 시에는 반드시 적기.
- 실패한 명령
- 실패 원인 요약
- 다음 수정안 또는 fallback

## 의견 충돌 처리

Codex와 Claude 결론이 다르면 다음 순서로 최종 판단하기.
1. correctness
2. minimal diff
3. architecture consistency
4. testability
5. release risk
