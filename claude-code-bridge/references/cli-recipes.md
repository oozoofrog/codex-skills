# Claude Code CLI Recipes

신뢰 가능한 로컬 디렉터리에서만 사용하기.
기본 패턴은 `claude -p` 비대화형 호출이다.

## Quick Index

- 인증 확인
- 분석 호출
- 구현 호출
- 리뷰 호출
- 리뷰 반영 호출
- 구조화 출력
- 세션 재사용

## 인증 확인

```bash
claude auth status
```

로그인 필요 시:

```bash
claude auth login
```

## 분석 호출

짧은 코드베이스 분석:

```bash
cd /path/to/repo
claude -p \
  --add-dir /path/to/repo \
  "Read the relevant files in this repository and answer only: 1) current structure, 2) likely change points, 3) risks, 4) minimal plan."
```

## 구현 호출

범위를 잠근 수정 요청:

```bash
cd /path/to/repo
claude -p \
  --add-dir /path/to/repo \
  "Modify only the following files: path/A.swift, path/B.swift. Goal: <goal>. Constraints: minimal diff, no unrelated refactor, mention tests needed."
```

## 리뷰 호출

비판적 리뷰 요청:

```bash
cd /path/to/repo
claude -p \
  --add-dir /path/to/repo \
  "Review the recent changes in this repository. Prioritize bugs, regressions, concurrency risks, and missing tests. Use findings-first format."
```

독립 리뷰는 같은 구현 세션 대신 새 세션 또는 별도 컨텍스트에서 수행하기.

## 리뷰 반영 호출

리뷰 결과를 받은 뒤 범위를 잠근 수정:

```bash
cd /path/to/repo
claude -c -p \
  --add-dir /path/to/repo \
  "Apply only the accepted review findings. Do not expand scope. Return: 1) accepted/rejected findings, 2) files changed, 3) tests to rerun, 4) remaining risks."
```

## 구조화 출력

JSON 출력이 필요하면:

```bash
claude -p \
  --output-format json \
  --json-schema '{"type":"object","properties":{"summary":{"type":"string"},"risks":{"type":"array","items":{"type":"string"}}},"required":["summary","risks"]}' \
  "Analyze the task and return structured output only."
```

## 세션 재사용

같은 디렉터리 최근 대화 이어가기:

```bash
claude -c -p "Continue the previous analysis and focus only on test gaps."
```

특정 세션 재개:

```bash
claude -r <session-id> -p "Continue with a minimal implementation plan."
```

권장 세션 전략:
- 분석 → 구현 → 리뷰 반영: 같은 세션 유지 가능
- 독립 리뷰: 새 세션 사용 권장
- second-opinion: 새 세션 또는 Codex 단독 리뷰 권장

## 권장 사용 규칙

- 분석은 읽기 범위를 좁혀서 요청하기.
- 구현은 수정 파일을 명시하기.
- 리뷰는 findings-first로 강제하기.
- review-incorporation은 review 이후에만 수행하기.
- 긴 프롬프트는 prompt file이나 heredoc을 사용하기.
- Claude 출력은 항상 Codex가 다시 검증하기.
