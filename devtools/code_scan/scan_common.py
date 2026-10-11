"""Shared file discovery and ignore-file parsing for the static scans in devtools/."""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO_ROOT, "scripts")
EXTRA_DIRS = ("contract", "onboarding")


def scanned_files():
    """{display path: (absolute path, tier or None)}: highest tier copy of each tiered file, plus EXTRA_DIRS."""
    files = {}
    tiers = sorted((int(d.split("_")[0]), d) for d in os.listdir(SCRIPTS) if re.match(r"^\d+_", d))
    roots = [(os.path.join(SCRIPTS, d), n, False) for n, d in tiers]
    roots += [(os.path.join(SCRIPTS, d), None, True) for d in EXTRA_DIRS if os.path.isdir(os.path.join(SCRIPTS, d))]
    for root, tier, keep_dir in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    rel = os.path.relpath(path, SCRIPTS if keep_dir else root).replace("\\", "/")
                    files[rel] = (path, tier)
    return files


def ignore_lines(path):
    """Non-empty lines of an ignore file, '#' comments stripped. Missing file: none."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [line for line in (raw.split("#", 1)[0].strip() for raw in f) if line]
