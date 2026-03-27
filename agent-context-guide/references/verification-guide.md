# Instruction verification guide

## Stage 1. Reference integrity

확인 대상:
- markdown 링크
- 백틱 파일 경로
- `AGENTS.md`에서 언급한 문서/디렉토리

질문:
- 링크 대상이 실제로 존재하는가?
- 고립된 `CONTEXT.md`가 있는가?
- 특정 도메인 문서가 아무 데서도 참조되지 않는가?

## Stage 2. Code and command validation

확인 대상:
- 빌드/테스트 명령
- 파일 경로
- 핵심 심볼/디렉토리 이름

질문:
- `package.json`, `Makefile`, `Package.swift`, `Cargo.toml` 등과 맞는가?
- 문서가 오래된 파일명을 참조하지 않는가?
- 리팩터링 이후에도 설명이 유효한가?

## Stage 3. Content accuracy

확인 대상:
- “우리는 X를 사용한다” 같은 주장
- 금지/권장 패턴
- 아키텍처 설명

질문:
- 실제 코드가 그 규칙을 따르는가?
- 더 이상 쓰지 않는 라이브러리를 문서가 계속 언급하는가?
- 상위 instruction과 하위 instruction이 서로 충돌하지 않는가?

## Severity guidance

- `critical` — 깨진 링크, 잘못된 빌드 명령, 직접적인 충돌
- `warning` — 오래된 예시, 중복 규칙, 잘못된 범위 배치
- `info` — 설명 보강 제안, 문서 분리 제안
- `strength` — 잘 정리된 구조, 근접한 도메인 규칙 배치
