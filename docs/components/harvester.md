# Component: harvester

> **Category:** Production & Storage | **Component Name:** Harvester

A slow general-purpose surface vehicle that collects loose items, plants and tends crops, harvests Forage, and deploys fixed field machines. Movement and field work take time and build heat, so long routes need cooling pauses.

| Field | Value |
| --- | --- |
| Type | Harvesting |

**Returned by:** `self`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.move(sector: str) → ActionResult` *(self only)*

Move one sector up, down, left, or right with `self.move("E14")`; diagonal moves are invalid. Travel takes **0.5 hours** and pauses the script. `self.get_position()` shows the destination immediately, but physical actions stay locked until arrival. Moving into an item sector adds **1** heat; moving into an empty one adds **7**, so scan first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | Adjacent grid sector id to move to (one cardinal step). |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid"` | rejection | One or more supplied arguments are outside the accepted domain. |
| `"too_far"` | rejection | The requested target is outside interaction distance. |
| `"already_here"` | rejection | The vehicle is already at the requested destination. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.collect() → ScanResult` *(self only)*

Pick up the item in the current sector into the Harvester's single held slot, not Inventory. Collection takes **0.25 hours** and pauses the script. Empty sectors still take time and add **9** heat.

- **Returns** `ScanResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.id`, `.name`, `.value`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | Collected `item_id` into the Harvester's held slot. |
| `"empty"` | success | The current sector contains no collectible item. |
| `"holding"` | rejection | The Harvester's held slot is occupied. |
| `"overheated"` | rejection | The Harvester has reached its heat limit, or the attempted collection would exceed it. |
| `"moving"` | transient | The Harvester is still completing a physical movement. |
| `"busy"` | transient | The Harvester is occupied by another field action. |
| `"collecting"` | transient | A previous collection cycle is still in progress. |

##### `.store() → ItemResult` *(self only)*

Move the Harvester's held item into the first empty inventory slot, freeing the held slot for the next pickup. It works from any sector; the Harvester never has to return to a base sector to unload. A full inventory leaves the item held; drop it or free space by selling through the Shop.

- **Returns** `ItemResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.item_id`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation affected item `.item_id`. |
| `"empty"` | success | The selected item source was already empty. |
| `"inventory_full"` | rejection | Inventory has no capacity for the held item. |

##### `.drop() → ActionResult` *(self only)*

Release the currently held item into the Harvester's current sector, the cell becomes collectable again. Use it to stage items for later pickup or clear the held slot without storing.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"dropped"` | success | The item was removed from its source. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"occupied"` | rejection | The requested cell, sector, or Habitat is already occupied. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.get_held() → str`

Item id currently held by the Harvester, or empty string if the held slot is empty. Call `self.get_held()` before `collect()` (if non-empty, the slot is busy) or before `self.store()` (if empty, nothing to store). Essential first line of any collect loop.

- **Returns** String (item id, or empty string if not holding)

##### `.get_position() → str`

Current sector id as a string (e.g. `"E14"`). Use to plan the next `move()` target, movement is strictly to adjacent cells, so the script needs to know where it is to compute where it can go.

- **Returns** String (sector)

##### `.get_heat() → float`

Exact current heat level (**0-100**), including fractional cooling between whole heat costs. Every `move()` adds heat, and an empty-sector `collect()` attempt also adds heat; passive cooling runs continuously as game time passes, including during movement and collection. Read before moving, if you're close to **100** and your planned route crosses empty cells (+7 heat each), stop and cool. Losing the route to `"overheated"` mid-sweep wastes hours.

- **Returns** Number (0-100)

##### `.get_max_heat() → int`

Maximum heat capacity, always **100**. Reaching this stalls all movement and collection until heat drops below the cap. Exposed as a method so scripts can reason about thresholds without hardcoding the number.

- **Returns** Number (100)

##### `.is_overheated() → bool`

`True` when heat `>= 100`. Shortcut for `self.get_heat() >= self.get_max_heat()`. Use it as an early-exit guard when you intentionally want the Harvester to cool: `if self.is_overheated(): sleep(1)`. The Harvester cools passively whenever game time advances.

- **Returns** Boolean

##### `.water_level() → float`

Read the water currently in the Harvester's onboard tank, in tons, including fractional amounts. Each watering uses **1 t**. Compare with `water_capacity()` to plan refills from the home outpost's water tanks.

- **Returns** Number: onboard water in tons, including fractional amounts.

##### `.water_capacity() → float`

Read the Harvester's maximum onboard water supply in tons, currently **5 t**. Compare with `water_level()` to check how full the tank is.

- **Returns** Number: onboard water capacity in tons.

##### `.load_seed(seed: str) → ActionResult` *(self only)*

Transfer one species seed from home Inventory, from anywhere on the grid, into the Harvester's single held slot. Use the same seed id with `plant(seed)` after driving to an empty field cell. Loading fails while another item is held.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `seed` | `str` | Seed item id from the Seed Maker. Loading transfers one seed from Inventory into the Harvester's single held slot, from anywhere on the grid. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"invalid_seed"` | rejection | The supplied item is not a plant seed. |
| `"no_seed"` | rejection | The requested seed is not available. |
| `"holding"` | rejection | The Harvester's single held slot is already occupied. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.plant(seed: str) → ActionResult` *(self only)*

Sow the physical seed currently in the Harvester's held slot into this empty cell. The argument must identify that held seed. The base sector is depot ground and refuses sowing. Sowing takes **0.5 hours**, and the seed and new crop appear only after the action finishes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `seed` | `str` | Seed item id matching the physical seed in the Harvester's held slot. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"invalid_seed"` | rejection | The supplied item is not a plant seed. |
| `"no_seed"` | rejection | The requested seed is not available. |
| `"not_empty"` | rejection | The relevant cell, slot, or component is not empty. |
| `"base_sector"` | rejection | The base sector is the Harvester's depot pad and cannot be planted. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.deploy(kit: str) → ActionResult` *(self only)*

Place a supported field-machine kit in the current empty cell, consuming one kit from Inventory. Installation takes **0.25 hours** and pauses the script. Call `deployables()` for the available kit ids. Seed Makers and other outpost buildings deploy through Inventory.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `kit` | `str` | Fixed field-machine kit item id unlocked by current research. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_kit"` | rejection | The required deployable kit is not available. |
| `"not_empty"` | rejection | The relevant cell, slot, or component is not empty. |
| `"invalid_kit"` | rejection | The supplied deployable kit is invalid for this operation. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.deployables() → list[str]`

List of fixed field-machine kit ids unlocked by your current research. This is a capability list, not a live deployment check: `deploy(...)` still checks Inventory stock, the current cell, movement, heat, and whether the Harvester is busy.

- **Returns** List of fixed field-machine kit ids unlocked by research. It does not check Inventory stock, placement, heat, movement, or busy state. Empty until Grow Lamp research.

##### `.light() → ActionResult` *(self only)*

Light the current plantable cell with the Harvester's work lamp, even if it is already lit or covered by a Grow Lamp. Each application resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Lighting takes **0.25 hours** and pauses the script. Use a Grow Lamp later to cover four orthogonally adjacent cells (directly above, below, left, and right) continuously.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"not_plantable"` | rejection | The current cell cannot receive the requested plant treatment. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.water() → ActionResult` *(self only)*

Water the current plantable cell from the Harvester's onboard supply, even if it is already watered or covered by a Sprinkler. Each watering uses **1 t** and resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Watering takes **0.25 hours** and pauses the script. Use `refill_water()` anywhere on the local grid to draw from the home outpost's tanks.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"insufficient_water"` | rejection | The Harvester has less than the 1 t of onboard water required for treatment. |
| `"not_plantable"` | rejection | The current cell cannot receive the requested plant treatment. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.refill_water() → ActionResult` *(self only)*

Refill the Harvester's onboard water supply from the home outpost's water tanks, from anywhere on the grid. Refilling takes **0.25 hours** and pauses the script.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"tank_empty"` | rejection | The source tank is empty. |
| `"already_full"` | rejection | The target is already at full capacity. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.dispense_salt() → ActionResult` *(self only)*

Treat the current plantable cell with one unit of `salt` from Inventory, even if it is already salted or covered by a Dispenser. Each application resets the treatment to **24 hours** when the work finishes, replacing any remaining time. Dispensing takes **0.25 hours** and pauses the script. Water Pumps produce salt as a byproduct.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_salt"` | rejection | No salt is available for the treatment. |
| `"not_plantable"` | rejection | The current cell cannot receive the requested plant treatment. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.fertilize(item_id: str = "fertilizer") → ActionResult` *(self only)*

Dose the current cell's growing plant with one Fertilizer Mk I, II, or III. Each unit boosts output for **8 hours**. Additional units of the same tier extend it; wait for the active dose to drain before switching tiers. Dosing occupies the Harvester for **0.25 hours**.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item_id` | `str` | Fertilizer item id picking the tier; omit for Mk I. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_input"` | rejection | The supplied input value is invalid. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_plant"` | rejection | The current cell contains no plant. |
| `"already_mature"` | rejection | The plant is already mature, so a growth treatment cannot affect it. |
| `"tier_conflict"` | rejection | The cell already has a different active Fertilizer tier. |
| `"no_dose"` | rejection | The required treatment item is not available. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.accelerate() → ActionResult` *(self only)*

Dose the current cell's growing plant with one `growth_accelerant` to double its growth rate for **8 hours**. Dosing occupies the Harvester for **0.25 hours**. The dose cannot affect a crop that is already mature.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_plant"` | rejection | The current cell contains no plant. |
| `"already_mature"` | rejection | The plant is already mature, so a growth treatment cannot affect it. |
| `"no_dose"` | rejection | The required treatment item is not available. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.amplify() → ActionResult` *(self only)*

Apply one `yield_amplifier`, the capstone **field-wide** Forage-output boost (no cell needed). Applying it occupies the Harvester for **0.25 hours**. The dose drains over about one game-day, so re-call to sustain.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_dose"` | rejection | The required treatment item is not available. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.amplifier_remaining() → float`

Hours remaining on the field-wide Yield Amplifier effect. Each applied unit adds **24 hours**. Returns **0** when the field is not amplified.

- **Returns** Hours remaining on the field-wide Yield Amplifier effect.

##### `.uproot() → ActionResult` *(self only)*

Remove the plant in the current cell and place one matching seed in Inventory. Uprooting takes **0.5 hours** and pauses the script.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"no_plant"` | rejection | The current cell contains no plant. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.undeploy() → ActionResult` *(self only)*

Remove the fixed field machine in the current cell and return its kit to Inventory. This is the only removal path for Grow Lamps, Sprinklers, Dispensers, and Crop Automators. Its stored items must be empty, the hardware refund must fit, and its attached script must not be running. Authored scripts are stopped and kept in Computer > Scripts > Unassigned. Unfinished machine work and machine-only result history are discarded; queued Crop Automator jobs have not consumed their inputs. Removal takes **0.25 hours** and pauses the Harvester script.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"nothing"` | rejection | There is no applicable target at the requested location. |
| `"not_empty"` | rejection | The relevant cell, slot, or component is not empty. |
| `"script_present"` | rejection | An attached script is currently running on the machine. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.harvest() → ActionResult` *(self only)*

Harvest the ready crop in the current cell. The action takes **0.5 hours** and transfers nothing until it finishes. On completion it moves as much of `cell.forage` as Inventory can hold: a crop larger than the free room leaves its remainder banked and the plant standing, so drain Inventory and harvest again to collect the rest. Only a fully collected crop is removed and frees the cell for another physical seed.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"partial"` | partial | The operation moved part of the requested amount; the remainder is still available at the source. |
| `"locked"` | rejection | The required feature, recipe, or operation is locked. |
| `"no_plant"` | rejection | The current cell contains no plant. |
| `"not_mature"` | rejection | The plant has not reached maturity. |
| `"no_forage"` | rejection | The ready crop has no whole forage unit to collect. |
| `"inventory_full"` | rejection | Inventory has no capacity for the result. |
| `"overheated"` | transient | The component is too hot for the requested operation or would exceed its heat limit by performing it. |
| `"moving"` | transient | The vehicle or component is currently moving. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.cell(sector: str) → Cell | None`

Read one grid sector as a `Cell` snapshot. Unscanned natural ground has status `"unknown"` until scanned; the depot and player-created plants or providers stay visible. The snapshot includes plant, growth, conditions, and remaining treatment hours. Returns `None` for an invalid sector.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sector` | `str` | Grid sector id (e.g. `"E13"`). |

- **Returns** A `Cell` for the requested sector, or `None` for an invalid or off-grid id. Natural ground is `"unknown"` until scanned; the depot and player-created plants or providers remain visible. Includes plant, growth, conditions, treatment time, fertilizer tier, and forage.

##### `.cells() → list[Cell]`

Read every harvester-grid sector as a list of `Cell` snapshots. Unscanned natural ground reports status `"unknown"`; scan sectors before planning around occupancy. Use the list for field-wide planting, treatment-route scheduling, uprooting, undeploying, and harvesting policies.

- **Returns** List of every grid `Cell` on the board. Unscanned natural ground has status `"unknown"`; scanned cells expose occupancy. Player-created plants/providers, growth, direct conditions, precise remaining treatment times, active fertilizer tier, and accumulated forage remain visible.

##### `.position() → str`

Current sector id as a string. Same position source as `get_position()`, exposed as a property-style read for grid scripts.

- **Returns** String: the sector the harvester currently occupies (e.g. `"E13"`). The Plants verbs all act on this cell; `self.move(...)` to act elsewhere.

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Production & Storage*
