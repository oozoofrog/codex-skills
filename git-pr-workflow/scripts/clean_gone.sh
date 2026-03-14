#!/usr/bin/env bash
set -euo pipefail

APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
elif [[ "${1:-}" == "--dry-run" || -z "${1:-}" ]]; then
  APPLY=0
else
  echo "usage: $0 [--dry-run|--apply]" >&2
  exit 2
fi

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "not a git repository" >&2
  exit 1
fi

ROOT=$(git rev-parse --show-toplevel)
CURRENT=$(git branch --show-current)
mapfile -t GONE_BRANCHES < <(git branch -vv | awk '/\[gone\]/{sub(/^[*+ ]+/, "", $1); print $1}')

if [[ ${#GONE_BRANCHES[@]} -eq 0 ]]; then
  echo "No [gone] branches found."
  exit 0
fi

echo "Repository: $ROOT"
echo "Current branch: $CURRENT"
echo "Mode: $([[ $APPLY -eq 1 ]] && echo apply || echo dry-run)"
echo

for branch in "${GONE_BRANCHES[@]}"; do
  if [[ "$branch" == "$CURRENT" ]]; then
    echo "skip current branch: $branch"
    continue
  fi

  worktree=$(git worktree list --porcelain | awk -v b="$branch" '
    /^worktree / { wt=$2 }
    /^branch / {
      sub("refs/heads/", "", $2)
      if ($2 == b) print wt
    }
  ' | head -n1)

  echo "branch: $branch"
  if [[ -n "$worktree" && "$worktree" != "$ROOT" ]]; then
    echo "  worktree: $worktree"
  fi

  if [[ $APPLY -eq 1 ]]; then
    if [[ -n "$worktree" && "$worktree" != "$ROOT" ]]; then
      git worktree remove --force "$worktree"
    fi
    git branch -D "$branch"
    echo "  deleted"
  else
    echo "  preview only"
  fi
  echo

done
