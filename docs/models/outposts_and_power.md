# Models: Outpost, Building & Power Grid Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `BuildingRef`

```python
class BuildingRef:
    """outpost.buildings() / outpost_network.outposts()[i].buildings()"""
    id: _str
    name: _str
    type_id: _str
    outpost_id: _str
    outpost: OutpostRef | None
    powered: _bool
    position: _list[_float]
```

## `Computer`

```python
class Computer(Component):
    """Ship Computer: Manages the hardware roster: deploy a machine, vehicle, or drone from Inventory into an outpost, remove one back to Inventory, decommission an emptied outpost, and rename anything you own. These are the Inventory page's Deploy button and the Computer's System tab, reached from a script. Every call needs Ship Computer research; the buttons themselves keep working before it."""
    name: _str
    def deploy(self, item_id: _str, outpost: _str | Outpost | None = ...) -> ComputerDeployResult[Literal["ok", "no_kit", "locked", "not_deployable", "deploy_limit", "location_not_found", "wrong_biome_for_machine", "duplicate_outpost_machine", "missing_drone_station", "drone_station_full"]]:
        """Deploy one unit of an inventory item into an outpost, defaulting to home. The machine lands with no script and does nothing until you attach one, exactly as a hand-placed machine does. A machine that the outpost's subnet cannot yet carry lands powered off. Fixed result contract: `ComputerDeployResult`; branch on `.status` and read `.message`. Payload fields: `.machine_id`."""
        ...
    def undeploy(self, machine: _str | Component) -> ActionResult[Literal["ok", "locked", "not_found", "not_undeployable", "self_target", "cargo_present", "docked_drone", "construction_dependency", "inventory_full"]]:
        """Remove a deployed machine, vehicle, or drone and return its kit, mounted modules, contained items, and tier upgrade packs to Inventory. Stored cargo blocks removal, so empty it first. Authored scripts survive as detached records. Field equipment is recovered by its Harvester and map structures by a Pioneer, not here. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def decommission(self, outpost: _str | Outpost) -> ActionResult[Literal["ok", "locked", "not_found", "is_home", "not_empty", "construction_dependency", "inventory_full"]]:
        """Remove a founded outpost and return its Outpost Kit to Inventory. The outpost must hold no machines; nothing is cascade-destroyed. Pipes, power lines, and bridges that touched it stay on the map for a Pioneer to reclaim. The home outpost is permanent. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def rename(self, target: _str | Component | Outpost, name: _str) -> ActionResult[Literal["ok", "locked", "not_found", "name_empty", "name_too_long", "name_taken"]]:
        """Set the display name of a machine or outpost. Names are unique across every machine, outpost, and panel. Ids never change, so saved references keep working. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
```

## `ComputerDeployResult`

```python
class ComputerDeployResult(Generic[_StatusT]):
    """computer.deploy()"""
    status: _StatusT
    message: _str
    machine_id: _str
```

## `Fleet`

```python
class Fleet:
    """get_component(\"fleet\")"""
    def vehicles(self) -> _list[VehicleRef]:
        """All owned ground vehicles as read-only `VehicleRef` snapshots. Use `.id` when passing a vehicle to station APIs; call `vehicles()` again for fresh ref fields, or `get_component(ref.id)` for the live vehicle API."""
        ...
    def drones(self) -> _list[DroneRef]:
        """All owned drones as read-only `DroneRef` snapshots. Use `.id` when passing a drone to station/recovery APIs; call `drones()` again for fresh ref fields, or `get_component(ref.id)` for the live drone API."""
        ...
    def mobile_units(self) -> _list[MobileUnitRef]:
        """All owned vehicles and drones in one snapshot list. Use `.category` to branch between `\"vehicle\"` and `\"drone\"`; re-query for fresh positions/status."""
        ...
```

## `FleetComponent`

```python
class FleetComponent(Component):
    """Fleet: Read-only index of every owned mobile unit: ground vehicles and drones. Use it for dashboards, charging scripts, rescue thresholds, and dispatch decisions without hardcoding names. Fleet refs are snapshots; control still goes through the unit's own script or the relevant station API."""
    name: _str
    def vehicles(self) -> _list[VehicleRef]:
        """All owned ground vehicles as `VehicleRef` snapshots. Each ref includes `.id`, `.name`, `.kind`, `.x`, `.y`, `.battery_level`, `.is_docked`, `.is_being_rescued`, and `.rescue_status`."""
        ...
    def drones(self) -> _list[DroneRef]:
        """All owned drones as `DroneRef` snapshots. Each ref includes `.id`, `.name`, `.kind`, `.engine`, `.current_station`, `.battery_level` or `.oil_level`, `.is_docked`, `.is_being_rescued`, and `.rescue_status`."""
        ...
    def mobile_units(self) -> _list[MobileUnitRef]:
        """All owned ground vehicles and drones in one list. Use `.category` to branch between `\"vehicle\"` and `\"drone\"`."""
        ...
```

## `LatticeGrid`

```python
class LatticeGrid:
    """.grid"""
    def width(self) -> _int:
        """The grid width in cells (32)."""
        ...
    def height(self) -> _int:
        """The grid height in cells (32)."""
        ...
    def start(self) -> _list[_int]:
        """A guaranteed-clear foothold cell, returned as `[x, y]`. Probe it first to get a reading and begin the deduction."""
        ...
    def reset(self) -> ActionResult[Literal["ok"]]:
        """Clear a tripped fault so probing can continue in the same script run. The hidden board and guaranteed-clear starting cell do not change. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
    def probe(self, x: _int, y: _int) -> LatticeProbeResult[Literal["ok", "node_tripped", "lattice_tripped"]]:
        """Probe a proven clear whole-number cell. The reading is the whole-number count of neighboring volatile nodes in the **0-8** range. Tripping a node faults the lattice until `reset()` is called. Wrong argument types raise `TypeError`; fractional, non-finite, or out-of-bounds coordinates raise `ValueError` without tripping an intact lattice. Fixed result contract: `LatticeProbeResult`; branch on `.status` and read `.message`. Payload fields: `.reading`."""
        ...
```

## `Nocturna`

```python
class Nocturna(Component):
    """Nocturna: Provides stable planet-wide data for Nocturna through `get_component(\"nocturna\")`, including map bounds, biomes, terraforming progress, and permanent map contacts. Hidden weather aftermaths are deliberately absent; their coordinates exist only in the storm packets your station network captures. Sonar discoveries and surveys are stored separately in `get_component(\"journal\")`."""
    name: _str
    def get_name(self) -> _str:
        """Display name of this planet, returns `\"Nocturna\"`. Safe to hardcode, but querying future-proofs scripts against rename or multi-planet expansion."""
        ...
    def get_bounds(self) -> Bounds:
        """Surface coordinate bounds as a `Bounds` object with `.min_x`, `.max_x`, `.min_y`, `.max_y`, all in meters from base. Use to clamp nav targets inside the operational surface, or to generate random valid coordinates: `import random; b = planet.get_bounds(); x = random.randint(b.min_x, b.max_x); y = random.randint(b.min_y, b.max_y)`. See `Bounds`."""
        ...
    def contains(self, x: _float, y: _float) -> _bool:
        """`True` if the point `(x, y)` is inside Nocturna's surface bounds. Use as a safety check before `nav.set_target()`: `if nocturna.contains(x, y): self.nav.set_target(x, y)`. Targeting outside the bounds returns immediately with no drive."""
        ...
    def biome_at(self, x: _float, y: _float) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]:
        """Biome id at the world coordinate `(x, y)`. Returns one of `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"`, `\"deep\"`. Pure geography, same answer for the same coordinate forever. Use to script biome-aware behavior anywhere on the planet: `if nocturna.biome_at(x, y) == \"volcanic\": deploy_heat_resistant()`."""
        ...
    def life_form_biome(self, item_id: _str) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None:
        """Find the native biome for a life-form item: `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"`, or `\"deep\"`. Returns `None` for other items. A species always belongs to the same biome, regardless of where the specimen was found. Essence Liquifiers accept only life forms native to their outpost, so a drone can test `nocturna.life_form_biome(item) == self.outpost.biome` before unloading."""
        ...
    def biomes(self) -> _list[_str]:
        """Lists every biome id on the planet. Use it for planet-wide loops: `for biome in nocturna.biomes(): print(biome)`. The set never changes during play."""
        ...
    def terraform_progress(self) -> _float:
        """Terraform Index progress on a **0-100%** scale: **0** is untouched; **100** means 1,000,000 TP and all six pillars are complete. Atmosphere owns 70% of the Index; biomass, plants, and wildlife each own a separate 10% that cannot substitute for another pillar. Gate progress logic with it: `if nocturna.terraform_progress() >= 50: ...`. For the raw TP value, use `total_tp()`."""
        ...
    def total_tp(self) -> _float:
        """The finite Terraform Index in TP, in the **0-1,000,000** range. Temperature, oxygen, and pressure together own 700,000 TP; biomass, plants, and wildlife each own a non-substitutable 100,000 TP. Raw metrics may keep growing after their final phase, but a completed pillar contributes no additional Index. The value gates cross-system research."""
        ...
    def points_of_interest(self) -> _list[PointOfInterest]:
        """Lists every permanent \"?\" contact on the Planet Map so scripts can route to real sites. Each `PointOfInterest` has whole-number coordinates, a `scanned` flag, and a `kind` that stays `\"unknown\"` until a scanner reaches the contact. Filter for `not point.scanned`, travel to its coordinates, and scan with Rover or Pioneer sonar or a drone Bio Scanner. A contact the instrument you brought cannot identify stays unscanned even after a sweep that succeeded, and the sweep lists it in `scan.blocked` with the same coordinates and a reason: record those or your loop reselects the same contact. See `PointOfInterest`."""
        ...
```

## `Outpost`

```python
class Outpost:
    """get_component(outpost_id) / get_component_by_name(outpost_name)"""
    id: _str
    def name(self) -> _str:
        """Display name. Defaults to `\"Nocturna Base\"` for the home outpost or a generated `\"Outpost N\"` name for founded outposts; freely renameable from the Computer System tab. Mutable: prefer `id` when persistence matters."""
        ...
    def coords(self) -> _list[_int]:
        """World coordinates of the outpost anchor as `[x, y]`. Home outpost sits at `[0, 0]`; founded outposts carry the position chosen in Plan mode."""
        ...
    def buildings_used(self) -> _int:
        """Number of buildings deployed at this outpost. Sensors, mobile units, structural hubs, and POI extraction don't count."""
        ...
    def buildings_capacity(self) -> _int:
        """Soft building threshold at this outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; founded outposts use the standard threshold."""
        ...
    def is_full(self) -> _bool:
        """Returns `True` when this outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment."""
        ...
    def is_home(self) -> _bool:
        """Returns `True` when this is the home outpost (default name `\"Nocturna Base\"`)."""
        ...
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `\"storage_bin\"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads."""
        ...
```

## `OutpostComponent`

```python
class OutpostComponent(Component):
    """Outpost: Represents a home or player-founded outpost. Look one up by stable id with `get_component(\"outpost_1\")` or by display name with `get_component_by_name(\"Mining Camp\")`. Players can rename outposts from the Computer System tab, so use the id for scripts that must survive renames."""
    def name(self) -> _str:
        """Display name. The home outpost starts as `\"Nocturna Base\"`; player-founded outposts start as `\"Outpost N\"`. Freely renameable from the Computer System tab. Mutable, prefer `id` for stable references."""
        ...
    def coords(self) -> _list[_int]:
        """World coordinates as `[x, y]`. Home outpost sits at `[0, 0]`."""
        ...
    def buildings_used(self) -> _int:
        """Number of buildings deployed at this outpost. Sensors, mobile units, structural hubs, and POI extraction don't count."""
        ...
    def buildings_capacity(self) -> _int:
        """Soft building threshold at this outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; player-founded outposts use the standard threshold."""
        ...
    def is_full(self) -> _bool:
        """Returns `True` when this outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment."""
        ...
    def is_home(self) -> _bool:
        """Returns `True` when this is the home outpost."""
        ...
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Lists buildings deployed at this outpost as `BuildingRef` snapshots. Call `self.outpost.buildings()` for all of them or pass a building `type_id` to filter. Each ref has `.id`, `.name`, `.type_id`, `.outpost`, `.powered`, and `.position`; use `get_component(ref.id)` for type-specific live reads. The list covers machines that count toward building capacity, not sensors, mobile units, POI extraction, or fixed Harvesting-field machines. Use `harvesting_machines()` for those field machines."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Lists fixed machines deployed on this outpost's Harvesting field as `HarvestingMachineRef` snapshots. Call without an argument for every Grow Lamp, Sprinkler, Dispenser, and Crop Automator there, or pass one of those `type_id` values to filter. They occupy field cells, do not use building capacity, and do not appear in `buildings()`. This excludes the mobile Harvester, crops, loose items, Water Wells, and other POI extractors. Only Nocturna Base currently has a Harvesting field, so founded outposts return an empty list. Use `get_component(ref.id)` for type-specific live reads."""
        ...
```

## `OutpostNetwork`

```python
class OutpostNetwork:
    """get_component(\"outpost_network\")"""
    def outposts(self) -> _list[OutpostRef]:
        """All owned outposts as read-only `OutpostRef` snapshots, including home. Use `.id` when passing an outpost to another API; call `outposts()` again when you need fresh counts/names."""
        ...
    def home(self) -> OutpostRef:
        """The home outpost as an `OutpostRef` snapshot."""
        ...
    def nearest(self, x: _float, y: _float) -> OutpostRef:
        """Nearest owned outpost to the given world coordinate as an `OutpostRef` snapshot."""
        ...
```

## `OutpostNetworkComponent`

```python
class OutpostNetworkComponent(Component):
    """Outpost Network: Read-only index of every owned outpost, including home. Use it for routing, deployment planning, capacity dashboards, and nearest-service decisions without hardcoding `outpost_1`, `outpost_2`, etc. An outpost's `.x` and `.y` identify its footprint anchor. For an at-building action, select that outpost's `BuildingRef` and route to `.position`. Construction planning belongs to Plan Mode and the shared `construction_blueprint` component; physical work belongs to Constructor scripts."""
    name: _str
    def outposts(self) -> _list[OutpostRef]:
        """All owned outposts as `OutpostRef` snapshots. Each ref includes `.id`, `.name`, `.x`, `.y`, `.is_home`, `.buildings_used`, `.buildings_capacity`, and `.is_full`. The coordinates are the top-left footprint anchor, not a particular building's docking point."""
        ...
    def home(self) -> OutpostRef:
        """The home outpost as an `OutpostRef`."""
        ...
    def nearest(self, x: _float, y: _float) -> OutpostRef:
        """Nearest owned outpost to the given world coordinate. Useful before routing a vehicle home to recharge or choosing where a constructor should stage."""
        ...
```

## `OutpostRef`

```python
class OutpostRef:
    """outpost_network.outposts() / outpost_network.home() / outpost_network.nearest()"""
    id: _str
    name: _str
    x: _int
    y: _int
    def position(self) -> Position:
        """Top-left anchor of the outpost footprint as a `Position` snapshot. This identifies the outpost, not a particular building's docking point."""
        ...
    def coords(self) -> _list[_int]:
        """Top-left anchor of the outpost footprint as `[x, y]`. Use `buildings()` and `BuildingRef.position` when routing to a particular service building."""
        ...
    is_home: _bool
    biome: Literal["frozen", "coastal", "geothermal", "volcanic", "deep"]
    buildings_used: _int
    buildings_capacity: _int
    is_full: _bool
    def buildings(self, type_id: _str = ...) -> _list[BuildingRef]:
        """Fresh list of `BuildingRef` snapshots: one entry per building deployed here. Pass a `type_id` (e.g. `\"storage_bin\"`) to filter, or omit for every building. Each ref carries `.id` / `.name` / `.type_id` / `.outpost` / `.powered` / `.position`: for type-specific live reads (`count()`, `material()`, `recipe`, etc.) call `get_component(ref.id)` to reach the full component API."""
        ...
    def harvesting_machines(self, type_id: _str = ...) -> _list[HarvestingMachineRef]:
        """Fresh list of `HarvestingMachineRef` snapshots for fixed machines deployed on this outpost's Harvesting field. Currently only the home outpost, Nocturna Base, has that field, so founded outposts return an empty list. Includes Grow Lamps, Sprinklers, Dispensers, and Crop Automators, which occupy field cells but do not use building capacity or appear in `buildings()`. It does not include the mobile Harvester, crops, loose items, Water Wells, or other POI extractors. Pass a `type_id` to filter, or omit it for all four fixed machine types. Use `get_component(ref.id)` for type-specific live reads."""
        ...
```

## `PowerControl`

```python
class PowerControl(Component):
    """Power Control: Discover every independent power grid, inspect connected outposts, buildings, and field power structures, read generation, consumption, battery charge, and Lightning reserve, or operate machine breakers from one shared controller. Grid objects are snapshots of the latest completed power allocation. After changing a breaker or rewiring infrastructure, re-query on the next loop iteration for refreshed grid totals and membership."""
    name: _str
    def grids(self) -> _list[PowerGrid]:
        """Returns every independent power grid on the planet as a fresh list of `PowerGrid` snapshots. Isolated completed outposts and field structures appear as their own grids, so scripts do not need to guess or hardcode grid ids."""
        ...
    def grid(self, target_id: _str) -> PowerGrid | None:
        """Finds the grid containing `target_id`, which may be an outpost, building, or field power-structure id. Pass a returned grid's `.anchor_id` to look it up again. Returns `None` for an unknown, mobile, under-construction, non-grid, or currently unmapped target."""
        ...
    def total(self) -> PowerSummary:
        """Returns a planet-wide `PowerSummary` across every independent grid. Conventional battery storage and Lightning reserve remain separate so automation can decide which supply it is relying on."""
        ...
    def is_powered(self, machine_id: _str) -> _bool:
        """Returns `True` when the named machine is currently switched on. Unknown machine ids return `False`, so this is safe to call before deciding whether to send a breaker command."""
        ...
    def can_power_off(self, machine_id: _str) -> _bool:
        """Returns `True` when the named machine exists and has a visible breaker toggle. Terraforming machines and many production machines can usually be switched; batteries, passive tanks, mobile units, and ship equipment usually cannot."""
        ...
    def set_powered(self, machine_id: _str, on: _bool) -> ActionResult[Literal["ok", "not_found", "not_toggleable", "under_construction", "not_connected", "not_enough_power"]]:
        """Send the same breaker command as clicking the machine card toggle. `power.set_powered(\"o2gen_1\", False)` switches a machine off; `True` switches it back on. Switching off pauses scripts attached to that machine and preserves their setpoints; switching back on resumes only scripts that were paused by the power-off. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
        ...
```

## `PowerGrid`

```python
class PowerGrid:
    """power_control.grids() / power_control.grid(target_id)"""
    anchor_id: _str
    outpost_ids: _list[_str]
    machine_ids: _list[_str]
    members: _list[PowerGridMember]
    generated: _float
    consumed: _float
    net: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
    has_generator: _bool
```

## `PowerGridMember`

```python
class PowerGridMember:
    """PowerGrid.members"""
    id: _str
    name: _str
    type_id: _str
    outpost_id: _str
    powered: _bool
    roles: _list[_str]
    generated: _float
    consumed: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
```

## `PowerSummary`

```python
class PowerSummary:
    """power_control.total()"""
    grid_count: _int
    generated: _float
    consumed: _float
    net: _float
    stored: _float
    capacity: _float
    reserve_stored: _float
    reserve_capacity: _float
```
