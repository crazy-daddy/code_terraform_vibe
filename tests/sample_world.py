"""
Synthetic mid-game save for stub tests and step profiling (devtools/step_profile.py).

build_sample_world(size) fills a fresh game_stubs.World with a bit of
everything the stubs support: a home outpost plus remote outposts, a tiered
recipe tree (ore -> ingot -> alloy -> part -> component -> kit), Inventory and
Warehouses holding a random spread of those items, Smelters, Fabricators,
Supply Docks (home and remote) and active Earth Orders. route_scenario(size)
returns the pure dicts the drone hauler / Pioneer route planners work on
(destinations with need/buffer tiers, drill and depot sources with coords).

Sizes are guesses at a small, a typical and a sprawling save; everything is
seeded, so a size + seed always builds the same world. Numbers measured on it
are estimates for comparing code versions, not a prediction of a real save.
"""
import random

import harness
from game_stubs import Recipe, World

SIZES = {
    # outposts = remote outposts besides home; items_per_wh = distinct stacks per Warehouse
    "small": {"outposts": 1, "warehouses": 4, "items_per_wh": 15, "smelters": 3, "fabricators": 3, "docks": 2, "orders": 4,
              "route_dests": 2, "route_sources": 6, "route_items": 3},
    "medium": {"outposts": 2, "warehouses": 8, "items_per_wh": 25, "smelters": 8, "fabricators": 8, "docks": 4, "orders": 8,
               "route_dests": 3, "route_sources": 12, "route_items": 4},
    "large": {"outposts": 4, "warehouses": 14, "items_per_wh": 35, "smelters": 14, "fabricators": 14, "docks": 6, "orders": 12,
              "route_dests": 4, "route_sources": 20, "route_items": 5},
}

ORES = [f"ore_{i}" for i in range(12)]
INGOTS = [f"ingot_{i}" for i in range(12)]
ALLOYS = [f"alloy_{i}" for i in range(8)]
PARTS = [f"part_{i}" for i in range(25)]
COMPONENTS = [f"comp_{i}" for i in range(20)]
KITS = [f"kit_{i}" for i in range(15)]
ALL_ITEMS = ORES + INGOTS + ALLOYS + PARTS + COMPONENTS + KITS


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
        world.add_warehouse(f"warehouse_{i + 1}", site(i, 4), capacity=100000,
                            items={item: rnd.randint(1, 80) for item in rnd.sample(ALL_ITEMS, spec["items_per_wh"])})
    for item in rnd.sample(ALL_ITEMS, 30):
        world.inventory.add(item, rnd.randint(1, 50))
    sample.smelters = [world.add_smelter(f"smelter_{i + 1}", site(i, 4), smelt) for i in range(spec["smelters"])]
    sample.fabricators = [world.add_fabricator(f"fabricator_{i + 1}", site(i, 4), fab) for i in range(spec["fabricators"])]
    sample.docks = [world.add_supply_dock(f"supply_dock_{i + 1}", site(i, 3)) for i in range(spec["docks"])]
    orderable = PARTS + COMPONENTS + KITS + INGOTS + ALLOYS
    for i in range(spec["orders"]):
        world.add_order(f"order_{i + 1}", {item: rnd.randint(5, 40) for item in rnd.sample(orderable, rnd.randint(2, 5))})
    return sample


def route_scenario(size="medium", seed=3):
    """(dests, sources) in the shape drone_hauler._plan_haul_job() builds
    (dest: outpost_id/coords/need/buffer/deficits; source: id/coords/available).
    A Pioneer's _plan_pull_chain() takes the first dest's need/buffer."""
    spec = SIZES[size]
    rnd = random.Random(seed)
    items = ORES[:10]
    n_items = spec["route_items"]
    dests = []
    for d in range(spec["route_dests"]):
        need = {i: rnd.randint(20, 300) for i in rnd.sample(items, n_items)}
        buffer = {i: rnd.randint(20, 300) for i in rnd.sample(items, n_items)}
        dests.append({"outpost_id": f"outpost_{d + 1}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)),
                      "need": need, "buffer": buffer,
                      "deficits": {i: need.get(i, 0) + buffer.get(i, 0) for i in set(need) | set(buffer)}})
    sources = [{"kind": "drill", "id": f"drill_{k + 1}", "coords": (rnd.uniform(-900, 900), rnd.uniform(-900, 900)),
                "available": {i: rnd.randint(10, 400) for i in rnd.sample(items, rnd.randint(1, n_items))}}
               for k in range(spec["route_sources"])]
    return dests, sources
