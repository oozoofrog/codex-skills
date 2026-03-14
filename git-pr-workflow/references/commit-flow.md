# Commit flow

## 1. 먼저 확인할 것
- `git status --short`
- `git branch --show-current`
- `git diff --stat`
- 필요 시 `git log --oneline -10`

## 2. Commit only
- 어떤 파일이 바뀌었는지 먼저 요약
- staging 범위를 점검
- commit 메시지는 저장소 관례를 최대한 따름
- 관련 없는 파일은 묶지 않음

## 3. Commit + PR
- 기본 브랜치면 새 브랜치 생성 (`codex/...` 권장)
- commit 후 push
- `gh pr create` 전에 base branch를 확인
- PR 본문에는 최소 다음이 있으면 충분함
  - Summary
  - Test Plan
  - Risks / Notes (필요 시)

## 4. Commit message 작성 기준
- 최근 log 스타일을 먼저 본다.
- 가능하면 한 줄 제목은 짧고 구체적으로 쓴다.
- 과도한 장황함보다 diff가 말해주는 핵심 변화에 집중한다.
