# Plan: building planner (`autoplay/`: deploy and undeploy machines inside outposts)

Status: **draft.** Owner decisions are at the end.

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
   retire handshake, restart adoption. **Done** (`lib/building_ops.py`, autoplay.md §11k).
2. Move the existing undeploy call sites onto it (`plants_retire`, `biomass_retire`, Habitat retire, Refiner
   retire as its first consumer). No behavior change except the unified status handling. **Done**; `fleet_decommission`
   keeps its own bounded retry count (a repeated `cargo_present` there blocks the entry), swaps stay until step 7.
3. Decider with the role-gap and Warehouse providers, **propose only** (archive + log, like founding phase 4),
   plus a simple BUILD Control Room card: one row per proposal (outpost, building, why, kit source, cost)
   with approve / reject buttons. **Done** (autoplay.md §11l): approval already queues executor jobs; kit
   sourcing (Shop, craft) is still step 4.
4. Execution behind approval: kit sourcing (Inventory, craft, Shop via cash manager), deploy, attach.
5. Count providers: Plant Terraformers, Smelter/Fab, power.
6. Headless validation on the owner's saves (`devtools/headless/`): early save fills a designated factory
   outpost, late save retires finished machines. Saves stay private.
7. Optional: move swaps and fleet commission onto the executor; relocation (empty, decommission, refound).

## Training data: manual runs
A manual run on a scored seed gives reference decisions for the providers and start points for headless
runs. `devtools/decision_recorder.py` watches the save file from outside the game (no script slot), logs each
change, asks in the terminal for a reason at major changes (new outpost, tech, milestone achievement, first
machine of a type or tier) and copies the save there. Output goes to
`internals/sample_saves/<YYYYMMDD>_<commit>/` (private submodule, so saves stay private). Autoplay stays propose-only during such a run, so the log holds the
player's choices, and each proposal sits next to what the player actually did.

## Decisions (owner, 2026-10-06)
1. **Autonomy v1: proposals only**, approved on a simple BUILD card. The retire flows that already run on
   their own (Plants, Biomass, Habitats) stay automatic; new retire signals (Refiner, long-spare groups) start
   as proposals too.
2. **Script attach:** `scripts_sync` for now; variants once `save_variant` exists for scripts. Variants can
   only be saved in the UI today.
3. **Relocation:** no separate flow. Undeploy puts the kit in Inventory, so a move is a retire job plus a
   deploy job, proposed as one pair (phase evictions below). Decommissioning whole outposts stays out of scope.

## Count ownership (owner, 2026-10-06): hybrid, market with one clearing house
Domains post requests (`want N of type X`, constraints such as biome or outpost, urgency, reason) into one
archive key; only the building planner turns them into proposals, picks the host outpost, and respects the
cap and the cash manager (same pattern as `cash.can_spend()` and `logistics_requests`).

**The planner also issues its own requests for phase changes**, which no machine can see from its local view:
it reserves slots for roles the next phase needs and evicts machines that still have work. Example: the
early Smelter at home is busy, but home slots will be needed later for Feed Makers and Habitats, so the
planner proposes a move (retire at home + deploy at a factory outpost, paired as one proposal so the
smelter is not lost in between). Home's slot budget and its "home only until wildlife is unlocked" rule
come from the founding planner (`outpost_needs.plan_hosts()`), so both planners share one view of which
roles belong where. The founding planner stays the only one deciding where new outposts go.

Why this split, and what was weighed against it:
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


## Where it runs: one planner loop, separate passes (approved by the owner 2026-10-06)
Question: merge the founding planner and the building planner into one "grand unified autoplayer", or run
them side by side and talk through the archive? Answer: **one Automation and one loop, separate modules.**
The building decider becomes another pass in `planner_loop.run_planner()`, after the founding pass and before
the infra passes. Neither a merged god-module nor a second planner script.

Why one loop:
- **No step gain from two scripts.** The base shares 50,000 steps per tick; a second script only splits it
  (dev_workflow §1d-1, "Don't split work into helper scripts for throughput"). Heavy pure work already runs in
  `run_batched` slices either way.
- **One snapshot, one ordering.** `outpost_needs.snapshot()` (outposts, kits, recipes, stock) is the costly
  read both planners need. In one loop it is read once per pass, and a designation the founding pass writes is
  seen by the building pass in the same pass. Two scripts would read it twice and race (founding re-designates
  home while the building planner proposes an eviction from the old view).
- **Precedent:** `run_founding()` and `run_planner()` already must not run together because both own the same
  proposals and markers. Two planners owning outposts would repeat that.

Why separate passes, not one merged module: each pass keeps its own proposals key and UI (founding: map
markers; building: the BUILD card), its own tests, and can be switched off alone. The central planner's Con above
("drifts towards a god object") is avoided by keeping the domain rules in providers and shared libs.

The archive stays the interface where the other side really is another script: domain requests in (the
market), executor jobs and machine status out (`build.jobs`, retire `ready` flags). Planner to planner talks
in process.

What changes in the loop: `run_planner()` ends today once nothing is left to plan. With a building pass it
becomes long-lived: infra passes run only when a designation or the map changed, the building and founding
passes on their own `due()` timers.

### Designations: one writer, already in place
Designations exist since the founding plan (2026-10-02): `autoplay.outpost_roles` is the intent, machine
scripts keep going by the buildings actually there, and `autoplay_roles.role_gaps()` compares the two. That
split stays; the earlier "roles come from buildings, no designation" rule now holds for machine scripts only.
- **Only the founding pass (and the operator) writes `autoplay.outpost_roles`.** The building pass reads it.
- **Phase moves are designation changes.** When home turns reserved (`outpost_needs.home_reserved()`), the
  founding pass proposes moving `smelter` off home's designation onto a factory outpost. The building pass then
  sees `missing: smelter` at the new host and `extra: smelter` at home and proposes the paired retire + deploy.
  So the eviction rule lives once, next to `plan_hosts()`, instead of in both planners.
- `extra` from a hand-built machine still means nothing. Only roles the designation owner released count as
  retire work: it records them in `autoplay.role_releases` `{outpost_id: [role, ...]}`, cleared once the
  role's buildings are gone.

### Phase: one shared, derived module
Phase checks are scattered today: `power.grid_phase()` (generator types), `drone_upgrade.upgrade_phase_reached()`
(any drill deployed), `outpost_needs.home_reserved()` (wildlife unlocked), the Large Warehouse staging
(`per_warehouse`), the Biomass phase (`read_essences_required()`), the Forage phase in the Plant Terraformer
code. The founding planner also reads it for look-ahead (outpost_founding_planner.md "Look-ahead"). New `scripts/4_controlpanel/lib/game_phase.py`: pure predicates over a snapshot (`wildlife_unlocked`,
`drills`, `large_warehouse`, `biomass_phase`, `forage_phase`, `power_phase`) plus one thin reader. Both planners
and machine scripts (`drone_upgrade`) import it, so no rule exists twice. The phase is derived from in-game reads
every pass, not stored as a separate truth; monotonic milestones may be cached the way `drone_upgrade` caches
`phase_reached`.

### Phase changes behaviour inside a designation too (owner, 2026-10-06)
A phase change is not only a designation change. The same designation can need **different buildings** and
**different machine behaviour** once a phase is reached. So providers never post building counts; they post
**capacity in the domain's own unit**, and one per-phase fulfilment rule in the building pass turns it into
buildings. A phase change then keeps the need and changes the buildings that meet it, which the building pass
proposes as paired retire + deploy, the same way as a designation move.

| Domain | Need (unit) | Fulfilment depends on |
|---|---|---|
| Storage | slots per outpost (`stock_slots()` / `site_slots()`) | `large_warehouse` phase: Warehouses only before `research_high_bay_warehousing`; from then on only Large Warehouses (`WAREHOUSE_SLOTS`, autoplay cheatsheet) |
| Power | W and reserve per grid (`power.py` balance) | `power_phase`: solar, steam, oil, reactor generator mix |
| Smelting | throughput per host (order backlog) | which host the designation allows (home reserved after wildlife unlock) |

- **Storage replaces the fixed 2:1 swap.** `warehouse_upgrade.py` swaps two Warehouses for one Large Warehouse
  (`SWAP_RATIO`) regardless of how much storage the outpost needs. Instead the Warehouse provider says "this
  outpost needs N slots", and the fulfilment rule picks the type by the research alone (owner, 2026-10-06):
  before High Bay Warehousing, ceil(N / 5) Warehouses; once it is researched, **every new storage building is
  a Large Warehouse**, ceil(N / 15) of them. The price gap is small, and a later swap blocks both Warehouses'
  feeders for minutes while it drains, so the planner never deploys a small Warehouse it would have to swap
  later. Small Warehouses already standing count toward the slots and stay; they are swapped only when the
  outpost needs their building slot (cap) or more slots than a new Large Warehouse beside them gives. Surplus
  storage after a role leaves is retire work like any other.
- **Retiring a Warehouse has no script handshake** (Warehouses have no script slot). The executor's retire for
  storage reuses the greedy drain from `warehouse_upgrade.py` (`transfer_to()` chunks into the new or another
  store, then undeploy). Until the swaps move onto the executor (Phases, step 7), `warehouse_upgrade.py`
  stays the executor for storage swaps and the planner doesn't propose them while it is switched on, so the two
  never act on the same Warehouses.
- **Behaviour inside a machine** reads the same module: `power.py`'s per-phase guards and `oil_generator.py`'s
  reactor rule already switch on the phase; they import `game_phase` instead of their own checks. The planner
  doesn't push behaviour changes to machines; each machine script reads the phase itself.

### Capacity metric per domain (draft, owner 2026-10-06: needed for every use case)
Storage slots are one example. Every provider needs a metric of the same shape: **a need in the domain's
unit**, plus a **rate per building and tier** read from game data (`docs/database/`, recipe durations,
component reads), never a hard-coded building count. Fulfilment has three options, not two: deploy more of a
type, deploy a larger type (paired retire + deploy), or apply an **upgrade pack in place** (Mk II to IV: no
slot, no retire, often the only option at a capped outpost). The rule picks the option that meets the need
at the lowest cost, with the building cap as the scarce resource.

| Domain | Need (unit, per scope) | Buildings and tiers that meet it | Phase that changes the mix |
|---|---|---|---|
| Item storage | slots per outpost | warehouse, large_warehouse | High Bay Warehousing research |
| Fluid storage | tons per fluid per outpost | liquid_tank, bulk_liquid_reservoir (the Large Liquid Tank), gas_tank | tank research (today's Large Liquid Tank swap, production_logistics §2k-3) |
| Power supply | W (average and peak) per grid | solar, steam_turbine, oil_generator, reactor | `power_phase` |
| Power reserve | Wh to bridge the grid's dry spell | battery, battery_large, lightning_rod | `power_phase` (night vs vent dormancy) |
| Smelting | ore units/h per host, from orders and ore stock targets | smelter, Mk II/III packs | home reserved after wildlife unlock; Industrial Machinery research |
| Fabrication | crafting hours/day of backlog per host | fabricator, Mk II/III packs | same |
| Atmosphere | O2 / pressure / heat per day toward the target | oxygen, pressure, heat generators | Mk II to IV packs (research) |
| Plants | Forage/h toward the next threshold | plant_terraformer, grow_lamp, sprinkler | Mk II packs, Forage phase |
| Wildlife | feed units/day per species, habitat capacity per colony | feed_maker, habitat | Mk II packs, Breakthroughs |
| Biomass | essence t/h per biome | essence_liquifier, biomass_mixer | Biomass phase, Mk II pack |
| Refining | refined exotic t/h | refiner | exotic unlocks |
| Water | t/h of condensed water | steam_condenser | steam phase |
| Item logistics | drone trips/h per outpost | drone_station small, medium, large | dispatch research |
| Vehicle upkeep | vehicles to service or charge | drone_service_station, vehicle_charging_station | Mk II, III packs |
| Pioneer energy | battery swaps/day for Pioneers on long routes | battery_charger, Mk II pack | Battery Charger research |
| Unique sites | present or not (count 1) | bio site set, weather_station | none: designation only |

### Cost of a proposal: cash plus three maluses (owner, 2026-10-06)
"Lowest cost" is never cash alone. Every proposal also pays for three scarce things, each priced by how close
the base is to that limit (cheap with room, steep near it). A hard limit is a gate, not a weight. Weights live
in one dict (autoplay cheatsheet), so they can be tuned in one place.
- **A) Build slots** (per outpost): each counted building it adds. The cost rises as the outpost nears its cap,
  and going over the cap at an outpost with a penalized machine stays blocked (founding plan §capacity). An
  upgrade pack in place adds no slot, a larger type replaces several, so both win at a full outpost. Home's
  slots cost more once they are reserved for wildlife (`home_reserved()`).
- **B) Limited inputs** (per input, base-wide): some inputs have a world supply, not a price, e.g. Raw Uranium
  (~10 t/day on average, owner), salt (wells cap at 50/h), an exotic deposit's flow, a steam vent's flow. A
  provider's need is capped at what the input sustains on average, so no amount of demand buys the Xth reactor
  past the uranium it would get. Domains that share an input split its headroom; the cost of a proposal rises
  with the share of the remaining headroom it takes. Supply is read in game where possible (well and deposit
  rates, aftermath history); only fixed absolute limits may be constants (information policy, founding plan).
- **C) Script slots** (base-wide): each script a proposal keeps running. Above 50 running scripts every extra
  one shrinks every script's step allowance (dev_workflow §1d-1), so it slows the whole base. N comes from the
  census (`script_census.count_running()`). A building without a script (Warehouse, tank) or with a script that
  parks or ends when idle (`script_parking`) costs nothing or little; one big machine beats two small ones.
  Retiring a running machine gives the slot back, which counts in favour of retire work.

Not the building pass: drones and vehicles (`fleet_commission`) and map machines a Pioneer builds (drills,
pumps, Thermal Caps: infra planner). They can post a need here, but their executor stays theirs.

Order of work: item storage first (the metric exists in `stock_slots()`, and the 2:1 swap is the first thing
it replaces), then power and smelting, whose data partly exists (`power.py` balance, order backlog). Each
other domain gets its metric when its provider is built (Phases, step 5); a domain without one stays
operator-placed.

## Game build e1986ce (v0.1.30): all four changes folded in (owner, 2026-10-08)
The build review ([e1986ce.md](../../e1986ce.md)) found four changes that touch this plan. The owner chose to
fold in all of them now. Thresholds and counts still wait for the new run.
1. **Upgrade packs in place** (`computer.upgrade(item_id, machine)`, e1986ce §3, §6). The executor gets a third
   job kind, `upgrade(machine_id, item_id, requester, why)`, with the same kit sourcing as `deploy` (Inventory,
   craft, Shop). Its outcomes join the one status table: `item_not_in_inventory` sends the job back to kit
   sourcing; `under_construction`, `not_enough_power`, `inventory_full` and `tier_not_ready` are transient;
   `locked`, `not_upgrade_item`, `not_found`, `not_at_outpost`, `wrong_machine_type` and `tier_too_high` are
   fatal. The pack applies to every type that has one: Smelter and Fabricator (Mk II: 2× speed, 1.5× power;
   Mk III: 4× speed, 3× power), the terraforming generators (Heat, O2, Pressure Mk II to IV, today only
   `early_buyer`'s Pressure stage) and the Drone Depot kit upgrade (`drone_upgrade` already uses it). For a
   Smelter or Fabricator host that runs full, the fulfilment rule weighs "upgrade the machine" against "deploy
   another one" by the cost model: a pack adds no build slot and no script (maluses A, C) but more power (gate 1
   below). Prerequisite: `craft_seconds()` has to divide by the machine tier (e1986ce §6), or the Smelting and
   Fabrication rates read too low on upgraded machines.
2. **Battery Charger** (`battery_charger`, Mk II pack `battery_charger_upgrade_pack_mk2`; e1986ce §8). A new
   building with its own capacity row (Pioneer energy). The provider compares it with station charging in
   `lib/vehicle_energy.py` for long Pioneer routes and posts a need only where the charger wins. It draws from
   the local grid, so the power gate applies.
3. **Oil Pump Mk II and Seismic Sonar** (e1986ce §3, §4, §6). Oil Pumps are map machines, so the pack goes
   through the infra planner (`construction_blueprint.plan_upgrade()`, blueprint kind `"upgrade"`, a Pioneer
   carries the pack), not through this executor. This plan sees the effect: each Mk II pump gives 1.5× flow
   at 100 W (20×), so oil supply (malus B) and the power gate both change. A Seismic Sonar re-survey of inert
   formations adds new wells, which also raises the oil supply.
4. **Drill location API** (`MiningSite.has_drill()` / `drill_id()`, `mining_drill.site()`; e1986ce §5). Every
   pass that matches drills to sites (infra extractor pass, the Smelting provider's ore supply) reads the live
   link. Done for the extractor, power and fluid passes and the pull haulers (`drill.positions` retired).

## Walkthrough check: what else the planner must consider (2026-10-06, open)
A pass over [manual_walkthrough.md](../autoplay/manual_walkthrough.md) phase by phase, asking at each step what the
building planner would have to decide. Facts are cited; anything marked *verify* is not checked yet.
1. **Power per deploy.** Every machine adds draw; a deploy the grid can't carry (night, no reserve) only sheds
   something else. The power provider's balance is a gate for every other provider's proposal, not just its own
   domain. Mk IV atmosphere packs draw **100× Mk I power** (`docs/database/equipment_atmosphere.md`), so each one is
   a power proposal too.
2. **Uranium has two consumers.** Reactors and the Mk IV O2/heat/pressure packs both burn Fuel Rods (Mk IV: 4-rod
   magazine, ~240 h per rod; Reactor: 72 h per rod at heat 1.0). The uranium malus (B) must split one supply
   between power and terraforming, not price each alone.
3. **Fluids before the machine.** A machine that takes water, steam or oil is idle until the infra planner's pipe
   reaches it. Order: designation → pipe → deploy, or accept idle and don't count its capacity yet.
4. **Logistics capacity.** Each item machine adds Warehouse feeder time and haul trips (the factory-outposts limit).
   Drone trips per outpost is a capacity row already; a deploy whose inputs can't be hauled adds nothing.
5. **Fabricator time is scarce too.** Kits, packs and pipe segments queue behind orders on the same Fabricators.
   A fourth malus or a gate: crafting hours the proposal takes from the backlog.
6. **Fleet shares the script budget.** Drones and Pioneers run scripts as well; malus C has to see
   `fleet_commission` proposals and building proposals against the same running count.
7. **Unlocks come from orders, not only research.** Pipes, valves, power lines and the Yield Amplifier come from
   contractor orders (walkthrough §2.2, §2.4; Spire order). Kit availability (`read_kits()`) covers what is
   available now; anticipating an unlock (reserve a slot, pre-place power) needs the order chain *(verify which)*.
8. **Things that go obsolete.** Solar on oil/reactor grids (`power.SOLAR_RETIRE_SHARE`), Rovers once drones haul,
   Storage Bins once Warehouses exist, Dispensers vs Harvester care (salt), Pioneer mining once drills run, steam
   Heaters once Mk IV replaces steam (frees steam for turbines). Each is a retire provider with a phase trigger.
9. **Capped pillars free resources.** When a pillar hits its max (e.g. Plants 5M), its machines become retire work
   (`plants_retire.py` does this for Plants), and the slots, scripts, water and salt they used go back to the pool.
10. **Caps change mid-game.** Outpost Expansion (+5) and a Weather Station (+1) raise an outpost's cap
    (`research_catalog.md`), so slot plans must re-read capacity, not cache it.
11. **Retire returns a kit.** Keep it in Inventory for the next deploy or sell it (cash manager); a paired move
    keeps it.
12. **Operator overrides.** Hand-built machines and hand edits of designations win; the planner proposes around
    them, never undoes them silently.
