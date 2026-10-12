#!/usr/bin/env bash
# SessionStart: tell Claude when origin/main has new commits or a merge/rebase is unfinished.
# Unpushed local commits and uncommitted changes are normal here (parallel work) and not reported.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
gitdir=$(git rev-parse --git-dir)
msgs=()

if ! timeout 20 git fetch -q origin 2>/dev/null; then
  msgs+=("git fetch origin failed or timed out; remote state unknown.")
fi

for f in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD; do
  [ -e "$gitdir/$f" ] && msgs+=("Unfinished operation: $f exists ($(git diff --name-only --diff-filter=U | wc -l) unmerged paths). Tell the user before doing anything else.")
done
[ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ] && msgs+=("Unfinished rebase in progress. Tell the user before doing anything else.")

branch=$(git symbolic-ref --short -q HEAD)
upstream=$(git rev-parse --abbrev-ref -q "@{u}" 2>/dev/null)
if [ -n "$upstream" ]; then
  behind=$(git rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)
  if [ "$behind" -gt 0 ]; then
    msgs+=("$upstream has $behind commit(s) not in local $branch:")
    msgs+=("$(git log --oneline -10 "HEAD..$upstream")")
    msgs+=("Before starting the task: tell the user, then pull them (git pull --no-rebase origin ${upstream#origin/}). Set your own sync hold (devtools/.sync-backups/holds/<session id>) first and remove only that file after. If the pull conflicts, stop and report the conflicts.")
  fi
fi

[ ${#msgs[@]} -eq 0 ] && exit 0
echo "[git sync check]"
printf '%s\n' "${msgs[@]}"
exit 0
