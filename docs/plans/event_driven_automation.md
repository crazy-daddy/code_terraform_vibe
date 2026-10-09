# Event-Driven Automation

Plan for moving `orchestrator_automation.py` from polling to events: whoever causes a change reports it, and the Automation handles it instead of searching for it every pass. The script cost model is in [dev_workflow.md §1d-1](../cheatsheet/dev_workflow.md); script parking is in §1d-2.

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

Behavior is unchanged except for the parking split. Estimated by replaying the live save's machines and parking archive through the stub harness (scratch profile on top of `devtools/step_profile.py`). The replay matched the live logs at about 43 ticks per parking pass before the change.

| Change | Before | After |
|---|---|---|
| Parking: one indexed member pass (`_by_type`, `_dark`) instead of four walks over all members; unused `_summary()` removed | ~43 ticks per pass | ~28 ticks per full pass |
| Parking: fast pass every 50 ticks (wakes only, reuses the last full pass's member rows and oil surplus verdict); full pass every `PARKING_FULL_TICK_INTERVAL = 150` | 3 × 43 = ~129 ticks per 150 | 28 + 2 × 12 = ~52 ticks per 150 |
| Census: machine rows built and de-duplicated in atomic batches | ~93 ticks per 300 (with activity) | ~30 ticks per 300 |
| Machine activity: per-group tally and merge in atomic batches, `ACTIVITY_CHUNK` 50 → 100 | (included above) | (included above) |

The largest single atomic call is about 3.4k steps, under the 10,000-step cap.

**Verify after deploy:**

1. Run `python devtools/log_block_timing.py --script automation --since <deploy time UTC>`. Expected: `script parking` median about 28 ticks (full) and about 12 ticks (fast).
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

State on 2026-10-06:

- Phase 0 (1e419c6) and fix A (2d8b676) are committed and deployed. Fix A results are above.
- Phase 1 (except 1.3) is in the working tree and passed the headless A/B; see "Phase 1 status". Next step: deploy and remeasure with `--since` set to its deploy time (`run automation_1.py restarted in game` in `devtools/.sync-backups/sync.log`).
- Fix B (full pass by pass count) is still open. Decide after the Phase 1 measurement, since fewer events change the pass spacing.

How to measure (main save, read-only; the logs are in `%APPDATA%\io.codeterraform.game\save_mtzkzly3_4ww80o_scripts\logs\`):

1. Block times: `python devtools/log_block_timing.py --script automation --since <ISO UTC>`. A debug block's header carries the clock of its first inner line, so the parking row misses the pass's pre-work. Add the gap between the line before `┏━ script parking` and that header.
2. Events per pass: count `woke ` and `parked ` lines between `┏━ script parking` and `┗━ END script parking` in `automation_1.log`. Group wakes by the reason in parentheses.
3. Pass spacing: the game-clock difference between consecutive `┏━ script parking` headers, divided by 14.4 s per tick.
4. Backoff hits: `grep -c "found no work" automation_1.log` and `grep -o "next one in [0-9]* ticks" | sort | uniq -c`. Compare with the count of `re-check due` wakes per kind.
5. Storage pass period: the tick difference between consecutive `home salt request` lines.
6. Decommission delay: see "Verify after deploy", step 3.

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

6. **Verify in headless** (A/B, before deploying): `devtools/headless/save_scripts.py` maps the repo's scripts onto a save's slots (dev_workflow.md §10b). Resolve one directory from `main` (baseline) and one from the change, then run both on the same save with `run.mjs --save <save> --scripts <dir> --libs <dir>/lib --hours 0.6 --paid-debug --sticky-fluids --out <dir>`. `--paid-debug` is required: a debug line costs about a tick in game, about half of a wake or park event. Saves: the mid-late sample (`internals/sample_saves/`, 2026-10-05, 16 habitats) and a copy of the current main save. Compare from `console.log` (`[tick N] [level] [script] text`): parking passes, block ticks, events per pass, wakes by kind and reason, writer wakes (`[PARKING] Woke N <kind>(s) (...)`), and Fabricator/Smelter output (`Sent Nx <item> to storage`) so the longer backstop timers cost no production.

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

Open: 1.3 (Oil Generator wake from `supervise_grid()`). In the 169k-tick main-save window no Oil Generator woke on a low reserve, so it waits for a measurement that shows the fast-pass reserve check costs anything.

## Phase 2: timer index for the fast pass

1. Keep `next_due`, the earliest `since + wake_after` over the parked breaker entries, in the `ScriptParking` instance. Recompute it on every full pass and after every park or wake.
2. Fast pass: if `now < next_due` and no wake message is queued (`comms.queue_size()`), return before reading the archive. Expected cost: a few dozen steps, down from about 12 ticks.
3. Entries other scripts write (`turbine_commit`, `wake_for_visit()` holds) don't move `next_due` earlier. If one ever needs an early wake, it sends a message.

## Phase 3: remaining physics polls

1. **Oil Pump `well_active()`, exotic cap `deposit().current_phase()`.** Where `next_phase_in()` is known, the machine files `wake_after` as `exotic_cap` already does, so the wake becomes a timer. Otherwise poll on the full pass only, if the data allows. Check how fast wells really turn active in the logs before slowing this down.
2. **Solar day/night.** It is driven by the clock elevation, so it can become a timer from the day length. Low priority: it is cheap after Phase 0.
3. **Strays and orphan adoption.** These stay on the full pass. They are backstops by design.

## Phase 4: fleet decommission as the first queued event

A small pilot for the message pattern outside parking.

1. `drone_claims._prepare_decommission()` and `vehicle_claims._prepare_decommission()` send `fleet.decommission_ready` with `{"id", "kind"}` after `mark_decommission_ready()`.
2. `between_steps()` in `orchestrator_automation.py` checks `comms.queue_size("fleet.decommission_ready")`. When it is non-zero, it `receive()`s and runs `FleetDecommissionCoordinator` for that machine.
3. The storage pass keeps its full `fleet_decommissioner.step()` as the backstop for lost messages.
4. Expected: undeploy within one `between_steps()` gap (minutes) instead of one storage pass (hours).

Open question: whether `between_steps()` should drain a generic `automation.events` channel with `wait_any`-style priority instead of one `queue_size()` check per feature. Decide after the pilot shows the cost of a check (BENCHMARK: about 5 steps per call).

## Phase 5: scanners and workers (depends on game features)

Long-term direction: scanner automations detect work and queue it on the Signal Bus; worker automations take it and handle it. Workers could scale with queue length.

- **Blocked on the developer:** deploying automations by script (`deploy()`) and starting or stopping them by script (`run_control` for automations). Without these, every worker counts as a running script all the time, even while it waits on an empty queue.
- **Once available:** a worker ends when its queue is empty; the scanner starts one (`run_control.start()`) when work is queued and none is running, and more when the queue grows. The worker count then follows the load.
- **Until then:** keep event handling inside the existing Automation (Phases 1–4). Split a worker out only where a queue measurably delays something that must react fast, and measure the delay first (TODO "Consider splitting `orchestrator_automation.py`").
- **Candidates for queued work:** decommission and commission steps, dock re-plans on order events, site supply re-publishes on demand changes, warehouse compaction per outpost.

## Open leads outside this plan

- Census plus machine activity still cost about 30 ticks per 300. The census only feeds `log_block_timing.py` and the activity card. Consider `CENSUS_TICK_INTERVAL = 600`, or running the activity sample every second census.
- `plan_dock_assignments` costs about 10 ticks per run, every 50 ticks while its signature changes. Phase 1.2 could make it event-driven too.
- The warehouse compaction sweep calls `between_steps()` once per outpost. With cheap fast passes this matters less; re-check after Phase 2.
