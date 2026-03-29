---
name: hey-codex
description: 별도 Codex CLI 실행을 위임합니다. 사용자가 명시적으로 다른 Codex 인스턴스 실행, 세컨드 오피니언, 격리된 full-auto 실행을 원할 때만 사용합니다.
---

# Hey Codex

원본 `hey-codex`는 Claude에서 Codex를 부르는 스킬이었고, 여기서는 **현재 세션과 분리된 Codex CLI 실행**으로 재해석합니다.

## When to use
- 사용자가 명시적으로 별도 Codex 인스턴스 실행이나 세컨드 오피니언을 원할 때
- 현재 세션과 분리된 read/review/suggest/write 실행이 필요할 때
- 부모 세션과 별도 Codex 결과를 비교하거나 격리된 full-auto 실행이 필요할 때

## Do not use when
- 현재 세션에서 바로 처리하면 되는 일반 작업
- 사용자가 nested Codex 실행을 명시적으로 원하지 않은 작업
- diff 검토 없이 하위 Codex의 write 결과를 바로 수용하려는 경우

## Quick start
1. `scripts/preflight.sh`로 Codex CLI 사용 가능 여부를 확인한다.
2. `mode-detection.md`로 read/review/suggest/write 모드를 정한다.
3. 작업 디렉토리를 분리하고 Codex CLI를 실행한다.
4. `process-output.sh`와 diff/snapshot으로 결과를 재검토한다.

## Use references
- `references/mode-detection.md`
- `references/output-handling.md`
- `scripts/preflight.sh`
- `scripts/process-output.sh`
- `scripts/snapshot-diff.sh`

## Workflow
1. `scripts/preflight.sh`로 `codex` CLI 설치 여부를 확인한다.
2. 사용자 프롬프트에서 트리거 문구를 제거하고 작업 디렉토리를 분리한다.
3. `mode-detection.md` 기준으로 `read / review / suggest / write`를 판별한다.
4. 쓰기 모드에서는 Git 저장소 여부를 먼저 확인하고, non-git이면 스냅샷 기반 보호 절차를 사용한다.
5. Codex CLI 출력을 `scripts/process-output.sh`로 정리한다.
6. 결과를 요약하고, 부모 세션이 직접 반영해야 할 후속 액션을 분명히 남긴다.

## Important
- 이 스킬은 **사용자가 명시적으로 요청했을 때만** 사용한다.
- 평범한 코드 작업은 현재 Codex 세션에서 직접 처리하는 편이 낫다.
- nested write 결과는 diff를 확인한 뒤에만 수용한다.

## Review Harness
- mode: optional
- 공통 기준: `../../../docs/review-harness.md`
- generator: 별도 Codex CLI 인스턴스가 read/review/suggest/write 작업을 수행한다
- evaluator: 부모 세션이 `process-output.sh`, diff, 스냅샷 비교로 결과를 재검토한다
- 평가축: explicit-only 준수, subprocess 결과 품질, diff 안전성, 결과 요약 충실성
- artifacts/evidence: subprocess output, snapshot diff, mode detection 결과, 변경 파일 목록
- pass condition: 특히 `write` 모드에서는 변경 diff와 안전장치 결과를 검토한 뒤에만 수용한다
- 자동 다음 행동: `pass`면 결과 요약 전달, `refine`이면 prompt/모드 수정 후 재실행, `critical`이면 write 결과 수용 중단, `escalate`면 부모 세션이 직접 검토한다

## Output expectation
- 선택한 실행 모드
- subprocess 실행 요약
- 결과 수용/보류 판단
- 부모 세션이 직접 해야 할 후속 액션
