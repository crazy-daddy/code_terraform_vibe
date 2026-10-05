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

### Who flips the signature on the late save

Measured with a headless run that diffs consecutive signatures per machine (late save, 10 game minutes, `bulk_liquid_reservoir_9` set to 900 t at the start):
- `bulk_liquid_reservoir_9`: 9,263 of 9,378 changes. Its drain is 6 Fabricators on `craft_tar` (outposts 1 and 5, ~8 t/h each while starved, far more while oil is plentiful) plus 5 Oil Generators, against 48 t/h from 5 Oil Pumps. The 900 t were gone within minutes, then the tank flipped every tick.
- Item port rewiring: ~300 changes, about one rebuild every 20 ticks. `ioConnections` of every machine are in the signature, item ports included, so each `input`/`output` `connect()` to another Warehouse (Fabricators 11-16, `drone_station_lrg_6`/`_7` here) rebuilds every network once.
- Nothing else. Inferred from the code, not seen in this save: a machine with a generic `gas_in`/`liquid_in` port (Refiner, Habitat) flips too when its input buffer reaches 0 every tick, because `gas_in_level`/`liquid_in_level > 1e-9` is in the signature.

`FluidPort.connections()` also builds the signature (the connection index is cached under it), so every call costs one signature string over all machines and pipes, and a full rebuild while something is flipping. Prefer `connected_id()` on hot paths.

## What to do in game

- Keep pass-through tanks and reservoirs **buffered**: supply must exceed the draw, or the consumer is throttled below the supply. A tank that sits at a few units with in ≈ out is the worst case.
- When the draw can exceed the supply, the consumer, not the tank, has to give way: batch it with hysteresis (stop at a low fill, restart at a higher one). Throughput is the same, set by the supply, but the tank never sits at 0. Fluid-only Fabricator recipes (`craft_tar`) do this on their own ([production_logistics.md](../cheatsheet/production_logistics.md), "Fluid-only recipe"); the Oil Generator surplus burn already stops below 70 % ([power_fluids.md §1c-1](../cheatsheet/power_fluids.md)).
- Size consumers to the supply: count wells × rate against the sum of the always-on draws (Oil Generators on last resort, Fabricator recipes with oil plus items). Those don't pause, so if they alone exceed the supply the tank still runs dry.
- A buffer tank that only passes fluid through and is often empty is better removed from the line.
- Give every passive producer (Refiner, Liquifier, Steam Condenser) a tank of its output fluid in its own outpost and pipe that tank onward, or use a storage outpost on split networks (see "Storage outpost" below). A tank in another outpost that also feeds consumers over the pipes takes nothing from it while it holds stock (see "Remote (pipe) connections" below); the scripts then rank such a tank last. May change in the next game build: see the note under "Local vs remote tanks".
- Other signature inputs change rarely (building, deploying, reconnecting a fluid port); each such change costs one rebuild, which is fine. Frequent item port rewiring adds up (see above).

## Headless runs

`run.mjs --sticky-fluids` patches the signature (not the state): an empty machine keeps its last fluid type and the content flags are left out, so the cached analysis survives a tank running dry. Safe for our scripts, which route by the static tank assignment in the Data Archive, not by what an empty tank last held. Not safe for a test about tanks switching fluid.

## Local vs remote tanks: source and sink roles

> **To re-verify on the next game build** (the game dev, relayed by the owner on 2026-10-05, says it is fixed there: on a shared pipe a tank fills from its suppliers and feeds its consumers at the same time, and fluid on a pipe follows the declared connections exactly). Until that is checked, everything below still describes the current build. Affected if the fix holds:
> - the "consumers minus providers" rule (a remote tank that holds stock only gives) and the per-component pool ("declared pairs only decide who is on the component");
> - the storage outpost needing two pipe networks;
> - the producer-tank-to-storage drain (a producer's local tank pulled empty every tick by an unrelated sink);
> - in the scripts, `FluidOutputRouter` ranking a remote relay tank last (`feeds_remote_route()`, PR #24) and the "give every passive producer a local tank" rule.
>
> Check: rerun the storage test from "Storage outpost" below against the new simworker (one network vs two). The fix holds if storage fills to ~900 t on one shared network. Then remove the relay ranking and update this page. Tracked in [TODO.md](../../TODO.md) ("Fluids: validate the shared-pipe fix").
>
> Expected unaffected: the empty-tank rebuild trap above (an empty tank still unlatches) and the fluid-only recipe pause (PR #24), the item port rewiring cost, local direct connections, and the pumps/caps path.

Source: `FlowTransportSystem` in the decompiled sim worker (search `tickDirectConnections(`, `redistributePerFluidNetworks(`, `getFluidNetworkPlans(`, `routeSourceToTarget(`). Player-facing rules: [flow_networks_fluids.md](../guide/flow_networks_fluids.md) "Local versus remote".

### Two separate transport paths

Every declared `connect()` pair (from either side) is classified by its two **anchors**: an outpost machine's anchor is its outpost, a map machine (Water/Oil Pump, Thermal Cap, Exotic Cap/Tap) is its own anchor.
- **Same anchor ("local")**: handled only by `tickDirectConnections`. No pipe is involved and the pair never shows up in a pipe network.
- **Different anchors ("remote")**: becomes a *route* in the network analysis (`Ex`, routes are kept only when `sourceAnchorId !== sinkAnchorId`) and is moved by the pipe component it is assigned to.

So a pump or cap never connects "locally": it always needs a pipe, even to a tank at the outpost next to it.

### Local (direct) connections

- Each source/sink/fluid pair is its own edge with its own cap: `flow.directMaxFlowPerGameHour` per pair (High Pressure tech does not raise it).
- At the start of the tick the game snapshots every source's level and every sink's headroom, then solves one max-flow over all pairs of the same fluid (`a_e`: proportional first guess, then augmenting paths).
- Sources and sinks are separate nodes in that graph. A tank that is the source of one pair and the sink of another is in both roles at once: it can give and take in the same tick.
- Pump-type machines (`$w` set) are skipped here as sources.

### Remote (pipe) connections

`Ex` builds, per pipe component, `sourceEndpointIds` (every machine that is the source of a route on it) and `sinkEndpointIds` (every route sink). `getFluidNetworkPlans` keeps a source only if it can supply the component's fluid (a tank needs its latched `stringData.fluid` to match, so an empty, unlatched tank is not a source) and a sink only if it can accept it.

Tanks and other passive sources are then moved by `redistributePerFluidNetworks` before power:
- **Providers** are the source endpoints with level > 0 (pump-type machines excluded).
- **Consumers** are the sink endpoints with headroom > 0, **minus every id that is already a provider** on that component. This is the rule behind the owner's observation: a remote tank that is both a route source and a route sink on the same component, and holds fluid, only gives; it receives nothing from other passive providers there.
- An empty tank drops out of the providers (and out of the sources when its fluid unlatches), so it can be filled again. Inferred: such a tank alternates between "giving" and "taking" ticks, and each unlatch also rebuilds the analysis (see the trap above).
- The fluid is **pooled per component**: all providers' levels form one pool that is split over all consumers by headroom. The declared pairs only decide who is on the component, not who feeds whom. Recorded pipe flows are a sorted id pairing for display.
- A tank that is a source on component P and a sink on another component Q is not affected: the exclusion is per component. Inferred from the code path, not tested in game.

Pumps, Thermal Caps and Exotic Caps/Taps run after power in `routeSourceToTarget`. They follow their own declared routes (sink by `sinkMachineId`) and check only sink headroom and the ledgers, not the provider list, so a pump **can** fill a remote tank that is also a provider on that component.

### Storage outpost: one network or two (tested on the current build)

Headless test on a copy of the late save: three new outposts with one Large Liquid Tank each, a producer tank (1,000 t oil) connected to a storage tank, the storage tank connected to a consumer tank with 100 t room. Run 500 ticks.
- **One pipe network through all three**: storage held ~22 t and never filled. Once the consumer was full, the producer stalled at 878 t. Storage feeds the consumer over the same network, so it is a provider there and takes nothing from the pool.
- **Two pipe networks** (producer to storage, storage to consumer; both pipes enter the storage outpost but don't touch each other): storage filled to 900 t, the producer emptied into it, the consumer was fed throughout.

So a storage outpost works with a supplier network and a consumer network that meet only inside the storage outpost. Two pipes that end in the same outpost stay separate networks unless they touch. Producers then need no tank of their own: storage takes their output directly. Tank to tank links work too (a script can `connect()` a tank's `liquid_out` to another tank; ~24 t per tick on one pipe).

### Capacity ledgers and ordering

- Per component, per tick: `throughputLinks × pipe max` in total, and per endpoint `(pipe links it claims, min 1) × pipe max` on each side (`ensureNetworkCapacityLedgers`). The pipe max is the High Pressure value once unlocked.
- Order in a tick: direct connections, then tank pooling (pre-power), then caps, then pumps (post-power). The ledger is shared, so tank pooling consumes component capacity first and pumps get what is left.
- Pump-type sources on one component split the remaining capacity equally (`prepareScriptSourceFairness`). Within one source, sinks are filled in proportion to headroom, ordered by id.
- An endpoint on several components of the same fluid has its level or headroom split between them by requested share (`B0`).

### What this means for our scripts

- A tank that should both receive and pass on fluid (a relay or buffer) works when its in-pair and out-pair are local. Across outposts, put its inflow and outflow on different pipe components, or feed it from a pump (pumps ignore the exclusion).
- Never rely on a declared pair across a shared component: any passive provider on it can feed any consumer on it.
- A local connection does not compete for pipe capacity; prefer a same-outpost tank where one exists (`rank_own_outpost_first` in `fluid_routing.py` already does).
- Several tanks pooling on one component can use up its capacity before pumps get their turn: a stalled pump may mean a full pipe ledger, not a full tank.
