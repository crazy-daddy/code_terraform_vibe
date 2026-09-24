# Guide: power_networks

## Power Networks

### Overview

Completed power lines divide the planet into connected subnets. Every generator, consumer, and battery in one subnet shares that subnet's generation and stored energy. A subnet may run from generation, stored energy, or both; it does not require a local or currently active generator while battery energy remains.

### Physical topology

**Touching lines connect.** Power-line pieces join wherever their tile-aligned geometry touches. T-junctions and ordinary crossings form one subnet.

**Outposts expose power service footprints.** Every completed power component touching an outpost footprint joins that structure bus and therefore the same subnet. Every valid completed machine belonging to that outpost uses the same subnet automatically. Personnel distribution does not affect utility connectivity.

**Power Bridges cross without joining.** A Power Bridge connects along its own axis. A perpendicular ground-level power line passing under the middle tile remains a separate subnet.

**Lines have no direction, loss, or per-line watt limit.** Generation, storage, and demand are pooled across the connected subnet. Direction emerges from which machines generate and consume power.

**Incomplete work carries no power.** Blueprint ghosts and partially built pieces are visible planning state only. Machines with a missing or stale outpost location are invalid and receive no fallback power.

### Allocation and storage

Generation serves the subnet's complete live demand first. Powered conventional batteries form one capacity-weighted pool: they charge from surplus and discharge before Lightning Rod reserve. Lightning Rods never charge from ordinary grid surplus and are not included in the main battery Stored total.

There is no consumer priority or partial load shedding. If generation plus conventional batteries and Lightning reserve cannot fund the full live load for the current tick, every live consumer on that subnet pauses before work runs. Canceled work does not spend partial storage. If available energy covers the tick exactly, that tick completes and the next unfunded tick pauses the grid. Displayed W and Wh values may be rounded, but small internal charge and drain increments continue to accumulate.

### Building and recovery

Plan power lines and Power Bridges in Plan Mode or by using `construction_blueprint.plan_power_line()` and `construction_blueprint.plan_bridge()`, then have a Constructor-equipped Pioneer drive within interaction range of each job and call `self.constructor.execute(job.id)`. If a route is split by deconstruction, the surviving pieces immediately become separate subnets. Machines paused by an outage return together when live generation covers the full returning load, or when conventional batteries plus Lightning reserve hold one hour of the remaining deficit. Newly banked Lightning energy can recover a dark subnet directly. Manually powered-off machines do not join automatic recovery.

### Diagnosing a subnet

Use the Planet Map to follow highlighted connected pieces and the Power dashboard to compare generation, demand, and battery storage. Lightning Rod cards and their category total show the separate deep reserve. If a remote outpost is dark, verify that every intended wire piece and bridge is complete, that ground geometry touches both service footprints, and that the subnet has enough current generation or stored energy for its complete live load.

### Cross-references

- Infrastructure & Pipes, construction and bridge crossing rules
- Batteries, storage behavior
- Constructor Module, executing Planet Map jobs

*Guide / World & Infrastructure*
