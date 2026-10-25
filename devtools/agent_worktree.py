#!/usr/bin/env python
"""Local git worktrees for parallel agent sessions: create, list, merge into main, remove.

Each worktree lives in .claude/worktrees/<topic> on branch agent/<topic>. It is
local only (no fetch, no remote): git checks it out from the shared object store.
Its .venv is a small venv that reuses the main checkout's packages through a .pth
file. It is not a junction, because `git worktree remove` follows junctions and
would empty the main .venv.

The watcher only deploys the main checkout, so worktree edits never reach the
save. scripts_sync.py refuses its save-writing commands inside a worktree.

merge first rebases the branch onto main inside the worktree, so the unit tests
run on exactly the tree that lands. Then it sets a sync hold in the main
checkout, runs `git merge --no-ff`, releases the hold, and removes the worktree
and its branch. On a conflict or a refused merge it aborts, releases the hold
and stops. A merge killed hard can leave the hold file; the tool prints its path.
The merge message is required, in the CODE_GUIDES.md commit format: the first -m
is the subject, each further -m a body paragraph.

remove refuses a worktree holding uncommitted or gitignored files that are not
regenerable (see REGENERABLE), unless --force: git deletes them with the worktree.

Examples:
  python devtools/agent_worktree.py new fluid-rework
  python devtools/agent_worktree.py list
  python devtools/agent_worktree.py merge fluid-rework -m "refactor(fluid): split plan from outlook"
  python devtools/agent_worktree.py merge fluid-rework -m "fix(fluid): ..." -m "Why ..." --keep --skip-tests
  python devtools/agent_worktree.py remove fluid-rework
"""

import argparse
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Also a valid scripts_sync holder name. Starts alphanumeric, so never "." or "..".
TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in range(1, 10)}
BRANCH_PREFIX = "agent/"
MAIN_BRANCH = "main"
VENV_PTH = "_main_venv.pth"
# Gitignored state the worktree rebuilds on demand; anything else ignored blocks remove.
REGENERABLE = {".venv", ".pyright-resolved", "__pycache__", ".ruff_cache", ".pytest_cache", ".sync-backups", ".cache"}
# Copied into a new worktree so resolve-preview picks the same tier as the main checkout.
SEEDED_STATE = ("devtools/.sync-backups/tier_high_water.json",)
# Conventional Commits subject, per CODE_GUIDES.md#commits
SUBJECT_RE = re.compile(r"^(feat|fix|refactor|perf|docs|test|chore|build|ci|style|revert)(\([\w./-]+\))?!?: \S")
SUBJECT_MAX = 72
BODY_WRAP = 72


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=False, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace")


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = run(["git", *args], cwd)
    if check and proc.returncode:
        fail(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return proc


def main_checkout() -> Path:
    """The main checkout, also when called from inside a linked worktree."""
    here = Path(__file__).resolve().parent
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=here).stdout.strip()
    return Path(common).parent


def venv_python(root: Path) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def python_out(python: Path | str, code: str) -> str:
    proc = run([str(python), "-c", code])
    if proc.returncode:
        raise RuntimeError(f"{python}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def worktrees(main: Path) -> list[dict]:
    """`git worktree list --porcelain` as dicts with path and branch (short name, or None)."""
    out, cur = [], {}
    for line in git("worktree", "list", "--porcelain", cwd=main).stdout.splitlines() + [""]:
        if not line:
            if cur:
                out.append(cur)
            cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": Path(val), "branch": None}
        elif key == "branch":
            cur["branch"] = val.removeprefix("refs/heads/")
    return out


def find(main: Path, name: str) -> dict:
    """The linked worktree named by topic, branch or path."""
    target = Path(name).resolve() if Path(name).exists() else None
    for wt in worktrees(main)[1:]:
        if name in (wt["path"].name, wt["branch"], BRANCH_PREFIX + name) or wt["path"].resolve() == target:
            return wt
    fail(f"no linked worktree matches {name!r} (see `list`)")
    raise AssertionError  # unreachable; fail() exits


def make_venv(main: Path, wt: Path) -> None:
    main_py = venv_python(main)
    if not main_py.exists():
        print(f"warning: {main_py} missing; worktree gets no .venv")
        return
    base = python_out(main_py, "import sys; print(sys._base_executable)")
    proc = run([base, "-m", "venv", "--without-pip", str(wt / ".venv")])
    if proc.returncode:
        raise RuntimeError(f"venv: {proc.stderr.strip()}")
    purelib = "import sysconfig; print(sysconfig.get_path('purelib'))"
    pth = Path(python_out(venv_python(wt), purelib)) / VENV_PTH
    pth.write_text(f"import site; site.addsitedir({python_out(main_py, purelib)!r})\n", encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> None:
    main = main_checkout()
    topic = args.topic
    if not TOPIC_RE.match(topic) or topic.endswith(".") or topic.split(".")[0].upper() in WINDOWS_RESERVED:
        fail(
            "topic: start with a letter or digit, then letters, digits, '.', '_' or '-'; no trailing '.' or CON/NUL/..."
        )
    wt = main / ".claude" / "worktrees" / topic
    if wt.exists():
        fail(f"{wt} exists")
    branch = BRANCH_PREFIX + topic
    git("worktree", "add", "-b", branch, str(wt), args.base, cwd=main)
    try:
        make_venv(main, wt)
    except (RuntimeError, OSError) as exc:
        git("worktree", "remove", "--force", str(wt), cwd=main, check=False)
        git("branch", "-D", branch, cwd=main, check=False)
        fail(f"{exc}; worktree and branch removed again")
    for rel in SEEDED_STATE:
        if (main / rel).is_file():
            (wt / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(main / rel, wt / rel)
    py = venv_python(wt)
    if py.exists():
        proc = subprocess.run([str(py), "devtools/scripts_sync.py", "resolve-preview"], check=False, cwd=wt)
        if proc.returncode:
            print("warning: resolve-preview failed; run it in the worktree before pyright")
    print(f"\nWorktree {wt}\nBranch   {branch} (from {args.base})")
    print(f"Untracked data such as internals/ stays in {main}; read it there.")


def cmd_list(args: argparse.Namespace) -> None:
    main = main_checkout()
    for wt in worktrees(main)[1:]:
        branch = wt["branch"]
        if not wt["path"].exists():
            print(f"{wt['path']}  (missing; `git worktree prune`)")
            continue
        dirty = len(git("status", "--porcelain", cwd=wt["path"]).stdout.splitlines())
        if branch:
            counts = git("rev-list", "--left-right", "--count", f"{MAIN_BRANCH}...{branch}", cwd=main).stdout.split()
            state = f"ahead {counts[1]}, behind {counts[0]}"
        else:
            state = "detached"
        print(f"{wt['path'].name:<36} {branch or '-':<40} {state}, {dirty} uncommitted")


def check_message(paragraphs: list[str]) -> None:
    subject, body = paragraphs[0], paragraphs[1:]
    if not SUBJECT_RE.match(subject):
        fail(f"subject {subject!r}: use `<type>(<scope>): <imperative summary>` (CODE_GUIDES.md#commits)")
    if len(subject) > SUBJECT_MAX or subject.endswith(".") or "\n" in subject:
        fail(f"subject: one line, at most {SUBJECT_MAX} characters, no trailing period")
    long = [line for para in body for line in para.splitlines() if len(line) > BODY_WRAP]
    if long:
        fail(f"body: wrap at {BODY_WRAP} characters; too long: {long[0]!r}")


def set_hold(main: Path, holder: str, note: str) -> Path:
    """Same file scripts_sync.py `hold` writes, in the main checkout the watcher reads."""
    path = main / "devtools" / ".sync-backups" / "holds" / holder
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{datetime.now(UTC).isoformat(timespec='seconds')} {note}\n", encoding="utf-8")
    print(f"Sync hold {path} set (delete it by hand if this run dies).")
    return path


def is_ancestor(main: Path, older: str, newer: str) -> bool:
    return git("merge-base", "--is-ancestor", older, newer, cwd=main, check=False).returncode == 0


def cmd_merge(args: argparse.Namespace) -> None:
    check_message(args.message)
    main = main_checkout()
    wt = find(main, args.name)
    path, branch = wt["path"], wt["branch"]
    if not branch:
        fail(f"{path} has a detached HEAD; commit on a branch first")
    if git("status", "--porcelain", cwd=path).stdout.strip():
        fail(f"{path} has uncommitted changes; commit or drop them first")
    head = git("symbolic-ref", "--short", "HEAD", cwd=main, check=False).stdout.strip()
    if head != MAIN_BRANCH:
        fail(f"main checkout is on {head or 'a detached HEAD'}, not {MAIN_BRANCH}")
    ahead = int(git("rev-list", "--count", f"{MAIN_BRANCH}..{branch}", cwd=main).stdout)
    if not ahead:
        print(f"{branch} has no commits beyond {MAIN_BRANCH}; nothing to merge.")
    else:
        if not is_ancestor(main, MAIN_BRANCH, branch):
            print(f"Rebasing {branch} onto {MAIN_BRANCH} in the worktree ...")
            if git("rebase", MAIN_BRANCH, cwd=path, check=False).returncode:
                conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=path, check=False).stdout.split()
                git("rebase", "--abort", cwd=path, check=False)
                fail(
                    f"rebase of {branch} onto {MAIN_BRANCH} stopped, branch unchanged. conflicts: {', '.join(conflicts)}"
                )
        if not args.skip_tests:
            py = venv_python(path)
            print(f"Running unit tests in {path} ...")
            tests = [str(py if py.exists() else sys.executable), "-m", "unittest", "discover", "-s", "tests", "-q"]
            if subprocess.run(tests, check=False, cwd=path).returncode:
                fail("tests failed in the worktree; nothing merged")
        hold = set_hold(main, "wt-" + path.name, f"agent_worktree merge {branch}")
        try:
            if not is_ancestor(main, MAIN_BRANCH, branch):
                fail(f"{MAIN_BRANCH} moved during the tests; nothing merged, run merge again")
            msg = [arg for para in args.message for arg in ("-m", para)]
            proc = git("merge", "--no-ff", "--no-edit", *msg, branch, cwd=main, check=False)
            if proc.returncode:
                conflicts = git("diff", "--name-only", "--diff-filter=U", cwd=main, check=False).stdout.split()
                if git("rev-parse", "-q", "--verify", "MERGE_HEAD", cwd=main, check=False).returncode == 0:
                    git("merge", "--abort", cwd=main)
                detail = ("conflicts: " + ", ".join(conflicts)) if conflicts else (proc.stderr or proc.stdout).strip()
                fail(f"merge of {branch} stopped, main unchanged. {detail}")
        finally:
            hold.unlink(missing_ok=True)
        print(f"Merged {branch} into {MAIN_BRANCH} ({ahead} commit(s)).")
    if not args.keep:
        remove(main, wt, force=False)


def unregenerable(path: Path) -> list[str]:
    """Uncommitted or gitignored files that `git worktree remove` would delete for good."""
    lost = []
    for line in git("status", "--porcelain", "--ignored", cwd=path).stdout.splitlines():
        rel = line[3:].strip('"')
        if not (line.startswith("!! ") and REGENERABLE & set(Path(rel).parts)):
            lost.append(rel)
    return lost


def remove(main: Path, wt: dict, force: bool) -> None:
    path, branch = wt["path"], wt["branch"]
    if not force:
        lost = unregenerable(path)
        if lost:
            fail(f"{path} still holds files remove would delete: {', '.join(lost[:8])}. Commit them, or use --force")
    proc = git("worktree", "remove", "--force", str(path), cwd=main, check=False)
    if proc.returncode:
        fail(f"could not remove {path}: {(proc.stderr or proc.stdout).strip()}. Branch {branch} kept")
    print(f"Removed worktree {path}")
    if branch:
        proc = git("branch", "-d", branch, cwd=main, check=False)
        if proc.returncode:
            print(f"Kept branch {branch}: not merged into {MAIN_BRANCH}. Drop it with `git branch -D {branch}`.")
        else:
            print(f"Deleted branch {branch}")


def cmd_remove(args: argparse.Namespace) -> None:
    main = main_checkout()
    remove(main, find(main, args.name), args.force)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("new", help="create .claude/worktrees/TOPIC on branch agent/TOPIC")
    p.add_argument("topic")
    p.add_argument("--base", default=MAIN_BRANCH, help="commit or branch to start from (default: main)")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("list", help="linked worktrees with commits ahead/behind main")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("merge", help="rebase, test, merge into main under a sync hold, then remove")
    p.add_argument("name", help="topic, branch or path")
    p.add_argument(
        "-m",
        "--message",
        action="append",
        required=True,
        help="merge message: first -m is the Conventional Commits subject, each further -m a body paragraph",
    )
    p.add_argument("--keep", action="store_true", help="keep the worktree and branch after merging")
    p.add_argument("--skip-tests", action="store_true", help="skip the unit tests before merging")
    p.set_defaults(func=cmd_merge)
    p = sub.add_parser("remove", help="remove a worktree; deletes its branch only if merged")
    p.add_argument("name", help="topic, branch or path")
    p.add_argument("--force", action="store_true", help="also remove uncommitted and unregenerable ignored files")
    p.set_defaults(func=cmd_remove)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
