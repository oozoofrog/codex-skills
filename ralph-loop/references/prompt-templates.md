# Ralph Loop prompt templates

## 1. 테스트 기반 구현
```markdown
Implement feature X.

Success conditions:
- `swift test` passes
- changed files are limited to A, B, C
- output `<promise>COMPLETE</promise>` only when all conditions are true

If blocked:
- explain the blocker
- list the failing command
- suggest the smallest next fix
```

## 2. 리팩터링 반복
```markdown
Refactor module Y for clarity without changing behavior.

Success conditions:
- existing tests pass
- code is simpler and duplication is reduced
- output `<promise>COMPLETE</promise>` only when refactor is stable

If not complete after several attempts:
- summarize what remains risky
```

## 3. 문서/정리 작업
```markdown
Clean up release docs and scripts.

Success conditions:
- target files updated
- references are internally consistent
- output `<promise>COMPLETE</promise>` when all links and instructions align
```
