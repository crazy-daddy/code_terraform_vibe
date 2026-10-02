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
docs/plans/fake_world.md"*. Each step section is self-contained. At the end of a step:
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

### - [ ] Step 3: Census devtool (optional)
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

### - [ ] Step 5: Migrate tests to the shared fakes
- **Goal:** remove private duplicates.
- **Read first:** `tests/game_stubs.py`, then only the test files in this session's batch.
- **Touch:** 1–2 test files per session, in this order: `test_turbine_commit`,
  `test_fuel_assembler`, `test_habitat`, `test_fleet_commission`, `test_fleet_decommission`, then
  the rest (list them in the notes as they are done).
- **How:** replace private fakes with shared ones; keep a local subclass for odd behaviour
  (e.g. `_FreshTurbine(game_stubs.Turbine)`). Each commit is behaviour-neutral: same assertions.
- **Done when:** the batch's files hold no class that duplicates a `game_stubs` export.
- **Verify:** `python -m unittest discover -s tests`.

### - [ ] Step 6: Sample world, guard test, docs
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

## Out of scope
- Running the real simworker JS as the test backend (full engine, needs a Python bridge).
- Simulating crafting, travel or power flow over time.
- Loading a real save as a test fixture (save-specific, not portable).
