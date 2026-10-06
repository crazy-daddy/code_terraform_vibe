# Plan: building planner (`autoplay/`: deploy and undeploy machines inside outposts)

Status: **draft.** Decisions and the one open question are at the end.

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
     then **attach**: `scripts_sync` fills the new slot from the type template (decided 2026-10-06), the job
     confirms the machine reports in its status key. Once the game offers a script-side `save_variant`
     (requested from the dev), switch to `run_control.variants()` → `apply_variant()` → `start()` with a
     per-type `Autoplay` variant (see "Script attach" below).
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

## Script attach through variants (verified headless 2026-10-06)
- A deployed machine gets an empty script slot (`Main`, status `idle`). `run_control.variants(id)` lists Main
  plus the save's **exact-type** catalog (`scriptLibrary["machine:<typeId>"]`) and the family catalog, so a
  named variant saved once for a type is offered to every later machine of that type, new ones included.
- Headless run on the late save: seed an `Autoplay` variant for `smelter` (the editor's Duplicate Variant,
  command `script.saveVariant`, scope `type`); then a script did `computer.deploy("smelter")` → `smelter_14`,
  `run.variants()` = `[Main, Autoplay]`, `apply_variant` `ok`, `start` `ok`, status `running`, variant `Autoplay`.
  All inside the game, no file and no editor involved.
- Variants live in the save, not in the scripts folder (`docs/guide/editor_and_tools.md`, "Every file in the
  folder"), so a file placed there never becomes a variant. Seeding is one in-game step per machine type
  (Duplicate Variant on any machine of that type, scope exact type). The "External edit, Day N" entries in
  the late save's catalogs are conflict copies the game made, not a seeding path.
- Consequences: a variant is the same code for every machine of the type, so per-machine parameters
  (`smelter.py`'s `target_ore`, `pioneer.py`'s `${HOME_BASE}` placeholder) must come from the archive (the
  deploy job's params) instead of the slot's source. Keep variant bodies thin (import the controller, run it):
  `apply_variant` copies the code once, while Library changes still reach every machine through Apply.
- Pre-placed file (read in the UI bundle `internals/raw_assets/assets/main-*.js`, `scriptFileSync`; not run):
  the folder mirror is active whenever the scripts folder holds files, editor open or not. When the game
  writes a new script (`writeScript()`/`writeToDisk()`), a file already sitting at its canonical path with
  other content, unknown to the manifest and not in `abandonedPaths`, counts as an external change and is
  pulled in as the script's source (`applyDiskSource()`, log "pulled N from disk"). So a pre-placed
  `<prefix>_<serial>.py` becomes the new machine's **Main**, not a variant, and is not started. The serial is
  the highest existing or retired one + 1 (simworker `oh()`), so the file has to be written ahead for the
  right number, by the PC. Fallback only: the variant route needs no PC.

## Phases
1. Executor core + status table + tests on the shared fakes (`tests/game_stubs.py`): deploy, attach wait,
   retire handshake, restart adoption.
2. Move the existing undeploy call sites onto it (`plants_retire`, `biomass_retire`, Habitat retire, Refiner
   retire as its first consumer). No behavior change except the unified status handling.
3. Decider with the role-gap and Warehouse providers, **propose only** (archive + log, like founding phase 4),
   plus a simple BUILD Control Room card: one row per proposal (outpost, building, why, kit source, cost)
   with approve / reject buttons.
4. Execution behind approval: kit sourcing (Inventory, craft, Shop via cash manager), deploy, attach.
5. Count providers: Plant Terraformers, Smelter/Fab, power.
6. Headless validation on the owner's saves (`devtools/headless/`): early save fills a designated factory
   outpost, late save retires finished machines. Saves stay private.
7. Optional: move swaps and fleet commission onto the executor; relocation (empty, decommission, refound).

## Decisions (owner, 2026-10-06)
1. **Autonomy v1: proposals only**, approved on a simple BUILD card. The retire flows that already run on
   their own (Plants, Biomass, Habitats) stay automatic; new retire signals (Refiner, long-spare groups) start
   as proposals too.
2. **Script attach:** `scripts_sync` for now; variants once `save_variant` exists for scripts. Variants can
   only be saved in the UI today.
3. **Relocation:** rarely needed, out of scope. Undeploy puts the kit in Inventory, so a move is a retire job
   plus a deploy job; no separate flow.

## Open question: who decides counts
Outposts run no script of their own; only machines and Automations do. So "every outpost manages itself" means
either the outpost's machines decide, or one loop handles outposts one at a time.

**Central planner** (one coordinator owns the whole desired state)
- Pro: sees everything that is shared and scarce: cash, kits in Inventory, building caps, which outpost
  should host a machine. No two deciders claim the same slot or kit.
- Pro: one place to read why something was proposed; retire-before-deploy across outposts is easy.
- Con: one script carries all the work (step budget, slower reaction) and has to learn every domain's rules
  (Terraformer timeline, smelter demand, power balance), so it drifts towards a god object.
- Con: a domain change means touching the planner.

**Decentralised** (each domain or outpost decides and acts on its own)
- Pro: the rule sits next to the knowledge (the Plant code knows how many Terraformers it needs); scales
  by adding a provider, not by growing one file.
- Con: the deciders compete for the same cash, kits and slots, so they still need an arbiter, or they
  double-deploy and fight over caps.
- Con: coordination runs through archive keys (staleness, races), and deploy/retire churn can oscillate
  between two deciders; harder to see why a machine appeared.

**Recommended: hybrid, "market with one clearing house".** Domains post requests (`want N of type X`,
constraints such as biome or outpost, urgency, reason) into one archive key; only the building planner turns
them into proposals, picks the host outpost, and respects the cap and the cash manager. Same pattern the repo
already uses for money (`cash.can_spend()` with one priority list) and freight (`logistics_requests`). The
founding planner stays the only one deciding where new outposts go.
