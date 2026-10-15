# Event-Driven Automation

Plan for moving `orchestrator_automation.py` from polling to events: whoever causes a change reports it, and the Automation handles it instead of searching for it every pass. The script cost model is in [dev_workflow.md §1d-1](../cheatsheet/dev_workflow.md); script parking is in §1d-2.

## Status (2026-10-15)

| Item | State |
|---|---|
| Phase 0, fix A | Done, deployed, measured |
| Fix B (full pass by pass count) | Dropped (2026-10-15): passes run ~415 ticks apart, so nearly every pass is already full |
| Phase 1.1, 1.2, 1.4, 1.5 | Done (bf20ec8), headless A/B passed, live remeasure done (2026-10-15); dock-order wake moved after the publish, backstops raised (2026-10-15, "Backstop A/B") |
| Phase 1.3 (Oil Generator wake from `supervise_grid()`) | Open: `_low_reserve_grids()` still runs on every pass |
| Phase 1.6 (vehicle work wakes at the writer) | New, open; vehicle pausing itself is done (5057aaf) |
| Phase 2 (timer index) | Not started |
| Phase 3 | Exotic cap done (deposit-active wake); Oil Pump and solar still polls |
| Phase 4 (decommission message) | Superseded by the builder split (489df5f) |
| Phase 5 | Still blocked |

Code moved since the plan was written: fleet commission, decommission and upgrades run in `builder_automation.py` (489df5f), not in the orchestrator's storage pass. `orchestrator_automation.py` keeps parking, grid supervision, dock and Wildlife planning, the early buyer and the storage sweeps.

## Why

In the main save, one storage pass of the Automation took 5–9 game hours (2026-10-05 logs). The pass includes fleet decommission, site planning and supply requests. Two fixed chores used up the Automation's step allowance (about 364 steps per tick at about 140 running scripts):

- **Script parking** ran every 50 ticks and cost about 43 ticks.
- **Census plus machine activity** cost about 93 ticks every 300 ticks.

The storage pass only ran in the gaps. A drone marked ready for decommission at 16:45 game time was undeployed at 23:36.

Most of the parking pass is polling. It re-reads every grid member, re-computes the demand snapshot and re-checks every parked entry to find the few wakes that are due. Each poll costs the same whether anything changed or not.

## Principles

- **Report at the cause, not at the sleeper.** A parked machine cannot detect that it should wake up. The script that changes its situation can: the writer of a demand key, the dock planner, a Fabricator missing input, a vehicle heading to a station. This pattern already exists: `script_parking.wake_kind()`, `wake_for_visit()`, `fabricator.wake_local_smelters()`.
- **Timers are not polls.** A wake that is due at a known tick needs one comparison against the earliest due tick, not a walk over every entry.
- **Poll only physics with no known timing.** Some state changes with no script involved and no announced time, for example a well turning active without `next_phase_in()`. Only these remain polls, on the slowest interval that is still safe.
- **The archive holds state, the Signal Bus carries work.** "What is parked" stays in `script.parked`. "Wake X now" or "drone_18 is ready" is a queued message (`comms.send()`, handled once by `receive()`).
- **A full pass stays as the backstop.** Every event path keeps a slow full pass that catches lost events (a producer crashed between its write and its signal, a script restart dropped state).
- **Extra scripts add speed, not budget.** At 50 or more running scripts the base shares 50,000 steps per tick. An extra worker takes its share from every other script, and a script blocked in `wait()` or `sleep()` still counts. Workers scale cheaply only if they end when idle and something restarts them.

## Phase 0: chore cost cut (deployed 2026-10-05 04:52 UTC, commit 1e419c6)

Behavior is unchanged except for the parking split. Estimated by replaying the live save's machines and parking archive through the stub harness (scratch profile on top of `devtools/perf/step_profile.py`). The replay matched the live logs at about 43 ticks per parking pass before the change.

| Change | Before | After |
|---|---|---|
| Parking: one indexed member pass (`_by_type`, `_dark`) instead of four walks over all members; unused `_summary()` removed | ~43 ticks per pass | ~28 ticks per full pass |
| Parking: fast pass every 50 ticks (wakes only, reuses the last full pass's member rows and oil surplus verdict); full pass every `PARKING_FULL_TICK_INTERVAL = 150` | 3 × 43 = ~129 ticks per 150 | 28 + 2 × 12 = ~52 ticks per 150 |
| Census: machine rows built and de-duplicated in atomic batches | ~93 ticks per 300 (with activity) | ~30 ticks per 300 |
| Machine activity: per-group tally and merge in atomic batches, `ACTIVITY_CHUNK` 50 → 100 | (included above) | (included above) |

The largest single atomic call is about 3.4k steps, under the 10,000-step cap.

**Verify after deploy:**

1. Run `python devtools/perf/log_block_timing.py --script automation --since <deploy time UTC>`. Expected: `script parking` median about 28 ticks (full) and about 12 ticks (fast).
2. Measure the storage pass period from the spacing of the `home salt request` debug lines in `automation_1.log`. It was 3,000–5,000 ticks.
3. Compare the decommission delay: `Empty and docked; ready for undeploy` (drone log) to `[decommission] Retiring` (automation log).

### Phase 0 live results (2026-10-05, about 11,000 ticks, 45 parking passes)

The replay estimates did not hold. The replay modeled member reads; the live cost is wake and park events.

| Metric | Estimate | Measured |
|---|---|---|
| Parking pass | full ~28, fast ~12 ticks | ~50–55 ticks: block median 36, plus ~15–20 ticks of pre-work before its first log line |
| Pass with at most 2 wakes or parks | – | ~4 ticks inside the block |
| Spacing between passes | 50 ticks | median 170, minimum 67 |
| Storage pass period (`home salt request`) | – | 3,982 / 3,043 / 3,004 ticks (was 3,000–5,000) |
| Parking share of Automation game time | – | ~22% |

Findings:

1. **The fast/full split has no effect.** Passes run about 170 ticks apart, more than `PARKING_FULL_TICK_INTERVAL = 150`, so almost every pass is full.
2. **Pass cost follows events, not member reads.** Each wake or park costs about 2 ticks (`set_powered`, an archive transaction, a log line). Median 16 events per pass.
3. **Re-check backoff almost never fired.** 332 of 346 wakes were `re-check due`. The backoff applied to only 20 of 283 re-check wakes of smelter, fabricator, crop_automator and supply_dock. `_backoff_wake_after()` measured wake-to-park, and the park came on the next pass, outside `FRUITLESS_REPARK_TICKS = 150`. The same machines woke about every 900 ticks and parked again. Each woken machine also counts as a running script until it parks.

### Fixes after the measurement

- **A (done in the working tree, not committed):** backoff measures wake-to-request using the tick in the machine's own park request, so pass spacing no longer matters. Test: `test_backoff_counts_the_request_tick_not_a_late_park_pass`.
- **B (open):** choose the full pass by pass count (for example every 3rd pass) instead of by ticks. Check first: a request older than `REQUEST_FRESH_TICKS = 150` is not parked. Two skipped passes at 170-tick spacing could let requests go stale unless `ParkRequester` re-files often enough.
- **C:** Phases 1–2 below replace timed re-checks with wakes at the cause, which removes most of the remaining churn.

### Fix A live results (2026-10-06, about 169,000 ticks, 607 parking passes)

Window: `automation_1*.log` from 2026-10-05 22:38 to 2026-10-06 03:30 UTC, all after fix A (2d8b676). The save was mostly idle (terraforming toward its caps), so few demand events. No decommission happened in the window.

| Metric | Phase 0 | Fix A |
|---|---|---|
| Parking block median (p90, max) | 36 ticks | 34 ticks (47, 67) |
| Gap before the block header (pre-work plus idle time since the previous line) | ~15–20 ticks | median 49 ticks |
| Pass with at most 2 events | ~4 ticks | ~9 ticks (37 passes) |
| Spacing between passes | median 170, min 67 | median 186, min 70 |
| Events per pass | median 16 | median 19 |
| Wakes / parks per 11,000 ticks | 346 wakes | 341 / 349 |
| `re-check due` share of wakes | 332 of 346 | 4,983 of 5,247 |
| Parking share of Automation game time | ~22% | ~29% (block plus gap) |
| Storage pass period (`home salt request`) | 3,004–3,982 ticks | 3,072–4,009, typically 3,100–3,800 (48 periods) |

Backoff hits per kind (`found no work` lines against `re-check due` wakes): smelter 443 of 1,021, fabricator 371 of 1,665, supply_dock 117 of 426, crop_automator 19 of 958. Backoff values: 600 ticks 435 times, 1,200 ticks 514 times, 1,800 ticks once. Re-check wake to next re-check wake per machine is still about 900 ticks (smelter 923, fabricator 888, supply_dock 910).

Findings:

1. **Fix A works, but `FRUITLESS_REPARK_TICKS = 150` is too short.** Backoff now fires (950 times, against 20 before), yet the wake rate did not drop. A woken script steps about every 45 ticks in this save (`fabricator_9.log`: steps at ticks +0, +45, +90, +135 after each wake, then about 600 ticks of silence). With `PARK_AFTER_IDLE_STEPS = 3`, the park request comes about 135–180 ticks after the wake, so most fruitless re-checks fall outside the window and reset the streak. The streak rarely passes 2, so the 1,800-tick caps are almost never reached.
2. **crop_automator rarely backs off** (2%). Its wake-to-park median is 698 ticks, against about 215 for the other kinds. It probably does real work after most wakes; check its log before changing its timer.
3. **Pass cost and storage period are unchanged.** Pass cost still follows events (median 19 per pass at about 2 ticks each), and the event count did not fall.

Decision: no further backoff tuning. Phase 1 removes the reason for most timed re-checks. Fabricator and smelter (about 2,700 of the 4,983 re-check wakes) get demand wakes (1.1), supply_dock gets order wakes (1.2). Their timed re-check then becomes a long backstop without backoff (Phase 1.5). A machine-side "fruitless" flag would be work Phase 1 makes obsolete. Stopgap only if Phase 1 is more than a few days out: `FRUITLESS_REPARK_TICKS = 300`.

## Hand-off

State on 2026-10-11:

- Phase 0 (1e419c6), fix A (2d8b676) and Phase 1 except 1.3 (bf20ec8) are committed. Vehicle pausing (5057aaf) is committed and adds paused Pioneers and drones to the parking pass.
- The main save has not been played since 2026-10-06 (Plants and Wildlife complete), so the remeasure needs the active run's save or a headless window on a producing save. Headless `run.mjs --save` now runs the repo's current scripts by default (dev_workflow.md §10b); an A/B baseline still needs `save_scripts.py` on the baseline commit.
- 2026-10-15: the Phase 1 live remeasure is done ("Phase 1 live results" below). Fix B is dropped. The headless backstop A/B found the dock-order wake racing the demand record; the wake now follows the publish, and the fabricator, smelter and Supply Dock backstops are 3000 ("Backstop A/B" below). Next: one live window to confirm, then Thermal Cap's new wake in the same window.

How to measure (live save, read-only; the logs are in `%APPDATA%\io.codeterraform.game\<save>_scripts\logs\`; headless runs write the same lines to `console.log`):

1. Block times: `python devtools/perf/log_block_timing.py --script automation --since <ISO UTC>`. A debug block's header carries the clock of its first inner line, so the parking row misses the pass's pre-work. Add the gap between the line before `┏━ script parking` and that header.
2. Events per pass: count `woke `, `parked `, `paused ` and `resumed ` lines between `┏━ script parking` and `┗━ END script parking` in `automation_1.log`. Group wakes and resumes by the reason in parentheses.
3. Pass spacing: the game-clock difference between consecutive `┏━ script parking` headers, divided by 14.4 s per tick.
4. Backoff hits: `grep -c "found no work" automation_1.log` and `grep -o "next one in [0-9]* ticks" | sort | uniq -c`. Compare with the count of `re-check due` wakes per kind.
5. Storage pass period: the tick difference between consecutive `home salt request` lines.
6. Decommission delay: `Empty and docked; ready for undeploy` (vehicle log) to `[decommission] Retiring`, now in the builder Automation's log.

Success for fix A: backoff lines for most re-check wakes of the four backoff kinds, fewer than about 260 wake/park pairs per 11,000 ticks, fewer events per pass, and a shorter storage pass period.

## Phase 1: wakes at the cause

Goal: the fast parking pass finds wake work without diffing snapshots.

1. **Demand wakes.** Today `_demand_wakes()` diffs `_demand_signature()` (six archive reads plus a loop) on every pass. Instead, each writer of a demand key calls `wake_kind("fabricator" | "smelter", reason)` when it raises a value. The writers are in `production_orders.py`, `production_sites.py`, `site_plan.py`, `production.py` and `supply_dock.py`; list them with a grep for the keys `_demand_signature()` reads.
   - Keep the signature diff on the full pass only, as the backstop.
   - Open question: a writer that raises demand on every pass (rounding, a target that oscillates) would wake machines each time. Compare against the written value and wake only on a real rise, as `_demand_signature()` does today.
2. **Dock order assigned.** `supply_dock.plan_dock_assignments()` wakes a parked dock when it assigns that dock an order (a `wake_for_visit(dock, hold=False)`-style call). The `order assigned` check in `_wake_reason()` then moves to the full pass.
3. **Oil Generator low reserve.** `PowerGridManager.supervise_grid()` already measures every grid every `SOLAR_TICK_INTERVAL = 10` ticks. When a grid's reserve falls below `OIL_WAKE_RESERVE_FRACTION`, it wakes that grid's parked Oil Generators. `_low_reserve_grids()` and its `RESERVE_CACHE_TICKS` cache then leave the fast pass.
4. **Decide per producer: direct wake or queued message.** A direct `wake_kind()` from the producer is the simplest path. It works from any script, because `power_control` is exempt from the remote-write block. Use a Signal Bus queue (channel e.g. `parking.wake`, payload `{"id" or "kind", "reason"}`) only where the producer must not carry parking logic, or where several wakes should merge into one handled batch.

5. **Long backstop timers.** Once a kind has its event wake (1.1 for fabricator and smelter, 1.2 for supply_dock), raise its `WAKE_AFTER_TICKS` to a backstop value (for example 3000, as for other kinds with event wakes) and remove it from `WAKE_BACKOFF_MAX_TICKS`. If no kind is left in it, remove the backoff (`_note_wake()`, `_backoff_wake_after()`, `FRUITLESS_REPARK_TICKS`). crop_automator has no event wake; check in its log whether its wakes find work before changing its timer.

Tests: one stub test per producer (the change wakes exactly the parked machines of that kind, no wake without a rise).

Expected: re-check wakes of the three kinds drop from about 2,350 to under 200 per 169,000 ticks, so events per pass and pass cost fall with them.

6. **Verify in headless** (A/B, before deploying): `devtools/simulation/headless/save_scripts.py` maps the repo's scripts onto a save's slots (dev_workflow.md §10b). Resolve one directory from `main` (baseline) and one from the change, then run both on the same save with `run.mjs --save <save> --scripts <dir> --libs <dir>/lib --hours 0.6 --paid-debug --sticky-fluids --out <dir>`. `--paid-debug` is required: a debug line costs about a tick in game, about half of a wake or park event. Saves: the mid-late sample (`internals/sample_saves/`, 2026-10-05, 16 habitats) and a copy of the current main save. Compare from `console.log` (`[tick N] [level] [script] text`): parking passes, block ticks, events per pass, wakes by kind and reason, writer wakes (`[PARKING] Woke N <kind>(s) (...)`), and Fabricator/Smelter output (`Sent Nx <item> to storage`) so the longer backstop timers cost no production.

### Phase 1 status (2026-10-06, working tree)

Done: 1.1 (`wake_on_rise()` at `production_orders._set_requester_order()`, `production_demand.ingot_stock_levels()` seeding, `site_plan.plan_sites()`, and dock-plan order ids in `supply_dock._wake_for_plan()`), 1.2 (the planner wakes a parked dock it assigns an order), 1.4 (direct `wake_kind()`, no Signal Bus queue), 1.5 (fabricator and smelter 1200 ticks, supply_dock 1800, their former backoff caps; only crop_automator keeps the backoff). The signature diff and the `order assigned` check run on full passes only. `wake_kind()` now clears the woken machines' pre-park requests, as the parking pass does. Manual orders and Fabricator stock targets have no script writer (Notebook edits), so they stay on the full-pass backstop.

Headless A/B (21,600 ticks each, `--paid-debug --sticky-fluids`, 0 crashes in all four runs; baseline = `main` scripts and libs):

| Metric | Late (main save 2026-10-06, idle) base → Phase 1 | Mid-late (sample 2026-10-05, producing) base → Phase 1 |
|---|---|---|
| Parking passes | 71 → 68 | 46 → 42 |
| Block median (p90) | 34 (51) → 23 (49) ticks | 23 (36) → 23 (34) ticks |
| Parking share of the run | 11.0% → 8.3% | 4.7% → 4.5% |
| Events per pass, median | 16 → 10 | 8 → 7 |
| Wakes inside passes | 604 → 448 | 183 → 147 |
| Fabricator / Smelter / Supply Dock wakes inside passes | 205 / 109 / 20 → 113 / 72 / 7 | 55 / 2 / 12 → 15 / 0 / 6 |
| Writer wakes (`wake_on_rise()`) | 0 → 0 | 0 → 32 machines in 15 calls |
| Fabricator / Smelter output (`Sent`/`Drained` units) | 0 / 0 both | 1,750 / 3,752 → 1,935 / 3,806 |
| TP at the end | equal | 828,308 → 828,253 |

Findings:

1. The idle late save gains most: a third fewer events per pass and the block median falls by a third. The remaining fabricator and smelter wakes are the 1,200-tick backstop (about 10 fabricators × 21,600 / ~1,400).
2. In the producing save the writer wakes replace timed re-checks one for one or better: 55 fabricator re-checks became 15 re-checks plus 30 demand wakes, all from real rises (Plant Terraformer backlog orders, site plan, field amplifier, one ingot target). Output did not drop (Fabricators +11%, Smelters +1%).
3. Next lever: raise the fabricator and smelter backstop toward 3000 once a live measurement confirms that the writer wakes cover the work. Going from 1200 to 3000 removes about 60% of the idle re-checks.

### Phase 1 live results (2026-10-15)

Window: `automation_1*.log` of save `save_muzfgrhc_6h7rbh` (sample `internals/sample_saves/20261008_7e5e168`), 2026-10-14 14:19 to 19:13 UTC, ticks 2,056,810–2,294,835 (238k ticks, 392 parking passes). Scripts at the then-current `main`: Phase 1 and vehicle pausing deployed. The save was producing (dock orders, wildlife, biomass), with a median of 142 running scripts. Pass spacing is from the header game clock: the debug lines' `tick=` is the flush tick.

| Metric | Fix A live (2026-10-06, idle) | Phase 1 live |
|---|---|---|
| Wakes / parks per 11,000 ticks | 341 / 349 | 123 / 152 |
| Vehicle pauses / resumes per 11,000 ticks | – | 20 / 20 |
| Events per pass, median | 19 | 16 (mean 17.3, max 62) |
| Spacing between passes, median | 186 ticks | 415 ticks (p10 167, p90 1,054) |
| Parking block median | 34 ticks | 48 ticks (8.9% of the window) |
| Writer wakes (`demand changed`) | 0 | 23 calls, 152 machines (82 fabricator, 70 smelter), all dock orders |

Passes each machine stayed awake after a `re-check due` wake (1 = parked again on the next pass, so the re-check found no work):

| Kind | Re-check wakes | Parked on the next pass |
|---|---|---|
| smelter (10) | 751 | 626 (83%) |
| fabricator (8) | 456 | 395 (87%) |
| supply_dock | 88 | 82 (93%) |
| thermal_cap | 91 | 76 (84%) |
| oil_generator | 152 | 136 (89%) |
| crop_automator (8) | 543 | 244 (45%; backoff fired 34 times) |

Findings:

1. Wakes fell to about a third of the fix A count and parks to under half. The block median rose from 34 to 48 ticks with about 142 running scripts, but the pass now runs about half as often.
2. Pass spacing more than doubled (median 415 ticks), as predicted for the demand publisher in `between_steps()` (Phase 2 notes). `PARKING_FULL_TICK_INTERVAL = 150` is below even the p10 spacing, so nearly every pass is a full pass. Fix B (full pass by pass count) would only space the parks further apart: dropped. Park requests stay fresh across the wider spacing because `ParkRequester.update()` re-files on every idle step.
3. A fruitless re-check now keeps the script running for one pass spacing (~415 ticks), about twice as long as under fix A. 83–87% of fabricator and smelter re-checks are fruitless, and dock-order writer wakes do fire, so the backstop raise to 3000 is supported. The logs can't show whether the remaining 13–17% of re-checks found work a writer wake would have missed: the headless A/B on output decides that.
4. Supply Dock (1800) and Thermal Cap (600) re-checks are as fruitless. Supply Docks get order wakes (1.2), so their backstop can rise with the others. Thermal Cap has no event wake: it needs one (Phase 3) or an entry in `WAKE_BACKOFF_MAX_TICKS`.

### Backstop A/B (2026-10-15)

Headless, save `1631_t2294802` (the same run's last sample), `--hours 1 --paid-debug --sticky-fluids`, every group real (stand-ins skewed the factory: [headless_phase14_handoff.md](headless_phase14_handoff.md) "Field report").

First pair, the code as it was: at 3000 the Fabricators made only 18 units against 27, all before tick 2,295,580. Cause: `supply_dock._wake_for_plan()` woke them on the dock plan diff, but they read the demand record, which carries a new order only after the next refresh (`DemandPublisher`, 300–1,100 ticks later). Woken early, they logged `site targets(outpost_1) from the stale demand record` and `choose_recipe: no candidates at all`, then parked; at 1200 the next re-check usually caught the refresh, at 3000 it did not. Fix: `DemandPublisher._publish()` wakes each kind whose part of `demand_signature()` rose (`wake_risen()`), and `_wake_for_plan()` wakes only the docks. Site plan, `fabricator.orders` and ingot target writers keep their own wakes (a changed site plan makes the record `MISSING`, so a woken Fabricator computes its own targets).

Second pair, with the fix (the Supply Dock backstop at 3000 and Thermal Cap's lead wake in both arms):

| | old code, 1200 | fix, 1200 | fix, 3000 |
|---|---|---|---|
| Fabricator / Smelter `Sent` units | 73 / 105 | 30 / 98 | 43 / 90 |
| Fabricator / Smelter `re-check due` wakes | 99 / 125 | 116 / 155 | 60 / 85 |
| of those parked on the next pass | 98 / 124 | 108 / 144 | 48 / 74 |
| Breaker wakes, whole run | 477 | 529 | 399 |
| Dock order assigned → crafters woken | 8–10 ticks (before the record) | 367–447 ticks | 362–544 ticks |
| TP at the end | 789,559 | 789,589 | 789,572 |
| errored / crashed | 0 / none | 0 / none | 0 / none |

The output column follows when the weekly orders land, not the backstop: `weekly_55_4` was assigned at tick 2,326,778, 2,329,591 and 2,328,623 in the three runs, and its `machine_frame` units follow it in each run with time left. Every run waits about 4,500 ticks between `weekly_55_3`'s assignment and its first craft (inputs, not parking). One hour holds about four order changes, so output differences under ~30% are noise here. The 3000 arm halves the fruitless re-checks and loses nothing measurable: `WAKE_AFTER_TICKS` smelter and fabricator are 3000.

Open: 1.3 (Oil Generator wake from `supervise_grid()`). In the 169k-tick main-save window no Oil Generator woke on a low reserve, so it waits for a measurement that shows the fast-pass reserve check costs anything. Still open on 2026-10-11: `ScriptParking.step()` calls `_low_reserve_grids()` on fast and full passes. The 2026-10-15 window had 8 `grid reserve low` wakes in 238k ticks; it still shows no cost for the check.

### 1.6 Vehicle pausing and its wakes (added 2026-10-11)

Done (5057aaf, game build v0.1.31; design reasons in DESIGN_HISTORY §1d-2v): idle Pioneers and drones (`PAUSE_KINDS`) file park requests like machines, and the parking pass pauses them with `run_control.pause()` (mode `"paused"` in `script.parked`). `_wake_paused()` resumes them when:

- the 3000-tick re-check is due (`WAKE_AFTER_TICKS["pioneer"]`, `["drone"]`, below the 6000-tick heartbeat windows other scripts read);
- a command for the vehicle is waiting (`_vehicle_commands()`: recall, drone recall, decommission, fleet upgrade, Sport Nav). Checked on every pass while a vehicle is paused, five archive reads;
- its role got new work (`_work_wakes()`, full passes only): a new (outpost, item) key in the open haul requests for haulers, a new pending or paused construction job id for Constructors.

The command check is a deliberate panel-side poll: those keys have several writers, including hand edits (DESIGN_HISTORY §1d-2v). `_work_wakes()` is the snapshot diff that Phase 1 replaced for machines. Open:

1. **Work wakes at the writer.** `logistics_requests` (a new request key) and the construction planner (a new job) call a `wake_kind`-style resume for the paused vehicles of that role. The key diff stays on the full pass as the backstop. Do this only if the remeasure shows work wakes arriving late (up to one full-pass spacing) or the diff costing ticks.
2. **Command wakes.** Keep the panel check unless the measurement shows its five reads on every pass matter. Then gate it behind Phase 2's `next_due` with a cheap marker the command writers bump.

Tests exist in `tests/test_script_parking.py` and `tests/test_job_loop.py`.

## Phase 2: timer index for the fast pass

1. Keep `next_due`, the earliest `since + wake_after` over the parked breaker and paused vehicle entries, in the `ScriptParking` instance. Recompute it on every full pass and after every park, pause, wake or resume.
2. Fast pass: if `now < next_due` and no wake message is queued (`comms.queue_size()`), return before reading the archive. Expected cost: a few dozen steps, down from about 12 ticks.
3. Entries other scripts write (`turbine_commit`, `wake_for_visit()` holds) don't move `next_due` earlier. If one ever needs an early wake, it sends a message.
4. Today the fast pass also does work that is not timer-driven. Each needs its own trigger before the early return is safe:
   - `_low_reserve_grids()`: move to `supervise_grid()` first (1.3).
   - `_wake_paused()`'s vehicle command check (1.6): a queued message from the command writers, or keep it outside the early return.
   - The sunrise solar start (3eafee4 moved it onto fast passes): a timer from the day length (Phase 3.2), or keep it outside the early return.

## Phase 3: remaining physics polls

1. **Oil Pump `well_active()`.** Where `next_phase_in()` is known, the machine files `wake_after` as `exotic_cap` already does, so the wake becomes a timer. Otherwise poll on the full pass only, if the data allows. Check how fast wells really turn active in the logs before slowing this down. Exotic Gas Cap and Spring Tap are done: woken when the deposit turns active, `WAKE_AFTER_TICKS["exotic_cap"] = 6000` as the backstop. Oil Pump is still a 3000-tick re-check.
2. **Solar day/night.** It is driven by the clock elevation, so it can become a timer from the day length. Low priority: it is cheap after Phase 0. Since 3eafee4 the sunrise start runs on fast passes too (on full passes only, panels started up to ~36 game minutes late); the night stop stays full-pass only; see Phase 2, item 4.
3. **Strays and orphan adoption.** These stay on the full pass. They are backstops by design.

## Phase 4: fleet decommission as the first queued event

**Superseded (2026-10-11).** The builder split (489df5f) moved fleet decommission out of the orchestrator's storage pass into `builder_automation.py`, which runs `FleetDecommissionCoordinator.step()` every `FLEET_TICK_INTERVAL` ticks. The delay that motivated this phase (hours, waiting for a storage pass) drops to one builder pass: at most about `FLEET_TICK_INTERVAL` plus one Warehouse drain slice (`warehouse_upgrade.DRAIN_PASS_TICKS`). Measure it (Hand-off, step 6) before reviving the pilot. The message pattern below stays the template for the first queued event elsewhere (Phase 5 candidates).

Original plan, kept for reference (the `_prepare_decommission()` methods now live in `drone_claims.py` and `vehicle_recall.py`):

1. `drone_claims._prepare_decommission()` and `vehicle_recall._prepare_decommission()` send `fleet.decommission_ready` with `{"id", "kind"}` after `mark_decommission_ready()`.
2. `between_steps()` in `orchestrator_automation.py` checks `comms.queue_size("fleet.decommission_ready")`. When it is non-zero, it `receive()`s and runs `FleetDecommissionCoordinator` for that machine.
3. The storage pass keeps its full `fleet_decommissioner.step()` as the backstop for lost messages.
4. Expected: undeploy within one `between_steps()` gap (minutes) instead of one storage pass (hours).

Open question: whether `between_steps()` should drain a generic `automation.events` channel with `wait_any`-style priority instead of one `queue_size()` check per feature. Decide after the pilot shows the cost of a check (BENCHMARK: about 5 steps per call).

## Phase 5: scanners and workers (depends on game features)

Long-term direction: scanner automations detect work and queue it on the Signal Bus; worker automations take it and handle it. Workers could scale with queue length.

- **Blocked on the developer:** deploying automations by script (`deploy()`) and starting or stopping them by script (`run_control` for automations). Without these, every worker counts as a running script all the time, even while it waits on an empty queue. Re-checked against the v0.1.31 docs (2026-10-11): `run_control` gained `pause()`/`resume()`, but it still documents machine scripts only, and the docs show no `deploy()` for automations. A paused script leaves the running count, so `pause()` on automations would be enough for idle workers. Ask the developer whether it applies to automations.
- **Once available:** a worker ends when its queue is empty; the scanner starts one (`run_control.start()`) when work is queued and none is running, and more when the queue grows. The worker count then follows the load.
- **Until then:** keep event handling inside the existing Automations (Phases 1–3). Split a worker out only where a queue measurably delays something that must react fast, and measure the delay first (TODO "Consider splitting `orchestrator_automation.py`"). The first split is done: `builder_automation.py` (489df5f) takes every step that buys, deploys, upgrades or removes hardware.
- **Candidates for queued work:** decommission and commission steps, dock re-plans on order events, site supply re-publishes on demand changes, warehouse compaction per outpost.

## Open leads outside this plan

- Census plus machine activity still cost about 30 ticks per 300 (`CENSUS_TICK_INTERVAL` unchanged on 2026-10-11). The census only feeds `log_block_timing.py` and the activity card. Consider `CENSUS_TICK_INTERVAL = 600`, or running the activity sample every second census.
- `plan_dock_assignments` costs about 10 ticks per run. `plan_docks_if_due()` still checks `plan_signature()` every `DOCK_PLAN_TICK_INTERVAL` and re-plans when it changed or after `DOCK_PLAN_MAX_TICK_INTERVAL`. Phase 1.2 could make it event-driven too.
- The warehouse compaction sweep calls `between_steps()` once per outpost. With cheap fast passes this matters less; re-check after Phase 2.
- The demand record publisher now runs last in `between_steps()` (`publish_demand_if_due()`). After deploy, measure its block cost and the `supervise_grids` spacing with `log_block_timing.py --script automation`; expect about 180 ticks per refresh, normally in one call (`DEMAND_SLICE_TICKS = 400`). Headless (mid-late sample, 0.6 h): a refresh costs ~1,300–1,900 ticks, and parking passes moved from a median of 226 ticks apart (`main`) to ~1,100. Open: cut the refresh cost (atomic prefetch of stock scans and machine holdings) before deploy, then remeasure the spacing.
