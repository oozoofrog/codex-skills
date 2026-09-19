#!/bin/bash
set -euo pipefail
umask 077
export PYTHONUNBUFFERED=1
# Full-display OCR avoids Chrome helper windows cropping out native permission sheets.
export CLICKER_FULL_SCREEN="${CLICKER_FULL_SCREEN:-1}"
export CLICKER_OCR_LANGUAGES="${CLICKER_OCR_LANGUAGES:-ko-KR,en-US}"
mode="${1:-status}"
if [ "$#" -gt 0 ]; then shift; fi
if [ "${JEV_CONTROLLER_LOCKED:-0}" != 1 ]; then
  case "$mode" in
    run|preview) exec env JEV_CONTROLLER_LOCKED=1 python3 "$(dirname "$0")/controller.py" bash "$0" "$mode" "$@" ;;
  esac
fi
cd /Users/oozoofrog/.local/share/typesafe-computer-use
case "$mode" in
  status)
    /Applications/ChatGPT.app/Contents/Resources/codex login status
    test -s .env
    stat -f '.env permissions: %Lp' .env
    exec uv run --locked python -c 'import Quartz; from typesafe_computer_use.macos import accessibility_trusted; print({"screen_recording":bool(Quartz.CGPreflightScreenCaptureAccess()),"accessibility":accessibility_trusted()})'
    ;;
  windows)
    exec uv run --locked python -c 'import json,sys; from typesafe_computer_use import macos; print(json.dumps([{"id": i, "title": t, "bounds": b} for i,t,b in map(macos.window_record,macos.app_windows(macos.app_pid(sys.argv[1])))],ensure_ascii=False))' "${1:?Supply an app name}"
    ;;
  inspect) exec uv run --locked --env-file .env clicker-inspect "$@" ;;
  preview)
    for arg in "$@"; do
      if [ "$arg" = '--act' ]; then echo 'Use run for live actions.' >&2; exit 2; fi
    done
    exec uv run --locked --env-file .env clicker "$@"
    ;;
  run) exec uv run --locked --env-file .env clicker --act --steps 10 "$@" ;;
  *) echo 'Usage: clicker.sh status | windows APP | inspect GOAL | preview GOAL | run GOAL [--target-app APP] [--window-id ID]' >&2; exit 2 ;;
esac
