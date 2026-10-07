# Solar power: day curve, panel output and night sizing

Source: `internals/terraform_decompiled/simworker/deobfuscated.js`. Search `dayCycleDuration` (constants), `morningPeakStart` (curve, inside the clock update), `function F1(` (panel output), `function dne(` (overcrowding). Re-check these when the game updates.

## Constants

| Constant | Value |
| --- | --- |
| Day length | 24 game hours (`planet.dayCycleDuration` = 600 s real time at 1x) |
| Panel peak (`power.generatorPeakOutput`) | 50 W |
| Battery (`power.batteryCapacity`) | 500 Wh |
| Default panel tilt (idle, no script) | 90° |

## Solar efficiency over the day

`clock.solarEfficiency` is piecewise linear in the day fraction `f` (0 = midnight). The sun elevation is `solarEfficiency * 90`, so `clock.get_elevation() / 90` gives the efficiency directly.

| Day fraction | Hours | Efficiency | Phase |
| --- | --- | --- | --- |
| 0.00 – 0.25 | 00:00 – 06:00 | 0 | night |
| 0.25 – 0.30 | 06:00 – 07:12 | 0 → 0.5 | dawn |
| 0.30 – 0.38 | 07:12 – 09:07 | 0.5 → 1 | morning |
| 0.38 – 0.54 | 09:07 – 12:58 | 1 | peak |
| 0.54 – 0.71 | 12:58 – 17:02 | 1 → 0.5 | afternoon |
| 0.71 – 0.83 | 17:02 – 19:55 | 0.5 → 0 | dusk |
| 0.83 – 1.00 | 19:55 – 24:00 | 0 | night |

- Zero output for 10.08 h (19:55 to 06:00).
- Daylight 13.92 h, but the integral is only **0.39 day = 9.36 full-sun hours**.
- **One perfectly tracked panel gives 468 Wh per day**, average 19.5 W over 24 h.

## Panel output

`W = 50 × solarEfficiency × tiltFactor × overcrowding` (only when powered).

- `tiltFactor = cos(err)^5`, with `err = |tilt − (90 − elevation)|` (0 when `err` ≥ 90°). It is 1 when tilt + elevation = 90°, as `lib/solar.py` sets it. Losses: 2° off costs 0.3 %, 5° costs 1.9 %, 10° costs 7.4 %, 20° costs 27 %. A panel left at the default 90° tilt makes almost nothing while the sun is high.
- `overcrowding`: solar is a `throughput` building. At an outpost with more buildings than its slot limit, each building over the limit costs 10 % (floor 20 %). Slot limit: home 25, other outposts 20, +5 with `outpost_expansion_unlock`, +1 at home with `weather_program_unlock`. Within the limit the factor is 1.

## Sizing for a constant load

For a constant load `L` (W) on a grid with only solar and batteries:

- **Energy:** panels ≥ `L × 24 / 468` = `0.0513 × L`. This is the hard floor; below it the batteries drain a little every day, and the grid browns out after some days.
- **Storage:** the batteries must carry the load from the moment output drops below `L` in the evening until it rises above `L` in the morning. That is the 10.08 h of night plus the dim dawn/dusk edges, about **11.5 h × L** in practice. With the panel count near the energy floor, about 11.5 Wh of battery per W of load (393–408 Wh per 35 W).
- Add margin above both floors: the curve has no weather term today, but any extra load (vehicle charging, scripts turning machines on) eats the surplus.

Machine draws (game text): Pressure Generator Mk I 7 W; Mk II pack 5x = 35 W.

## Worked example: 20 slots, Mk II Pressure Generators only

Steady state after 40 simulated days, perfect tracking, no other load. `G` Mk II generators, `S` panels, `B` batteries, `G + S + B = 20`. "Min charge" is the lowest battery level of the day.

| G | Feasible (S, B, min charge Wh) |
| --- | --- |
| 5 | (9, 6, 958), (10, 5, 486), (11, 4, 9) |
| 4 | (8, 8, 2389) … (12, 4, 456) |
| 3 | (6, 11, 4292) … (14, 3, 377) |
| 6+ | none |

**Best: 5 Mk II + 10 solar + 5 batteries.** 4,680 Wh/day against 4,200 Wh used (11 % surplus), and the batteries keep 486 Wh at dawn. 9/6 has more battery margin, but its energy surplus is 0.3 %, so any extra load drains it over days. 11/4 ends the night at 9 Wh. This matches the headless sim result in [early_optimization.md](../autoplay/early_optimization.md) ("Pressure Mk II in the tail"), where pw10/5 was the best power level.

Script for other loads: copy the curve above into a loop over the day in small steps, starting with full batteries, and run 40 days to reach steady state; a grid fails if the charge goes below 0.
