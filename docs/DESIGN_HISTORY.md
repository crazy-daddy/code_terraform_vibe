# Design History & Postmortems

This file holds the *why* behind decisions in [`AI_CHEATSHEET.md`](AI_CHEATSHEET.md): bug-hunt
narratives, rejected approaches, root-cause postmortems, and design-reasoning that don't belong in
a quick-reference doc but are worth keeping discoverable. Organized by the same section topics as
the cheatsheet, so a `§1b`-style reference there maps to a matching heading here. Numbers/formulas
that are still the live source of truth live in the cheatsheet, not here — this file is prose,
not a duplicate constants table.

---

| § prefix | Topic | File |
| :--- | :--- | :--- |
| §1, §1a, §1b, §1c, §0 (heater) | Power & Fluids | [`design_history/power_fluids.md`](design_history/power_fluids.md) |
| §1e-§1l | Bio, Seeds, Planting & Wildlife | [`design_history/bio_wildlife.md`](design_history/bio_wildlife.md) |
| §2a, §2c, §2d, §2i, §10 | Production, Storage & Logistics | [`design_history/logistics_production.md`](design_history/logistics_production.md) |
| §0 (vehicles), §2, §2b, §2f, §2k, §11 (haulers) | Vehicles & Drones | [`design_history/vehicles_drones.md`](design_history/vehicles_drones.md) |
| §0, §0a, §1d, §8, §9, §10b, §12 | Dev Tooling, Profiling & Headless | [`design_history/dev_tooling_headless.md`](design_history/dev_tooling_headless.md) |
| §7, §11 | Control Room Panels & Autoplay | [`design_history/panels_autoplay.md`](design_history/panels_autoplay.md) |

Find an entry: `python devtools/docs_section.py <id>`. New entries go into the matching topic file above, under a heading that starts with its § id.
