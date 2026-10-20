# Design History: Vehicles & Drones

Why behind vehicle mixins, Pioneer roles, haulers and drone depots (cheatsheet §2, §2b, §2f, §2k, §11 haulers). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

## §2f — Demand-Driven Transporter: Real-World Bugs Found Live

**The `is_at_base()` check before loading was added after a real failure mode**: without it, the
haul loop jumped straight to loading wherever the vehicle happened to be, failed every `take_item()`
call (wrong/no local source), and sat there printing "Could not load any planned item" forever
instead of ever driving back to the stationed outpost — caught from real in-game console output
showing exactly that. Fixed by checking `is_at_base()` first and driving via `return_to_base()` if
not already there.

The whole Phase D transporter role was originally `lib/pioneer.py`'s single-route,
manually-configured `transport_once()`/`run_transport_loop()`/`find_outpost_coords()`/
`find_local_store()` — deleted outright once the demand-driven, multi-ore version (§2f/§2g in the
cheatsheet) shipped, since no thin entrypoint script referenced the old functions any more.

---

## §11 — Pioneer Haulers Pull to a Home, No Destination (2026-09-29)

The push hauler (`run_haul_loop(dest)`, `DESTINATION_OUTPOST_ID`) had two uses: an ore hauler parked at a
mine delivering home, and a reagent hauler parked at home buying and delivering to a remote Bio Lab. The
pull hauler already covered the first from the other end (homed at home, reading home raw-ore demand), so
the push hauler was removed and every Pioneer hauler serves its `HOME_BASE`. The reagent case became a
buyable request at the lab's outpost plus a Shop pickup at home, restricted to flagged requests so a hauler
never buys what should be mined or made.

Fully floating Pioneer haulers were considered and rejected: nearest-free dispatch picks a Pioneer 1000 km
away while one near the job is busy, and a Pioneer pays for every empty metre on terrain. Idle Pioneers
pinned to outposts are the accepted cost; drones stay the floating fleet. Existing save slots are re-homed
by scripts_sync from their old destination, since keeping `HOME_BASE` would have turned the mine-parked ore
hauler into one pulling toward the mine.

## §2 — Early Harvester: Credits per Tick, Monotone Routes, Planning in Callbacks (2026-10-06)

Replaced vakermit's value-density script (`value / d^1.35`, nearest item within 2 first, collect whatever it stands on, clearing mode at 25/25) after an offline policy search (`devtools/simulation/headless/harvest_policies.mjs`, results in [plans/scoring_map_seeds.md](../plans/scoring_map_seeds.md)).

- **Objective**: run time from a new game to the 25/25 build-out credits (10,250 cr), when the Harvester is still the only income. Credits by 0.5 h only break ties.
- **Skip cheap items**: early on time limits the Harvester, not heat. A collect costs 63 ticks, driving over an item cell +1 heat, so items worth less than half a collect at the best rate stay on the field. They serve as stepping stones and are collected later.
- **Heat price instead of rests in the plan**: heat matters later (routes otherwise end in 1.8 h rests per empty hop). A price per heat unit that rises with heat beats both a fixed price and none.
- **Monotone routes, not Dijkstra**: almost the same result (12.7 vs 12.6 min) at about a quarter of the interpreter steps. In game, steps are the real cost: each tick of planning per hop costs ~0.06 min.
- **Planning in `map()` callbacks**: the `0_cold_boot` tier has no `lib/atomic.py`, so the script inlines the same trick. Chunks are sized from headless step probes on a full field (largest ~4,200 of the 10,000-step cap). Exceeding the cap would end the script, and it can't be caught.
- **No clearing mode**: once rich items are gone, the rate gate drops and the cheap ones get collected anyway, so nothing starves.

## §2b-2 — Mining Pioneer Holder/Rack Split (2026-10-07)

Mining Pioneers carried far more cargo than their batteries could fill: 2 × 50 Wh against 400 units, so an Industrial drill came home with ~14 units from a 120 m site and spent most of each trip driving. The tier ladder (§2b-1) only grows each container; nothing chose how many slots each kind gets.

- **Only the split moves**: function modules stay, each kind keeps the best tier. Swaps are near free (Shop buys back at full price).
- **Objective = drive Wh per delivered unit**, not units per trip: averaging units per trip lets a cheap near site outvote a far one, while drive overhead per unit weighs the far site by what it really costs. Drill power per unit doesn't depend on the split, so it drops out of the comparison.
- **Sites from the journal and the resource markers each cycle**, not a configured distance, so a new site or a moved marker re-splits on the next idle stop.
- **Hysteresis (`SPLIT_MIN_GAIN`)**: sites come and go as stock targets fill; without a margin a Pioneer would sell and rebuy slots every few trips.
- **Haulers too (2026-10-09)**: a pull hauler's preset (2 holders, 5 racks) could not pay the round trip to a far source. Its sites are every source it may pull from, not only those holding stock now: stock comes and goes per trip, and a source the battery can't reach never gets planned, so a stock-based list would never learn it. Hauler energy is mostly the empty drive (the cargo term is ~0.04 W per unit), so the split mostly follows distance. A source outpost with a charging station only needs the loaded way back from a full battery; its drive cost still counts the whole round trip, hence the optional `drive_wh`.

## §0 — Vehicle Mixins: Abilities as Methods, Jobs as Objects (2026-10-11)

The vehicle mixins had grown by topic. `VehicleEnergyMixin` held formulas, charging-station discovery and a driving `recharge_at_station()`; `PioneerConstructionMixin` held archive bookkeeping, stocking, build actions and the role loop. Navigation, energy, claims and cargo formed one dependency cycle. The mission state (`current_target`, `current_target_key`, `current_target_reserved`, ...) had four writers, and five role loops (expedition, stationed mining, survey, pull, construction) each re-implemented the same recall-check, charge, pick, drive, act, return, release, unload shape.

- **Decision (hybrid)**: the vehicle's own abilities stay controller methods in layered mixins of one ability each, calling only lower layers. A `Mission` dataclass is written only by `VehicleClaimsMixin.begin_mission`/`end_mission`. Each role is a `Job` object that owns its state and step logic, run by one `run_job_loop`. Pure math and archive I/O are module functions with explicit arguments.
- **Why abilities did not become helper objects** (`self.nav`, `self.energy`, ...): navigation, energy, claims and charging read each other constantly (`drive_to` needs the battery and the nearest station, `recharge_at_station` needs `drive_to`). As objects the cycle would stay as back-references plus one more hop per call. A job is different: its data and step logic belong together, and the controller needs only one loop.
- Plan, layer table and step log: [plans/mixin_refactor/README.md](../plans/mixin_refactor/README.md). Harvesters follow the same recipe later.
- **Drones (2026-10-11)**: same recipe (`followups.md`). `run_job_loop` moved to `FleetUnitMixin` so one loop serves both controllers; the vehicle's brake became the `stop_moving()` hook and a `Job.hold()` hook covers the drone's "stranded, await rescue" state, which must come before the recall check. The hauler's delivery became a `Mission` without a claim key (`kind="haul"`), so `load_mission` restores a key-less mission without a claim check and `end_mission` releases no claim for it (`release_claims("")` would drop every claim).

## §2k — Drone Depot Swap Replaced by In-Place Upgrade (2026-10-08, game build e1986ce)

Before build e1986ce, a bigger Depot meant a swap: deploy the new kit, hide the old Depot from drones (`retiring_depots`), wait for its script to drain everything, undeploy it, rename the new one and move the home pins.

- **Now**: one `computer.upgrade(kit, depot)` call. In the simworker the in-place kit only changes the machine's typeId and default data (`bays`, stack slots). The machine object, its stockpile, script slot and docked drones stay, and bays only grow, so no drone needs to leave. The old kit returns to Inventory.
- **Removed**: `retiring_depot_ids()`, `DroneDepotController.drain_everything()` and the drain/undeploy/rename states. A save with a swap in flight drops the entry; a Depot it already deployed stays as an extra Depot.
- **Kept**: the script slot keeps its small-Depot name (`drone_station_N`). All three Depot templates run the same `DroneDepotController`, and it reads `bay_count()` live.

## §2b — Mine Site Ranking by Urgency per Hour (2026-10-10)

- **Purity then distance starved slow ores**: outpost_1's stock-tier sites were all Standard and 149–160 m away, so the nearest won every pick. Iron (8 m closer than cobalt) stayed under target because Smelters drain it, and cobalt sat at 81 of 1800 while Fabricators waited on cobalt ingots.
- **Time per unit alone is not enough**: digging dominates driving (15–25 game minutes per unit against a few minutes of round trip per unit), so pure speed still picks iron. Dividing urgency (missing share of the stock target) by hours per unit lets an empty slow ore beat a half-full fast one, and fast ores still get topped up more often.
- **Fill buckets rejected**: quartered fill levels with purity and distance as tie-breaks would fix the starvation but keep purity and distance as separate lexicographic keys. Both only matter through time, so one rate replaces them.
- **Everything live, nothing calibrated**: battery on board, the battery-capped leg throttle and the mounted drill/nav are read at each pick, so outfitter loadout changes and throttle caps re-rank on their own. Only the order matters, and digging dominates, so model error rarely flips a pick. Recharge time is left out.

## §2f — Pioneer Haulers Float (2026-10-19)

Reverses the "no floating Pioneer haulers" decision of §11 (2026-09-29), as stage 1 of the dynamic roles plan
(`docs/plans/dynamic_roles/README.md`): fixed roles go away, so a hauler can no longer be pinned to the outpost
it was commissioned for. The old objection was nearest-free dispatch. The floating hauler does not dispatch by
distance: each hauler plans its own trip to every outpost with demand and takes the best `haul_rank()` from
where it stands, which already charges the empty leg to the first stop.

- **Band first, then the trip.** Destinations are grouped by their highest open band, and only the top group is
  planned unless none of its trips reaches the minimum load. Each planned destination costs one source walk, so
  the group bound limits the walks to the top band's outposts; with no viable trip anywhere, every group is
  planned in that cycle. A claim trimmed below the minimum ends the cycle instead of trying the next destination:
  the next cycle replans against the claim that trimmed it.
- **Container split stays on `HOME_BASE`.** The hauler's Battery Holder/Cargo Rack split is rated from the
  commission outpost, not the moving base, so it does not swap containers between trips.
- **The base follows the claim.** `set_base()` runs when the pickups are claimed, not at delivery, so cargo
  aboard after an error is delivered where it was claimed for. A reload resets the base to `HOME_BASE`; the
  pickups' `dest` (and a resumed mission's `"dest"`) restore it.
- **`home_base` stays.** It is the commission origin that lineage and `_wrong_home` compare against; `base` is
  published beside it.

## §2f — Idle Pioneer Haulers Disperse by Outbound Flow (2026-10-19)

Stage 1b of the dynamic roles plan. A floating hauler with no demand used to park wherever its last delivery
ended, so haulers piled up at the busiest destination while the next request's goods sat elsewhere.

- **Weight by where goods leave, not where they arrive.** A trip's empty leg runs to its first source, so an idle
  hauler waits best near the outposts that send the most. `logistics.outpost_flow` keeps `received` too, for A/B
  measurement and later tuning, but dispersal reads only `sent`.
- **Per idle hauler, with hysteresis.** The weight divides by the idle haulers already based there, counting the
  mover as if it stood there, so two haulers spread over two equal outposts and then stay. A move must beat the
  current base by `DISPERSE_GAIN`, and a hauler moves at most once per `DISPERSE_COOLDOWN_TICKS`, which bounds a ping-pong. A mover
  publishes its new base before driving, so a later decision counts it there; two haulers deciding on the same
  tick can still both move, and the cooldown then lets the next idle cycle even them out.
- **Decay instead of windows.** One decayed counter per outpost (half-life `FLOW_HALF_LIFE_TICKS`) needs no
  per-trip history and stays one archive dict (the 2,048-entry cap). Drill and pump pickups count for the nearest
  outpost, since haulers can only be based at outposts.
- **Drones record, Pioneers read.** Drone hauler trips count toward the flow (it is network traffic), but drones
  float without a base and do not disperse.
- **`SHORT` disperses like `NO_DEMAND`.** The first A/B (ab_results.md "Stage 1b") never fired dispersal: with
  three outposts some deficit always exists, so `pick()` returns `SHORT` (stock below the minimum load) and never
  `NO_DEMAND`. `SHORT` is a stock condition, not a reach one (`reachable` sums every source), so the wait is best
  spent where the stock will appear, which is what the `sent` weight measures. The two states still differ in
  `parkable()`: only `NO_DEMAND` pauses the hauler.

## §2f-1 — Idle Pioneers Refit Instead of Retiring (2026-10-19)

Stage 1 (foundation) of the dynamic roles plan (docs/plans/dynamic_roles/). Autoplay retired idle scouts, miners and
surplus haulers and commissioned new Pioneers for new work: a sale loses most of a kit's price, and the next
commission waits on credits.

- **Refit, never sell.** An idle Pioneer takes a role that wants more vehicles; a Pioneer whose role has no work
  joins the haulers while they have any. The keep floor stops a role from emptying itself.
- **Reuse the commission coordinator.** A refit queues a `fitting` job with a lineage entry, the shape a freshly
  deployed Pioneer has once its script attaches. The coordinator's buy-once-per-settled-report loop serves refits
  unchanged, and a script restart mid-refit resumes through `fit_commissioned_loadout()`. The job goes ahead of
  queued commissions: the refit Pioneer stands stripped at an outpost until its parts arrive.
- **Keep by category, not by id.** A lower-tier holder or rack stays; selling it for the best tier costs credits
  the upgrade cycle spends later anyway, when the cash manager allows.
- **Slots count heads.** Every running Pioneer holds a slot of its role, so a switch compares `wanted` with real
  head counts, and the claim on `"<role>:<i>"`, `i < wanted`, settles two idle Pioneers racing for one opening.
- **Idle means `IDLE*`.** `fleet_status.is_idle()` also counts `READY_*` and `SURVEY_COMPLETE`, which a working
  scout publishes after every route; with those the idle timer would never reset.
- **Names stay the operator's.** A refit renames only a name the code gave (or the game's id), extending the
  "display names belong to the player" rule.
- **Slot refresh in `next_job()`, not in a job's `prepare()`.** `BuildJob` overrides `step()` and never calls
  `prepare()`; `next_job()` runs every cycle of every role.

## §2f-1 — Autoplay Stops Retiring Scouts and Haulers (2026-10-20)

Stage 2 of the dynamic roles plan. With refit in place, the autoplay scout retire rule (no survey request for
`SCOUT_IDLE_TICKS`) and the hauler rule (keep 2 once a hauler drone flies) sold Pioneers that would have refit.

- **One sell rule, on the fallback role.** An idle scout or builder joins the haulers even when no hauler work is
  open (before, the fallback needed hauler work, so a surplus scout stayed idle for good). Haulers are then the only
  role that grows without work. The cap is `max(MAX_PIONEER_HAULERS, hauler wanted)` fleet-wide: the constant is
  easy to read on the BUILD card, and the demand term keeps haulers the open deficits still use.
- **Salt haulers stay a separate floor.** The old keep-2 rule handed freight to drones while keeping Pioneers for
  pump salt, which drones can't load. With drone yield on and a hauler drone flying, the cap drops to
  `SALT_PIONEER_HAULERS = 2` and ignores hauler `wanted`, which counts drone-servable deficits too. The yield
  switch, not the drone count alone, marks the handover: without it Pioneers still carry everything.
- **A builder and a scout stand by.** Operator decision: one builder at all times (`KEEP_BUILDERS`), one scout
  until every POI but known biomass is scanned, then the scout may become a hauler for good. Research-blocked and
  out-of-reach POIs hold the floor too: no Pioneer re-checks reach once the scout is gone, and autoplay commissions
  no scouts, so a scout let go early would not come back when a battery or sonar unlock opens them. Once drones carry the freight, more
  than two Pioneer haulers bring nothing, so the fallback only fills the salt slots, builders never take it, and
  autoplay sells the builders above the floor and the obsolete scout instead of refitting them. Selling skips the
  refit's part purchase that the hauler cap would undo.
- **Scout keep comes from the demand.** The Seismic-scout guard went with the rule: `scout` keeps 1 while survey
  work is open (`role_demand.scout_demand()`), and a refit keeps a Seismic Sonar as the best sonar.
- **Miners stay.** Their retire rules hold until Stage 3 gives miners an outpost-level demand.
- **Work queue on its own tab.** The Ground tab's top row is full (throttle, yield, counters); the Roles tab
  reuses the roster + detail layout and stays read-only.

## §2f-1 — Miners Join the Dynamic Roles (2026-10-20)

Stage 3 of the dynamic roles plan (spec: `docs/plans/dynamic_roles/stage3.md`).

- **Demand from host-free reads, not from `OutpostStockpile`.** A miner's targets come from four vehicle-bound
  helpers (battery reach, drill hardness, its own reservations excluded). The Automation has no vehicle, so
  `miner_demand()` reads what autoplay already reads without one: the outposts' raw-ore deficits and the reach
  the stationed miners publish. `OutpostStockpile` is unchanged; `home_ore_demand()` stays Rover code.
- **Per-outpost slots.** A miner works for one outpost, so a fleet-wide count would send a surplus miner at a
  full outpost to "fill" demand at another without moving it. Slots `miner:<outpost>:<i>` count heads per base,
  and the same refit path re-stations a miner (base and name only, no Shop).
- **NEED pulls, STOCK holds.** `wanted` counts only `NEED` ores in reach; buffers are the floor miner's job
  (`KEEP_MINERS` 1 per smelting outpost). Counting STOCK would hold every miner at its outpost forever, since
  a buffer below target always reads as work. The tuning knobs, in order: `KEEP_MINERS`, STOCK toward `wanted`,
  a higher ore NEED level.
- **Unknown reach probes with one miner.** An outpost no miner has published a reach for wants at most one: that
  miner publishes it within its first pick, and the next publish counts the rest. Without the cap, an outpost
  whose sites are all out of reach would pull a miner per ore and idle them all.
- **No drill filter for refits.** Autoplay skips drill-fed ores when it commissions miners (a purchase); a refit is
  cheap and reversible, and a NEED deficit that persists next to a drill is real demand.
- **Autoplay idle retire goes.** An idle miner refits or re-stations; the drills rule (every Smelter ore drilled)
  still sells them all, and once drones carry the freight the surplus above `max(keep, wanted)` is sold per
  outpost: fleet totals would sell a smelting outpost's floor miner while another outpost's need held its own.
