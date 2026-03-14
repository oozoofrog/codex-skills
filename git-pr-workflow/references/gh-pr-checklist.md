# GitHub PR checklist

## 사전 조건
- `gh auth status`
- `origin` remote 확인
- branch push 가능 여부 확인

## PR 생성 전 체크
- base branch 확인 (`main` 등)
- 현재 branch 이름 확인
- commit이 필요한 상태인지 확인
- 로컬 검증/테스트 완료 여부 정리

## PR 본문 최소 구조
### Summary
- 변경 요약 1~3개 bullet

### Test Plan
- [x] 또는 bullet 형태로 실행한 검증

### Notes / Risks
- 사용자 영향, 롤백 포인트, 미해결 이슈 (있을 때만)

## PR 생성 후
- 생성된 URL 확인
- draft 여부가 맞는지 확인
- 필요한 라벨/리뷰어/템플릿 반영 여부 확인
