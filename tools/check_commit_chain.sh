#!/usr/bin/env bash
# Run the test suite at each commit in a range, in a detached worktree.
#
# A commit that only passes with a later commit's code applied is a commit nobody
# can bisect through, and the failure surfaces months later in somebody else's
# afternoon. Cheap to check, so worth checking.
#
#   tools/check_commit_chain.sh main..HEAD
set -uo pipefail

RANGE="${1:-main..HEAD}"
WORKTREE="$(mktemp -d)/wt"
FAILED=0

cleanup() {
  git worktree remove --force "$WORKTREE" 2>/dev/null || true
}
trap cleanup EXIT

for sha in $(git rev-list --reverse "$RANGE"); do
  subject=$(git log -1 --format='%s' "$sha")
  cleanup
  if ! git worktree add -q --detach "$WORKTREE" "$sha" 2>/dev/null; then
    echo "SETUP-FAIL ${sha:0:9}  $subject"
    FAILED=1
    continue
  fi
  out=$(cd "$WORKTREE" && timeout 900 uv run pytest -q -x 2>&1 | tail -1)
  if echo "$out" | grep -qE '^[0-9]+ passed'; then
    printf 'PASS  %s  %-60.60s  %s\n' "${sha:0:9}" "$subject" "$out"
  else
    printf 'FAIL  %s  %-60.60s  %s\n' "${sha:0:9}" "$subject" "$out"
    FAILED=1
  fi
done

exit "$FAILED"
