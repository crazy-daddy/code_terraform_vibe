# Pioneer instant charge: Battery Charger, swaps and remote install

Source: game build e1986ce. API docs: [battery_charger.md](../components/battery_charger.md), [pioneer.md](../components/pioneer.md) (`swap_batteries`, `install`, `uninstall`), [guide/batteries_and_charging.md](../guide/batteries_and_charging.md). Checked in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `swap_batteries`, `battery_swap`, `batteryChargeWh`).

Status: not used. Home building space is valuable late game, so remote Vehicle Charging Stations stay the plan. This note records the options in case that changes.

## Battery Charger

- Charges loose Portable (50 Wh) and Heavy Portable (100 Wh) Batteries from the local grid. Mk I: 4 shared slots, 1 bay, 30 W. Mk II: 8 slots, 2 bays, 60 W. A Vehicle Charging Station gives 30 / 120 / 240 W (Mk I / II / III), so the charger is the slower source of energy. Its gain is that the Pioneer doesn't wait.
- Charging is script-controlled (`charge(slot_index)` per cell). A job survives the script stopping and pauses during an outage. Charged, unqueued cells stay usable during an outage.
- The output port keeps each cell's stored charge, also when cells go into Inventory.

## `pioneer.swap_batteries(charger, slots, min_level)`

- Needs a Battery Charger only. No Vehicle Charging Station is involved.
- The charger name is resolved planet-wide, but the service check makes it local. The Pioneer must be stopped, and either within about 2 m of the charger or anywhere inside the service rectangle of the charger's (finished) outpost. One charger per outpost on a swap route.
- Atomic: every selected cell needs a matching unqueued replacement at or above `min_level`, else nothing changes. Drained cells take the vacated sockets. Charged plus drained cells share the slot count, so one swap is capped at 4 (Mk I) or 8 (Mk II) cells; use `slots=` for a subset.
- Duration: the normal item handling time for 2 items per swapped cell.
- Pioneers only. Rover batteries are fixed; drones use the drone_service.

## Remote swap via Inventory (`uninstall` / `install`)

`install`/`uninstall` are hardware service orders. They work at home **or any operational founded outpost**, straight from Inventory. The "Inventory only at home" rule applies to freight only. So a charger at home that outputs charged cells into Inventory can feed Pioneers at every outpost, with no charger or station there.

- `uninstall` gives the cell the Pioneer pool's current average fraction × the cell's capacity. `install` adds the cell's stored charge to the pool; a cell without a stored-charge property counts as full (fresh Shop cells). No energy is created or lost.
- Catch: `install(slot, bay, item_id)` takes the **first Inventory slot** with that item id, whatever its charge. A drained cell just uninstalled can land in an earlier free slot and get reinstalled. Guard: compare `self.battery.wh()` before and after, and retry. Or have the home charger pull drained cells out of Inventory right away (a race, not a guarantee). Not tested in game.
- Each cell is its own timed service order, probably slower than one `swap_batteries` call (duration not checked).
- Costs of dropping outpost stations: no `dispatch_rescue` near those outposts, Rovers still need a station, all charging power and building space sits at home (30–60 W per charger), and more spare cells are needed to cover cells in transit and cells charging.
