All files in subfolders here are extracted from the game's guidebook - all rights belong to the developer!

Current extraction: DOCS Manual **build 3b1b03e** (2026-09-30).

To refresh after a game update: export the DOCS Manual in-game, drop it here as `Code-Terraform-DOCS-Manual-<build>.md` (gitignored), run `python devtools/split_docs_manual.py`, then review its printed routing report and `git diff`. The script updates the build line above. The same run also rebuilds `models/` from the game's `.pyright-resolved/stubs/__builtins__.pyi` (refreshed by the editor integration on each game update).

`extracted/` (gitignored, may be missing) is an optional local dump made with `inspirations/vakermit/tools/build_docs.py` straight from the game executable. Nothing depends on it; the only content it adds is the per-machine editor guides, the training lessons and the language-feature unlock flags.
