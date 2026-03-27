#!/bin/bash
set -euo pipefail

TARGET="${1:-$(pwd)}"
ROOT_FILE="$TARGET/AGENTS.md"

if [[ ! -f "$ROOT_FILE" ]]; then
  echo "ℹ️ AGENTS.md가 없습니다. agent-context-init으로 기본 구조를 만드는 것이 좋습니다."
  exit 0
fi

LINE_COUNT=$(wc -l < "$ROOT_FILE" | tr -d ' ')
NESTED_COUNT=$(find "$TARGET" -name AGENTS.md -not -path "$ROOT_FILE" | wc -l | tr -d ' ')
OVERRIDE_COUNT=$(find "$TARGET" -name AGENTS.override.md | wc -l | tr -d ' ')

echo "Root AGENTS.md: $ROOT_FILE"
echo "Root lines: $LINE_COUNT"
echo "Nested AGENTS.md: $NESTED_COUNT"
echo "AGENTS.override.md: $OVERRIDE_COUNT"

if [[ "$LINE_COUNT" -gt 200 ]]; then
  echo "⚠️ 루트 AGENTS.md가 ${LINE_COUNT}라인입니다. 공통 규칙만 남기고 분산 여부를 검토하세요."
fi
