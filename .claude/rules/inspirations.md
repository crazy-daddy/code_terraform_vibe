---
paths:
  - "inspirations/**"
  - "TODO_inspirations*.md"
---

- `inspirations/` holds community solutions; `inspirations/discord-panels/` is the reference for telemetry and dashboard UI layouts. `TODO_inspirations.md` lists the ideas selected for implementation.
- Ideas there may be outdated. Cross-check against `TODO.md` and `docs/` before using one.
- Sweep workflow:
  1. Compare files in `inspirations/` against `inspirations/.lastaccesslist`. Pick unassessed files and files modified after their entry, 3-5 per run. Read helper files they depend on only when relevant.
  2. Evaluate them against `TODO.md`, `TODO_inspirations.md` and `docs/`.
  3. Add or update ideas in `TODO_inspirations.md` as `[ ]`/`[x]` entries with a rationale and the `inspirations/` file location.
  4. In the same turn, add a `.lastaccesslist` line per file: `<relative path> | <ISO date> | <brief note>`.
- `.lastaccesslist` lists only files actually read. A file read and judged irrelevant still gets a line saying why. A partly read helper gets a line saying "partial". A byte-identical duplicate can be noted as "duplicate of X". Never list a file you selected but didn't read.
