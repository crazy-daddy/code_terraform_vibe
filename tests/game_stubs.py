"""
Shared fake game world for offline stub tests of the `lib/` modules.

Models the game API (docs/components/, docs/types/) that tests need:
outposts with Warehouses, home Inventory, Smelters, Fabricators, Supply
Docks and Earth Orders, the Data Archive (notebook), clock, console,
power control with grids and batteries, run control, the fleet with drones
and pioneers, the ship computer, the Signal Bus (comms), tanks, Steam
Turbines, Drone Depots and Habitats. Port locality follows the docs:
Inventory works at home only, and a remote machine's ports only reach
storage at its own outpost (anything else answers "not_local" /
"source_not_local" / "target_not_local" / "inventory_not_local").

Method names, parameter names and result statuses follow the real game
API in tests/game_spec.json; tests/test_stub_contract.py checks them.
Default capacities, power flags and recipes come from the same file
(machine_spec(), spec_recipe()).

Nothing here crafts, travels or moves power on its own; a test sets state
(buffers, `running`, levels, grid numbers) directly and then calls a
controller step. Extend these fakes instead of writing private ones.
"""
import copy
import json
import os
from typing import Any

SPEC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_spec.json")
_SPEC = {}


def game_spec():
    """tests/game_spec.json (devtools/extract_game_spec.py), loaded once."""
    if not _SPEC:
        with open(SPEC_PATH, encoding="utf-8") as f:
            _SPEC.update(json.load(f))
    return _SPEC


def machine_spec(type_id):
    """The machine table entry for type_id ({} when unknown)."""
    return game_spec()["machines"].get(type_id) or {}


def default_data(type_id, key, fallback):
    """machine_spec(type_id)["defaultData"][key], or fallback."""
    return (machine_spec(type_id).get("defaultData") or {}).get(key, fallback)


class Result:
    """ActionResult / TransferResult; `payload` adds the extra result fields
    (machine_id, message_id, packet, count, ...)."""

    def __init__(self, status="ok", moved: float = 0, message="", **payload):
        self.status = status
        self.moved = moved
        self.message = message
        for name, value in payload.items():
            setattr(self, name, value)

    def __getattr__(self, name) -> Any:
        """Only reached for a payload field this result lacks; declared so
        type checkers accept `result.machine_id` and friends."""
        raise AttributeError(name)

    def __repr__(self):
        return f"Result({self.status!r}, moved={self.moved})"


class Stack:
    def __init__(self, item_id, count):
        self.id = item_id
        self.count = count

    def __repr__(self):
        return f"Stack({self.id!r}, {self.count})"


class Recipe:
    def __init__(self, recipe_id, inputs, output_item, output_count=1, duration_game_hours=0.08, fluid_inputs=None, power_draw=0,
                 fluid_outputs=None, input_fluid=None, output_fluid=None):
        self.id = recipe_id
        self.name = recipe_id
        self.inputs = dict(inputs)
        self.output_item = output_item
        self.output_count = output_count
        self.duration_game_hours = duration_game_hours
        self.fluid_inputs = dict(fluid_inputs or {})
        self.power_draw = power_draw
        self.fluid_outputs = dict(fluid_outputs or {})
        self.input_fluid = input_fluid
        self.output_fluid = output_fluid

    def __repr__(self):
        return f"Recipe({self.id!r})"


SMELTER_RECIPES = [
    Recipe("smelt_iron_ingot", {"iron_ore": 1}, "iron_ingot"),
    Recipe("smelt_glass", {"silicon": 1}, "glass"),
    Recipe("smelt_titanium_ingot", {"titanium": 1}, "titanium_ingot"),
]

def _recipe_from_spec(entry):
    output = entry.get("output") or {}
    return Recipe(
        entry["id"],
        {i["itemId"]: i["count"] for i in entry.get("inputs") or []},
        output.get("itemId", ""),
        output.get("count", 1),
        entry.get("durationGameHours", 0.0),
        entry.get("fluidInputs"),
        entry.get("powerDraw", 0),
        entry.get("fluidOutputs"),
        entry.get("inputFluid"),
        entry.get("outputFluid"),
    )


def spec_recipe(recipe_id):
    """The real recipe recipe_id from the spec's recipe table, or None."""
    entry = next((r for r in game_spec()["recipes"] if r["id"] == recipe_id), None)
    return _recipe_from_spec(entry) if entry else None


def spec_recipes(machine_type):
    """Every real recipe the spec lists for machine_type."""
    return [_recipe_from_spec(r) for r in game_spec()["recipes"] if r.get("machine") == machine_type]


FABRICATOR_RECIPES = [
    Recipe("craft_gas_pipe_segment", {"iron_ingot": 2}, "gas_pipe_segment", duration_game_hours=0.1),
    Recipe("craft_power_line_segment", {"iron_ingot": 1, "glass": 1}, "power_line_segment", duration_game_hours=0.1),
    Recipe("craft_liquid_pipe_segment", {"iron_ingot": 2}, "liquid_pipe_segment", duration_game_hours=0.1),
    Recipe("craft_steel_plate", {"iron_ingot": 3}, "steel_plate", duration_game_hours=0.2),
]


class BuildingRef:
    """outpost.buildings() entry: .id / .name / .type_id / .outpost."""

    def __init__(self, component):
        self.id = component.id
        self.name = component.id
        self.type_id = component.type_id
        self.outpost = component.outpost
        self.powered = True


class OutpostRef:
    """OutpostRef snapshot: .is_home is a plain bool here (docs/types/world_and_sites.md)."""

    def __init__(self, world, outpost_id, is_home=False):
        self._world = world
        self.id = outpost_id
        self.name = outpost_id
        self.is_home = is_home
        self.x = 0.0
        self.y = 0.0

    def buildings(self, type_id=None):
        return [
            BuildingRef(component)
            for component in self._world.components.values()
            if getattr(component, "outpost", None) is self
            and getattr(component, "type_id", None)
            and not getattr(component, "_mobile", False)
            and (type_id is None or component.type_id == type_id)
        ]

    def harvesting_machines(self, type_id=None):
        return []

    def __repr__(self):
        return f"OutpostRef({self.id!r})"


class OutpostComponent:
    """`outpost_<id>` component (docs/components/outpost.md) over an OutpostRef:
    buildings_used() counts its buildings, capacity is World.building_capacity."""

    def __init__(self, world, ref):
        self._world = world
        self._ref = ref
        self.id = ref.id

    def is_home(self):
        return self._ref.is_home

    def buildings(self, type_id=None):
        return self._ref.buildings(type_id)

    def buildings_used(self):
        return len(self._ref.buildings())

    def buildings_capacity(self):
        return self._world.building_capacity


# Hot radioactive items: only a Lead Cask (or a shielded receiver) holds them.
HOT_ITEMS = ("raw_uranium", "fuel_rod")


class PassiveStore:
    """Passive storage endpoint (`passive_storage` in the spec): unit-capacity
    item store with transfer_to() to another store at the same outpost."""

    def __init__(self, world, store_id, type_id, outpost, capacity=1000, items=None):
        self._world = world
        self.id = store_id
        self.name = store_id
        self.type_id = type_id
        self.outpost = outpost
        self.capacity_units = capacity
        self.items = dict(items or {})
        self.busy = False  # True: a material endpoint lock, OutputSlot.send() answers "busy"

    def count(self, item_id):
        return self.items.get(item_id, 0)

    def _used(self):
        return sum(self.items.values())

    def _room_for(self, item_id):
        return max(0, self.capacity_units - self._used())

    def fill_percent(self):
        return self._used() / self.capacity_units if self.capacity_units else 1.0

    def transfer_to(self, target, item_id, count, properties=None, property_match=None):
        if count <= 0:
            return Result("no_op", requested=count)
        store, problem = self._world.local_store(target, self.outpost)
        if problem == "not_found":
            return Result("target_missing", requested=count)
        if store is None:
            return Result("target_not_local", requested=count)
        if store is self:
            return Result("same_storage", requested=count)
        if self.count(item_id) <= 0:
            return Result("source_empty", requested=count)
        hot = item_id in HOT_ITEMS
        if hot and not isinstance(store, LeadCask):
            return Result("hot_cargo_requires_cask", requested=count)
        if not hot and isinstance(store, LeadCask):
            return Result("cask_accepts_hot_only", requested=count)
        if isinstance(store, LeadCask) and store.material() not in ("", item_id):
            return Result("target_wrong_material", requested=count)
        if isinstance(store, StorageBin) and store.get_material() not in ("", item_id):
            return Result("target_wrong_material", requested=count)
        moved = store.add(item_id, min(count, self.count(item_id)))
        self.remove(item_id, moved)
        return Result("ok" if moved == count else ("partial" if moved > 0 else "target_full"), moved, requested=count)

    def add(self, item_id, n):
        moved = min(n, self._room_for(item_id))
        if moved > 0:
            self.items[item_id] = self.items.get(item_id, 0) + moved
        return moved

    def remove(self, item_id, n):
        moved = min(n, self.items.get(item_id, 0))
        if moved > 0:
            self.items[item_id] -= moved
            if self.items[item_id] <= 0:
                del self.items[item_id]
        return moved


class Store(PassiveStore):
    """Home Inventory or a Warehouse."""

    def capacity(self):
        return self.capacity_units

    def stacks(self):
        return [Stack(item_id, n) for item_id, n in self.items.items() if n > 0]

    def space_for(self, item_id, properties=None):
        return self._room_for(item_id)

    def materials(self):
        return sorted(i for i, n in self.items.items() if n > 0)

    def total(self):
        return self._used()

    def drop_all(self, item_id):
        n = self.items.pop(item_id, 0)
        return Result("ok" if n > 0 else "no_op", count=n)

    def compact(self):
        return Result("already_compact")


class LeadCask(PassiveStore):
    """Lead Cask: 100 units of one hot item; latches to the first item put in
    and unlatches when empty. add() refuses other or non-hot items."""
    type_id = "lead_cask"

    def __init__(self, world, cask_id, outpost, material="", count=0, capacity=100):
        super().__init__(world, cask_id, self.type_id, outpost, capacity, {material: count} if material and count else None)

    def capacity(self):
        return self.capacity_units

    def material(self):
        return next((i for i, n in self.items.items() if n > 0), "")

    def _room_for(self, item_id):
        if item_id not in HOT_ITEMS or self.material() not in ("", item_id):
            return 0
        return super()._room_for(item_id)


class StorageBin(PassiveStore):
    """Storage Bin: 500 units of one material; latches to the first item put
    in and unlatches when empty (docs/components/storage_bin.md). No
    space_for()/materials()/slots(): storage.BinStore adapts it."""
    type_id = "storage_bin"

    def __init__(self, world, bin_id, outpost, material="", count=0, capacity=500):
        super().__init__(world, bin_id, self.type_id, outpost, capacity, {material: count} if material and count else None)

    def get_material(self):
        return next((i for i, n in self.items.items() if n > 0), "")

    def get_capacity(self):
        return self.capacity_units

    def stacks(self):
        return [Stack(item_id, n) for item_id, n in self.items.items() if n > 0]

    def is_empty(self):
        return self._used() == 0

    def space(self):
        return max(0, self.capacity_units - self._used())

    def has_space(self, amount):
        return self.space() >= amount

    def _room_for(self, item_id):
        if item_id in HOT_ITEMS or self.get_material() not in ("", item_id):
            return 0
        return super()._room_for(item_id)


# Distinct materials a machine's input stockpile holds at once, per type
# (simworker `defaultItemStackSlots`); take() of a new material past it
# answers "slots_full" even with unit room left.
MATERIAL_SLOTS = {
    "fabricator": 8, "feed_maker": 8, "crop_automator": 8, "garbage_disposal": 10,
    "plant_terraformer": 6, "habitat": 5, "bio_lab": 4, "bio_caster": 4,
    "fuel_assembler": 3, "seed_maker": 3,
    "drone_station": 3, "drone_station_medium": 4, "drone_station_large": 6,
}


class Slot:
    """InputSlot / OutputSlot on a machine. `buffer` is the machine-side
    {item: units} dict the slot fills (input) or drains (output).
    `material_slots`: cap on distinct materials; defaults to the machine
    type's MATERIAL_SLOTS for its input buffer, else no cap."""

    def __init__(self, machine, buffer, capacity, material_slots=None):
        self.machine = machine
        self.buffer = buffer
        self._capacity = capacity
        self.material_slots = material_slots
        self.connected = ""
        self.connect_log = []

    # -- shared --
    def capacity(self):
        return self._capacity

    def count(self):
        return sum(self.buffer.values())

    def stacks(self):
        return [Stack(item_id, n) for item_id, n in self.buffer.items() if n > 0]

    def connected_id(self):
        return self.connected

    def connected_to(self):
        return self.connected

    def _slots_full_for(self, item_id):
        """True when item_id is a new material and every material slot is taken."""
        cap = self.material_slots
        if cap is None and self.buffer is getattr(self.machine, "input_buffer", None):
            cap = MATERIAL_SLOTS.get(getattr(self.machine, "type_id", ""))
        if cap is None or self.buffer.get(item_id, 0) > 0:
            return False
        return sum(1 for n in self.buffer.values() if n > 0) >= cap

    def _resolve(self, target_id, machines=False):
        """(store, problem) for target_id as seen from this machine's outpost;
        see World.local_store(). `machines`: an output may also reach another
        machine's input there (MachineInput)."""
        return self.machine.world.local_store(target_id, self.machine.outpost, machines)

    def connect(self, name):
        self.connect_log.append(name)
        store, problem = self._resolve(name, machines=self.buffer is getattr(self.machine, "output_buffer", None))
        if problem == "not_found":
            return Result("not_found")
        if store is None:
            return Result("not_local")
        self.connected = name
        return Result("ok")

    # -- input side --
    def take(self, item_id, count):
        store, problem = self._resolve(self.connected)
        if problem == "no_connection":
            return Result("no_connection")
        if problem == "not_found":
            return Result("source_missing")
        if problem == "not_local":
            return Result("source_not_local")
        if store is None:
            return Result("inventory_not_local")
        room = self._capacity - self.machine._input_used()
        if room <= 0:
            return Result("buffer_full")
        if self._slots_full_for(item_id):
            return Result("slots_full", requested=count)
        moved = store.remove(item_id, min(count, room))
        if moved > 0:
            self.buffer[item_id] = self.buffer.get(item_id, 0) + moved
        return Result("ok" if moved == count else ("partial" if moved > 0 else "source_empty"), moved)

    def eject(self, destination, item_id, count):
        store, problem = self._resolve(destination)
        if problem == "not_found":
            return Result("target_missing")
        if problem == "not_local":
            return Result("target_not_local")
        if store is None:
            return Result("inventory_not_local")
        n = min(count, self.buffer.get(item_id, 0))
        if n <= 0:
            return Result("source_empty")
        moved = self._unload(store, item_id, n)
        return Result("ok" if moved == count else ("partial" if moved > 0 else "target_full"), moved)

    # -- output side --
    def send(self, item_id, count):
        store, problem = self._resolve(self.connected, machines=True)
        if problem == "no_connection":
            return Result("no_connection")
        if problem == "not_found":
            return Result("target_missing")
        if problem == "not_local":
            return Result("target_not_local")
        if store is None:
            return Result("inventory_not_local")
        if getattr(store, "busy", False):
            return Result("busy")
        n = min(count, self.buffer.get(item_id, 0))
        if n <= 0:
            return Result("source_empty")
        moved = self._unload(store, item_id, n)
        return Result("ok" if moved == count else ("partial" if moved > 0 else "target_full"), moved)

    def _unload(self, store, item_id, n):
        """Moves up to n units of item_id from the buffer into store; units moved."""
        moved = store.add(item_id, n)
        if moved > 0:
            self.buffer[item_id] -= moved
            if self.buffer[item_id] <= 0:
                del self.buffer[item_id]
        return moved


class MachineInput:
    """Another machine's input reached by an OutputSlot (connect/send to a
    machine id): fills its `input_buffer` up to the input capacity and
    material slots. A Supply Dock takes only its active order's remaining
    need (docs/components/supply_dock.md). `busy` mirrors the machine's
    `input_busy` flag."""

    def __init__(self, building):
        self.building = building
        self.busy = getattr(building, "input_busy", False)

    def count(self, item_id):
        return self.building.input_buffer.get(item_id, 0)

    def add(self, item_id, n):
        slot = self.building.input
        room = slot.capacity() - self.building._input_used()
        if slot._slots_full_for(item_id):
            room = 0
        order = getattr(self.building, "order", None) if isinstance(self.building, SupplyDock) else None
        if isinstance(self.building, SupplyDock):
            owed = 0
            if order is not None:
                owed = order.requires.get(item_id, 0) - order.shipped.get(item_id, 0) - self.count(item_id)
            room = min(room, max(0, owed))
        moved = max(0, min(n, room))
        if moved > 0:
            self.building.input_buffer[item_id] = self.count(item_id) + moved
        return moved

    def remove(self, item_id, n):
        return 0


class Building:
    """Placed building with item buffers behind its ports."""
    type_id = ""

    def __init__(self, world, building_id, outpost):
        self.world = world
        self.id = building_id
        self.outpost = outpost
        self.input_buffer = {}
        self.output_buffer = {}

    def _input_used(self):
        return sum(self.input_buffer.values())


class PressureGenerator(Building):
    """pressure_generator: tier() is raised by Computer.upgrade() packs (UPGRADE_PACKS)."""
    installed_tier = 1

    def tier(self):
        return self.installed_tier


class Machine(Building):
    """Recipe machine (Smelter, Fabricator)."""

    def __init__(self, world, machine_id, outpost, recipes):
        super().__init__(world, machine_id, outpost)
        self._recipes = list(recipes)
        self.recipe = ""
        self.running = False

    def list_recipes(self):
        return list(self._recipes)

    def find_recipe(self, recipe_id):
        return next((r for r in self._recipes if r.id == recipe_id), None)

    def get_recipe(self):
        return self.recipe

    def set_recipe(self, recipe_or_id):
        recipe_id = getattr(recipe_or_id, "id", recipe_or_id)
        if self.find_recipe(recipe_id) is None:
            return Result("unknown_recipe")
        self.recipe = recipe_id
        return Result("ok")

    def clear_recipe(self):
        self.recipe = ""
        return Result("ok")

    def is_running(self):
        return self.running


class Smelter(Machine):
    type_id = "smelter"

    def __init__(self, world, machine_id, outpost, recipes=None):
        super().__init__(world, machine_id, outpost, SMELTER_RECIPES if recipes is None else recipes)
        self.input = Slot(self, self.input_buffer, 50)
        self.output = Slot(self, self.output_buffer, 50)

    def get_input_count(self):
        return sum(self.input_buffer.values())

    def get_output_count(self):
        return sum(self.output_buffer.values())


class Fabricator(Machine):
    type_id = "fabricator"

    def __init__(self, world, machine_id, outpost, recipes=None):
        super().__init__(world, machine_id, outpost, FABRICATOR_RECIPES if recipes is None else recipes)
        self.input = Slot(self, self.input_buffer, 200)
        self.output = Slot(self, self.output_buffer, 50)
        self.byproduct = None

    def get_stockpile(self):
        return dict(self.input_buffer)

    def get_stockpile_capacity(self):
        return self.input._capacity

    def get_stockpile_used(self):
        return self._input_used()

    def get_output_count(self):
        return sum(self.output_buffer.values())


class Order:
    """Earth Order (campaign or weekly): requires/shipped per item."""

    def __init__(self, order_id, requires, shipped=None, reward_kind="credits"):
        self.id = order_id
        self.name = order_id
        self.requires = dict(requires)
        self.shipped = dict(shipped or {})
        self.status = "active"
        self.reward_kind = reward_kind
        self.reward_credits = 100
        self.reward_label = ""
        self.kind = "campaign"
        self.expires_day = None
        self.contractor_id = None


class Orders:
    """`orders` service: campaign orders only (no weekly ones). `upcoming` holds
    queued campaign orders in queue order (list_upcoming_orders())."""

    def __init__(self):
        self.orders = {}
        self.upcoming = []

    def list_orders(self):
        return list(self.orders.values())

    def list_upcoming_orders(self):
        return list(self.upcoming)

    def list_weekly_orders(self):
        return []

    def get_order(self, order_id):
        return self.orders.get(order_id)


class DockSlot:
    def __init__(self, index, item_id, count):
        self.index = index
        self.item_id = item_id
        self.count = count


class SupplyDock(Building):
    """Supply Dock: input port loads cargo into `input_buffer`; set_order()
    rejects while cargo is present. Nothing ships on its own."""
    type_id = "supply_dock"

    def __init__(self, world, dock_id, outpost):
        super().__init__(world, dock_id, outpost)
        self.input = Slot(self, self.input_buffer, 200)
        self.order = None
        self.enabled = False
        self.input_busy = False

    def current_order(self):
        return self.order

    def set_order(self, order_id):
        if self.total() > 0:
            return Result("cargo_present")
        order = self.world.services["orders"].get_order(order_id)
        if order is None:
            return Result("unknown_order")
        if order.status == "completed":
            return Result("completed")
        self.order = order
        return Result("ok")

    def clear_order(self):
        self.order = None
        return Result("ok")

    def count(self, item_id):
        return self.input_buffer.get(item_id, 0)

    def total(self):
        return sum(self.input_buffer.values())

    def slots(self):
        return [DockSlot(index, i, n) for index, (i, n) in enumerate(self.input_buffer.items()) if n > 0]

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, on):
        self.enabled = on
        return Result("ok")

    def dispatch_rate(self):
        return 25.0

    def current_dispatch(self):
        return None

    def dispatch_progress(self):
        return 0.0


class Notebook:
    """Data Archive: JSON-ish key/value store with transaction()."""

    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return copy.deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.data[key] = copy.deepcopy(value)
        return Result("ok")

    def has(self, key):
        return key in self.data

    def transaction(self, key, default, updater):
        current = copy.deepcopy(self.data.get(key, default))
        self.data[key] = copy.deepcopy(updater(current))
        return Result("ok")

    def delete(self, key):
        self.data.pop(key, None)
        return Result("ok")

    def keys(self, prefix=None):
        return [key for key in self.data if prefix is None or key.startswith(prefix)]


class Clock:
    def __init__(self, seconds_per_hour=25.0):
        self.now = 1000
        self.hours = 0.0
        self.seconds_per_hour = seconds_per_hour
        self.day = 1
        self.elevation = 0.0

    def tick(self):
        return self.now

    def get_day(self):
        return self.day

    def get_elevation(self):
        return self.elevation

    def elapsed_game_hours(self):
        return self.hours

    def real_seconds_per_hour(self):
        return self.seconds_per_hour


class Commander:
    def __init__(self, credits=0):
        self.credits = credits

    def get_credits(self):
        return self.credits


class ShopItem:
    def __init__(self, item_id, cost):
        self.id = item_id
        self.name = item_id
        self.cost = cost


class Shop:
    """`shop`: catalogue prices; buy() debits the commander and puts the
    purchase in Inventory (all or nothing); sell() takes units from Inventory
    and credits the commander at the same price. `sold` totals the sales."""

    def __init__(self, world, prices=None, not_sellable=()):
        self._world = world
        self.prices = dict(prices or {})
        self.not_sellable = set(not_sellable)
        self.sold = {}

    def get_catalogue(self):
        return [ShopItem(i, c) for i, c in self.prices.items()]

    def buy(self, item_id, quantity=1):
        cost = self.prices.get(item_id, 0) * quantity
        commander = self._world.services["commander"]
        if commander.credits < cost:
            return Result("insufficient_credits")
        inventory = self._world.inventory
        if inventory.space_for(item_id) < quantity:
            return Result("inventory_full")
        commander.credits -= cost
        inventory.add(item_id, quantity)
        return Result("ok")

    def sell(self, item_id, quantity=1):
        if item_id in self.not_sellable:
            return Result("not_sellable")
        inventory = self._world.inventory
        if inventory.count(item_id) < quantity:
            return Result("no_stock")
        inventory.remove(item_id, quantity)
        credits = self.prices.get(item_id, 0) * quantity
        self._world.services["commander"].credits += credits
        self.sold[item_id] = self.sold.get(item_id, 0) + quantity
        return Result("ok", item_id=item_id, units=quantity, credits=credits)


class Console:
    def __init__(self):
        self.lines = []
        self.time_of_day = "12:00:00"

    def now(self):
        return self.time_of_day

    def print(self, message, level="info", **_kwargs):
        self.lines.append((level, message))

    def text(self, level=None):
        return "\n".join(m for lv, m in self.lines if level is None or lv == level)


class OutpostNetwork:
    def __init__(self, world):
        self._world = world

    def home(self):
        return self._world.home

    def outposts(self):
        return list(self._world.outposts.values())

    def nearest(self, x, y):
        outposts = self.outposts()
        return min(outposts, key=lambda o: (o.x - x) ** 2 + (o.y - y) ** 2) if outposts else None


class Journal:
    """Site and creature lists are test-set; the planet id is ignored."""

    def __init__(self, surveyed=(), discovered=(), creatures=()):
        self.surveyed = list(surveyed)
        self.discovered = list(discovered)
        self.creatures = list(creatures)

    def surveyed_sites(self, planet_id):
        return list(self.surveyed)

    def discovered_sites(self, planet_id):
        return list(self.discovered)

    def cataloged_creatures(self, planet_id):
        return list(self.creatures)


class WildlifeSensor:
    """get_value() returns the test-set population; `broken` makes it raise."""

    def __init__(self, population=0):
        self.population = population
        self.broken = False

    def get_value(self):
        if self.broken:
            raise RuntimeError("wildlife_sensor unpowered")
        return self.population


class Construction:
    def __init__(self, job_id, required_item, required_count):
        self.id = job_id
        self.required_item = required_item
        self.required_count = required_count


class Site:
    """Surveyed site (journal.surveyed_sites()): kind, coordinates, the pump/cap
    on it, a mineral site's ore, hardness and purity, and a thermal vent's
    phase (test-set `_phase`), rate (wide) and cycle timing (deep). An
    "inert" site is a GeologicalAnomaly with its learned `seismic_status`."""

    def __init__(self, kind, x=0.0, y=0.0, machine="", medium=None, item_id=None, hardness=1, purity="standard", site_id="",
                 phase=None, steam_rate=None, cycle=None, seismic_status="unscanned"):
        self._kind = kind
        self.x = x
        self.y = y
        self._machine = machine
        self._medium = medium
        self.item_id = item_id
        self.hardness = hardness
        self.purity = purity
        self.id = site_id
        self._phase = phase
        self._steam_rate = steam_rate
        self._cycle = cycle  # (active, dormant) minutes once Deep-surveyed, else None
        self.seismic_status = seismic_status

    def current_phase(self):
        return self._phase

    def base_steam_rate(self):
        return self._steam_rate

    def cycle_active_minutes(self):
        return self._cycle[0] if self._cycle else None

    def cycle_dormant_minutes(self):
        return self._cycle[1] if self._cycle else None

    def kind(self):
        return self._kind

    def pump_id(self):
        return self._machine

    def cap_id(self):
        return self._machine

    def has_cap(self):
        return bool(self._machine)

    def medium(self):
        return self._medium


class ConstructionBlueprints:
    """`deconstructs` records mark_deconstruct() targets; marking one twice answers already_queued."""

    def __init__(self):
        self.pending = []
        self.deconstructs = []

    def mark_deconstruct(self, x, y, layer="auto", target_id=""):
        key = (x, y, layer, target_id)
        if key in self.deconstructs:
            return Result("already_queued")
        self.deconstructs.append(key)
        return Result("ok")

    def pending_constructions(self):
        return list(self.pending)

    def active_constructions(self):
        return []

    def paused_constructions(self):
        return []


class Position:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

    def __iter__(self):
        return iter((self.x, self.y))


class FluidConnection:
    """One link of a FluidPort (connections()): the machine at the other end
    and the fluid on the link (None while nothing flows)."""

    def __init__(self, machine_id, fluid=None, state="ready", declared_by=""):
        self.machine_id = machine_id
        self.machine_name = machine_id
        self.fluid = fluid
        self.state = state
        self.declared_by = declared_by


class FluidPort:
    """FluidPort (gas/liquid in or out): a level/capacity buffer and one
    connection. connect() answers "not_found" for an id that is no component.
    `links` (FluidConnection) are what connections() reports while connected."""

    def __init__(self, world, level=0.0, capacity=100.0, connected=""):
        self._world = world
        self._level = level
        self._capacity = capacity
        self.connected = connected
        self.flow = 0.0
        self.links = []
        self.connect_log = []
        self.disconnects = 0

    def level(self):
        return self._level

    def capacity(self):
        return self._capacity

    def flow_rate(self):
        return self.flow

    def connected_id(self):
        return self.connected

    def connected_to(self):
        return self.connected

    def connections(self):
        return list(self.links) if self.connected else []

    def connect(self, target):
        self.connect_log.append(target)
        if target not in self._world.components:
            return Result("not_found")
        self.connected = target
        return Result("ok")

    def disconnect(self):
        self.disconnects += 1
        self.connected = ""
        return Result("ok")


class Tank(Building):
    """Gas Tank / Liquid Tank (type_id), capacity from the spec; a `liquid_in`
    FluidPort when the spec has one (Large Liquid Tank)."""

    def __init__(self, world, tank_id, outpost, type_id="liquid_tank", fluid="", level=0.0, capacity=None):
        super().__init__(world, tank_id, outpost)
        self.type_id = type_id
        self._fluid = fluid
        self._level = level
        self._capacity = default_data(type_id, "capacity", 100) if capacity is None else capacity
        self.inflow = 0.0
        self.outflow = 0.0
        intake = default_data(type_id, "liquid_in_capacity", None)
        if intake is not None:
            self.liquid_in = FluidPort(world, 0.0, intake)

    def fluid(self):
        return self._fluid if self._level > 0 else ""

    def level(self):
        return self._level

    def capacity(self):
        return self._capacity

    def fill_pct(self):
        return self._level / self._capacity if self._capacity else 0.0

    def is_empty(self):
        return self._level <= 0

    def is_full(self):
        return self._level >= self._capacity

    def inflow_rate(self):
        return self.inflow

    def outflow_rate(self):
        return self.outflow


class BatteryBank(Building):
    """Battery / Large Battery building: charge and capacity in Wh."""

    def __init__(self, world, battery_id, outpost, type_id="battery", charge=0.0, capacity=None):
        super().__init__(world, battery_id, outpost)
        self.type_id = type_id
        self.charge = charge
        self._capacity = default_data(type_id, "capacity", 500) if capacity is None else capacity

    def get_level(self):
        return self.charge

    def get_capacity(self):
        return self._capacity


class SteamTurbine(Building):
    type_id = "steam_turbine"

    def __init__(self, world, turbine_id, outpost, steam=0.0, source="", output=0.0, stalled=False, throttle=0.0):
        super().__init__(world, turbine_id, outpost)
        self.steam_in = FluidPort(world, steam, default_data(self.type_id, "steam_in_capacity", 100), source)
        self.output = output
        self.stalled = stalled
        self._throttle = throttle

    def power_output(self):
        return self.output

    def is_stalled(self):
        return self.stalled

    def throttle(self):
        return self._throttle

    def set_throttle(self, t):
        self._throttle = max(0.0, min(1.0, t))
        return Result("ok")

    def efficiency(self):
        return 1.0 if self.output > 0 else 0.0


class PowerGridMember:
    """Snapshot of one machine on a grid; `stored`/`capacity` are a battery's Wh."""

    def __init__(self, component, powered):
        self.id = component.id
        self.name = getattr(component, "name", component.id)
        self.type_id = component.type_id
        self.outpost_id = component.outpost.id if component.outpost else ""
        self.powered = powered
        self.consumed = 0.0
        power_output = getattr(component, "power_output", None)
        self.generated = power_output() if callable(power_output) else 0.0
        self.stored = component.charge if isinstance(component, BatteryBank) else 0.0
        self.capacity = component.get_capacity() if isinstance(component, BatteryBank) else 0.0
        self.reserve_stored = 0.0
        self.reserve_capacity = 0.0
        self.roles = []


class PowerGrid:
    """One grid. `members` are rebuilt from the world on each read; battery
    charge (`stored` / `capacity`) sums the member BatteryBanks unless the test
    set it. `consumed` / `generated` are whatever the test set."""

    def __init__(self, world, anchor_id, machine_ids, consumed=0.0, generated=0.0, stored=None, capacity=None):
        self._world = world
        self.anchor_id = anchor_id
        self.machine_ids = list(machine_ids)
        self.consumed = consumed
        self.generated = generated
        self._stored = stored
        self._capacity = capacity
        self.reserve_stored = 0.0
        self.reserve_capacity = 0.0

    @property
    def members(self):
        power = self._world.get_component("power_control")
        components = (self._world.components.get(i) for i in self.machine_ids)
        return [PowerGridMember(c, power.is_powered(c.id)) for c in components if c is not None]

    @property
    def stored(self):
        return sum(m.stored for m in self.members) if self._stored is None else self._stored

    @property
    def capacity(self):
        return sum(m.capacity for m in self.members) if self._capacity is None else self._capacity

    @property
    def net(self):
        return self.generated - self.consumed

    @property
    def has_generator(self):
        return any(machine_spec(m.type_id).get("category") == "power" and not isinstance(self._world.components.get(m.id), BatteryBank) for m in self.members)

    @property
    def outpost_ids(self):
        return sorted({m.outpost_id for m in self.members if m.outpost_id})


class PowerSummary:
    def __init__(self, grids):
        self.grid_count = len(grids)
        self.consumed = sum(g.consumed for g in grids)
        self.generated = sum(g.generated for g in grids)
        self.stored = sum(g.stored for g in grids)
        self.capacity = sum(g.capacity for g in grids)
        self.net = self.generated - self.consumed
        self.reserve_stored = 0.0
        self.reserve_capacity = 0.0


class PowerControl:
    """`power_control`: grids the test added (World.add_grid) and per-machine
    power switches (default on). can_power_off follows the spec's canPowerOff."""

    def __init__(self, world):
        self._world = world
        self.grid_list = []
        self.powered = {}
        self.calls = []

    def grids(self):
        return list(self.grid_list)

    def grid(self, target_id):
        return next((g for g in self.grid_list if target_id == g.anchor_id or target_id in g.machine_ids), None)

    def total(self):
        return PowerSummary(self.grid_list)

    def is_powered(self, machine_id):
        return self.powered.get(machine_id, True)

    def can_power_off(self, machine_id):
        component = self._world.components.get(machine_id)
        return bool(component is not None and machine_spec(getattr(component, "type_id", "")).get("canPowerOff"))

    def set_powered(self, machine_id, on):
        self.calls.append((machine_id, on))
        if machine_id not in self._world.components:
            return Result("not_found")
        if not self.can_power_off(machine_id):
            return Result("not_toggleable")
        self.powered[machine_id] = on
        return Result("ok")


class RunControl:
    """`run_control`: which machines' scripts run (a set of ids). status() reads
    `states[id]` when set, else "running"/"idle" from `running`."""

    def __init__(self, world):
        self._world = world
        self.running = set()
        self.states = {}

    def status(self, machine_id, slot=0):
        if machine_id not in self._world.components:
            raise ReferenceError(machine_id)
        state = self.states.get(machine_id) or ("running" if machine_id in self.running else "idle")
        return type("RunControlStatus", (), {"state": state, "script_id": "", "variant_id": "", "variant_name": ""})()

    def is_running(self, machine_id):
        return machine_id in self.running

    def start(self, machine_id):
        if machine_id not in self._world.components:
            return Result("not_found")
        if machine_id in self.running:
            return Result("already_running")
        self.running.add(machine_id)
        return Result("ok")

    def stop(self, machine_id):
        if machine_id not in self._world.components:
            return Result("not_found")
        self.running.discard(machine_id)
        return Result("ok")


class BroadcastInfo:
    def __init__(self, value, sender, age_seconds):
        self.value = value
        self.sender = sender
        self.age_seconds = age_seconds


class CommsMessage:
    def __init__(self, message_id, sender, tick, value):
        self.id = message_id
        self.sender = sender
        self.tick = tick
        self.value = value


class Comms:
    """`comms` (Signal Bus): broadcasts and per-channel message queues.
    Broadcast ages do not advance; a test sets one with publish()."""

    def __init__(self, world):
        self._world = world
        self.broadcasts = {}
        self.queues = {}
        self._next_id = 1

    @staticmethod
    def _valid(channel):
        return isinstance(channel, str) and channel != ""

    def publish(self, channel, value, age_seconds=0.0, sender=None):
        """Test helper: a broadcast as if sent age_seconds ago."""
        self.broadcasts[channel] = BroadcastInfo(copy.deepcopy(value), sender, age_seconds)

    def broadcast(self, channel, value):
        if not self._valid(channel):
            return Result("invalid_channel")
        self.publish(channel, value)
        return Result("ok")

    def latest(self, channel):
        info = self.broadcasts.get(channel)
        return copy.deepcopy(info.value) if info else None

    def latest_info(self, channel):
        return self.broadcasts.get(channel)

    def channels(self):
        return sorted(set(self.broadcasts) | {c for c, q in self.queues.items() if q})

    def send(self, channel, value):
        if not self._valid(channel):
            return Result("invalid_channel")
        message = CommsMessage(self._next_id, "", self._world.clock.now, copy.deepcopy(value))
        self._next_id += 1
        self.queues.setdefault(channel, []).append(message)
        return Result("ok", message_id=message.id)

    def pending(self, channel):
        return list(self.queues.get(channel, []))

    def queue_size(self, channel):
        return len(self.queues.get(channel, []))

    def receive(self, channel, message_id=None):
        if not self._valid(channel):
            return Result("invalid_channel", packet=None)
        queue = self.queues.get(channel, [])
        if not queue:
            return Result("empty", packet=None)
        message = next((m for m in queue if message_id is None or m.id == message_id), None)
        if message is None:
            return Result("not_found", packet=None)
        queue.remove(message)
        return Result("ok", packet=message)

    def cancel(self, channel, message_id):
        if not self._valid(channel):
            return Result("invalid_channel")
        queue = self.queues.get(channel, [])
        message = next((m for m in queue if m.id == message_id), None)
        if message is None:
            return Result("not_found")
        queue.remove(message)
        return Result("ok")

    def clear(self, channel):
        if not self._valid(channel):
            return Result("invalid_channel", count=0)
        count = len(self.queues.pop(channel, []))
        return Result("ok" if count else "no_op", count=count)


class MountSlot:
    def __init__(self, index, slot_type, module_id=None, internal_items=()):
        self.index = index
        self.type = slot_type
        self.module_id = module_id
        self.internal_items = list(internal_items)
        self.internal_count = len([i for i in self.internal_items if i])


class SonarModule:
    """Mounted sonar's read-only queries (sonar_module.md): tier name, hardness limit, range in m."""

    def __init__(self, tier="basic", hardness_limit=2, range_m=50.0):
        self._tier = tier
        self._hardness_limit = hardness_limit
        self._range = range_m

    def tier(self):
        return self._tier

    def hardness_limit(self):
        return self._hardness_limit

    def range(self):
        return self._range


class Cargo:
    """Pioneer Cargo / drone DroneCargo: units per item up to a capacity."""

    def __init__(self, capacity=0, items=None):
        self._capacity = capacity
        self.items = dict(items or {})

    def capacity(self):
        return self._capacity

    def count(self):
        return sum(self.items.values())

    def full(self):
        return self.count() >= self._capacity

    def contents(self):
        return {i: n for i, n in self.items.items() if n > 0}

    def stacks(self):
        return [Stack(i, n) for i, n in self.items.items() if n > 0]

    def space_for(self, item_id):
        return max(0, self._capacity - self.count())


class VehicleBattery:
    """A pioneer's Battery: level() is a 0-1 fraction, wh() the charge."""

    def __init__(self, capacity_wh=0.0, wh=0.0):
        self._capacity = capacity_wh
        self._wh = wh

    def capacity(self):
        return self._capacity

    def wh(self):
        return self._wh

    def level(self):
        return self._wh / self._capacity if self._capacity else 0.0

    def holders(self):
        return []


class DroneBattery:
    """A drone's DroneBattery: level() is the charge in Wh, percent() 0-1."""

    def __init__(self, capacity_wh=0.0, wh=0.0):
        self._capacity = capacity_wh
        self._wh = wh

    def capacity(self):
        return self._capacity

    def level(self):
        return self._wh

    def percent(self):
        return self._wh / self._capacity if self._capacity else 0.0


class MobileUnit:
    """Shared state of a drone or pioneer: status, station, position (x, y), mounts."""
    _mobile = True
    category = ""

    def __init__(self, world, unit_id, outpost, type_id, station="", status="idle", x=0.0, y=0.0, slots=()):
        self.world = world
        self.id = unit_id
        self.name = unit_id
        self.outpost = outpost
        self.type_id = type_id
        self.station = station
        self._status = status
        self.x = x
        self.y = y
        self.slots = list(slots)
        self.rescue = ""
        self.cargo = Cargo(0)

    def status(self):
        return self._status

    def current_station(self):
        return self.station

    def modules(self):
        return list(self.slots)

    def is_being_rescued(self):
        return self.rescue != ""

    def rescue_status(self):
        return self.rescue


class Rover(MobileUnit):
    """Rover with ROVER_SLOTS empty universal slots unless `slots` is given."""
    category = "vehicle"
    type_id = "rover"
    ROVER_SLOTS = 3

    def __init__(self, world, rover_id, outpost, station="", **unit):
        unit.setdefault("slots", [MountSlot(i, "universal") for i in range(self.ROVER_SLOTS)])
        super().__init__(world, rover_id, outpost, "rover", station, **unit)

    def mount(self, slot_index, item_id):
        """Self-only: the module comes from Inventory into an empty slot."""
        slot = next((s for s in self.slots if s.index == slot_index), None)
        if slot is None:
            return Result("invalid_slot")
        if slot.module_id is not None:
            return Result("slot_occupied")
        if self.world.inventory.count(item_id) < 1:
            return Result("item_not_in_inventory")
        self.world.inventory.remove(item_id, 1)
        slot.module_id = item_id
        return Result("ok")


class Drone(MobileUnit):
    category = "drone"

    def __init__(self, world, drone_id, outpost, kind="drone_small", station="", engine="electric", battery_wh=100.0, battery_capacity=100.0, cargo_capacity=0, **unit):
        super().__init__(world, drone_id, outpost, kind, station, **unit)
        self.engine = engine
        self.battery = DroneBattery(battery_capacity, battery_wh)
        self.cargo._capacity = cargo_capacity

    def position(self):
        return Position(self.x, self.y)


class Pioneer(MobileUnit):
    category = "vehicle"
    type_id = "pioneer"

    def __init__(self, world, pioneer_id, outpost, station="", battery_wh=1000.0, battery_capacity=1000.0, cargo_capacity=0, **unit):
        super().__init__(world, pioneer_id, outpost, "pioneer", station, **unit)
        self.battery = VehicleBattery(battery_capacity, battery_wh)
        self.cargo._capacity = cargo_capacity
        self.drill: object = None  # a test sets a DrillModule-like object

    # Bays of a Battery Holder / Cargo Rack (equipment_modules.md).
    CONTAINER_BAYS = {
        "battery_holder_small": 1, "battery_holder_medium": 2, "battery_holder_large": 3,
        "cargo_rack_small": 1, "cargo_rack_medium": 2, "cargo_rack_large": 3,
    }

    def _slot(self, slot_index):
        return next((s for s in self.slots if s.index == slot_index), None)

    def mount(self, slot_index, item_id):
        """Self-only: the module comes from Inventory into an empty slot; a container gets empty bays."""
        slot = self._slot(slot_index)
        if slot is None:
            return Result("invalid_slot")
        if slot.module_id is not None:
            return Result("slot_occupied")
        if self.world.inventory.count(item_id) < 1:
            return Result("item_not_in_inventory")
        self.world.inventory.remove(item_id, 1)
        slot.module_id = item_id
        slot.internal_items = [None] * self.CONTAINER_BAYS.get(item_id, 0)
        return Result("ok")

    def install(self, slot_index, internal_index, item_id):
        """Self-only: a portable from Inventory into an empty container bay."""
        slot = self._slot(slot_index)
        if slot is None or slot.module_id is None:
            return Result("invalid_slot")
        if not 0 <= internal_index < len(slot.internal_items) or slot.internal_items[internal_index] is not None:
            return Result("invalid_internal_slot")
        if self.world.inventory.count(item_id) < 1:
            return Result("item_not_in_inventory")
        self.world.inventory.remove(item_id, 1)
        slot.internal_items[internal_index] = item_id
        slot.internal_count += 1
        return Result("ok")

    def uninstall(self, slot_index, internal_index):
        """Self-only: the portable in a container bay goes to Inventory."""
        slot = self._slot(slot_index)
        if slot is None:
            return Result("invalid_slot")
        if slot.module_id is None:
            return Result("slot_empty")
        if not 0 <= internal_index < len(slot.internal_items):
            return Result("invalid_internal_slot")
        item_id = slot.internal_items[internal_index]
        if item_id is None:
            return Result("internal_slot_empty")
        if self.world.inventory.space_for(item_id) < 1:
            return Result("inventory_full")
        self.world.inventory.add(item_id, 1)
        slot.internal_items[internal_index] = None
        slot.internal_count -= 1
        return Result("ok")

    def unmount(self, slot_index):
        """Self-only: the module goes to Inventory; its bays must be empty."""
        slot = self._slot(slot_index)
        if slot is None:
            return Result("invalid_slot")
        if slot.module_id is None:
            return Result("slot_empty")
        if any(slot.internal_items):
            return Result("holder_not_empty")
        if self.world.inventory.space_for(slot.module_id) < 1:
            return Result("inventory_full")
        self.world.inventory.add(slot.module_id, 1)
        slot.module_id = None
        slot.internal_items = []
        return Result("ok")


class UnitRef:
    """DroneRef / VehicleRef / MobileUnitRef snapshot of a MobileUnit."""

    def __init__(self, unit):
        self.id = unit.id
        self.name = unit.name
        self.kind = unit.type_id
        self.category = unit.category
        self.status = unit.status()
        self.current_station = unit.station
        self.is_docked = unit.station != ""
        self.is_being_rescued = unit.is_being_rescued()
        self.rescue_status = unit.rescue
        self.x = unit.x
        self.y = unit.y
        self.engine = getattr(unit, "engine", "")

    def position(self):
        return Position(self.x, self.y)


class Research:
    """`research`: is_unlocked() answers from `unlocked` (research_* ids)."""

    def __init__(self):
        self.unlocked = set()

    def is_unlocked(self, research_id):
        return research_id in self.unlocked


class Fleet:
    """`fleet`: refs built from the Drone / Pioneer / Rover components."""

    def __init__(self, world):
        self._world = world

    def _units(self, cls):
        return [UnitRef(c) for c in self._world.components.values() if isinstance(c, cls)]

    def drones(self):
        return self._units(Drone)

    def vehicles(self):
        return self._units(Pioneer) + self._units(Rover)

    def mobile_units(self):
        return self._units(MobileUnit)


# Storage buildings Computer.deploy() places from a kit: Warehouse type -> unit capacity.
DEPLOYABLE_STORES = {"warehouse": 20000, "large_warehouse": 30000}
# Tank types Computer.deploy() places from a kit (capacity from the spec).
DEPLOYABLE_TANKS = ("liquid_tank", "bulk_liquid_reservoir")


# Deploy kit -> (machine type, types it upgrades in place), simworker `upgradesInPlaceFrom`.
IN_PLACE_KITS = {
    "drone_station_kit_medium": ("drone_station_medium", ("drone_station",)),
    "drone_station_kit_large": ("drone_station_large", ("drone_station", "drone_station_medium")),
}
# Upgrade pack -> (machine type, tier it raises to).
UPGRADE_PACKS = {"pressure_upgrade_pack_mk2": ("pressure_generator", 2)}
DEPOT_KIT_BY_TYPE = {"drone_station": "drone_station_kit", "drone_station_medium": "drone_station_kit_medium", "drone_station_large": "drone_station_kit_large"}


class Computer:
    """`computer` (ship computer): deploy() turns an Inventory kit into a
    Drone (chassis ids), Pioneer, Rover, Warehouse, Liquid Tank or any other
    machine of the spec (a plain Building at the outpost); undeploy() refuses a
    loaded Warehouse (cargo_present), drops a tank's fluid, removes any machine and returns
    its kit (type_id), plus a unit's mounted modules and portables, to Inventory.
    `forced_status` makes every call answer that status instead."""

    def __init__(self, world):
        self._world = world
        self.calls = []
        self.forced_status: str | None = None

    def deploy(self, item_id, outpost=None):
        self.calls.append(("deploy", item_id, outpost))
        if self.forced_status:
            return Result(self.forced_status, machine_id=None)
        world = self._world
        if world.inventory.count(item_id) <= 0:
            return Result("no_kit", machine_id=None)
        if not machine_spec(item_id) and item_id not in DEPLOYABLE_STORES and item_id not in DEPLOYABLE_TANKS:
            return Result("not_deployable", machine_id=None)
        target = world.outposts.get(getattr(outpost, "id", outpost)) if outpost is not None else world.home
        if target is None:
            return Result("location_not_found", machine_id=None)
        world.inventory.remove(item_id, 1)
        prefix = machine_spec(item_id).get("instancePrefix") or item_id
        new_id = next(f"{prefix}_{n}" for n in range(1, len(world.components) + 2) if f"{prefix}_{n}" not in world.components)
        if item_id == "pioneer":
            world.add_pioneer(new_id, target)
        elif item_id == "rover":
            world.add_rover(new_id, target)
        elif item_id in DEPLOYABLE_STORES:
            world.add_warehouse(new_id, target, capacity=DEPLOYABLE_STORES[item_id]).type_id = item_id
        elif item_id in DEPLOYABLE_TANKS:
            world.add_tank(new_id, target, type_id=item_id)
        elif prefix == "drone":
            world.add_drone(new_id, target, kind=item_id)
        else:
            world.add_building(new_id, target, item_id, PressureGenerator if item_id == "pressure_generator" else Building)
        return Result("ok", machine_id=new_id)

    def upgrade(self, item_id, machine):
        """The in-place Drone Depot kits (IN_PLACE_KITS) and the UPGRADE_PACKS, else not_upgrade_item."""
        self.calls.append(("upgrade", item_id, machine))
        if self.forced_status:
            return Result(self.forced_status)
        if item_id not in IN_PLACE_KITS and item_id not in UPGRADE_PACKS:
            return Result("not_upgrade_item")
        unit = self._world.components.get(getattr(machine, "id", machine))
        if unit is None:
            return Result("not_found")
        if self._world.inventory.count(item_id) <= 0:
            return Result("item_not_in_inventory")
        if item_id in UPGRADE_PACKS:
            type_id, tier = UPGRADE_PACKS[item_id]
            if getattr(unit, "type_id", "") != type_id:
                return Result("wrong_machine_type")
            if not isinstance(unit, PressureGenerator):
                return Result("wrong_machine_type")
            if unit.tier() >= tier:
                return Result("tier_too_high")
            if unit.tier() < tier - 1:
                return Result("tier_not_ready")
            self._world.inventory.remove(item_id, 1)
            unit.installed_tier = tier
            return Result("ok")
        new_type, from_types = IN_PLACE_KITS[item_id]
        if getattr(unit, "type_id", "") not in from_types:
            return Result("wrong_machine_type")
        self._world.inventory.remove(item_id, 1)
        self._world.inventory.add(DEPOT_KIT_BY_TYPE[unit.type_id], 1)
        unit.type_id = new_type
        if isinstance(unit, DroneDepot):
            unit.bays = default_data(new_type, "bays", unit.bays)
        return Result("ok")

    def undeploy(self, machine):
        self.calls.append(("undeploy", machine))
        if self.forced_status:
            return Result(self.forced_status)
        unit = self._world.components.get(getattr(machine, "id", machine))
        if unit is None or not getattr(unit, "type_id", ""):
            return Result("not_found")
        if isinstance(unit, Store) and unit.type_id in DEPLOYABLE_STORES:
            if unit.total() > 0:
                return Result("cargo_present")
        elif isinstance(unit, StorageBin):
            if not unit.is_empty():
                return Result("cargo_present")
        elif isinstance(unit, PassiveStore):
            return Result("not_undeployable")
        cargo = getattr(unit, "cargo", None)
        if isinstance(cargo, Cargo) and cargo.count() > 0:
            return Result("cargo_present")
        del self._world.components[unit.id]
        mounts = unit.slots if isinstance(unit, MobileUnit) else []
        for item_id in [unit.type_id] + [i for s in mounts for i in [s.module_id] + s.internal_items]:
            if item_id:
                self._world.inventory.add(item_id, 1)
        return Result("ok")

    def decommission(self, outpost):
        self.calls.append(("decommission", outpost))
        if self.forced_status:
            return Result(self.forced_status)
        target = self._world.outposts.get(getattr(outpost, "id", outpost))
        if target is None:
            return Result("not_found")
        if target.is_home:
            return Result("is_home")
        if any(getattr(c, "outpost", None) is target for c in self._world.components.values()):
            return Result("not_empty")
        del self._world.outposts[target.id]
        return Result("ok")

    def rename(self, target, name):
        component = self._world.components.get(getattr(target, "id", target))
        if component is None:
            return Result("not_found")
        if not name:
            return Result("name_empty")
        if any(getattr(c, "name", None) == name for c in self._world.components.values() if c is not component):
            return Result("name_taken")
        component.name = name
        return Result("ok")


class DroneDepot(Building):
    """Drone Depot (drone_station*): bays from the spec; docked drones are the
    Drone components whose `station` is this depot."""

    def __init__(self, world, depot_id, outpost, type_id="drone_station"):
        super().__init__(world, depot_id, outpost)
        self.type_id = type_id
        self.input = Slot(self, self.input_buffer, 100)
        self.output = Slot(self, self.output_buffer, 100)
        self.bays = default_data(type_id, "bays", 1)

    def bay_count(self):
        return self.bays

    def get_docked(self):
        return [c.id for c in self.world.components.values() if isinstance(c, Drone) and c.station == self.id]

    def bays_occupied(self):
        return len(self.get_docked())

    def slot_capacity(self):
        return self.input.capacity()

    def slots_used(self):
        return self._input_used()


class CropJob:
    """Crop Automator current_job() / get_queue() entry."""

    def __init__(self, job_id, action, sector, state="queued", blocker=None, item_id=None):
        self.id = job_id
        self.action = action
        self.sector = sector
        self.state = state
        self.blocker = blocker
        self.item_id = item_id
        self.progress = 0.0


class CropAutomator(Building):
    """Crop Automator: `jobs` is the FIFO (jobs[0] = current_job()); output
    holds Forage up to 50,000."""
    type_id = "crop_automator"

    def __init__(self, world, machine_id, outpost, sector="C7"):
        super().__init__(world, machine_id, outpost)
        self.sector = sector
        self.input = Slot(self, self.input_buffer, 400)
        self.output = Slot(self, self.output_buffer, 50000)
        self.jobs = []
        self.canceled = []

    def position(self):
        return self.sector

    def current_job(self):
        return self.jobs[0] if self.jobs else None

    def get_queue(self):
        return list(self.jobs[1:])

    def queue_count(self):
        return len(self.jobs)

    def cancel_job(self, job_id):
        job = next((j for j in self.jobs if j.id == job_id), None)
        if job is None:
            return Result("not_found")
        self.jobs.remove(job)
        self.canceled.append(job_id)
        return Result("ok")


class HabitatBonusNode:
    def __init__(self, node_id, slot, source_species, insight_cost=1.0, purchased=False):
        self.id = node_id
        self.name = node_id
        self.slot = slot
        self.source_species = source_species
        self.insight_cost = insight_cost
        self.purchased = purchased


class HabitatBonusTree:
    def __init__(self, species, nodes):
        self.species = species
        self.nodes = list(nodes)
        self.purchased_count = len([n for n in self.nodes if n.purchased])


class HabitatInsight:
    def __init__(self, shared_exact=0.0):
        self.shared_exact = shared_exact
        self.shared = int(shared_exact)


class Habitat(Building):
    """Habitat: colony state the test sets (species, population, fluids,
    bands, bonus nodes); feed sits in the `input` buffer."""
    type_id = "habitat"

    def __init__(self, world, habitat_id, outpost, species="", target="", feed_item="", established=False):
        super().__init__(world, habitat_id, outpost)
        self.input = Slot(self, self.input_buffer, 100)
        self.reagents_buffer = {}
        self.reagents = Slot(self, self.reagents_buffer, 100)
        self.gas_in = FluidPort(world, 0.0, default_data(self.type_id, "gas_in_capacity", 50))
        self.liquid_in = FluidPort(world, 0.0, default_data(self.type_id, "liquid_in_capacity", 50))
        self.colony = species
        self.target = target
        self.feed_item = feed_item
        self.established = established
        self.pop = 0
        self.capacity = 0
        self.level = 1
        self.room = 0
        self.stage = ""
        self.rate = 0.0
        self.efficiency = 1.0
        self.next_pop = 0
        self.failed = False
        self.progress = 0.0
        self.bands = {"gas": [], "liquid": []}
        self.levels = {"gas": 0.0, "liquid": 0.0}
        self.fluids = {"gas": "", "liquid": ""}
        self.required = {"gas": "", "liquid": ""}
        self.next_bands = {"gas": [], "liquid": []}
        self.next_required = {"gas": "", "liquid": ""}
        self.intake: dict[str, float | None] = {"gas": None, "liquid": None}  # None: never set
        self.nodes = []
        self.insight = 0.0
        self.calls = []

    # identity / colony
    def species(self): return self.colony
    def revival_target(self): return self.target
    def is_established(self): return self.established
    def rearing_failed(self): return self.failed
    def rearing_progress(self): return self.progress
    def population(self): return self.pop
    def carrying_capacity(self): return self.capacity
    def tier(self): return self.level
    def headroom(self): return self.room
    def life_stage(self): return self.stage
    def breeding_rate(self): return self.rate
    def breeding_efficiency(self): return self.efficiency
    def next_stage_population(self): return self.next_pop
    def required_feed(self): return self.feed_item
    def feed_level(self): return float(self.input_buffer.get(self.feed_item, 0))
    def feed_ok(self): return self.feed_level() > 0
    def get_insight(self): return HabitatInsight(self.insight)
    def get_active_bonuses(self): return [n for n in self.nodes if n.purchased]
    def get_bonus_tree(self): return HabitatBonusTree(self.colony or self.target, self.nodes)

    # fluids
    def gas_band(self): return list(self.bands["gas"])
    def liquid_band(self): return list(self.bands["liquid"])
    def gas_level(self): return self.levels["gas"]
    def liquid_level(self): return self.levels["liquid"]
    def gas_fluid(self): return self.fluids["gas"]
    def liquid_fluid(self): return self.fluids["liquid"]
    def required_gas(self): return self.required["gas"]
    def required_liquid(self): return self.required["liquid"]
    def next_gas_band(self): return list(self.next_bands["gas"])
    def next_liquid_band(self): return list(self.next_bands["liquid"])
    def next_required_gas(self): return self.next_required["gas"]
    def next_required_liquid(self): return self.next_required["liquid"]
    def gas_ok(self): return self._medium_ok("gas")
    def liquid_ok(self): return self._medium_ok("liquid")

    def _medium_ok(self, medium):
        band = self.bands[medium]
        if self.required[medium] and self.fluids[medium] != self.required[medium]:
            return False
        return not band or band[0] <= self.levels[medium] <= band[1]

    def set_gas_intake(self, rate):
        self.intake["gas"] = rate
        return Result("ok")

    def set_liquid_intake(self, rate):
        self.intake["liquid"] = rate
        return Result("ok")

    def purge_reserve(self, medium):
        self.calls.append(("purge_reserve", medium))
        if self.levels.get(medium, 0.0) <= 0:
            return Result("empty")
        self.levels[medium] = 0.0
        self.fluids[medium] = ""
        return Result("ok")

    def purge_intake(self, port=None):
        """Vents "gas_in", "liquid_in", or both when port is None."""
        self.calls.append(("purge_intake", port))
        ports = [p for name, p in (("gas_in", self.gas_in), ("liquid_in", self.liquid_in)) if port in (None, name)]
        if all(p.level() <= 0 for p in ports):
            return Result("empty")
        for fluid_port in ports:
            fluid_port._level = 0.0
        return Result("ok")

    # actions
    def set_revival_target(self, creature_id):
        self.calls.append(("set_revival_target", creature_id))
        if self.colony:
            return Result("occupied")
        self.target = creature_id
        return Result("ok")

    def revive(self):
        self.calls.append(("revive",))
        if self.colony:
            return Result("occupied")
        if not self.target:
            return Result("no_target")
        if not self.feed_ok():
            return Result("insufficient_feed")
        self.colony = self.target
        return Result("ok")

    def unlock_bonus(self, node_id):
        self.calls.append(("unlock_bonus", node_id))
        node = next((n for n in self.nodes if n.id == node_id), None)
        if node is None:
            return Result("unknown_node")
        if node.purchased:
            return Result("already_purchased")
        if self.insight < node.insight_cost:
            return Result("insufficient_insight")
        self.insight -= node.insight_cost
        node.purchased = True
        return Result("ok")


class World:
    """One fake save. `get_component` is installed as the game builtin."""

    def __init__(self):
        self.components = {}
        self.outposts = {}
        self.notebook = Notebook()
        self.notices = []  # notify() texts (harness builtin)
        self.clock = Clock()
        self.console = Console()
        self.home = self.add_outpost("home", is_home=True)
        self.inventory = Store(self, "inventory", "", self.home, capacity=100000)
        self.services = {
            "notebook": self.notebook,
            "clock": self.clock,
            "console": self.console,
            "outpost_network": OutpostNetwork(self),
            "inventory": self.inventory,
            "journal": Journal(),
            "orders": Orders(),
            "commander": Commander(),
            "construction_blueprint": ConstructionBlueprints(),
            "wildlife_sensor": WildlifeSensor(),
        }
        self.services["shop"] = Shop(self)
        self.power_control = PowerControl(self)
        self.run_control = RunControl(self)
        self.fleet = Fleet(self)
        self.computer = Computer(self)
        self.comms = Comms(self)
        self.research = Research()
        self.building_capacity = 25  # home base building slots (OutpostRef.buildings_capacity())
        self.services.update({
            "research": self.research,
            "outpost_home": OutpostComponent(self, self.home),
            "power_control": self.power_control,
            "run_control": self.run_control,
            "fleet": self.fleet,
            "computer": self.computer,
            "comms": self.comms,
        })

    # -- building the world --
    def add_outpost(self, outpost_id, is_home=False):
        outpost = OutpostRef(self, outpost_id, is_home=is_home)
        self.outposts[outpost_id] = outpost
        return outpost

    def add_warehouse(self, warehouse_id, outpost, items=None, capacity=1000):
        store = Store(self, warehouse_id, "warehouse", outpost, capacity=capacity, items=items)
        self.components[warehouse_id] = store
        return store

    def add_storage_bin(self, bin_id, outpost, material="", count=0, capacity=500):
        return self._place(StorageBin(self, bin_id, outpost, material, count, capacity))

    def add_lead_cask(self, cask_id, outpost, material="", count=0):
        return self._place(LeadCask(self, cask_id, outpost, material, count))

    def add_smelter(self, smelter_id, outpost, recipes=None):
        machine = Smelter(self, smelter_id, outpost, recipes)
        self.components[smelter_id] = machine
        return machine

    def add_fabricator(self, fabricator_id, outpost, recipes=None):
        machine = Fabricator(self, fabricator_id, outpost, recipes)
        self.components[fabricator_id] = machine
        return machine

    def add_supply_dock(self, dock_id, outpost):
        dock = SupplyDock(self, dock_id, outpost)
        self.components[dock_id] = dock
        return dock

    def add_building[B: Building](self, building_id, outpost, type_id, cls: type[B] = Building) -> B:
        """A plain Building (or a test's Building subclass `cls`) of any spec type_id."""
        building = cls(self, building_id, outpost)
        building.type_id = type_id
        self.components[building_id] = building
        return building

    def _place(self, component):
        self.components[component.id] = component
        return component

    def add_tank(self, tank_id, outpost, fluid="", level=0.0, type_id="liquid_tank", capacity=None):
        return self._place(Tank(self, tank_id, outpost, type_id, fluid, level, capacity))

    def add_battery(self, battery_id, outpost, charge=0.0, type_id="battery", capacity=None):
        return self._place(BatteryBank(self, battery_id, outpost, type_id, charge, capacity))

    def add_turbine(self, turbine_id, outpost, steam=0.0, source="", output=0.0, stalled=False, throttle=0.0):
        return self._place(SteamTurbine(self, turbine_id, outpost, steam, source, output, stalled, throttle))

    def add_grid(self, anchor_id, machine_ids, consumed=0.0, generated=0.0, stored=None, capacity=None):
        """A power grid over machine_ids (components added before or after);
        stored/capacity default to the member batteries' charge."""
        grid = PowerGrid(self, anchor_id, machine_ids, consumed, generated, stored, capacity)
        self.power_control.grid_list.append(grid)
        return grid

    def add_drone(self, drone_id, outpost, kind="drone_small", station="", **state):
        return self._place(Drone(self, drone_id, outpost, kind, station, **state))

    def add_pioneer(self, pioneer_id, outpost=None, station="", **state):
        return self._place(Pioneer(self, pioneer_id, outpost or self.home, station, **state))

    def add_rover(self, rover_id, outpost=None, station="", **state):
        return self._place(Rover(self, rover_id, outpost or self.home, station, **state))

    def add_drone_depot(self, depot_id, outpost, type_id="drone_station"):
        return self._place(DroneDepot(self, depot_id, outpost, type_id))

    def add_habitat(self, habitat_id, outpost, species="", target="", feed_item="", established=False):
        return self._place(Habitat(self, habitat_id, outpost, species, target, feed_item, established))

    def add_wildlife_sensor(self, population=0):
        sensor = self.services["wildlife_sensor"]
        sensor.population = population
        return sensor

    def add_blueprint(self, job_id, required_item, required_count=1):
        job = Construction(job_id, required_item, required_count)
        self.services["construction_blueprint"].pending.append(job)
        return job

    def add_order(self, order_id, requires, shipped=None):
        order = Order(order_id, requires, shipped)
        self.services["orders"].orders[order_id] = order
        return order

    # -- game API --
    def get_component(self, component_id):
        """A component a test placed under component_id wins over the default service."""
        if component_id in self.components:
            return self.components[component_id]
        return self.services.get(component_id)

    def local_store(self, target_id, outpost, machines=False):
        """(store, problem) for a port at `outpost` reaching target_id. problem
        is "ok" (store set) or one of "no_connection", "not_found", "not_local",
        "inventory_not_local"; each port method maps it to its own status.
        `machines`: another machine's input counts as a store (an OutputSlot
        destination, wrapped in MachineInput)."""
        if not target_id:
            return None, "no_connection"
        if target_id == "inventory":
            return (self.inventory, "ok") if outpost is self.home else (None, "inventory_not_local")
        store = self.components.get(target_id)
        if machines and isinstance(store, Building) and isinstance(getattr(store, "input", None), Slot):
            if store.outpost is not outpost:
                return None, "not_local"
            return MachineInput(store), "ok"
        if store is None or not isinstance(store, PassiveStore):
            return None, "not_found"
        if store.outpost is not outpost:
            return None, "not_local"
        return store, "ok"

    def stock(self, item_id, outpost=None):
        """Units of item_id in storage at `outpost` (None = every outpost + Inventory)."""
        total = 0
        if outpost is None or outpost is self.home:
            total += self.inventory.count(item_id)
        for component in self.components.values():
            if isinstance(component, PassiveStore) and (outpost is None or component.outpost is outpost):
                total += component.count(item_id)
        return total
