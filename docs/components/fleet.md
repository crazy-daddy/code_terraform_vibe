# Component: fleet

> **Category:** Vehicles & Modules | **Component Name:** Fleet

Read-only index of every owned mobile unit: ground vehicles and drones. Use it for dashboards, charging scripts, rescue thresholds, and dispatch decisions without hardcoding names. Fleet refs are snapshots; control still goes through the unit's own script or the relevant station API.

**Access via:** `get_component("fleet")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.vehicles() → list[VehicleRef]`

All owned ground vehicles as `VehicleRef` snapshots. Each ref includes `.id`, `.name`, `.kind`, `.x`, `.y`, `.battery_level`, `.is_docked`, `.current_station`, `.is_being_rescued`, and `.rescue_status`.

- **Returns** `list[VehicleRef]`. Snapshots. Re-query for fresh positions and status, or use `get_component(ref.id)` for the live vehicle API.

##### `.drones() → list[DroneRef]`

All owned drones as `DroneRef` snapshots. Each ref includes `.id`, `.name`, `.kind`, `.engine`, `.current_station`, `.battery_level` or `.oil_level`, `.is_docked`, `.is_being_rescued`, and `.rescue_status`.

- **Returns** `list[DroneRef]`. Snapshots. Re-query for fresh positions and status, or use `get_component(ref.id)` for the live drone API.

##### `.mobile_units() → list[MobileUnitRef]`

All owned ground vehicles and drones in one list. Use `.category` to branch between `"vehicle"` and `"drone"`.

- **Returns** `list[MobileUnitRef]`. Snapshots. Re-query for fresh positions and status.

*Components / Vehicles & Modules*
