# Guide: flow_networks_fluids

## Flow Networks, Fluids

### The complete mental model

Gas and liquid use the same transport model. Gas Pipes carry registered gases; Liquid Pipes carry registered liquids. Always answer three questions in order:

1. **Can the two locations reach each other?** Completed physical topology answers this.
2. **Which machines intend to exchange which exact substance?** `FluidPort.connect(...)` relationships answer this.
3. **How much can move now?** Supply, demand, power, throttle, buffer headroom, and shared throughput answer this.

A useful shorthand is: compatible connection + reachable topology + live supply + live demand = flow. The connection and topology establish identity. Live conditions only change the current `t/h` rate, so zero flow does not make a pipe neutral.

### What `connect()` means

Players connect machine ports to machines, never ports to pipe ids:

```
# Water Pump script
self.water_out.connect("bio_caster_1")

# Equivalent when written in the Bio Caster script
self.water_in.connect("water_pump_1")
```

Either side may declare the provider-consumer relationship, and only one side is required. The target can be a stable machine id or display name. The target must expose a compatible opposite-direction port: `water_out` matches `water_in` or generic `liquid_in`; `steam_in` matches `steam_out` or generic `gas_out`.

Each port stores one declared target. Calling `connect()` again on that port replaces its previous target. `result.status == "ok"` means the target exists and has a compatible port. It does not guarantee that a remote pipe is complete, that the source has supply, or that flow is nonzero.

`disconnect()` clears only the declaration owned by that port and leaves buffered fluid in place. `connected_to()` reports only the target declared by that port; it does not list reverse declarations made by peers. If both ends independently call `connect()` for the same pair, transport is deduplicated, but both declarations must be disconnected to remove the relationship completely.

There is no `connect_pipe`, `disconnect_pipe`, or `connected_pipe` API. Pipe ids are for construction and diagnostics.

### Local versus remote

Machines in the same completed outpost transfer directly after a compatible `connect()` call. They do not need a local pipe piece, but they still need the machine connection.

Machines at different locations need at least one completed conflict-free physical component of the correct medium reaching both location anchors. A map machine such as a Pump or Thermal Cap uses its own visible utility footprint. An internal machine uses its completed outpost footprint as its anchor.

A remote `connect()` call may produce `.status == "ok"` before the pipe exists. That records durable intent. Flow begins when suitable topology is complete. Cutting the pipe makes the route unreachable but does not erase the connection; restoring topology resumes it.

### Footprints expose availability, not storage

A pipe touching an outpost service footprint exposes that component to compatible connections owned by machines there. Personnel distribution does not change utility reachability. The outpost stores nothing, mixes nothing, and selects no source or tank automatically. Every local machine still needs an explicit `connect()` relationship.

Separate physical components touching the same outpost service footprint remain separate; footprint contact is an availability relation and never a fluid junction. This lets water, oil, and volcanic essence reach one outpost through independent liquid components without becoming one pool. A map readout listing several liquids means those identified components reach the footprint; it does not mean the liquids are mixed.

One remote relationship uses at most one physical component. An existing valid non-conflicting assignment is retained. A new relationship uses a component already carrying that exact fluid, or one neutral component. If exactly one component serves simultaneous different-fluid relationships, both connector claims conflict there. Independent components never combine capacity automatically.

### How a pipe gets exact contents

Pipe hardware establishes only `gas` or `liquid`. A completed physical component gets an exact substance only from complete compatible provider-consumer relationships assigned to that component.

- No connection: neutral.
- Provider present but unconnected: neutral.
- Consumer present but unconnected: neutral.
- One complete water connection: contents are `water`.
- Several water connections: compatible, they share supply and throughput.
- Water and oil relationships simultaneously have only one eligible component: both claims conflict and all flow on that component stops.
- Separately designated Water and Oil components are physically joined: conflict, all flow on the joined component stops.
- A water connection with throttle at zero, no power, no supply, or a full sink: contents remain `water`, live flow is zero.
- Remove the final complete connection: the component becomes neutral again.

The same rule applies to gases. A dormant Steam source still designates its component while its connection exists. If a new Ammonia relationship has only that Steam component, the overlapping connector claims conflict. If separately designated Steam and Ammonia components are physically joined, the joined component also conflicts even while both sources are idle.

If several components reach the same two anchors, each relationship selects only one. A second exact fluid can designate another neutral component without affecting the first. If exactly one component is eligible for both exact fluids, their simultaneous connector claims conflict on it. Independently assigned fluids also conflict if their pipe geometries are later physically joined.

### Physical joins

- Only completed pipe and bridge hardware transports fluid.
- Gas and liquid hardware never join.
- Same-medium ground pieces join wherever their real geometry touches.
- T shapes and ordinary ground crossings are real junctions.
- Components contacting one service footprint remain physically independent unless their own ground geometry touches.
- Deliberately building a real ordinary junction in the ground geometry joins the routes.
- A bridge joins its matching ramps along the bridge axis.
- A perpendicular ground line below the bridge's middle tile remains separate.

`Pipe.start()` and `Pipe.end()` report construction geometry only. They do not force live flow direction. Port direction, supply, and demand decide live movement.

### Tanks are explicit storage

An empty Gas Tank accepts any gas; an empty Liquid Tank accepts any liquid. Connecting an exact source to an empty tank establishes the route identity before delivery. The first exact fluid actually deposited latches the tank. It then accepts and provides only that fluid until it drains fully to zero and unlatches.

A tank is not inserted automatically by the outpost. A source-to-tank-to-consumer chain needs two relationships:

```
# Water Pump script, fill storage
self.water_out.connect("Water Reserve")
self.set_throttle(1.0)
```

```
# Consumer script, draw from storage
self.water_in.connect("Water Reserve")
```

The tank itself is passive and needs no control loop. Draining it to zero does not erase its port declarations. If it later latches to a different liquid or gas, an old incompatible declaration cannot flow and should be reconnected.

Two empty generic tanks connected only to each other remain neutral because neither side identifies an exact substance.

### One provider, several consumers

Each consumer can connect its own input to the same provider:

```
# Bio Caster script
self.water_in.connect("water_pump_1")

# Sprinkler script
self.water_in.connect("water_pump_1")

# Reactor script
self.water_in.connect("water_pump_1")
```

All three relationships participate. Available supply, destination headroom, and physical throughput are shared without list-order priority. Use separate tanks, topology, connection choices, or throttles when one consumer must have deliberate priority.

### Pipe throughput ceiling

Individual pipe pieces have no throughput capacity of their own. A physical component starts with **2,000 t/h** of shared throughput for each matched source-side and sink-side attachment link. The common layout with one source link and one sink link therefore starts at **2,000 t/h**. **High-Pressure Fluid Transport** research retrofits every completed and future Gas Pipe and Liquid Pipe attachment link to **6,000 t/h**. Pipe length and extra pieces within the same route do not reduce or increase that limit.

Every compatible relationship assigned to the component shares this budget. Multiple attachment links on both sides can raise aggregate capacity, but extra length or interior branches alone add nothing. One logical connection never pools independent components. Machine production, throttle, supply, consumer demand, and buffer headroom may set a lower live rate; stored bursts or several producers can still reach the ceiling.

### Reading the APIs

`FluidPort.level()` is tons buffered at that port. Some pass-through outputs, including Pumps, store nothing and therefore read **0**. `capacity()` is the port's buffer limit. `flow_rate()` is the current live rate in `t/h`; **0** can mean idle, starved, full, unreachable, conflicted, or merely waiting across the simulation timing boundary.

```
print(self.water_in.connected_to())
print(self.water_in.level(), self.water_in.capacity())
print(self.water_in.flow_rate())
```

Pipe diagnostics show the physical side:

```
for pipe in list_pipes():
    print(pipe.id, pipe.type(), pipe.contents(), pipe.state())
    print("rate", pipe.flow_rate())
    print("connections", pipe.connections())
    print("conflicts", pipe.conflicting_contents())
```

`type()` reports `"gas"` or `"liquid"`. `contents()` reports the exact established substance, or `None` while neutral or conflicted. Because both cases return `None`, check `state()` and `conflicting_contents()` too. `connections()` lists the complete logical routes using the component; the representative pipe id in each diagnostic row is not a connection handle.

### Troubleshooting zero flow

Check these in order:

1. Does the expected port's `connected_to()` show its own declaration?
2. Did the `connect()` result have `.status == "ok"` instead of `"not_found"` or `"incompatible"`?
3. For remote machines, is every intended pipe or bridge piece complete?
4. Does a component of the correct medium reach both anchors?
5. Does `Pipe.state()` report `"conflict"`?
6. Is the source powered, supplied, active, and throttled above zero?
7. Does the destination have headroom or current demand?
8. Is shared throughput already being consumed by other routes?

Stored fluid redistributes before power, so generators may use tank delivery in that power tick. Powered Pumps and Caps release after the grid check. Later processing may use that release in the same tick, but a generator uses newly pumped or capped fluid on the following power tick. A one-tick delay can therefore be normal.

### Invalid machine locations

A machine with a missing, stale, or unfinished outpost location fails closed. It does not borrow home connectivity. Outpost deconstruction should never leave such a machine behind; this rule prevents corrupted state from receiving hidden utility access.

### Cross-references

- Infrastructure & Pipes, construction, physical joins, and bridges
- `FluidPort`, exact API return values
- `Pipe`, physical diagnostics
- Thermal Vents, steam source behavior
- Wells, water and oil source behavior

*Guide / World & Infrastructure*

---
