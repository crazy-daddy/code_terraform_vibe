# Guide: infrastructure_and_pipes

## Infrastructure & Pipes

### Overview

Infrastructure is physical hardware built on the Planet Map. Gas pipes carry gases and consume `gas_pipe_segment` items. Liquid pipes carry liquids and consume `liquid_pipe_segment` items. Hardware establishes only the medium; complete player-authored provider-consumer connections establish exact contents.

### Building a pipe

Plan Mode and `construction_blueprint.plan_pipe(...)` create tile-based Construction jobs. A Pioneer with a Constructor executes each job:

```
bpq = get_component("construction_blueprint")
bpq.plan_pipe("liquid", 0, 0, 80, 0)

for job in bpq.pending_constructions():
    if job.kind == "pipe":
        self.nav.set_target(job.position.x, job.position.y)
        self.nav.set_throttle(1)
        while self.nav.get_distance_to(job.position.x, job.position.y) > 2:
            pass
        self.nav.brake()
        build = self.constructor.execute(job.id)
        print(build.status, build.message)
```

Unbuilt pieces are ghosts and transport nothing.

### Physical topology

**Touching geometry connects.** Same-medium segments connect wherever their tile-aligned paths touch. Ordinary T and cross shapes are real junctions.

**Service-footprint contacts stay independent.** Two fluid components do not merge merely because both touch the same outpost. The outpost footprint exposes each component independently to connected local machines. This allows water, oil, and other routes to touch one outpost without becoming one physical network.

**Connections define contents.** Provider presence alone and consumer presence alone are neutral. Each complete compatible remote `connect()` relationship selects at most one physical component reaching both locations and establishes its exact fluid there, including while idle, full, powered off, or throttled to zero.

**Conflicts halt flow.** If exactly one component serves simultaneous water and oil relationships, both connector claims conflict and that component stops. Separately designated components produce the same conflict if their physical geometry is joined. The same applies to different gases. Same-fluid connections may share one component and its capacity.

**Machines do not connect to pipe ids.** Scripts connect providers and consumers. Local machines transfer directly; each remote relationship retains one valid non-conflicting completed physical component reaching both locations, or selects a same-fluid component, or failing that a neutral one. Independent components never pool capacity automatically.

**Bridges cross without joining.** Gas, liquid, and power bridges are 3-tile overpasses. Their own axis connects; a perpendicular line beneath the middle tile remains a different network.

### Throughput

**Throughput belongs to the component, not its segments.** Individual pipe segments have no capacity stat. The common layout with one source link and one sink link starts at **2,000 t/h**, shared by every compatible relationship assigned to that component. **High-Pressure Fluid Transport** research retrofits every completed and future Gas Pipe and Liquid Pipe attachment link to **6,000 t/h**. Pipe length and extra pieces within the same route do not reduce or increase the limit. Multiple attachment links on both sides can raise aggregate capacity, while machine rates, throttle, supply, demand, and headroom may impose a lower live rate.

### Inspecting pipes

```
for pipe in list_pipes():
    print(pipe.id, pipe.type(), pipe.contents(), pipe.state())
    print("connections", pipe.connections())
    print("conflicts", pipe.conflicting_contents())
```

These pipe ids are inspection and construction identities, not player fluid-port handles. On the Planet Map, flowing networks use the exact fluid color, stalled networks are amber, and conflicts are red.

### Materials and recovery

Pipe segment cost is based on route length, approximately one segment per 10 meters. If construction pauses, query `get_component("construction_blueprint").paused_constructions()` and execute the same job again within range. Splitting or removing a route recomputes physical reachability immediately while preserving player-authored machine connection intent.

### Cross-references

- Flow Networks, transport, throughput, and backpressure behavior
- Power Networks, wire topology and power bridges
- Constructor Module, `self.constructor.execute(...)`
- Construction Blueprint, script-side planning
- Thermal Vents and Wells, physical producers

*Guide / World & Infrastructure*

---

## Thermal Vents

### Overview

A **thermal vent** is a fracture in the planet's crust where internal heat leaks through as steam. Vents are discovered by sonar and harvested by placing a Thermal Cap blueprint on them. Each vent cycles between active and dormant phases.

### Discovery

`self.sonar.scan()` returns `SonarScanResult`. When `.status == "ok"`, iterate `.sites` and select contacts whose `kind() == "thermal"`; `.message` explains any rejected scan. Survey the selected contact with `self.sonar.survey(site)` and read the `SurveyResult.site` payload only after its status is `"ok"`. Basic Sonar reveals phase, Wide adds steam rates, and Deep adds cycle timing.

### Harvesting steam

Plan a Thermal Cap on the vent, carry its kit in the Pioneer, and execute the queued blueprint with the Constructor. The completed cap captures steam into its chamber while powered.

### Routing after capture

Nothing leaves until the cap script calls `self.steam_out.connect(...)` with a compatible consumer's stable machine id or display name and opens it with `self.set_throttle(value)`, where `value` is **0-1**. A local target transfers directly. A remote target uses completed gas topology between the cap and target locations automatically; scripts never select an individual pipe. The complete connection establishes steam identity even before flow starts and keeps it while idle, full, off, or throttled to zero.

Under-release and the chamber climbs. At **100%** it overpressurizes and blows off the whole chamber, then refills from empty. Read `pressure()`, `is_overpressured()`, and `is_stalled()` to control release, add storage, or restore physical reachability.

### Cross-references

- Flow Networks, what happens after capture
- Infrastructure & Pipes, physical routing
- Construction Blueprint, queued build work

*Guide / World & Infrastructure*

---

## Water & Oil Wells

### Overview

The planet has deterministic **water wells** and **oil wells**. Water is steady; oil pulses between active and dormant phases.

Water wells produce **10 / 20 / 30 t/h** by yield tier. Active oil wells produce **8 / 16 / 24 t/h** and **0** while dormant.

### Reading wells in scripts

```
scan = self.sonar.scan()
if scan.status == "ok":
  for contact in scan.sites:
    if contact.kind() == "water" or contact.kind() == "oil":
      survey = self.sonar.survey(contact)
      if survey.status == "ok":
        site = survey.site
        print(site.id, site.kind(), site.yield_tier(), site.flow_rate())
      else:
        print(survey.message)
else:
  print(scan.message)
```

`scan()` returns `SonarScanResult`; `survey()` returns `SurveyResult`. Their payload fields are available only for the appropriate `.status`.

A deployed Pump starts at throttle **0**. Connect its output port, check the connection `ActionResult`, then set throttle. Local targets transfer directly; remote targets use a completed Liquid Pipe route. A Pump exposes its bound well through the read-only `well()` query.

*Guide / Reference*

---

## Tier 3 Progression

### Overview

Tier 3 introduces **input-gated** upgrades. A supplied Mk III Oxygen or Pressure Generator runs at **200x** Mk I output, while a supplied Mk III Heat Generator runs at **208x**. Starved machines fall back to their Mk II base output, **5x** for Oxygen and Pressure or **4.7x** for Heat.

The gate is enforced per tick: every frame the machine checks its input buffer. If the required fluid is unavailable, `is_degraded()` reads `True` and `effective_tier()` falls back to the previous tier for that tick. The installed tier reported by `tier()` itself never changes.

### The three Mk III packs

Each pack adds a required fluid port and consumption rate:

- **Oxygen Mk III**, `water_in`, **8 t/h**
- **Heat Mk III**, `steam_in`, **12 t/h** (direct steam, not water)
- **Pressure Mk III**, `water_in`, **5 t/h**

After applying a pack, the machine gains the corresponding port:

```
oxy = get_component("o2gen_1")
oxy.water_in.connect("liquid_tank_1")
print(oxy.water_in.level(), "/", oxy.water_in.capacity())
```

### Degradation signals

- `machine.is_degraded()` returns `True`.
- `machine.effective_tier()` returns one less than `machine.tier()`, the tier actually in effect right now.
- `machine.tier()` itself never changes, the pack is permanent; degradation is runtime.

When the input buffer refills, all of the above flip back on the next tick.

### Contention

Early water comes from **Water Pumps on wells** (a well yields **10 / 20 / 30 t/h** by tier). Your downstream consumers at full Mk III:

- 1 Oxygen Mk III at full rate consumes 8 t/h of water.
- 1 Pressure Mk III consumes 5 t/h of water.
- Combined at full rate: 13 t/h of water.

A single standard well (10 t/h) can't feed both at once. Your options:

1. Tap a **richer well** (rich / pure yield 20 / 30 t/h) or add a **second well** with its own pump.
2. Buffer with a **Liquid Tank** so short demand spikes draw from storage.
3. Allocate via script, prioritize whichever Mk III matters more right now, let the other degrade to Mk II temporarily.
4. After **Steam Condensation** unlocks at 1,000,000 Plants, route stored vent steam through a **Steam Condenser** for another 250 t/h Water at full throttle.

### Allocation script

A water allocator runs forever and decides which Mk III gets fresh water based on terraforming progress:

```
o2_tank = get_component("liquid_tank_1")
oxy = get_component("o2gen_1")
pres = get_component("pressure_1")
atmo = get_component("atmosphere")

while True:
  # Prioritize whichever pillar has the larger gap to next phase
  oxy_gap = ...  # compute from atmo.oxygen and next phase threshold
  pres_gap = ...
  if oxy_gap > pres_gap:
    # Favor oxygen, route the current water supply to its tank first
    ...
```

Choose the allocation rule that matches your current terraforming goal. Add `sleep()` only if you intentionally want a slower allocator cadence.

### Heat is different

Heat Mk III takes steam **directly**, not water. Captured steam can feed any combination of three sinks:

- A **Steam Turbine** for grid power.
- **Heat Gen Mk III** for maximum heat output.
- A **Steam Condenser** for clean water used by Oxygen, Pressure, Plants, and other consumers.

One vent may supply several connected sinks when its average output and stored reserve can cover them. Reachable consumers share available flow; their throttle, demand, and buffer headroom determine what they accept. Gas Tanks are the practical way to bank active-phase steam and carry every branch through dormancy. Condenser-fed Oxygen and Pressure therefore compete indirectly with turbines and Heat for the same captured steam.

### Graceful fallback

Degradation is a normal running state. The machine doesn't stop; output continues at the previous tier until the input buffer refills. Scripts can observe `is_degraded()`, inspect the input port, and correct the supply chain.

### Cross-references

- Flow Networks, the input system Mk III uses
- Thermal Vents, steam capture, storage, power, and condensation

*Guide / World & Infrastructure*

---
