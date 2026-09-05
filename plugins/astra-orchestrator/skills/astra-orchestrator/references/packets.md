# Handoff와 반환 계약

## Worker handoff packet

8개 heading을 유지하고 실제 값으로 채운다. 해당 없으면 이유가 있는 N/A로 쓴다. 템플릿만 보내지 않는다.

```markdown
## Task
작업 ID, 역할, 목표 한 문장. 모델 gpt-6-astra, effort, 분류 이유.
## Why
사용자 요구사항과 이 과제가 해결하는 문제.
## Scope
작업 디렉터리와 소유 worktree·branch/HEAD, 변경 가능한 파일/심볼,
범위 밖 항목, 단일 writer 소유권과 Git Steward 인계 시점.
## Inputs
권위 문서, AGENTS.md, 실제 관련 파일, 수용된 선행 결과.
기준 commit과 dirty diff/untracked 입력 또는 snapshot 식별자.
## Constraints
구현 제약, 호환성, 공유 빌드/테스트 자원, 사용자 변경 보존.
Do-not-touch: 수정 금지 파일/영역과 금지된 외부 행동.
일반 Worker는 구현·테스트 담당. Git 변경/통합은 Steward에게 인계.
범위 밖 필요는 리더에게 반환. 중첩 위임 금지.
## Acceptance criteria
AC1, AC2처럼 관측 가능한 완료 조건과 적합한 정상/오류 검증.
필수 검증과 선택 검증을 구별.
## Relevant evidence
현재 동작, 재현 단계, 원문 오류, 테스트/로그 경로, 실행 환경.
Escalation이면 각 수정 시도, 실제 재검증 결과, 미해결 가설.
## Expected output
아래 worker 반환 형식. 완료 조건별 증거와 미실행 항목 포함.
```

## Worker 반환

```markdown
Status: COMPLETE | PARTIAL | BLOCKED
Task ID / session ID:
Configuration: desired / submitted / observed (관측 불가이면 unverified)
Changes: 변경 파일·심볼과 동작 영향
Evidence:
| Criterion | Result | Evidence path or command | Environment/input identity |
| --- | --- | --- | --- |
Tests: 실제 실행 명령, 결과, 필요한 로그 경로
Not run: 미실행 필수/선택 검증과 이유
Remaining: 남은 오류, 위험, 범위 밖 필요한 변경
```

COMPLETE는 자기 scope에 대한 주장이다. 전체 완료는 리더가 통합·검토 후 판정한다. 명령 제시와 실제 실행을 구별한다. Git Steward에는 같은 8개 heading을 쓰되 [Git 전용 입력과 12항목 Result](git-steward.md)를 적용한다.

## 독립 reviewer

동일한 8개 heading을 사용하되 역할은 independent final reviewer, 모델/effort는 `gpt-6-astra` / `max`다. Scope는 고정된 통합 snapshot 검증으로 제한한다. Git Steward/구현 워커와 다른 새 세션을 쓴다. Constraints에는 제품 파일·Git history/index 변경 금지, 중첩 위임 금지, 검증용 임시 출력 위치와 권한을 명시한다. 요구사항, 통합 SHA·diff 등 원본 evidence는 주되 구현자·Steward의 성공 결론은 주입하지 않는다.

Expected output:

```markdown
Verdict: PASS | CHANGES_REQUIRED | BLOCKED
Reviewed snapshot: commit + dirty/untracked 변경 식별자
Configuration: desired / submitted / observed (또는 unverified)
Requirements: acceptance criteria별 충족 여부와 직접 확인한 근거
Findings: 심각도, 실제 파일/심볼, 문제, 재현/근거, 영향, 필요한 수정
Checks: requirements / regression / concurrency / lifetime / error handling /
        test coverage / integration / completion claims
        각 항목의 검증 또는 이유가 있는 N/A
Validation: 직접 실행 검사와 전달받은 증거를 구별
Not verified: 미실행·환경 제한·남은 불확실성
Completion assessment: 현재 evidence로 주장 가능한 범위
```

필수 evidence가 없어 판단 불가이면 BLOCKED, 실제 수정이 필요하면 CHANGES_REQUIRED다. 둘 다 있으면 CHANGES_REQUIRED에 검증 blocker도 명시한다. PASS는 미실행 필수 검증을 생략하거나 확인 범위를 넘는 출시/실기기 보장을 의미하지 않는다.
