#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_NAME="${REMOTE_NAME:-origin}"
SYNC_BRANCH="${SYNC_BRANCH:-}"
COMMIT_MESSAGE=""
DRY_RUN=0
NO_PUSH=0
QUIET=0
AUTO_MODE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/sync_repo.sh [options]

Safely sync the current repo by fetching, rebasing, staging, committing, and pushing.

Options:
  --branch <name>      Branch to sync. Defaults to the current branch.
  --remote <name>      Remote to sync against. Defaults to origin.
  --message <text>     Custom commit message.
  --auto               Mark this run as auto-sync and use an auto message if needed.
  --no-push            Stop after commit; do not push.
  --dry-run            Print planned actions without changing git state.
  --quiet              Reduce informational output.
  --help               Show this help.
EOF
}

log() {
  if [[ "${QUIET}" -eq 0 ]]; then
    printf '[sync_repo] %s\n' "$*"
  fi
}

changed_roots() {
  git diff --cached --name-only | awk '
    NF == 0 { next }
    {
      split($0, parts, "/")
      if (parts[1] == ".system" && parts[2] != "") {
        print parts[1] "/" parts[2]
      } else {
        print parts[1]
      }
    }
  ' | awk '!seen[$0]++'
}

build_auto_commit_message() {
  local -a paths=()
  local item

  while IFS= read -r item; do
    [[ -n "${item}" ]] && paths+=("${item}")
  done < <(changed_roots)

  if [[ "${#paths[@]}" -eq 0 ]]; then
    printf 'Auto-sync skills'
    return
  fi

  local limit=3
  local -a preview=("${paths[@]:0:${limit}}")
  local summary
  summary="$(IFS=', '; printf '%s' "${preview[*]}")"

  if [[ "${#paths[@]}" -gt "${limit}" ]]; then
    printf 'Auto-sync skills: %s (+%d more)' "${summary}" "$(( ${#paths[@]} - limit ))"
  else
    printf 'Auto-sync skills: %s' "${summary}"
  fi
}

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '+'
    for arg in "$@"; do
      printf ' %q' "${arg}"
    done
    printf '\n'
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch)
      SYNC_BRANCH="${2:?missing branch value}"
      shift 2
      ;;
    --remote)
      REMOTE_NAME="${2:?missing remote value}"
      shift 2
      ;;
    --message)
      COMMIT_MESSAGE="${2:?missing message value}"
      shift 2
      ;;
    --auto)
      AUTO_MODE=1
      shift
      ;;
    --no-push)
      NO_PUSH=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
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

cd "${REPO_ROOT}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This directory is not a git repository: ${REPO_ROOT}" >&2
  exit 1
fi

if [[ -z "${SYNC_BRANCH}" ]]; then
  SYNC_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi

if [[ "${SYNC_BRANCH}" == "HEAD" ]]; then
  echo "Detached HEAD is not supported for sync_repo.sh." >&2
  exit 1
fi

if [[ "${DRY_RUN}" -eq 0 ]]; then
  LOCK_HASH="$(printf '%s' "${REPO_ROOT}" | shasum | awk '{print $1}')"
  LOCK_DIR="${TMPDIR:-/tmp}/codex-sync-${LOCK_HASH}.lock"
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    log "Another sync is already running; skipping."
    exit 0
  fi
  trap 'rmdir "${LOCK_DIR}" >/dev/null 2>&1 || true' EXIT
fi

log "Repo: ${REPO_ROOT}"
log "Remote/branch: ${REMOTE_NAME}/${SYNC_BRANCH}"

run git fetch "${REMOTE_NAME}" "${SYNC_BRANCH}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "Would run: git pull --rebase --autostash ${REMOTE_NAME} ${SYNC_BRANCH}"
else
  if git show-ref --verify --quiet "refs/remotes/${REMOTE_NAME}/${SYNC_BRANCH}"; then
    log "Rebasing onto ${REMOTE_NAME}/${SYNC_BRANCH}"
    git pull --rebase --autostash "${REMOTE_NAME}" "${SYNC_BRANCH}"
  else
    log "Remote branch ${REMOTE_NAME}/${SYNC_BRANCH} does not exist yet; pull skipped."
  fi
fi

run git add -A

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log "Dry run complete."
  exit 0
fi

if ! git diff --cached --quiet; then
  if [[ -z "${COMMIT_MESSAGE}" ]]; then
    if [[ "${AUTO_MODE}" -eq 1 ]]; then
      COMMIT_MESSAGE="$(build_auto_commit_message)"
    else
      COMMIT_MESSAGE="Sync skills: $(date '+%Y-%m-%d %H:%M:%S %z')"
    fi
  fi
  log "Creating commit: ${COMMIT_MESSAGE}"
  git commit -m "${COMMIT_MESSAGE}"
else
  log "No new local changes to commit."
fi

if git show-ref --verify --quiet "refs/remotes/${REMOTE_NAME}/${SYNC_BRANCH}"; then
  AHEAD_COUNT="$(git rev-list --count "${REMOTE_NAME}/${SYNC_BRANCH}..HEAD")"
else
  AHEAD_COUNT="1"
fi

if [[ "${NO_PUSH}" -eq 1 ]]; then
  log "Push skipped (--no-push)."
elif [[ "${AHEAD_COUNT}" -gt 0 ]]; then
  log "Pushing ${SYNC_BRANCH} to ${REMOTE_NAME}"
  git push "${REMOTE_NAME}" "${SYNC_BRANCH}"
else
  log "Already synced with ${REMOTE_NAME}/${SYNC_BRANCH}."
fi
