# Plan: shared fake world from the game spec

## Context
`tests/game_stubs.World` (loaded by `tests/harness.py`) models only the production slice: Store
(Inventory / Warehouse / Large Warehouse), Smelter, Fabricator, SupplyDock, Orders, Notebook,
Clock, Console, OutpostNetwork, Journal (empty), Commander, Shop and ConstructionBlueprints.

- **Coverage gaps.** Services our code requests via `get_component()` but the World lacks:
  `power_control` (25 call sites), `transmitter` (16), `comms` (12), `fleet` (11), `nocturna` (9),
  `research` (8), plus `run_control`, `item_catalog`, `markers`, `computer` and the sensors.
  The live save has 48 machine type ids; the stubs cover about 6.
- **Duplication.** Test files hand-roll private fakes: `_Result` in 10 files, and `_Port`,
  `_Stack`, `_Recipe`, `_Power`/`_PowerControl`, `_Grid`/`_Member`, `_Tank`/`_Cask`, `Shop`,
  `Journal`, `RunControl`, `Fleet`, `Computer` in several. They drift from each other and from
  the game.
- **Drift found.** The stub `SupplyDock.set_order` returns `"not_found"`; the real contract is
  `["ok", "unknown_order", "completed", "cargo_present"]`. `lib/supply_dock.py` branches on
  `"unknown_order"`, so tests never reach that branch.

**Goal:** one shared fake world whose constants come from the real game tables, whose method
names, parameters and result statuses are checked against the real API contracts, and whose
coverage gaps are measured against a real save. New features extend this world instead of
adding private fakes.

## Sources
- **Decompiled game:** `internals/terraform_decompiled/simworker/deobfuscated.js` (8 MB,
  gitignored, so absent on cloud agents; everything derived from it is committed as
  `tests/game_spec.json`). Machine-readable parts:
  - **API registry:** method entries with `name`, `signature`, `params: [{name, type, ...}]`,
    `returnType`, `readonly`, `descriptionKey: components.<comp>.<method>` and
    `outcomeContract: B(\`<comp>.<method>\`, [\`ok\`, ...])` (about 167 contracts). Example near the
    `supply_dock.set_order` contract.
  - **Machine table** `const kg = [{id, building, category, powerDraw, scriptSlots, canPowerOff,
    passive, defaultData, ...}, ...]`.
  - **Storage table** `Eg`: warehouse 5 slots, large_warehouse 15 slots, 2000 units each.
  - **Recipe table** `const Ix = [{id, machine, inputs: [{itemId, count}], output, durationGameHours,
    powerDraw}, ...]`.
  - **Minified constants** such as ``const Un = `large_warehouse`;`` — table fields reference
    these names, so resolve them first.
- **Save:** newest `save_*.json` under `%APPDATA%\io.codeterraform.game` (same lookup as
  `devtools/scripts_sync.py`), **read-only**: `state.machines[*].typeId` counts,
  `state.planet.outposts`. Never commit save data.
- **Docs:** `docs/components/` for behaviour (port locality, power semantics). Where docs and
  the decompiled code disagree, the code wins; note the disagreement below.

## How to run this plan
One step per fresh session (`/clear` between steps). Prompt: *"Do step N of
docs/plans/done/fake_world.md"*. Each step section is self-contained. At the end of a step:
1. Check off its box here and the matching sub-item in `TODO.md` (Phase 7).
2. Append findings to **Notes from earlier steps** (drift found, unresolved fields, surprises).
3. Run `python -m unittest discover -s tests` and commit (caveman-commit, on main).

Before starting a step, read **Notes from earlier steps**: earlier steps record where the
result differs from the step text below (e.g. extra spec sections), and the notes win.

Order: 1 → 2 → (3, 4 in either order) → 5 (may span several sessions) → 6.

## Steps

### - [x] Step 1: Spec extractor and committed snapshot
- **Goal:** turn the decompiled tables into `tests/game_spec.json`.
- **Read first:** this doc's Sources; `devtools/scripts_sync.py` (style of a devtool, save lookup).
- **Touch:** new `devtools/extract_game_spec.py`, new `tests/game_spec.json`.
- **How:**
  - Resolve constants by regex: ``const NAME = `str`;`` and numeric `const NAME = 123;`.
  - API registry: find each `name: \`m\`` method object by brace matching; take `descriptionKey`
    for the component, `params[].name/type`, `returnType`, `readonly`, `outcomeContract` statuses.
  - Data tables (`kg`, `Ix`, `Eg`): slice the literal by bracket matching and evaluate it in a
    Node `vm` sandbox seeded with the resolved constants (Node is installed). Never execute the
    whole file. Getter fields (`get description() {...}`) and unresolvable references become
    `null` and are listed in an `unresolved` array.
  - Output shape: `{game_version, api: {comp: {method: {params, returns, readonly, outcomes}}},
    machines: {type_id: {...}}, recipes: [...], storage: {...}, unresolved: [...]}`. Sort keys
    so regenerations diff cleanly. Take `game_version` from the file if present, else the
    source file's mtime.
- **Done when:** about 167 methods carry `outcomes`; `storage` has warehouse 5×2000 and
  large_warehouse 15×2000; `smelt_iron_ingot` has `durationGameHours` 0.08; every `typeId` in the
  live save appears in `machines`.
- **Verify:** `python devtools/extract_game_spec.py` then spot-check the four facts above.

### - [x] Step 2: Contract test against the spec
- **Goal:** fail when a stub invents a method, misnames a parameter, or returns a status the
  real method never returns.
- **Read first:** `tests/game_stubs.py`, `tests/game_spec.json`, `tests/harness.py`.
- **Touch:** new `tests/test_stub_contract.py`; fixes in `tests/game_stubs.py`; a new test for
  the `unknown_order` branch of `lib/supply_dock.py` (in `tests/test_production.py` or a
  supply-dock test file).
- **How:** map each stub class to its spec component (explicit dict in the test, e.g.
  `SupplyDock → supply_dock`, `Store → warehouse` / `inventory`). For each public method:
  it exists in the spec, parameter names match. Collect literal `Result("...")` statuses per
  method via `ast` and assert each is in that method's `outcomes`. Test-only helpers (prefix
  `_`, or a small allowlist like `add`/`remove` on `Store`) are exempt.
- **Done when:** the test is green, `set_order` returns `unknown_order`, the lib branch has a
  test, and every other drift found is fixed or listed in the notes with a reason.
- **Verify:** `python -m unittest discover -s tests -p test_stub_contract.py -v`.

### - [x] Step 3: Census devtool (optional, dropped)
- **Goal:** a printed gap list to choose what to stub next.
- **Read first:** `tests/game_stubs.py`, `tests/game_spec.json`.
- **Touch:** new `devtools/stub_census.py` (prints only, writes nothing).
- **How:** combine (a) save `typeId` counts, (b) `get_component("...")` service names across
  `scripts/` and `autoplay/`, (c) what `game_stubs` models, (d) private fake class names per test
  file. Print one table sorted by save count / call count: name, count, stubbed yes/no, private
  fakes.
- **Done when:** it runs against the live save and prints the table.
- **Verify:** `python devtools/stub_census.py`; `git status` shows no new files outside the tool.

### - [x] Step 4: Consolidate and extend `game_stubs.py`
- **Goal:** shared fakes for everything tests currently hand-roll.
- **Read first:** `tests/game_stubs.py`, the private fakes in `tests/test_turbine_commit.py`,
  `tests/test_fuel_assembler.py`, `tests/test_habitat.py`, `tests/test_fleet_commission.py`;
  `docs/components/` for each new fake; the census output (step 3) if available.
- **Touch:** `tests/game_stubs.py`, `tests/harness.py` (`_reset_module_state` for any new
  service state), `tests/test_stub_contract.py` (cover the new fakes).
- **How:**
  - Shared primitives: `Result` (extra payload fields), `Stack`, `Recipe` (`fluid_inputs`), item
    and fluid `Slot`, `Tank`, `PowerControl` (grids, members, battery charge), `RunControl`,
    `Fleet`, `Computer`, `Comms` (`latest_info` with age).
  - Default services in `World.services`; builders `add_tank`, `add_battery`, `add_drone`,
    `add_pioneer`, `add_drone_depot`, `add_habitat`.
  - A small loader reads `tests/game_spec.json` once; new fakes default slot counts, capacities,
    `powerDraw`, recipes and `defaultData` from it. Keep the synthetic `SMELTER_RECIPES` /
    `FABRICATOR_RECIPES` where existing tests rely on their simple numbers.
  - Fakes stay state-only: a test sets state, then calls one controller step.
- **Done when:** existing tests still pass unchanged; contract test covers the new fakes.
- **Verify:** `python -m unittest discover -s tests`; Pyright on `tests/`.

### - [x] Step 5: Migrate tests to the shared fakes
- **Goal:** remove private duplicates.
- **Read first:** `tests/game_stubs.py`, then only the test files in this session's batch.
- **Touch:** 1–2 test files per session, in this order: `test_turbine_commit`,
  `test_fuel_assembler`, `test_habitat`, `test_fleet_commission`, `test_fleet_decommission`, then
  the rest (list them in the notes as they are done).
- **How:** replace private fakes with shared ones; keep a local subclass for odd behaviour
  (e.g. `_FreshTurbine(game_stubs.Turbine)`). Each commit is behaviour-neutral: same assertions.
- **Done when:** the batch's files hold no class that duplicates a `game_stubs` export.
- **Verify:** `python -m unittest discover -s tests`.
- **Parallel finish (remaining 14 files, one session):** the coordinating session starts four
  Sonnet subagents (not Haiku: deciding whether a private fake's behaviour differs from the
  shared one, and whether a changed assertion still means the same, needs judgement), each in
  its own worktree (`isolation: "worktree"`) so a half-edited file in one never fails another's
  test run. Groups, so each cold start reads `game_stubs.py` once for several files:
  - A, autoplay (`Result`, `Journal`, `Building`): `test_autoplay_fluid`,
    `test_autoplay_outpost_sites`, `test_autoplay_power`, `test_autoplay_survey`,
    `test_site_supply`.
  - B, power (`PowerControl`, `Stack`, `Clock`): `test_ingot_buffer`, `test_mining_drill`,
    `test_thermal_cap_parking`.
  - C, fluids (`Tank`, `FluidPort`): `test_reactor`, `test_wildlife_planner`,
    `test_ship_before_craft`.
  - D, misc (`Recipe`, `Store`, `Drone`): `test_feed_maker`, `test_harvester_amplify`,
    `test_drone_weather`.

  Agent rules: edit only the group's test files; never `tests/game_stubs.py`, the contract test
  or this plan. Where a shared fake lacks a method or behaviour, keep a small local subclass of
  it and report the gap (what, which docs/spec entry). Keep every assertion's meaning; report
  any assertion that had to change and why. Run the full suite in the worktree. Report: files
  changed, fakes replaced, local subclasses kept, gaps, changed assertions, notes for this plan.
  The coordinator then reviews each diff (watch for weakened assertions), cherry-picks the
  worktrees, moves reported gaps into `game_stubs.py` (with contract-test coverage) in one pass,
  drops the local subclasses that covered them, appends the notes, runs the suite and Pyright on
  `tests/`, and commits per group.

### - [x] Step 6: Sample world, guard test, docs
- **Goal:** keep the shared world the default from now on.
- **Read first:** `tests/sample_world.py`, `tests/test_sample_world.py`,
  `docs/cheatsheet/dev_workflow.md` (testing section).
- **Touch:** `tests/sample_world.py`, new guard test (e.g. `tests/test_no_private_fakes.py`),
  `docs/cheatsheet/dev_workflow.md`.
- **How:**
  - Add the new types (tanks, batteries, drones, pioneers, depots, habitats) to
    `sample_world.SIZES`; set "large" from the census numbers.
  - Guard: a test file may not define a class named like a `game_stubs` export (with or without
    a leading `_`) unless it subclasses it.
  - Docs: extend `game_stubs` instead of adding private fakes; rerun
    `devtools/extract_game_spec.py` after a game update and review the `game_spec.json` diff;
    `devtools/stub_census.py` shows gaps.
- **Done when:** guard test green; `devtools/step_profile.py` still runs on "large".
- **Verify:** `python -m unittest discover -s tests`.

## Notes from earlier steps
### Step 1 (2026-10-02)
- Tool is two files: `devtools/extract_game_spec.py` (wrapper, save check, writes the JSON) and
  `devtools/extract_game_spec.js` (Node evaluator). The evaluator slices a top-level definition
  only when an evaluated literal reads it, so helper calls like `B(...)`, `Zk(...)`, `OA(UA)`
  run their real code; nothing else in the file runs.
- Result for build `3b1b03e`: 92 components / 791 methods, 186 with `outcomes` (more than
  the 167 `B(...)` calls because helper-built contracts such as `SonarScanResult` and
  `TransferResult` resolve too); 69 machines; 99 recipes; storage as expected; 0 unresolved;
  all 48 save typeIds present.
- Added a `types` section that the plan did not list: the 171 object types that component calls
  return (`InputSlot`, `ItemStack`, `NavModule`, `DockSlot`, `PowerGrid`, ...), with the same
  entry shape. 39 more `outcomes` live there (`InputSlot.connect`, `NavModule.set_target`, ...).
  Step 2/4 fakes for slots, stacks and modules should check against `types`, not `api`.
- Entry fields beyond the plan: `signature`, `result_type`, `payload_fields` (extra result
  fields such as `requested`/`moved`), `property: true` for attributes (`ItemStack.count`),
  and `contract_kind: "optional"` for 3 methods that return None instead of a status
  (`power_control.grid`, `crop_automator.cell`, `crop_automator.current_job`).
- `pioneer.constructor` is a method name that collides with `Object.prototype.constructor`; the
  evaluator uses prototype-free dicts for that reason.
- Not in the spec: the `panel.*` API (UI panels) and the global API functions (`GA` table:
  `boot()`, `activate_power()`, `activate_sensors()`, `get_game_version()`, ...). Of the file's
  240 `outcomeContract` occurrences, the spec holds 225; the rest are 3 contracts on those
  global functions, 3 identical repeated registrations, and 9 code references (validators
  reading `.outcomeContract`), not contracts. Add a `functions` section from `GA` if a fake ever
  needs the cold-boot calls.

### Step 2 (2026-10-02)
- `tests/test_stub_contract.py` maps stub classes in two dicts: `COMPONENTS` (methods checked:
  name, positional parameter names, literal `Result("...")` statuses incl. both branches of a
  conditional) and `VALUE_TYPES` (public `self.x` attributes in `__init__` checked against the
  type's fields). A stub class in neither dict nor `NOT_API` fails the test, so step 4 must
  map every new fake. A union mapping (`Store` → warehouse + inventory, `Slot` → InputSlot +
  OutputSlot) passes a method found in any entry. Parameters match by position as a prefix, so
  a stub may omit trailing optional real parameters (`properties`, `channel`, ...).
- Run it with `python -m unittest discover -s tests -p test_stub_contract.py -v`; the
  `tests.test_stub_contract` form fails because `tests/` is not a package.
- Statuses produced dynamically (`Result(status)`) are invisible to the check. `Slot` port
  methods therefore map `World.local_store()`'s problem code (`no_connection` / `not_found` /
  `not_local` / `inventory_not_local`) to literal statuses per side.
- Drift fixed in `game_stubs.py`: `SupplyDock.set_order` (`unknown_order`, plus `completed` for
  a completed order); `SupplyDock` no longer inherits recipe methods (new `Building` base);
  `Store.compact` → `already_compact` (was `no_op`); port statuses `not_connected` →
  `no_connection`, `empty` → `source_empty`, `not_found`/`not_local` → `source_missing` /
  `source_not_local` (take) and `target_missing` / `target_not_local` (send, eject),
  `inventory_not_local` for Inventory away from home, new `buffer_full` when the input buffer
  has no room; renamed params `set_recipe(recipe_or_id)` (now also accepts a Recipe),
  `set_enabled(on)`, `buy(item_id, quantity)`, `print(message, ...)`, `connect(name)`,
  `eject(destination, ...)`, `surveyed_sites/cataloged_creatures(planet_id)`;
  `Slot.count()` takes no item id (real API); `Notebook.keys(prefix=None)`;
  `CatalogueEntry` → `ShopItem` (adds `name`); inline `DockSlot` type → class with `index`;
  test-only `Store.used`/`Machine.input_used` → `_used`/`_input_used`.
- Exempt helpers: `Store.add/remove`, `Console.text` (`TEST_HELPERS`). `Slot` and machine
  state attributes (`buffer`, `connect_log`, `running`, ...) are not checked: attributes are
  checked only for `VALUE_TYPES`.
- No lib code branched on the old stub-only statuses; all tests passed unchanged.
  `tests/test_fleet_commission.py` has its own private `CatalogueEntry` (step 5 should use
  `game_stubs.ShopItem`).
- Pyright on the new test reports `ast` narrowing errors (`Cannot access attribute "func"
  for class "AST"`); `tests/test_log_blocks_balanced.py` shows the same, so it is the local
  Pyright setup, not the code.

### Step 4 (2026-10-02)
- Step 3 (census) was skipped; the fake list came from the plan and a scan of private fake
  class names in `tests/`.
- New in `game_stubs.py`: spec loader `game_spec()` / `machine_spec()` / `default_data()` /
  `spec_recipe()` / `spec_recipes()`; `Result(**payload)` for extra fields (`machine_id`,
  `message_id`, `packet`, `count`); `Recipe` gains `name` and `power_draw`; `Position`,
  `FluidPort`, `Tank` (gas/liquid), `BatteryBank` (the `battery` building), `SteamTurbine`,
  `PowerGrid` / `PowerGridMember` / `PowerSummary` / `PowerControl`, `RunControl`, `Comms` +
  `BroadcastInfo` / `CommsMessage`, `MobileUnit` → `Drone` / `Pioneer` with `Cargo`,
  `VehicleBattery` / `DroneBattery`, `MountSlot`, `UnitRef` (DroneRef / VehicleRef /
  MobileUnitRef), `Fleet`, `Computer`, `DroneDepot`, `Habitat` + bonus tree / node / insight.
  Builders: `add_tank`, `add_battery`, `add_turbine`, `add_grid`, `add_drone`, `add_pioneer`,
  `add_drone_depot`, `add_habitat`.
- Default services `power_control`, `run_control`, `fleet`, `computer`, `comms` are also typed
  `World` attributes (`world.power_control`, ...), so tests reach them without Pyright
  complaints. `World.get_component()` now checks `components` before `services`: a test that
  places a private fake under a service id (`components["power_control"]` in
  `test_mining_drill.py`) still wins over the default.
- Semantics worth knowing: `PowerGrid.members` and `stored` / `capacity` are rebuilt from the
  world on each read (stored = member `BatteryBank` charge unless the test passes it);
  `PowerControl.is_powered` defaults to True, `set_powered` answers `not_found` for an unknown
  id and `not_toggleable` when the spec's `canPowerOff` is false. `RunControl.start/stop`
  answer `not_found` for ids that are no component. `Computer.deploy` needs the kit in
  Inventory and creates a `Drone` (any `instancePrefix == "drone"` machine) or `Pioneer`;
  `forced_status` overrides every answer. Comms broadcast ages do not advance with the clock;
  the test helper `Comms.publish(channel, value, age_seconds)` sets one. Drones and pioneers
  carry `_mobile = True`, so `OutpostRef.buildings()` skips them like the game does.
- Units follow the docs: `Tank.fill_pct()` and `VehicleBattery.level()` are 0-1 fractions,
  `DroneBattery.level()` and `BatteryBank.get_level()` are Wh. `test_turbine_commit.py`'s
  private `_Tank.fill_pct()` returns a percent (90.0); `lib/turbine_commit.py` accepts both,
  so step 5 can pass 0.9 to `Tank` with the same result.
- Shared methods sit in their own spec entries: `transfer_to` of Warehouse, Storage Bin and
  Lead Cask is listed once under `api.passive_storage`, not under each component. Map a fake to
  that entry too (`Store` and `LeadCask` do). The fakes share a `PassiveStore` base with
  `transfer_to` (locality, `same_storage`, hot-cargo rules via `HOT_ITEMS`); `LeadCask` latches
  to one hot item, 100 units; builder `add_lead_cask`. `World.local_store()` resolves any
  `PassiveStore`, so machine ports can take from a cask.
- Not added: item `Slot` variants with `eject` side logs (`test_habitat.py`'s `_Port`), and
  `_Power` stand-ins for `lib/power.py` helpers (those fake our own module, not the game).
- `harness._reset_module_state` needed nothing: all new state lives on the per-test `World`.
- The contract test maps every new class (`COMPONENTS` / `VALUE_TYPES`, `MobileUnit` in
  `NOT_API`, `Comms.publish` in `TEST_HELPERS`) and adds `SharedFakeTests` (spec defaults,
  grid members and power switches, deploy and fleet refs, comms).
- `World.local_store()` narrows with `store is None or not isinstance(...)`: with the typed
  components the repo's Pyright config no longer narrows `isinstance` alone there.

### Step 5 (2026-10-03)
- Done: `test_turbine_commit`, `test_fuel_assembler`, `test_habitat`, `test_fleet_commission`,
  `test_fleet_decommission`, `test_plants_retire`, `test_script_parking`, `test_refiner`
  (2026-10-03). Next, by count of private classes named like a `game_stubs` export:
  `test_site_supply`, `test_reactor`, `test_mining_drill`, `test_ingot_buffer`,
  `test_feed_maker`, `test_autoplay_power` (2 each), then the single-class files
  (`test_wildlife_planner`, `test_thermal_cap_parking`, `test_ship_before_craft`,
  `test_harvester_amplify`, `test_drone_weather`, `test_autoplay_survey`,
  `test_autoplay_outpost_sites`, `test_autoplay_fluid`). `test_habitat`'s `_Shop` / `_Journal`
  are subclasses and stay.
- `test_turbine_commit`: turbines via `add_turbine` (pass `output=108.0`; the shared default is
  0), source tanks as `gas_tank` with `capacity=100.0` and level 90 (fill 0.9), grids via
  `add_grid(..., stored=1000.0, capacity=1000.0)`, `world.power_control` for switches (a
  player-off turbine is `power_control.powered[id] = False`). `_FreshTurbine` needed no subclass:
  `add_turbine(..., output=0.0, throttle=1.0)`. A test with two steps mutates the grid's
  `consumed` / `generated` between them.
- `test_fuel_assembler`: casks are `LeadCask` (`add_lead_cask`; `.units` → `.count(item)`,
  `put` → `add`); ports are `Slot`. Two local classes stay because `game_stubs` has no such
  machine: `_Consumer(Building)` (reactor / Mk IV terraformer with `tier()`, 4-unit magazine)
  and `_Assembler(Machine)` (records recipe calls, `get_progress`, `get_stockpile` without zero
  entries). Its `stock_pile` / `out` became `input_buffer` / `output_buffer`. `_Power` stays: it
  stands in for `lib/power.py`, not the game. `_PowerService` became `add_grid("grid_a",
  ["fuel_assembler_1"])`.
- A shared `Slot` sending into a cask of the wrong material answers `target_full` (moved 0),
  where the private fake said `target_wrong_material`; `lib/fuel_assembler.py` only logs the
  status, so no test depends on it.
- `game_stubs` changes for the second batch: new `FluidConnection` (`types.FluidConnection`);
  `FluidPort.links` is what `connections()` returns while connected. Drift fixed:
  `Habitat.purge_intake(port=None)` takes `"gas_in"` / `"liquid_in"` (it compared against
  `"gas"`) and vents both on None; `Shop.buy` puts the purchase in Inventory and answers
  `inventory_full` (docs/components/shop.md). `Habitat.intake` starts at None (never set), so
  a test asserting an intake of 0.0 proves the controller set it.
- `test_habitat`: a `habitat()` helper on the test case builds the shared `Habitat` with the
  old fake's defaults (capacity 175000, headroom 100, "thriving", 2.5 insight, `<s>_a`
  adaptation / `<s>_b` breakthrough nodes). The shared Habitat's feed item is fixed at
  creation, so an empty habitat takes `revive=<species>` to set it. "Awaiting insight" is
  insight 0 instead of a patched `unlock_bonus`. The wrong-feed test checks Inventory and the
  input buffer (shared `Slot.eject` keeps no log). `_Shop(Shop)` and `_Journal(Journal)` are
  local subclasses; `_Cash` (fakes `lib/cash.py`) and `_Creature` (no shared type yet) stay.
- `test_fleet_commission`: shared `Fleet`, `Computer`, `RunControl`, `Shop` (price 10 per
  item), `Commander(credits)`. `Computer.calls` entries carry the verb (`("deploy", item,
  outpost)`), `next_status` → `forced_status`, and `deploy` needs the target outpost to exist,
  so `setUp` adds `outpost_2`.
- `game_stubs` changes for the third batch: `Computer.undeploy` follows
  docs/components/ship_computer.md: it removes any component with a `type_id` (a `PassiveStore`
  answers `not_undeployable`), checks `cargo_present` only for a `Cargo`, and returns the kit
  plus a unit's mounted modules and portables to Inventory. New `Shop.sell(item_id,
  quantity=1)` (`no_stock`, `not_sellable` from a `not_sellable` set; credits the commander at
  `prices`; payload `item_id` / `units` / `credits`; `Shop.sold` totals sales). New
  `Pioneer.uninstall` / `unmount` (Inventory gets the part; `holder_not_empty`,
  `internal_slot_empty`, `slot_empty`, `inventory_full`). The contract test's
  `test_pioneer_strip_undeploy_and_sell` covers them.
- `test_fleet_decommission`: pioneer via `add_pioneer(slots=pioneer_slots())` (`MountSlot`,
  fresh per test), drone via `add_drone(station="depot_1")` with a `battery_pack` mount, depot
  via `add_drone_depot`; shared `Fleet` / `Computer` / `RunControl`; `Shop(world, {part: 10})`.
  Cargo aboard is `cargo.items[...]`, an undocked drone is `station = ""`, a vanished machine is
  `del world.components[...]`. `StripVehicle` became the shared Pioneer; `StripHost` stays
  (it hosts the `VehicleClaimsMixin` under test).
- `test_plants_retire`: shared `Computer` and `RunControl`; `_Terraformer` gains `type_id` and is
  put in `world.components` so `undeploy` finds it. "Script restarted" is
  `run_control.running`, not a `started` log. Don't name a test attribute `self.run`: it
  shadows `TestCase.run` (Pyright flags it). `_Terraformer` / `_Input` / `_Outpost` stay (no
  shared plant terraformer yet).
- `game_stubs` changes for the fourth batch: `World.add_building(id, outpost, type_id, cls=Building)`
  places a plain `Building` (or a test's `Building` subclass, typed as that subclass) of any
  spec type, for machines without their own fake. `Recipe` gains `fluid_outputs`,
  `input_fluid`, `output_fluid` (`types.Recipe` fields), filled by `spec_recipe()`.
- `test_script_parking`: shared `PowerControl` / `RunControl` / `add_grid`; machines via
  `add_building` with real type ids. Grid members' `powered` comes from
  `power_control.powered`, so the old extra `member.powered = False` lines are gone.
  `set_powered` answers `not_found` for a machine that is no component, so a test that wakes
  parked machines must place them (grow lamp, sprinkler). Extra grid members are appended to
  `grid.machine_ids`. The pump / cap stand-ins are `Building` subclasses; `_FakePower` stays
  (fakes `lib/power.py`). The spec says `solar_generator` can power off (the old fake said
  no); no test relies on it.
- `test_refiner`: recipes are `spec_recipe("refine_*")` (same tar / port numbers as the old
  synthetic ones); ports are shared `FluidPort(capacity=10.0)` and `Slot` over
  `input_buffer["tar"]`. `_Refiner(Building)` stays (no shared refiner); `_Router` stays (it
  fakes our own routing helper).

- Parallel finish (2026-10-03): four Sonnet worktree agents as planned, rebalanced first.
  `test_wildlife_planner` already had no private fakes and was dropped; `test_site_supply`
  moved from group A to B (A had 5 files, B 3 light ones). No assertion was weakened.
- Gap pass in `game_stubs`: `Journal(surveyed=(), discovered=(), creatures=())` with
  `discovered_sites()` (journal.md); `Clock(seconds_per_hour=25.0)` with
  `real_seconds_per_hour()` (clock.md; 25 matches the `exotic_cap` / `thermal_cap` fallback,
  so `test_exotic_cap` keeps its numbers); `Slot.connected` starts as `""` (spec:
  `connected_id` returns `string`, like `FluidPort`), and `World.local_store()` treats any
  falsy target as `no_connection`. This dropped the local `Journal` subclasses (autoplay power /
  fluid / outpost sites, site supply, habitat) and the `Clock` subclasses (reactor, thermal cap).
  `test_smelter` and `test_ship_before_craft` now assert `connected_id() == ""` for a
  disconnected port.
- `test_autoplay_power` / `test_autoplay_fluid` (group A): `Pos` → `Position`, `Job(Construction)`,
  `Grid(PowerGrid)` / `Power(PowerControl)` over fixed grid lists with no world, `Blueprints` /
  `ProbeBlueprints(ConstructionBlueprints)` with answer queues; blueprint plan results are
  `Result("ok", blueprint_ids=[...])`. `test_autoplay_extractor` (in no group) imports
  `Result`, `Job`, `Site`, `Journal`, `Power`, `Grid` and both `Blueprints` from these files and
  sets `.jobs`; the positional-ids `Result` subclass, `Power` and the `jobs` property (alias of
  `pending`) stay for it. Migrate it to direct `game_stubs` imports, then drop those shims.
- Group B: `test_mining_drill` puts `_Drill(Building)` on a grid with `add_building(...,
  cls=_Drill)` + `add_grid(id, [id])`; the default `world.power_control` replaces its private
  one. `test_ingot_buffer` reads `world.power_control.calls`.
- Group C: `test_reactor` uses `add_lead_cask`, `Slot` (rod input, capacity 10), `add_tank`,
  `FluidPort`; `_SimReactor(Building)` stays. The test that moves the tank level writes
  `tank._level` (no public setter). Shared `FluidPort.connect()` answers `not_found` for a
  non-component id where the private fakes said `ok`; no test depended on it.
- Group D: `_FeedMaker(Machine)` (adds progress / stockpile / `tier()`), `_Drone(Drone)` (scripted
  `collect()`, `exposure()`), `_Store(Store)` (fixed `transfer_to` answer, incl. Auto Feeder
  `busy`). Feed maker eject assertions check Inventory instead of an eject log.
- Open gaps, kept as local subclasses (candidates for a later pass, each with contract-test
  coverage): `ConstructionBlueprints.plan_power_line` / `plan_pipe` / `plan_bridge` /
  `mark_deconstruct` / `cancel` (construction_blueprint.md); `Drone.collect` / `exposure`
  (drone.md); a `FeedMaker` fake (spec `feed_maker`); a `Tank` level setter; a surveyed-site
  value type (`kind`, `pump_id`, `cap_id`, `medium`, ...); thermal / exotic cap fakes;
  `PowerGrid` described by outpost ids without placed buildings; `OutpostRef.x` / `.y`.
  `Store.transfer_to` answering `busy` is documented only in `lib/field_keeper` comments.

### Step 6 (2026-10-03)
- `sample_world.SIZES` gains `tanks`, `batteries`, `depots`, `drones`, `pioneers`, `habitats`.
  Step 3's census was never built, so "large" takes the live save's counts read directly from
  `state.machines` (gas_tank + bulk_liquid_reservoir 35, battery + battery_large 18,
  drone_station_large 7, drone_small/large 17, pioneer 4, habitat 16). The older keys
  (outposts, warehouses, ...) keep their guesses so earlier `step_profile` numbers stay
  comparable; the live save has 9 outposts and 27 Large Warehouses against "large"'s 4 and 5.
  Tanks alternate `gas_tank` / `liquid_tank`, batteries `battery_large` / `battery`; every
  4th drone is undocked (`traveling`); one grid per outpost spans its non-mobile buildings.
  Habitat species and feed items are synthetic (`species_<n>`, `feed_<species>`).
- Guard `tests/test_no_private_fakes.py` (AST): a class in a `test_*.py` file (top-level or
  nested) named like a `game_stubs` class, with or without leading `_`, must list that class
  as a base; `from game_stubs import X as Y` aliases count as X. It found three: a nested
  `Recipe` in `test_autoplay_outpost_needs` (now `game_stubs.Recipe`), a nested `Store` in
  `test_autoplay_survey` that faked our `lib/archive.py` (now `_Archive(Notebook)`), and
  `test_autoplay_power`'s `Result(BaseResult)` (a subclass under an alias; passes).
- `devtools/step_profile.py`'s `raw_demands` target called the removed
  `production.get_raw_material_demands()` (commit 12241b2) and crashed every all-targets run;
  it is now `demands` over `get_material_demands()`. All targets run on "large".
- Step 3 dropped (2026-10-03): the guard test covers private fakes, save counts were a
  one-off read, and a print-only tool rots unseen. Its one lasting use, services our code
  requests that `game_stubs` does not fake, is `tests/test_service_coverage.py`: it walks
  `scripts/` and `autoplay/` for literal `get_component("...")` ids (skipping machine and
  outpost ids like `battery_1` / `outpost_home`) and fails on any service that `World` does
  not fake and `KNOWN_GAPS` does not list, and on stale `KNOWN_GAPS` entries. Gaps at
  creation: transmitter, nocturna, research, markers, item_catalog, atmosphere and the
  sensors (thermometer, plants / pressure / oxygen / biomass).
- Pyright on new AST code reports `Cannot access attribute ... for class "AST"` after
  `isinstance` checks, as in `test_stub_contract.py` / `test_game_imports.py`: a config issue.

## Out of scope
- Running the real simworker JS as the test backend (full engine, needs a Python bridge).
- Simulating crafting, travel or power flow over time.
- Loading a real save as a test fixture (save-specific, not portable).
