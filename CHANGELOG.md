# Changelog

이 저장소의 의미 있는 skill 묶음 변경을 기록합니다.

## [Unreleased]
### Added
- `gptpro` dependency-free Phase-2 Web MCP stdio core: exact three-tool legacy catalog, deny-all default authorization boundary, strict no-extraction immutable ZIP verification, HMAC-bound pagination, bounded literal search/read, cancellation, stable sanitized errors, and protocol/entrypoint tests. Persistent authorization, audit, Tunnel lifecycle, and logged-in ChatGPT Web E2E remain separate gates
- `gptpro` explicit `mcp-read` schema-3 foundation: browser delivery와 Secure MCP Tunnel connector를 context transport와 분리하고, immutable local ZIP의 최대 공개 file/hash set·정적 read-only tool schema·limits·TTL·package-bound Tunnel hash를 이중 사용자 승인에 결속. 이 단계에는 MCP server, Tunnel process lifecycle, 또는 실제 ChatGPT Web E2E가 포함되지 않음
- `gptpro/references/web-mcp.md`와 dependency-free foundation tests: raw Tunnel ID 비지속, prompt-only outbound, schema-2 호환, 변조 및 허위 active-session 차단을 검증
- `gptpro/scripts/validate_structure.py`: PyYAML 없이 standalone/Plugin 구조, frontmatter, 링크, prompt placeholder, Python 문법·실행 모드와 mirror hash를 검증하는 표준 라이브러리 도구
- `gptpro` Skill: plan/ask/review/debug/architecture 모드, Git SHA와 packaged-tree pinning, secret/exclude scan, manifest/archive hash 검증, 승인 gate, visible Chrome handoff, response import, receipt/state, advisory 검증 계약
- `gptpro` skills-only Plugin과 repo Marketplace: Codex Plugin 브라우저 및 `$skill-installer` 기반 네트워크 설치 경로
- Plugin manifest, Marketplace entry, standalone/Plugin Skill mirror 일치 검증 테스트와 설치 문서
- `scripts/manage_skills.py`: top-level Skill 목록 조회와 선택 설치, dry-run, hash-checked atomic update
- 선택 설치 운영 문서와 단위/통합 테스트
- `hierarchical-context-architecture` skill 추가
- 루트 `CLAUDE.md`, `AGENTS.md` 및 `docs/`, `scripts/`, `.system/`, `hierarchical-context-architecture/`용 `CONTEXT.md` 초안 추가
- `docs/release-checklist.md` 추가

### Updated
- `gptpro` `auto`를 GitHub-first로 확장: 선택 파일과 HEAD 바이트 일치, github.com 원격 ref/PR head의 SHA 검증, immutable commit·경로 allowlist pinning, prompt-only 전송, 사람 소유 App 권한 checkpoint, 응답 attestation 검증 및 text fallback 사유 기록
- `gptpro`에 로그인·OAuth/app scope·권한·파일 선택·모델 확인·수동 전송·불확실한 제출·response export를 정상적인 attended human checkpoint로 다루는 read-only `human-handoff` workflow 추가
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
