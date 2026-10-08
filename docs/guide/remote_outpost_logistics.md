# Guide: remote_outpost_logistics

## Storage and remote outpost logistics

A new outpost gives you somewhere to build. It still needs supplies. Think through a delivery the same way you would a vehicle trip: where are the goods now, who carries them, and where will they be unloaded?

### Pick the right store

| Store | What it is for |
|---|---|
| Base Inventory | Purchases and general stock at Nocturna Base |
| Storage Bin | A local supply of one item type; empty it to change the material |
| Warehouse | Local storage for several item types and their property variants |
| Vehicle cargo | Carrying goods between sites and outposts |
| Lead Cask | Raw Uranium or Fuel Rods, one radioactive material per cask |

You can open Inventory from anywhere, but **its goods are physically at Nocturna Base**. A machine at a remote outpost cannot pull them across the map. Give that outpost a local store and bring supplies by Pioneer or drone.

A connection does not move goods on its own. After **Auto Feeders** research, an input uses `take(...)` and a routed output uses `send(...)`. These transfers take time and can move fewer items than requested if supply or capacity runs short. Read the result's `.moved` value before deciding that a delivery is complete.

### Your first remote delivery

Suppose you want a remote Smelter to process Iron Ore.

1. Deploy the Smelter and a Warehouse at the founded outpost, and provide power.
2. Park a cargo-equipped Pioneer at home. Connect its input to `"inventory"` and load Iron Ore with `take(...)`.
3. Drive to the destination outpost and brake inside its service area.
4. Connect the Pioneer's output to that outpost's Warehouse and unload with `send(...)`.
5. From the Smelter's own script, connect its input to the Warehouse, select the iron recipe and take ore into the input. Move finished ingots out of its output as they become ready.

Use your actual machine ids or display names in connections. A connection remembers its target; it does not follow the vehicle or switch to a new store when you arrive. Reconnect deliberately for the next leg.

A drone route uses its cargo commands and Drone Depots instead. Either way, the useful pattern is **load, travel, unload, process**. Check the receiving store has room before sending the next load. See `refinement` for processing and `io_slots` for transfer examples.

### Close enough, and stopped

Stationary machines and ordinary stores exchange goods within the same outpost. A ground vehicle must be parked in the target's service area to load or unload. Vehicle-to-vehicle handoffs need both vehicles stopped within about **2 m**. A connection to a faraway target does not make it reachable.

Route to the destination's service position, wait for arrival, then brake before starting the handoff. A ground vehicle's movement also stops if its controlling script ends or fails. See `vehicle_service` for the complete parking and docking rules.

### Buying a machine is different from feeding it

**Deploying a shop kit is a service order.** Inventory can deploy an ordinary outpost building straight into a founded outpost. You do not need a cargo trip just to commission that building. Its working supplies still follow the local delivery rules above.

**Planet Map construction needs a Pioneer and materials.** Field Mining Drills, pumps, caps and utilities use blueprints. Their kits or segments must be in the Constructor-equipped Pioneer's cargo. Creating the blueprint does not move the materials or build the machine. See `first_outpost` and `plan_mode`.

Manual Biology has a separate stockroom choice. It uses Inventory at home and one selected local Warehouse at a remote outpost. Changing that selection does not transport anything, and scripted machine ports still need their own connections.

### When a transfer will not go through

Check location, parking, research, available items, free space and whether either endpoint is already busy. A bin may have room but be latched to another material; a Warehouse may need a free physical slot for a different property variant. Raw Uranium and Fuel Rods need the shielded route in `nuclear_power`.

If the wrong goods are already inside a machine input, `input.eject(...)` can recover them to a compatible destination. **`input.flush()` destroys the contents**; it is not an unload command. Read the returned message when a transfer is refused, fix that condition, then try again.

*Guide / Tutorials*
