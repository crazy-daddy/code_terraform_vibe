# Design History & Postmortems

This file holds the *why* behind decisions in [`AI_CHEATSHEET.md`](AI_CHEATSHEET.md): bug-hunt
narratives, rejected approaches, root-cause postmortems, and design-reasoning that don't belong in
a quick-reference doc but are worth keeping discoverable. Organized by the same section topics as
the cheatsheet, so a `§1b`-style reference there maps to a matching heading here. Numbers/formulas
that are still the live source of truth live in the cheatsheet, not here — this file is prose,
not a duplicate constants table.

---

## §1a/§1a-1 — Power Grid: Master Election Removal & Night Duration Calibration

`PowerGridManager` used to be instantiated once **per solar generator** (`lib/solar.py`'s
`SolarController`), with every instance independently re-electing the same single Master every
tick (`check_master()`: sort every solar id on this generator's grid by numeric suffix, lowest one
currently `run_control.is_running()` wins) purely so they could all agree on which ONE of them
should call `supervise_grid()`. That election is gone — `panel_7.py`'s AUTOMATION section is a
single always-running process, so it just owns grid supervision directly, one `PowerGridManager`
instance per grid, with no election needed at all. `lib/smelter.py`'s `SmelterController` lost the
mirror-image Leader election the same way, for the same reason (the "inventory manager" sweep now
runs centrally from `panel_7.py` instead of whichever `SmelterController` instance won that tick's
election).

`resolve_pattern_machines()`'s outpost-buildings fallback was removed too (it read
`self.machine.outpost`, impossible without a bound machine, since `PowerGridManager.__init__` no
longer takes a `machine` param) — the fallback chain narrows to the grid snapshot's own
`.machine_ids`/`.members` (primary, always populated for a real grid) → the numbered-guess
`get_component(f"{prefix}{i}")` last resort. Deliberate narrowing, not an oversight.

**Night duration used to be empirically calibrated, not a constant.** The old
`power.night_duration` archive value (measured `sunset_hour -> sunrise` gap, EMA-smoothed in
`handle_sunrise()`) chased a schedule that never actually varies day to day — the old approach was
only ever wrong immediately after a script restart while it re-converged toward the same value
every time. Replaced with `NIGHT_DURATION_HOURS` computed once at module load from the decompiled
simworker's exact day-cycle schedule (see the cheatsheet's §1a for the derivation and exact value)
— nothing left to calibrate for the *duration* specifically (the *amount* of overnight Wh,
`power.night_wh`, is still genuinely variable and still calibrated live).

---

## §1b — Thermal Cap / Steam Turbine: Fluid Routing Bug Hunt

This section shipped in three escalating passes, each one uncovering a deeper bug once the
previous fix didn't fully resolve the reported symptom (a Thermal Cap repeatedly ping-ponging
between two unreachable Gas Tanks at a different outpost, never trying the one actually
pipe-connected to its own outpost).

**Pass 1 — shared blacklist clock.** The original blacklist implementation used one shared counter
that wiped the *entire* blacklist at once on a fixed timer. With 2+ simultaneously-unreachable
candidates ranked ahead of the one genuinely-reachable target (by fill_pct/discovery-order ties),
eliminating all of them could take longer than that window — the shared timer would erase
already-made elimination progress and restart the cycle from the first bad candidate before ever
reaching the real one. Fixed by giving each blacklist entry its own independent expiry tick
(`PerEntryBlacklist`, now the shipped mechanism — see cheatsheet §1b). Verified by stub test: an
older entry expires while a newer one stays blacklisted, and a full elimination-order test (two
unreachable tanks → correctly settles on and stays on the third, reachable one).

**Pass 2 — this fix alone did not resolve the ping-pong.** A second, more fundamental bug was
still there underneath it, found by the player debugging in-game and confirmed by inspecting the
fill-percent helper: `discover_network_buildings()` used to append the raw `BuildingRef` from
`outpost.buildings(type_id)` directly. Per `docs/components/outpost.md`, that's a lightweight
*snapshot* carrying only `.id`/`.name`/`.type_id`/`.outpost`/`.powered`/`.position` — **not** the
type-specific live methods (`fill_pct()`, etc.) that only exist on the full resolved component
(`get_component(ref.id)`). So the fill-percent check failed for *every* tank, always hitting the
"unreadable, treat as 1.0" fallback — degenerating the fill-based sort into a no-op tie broken
purely by discovery order, **and** defeating the fast path too (a healthy current tank also reads
as `1.0 >= GAS_TANK_REBALANCE_FILL_FRACTION`, so it never short-circuits, forcing a full rescan
every step). Net effect: selection became "skip current, take the next one in a fixed
discovery-order list" every call — a stable alternation between whichever two candidates sit
adjacent in that order, never advancing to a third. Fixed by resolving each `BuildingRef` via
`get_component(ref.id) or building` inside `discover_network_buildings()` itself — the same
`get_component(id) or ref` pattern already used correctly in `storage.py`'s
`discover_storage_buildings()` and `vehicle_energy.py`'s `get_all_charging_stations()`; this was
the one discovery helper in the codebase that hadn't followed it. Verified by stub test using a
`BuildingRef`-shaped fake (deliberately no `fill_pct()`) distinct from its full component,
asserting fill-based sorting reflects real values instead of a universal `1.0` tie. **Lesson for
any future `outpost.buildings()`/`outpost_network`-based discovery helper**: always resolve to the
full component before relying on anything beyond the five `BuildingRef`-native fields.

**The `0.98` rebalance threshold was deliberately raised from an initial `0.85`.** That lower
threshold re-evaluated every `step()`, so with two-or-more tanks both hovering above it, whichever
read as "less full" that particular tick flipped every cycle, reconnecting `steam_out` constantly
and never giving flow a chance to establish on either one — pressure climbed unchecked with
nowhere actually receiving it, causing real overpressure blowoffs. `0.98` ("truly full") only ever
abandons a target once it genuinely can't take more, guaranteeing no oscillation: "imperfect load
balancing" loses to "never interrupts flow."

**Turbine candidate ranking (same-outpost-first) was added from a real case**: turbine_5/turbine_6
initially connected to `gas_tank_2` at a *different* outpost with no completed pipe route to
either, instead of trying their own outpost's tank first — `connect()`'s `"ok"` status doesn't
catch this, so the wrong pick still burned a full `STALL_STREAK_BLACKLIST_THRESHOLD`-tick stall
window (and, once blacklisted, a full `RESCAN_INTERVAL_TICKS` window before even retryable) before
falling through to a reachable candidate that was available the whole time.

**Discovery-cost profiling (three further passes, see §1d below for the tooling) found the real
per-step cost was elsewhere.** With the network walk itself gone via the fast paths, Thermal Cap's
`step()` still cost 2-3 sim ticks every call (Turbine's cost ~0). Root cause 1: the Cap's fast path
still resolved its *currently connected* tank via a fresh `get_component(current_id)` round trip
every step just to read `fill_pct()`. Fixed by having `discover_network_buildings(resolve=True)`
return live building objects directly, cached in `FluidOutputRouter._target_lookup` (an id →
object dict, populated from every discovery batch, never wholesale-cleared) so `_resolve_target(id)`
becomes a plain dict read after the first time an id is seen. Verified via a stub test asserting
zero `get_component()` calls across 20 consecutive healthy steps (previously: one per step).

Root cause 2 (still ~2 ticks/step after the above): `ensure_output_connection()` called a port
method **unconditionally on every call**, whereas Turbine's healthy fast path calls no port method
at all — it trusts its own `self.connected_input` boolean and only queries the port on the rare
blacklist branch. Fixed the same way: `FluidOutputRouter` tracks `self._connected_id` locally,
updated only by its own `connect()` calls and blacklist decisions, so the port is queried exactly
**once ever** — a one-time sync on first `ensure_connection()` so a script reload recovers an
already-working connection. That one-time sync originally called `port.connected_to()` (the
renameable display name) while every other lookup keys on the stable id via `connected_id()`/`.id`
— a latent bug (a renamed Gas/Liquid Tank would desync the cache right after a reload), fixed
alongside this same unification so the one-time sync now calls `connected_id()` too. Verified via
a stub test asserting the port's id method is called exactly once total across bootstrap + reselect
+ 20 healthy steps (previously: once per step). A third pass still showed Thermal Cap reading ~2-3
against Turbine's ~0 with nothing left in either script's own code to explain the gap — see §1d
below for why that's where the investigation stopped.

**Lesson learned generally**: for any "read a possibly-external object by remembered id every
step" cost, keep the object reference from whatever discovery/connect call first produced it,
rather than re-resolving by id every time.

---

## §1d — Per-Script Tick-Cost Profiling: Thermal Cap Case Study

Two profiling passes each found a real, *sustained* per-step cost with no periodic spike at the
discovery-cache/rescan intervals, which correctly pointed at genuine bugs — see §1b above for what
they were and how they were fixed (both verified via stub tests confirming the call counts dropped
to zero/near-zero). A third pass still showed Thermal Cap reading ~2-3 against Turbine's ~0 with
nothing left in either script's own code to explain the gap — at that point the signal had reached
the profiler's own noise floor (ambient cooperative-scheduling jitter, or a fixed engine-side cost
of that specific component's own methods, neither fixable from script code) and further chasing it
stopped being productive.

That's the profiler's actual working mode and its limit: it can't measure a single call's cost
directly (see the cheatsheet's granularity-limit note on why a `0` doesn't mean "cheap"), and a
*sustained per-step* delta with no periodicity matching a known cache/interval constant is a
reliable signal worth grep-ing for once or twice — not an oracle to keep re-running against the
same script once every explanation in its own code has been exhausted.

Instrumentation was added to `lib/thermal_cap.py` and `lib/steam_turbine.py` for this
investigation, then deliberately removed again from both once it stopped yielding actionable
findings — `lib/profiling.py` itself is kept for any future script suspected of doing real bulk
per-call work.

---

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

`consolidate_cross_warehouse_stock()`'s `.compact()` call was confirmed, by observation, to
genuinely pull stock from *other* Warehouse buildings into the one it's called on — not a purely
intra-building operation, which its outcome vocabulary (shared with `transfer_to()`:
`source_under_construction`/`source_changed`/`slots_full`/`target_full`) only makes sense under.
This also matches why the game would expose it at all: with Auto Feeders, a single Warehouse
already adds to / draws from its lowest-numbered occupied slot for a given item on its own, so a
purely intra-building `.compact()` would have nothing to ever actually do.

---

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

## §7 — Control Room Panels: The Headless Split & Overlap Bugs

**Why the automation calculator had to become headless.** A single combined script (originally
`panel_1.py`) used to both draw the STATUS/AUTOMATION card *and* run all the automation itself
(grid supervision, rebalance sweep, outpost sync, `supply_dock.plan_dock_assignments()`). Found
live: `plan_dock_assignments()` running inside that same per-tick loop (even after §2a-1b's
`SourceCache` fix cut its cost to ~2s) wedged the card's own rendering outright — confirmed via
temporary debug prints that the script kept looping and completing fine underneath
(~100ms/iteration) the entire time the card stayed visually blank, with no exception anywhere.
There's no known threshold under which an occasional multi-second stall is safe for a script that
also renders every tick, and this game has no true background/daemon script type — a Custom Panel
is the only slot that can host an "always-on, not tied to one building" process — so the fix was
structural, not a further speedup: the calculator became headless
(`sleep(1.0)`-paced like every other controller's `run()`), publishing its result summary to
`archive` instead of drawing it directly. Everything the UI script draws (STATUS's clock/power/
storage/alerts, the version gate, the manual buttons) is a cheap single-call component read or a
rare user-triggered one-off, not the chronic per-cycle cost that forced the calculator headless, so
it stays inline in that UI script.

**Why the panel-numbering table exists at all.** Custom Panel ids are assigned by the game on
creation and only ever increment — deleting a panel doesn't free its number, and cards can't be
drag-reordered once placed (confirmed live; a ticket was filed with the dev about both). The
calculator started out as `panel_1.py` (the first panel that exists on any save) but was later
recreated at a new number to get the UI card into the visual slot the operator wanted — hence the
"currently" qualifier on every cross-reference to a specific `panel_N.py` filename.

**Two real overlap bugs, screenshot-driven** (text was visibly stacked on top of other text
in-game):
1. `card(x, y, w, h, title)` already renders its own title bar text. All three cards additionally
   called `panel.label(24, 34, TITLE, "caption")` right after — a second, independently-positioned
   render of the exact same title, landing almost on top of the card's own title bar. Removed the
   redundant `label()` call in all three.
2. `slider(key, x, y, w, default, label)` draws its own `label` text at a position the script
   doesn't control — pairing it with a separately-positioned `panel.draw_text()` right after it
   (to show the slider's live numeric value) visibly collided with the widget's own label. Fixed
   by folding the live value INTO the label string itself instead of a second draw call. The
   scroll slider does the same, but the "X-Y of N" range text can only be computed *after*
   `slider()` returns a value for this tick, so it's built from the return of the *previous* tick's
   call (a plain script-level variable persisting across the `while True:` loop, the same way
   `self.wh_per_progress` persists across a controller's own loop) — a one-tick lag, invisible
   since the panel repaints every tick regardless.
3. `panel_2.py`'s narrow-mode per-vehicle row placed the location text almost directly under the
   role pill — the pill renders taller than the assumed 16px gap allows, so the two visibly
   overlapped. Fixed by moving the location text down and widening narrow-mode `row_height` from
   `54` to `64`.

These three produced the general layout rules now listed in the cheatsheet's §7 (never duplicate a
`card()`'s own title, fold a widget's live value into its own label instead of a second text
element, give a `pill()` more vertical clearance than plain text, anchor fixed-footprint elements
from the edge rather than a width fraction).
