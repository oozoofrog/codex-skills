#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LABEL="${LABEL:-com.oozoofrog.codex-skills-autosync}"
INTERVAL="${INTERVAL:-15}"
DEBOUNCE="${DEBOUNCE:-20}"
RETRY_COOLDOWN="${RETRY_COOLDOWN:-120}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"

usage() {
  cat <<'EOF'
Usage: ./scripts/install_auto_sync_launchd.sh [options]

Options:
  --label <value>           launchd label
  --interval <seconds>      git status polling interval
  --debounce <seconds>      stable change wait time before sync
  --retry-cooldown <sec>    failed sync retry cooldown
  --python-bin <path>       python3 executable path
  --help                    show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      LABEL="${2:?missing label value}"
      shift 2
      ;;
    --interval)
      INTERVAL="${2:?missing interval value}"
      shift 2
      ;;
    --debounce)
      DEBOUNCE="${2:?missing debounce value}"
      shift 2
      ;;
    --retry-cooldown)
      RETRY_COOLDOWN="${2:?missing retry cooldown value}"
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN="${2:?missing python path}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 not found in PATH." >&2
  exit 1
fi

PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs"
STDOUT_LOG="${LOG_DIR}/${LABEL}.out.log"
STDERR_LOG="${LOG_DIR}/${LABEL}.err.log"

mkdir -p "${PLIST_DIR}" "${LOG_DIR}"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>${REPO_ROOT}/scripts/auto_sync_daemon.py</string>
    <string>--repo-root</string>
    <string>${REPO_ROOT}</string>
    <string>--sync-script</string>
    <string>${REPO_ROOT}/scripts/sync_repo.sh</string>
    <string>--interval</string>
    <string>${INTERVAL}</string>
    <string>--debounce</string>
    <string>${DEBOUNCE}</string>
    <string>--retry-cooldown</string>
    <string>${RETRY_COOLDOWN}</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>WorkingDirectory</key>
  <string>${REPO_ROOT}</string>

  <key>ProcessType</key>
  <string>Background</string>

  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>

  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
</dict>
</plist>
EOF

plutil -lint "${PLIST_PATH}" >/dev/null

launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

cat <<EOF
Installed launchd auto-sync job.

- Label: ${LABEL}
- Plist: ${PLIST_PATH}
- Stdout log: ${STDOUT_LOG}
- Stderr log: ${STDERR_LOG}

Useful commands:
  launchctl print gui/$(id -u)/${LABEL}
  tail -f ${STDOUT_LOG}
  tail -f ${STDERR_LOG}
EOF
