# Plan: shared mission pool

Part of [README.md](README.md) (dynamic roles). Status: **session A done** 2026-10-20 (index published,
handoff in the README); session B below next. Supersedes the 2026-10-19 deferral: the pool returns as a read-only **index**
(`fleet.missions`), not as a second reservation system. The seam from the mixin refactor stays (`Mission.prio`,
`Mission.source`, `Job.pick()` as the single work intake, `next_job()` hook).

## Question

The priority ladder (`lib/priority.py`, [fabricator_demand.md §2a-p](../../cheatsheet/fabricator_demand.md))
ranks every demand from an Earth order or blueprint down to the ore. Should the cascade publish *missions* with
a priority, and the vehicle pool take the one it can fulfil, weighted by priority, and later by distance, time
to fulfil and staleness (floating Pioneers without a home)?

## Where we are (verified 2026-10-20)

Demand is pulled. Each role computes its work from ladders and reserves it atomically in the archive, and
every `pick()` ties feasibility and reservation together:

| Role | Reads | Reserves | Where the claim happens |
|---|---|---|---|
| hauler (pull) | `logistics.requests` (`logistics_requests.outpost_tier_deficits`) | `logistics.pickups` | `PullJob.pick` `claim_pickups` trims the planned route (`lib/job_pull.py:98-150`) |
| builder | blueprint lists + `construction.priority`, `construction.hold` | `survey.claims` (`build_<id>`), `construction.lots` | `BuildJob._select_work` scan (`lib/job_build.py:145-193`) |
| miner | `OutpostStockpile` helpers (Pioneer), `home_ore_demand()` (Rover) | `survey.claims` (`@vehicle`), `mining.reserved_yield` | `targets.select()` claims before it returns (`lib/job_mine.py:104-128`) |
| scout | unscanned POIs, `autoplay.survey_requests`, deep-oil targets | `survey.claims` (`poi_` keys) | per leg inside `survey_known_pois()` (`lib/job_survey.py:65-73`) |

Above them, `fleet.role_demand` (`lib/role_demand.py`) ranks the four pools per role (band, wanted, keep,
outposts) and `PioneerController.next_job()` (`lib/pioneer.py:154-215`) refits an idle Pioneer to the best
role through `fleet.role_claims` slots. Drones have no `next_job` yet.

## Decision: an index, no takes

A per-entry *take* would be a fifth reservation beside the four above, and each `pick()` would have to take
the pool entry and the source record in one step or double-account (the sketch's first open point). Nothing
observed needs that: the role-level switch already beats the retire rules
([ab_results_roles.md](../../headless/ab_results_roles.md)), and a refit costs parts, so ranking a build
against a haul *per entry* cannot change the refit decision more than the role bands do.

What is missing is one **view** of the fleet's open work at entry level: what, where, how urgent, since when,
and who holds it. Today that lives in four archive families and three job scans, so the operator cannot see
why a Pioneer refits (or does not), autoplay's `fleet:pioneer:<role>:+` rows cannot say what is waiting, and
two roles at the same band tie by name in `switch_candidates()` (`lib/role_demand.py:309-351`). The index
closes those three gaps. A take per kind comes back only with evidence from this index: an entry whose
`since` keeps growing while holders of its role sit idle.

Signal Bus: not used. A pool wake-up ("new mission") would reach no parked Pioneer (parked scripts are
powered off; `ScriptParking` wakes them, [dev_workflow.md §1d](../../cheatsheet/dev_workflow.md)), and an
idle job polls every `idle_delay` 10 s anyway. The bus guide's `receive(channel, id)` take leaves no record of
the holder and expires nothing ([signal_bus_guide.md](../../guide/signal_bus_guide.md) "Choose and take a
job"), so it fits neither the index nor a later take.

## Shape

- **Key** `fleet.missions = {"tick", "entries": [entry, ...], "dropped": {kind: n}}`, one archive dict
  (cap: [CODE_GUIDES.md#archive](../../../CODE_GUIDES.md)), stored as a list like `role_demand.stored()` so
  the game's JSON keeps the order. Stale after `ROLE_DEMAND_STALE_TICKS` like the role index.
- **Entry** `{"id", "kind", "prio", "outpost", "coords", "by", "item", "units", "since", "holders"}`.
  `id` is stable per demand (below), `prio` the ladder band (`priority.band()`), `outpost` the outpost id
  (None for a scan request away from any), `coords` `[x, y]` when the source has one (blueprint position,
  survey request), `by` the requester (`logistics.requests` `by`, the blueprint kind, the survey request
  `why`), `item`/`units` for haul and mine, `since` the tick the id first appeared (carried over from the
  previous value by id; the only state the index keeps), `holders` the vehicle names working it (derived,
  below). No `taken_by`, no `taken_tick`: there is no take.
- **Entries are demands, not trips.** Feasibility (energy, cargo, modules, hardness) stays per vehicle in
  `Job.execute()`/`pick()`; the index never decides who goes.
- **Publisher** `lib/mission_pool.py`, called from `role_demand.publish()` on the same cadence
  (`ROLE_DEMAND_TICK_INTERVAL = 600`, `orchestrator_automation.py:322-332`) with the same `PlanReads` and
  the intermediates `compute()` already builds (deficits per outpost, open job rows, scout work, miner
  bands). `compute()` returns them beside `roles` so nothing is read twice; `publish()` writes both keys.
- **Cap** `MAX_ENTRIES = 48`: band first, then oldest `since`, then id; the rest is counted in `dropped`
  per kind. Session A added `KIND_SHARE = 12`: each kind's first 12 are kept before the band order fills
  the rest (headless: 93 pipe blueprints at `BUILD` dropped every haul, mine and scan entry). Sorting is a `sorted(key=)` callback: one call, no logging inside
  ([dev_workflow.md](../../cheatsheet/dev_workflow.md) "Callbacks run as one unit").

### Entries per kind

| kind | id | source (already in `compute()`) | prio | holders (derived) |
|---|---|---|---|---|
| `haul` | `haul:<outpost>:<band>` | `deficits[oid][band]` (`outpost_tier_deficits`); `units` = sum, `item` = the largest, `by` = that item's request `by` from `reads.requests` | the band | haulers with a `logistics.pickups` entry `dest == oid` (`reads.pickups`, the vehicle field) |
| `build` | `build:<job id>` | `_open_job_outposts()` (`lib/role_demand.py:164-176`) extended to return `(id, kind, outpost, coords, prio)` rows; held kinds stay out as today | `priority.blueprint_prio(planned, priority)` with `autoplay.planned` (`construction_plan.PLANNED_KEY`) and `construction_lots.read_priorities()` | the `build_<id>` claim's vehicle in `survey.claims` (`construction_plan.py:49` key) |
| `mine` | `mine:<outpost>:<ore>` | `miner_demand()`'s per-outpost `bands` (every band, not only NEED; the cap and the band sort keep STOCK below) | the band | `mining.reserved_yield` entries with that `outpost_id` and `item_id` (`mining_reservations.get_reserved_yield_totals` has the pass; add a reader returning names) |
| `scan` | `scan:<request id>` | `survey_requests.read_requests()` (`{id: {x, y, radius, why}}`) | `NEED` (as `scout_demand()`) | none (a scout claims per leg; not worth a pass over `poi_` claims) |
| `scan` | `scan:pois` | one aggregate: `units` = unscanned POIs + unsurveyed sites from `read_scout_work()` | `STOCK` | none |

Drone-only kinds (`sample`, `aftermath`) come with the drone session (below).

## Consumers

1. **FLEET card, Roles tab → Queue view** (`lib/roles_card.py`): a second roster under the role list, or a
   toggle, listing entries as `kind target band age holders` (age from `since` in h, `game_clock`), detail
   pane with `by`, `item`/`units`, `coords`; a `dropped` line per kind. The role rows gain the count of open
   entries of their kind (haul→hauler, build→builder, mine→miner, scan→scout).
2. **Tie-break in `switch_candidates()`**: among roles at the same band, the role whose oldest *unheld* entry
   is older ranks first (`mission_pool.oldest_open(entries, kind)`), replacing the name tie. Age reorders only
   inside a band (sketch's ageing point): a STOCK entry never outranks a NEED one.
3. **Autoplay `why`**: `build_providers.want("fleet", ...)` rows for `fleet:pioneer:<role>:+` cite the oldest
   open entry of the role's kind (`"build cap_3 open 2.1 h"`), read from `fleet.missions` through the
   autoplay reads. Text only; no rule changes.

Not a consumer: `PullJob.pick`, `BuildJob`, `MineJob`, `SurveyJob`. They keep their own scans (the index is
600 ticks stale by design).

## Costs

One archive key. Per publish: the reads `compute()` already does plus `survey.claims`, `mining.reserved_yield`,
`autoplay.planned`, `construction.priority` and the previous `fleet.missions` (for `since`), then a loop over
< 100 candidate entries and one `sorted()`. Runs in the Automation every 600 ticks beside the role index;
measure with `devtools/perf/step_profile.py` once, together with the still-open `pull_destinations()` pass.

## Sessions

Each ends like the plan's rows ([README.md](README.md) "Sessions"): unittest, ruff, pyright green,
`cavecrew-reviewer` findings fixed, docs updated, commits on an `agent/<topic>` worktree, headless check,
handoff here. The operator merges before the next row.

| # | Session | Model | Why |
|---|---|---|---|
| 6 | This spec. | Fable | design |
| A | `lib/mission_pool.py` (`build(curr_tick, parts, previous)` pure, `publish`, `read`, `oldest_open`), `compute()` returns its intermediates, `publish()` writes both keys, the holder readers, `tests/test_mission_pool.py` on fixtures (ids stable, `since` carried, cap and `dropped`, holders), docs ([archive_ipc.md](../../cheatsheet/archive_ipc.md) `fleet.missions`, [lib_map](../../cheatsheet/lib_map.md), [§2f-1](../../cheatsheet/fleet_lifecycle.md)). Headless: entries appear with the `logistics` group real; ids survive a republish. | Opus | mechanical, every seam above verified |
| B | Consumers 1-3, DESIGN_HISTORY §2f-1 (why an index and no take), [panels](../../cheatsheet/panels.md) card row. Headless: the tie-break fires on two roles at one band. | Opus | mechanical |
| C | Drones: `sample:<contact>`/`aftermath:<event>` entries from the sources `job_biosite.py`/`job_aftermath.py` read; `DroneController.next_job` reads the role index (the plan's drone row). | Fable design, Opus edits | depends on the drone refit handshake |

## Open points

- Double accounting: resolved by having no take; holders are derived from the four reservation families.
- A take per kind: only on evidence from the index (an entry's `since` growing while its role's holders idle);
  construction first (claims, lots and priorities exist), through `fleet_claims_common.try_claim` on the
  entry id with `CLAIM_STALE_TICKS`, and `BuildJob` taking the source claim in the same transaction. Until
  then the index stays read-only for good: no job reads it, so `MAX_ENTRIES`/`KIND_SHARE` only bound what is
  listed, never what a builder does (verified 2026-10-20). A take would change that: an entry past the cap
  could not be taken, so the cap and the per-kind share need rethinking in the same change.
- `scan:pois` holders and per-POI entries: only if the scout tie-break needs them.
- `pull_destinations()` cost pass (`step_profile.py`), carried from Stage 1a.
