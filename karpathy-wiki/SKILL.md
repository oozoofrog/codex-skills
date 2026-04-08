---
name: karpathy-wiki
description: Karpathy의 LLM Wiki 아이디어를 바탕으로 raw source와 LLM-maintained wiki를 분리한 지속형 지식 베이스를 설계·부트스트랩합니다. markdown/git 기반의 범용 구조, `AGENTS.md` 운영 규칙, ingest/query/lint 워크플로우, Obsidian 같은 선택적 어댑터 분리가 필요할 때 사용합니다.
---

# Karpathy Wiki

Karpathy의 `LLM Wiki` 패턴을 **도구 비종속 knowledge architecture**로 옮겨 설계하거나 초기 구조를 잡는 스킬입니다.

## When to use
- Karpathy gist에서 말한 persistent wiki 패턴을 실제 프로젝트/개인 저장소에 맞게 구체화해야 할 때
- raw source, wiki, schema, derived artifacts를 분리한 markdown/git 기반 knowledge base가 필요할 때
- `AGENTS.md` 중심으로 ingest / query / lint 운영 규칙을 만들고 싶을 때
- Obsidian, VS Code, 정적 사이트, CLI 검색기 등을 **선택적 adapter**로 두고 core를 범용적으로 유지하고 싶을 때
- 장기 리서치, 독서 노트, 팀 내부 위키, due diligence, personal PKM처럼 축적형 지식 운영 흐름을 설계할 때

## Do not use when
- 문서 한두 개를 일회성으로 요약하면 충분한 작업
- embeddings/RAG 파이프라인 구현이 주목적이고 persistent wiki 설계는 필요 없을 때
- Obsidian 플러그인 설정, graph view, clipper 자동화 같은 특정 앱 사용법만 묻는 작업
- 일반 코드 저장소의 instruction 분할 구조만 설계하면 되는 작업 → `agent-context-guide`

## Quick start
1. 다룰 도메인과 truth model을 정합니다. (`raw source`가 무엇인지, 사람 검토가 필요한지)
2. `references/architecture.md`를 읽고 base layout과 page contract를 고릅니다.
3. `references/starter-template.md`를 바탕으로 루트 디렉토리와 `AGENTS.md` 골격을 만듭니다.
4. ingest / query / lint 흐름과 `index.md`, `log.md`, citation 규칙을 고정합니다.
5. 필요하면 Obsidian, 정적 사이트, 로컬 검색기 같은 adapter를 마지막에 붙입니다.

## Use these references
- `references/architecture.md` — 범용 LLM Wiki 아키텍처, 계층 책임, 페이지 규칙, 운영 원칙
- `references/starter-template.md` — 바로 복사해서 쓸 수 있는 디렉토리 구조, `AGENTS.md` 골격, 페이지 템플릿

## Workflow

### 1. Scope the knowledge system
먼저 아래를 고정합니다.

- 대상 도메인: personal / research / book / team / market intelligence / etc.
- 원천 자료의 형태: markdown / pdf / web archive / image / spreadsheet / transcript
- 정확도 요구: low / medium / high stakes
- 사람 검토 지점: ingest마다 검토할지, lint에서만 검토할지

고위험 도메인(의료/법률/재무)은 wiki만 믿지 말고 **원문 재검증 절차**를 같이 설계합니다.

### 2. Separate layers clearly
최소한 다음 레이어를 분리합니다.

- `raw/` — immutable source of truth
- `wiki/` — LLM이 유지하는 정제된 markdown 지식 레이어
- `schema/` 또는 루트 문서 — 규칙, naming, citation, workflow
- `state/` — log, review queue, unresolved issues
- `derived/` — catalog, backlinks, graph, search index 등 재생성 가능한 산출물

핵심 원칙은 **tool-first가 아니라 data-first** 입니다. 특정 앱 기능이 core contract를 결정하게 두지 않습니다.

### 3. Choose portable contracts
가능하면 아래를 기본값으로 둡니다.

- 표준 Markdown
- YAML frontmatter
- 상대 경로 링크
- JSON/JSONL manifest
- Git version control

`[[wikilink]]`, Dataview 전용 문법, 앱 설정 파일 등은 optional adapter에만 둡니다.

### 4. Define page types and metadata
페이지는 몇 가지 canonical type으로 단순화하는 편이 좋습니다.

- source note
- topic / concept
- entity
- synthesis
- comparison
- overview / index

모든 페이지에 최소 메타데이터를 두면 lint와 자동화가 쉬워집니다.

- `id`
- `title`
- `type`
- `status`
- `updated_at`
- `source_ids`
- `confidence` (선택)

### 5. Write the operating schema
`AGENTS.md` 또는 동등한 schema 문서에는 최소한 아래를 적습니다.

- raw는 수정 금지
- ingest 후 어떤 파일을 반드시 갱신할지
- query 결과를 wiki에 남기는 조건
- citation/backlink 규칙
- lint에서 찾을 문제 목록
- adapter는 optional이며 core format을 덮어쓰지 못한다는 원칙

### 6. Design ingest / query / lint loops
- **Ingest**: source import → source note 생성 → 관련 wiki 갱신 → index/log 갱신
- **Query**: wiki 우선 검색 → 필요한 경우 raw 재검증 → 답변 합성 → 가치 있으면 synthesis로 저장
- **Lint**: broken link, orphan page, stale claim, source 없는 주장, 중복, 모순을 검사

이 세 루프가 명시되어야 knowledge base가 시간이 지나도 썩지 않습니다.

### 7. Add adapters last
Obsidian, VS Code workspace, qmd, 정적 사이트 생성기, SQLite search, web UI는 **마지막에 붙이는 adapter**로 다룹니다.

질문은 항상 이렇게 묻습니다.

- 이 기능이 없어도 markdown/git/raw/wiki 계약이 유지되는가?
- adapter를 제거해도 knowledge base가 손상되지 않는가?

대답이 아니오라면 설계를 다시 단순화합니다.

## Review Harness
- mode: optional
- 공통 기준: `../../../docs/review-harness.md`
- generator: knowledge base layout, `AGENTS.md`, page contract, 운영 루프를 설계·초기화한다
- evaluator: 생성된 구조가 앱 종속 없이 유지되는지, citation/log/index 계약이 충분한지 read-only로 재검토한다
- 평가축: layer 분리, portability, citation 가능성, ingest/query/lint completeness, adapter 분리
- artifacts/evidence: 디렉토리 트리, `AGENTS.md`, 샘플 page frontmatter, index/log 규칙, optional adapter 목록
- pass condition: 특정 앱을 제거해도 raw/wiki/schema 운영 계약이 유지되어야 한다
- 자동 다음 행동: `pass`면 구조 확정, `refine`이면 contract 보강, `rescope`면 page type/adapter 수 축소, `escalate`면 사람 검토 규칙을 강화한다

## Output expectation
작업이 끝나면 최소 다음을 제공합니다.

1. 제안하는 디렉토리 트리
2. `AGENTS.md` 또는 schema 문서 골격
3. page type / frontmatter contract
4. ingest / query / lint workflow
5. optional adapter 분리 원칙
6. 남은 리스크와 사람 검토 포인트
