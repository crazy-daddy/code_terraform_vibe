---
paths:
  - "scripts/**/*.py"
  - "autoplay/**/*.py"
  - "devtools/**/*.py"
  - "tests/**/*.py"
---

- Before editing, read the matching sections of `CODE_GUIDES.md`. Code under `scripts/` and `autoplay/` runs in the game's restricted interpreter: read "Game interpreter" there first.
- `devtools/` runs on host Python; the game interpreter rules don't apply to it.
- `devtools/scripts_sync.py` is the only code allowed to write into a save folder: script slots, `lib/`, the typed-`self` block of `user_stubs.py`, and the `.codeterraform/` command files. Mechanics: `docs/cheatsheet/dev_workflow.md` §9.
