# Starter Template

## Minimal repository layout

```text
knowledge-base/
  README.md
  AGENTS.md
  raw/
    inbox/
    sources/
    assets/
    manifest.jsonl
  wiki/
    index.md
    overview.md
    topics/
    entities/
    source-notes/
    syntheses/
    comparisons/
  state/
    log.md
    review-queue.md
    unresolved.md
  derived/
    catalog.json
    backlinks.json
    graph.json
```

## Minimal `AGENTS.md` skeleton

```md
# AGENTS.md

## Purpose
이 저장소는 raw source와 LLM-maintained wiki를 분리해 지속적으로 지식을 축적하는 knowledge base다.

## Core layers
- `raw/`: immutable source of truth
- `wiki/`: LLM이 유지하는 markdown knowledge layer
- `state/`: log, review queue, unresolved issues
- `derived/`: 재생성 가능한 검색/그래프 산출물

## Non-negotiable rules
- raw source는 수정하지 않는다.
- wiki의 주요 주장에는 source trace가 있어야 한다.
- ingest 후 `wiki/index.md`와 `state/log.md`를 갱신한다.
- high-stakes 질문은 raw source 재검증 없이 단정하지 않는다.
- adapter-specific 기능은 core format을 오염시키지 않는다.

## Workflows
### Ingest
1. source 저장
2. manifest 갱신
3. source note 생성
4. 관련 wiki pages 업데이트
5. index/log 갱신

### Query
1. wiki/index 또는 derived catalog에서 관련 pages를 찾는다.
2. wiki를 우선 사용하되 필요 시 raw source를 재검증한다.
3. 재사용 가치가 높은 답변은 synthesis page로 남긴다.

### Lint
다음 문제를 정기적으로 찾는다.
- broken links
- orphan pages
- stale claims
- source 없는 주장
- unresolved contradiction
```

## `index.md` starter

```md
# Index

## Overview
- [Overview](./overview.md) — 이 knowledge base의 진입점

## Topics
- [Transformers](./topics/transformers.md) — transformer architecture overview

## Source notes
- [Karpathy LLM Wiki](./source-notes/2026-04-08-karpathy-llm-wiki.md) — persistent wiki pattern gist summary
```

## `log.md` starter

```md
# Log

## [2026-04-08] ingest | Karpathy LLM Wiki gist
- source id: src-2026-0001
- added source note: `wiki/source-notes/2026-04-08-karpathy-llm-wiki.md`
- updated pages:
  - `wiki/index.md`
  - `wiki/overview.md`
```

## Recommended frontmatter

```yaml
---
id: src-note-2026-0001
title: Karpathy LLM Wiki
type: source-note
status: active
updated_at: 2026-04-08
source_ids:
  - src-2026-0001
confidence: high
---
```

## Optional adapters checklist
- Obsidian vault로 열 수는 있지만 core link format은 markdown 상대 링크로 유지한다.
- static-site generator를 붙일 수 있지만 `wiki/` 구조를 build step에 맞춰 뒤틀지 않는다.
- qmd나 SQLite search를 붙일 수 있지만 `derived/` 아래 산출물로 취급한다.
