# Inspiration TODO: Ideas to Pick and Choose

This is a separate idea backlog based on the current roadmap in [TODO.md](TODO.md) and the `graviaDaemon` reference implementation in [inspirations/graviadaemon](inspirations/graviadaemon). Nothing here is assumed to be required. Select items when they fit the current save, unlocked research, and desired automation style.

The inspiration repository is a reference for patterns, not a drop-in replacement. Keep our existing game-specific behavior, demand planner, recovery policy, and spiral survey unless an item below explicitly improves them.

Ideas marked with an X here are **not** yet implemented; the X means "Copy/Adapt this into the main TODO"

Checked-off items, and reviews found not actionable, live in [TODO_inspirations_done.md](TODO_inspirations_done.md).

## Viability Review Against Local Docs

Reviewed against the local component and guide documentation on 2026-09-13. The inspiration ideas are generally viable as patterns, but several need to respect this save's exact API boundaries.

- **Viable now:** capability probing, JSON-safe Data Archive state, stale-aware Signal Bus broadcasts, read-only telemetry panels, sampled trend charts, and generic construction-queue prioritization.
- **Viable with an authority layer:** interactive panel controls. The docs provide `button`, `switch`, `slider`, and `toggle` widgets, but a panel has `panel` rather than machine `self`; commands must go through Signal Bus queues or documented shared authorities. Panels should not directly call vehicle movement, recipe selection, or mining actions.
- **Viable with save-specific discovery:** outpost/store discovery, nearest charging station routing, expansion candidates, and map markers. Do not copy the inspiration repository's ids, coordinates, research gates, or assumptions.
- **Needs bounded persistence:** trend history, mission ledgers, reservations, and unresolved contacts must stay within Data Archive value limits. Prefer compact summaries and fixed-size histories over unbounded append-only records.
- **Not automatically portable:** the inspiration repository's helper modules and panel readout APIs. Reimplement against this save's existing component APIs before marking those items complete.

## Exploration and Outposts

- [ ] Split Pioneer responsibilities into two explicit modes:
  - [O] Constructor Pioneer: consume the shared construction queue and build approved jobs. # O = Maybe; see below
  - References: [inspirations/graviadaemon/pioneer_1.py](inspirations/graviadaemon/pioneer_1.py), [inspirations/graviadaemon/pioneer_2.py](inspirations/graviadaemon/pioneer_2.py), [inspirations/graviadaemon/lib/scout.py](inspirations/graviadaemon/lib/scout.py)

## Pioneer Construction Queue

- [ ] Replace the current single-purpose construction loop with a generic queue worker:
  - Reference: [inspirations/graviadaemon/lib/pioneer.py](inspirations/graviadaemon/lib/pioneer.py)

## Rover and Vehicle Safety

- [ ] Add a fleet manager that limits simultaneous long missions based on available charging bays and grid budget.
  - Reference: [inspirations/graviadaemon/lib/fleet.py](inspirations/graviadaemon/lib/fleet.py)

## Biology and Logistics

- [ ] Add Bio machine heartbeats and status broadcasts:
  - [ ] Collector target and collection result.
  - [ ] Lab specimen stage and reagent shortfall.
  - [ ] Exchange active order and delivery throughput.
- [ ] Add freshness-aware demand fallback so a stopped Exchange does not leave stale `bio.wanted` demand active forever.
- [ ] Add reusable port/storage routing helpers for Bio Lab, Smelter, Fabricator, and Supply Dock.
  - Reference: [inspirations/graviadaemon/lib/ports.py](inspirations/graviadaemon/lib/ports.py)
- [ ] Add Supply Dock source explanations:
  - [ ] Already in Inventory.
  - [ ] Can be made from unlocked recipes.
  - [ ] Requires an unsurveyed node.
  - [ ] Requires unavailable research.
  - [ ] Blocked by storage or transport capacity.
- [ ] Add contract scoring that balances reward value against time-to-deliver, energy cost, surveyed sources, and current production capacity.
- [ ] Add a generic storage rebalance job for home bins, warehouses, and outpost stores.

## Control Room and Operator UX

- [ ] Keep panels read-only and make shared libraries the sole owners of machine actions.

### Additional Panel Inspirations

The attached panel designs suggest a useful second layer beyond read-only monitoring: a small number of intentional controls that publish operator intent while shared libraries remain the only owners of machine actions.

#### Colony Strategy

- [ ] Add a card:
  - [ ] Provide a bounded strategy selector such as `atmosphere`, `production`, `outposts`, `drones`, or `biosphere`.
  - [ ] Show the current strategic goal, the next unlock or milestone, the active bottleneck, and the recommended priority order.
  - [ ] Show the current campaign requirements that block the selected goal.
  - [ ] Persist the selected goal in the Data Archive and broadcast it as operator intent.
  - [ ] Keep the selector advisory until a controller explicitly consumes it.
#### Atmosphere Operations Control

- [ ] Add a card: # good idea - merge with cards mentioned above
  - [ ] Add `auto_power` and `auto_hardware` toggles that publish requests to the Terraforming supervisor.  # auto_hardware means auto buy stuff from shop?
  - [ ] Show current outpost/subnet headroom and the next planned upgrade.
  - [ ] Require the power/terraforming library to validate every requested action before applying it.
#### Vehicle Operations Control

- [ ] Add a card:
  - [ ] Choose Pioneer mission policy: `auto`, `scout`, `constructor`, `nearest_outpost`, or `hold`.
  - [ ] Toggle directional exploration, water scouting, explorer fit, and rescue-dependent range policy.
  - [ ] Add commands for `resume`, `clear survey retries`, and `refresh outpost sites`.
  - [ ] Display every ground vehicle's current mission, battery, rescue state, and reason for its target.
  - [ ] Route commands through a queue with acknowledgements; panels must not call vehicle actions directly.
#### Production Operations Control

- [ ] Add a card:
  - [ ] Show `AUTO` versus manual-priority mode and the currently selected high-priority target.
  - [ ] Let the operator choose an unlocked recipe or output target from a bounded list.
  - [ ] Show the dependency chain, for example `raw ore -> ingot -> fabricator component -> Earth order`.
  - [ ] Add `apply high priority` and `auto` commands that take effect at the next safe recipe change.
  - [ ] Refuse locked recipes, unavailable raw sources, and changes while incompatible input is buffered.
  - [ ] Show storage readiness, input/output buffers, duty cycle, and the reason production is idle.
#### Expansion Candidates

- [ ] Add a region to the Vehicle or Strategy card:
  - [ ] Rank candidate outposts by newly reachable site kinds, resource density, distance, power potential, and current demand.
  - [ ] Show the top candidates with coordinates, site count, new resource types, and construction feasibility.
  - [ ] Let the operator accept, reject, or defer a candidate without silently founding it.
#### Power History

- [ ] Add a dedicated card:
  - [ ] Plot hourly or tick-sampled stored Wh, generation, demand, and net power.
  - [ ] Shade forecast night, conserve, and critical intervals differently.
  - [ ] Mark load-shed and recovery events on the timeline.
  - [ ] Display current stored/capacity values and time until dawn over the chart.
  - [ ] Keep chart history in a panel-local ring buffer or Data Archive series, sampled at a fixed interval rather than every repaint.
- [ ] Standardize panel interaction and visual language:
  - [ ] Use status dots for healthy/warning/error states and meters for battery, completion, and storage.
  - [ ] Use compact controls with explicit current values and a visible acknowledgement/result state.
  - [ ] Show stale publisher data as `stale`, never as a current command or mission.
  - [ ] Keep read-only telemetry separate from operator commands in both the UI and Signal Bus channels.
  - [ ] Add overflow counts when a card cannot show every vehicle, alert, machine, or order.
- [ ] Add command ownership and safety rules:
  - [ ] One controller owns each concern: Terraforming owns power/hardware, Production owns recipes, Fleet owns vehicle missions.
  - [ ] Panels publish intent only; controllers validate research, capacity, energy, and current state.
  - [ ] Persist the last command, issuer, tick, result status, and rejection reason.
  - [ ] Add a clear `manual override active` indicator and an expiry/return-to-auto policy.

References for these patterns:

- Baseline read-only cards: `panel_2.py` through `panel_6.py` in [inspirations/graviadaemon](inspirations/graviadaemon)
- Strategy and operator controls: attached Control Room concepts; adapt to this save's panel command API
- Power history visualization: attached `Nocturna power` concept; sample history at a stable game-time interval

## Developer Workflow Tooling (Outside Game Scripts, Reviewed 2026-09-16)

Two more community repos were reviewed for the first time this pass: `cyber-f0x` and `vakermit`. Both are much smaller than `graviadaemon`; most of their in-game automation (solar, o2gen, heater, bio_lab, harvester, relay-hack, etc.) is a simpler version of patterns already implemented here, so no new game-automation ideas were found in the files sampled. One item stood out as worth flagging, but it lives outside the `lib/`-architecture rules in `CLAUDE.md` entirely — it is a local dev tool that runs beside the game, not a script that runs inside it.

- [ ] Consider a save-directory sync watcher for our own workflow (external tool, NOT a `lib/` module or in-game script):
  - Watches `%APPDATA%/io.codeterraform.game/save_*_scripts/` for empty script slots the game creates and fills them from a version-controlled `scripts/` tree by matching base name (ignoring a trailing `_<number>`), rewriting only the script's own numbered id to match the slot.
  - A `xyz` marker on a file's first line force-fills it (even non-empty); a `zyx` marker pulls a game-tuned file back into the repo tree instead, backing up whatever it replaces.
  - Supports named variants of a script (e.g. an `early`/`mid` tier of `bio_lab_1.py`) picked via marker, a per-directory `.current` file, or a `--variant` flag.
  - This workspace *is* the save's script directory already, so the closest fit would be a separate sibling tool/repo that treats our root `*_<n>.py` entrypoints as the sync source — not something to build inside this repo, and not a priority; only worth doing if manually re-pasting thin entrypoint scripts into new slots becomes a real recurring cost.
  - Reference: [inspirations/vakermit/bin/ct_sync.py](inspirations/vakermit/bin/ct_sync.py), [inspirations/vakermit/bin/README.md](inspirations/vakermit/bin/README.md)
- Reviewed and found not actionable:
  - [inspirations/cyber-f0x/README.md](inspirations/cyber-f0x/README.md) — personal repo blurb, no patterns.
  - [inspirations/cyber-f0x/libraries/coordinate_handling.py](inspirations/cyber-f0x/libraries/coordinate_handling.py) — a bare `Coord(row, col)` class (`toString()` only); far less capable than what our own `lib/` coordinate handling already does, nothing to adopt.
  - [inspirations/vakermit/README.md](inspirations/vakermit/README.md) — repo overview; describes the `ct_sync.py`/`build_docs.py` tooling covered above, no game-automation content itself.
  - [inspirations/vakermit/scripts/power/power.py](inspirations/vakermit/scripts/power/power.py) — a one-line `activate_power()` entrypoint; same thin-entrypoint-calls-shared-lib pattern we already follow, nothing new.

## Contract Puzzle Solvers (Future Reference, Reviewed 2026-09-16)

`vakermit/scripts/contract/` has algorithm solutions for several Earth contract puzzle types we have not yet encountered in this save (our own completed set per [TODO.md](TODO.md) is `relay_hack`, `xenogenetics`, `corrupted_archive`, `sealed_vault`, `terminal_breach`, `data_tablet`). These are pure self-contained algorithms with no shared-library dependency, so nothing to adopt into `lib/` now — logged only so that if/when one of these contract types appears in our own save, we have a starting algorithm to adapt (never copy verbatim without confirming the exact rules/format match, since contract wording can vary run to run):

- [ ] `buried_five` — message wrapped N times, each layer expanding every token into 5; `analyzer.read()` collapses one aligned group of 5 back to its source token, peeled layer by layer left-to-right. Reference: [inspirations/vakermit/scripts/contract/buried_five.py](inspirations/vakermit/scripts/contract/buried_five.py)
- [ ] `cold_boot` — an Intcode-style bytecode VM (opcode in low two digits, parameter modes above; add/mul/out/jump-if-true/jump-if-false/less-than/equals/halt), decoding numeric outputs as letters (`1 = A`). Reference: [inspirations/vakermit/scripts/contract/cold_boot.py](inspirations/vakermit/scripts/contract/cold_boot.py)
- [ ] `core_sample` — ten damaged byte-record cores with `None` holes; constraint propagation (mutual partner links, `kind + partner.kind = 5`, `sum = (kind+load+partner) mod 256`, and a lock byte that is the XOR of every record's sum) fixed-pointed until no field changes, then submitted per-core. Reference: [inspirations/vakermit/scripts/contract/core_sample.py](inspirations/vakermit/scripts/contract/core_sample.py)
- Skipped by operator decision (2026-09-16): `beat_the_system`, `crosstalk`, `drifting_signal`, `lattice`, `the_loom`, `three_echoes` in the same directory. These are one-off contract puzzle scripts for contract types we already solve with our own (less elegant but working) code — not worth the review time. Do not re-queue these for future batches.

## discord-ideas: Community Contract Solver + Logging Service (Reviewed 2026-09-18)

Two files shared over Discord and added to [inspirations/discord-ideas/](inspirations/discord-ideas) — unattributed source, not a pinned submodule, so treat it like the standalone `inspirations/classes.txt` reference (pattern only, re-verify against our own save before trusting). `contract_solver.py` is a single dispatcher (`identify_contract()` + `run()`) covering 12 contract puzzle types by duck-typed field probing, instead of our own one-script-per-contract-type layout and vakermit's one-file-per-puzzle set (logged above). `terraform_logging.py` is a generic flat-format logging shim.

**Blocking bug — do not run `contract_solver.py` as-is:** its `run()` references a bare `SCRIPT_VERSION` name that is never defined anywhere in the file (only `terraform_logging.py` defines it) and it has no `import terraform_logging` / `from terraform_logging import SCRIPT_VERSION` at all. Calling `run(contract)` standalone raises `NameError` on the very first line, before any solver logic executes.

Algorithm review against `docs/contracts/*` (verified field-by-field, not just skimmed):

- [ ] Relay Hack: solves all 6 tumblers in one sweep — test the same candidate value across every still-unresolved tumbler each round, keep only the positions `lock.intercept()` still reports false — instead of our own `relay_hack.py`'s one-tumbler-at-a-time scan. `docs/contracts/relay_hack.md` confirms `.intercept()` returns one independent bool per tumbler, so the parallel sweep is valid and needs ≤100 calls total instead of up to 600. Worth adapting into our own script if `relay_hack` reappears. Reference: `solve_relay_hack()`.
- [ ] Sealed Vault: DFS explores all four directions (`north/south/east/west`) with backtracking; our own `sealed_vault.py` only tries `south/east/north` — `west` is missing from its `moves` list, so a maze that requires a westward step is unsolvable by our current script. Worth backporting the missing direction. Reference: `solve_sealed_vault()`.
- [ ] Shifting Slabs (this is the `drifting_signal` contract id — confirmed via `docs/contracts/drifting_signal.md`'s `.device.slabs`): scores all 26 Caesar shifts by common-word frequency and transmits only the single best-scoring candidate, versus our root `drifting_signal.py`, which blindly transmits all 27 shift attempts in a row. The scored single-shot approach is the better pattern (no 26 wrong `transmitter.transmit()` calls). Worth adapting. Reference: `solve_shifting_slabs()`.
- [ ] The Loom: reconstructs the two 21-char threads via a specific increasing-chunk-size interleave, then defensively verifies its own guess with `loom.weave(thread_a, thread_b) == record` before scoring which thread reads as English — a good defensive pattern (fails loud instead of transmitting a wrong guess) worth keeping in mind if `the_loom` shows up. The weave rule itself isn't documented in `docs/contracts/the_loom.md` beyond "reverse the loom's rule," so this exact chunking pattern is this author's own reverse-engineering — re-verify against our own `record`/`loom.weave()` before trusting it (the built-in check will at least catch a mismatch rather than transmit garbage). Reference: `solve_loom()`.
- [ ] Corrupted Archive: hardcodes `if len(pairs) != 50: raise`; our own `corrupted_archive.py` doesn't hardcode the pair count. `docs/contracts/corrupted_archive.md` doesn't state 50 is fixed across all archive sizes — if adapting this, derive the expected count from `archive.rows * archive.cols // 2` instead of the literal `50`, per this repo's save-agnostic design rule (CLAUDE.md #1). Reference: `solve_corrupted_archive()`.
- Buried Five, Crosstalk, Xenogenetics, Data Tablet, Cold Boot, Three Echoes (misspelled `three_echos` internally — harmless, since `contract.id` is what actually gets transmitted, not the detected label) all check out against `docs/contracts/*` and are functionally equivalent to, or a minor simplification of, our own existing scripts. Nothing new to adopt from these five.
- Not handled by this dispatcher at all: `beat_the_system`, `core_sample`, `lattice` — falls through to its own `raise ValueError("Unsupported contract API...")`, a safe failure mode, just incomplete coverage next to vakermit's set (logged above) for those three types.

`terraform_logging.py` — do not adopt as our logging pattern, but two ideas are worth salvaging:

- CLAUDE.md's Development Workflow rule 6 requires the shared `lib/tree_console.py` `TreeConsole` helper for structured console logging (tree-indented start/end blocks, `.debug()` for the reasoning trail) rather than ad hoc `console.print()` wrappers. `terraform_logging.py` is a second, incompatible logging framework (flat `[LEVEL][actor][category] message` lines, no block nesting) — adopting it wholesale would fork our logging convention in two directions, so it is **not recommended for adoption as-is**.
- Its `CATEGORY_LEVELS` example (`"fleet"`, `"fleet.resource_transfer"`, `"fleet.resources"`) doesn't match any category/channel name actually used in our `lib/` (grepped, no hits) — generic scaffolding from wherever this was authored, not tailored to this repo; it would need renaming to our real module names before use regardless.
- [ ] Two ideas worth folding into `TreeConsole` if repeated per-tick log spam ever becomes a problem: `rate_limited()`/`heartbeat()` (suppress a recurring debug/log line unless N seconds have passed since it last fired) and `log_once()` (fire a line at most once per script run, keyed by an arbitrary string) — `TreeConsole` has no throttling today. A small `TreeConsole.heartbeat(key, msg, seconds=...)` addition would cover this; not a priority now.
- Its docstring claims console timestamps use "the developer-recommended `console.now()` prefix format" — no such recommendation exists anywhere in `docs/` (checked `docs/components/console.md` and `docs/AI_CHEATSHEET.md`); `console.print(..., timestamp=True)` (what `TreeConsole` already uses) achieves the same result without manually prepending `console.now()`. Not a functional bug, just an unsupported claim in the comment — don't repeat it as justification elsewhere.

## Oxygen Generator: Overshoot-Penalty Gap Found (Reviewed 2026-09-16)

`vakermit/scripts/atmos/o2gen_1.py`'s header documents a real failure mode that our own `OxygenController.step()` ([lib/terraforming.py:108-118](lib/terraforming.py)) has not addressed: waste rises with intake, so on a rich atmosphere a single tick's `co2/10` intake can carry waste from just under the clean-dump window (50) straight past its top (60) in one step — the dump that follows is penalized, and "the penalty lingers until the NEXT dump, so it is not a one-off cost: it taxes the whole cycle that follows." Our current code sets full-rate intake unconditionally and only checks `current_waste >= 50` to trigger a dump — it has no notion of trimming intake to land inside the window, so on any CO2 level rich enough for one tick's waste production to exceed the ~10-unit window width, every single dump cycle would be a dirty one.

- [ ] Add overshoot-aware intake trimming to `OxygenController`:
  - [ ] Learn waste-produced-per-unit-intake (`wpi`) as an exponential moving average from consecutive `waste()` deltas (skip ticks where waste did not move).
  - [ ] Let the first overshoot go through and price the real penalty-per-unit-over-window (`ppu`) from `dump_waste()`'s `.penalty` result, rather than assuming a cost.
  - [ ] Before setting intake, check whether a full-rate tick would carry current waste past the dump window's top; if so, compare the cost of trimming intake this tick (lost production) against `ppu * (projected overshoot)` averaged over the cycle, and only trim when trimming is cheaper.
  - [ ] Keep it self-adapting per-machine/per-CO2-regime rather than a fixed threshold, since the answer depends on the (undocumented) penalty severity, which can only be learned empirically.
  - Reference: [inspirations/vakermit/scripts/atmos/o2gen_1.py](inspirations/vakermit/scripts/atmos/o2gen_1.py) (`trim_to()`, `wpi`/`ppu` learning)

## Harvester: Heat-Priced Routing (Reviewed 2026-09-16, Worth Evaluating)

`vakermit/scripts/harvesting/harvester_1.py` takes a different strategy from our `HarvestingMixin` ([lib/harvesting.py](lib/harvesting.py)): rather than BFS-shortest-pathing to a target and reactively pausing to cool once heat crosses `HEAT_SAFE_CEILING`, it prices each candidate hop by its heat cost (a hop onto an item sector costs 1 heat, an empty sector costs 7 — measured from the machine's own heat rules) and greedily prefers routes that thread through item cells, since "on a scattered map the hours spent cooling outnumber the hours spent moving about 3 to 1." It also selects the next target by value-per-Manhattan-step rather than nearest-first, and experimented with (then measured against and disabled) a "leave junction cells standing as cheap road" heuristic — worth reading as a documented negative result, not just the positive pattern.

- [ ] Consider whether `find_path`/target selection in `lib/harvesting.py` could reduce total cooldown time by preferring hops that land on item sectors (1 heat) over empty ones (7 heat) when a route has a choice of equally-short paths, and by ranking candidate targets on value-per-distance instead of pure distance — a proactive heat budget instead of the current reactive pause-at-ceiling/resume-at-floor policy. Only pursue if `docs/components/harvester.md` confirms the same 1/7/9 heat-per-action figures this reference used (these may be specific to that reference's own measurements, not necessarily an official constant), and only if real playtesting shows meaningful idle-cooldown time on our own map density.
  - Reference: [inspirations/vakermit/scripts/harvesting/harvester_1.py](inspirations/vakermit/scripts/harvesting/harvester_1.py) (`is_bridge()`, `choose()`, `go()`)

## Biology: Signal-Bus Job-Queue Economics (Reviewed 2026-09-16)

`vakermit/scripts/bio/mid/*.py` implements a materially more advanced 3-machine biology pipeline than its own `early/` tier (which is close to our current design): the Exchange becomes an explicit planner publishing `bio.plan` (active order + net remaining) and `bio.jobs` (one queued collection job per still-needed sample, consumed exactly once so multiple Collectors across outposts split the work without double-collecting), while the Lab publishes `bio.prices` (real reagent cost per fragment, learned from `analyze()` and persisted to the Data Archive) so the Exchange can rank orders by **actual margin** (reward minus reagent cost) instead of a rarity proxy — falling back to the rarity-weighted proxy only for not-yet-analyzed fragments, and switching a `scout` flag to bias the Collector toward pricing unknowns when an order's margin is still an estimate. It also gates order selection on `serviceable_biomes()` (only bid on an order whose biome has a *powered* Bio Collector at some outpost) and degrades cleanly to the early-tier's read-the-Exchange's-active-order-directly behavior when the Signal Bus is absent.

This lines up with several already-open items in Biology and Logistics above (bio heartbeats, freshness-aware demand fallback, contract scoring) and adds one further idea:
- [ ] Consider a `bio.prices` channel — reagent cost per fragment learned from `analyze()`, persisted in `archive`/Data Archive and broadcast — so a Bio Exchange can score competing Bio Orders by real margin (reward minus reagent cost) rather than the current implicit "first incomplete order" or a rarity-only proxy. Use the learned price only once known; fall back to a rarity-weighted estimate (average learned cost per rarity point) for anything not yet analyzed, and bias collection toward unpriced fragments while an order's margin is still an estimate.
- [ ] Consider gating Bio Order selection on biome coverage: only activate an order whose required fragment's biome has an actual powered Bio Collector, discovered via `outpost_network` rather than assumed.
  - Reference: [inspirations/vakermit/scripts/bio/mid/bio_exchange_1.py](inspirations/vakermit/scripts/bio/mid/bio_exchange_1.py), [inspirations/vakermit/scripts/bio/mid/bio_lab_1.py](inspirations/vakermit/scripts/bio/mid/bio_lab_1.py), [inspirations/vakermit/scripts/bio/mid/bio_collector_1.py](inspirations/vakermit/scripts/bio/mid/bio_collector_1.py)
- `vakermit/scripts/bio/early/*.py` reviewed too: close to our current bio pipeline's shape (Collector reads the Exchange's active order directly, no persisted pricing) — nothing further to adopt from that tier specifically.

## vakermit Controller, Pioneer & Storage Update (Reviewed 2026-09-28)

Covers vakermit commits `2ffa380..aa5568f` (two submodule bumps; the first, up to `9a5319d`, was never reviewed when it landed). vakermit extracted shared `scripts/lib/` modules, added a central Control Room controller, a Pioneer script with scout/build roles, a Supply Dock script, and Storage Bin routing. Most of it is already covered here; three ideas are kept: survey clustering (merged into TODO.md), outpost siting, and Storage Bin support.

- [ ] **Outpost siting by cluster value (autoplay goal).** The same clustering at pipe-range radius (150 m) groups surveyed sites into candidate outposts. Each cluster is scored by site kind (water/thermal 4, exotic 3, oil 2, mineral 1 + purity bonus, inert 0), +6 for a new biome or −4 for the home biome, minus distance/200. Clusters past 1200 m score 0. Autoplay needs automatic outposts, so this is a starting point for the building planner's site-selection step and for the unchecked **Expansion Candidates** card above. Our `pioneer_scout.py` surveys sites but does not rank outpost locations yet. Founding stays under the CLAUDE.md outpost rule until the planner ships.
  - Reference: [inspirations/vakermit/scripts/lib/scout.py](inspirations/vakermit/scripts/lib/scout.py) (`score_outpost()`, `best_outposts()`)
- [ ] **Storage Bin support in `lib/storage.py` (low priority, easy).** Early game the building-slot limit binds before Inventory size does, so bins have not been worth a slot so far. A bin behaves like a one-slot Warehouse: the first deposit latches its material, and the lock clears once it drains empty (`docs/components/storage_bin.md`). Adding it means `"storage_bin"` in `discover_storage_buildings()`'s `type_ids`, plus bin-shaped reads (`get_material()`, `count()`, `is_empty()`). vakermit's routing order: push to a bin latched to the item with space, then an empty bin, then Inventory. Pull from Inventory first, then any bin holding the item.
  - Reference: [inspirations/vakermit/scripts/lib/store.py](inspirations/vakermit/scripts/lib/store.py) (`sink_for()`, `source_for()`, `push()`)

Not actionable (already matched or exceeded):
- `lib/control.py` + `control_room/controller.py`: controller broadcasts `control.policy` (normal/conserve/emergency mode, per-subsystem allow flags, ore priority, per-vehicle role), and machines hold their own discretionary work. Policy is ignored after 6 world-clock hours, so a crashed controller cannot hold the base in conserve forever. A combo box gives a manual mode override. Our `PowerGridManager` tiered shedding + power-mode channels + mission gate cover this. The world-clock staleness rule is the same as our existing age/stale check convention.
- `lib/power.py`: hysteretic start/continue gate (new work waits for 60%, running work continues down to 25%) and one long sleep to dawn when draining at night. We already have hysteresis. The dawn sleep plus hours-to-empty (`stored / -net` from `power_control.grid()`) is noted for the **Power History** card, which already plans a time-until-dawn readout.
- `lib/demand.py`: rebuilds ore demand from `factory.needs` through the Smelter's recipes when `factory.ore` is silent; capped demand weight (0.35 for unwanted ore, never excluded). Our `lib/production.py` dependency graph computes demand directly and does not depend on a running Smelter.
- `factory/supply_dock_1.py`: reward × fillable-fraction scoring, weekly finishability from `dispatch_rate()` × hours left, eject leftovers before `set_order()`. Our `lib/supply_dock.py` already does all three, across multiple docks.
- `rover/pioneer_1.py` build phase (paused jobs first, then pending jobs whose kit is in stock) and role fallback when a module is missing. Our `PioneerController` construction loop does more: claims, per-trip progress budgeting, recharge-and-resume.
- `control_room/fleet_card.py` (physical status vs script intent per vehicle) and `factory_card.py`: the same shape as our fleet intent line and production panels.
- `lib/{machines,signals,util,bio}.py` and the `bio/`, `fabricator_1.py`, `smelter_1.py`, `rover_1.py`, `harvester_1.py` diffs: helpers moved out of scripts into libraries, plus `wait_for_policy()` gates. No behaviour worth adopting beyond the storage routing above.
- `bin/ct_sync.py` lib mirroring: repo-to-save mirror that will not overwrite a save copy edited in game; new libs still need a manual in-game import. Our `devtools/scripts_sync.py` already registers new libs via `create-library`.
- `rover/pioneer_explorer.py` survey census (per-biome open contacts vs one-way range, sonar-tier refusals counted separately): covered. Blocked contacts get map markers, and `survey_known_pois()` already logs each accepted or rejected candidate with its Wh budget at debug level.
- `tools/build_docs.py` diff: skipped (tools code, operator decision 2026-09-16).

## vakermit Pioneer Range & Conserve Fixes (Reviewed 2026-09-29)

Covers vakermit commits `aa5568f..b1887c9` (three commits, `scripts/rover/pioneer_1.py` and a docstring in `scripts/lib/control.py`). All three fix one symptom: an assigned builder kept loading an outpost kit, leaving, turning back, and unloading it. Nothing new to adopt.

Not actionable (already matched or exceeded):
- Long-run throttle (`cruise_for()`: 0.35 beyond 250 m, 0.6 otherwise). Our `select_cruise_throttle()`/`max_safe_throttle_for_leg()` in `lib/vehicle_energy.py` already pick the throttle per leg from the power/speed model. vakermit's comment claims a fixed draw makes very low throttle cost more per meter. That claim is not measured, and `docs/` documents no fixed travel draw. Our model (Wh/m rises with throttle) has no such term, so there is nothing to change unless in-game data shows it.
- Persisted Wh/m (`fleet.cost.<id>` on the Signal Bus, recalled at startup). vakermit needed it because its EMA restarted from an optimistic guess. Our budget comes from the analytic model, so a restart cannot reset it to an optimistic value.
- Keep the kit aboard on an aborted run (`needed_kits()`). Our `PioneerController.run_construction_loop()` already unloads only when the cargo holds none of the job's `required_item`.
- Log why a planned build is skipped. Our loop already warns when a kit cannot be loaded and defers the job through `failed_jobs`.
- Assigned build/scout role works through conserve, not emergency. Our `PowerGridManager` sheds buildings only and does not gate vehicle construction, so a builder is never held back by conserve mode.

## Jasmine Control Room Panel Mockups (Reviewed 2026-09-18)

`inspirations/discord-panels/jasmine/` (screenshots `2.png`–`9.png`, `10.png`==`2.png` and `image.png`==`9.png` are exact duplicates) and `inspirations/discord-panels/manual_craft.png` are UI mockups of a tabbed "Colony Control Room" (OVERVIEW / STRATEGY / PRODUCTION / FLEET / OUTPOSTS / INFRA / SYSTEM), attributed to a "Control Room" platform distinct from our own panel API (its own `docs`/`Manage`/`+ New Card`/column-layout chrome is not ours — treat only the information architecture as a pattern, not the widget implementation). These are mockups/concept art, not runnable code, so nothing here is a drop-in reference file the way `graviadaemon`'s `lib/` is — reimplement against this save's own `panel_*.py` + Signal Bus conventions.

- `2.png`/`3.png`/`10.png` (STRATEGY tab) and `9.png`/`image.png` (OVERVIEW tab) confirm the already-open **Colony Strategy** card idea above almost exactly: a bounded goal selector (`BALANCED`/`DRONES`/`STEAM`/`BIOMASS`), `STATE`, `OBJECTIVE`, `BOTTLENECK`, and a breadcrumb `PATH` trace of unlock prerequisites. No new pattern beyond confirming the existing backlog item's shape.
- `4.png` (PRODUCTION tab) confirms the already-open **Production Operations Control** card: `AUTO`/high-priority mode toggle (`APPLY HIGH PRIORITY`, `RETURN TO AUTO`, `MODE: AUTO` readout), a fabricator target picker showing progress (`7/25 Drone Station Kit`) and source (`[strategic_order]`), and a `BLUEPRINT` selector. Adds one new widget idea not yet in the backlog: a **type-to-search recipe/item picker** (search box + on-screen A–Z keyboard grid) for choosing a target among many unlocked recipes/blueprints without a long dropdown.
- `manual_craft.png` (a separate "Control Room" concept, smelter/crafter cards) adds a second concrete manual-production widget shape: a **throughput slider** (0–100, e.g. "65") paired with a `CRAFT` button, and a **radio-button recipe list** (`SELECT` + selected-dot + recipe formula, e.g. "Iron Ore → Iron Ingot") with a `SELECTED:` readout and pagination (`PAGE 1/2`) for long recipe lists. Same intent-publish/controller-validates split already required by the existing card rules — the slider/craft button would publish an intent (target rate + recipe), not drive the Smelter/Fabricator directly.
  - [ ] Consider a type-to-search item/recipe picker (search box + A-Z key grid, or a paginated radio-select list) as the standard widget for "choose one item from a long unlocked list" across the Production and Strategy cards, instead of a single long dropdown.
- `5.png` (FLEET tab) confirms **Vehicle Operations Control** (Pioneer priority `AUTO`, `Explorer fit`/`Directional exploration`/`Water scout` toggles, `NEAREST OUTPOST`/`NOCTURNA`/`RESUME` recall-style buttons) and **Expansion Candidates** (ranked, numbered candidate list with coordinates, `CANDIDATE DETAIL` panel showing surveyed-site count and nearby resources, `REFRESH OUTPOST SITES`/`CLEAR SURVEY RETRIES` commands) side by side. New idea: this mockup treats **drones as a distinct fleet category** alongside ground vehicles ("4 vehicles" / "5 drones" counted and shown separately), with their own `SERVICE / RECOVERY` block ("Drone Service Station: progression target", "Recovery capability: unavailable until station deployed") — worth keeping in mind once `drone_1.py`/`drone_service_1.py` (already present as untracked scripts in this workspace) mature enough to want their own FLEET-card section separate from ground vehicles.
- `6.png` (OUTPOSTS tab) is a new pattern not yet in the backlog: a per-outpost summary row showing **building/slot capacity** (`slots 29/31`), a biome tag (`FROZEN`/`DEEP`/`GEOTHERMAL`/`COASTAL`/`VOLCANIC`), a color-coded status (red "Building capacity low: N/M" vs. green "NO IMMEDIATE ACTION"), optional per-outpost readouts (`BIO READY 16/16`), and a global `BIO POWER: ON` toggle.
  - [ ] Consider an OUTPOSTS card: one row per owned outpost showing building/storage slot capacity, biome, and a "capacity low" warning once near the slot cap — complements the existing Expansion Candidates card (which covers unfounded sites) with a view of already-founded ones.
- `7.png`/`8.png` (INFRA tab, `FLUIDS` sub-view) is a new pattern not yet in the backlog: per-tank fluid routing rows (`liquid_tank_N`, kind, status `OPERATIONAL`/`DRAINING`/`STALLED`, current contents + fill bar `70/100t`, in/out flow rate, source/destination edge e.g. "OUT 0 t/h → biomass_mixer_1"), a per-tank pair of `<biome> SOURCE`/`<biome> RECEIVE` role buttons plus `APPLY`/`RELEASE` to assign/clear that role, and pagination across many tanks. `8.png` shows the tab has sibling sub-views not yet mocked in detail: `ATMOSPHERE` and `POWER` alongside `FLUIDS`.
  - [ ] Consider an INFRA/FLUIDS card once cross-outpost liquid/gas piping exists in this save: one row per tank with status, fill level, flow direction, and source/receive role assignment — read-only telemetry first; role assignment (`APPLY`/`RELEASE`) would need the same intent-publish/controller-validates pattern as other command cards, not direct tank control from the panel.
- Cross-cutting mockup conventions worth folding into the existing "Standardize panel interaction and visual language" backlog item: color-only status coding (green/orange/red text, no icons) for OPERATIONAL/DRAINING/STALLED-style states, a `▸ TAB ◂` chevron marker for the active top-level tab, and an OVERVIEW tab that shows one shortened summary line per section (mirroring each dedicated tab's headline fact) plus a single `PRIORITY / ALERTS` rollup list and a footer hint ("SELECT A TOP TAB FOR FULL CONTROLS") pointing at the detail tabs.

## zroski Python Idioms: Dataclasses and Decorators (Reviewed 2026-10-05)

Source: [inspirations/discord-ideas/zroski.txt](inspirations/discord-ideas/zroski.txt) and [inspirations/discord-ideas/image.png](inspirations/discord-ideas/image.png). This is a set of code snippets from a different codebase (rover task queue, bio exchange orders, console helpers), not a full solution. The game supports both `dataclasses` and `functools` (`wraps`, `cache`, `lru_cache`, `partial`); see the manual's dataclasses and functools sections. We use neither yet.

- [ ] Try `@dataclass` on one in-memory record class that has a long hand-written `__init__` (plan rows, claims, haul candidates). It gives generated construction, a readable `repr` in logs, value equality for test asserts, `order=True` sorting, and `replace()`.
  - Only for objects that stay in memory. The manual says a dataclass cannot cross notebook, archive or Signal Bus boundaries: use `TypedDict` for those. Going out needs `asdict()`, and coming in needs a manual rebuild of nested fields. zroski's `serializable_dataclass` / `typed_dict` helpers (see `image.png`) exist only to work around that rebuild. Our persisted state is dict-shaped, so a conversion on every tick costs work for no gain.
  - Not supported in game: `frozen=True`, `slots=True`, `ClassVar`, `InitVar`. Annotations are not enforced.
- [ ] `functools.cache` / `lru_cache` for pure lookups, for example the cached clock in step 1 of [docs/plans/done/controller_unification.md](docs/plans/done/controller_unification.md). The cached function must not read game state that changes.

Not recommended:
- `CommandStatusWrapper` (status-to-callback map as a decorator). It fits our code poorly: about 258 `.status` branches in `scripts/` handle statuses differently per call site, and a decorator hides that control flow. zroski's version also has a mutable `{}` default, no `functools.wraps`, and discards the `ActionResult` for a bool. A plain status-group helper (`lib/results.py` style) without the decorator is the better shape.
- `Overload` (type dispatch keyed on type names): obscure, and pyright cannot follow it.
- `__init_subclass__` task registry: nothing needs a class registry. The `MachineControllerBase` plan uses class attributes, not a registry.
- `Point` multi-type constructor, duplicated travel-power formulas, `BaseMachine` loop: no gain over our vehicle energy model and controller loops.

## Engineering Quality

- [ ] Adopt a capability-first import convention for new libraries:
  - [ ] Machine scripts remain tiny entry points.
  - [ ] Libraries receive the machine object explicitly.
  - [ ] Optional components degrade cleanly.
  - [ ] No new hardcoded machine ids when discovery is available.
- [ ] Add result-status groups/helpers for common transient, capacity, research, and capability failures.
  - Reference: [inspirations/graviadaemon/lib/results.py](inspirations/graviadaemon/lib/results.py)
  - Use plain helpers (for example `is_transient(res)`), not a decorator. [inspirations/classes](inspirations/classes) and [inspirations/discord-ideas/zroski.txt](inspirations/discord-ideas/zroski.txt) show a `CommandStatusWrapper(callbacks={...})` decorator that maps statuses to callbacks. A 2026-10-05 review rejected it: our status branches differ per call site, and the decorator hides that control flow. See "zroski Python Idioms" above. The same files' `BaseMachine` loop does not fit our thin entry points calling `lib/` controllers either.
- [ ] Add once-per-session warning helpers for recurring blocked conditions.
- [ ] Add focused test doubles or offline validation for:
  - [ ] Empty/missing optional components.
  - [ ] Stale Signal Bus values.
  - [ ] Full Inventory and full output buffers.
  - [ ] Locked recipes and missing source nodes.
  - [ ] Paused construction jobs.
  - [ ] Vehicle rescue and return-to-station transitions.
- [ ] Add a documentation convention for every shared library:
  - [ ] Public entry points.
  - [ ] Required modules/research.
  - [ ] Status handling.
  - [ ] Persistence keys and bus channels.
  - [ ] Recovery behavior.
  - Reference: [inspirations/graviadaemon/docs/libraries.md](inspirations/graviadaemon/docs/libraries.md)
- [ ] Keep the inspiration submodule pinned and review upstream changes deliberately before adopting them.

## Ideas to Defer or Adapt Carefully

- [ ] Consider replacing hardcoded `rover_1`, `smelter_1`, and `supply_dock_1` lookups only after a discovery helper can preserve current behavior.
- [ ] Consider a full five-panel Control Room only after the game save has the required panel support and dashboard APIs.
- [ ] Consider splitting `lib/vehicle.py` into smaller vehicle, navigation, energy, and recovery libraries only when the current file becomes difficult to test.
- [ ] Do not copy the inspiration repository's coordinates, research assumptions, or machine ids into this save.
- [ ] Do not replace working game-specific loops solely to match the inspiration repository's naming or layout.

## Source Notes

- Inspiration repository: [inspirations/graviadaemon](inspirations/graviadaemon)
- Current roadmap: [TODO.md](TODO.md)
- Inspiration commit reviewed: `3f6118a` (`Added new changes, and documentation`)
- Primary inspiration files reviewed:
  - [README.md](inspirations/graviadaemon/README.md)
  - [lib/caps.py](inspirations/graviadaemon/lib/caps.py)
  - [lib/bus.py](inspirations/graviadaemon/lib/bus.py)
  - [lib/scout.py](inspirations/graviadaemon/lib/scout.py)
  - [lib/pioneer.py](inspirations/graviadaemon/lib/pioneer.py)
