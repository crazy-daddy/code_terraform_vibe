# Stand-ins

A focused headless run keeps one subsystem real and replaces the rest with something cheaper that still feeds and drains the target. This page is the design reference: the groups, each group's boundary, each mode's mechanism and the state it touches, and the status of the phased build-out. Code: [`standins.mjs`](../../devtools/simulation/headless/standins.mjs), [`stacks.mjs`](../../devtools/simulation/headless/stacks.mjs), [`passive.mjs`](../../devtools/simulation/headless/passive.mjs). Scenario format: [scenarios.md](scenarios.md). Fidelity numbers: [ab_results.md](ab_results.md).

## Two levels

- **Level 1** works on scripts and archive keys only: stop a group's scripts (`off`), park them (`park`), stop all but the needed generators (`trim`), or run a cheap Python script in the slot (`standin`, phase 1). Power, fluids and every machine stay real, so no simworker patch is needed and a game update cannot break it.
- **Level 2** patches the simworker: `scale` collapses N identical terraformers into one record (phase 2), `mover` moves items between stores in code instead of flying drones (phase 3). Faster, and dependent on the anchors in [anchors.md](anchors.md).

Both levels are reported in `summary.json` (`standins`), so a result always says what it verified.

## Groups

The registry is per machine type (`TYPES` in `standins.mjs`: `{typeId: {group, reason}}`); a group is the set of types with that name. Grouping follows the chain (who feeds whom), not what a machine looks like. A scenario's `assign` moves a type for one run.

| Group | Types | Boundary when off: produces / consumes |
| :--- | :--- | :--- |
| `terraforming` | temp_heater, heat_generator, oxygen_generator, pressure_generator | atmosphere (heat, O2, pressure) / power, `steam_in` and `water_in` (Mk III), fuel rods (Mk IV) |
| `power` | solar_generator, steam_turbine, oil_generator, reactor, oil_pump, water_pump, thermal_cap, steam_condenser, charging_station, fuel_assembler, lead_cask | grid power, steam, water, oil / oil, steam, water |
| `orchestrator` | automation and panel slots (`# ct-automation:` / `# ct-panel:` marker, or `automation_N` / `panel_N` ids) | `production.demand`, `power.shedded`, `cash.budget`, `script.parked`, `fleet.commission`, `build.jobs` / telemetry keys |
| `logistics` | drone_small/medium/large, drone_station (+medium, large), drone_service_station, pioneer, rover, supply_dock | items at outposts (`logistics.requests` served), ore at smelters, construction / `logistics.requests`, power |
| `factory` | smelter, fabricator, garbage_disposal, mining_drill (+industrial, heavy) | ingots, crafted items, kits / ore, ingots, `fabricator.orders`, `production.demand` |
| `plants` | harvester, crop_automator, scanner, sprinkler, grow_lamp, dispenser, seed_maker, plant_terraformer | forage, seeds, km² / seeds, water, salt, fertilizer |
| `biolab` | bio_lab, bio_collector, bio_exchange, bio_caster, bio_luminizer, bio_processor, bio_conditioner, dna_sequencer | samples, life-form items / reagents, power |
| `wildlife` | habitat, feed_maker, refiner, exotic_gas_cap, exotic_spring_tap | revived species, Insight / feed, refined fluids |
| `biomass` | essence_liquifier, biomass_mixer | biomass / essence |
| `weather` | weather_station | `weather.signals` / nothing |
| `system` | `boot`, `uplink`, `planet_*`, `contract_*` slots; the sensor and fixture machines (oxygen_sensor, pressure_sensor, thermometer, clock, gps, inventory) | never touched |

Why these groups (owner's calls, 2026-10-14): `seed_maker` and `plant_terraformer` behave like fabricators but only the harvester chain uses them, so they sit with `plants`; `refiner` and the exotic caps only serve wildlife; `supply_dock` ships orders, so it is logistics; `mining_drill` is the smelters' ore source once drills exist. The bio chain is split three ways because a test rarely needs all of it.

A machine's script slots come from `m.scriptSlots` (ids that exist in `state.scripts`). Slots no machine owns are matched by marker, id or system name; the rest go to `summary.standins.unclassified` (`strict: true` fails instead). An unowned slot that is not running (a recycled machine's old slot, e.g. `o2gen_51` after the generator was undeployed) is only counted (`orphans`).

## Modes

| Mode | Groups | Mechanism | Ghosts |
| :--- | :--- | :--- | :--- |
| `real` | all | nothing changes | 0 |
| `off` | all but `system` | `script.stop` for every running slot of the group (minus `keep`). The machines stay; a stopped machine draws no power (the game gates draw on a running script) and makes nothing. | scripts stopped |
| `park` | terraforming | `Parker` from `passive.mjs` on the group's types: the real scripts stay `waiting` and run a loop pass only on a trigger (waste, gauge window, new day, power or tier change, low feed, one-minute refresh). A/B in [../plans/headless_sim.md](../plans/headless_sim.md). | 0 |
| `trim` | power | Watches each subnet for `warmupTicks` (600): peak `consumed` and `generated` per running turbine or oil generator. Then keeps `k = max(keepMin, ceil(peak × margin / perGenerator))` generator scripts per subnet (lowest ids) and stops the rest. A generator without a running script makes no power and drains no steam or oil. Solar stays real (cheap, no fluid). | scripts stopped |
| `standin` | terraforming | Each running slot of a heater, O2 or pressure generator gets the type's Python stand-in from `standins/` (`sim.setScript`, same slot, so `self` binds): `heater.py`, `o2gen.py`, `pressure.py`. The harness runs the Mk III steam guard in JS every `guardTicks` (600): banked steam over every steam Gas Tank on the network (`data.level` / `data.capacity`, as `lib/power.py` `steam_pool()` reads it), guard closed below `stop` (0.50), open again at `start` (0.70), written to archive key `standin.terraforming` (`{heater_power: {id: W}, guard_off: [id], tick}`); `heaterPower` (a number for every heater, or `{id: W}`) overrides the learned setpoint. `keep` slots and idle slots stay as they are. | 0 (same script count) |
| `scale` | terraforming | Level 2, needs `features.scale` and `machineRevision` ([anchors.md](anchors.md)), else falls back to `standin` with a warning. Identical machines (type, `tier`, `tierUpgrade`, outpost, subnet, `ioConnections`; a running slot not in `keep`) collapse into records of at most `perRecord` (10) members: the members with the highest `*_in_level` survive, the others are undeployed with the game's own `machine.undeploy` (a refusal such as `cargo_present` or `inventory_full` keeps that member real) and the refunded kits and upgrade packs leave the Inventory again. Each survivor gets `data.scale = N`, so the patched worker does N machines' atmosphere output, fluid drain and power draw in one record; `max` (50) caps the scaled members per group, the rest stay real. Every machine left runs the `standin` script (same params). A record whose port level reads 0 at every check over 6,000 ticks warns once (`stalled`). | undeployed members' scripts |
| `mover` | logistics | Level 2 item mover: the group's running slots are stopped like `off` (haulers, drones, depots; Supply Docks that must stay real go in `keep`), and every `every` (100) ticks the harness serves `logistics.requests` in code: per destination and item, the ladder is walked from the highest band down, the deficit is the band's level minus the live store count (`stacks.mjs` `outpost:<id>`, never the entry's `have`) minus every fresh pickup bound for that outpost (any vehicle, as `in_flight()` sums them); the nearest other outpost by `planet.outposts[].x/y` gives what it holds above its own level at that band (or its `keep`), minus other vehicles' reservations; `buy: true` entries fall back to `sim.buy()` from the Inventory (source `shop`). Items leave the source at once and land at the destination after `loadTicks` (50) + 10 × distance / `speedMps` (12) ticks; a full store keeps the remainder queued and retries every pass. While in flight the trip is a pickup `pull:standin_mover:<dest>:<item>:<source>` = `{vehicle: "standin_mover", dest, source, item_id, units, tick, aboard: true}` (the `reserve_pickup()` shape), deleted on arrival. Stale requests (`REQUEST_STALE_TICKS`) and entries without a ladder are skipped; the stopped haulers' own pickups are dropped at setup (nothing else would release them for `PICKUP_STALE_TICKS`). No capacity, charge or weather: a throughput upper bound. | scripts stopped |
| `produce`, `cash` | plants | phase 4 | |

A planned mode named in a scenario fails validation with its phase.

## Virtual script count

The game grants each script `min(stepsPerTick, floor(totalStepsPerTick / N))` interpreter steps per tick, N = scripts in `running`, `waiting` or `flushing` status (cheatsheet dev_workflow §1d-1; the scheduler reads both numbers from its config object every tick). Stopping 70 scripts would hand the target 1,000 steps instead of the ~700 it has in the full base, which changes its timing. So before every tick the harness sets

```
config.interpreter.totalStepsPerTick = floor(base × n / (n + ghosts))
```

with `n` the real count and `ghosts` the scripts the stand-ins removed (each mode reports its own; a scenario's `ghosts` overrides a group). `sim.config` is the simworker's config object (bootstrap anchor `config` in `simhost.mjs`), so this needs no patch. `summary.standins.allowance` shows `{n, ghosts, steps}`. Parity check (0262 save, `--only-scripts harvester_1`, 71 ghosts): the harvester got 694 steps, the full base's value.

Rule of thumb for `ghosts` when a mode has no count of its own (owner, 2026-10-14): haulers 1.5 per outpost before drones, 1 per outpost with drones; extractor drones 2 per biome with life-form sites; miner Pioneers 3 per smelting outpost before any mining drill, 1.5 with drills, 0 with a large drill.

## Stores and flows

`stacks.mjs` reads and writes item stores in the raw state (a game command would notify the UI or drop overflow on the field):

| Store | State | Capacity |
| :--- | :--- | :--- |
| base Inventory | `state.inventory.slots`: `Array<{id, count} | null>` | one stack per slot, no unit cap in the state |
| store machines | `m.itemStacks: Array<{id, count}>` (`drone_station*`, vehicles) | `m.itemStacksCap` units in total, `m.itemStackSlots` distinct stacks |
| bin stores | `m.bins: {slot_i: {itemId, stacks: [{id, count}], capacity}}` (`warehouse`, `large_warehouse`, `storage_bin`) | per bin: `capacity` units; an empty bin takes any item, a holding bin only its own (its `itemId` resets when emptied), as the worker's bin add does |

`m.locationId` names the outpost (`outpost_home`, or absent, at home); `outpost:<id>` addresses that outpost's stores, the Inventory first at home. Fabricators and smelters also carry `itemStacks` but are not stores (their stock is work in progress).

Flows (`Flows` in `stacks.mjs`) run every 100 ticks (`keep`, `rate_h`; the latter keeps a fractional balance and moves whole units) and every tick (`after`, a queue of arrivals). Totals per flow go to `summary.standins.flows`.

## Phase status

| Phase | Content | Status |
| :--- | :--- | :--- |
| 0 | registry, scenario file and flags, `off`, `park`, `trim`, flows over any store, archive seeds, virtual script count, Node tests, this folder | done 2026-10-14; parity with the 306e188 `--only-scripts` run (identical metrics) |
| 1 | Level-1 Python stand-ins for heaters, O2 and pressure generators (`standins/*.py`, a JS steam guard writing `standin.terraforming`) | done 2026-10-14; A/B below |
| 2 | `scale`: one record per group of identical terraformers with `data.scale = N` (atmosphere output, fluid drain, power draw multiplied; `perRecord` split against fluid stall), `anchors.mjs` | done 2026-10-14; A/B in [ab_results.md](ab_results.md) |
| 3 | `mover`: direct item moves serving `logistics.requests`, with `logistics.pickups` bookkeeping so the real orchestrator sees one world | done 2026-10-14; A/B in [ab_results.md](ab_results.md) |
| 4 | plants `produce` (forage per hour from telemetry) and `cash`; off-stubs for orchestrator, wildlife, biomass; `buildorder_search.py --scenario` | open |
| 5 | A/B tables per mode, DESIGN_HISTORY entry | open |
| 6 | construction `instant`, power `topup` | optional |

### Design notes for the open phases

Facts below were read from the decompiled simworker on 2026-10-14 (build in `internals/` at that date); re-check line references with the anchors after a game update.

- **Terraforming Level 1 (`standin`, done)**: Python sources under `devtools/simulation/headless/standins/` (no `lib/` imports, game-interpreter rules of `CODE_GUIDES.md`; `ruff.toml` and `pyrightconfig.json` treat the folder as game code), deployed with `sim.setScript(slot, src, {run: true})`. O2: intake CO2 / 10, dump waste at 50, 1 s poll. Pressure: sync inside the window when unsynced, reset on gauge wrap, polls paced to the measured sweep speed like `PressureController`. Heater: power from `standin.terraforming` `heater_power[id]`, else `heat.optimal_setpoints[thermal_state]` (read, and written back after a 1-10 W sweep like `HeatController`), re-evaluated on a day or thermal-state change; `guard_off` makes a Mk III heater remember `steam_in.connected_id()`, `disconnect()`, and `connect()` it back when its id leaves the list. `_feed.py` (prepended to every stand-in by `standinSource()`) keeps a Mk III port fed: a port under 20 % of its capacity on two checks 5 s apart moves to the next candidate, tanks latched to the fluid first, then producers, own outpost first (the real `FluidInputRouter` with no reachability check, blacklist or pipe-conflict handling; POI pumps are not candidates). The Mk IV rod feed is not modelled (a Mk IV heater runs its magazine dry). The stand-in sources land in `final_save.json`: never load that save in game. Per-machine `waste`, `gauge`, `efficiency` do not matter for fidelity (owner: waste is deleted on dump, efficiency stays 100 % after the first gauge loops).
- **Terraforming Level 2 (`scale`, done)**: grouping and undeploy as in the Modes table; the kits are removed by diffing `state.inventory.slots` around `sim.undeploy()` (the command returns no item list; a kit may merge into an existing stack or take a free slot). Five simworker lines multiply by `data.scale ?? 1` (`SCALE_PATTERNS` in `anchors.mjs`, stable strings only, each exactly once or the feature is off): the AtmosphereSystem loops (O2 `Math.min(<output>, <atmosphere>.co2)`, heat `.heatUnits = <add>(<state>.planet.temperature.heatUnits, <output>)`, pressure `<atmosphere>.pressure = <add>(<atmosphere>.pressure, <output> * <dt>)`; the data local is the `let <data> = <machine>.data;` of the enclosing loop, found by looking back from the anchor), the fluid drain (`` `${<port>.portType}_level` `` two lines above `<port>.ratePerGameHour * <hours>`; the fuel-rod branch stays unscaled, so a Mk IV record burns one machine's rods) and the power draw (`return <base> * <tierFactor>(<machine>.data.tier ?? 1, <machine>.data.tierUpgrade ?? 0)`; the heater's dynamic `data.power` draw is inside `<base>`, so it scales too). The survivor keeps one running script, so the `scriptSlots.some(running)` gate needs no patch. Fluid stall: a port has one declared target and its own buffer and flow cap, so one record draining N machines' worth can run its port dry; `perRecord` splits the group into several records (same tank, separate ports), and `summary.standins.scale.minLevel` and `stalled` show whether that was enough. Grid shed is binary per subnet, so totals shed at the same moment as N real machines; the Python Power Guard loses per-id granularity. A save written with `data.scale` must not be loaded in game.
- **Logistics `mover`**: every `every` ticks read `logistics.requests` (`{outpost: {item: {levels, have, by, tick, buy?, keep?}}}`, `lib/logistics_requests.py`), drop stale entries, compute each outpost's deficit from the live store count (never from `have`: requesters do not republish on stock changes) minus in-flight units, take from the nearest outpost's surplus (or `sim.buy()` for `buy` entries), deliver after `loadTicks + 10 × distance / speedMps`. Write `logistics.pickups["pull:standin_mover:<dest>:<item>:<source>"] = {vehicle, dest, source, item_id, units, tick, aboard: true}` while in flight and delete it on arrival, so `in_flight()` caps over-asking and the real orchestrator sees one world. `drone.mission`, `drone.heli_free`, `depot.stage` are drone-only and stay untouched. The mover is a throughput upper bound (no capacity, charge or weather); never size a fleet from it.
- **Plants `produce` / `cash`**: `produce` turns `{forage_h, ...}` into flows into the Inventory (defaults from `plant.status` / `plant.automators` telemetry when the save has it, else the scenario states the rates); `cash` adds `creditsPerHour / 360` to `state.player.credits` every 100 ticks (early game only; later the harvester is a forage source, not a cash source).
- **Off-stubs** (phase 4, each to be confirmed against the reader before it is written): orchestrator off → `power.shedded: []`, a `cash.budget` record so `can_spend()` sees a fresh manager; wildlife off → `wildlife.plan = {}`; biomass off → `biomass.retire = {complete: false}`.
- **Power later**: `topup` (batteries to capacity every tick) once the battery storage field is identified; construction `instant` once `ConstructionSystem.tick` is read.
