# Design History: Bio, Seeds, Planting & Wildlife

Why behind the bio pipeline, seed sweep, planting and wildlife schedule (cheatsheet §1e-§1l). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

## §1e/§1f — Bio Coastal Pipeline: Postmortem Chain

A long sequence of live-debugging incidents, each fixing a real bug, chased the same underlying
symptom: Luminous/coastal specimens piling up unused or the pipeline deadlocking outright. Kept
here roughly chronologically since later fixes build on findings from earlier ones.

**1. `active_order()` misuse.** Found live: multiple differently-glowing Luminous
`sd_wing_membrane` stacks piling up unused in Warehouses. Root cause:
`BioExchangeController.sweep_and_deliver()` reassigns `active_order` constantly, to whatever order
it's currently delivering ANY matching sample to (coastal or not) — it's delivery-routing state,
not a stable "current coastal target" signal. The Luminizer used to read `exchange.active_order()`
directly for `target_glow`, so every sweep-triggered switch retargeted the Luminizer mid-tint.
Fixed with `_find_coastal_order()` scanning `exchange.orders()` directly, independent of
`active_order()`. (A live diagnostic run initially seemed to confirm this theory as the sole cause
— it wasn't; see finding 3 below for what the actual mistinted-looking stock turned out to be.)

**2. `*(self only)*` hardware calls.** Confirmed live: calling `exchange.set_order(order.id)` from
the Luminizer's own script raised `PermissionError: Cannot call set_order() on bio_exchange_4
remotely`. This means `matches_order()` is unusable from any script other than the Exchange's own.
Any other controller comparing "does this stack match an order" has to compare the raw property
directly instead (e.g. `list(stack.properties.get("glow", [])) == list(order.target_glow)`) — no
hardware call needed, since `target_glow` and a stack's `properties` are both plain reads.

**3. The "mistinted" stock was actually just raw, never-tinted specimens.** `bio_luminizer_1.log`
showed every real infuse exactly matching a live order target. The stray stacks (glow values 9-29,
nowhere near any coastal order's 62-202 range) were raw specimens still waiting for the Luminizer —
every raw sample carries its own naturally-varying starting glow, so `matches_order()` correctly
said `False` for all of them. The real problem was a Collector/Lab extraction rate outpacing the
Luminizer's throughput (~10-70s per infuse); raw specimens don't stack any better than mistinted
ones, so the backlog exhausted Warehouse material slots and deadlocked the whole pipeline. This is
what the throttle-then-structural-fix arc below (§1f) exists to prevent.

**4. `_find_coastal_order()` could deadlock the machine outright.** With two coastal orders both
incomplete, it always returned whichever sorted first in `exchange.orders()`, regardless of
whether any material for it actually existed. If the *other* order's fragment was already staged
in `self.machine.input` (latched to that item id until `load()`/`flush()`), the Luminizer fixated
on the wrong order forever. Fixed two ways: (1) prefer a candidate order with existing local stock
for one of its requirements over one needing fresh collection; (2) check
`self.machine.input.stacks()` FIRST, before consulting order priority at all.

**5. A staged sample can itself already be finished, not just raw.** Debugging live turned up the
input holding two property-distinct stacks simultaneously, both already correctly tinted from an
earlier successful `infuse()`, just never drained out. Calling `load(fragment_id)` with no
`properties` was ambiguous across the two variants and failed `"not_in_input"`; even loading one on
purpose would be pointless since it's already at target. Fixed by checking every staged stack
individually: a stack whose glow exactly equals a live order's target is already finished and gets
**ejected** (with its exact `properties`, not reloaded); only a stack matching no order's target is
loaded as raw. The "pull fresh raw material" path applies the identical exact-glow exclusion when
picking a storage stack, to avoid grabbing an already-tinted unit from the other direction.

### §1f — Raw-Specimen Backlog: From Numeric Throttle to Structural Idle-Gate

The mechanism shipped today (§1f in the cheatsheet: a structural idle-gate) replaced a much more
complicated numeric-throttle system that was tuned across several rounds before being deleted
outright. Kept here because it's real "why we tried X and it wasn't enough" context, even though
none of this code still exists.

1. **Per-fragment raw backlog cap** (`RAW_BACKLOG_CAP_PER_FRAGMENT`, initially `2`): capped raw
   stock of any one glow-requiring fragment ahead of what the Luminizer had tinted. Found
   insufficient — with ~8 simultaneously-incomplete coastal orders, each needing 2-4 different
   fragments, capping each individual type did nothing to limit how many DISTINCT types were in
   flight at once; the Collector opportunistically gathered for every incomplete order in parallel
   and still blew past Warehouse capacity.
2. **One-order-at-a-time focus** (`_focus_coastal_order()`): fixed the above by concentrating both
   Collector and Luminizer on the same single order. Found too narrow — after a full manual
   Warehouse clear, every bio script went silent with empty cargo: if the one focus order's
   fragments weren't discoverable nearby yet, throttling blocked every OTHER order's fragments too.
3. **`FOCUS_ORDER_COUNT = 3` / `_focus_coastal_orders()` (plural)**: the Collector concentrates on
   up to 3 orders at once, giving it real alternatives while still bounding distinct fragment types
   far below "every incomplete order at once." The Luminizer kept the singular version for its own
   one-at-a-time tinting.
4. **A genuinely pre-existing, unrelated bug found alongside this**: `comms.latest(channel)`
   returns the raw broadcast value directly (`-> Any`), never a status-wrapped object — unlike
   `.receive()`. `BioCollectorController` checked `b_res.status == "ok" and b_res.broadcast` against
   a plain dict, raising a silently-swallowed `AttributeError` every call, so `demands` always
   stayed `None` and the Collector permanently fell back to deriving demand from a single
   `active_order()` (the same volatile pointer from finding 1 above) instead of the properly
   aggregated broadcast. Fixed by checking `isinstance(broadcast, dict)` and reading
   `.get("local_demands", {})` directly.
5. **`RAW_BACKLOG_CAP_PER_FRAGMENT = 2` over-corrected into full lockstep.** With the Collector's
   one-slot cargo and the Lab's one-specimen chamber already forcing some serialization, a cap of 2
   left almost no pipelining slack — reported live as "harvest one, wait for the whole chain to
   finish it, only then harvest the next." Raised to 4.
6. **Raising the cap "didn't do anything" — the real bottleneck was `exchange.orders()` being
   re-fetched per fragment.** Measured live: evaluating `BioCollectorController.step()`'s demand
   loop (~20-30 fragments) took **~20 seconds**. Every fragment called `_glow_throttled()`, which
   called `exchange.orders()` itself AND called `_focus_coastal_orders()`, which called it again —
   40-60+ redundant ~80-order fetches per cycle. Fixed by threading an already-fetched `orders`
   list through every order-scanning helper, fetched exactly once per `step()`. The Luminizer had
   the identical anti-pattern, fixed the same way even though it hadn't been reported yet.
7. **Still ~8 seconds after caching `orders()`** — every fragment/order check was independently
   re-walking every Warehouse + home Inventory to compute stock counts. Fixed with one full storage
   walk per cycle (`_local_stock_snapshot()`), read via `_snapshot_stock()`/`_snapshot_glow_count()`.
8. **Still ~6 seconds after caching the storage walk too — the numeric throttle itself was the
   remaining cost, and it was solving a problem with a much simpler structural fix.** Every
   fragment in the demand loop still ran its own `_glow_throttled()` check. But the entire numeric
   system existed only because the Collector/Lab could harvest/extract faster than the Luminizer
   could tint one at a time. Since every stage already has single-slot hardware (Collector cargo,
   Lab specimen/output, Luminizer chamber/input/output), gating the **Lab** on "Luminizer fully
   idle" bounds the in-flight raw specimen count to at most one, structurally — no Warehouse
   pileup possible regardless of how broadly the Collector searches. `RAW_BACKLOG_CAP_PER_FRAGMENT`,
   `_raw_backlog_count()`, `FOCUS_ORDER_COUNT`, `_focus_coastal_orders()` (plural), and
   `_glow_throttled()` were all deleted; the singular `_focus_coastal_order()` (now
   `_focus_local_order()`), `_local_stock_snapshot()`, and the snapshot readers stayed (already
   O(1)-per-cycle, not part of the perf problem).
9. **No busy-polling for the gate** — `BioLuminizerController._notify_heartbeat()` fires an
   unconditional per-cycle Signal Bus broadcast; `_wait_for_luminizer()` uses
   `comms.wait_broadcast()` instead of `sleep(0.5)`. First version only broadcast on a successful
   `load()` — found (before it ever shipped) that this could hang the Lab forever, since
   `wait_broadcast()` only satisfies on a broadcast published *after* the call: a Luminizer that
   drained its last item with nothing staged behind it (including at fresh startup) would never
   broadcast again. Fixed by making it an unconditional heartbeat instead of a load-success event.
10. **The total-artifact safety net (`MAX_LOCAL_GLOW_ARTIFACTS`, now `MAX_LOCAL_BIO_ARTIFACTS`)
    tripped at 5 with the Luminizer picking up nothing.** Root cause:
    `_focus_coastal_order()`/`_focus_local_order()` locked onto an already-satisfied order — neither
    branch checked whether a candidate order's need for a fragment was actually still outstanding,
    only whether the fragment appeared in `.requires` or had nonzero local stock. If order A's need
    was already covered but order B (also wanting the same fragment) wasn't, the focus selector
    could still lock onto A, and every subsequent remaining-deficit check on A correctly came back
    0 — `_load_next_sample()` found nothing to load and exited, forever, despite real stock and
    demand for the same fragment on order B. Fixed with `_order_fragment_remaining()` (shared,
    module-level): both branches now require genuine remaining deficit before treating an order as
    actionable.
11. **The Lab extracted every analyzed specimen unconditionally, with no demand check.** Reported
    live: two fragment types both sat at their artifact-cap share, neither needed by any current
    order, permanently wedging the Collector (which refuses to harvest ANYTHING once the
    total-artifact cap is hit). Root cause was structurally different from finding 10: the
    Collector already gates *harvesting* on demand, but the Lab never gated *extraction* on demand
    — once a specimen reached `stage == "analyzed"`, it went straight to `extract()` regardless of
    whether anything still wanted the result. The Collector's own "uncataloged discovery" priority
    picks up a specimen purely to identify a new location, with zero demand behind it — analysis
    alone satisfies that, but the old code extracted anyway, spending reagents on a sample nothing
    would ever collect. Fixed with `_bio_demand_totals()` (shared), checked right after `analyze()`,
    before loading reagents: if demand doesn't exceed local stock, `discard()` runs instead of
    `extract()`.
12. **Self-cleaning backstop for artifacts already stuck before this fix**:
    `BioExchangeController._cleanup_orphaned_artifacts()` — a one-time-recurring problem needs a
    one-time-recurring cleanup, the same "throttle stops recurrence, doesn't retroactively fix
    existing stock" pattern as the raw-backlog cap earlier in this arc.

**Separately: `best_unload_target()`'s fallback tried to connect a remote machine's output to a
non-local destination.** When no local Warehouse had room, it unconditionally returned the literal
id `"inventory"` — but `"inventory"` only exists/connects at the home outpost. For a remote machine
(the coastal Bio Luminizer, once its local Warehouses filled up) this meant a `port.connect("inventory")`
call from a Warehouse-only outpost. Fixed by gating the `"inventory"` fallback on `outpost.is_home`
(a plain `bool` property, not the differently-shaped `is_home()` method on the full `Outpost`
component — a genuine naming trap). Three call sites weren't already wrapped in a blanket
try/except around `.connect()` and got an explicit `if target is None:` skip added.

---

## §1l-1 — Wildlife Schedule Solved Offline (2026-09-30)

Every input to the revival/Insight order is a world-independent game constant (breeding formula,
Insight curve, bonus trees), so the order is solved once on the dev machine by
`devtools/simulation/wildlife_optimizer.py` and shipped as `WILDLIFE_SCHEDULES`, instead of simulating the
menagerie in game every planning pass. The in-game planner only walks the schedule and skips a step
whose assumptions fail live (missing recipe, fluid, feed ingredients).

Revival was first gated on Insight: every non-bootstrap species bought its Adaptation before
`revive()`, because founding bonuses apply only at establishment and the below-2,500 speed boosts
lose value when bought late. The optimizer showed that letting it skip the Adaptation for some
species reaches 600,000 Wildlife about 5 % sooner (breadth earns Insight sooner), so the gate was
dropped: the schedule marks each revival `revive` or `revive_raw`. Schedules are stored per Habitat
count because the best order changes with it.
The schedules were first solved for 600,000 Wildlife (the Habitat Mk II gate) with no Refiner. The
Wildlife pillar is 5,000,000 of a possible 5,600,000, which needs nearly every species full and
therefore the Refiner and Deep Exotics, so the target moved to 5,000,000. At that target the
slowest colonies (Legendaries, Rares) set the finish and are revived early, and colonies park at the
Mk I ceiling and at 350,000 to free Habitats.

In-game, parking colonies to free Habitats for later revivals was deferred: it gains 1-2 % at 5-10
Habitats and nothing at 16, while undeploy/rehouse adds risk. The planner skips revive steps with no
free Habitat instead. Feed comes before Plants (the Plant Terraformer leaves the Feed Makers' Forage
reserve), feed is reserved by staging it in the reviving Habitat's own bin, and Habitats shed last
because an unpowered Habitat only pauses.

## §1k — Garden-Aligned Starter (2026-10-13)

- **Layout.** The starter block is columns 1-6 of the crowncap full layout at A1, without Sunspur and Pondmoss (13 species, 31 plants). Every starter cell keeps its species in the full layout, so the rebuild at Field Automation keeps the whole starter and uproots nothing. The old searched 6 x 8 block (anchored nearest the base) was uprooted almost entirely by that rebuild.
- **Pave first.** Headless simworker runs (real scripts, empty field, 8 world days): the old block reached 13 species on day 5 with 0-3 h/day of heat rest. The garden block unpaved never got fully planted (10 species) and rested 7-10 h/day at ~90 heat; paving sat behind planting and behind the `ITEM_SWEEP_MAX_HEAT` gate, which that heat never reached. The garden block with its 4 path cells paved (Harvester starting inside it) reached 13 species on day 3, all 31 cells on day 7, and 0 h/day rest from day 5. So in the starter, paving ranks before harvest and planting with no heat gate; the just-in-time rests of each hop keep it safe. A fixed rest down to 40 was rejected: it buys nothing the per-hop rests don't, and costs a long one-off idle.
- **Slow crops only with a seed at home.** During Seed Maker stage A (recipe discovery, ~85 days) the sweep makes no replanting seeds, so a harvested plant without a seed is lost for good, and with it a diversity species. Species with growth_time >= 48 h are harvested only while their seed is at home; faster starter species stay kept as before. An offline stage-A model put harvesting slow crops with replacement seeds at ~52k Forage median (p10 27k, p90 90k) over stage A, for ~1.7 days of discovery delay. `plant.seed_demand["replace"]` tells the stage-A Seed Maker which known blends to make before its next trial.

## §1i-1 — Replacement Seeds During the Discovery Sweep (2026-10-13)

Stage A marks every known blend tried, so it never crafted a seed of a species it had already found. The Harvester harvests a slow starter crop (growth >= 48 h) only once a seed for its replant is at home; with no seed, a harvested crop was lost, and in the live save nothing was harvested for ~85 days while discovery ran.

- **Replacement before the next trial.** The Harvester names such crops in `plant.seed_demand["replace"]`; stage A crafts one from its known blend before picking a triple when the forms are in stock. Offline model (one trial per 0.5 h, random discovery order): replacement seeds for slow crops gain ~52k Forage median (p10 27k, p90 90k) over stage A, for a discovery delay of ~1.7 days (p10 0.9, p90 2.7). A replacement costs 3 t life forms like a trial, and stage A is life-form bound, so the delay is real but small against the Forage gained.
- **Missing forms skip, not block.** Discovery keeps running; no extra request, since the sweep's requests already cover forms still in open triples.
- **Claim per seed, not per triple.** `seed.combos_tried` holds triple claims that `_recover()` and the pick interpret; a replacement there would read as a trial claim. A separate small dict `seed.replace_claims` counts in-flight seeds per maker, so makers sharing an outpost make at most the asked count between them; home stock covers the rest once the seed is drained.

## §1k — Loose Field Items: Pave With the Cheapest, Sell the Rest (2026-10-13)

The Field Keeper never sold loose items: its sweep only stored them into Inventory, and only at heat ≤ `ITEM_SWEEP_MAX_HEAT` once the path was paved. Items the early Harvester had not collected by the lib switch (~150k TP) stayed on the field. The garden starter needs exactly 4 path items, and a cell paved with a loose item saves the 3 t of life forms a paving seed costs.

- **Early Harvester leaves `PAVE_KEEP_ITEMS = 4`.** The 4 lowest-value items (never the base pad) are never targets; they still serve as +1-heat stepping stones. It does not carry them to the path: its monotone router has no drop step, and the Field Keeper's paving already collects, carries and drops.
- **Field Keeper: one cheap item per unpaved path cell, the rest sold.** Cheapest by the Scanner's `get_scanned()` value (at equal value a non-seed first; unknown last). The Scanner is read only while a path cell is unpaved, and again only when the set of loose sectors changes. Every other loose item is collected, stored and sold one unit at a time (`shop.sell(item, 1)`, not `sell_all`, so stock of the same id from elsewhere stays). A seed of a layout species goes to Inventory instead. Planting and machine deploys clear an item on their cell the same way.

## §1k — Rebuild Sweep, Local Work First, Inventory-Full Rebalance (2026-10-13)

After the starter moved from columns 11-18 to the A1 garden (columns 1-6), the Harvester alternated between the old zone (mature or in-the-way old crops, loose items) and the new layout. Each trip crossed 5-10 empty cells at +7 heat: one move took 6.5 h with heat 0 → 49.5, and a headless run had single moves of 19 h from heat rests. Crops away from the new block were left to finish their cycle, so growing ones pulled it back for days. The choice ranked by task kind first and took the cheapest route only inside the kind.

- **Stale crops, one sweep.** Every crop not on a layout cell of its own species is stale (`field_layout.stale()`, replaces `misplaced()`). Once the Harvester takes one, it keeps taking the nearest stale crop within `SWEEP_REACH_COST` before other non-urgent work. Mature → harvest, growing/stalled → uproot.
- **Uproot unused species too.** Uprooting returns the seed, so only the Forage still to grow is lost. Waiting for maturity costs one more field crossing per crop, which at ~8.5 route cost per empty hop is worth more than that Forage while the Harvester is heat-bound.
- **Local work first, hard priorities strict.** Among harvest, sweep, plant, pave and loose items, a target within `LOCAL_ROUTE_COST` beats a farther target of a higher rank. Amplifier, strays, build, care and `pave_first` stay strict: they protect growth or remove work for good. Reuses the step's single-source route map, capped at the threshold, so no second search.
- **Pave first must not starve planting.** Headless run of the wave-1/2 code (empty field, all recipes, 3 leftover items at D14/E11/F12 near base E13): ferrying them across ~10 empty cells took ~5 world days at 15-18 h/day heat rest, and strict `pave_first` held back planting the whole time (23/31 planted, 7 species by day 7; 31/31 with a pre-paved path). `pave_first` is strict only while the material is near or nothing is plantable; else the pave waits behind planting and is taken when the Harvester is near the item. An item beyond `PAVE_ITEM_MAX_COST` (~a day's heat with the carry) is left for a paving seed (3 t life forms).
- **Early Harvester keeps the items nearest the path.** The 4 kept items are chosen by Manhattan distance to the starter path cells first, value second, so the Field Keeper's ferry is short. `PAVE_PATH` is a constant there (cold_boot has no `lib/`); a test pins it to `field_layout.path_cells()`.
- **No detour pickup on unrelated routes.** The single held slot must be empty for `load_seed`/plant, so an item picked up on the way to other work would have to be dropped on a path cell before that task. Locality plus the deferred `pave_first` give the carry-along effect: the item is fetched once it is the local task.
- **inventory_full → early rebalance, direct call.** The live save hit `harvest -> inventory_full` repeatedly. The orchestrator already runs `rebalance_inventory_to_warehouses()` every `STORAGE_TICK_INTERVAL`, so an archive request flag would add a key and change nothing. The Field Keeper calls it itself (cooldown `REBALANCE_COOLDOWN_TICKS`) and retries after `INVENTORY_FULL_RELIEVED_RETRY_TICKS` when Forage then fits, else after the full `INVENTORY_FULL_RETRY_TICKS`. Never sells to make room.

## §1k — Crop Automators: One Round, No Hand-Planted Fill (2026-10-13)

Live save, right after Field Automation: the build phase picked its next step by `work_order()` rank over garden plants and machine deploys together, and kits were bought one at a time (only with none at home). The Harvester went garden → C7 → F7 → C12 → back to H3 for one pondmoss (4.5 h) → F12 (6.6 h), and it hand-planted Crowncap on fill cells (C15, C16) on its way to their automator.

- **Automators first, nearest next.** While any Crop Automator kit is at home, the build step deploys the nearest one by route cost, ahead of garden work. All automators go out in one round over the fill (~20 h with heat rests); then the garden build resumes and the Harvester stays there.
- **Kits bought until stock covers the missing count.** One per pass while fewer are at home than missing, so the round never waits on the Shop. A stray automator still blocks buying (its kit comes back on removal).
- **The Harvester never plants fill.** `harvester_layout()` is the garden minus automated cells; `HARVESTER_FILL_CHUNKS` is gone. A fill cell waits for its automator, which deploys within the round anyway.

## §1g-1 / §1h-1 — Finished Chains Sell Themselves: Biomass and Bio Orders (2026-10-14)

A finished production chain is undeployed and sold by the Automation as soon as each machine is empty ([bio_seeds_planting.md §1g-1, §1h-1](../cheatsheet/bio_seeds_planting.md)).

- **No operator button.** The essence chain's sale used to wait for a status-panel button, out of caution about an irreversible sale. The trigger cannot fire early: Full Biomass never falls back, and a completed Bio Order stays completed. The kits resell at full Shop price, so selling loses nothing but buffered essence or worthless samples. Plants already undeployed on their own. Every completion retirement now follows the same rule.
- **Per biome, not per planet.** Each biome's Bio Orders finish at different times; a biome's chain stops taking new work the moment its own orders are done, and each machine is sold as soon as it has emptied itself. The done list is latched in the archive, because the Exchange that reads the orders is one of the machines sold.
- **Drain by the machine, sale by the Automation.** Emptying a chamber or bin is self-only, so every chain script checks `retire_pass()` in its run loop; the Automation only tries `undeploy()`, and the game's own cargo check decides when a machine is empty.
