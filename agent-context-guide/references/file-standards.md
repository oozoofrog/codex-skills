# Codex instruction file standards

## 1. Root AGENTS.md

루트 `AGENTS.md`에는 저장소 공통 규칙만 둡니다.

포함 권장:
- 빌드/테스트/검증 기본 명령
- 아키텍처 상수와 금지사항
- PR/커밋/문서화 기준
- 팀 공통 작업 방식

제외 권장:
- 자주 바뀌는 TODO 목록
- 긴 API 사양
- 디렉토리별 세부 지침
- 대량 예시 코드

## 2. Nested AGENTS.md

공식 Codex 문서 기준으로, Codex는 현재 작업 디렉토리까지 올라가며 가장 가까운 instruction 파일을 함께 반영합니다. 따라서 특정 도메인 규칙은 그 코드에 가장 가까운 디렉토리의 `AGENTS.md`에 둡니다.

예시:

```text
AGENTS.md
services/
  payments/
    AGENTS.md
  search/
    AGENTS.md
```

## 3. AGENTS.override.md

더 강한 예외 규칙이 필요한 곳에는 `AGENTS.override.md`를 둡니다.

예시:
- 임시 마이그레이션 기간 규칙
- 한 서브시스템에만 적용되는 더 엄격한 절차
- 일반 규칙보다 우선해야 하는 운영 제약

## 4. CONTEXT.md와 docs/

장문 설계 문서, 용어집, 도메인 배경지식은 `CONTEXT.md` 또는 `docs/`에 둡니다.

원칙:
- `AGENTS.md`는 **지침**
- `CONTEXT.md` / `docs/`는 **배경지식**

## 5. Fallback filenames

저장소가 이미 다른 지침 파일명을 사용한다면 Codex 설정의 fallback filename 기능으로 연결합니다.

예시:

```toml
project_doc_fallback_filenames = ["TEAM_GUIDE.md", ".agents.md"]
project_doc_max_bytes = 65536
```

## 6. Migration note from Claude

원본 Claude 구조의 일반적인 치환:

| Claude | Codex 권장 |
|---|---|
| `CLAUDE.md` | `AGENTS.md` |
| `.claude/rules/*.md` | 가까운 하위 `AGENTS.md` 또는 `AGENTS.override.md` |
| `CONTEXT.md` | 그대로 사용 가능 (보조 지식 문서) |
| plugin hooks 기반 세션 알림 | 수동 스크립트, CI, 또는 별도 Codex config로 대체 |
