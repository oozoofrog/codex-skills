---
name: agent-context-verify
description: AGENTS.md 기반 instruction 구조의 정합성을 검증합니다. 링크 무결성, 코드/명령 참조, 문서 주장 정확성을 점검할 때 사용합니다.
---

# Agent Context Verify

원본 `ctx-verify`의 Codex 버전입니다. `AGENTS.md` 계층 구조와 보조 문서가 실제 저장소 상태와 맞는지 검사합니다.

## Use references
- `../agent-context-guide/references/verification-guide.md`

## Verification stages
1. **Reference integrity**
   - `AGENTS.md`, `AGENTS.override.md`, `CONTEXT.md`, `docs/` 링크가 실제로 존재하는지 확인한다.
2. **Code and command validation**
   - 문서에 적힌 파일 경로, 실행 명령, 테스트 명령이 현재 저장소와 맞는지 확인한다.
3. **Content accuracy**
   - 아키텍처 설명, 사용 라이브러리, 금지사항이 코드와 충돌하지 않는지 확인한다.

## Workflow
1. instruction 문서 전체를 수집한다.
2. 상위/하위 문서가 어떤 범위를 담당하는지 매핑한다.
3. 위 3단계를 순서대로 실행한다.
4. 결과를 `critical / warning / info / strength`로 정리한다.
5. 필요 시 `context-validator` custom agent 또는 일반 read-only subagent에 검증 일부를 위임한다.

## Review Harness
- mode: none
- 공통 기준: `../../../docs/review-harness.md`
- generator: 상위 스킬이 만든 instruction 파일 및 링크
- evaluator: 이 스킬 자체가 evaluator-native verification 역할을 수행한다
- 평가축: 링크 무결성, 명령/파일 경로 정확성, 문서 주장과 저장소 상태 일치성
- artifacts/evidence: 링크 무결성, 파일 경로, 실행 명령, 코드와 문서 주장 일치 여부
- pass condition: 모든 `critical` 항목이 해소되거나 명시적으로 남아 있어야 한다
- 자동 다음 행동: `pass`면 종료, `warning`이면 수정 후보 제시, `critical`이면 해당 문서를 block 처리하고 상위 스킬에 재작성 요청

## Output expectation
- 단계별 검증 결과
- 깨진 링크 / 오래된 명령 / 잘못된 주장 목록
- 바로 수정할 파일 제안
