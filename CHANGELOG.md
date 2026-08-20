# Changelog

이 저장소의 의미 있는 skill 묶음 변경을 기록합니다.

## [Unreleased]
### Added
- `gptpro` Skill: plan/ask/review/debug/architecture 모드, Git SHA와 packaged-tree pinning, secret/exclude scan, manifest/archive hash 검증, 승인 gate, visible Chrome handoff, response import, receipt/state, advisory 검증 계약
- `scripts/manage_skills.py`: top-level Skill 목록 조회와 선택 설치, dry-run, hash-checked atomic update
- 선택 설치 운영 문서와 단위/통합 테스트
- `hierarchical-context-architecture` skill 추가
- 루트 `CLAUDE.md`, `AGENTS.md` 및 `docs/`, `scripts/`, `.system/`, `hierarchical-context-architecture/`용 `CONTEXT.md` 초안 추가
- `docs/release-checklist.md` 추가

### Updated
- `gptpro` 첫 사용 시 `.gptpro/handoffs`와 Git 제외 규칙을 preview 후 선택적으로 구성하는 멱등 `init` workflow 추가
- `gptpro` 기본 전달을 ZIP 업로드에서 `auto` 선택형 구조화 텍스트(`paste`/`text-file`)로 변경하고, 실제 전송 bytes/hash에 승인·receipt를 결속
- 사용자 스킬 정리: 중복 discovery 제거, `macos-release` 단일화, `codex-research`를 기존 `.codex-research/` 호환 runner로 축소
- 누락된 `agents/openai.yaml` metadata를 사용자 스킬에 보강하고, `SKILL.md` extra frontmatter를 제거
- README skill catalog를 현재 활성 사용자 스킬 기준으로 재작성
- `hierarchical-context-architecture` 검증 스크립트에 `--strict`와 `.context-audit.yml` 기반 운영 설정 지원 추가
- `hierarchical-context-architecture` 문서에 운영 모드와 감사 설정 예시 추가
- 저장소 루트에 `.context-audit.yml`을 추가해 기본 감사 실행에 strict 운영 기준 적용
- README skill catalog를 표 형태와 빠른 선택 가이드 중심으로 재구성
- 릴리즈 운영 파일 섹션에 `docs/release-checklist.md` 링크 추가
- README에 `hierarchical-context-architecture` 사용 예시와 선택 가이드 추가

### Removed
- `fixer` legacy plugin doctor skill 제거 (`plugin-doctor`로 통합)
- `ooz-macos-release` 제거 (`macos-release`로 통합)
- `codex-research/skills/codex-research` nested duplicate 제거

## [0.1.1] - 2026-03-14
### Added
- README에 skill별 사용 예시 섹션 추가
- `docs/release-notes-template.md` 추가
- `CHANGELOG.md` 추가

### Updated
- README에 신규 skill 설명과 릴리즈 운영 파일 섹션 추가

## [0.1.0] - 2026-03-14
### Added
- `frontend-design`
- `git-pr-workflow`
- `ralph-loop`
- `macos-release` 업데이트
- `swift-master` SourceKit-LSP 보강
- `ios-swift-orchestrator` SourceKit-LSP 라우팅 보강
- 첫 annotated tag `v0.1.0`
