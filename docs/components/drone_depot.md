# Component: drone_depot

> **Category:** Logistics & Orders | **Component Name:** Drone Depot

1-bay logistics endpoint at an outpost. Cargo I/O.

| Field | Value |
| --- | --- |
| Type | Mining |
| Power in | -2 W (draws from grid) |
| Stockpile | 50 units (mixed) |

### How to obtain

1. The recipe unlocks when you complete **Helios, Frame Order**.
2. Requires the **Basic Drone Operations** research (Terraform Index 180,000).
3. Fabricate a **Drone Depot Kit** on a **Fabricator**: 2× Machine Frame, 1× Control Unit, 2× Gas Pipe Segment, 2× Liquid Pipe Segment, and 3 t Water.
4. Deploy it from your Inventory.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `.input`

`InputSlot` for this station's local stockpile. Connect `"inventory"` or a machine or storage source at the same outpost, then call `self.input.take(item_id, count)`. `self.input.flush()` discards the station stockpile. Stock at another Drone Depot is not visible here.

- **Returns** InputSlot: `connect()`, `take()`, `eject()`, `flush()`, `count()`, `capacity()`, `connected_to()`.

##### `.output`

`OutputSlot` for this station's local stockpile. Connect `"inventory"` or a machine or storage target at the same outpost, then call `self.output.send(item_id, count)`. Move cargo between outposts with a drone; stations do not share stock.

- **Returns** OutputSlot.

### Methods

##### `.get_docked()`

List of drone ids currently docked at this Depot, in stable id order. Read each drone's state with `get_component(id)`.

- **Returns** List of drone instance ids currently docked at this Depot, in stable id order.

##### `.bay_count()`

Total bays at this station: **1** (basic) / **2** (medium) / **4** (large).

- **Returns** Number: total bays at this station (**1** / **2** / **4** depending on tier).

##### `.bays_occupied()`

Bays currently occupied by docked drones. When equal to `bay_count`, arriving drones queue in airspace.

- **Returns** Number: bays currently occupied by docked drones.

##### `.slots_used()`

How many distinct materials the stockpile currently holds. One material is one slot no matter how many units of it are stored, so **50** units of one material fills a single slot.

- **Returns** Number: distinct materials currently held. Each material occupies one slot regardless of how many units of it are stored.

##### `.slot_capacity()`

How many distinct materials this depot can hold at once. A depot is a transfer proxy, not a warehouse: when every slot is taken, a `cargo.unload()` of a new material moves **0** units and reports that no slot is free, even while units remain free. Drain a material out to release its slot.

- **Returns** Number: how many distinct materials this depot can hold at once (**3** / **4** / **6** depending on tier).

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Logistics & Orders*
