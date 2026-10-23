# Notify wrappers and building_ops calls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two open helper candidates of the code quality plan: drop the `_notify` wrappers, and route every remaining raw `computer.deploy()` / `undeploy()` / `upgrade()` call through `building_ops`.

**Architecture:** `notify()` raises only on bad arguments (decompiled `evaluator.createbuiltins.notify_*` messages: type and level checks), so a guard around it hides our own bugs. The wrappers go and callers call `notify()` directly. `building_ops` already owns `undeploy()` and `deploy_new()` (guarded call, shared status table `classify()`); it gains `upgrade()` and one constant for "the call could not ask", and the last raw callers move onto the three helpers. Each caller keeps its own policy (sell, buy, retry limits, logs).

**Tech Stack:** in-game Python libs under `scripts/4_controlpanel/lib/`, `unittest` with `tests/harness.py` (`StubTestCase`, builtin `notify` appends to `self.world.notices`).

**Spec:** [code_quality.md](../code_quality.md), "Open candidates" (first two bullets).

## Global Constraints
- Sync hold before editing `scripts/` (CLAUDE.md §Boundaries); remove it after the last edit of each task.
- A call that could not ask (`"error"`, `"no_computer"`) waits and retries next pass: it never blocks a job, never counts toward a refusal limit, and logs no warn of its own (`swallowed()` already logged the raise).
- No behavior change for the player beyond the two rules pinned in Tasks 3 (gone = done). Toast texts, levels and durations stay exactly as they are today.
- Every task ends green: `python -m unittest discover -s tests`, `.venv/Scripts/python.exe -m ruff check` + `ruff format` on touched paths, `.venv/Scripts/python.exe devtools/scripts_sync.py resolve-preview` then `npx pyright`.
- Commit messages per `caveman:caveman-commit`; no AI attribution.

## Review Focus
1. A `_notify` call that relied on the wrapper defaults (`level="warn"`, `duration=8.0`) must get both spelled out, or its toast turns `info` / 5 s. Task 1 test pins one such call per module.
2. A caller's own wait-status tuple lacking `"error"` / `"no_computer"` would block a Depot or swap on one raised call. Tasks 2-3 each pin it with a raising stub.
3. `building_ops.undeploy()` logs the refusal itself; a caller that still prints `res.message` would double-log or reference a name that no longer exists. Grep each touched function for `res.` after the edit.
4. `fleet_decommission` and the `fleet_upgrade` drone swap now treat `not_found` as done. A test per site pins that the machine is forgotten, not blocked.
5. `test_reactor.py` and `test_script_parking.py` patch or read `_notify`; they must read `self.world.notices` instead, or they pass vacuously.

---

### Task 1: Drop the `_notify` wrappers

**Files:**
- Modify: `scripts/4_controlpanel/lib/power.py` (def at :194, calls :395, :412, :558)
- Modify: `scripts/4_controlpanel/lib/power_solar.py` (def :59, calls :113, :119, :173, :218)
- Modify: `scripts/4_controlpanel/lib/reactor.py` (def :146, calls :340, :343, :396, :426)
- Modify: `scripts/4_controlpanel/lib/oil_generator.py` (def :110, call :350)
- Modify: `scripts/4_controlpanel/lib/script_parking.py` (staticmethod `_notify(text)` :745 and its callers)
- Modify: `scripts/4_controlpanel/lib/wildlife_planner.py` (def `_notify(message)` :931 and its callers)
- Modify: `tests/test_reactor.py:111-115`, `tests/test_script_parking.py` (any `_notify` patch)
- Modify: `tests/harness.py:50` (builtin `notify` also records its args), `tests/game_stubs.py:2795` (`world.notice_args`)

**Interfaces:**
- Produces: no `_notify` name in `scripts/` (grep `_notify\b` returns nothing).

- [ ] **Step 1: Switch the tests to `self.world.notices`.** In `test_reactor.py` remove the `rx._notify` patch and restore in `setUp`/`tearDown`; every `self.notified` read becomes `self.world.notices`. Same for `test_script_parking.py` if it patches `_notify`.
- [ ] **Step 2: Add one default-pinning test per module** (`power`, `power_solar`, `reactor`, `oil_generator`, `script_parking`, `wildlife_planner`): extend `tests/harness.py`'s builtin to also record `(text, level, duration_seconds)` in `world.notice_args` (new list next to `world.notices` in `game_stubs.py:2795`), then assert the existing trigger yields the same level and duration as today. Example for reactor overheat: `assertEqual(self.world.notice_args[-1][1:], ("warn", 8.0))`; for the sticky out-of-fuel toast `("error", 0)`; for `script_parking` / `wildlife_planner` `("warn", 10.0)`. Reuse each module's existing test that reaches the notify line; add a test only where none does.
- [ ] **Step 3: Run the tests.** `python -m unittest tests.test_reactor tests.test_script_parking` (plus the other touched modules' test files). Expected: PASS (wrappers still in place, same args).
- [ ] **Step 4: Replace every wrapper call with `notify(text, level=..., duration_seconds=...)`**, spelling out the wrapper's defaults where the call omitted them; delete the six wrapper definitions and any `swallowed` import left unused.
- [ ] **Step 5: Run the full checks** (Global Constraints). Expected: all green; `grep -rn "_notify\b" scripts tests` empty.
- [ ] **Step 6: Commit** `refactor(notify): call notify() directly, drop six guards`.

### Task 2: `building_ops.upgrade()` and its callers

**Files:**
- Modify: `scripts/4_controlpanel/lib/building_ops.py` (new `upgrade()` after `deploy_new()` :104; `_step_upgrade` :373-381 uses it)
- Modify: `scripts/4_controlpanel/lib/early_buyer.py:349` (`apply_mk2_packs`)
- Modify: `scripts/4_controlpanel/lib/fleet_upgrade.py:328` (Depot in-place upgrade)
- Modify: `scripts/4_controlpanel/lib/pillar_swap.py:422` (`_upgrade`)
- Modify: `scripts/4_controlpanel/lib/machine_pack_upgrade.py:130-137` (`_apply`)
- Test: `tests/test_building_ops.py`, `tests/test_early_buyer.py`, `tests/test_fleet_upgrade.py`, `tests/test_pillar_swap.py`, `tests/test_machine_pack_upgrade.py`

**Interfaces:**
- Produces: `building_ops.CALL_FAILED_STATUSES = ("error", "no_computer")` (next to `TRANSIENT_STATUSES` :46, which keeps both).
- Produces: `building_ops.upgrade(pack, machine_id, computer=None) -> tuple[str, str]`: `(status, message)`; `("no_computer", "")` without a computer, `("error", "")` when the call raised (`swallowed("building_ops.upgrade: computer.upgrade", error)`), else `(res.status or "?", res.message or "")`.

- [ ] **Step 1: Write the failing tests** in `tests/test_building_ops.py` `UpgradeTests`: `test_upgrade_returns_status_and_message` (stub refusal `"wrong_machine_type"` comes back with its message), `test_upgrade_raise_is_error` (stub computer whose `upgrade` raises `RuntimeError` gives `("error", "")`), `test_upgrade_without_computer` (`("no_computer", "")`).
- [ ] **Step 2: Run** `python -m unittest tests.test_building_ops`. Expected: FAIL, `module 'building_ops' has no attribute 'upgrade'`.
- [ ] **Step 3: Implement `upgrade()` and `CALL_FAILED_STATUSES`**; `_step_upgrade` calls `upgrade(item_id, machine_id)` and keeps its two messages: `no_computer` -> `"{job_id}: no Ship Computer"`, `error` -> `"{job_id}: upgrade error"`.
- [ ] **Step 4: Run** the same tests. Expected: PASS, existing `test_pack_from_inventory` too.
- [ ] **Step 5: Write one failing test per caller** with a raising `upgrade` stub: early_buyer returns without a warn line; fleet_upgrade Depot stays out of `blocked` and returns `"{old_id}: upgrade error"`; pillar_swap returns the waiting line and leaves the job's phase; machine_pack_upgrade `_apply` returns `False` without recording a refusal.
- [ ] **Step 6: Run** those test files. Expected: FAIL for the three uncaught callers (the raise propagates).
- [ ] **Step 7: Switch the four callers** to `status, message = building_ops.upgrade(pack, machine_id, computer)`. Each caller's wait tuple check becomes `status in <WAIT_TUPLE> or status in building_ops.CALL_FAILED_STATUSES`; logs that printed `res.message` print `message`. `machine_pack_upgrade` drops its own try/except.
- [ ] **Step 8: Run the full checks.** Expected: green; `grep -rn "computer.upgrade(" scripts/4_controlpanel/lib` only in `building_ops.py` and comments.
- [ ] **Step 9: Commit** `refactor(building_ops): one upgrade() for every pack call`.

### Task 3: Undeploy callers onto `building_ops.undeploy()`

**Files:**
- Modify: `scripts/4_controlpanel/lib/early_buyer.py:298` (`undeploy_and_sell`)
- Modify: `scripts/4_controlpanel/lib/fleet_decommission.py:240-253` (and `__init__` :124 for `self.warned = {}`)
- Modify: `scripts/4_controlpanel/lib/fleet_upgrade.py:425-434` (drone swap)
- Test: `tests/test_early_buyer.py`, `tests/test_fleet_decommission.py`, `tests/test_fleet_upgrade.py`

**Interfaces:**
- Consumes: `building_ops.undeploy(machine_id, logger=None, warned=None, computer=None, tag="") -> str`, `building_ops.classify(status) -> str`, `CALL_FAILED_STATUSES` (Task 2).

- [ ] **Step 1: Write the failing tests:**
  - `test_fleet_decommission`: `not_found` from undeploy forgets the machine (no entry left, state not `blocked`); a raising undeploy leaves `attempts` unchanged and the entry `requested`; a fatal refusal still blocks after `MAX_UNDEPLOY_ATTEMPTS`.
  - `test_fleet_upgrade`: drone swap with `not_found` continues to the deploy step; a raising undeploy leaves `attempts` unchanged.
  - `test_early_buyer`: a raising undeploy removes nothing and sells nothing.
- [ ] **Step 2: Run** those files. Expected: FAIL (raw calls raise; `not_found` counts as a refusal).
- [ ] **Step 3: Switch the three sites.**
  - early_buyer: `status = building_ops.undeploy(b_id, logger=log, computer=computer, tag="[early_buyer] ")`; `"ok"` keeps the "Undeployed ... (freed slot)" print; drop its own refusal print (building_ops logs it).
  - fleet_decommission: `status = building_ops.undeploy(machine_id, logger=self.log, warned=self.warned, computer=computer, tag="[decommission] ")`. `classify(status) in ("ok", "gone")` takes the retired path. Attempts add `0` for `RETRY_STATUSES` and `CALL_FAILED_STATUSES`, else `1`. The blocked warn and the debug line drop `res.message`.
  - fleet_upgrade drone swap: the same call with `tag="[fleet_upgrade] "` and a `self.warned` dict; `ok`/`gone` continues; `CALL_FAILED_STATUSES` adds no attempt.
- [ ] **Step 4: Run the full checks.** Expected: green.
- [ ] **Step 5: Commit** `refactor(building_ops): last undeploy callers use the shared wrapper`.

### Task 4: Deploy callers onto `deploy_new()`, docs

**Files:**
- Modify: `scripts/4_controlpanel/lib/early_buyer.py:324` (`buy_and_deploy`)
- Modify: `scripts/4_controlpanel/lib/storage_expand.py:139-150` (`_deploy`)
- Modify: `docs/cheatsheet/lib_map.md:141` (name `upgrade()` and `CALL_FAILED_STATUSES` in the `building_ops.py` row)
- Modify: `docs/cheatsheet/autoplay.md` §11k if it lists the helpers (`python devtools/docs_section.py 11k`)
- Modify: `docs/plans/code_quality.md` ("Open candidates": mark both bullets done with the date, move them to the "Done" table)
- Modify: `TODO.md` (Code Quality section: tick the helper candidates box, keep the sweep box open)
- Test: `tests/test_early_buyer.py`, `tests/test_storage_expand.py`

**Interfaces:**
- Consumes: `building_ops.deploy_new(kit, outpost_id, fresh=(), computer=None) -> (machine_id | None, status, message)`.

- [ ] **Step 1: Write the failing tests:** early_buyer with a raising deploy stops the loop without a crash and powers nothing; storage_expand with a raising deploy returns `"deploy error"`, stamps `settled[outpost_id]`, and logs no warn.
- [ ] **Step 2: Run** both files. Expected: FAIL (raise propagates).
- [ ] **Step 3: Switch both sites.** early_buyer: `new_id, status, message = building_ops.deploy_new(item_id, None, computer=computer)` (the game's `outpost=None` is home, docs/components/computer.md `.deploy`); `set_powered` gets `new_id`. storage_expand: drop the `hasattr(computer, "deploy")` probe, `deploy_new(type_id, outpost_id)`; `"no_computer"` returns `"no Ship Computer"`; `CALL_FAILED_STATUSES` return `f"deploy {status}"` without the warn; other refusals keep the warn with `message`.
- [ ] **Step 4: Run the full checks.** Expected: green; `grep -rn "computer\.\(deploy\|undeploy\|upgrade\)(" scripts/4_controlpanel/lib` hits only `building_ops.py` and comments.
- [ ] **Step 5: Update the docs** listed above.
- [ ] **Step 6: Commit** `refactor(building_ops): early_buyer and storage_expand deploy via deploy_new`.
