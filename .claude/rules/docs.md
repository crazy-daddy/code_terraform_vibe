---
paths:
  - "docs/**"
---

- Game API docs (`docs/components/`, `contracts/`, `database/`, `guide/`, `models/`, `types/`) are authoritative and read-only. Allowed edits: AI-accessibility fixes (docstrings, clearer examples, typos).
- Keep those game docs tracked in git; cloud agents have no other access to them. Only the raw export `docs/Code-Terraform-DOCS-Manual*.md` stays gitignored.
- `docs/00_Table_of_Contents.md` is our navigation file: add new docs files there.
- `docs/AI_CHEATSHEET.md` and `docs/cheatsheet/` describe current behavior only. Topic-file section headings use `### §<id> Title`, so `grep -n "^#.*§<id>"` finds them. History and rationale go to `docs/DESIGN_HISTORY.md`.
