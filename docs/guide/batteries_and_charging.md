# Guide: batteries_and_charging

## Batteries & Charging

Vehicles run on batteries. A parked vehicle costs nothing, battery only drains during actions.

### What drains battery

- **Moving**, the main cost. The Rover gets much worse at high speeds; the Pioneer is more efficient, but top speed still costs extra watt-hours per meter.
- **Drilling**, draws **10-30 W** while the drill is running, depending on the drill variant (basic / Industrial / Heavy). Watts are the rate and watt-hours are the amount used: **10 W** for one hour uses **10 Wh**, and for **15** minutes uses **2.5 Wh**. See **What mining costs** below.
- **Sonar**, a small flat cost (**0.5-3 Wh**, by sonar tier) per scan or paid survey. See sonar guide for the comparison.
- **Stationary**, free. No drain.

### What mining costs

Each `self.drill.mine()` digs **1** unit, and the drill draws its power for the whole dig, so one unit costs **drill watts × mining time**. Mining time is the mineral's base time, multiplied by the drill's speed multiplier, divided by the site's purity.

| Mineral | Base time per unit |
| --- | --- |
| Iron, Silicon | 15 min |
| Lead | 18 min |
| Titanium, Cobalt | 20 min |
| Rare Earth | 25 min |
| Neutronium | 30 min |

A **rich** site digs **2×** as fast and a **pure** site **3×** as fast as a standard one.

| Drill | Power | Speed multiplier | Iron, standard site | Iron, pure site |
| --- | --- | --- | --- | --- |
| Basic | 10 W | 1.0× | 15 min, 2.5 Wh | 5 min, 0.83 Wh |
| Industrial | 20 W | 0.75× | 11.25 min, 3.75 Wh | 3.75 min, 1.25 Wh |
| Heavy | 30 W | 0.6× | 9 min, 4.5 Wh | 3 min, 1.5 Wh |

A faster drill finishes sooner but uses more energy per unit. `mine()` does not start a dig the battery cannot finish.

### The Rover's battery

- Integrated, fixed **100 Wh**. Cannot be upgraded.
- At full speed the rover burns through battery fast. At half speed, it's much more efficient. Lower throttle is better for long trips.
- A fully-charged Rover at full throttle lasts about **5 hours**. At half throttle, closer to **20**.

### The Pioneer

- No built-in battery, mount battery modules for capacity.
- More efficient drivetrain, the high-throttle penalty is gentler than the Rover's, but slower cruises still stretch range.
- Each mounted module adds to the power draw while moving.

### Querying the battery

```
level = self.battery.level()    # 0-1
wh = self.battery.wh()       # current Wh stored
cap = self.battery.capacity()   # max Wh
```

Check `level` before driving far.

### Charging & Rescue

Park within **~2 m** of a Vehicle Charging Station, anywhere inside its service area, to charge directly. The station queues docked vehicles by target level: `self.charge(vehicle_id, 0.8)` charges that vehicle until it reaches **80%**. `dispatch_rescue(vehicle, target_level)` can also send a slow field-service drone to any rover or Pioneer in the field. Your script decides the threshold and target: `0.2` for a safety bump, `0.8` before a long return trip, or `1.0` for full remote charging. `cancel_rescue()` recalls that station's active rescue drone; any charge already delivered stays on the vehicle, and the vehicle is released while the drone flies home.

A dead battery **pauses** the current route while the script is still running; it does not cancel the script's intent. If the vehicle is recharged before the script stops, it resumes course. The vehicle stops and clears its route when you press Stop, the script reaches its end, or an uncaught error occurs. A vehicle being rescue-charged stays parked until the drone finishes, detaches, or is recalled by `cancel_rescue()`.

### Charge the vehicle, or swap its batteries?

A **Vehicle Charging Station** charges a parked Rover or Pioneer directly and can send its service drone to a stranded vehicle. A **Battery Charger** charges loose Portable Batteries for a Pioneer to collect during a stop. The Rover's fixed battery cannot be swapped.

Swapping is useful on a regular delivery route: the Pioneer takes ready batteries and leaves its drained ones behind, while the charger works during the next trip. You need a spare set of the same battery types installed in that Pioneer.

### Set up a Battery Charger

Research Battery Charger, buy one and deploy it at home or a founded outpost. Supply it from the local grid, then load loose **Portable Batteries (50 Wh)** or **Heavy Portable Batteries (100 Wh)** through its input. Use Inventory at home or a local Warehouse at a remote outpost. Automated item transfers need Auto Feeders.

| Charger | Shared battery slots | Charging bays | Total charging power |
|---|---|---|---|
| Mk I | 4 | 1 | 30 W |
| Mk II | 8 | 2 | 60 W |

Slots hold all batteries, whether waiting, charging or ready. Bays determine how many charge at once. At Mk II, one active cell can use the full **60 W**; two share **30 W** each before any outpost overcrowding penalty. The charger draws no power while idle.

Charging is script-controlled. This loop belongs on the **Battery Charger** and queues newly arrived cells, including batteries left by a returning Pioneer:

```
while True:
  for cell in self.slots():
    if cell.item_id and cell.level < 1.0 and cell.target is None:
      result = self.charge(cell.index)
      if result.status != "queued":
        print(result.message)
  sleep(1)
```

A charging job continues after its script stops and pauses through a power outage. When it reaches its target, the cell is released for collection. An unfinished job reserves its cell: wait for it or call `self.stop(slot_index)` to release it with its current charge. The incoming battery does not inherit the outgoing battery's job, which is why a repeating queue script is useful.

### Exchange from the Pioneer

Drive to the charger's service area and brake. Call the exchange from the **Pioneer's** script, using your charger's actual id or display name:

```
result = self.swap_batteries("battery_charger_1", None, 0.9)
print(result.status, result.message)
```

Here `None` selects all installed batteries and `0.9` requires each replacement to be at least **90%** charged. Omit those optional arguments to request fully charged replacements for all installed batteries. Call when the Pioneer needs replenishing; the minimum is your chosen acceptance threshold.

Every selected battery needs an unqueued replacement of the **same type**. If one is missing or below the requested charge, the whole exchange is refused and nothing changes. Drained batteries take the vacated charger slots, so a full charger can still exchange a complete matching set. The transfer takes handling time; let it finish before driving away.

Ready, unqueued batteries remain usable during a grid outage, although the charger cannot replenish them until power returns. If a swap fails, check parking, matching types, charge levels, reserved charging jobs and whether either endpoint is still handling another transfer.

### Tips

- Plan trips around battery. Round trip + drilling must fit in your charge.
- Throttle down for long expeditions, lower speed extends range.
- Write a fleet manager that auto-dispatches rescues before vehicles are dead.

*Guide / Production & Logistics*
