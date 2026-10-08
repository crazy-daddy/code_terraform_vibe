# Guide: nuclear_power

## Nuclear power: uranium to electricity

A Reactor can supply up to **5,000 W**, but it needs a working fuel chain and steady cooling. Build that chain before relying on it to keep the rest of the base running.

### What you are building

The route is: **dust-storm aftermath, drone collection, Raw Uranium Lead Cask, Fuel Assembler, Fuel Rod Lead Cask, Reactor**. Ordinary storage supplies Lead Plates to the assembler, and a water connection cools the Reactor.

Research opens the machinery; Earth Orders provide important recipes. Nuclear Program unlocks the Reactor, while Fuel Assembler research opens the assembler. Check the order rewards for Lead Casks, Shield Plating and Fuel Rods. The Fuel Rod recipe comes from the Vestibule order that requests **12 Raw Uranium**. Owning the assembler does not grant every recipe it can make.

### Collect uranium and bring it back

Dust storms can leave Raw Uranium after they end. Decode the weather message to recover the coordinate, then send a drone there before the aftermath expires. Sonar does not find this supply. See `weather_overview` for receiving weather signals and recovering the location.

One successful `collect()` takes at most **5 units**. Without Shield Plating, each uranium collection adds **40 exposure**; at **100**, the drone scrambles. The collected cargo stays aboard. Shield Plating prevents that collection exposure, but halves Cargo Pod capacity and increases fuel burn **1.5×**. Plan room and range for the shielded trip, not the empty drone's usual trip.

Drone Service Stations handle decontamination and rescue. Do not wait for the third unshielded collection to discover that the drone needs help. The `drone` guide covers service and recovery.

### Keep hot cargo in Lead Casks

Raw Uranium and Fuel Rods are radioactive cargo. Ordinary Inventory, Storage Bins, Warehouses and Depot stockpiles are not their storage route. Use a **Lead Cask** and the compatible nuclear-machine ports. Drones move hot cargo directly through the outpost's Lead Cask, rather than stocking it in a Depot.

Use **two casks** near the assembler: one for incoming uranium and one for finished rods. A cask holds **100 units** and latches to one hot material at a time, so a cask still holding uranium cannot also receive rods. Lead Plates belong in ordinary local storage.

### Make the first rods

One Fuel Rod needs **4 Raw Uranium + 2 Lead Plates**, takes **6 h**, and draws **1,800 W** while crafting. Have solar, steam, oil or stored energy ready to support that first batch. A Reactor waiting for its first rod cannot power the assembler making it.

The assembler's input has one source connection at a time. Take uranium from its cask, reconnect to the local Lead Plate supply and take the plates. Select `"craft_fuel_rod"`, and keep its output clear by sending finished rods to the second cask. Transfers need Auto Feeders research. A full output or missing ingredient can stall the chain even when power is available.

The assembler can also make Nuclear Batteries after their recipe unlocks. Those are ordinary power-storage products, not Reactor fuel, and can go to compatible ordinary storage.

### Start the Reactor with both supplies ready

Connect the Reactor's input to the Fuel Rod cask and use `take(...)` to keep rods in its input buffer. It automatically starts the next buffered rod when the active one runs out. That does not pull replacements from the cask for you.

Connect `water_in` to a reachable water provider or Liquid Tank. The cooling loop consumes **0.5-1 t/h** while heating. Missing water pauses heating and fuel use until the supply returns. See `flow_networks` for local connections, remote pipes and explicit tank buffering.

`self.set_heat(...)` accepts **0-1**, but temperature responds gradually:

| Core temperature | What happens |
|---|---|
| Below 300 °C | No power output |
| 300-600 °C | Output rises to 50% |
| 600-900 °C | Output rises to 100% |
| 900-950 °C | Output falls as the core gets hotter |
| 950 °C | Shutdown and automatic cooling; recovery at 600 °C |

**More heat is not always more power.** Read `self.temperature()` and `self.power_output()` as you adjust. The core's internal condition changes every **12 h**, so a heat setting that worked earlier may need correction. Let the temperature respond between adjustments. The Reactor's Info tab explains how to build a controller that adapts to these changes and game speed.

If output disappears, read `self.status()` first: an empty fuel buffer, lost cooling and overheating need different fixes. Keep some backup power and a reserve of rods and water while you get the loop working.

*Guide / Tutorials*
