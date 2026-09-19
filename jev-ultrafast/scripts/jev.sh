#!/bin/bash
set -euo pipefail
umask 077
mode="${1:-status}"
if [ "$#" -gt 0 ]; then shift; fi
if [ "${JEV_CONTROLLER_LOCKED:-0}" != 1 ]; then
  case "$mode" in
    run|demo|prepare) exec env JEV_CONTROLLER_LOCKED=1 python3 "$(dirname "$0")/controller.py" bash "$0" "$mode" "$@" ;;
  esac
fi
cd /Users/oozoofrog/.local/share/jev-ultrafast
case "$mode" in
  status)
    /Applications/ChatGPT.app/Contents/Resources/codex login status
    test -s .env
    stat -f '.env permissions: %Lp' .env
    exec uv run --locked browser-harness doctor --json --require-existing-daemon
    ;;
  prepare) exec uv run --locked python /Users/oozoofrog/.codex/skills/jev-ultrafast/scripts/connection.py ;;
  demo)
    uv run --locked python -c 'import sys; sys.path.insert(0, "/Users/oozoofrog/.codex/skills/jev-ultrafast/scripts"); from connection import ready; sys.exit(0 if ready() else "Chrome is not ready; run jev.sh prepare first.")'
    exec uv run --locked --env-file .env jev "$@"
    ;;
  run) exec uv run --locked --env-file .env python /Users/oozoofrog/.codex/skills/jev-ultrafast/scripts/run.py "$@" ;;
  *) echo 'Usage: jev.sh status | prepare | demo | run --url URL --goal GOAL' >&2; exit 2 ;;
esac
