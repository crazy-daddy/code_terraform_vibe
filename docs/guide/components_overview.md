# Guide: components_overview

## Components

Everything on this planet is a component: sensors, generators, scanners, vehicles, storage bins, smelters, the planet itself, your field journal.

There are two ways to access them:

**self**, your own machine. Every script has a `self` variable that refers to the machine it runs on. You can read state and control it.

**get_component(id)**, a shared component or another machine by its concrete instance id. Read shared state from anywhere:

```
clock = get_component("clock")
print(clock.get_elevation())
```

For instanced machines, the id is the stable programmatic identifier such as `"bio_collector_1"`, `"rover_1"`, or `"storage_bin_2"`. The card title is the display name and can be renamed; use the id in long-running scripts so renames do not break references:

```
rover_id = "rover_1"
rover = get_component(rover_id)
print(rover.nav.get_position())
```

Use the exact id from the machine card. Type names like `"bio_collector"` describe a kind of machine; they are not the same thing as the deployed machine id `"bio_collector_1"`.

### Each call is a new instance

`get_component(id)` is a factory, every call creates a fresh wrapper, like instantiating a Python class. For machines tied to a physical entity (rover, smelter, generator), wrappers all read and write through the same backing data, so it feels singleton-ish in practice: setting a value from one wrapper is visible from another.

For purely virtual components like the `transmitter`, each wrapper is independent:

```
# Fails, two separate transmitters, only the first is connected:
get_component("transmitter").connect("earth")
get_component("transmitter").transmit("weather", 42)

# Works, one transmitter, used twice:
t = get_component("transmitter")
t.connect("earth")
t.transmit("weather", 42)
```

> Wrappers are just objects. Make one, make ten, each is independent.

### Storage bins by name

Storage bins are special, you label them with the material they hold ("Iron Ore Bin", "Copper Ingot Bin"), so querying by that label reads naturally:

```
ore_bin = get_component_by_name("Iron Ore Bin")
if ore_bin.fill_percent() < 0.2:
  print("Ore running low!")
```

`get_component_by_name()` works for any uniquely named machine or outpost, but names are editable. Custom Panels share the rename namespace but are not components, so panel names are not returned here. For long-running scripts, store and use the stable id when you can.

### Fleet lookup

Use `fleet` when a script needs to monitor all vehicles or drones without hardcoding names:

```
fleet = get_component("fleet")
for unit in fleet.vehicles():
  print(unit.id, unit.name, unit.battery_level)
```

Fleet refs are read-only snapshots. Station APIs accept either `.id` or `.name`; ids are safer for rename-proof scripts. Use `get_component(id)` when you need the full component.

### The planet and your journal

Two components represent the world you're exploring: the **planet** and your **journal**.

`nocturna` is the planet itself, intrinsic data, the same for any observer:

```
planet = get_component("nocturna")
print(planet.get_name())       # "Nocturna"
b = planet.get_bounds()
print(b.min_x, b.max_x, b.min_y, b.max_y)
```

`journal` is *your* record of what you've explored, sonar writes to it, you read from it:

```
log = get_component("journal")
for site in log.discovered_sites("nocturna"):
  print(site.id, "at", site.x, site.y)

for site in log.surveyed_sites("nocturna"):
  if site.kind() == "mineral":
    print(site.id, site.item_id, site.purity)
```

Passing the planet id scopes the query, future planets will work the same way.

### Read vs control

You can read shared components from any script, check the clock, inspect inventory, or monitor a generator by its instance id.

But hardware actions belong to the machine's own script via `self`. Methods marked **self only** in DOCS won't work through `get_component()`, you'll get an error explaining why.

Every component has `.id` (programmatic identifier) and `.name` (display name). Check the Components section below for all available components and their methods.

*Commands*
