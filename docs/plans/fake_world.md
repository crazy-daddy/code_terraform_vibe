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

Order: 1 → 2 → (3, 4 in either order) → 5 (may span several sessions) → 6.

## Steps

### - [ ] Step 1: Spec extractor and committed snapshot
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

### - [ ] Step 2: Contract test against the spec
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
- **Verify:** `python -m unittest tests.test_stub_contract -v`.

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

### - [ ] Step 4: Consolidate and extend `game_stubs.py`
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
_(empty — each step appends here)_

## Out of scope
- Running the real simworker JS as the test backend (full engine, needs a Python bridge).
- Simulating crafting, travel or power flow over time.
- Loading a real save as a test fixture (save-specific, not portable).
