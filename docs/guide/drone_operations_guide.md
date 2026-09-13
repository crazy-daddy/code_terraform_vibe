# Guide: drone_operations_guide

## Drones

### Overview

Drones are aerial logistics and field-work units. Every drone can use `self.go_to(x, y)` from the beginning; specialist modules determine what it can do when it arrives, not whether coordinate flight exists. Electric drones use Battery Packs and trade speed for range. Heli drones use Oil Tanks and fly much faster. Cargo Pods add single-material storage.

### Blueprint unlocks and deployment

**Basic Drone Operations** opens the system. Hardware recipes come through Earth Orders. Fabricate a Drone Depot Kit and deploy it into an outpost. Keep each fabricated chassis in Inventory, select its item card, and use **Deploy** to commission it into a free Depot bay. Once the drone is docked, mount its thruster, energy storage, and role modules through that drone's service controls. Commissioning and empty-rig module installation are service orders; do not freight the chassis or modules into the Depot stockpile.

Drone Depots commission chassis and handle local cargo. Drone Service Stations charge electric drones, refuel heli drones from `oil_in`, decontaminate working docked drones by **10 exposure per hour**, and rescue stalled or scrambled drones.

### Field work

Ground Rover/Pioneer Sonar discovers mineral sites, vents, wells, and exotic deposits. Portable Bio Scanners and Extractors handle permanent biological coordinates. Weather aftermath collection uses the same coordinate flight and `collect()` interface; the Weather DOCS define the information available to your programs.

`collect()` finds only a live aftermath at the drone's exact coordinate. Wrong, nearby, expired, and exhausted targets return `nothing_here` without a direction clue. Storm Glass is ordinary cargo. Raw Uranium is hot cargo: one call takes at most **5**, adds **40 exposure** without Shield Plating or **0** with it, and remains in cargo if that batch scrambles the drone at 100. Plating also halves Cargo Pod capacity and raises fuel burn **1.5×**.

### Reading the Fleet

```
fleet = get_component("fleet")
for drone in fleet.drones():
    print(drone.id, drone.name, drone.status, drone.battery_level, drone.oil_level)
```

Use stable ids when passing a drone to station and recovery APIs. Use `self.cargo.space_for(item_id)` before a harvest or transfer, and route through service stations before fuel, oil, or exposure becomes a problem.

### Cross-references

- Weather, programmable signals and aftermath collection
- Biosphere / Biomass, Portable Bio Scanner and Extractor work
- Drone Depot and Drone Service Station component APIs
- Orders, the source of drone blueprint rewards
- Flow Networks and Refinement, oil supply for heli drones

*Guide / Production & Logistics*

---
