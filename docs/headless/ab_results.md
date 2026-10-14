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

## Phase 1: terraforming `standin` vs real (2026-10-14)

Midlate save, `--hours 0.33 --report-every 5` (11,880 ticks), everything else real; 9 slots replaced (3 Mk III heaters, 3 Mk III O2 generators, 3 Mk III pressure generators), 134 scripts running in both runs.

| | real | `--standin terraforming=standin` |
| :--- | ---: | ---: |
| heat gained | 310.11 | 310.97 (+0.28 %) |
| O2 gained | 284.47 | 283.80 (-0.24 %) |
| pressure gained | 14.256 | 14.256 |
| TP at the end | 826,587 | 826,581 |
| errored / crashed | 0 / none | 0 / none |
| steam guard | open (pool 100 %) | open (`pool` 1, `guardOff` []) |
| × real time | 1.85 | 1.81 |

Notes: the save's O2 generators start on a dry `steam_condenser_1`; the real router moves them to `bulk_liquid_reservoir_8` within ~80 ticks, the `_feed.py` keeper after ~210 (two checks 5 s apart), which is the O2 gap. Two earlier attempts are the reason for two rules in the code: the guard read the port buffer keys (`gas_in_level`) instead of the tank's `data.level` and closed on a 100 % pool (heat +11 instead of +310), and without the feed keeper the stand-ins kept the dry source (O2 +122). No speed gain is expected on this save (9 of 134 scripts); the mode exists so a later `scale` and the other groups' modes can run with the atmosphere still moving. Still open: the same pair on 0262 (24 pressure generators, no heaters) and `park` in the same table.

## Phase 2: terraforming `scale` vs real (2026-10-14)

Midlate save, `--hours 0.33 --report-every 5` (11,880 ticks), everything else real; `--standin terraforming=scale,max=50`: 9 Mk III machines into 3 records (`heater_10`, `o2gen_10`, `pressure_10`, `data.scale` 3 each), 6 undeployed, 18 kit and upgrade-pack units removed from the Inventory, no refusal, no stall (`minLevel` 7.95 / 4.97 / 4.98 t, the ports' capacity). 134 scripts running in the real run, 128 plus 6 ghosts in the scaled one (allowance 370 steps at the end in both).

| | real | `--standin terraforming=scale,max=50` |
| :--- | ---: | ---: |
| heat gained | 310.13 | 310.97 (+0.27 %) |
| O2 gained | 284.47 | 283.71 (-0.27 %) |
| pressure gained | 14.256 | 14.256 |
| TP at the end | 826,552 | 826,507 |
| errored / crashed | 0 / none | 0 / none |
| `power.consumed` at the 5-minute reports | 5393 / 5533 / 5736 / 4519 W | 5301 / 5355 / 5724 / 4376 W (-1.7 / -3.2 / -0.2 / -3.2 %) |
| net worth at the end | 5,081,621 | 5,052,221 (the 6 machines' value) |
| × real time | 1.55 | 1.61 |

The `power.consumed` gap is not the terraformers: with every other group `off` (power real, 3 game minutes, `iso_real` / `iso_scale` scenarios), `consumed` is identical at every report (3482.4 / 3320.4 / 3310.4 / 3190.5 W in both), so the scaled draw of a record equals its N machines' draw. In the full pair the other loads drift (running scripts 125-136 vs 124-129 between reports, drones charging and fabricators on different schedules). The heat and O2 deltas are the Level-1 stand-in's (phase 1 above: the O2 generators' dry-condenser gap); `scale` adds nothing measurable. No speed gain on this save (9 of 134 scripts); the mode pays off on saves with dozens of identical terraformers.

## Open rows

| Mode | Save | Planned comparison |
| :--- | :--- | :--- |
| terraforming `park` vs `standin` | 0262; `park` on midlate | heat / O2 / pressure gained over 20 game minutes, errored, speed; accept ≤ 1 % heat deviation (midlate `standin` vs real: done above) |
| terraforming `scale` | 0262 (24 pressure generators) | records of 10, speed gain, `stalled` empty; midlate: done above |
| power `trim` | 0262, midlate | brownout seconds, `stored` trace, speed |
| logistics `mover` | 0262 with factory real | ingots and kits reaching outposts per hour, errored 0 with everything else real |
| plants `produce` | 0142, 0262 | credits per hour with the rest stood in |
