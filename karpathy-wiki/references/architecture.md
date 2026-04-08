# Karpathy-style LLM Wiki Architecture

## Design goals
- raw source와 정제 지식을 분리한다
- 지식이 chat history가 아니라 파일 자산으로 누적되게 한다
- 특정 앱이나 플러그인이 없어도 유지된다
- LLM이 유지보수 담당자처럼 동작하도록 schema를 명시한다
- 검색, graph, 대시보드, editor는 adapter로 취급한다

## Recommended layers

### 1. Source layer
원본 자료를 보관하는 계층입니다.

권장 특성:
- immutable
- canonical source of truth
- 텍스트 외에도 PDF, 이미지, 웹 아카이브, transcript, CSV 허용
- 각 항목은 stable id를 가짐

예시:
```text
raw/
  inbox/
  sources/
  assets/
  manifest.jsonl
```

`manifest.jsonl` 권장 필드:
- `id`
- `title`
- `kind`
- `path`
- `source_url`
- `captured_at`
- `checksum`
- `tags`

### 2. Wiki layer
LLM이 읽고 쓰는 정제 지식 계층입니다.

예시:
```text
wiki/
  overview.md
  index.md
  topics/
  entities/
  source-notes/
  syntheses/
  comparisons/
```

권장 원칙:
- 사람이 읽기 쉬운 markdown 우선
- source note와 synthesis를 분리
- 페이지 수가 커져도 naming 규칙이 유지되게 한다
- 링크는 표준 markdown 상대 경로를 기본으로 한다

### 3. Schema/control layer
운영 규칙을 담습니다.

예시:
```text
AGENTS.md
schema/
  page-contract.md
  citation-policy.md
  naming.md
  workflow-ingest.md
  workflow-query.md
  workflow-lint.md
```

### 4. State layer
시간 흐름과 pending work를 따로 둡니다.

예시:
```text
state/
  log.md
  review-queue.md
  unresolved.md
```

권장 원칙:
- `log.md`는 append-only
- `review-queue.md`는 사람 검토 필요 항목만 모음
- `unresolved.md`는 아직 결론나지 않은 모순, 데이터 갭, open question을 유지

### 5. Derived layer
삭제 후 재생성 가능한 기계 친화 산출물입니다.

예시:
```text
derived/
  catalog.json
  backlinks.json
  graph.json
  search.sqlite
```

권장 원칙:
- source of truth로 취급하지 않는다
- regeneration command를 문서화한다
- UI/검색 기능은 여기에서 읽어가게 한다

## Page contracts

### Common frontmatter
```yaml
---
id: topic-transformers
title: Transformers
type: topic
status: active
updated_at: 2026-04-08
source_ids:
  - src-2026-0012
confidence: medium
---
```

### Recommended page sections
```md
# Title

## Summary
...

## Key Claims
...

## Evidence / Sources
...

## Open Questions
...

## Related Pages
...
```

### Suggested page types
- `source-note` — 단일 source에서 추출한 사실과 요약
- `topic` — 개념/주제 정리
- `entity` — 사람, 조직, 시스템, 프로젝트, 책, 제품 등
- `synthesis` — 질의 결과로 생성된 종합 분석
- `comparison` — 비교표/장단점/차이점
- `overview` — 진입점, index, map

## Link policy
- 기본 링크는 표준 markdown 상대 링크를 사용합니다.
- wikilink 문법은 optional adapter에서만 허용합니다.
- 페이지 제목 변경에 대비해 stable id와 slug 규칙을 유지합니다.

예시:
```md
[Transformers](../topics/transformers.md)
```

## Citation policy
최소 요구사항:
- 주요 주장에는 `source_ids` 또는 source note backlink가 있어야 한다
- high-stakes page는 원문 확인 날짜와 검토자 정보를 남긴다
- source 없는 주장이나 모호한 synthesis는 lint 대상으로 잡는다

강한 권장:
- source note마다 원문 경로와 source URL 유지
- synthesis에는 “raw recheck needed” 플래그 가능
- quote는 필요 최소한만 보관

## Operating loops

### Ingest loop
1. source를 `raw/inbox` 또는 `raw/sources`에 저장
2. stable id 부여 후 manifest 갱신
3. source note 생성
4. 관련 topic/entity/comparison/synthesis 페이지 갱신
5. `wiki/index.md` 갱신
6. `state/log.md`에 ingest 기록
7. 필요 시 `derived/*` 재생성

### Query loop
1. index/catalog/search를 통해 관련 wiki 페이지를 찾음
2. wiki 중심으로 answer를 합성
3. high-stakes 또는 ambiguity가 있으면 raw 재검증
4. 결과가 재사용 가치가 높으면 `wiki/syntheses/`에 저장
5. `state/log.md`에 query 기록

### Lint loop
정기적으로 아래를 확인합니다.
- broken links
- orphan pages
- stale claims
- source 없는 주장
- 서로 모순되는 pages
- naming drift
- duplicate pages
- unresolved question 누락

## Adapter strategy

### Core vs adapter test
새 기능을 넣을 때 아래를 확인합니다.
- adapter가 없어도 raw/wiki/schema 계약이 유지되는가?
- 앱 설정 파일이 없으면 ingest/query/lint가 멈추는가?
- 데이터 포맷이 앱 문법에 잠겨 있는가?

### Acceptable adapters
- Obsidian
- VS Code workspace settings
- qmd / local search CLI
- 정적 사이트 생성기
- lightweight web UI
- SQLite/full-text index

### Red flags
- canonical 링크가 `[[wikilink]]`에만 의존
- Dataview 없이는 index 탐색이 불가능
- app-specific metadata가 frontmatter 핵심을 오염
- source import가 browser extension 하나에 묶임

## Human-in-the-loop recommendations
- ingest 후 중요한 페이지는 샘플링 검토
- 고위험 도메인은 human review required 플래그 사용
- 질문 응답이 새 synthesis를 만들 때는 source coverage를 확인
- lint 결과 중 contradiction/stale claim은 사람이 우선순위를 지정

## Scale-up path
작게 시작할 때:
- `raw/`
- `wiki/index.md`
- `wiki/source-notes/`
- `wiki/topics/`
- `state/log.md`

중간 규모로 커지면:
- `entities/`, `syntheses/`, `comparisons/`
- `derived/catalog.json`, `backlinks.json`
- local search CLI

더 커지면:
- review queue automation
- search.sqlite 또는 external index
- web UI/dashboard
- scheduled lint jobs

## Non-goals
- raw source를 덮어쓰는 편집 시스템
- chat export를 그대로 wiki로 보관하는 것
- 특정 note-taking 앱을 시스템 필수요건으로 두는 것
- 모든 답변을 무조건 자동 저장하는 것
