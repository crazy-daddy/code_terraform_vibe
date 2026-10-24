# Helper sweep families: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the ranked `drift-bug` and `merge` families of the 2026-10-23 helper sweep: one helper per family, the copies call it.

**Architecture:** Every helper goes to the owner module its family verdict names (`archive.py`, `components.py`, `swallow.py`, `cash.py`, `geometry.py`, ...). Sites switch in batches, one commit per batch. Three phases, one session each, `/clear` between; each phase runs in its own worktree and merges after the operator approves.

**Tech Stack:** game Python (no CPython stdlib, see `tests/test_game_imports.py`), `unittest` stub tests (`tests/harness.py` `StubTestCase`), ruff, pyright.

**Spec:** [helpers_sweep_candidates.md](helpers_sweep_candidates.md) (families, sites, verdicts; `## Ranking` at the end) and [helpers_sweep_candidates_2.md](helpers_sweep_candidates_2.md) (part 2, marked (2) in the ranking). Each task names its family heading; the sites, owner and `Apart` list there are the task's requirements. Path key as in the spec: `L/` = `scripts/4_controlpanel/lib/`, `ap/` = `autoplay/lib/`, `s0/` = `scripts/0_cold_boot/`.

## Decisions (open questions from the sweep handoff)
- Unsupported-target collision order: the archive_cleaner order wins (legacy pioneer, then legacy rover, then shared on top), so the fleet's view matches what the cleaner persists. Legacy pioneer keys are stored under the canonical `poi_X_Y` key only.
- `research_unlocked` swallows a raised `get_component("research")` at the five sites that let it escape today (`drone_depots:85`, `drone_scout:25`, `drone_weather:132`, `pioneer_upgrade:78`, `:171`). Wanted: it reads "not unlocked", like the seven sites that already go through `component()`.
- `SURVEY_SPIRAL_KEY` owner is `L/vehicle_survey.py` (the writer). `archive_cleaner` imports it; only `control_panel/status_panel.py` imports archive_cleaner, so no cycle.
- `key_tile(key)` moves from `archive_cleaner._key_tile` to `L/unsupported_markers.py` beside `key_coords`, so the merge helper and the cleaner share one parser.
- Depot walks (Phase 3): `fleet_upgrade._advance_depot` reads right after a deploy, and the depot walk memoizes 20 ticks. If `discover_drone_depots` gets no fresh-read path without a new parameter, `_advance_depot` stays apart and only the other site merges.
- `archive.mutate` / `pop_entries` (~30 updaters) land in Phase 2, after `get_dict`, in batches by shape.

## Global Constraints
- Import rules: `scripts/<tier>` never imports `autoplay/lib`; tier 0 never imports tier 4 libs; a helper for an `ap/` site sits in a small lib (the planner chain runs under the 10,000-step cap, CODE_GUIDES "Game interpreter").
- Every recovering `except` names its site: `swallowed(where, error)` (CODE_GUIDES "Errors").
- One definition per constant (CODE_GUIDES); `tests/test_constant_owners.py` pins string-literal owners.
- Wrappers the spec says to keep (named, imported, documenting a key) keep their names and become one-line calls.
- Work in a worktree: `python devtools/agent_worktree.py new helpers-impl-<phase>`; commit on its branch; merge only after the operator approves (`agent_worktree.py merge`). No sync hold needed there.
- Checks per task: `python -m unittest discover -s tests`; `.venv/Scripts/python.exe -m ruff check <paths>` and `ruff format <paths>`; after `scripts/*/lib` edits `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview`, then `npx pyright`. All clean before each commit.
- Commits: Conventional Commits, `refactor(<scope>)` for merges, `fix(<scope>)` for the two drift-bugs; no AI attribution.
- A scan-ignored function you restructure gets its `devtools/code_scan/*_ignore.txt` entry rechecked in the same commit (CODE_GUIDES "Checks").
- Phase end: `caveman:cavecrew-reviewer` on the phase diff (model = the session's main-loop model), fix findings, update docs (Task "Phase close").

## Review Focus
1. A caller that looks up a legacy raw `X:Y` pioneer key in `get_unsupported_targets()` misses after Task 1.3: grep every reader of that map; test pins that the raw key is gone and the canonical key holds the entry.
2. `get_dict` returns the stored object, like `get`: a caller that mutates the result must copy it (`logistics_requests.pickups_snapshot` keeps `dict(...)`). Test pins identity (`is`), so nobody adds a silent copy.
3. Sites whose default is not `{}`, or that treat None differently from `{}` (spec shape S4, `pillar_swap.swap_state`, `drone_energy.default_cruise_throttle`), must not switch to `get_dict`. Task 1.4 lists them as untouched.
4. `research_unlocked` on an empty id list reads False (not `all([])` True); the two "researched OR in inventory" sites keep the inventory branch. Tests pin both.
5. `components.outposts()` turns a raised network read into `[]`: `weather_signals.discover_stations` gains a guard, `production_core._all_outposts` keeps its home fallback. Tests pin `[]` on a raise and the fallback.

---

## Phase 1 (one session): ranks 1-5

Worktree `helpers-impl-1`.

### Task 1.1: `ArchiveClient.get_dict`

**Files:**
- Modify: `scripts/4_controlpanel/lib/archive.py` (beside `get_entry`, :123)
- Create: `tests/test_archive_client.py`

**Interfaces:**
- Produces: `ArchiveClient.get_dict(key: str) -> dict` (module singleton `archive.get_dict`).

- [ ] **Step 1: Write the failing tests** (`StubTestCase`, `archive` from `archive`, writes through `self.world.notebook` or `archive.set`)
  - `test_get_dict_missing_reads_empty`: `archive.get_dict("t.k") == {}`.
  - `test_get_dict_non_dict_reads_empty`: stored `[1, 2]`, then `"x"`, then `0`: each reads `{}`.
  - `test_get_dict_returns_stored_dict`: stored `{"a": 1}`: result equals it, and two reads return the same object as `archive.get("t.k")` (`assertIs`).
  - `test_get_dict_without_notebook_reads_empty`: an `ArchiveClient()` whose `notebook` attribute is set to None after construction (the constructor falls back to `get_component("notebook")`): `{}`.
- [ ] **Step 2: Run** `python -m unittest tests.test_archive_client -v`. Expected: FAIL, `AttributeError: ... 'get_dict'`.
- [ ] **Step 3: Implement** `get_dict`: `value = self.get(key, {})`, return it if a dict, else `{}`. Docstring: missing, None or non-dict read `{}`; `get` already swallows notebook errors. Add the TYPE_CHECKING return type if the overload block style needs it.
- [ ] **Step 4: Run** the tests. Expected: PASS. Then the full checks.
- [ ] **Step 5: Commit** `refactor(archive): add get_dict for dict-valued keys`.

### Task 1.2: Survey spiral drift-bug (rank 1)

Spec family: "Survey spiral progress reads (SURVEY_SPIRAL_KEY)".

**Files:**
- Modify: `L/vehicle_survey.py` (:23 constant, :365 `update_progress`), `L/job_survey.py` (:116, :179), `L/archive_cleaner.py` (:31 constant goes, import added), `tests/test_constant_owners.py`
- Test: `tests/test_job_survey.py`

**Interfaces:**
- Consumes: `archive.get_dict(key) -> dict` (Task 1.1).
- Produces: `vehicle_survey.spiral_next_index(default: int = 0) -> int`.

- [ ] **Step 1: Write the failing tests** in `tests/test_job_survey.py` (reuse its existing setup):
  - `test_spiral_mission_non_dict_progress_starts_at_zero`: `archive.set(SURVEY_SPIRAL_KEY, [1])`; picking the spiral mission does not raise and uses start index 0.
  - `test_spiral_next_index_reads_stored_and_default`: `{"next_index": 4}` reads 4; a list reads the default (`spiral_next_index(7) == 7`).
  - `test_update_progress_replaces_non_dict`: with `[1]` stored, recording one spiral point stores a dict with that waypoint and `next_index`.
  - In `tests/test_constant_owners.py`, add `"survey.spiral": "vehicle_survey.py"` to `owners`.
- [ ] **Step 2: Run** `python -m unittest tests.test_job_survey tests.test_constant_owners -v`. Expected: FAIL (`AttributeError` on the list; owner test finds the literal in archive_cleaner too).
- [ ] **Step 3: Implement**: add `spiral_next_index` in vehicle_survey (`archive.get_dict(SURVEY_SPIRAL_KEY).get("next_index", default)`); both job_survey sites call it (:179 passes `start_index`); `update_progress` starts from `dict(current) if isinstance(current, dict) else {}`; archive_cleaner drops its definition and imports `SURVEY_SPIRAL_KEY` from vehicle_survey.
- [ ] **Step 4: Run** the tests, then the full checks. Expected: PASS.
- [ ] **Step 5: Commit** `fix(survey): read spiral progress as a dict`.

### Task 1.3: Unsupported-target legacy merge drift-bug (rank 2)

Spec family: part 2 "Unsupported-target legacy merge".

**Files:**
- Modify: `L/unsupported_markers.py` (add `key_tile`, `merge_unsupported`), `L/archive_cleaner.py` (:119 `_key_tile` goes, :500 `_merge_unsupported` goes, :438-442 and :461 call the shared ones), `L/vehicle_claims.py` (:442 `get_unsupported_targets`)
- Create: `tests/test_unsupported_merge.py`

**Interfaces:**
- Consumes: `archive.get_dict` (Task 1.1).
- Produces: `unsupported_markers.key_tile(key: str) -> tuple[int, int] | None` (the cleaner's `_key_tile` body); `unsupported_markers.merge_unsupported(shared, rover, pioneer) -> tuple[dict, int]` (merged entries, count of legacy pioneer keys renamed to `poi_X_Y`; non-dict inputs ignored).

- [ ] **Step 1: Write the failing tests** (`tests/test_unsupported_merge.py`, plain `unittest` for the pure helper, `StubTestCase` for vehicle_claims):
  - `test_legacy_pioneer_key_becomes_canonical`: `merge_unsupported({}, {}, {"3:4": e})` == `({"poi_3_4": e}, 1)`; the raw `"3:4"` key is absent.
  - `test_rover_wins_over_pioneer_on_collision`: pioneer `{"3:4": p}`, rover `{"poi_3_4": r}`: entry is `r`.
  - `test_shared_wins_over_legacy`: shared `{"poi_3_4": s}` beats both.
  - `test_non_dict_inputs_ignored`: `merge_unsupported([1], None, "x") == ({}, 0)`.
  - `test_pioneer_key_without_coords_kept`: pioneer `{"a:b": e}` stays under `"a:b"`, migrated 0.
  - `test_fleet_view_matches_cleaner`: same three stores in the notebook; `get_unsupported_targets()` (on a `VehicleClaimsMixin` host as the existing vehicle tests build one) equals `merge_unsupported(...)[0]`.
- [ ] **Step 2: Run** `python -m unittest tests.test_unsupported_merge -v`. Expected: FAIL (`ImportError`).
- [ ] **Step 3: Implement**: move `_key_tile` to `unsupported_markers.key_tile`; `merge_unsupported` is the cleaner's `_merge_unsupported` body returning the migrated count instead of bumping stats. The cleaner reads its three keys with `get_dict`, calls `merge_unsupported`, adds the count to `stats["unsupported_migrated"]`. `get_unsupported_targets` reads the three keys with `get_dict` and returns `merge_unsupported(...)[0]`. Grep readers of `get_unsupported_targets()` for raw `X:Y` lookups (Review Focus 1) and switch any to the canonical key.
- [ ] **Step 4: Run** the new tests plus `tests.test_archive_cleaner_status`, then the full checks. Expected: PASS.
- [ ] **Step 5: Commit** `fix(survey): one unsupported-target merge for fleet and cleaner`.

### Task 1.4: `get_dict` site sweep (rank 3)

Spec families: "Archive dict read, non-dict to empty", "try around archive.get (double guard)", "Survey archive reads" (the three bypassers and `vehicle_claims` :342).

**Files:** the sites listed under "Sites merged" in those families. Untouched (spec `Apart`): `pillar_swap.swap_state`, `logistics_snapshot._entry`, `plant_terraformer._was_running` / `_last_batch_km2`, `construction_lots` (keeps its try), `fluid_routing.get_tank_assignments`, `production_orders.get_manual_orders`, the typed `survey_requests.read_*` readers, `archive_cleaner._reset_if_not_dict`, every S4 site (None default or None test, e.g. `drone_energy.default_cruise_throttle`).

**Interfaces:**
- Consumes: `archive.get_dict` (Task 1.1). For a class holding `self.archive`, call `self.archive.get_dict`.

Batches (one commit each; run the module's existing tests after each swap, the full checks before each commit):
- [ ] **Batch a**: the 20 def-level wrappers (spec "Sites (A, def level)") become `return archive.get_dict(KEY)`; `seed_maker._refresh_tried` assigns `self._tried = archive.get_dict(TRIED_KEY)`. Commit `refactor(archive): def-level dict readers use get_dict`.
- [ ] **Batch b**: the three try-guarded readers (`machine_activity._read_dict`, `retired_machines.retired`, `script_parking._vehicle_commands.stored`) drop their `try`. Commit `refactor(archive): drop the double guard around dict reads`.
- [ ] **Batch c**: the line-level sites (spec "Sites (B, line level)") whose default is `{}` and that test `isinstance(..., dict)` afterwards; `drone_scout.py:44` calls `survey_requests.read_unsupported()`; `unsupported_markers` :156/:261 and `vehicle_claims` :342 use `archive.get_dict(SURVEY_UNSUPPORTED_KEY)`; `logistics_requests.pickups_snapshot` keeps its copy, `dict(archive.get_dict(PICKUPS_KEY))`. Commit `refactor(archive): line-level dict reads use get_dict`.
- [ ] **Batch d**: the `ap/` wrappers (`autoplay_roles.outpost_roles`, `blueprint_queue.planned`, `building_plan.load`). Commit `refactor(autoplay): dict readers use get_dict`.
- [ ] **Step: confirm the sweep**: `grep -rn "archive.get(.*{})" scripts autoplay` lists only `Apart` sites and sites a later family owns; note any leftover in the phase handoff.

### Task 1.5: `components.research_unlocked` (rank 4)

Spec family: "Research unlock guards (`research.is_unlocked` wrappers)".

**Files:**
- Modify: `L/components.py`; the 12 sites under "Sites merged" (early_buyer, drone_depots, drone_scout, drone_weather, pioneer_upgrade x2, storage x2, site_supply, building_swap_upgrade, storage_expand, vehicle_claims :512-518)
- Create: `tests/test_components_helpers.py`

**Interfaces:**
- Produces: `components.research_unlocked(research_id: str, where: str = "components.research_unlocked") -> bool`; `components.all_research_unlocked(research_ids, where: str = "components.all_research_unlocked") -> bool` (False for an empty list).

- [ ] **Step 1: Write the failing tests** (`StubTestCase`; the world's research stub answers from `self.world.research.unlocked`):
  - `test_research_unlocked_reads_stub`: an id in `unlocked` reads True, another False.
  - `test_research_unlocked_missing_component_reads_false`: research component removed from the world: False.
  - `test_research_unlocked_raise_reads_false`: `is_unlocked` replaced by one raising `RuntimeError`: False, and the console has a `swallowed` line naming `where`.
  - `test_all_research_unlocked`: all ids unlocked True; one locked False; `[]` False.
  - `test_large_unlocked_falls_back_to_inventory`: `BuildingSwapUpgrader._large_unlocked` and `StorageExpander._unlocked` read True with the research locked and one unit in inventory (use those modules' existing test setup in `tests/test_building_swap_upgrade.py` if it covers them; add the case there instead).
- [ ] **Step 2: Run** `python -m unittest tests.test_components_helpers -v`. Expected: FAIL (`AttributeError`).
- [ ] **Step 3: Implement** both helpers in components.py (per call `component("research")`, `bool(research.is_unlocked(id))`, raise goes to `swallowed(where, error)`; no `hasattr` guard, no id variants). Switch the 12 sites; `early_buyer.is_unlocked` becomes an import of `research_unlocked` under its old name only if its tests patch it, else its 4 callers call the helper. `_seismic_wanted` and `_exotic_research_done` use `all_research_unlocked`. `_stock_table` loses its lazy resolve.
- [ ] **Step 4: Run** the new tests and the touched modules' tests, then the full checks. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(components): one research unlock guard`.

### Task 1.6: `components.outposts()` (rank 5)

Spec family: "Network outposts list guard".

**Files:**
- Modify: `L/components.py` (next to `home_outpost()`); the six `_outposts` / `_all_outposts` copies and the prologue sites listed there; `ap/` prologues (`outpost_needs` :641 :663, `building_plan` :385, `focus_plan` :215, `extractor_plan` :119, `blueprint_queue` :25).
- Test: `tests/test_components_helpers.py`

**Interfaces:**
- Produces: `components.outposts() -> list[OutpostRef]` (`[]` when the network is missing or `outposts()` raises; `swallowed("components.outposts: network.outposts", error)`).

- [ ] **Step 1: Write the failing tests**:
  - `test_outposts_lists_network`: returns the world's outposts (ids equal `self.world.outposts` keys).
  - `test_outposts_missing_network_reads_empty`, `test_outposts_raise_reads_empty` (`RuntimeError` from the stub's `outposts`).
  - `test_production_core_falls_back_to_home`: with `outposts()` raising, `production_core._all_outposts()` returns `[home]`.
  - `test_weather_stations_survive_network_raise`: `weather_signals.discover_stations` with a raising network returns its empty result instead of raising.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** `outposts()`; the six copies go (callers call `components.outposts()`); `drone_haul_plan.outposts_by_id` = `{o.id: o for o in outposts()}`; `production_core._all_outposts` = `outposts() or ([home] if home else [])`; prologues replace their own guard (the walks stay). `fleet_upgrade._drones` stays (fleet, not network). Two commits: `L/` sites, then `ap/` sites.
- [ ] **Step 4: Run** the tests, then the full checks. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(components): one outposts() read` and `refactor(autoplay): outpost prologues use components.outposts`.

### Task 1.7: Phase close

- [ ] Docs: `docs/cheatsheet/archive_ipc.md` §Data Archive names `get_dict` beside `get_entry`; `docs/cheatsheet/lib_map.md` rows for `components.py` name `research_unlocked`, `outposts`; spec families get a `Landed (commit)` line; `docs/plans/code_quality.md` Done table gains the families.
- [ ] `python devtools/code_scan/clone_scan.py --min-ratio 0.85 --min-lines 3 --top 0`: the merged pairs are gone; recheck ignore entries of restructured functions.
- [ ] Review: `caveman:cavecrew-reviewer` on the branch diff; fix findings; full checks.
- [ ] Handoff: `docs/plans/helpers_handoff.md` (landed, next phase, open questions); tick Phase 1 in TODO.md; ask the operator to approve the merge.

---

## Phase 2 (one session): ranks 6-12

Worktree `helpers-impl-2`. Same task shape as Phase 1: failing tests for the new helper first, then batches of sites, one commit per batch.

### Task 2.1: `mutate`, `pop_entries`, `dict_entry` (ranks 6, 10)

Spec families: "Archive transaction updater coerces non-dict to empty", "Keyed-state mutate wrapper", "Archive sub-entry lookup and patch".

**Interfaces:**
- Produces, in `L/archive.py`: `ArchiveClient.mutate(key: str, fn: Callable[[dict], None]) -> bool` (coerce to dict, `fn(state)` edits in place, write back; the transaction's bool); `ArchiveClient.pop_entries(key: str, entry_ids) -> bool`; `ArchiveClient.dict_entry(key: str, *path) -> dict | None` (walk nested dicts; None unless the leaf is a dict).
- Tests (`tests/test_archive_client.py`): `test_mutate_coerces_non_dict`, `test_mutate_returns_false_without_notebook`, `test_pop_entries_drops_listed_keeps_rest`, `test_pop_entries_non_dict_writes_empty`, `test_dict_entry_walks_path`, `test_dict_entry_non_dict_leaf_reads_none`. Updaters stay pure (cheatsheet archive_ipc "Updaters must be pure"): `fn` must not log.
- [ ] Helpers plus tests. Commit.
- [ ] Keyed-state wrappers (`update_fleet_upgrade`, `update_commission` stay as one-line aliases; the two private `_update` go), lookups onto `dict_entry`, the three `_patch` onto `mutate`. Commit.
- [ ] Updater batches by the spec's shape list, each with its module's tests: (a) set one / pop one onto `set_entry` / `pop_entry`; (b) pop many onto `pop_entries` (the archive_cleaner :282 re-check variant uses `mutate`); (c) set many or mixed onto `mutate`. Fabricator :713, smelter :331, fluid_routing :242, lead_cask :298 stay (prune then set). One commit per batch.

### Task 2.2: `swallow.safe_call` (rank 7)

Spec family: "Guarded getattr-by-name or thunk call helper". Produces `safe_call(where: str, read: Callable[[], T], default: T) -> T` in `L/swallow.py`. Tests: returns `read()`; returns `default` and logs `swallowed(where)` on a raise. Callers pass the bound method. Commit per file group.

### Task 2.3: `cash.shop_prices` / `shop_price` (rank 8)

Spec family: "Shop catalogue price read". Produces `shop_prices() -> dict[str, int]` and `shop_price(item_id, fallback=None) -> int | None`. Tests: catalogue read, `{}` on a missing or raising shop, fallback for an unknown id.

### Task 2.4: per-outpost lookups (ranks 9, 11)

Spec families: "Per-outpost building ids of one type", "Outpost-by-id lookup", "Components of one type at one outpost", "Sensor value read". Produces in `L/components.py`: `building_ids_at(outpost, type_id) -> list[str]` (sorted, empty ids dropped, `[]` on a raised walk); `outpost_by_id(outpost_id) -> OutpostRef | None` (scans `outposts()`); `components_at(outpost, type_id) -> list` (`[]` for None, None dropped); `sensor_value(sensor_id, where) -> float | None`. `outpost_mining.outpost_by_id` stays as a one-line alias. One test per contract line above.

### Task 2.5: `geometry.dist`, `game_clock.now_tick` (rank 12)

Spec families: "_dist(ax, ay, bx, by) copies", "Game clock tick copies". Produces `geometry.dist(ax, ay, bx, by) -> float` beside `distance(a, b)`; the three `_dist` defs go, their 21 call sites import it; the four tick copies import `game_clock.now_tick`. Test: `dist(0, 0, 3, 4) == 5.0`.

### Task 2.6: Phase close

As Task 1.7 (cheatsheet `archive_ipc.md` names `mutate` / `pop_entries` / `dict_entry` and the rule that no site writes its own coerce).

---

## Phase 3 (one session): ranks 13-16, deferred minors

Worktree `helpers-impl-3`.

### Task 3.1: depot walks (rank 13)

Spec family: "Depot walks". Merge onto `drone_depots.discover_drone_depots`; `fleet_upgrade._advance_depot` stays apart unless a fresh read exists (see Decisions). Test: a depot deployed in the same tick is seen by `_advance_depot`.

### Task 3.2: part 2 small families (rank 14)

Spec: part 2 "Small families" marked merge, plus "Per-outpost building type counts" (`components.building_type_counts(outpost) -> dict[str, int]`, `{}` on a raised walk). One commit per family; each new helper gets one test for its contract.

### Task 3.3: remaining singles (rank 15) and the solar nit (rank 16)

Spec: the singles listed in ranking item 15; `s0/power/solar.py` drops the id-variant loop (:98-106) and the import-time bind (tier 0, no helper).

### Task 3.4: deferred minors and the open notify candidate

- `early_buyer` keeps calling undeploy after a call failure in one pass: stop the pass on a `CALL_FAILED_STATUSES` result; test it.
- Decommission restarts the script on every wait pass while the drone swap leaves it stopped: read both flows, pick one behavior, record the reason in `docs/design_history/`, test it.
- `building_ops` lists `error` / `no_computer` twice: one definition.
- `docs/cheatsheet/fabricator_demand.md:52` omits `staged_units(item)`: add it.
- The 10 guarded raw `notify()` sites (`docs/plans/code_quality.md` "Open candidates"): judge, then merge or record as keep.

### Task 3.5: Phase close

As Task 1.7; then move this plan, both candidate files and the TODO item to `done/` / `TODO_done.md`.
