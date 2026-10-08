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

---

## §8 — Live-Debug Bridge: How the Command Channel and Library Caching Were Established

The general external-command channel was found (2026-09-22) from a real stale request left in `command.json` by earlier tool use, not reverse-engineered blind. Sending `"action":"run"` for `rover_1.py` force-restarted the running script (fresh startup, tick counter reset). The same session showed that restarting `rover_1.py` after syncing a new `lib/vehicle_mining.py` still ran the stale cached module. Every relevant VS Code command was then tried against the changed library file (Run Script in Game → `context`, Create Library in Game → `file_exists`, Import File as Game Library → `duplicate_name`, Rename Library and Update Imports → `no_change`); each failed for a semantically correct reason, never "not found", ruling out a hidden apply command. `scripts_sync.py --auto`'s launch retry exists because a freshly re-filled `drone_2.py` failed an immediate launch and succeeded after a short wait. Library registration via `create-library` was confirmed 2026-09-24 (`drone_upgrade`, `fleet_upgrade` → `{"ok": true}`).

---

## §9 — Tiered `scripts/` Migration

pre-restructure codebase written/tested against save with 60 techs unlocked (incl. `data_archive_unlock`, `custom_panels_unlock`) → moved wholesale into `4_controlpanel/` as honest home tier (see `devtools/_migrate_from_root.py`), not guessed apart per file. `0_cold_boot`/`1_early` seeded separately from former `early_game_runner/` submodule's ([code-terraform-earlygame-automation](https://github.com/crazy-daddy/code-terraform-earlygame-automation)) `early_game_runner/templates/` (flat) and `early_game_runner/templates/early/` (richer) boilerplate. That submodule = this project's own earlier `code-terraform-earlygame-automation` prototype, not `inspirations/vakermit`. Flat `early_game_runner/templates/*.py` = thin `from <lib_module> import ...` wrappers around project's own `lib/` controllers (`terraforming.py`, `solar.py`, `smelter.py`, ...), need `research_shared_library` → wrongly copied into `0_cold_boot` in initial seeding. Only `early_game_runner/templates/early/` genuinely self-contained (no `lib/`/game-module imports), belongs at `0_cold_boot`/`1_early`. `0_cold_boot/power/solar.py` = hand-trimmed exception: `early_game_runner/templates/early/solar.py` bundles full Ship-Computer building-buyer speedrunner around tracking loop, so cold-boot gets few-line sun-tracking-only script extracted from it. `fabricator`, unified `pioneer` (destination-routing, distinct from `pioneer_scout`), `steam_turbine`, `thermal_cap`, `water_pump` have no self-contained early equivalent yet → removed from `0_cold_boot` rather than left broken. They resolve once save reaches tier defining them (currently `4_controlpanel`). Splitting rest of `4_controlpanel` into earlier-tier-capable content = manual follow-up (see TODO.md), not automatic.


**Collapsed to two tiers (2026-10-04).** An audit of `scripts/` found that only 16 files were ever replaced by a higher tier, and 14 of those swaps happened at or before `4_controlpanel`. Tiers 5–10 held almost only new files. Those were already deployed early (`lib_chain()`), or they matched a slot only once their machine existed, so their `.criteria` gates added nothing. `2_libunlock`/`3_archiveunlock` were empty markers. `1_early` needed no gate of its own either: its Solar buyer guards `computer` behind `research_computer` itself, and `shop`/`research` exist from the start. Result:
- `0_cold_boot` (self-contained, no `lib/`) + `4_controlpanel` (full stack). `LIB_UNLOCK_TIER_NUMBER = 4`.
- The tier-1 Solar buyer replaced the tracking-only cold-boot Solar. The Pioneer Scout became `0_cold_boot/pioneer/pioneer.py`, so pioneer slots match before tier 4. The `mount_vehicle.py` step moved inline into the early Rover/Pioneer scripts, because scripts_sync has no separate mount pass.
- The planting Harvester (`field_keeper.py`) became the only tier-4 Harvester: before Seed Makers it degrades to the loose-item sweep.
- The two Power Guards (tier-4 night forecast, tier-5 combined reserve) were the one real fork. They merged into one `lib/power.py` that picks its strategy per grid from the generator mix (`grid_phase()`: solar / steam / oil / reactor; cheatsheet §1a). The deciding point: what a grid needs depends on its generators, not on how far the save has progressed, and a save can have a solar-only grid next to a steam grid. The reactor phase only stops oil *surplus* burning. Idle Oil Generators already park themselves through `script_parking`, so no extra park mode was needed.

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

## §12 — Script Cost Scales With Running-Script Count (2026-09-30)

Machines felt "behind" (Harvester, Smelter, Fabricator; Supply Docks joining completed orders). A
performance pass cut per-poll work: building discovery memoized for 2 s (`production`, `storage`,
`drone_energy`, `vehicle_energy`), one `SourceCache` per Fabricator step, Harvester geometry/per-step
caches and a route search that stops at the first reached target, Pressure Generators sleeping until
their sync window, slower polls for solar/pumps/turbines/thermal caps/oil generators/Crop Automators,
nearest-station-first arbitration for Drone Service and Charging Stations, and the dock plan published
on its own 5 s timer (Docks also re-check a planned order is still active).

The measurements behind it (docs/BENCHMARK.md) first looked like one interpreter budget shared by the
awake scripts, which argued for slower polls everywhere. Further runs disproved that: stopping all 8
Control Room cards (always awake) changed nothing beyond their count, and stopping 19 solar trackers that
sleep 10 s at a time helped exactly as much as their count predicts. The decompiled scheduler confirmed the rule: each script gets
`min(1000, floor(50000 / N))` steps per tick, N counting running and sleeping scripts, so up to 50 scripts
run at full speed and beyond that a fixed 50,000 steps per tick are split evenly. The Smelter/Fabricator active poll therefore went back to 1 s: a faster poll costs
only the script itself.

A rewrite with centralized control was considered and rejected: the slowness was pacing and
recomputation, not structure, and *self only* setpoints (`set_tilt`, `set_throttle`, ...) reset to idle
whenever a script ends or is stopped (measured on a solar panel), so machine scripts cannot be replaced by
one central script. The remaining levers are fewer running scripts (retire machines that don't earn their
share, merge Control Room cards, start scripts only while their machine has work) and computing shared
results once centrally; both are in TODO.md.

## §7a — Suspended Generators Froze Panel Cards (2026-09-29, fixed in game v0.1.29)

A generator left suspended in a Control Room card (`any(<genexpr>)` stopping at its first match,
or `next(<genexpr>)`) froze the card on its last frame while the script kept looping. Cause: the
simworker commits a panel frame only at a top-level loop boundary with `loopDepth === 1`, and a
suspended generator's `for` loop left `loopDepth` raised. We worked around it with list
comprehensions in panel code (`devtools/panel_generator_repro.py` reproduces it). Game v0.1.29
saves and restores `loopDepth` in `enterGeneratorFrame`/`exitGeneratorFrame`, and the repro keeps
updating live, so the panel rule was dropped.

## §7b — Headless Workers Moved to Automations (2026-09-30, game v0.1.29)

Before v0.1.29 a Custom Panel was the only slot for an always-on script tied to no building, so the
Control Room calculator (`automation_panel.py`) and the Warehouse upgrade worker
(`warehouse_upgrade_panel.py`) ran as panels that drew nothing (see §7). The v0.1.29 Automations
tab (Computer > Automations) gives such scripts their own slot type: no machine, no power supply
(a brownout never pauses grid supervision), no card. Both moved there as
`control_room_automation.py` and `warehouse_upgrade_automation.py`; `scripts_sync.py` role-matches
`automation_N` slots the same way as `panel_N`. The move does not change the running-script count.
`run_control` still only targets machines (`f4()` looks up `state.machines`), so an automation
cannot be started or stopped from another script.

## §1l-1 — Wildlife Schedule Solved Offline (2026-09-30)

Every input to the revival/Insight order is a world-independent game constant (breeding formula,
Insight curve, bonus trees), so the order is solved once on the dev machine by
`devtools/wildlife_optimizer.py` and shipped as `WILDLIFE_SCHEDULES`, instead of simulating the
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

## §1 — Lightning Rods Evaluated, Deferred (2026-10-01)

Question: are Lightning Rods a cheap power source? Answer: a real one, but not worth it while
steam/nuclear cover the grid. Mechanics below come from the decompiled simworker (`ZC` storm
generator, `uw` strike generator, `chargeRodsAt`, power tick), checked against 66 days of
Station3 `strikes()` history.

**Mechanics**
- Storm slots every 24 game hours; slot index `% 4 == 0` is dust, the rest thunder (75 %).
  Post-unlock extra dust storms are scheduled separately and bring no lightning.
- A storm crosses the 1,800 × 1,800 m map in a straight line at 200–260 m/h, radius 120–220 m,
  lifetime about 12–15 h (starts/ends off-map). Strikes: `round(6 + baseIntensity × 8)` = 8–14,
  uniform in time, within `0.8 × radius` of the storm centre, only on-map. Energy
  `1500 + U × intensity × 1500` Wh, intensity scaled by pressure/heat (Station3 mean ≈ 1,850 Wh).
- Weather Station logs strikes within `stationRadiusM = 300` while powered — no script needed;
  planet-wide log cap 300. Rod catches within `rodCatchRadiusM = 600`; only the nearest rod in range
  gets the strike. Bank cap 4,000 Wh, capture × integrity, integrity −0.05/day.
- A rod discharges only after the subnet's conventional batteries are empty and generation is
  short; it never charges from surplus. It feeds only its own subnet, so remote rods need lines.

**Yield estimate (4 rods at about (±450, ±450))**
- Strike supply far exceeds the 4 kWh bank: a rod in a storm's path fills in 2–3 strikes. Using
  strikes as they land would need a ~2 kW deficit, so most storm energy is wasted regardless.
- A storm path passes within 600 m of ~2 (sometimes 3) of the 4 rods. Typical
  2 × 4 kWh × 0.75 storms/day ≈ 6 kWh/day ≈ 250 W; best case ≈ 500 W. Integrity barely matters
  (surplus strikes still fill a worn rod), so repairs every 1–2 weeks suffice.

**Why deferred**
- Harvesting needs a "rod drain mode": batteries held at 0 between storms, turbines/oil throttled
  so the grid stays short and the rods empty before the next storm. With no partial load shedding,
  a rod running dry at 0 battery pauses the whole subnet (restart needs 1 h of deficit in storage).
- Gain is 2–4 Steam Turbines' worth, paid back only as saved steam/oil, not script count: 4 rods
  add repair scripts and controller complexity. This save goes nuclear instead.
- If revisited: replay past storms from the save seed (`storm_<n>` via `ZC`/`uw`) in a devtool to
  score rod layouts before building, then add drain mode to the turbine target and Oil Generator
  start rule (power guard already counts rod reserve via `measure_grid()`).

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

## §11f — One Refinery Role, No Per-Fluid Sub-Roles (2026-10-03)

- The `refinery_<fluid>` sub-roles (one raw fluid in, one refined fluid out) were dropped. Only `refinery` is
  left, and it always pipes all four raw exotics in and all four refined exotics out.
- Reason: the Refiner controller (`lib/refiner.py`) picks its recipe from the network-wide tank fill. It
  takes the emptiest refined fluid whose raw fluid has stock anywhere. A Refiner with only one fluid pair
  piped in would switch to a recipe whose raw input it cannot reach, or whose output has no pipe.
- Port budget: the refinery needs 4 gas fluids and 4 liquid fluids. A 4×4 footprint has 12 perimeter
  tiles per layer, so it also fits next to `factory` or `wildlife`.
- No migration: no save used the sub-roles yet.

## §0 — Mixin Self-Typing: `_host` Over Fake Base or Protocol (2026-09-22)

Mixins (vehicle, drone, pioneer, harvester, ...) need `self` typed as the composed controller for Pyright.

- **Fake base, rejected**: `_Base = VehicleController if TYPE_CHECKING else object`, then `class VehicleSurveyMixin(_Base)`. Checking one mixin file alone showed only a harmless "dead code" hint, so it was rolled out to all 11 mixins. A full-repo `npx pyright` then reported "Class cannot derive from itself" on every base of `class VehicleController(...)` in `lib/vehicle.py` (same for `lib/drone.py`): each mixin's type-only base is the composed class itself, a real cycle that only shows at the composition site. Fully reverted.
- **Protocol, not built**: a `VehicleControllerLike(Protocol)` with the whole cross-mixin surface, used as a per-method `self:` annotation. It worked in a scratchpad test, but needed the full attribute surface of all mixins and an annotation on every method.
- **Chosen**: one `_host` property per mixin returning `self` typed as the controller (one `# type: ignore[return-value]`), with methods going through `self._host`. A full Pyright pass at `lib/vehicle.py` showed 0 errors, 0 warnings.
- **Lesson**: a single-file diagnostics check is not evidence that a typing pattern is safe for a multi-file composition. Verify at the composition site before rolling a pattern out.

## §0 — Cold-Boot Heater: Per-State Cache and Duty-Cycle Throttle (2026-10-05)

The tier-0 `heater.py` used to re-scan powers 1–10 at every day change and cut to 1 W when
the battery fell below 25 %. Two findings from the simworker changed both parts:

- `thermal_state()` comes from a seed on the day number and holds for the whole day. Each of
  the four states has one fixed optimal power. So the script learns each state's optimum once
  (four scans per machine lifetime) and switches instantly on later days. Tier 0 has no archive
  or Signal Bus, so every machine learns on its own.
- Heat output depends on efficiency only, not on watts, and grid draw equals the set power.
  Efficiency is `0.1 + 0.9·exp(-(1.2·Δ)²)` for Δ steps from the optimum, so a lower setpoint
  loses far more heat than it saves power: 1 W gives the 10 % floor in most states. Running at
  the optimum for part of the time (duty cycle) keeps heat per watt at its maximum. The throttle
  therefore maps battery level linearly to a duty fraction and alternates optimum and 0 W.

The 93 % average heater efficiency in [autoplay/early_optimization.md](autoplay/early_optimization.md)
was measured in the headless runner, which wakes parked heater scripts only every
`HEATER_REFRESH_TICKS` (`devtools/headless/passive.mjs`). Part of that dip is the runner, not
the script.

## §0a — TreeConsole Wrapped Blocks: Decorator, Opt-In (2026-10-05)

Adapted from zroski's newer `RConsole.block` / `run` (`inspirations/discord-ideas/zroski.txt`), the same
author's console that TreeConsole grew from.

- **Why**: 249 `log.start()` calls need 612 `log.end()` calls, mostly an `end()` before every early `return`.
  A wrapper closes the block on every exit. An exception escaping a manual block also left the header with no
  END line until `reset_all()`; the wrapper writes `END <name> !! <Type>: <message>` instead, so the log
  shows the path the error took.
- **Opt-in, no mass migration**: most info blocks end with an outcome message (`end("3 orders placed")`)
  that a wrapper cannot know. The wrapper fits debug decision-trail blocks around a whole function.
- **`method_block` reads `self.log` at call time**: a class-level decorator cannot see the instance's
  `log`, so `@self.log.block` (RConsole's shape) is impossible for methods.
- **Not taken**: per-indent colors (one `log.color()` call in the codebase) and `pretty_format` dumps
  (CODE_GUIDES prefers aggregates; dumps fight the buffer cap).
- **Unverified in game at the time of writing**: no `lib/` used a custom decorator, `functools.wraps` or
  `__name__` live before. `drone_depot.flush_surplus` was the pilot: it ran every tick on all 7 Drone Depots of the main save without errors, so the
  same day it was rolled out to the 21 methods whose debug block had 5+ bare `end()` exits (208 lines removed).

## §2 — Early Harvester: Credits per Tick, Monotone Routes, Planning in Callbacks (2026-10-06)

Replaced vakermit's value-density script (`value / d^1.35`, nearest item within 2 first, collect whatever it stands on, clearing mode at 25/25) after an offline policy search (`devtools/headless/harvest_policies.mjs`, results in [plans/scoring_map_seeds.md](plans/scoring_map_seeds.md)).

- **Objective**: run time from a new game to the 25/25 build-out credits (10,250 cr), when the Harvester is still the only income. Credits by 0.5 h only break ties.
- **Skip cheap items**: early on time limits the Harvester, not heat. A collect costs 63 ticks, driving over an item cell +1 heat, so items worth less than half a collect at the best rate stay on the field. They serve as stepping stones and are collected later.
- **Heat price instead of rests in the plan**: heat matters later (routes otherwise end in 1.8 h rests per empty hop). A price per heat unit that rises with heat beats both a fixed price and none.
- **Monotone routes, not Dijkstra**: almost the same result (12.7 vs 12.6 min) at about a quarter of the interpreter steps. In game, steps are the real cost: each tick of planning per hop costs ~0.06 min.
- **Planning in `map()` callbacks**: the `0_cold_boot` tier has no `lib/atomic.py`, so the script inlines the same trick. Chunks are sized from headless step probes on a full field (largest ~4,200 of the 10,000-step cap). Exceeding the cap would end the script, and it can't be caught.
- **No clearing mode**: once rich items are gone, the rate gate drops and the cheap ones get collected anyway, so nothing starves.

## §9 — Lib Tier at the Data Archive (70k TP), Not the Control Room (2026-10-07)

The `4_controlpanel` tier used to wait for Custom Panels (150k TP). Everything the full `lib/` stack needs is unlocked by 70k: Shared Library (20k), Signal Bus (35k), Automations (50k), Data Archive (70k). Only the cards need the Control Room.

- **One version per machine**: the Charging Station, Rovers, scout Pioneer and Supply Dock all deploy after 70k under the `STAGES` build order (vehicles need pressure, which comes last; the Pioneer and Supply Dock need 100k/110k TP). With the switch at 70k they start on the tier-4 scripts, so their tier-0 stand-ins (rover, pioneer, charging station, supply dock) were deleted instead of kept in step with the libs.
- **Buyer in `control_room_automation.py`, not a second Automation**: the Automation already exists from the lib tier on, and grid supervision (PowerGridManager) is wanted from the start. An extra Automation would cost a running script for good. The buyer goes idle for good once the Control Room is researched.
- **Pioneer through the commission queue**: a tier-4 Pioneer only fits itself as a commissioned one (`LoadoutFittingMixin`), so the buyer queues a `scout` job instead of buying a bare chassis. It queues only a buildable spec: a blocked job can only be cancelled on the COMMISSION card, which comes at 150k.
- **Rovers fit themselves**: same mixin, fixed `ROVER_LOADOUT`; a kind counts as mounted at any tier.
- **Headless keeps up**: `run.mjs --lib-tier` makes the same switch in a fresh game (`library.create`, `automation.create`), so the build-order search still reaches 150k with a scouting Pioneer on the real scripts.

## §2b-2 — Mining Pioneer Holder/Rack Split (2026-10-07)

Mining Pioneers carried far more cargo than their batteries could fill: 2 × 50 Wh against 400 units, so an Industrial drill came home with ~14 units from a 120 m site and spent most of each trip driving. The tier ladder (§2b-1) only grows each container; nothing chose how many slots each kind gets.

- **Only the split moves**: function modules stay, each kind keeps the best tier. Swaps are near free (Shop buys back at full price).
- **Objective = drive Wh per delivered unit**, not units per trip: averaging units per trip lets a cheap near site outvote a far one, while drive overhead per unit weighs the far site by what it really costs. Drill power per unit doesn't depend on the split, so it drops out of the comparison.
- **Sites from the journal and the resource markers each cycle**, not a configured distance, so a new site or a moved marker re-splits on the next idle stop.
- **Hysteresis (`SPLIT_MIN_GAIN`)**: sites come and go as stock targets fill; without a margin a Pioneer would sell and rebuy slots every few trips.

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

## §1c-5 — Remote Relay Tank Ranking Removed (2026-10-08, game build e1986ce)

Until build e1986ce, all providers on a pipe component formed one pool, and a remote tank that held stock and fed consumers on that component received nothing. `FluidOutputRouter` therefore ranked such a relay tank last (`feeds_remote_route()`, PR #24), and producers needed a tank in their own outpost.

- **Removed**: build e1986ce moves pipe fluid along the declared pairs, and a tank that holds fluid is a sink too. The headless storage test (fluids.md "Storage outpost") fills storage to 900 t on one shared network; the same harness on the previous build reproduces the old failure (storage ~22 t, producer stalled at 878 t).
- **Kept**: own-outpost targets still rank first. A local link uses no pipe capacity.

## §2k — Drone Depot Swap Replaced by In-Place Upgrade (2026-10-08, game build e1986ce)

Before build e1986ce, a bigger Depot meant a swap: deploy the new kit, hide the old Depot from drones (`retiring_depots`), wait for its script to drain everything, undeploy it, rename the new one and move the home pins.

- **Now**: one `computer.upgrade(kit, depot)` call. In the simworker the in-place kit only changes the machine's typeId and default data (`bays`, stack slots). The machine object, its stockpile, script slot and docked drones stay, and bays only grow, so no drone needs to leave. The old kit returns to Inventory.
- **Removed**: `retiring_depot_ids()`, `DroneDepotController.drain_everything()` and the drain/undeploy/rename states. A save with a swap in flight drops the entry; a Depot it already deployed stays as an extra Depot.
- **Kept**: the script slot keeps its small-Depot name (`drone_station_N`). All three Depot templates run the same `DroneDepotController`, and it reads `bay_count()` live.

## §10b-1 — Fluid Network Rebuild Trap and `--sticky-fluids` (2026-10-05 to 2026-10-08)

**Up to build 3b1b03e** the fluid network analysis (`Ex()`, cached in `ux` under one signature string `gx()`) had a single key that held both the pipe geometry and every machine's fluid types and content flags. A tank running dry every tick therefore rebuilt everything, topology included, twice per tick. Measured on the owner's late save (887k TP, 274 machines), where `bulk_liquid_reservoir_9` (oil, outpost_4, 48 t/h in, ~48 t/h out, ~0.2 of 1,000 stored) ran dry every tick:
- 121 of 132 analysis calls missed the cache over 60 ticks (buffered: 13 of 131).
- FlowTransport 142 ms per tick against 13 ms buffered: 43 % of all simulation CPU, twice the cost of all 146 running scripts.
- Filled to 500 or 900 t by hand, the reservoir was empty again within minutes. A per-machine signature diff over 10 game minutes put 9,263 of 9,378 changes on that reservoir (drain: 6 Fabricators on `craft_tar` plus 5 Oil Generators against 5 Oil Pumps) and ~300 on item port rewiring.

Workarounds from that time: `run.mjs --sticky-fluids` patched the signature so headless runs stayed usable (every late-save run used it), the fluid-only recipe hysteresis in `lib/fabricator.py`, and the "keep tanks buffered" advice. The developer announced a fix on 2026-10-05.

**Build e1986ce** splits the key (fluids.md "Rebuild cost"): the topology is cached under `geometry`, without content flags. A forced flip now costs about 1 ms per tick (the 887k save state was no longer available, so the flip was forced on the mid-late sample save), and a natural late-save run differs by about 1 ms per tick with and without the flag. So runs no longer pass `--sticky-fluids`.

- **Kept, not removed**: the patch is small, feature-detected (it switches off with a warning when the pattern no longer matches), and still useful to reproduce older A/B numbers that were taken with it (event_driven_automation.md, headless_sim.md "Passive machines"), or on a future build that regresses.
- **Cost of keeping**: one signature pattern in `simhost.mjs` to maintain per game update. Remove it when that pattern breaks and nothing needs the old numbers.
- **Fluid-only recipe hysteresis kept, new reason**: the CPU reason is gone, but the pause still keeps a reserve for the consumers that never pause (Oil Generators on last resort, recipes with fluid plus items). Without it they share an empty tank with `craft_tar`. Throughput is unchanged, set by the supply.
