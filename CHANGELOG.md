# Changelog

이 저장소의 의미 있는 skill 묶음 변경을 기록합니다.

## [Unreleased]
### Added
- `gptpro` opt-in Tunnel request-correlation diagnostic: a dedicated activation can read one bounded official v0.0.12 private admin-log snapshot over its owner-only Unix socket after revoke, convert allowlisted outer/JSON-RPC/connector request identifiers immediately to per-session HMACs, and align only complete evidence with the receipt-bound protocol trace and disclosure audit. Raw identifiers/payloads and the HMAC key are not persisted, normal logging remains `warn` to `/dev/null`, incomplete evidence is inconclusive, every physical call/byte remains budgeted, and the write-tool gate stays blocked
- `gptpro` owner-only MCP protocol diagnostics: a package-local, full-runtime-bound, mode-`0600`, 64-event hash chain retains only allowlisted decision/processed/response-flush sequence and version evidence, excludes IDs/client metadata/arguments/content/credentials, binds activation headers and active-session exact-stop final summaries into receipts, marks pre-active failure evidence as header-only rather than falsely lifecycle-bound, fingerprints safely readable invalid bytes, preserves forced-stop or unsafe-trace evidence without erasing disclosure audit evidence, and detects post-stop rewrites with `mcp-protocol-trace`
- `gptpro` experimental Phase-3 Web MCP runtime: owner-only user-global one-package authorization, package-local fail-before-return disclosure audit, explicit probe/activate/status/stop lifecycle, and cooperative exact-controller shutdown. The official `tunnel-client` v0.0.12 public foreground `init`/`doctor`/`run` flow is used; activation readiness additionally requires `health --require-control-plane-poll`, while ChatGPT Developer Mode, account/app/workspace selection, and prompt submission remain attended human steps
- `gptpro` Web MCP execution hardening: key-bearing Tunnel operations require the no-secret probe's exact binary path/hash, validate and bind the owner-only official-init profile, force canonical OpenAI control-plane/system-trust/no-proxy settings, pass a finite secret-filtered child environment, confine health/admin to an activation-owned owner-only Unix socket with no TCP listener, suppress persistent Tunnel logs, and hash an isolated absolute Python command (`-I -S -B -Xpycache_prefix=/dev/null`) that ignores user-site/startup injection and source-adjacent bytecode
- `gptpro` dependency-free Phase-2 Web MCP stdio core: exact three-tool legacy catalog, deny-all default authorization boundary, strict no-extraction immutable ZIP verification, HMAC-bound pagination, bounded literal search/read, cancellation, stable sanitized errors, and protocol/entrypoint tests. Phase 3 layers active authorization, audit, and Tunnel lifecycle on this core; logged-in ChatGPT Web E2E remains a separate evidence gate
- `gptpro` explicit `mcp-read` schema-3 foundation: browser delivery와 Secure MCP Tunnel connector를 context transport와 분리하고, immutable local ZIP의 최대 공개 file/hash set·정적 read-only tool schema·limits·TTL·package-bound Tunnel hash를 이중 사용자 승인에 결속
- `gptpro/references/web-mcp.md`와 dependency-free foundation tests: gptpro package/runtime artifacts의 raw Tunnel ID 비지속, owner-only official profile 경계, prompt-only outbound, schema-2 호환, 변조 및 허위 active-session 차단을 검증
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
- `gptpro` request-correlation hardening: the private admin-log diagnostic is now gated to the exact official `0.0.12+881c9a8...` contract without narrowing ordinary Tunnel compatibility, verifies the Unix peer against the owned child PID, enforces a wall-clock snapshot deadline, requires contiguous exact event shapes and a closed receipt-bound final trace, treats terminal errors/late responses/zero-tool windows as inconclusive, and removes stable unkeyed join hashes from terminal output in favor of session-local group ordinals while documenting their pre-existing owner-only audit retention
- `gptpro` Web MCP diagnostics now separate protocol stream closure from controller-observed runtime stop and final stop-receipt binding through a stable `terminal_evidence` summary. A valid receipt-bound `closed: false` prefix is reported as `runtime_stopped_protocol_eof_unobserved` rather than implying a live authorization or fabricating a footer; documentation also names observed repeated calls as upper-layer duplicate dispatch and keeps every physical call/returned byte in the fail-closed budget
- `gptpro` schema-3 prompts now disclose the exact package-specific MCP hard limits and require an explicitly bounded first `gptpro_package_info` request plus explicit search bounds, preventing static schema defaults from consuming a narrow approved call budget while retaining fail-closed accounting for invalid or rejected attempts
- `gptpro` Web MCP legacy request compatibility now idempotently answers repeated same-version `initialize` requests only in an already-ready no-discovery lifecycle, accepts the MCP 2025-11-25 optional object-valued `_meta` and omitted `arguments` shapes for exact allowlisted `tools/call`, discards `_meta` before dispatch, and continues to reject different versions, discovery-path post-ready reinitialization, unknown keys, and task augmentation
- `gptpro` Web MCP request execution now recognizes the logged-in ChatGPT Tunnel sequence that omits `notifications/initialized`: only `initialize` plus one identical supported-version replay, followed by a structurally valid allowlisted `tools/call` with no preceding `server/discover`, can enter an explicitly traced request-scoped compatibility state. Standard discovery still requires the notification; mismatched versions, malformed/unknown calls, `tools/list`, and unrelated duplicate initialization remain denied
- `gptpro` Web MCP legacy handshake now tolerates the observed Tunnel startup-probe pattern by replaying exactly one identical supported-version `initialize` while initialization is acknowledged but not ready; the standard discovery lifecycle still rejects third, different-version, or post-ready duplicates and keeps tools locked until `notifications/initialized`
- `gptpro` Web MCP profile lifecycle now detects Homebrew/Python interpreter-path drift without resolving credentials and supports an explicitly confirmed, same-Tunnel atomic staged refresh behind a machine-global profile/controller flock and proven-safe terminal controller lease, rejecting missing/unsafe/live lease ambiguity, restoring failed replacements byte-for-byte, and reporting retained private-stage cleanup separately
- `gptpro` Web MCP legacy stdio handshake compatibility: ChatGPT's `server/discover` legacy fallback closes tool readiness and opens a fresh initialization lifecycle over the persistent Tunnel child; tools stay denied until a new `notifications/initialized`
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
