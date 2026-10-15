"""PreToolUse guard: block git commands that swap scripts/ content unless this session holds the sync watcher.

scripts_sync.py watch deploys every scripts/ change within ~0.4 s, so a stash/checkout/reset without
a hold pushes the swapped files live (CLAUDE.md Boundaries). The hold is
devtools/.sync-backups/holds/<session_id>; a command that creates it itself passes.
Exit 2 blocks the call and shows stderr to the model.
"""

import json
import os
import re
import sys

# Read-only or non-swapping forms pass: stash list/show, checkout -b/-B new branch, restore --staged only.
SWAP = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:"
    r"stash(?!\s+(?:list|show)\b)"
    r"|checkout(?!\s+-[bB]\b)"
    r"|switch"
    r"|restore(?!\s+--staged\s+[^-])"
    r"|reset\s+--hard"
    r"|pull|merge|rebase|cherry-pick|revert|am\b"
    r")"
)


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    session = data.get("session_id") or ""
    if not session or not SWAP.search(command):
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    hold = os.path.join(root, "devtools", ".sync-backups", "holds", session)
    if os.path.exists(hold) or f"holds/{session}" in command:
        return 0
    print(
        "Blocked: this git command can swap scripts/ content while the sync watcher is live, and no sync hold is set. "
        f"Set it first: mkdir -p devtools/.sync-backups/holds && date > devtools/.sync-backups/holds/{session} "
        f"(remove it after: rm -f devtools/.sync-backups/holds/{session}). "
        "Prefer git worktree or git show REV:path over swaps.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
