# Plan: outpost founding planner (`autoplay/`)

## Context
The infra planner (docs/plans/autoplay_infra_planner.md) places extractors, pipes and power lines,
but outposts are still founded by hand, and their roles (`autoplay.outpost_roles`) are typed in by the
operator. Next step: the autoplayer works out **which outposts we need now and later, where, and with
which roles**, proposes them, and once the operator approves, buys the kit and queues the blueprint.

Decisions taken with the user (2026-10-02):
- **Autonomy v1: propose + approve.** Ranked proposals go to the archive and the log; the operator approves
  one; then the planner buys the kit and queues the blueprint. Later: fully automatic through the cash manager.
- **Two role views.** Outpost *behaviour* (machine scripts) stays driven by buildings (Phase E). *Autoplay*
  behaviour is driven by **designation** (intent): an outpost designated `smelter + liquifier_deep` keeps
  that wish while the liquifier is still locked. Designation = `autoplay.outpost_roles` (existing key).
  Buildings = observed roles. The gap between the two becomes the backlog for the next plan (building planner).
- **Scope:** need model, site scoring, proposals, approval, kit purchase, blueprint, role designation.
  Deploying machines into outposts is out of scope (next plan: building planner).

## Game facts this relies on (research 2026-10-02, cite into cheatsheet)
- Found: `construction_blueprint.plan_structure("outpost", x, y)`, statuses `locked`, `out_of_bounds`,
  `occupied`, `clearance`, `blocked`, `outpost_overlap`, `anomaly_overlap`. A Pioneer with Constructor +
  `outpost_kit` in cargo builds it (`docs/guide/first_outpost.md`).
- **Kit price is a step table**, index = founded non-home outposts + unbuilt kits held:
  15k, 30k, 50k, 75k, 110k, 200k, 350k, 550k, 800k, 1M (simworker `Nae`). `decommission()` returns the kit,
  so the count (and the price) never drops. **Moving an empty outpost costs nothing**; every *new* one is
  permanent spend. A kit bought and not yet built already raises the next price.
- Placement: footprint 2×2 tiles for placement, 4×4 for utilities, anchor top-left; 40 m clearance from other
  outposts (centre to footprint), 20 m from every POI incl. unsurveyed ones; biosites block. Map ±900 m.
  No biome, distance or power restriction.
- Biome: `nocturna.biome_at(x, y)`, `biomes()`; the outpost's biome is read **at the anchor point**.
- Capacity: soft cap 20 per founded outpost (home 25, +1 Weather program), +5 Outpost Expansion
  (simworker `R_`). Each counted building over the cap costs 10% efficiency (floor 20%, `dne`). Deploys are
  never blocked. **Avoid over-cap at any outpost that has a penalized machine.**
- Overcrowding classes (simworker machine table, `overcrowding` + `building` flags):
  - *Counted + penalized* (`throughput`): smelter, fabricator, refiner, all bio_* machines, essence_liquifier,
    biomass_mixer, seed_maker, feed_maker, habitat, plant_terraformer, reactor, fuel_assembler, steam_turbine,
    steam_condenser, oil_generator, solar_generator, O2/heat/pressure generators, garbage_disposal,
    lightning_rod, charging_station, drone_service_station, **supply_dock**.
  - *Counted, never slowed* (`exempt`): warehouse, large_warehouse, storage_bin, gas_tank, liquid_tank,
    bulk_liquid_reservoir, battery, battery_large, nuclear_battery, drone_station (all sizes), lead_cask,
    weather_station.
  - *Not counted*: field structures (drills, pumps, caps, taps), sensors, vehicles, field machines.
  - So a **storage outpost** with only exempt buildings (Warehouses, tanks, Depots, batteries) can go far over
    the cap with no loss. A Supply Dock there is slowed, so it is not a free "central supply depot".
    Every exempt building still counts, so it uses up slots at a production outpost.
- Biome-locked: each of the 4 biome processors works only in its own biome: `bio_luminizer` coastal,
  `dna_sequencer` geothermal, `bio_caster` volcanic, `bio_conditioner` deep. Frozen (home) has none.
  Essence Liquifier makes its own biome's essence only.
- Max one per outpost (not required at every outpost): `bio_collector`, `bio_lab`, `bio_exchange`, the
  biome's processor, `weather_station`.
- Inventory works only at home; remote outposts need Warehouses + haulers. Harvesting field only at home.
  Inventory holds 60 slots × 20 units at most, so it is no bulk store: home needs Warehouses too.

## Role catalog (unify naming)
One catalog, extending `DEFAULT_ROLE_PRESETS` in [autoplay_roles.py](autoplay/lib/autoplay_roles.py) (same
role names the infra planner already uses; new fields optional, so old archive presets keep working):
```
role: {"in": [...], "out": [...],                    # existing fluid fields
       "buildings": [type_id, ...],                  # machines that make up the role (observed-role match)
       "biome": biome | None,                        # biome lock (bio processors, liquifier_<biome>, weather_<biome>)
       "unique": bool,                               # holds a max-one-per-outpost machine -> no 2nd copy there
       "slots": n, "penalized": bool,                # counted buildings; any throughput machine in it?
       "site": {"ore": [...], "fluid": [...], "biosites": bool}}  # what it wants near the footprint
```
New roles for founding: `smelter`, `factory` (exists), `mining` (Pioneer/stationed mining base),
`bio_<biome>` (collector+lab+exchange+that biome's processor; frozen has no processor), `weather_<biome>`,
`drone_depot`, `storage` (exempt buildings only: Warehouses, tanks, Depots, batteries; may exceed the cap).
`observed_roles(outpost)` = roles whose `buildings` are all present (pure, from `outpost.buildings()`).
`role_gaps(outpost)` = designated − observed → `autoplay.role_gaps` for the panel and the future building planner;
observed − designated → debug note only (operator built by hand; no auto-designation in v1).

## Need model (`autoplay/lib/outpost_needs.py`, pure + thin readers)
Produces a list of **needs**: `{role, biome|None, urgency: now|soon|later, why}`.
- **a) Now** (live demand): biome processor needed by an open Earth order or Bio Lab for a biome without
  an outpost; Biomass phase needs an essence the network can't make; Smelter/Fab demand that home slots
  can't take (home `is_full`, Phase E); ore requested with no site within mining range of any outpost.
- **b) Later** (end-state checklist): one outpost per biome (5) with `weather_<biome>`, `liquifier_<biome>`,
  `bio_<biome>` where the biome has a processor; wildlife needs. Refining is fast, so `refinery_<fluid>` is
  never a reason to found: it is a **secondary role** added to an existing outpost (slots free, under cap)
  that has raw deposits of that fluid within `NEAR_TILES`.
  Gated by tech: a locked role is still a need at `later`, but only `now`/`soon` needs trigger a proposal.
- **c) Merge roles** onto existing outposts first: a need is met by designating an existing outpost
  (same biome if locked, slots free under the cap, site needs within range) before proposing a new
  one. Only leftover needs make a founding proposal. Designation of an existing outpost is also a proposal
  (cheap, but the operator still approves in v1).

## Information policy (user, 2026-10-02)
The planner decides only from **in-game readable data**. It never uses a-priori world knowledge: no
fixed site lists from the simworker, no reads of the save file. The decompiled code may inform how the
scripts are written, never what they decide. Exemptions: formulas and fixed absolute limits (e.g. the
kit price table, cap numbers, 50 salt/h).
Knowledge levels per contact, all readable in game:
1. `nocturna.points_of_interest()`: position only, `kind == "unknown"` until resolved.
2. `journal.discovered_sites()`: `kind()` known (mineral/thermal/water/oil/exotic/anomaly), details `None`.
3. `journal.surveyed_sites()`: full details (ore `item_id`, hardness, purity, flow rates).
Biomass contacts resolve by drone bio-scan; `PointOfInterest.kind == "biomass"` after that. Before that,
a scout's sonar sweep that fails with `wrong_scanner` on a contact already shows it is biomass. Record those
contacts as known biomass (positions only, one shared dict) and count them as biosites without a bio-scan.
Scoring uses **expected value** for less-known contacts. The prior is derived at runtime from what this
save has already surveyed (e.g. the share of each ore among surveyed minerals). With nothing surveyed,
use a flat prior. Each proposal carries a confidence (share of its score from levels 1–2). A
low-confidence proposal first asks for a survey trip near the candidate, then re-scores. It is not founded
on a guess. **Dependency:** today the scout logic sweeps blindly, with a blacklist of contacts it could not
scan. It needs a targeted work list: `autoplay.survey_requests` `{request_id: {"x", "y", "radius", "why"}}`,
which the scout (`drone_scout`/`vehicle_survey`) serves first. That rework is its own phase (below).
The `resource.*` marker system (nearest outpost within 200 m) needs rework separately. The founding
planner reads `journal`/POIs directly, not the markers. After a founding it calls the marker re-assign hook,
whichever form that takes after the rework.

## Site scoring (`autoplay/lib/outpost_sites.py`, pure)
Candidates: tile grid over the map at `CANDIDATE_STEP_M` (e.g. 40 m), filtered by biome at the anchor,
clearance to outposts and POIs (`points_of_interest()` holds every contact, even unknown ones), map bounds
(`nocturna.get_bounds()`); refine the best N on a 10 m grid. Run in
`run_batched` slices; cache biome lookups in a pass (biome map doesn't change).
Score for a candidate given the role bundle it should host (higher better, weights in one dict, cheatsheet):
- **Ore cluster (d):** sum over the ores the role bundle wants, for contacts within `MINING_RANGE_M`:
  weight(ore demand) × purity factor / mining time for surveyed sites; expected value for discovered
  `mineral` contacts and unknown POIs. Bonus for ores no outpost covers yet. Penalty for sites too hard for
  any unlocked drill or Pioneer (`drill.hardness_limit()`).
- **Fluid sites:** wanted fluid sites (`site.fluid`) within `supply_tiers.NEAR_TILES` (steam vents for
  `power`); raw exotics only as a small bonus (future secondary `refinery_*` role).
- **Biosites:** count of bio-scanned `biomass` POIs (plus expected value for unknown POIs) within drone
  range, for `bio_<biome>`.
- **Biome margin:** distance from anchor to the nearest other biome (`biome_at` probe ring); a site near a
  border scores lower (anchor mistakes, and bio collectors want native biosites around).
- **Logistics:** distance to home and to the nearest Depot outpost (haul time, drone energy budget
  `vehicle_energy`/`drone_energy`), and power/pipe length to the existing grid (`power_plan` A* cost estimate).
- **Future room:** free land around it for later extractors (clearance-free tiles within 100 m).
- **Pathing risk:** past stall points from `vehicle_navigation` near the route, if recorded.

## Proposals, approval, execution (`autoplay/lib/outpost_plan.py`)
Archive (one dict per concern):
- `autoplay.outpost_proposals` `{proposal_id: {"kind": "found"|"designate", "x", "y", "biome", "roles": [...],
  "urgency", "score", "why": [..short..], "price", "status": "proposed"|"approved"|"buying"|"queued"|"built"|"rejected", "tick"}}`
  bounded (`MAX_PROPOSALS` = 5, rewritten only on change).
- **Map markers are the approval UI.** Each of the 5 best proposals gets a marker at its anchor:
  id `autoplay.outpost.<proposal_id>`, label `Outpost Suggestion` (48 chars max), note = the designated roles
  plus the short reasons and price (240 chars max). A `designate` proposal sits on the existing outpost.
  - **Approve:** the operator adds `OK` to the label in game. The planner reads `markers.list("autoplay.outpost.")`
    each pass; a label containing `OK` (case-insensitive, whole word) sets `status = approved`.
  - **Move:** a marker dragged by the operator gives a new anchor. The planner re-checks it (biome at the
    anchor, clearance, bounds) and re-scores it; a failed check is written into the note and blocks approval.
  - **Reject:** a deleted marker = `rejected`. That site is not proposed again for `REJECT_HOLD_TICKS`.
  - The planner re-places a marker only when its own content changes. It never overwrites an operator label
    that contains `OK`. It removes markers of proposals that are built, rejected or out of the top 5.
- On `approved` + `found`: `cash.can_spend("outpost_founding", price)` (new capital consumer, added to
  `DEFAULT_PRIORITY`/labels, planned = price) → buy `outpost_kit` → `plan_structure("outpost", x, y)` at prio 0
  → record blueprint in `autoplay.planned`. Re-plan on `clearance`/`occupied` with the next best site.
- When the outpost appears in `outpost_network.outposts()` near (x, y): write its roles into
  `autoplay.outpost_roles`, run `outpost_mining.reevaluate_unassigned_near_outpost()` (today manual), mark `built`.
- `designate` approvals write `autoplay.outpost_roles` directly.
- Every decision logs `debug()` reasons (AGENTS.md rule 5): need → candidates kept/rejected → score terms.
- Pass hooks into `planner_loop.run_planner()` as its first pass (needs before extractors/fluids), so a
  new outpost's roles drive extractor/pipe/power work on the next pass.

## Other things worth handling (answer to "what else?")
- **Kit timing:** buying a kit early raises the price of the next one; buy only after approval and right
  before queuing.
- **Relocation (redeploy):** outposts can be undeployed. `decommission()` returns the kit, and a rebuild
  with that kit costs nothing extra, but the outpost must be empty first: undeploy its machines, haul its
  stock out. Triggers: the stage changes (Pioneer mining → drills, where ore proximity stops mattering and
  logistics distance matters more), a designation is gone, or a much better site was surveyed. A relocation
  proposal = (score gain) vs (emptying + hauling + rebuilding effort). v1: propose only; never auto-decommission.
- **Slot budget:** an outpost with any `penalized` role keeps its counted buildings (incl. Warehouses,
  tanks, Depots, Weather Station) ≤ capacity: never plan over the cap there. Demand is local, so storage
  stays at the outpost that uses it.
- **Warehouses come with the roles**, home included: one 2000-unit slot per stocked item.
  Smelter = 1 slot per ore + 1 per ingot (+ byproducts) of its recipes; Fabricator = 1 slot per ingot its
  recipes take + `FACTORY_BUFFER_SLOTS` for intermediates and finished goods; mining = 1 per mined ore;
  bio chain = 4 samples (`bio.MAX_LOCAL_BIO_ARTIFACTS`) + 5 reagents (`outpost_reagents`); Feed Makers = the
  inputs of their recipes (Forage + life forms, up to 30); Habitats = one feed per housed species (16 planned);
  liquifier = 6 (one per life form of its biome). The Feed Maker list read in game counts only when complete
  (a recipe for every species), else the end-state fallback, since a partial list underestimates drastically.
  Smelter/Fabricator stock is staged by the Large Warehouse (Biomass 30,000): before it, the recipes unlocked
  now in 5-slot Warehouses (late ores such as Neutronium come later; the Large swap frees slots for them);
  after it, every ore in 15-slot Warehouses. Wildlife roles unlock after the Large Warehouse, so they always
  plan with 15. Items shared by two roles at one
  slot (a smelter + mining outpost stocks each ore once). The slots beyond the Warehouses already there become
  new Warehouses (Large Warehouse, 15 slots, once its kit is available, else 5), and those count against the
  cap like any other building (`autoplay_roles.site_slots()`). Founding bundles report their building count
  incl. Warehouses and flag `over_cap`; phase 3 site scoring and phase 4 proposals use that count.
- **Home is reserved late game.** Wildlife lives at home (Forage comes from the home field, so no feed
  hauling): all Habitats, Feed Makers, Plant Terraformers and the farm, plus their Warehouses, fill home's
  slots. Early on home may host other roles (Smelter, Fabricator, ...) within its cap. Once wildlife is unlocked
  (Habitat kit available, a Habitat at home, or wildlife designated there) home takes only
  `HOME_RESERVED_ROLES` (farm, plants, feed, wildlife). Roles home took early become relocation candidates then.
- **One `storage` outpost at most**, for large stockpiles nobody uses locally yet: life-form stockpiles,
  stray tar until a Refiner takes it, etc. It holds only exempt buildings, so it may go over the cap. Need
  signal: such stock has no home elsewhere (home slot budget §1l-2, eviction holds). No Supply Dock there: docks
  are penalized.
- **Pioneer mining early, drills later:** score ore clusters for Pioneer reach first. Once drills are unlocked,
  ore proximity matters less (drills sit on the site) and logistics distance matters more. This is also a
  relocation trigger (above).
- **Biome at the anchor (validated in simworker):** `lne()` checks a machine's biome at
  `c_(outpost.x, outpost.y)`, the stored anchor. `Pv()` puts the centre at `(x + half, y − half)`, so the
  anchor is the NW corner. A footprint across a border takes the NW corner's biome. Check `biome_at(x, y)`
  at the anchor and keep a margin.
- **Drone Depot is mandatory** for every outpost that takes part in item logistics (not fluid-only or
  storage-free ones). Drones replace Pioneer haulers over time. Every `found` proposal with an item role
  includes `drone_depot` in its bundle and slot budget.
- **Drone Service Station is optional:** an outpost may skip it when a nearby outpost has one (drone
  range check) and its slots are tight. It then needs no oil (no `drone_service` role, no oil pipe).
- **Power & pipes follow automatically** from the infra planner once roles are written; include their
  segment cost in the score (long lines = many Fabricator segments).

## Phases
1. Role catalog fields + `observed_roles()`/`role_gaps()` + tests (pure). **Done**: `ROLE_CATALOG` is code-side
   (fluids stay in the archive presets, missing default roles are merged in); unlock = every building's kit
   is available (Shop catalogue / Fabricator / Inventory, read in game) instead of research ids;
   `biome_locks()` replaces a unique-clash check (roles sharing a unique machine just share it).
   Cheatsheet §11f, `tests/test_autoplay_outpost_roles.py`.
2. `outpost_needs` (later-checklist + now-signals) + tests with fake outposts/tech. **Done**: pure core over one
   snapshot (`snapshot()` reads it); now = Bio Orders without the biome's chain, Biomass essence deficit; soon =
   next phase's essence, ores out of every outpost's range, every Smelter/Fab host full, refined exotic taken with
   nothing refining it; later = end-state checklist and locked roles. `plan_hosts()` merges onto existing
   outposts (biome, cap with penalized machines, depot, site reach; home only until wildlife is unlocked), leftovers
   form founding bundles. Life-form Earth orders are no need (drones catch them anywhere).
   Cheatsheet §11h, `tests/test_autoplay_outpost_needs.py`.
3. `outpost_sites` candidate generation + scoring + tests (fake biome map, sites, POIs); step-budget test.
4. `outpost_plan` proposals + approval + designate path (no spending) → first live run, read-only proposals.
4b. Scout rework: `autoplay.survey_requests` served first by the scout, `wrong_scanner` contacts recorded
   as known biomass, blacklist kept for truly unscannable contacts.
5. Founding execution: cash consumer `outpost_founding`, kit purchase, blueprint, built detection,
   ore reassignment. Verify the Pioneer construction loop carries `outpost_kit` for an outpost job.
6. Cheatsheet §11 (new section: constants, weights, archive keys), TODO.md entry, DESIGN_HISTORY note on the
   intent-vs-observed role split; panel line for proposals (later: CONTROL panel button).
7. Later: auto-approve under cash-manager rules (urgency `now`, price ≤ share of balance).

## Critical files
- [autoplay/lib/autoplay_roles.py](autoplay/lib/autoplay_roles.py) — catalog fields, observed/gaps.
- New: `autoplay/lib/outpost_needs.py`, `outpost_sites.py`, `outpost_plan.py`.
- [autoplay/lib/planner_loop.py](autoplay/lib/planner_loop.py) — new first pass.
- Reuse: `grid_geom` (footprints, tiles), `infra_topology` (`outpost_positions`, `surveyed_sites`),
  `supply_tiers.NEAR_TILES`, `power_plan` (route cost), `blueprint_queue` (queue + `autoplay.planned`),
  [scripts/4_controlpanel/lib/cash.py](scripts/4_controlpanel/lib/cash.py) (`can_spend`/`spent`),
  `outpost_mining` (`resource_assignment_range_m`, `reevaluate_unassigned_near_outpost`),
  `weather_signals.missing_biomes()` (biome coverage pattern).
- Docs: `docs/cheatsheet/autoplay.md`, `docs/AI_CHEATSHEET.md` index, `docs/cheatsheet/production_logistics.md` §2l (new consumer).

## Verification
- `pytest tests/` with new `tests/test_autoplay_outpost_*.py`: biome lock respected, unique clash rejected,
  merge onto existing outpost preferred over founding, clearance/POI/biosite filters, anchor-biome check,
  ore-cluster score ranks a 3-ore site over a 1-ore site, price step table, slot budget, proposal bounded,
  marker approval (label `OK`, moved marker re-checked, deleted marker = rejected, operator label kept).
- `test_game_imports`, `test_log_blocks_balanced`, `test_reset_in_run_loops` already scan `autoplay/`; Pyright.
- Live (ask first each time): `scripts_sync.py once --include-autoplay --apply-libs`; phase 4 run only logs and
  writes proposals and places the 5 suggestion markers; check them against the map. Edit one label to add
  `OK` and check the archive status; drag one marker and check the re-check result in its note. Phase 5: approve one cheap proposal, watch kit purchase, ghost,
  Pioneer build, roles written, extractor/pipe/power passes picking it up.
