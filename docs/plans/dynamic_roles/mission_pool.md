# Sketch: shared mission pool

Part of [README.md](README.md) (dynamic roles). Status: **deferred**. Decision 2026-10-19: `fleet.role_demand`
(the role-level index of that plan) covers what this pool was for; a per-entry `fleet.missions` with takes comes
back only if band-level ranking proves too coarse. The seam from the mixin refactor stays (`Mission.prio`,
`Mission.source`, `Job.pick()` as the single work intake, `next_job()` hook).

## Question

The priority ladder (`lib/priority.py`, [fabricator_demand.md §2a-p](../../cheatsheet/fabricator_demand.md))
ranks every demand from an Earth order or blueprint down to the ore. Should the cascade publish *missions* with
a priority, and the vehicle pool take the one it can fulfil, weighted by priority, and later by distance, time
to fulfil and staleness (floating Pioneers without a home)?

## Where we are

Demand is pulled. Each role computes its work from ladders and reserves it atomically in the archive:

| Role | Reads | Reserves |
|---|---|---|
| hauler (pull) | `logistics.requests` (`logistics_requests.outpost_tier_deficits`) | `logistics.pickups` (`claim_pickups`) |
| constructor | blueprint lists + `construction.priority`, `construction.hold` | `survey.claims` (`build_` keys), `construction.lots` |
| miner | `home_ore_demand()` / outpost stockpile targets | `survey.claims` (`@vehicle` keys), `mining.reserved_yield` |
| scout | unscanned POIs, `autoplay.survey_requests`, deep-oil targets | `survey.claims` (`poi_` keys) |

These are four pools already. What is missing is one index over them ranked by band, so a Pioneer could
weigh a build against a haul, and a floating one could weigh distance and age.

## Shape

- **Archive, not Signal Bus.** Bus queues survive save/load and `receive()` takes each message at most once
  ([signal_bus_guide.md](../../guide/signal_bus_guide.md)), but a taken message leaves the queue: no lease,
  no stale expiry, no record of who holds it, and a queue holds at most 64 messages. A pool needs a take that
  expires and stays visible, so it is one archive dict, `fleet.missions = {mission_id: {kind, prio, target, by, tick, taken_by, taken_tick}}`,
  written through `archive.transaction()` and taken with `fleet_claims_common.try_claim`. The bus can carry a
  wake-up ("new mission") so idle vehicles don't poll.
- **Entries are demands, not trips.** What, where, how urgent (`prio` from the ladder), who asked (`by`).
  Feasibility (energy budget, cargo capacity, mounted modules, hardness) is per vehicle, so `Job.execute()`
  keeps planning the trip, and `Job.pick()` filters the pool by what this vehicle can do.
- **Publishers.** The orchestrator (`orchestrator_automation.py`) per cascade tick, from the existing sources:
  site-supply requests → `haul`; pending/paused blueprints → `build`; ore deficits → `mine`; survey requests
  and unscanned POIs → `scan`. Each publisher owns its ids and prunes its own dead entries.
- **Take.** `try_claim` on `taken_by`; `refresh` while working; `release` on failure. Stale takes expire with
  `CLAIM_STALE_TICKS`, like claims today.
- **Ranking in `pick()`.** Band first (lexicographic, rule 1 of §2a-p), then within the band a score of
  distance (or time to fulfil from the energy model), then age (older first). Haulers and miners rank by band
  only today (rule 2); keep that until the fine value is shown to help.
- **Role swap.** With `next_job()` a Pioneer that can build and haul can take a `build` entry while idle as a
  hauler; `on_leave()` releases what the current job holds first.

## Open points

- Double accounting while both the old per-role pools and `fleet.missions` exist: the pool entry must point
  at the source record (request id, blueprint id, site key), and the take must also take the source
  reservation, or the source stays the only reservation and the pool is read-only (an index). Start with
  the index; add take per kind, construction first (it has claims, lots and priorities already).
- Ageing: an untaken `STOCK`-band entry should not outrank a fresh `NEED` entry; age only reorders inside a
  band.
- FLEET card: show the pool (kind, prio, age, taken_by) as the fleet's work queue.
- Drones: same pool, kinds `haul`, `sample`, `scan`, `aftermath`; `DroneController` shares `run_job_loop`.
