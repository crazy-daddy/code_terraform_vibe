# Component: ship_computer

> **Category:** Infrastructure & Fluids | **Component Name:** Ship Computer

Manages the hardware roster: deploy a machine, vehicle, or drone from Inventory into an outpost, upgrade a deployed machine, remove one back to Inventory, decommission an emptied outpost, and rename anything you own. These are the Inventory page's Deploy and Upgrade buttons and the Computer's System tab, reached from a script. Every call needs Ship Computer research; the buttons themselves keep working before it.

**Access via:** `get_component("computer")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id: str`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** `str`

##### `.name: str`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** `str`

### Methods

##### `.deploy(item_id: str, outpost: str | Outpost | None = None) → ComputerDeployResult`

Deploy one unit of an inventory item into an outpost, defaulting to home. The machine lands with no script and does nothing until you attach one, exactly as a hand-placed machine does. A machine that the outpost's subnet cannot yet carry lands powered off.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Inventory item id of the machine, vehicle, or drone kit to deploy. |
| `outpost` | `str \| Outpost \| None` | Target outpost id, name, or `Outpost`. Omit for the home outpost. |

- **Returns** `ComputerDeployResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.machine_id`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Deployed `name` at `location`. |
| `"no_kit"` | rejection | Inventory holds no `item_id` to deploy. |
| `"locked"` | rejection | Deploying from a script needs Ship Computer research, or the machine's own research is not yet complete. |
| `"not_deployable"` | rejection | That item is not a deployable machine. |
| `"deploy_limit"` | rejection | The deployed count for this machine type is already at its maximum. |
| `"location_not_found"` | rejection | The requested outpost does not exist or is not operational. |
| `"wrong_biome_for_machine"` | rejection | This machine only operates in another biome. |
| `"duplicate_outpost_machine"` | rejection | This outpost already has a machine of this type, and only one is allowed. |
| `"missing_drone_station"` | rejection | The target outpost has no Drone Depot to assemble a drone at. |
| `"drone_station_full"` | rejection | Every Drone Depot bay at the target outpost is occupied. |

##### `.upgrade(item_id: str, machine: str | Component) → ActionResult`

Upgrade a deployed machine with one item from Inventory. An upgrade pack raises the machine to the pack's tier. A larger deploy kit upgrades a smaller machine of the same family in place: the machine keeps its id, name, cargo, scripts, and connections, and its old kit returns to Inventory. The machine must be finished and part of an operational outpost, and a running machine's subnet must carry the larger kit's extra draw. These are the Inventory page's UPGRADE and UPGRADE EXISTING buttons, reached from a script.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Inventory item id of the upgrade pack, or of the larger kit that replaces a smaller machine in place. |
| `machine` | `str \| Component` | Machine id, name, or component to upgrade. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"not_upgrade_item"` | rejection | The item is not an upgrade pack or a kit that upgrades a machine in place. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"under_construction"` | transient | The target is still under construction. |
| `"not_at_outpost"` | rejection | The machine is not part of an operational outpost. |
| `"item_not_in_inventory"` | rejection | Inventory does not contain the requested item. |
| `"wrong_machine_type"` | rejection | The upgrade does not fit the machine's type. |
| `"tier_too_high"` | rejection | The machine is already at or above the upgrade's tier. |
| `"tier_not_ready"` | rejection | The machine is below the tier the upgrade applies to. |
| `"not_enough_power"` | rejection | The available energy is below the operation's requirement. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

##### `.undeploy(machine: str | Component) → ActionResult`

Remove a deployed machine, vehicle, or drone and return its kit, mounted modules, contained items, and tier upgrade packs to Inventory. Stored cargo blocks removal, so empty it first. Authored scripts survive as detached records. Field equipment is recovered by its Harvester and map structures by a Pioneer, not here.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `machine` | `str \| Component` | Machine id, name, or component to remove. Its hardware returns to Inventory. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"not_undeployable"` | rejection | This machine type is not removed through the Computer. Field equipment is recovered by the Harvester and map structures by a Pioneer. |
| `"self_target"` | rejection | A machine's own script cannot remove the machine it runs on. |
| `"cargo_present"` | rejection | Existing cargo prevents the requested configuration change. |
| `"docked_drone"` | rejection | A drone is still assigned to this station. |
| `"construction_dependency"` | rejection | Another construction job depends on this job. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

##### `.decommission(outpost: str | Outpost) → ActionResult`

Remove a founded outpost and return its Outpost Kit to Inventory. The outpost must hold no machines; nothing is cascade-destroyed. Drones and vehicles don't belong to an outpost, so they never block it. Pipes, power lines, and bridges that touched it stay on the map for a Pioneer to reclaim. The home outpost is permanent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `outpost` | `str \| Outpost` | Outpost id, name, or `Outpost` to remove. It must hold no machines. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"is_home"` | rejection | The home outpost is permanent. |
| `"not_empty"` | rejection | The relevant cell, slot, or component is not empty. |
| `"construction_dependency"` | rejection | Another construction job depends on this job. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |

##### `.rename(target: str | Component | Outpost, name: str) → ActionResult`

Set the display name of a machine or outpost. Names are unique across every machine, outpost, and panel. Ids never change, so saved references keep working.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `target` | `str \| Component \| Outpost` | Machine or outpost id, name, or component to rename. |
| `name` | `str` | New display name. Must be unique across machines, outposts, and panels. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"not_found"` | rejection | The requested object, target, or record does not exist. |
| `"name_empty"` | rejection | A display name cannot be blank. |
| `"name_too_long"` | rejection | The display name exceeds the maximum length. |
| `"name_taken"` | rejection | Another machine, outpost, or panel already uses that name. |

*Components / Infrastructure & Fluids*
