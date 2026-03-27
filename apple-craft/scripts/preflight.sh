#!/bin/bash
set -euo pipefail

# apple-craft: 참조 문서 존재 확인

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REF_DIR="$SKILL_DIR/references"

if [[ ! -d "$REF_DIR" ]]; then
  echo "apple-craft: 참조 디렉토리가 존재하지 않습니다: $REF_DIR" >&2
  echo "  scripts/sync-docs.sh를 먼저 실행하세요." >&2
  exit 1
fi

count=0
for f in "$REF_DIR"/*.md; do
  [ -e "$f" ] || continue
  [[ "$(basename "$f")" == "_index.md" ]] && continue
  count=$((count + 1))
done

if [[ "$count" -lt 1 ]]; then
  echo "apple-craft: 참조 문서가 없습니다. scripts/sync-docs.sh를 먼저 실행하세요." >&2
  exit 1
fi
echo "apple-craft: ${count}개 참조 문서 확인됨"
