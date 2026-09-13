# Guide: plan_mode

## Using Plan Mode

Plan Mode is the visual construction-planning layer on the Planet Map. It does not build instantly. It creates persistent blueprints that a Constructor-equipped Pioneer can execute later.

### Visual planning flow

1. Open the Planet Map and turn on Plan Mode.
2. Choose a category, then choose a tool.
3. Place a blueprint where the map allows it.
4. Read the placement card and blueprint hover card for the required material.
5. Load that material into a Pioneer with a Constructor Module.
6. Send the Pioneer to the blueprint and execute construction from the Pioneer script.

### Script planning

Scripts write to the same queue through `get_component("construction_blueprint")`. Use `plan_structure(kind, x, y)` for Outposts, caps, pumps, taps, and Mining Drills; use `plan_pipe`, `plan_power_line`, and `plan_bridge` for utilities. A successful planning call places the ghost immediately without sending a vehicle there. The Pioneer is still required for the physical build.

```
plans = get_component("construction_blueprint")
result = plans.plan_structure("thermal_cap", vent.x, vent.y)
if result.status == "ok":
    print(result.blueprint_ids[0])
```

### Locked tools

Visual tools and script calls enforce the same research. Outposts have two gates: **Outpost Construction** unlocks the kit, and **Constructor Module** unlocks the Pioneer module that can build the blueprint.

### Planning habits

Keep plans small until the first one works. One blueprint plus the exact material it asks for is easier to debug than a whole remote base. Once you trust the loop, scale up to outposts, pipes, power lines, pumps, and field extractors. Internal outpost machines, including drone facilities, deploy directly from Inventory and never appear as map blueprints.

*Guide / Tutorials*

---
