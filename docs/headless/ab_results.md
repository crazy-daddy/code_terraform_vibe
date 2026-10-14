# A/B results

A stand-in mode ships with a row here: the same save, the same game time, the real run against the mode, both on current repo scripts. Columns: what the test target would read (TP, atmosphere, credits), script health, and speed. Earlier tables (passive-machine parking, the late-save profile) are in [../plans/headless_sim.md](../plans/headless_sim.md).

Canonical saves: `internals/sample_saves/20261007_c5f9ebf/saves/0262_t349372.json.gz` (day 59, 24 pressure generators, 8 turbines, 10 smelters, 12 pioneers) and `internals/sample_saves/save_mtzkzly3_4ww80o.midlate_2026-10-05.json` (the main save, mid-late, heaters and Mk III machines). Record the `latest scripts:` line and any `skip` lines once per save: both saves run the repo's current scripts by default, and the 20261007 run predates some role renames.

## Phase 0: parity of the scenario engine with the 306e188 hack (2026-10-14)

Save 0262, `--only-scripts harvester_1 --stock seeds_basic=40 --drain forage:600 --hours 0.25`, old `run.mjs` (commit 306e188) against the scenario engine.

| | 306e188 | scenario engine |
| :--- | ---: | ---: |
| `metrics.jsonl` (wall time fields removed) | identical | identical |
| `stocked.seeds_basic` / `drained.forage` | 40 / 0 | 40 / 0 |
| TP, credits at the end | 240,924 / 25,148 | 240,924 / 25,148 |
| scripts running / errored | 1 / 0 | 1 / 0 |
| harvester allowance (steps per tick) | 1,000 | 694 (71 ghosts; the full base's value) |
| × real time | 100 | 118 |

The harvester sleeps most of the time, so the lower allowance changed nothing here; it matters for a busy target.

## Open rows

| Mode | Save | Planned comparison |
| :--- | :--- | :--- |
| terraforming `park` vs `standin` | midlate, 0262 | heat / O2 / pressure gained over 20 game minutes, errored, speed; accept ≤ 1 % heat deviation |
| terraforming `scale` | midlate | the same plus `planet.power.consumed` within 1 % at every report, no record's `*_in_level` pinned at 0 |
| power `trim` | 0262, midlate | brownout seconds, `stored` trace, speed |
| logistics `mover` | 0262 with factory real | ingots and kits reaching outposts per hour, errored 0 with everything else real |
| plants `produce` | 0142, 0262 | credits per hour with the rest stood in |
