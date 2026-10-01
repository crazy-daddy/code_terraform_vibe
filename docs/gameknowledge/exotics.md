# Exotic deposits (gas caps, spring taps)

Source: the world generator in `internals/terraform_decompiled/simworker/deobfuscated.js` (exotic deposit table, around lines 161748-161910). 15 deposits per world.

## Fixed on every map

Counts and ranges are constants. Rates are `t/h` at the peak (`basePeakRate`); times are game minutes.

| Fluid | Medium | Rarity | Count | Active (min) | Dormant (min) | Peak rate (t/h) |
|---|---|---|---|---|---|---|
| swamp_gas | gas | common | 3 | 25-45 | 40-70 | 40-90 |
| ammonia | gas | common | 3 | 25-45 | 40-70 | 40-90 |
| raw_sulfur_gas | gas | uncommon | 2 | 20-35 | 60-100 | 30-70 |
| raw_chlorine | gas | rare | 1 | 15-30 | 90-150 | 25-55 |
| brine | liquid | common | 3 | 25-45 | 40-70 | 40-90 |
| raw_cryofluid | liquid | uncommon | 2 | 20-35 | 60-100 | 30-70 |
| raw_quicksilver | liquid | rare | 1 | 15-30 | 90-150 | 25-55 |

Deposits do not deplete. Refining is 1:1 raw to refined and also consumes tar (moderate for uncommon, heavy for rare; exact amounts are in the Refiner recipes).

## Rolled per map

A PRNG seeded from the world seed (`seed ^ 1016756193`) rolls, per deposit:
- position (needs deep sonar reach; at least 60 from other exotics, 40 from other hazards),
- active and dormant minutes inside the ranges above,
- phase offset (`basePhase`, 0 to active + dormant),
- peak rate inside the range.

A script reads the real values at runtime: wide survey gives the rate, deep survey gives the cycle (`cycle_active_minutes()`, `cycle_dormant_minutes()`, `next_phase_in()`).

## Worst-case and best-case average rate

Average = peak rate x active / (active + dormant), assuming capture holds the peak rate through the active phase.

| Rarity | Worst per deposit | Best per deposit |
|---|---|---|
| common | 40 x 25 / (25 + 70) = 10.5 t/h | 90 x 45 / (45 + 40) = 47.6 t/h |
| uncommon | 30 x 20 / (20 + 100) = 5.0 t/h | 70 x 35 / (35 + 60) = 25.8 t/h |
| rare | 25 x 15 / (15 + 150) = 2.3 t/h | 55 x 30 / (30 + 90) = 13.8 t/h |
