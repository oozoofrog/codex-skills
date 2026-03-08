# Session Strategy

Claude Code CLI 세션은 단계별로 독립성과 연속성을 다르게 가져가기.

## Keep the Same Session

다음은 같은 Claude 세션을 유지하는 편이 좋다.
- analysis → implementation
- implementation → review-incorporation
- 같은 변경 범위를 연속 수정하는 후속 구현

이유:
- 기존 맥락과 제약을 유지하기 쉬움
- 불필요한 재설명 비용 감소

## Use a New Session

다음은 새 세션을 권장한다.
- 독립적인 review
- second-opinion
- 기존 Claude 구현을 깨보는 단계

이유:
- 자기 구현 방어 편향 감소
- 독립성 확보

## Anti-Patterns

- 같은 Claude 세션에 구현과 독립 리뷰를 모두 맡기기
- Codex와 Claude가 같은 단계에서 동시에 구현하기
- review 없이 곧바로 review-incorporation으로 넘어가기
