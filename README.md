# Code: Terraform — Automation Scripts

Python automation scripts for [Code: Terraform](https://store.steampowered.com/app/868160/Code_Terraform/), a game where you
write Python that runs inside the game's own sandboxed interpreter to run an automated colony.
This repo is the **dev root** — it is not itself a save folder. Deployed scripts live in the
game's live save directory (`%APPDATA%\io.codeterraform.game\save_*_scripts`) and are kept in sync
from here by a small tool, so this repo never gets swarmed with per-instance, per-save generated
files.

## Structure

```
scripts/                    # source of truth for every deployable script and lib/ module
  0_cold_boot/               # baseline tier - always active, no unlocks required
  1_early/                   # unlocked once research_computer is researched
  2_libunlock/                # unlocked once the Shared Library is researched
  3_archiveunlock/            # unlocked once the Data Archive is researched
  4_controlpanel/             # unlocked once the Control Room is researched
  5_uprising/                 # placeholder future tier
    <category>/<name>.py      # one script per machine type, e.g. power/solar.py
    lib/<module>.py           # shared library modules for that tier
    control_panel/            # Control Room panel cards (see docs/AI_CHEATSHEET.md §7)
  contract/                   # Earth Clearance contract puzzle solvers - untiered, see below
  _unmatched/                 # gitignored staging area, see devtools/scripts_sync.py

devtools/
  scripts_sync.py            # syncs scripts/ into a live save folder's script slots
  _migrate_from_root.py       # one-off migration script (kept for reference)

docs/                        # authoritative game API reference (components, models, database)
tools/                       # git submodule: auto-deploy/DAP/early-game automation
inspirations/                # git submodules: other players' Code: Terraform repos
legacy/, internals/          # archived / reference-only material

CLAUDE.md                    # project rules and conventions for AI coding agents
TODO.md                      # roadmap and task tracker
docs/AI_CHEATSHEET.md         # single source of truth for formulas, constants, module map
```

### Why tiers?

Each tier is a checkpoint in the game's own progression (research unlocks, in this codebase's
current scheme), not a folder you pick by hand. A `.criteria` file at each tier's root (e.g.
`scripts/3_archiveunlock/.criteria`) declares what must be true of a save — which techs are
unlocked, how many outposts exist — for that tier to be considered active. `scripts_sync.py` reads
a save's own state file to figure out the highest tier whose criteria (and all its ancestors') are
satisfied, automatically, per save — no manual bookkeeping. A script or `lib/` module only needs to
exist at the lowest tier where its behavior is actually correct; higher tiers fall back to a lower
tier's file when they don't define their own. See `docs/AI_CHEATSHEET.md` §9 for the full scheme.

Tiers aren't a hardcoded list — `scripts_sync.py` discovers them by scanning `scripts/` for
`<N>_<anything>` dirs and sorting by `N` numerically (`10_x` sorts after `9_x`, never between
`1_x`/`2_x`), so the text after the number is free-form and numbers can skip (add
`scripts/3_inbetween/` later between two existing tiers and it's picked up automatically, no code
change). A dir that starts with a digit but isn't a clean `<int>_...` (`1N3_DERP`), or two dirs
claiming the same number (`10_hi`/`10_ho`), is treated as a naming mistake and errors out rather
than being guessed past.

A category dir sitting directly under `scripts/` (a sibling of the tier dirs, not nested inside
one) is a **global category** — not gated by any `.criteria`, always included regardless of which
tier is active. `scripts/contract/` is the current example: Earth Clearance contracts are genuinely
tech-independent, self-contained scripts, not something that belongs to one progression tier.

## Basic usage

Set up the environment once:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Then, from the repo root:

```
# Show what would sync, without writing anything
.venv\Scripts\python devtools\scripts_sync.py status

# Fill every empty script slot in the live save, once
.venv\Scripts\python devtools\scripts_sync.py once

# Keep running and sync as files change on either side
.venv\Scripts\python devtools\scripts_sync.py watch

# Regenerate the resolved lib/ preview so Pyright can resolve imports
.venv\Scripts\python devtools\scripts_sync.py resolve-preview
```

The save folder is auto-detected (newest `save_*_scripts` under
`%APPDATA%\io.codeterraform.game\`); pass `--save-dir` or set `CT_SAVE_DIR` to target a specific
one. Run `scripts_sync.py --help` (or any subcommand `--help`) for the full flag list.

This is boilerplate for now — proper per-script usage docs (what each machine script does, what it
expects deployed, how tiers differ for it) are still to be written; `docs/AI_CHEATSHEET.md` and each
script's own module docstring are the best reference until then.
