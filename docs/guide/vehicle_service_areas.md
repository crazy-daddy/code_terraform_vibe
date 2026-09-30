# Guide: vehicle_service_areas

## Vehicle Proximity & Service

Ground vehicles use a forgiving service-area model. You do not need to land on one exact coordinate, but physical work requires the vehicle to be parked.

### The five terms

- **Near**, the vehicle is inside a machine or outpost service area. It may still be driving through.
- **Stopped**, live speed is zero. A dead battery can stop a vehicle without canceling its route.
- **Parked**, the vehicle is stationary with no powered movement command. A stationary vehicle with no drive energy counts as parked even if its throttle or route remains set. Rescue and charging holds also keep a vehicle parked. `self.nav.brake()` parks it immediately.
- **Docked**, the vehicle is parked inside the service area required by an outpost, machine, or station.
- **Connected**, an item endpoint, pipe, or power relationship has been configured. A connection does not prove that a vehicle is docked and does not move cargo by itself.

The short rule is: **get near, park, then perform physical work**.

### Service areas

Machine and outpost service areas include a **~2 m** margin, so continuous vehicle movement does not need exact floating-point coordinates. An outpost's full footprint is its common service area. A field machine uses its own position and service area. Being near an outpost never makes a field machine part of that outpost.

### Parking before service

```
x = 25
y = -10
self.nav.set_target(x, y)
self.nav.set_throttle(0.5)
while self.nav.get_distance_to(x, y) > 2:
  sleep(1)
self.nav.brake()
```

After `brake()`, cargo transfer, charging, and hardware service can use the matching service area. A timed cargo handoff keeps the vehicle parked until its handling cycle ends; movement commands return `busy` during that cycle.

`fleet.vehicles()` reports current activity separately from docking. `.status` can be `"moving"`, `"charging"`, `"drilling"`, or another activity. `.is_docked` means the ground vehicle was parked at an outpost when that snapshot was created; `.docked_at` gives that outpost id.

### Charging Stations

A parked vehicle is docked at one Vehicle Charging Station at a time. Every station inside an outpost covers the whole outpost, so when an outpost has several, the vehicle's own script picks one with `self.dock("charging_station_2")`. Without a choice, it uses the eligible station with the shortest distance to its station position or its outpost's center, with equal-distance ties broken alphabetically by station id. The choice lasts until the vehicle drives away. `self.current_station()` and the fleet ref's `.current_station` report the station.

Drones use explicit station docking. A drone at a field Mining Drill must have completed its route before it can load ore.

*Guide / Automation Systems*
