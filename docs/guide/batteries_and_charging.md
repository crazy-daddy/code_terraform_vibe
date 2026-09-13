# Guide: batteries_and_charging

## Batteries & Charging

Vehicles run on batteries. A parked vehicle costs nothing, battery only drains during actions.

### What drains battery

- **Moving**, the main cost. The Rover gets much worse at high speeds; the Pioneer is more efficient, but top speed still costs extra watt-hours per meter.
- **Drilling**, draws **10-30 W** while the drill is running, depending on the drill variant (basic / Industrial / Heavy).
- **Sonar**, a small flat cost (**0.5-2 Wh**, by sonar tier) per scan or survey.
- **Stationary**, free. No drain.

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

### Tips

- Plan trips around battery. Round trip + drilling must fit in your charge.
- Throttle down for long expeditions, lower speed extends range.
- Write a fleet manager that auto-dispatches rescues before vehicles are dead.

*Guide / Production & Logistics*

---
