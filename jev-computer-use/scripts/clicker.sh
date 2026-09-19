#!/bin/bash
set -euo pipefail
umask 077
cd /Users/oozoofrog/.local/share/typesafe-computer-use
mode="${1:-status}"
if [ "$#" -gt 0 ]; then shift; fi
case "$mode" in
  status)
    /Applications/ChatGPT.app/Contents/Resources/codex login status
    test -s .env
    stat -f '.env permissions: %Lp' .env
    exec uv run --locked python -c 'import Quartz; from typesafe_computer_use.macos import accessibility_trusted; print({"screen_recording":bool(Quartz.CGPreflightScreenCaptureAccess()),"accessibility":accessibility_trusted()})'
    ;;
  inspect) exec uv run --locked --env-file .env clicker-inspect "$@" ;;
  preview)
    for arg in "$@"; do
      if [ "$arg" = '--act' ]; then echo 'Use run for live actions.' >&2; exit 2; fi
    done
    exec uv run --locked --env-file .env clicker "$@"
    ;;
  run) exec uv run --locked --env-file .env clicker --act --steps 10 "$@" ;;
  *) echo 'Usage: clicker.sh status | inspect GOAL | preview GOAL | run GOAL' >&2; exit 2 ;;
esac
