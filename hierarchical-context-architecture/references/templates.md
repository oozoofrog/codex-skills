# Templates and Starter Patterns

## 목차
1. Root `CLAUDE.md` 템플릿
2. Subsystem `CONTEXT.md` 템플릿
3. Portable `AGENTS.md` 템플릿
4. XML 분리 패턴
5. 정기 검증 체크리스트

## 1. Root `CLAUDE.md` 템플릿

```md
# CLAUDE.md

## Repository Commands
- Build: `...`
- Test: `...`
- Lint: `...`
- Run: `...`

## Global Architecture Decisions
- 핵심 런타임 구조
- 공통 데이터 흐름
- 금지된 패턴

## Environment Constraints
- 필수 환경 변수
- 배포/실행 제약

## Context Tree Entry Points
- `src/CONTEXT.md`: 애플리케이션 소스 구조
- `infra/CONTEXT.md`: 인프라/배포 규칙
- `docs/CONTEXT.md`: 장문 문서와 ADR
```

### 작성 규칙
- 200라인 이내 유지하기.
- 모든 서브시스템 세부사항을 넣으려 하지 말기.
- “가장 자주 다시 읽혀야 하는 내용”만 남기기.

## 2. Subsystem `CONTEXT.md` 템플릿

```md
# CONTEXT.md

## Scope
- 이 디렉토리가 담당하는 문제 영역
- 다른 디렉토리와의 경계

## Why This Exists
- 이 구조를 유지하는 이유
- 자주 깨지는 전제

## Key Files
- `service.ts`: 요청 조합과 에러 매핑
- `types.ts`: 외부 계약 타입
- `auth/CONTEXT.md`: 인증 세부 규칙

## Local Rules
- 여기서만 허용되는 패턴
- 여기서 금지하는 패턴
- 상위 규칙을 덮어쓰는 예외

## Child Contexts
- `auth/CONTEXT.md`
- `billing/CONTEXT.md`

## Verification Notes
- 관련 테스트 위치
- 변경 시 반드시 확인할 수동 QA
```

### 작성 규칙
- 구현 세부 코드를 길게 복사하지 말기.
- 파일 이름을 나열하는 것보다 관계와 의도를 설명하기.
- 더 깊은 하위 문서가 있으면 반드시 링크 걸기.

## 3. Portable `AGENTS.md` 템플릿

```md
# AGENTS.md

## Collaboration Rules
- 먼저 읽고, 그 다음 수정하기.
- 범위를 벗어나는 리팩터링은 분리 제안하기.
- 검증하지 않은 성공을 보고하지 않기.

## Output Contract
- 변경 파일
- 검증 명령
- 남은 위험
- 다음 단계

## Review Rules
- 문제는 파일/함수/근거와 함께 적기.
- 이슈가 없으면 `없음`을 명시하기.
- 요약보다 결함 탐지를 우선하기.
```

### 작성 규칙
- 도구 고유 설정 대신 범용 규칙 위주로 적기.
- 장황한 메타데이터는 피하기.

## 4. XML 분리 패턴

```xml
<instructions>
  - 루트 규칙은 간결하게 유지한다.
  - 하위 예외는 가장 가까운 CONTEXT.md에 둔다.
</instructions>

<context>
  repo_root: /workspace/project
  active_path: src/api/
  loaded_contexts:
    - /CLAUDE.md
    - /src/CONTEXT.md
    - /src/api/CONTEXT.md
</context>

<data>
  latest_test_summary: 12 passed, 1 failed
  failing_test: src/api/auth.test.ts
</data>
```

## 5. 정기 검증 체크리스트

주간 또는 대규모 리팩터링 직후 다음을 반복하기.

- 링크된 문서 경로가 모두 실제로 존재하는가?
- 이동된 코드 경로를 옛 문서가 여전히 가리키지 않는가?
- 루트 `CLAUDE.md`가 비대해지지 않았는가?
- 새로운 하위 디렉토리에 `CONTEXT.md`가 필요한데 빠져 있지 않은가?
- 같은 실수가 반복되는데 규칙 문서는 그대로 남아 있지 않은가?
