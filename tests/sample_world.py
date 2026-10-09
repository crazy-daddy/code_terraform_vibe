"""
Synthetic mid-game save for stub tests and step profiling (devtools/step_profile.py).

build_sample_world(size) fills a fresh game_stubs.World with a bit of
everything the stubs support: a home outpost plus remote outposts, a tiered
recipe tree (ore -> ingot -> alloy -> part -> component -> kit), Inventory and
Warehouses / Large Warehouses holding a random spread of those items (at
most one item per slot: 5 / 15 slots), Smelters, Fabricators,
Supply Docks (home and remote), active Earth Orders, gas and liquid Tanks,
Batteries, one power grid per outpost over its buildings, Drone Depots with
docked Drones, Pioneers and Habitats. route_scenario(size)
returns the pure dicts the drone hauler / Pioneer route planners work on
(destinations with need/buffer tiers, drill and depot sources with coords).

Sizes are guesses at a small, a typical and a sprawling save ("large" tanks,
batteries, drones, pioneers, depots and habitats follow a late-game live save's
building counts); everything is
seeded, so a size + seed always builds the same world. Numbers measured on it
are estimates for comparing code versions, not a prediction of a real save.
"""
import random

import harness
from game_stubs import Recipe, Store, World

SIZES = {
    # outposts = remote outposts besides home; warehouses includes large_warehouses of them
    "small": {"outposts": 1, "warehouses": 4, "large_warehouses": 1, "smelters": 3, "fabricators": 3, "docks": 2, "orders": 4,
              "tanks": 2, "batteries": 2, "depots": 1, "drones": 2, "pioneers": 1, "habitats": 1,
              "route_dests": 2, "route_sources": 6, "route_items": 3},
    "medium": {"outposts": 2, "warehouses": 8, "large_warehouses": 3, "smelters": 8, "fabricators": 8, "docks": 4, "orders": 8,
               "tanks": 10, "batteries": 6, "depots": 3, "drones": 6, "pioneers": 2, "habitats": 5,
               "route_dests": 3, "route_sources": 12, "route_items": 4},
    "large": {"outposts": 4, "warehouses": 14, "large_warehouses": 5, "smelters": 14, "fabricators": 14, "docks": 6, "orders": 12,
              "tanks": 35, "batteries": 18, "depots": 7, "drones": 17, "pioneers": 4, "habitats": 16,
              "route_dests": 4, "route_sources": 20, "route_items": 5},
}
# Material-locked slots per storage building, SLOT_UNITS each (docs/components/warehouse.md):
# one item per slot, so a Warehouse holds at most 5 distinct items, a Large Warehouse 15.
WAREHOUSE_SLOTS = {"warehouse": 5, "large_warehouse": 15}
SLOT_UNITS = 2000
INVENTORY_ITEMS = 30

ORES = [f"ore_{i}" for i in range(12)]
INGOTS = [f"ingot_{i}" for i in range(12)]
ALLOYS = [f"alloy_{i}" for i in range(8)]
PARTS = [f"part_{i}" for i in range(25)]
COMPONENTS = [f"comp_{i}" for i in range(20)]
KITS = [f"kit_{i}" for i in range(15)]
ALL_ITEMS = ORES + INGOTS + ALLOYS + PARTS + COMPONENTS + KITS
# Tank fluids by type (every other tank is a gas_tank); habitat species and their feed.
TANK_FLUIDS = {"gas_tank": ["steam", "oxygen", "ammonia"], "liquid_tank": ["water", "oil"]}
SPECIES = [f"species_{i}" for i in range(6)]


class SampleWorld:
    """The built world plus handles to what was placed in it."""

    def __init__(self, world, size, smelter_recipes, fabricator_recipes):
        self.world = world
        self.size = size
        self.smelter_recipes = smelter_recipes
        self.fabricator_recipes = fabricator_recipes
        self.remotes = []
        self.smelters = []
        self.fabricators = []
        self.docks = []
        self.tanks = []
        self.batteries = []
        self.grids = []
        self.depots = []
        self.drones = []
        self.pioneers = []
        self.habitats = []


def sample_recipes(seed=1):
    """(smelter recipes, fabricator recipes): 12 ore smelts, 8 alloys, then
    25 parts, 20 components and 15 kits, each tier built from the tiers below."""
    rnd = random.Random(seed)
    refined = INGOTS + ALLOYS
    smelt = [Recipe(f"smelt_{i}", {ORES[i]: 2}, INGOTS[i]) for i in range(12)]
    smelt += [Recipe(f"smelt_alloy_{i}", {INGOTS[i]: 1, INGOTS[(i + 3) % 12]: 1}, ALLOYS[i]) for i in range(8)]
    fab = [Recipe(f"craft_{p}", {rnd.choice(refined): rnd.randint(1, 4), rnd.choice(refined): rnd.randint(1, 3)}, p) for p in PARTS]
    fab += [Recipe(f"craft_{c}", {rnd.choice(PARTS): rnd.randint(1, 3), rnd.choice(PARTS): 2, rnd.choice(refined): 2}, c) for c in COMPONENTS]
    fab += [Recipe(f"craft_{k}", {rnd.choice(COMPONENTS): 2, rnd.choice(PARTS): 3, rnd.choice(COMPONENTS): 1}, k) for k in KITS]
    return smelt, fab


def build_sample_world(size="medium", seed=1):
    """A fresh World installed as the game builtins (like StubTestCase.setUp()), filled per SIZES[size]."""
    spec = SIZES[size]
    rnd = random.Random(seed)
    world = World()
    harness._install_builtins(world)
    harness._reset_module_state(world)
    smelt, fab = sample_recipes(seed)
    sample = SampleWorld(world, size, smelt, fab)
    sample.remotes = [world.add_outpost(f"outpost_{i + 1}") for i in range(spec["outposts"])]

    def site(i, remote_every):
        """Home for most machines; every remote_every-th one goes to a remote outpost."""
        if sample.remotes and i % remote_every == remote_every - 1:
            return sample.remotes[(i // remote_every) % len(sample.remotes)]
        return world.home

    for i in range(spec["warehouses"]):
        type_id = "large_warehouse" if i < spec["large_warehouses"] else "warehouse"
        slots = WAREHOUSE_SLOTS[type_id]
        store = Store(world, f"{type_id}_{i + 1}", type_id, site(i, 4), capacity=slots * SLOT_UNITS,
                      items={item: rnd.randint(1, SLOT_UNITS) for item in rnd.sample(ALL_ITEMS, rnd.randint(slots - 2, slots))})
        world.components[store.id] = store
    for item in rnd.sample(ALL_ITEMS, INVENTORY_ITEMS):
        world.inventory.add(item, rnd.randint(1, 50))
    sample.smelters = [world.add_smelter(f"smelter_{i + 1}", site(i, 4), smelt) for i in range(spec["smelters"])]
    sample.fabricators = [world.add_fabricator(f"fabricator_{i + 1}", site(i, 4), fab) for i in range(spec["fabricators"])]
    sample.docks = [world.add_supply_dock(f"supply_dock_{i + 1}", site(i, 3)) for i in range(spec["docks"])]
    orderable = PARTS + COMPONENTS + KITS + INGOTS + ALLOYS
    for i in range(spec["orders"]):
        world.add_order(f"order_{i + 1}", {item: rnd.randint(5, 40) for item in rnd.sample(orderable, rnd.randint(2, 5))})
    _add_fluids_power_units(sample, spec, rnd, site)
    return sample


def _add_fluids_power_units(sample, spec, rnd, site):
    """Tanks, batteries, depots with docked drones, pioneers, habitats, then one grid per outpost."""
    world = sample.world
    for i in range(spec["tanks"]):
        type_id = "gas_tank" if i % 2 == 0 else "liquid_tank"
        tank = world.add_tank(f"{type_id}_{i + 1}", site(i, 3), rnd.choice(TANK_FLUIDS[type_id]), type_id=type_id)
        tank._level = round(tank.capacity() * rnd.random(), 1)
        sample.tanks.append(tank)
    for i in range(spec["batteries"]):
        type_id = "battery_large" if i % 2 == 0 else "battery"
        battery = world.add_battery(f"{type_id}_{i + 1}", site(i, 3), type_id=type_id)
        battery.charge = round(battery.get_capacity() * rnd.random(), 1)
        sample.batteries.append(battery)
    sample.depots = [world.add_drone_depot(f"drone_station_large_{i + 1}", site(i, 2), "drone_station_large") for i in range(spec["depots"])]
    for i in range(spec["drones"]):
        depot = sample.depots[i % len(sample.depots)] if sample.depots else None
        station = depot.id if depot is not None and i % 4 != 3 else ""  # every 4th drone is out flying
        kind = "drone_large" if i % 3 else "drone_small"
        sample.drones.append(world.add_drone(f"{kind}_{i + 1}", depot.outpost if depot else world.home, kind,
                                             station=station, status="idle" if station else "traveling",
                                             x=rnd.uniform(-900, 900), y=rnd.uniform(-900, 900),
                                             battery_wh=round(rnd.uniform(20, 100), 1)))
    sample.pioneers = [world.add_pioneer(f"pioneer_{i + 1}", world.home) for i in range(spec["pioneers"])]
    for i in range(spec["habitats"]):
        species = SPECIES[i % len(SPECIES)]
        sample.habitats.append(world.add_habitat(f"habitat_{i + 1}", site(i, 2), species, feed_item=f"feed_{species}",
                                                 established=i % 3 != 0))
    for outpost in [world.home] + sample.remotes:
        members = [c.id for c in world.components.values() if getattr(c, "outpost", None) is outpost and not getattr(c, "_mobile", False)]
        if members:
            sample.grids.append(world.add_grid(members[0], members, consumed=round(rnd.uniform(50, 400), 1),
                                               generated=round(rnd.uniform(50, 400), 1)))


def route_scenario(size="medium", seed=3):
    """(dests, sources) in the shape drone_haul_plan._plan_haul_job() builds
    (dest: outpost_id/coords/tiers/deficits; source: id/coords/available).
    A Pioneer's _plan_pull_chain() takes the first dest's tiers."""
    spec = SIZES[size]
    rnd = random.Random(seed)
    items = ORES[:10]
    n_items = spec["route_items"]
    dests = []
    for d in range(spec["route_dests"]):
        need = {i: rnd.randint(20, 300) for i in rnd.sample(items, n_items)}
        buffer = {i: rnd.randint(20, 300) for i in rnd.sample(items, n_items)}
        dests.append({"outpost_id": f"outpost_{d + 1}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)),
                      "tiers": {harness.logistics_requests.NEED: need, harness.logistics_requests.BUFFER: buffer},
                      "deficits": {i: need.get(i, 0) + buffer.get(i, 0) for i in set(need) | set(buffer)}})
    sources = [{"kind": "drill", "id": f"drill_{k + 1}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)),
                "available": {i: rnd.randint(10, 400) for i in rnd.sample(items, rnd.randint(1, n_items))}}
               for k in range(spec["route_sources"])]
    return dests, sources
