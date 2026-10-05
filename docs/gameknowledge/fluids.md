# Fluid networks: cache, rebuilds and CPU cost

Source: the flow transport system in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `tickPrePower(`, `function Ex(`, `function gx(`), measured with the headless runner ([dev_workflow.md §10b](../cheatsheet/dev_workflow.md), [plans/headless_sim.md](../plans/headless_sim.md)) on the owner's late save (887k TP, 274 machines).

## How the game computes flows

Every tick, `FlowTransportSystem` runs twice: before power (`tickPrePower`: tank port levels, network plans, pipe states, direct connections, per-fluid redistribution) and after power (`tickPostPower`: capacity ledgers, Thermal Caps, Exotic Caps and Taps, Fluid Pumps). Both start from the **network analysis** `Ex(state)`: pipes grouped by medium (gas, liquid), each segment sampled every 10 map units, union-find over the points, bridges and fluid route assignments, then which machine ports sit on which network.

The analysis is cached per state object (`ux`, a WeakMap). The cache key is a **signature string** `gx()` rebuilt on every call from:
- every outpost (id, position, under construction),
- every pipe (id, type, complete) and every segment's end points,
- every gas/liquid bridge, every fluid route assignment,
- every machine: id, type, location, under construction, footprint/rotation for utility buildings, its `*_capacity` keys, its io connections, its **fluid types** (`stringData.fluid`, `gas_in_fluid`, `liquid_in_fluid`), and whether `gas_in_level`/`liquid_in_level` and, for tanks, the stored `level` are **above 1e-9**.

When the string differs from the cached one, the whole analysis is rebuilt.

## The trap: a tank that runs dry every tick

An empty tank does not keep its fluid: when its level reaches 0 the game clears `stringData.fluid` and the per-fluid port keys (`gre()`), and they come back as soon as fluid flows in. A tank whose consumers draw at least as much as flows in therefore toggles every tick between "oil, has content" and "no fluid, empty". Each toggle changes the signature, so the analysis is rebuilt **twice per tick** (pre- and post-power), for every network on the planet, not just the tank's own.

Measured on the late save, `bulk_liquid_reservoir_9` (oil, outpost_4, 48 t/h in and ~48 t/h out, ~0.2 of 1,000 stored):
- 121 of 132 analysis calls missed the cache over 60 ticks (with the reservoir buffered: 13 of 131, from occasional machine changes).
- FlowTransport cost 142 ms per tick, against 13 ms with the reservoir buffered. That was 43 % of all simulation CPU, twice the cost of all 146 running scripts together.
- Filled to 500 by hand, the reservoir was empty again within ~2 game minutes (the outflow is a little higher than the inflow), and the rebuilds came back.

This is CPU only: the game's tick result does not change, but the sim worker is single-threaded, so a slow tick slows the whole game once it can no longer keep up with the tick rate (10 ticks/s × game speed). Inferred from the code path; the in-game slowdown itself was not measured.

## What to do in game

- Keep pass-through tanks and reservoirs **buffered**: supply must exceed the draw, or the consumer is throttled below the supply. A tank that sits at a few units with in ≈ out is the worst case.
- A buffer tank that only passes fluid through and is often empty is better removed from the line.
- Other signature inputs change rarely (building, deploying, reconnecting); each such change costs one rebuild, which is fine.

## Headless runs

`run.mjs --sticky-fluids` patches the signature (not the state): an empty machine keeps its last fluid type and the content flags are left out, so the cached analysis survives a tank running dry. Safe for our scripts, which route by the static tank assignment in the Data Archive, not by what an empty tank last held. Not safe for a test about tanks switching fluid.
