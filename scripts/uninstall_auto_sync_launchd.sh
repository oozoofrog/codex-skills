#!/usr/bin/env bash

set -euo pipefail

LABEL="${LABEL:-com.oozoofrog.codex-skills-autosync}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      LABEL="${2:?missing label value}"
      PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
      shift 2
      ;;
    --help)
      cat <<'EOF'
Usage: ./scripts/uninstall_auto_sync_launchd.sh [--label <value>]
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true

if [[ -f "${PLIST_PATH}" ]]; then
  rm -f "${PLIST_PATH}"
fi

cat <<EOF
Removed launchd auto-sync job.

- Label: ${LABEL}
- Plist removed: ${PLIST_PATH}
EOF
