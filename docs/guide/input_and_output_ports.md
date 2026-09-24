# Guide: input_and_output_ports

## Input & Output

Machines process items, while I/O ports decide where those items come from and where they go.

### Connections

A routed machine port connects to the display name/id of a compatible machine or store at the same outpost. `"inventory"` is a freight endpoint only at home.

```
self.input.connect("Raw Materials")
self.output.connect("inventory")
self.input.take("iron_ore", 10)
self.output.send("iron_ingot", self.output.count())
```

Connections persist. Transfers require **Auto Feeders**, take time proportional to units moved, and are transactional: rejected or blocked transfers leave the exact source items unchanged. **Fast Feeders** unlocks at **400,000 Terraform Points** and halves the duration of newly started timed item transfers throughout the logistics system. Transfers already in progress keep the duration they started with.

A Plant Terraformer's receiving feeder handles **16 items per handling step** at Mk I and **80** at Mk II. The same capacity applies whether its input pulls from a source or another machine or store sends to it. Both physical endpoints remain occupied for the resulting transfer duration.

Field Mining Drills and Water Pumps use a pickup-only `PickupOutputSlot` instead. It exposes `count()`, `capacity()`, and `stacks()` but no connection or send methods. A physically present carrier initiates the transfer through its own cargo API.

### Property-bearing items

The canonical value is an `ItemStack`: `.id`, whole-number `.count`, and opaque `.properties`. Properties belong to the item and survive Inventory, bins, warehouses, ports, and cargo. Equal ids merge only when their properties are deeply equal.

`stacks()` returns property-distinct snapshots:

```
for stack in self.output.stacks():
  print(stack.id, stack.count, stack.properties)
```

Use the optional property dict on `take` or `send` to select stacks containing that subset:

```
self.output.send(fragment_id, 1, {"forged": True})
```

The fourth argument controls matching. `"exact"` selects one full property identity, including `None` for ordinary propertyless items. `"subset"` selects dict subsets, and `"any"` ignores properties. When omitted, a dict uses subset matching and `None` uses any-variant matching.

```
self.output.send(fragment_id, 1, stack.properties, "exact")
self.output.send(fragment_id, 1, None, "exact")
```

Without a selector, transfers are deterministic. Most sources take matching stacks in storage order. A Warehouse keeps property-variant groups in storage order, but within the selected exact variant it drains the smallest physical stack first so partially filled duplicate slots are released sooner. Different Warehouse property variants still occupy different physical slots. A Storage Bin latches to one item id but may hold several property-distinct stacks of that id.

### Port API

- `connect(name)` / `disconnect()` / `connected_to()` on routed ports
- `take(item_id, count)` on inputs, with optional property and matching arguments
- `send(item_id, count)` on routed outputs, with optional property and matching arguments
- `count()` / `capacity()`
- `stacks()`

Manual UI actions are separate from port automation. At Nocturna Base, manual Biology uses Inventory. At another outpost, its Manual Stockroom selector binds every card to one local Warehouse. Habitat revival reagents use their own local staging. Port automation follows freight locality like every other machine.

Vehicle handoffs additionally require both vehicles stopped within about 2 m. Inventory freight requires a vehicle at home; stationary-store transfers require it inside the target service area. If a target rejects a transfer, its result names the reason and nothing is lost.

*Guide / Production & Logistics*

## Battery Holder

A **Battery Holder** is a module that mounts in a modular vehicle's Universal slot and hosts **Portable Battery** items. The holder itself stores no energy; it is a rack. The contained batteries hold the charge.

Every battery installed in any holder contributes to the vehicle's single shared battery pool. Uninstalling a battery shrinks the pool immediately and transfers that cell's proportional share of stored charge back onto the battery item. Reinstalling restores only that retained charge, so moving cells never creates free energy. Scripts query the pool through `self.battery`:

```
level = self.battery.level()   # 0-1
wh = self.battery.wh()      # current Wh
cap = self.battery.capacity()   # max Wh = sum of every battery's rated Wh
```

For per-holder detail:

```
for h in self.battery.holders():
  print(h.size, h.wh, "/", h.capacity)
  for b in h.batteries:
    if b is not None:
      print(" ", b.id, b.wh(), "/", b.capacity())
```

### Variants

- **Small Battery Holder**, **1** bay
- **Medium Battery Holder**, **2** bays
- **Large Battery Holder**, **3** bays

Each holder occupies **1 Universal slot** on a compatible modular vehicle. Mount/unmount at base or any outpost.

*Guide / Production & Logistics*

## Cargo Rack

A **Cargo Rack** is a module that mounts in a modular vehicle's Universal slot and hosts **Portable Storage Bin** items. The rack itself stores nothing; it is a frame. The contained bins hold the materials.

Every bin installed in any rack contributes to the vehicle's cargo. Each bin holds exactly **one material or item id**: the first unit loaded into it latches that id; subsequent units must match. Property-distinct variants of that id remain separate logical stacks in the bin, so transferring an item never erases its properties.

```
print(self.cargo.count(), "/", self.cargo.capacity())

for r in self.cargo.racks():
  for bin in r.bins:
    if bin is not None:
      print(bin.id, bin.item_id, bin.count, "/", bin.capacity)
      for stack in bin.stacks:
        print(stack.id, stack.count, stack.properties)
```

A bin drains back to **unassigned** when `send()` empties it to zero, ready for any material or item on the next trip.

### Variants

- **Small Cargo Rack**, **1** bin slot
- **Medium Cargo Rack**, **2** bin slots
- **Large Cargo Rack**, **3** bin slots

Each rack occupies **1 Universal slot** on a compatible modular vehicle. Mount/unmount at base or any outpost.

*Guide / Production & Logistics*

## Portable Battery

A **Portable Battery** is a rechargeable cell that installs into a Battery Holder's internal slot. Shop-purchased cells arrive at **100% charge**. Installed, the cell transfers its stored Wh into the vehicle's shared battery pool.

All installed batteries discharge together as one pool. Individual `.wh()` tracks the pool's fill percentage scaled by the battery's rated capacity, not an independent charge. Uninstalling a cell transfers its proportional share of the pool back onto that battery item, so reinstalling never creates free energy.

### Variants

- **Portable Battery**, **50 Wh** rated capacity
- **Heavy Portable Battery**, **100 Wh** rated capacity

Install or uninstall at base or any outpost.

*Guide / Production & Logistics*

## Portable Storage Bin

A **Portable Storage Bin** is a single-material container that installs into a Cargo Rack's internal slot. On its own, a portable bin stores nothing. Installed, it adds its rated capacity to the vehicle's cargo and accepts one material or item id at a time.

Use item id `"portable_bin"` for the standard bin and `"heavy_portable_bin"` for the heavy bin when calling `self.install(...)`.

The first unit loaded into the bin latches that id; subsequent units must match. When `send()` empties the bin to zero, it unassigns and is ready for any material or item on the next trip.

### Variants

- **Portable Storage Bin**, **25** unit capacity
- **Heavy Portable Storage Bin**, **50** unit capacity

Install/uninstall at base or any outpost.

*Guide / World & Infrastructure*
