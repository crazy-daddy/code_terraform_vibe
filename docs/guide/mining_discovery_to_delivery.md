# Guide: mining_discovery_to_delivery

## Mining: from discovery to delivery

Finding a deposit is the first step. To turn it into useful supplies, you need a drill that can cut it, somewhere for the ore to go, and a way to bring that ore to your machines.

### Start with a surveyed site

Use sonar to find a mineral contact, then survey it. A `MiningSite` tells you the mineral, its hardness and its purity. See `sonar_guide` for choosing sonar and working through blocked contacts.

**Sonar and drills have separate hardness limits.** Better sonar can show you Titanium while your starter drill still cannot mine it. Check both before sending a vehicle on a long trip.

| Hardness limit | Vehicle drill | Stationary Mining Drill |
|---|---|---|
| 1 | Basic Drill Module | Mk I |
| 3 | Industrial Drill | Mk II |
| 4 | Heavy Drill | Mk III |

Each tier handles everything below its limit. Hardness 1 covers Iron and Silicon; hardness 3 also covers Titanium, Cobalt, Lead and Rare Earth; hardness 4 adds Neutronium. The Rover takes the basic drill. The advanced vehicle drills need a Pioneer's universal slot.

### Take a vehicle, or leave a drill there?

**A Rover or Pioneer mines into its own cargo.** Mount the right Drill Module, drive to the surveyed deposit, brake, and call `self.drill.mine()`. Each successful dig adds one unit. You need enough charge to finish the dig and cargo space for that mineral. This is a useful way to bring home your first batches without building field infrastructure.

**A stationary Mining Drill keeps extracting while powered.** Fabricate its kit after earning the recipe, place a blueprint on the surveyed site, and have a Constructor-equipped Pioneer bring the kit and build it. Connect it to a working power network. Ore collects in the drill's own stockpile, so the vehicle that built it can leave.

The stationary drill needs no repeated dig command. Its script can inspect output, but collection is the carrier's job. See `plan_mode` for construction and `power_networks` for supplying field machines.

### Purity changes the trip

A rich site mines **2×** as fast as a standard site; a pure site mines **3×** as fast. Higher vehicle drill tiers also finish sooner, but draw more power while digging. A faster drill can therefore use more energy per unit. The worked time and energy comparison is in `batteries`.

For a vehicle, budget for **the outward trip, the ore you want to dig, and the return trip**. More cargo space does not help if the battery runs out before you get home. On a Pioneer, bins latch to one material each, so check space for the particular ore you are collecting, not just total empty capacity.

### Bring the ore home

A field drill's output is **pickup-only**. It does not send ore through a pipe or directly to Inventory. When the stockpile fills, extraction pauses until a carrier makes room.

- A Rover or Pioneer parks at the drill, connects its own input to the drill and takes ore. Automated item transfers need Auto Feeders research.
- A drone completes `go_to_drill(...)`, loads through `cargo.load(...)`, and carries the ore back to a Drone Depot.
- At the destination, unload into home Inventory or compatible local storage. Remote factories need the ore delivered to their own outpost.

Start with one deposit, one carrier and one destination. Make that route work before adding more drills. See `remote_logistics` for the delivery rules and `drone` for aerial carriers.

### When mining stops

Check the full route: surveyed deposit, compatible drill, power or vehicle charge, free cargo or stockpile space, then destination capacity. A stationary drill that reports zero extraction may simply be full. A vehicle beside a site may still be moving; brake before mining or loading. If ore reaches storage but your Smelter sits idle, check its recipe and input transfers next. See `refinement` for the first processing loop.

*Guide / Tutorials*
