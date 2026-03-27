---
name: hey-codex
description: 별도 Codex CLI 실행을 위임합니다. 사용자가 명시적으로 다른 Codex 인스턴스 실행, 세컨드 오피니언, 격리된 full-auto 실행을 원할 때만 사용합니다.
---

# Hey Codex

원본 `hey-codex`는 Claude에서 Codex를 부르는 스킬이었고, 여기서는 **현재 세션과 분리된 Codex CLI 실행**으로 재해석합니다.

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
