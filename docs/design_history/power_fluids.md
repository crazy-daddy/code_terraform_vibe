# Design History: Power & Fluids

Why behind power grid, steam/fluid routing, heat, lightning rods (cheatsheet §1a-§1c). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

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

The 93 % average heater efficiency in [autoplay/early_optimization.md](../autoplay/early_optimization.md)
was measured in the headless runner, which wakes parked heater scripts only every
`HEATER_REFRESH_TICKS` (`devtools/simulation/headless/passive.mjs`). Part of that dip is the runner, not
the script.

## §1c-5 — Remote Relay Tank Ranking Removed (2026-10-08, game build e1986ce)

Until build e1986ce, all providers on a pipe component formed one pool, and a remote tank that held stock and fed consumers on that component received nothing. `FluidOutputRouter` therefore ranked such a relay tank last (`feeds_remote_route()`, PR #24), and producers needed a tank in their own outpost.

- **Removed**: build e1986ce moves pipe fluid along the declared pairs, and a tank that holds fluid is a sink too. The headless storage test (fluids.md "Storage outpost") fills storage to 900 t on one shared network; the same harness on the previous build reproduces the old failure (storage ~22 t, producer stalled at 878 t).
- **Kept**: own-outpost targets still rank first. A local link uses no pipe capacity.

## §1b-1 — Input Sources: POI Extractors and Stock Ranking (2026-10-09, game build e1986ce)

- **POI extractors were never candidates**: every source walk went through `outpost.buildings()`, which omits Pumps, Caps and Taps (not building-capacity machines). So the documented "then Oil Pumps / Thermal Caps" tiers were empty, and `can_source_fluid()` reported a water recipe unsourceable with a Water Pump piped in and no tank. The offline fake listed them as outpost buildings, which hid it. Discovery now adds them from power grid members, and the fake follows the spec's `building` flag.
- **Stock ranking**: since §1c-5 there is no pool, and a consumer draws only from its declared source. A tank kept near empty (inflow ≈ draw) caps the consumer at the inflow while other tanks are full, and the old ranking (own outpost first, discovery order) never looked at levels, nor left a healthy link. `rank_sources()` ranks by stock, and `FluidInputRouter` moves a healthy link off a low tank or a producer. Two lines (low 5 %, switch 20 %) and one source direction (towards stock only) keep it from flapping.

## §1c-6 — One Tick Cache for Discovery and Refresh Memos (2026-10-09)

Ten module memos and six controller fields each held a value for N ticks with their own rule. They disagreed on tick 0 (no clock): some cached forever, some always recomputed. They also disagreed on a clock that went backwards: some recomputed, some kept the value until real time caught up. Some cached empty reads, and only one kept the last good read when a read failed. `game_clock.TickCache` is now the one rule: recompute at tick 0 and on a backwards clock, `None` = unreadable keeps the last value, `keep_empty=False` for lists that are empty only when the read failed.

- **Simulation ticks, not calls**: fluid routers reach discovery only on the slow path. A call counter advanced once per rebalance or stall event, so a new tank could stay invisible for 20 such events. Seen as turbine_10/11 cycling unreachable cross-outpost tanks while their own outpost's freshly assigned gas_tank_12/13 were never tried.
- **Tick 0 recomputes**: a stale list is the failure a cache must never cause; a missing clock costs only scans.
- **TTL constants stay per module**: tests set `cache.ttl_ticks` on the instance, since the constant is read once at import.

## §1b-2 — Direct Producer Links and Reachable Reserves (2026-10-09, game build e1986ce)

- **Habitat and Refiner inputs listed tanks only**: the producer tiers of §1b-1 covered water, oil, steam and essence, but a Habitat or Refiner could never link to an Exotic Cap/Tap or a Refiner, so a chain without tanks never connected and its routers answered `not_found` at debug. Exotic and Refiner outputs vary per building, so producers are filtered by `producer_fluid()` before ranking. A Refiner also counts raw fluid a Cap/Tap delivers now as available, or its recipe pick would wait for a raw tank that never comes.
- **Fluid-only pause read the whole network**: under declared pairs a Fabricator drains only tanks its port reaches. A full tank on another pipe network kept the network-wide fill high while the tank shared with the Oil Generators sat at 0 %. Reading only the current source would be wrong too, because the router can switch to any other tank it reaches, so the pause reads the router's candidate tanks minus blacklisted ones (tried and unreachable). Autoplay plans one network per fluid, where both readings agree; this keeps other layouts working at no extra walk.
- **No source at all warns once**: "no tank" alone is normal when a producer feeds the port directly, but no tank and no producer means the machine can never run. One warn per episode (cleared by any other router event) keeps it visible without repeating every poll.

## §1a-0 — Lightning Rods and the Power Source Order (2026-10-11)

- **Pooled rods locked latches on**: the battery pool added `reserve_stored`/`reserve_capacity`. Rods fill only from strikes, never from surplus, and the game spends them only after the bank is empty, so they sit mostly drained. A full 10k Wh bank with 3 drained rods read 45%: turbine commitment's all-on latch (50% → 70%) never released, its top-up asked ~2,000 W per empty rod, and the oil last resort (stop at 70%) never stopped. Rods weren't used in play yet, so it never showed.
- **Two readings**: full/top-up rules read the bank alone; shortfall checks (night guard, shedding, parking wake) add the stored rod Wh to both level and capacity, so a planned rod discharge never sheds.
- **Operator's source order**: solar-only grids shed for the night; turbines keep the bank full and yield to every source and to trickle oil, never to the last-resort burn (full oil tanks matter more than full steam tanks); oil comes last; the reactor never scales. On a reactor grid neither oil nor steam surplus burns: the power would be wasted too, and more machines would run. While rods hold energy, everything but trickle yields so the game spends them, ending above the first shed line.
- **Surplus steam yields to surplus oil** (2026-10-12): with both surplus base loads on, each covered the whole load, so all turbines ran next to the oil burn and the extra power was lost with a full bank. Turbines now subtract surplus oil (not last-resort oil): two Oil Generators replace many turbines, so more machines park, and steam venting is the cheaper loss.

## §1b-3 — Healthy Input Links Skip the Network Scan (2026-10-14)

A CPU profile of the live game put `FluidPort.connections()` at ~2.3 % of the sim worker, ~7 % of all script time: the engine replays a signature over every machine to validate its cached pipe analysis on each call. `FluidInputRouter.ensure()` called it on every loop of every fluid consumer. A healthy, unstarved link now reuses its last read for `HEALTHY_RECHECK_INTERVAL_TICKS` ([power_fluids.md §1b](../cheatsheet/power_fluids.md)).

- **Starvation is the break signal**: a broken or conflicting link stops flow, so a starved port re-reads at once. Habitat passes `port_starved()` for this.
- **Other callers on the same interval**: Habitat's wrong-fluid check (clean read per source and fluid), the Biomass Mixer gate's `linked` read per input, and Mixer telemetry (the source of its last `ensure()`).
- **`connected_id()` as tripwire**: it reads the port, not the network, so a reconnect by another script or the operator is seen at once. A peer-declared link reads `None` both times and stays on the fast path.
