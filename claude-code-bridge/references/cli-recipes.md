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
- 응답 회수 안정화
- 타임아웃 fallback

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

큰 작업은 한 번에 길게 묻지 말고 이렇게 쪼개기.

```bash
claude -p "Answer only: current structure in 4 bullets."
claude -p "Answer only: required dependency changes in 3 bullets."
claude -p "Answer only: top risks after migration in 3 bullets."
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

## 응답 회수 안정화

- Codex shell에서 Claude 출력 회수가 불안정하면 TTY/PTy 모드를 우선하기.
- 긴 자유형 프롬프트보다 짧고 목적이 하나인 프롬프트를 여러 번 보내기.
- analysis는 구조 / 의존성 / 리스크 / 검증 순으로 나눠 묻기.
- review는 `findings only`, `N bullets max`, `answer yes/no first`처럼 출력 길이를 강하게 잠그기.

예:

```bash
claude -p "Answer yes or no and one sentence."
claude -p "Return 3 bullets only."
claude -p "Return only numbered steps 1-4."
```

## 타임아웃 fallback

- 일정 시간 응답이 없으면 먼저 프롬프트를 절반 이하로 줄이기.
- 그래도 느리면 질문을 한 개씩 분리하기.
- 그래도 불안정하면 Claude 호출을 종료하고 Codex 단독 분석 또는 더 좁은 재질문으로 전환하기.
- 타임아웃/무응답은 성공처럼 보고하지 말고 호출 실패로 기록하기.

## 권장 사용 규칙

- 분석은 읽기 범위를 좁혀서 요청하기.
- 구현은 수정 파일을 명시하기.
- 리뷰는 findings-first로 강제하기.
- review-incorporation은 review 이후에만 수행하기.
- 긴 프롬프트는 prompt file이나 heredoc을 사용하기.
- 응답이 불안정하면 더 짧은 프롬프트와 TTY/PTy 모드로 재시도하기.
- Claude 출력은 항상 Codex가 다시 검증하기.
