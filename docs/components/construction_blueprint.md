# Component: construction_blueprint

> **Category:** Infrastructure & Fluids | **Component Name:** Construction Blueprint

Manages planned construction and removal work. Plan Mode and scripts share the same queue. Scripts can place structures, pipes, power lines, and bridges, or mark existing structures for removal. Planning creates the map marker immediately without needing a vehicle at the site. A Pioneer with a Constructor Module must still travel to each job and call `self.constructor.execute(construction.id)` to perform the work.

**Returned by:** `get_component("construction_blueprint")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.plan_structure(kind: str, x: float, y: float, rotation: int = 0) → BlueprintPlanResult`

Create one point-structure construction ghost from script coordinates. Supported kinds are `"outpost"`, `"thermal_cap"`, `"water_pump"`, `"oil_pump"`, `"exotic_gas_cap"`, `"exotic_spring_tap"`, `"mining_drill"`, `"mining_drill_industrial"`, and `"mining_drill_heavy"`. Drill kinds require their matching Earth Order kit recipe. Coordinates snap to the map grid. Extraction structures snap to the exact matching surveyed feature, while Outposts use the snapped footprint anchor. The optional clockwise rotation is `0`, `90`, `180`, or `270`. The ghost enters the shared queue immediately; a Pioneer still constructs it later.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `kind` | `str` | Point blueprint kind. |
| `x` | `float` | World x coordinate. |
| `y` | `float` | World y coordinate. |
| `rotation` | `int` | Optional clockwise rotation: 0, 90, 180, or 270 degrees. |

- **Returns** `BlueprintPlanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.blueprint_ids`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Construction blueprints created: `count`. |
| `"locked"` | rejection | The required construction technology or kit recipe has not been unlocked. |
| `"invalid_kind"` | rejection | The requested map structure kind is not supported. |
| `"invalid_rotation"` | rejection | A structure rotation must be 0, 90, 180, or 270 degrees. |
| `"out_of_bounds"` | rejection | At least one requested construction tile lies outside the planet bounds. |
| `"wrong_target"` | rejection | The requested position does not contain the map feature required by this structure. |
| `"unsurveyed_target"` | rejection | The required map feature has not been surveyed. |
| `"too_hard"` | rejection | The selected Mining Drill cannot cut this deposit's mineral hardness. |
| `"target_claimed"` | rejection | The required map feature already has a built or planned extractor. |
| `"occupied"` | rejection | The requested structure footprint overlaps existing or planned construction, or a physical anomaly. |
| `"clearance"` | rejection | The requested structure footprint crosses an Outpost or physical-anomaly clearance boundary. |
| `"blocked"` | rejection | The requested construction or deconstruction is blocked by existing or planned infrastructure. |

##### `.plan_pipe(medium: str, x1: float, y1: float, x2: float, y2: float) → BlueprintPlanResult`

Create pipe construction jobs from script coordinates. Requires Constructor Module research. `medium` is `"gas"`, `"liquid"`, or a registered fluid id such as `"steam"`, `"water"`, or `"oil"`. Coordinates snap to tile-center lanes. A field structure uses its site coordinates. An internal outpost machine uses its owning outpost as the utility anchor, so route to a point in `building.outpost`'s footprint, such as `[building.outpost.x, building.outpost.y]`, not to the vehicle docking point in `building.position`. Existing matching pieces are reused automatically.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `medium` | `str` | `"gas"` / `"liquid"`, or any registered fluid id. |
| `x1` | `float` | World x coordinate of the route start. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.x`. |
| `y1` | `float` | World y coordinate of the route start. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.y`. |
| `x2` | `float` | World x coordinate of the route end. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.x`. |
| `y2` | `float` | World y coordinate of the route end. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.y`. |

- **Returns** `BlueprintPlanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.blueprint_ids`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Construction blueprints created: `count`. |
| `"locked"` | rejection | The required construction technology or kit recipe has not been unlocked. |
| `"invalid_medium"` | rejection | The requested infrastructure medium is not supported. |
| `"out_of_bounds"` | rejection | At least one requested construction tile lies outside the planet bounds. |
| `"invalid_route"` | rejection | The requested endpoints do not define a usable construction route. |
| `"blocked"` | rejection | The requested construction or deconstruction is blocked by existing or planned infrastructure. |
| `"already_exists"` | success | The matching infrastructure route already exists, so no blueprint was created. |

##### `.plan_power_line(x1: float, y1: float, x2: float, y2: float) → BlueprintPlanResult`

Create power-line construction jobs from script coordinates. Requires Constructor Module research. Coordinates snap to tile-center lanes; off-axis paths choose the valid L-shaped elbow with the least new construction. A field structure uses its site coordinates. An internal outpost machine uses its owning outpost as the utility anchor, so route to a point in `building.outpost`'s footprint, such as `[building.outpost.x, building.outpost.y]`, not to the vehicle docking point in `building.position`. Existing matching pieces are reused automatically.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x1` | `float` | World x coordinate of the line start. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.x`. |
| `y1` | `float` | World y coordinate of the line start. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.y`. |
| `x2` | `float` | World x coordinate of the line end. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.x`. |
| `y2` | `float` | World y coordinate of the line end. For an internal outpost machine, use a point in its owning outpost footprint, such as `building.outpost.y`. |

- **Returns** `BlueprintPlanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.blueprint_ids`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Construction blueprints created: `count`. |
| `"locked"` | rejection | The required construction technology or kit recipe has not been unlocked. |
| `"out_of_bounds"` | rejection | At least one requested construction tile lies outside the planet bounds. |
| `"invalid_route"` | rejection | The requested endpoints do not define a usable construction route. |
| `"blocked"` | rejection | The requested construction or deconstruction is blocked by existing or planned infrastructure. |
| `"already_exists"` | success | The matching infrastructure route already exists, so no blueprint was created. |

##### `.plan_bridge(medium: str, x: float, y: float, axis: str) → BlueprintPlanResult`

Create one utility bridge job from script coordinates. Requires Constructor Module research. `medium` is `"gas"`, `"liquid"`, `"power"`, or a registered fluid id. `x`/`y` are the bridge center tile and `axis` is `"horizontal"` or `"vertical"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `medium` | `str` | `"gas"`, `"liquid"`, `"power"`, or any registered fluid id. |
| `x` | `float` | World x coordinate of the bridge tile. |
| `y` | `float` | World y coordinate of the bridge tile. |
| `axis` | `str` | `"horizontal"` or `"vertical"`. |

- **Returns** `BlueprintPlanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.blueprint_ids`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Construction blueprints created: `count`. |
| `"locked"` | rejection | The required construction technology or kit recipe has not been unlocked. |
| `"invalid_medium"` | rejection | The requested infrastructure medium is not supported. |
| `"invalid_axis"` | rejection | A bridge axis must be "horizontal" or "vertical". |
| `"out_of_bounds"` | rejection | At least one requested construction tile lies outside the planet bounds. |
| `"blocked"` | rejection | The requested construction or deconstruction is blocked by existing or planned infrastructure. |
| `"already_exists"` | success | The matching infrastructure route already exists, so no blueprint was created. |

##### `.mark_deconstruct(x: float, y: float, layer: str = "auto", target_id: str = "") → BlueprintPlanResult`

Mark built infrastructure or a normal map building at the coordinate for deconstruction. Requires Constructor Module research. Base and Outposts are protected. When several independent map layers overlap, choose the `"building"`, `"gas"`, `"liquid"`, or `"power"` layer; the default `"auto"` requires an unambiguous target. At a same-layer junction, provide the optional exact target id. A Pioneer still executes the job with `self.constructor.execute(id)` at the job's reported `position`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | World x coordinate of the target tile. |
| `y` | `float` | World y coordinate of the target tile. |
| `layer` | `str` | Optional target layer. Use `"building"`, `"gas"`, `"liquid"`, or `"power"` when several layers overlap; `"auto"` selects the first target on an unambiguous tile. |
| `target_id` | `str` | Optional exact machine or infrastructure id used to resolve same-layer junctions. |

- **Returns** `BlueprintPlanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.blueprint_ids`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Construction blueprints created: `count`. |
| `"locked"` | rejection | The required construction technology or kit recipe has not been unlocked. |
| `"nothing_here"` | rejection | There is no completed deconstructable target at that position. |
| `"already_queued"` | success | A matching deconstruction blueprint is already queued. |
| `"ambiguous_target"` | rejection | More than one deconstructable target matches that position and layer. Choose a more specific layer or another tile. |
| `"out_of_bounds"` | rejection | At least one requested construction tile lies outside the planet bounds. |
| `"invalid_layer"` | rejection | A deconstruction layer must be "auto", "building", "gas", "liquid", or "power". |
| `"blocked"` | rejection | The requested construction or deconstruction is blocked by existing or planned infrastructure. |

##### `.cancel(blueprint_id: str) → ActionResult`

Cancel a queued, active, or paused construction blueprint by id. Unpaid jobs cancel immediately. A paid job keeps its material at the build site: park a Pioneer there to recover it into cargo. A failed recovery leaves the job and material intact.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `blueprint_id` | `str` | Blueprint id from `.pending_constructions()`, `.active_constructions()`, or `.paused_constructions()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"worker_not_present"` | rejection | No Pioneer is present at the construction site to receive the refund. |
| `"no_cargo_space"` | rejection | Cargo has no compatible space for the result. |
| `"construction_dependency"` | rejection | Another construction job depends on this job. |

##### `.pending_constructions() → list[Construction]`

Returns blueprints awaiting a worker as `list[Construction]`. Drawn pipe/power paths and marked deconstruction targets are split into independent jobs, usually in placement order. Pass each `c.id` to `self.constructor.execute(c.id)` to build or deconstruct it. Read `c.required_item` and `c.required_count` to load the exact cargo before executing; never infer material from `c.kind`. Filter by `c.kind` to specialize a Pioneer's role, then use `c.medium` to distinguish `"gas"`, `"liquid"`, and `"power"` utility jobs. Point structures have `c.medium == None`; see `Construction.kind` for the full kind list.

- **Returns** List of `Construction` snapshots awaiting a worker. Each has `.id`, `.kind`, `.medium`, `.position`, `.progress`, `.required_item`, `.required_count`. Iterate and pass `c.id` to `self.constructor.execute(c.id)` to build or deconstruct it.

##### `.active_constructions() → list[Construction]`

Returns blueprints currently being built (a Pioneer is working). Useful for monitor scripts, read `c.progress` to see how far along.

- **Returns** List of `Construction` snapshots currently being built or removed (a Pioneer is working). Re-query for fresh `.progress`.

##### `.paused_constructions() → list[Construction]`

Returns blueprints started then abandoned (worker died, ran out of fuel, or script stopped). Any Pioneer can resume by navigating to `c.position` and calling `self.constructor.execute(c.id)`.

- **Returns** List of `Construction` snapshots started then abandoned (worker died / left). Resumable by any Pioneer via `self.constructor.execute(c.id)`. Re-query for fresh `.progress`.

*Components / Infrastructure & Fluids*
