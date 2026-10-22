# Event-Driven Automation, Next Steps: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Phase 1 (1.3 and 1.6) and land Phase 2 of [event_driven_automation.md](event_driven_automation.md), so a fast parking pass with nothing due returns before its first archive read.

**Architecture:** Every poll still left in the fast pass moves to its cause, with the full pass as the backstop: grid supervision wakes Oil Generators on the reserve's drop, the request and command writers resume paused vehicles. The parking engine then keeps the earliest due tick (`next_due`) in the instance and skips a fast pass that has nothing due. The one physics poll with no known timing (Oil Pump well) keeps running on ids cached from the last pass, without reading the archive.

**Tech Stack:** game-restricted Python under `scripts/4_controlpanel/` ([CODE_GUIDES.md](../../CODE_GUIDES.md) "Game interpreter"), offline stub tests (`tests/`, `python -m unittest discover -s tests`), headless A/B (`devtools/simulation/headless/`, [stub_tests.md §10b](../cheatsheet/stub_tests.md)).

**Spec:** [docs/plans/event_driven_automation.md](event_driven_automation.md), items 1.3, 1.6 (1 and 2), Phase 2 (1 to 4) and Phase 3.1. Current code state: 2026-10-23 assessment, see the Status table there.

## Global Constraints

- Work in a worktree: `python devtools/agent_worktree.py new event-driven-next`. Commit on its branch after every task. Merge only after the operator approves, with `python devtools/agent_worktree.py merge event-driven-next -m "<subject>"`.
- Game interpreter rules (CODE_GUIDES.md "Game interpreter"): no standard library, no `with`, one-line imports, no module-level import cycle between `lib/` modules. `parking_client.py` imports only `archive`, `game_clock`, `geometry`, `swallow`, `tree_console`; it must stay that way, so `power.py` and `logistics_requests.py` may import it, never the reverse.
- An `archive.transaction()` updater must be pure (no log calls); mutate a closure list to pass data out ([archive_ipc.md](../cheatsheet/archive_ipc.md) "Updaters must be pure").
- Before an edit with more than one hunk under `scripts/`, set a sync hold (CLAUDE.md "Boundaries"); remove it after the last edit of the task.
- Checks after every task: `python -m unittest discover -s tests`, `.venv/Scripts/python.exe -m ruff check <paths>`, `.venv/Scripts/python.exe -m ruff format <paths>`, then `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview` and `npx pyright`.
- A changed constant updates [dev_workflow.md §1d-2](../cheatsheet/dev_workflow.md) in the same commit. `WAKE_AFTER_TICKS` values stay as they are.
- Every wake moved to a writer keeps its full-pass check as the backstop (spec principle "A full pass stays as the backstop").
- Commit messages: Conventional Commits (CODE_GUIDES.md "Commits"), no AI attribution.

## Review Focus

1. A writer wake runs before its archive write lands: the resumed hauler then reads the old requests and re-parks. Task 3 calls `wake_role()` only after `archive.transaction()` returned, and its test asserts the request is readable when the drone is resumed.
2. An Oil Generator parked while its grid is already low never sees the edge wake. Task 2 keeps `_low_reserve_grids()` on the full pass and tests that it wakes within one full pass.
3. A command key edited by hand (no script writer) must still resume the vehicle. Task 4 keeps `_vehicle_commands()` on the full pass and tests a hand-written `drone.recall` entry.
4. An orchestrator restart loses `next_due`, the poll ids and the solar flag. Task 5 tests that a fresh instance's first `full=False` call still runs a full pass.
5. Entries other scripts write to `script.parked` (`turbine_commit` mode `"turbine"`, a malformed value) must not break `next_due`. Task 5 tests both.

---

## File Structure

- `scripts/4_controlpanel/lib/parking_client.py`: wake primitives callable from any script. Gains `_wake_entries()`, `wake_role()`, `resume_vehicle()`, a `within` filter on `wake_kind()`, and `OIL_WAKE_RESERVE_FRACTION`.
- `scripts/4_controlpanel/lib/power.py`: `PowerGridManager` gains the low-reserve edge wake; `reserve_is_low()` becomes the one formula for "reserve low".
- `scripts/4_controlpanel/lib/script_parking.py`: the engine loses its fast-pass polls and gains `next_due`, `_polls`, `_stopped_solar` and the early return.
- `scripts/4_controlpanel/lib/logistics_requests.py`, `machine_pack_upgrade.py`: work writers wake paused haulers and builders.
- `scripts/4_controlpanel/lib/vehicle_claims.py`, `drone_claims.py`, `fleet_decommission.py`, `pioneer_upgrade.py`, `fleet_upgrade.py`: command writers resume the paused vehicle.
- `tests/test_script_parking.py`, `tests/test_power_phases.py`, `tests/test_logistics_snapshot.py`: stub tests.
- `docs/cheatsheet/dev_workflow.md` §1d-2, `docs/design_history/dev_tooling_headless.md` §1d-2v, `docs/plans/event_driven_automation.md`, `TODO.md`: docs per task.

---

### Task 1: Wake primitives in `parking_client`

**Files:**
- Modify: `scripts/4_controlpanel/lib/parking_client.py:131-166` (`wake_kind`)
- Modify: `scripts/4_controlpanel/lib/script_parking.py:64` (import), `:155` (constant moves out)
- Test: `tests/test_script_parking.py` (`VehicleParkingTests`, `FieldProviderParkingTests`)

**Interfaces:**
- Consumes: `_unpark(woken: dict[str, int], where: str)` (parking_client.py:99), `RUN_OK`, `PARKED_KEY`.
- Produces:
  - `_wake_entries(entries: dict[str, dict], reason: str, label: str, where: str) -> list[str]`: today's `wake_kind()` body from "since = ..." on. Resumes `"paused"` entries with `run_control.resume()`, switches `"breaker"` entries on with `power_control.set_powered(id, True)`, `_unpark()`s the woken, prints `[PARKING] Woke {n} {label}(s) ({reason}).`. Returns the woken ids.
  - `wake_kind(kind: str, reason: str, within=None) -> list[str]`: as today; `within` (any iterable of ids, `None` = all) restricts the entries to those ids.
  - `wake_role(role: str, reason: str) -> list[str]`: every `"paused"` entry whose `entry.get("role") == role`.
  - `resume_vehicle(machine_id: str, reason: str) -> bool`: the `"paused"` entry of `machine_id`, if any; True when resumed.
  - `OIL_WAKE_RESERVE_FRACTION = 0.40` now lives in `parking_client.py`; `script_parking.py` imports it from there (one-line import, extend line 64).

- [ ] **Step 1: Write the failing tests**

In `VehicleParkingTests`:

```python
def test_wake_role_resumes_only_that_role(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.idle("pioneer_1", "pioneer", "builder")
    self.parking.step(self.grids, 10.0)
    self.assertEqual(set(self.parked()), {"drone_1", "pioneer_1"})
    self.assertEqual(parking_client.wake_role("hauler", "test"), ["drone_1"])
    self.assertEqual(set(self.parked()), {"pioneer_1"})
    self.assertIn("drone_1", self.run_control.running)
    self.assertNotIn("drone_1", self.world.notebook.data[PARK_REQUESTS_KEY])

def test_resume_vehicle_resumes_one_paused_vehicle(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.parking.step(self.grids, 10.0)
    self.assertFalse(parking_client.resume_vehicle("pioneer_1", "test"))  # not paused
    self.assertTrue(parking_client.resume_vehicle("drone_1", "test"))
    self.assertEqual(self.parked(), {})
    self.assertFalse(parking_client.resume_vehicle("drone_1", "test"))  # already running
```

In `FieldProviderParkingTests`, with the fixture of `test_wake_kind_switches_on_every_parked_provider` (tests/test_script_parking.py:679-686: `grow_lamp_1`, `sprinkler_1`, `smelter_1` seeded in `PARKED_KEY`):

```python
def test_wake_kind_within_wakes_only_the_listed_ids(self):
    ...  # the same two add_building() calls and PARKED_KEY seed
    self.assertEqual(parking_client.wake_kind("field_provider", "test", within={"sprinkler_1", "smelter_1"}), ["sprinkler_1"])
    self.assertEqual(set(self.world.notebook.data[PARKED_KEY]), {"grow_lamp_1", "smelter_1"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_script_parking -k wake_role -k resume_vehicle -k within -v`
Expected: FAIL with `AttributeError: module 'parking_client' has no attribute 'wake_role'` (and the `within` keyword rejected).

- [ ] **Step 3: Implement**

Extract `_wake_entries()` from `wake_kind()`; `wake_kind()`, `wake_role()` and `resume_vehicle()` each read `PARKED_KEY` once, filter, and call it. Labels: the kind, the role, the machine id. Move `OIL_WAKE_RESERVE_FRACTION` and update the import in `script_parking.py:64`.

- [ ] **Step 4: Run the whole parking test module, then the checks**

Run: `python -m unittest tests.test_script_parking -v`
Expected: all PASS. Then ruff, resolve-preview, pyright (Global Constraints).

- [ ] **Step 5: Commit**

```bash
git add scripts/4_controlpanel/lib/parking_client.py scripts/4_controlpanel/lib/script_parking.py tests/test_script_parking.py
git commit -m "feat(parking): wake by role, by id and within a grid"
```

---

### Task 2: Oil Generator wake from grid supervision (spec 1.3)

**Files:**
- Modify: `scripts/4_controlpanel/lib/power.py:267-272` (next to `reserve_fraction`), `:305-320` (`__init__`), `:583-600` (`supervise_grid`)
- Modify: `scripts/4_controlpanel/lib/script_parking.py:158` (`RESERVE_CACHE_TICKS` goes), `:280-281` (`_reserve_cache` goes), `:318` (`step`), `:585-626` (`_low_reserve_grids`)
- Test: `tests/test_power_phases.py` (new `OilWakeTests(_GridWorld)`), `tests/test_script_parking.py:12-21` (`_FakePower`), `:175-189`
- Docs: `docs/cheatsheet/dev_workflow.md` §1d-2 "Wake" paragraph

**Interfaces:**
- Consumes: `parking_client.wake_kind(kind, reason, within)` (Task 1); `measure_grid()`, `reserve_fraction()` (power.py:240, :267).
- Produces:
  - `power.reserve_is_low(now: dict) -> bool`: over `[reserve_fraction(now), now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None]` with `None` dropped: True when the list is empty or its minimum is below `OIL_WAKE_RESERVE_FRACTION`. This is the formula at script_parking.py:616 today; `_low_reserve_grids()` calls it instead.
  - `PowerGridManager.reserve_low: bool` (False in `__init__`): the last `supervise_grid()` verdict.
  - In `supervise_grid()`, right after `now = self._measure(grid)` and before the `bat_cap <= 0 and steam_cap <= 0` return (move the `grid_machines` line above it): `low = reserve_is_low(now)`; when `low and not self.reserve_low`, call `parking_client.wake_kind("oil_generator", "grid reserve low", within=grid_machines)`; then `self.reserve_low = low`. Import: `import parking_client` at power.py's module level (no cycle, see Global Constraints).
  - `ScriptParking.step()`: `low_grids = self._low_reserve_grids(...) if full else set()`. The verdict cache and `RESERVE_CACHE_TICKS` are removed (a full pass is already 150 ticks apart).

- [ ] **Step 1: Write the failing tests**

`tests/test_power_phases.py`:

```python
class OilWakeTests(_GridWorld):
    """A grid whose reserve drops below OIL_WAKE_RESERVE_FRACTION wakes its parked Oil Generators once."""

    def setUp(self):
        super().setUp()
        self.world.add_building("oil_generator_1", self.world.home, "oil_generator")
        self.ids.append("oil_generator_1")
        self.world.power_control.set_powered("oil_generator_1", False)
        self.world.notebook.data[parking_client.PARKED_KEY] = {"oil_generator_1": {"kind": "oil_generator", "mode": "breaker", "since": 0}}
        self.world.power_control.calls.clear()

    def reserve(self, stored):
        return self.world.add_grid("battery_1", self.ids, consumed=200.0, stored=stored, capacity=1000.0)

    def test_drop_below_the_fraction_wakes_once(self):
        manager = power.PowerGridManager(self.reserve(800.0), clock=self.world.clock)
        manager.supervise_grid(self.reserve(800.0))
        self.assertFalse(manager.reserve_low)
        self.assertNotIn(("oil_generator_1", True), self.world.power_control.calls)
        manager.supervise_grid(self.reserve(300.0))
        self.assertTrue(manager.reserve_low)
        self.assertIn(("oil_generator_1", True), self.world.power_control.calls)
        self.assertNotIn("oil_generator_1", self.world.notebook.data[parking_client.PARKED_KEY])
        self.world.power_control.calls.clear()
        self.world.power_control.set_powered("oil_generator_1", False)
        self.world.notebook.data[parking_client.PARKED_KEY] = {"oil_generator_1": {"kind": "oil_generator", "mode": "breaker", "since": 0}}
        manager.supervise_grid(self.reserve(300.0))  # still low: no second wake, the full pass is the backstop
        self.assertNotIn(("oil_generator_1", True), self.world.power_control.calls)

    def test_wake_runs_before_the_no_storage_return(self):
        # a grid without battery or steam: reserve_is_low() is True (nothing to measure)
        ...
```

For the second test, build a grid with `stored=0.0, capacity=0.0` and assert the wake call happened.

`tests/test_script_parking.py`: give `_FakePower` a `reserve_is_low(self, now)` returning `self.fraction < parking_client.OIL_WAKE_RESERVE_FRACTION`. Rewrite `test_oil_generator_wakes_and_stays_up_on_low_reserve` without the cache step: after `script_parking.power = _FakePower(0.1)`, one full pass wakes it. Add:

```python
def test_fast_pass_leaves_the_reserve_check_to_the_full_pass(self):
    script_parking.power = _FakePower(0.5)
    self.request("oil_generator_1", "oil_generator")
    self.parking.step(self.grids, 10.0)
    script_parking.power = _FakePower(0.1)
    self.parking.step(self.grids, 10.0, full=False)
    self.assertEqual(self.power.calls[-1], ("oil_generator_1", False))
    self.parking.step(self.grids, 10.0)
    self.assertEqual(self.power.calls[-1], ("oil_generator_1", True))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_power_phases.OilWakeTests tests.test_script_parking.ScriptParkingTests -v`
Expected: `OilWakeTests` FAIL (`reserve_low` missing); the fast-pass test FAIL (the fast pass still wakes).

- [ ] **Step 3: Implement** per Interfaces. Delete `_reserve_cache`, `RESERVE_CACHE_TICKS` and the `_FakePower` cache expectations.

- [ ] **Step 4: Run the tests and checks**

Run: `python -m unittest tests.test_power_phases tests.test_script_parking -v`, then the full suite and the checks.
Expected: all PASS.

- [ ] **Step 5: Docs.** In §1d-2 "Wake": Oil Generators are woken by `PowerGridManager.supervise_grid()` (every `SOLAR_TICK_INTERVAL`) when the grid's reserve drops below `OIL_WAKE_RESERVE_FRACTION` (on the drop, `reserve_low` edge); the full pass's `_low_reserve_grids()` is the backstop for a generator parked while the grid is already low. Delete the `RESERVE_CACHE_TICKS` sentence. In "Panel side": the fast pass no longer measures grids. Section size must stay under 16 KB (`tests/test_docs_lint.py`).

- [ ] **Step 6: Commit**

```bash
git add scripts/4_controlpanel/lib/power.py scripts/4_controlpanel/lib/script_parking.py tests/test_power_phases.py tests/test_script_parking.py docs/cheatsheet/dev_workflow.md
git commit -m "feat(power): wake parked Oil Generators from grid supervision"
```

---

### Task 3: Work wakes at the writer (spec 1.6.1)

**Files:**
- Modify: `scripts/4_controlpanel/lib/logistics_requests.py:185-218` (`set_requests`)
- Modify: `scripts/4_controlpanel/lib/machine_pack_upgrade.py:166-171` (after a planned install)
- Test: `tests/test_script_parking.py` (`VehicleParkingTests`), `tests/test_machine_pack_upgrade.py:59` (`test_plans_one_oil_pump_install_at_a_time`)
- Docs: §1d-2 "Vehicles" paragraph

**Interfaces:**
- Consumes: `parking_client.wake_role(role, reason)` (Task 1).
- Produces:
  - `set_requests()`: the updater records, in a closure list `added`, the item ids of `wants` that had no entry under `requests[outpost_id]` before this write (any requester; this is the `"outpost item"` key `_haul_keys()` reads). Assign with `added[:] = [...]`, since an updater can run more than once. After `archive.transaction()` returns, when `added` is non-empty: `wake_role("hauler", f"new haul request: {outpost_id} {added[0]}")`. Module-level `from parking_client import wake_role`.
  - `machine_pack_upgrade.py`: after the `res.status == "ok"` log line: `wake_role("builder", f"new construction job: {OIL_PUMP_PACK}")`.
  - `ScriptParking._work_wakes()` stays on full passes as the backstop (player-placed blueprints have no script writer).

- [ ] **Step 1: Write the failing tests**

`VehicleParkingTests` (the `wants` shape: `{item_id: (levels, have)}`, build `levels` with the `R()` helper of `tests/test_logistics_snapshot.py:42`, or `priority.from_levels()`):

```python
def test_new_haul_request_resumes_paused_haulers_at_the_writer(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.parking.step(self.grids, 10.0)
    self.assertEqual(self.parked()["drone_1"]["mode"], "paused")
    now = self.world.clock.now
    logistics_requests.set_requests("outpost_1", "fab", {"iron_ore": (R(10), 0)}, now)
    self.assertNotIn("drone_1", self.parked())
    self.assertIn("outpost_1", logistics_requests.active_requests(now))  # readable when the drone resumes
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.parking.step(self.grids, 10.0)
    logistics_requests.set_requests("outpost_1", "fab", {"iron_ore": (R(20), 0)}, now)  # same key, raised
    self.assertIn("drone_1", self.parked())
```

`tests/test_machine_pack_upgrade.py`, extend `test_plans_one_oil_pump_install_at_a_time`: pause a builder Pioneer first (seed `PARKED_KEY` with `{"pioneer_1": {"kind": "pioneer", "mode": "paused", "since": 0, "role": "builder"}}` and `run_control.states["pioneer_1"] = "paused"`), then assert that after the planned install `pioneer_1` is no longer in `PARKED_KEY`.

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_script_parking.VehicleParkingTests tests.test_machine_pack_upgrade -v`
Expected: the two new assertions FAIL (vehicle still paused).

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite and checks.** Expected: all PASS.

- [ ] **Step 5: Docs.** §1d-2 "Vehicles": new work resumes paused vehicles at the writer: `logistics_requests.set_requests()` on a new `(outpost, item)` key (`wake_role("hauler")`), `machine_pack_upgrade` on a planned install (`wake_role("builder")`); `_work_wakes()` on full passes stays the backstop and the only path for player-placed blueprints.

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(parking): resume paused vehicles when their work is written"
```

---

### Task 4: Command wakes at the writer (spec 1.6.2)

**Files:**
- Modify: `scripts/4_controlpanel/lib/vehicle_claims.py:111-114` (`set_vehicle_recalled`), `drone_claims.py:42-45` (`set_drone_recalled`), `fleet_decommission.py:89-91` (`request_decommission`), `pioneer_upgrade.py:87-96` (`request_sport_nav`), `fleet_upgrade.py:255-296` (`_start_next_drone`, where the drone entry gets state `"ordered"`)
- Modify: `scripts/4_controlpanel/lib/script_parking.py:745-778` (`_wake_paused`), `:326` (`step`)
- Test: `tests/test_script_parking.py:524-539`, `tests/test_script_parking.py` (new), `tests/test_job_loop.py` (only if it asserts command wakes on fast passes; grep `full=False`)
- Docs: §1d-2 "Vehicles"; `docs/design_history/dev_tooling_headless.md` §1d-2v (one dated paragraph)

**Interfaces:**
- Consumes: `parking_client.resume_vehicle(machine_id, reason)` (Task 1).
- Produces:
  - Each writer, after its archive write and only when it sets the command (recall `True`, a new decommission request, a new Sport Nav request, a drone entry entering `"ordered"`): `resume_vehicle(<vehicle name>, "<command> requested")`. Check each module's imports: `parking_client` is a leaf, so a module-level import is fine unless the module is itself imported by `parking_client` (none is).
  - `ScriptParking._wake_paused(parked, woken, now, work_wakes, commands)`: `commands` is passed in; `step()` passes `self._vehicle_commands()` on full passes and `{}` on fast passes. Fast passes resume on "re-check due" only.
  - `_pause_vehicle()` keeps its command check (full passes only already).

- [ ] **Step 1: Write the failing tests**

Change `test_pending_command_blocks_the_pause_and_wakes_a_paused_vehicle`: the `"ordered"` write there is a hand edit of the archive, so the wake now needs a full pass. Replace its last `full=False` step with `self.parking.step(self.grids, 10.0, full=False)` asserting the drone is **still** paused, then a full pass asserting it resumed (Review Focus 3). Add:

```python
def test_recall_and_decommission_writers_resume_the_vehicle(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.idle("pioneer_1", "pioneer", "builder")
    self.parking.step(self.grids, 10.0)
    drone_claims.set_drone_recalled("drone_1", True)
    self.assertNotIn("drone_1", self.parked())
    fleet_decommission.request_decommission("pioneer_1", "pioneer")
    self.assertNotIn("pioneer_1", self.parked())
    self.assertEqual(self.run_control.running, {"pioneer_1", "drone_1"})

def test_clearing_a_recall_resumes_nothing(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.parking.step(self.grids, 10.0)
    drone_claims.set_drone_recalled("drone_1", False)
    self.assertIn("drone_1", self.parked())
```

One test each for `set_vehicle_recalled`, `request_sport_nav` and the `fleet_upgrade` `"ordered"` transition, in the same shape (for `fleet_upgrade`, drive `_start_next_drone` the way `tests/test_fleet_upgrade*.py` does; if no such test exists, assert on `_patch(..., state="ordered")`'s caller through `FleetUpgradeCoordinator.step()` with one unlocked chassis tier).

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_script_parking.VehicleParkingTests -v`
Expected: the writer tests FAIL (vehicle still paused); the changed hand-edit test FAILs on the fast-pass assertion.

- [ ] **Step 3: Implement** per Interfaces.

- [ ] **Step 4: Run the full suite and checks.** Expected: all PASS. Run `python -m unittest tests.test_job_loop` on its own as well.

- [ ] **Step 5: Docs.** §1d-2 "Vehicles": a command resumes its vehicle at the writer (list the five callers); `_vehicle_commands()` runs on full passes only, so a hand-edited key resumes within `PARKING_FULL_TICK_INTERVAL`. Design history §1d-2v: one paragraph dated 2026-10, "the panel-side command poll moved to full passes; writers resume directly (Phase 2 needs a fast pass without archive reads); hand edits wait at most one full pass".

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(parking): command writers resume their paused vehicle"
```

---

### Task 5: `next_due` and the early return (spec Phase 2, Phase 3.1)

**Files:**
- Modify: `scripts/4_controlpanel/lib/script_parking.py:275-291` (`__init__`), `:293-364` (`step`), new helpers after `_wake_reason`
- Modify: `scripts/4_controlpanel/automation/orchestrator_automation.py:255-259` (`park_if_due` docstring only)
- Test: `tests/test_script_parking.py` (`ScriptParkingTests`, `VehicleParkingTests`)
- Docs: §1d-2 "Panel side"

**Interfaces:**
- Consumes: nothing new; Tasks 2 to 4 removed every other fast-pass trigger.
- Produces, on `ScriptParking`:
  - `self.next_due: int | None` (None before the first pass): the smallest `since + wake_after` over entries with `mode in ("breaker", "paused")`, where `wake_after = entry.get("wake_after", WAKE_AFTER_TICKS.get(kind, 600))`; entries that are not dicts or lack `since` are skipped. Recomputed by `_index_parked(parked, now)` at the end of every `step()` from the final `parked` dict.
  - `self._polls: list[str]`: ids of `"breaker"` entries with kind `"oil_pump"` at the end of the last pass (the Oil Well model has no `next_phase_in()`, `docs/models/misc_models.md:1754`, so the well poll stays). Also set by `_index_parked()`.
  - `self._stopped_solar: bool`: whether any `"stopped"` entry existed at the end of the last pass. Also set by `_index_parked()`.
  - `_fast_pass_idle(now, elevation) -> bool`: True when `self.next_due is not None and now < self.next_due`, and not (`elevation is not None and elevation > 0 and self._stopped_solar`), and no id in `self._polls` reads `_well_active()`. Called at the top of `step()` when `full` is False (after the `full = full or self._members_seen is None` line); when True, `step()` returns before `archive.get(PARKED_KEY)` and before `log.start()`, so an idle fast pass leaves no debug block.
  - The `exotic_cap` deposit poll (`_wake_reason`'s `deposit active`) and the `oil_pump` well poll inside `_wake_reason` are unchanged: they run whenever the pass runs. The Exotic Cap's own `wake_after` timer (exotic_cap.py:104-113) is its primary wake; the poll is the backstop.

- [ ] **Step 1: Write the failing tests**

`ScriptParkingTests`:

```python
def test_idle_fast_pass_reads_nothing(self):
    self.request("smelter_1", "smelter")
    self.parking.step(self.grids, 10.0)
    self.assertEqual(self.parking.next_due, self.world.clock.now + WAKE_AFTER_TICKS["smelter"])
    reads = self.world.notebook.reads  # new counter on the shared fake: tests/game_stubs.py:941 `Notebook`, `self.reads += 1` in `get()` (the existing `reads` at :1153 is the Panel stub's)
    self.parking.step(self.grids, 10.0, full=False)
    self.assertEqual(self.world.notebook.reads, reads)
    self.assertNotIn("script parking", self.debug_log())  # no block for an idle fast pass

def test_fast_pass_runs_once_the_earliest_wake_is_due(self):
    self.request("smelter_1", "smelter")
    self.parking.step(self.grids, 10.0)
    self.world.clock.now += WAKE_AFTER_TICKS["smelter"]
    self.parking.step(self.grids, 10.0, full=False)
    self.assertEqual(self.power.calls[-1], ("smelter_1", True))
    self.assertIsNone(self.parking.next_due)

def test_first_pass_of_a_fresh_instance_is_full(self):
    self.request("smelter_1", "smelter")
    self.parking.step(self.grids, 10.0)
    fresh = ScriptParking(power=self.power, run_control=self.run_control)
    self.world.clock.now += WAKE_AFTER_TICKS["smelter"]
    fresh.step(self.grids, 10.0, full=False)
    self.assertEqual(self.power.calls[-1], ("smelter_1", True))

def test_next_due_skips_foreign_and_malformed_entries(self):
    self.world.notebook.data[PARKED_KEY] = {"turbine_1": {"kind": "turbine", "mode": "turbine", "since": 0}, "junk": "x", "smelter_1": {"kind": "smelter", "mode": "breaker"}}
    self.parking.step(self.grids, 10.0)
    self.assertIsNone(self.parking.next_due)

def test_sunrise_start_runs_on_an_idle_fast_pass(self):
    # as test_solar_started_on_a_fast_pass_but_not_stopped, with a parked smelter whose wake is far off
    ...

def test_parked_oil_pump_is_polled_on_an_idle_fast_pass(self):
    # as test_oil_pump_wakes_when_its_well_turns_active, but the well turns active between two fast passes
    # while next_due is far off; assert the pump wakes on the fast pass
    ...
```

`VehicleParkingTests`:

```python
def test_paused_vehicle_sets_next_due(self):
    self.idle("drone_1", "drone", "hauler", state="IDLE")
    self.parking.step(self.grids, 10.0)
    self.assertEqual(self.parking.next_due, self.world.clock.now + WAKE_AFTER_TICKS["drone"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m unittest tests.test_script_parking -v`
Expected: FAIL with `AttributeError: 'ScriptParking' object has no attribute 'next_due'`.

- [ ] **Step 3: Implement** per Interfaces. `_index_parked()` is one walk over `parked`; put the call just before `log.end()`, after `_commit()`, using the pass's final `parked`. A machine-filed `wake_after` is already capped at `MAX_WAKE_AFTER_TICKS` when written, so no cap is needed here.

- [ ] **Step 4: Run the full suite and checks.** Expected: all PASS. Then `python devtools/code_scan/size_scan.py` if `script_parking.py` or `step()` is pinned in `devtools/code_scan/*_ignore.txt` (CODE_GUIDES.md "Checks").

- [ ] **Step 5: Docs.** §1d-2 "Panel side": a fast pass returns before any archive read while `now < next_due` (earliest `since + wake_after` over breaker and paused entries, kept in the instance), no solar script is stopped at sunrise and no parked Oil Pump reads `well_active()`; it then leaves no debug block, so `log_block_timing.py` counts only passes that did work. `park_if_due()` docstring: same sentence, short.

- [ ] **Step 6: Commit**

```bash
git commit -am "perf(parking): skip a fast pass with nothing due"
```

---

### Task 6: Headless A/B, live measure, plan close-out

**Files:**
- Modify: `docs/plans/event_driven_automation.md` (Status table, a "Phase 2 results" subsection), `TODO.md:95`
- No script changes unless the A/B shows a regression.

- [ ] **Step 1: Headless A/B** per spec Phase 1.6: `devtools/simulation/headless/save_scripts.py` on `main` (baseline) and on the branch; `run.mjs --save <save> --scripts <dir> --libs <dir>/lib --hours 0.6 --paid-debug --sticky-fluids --out <dir>` on the mid-late sample save (`internals/sample_saves/`) and a copy of the current main save.

- [ ] **Step 2: Compare** from each run's `console.log`: `┏━ script parking` block count and ticks (baseline fast passes ~12 ticks; branch: only full passes and working fast passes appear), `[PARKING] Woke` lines by reason (`grid reserve low`, `new haul request`, `* requested`), `resumed ` lines by reason, Fabricator/Smelter `Sent Nx` output and the pass spacing (spec "How to measure" 1 to 3). Pass when: no production loss, no vehicle paused longer than `WAKE_AFTER_TICKS["drone"]` with work pending, and fewer parking block ticks per 1,000 ticks than baseline.

- [ ] **Step 3: Record** the numbers in the spec under a new `### Phase 2 results (<date>)`, update its Status table (1.3 done, 1.6 done, Phase 2 done, Phase 3.1 "Oil Pump stays a poll on cached ids"), and shorten the TODO.md line 95 "Open:" list to what remains (live confirm, Phase 3.2 solar timer).

- [ ] **Step 4: Commit and hand over**

```bash
git commit -am "docs(plans): record the Phase 2 parking results"
```

Ask the operator to approve the merge (`python devtools/agent_worktree.py merge event-driven-next -m "feat(parking): wakes at the cause and an idle fast pass"`), then one live window per the spec's "How to measure" (hand-off step 1, 2 and 4).

---

## Out of scope (same pattern, separate plans)

Left for later, each its own measure-first change: `plan_docks_if_due` on a re-plan marker, `publish_demand_if_due` refresh cost and trigger, `log_vents_if_due` as a `next_phase_in()` timer, `CENSUS_TICK_INTERVAL = 600`, the builder's decommission message (spec Phase 4 template), site supply publish on `consume_manual_order()`. Listed in the spec's "Open leads outside this plan" and TODO.md "Script Load".
