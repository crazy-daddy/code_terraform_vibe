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

## Phase 0: chore cost cut (done in the working tree, not deployed)

Behavior is unchanged except for the parking split. Measured by replaying the live save's machines and parking archive through the stub harness (scratch profile on top of `devtools/step_profile.py`). The replay matched the live logs at about 43 ticks per parking pass before the change.

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
