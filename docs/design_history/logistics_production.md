# Design History: Production, Storage & Logistics

Why behind supply, demand records, priority ladder, storage and mining logistics (cheatsheet §2a, §2c, §2d, §2i, §10). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

## §2a-0-2 — Multi-Fabricator / Multi-Smelter Racing Bugs

**Pile-on fallback was itself a fix for a real reported symptom**: "fabricator_1 sits idle while
fabricator_2 slaves away producing 100 circuit boards" — with only ONE recipe ever demanded, the
claim's "spread across distinct recipes" logic left every Fabricator past the first idle forever,
since there was never a second demanded recipe to fall back to.

**Load chunking was found from a screenshot**: two Fabricators both needing Glass, one showed 44/1
staged while the other sat at 0/2 — one had grabbed the ENTIRE available Glass stock in a single
`take_item()` call before the other's own poll got a turn. Capped to `FABRICATOR_LOAD_CHUNK_SIZE = 10`
(mirrored to Smelter's ore top-up and, later, Supply Dock's material loading once multiple docks
could share an order).

**Chunking alone wasn't enough — it shrank the race, it didn't fix it.** Continued live reports
after chunking shipped: "smelter_1 grabs 50 silicon in 5 stacks of 10 each, smelter_2 never gets
any." Each `take_item()`/Auto Feeder transfer locks the source Warehouse for the whole transfer
duration, so a smaller per-call chunk still lets whichever consumer's `step()` happens to poll
first win it — and if one consumer consistently polls first (script start order, poll-interval
phase), it wins every chunk, every cycle, forever.

An archive-based cooperative turn-taking scheme (`storage.take_item_fair()`, tracking per-item
"last winner"/"seen consumers" state) was tried first and then **deliberately reverted**: it
doesn't scale to multiple production outposts (an item id is global, but contestion is really
per-outpost — a second outpost's Smelter would needlessly defer to a first outpost's, or collide on
the same key for an unrelated stock pool), and it grows the Data Archive by one entry per distinct
contested item id ever seen, against the archive's hard 512-entry save-wide cap — an unbounded cost
for what should be transient coordination.

Replaced with `production.craft_prefill_units()` (`INPUT_PREFILL_SECONDS = 30`, no archive state
at all — see cheatsheet §2a-0-2 for the formula) — instead of asking "how much is left to load"
(which naturally races toward a big number), it asks "how much do I need staged for the next ~30
real seconds." This fixes the race as a side effect: every consumer's ask shrinks to a short,
recipe-scaled window, so it tops up and stops far sooner, leaving much more frequent openings for a
peer to get its own share in between — a probabilistic, self-limiting fix instead of a
deterministic one, but stateless and correctly local-to-whatever-outpost-has-the-contention.

**Ore intake ignored demand SIZE entirely — a much bigger overproduction bug than the fairness
race, found live: ~80 excess Glass sitting in storage with no active demand.** Smelter's Step 3
buffer top-up used to gate purely on `demands.get(output_item, 0) > 0` and then always fill toward
the full 50-unit cap regardless of how large that demand actually was — a demand of 5 finished
units still triggered filling a 50-unit ore buffer, because nothing compared the top-up *amount*
against the demand *quantity*. Fabricator's `load_inputs()` never had this bug (always bounded by
`required_per_craft * crafts_remaining`, itself netted against stock). Worse with 2+ Smelters
"joined" on the same recipe (the pile-on fallback): each independently filled its own buffer toward
the SAME undivided demand figure, roughly doubling actual refined output before `total_stock()`
ever caught up — matching the observed report exactly, and would have applied even to a single
Smelter alone. Fixed with `get_smelter_worker_count()` + a fair per-Smelter `share` of current
demand, cast into an ore-unit ceiling (see cheatsheet §2a-0-2 for the resulting formula).

---

## §2a-1b — SourceCache Performance Investigation

Found live: what was then a single combined UI+automation script (at the time `panel_1.py`, later
split into the UI card and headless calculator now at `panel_1.py`/`panel_7.py` — see §7's
panel-numbering-quirk note) taking ~10s per call inside `plan_dock_assignments()`, and Fabricator
scripts sitting at "running — busy" for tens of ticks inside `choose_recipe()`. Root cause was two
compounding bugs:

1. **No caching across sibling recursion branches.** `can_source_item()`'s old recursive walk
   passed `seen.copy()` to each recipe input, so two inputs sharing a common sub-item (e.g. Steel
   under both Circuit Panel and Iron Ingot) each independently re-walked that sub-item's own recipe
   chain from scratch — exponential blowup on any recipe DAG with shared ancestors.
2. **No caching across sibling *calls*.** Every `can_fulfill_order()` check (once per candidate
   order, once per dock's current order) and every `recipe_unsourceable_reason()` check (once per
   candidate recipe) independently re-ran Smelter/Fabricator discovery, `list_recipes()`, and the
   fluid `outpost.buildings()` scan from zero, even though none of that changes mid-pass.

`SourceCache` (instantiate once per pass, thread it through) fixed both — see cheatsheet §2a-1b for
the shipped shape.

**A third, initially-missed cost**: `stock(item_id)` originally called `storage.total_stock()` per
item, which discovers Inventory + every Warehouse AND calls `.count(item_id)` on each — D distinct
items across W warehouses cost `D*(1+W)` real game calls for storage alone even after the
recipe-side caching above. Fixed by dropping `total_stock()` in favor of one `.stacks()` call per
building (returns every `ItemStack` in one call), summed into one `{item_id: total_units}`
snapshot — `1+W` calls for the whole pass, regardless of how many distinct items get checked.

---

## §2c — Storage Swap-Fallback Bug Hunts

The swap fallback in `rebalance_inventory_to_warehouses()` (evicting a cheap Warehouse occupant to
make room for a bulkier Inventory item) went through two real bugs before landing on its current
`slots_freed > slots_reclaimed` net-win check:

- **`slots_freed` computed from a stale count.** It was originally computed from the item's
  original slot count captured at the top of the loop, not `remaining` (units still stuck in
  Inventory *at swap-fallback time*) — the direct-move step earlier in the same loop can already
  have moved part of the item out before the swap is even considered, so using the stale count
  overstated the net win. Fixed by recomputing `slots_freed` from `remaining` at the point the swap
  is actually evaluated. Verified by stub test against the exact scenario that prompted this:
  Warehouse full except a 5-unit Titanium Ingot slot, 60 Iron Ingot spanning 6 Inventory slots —
  evicts the 5 titanium (costs 1 slot back), frees 6, a clear net win.
- **Silent failure paths.** Every previously-silent failure branch (`_cheapest_warehouse_occupant()`
  finding nothing, an eviction transfer moving 0 units, or the freed slot still reporting no room)
  now logs a `[storage] Could not clear...` / `[storage] Swap for <item> did not go through...` /
  `[storage] Freed a slot... but it still reports no room...` line instead of silently continuing,
  so a persistently-fragmented item is diagnosable from the console instead of never resolving with
  no explanation.

In practice, because `slots_reclaimed` divides by the small Inventory `stack_size` (10/20) while
`evicted_qty` can be up to a full 2,000-unit Warehouse slot, a swap is only ever a net win for a
*small*-quantity occupant — once every Warehouse slot everywhere holds a large quantity of
something, the swap fallback keeps correctly declining (logged, per above) and an item with no
Warehouse slot of its own stays split in Inventory until more Warehouse capacity is built. This is
expected behavior, not a bug to chase further.

**`best_unload_target()`'s consolidation preference was added from a real case**: a 100-unit
reagent target ended up 50 in one Warehouse + 50 in another, each its own single-slot partial
stack, even though one Warehouse had room for the full 100 the whole time. Ranking purely by
least-full (`fill_percent()`, the old behavior) ignores which Warehouse already has the item, so
alternating "least full" picks across separate deliveries can spread the same item across every
Warehouse one partial stack at a time. Fixed by preferring a Warehouse that already holds
`item_id` over ranking by fill percent, falling back to fill percent only when none already stocks
it.

**The Warehouse `.compact()` sweep (`consolidate_cross_warehouse_stock()`) was removed.** An
earlier note here claimed `.compact()` pulls stock from *other* Warehouses. That was wrong: the
decompiled simworker runs it on the calling building's own slots only (source and target are the
same building), and its outcome codes are just the shared transfer set. Inside one Warehouse the
game already keeps stock packed: inserts top up an existing partial slot of the same exact variant
before opening an empty one, and takes drain the smallest stack first, so each variant has at most
one partial slot. The sweep moved nothing in an 8.4 h log window. Fragmentation can still come from
non-exact property takes (index-order drain), but that has not shown up in play.

Fragmentation *across* Warehouses is bounded by `best_unload_target()`: it prefers a Warehouse
that already holds the item, so an item spreads over at most N full stacks plus one partial. If
cross-Warehouse fragmentation ever shows up in game, the fix is a `transfer_to()`-based
consolidation, not `.compact()`.

---

## §10 — Two-Tier Logistics Demand and Depot Flush (2026-09-27)

A live stall (Seed Maker idle, diversity 3/15) came from the FLEET "leave to drones" switch handing
outpost pickups to drones that could only load at drills: nobody hauled outpost stock home. Floating
haulers now load at Depot outposts through Depot-side staging, and the yield switch only yields while a
hauler drone is alive.

Requests got a `min` (need tier) below `target` (buffer tier). A single target mixed "can't keep working
without this" with "nice stock to have", so a home salt buffer of 2000 would have kept every unit from an
outpost Terraformer short of 6. Need is served first everywhere; buffers share the rest in proportion to
their deficits. Legacy requesters without `min` stay all-need, so their behaviour is unchanged.

Depots clogged by life forms nobody consumes after the Liquifiers retired are cleared with
`InputSlot.flush()`, not a Waste Processor: both only destroy, and the flush needs no extra building or
running script. Because flush discards the whole stockpile, it runs only once everything non-surplus has
been drained out.

## §2i-1 — Home Planned Like Any Outpost (2026-10-01)

**Decision**: home gets its ore, ingot, stockpile and consumer requests from `lib/site_supply.py`
exactly like every other outpost. Its only difference is the Inventory, which counts as home stock.
`production.get_raw_material_demands()` (network-wide ore demand plus a "home ore floor") and
`home_smelter_ores()` are gone; the Rover mines against its home's ore requests
(`vehicle_mining.home_ore_demand()`), haulers read only `logistics_requests` deficits, and the
dead home-demand `PioneerController.run_mining_loop()` was removed (Pioneer miners already ran the
stationed loop for `HOME_BASE`).

**Why**
- The function predated factory outposts. With the Smelters moved to outposts it kept pulling ore
  home that nothing consumed, and every drone and Pioneer hauler re-ran the full demand walk each
  planning cycle (about 1 h 45 m of game time per pass at ~150 running scripts).
- Two demand sources for the same stock (requests and the floor, max-folded per item) and a second
  in-flight bookkeeping (`mining.reserved_yield` from haulers) duplicated what `logistics.pickups`
  already does. `mining.reserved_yield` stays only for Rover mining trips.
- `site_supply` runs from tier 4 (`control_room_automation.py`), the same tier the lib-driven
  Rovers, Pioneers and haulers start at, so no earlier tier depended on the old path.

## §2i-1 — Construction Stock Reserve and Eviction Without Home Fallback (2026-10-08)

**Supply Dock ping-pong.** Fabricator targets take the max of their sources, not the sum: standing stock is meant to serve orders. With the kit and segment stock at the Constructor's home, a Supply Dock order at a remote fab site took that stock (home's buffer stock was free for another outpost's need), the dock site's Fabricator rebuilt it, and a hauler carried the refill back home: two hauls nobody needed.

- **Now**: the Fabricator-built construction stock at the Constructor's home is a reserve (request `keep`). It is not free for other outposts' need, and a dock order counts it out of network stock (`builder_reserve()`), so the dock's own Fabricator builds the order. Units above the stock target stay free.
- **Not done**: a general additive fold of every order over every buffer. Only this reserve had the problem, and the max fold stays right for the rest.
- **Not reserved**: stock no Fabricator builds. A dock order for it would otherwise wait forever.
- **No deadline exception**: a Weekly Order close to expiry does not get to take the reserve. A slow Fabricator could miss the deadline, but so could a slow hauler taking the reserve. Covering both means predicting build and haul times before taking the order: a lot of code to avoid losing part of one order.

**Eviction destinations.** Stranded ore with no smelting site, and every straggler that was not a Constructor item, went home. Home was the trash pile, and an evicted load could fill any destination's free slots.

- **Now**: users of the item first, then storage outposts (storage, a Drone Depot, no building that loses throughput over the outpost cap: they may go over the cap at no cost). No candidate, or no room, means the stock stays. Moving a clog to another outpost is not worth it.
- **Room**: slot-bound. A destination takes the item up to its planned target rounded up to whole slots, never into a slot nobody planned while that leaves fewer than one empty slot (storage outposts: any free slot). Real slot planning per outpost is a TODO.
- **Machine scripts don't depend on autoplay**: a storage outpost is found from the buildings standing there, not from the `storage` role designation. `PENALIZED_TYPES` moved to `lib/storage.py` so both sides use one list.

## §2a — Constructor Build Lots (2026-10-09)

Several Constructor Pioneers working one long power line chased each other: each pass picks the nearest open job the cargo serves, so builders leaving the same spot raced for the same piece, the loser skipped ahead past the winner, and they leapfrogged down the line. A lost claim also fell through to restocking and sent a loaded builder home.

- **Now**: after loading, a builder reserves the jobs its batch covers as a lot in `construction.lots`, a nearest-neighbour chain from its claimed seed job. Peers skip the lot, so two builders take adjacent stretches of one line, or separate sites.
- **One key, not one claim per job**: claiming 50 jobs would be 50 transactions on the shared claims dict. One lot entry is one transaction, and per-job claims still guard the job actually being built.
- **Validity from `fleet.status`, not a lot timeout**: a lot counts while its owner is an active Constructor (same rule as `peer_builders()`, any home). A crashed or recalled builder frees its lot without anyone writing, and a builder charging for a long time keeps it.
- **Seed stays in list order**: picking the seed farthest from peers' lots was considered. List order already starts the next lot where the previous one ended, which is the logical split of a line, at no extra cost.

## §2i-2 — Ground Haulers Load From Drone Depots (2026-10-09)

Pioneer haulers counted and loaded Warehouse stock only, on the belief that a Depot serves drones only. The decompiled simworker says otherwise: `drone_station` has an output ioSlot, so any InputSlot, a Pioneer's VehicleInputSlot inside the service area included, may `take()` from the stockpile. The limit was a script choice.

- **Now**: a Pioneer stop takes from the stores first, then the Depot. Free stock for a ground hauler (`LOADER_VEHICLE`) counts the Depot units the Depot isn't about to push: hauler drone stage requests and same-outpost Smelter wants (`depot_holds()`). Drones (`LOADER_DRONE`) still count everything held, since their Depot stages Warehouse stock for them.
- **Depot last**: the Depot drains freight to Warehouses anyway, so what stays there is mostly staged items, life forms and overflow. A take that races the Depot's own push finds it "busy"; trying it last keeps those races rare. Every Depot take's status is logged, so a refusal the game code didn't predict shows up.
- **Machines and the Supply Dock stay push-fed**: a pull from a Depot that also pushes (Smelter feed, drain) races into "busy". The Seed Maker, Plant Terraformer and Essence Liquifier keep `take_from_depots()`; they raced the drain before this change too.
- **Smelter want as an upper bound**: `fill_to` minus the live input would need a Smelter read per planned source. Over-holding costs nothing: what the Smelter turns down drains to a Warehouse, where the hauler takes it.
- **Not done**: one shared deduction function for the Supply Dock, Fabricator and haulers. Their deductions mean different things (dock promises within one pass, the construction reserve as demand, pickups as claims), so one function would hide the differences instead of removing them. The scope mismatch that caused the "need 1 more" against "got enough" bug is fixed by the shared stock scopes (`lib/stock_scan.py`).

## §2c — Warehouse Strays Folded by a Storage-Pass Scan (2026-10-09)

When a Warehouse answers "busy", `_send_to_best_target()` falls back to the next-best one. That leaves a small second stack, which takes a whole 2,000-unit slot. Because it is a holder, `best_unload_target()` can also route later deliveries to it. Another player's setup keeps one Warehouse empty as an overflow buffer, which moves stock back to the default slots when idle.

- **Scan, not Signal Bus**: a "went busy" event would need a writer in every machine script that sends stacks. It would also miss splits from partial drains, upgrades and top-up overflow. The storage pass already reads every store, so `consolidate_warehouse_strays()` finds splits from their state.
- **No dedicated buffer Warehouse**: the fold targets `best_unload_target(exclude=[source])`, so it can't fight the delivery ranking. Once the stray is empty, rank 1 converges on the main holder.
- **Gated**: a second holder gives `take_item()` a fallback while one answers "busy", and every fold transfer blocks the orchestrator for its feeder cycle. So it folds only when slots are tight (no empty Warehouse slot at the outpost) or when the stray sits next to a recipe partner.
- **`StorageSnapshot`, separate from `stock_scan.StockScan`**: the sweeps need slots (empty slots, capacity, properties), and StockScan keeps per-item totals from `stacks()`. `stock_scan` imports `storage`, so the snapshot lives in `storage`. Rebalance and reclaim had read `slots()` 2+N times per pass; now every sweep reads each store once.
- **Rebalance routing**: the Inventory sweep spread items by least fill and opened the same splits. It now asks `best_unload_target()`.
- **Follow-up, same day: stop the splits at the source.** A busy-heavy outpost (4 Smelters plus Fabricators and Pioneers on 4 Warehouses) had glass, iron and titanium ingots in all 4 Warehouses. Every split in the logs was a busy retry chain ending in "new stack", once even next to silicon (clash 36). The fold never ran: one Warehouse still had an empty slot. And holders tied on neighbour heat fell back to least full, so deliveries rotated over every holder and fed the strays.
  - A busy retry (`_send_to_best_target()`, the rebalance direct move) now passes `holders_only=True`: it never opens a new stack. A busy holder frees up within a few ticks; a staged stack costs nothing meanwhile.
  - Holders rank by units held (largest first) instead of neighbour heat and fill. That costs one `count()` per holder, usually one or two.
  - The fold gate is per stray: its own Warehouse full, or 3+ holders of the item, instead of every Warehouse at the outpost full.

## §2a-0 — Producer Holdings in Stock Netting (2026-10-09)

Fabricator targets netted against held stock plus the Fabricator output pipeline. Inputs loaded into a stockpile had left held stock but were counted nowhere. Loading 10 gas pipe segments into a Thermal Cap Kit craft read as a new shortfall of 10, so the Fabricator crafted 9 more segments and kept preempting the kit order. Smelter output and ore loaded into Smelters had the same gap in ingot and dock ore demand.

- **One count, not one scope in `stock_scan`**: `HELD` also feeds Supply Dock readiness, logistics requests and seed supply. Units inside a machine can't be taken by those, so the holdings live on `SourceCache` (`fab_have()`, `network_have()`) and only "make more" netting adds them.
- **Reservations stay held-only**: blueprint reservations and dock pushes protect units that can still be taken; a loaded input can't.
- **Shared site targets**: an entry carries its roots' `fab_have()` at compute time and a reader lowers each root by what is gone since, and it is stamped with the computing `SourceCache`'s birth tick. A long automation pass had published old reads as fresh, and units delivered from the pipeline into a Supply Dock still counted as wanted (2 surplus kits after an 11-kit order).

## §2a-p — One Priority Ladder from Order to Ore (2026-10-10)

Three unrelated rankings decided the same work: hauling used an `urgent` flag over a two-row need/buffer ladder, the Fabricator six set-membership tiers (manual-blocking, manual, blueprint, upgrade order, the rest, backlog), the Smelter none at all (first claimable recipe in `list_recipes()` order, with the ingot buffer and the key-unlock look-ahead on a separate idle-only path "because Smelters have no priority tiers"). Supply Dock scores never reached production, dock-owed ore went to miners through a side key haulers could not see, and a backlog item that was also an intermediate of an order ranked last.

- **One integer 0-999, bands by the hundreds** (`lib/priority.py`): BLOCKER 900 (operations stalled: a settled part a job waits on, nothing more arrives by waiting) > MANUAL 800 (manual orders, operator-placed blueprints) > BUILD 700 (autoplay construction blocking progress now) > ORDER 600 (current Earth orders) > UPGRADE 500 (fleet parts) > NEED 400 (a machine or role cannot run without it) > BUILD_AHEAD 300 (plan-ahead construction) > ORDER_AHEAD 200 (the next key unlock orders) > STOCK 100 (buffers). The owner's rule: what risks operations beats what blocks progress now, beats what will block it soon, beats what is sometimes relevant. Earth orders therefore moved above fleet upgrades and under autoplay construction; before, blueprints beat upgrades beat orders.
- **Bands are lexicographic, the fine value only breaks ties inside a machine.** A unit of a higher band always goes first (the lesson of 2026-09-29: a 500-unit buffer load must never outrank a 1-unit need trip). The fine value (dock score, blueprint priority) orders two Earth orders inside the Fabricator and the dock planner; haulers ignore it: a trip is scored by what it delivers per metre and mixes items of many fine values.
- **The ladder is the one demand shape.** `[[prio, cum_units], ...]` replaces `(target, min, urgent)` requests, the max-folded Fabricator target and the Smelter's flat demand. Stock covers the highest level first, so a stock top-up never rides on an order's priority (the 2026-10-07 blueprint-shortfall rule, generalized). Child demand inherits each parent level's prio; contributions of several parents sum, root floors of one item max-fold, as before.
- **Depth inside a band, not a "blocking input" set.** An intermediate a manual order is stuck on used to be found by a second cascade (tier 0). It now inherits MANUAL and sorts first by recipe depth, which covers upgrade-blocked inputs too and ends the Fabricator re-selecting a parent whose input nobody builds.
- **Hysteresis per band, with a starvation exit.** The sticky recipe stays (a switch ejects staged inputs: two feeder trips per unit) but only against same-band candidates; a higher band preempts. A recipe with less than one craft of an input in local stock and nothing in flight gives way to a same-band candidate that can run now.
- **Smelter preemption is bounded.** A higher-band demand preempts the current recipe only once it is worth one craft; inside a band the prefill-window minimum (`switch_min_demand()`) and the pile-on rule stay. The buffer and look-ahead refill became ordinary levels of the same demand map, so a Smelter's demand share is sized to the band it works and never widened by a buffer beneath an order.
- **Dock-owed ore is one request.** `dock_ore_levels()` folds into the smelting site's ore want at the order's prio, visible to miners and haulers alike. The miner-only key was added on 2026-10-08 to keep haulers from shuttling ore; since raw dock ore became a site request two days later, one path is consistent. Not every smelting site mines every ore (markers decide), so haulers carrying ore between smelting sites is wanted.
- **Not done: per-requester merge of one item's request.** Requests keep one owner per (outpost, item), first writer wins (`skip_foreign`). Merging ladders of several requesters would end the overwrite between `site_supply`, `site_evict`, `salt_reserve` and the Seed Maker's two writers, at the price of every reader's shape; the ownership split that exists today (salt by `pump_salt`, ore/ingots/stock by `site_supply`) holds.
- **Not done: a per-pass band subset in the planners.** `plan_take()`, `route_left()` and friends loop over all nine bands. Measured cost is in `ROUTE_COST_PER_ITEM`; limiting the loops to the bands any request uses is the next step if it binds.

## §2a-q — Demand Record, Not an Order Ledger (2026-10-11)

After §2a-p a Smelter step spent about 85% of its ~400 ticks on demand planning: `fabricator_target_ladders()` (~110 ticks) and the site targets (~70) on every poll, with the shared `production.site_targets` copy reused on only 10–40% of reads (it was stamped with `SourceCache.born`, so a result from a long pass was stale when published). The ticks went into game reads, not ladder arithmetic: a stock scan per outpost, the holdings of every Fabricator and Smelter, blueprint jobs, fleet cargo, dock orders. Eighteen machines redid them per poll. The stretched prefill window (working tree, never committed) only hid it.

An "Order class" ledger was considered: one record per order with its cascaded demand, decremented as units finish, units allocated to orders. Rejected:

- **Most roots are floors, not counts.** Stock targets, the orders book, ingot buffers and site stockpiles are "keep at least N". The consumable roots already count down in game state (a dock order's `shipped`, a built blueprint, `consume_manual_order()`), and the one ledger that exists, manual orders, needed `MANUAL_TRANSIT_KEY` to stay honest.
- **Stock moves without us.** Constructors load batches while jobs stay pending, docks ship, Depots push, the operator moves stacks, a script dies between craft and decrement. Netting a target against live stock on every read is what makes the system self-heal; a ledger drifts and its reconcile pass is the cascade again.
- **Allocation already exists**: `fabricator.wants`, `dock_delivery_targets()`, `logistics.pickups`. A second reservation layer would fight the first.
- **A transaction per craft** per machine on the hot path, against a read-only hot path today.

Built instead:

- **One demand record** (`production.demand`, `lib/production_demand_record.py`): network ladders, per-site targets and ship plans, Smelter demands, each with the `have` it was netted against, stamped with the publish tick. The orchestrator publishes it last in `between_steps()`, gated on `demand_signature()` (the archive writers of demand plus blueprint job ids) or a backstop, in slices bounded by a tick budget per call; `publish_site_requests()` publishes it for free from its own cache. The reader nets the record locally by what changed since its `have`; it never raises a target. The record also carries the recipe depth map and the gross construction cascade, the two other results every Fabricator and every home dock used to recompute alike.
- **Machines never write the record.** The first design let a machine that found the record stale take a lease and publish the whole record. Measured headless (mid-late sample, 0.6 h): a Smelter doing that spent ~1,400 ticks on it, the orchestrator's sliced refresh took 1,653 ticks, and Smelter output halved against baseline. Now a machine without a usable record computes only what it needs, as before the change; the record's stale window is long (3,000 ticks) because readers net it themselves; a refresh runs to completion inside a 400-tick budget per call.
- **The stretched prefill window was a symptom.** With the plan path out of the poll the window went back to 30 s. Headless, mid-late sample, 0.6 h, against `main`: Smelter output 3,249 → 4,490 units, Fabricator 1,435 → 2,766, median Smelter step spacing 1,180 → 190 ticks.
- **Atomic tasks: built, measured, switched off.** After PR 40 (logging inside atomic calls) the refresh was split into a prefetch and one `run_atomic()` call per task, sized on the synthetic worlds (largest ~6.8k opcodes). On the mid-late sample save the orchestrator died on the 10,000-step cap at once: real tasks are 10 to 300 times larger. Measured there with atomic off (ticks x allowance, an upper bound): Fabricator part of one site up to ~150k steps, network targets ~80k, finish ~25k, a site's Smelter need ~19k, an ingot batch of 6 outputs ~4k. Only the ingot batches would fit. `ATOMIC_TASKS = False` keeps the split and the measuring; atomic tasks need far smaller work units first.
- **Ship-before-craft was the largest repeat.** `site_spare_elsewhere()` re-scanned every other outpost's storage and re-read the hauler reservations once per short item (~60 full scans per Fabricator site). Sharing one `PlanReads` per pass (`SourceCache.plan_reads()`) halved the largest task (~270k to ~150k steps) and cut a refresh from ~1,550 to ~1,300 ticks. Headless, 0.6 h against `main`: Smelter output 3,249 to 5,204 units, Fabricator 1,435 to 3,542.
- **Index reads, not sweeps.** A tick profile of a refresh on the sample save showed the Fabricator part of a site going to ship-before-craft: per short item, a free-stock read at every other outpost (56 reads for 11 items), each sweeping every store row of that outpost's scan, plus a linear search of the recipe lists per make-time estimate. `StockScan` now indexes its rows per kind and per item on first read, `PlanReads` reads each Depot's holds once per plan, and `production_cascade.recipe_for_output()` keeps the output table per script like the recipe index. The cold Fabricator part of the busiest site dropped from ~355 to ~275 ticks (median).
- **Open cost: the orchestrator.** A refresh still spans ~1,250 ticks of orchestrator time, of which ~750 is its own work, and its parking passes run ~750 ticks apart (226 on `main`). The Fabricator part scales with short items x other outposts (the 56 free-stock reads remain, each now cheap but not free) and with busy sites: a second busy site adds ~190 ticks. The network cascade (~170 ticks) is ladder arithmetic, not reads.
- **Plan and feed split** in the Smelter and Fabricator controllers: the feed path (drain, top up, wants) runs every poll from the last plan; the plan path (demand, recipe choice) runs only when the record changed, a backstop passed, or the planned work is exhausted or blocked.
- Not a third automation (every running script taxes the others, §1d-1) and not `builder_automation.py` (its upgrade drains hold it for long stretches).

## §2d — Mining Without Resource Markers (2026-10-19)

Each surveyed mineral site used to get a `resource.` map marker whose note named the outpost that mined it. Stationed miners mined only marker ores, and the dock roles, dock ore and stranded-ore rules read the same notes. On the 2026-10-18 run no marker was ever assigned: only `mining`-designated outposts got sites, and the factory outposts had no role. Before Cartography (140k TP) there was no `markers` component at all, so stationed Pioneers mined nothing.

- **Demand picks the ore.** An ore joins `mining.active_ores` the first time anything wants it at `NEED` or above, and only active ores keep a `STOCK` buffer. The operator rejected a fixed ore order: iron, silicon and titanium already arrive in that order from demand, and titanium also needs a drill that cuts it.
- **The miner picks the site.** Miners already ranked sites by purity against round-trip drive. Without the marker filter they take any surveyed site their drill cuts and a full battery reaches.
- **Planners read reach, not ownership.** Each stationed miner publishes the ores it can reach (`mining.reach`). Dock roles, dock ore and stranded ore read that, so `site_supply` and `supply_dock` need no vehicle import. A mining outpost keeps its buffer only for an active ore its miners reach; otherwise eviction and mining would move the same ore back and forth.
- **Never unassign.** The active latch only grows. Dropping an ore when demand fades would empty and refill buffers with every order cycle.
- **Old markers are cleared, not migrated.** They carry nothing the reach record lacks. The archive cleaner and every unsupported-marker rebuild remove them.

## §2j — Tier-Deficit Snapshot (2026-10-22)

Every drone pick, Pioneer pull and role-demand publish recomputed every outpost's tier deficits and free stock a few ticks apart (save 0839: 209 of 342 wrapped ticks per drone plan). `lib/logistics_snapshot.py` now builds them once per round into `logistics.tier_snapshot`. Plan and measurements: [vector1_tier_snapshot_2026-10.md](../plans/vector1_tier_snapshot_2026-10.md).

- **Producer in the orchestrator loop, not a new automation.** `SnapshotPublisher` runs from `between_steps()` with its own 600-tick interval, a few outposts per call. A demand-refresh task kind would have inherited that record's 1,000 to 1,700-tick rounds; a separate automation costs every script allowance.
- **Computed tiers, corrected on read by pickups.** Raw stock in the record would leave the per-item tier math, the larger cost, in every consumer. A reader subtracts only pickups that grew since the build: towards a destination from its top band down, from a source in every band. A pickup that left the in-flight set is ignored, so a delivery does not reopen a covered deficit. The correction cannot see units claimed after the build and delivered before the next one, nor stock arriving from production; the claim-time trim below catches both.
- **Fair-share rivals from the record.** Rivals were each request's published `"have"` plus in-flight, which lagged the destination's own live deficit (save 0839: splits of one supply summed to ~95 %). The record's deficits include live stock and mining yields, so splits now sum to the supply; an outpost with yield inbound counts as a smaller rival.
- **Live only at the claim.** Before `claim_pickups()` the chosen destination's legs are capped at its live deficit, with rival claims since the plan's `seen` added back from the same pickups read, so the claim's own destination cut does not count them twice. Sources are never re-read: a short pickup self-corrects. A Pioneer pull has no alternates, so a snapshot trip that trims out re-plans live in the same pick; otherwise every Pioneer would pick the same filled destination until the next round.
- **A failed build discards the round.** A record that left out a failing outpost would hide its demand from every consumer while the error lasts; without a fresh record the consumers plan live.
