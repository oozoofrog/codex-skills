# Prompt Templates

Claude Code CLI에 넘길 때 사용할 최소 템플릿이다.
필요한 부분만 복사해서 사용하기.

## Analysis Template

```text
You are assisting Codex as a codebase analyst.
Do not implement yet.

Task:
<task>

Scope:
<files or directories>

Return only:
1) current structure
2) likely change points
3) risks
4) minimal implementation plan
```

## Implementation Template

```text
You are assisting Codex as an implementation worker.
Modify only the allowed files.

Task:
<task>

Allowed files:
<files>

Constraints:
- minimal diff
- no unrelated refactor
- preserve existing architecture
- mention tests needed

Return:
1) files changed
2) change summary
3) risks
```

## Review Template

```text
You are assisting Codex as a critical reviewer.
Prioritize defects over praise.

Review target:
<diff or changed files>

Return:
1) critical issues
2) likely bugs
3) regression risks
4) missing tests
5) next fixes
```

## Review Incorporation Template

```text
You are assisting Codex as an implementation worker after review.
Do not expand scope beyond accepted review findings.

Task:
<task>

Accepted review findings:
<findings>

Allowed files:
<files>

Return:
1) accepted vs rejected findings
2) reasons for any rejection
3) files changed
4) tests to rerun
5) remaining risks
```

## Second-Opinion Template

```text
Codex currently believes the following solution is correct:
<summary>

Challenge it.
Identify weak assumptions, concurrency risks, missing edge cases, or a better minimal approach.

Return concise findings only.
```

## iOS/Swift Task Brief Integration Template

```text
Use the following structured iOS/Swift task brief as the source of truth.
Do not broaden scope beyond the brief.

<task brief>

Current phase:
<analysis | implementation | review | review-incorporation>

Return only the requested phase output.
```
