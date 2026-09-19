#!/bin/bash
set -euo pipefail
cd /Users/oozoofrog/.local/share/jev-ultrafast
mode="${1:-status}"
if [ "$#" -gt 0 ]; then shift; fi
case "$mode" in
  status)
    /Applications/ChatGPT.app/Contents/Resources/codex login status
    test -s .env
    stat -f '.env permissions: %Lp' .env
    exec uv run --locked browser-harness doctor --json --require-existing-daemon
    ;;
  demo) exec uv run --locked --env-file .env jev "$@" ;;
  run) exec uv run --locked --env-file .env python /Users/oozoofrog/.codex/skills/jev-ultrafast/scripts/run.py "$@" ;;
  *) echo 'Usage: jev.sh status | demo | run --url URL --goal GOAL' >&2; exit 2 ;;
esac
