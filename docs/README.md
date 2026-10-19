Extracted from the game's guidebook (all rights belong to the developer): `components/`, `contracts/`, `database/`, `guide/`, `models/`, `types/`. Treat them as authoritative and read-only.

Our own notes: `AI_CHEATSHEET.md` + `cheatsheet/` (current behavior), `DESIGN_HISTORY.md` (rationale), `BENCHMARK.md`, `gameknowledge/` (game mechanics we measured or decompiled), `autoplay/` (walkthroughs), `headless/` (headless sim runs), `plans/` (work plans). Navigation: [`00_Table_of_Contents.md`](00_Table_of_Contents.md).

Current extraction: DOCS Manual **build 9f7a682** (2026-10-18).

To refresh after a game update: export the DOCS Manual in-game, drop it here as `Code-Terraform-DOCS-Manual-<build>.md` (gitignored), run `python devtools/game_update/split_docs_manual.py`, then review its printed routing report and `git diff`. The script updates the build line above. The same run also rebuilds `models/` from the game's `.pyright-resolved/stubs/__builtins__.pyi` (refreshed by the editor integration on each game update).

`extracted/` (gitignored, may be missing) is an optional local dump made with `devtools/game_update/build_docs/build_docs.py` (copied from `inspirations/vakermit/tools/`) straight from the game executable. Nothing depends on it; the only content it adds is the per-machine editor guides, the training lessons and the language-feature unlock flags.
