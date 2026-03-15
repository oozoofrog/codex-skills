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

## 추천 리뷰 출력 형식

기본 응답은 사람이 읽기 쉬운 Markdown으로 작성합니다.

예시:

```md
검토 범위
- PR #123 / `main...feature`
- `internal/agent/client.go`

판정
- blocking issue 2개

핵심 findings
1. [P2] 첫 요청 timeout 원인 라벨이 잘못됨
   - 위치: `internal/agent/client.go:163`
   - 이유: 실제 request timeout도 LaunchAgent 연결 실패처럼 다시 감싸짐
   - 영향: 사용자가 timeout 원인을 잘못 해석함
   - 수정 방향: 연결 실패일 때만 해당 라벨을 쓰고, request-timeout 메시지는 보존

2. [P2] LaunchAgent startup에 문서와 다른 5초 하드캡이 남아 있음
   - 위치: `internal/agent/client.go:237`
   - 이유: `--timeout`과 무관하게 startup 대기가 5초로 잘림
   - 영향: 문서/실제 동작 불일치, 긴 timeout 설정이 무효화됨
   - 수정 방향: startup 대기도 request timeout을 따르도록 통일하거나 문서를 수정

검증/남은 위험
- timeout 정책 관련 테스트 미확인
```

## inline directive 사용 규칙
- `::code-comment`는 기본 출력이 아니라 보조 출력입니다.
- 사용자가 inline 코멘트를 원하거나, 리뷰 UI가 directive를 제대로 렌더링하는 것이 확실할 때만 사용합니다.
- directive를 쓰더라도 사람이 읽는 요약과 findings 목록을 먼저 보여준 뒤 마지막에 덧붙입니다.
- raw directive만 여러 줄로 나열하는 답변은 피합니다.
