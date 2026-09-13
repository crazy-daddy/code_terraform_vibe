# Component: fleet

> **Category:** Vehicles & Modules | **Component Name:** Fleet

**Returned by:** get_component("fleet")

### Related object types

- `DroneRef`
- `MobileUnitRef`
- `VehicleRef`

### Methods

##### `.vehicles()`

All owned ground vehicles as read-only `VehicleRef` snapshots. Use `.id` when passing a vehicle to station APIs; call `vehicles()` again for fresh ref fields, or `get_component(ref.id)` for the live vehicle API.

- **Returns** `list<VehicleRef>`

##### `.drones()`

All owned drones as read-only `DroneRef` snapshots. Use `.id` when passing a drone to station/recovery APIs; call `drones()` again for fresh ref fields, or `get_component(ref.id)` for the live drone API.

- **Returns** `list<DroneRef>`

##### `.mobile_units()`

All owned vehicles and drones in one snapshot list. Use `.category` to branch between `"vehicle"` and `"drone"`; re-query for fresh positions/status.

- **Returns** `list<MobileUnitRef>`

*Types / Fleet & Vehicles*
