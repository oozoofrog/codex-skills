---
name: gpt-research
description: 외부 GPT 또는 deep research 워크플로우로 넘길 구조화 프롬프트를 만듭니다. 모듈/아키텍처/이슈 단위로 맥락을 추출해 붙여넣기 가능한 리서치 요청을 만들 때 사용합니다.
---

# GPT Research

원본 `gpt-research`를 Codex 환경용으로 옮긴 스킬입니다.

## Modes
- `module` — 특정 모듈/파일 중심 맥락 추출
- `arch` — 프로젝트 구조와 의존성 요약
- `issue` — 오류/버그 조사 맥락 정리
- `custom` — 사용자가 범위를 직접 지정

## Use references
- `references/context-extraction-guide.md`
- `references/output-templates.md`
- `references/prompting-best-practices.md`
- `references/size-limits-and-chunking.md`

## Workflow
1. 모드를 결정한다.
2. 관련 소스, 테스트, 설정, `AGENTS.md`, README, 빌드 파일을 모은다.
3. 너무 큰 입력은 chunking 규칙에 따라 압축·분리한다.
4. 템플릿에 맞춘 최종 프롬프트를 만든다.
5. 가능하면 `pbcopy`로 클립보드에 복사하고, 응답에도 프롬프트 본문을 남긴다.

## Review Harness
- mode: optional
- 공통 기준: `../../../docs/review-harness.md`
- generator: research prompt와 컨텍스트 패키지를 구성한다
- evaluator: source coverage, chunking, 민감정보 포함 여부를 read-only checklist로 재검토한다
- 평가축: 소스 커버리지, chunking 적절성, 민감정보 누락, prompt 사용 가능성
- artifacts/evidence: 포함 파일 목록, chunking 결과, 최종 프롬프트 본문
- pass condition: 누락·중복·과잉맥락 없이 바로 붙여넣어 쓸 수 있어야 한다
- 자동 다음 행동: `pass`면 prompt 반환, `refine`이면 맥락 추가/제거, `pivot`이면 mode 변경, `escalate`면 사람이 범위를 다시 지정한다

## Output expectation
- 선택한 모드
- 포함한 파일/문서 목록
- 최종 리서치 프롬프트
