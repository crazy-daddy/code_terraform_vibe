# Code: Terraform — AI Agent Quick Reference Cheat Sheet

Dense ref: physics, formulas, component specs, bus channels, data conventions.
**Single source of truth for tunable numbers and definitions** for every agent on project — this hub plus the topic files in [`cheatsheet/`](cheatsheet/). Change tunable constant in code (safety margins, tiers, thresholds, stale-tick counts, budgets, etc.) → update the section that documents it, same change. Other docs (`CODE_GUIDES.md`, `CLAUDE.md`, `TODO.md`) point at constant/module name, not restate value — one place to keep current.

**Current state only.** Describe what the code does now — no "previously", "was changed", "bug fixed on …", "found live" narration. *Why* behind design (postmortems, rejected approaches, history) → **[`DESIGN_HISTORY.md`](DESIGN_HISTORY.md)** and commit messages.

### Section index

Section numbers are stable; code comments cite them as `AI_CHEATSHEET.md §2c` etc. Find the file here, then read only that section: `grep -n "^#.*§2c" docs/cheatsheet/<file>.md` gives its line, and the next heading ends it. Topic files are large; never read one whole.

| § | Topic | File |
| :--- | :--- | :--- |
| 0 | `lib/` module map, interpreter limits (stdlib, parser, remote writes, breaker, import depth) | [`cheatsheet/lib_map.md`](cheatsheet/lib_map.md) |
| 0a, 0b | `TreeConsole` logging, `swallowed()` | [`cheatsheet/logging_errors.md`](cheatsheet/logging_errors.md) |
| 1 | Terraforming formula table | [`cheatsheet/reference.md`](cheatsheet/reference.md) |
| 1a, 1a-0, 1a-1 | Power phases and load-shedding (solar night guard, combined-reserve guard), grid ownership | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| — | Solar day curve, panel output formula, panel/battery sizing for a night | [`gameknowledge/solar.md`](gameknowledge/solar.md) |
| — | Battery Charger, Pioneer battery swap, remote swap via Inventory `install`/`uninstall` (not used) | [`gameknowledge/pioneer_instantcharge.md`](gameknowledge/pioneer_instantcharge.md) |
| 1b, 1c, 1c-1, 1c-2, 1c-3, 1c-4, 1c-5 | Steam loop, fluid routing, Fluid Pump, Oil Generator, Steam Condenser, Mk III terraforming fluid feed, Mk IV rod magazine, Reactor heat control, game fluid delivery rules (same-outpost / script source / declared pairs) | [`cheatsheet/power_fluids.md`](cheatsheet/power_fluids.md) |
| 1d, 1d-1, 1d-2, 1d-3 | Tick-cost profiling, script cost model (cost scales with running-script count), script parking, machine activity (retire candidates) | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |
| 1e–1h-1 | Bio pipeline (Luminizer, backlog gate, biomes, essence/Mixer, biomass-complete retirement) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1i, 1k | Seed discovery sweep, planting (layout, Harvester, field machines, Terraformer) | [`cheatsheet/bio_seeds_planting.md`](cheatsheet/bio_seeds_planting.md) |
| 1l | Wildlife game data: revival, stages, per-species fluids, bands, Insight, traits; revival/Insight schedule (§1l-1); Wildlife automation: planner, Habitat, Feed Maker (§1l-2) | [`cheatsheet/wildlife.md`](cheatsheet/wildlife.md) |
| 1j, 1m, 1n | Field Mining Drill telemetry, Weather Station signal decoding, Fuel Assembler + Lead Cask roles | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2, 2a | Vehicle table, vehicle energy budgeting, claims, recall, navigation | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2a-0 … 2a-3, 2a-p | Supply Dock, demand cascade, multi-Fabricator/Smelter/Dock, per-site order trees, `SourceCache`, priority bands and ladders (`lib/priority.py`) | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2b, 2b-1, 2b-2 | Vehicle mining, Pioneer roles, Pioneer auto-upgrade, miner/hauler Pioneer holder/rack split | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2c, 2d | Storage management, outpost mining (active ores, reach) | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2e, 2f, 2g | Stationed mining, hauler role (floating pull hauler), remote Bio Lab reagent resupply | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2h, 2j, 2j-1, 2k, 2k-2, 2k-4 | Drones (energy, home, claims, depot, service), drone hauler, aftermath collector, fleet upgrade, fleet commissioning, fleet decommissioning | [`cheatsheet/vehicles_drones.md`](cheatsheet/vehicles_drones.md) |
| 2i, 2i-1, 2k-1, 2k-3, 2k-4, 2k-5 | Pull logistics + reverse hauler, factory outpost site supply requests + stranded ore/goods eviction, Storage Bins/Warehouse → Warehouse/Large Warehouse, Liquid Tank → Large Liquid Tank, Fabricator/Smelter/Oil Pump tier packs, storage outpost expansion | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 2l, 2m | Cash manager (budget owner for every Shop purchase: floor, priority, savings goal, income/ETA), early build order 70k–150k TP (`early_buyer.py`) | [`cheatsheet/production_logistics.md`](cheatsheet/production_logistics.md) |
| 3, 5, 6 | Biome colors, hardware catalog, invocation pattern | [`cheatsheet/reference.md`](cheatsheet/reference.md) |
| 4 | Signal Bus channels, Data Archive keys | [`cheatsheet/archive_ipc.md`](cheatsheet/archive_ipc.md) |
| 7 | Control Room panels | [`cheatsheet/panels.md`](cheatsheet/panels.md) |
| 8, 8a, 8b, 9, 10, 10b, 10c | Live debugging, sim fast-forward via Chromium DevTools, reading live state/logs/decompiled logic, tiered `scripts/` + `scripts_sync.py`, offline stub tests (`tests/`), headless simworker runs (`devtools/simulation/headless/`), checklist after a game update | [`cheatsheet/dev_workflow.md`](cheatsheet/dev_workflow.md) |
| 11–11m | Autoplay infrastructure planner (`autoplay/`): map tile geometry, footprints, router, utility-layer occupancy, power pass, blueprint queue, power-line ledger, fluid pass, outpost roles, extractor pass and urgency tiers (plan-ahead chunks), outpost needs, site scoring and proposals with marker approval (founding planner), building executor and pass, game phase and research thresholds | [`cheatsheet/autoplay.md`](cheatsheet/autoplay.md) |

## 🗺️ Progression Walkthroughs & Speedrun Guides

High-level workflows, progression roadmaps, automation orchestration → dedicated walkthrough guides:

- **[`manual_walkthrough.md`](autoplay/manual_walkthrough.md)**: **Manual Progression Roadmap (0 $\rightarrow$ 1,000,000 TP Victory)**
  - Manual progression playbook: First Contact onboarding, Earth Clearance contract solvers (+3,750 cr & +22,500 cr), research prereqs, critical bottleneck matrix, chronological phases from Phase 0 (Cold Boot) to Phase 7 (Deep Biome, Nuclear Reactor Recovery & Endgame Victory).
- **[`auto_walkthrough.md`](autoplay/auto_walkthrough.md)**: **Autonomous Architecture & Early Speedrunner (0 $\rightarrow$ 150,000 TP)**
  - Hands-off automation blueprint: Master Automation Architecture, revised 25-slot Nocturna Base speedrun, `solar_1.py` master building-buyer (auto buy/deploy/sell cycles), early-game speedrunner daemon & machine watcher (`devtools/early_game.py`, run via `scripts_sync.py watch --early`), Earth Clearance contract solvers, 150k TP mid-game migration protocol to `lib/`.
