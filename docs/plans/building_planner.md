# Plan: building planner (`autoplay/`: deploy and undeploy machines inside outposts)

Status: **draft, no decisions taken yet.** Open questions for the owner are at the end.

## Context
The autoplayer can now place map infrastructure ([autoplay_infra_planner.md](autoplay_infra_planner.md)) and
propose outposts with designated roles ([outpost_founding_planner.md](outpost_founding_planner.md)). Nothing
fills those outposts. The founding plan names this as the next plan: "Deploying machines into outposts is out
of scope (next plan: building planner)", and the gap between designated roles and observed buildings
(`autoplay_roles.role_gaps()`) is meant to become its backlog.

What the code does today (2026-10-06):
- **No code deploys a production machine.** `computer.deploy()` is only called for vehicles and drones
  (`lib/fleet_commission.py`, `lib/fleet_upgrade.py`) and for the small→large swaps
  (`lib/building_swap_upgrade.py`: Large Warehouse, Large Liquid Tank). Every Smelter, Fabricator, Plant
  Terraformer, Habitat, Feed Maker, turbine and Refiner is placed by hand.
- **Undeploy is done in five places, each with its own status handling**: `plants_retire.py`,
  `biomass_retire.py`, `wildlife_planner.py` (Habitats), `fleet_decommission.py`, plus the swap and fleet
  upgrade flows. `TRANSIENT_UNDEPLOY_STATUSES` exists in four copies with different contents
  (`docked_drone` in one, `cargo_present` missing in another).
- **Some retire signals have no consumer.** A Refiner publishes `retire: "ready"` in `refiner.status`
  "for the planner to undeploy it" (`lib/refiner.py`), but nothing reads it. `lib/machine_activity.py`
  already counts spare members per machine group (`retire`), shown on the activity panel only.
- Machine counts the engine wants already exist as models but nobody acts on them: Mk II Terraformer count
  over time (PR #27 timeline), Warehouse slots per role (`autoplay_roles.stock_slots()`), Smelter/Fab host
  full (`outpost_needs` "soon" signal).

So the deploy/undeploy manager is the missing link between "the engine knows what it wants" and "the outpost
has it". It is the next piece for tier 4+ autonomy.

## Shape: one executor, one decider
Same split as the infra planner (`blueprint_queue.py` executes, the passes decide).

1. **Executor** `lib/building_ops.py` (shared lib, so the retire flows in `scripts/` can use it too).
   One job dict per request in the archive (`build.jobs`), restart-safe, stepped by whoever owns the loop:
   - `deploy(type_id, outpost, requester, why)`: kit in Inventory, else crafted through
     `fabricator.upgrade_orders`, else bought via `cash.can_spend(requester)`; snapshot-then-deploy so a restart
     adopts the new machine instead of deploying twice (the trick `fleet_commission` and the swaps already use);
     then **attach**: a deployed machine has no script, so the job waits for `scripts_sync` to fill the slot
     (template per type) and confirms the machine reports in its status key.
   - `retire(machine_id, requester, why)`: asks the machine's own script to empty itself (eject is self-only),
     waits for its `ready` flag, then `undeploy()`. Generalises the plants/biomass/Refiner handshake.
   - `decommission(outpost)` once every machine is gone (relocation, later).
   - One status table: `ok`, transient (`inventory_full`, `cargo_present`, `docked_drone`,
     `construction_dependency`, `drone_station_full`), fatal (`deploy_limit`, `duplicate_outpost_machine`,
     `wrong_biome_for_machine`, `location_not_found`, `not_deployable`, `locked`, `not_undeployable`). Replaces
     the four copies.
2. **Decider** `autoplay/lib/building_plan.py`. Builds a desired state `{outpost_id: {type_id: count}}` from
   providers, diffs it against observed buildings, and turns the diff into executor jobs.
   - Providers, each living next to its domain (no central guesswork):
     - role gaps: one of each building a designated role lacks (`role_gaps()`);
     - Warehouses: `stock_slots()` / `site_slots()`;
     - Plant Terraformers: count from the Plants/Wildlife timeline;
     - Smelter/Fabricator: host-full signal and order backlog from production demand;
     - power: turbines/generators from the grid balance (`power.py`);
     - retire: completion flags (Plants, Biomass, Wildlife, Refiner) and long-spare groups from
       `machine_activity`.
   - Gates: building cap (never over cap at an outpost with a penalized machine, founding plan §capacity),
     biome locks, cash manager priority (new consumer `building_plan`), kit availability, phase.
   - Order: retire before deploy (frees slots and kits), urgent `now` needs before `soon`.

`CODE_GUIDES.md#scope` gets one line: deploying machines into outposts happens only in `autoplay/`; machine
scripts keep only "undeploy machines whose step is finished", through the executor.

## Phases
1. Executor core + status table + tests on the shared fakes (`tests/game_stubs.py`): deploy, attach wait,
   retire handshake, restart adoption.
2. Move the existing undeploy call sites onto it (`plants_retire`, `biomass_retire`, Habitat retire, Refiner
   retire as its first consumer). No behavior change except the unified status handling.
3. Decider with the role-gap and Warehouse providers, **propose only** (archive + log, like founding phase 4).
4. Execution behind approval: kit sourcing (Inventory, craft, Shop via cash manager), deploy, attach.
5. Count providers: Plant Terraformers, Smelter/Fab, power.
6. Headless validation on the owner's saves (`devtools/headless/`): early save fills a designated factory
   outpost, late save retires finished machines. Saves stay private.
7. Optional: move swaps and fleet commission onto the executor; relocation (empty, decommission, refound).

## Open questions for the owner
1. **Autonomy v1.** Propose + approve for new deploys (like founding), automatic for retires? Recommended: yes.
2. **Script attach.** New machines only run once `scripts_sync watch` fills their slot from the type template.
   Is "the PC sync must be running" acceptable for now? Recommended: yes; the headless runner can attach
   directly for tests.
3. **Counts.** One provider per domain next to its own code (recommended), or one central count model?
4. **Relocation** (move machines to another outpost, decommission the old one): in scope now or later?
   Recommended: later.
