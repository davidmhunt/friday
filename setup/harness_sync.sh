#!/usr/bin/env bash
# Convenience wrapper for porting harness changes between projects that
# share the "friday" submodule. Run from a consumer repo root.
#
#   ./harness.sh sync push   # commit+push local .friday/ edits, bump the
#                             # pointer in this repo
#   ./harness.sh sync pull   # pull the latest .friday/ commit, re-sync
#                             # symlinks/materialized files, bump the pointer
#
# Refuses to run with unrelated uncommitted changes elsewhere unless --force.
set -euo pipefail

SUBMODULE_DIR=".friday"
FORCE=false
for arg in "$@"; do
  [ "$arg" = "--force" ] && FORCE=true
done

require_clean_tree() {
  if [ "$FORCE" = true ]; then
    return
  fi
  if [ -n "$(git status --porcelain -- . ":!$SUBMODULE_DIR" 2>/dev/null)" ]; then
    echo "Uncommitted changes outside $SUBMODULE_DIR/ — commit/stash them first, or pass --force." >&2
    exit 1
  fi
}

cmd_push() {
  require_clean_tree
  if [ -z "$(git -C "$SUBMODULE_DIR" status --porcelain)" ]; then
    echo "No changes in $SUBMODULE_DIR/ to push."
    return
  fi
  echo "Changes in $SUBMODULE_DIR/:"
  git -C "$SUBMODULE_DIR" status --short
  read -rp "Commit message: " msg
  git -C "$SUBMODULE_DIR" add -A
  git -C "$SUBMODULE_DIR" commit -m "$msg"
  git -C "$SUBMODULE_DIR" push
  submodule_hash=$(git -C "$SUBMODULE_DIR" rev-parse --short HEAD)
  git add "$SUBMODULE_DIR"
  git commit -m "Bump $SUBMODULE_DIR to $submodule_hash"
  superproject_hash=$(git rev-parse --short HEAD)
  echo "Pushed. friday@$submodule_hash, consumer@$superproject_hash"
}

cmd_pull() {
  require_clean_tree
  git submodule update --remote --merge "$SUBMODULE_DIR"
  if [ -z "$(git status --porcelain -- "$SUBMODULE_DIR")" ]; then
    echo "$SUBMODULE_DIR is already up to date."
    return
  fi
  python3 "$SUBMODULE_DIR/setup/init_harness.py"
  git add "$SUBMODULE_DIR"
  echo "Review the diff, then commit:"
  git status --short
}

case "${1:-}" in
  push) cmd_push ;;
  pull) cmd_pull ;;
  *) echo "Usage: $0 {push|pull} [--force]" >&2; exit 1 ;;
esac
