# Fluid networks: cache, rebuilds and CPU cost

Source: the flow transport system in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `tickPrePower(`, `function ak(`, `function JO(`, `function ese(`), measured with the headless runner ([dev_workflow.md §10b](../cheatsheet/dev_workflow.md), [plans/headless_sim.md](../plans/headless_sim.md)). Earlier builds and their workarounds: [DESIGN_HISTORY.md §10b-1](../DESIGN_HISTORY.md).

## How the game computes flows

Every tick, `FlowTransportSystem` runs twice: before power (`tickPrePower`: tank port levels, network plans, pipe states, direct connections, per-fluid redistribution) and after power (`tickPostPower`: capacity ledgers, Thermal Caps, Exotic Caps and Taps, Fluid Pumps). Both start from the **network analysis** `ak(state)`, built on a **topology** `ese()`: pipes grouped by medium (gas, liquid), each segment sampled every 10 map units, union-find over the points, bridges; the analysis then adds fluid route assignments and which machine ports sit on which network.

Both are cached per state object (WeakMaps). The keys come from `JO()`, rebuilt as strings on every call:
- **`geometry`** (topology key): every outpost (id, position, under construction), every pipe (id, type, complete) and its segment end points, every gas/liquid bridge, and every machine's id, type, location, under construction and, for utility buildings, footprint/rotation.
- **`complete`** (analysis key): all of the above plus every fluid route assignment and, per machine, its `*_capacity` keys, its io connections, its **fluid types** (`stringData.fluid`, `gas_in_fluid`, `liquid_in_fluid`), and whether `gas_in_level`/`liquid_in_level` and, for tanks, the stored `level` are **above 1e-9**.

A changed `complete` re-runs the analysis; a changed `geometry` also rebuilds the topology.

## Rebuild cost

An empty tank does not keep its fluid: when its level reaches 0 the game clears `stringData.fluid` and the per-fluid port keys (`cse()`), and they come back as soon as fluid flows in. A tank whose consumers draw at least as much as flows in therefore toggles every tick between "oil, has content" and "no fluid, empty", and the analysis misses twice per tick (pre- and post-power).

Measured headless on the mid-late sample save (244 machines, 600 ticks each), FlowTransport ms per tick:
- nothing changes: 5.95;
- `bulk_liquid_reservoir_9` forced to flip between empty/no fluid and 0.2 t oil every tick: 6.93, about 1 ms per analysis miss, so about 2 ms per tick for a tank running dry;
- the same reservoir's location flipped every tick (topology rebuilt too): 23.18.

So a tank running dry is a minor CPU cost. A geometry change (building, deploying, moving) costs a full rebuild, which is rare. Item port rewiring (`input`/`output` `connect()`) changes `complete` only. A machine with a generic `gas_in`/`liquid_in` port (Refiner, Habitat) flips `complete` too when its input buffer reaches 0 every tick (inferred from the code).

`FluidPort.connections()` builds the `complete` string on every call (its connection index is cached under it), and re-runs the analysis while something flips. Prefer `connected_id()` on hot paths.

## What to do in game

- Keep pass-through tanks and reservoirs **buffered**: supply must exceed the draw, or the consumer is throttled below the supply. A tank that sits at a few units with in ≈ out starves every consumer on it.
- When the draw can exceed the supply, the consumer, not the tank, has to give way: batch it with hysteresis (stop at a low fill, restart at a higher one). Throughput is the same, set by the supply, but a reserve stays for the consumers that don't pause. Fluid-only Fabricator recipes (`craft_tar`) do this on their own ([production_logistics.md](../cheatsheet/production_logistics.md), "Fluid-only recipe"); the Oil Generator surplus burn already stops below 70 % ([power_fluids.md §1c-1](../cheatsheet/power_fluids.md)).
- Size consumers to the supply: count wells × rate against the sum of the always-on draws (Oil Generators on last resort, Fabricator recipes with oil plus items). Those don't pause, so if they alone exceed the supply the tank still runs dry.
- A buffer tank that only passes fluid through and is often empty is better removed from the line.
- A passive producer (Refiner, Liquifier, Steam Condenser) can feed a tank in another outpost that also feeds consumers over the same pipe: the tank fills and drains at the same time (see "Remote (pipe) connections" below). A tank in the producer's own outpost is still preferred, because a local link uses no pipe capacity.

## Headless runs

`run.mjs --sticky-fluids` (optional, off by default) patches the `complete` string (not the state): an empty machine keeps its last fluid type and the content flags are left out, so the cached analysis survives a tank running dry. It saves about 1 ms per tick (late save: FlowTransport 7.1 against 8.2 ms per tick); why it exists: [DESIGN_HISTORY.md §10b-1](../DESIGN_HISTORY.md). Safe for our scripts, which route by the static tank assignment in the Data Archive, not by what an empty tank last held. Not safe for a test about tanks switching fluid.

## Local vs remote tanks: source and sink roles

Fluid on a pipe follows the declared connections; earlier builds pooled all providers on a pipe component ([DESIGN_HISTORY.md §1c-5](../DESIGN_HISTORY.md)). Verified headless with the storage test below.

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

Docs wording, build e1986ce: the game docs for `gas_tank`/`liquid_tank` say `outflow_rate()` 0 also means "no valid route". The thermal-vent guide no longer says "a local target transfers directly": every vent target needs a completed pipe route, even a nearby one (see "Two separate transport paths": a map machine is its own anchor). Code behavior is unchanged; this is a docs clarification only. Same-anchor machine pairs above still transfer directly.

### Remote (pipe) connections

`Ex` builds, per pipe component, `sourceEndpointIds` (every machine that is the source of a route on it) and `sinkEndpointIds` (every route sink). `getFluidNetworkPlans` keeps a source only if it can supply the component's fluid (a tank needs its latched `stringData.fluid` to match, so an empty, unlatched tank is not a source) and a sink only if it can accept it.

Tanks and other passive sources are then moved by `redistributePerFluidNetworks` before power:
- **Edges are the declared pairs**: one edge per route (source → sink) on the component whose source and sink both passed the plan filter. Pump-type sources are skipped here.
- The flow is one max-flow over those edges, limited by each source's level, each sink's headroom and the component's capacity ledger. Fluid goes only from a source to the sinks it is connected to, never to another pair's sink on the same pipe.
- A tank that holds fluid is a sink too: a tank that is the sink of one route and the source of another on the same component fills and drains in the same tick. So tank → tank chains and relay tanks on a shared pipe work.
- An endpoint on several components of the same fluid has its level or headroom split between them first (see "Capacity ledgers" below).
- A component is `stalled` when a source holds fluid but no edge moved any, and `no_source` when no source holds fluid.

Pumps, Thermal Caps and Exotic Caps/Taps run after power in `routeSourceToTarget`. They follow their own declared routes (sink by `sinkMachineId`) and check only sink headroom and the ledgers.

### Storage outpost: one network or two

Headless test on a copy of the late save: three new outposts with one Large Liquid Tank each, a producer tank (1,000 t oil) connected to a storage tank, the storage tank connected to a consumer tank with 100 t room. Run 500 ticks, all scripts stopped.
- **Build e1986ce, one pipe network through all three**: storage filled to 900 t, the producer emptied into it, the consumer filled to 1,000 t within the first ticks. Storage filled and fed the consumer at the same time.
- **Build e1986ce, two pipe networks** (producer to storage, storage to consumer; both pipes enter the storage outpost but don't touch each other): same result.
- **Previous build, one pipe network**: storage held ~22 t and never filled; the producer stalled at 878 t once the consumer was full. Two networks were needed then.

So a storage outpost works on one shared pipe. Producers need no tank of their own: storage takes their output directly. Tank to tank links work too (a script can `connect()` a tank's `liquid_out` to another tank; ~24 t per tick on one pipe).

### Capacity ledgers and ordering

- Per component, per tick: `throughputLinks × pipe max` in total, and per endpoint `(pipe links it claims, min 1) × pipe max` on each side (`ensureNetworkCapacityLedgers`). The pipe max is the High Pressure value once unlocked.
- Order in a tick: direct connections, then passive pipe routes (pre-power), then caps, then pumps (post-power). The ledger is shared, so passive routes consume component capacity first and pumps get what is left.
- Pump-type sources on one component split the remaining capacity equally (`prepareScriptSourceFairness`). Within one source, sinks are filled in proportion to headroom, ordered by id.
- An endpoint on several components of the same fluid has its level or headroom split between them by requested share (`B0`).

### What this means for our scripts

- A relay or buffer tank works on one shared pipe: its in-pair and out-pair can both be cross-outpost on the same component.
- Fluid follows the declared pairs: a consumer gets fluid only from the machine its port is connected to, not from any other provider on the same pipe.
- A local connection does not compete for pipe capacity; prefer a same-outpost tank where one exists (`rank_own_outpost_first` in `fluid_routing.py` and `FluidOutputRouter(local_outpost_id=...)` already do).
- Several passive routes on one component can use up its capacity before pumps get their turn: a stalled pump may mean a full pipe ledger, not a full tank.
