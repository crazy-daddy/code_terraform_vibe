# Event-Driven Automation

Plan for moving `control_room_automation.py` from polling to events: whoever causes a change reports it, and the Automation handles it instead of searching for it every pass. The script cost model is in [dev_workflow.md §1d-1](../cheatsheet/dev_workflow.md); script parking is in §1d-2.

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

## Hand-off

State on 2026-10-05:

- Phase 0 is committed (1e419c6) and deployed. Fix A is uncommitted in `scripts/4_controlpanel/lib/script_parking.py`, `tests/test_script_parking.py` and `docs/cheatsheet/dev_workflow.md` §1d-2. The user deploys it and lets it run longer before the next measurement.
- Next step: remeasure with `--since` set to the deploy time of fix A. Find the deploy time in `devtools/.sync-backups/sync.log` (`run automation_1.py restarted in game`).
- Then decide on fix B, then Phase 1.

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

Tests: one stub test per producer (the change wakes exactly the parked machines of that kind, no wake without a rise).

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
2. `between_steps()` in `control_room_automation.py` checks `comms.queue_size("fleet.decommission_ready")`. When it is non-zero, it `receive()`s and runs `FleetDecommissionCoordinator` for that machine.
3. The storage pass keeps its full `fleet_decommissioner.step()` as the backstop for lost messages.
4. Expected: undeploy within one `between_steps()` gap (minutes) instead of one storage pass (hours).

Open question: whether `between_steps()` should drain a generic `automation.events` channel with `wait_any`-style priority instead of one `queue_size()` check per feature. Decide after the pilot shows the cost of a check (BENCHMARK: about 5 steps per call).

## Phase 5: scanners and workers (depends on game features)

Long-term direction: scanner automations detect work and queue it on the Signal Bus; worker automations take it and handle it. Workers could scale with queue length.

- **Blocked on the developer:** deploying automations by script (`deploy()`) and starting or stopping them by script (`run_control` for automations). Without these, every worker counts as a running script all the time, even while it waits on an empty queue.
- **Once available:** a worker ends when its queue is empty; the scanner starts one (`run_control.start()`) when work is queued and none is running, and more when the queue grows. The worker count then follows the load.
- **Until then:** keep event handling inside the existing Automation (Phases 1–4). Split a worker out only where a queue measurably delays something that must react fast, and measure the delay first (TODO "Consider splitting `control_room_automation.py`").
- **Candidates for queued work:** decommission and commission steps, dock re-plans on order events, site supply re-publishes on demand changes, warehouse compaction per outpost.

## Open leads outside this plan

- Census plus machine activity still cost about 30 ticks per 300. The census only feeds `log_block_timing.py` and the activity card. Consider `CENSUS_TICK_INTERVAL = 600`, or running the activity sample every second census.
- `plan_dock_assignments` costs about 10 ticks per run, every 50 ticks while its signature changes. Phase 1.2 could make it event-driven too.
- The warehouse compaction sweep calls `between_steps()` once per outpost. With cheap fast passes this matters less; re-check after Phase 2.
