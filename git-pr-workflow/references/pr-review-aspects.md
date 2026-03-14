# PR review aspects

## code
- 일반 코드 품질
- 버그 가능성
- 프로젝트 규칙 위반
- 지나친 복잡성

## tests
- 새 기능/변경점이 실제로 커버되는지
- negative case, edge case, async/concurrency case 누락 여부
- brittle test 여부

## errors
- silent failure
- broad catch
- 사용자에게 모호한 에러 메시지
- 숨겨진 fallback

## comments
- 주석이 코드와 실제로 맞는지
- 문서가 오래될 가능성이 높은지
- 설명 가치가 있는지

## types
- 새 타입이나 모델이 invariant를 잘 표현하는지
- 캡슐화와 validation이 적절한지
- 불법 상태를 만들기 쉬운지

## simplify
- 기능은 맞지만 불필요하게 복잡한지
- 중첩/분기/추상화가 과한지
- 읽기 어려운 표현이 있는지

## 출력 원칙
- 실제 diff나 지정된 파일 범위를 기준으로 리뷰
- 중요도 순으로 정리
- 파일/라인 근거를 우선
- nit보다 실제 영향이 큰 문제를 우선
