# Ralph Loop safety rails

## 반드시 지킬 것
- 항상 최대 반복 수를 둔다.
- destructive command를 loop 기본 동작에 넣지 않는다.
- production deploy, secret handling, billing-affecting 작업에는 기본적으로 쓰지 않는다.
- 완료 조건이 모호하면 loop를 쓰지 않는다.

## 중단 기준
- 같은 실패가 반복된다.
- 외부 서비스/권한 이슈가 원인이다.
- 설계 결정을 사람에게 물어봐야 한다.
- diff가 계속 커지는데 검증 신호가 나아지지 않는다.

## 보고 방식
반복이 끝났는데 미완료면:
- 마지막 상태
- 반복 횟수
- 막힌 원인
- 다음 수동 단계
를 남긴다.
