"""
Fake game world for offline stub tests of the `lib/` production modules.

Models just enough of the game API (docs/components/, docs/types/) for
production.py, storage.py, smelter.py, fabricator.py and supply_dock.py:
outposts with Warehouses, home Inventory, Smelters, Fabricators, Supply
Docks and Earth Orders, the Data Archive
(notebook), clock and console. Port locality follows the docs: Inventory
works at home only, and a remote machine's ports only reach storage at its
own outpost (anything else answers "not_local").

Nothing here crafts on its own; a test sets machine state (buffers,
`running`, stock) directly and then calls a controller step.
"""
import copy


class Result:
    def __init__(self, status="ok", moved=0, message=""):
        self.status = status
        self.moved = moved
        self.message = message

    def __repr__(self):
        return f"Result({self.status!r}, moved={self.moved})"


class Stack:
    def __init__(self, item_id, count):
        self.id = item_id
        self.count = count

    def __repr__(self):
        return f"Stack({self.id!r}, {self.count})"


class Recipe:
    def __init__(self, recipe_id, inputs, output_item, output_count=1, duration_game_hours=0.08, fluid_inputs=None):
        self.id = recipe_id
        self.inputs = dict(inputs)
        self.output_item = output_item
        self.output_count = output_count
        self.duration_game_hours = duration_game_hours
        self.fluid_inputs = dict(fluid_inputs or {})

    def __repr__(self):
        return f"Recipe({self.id!r})"


SMELTER_RECIPES = [
    Recipe("smelt_iron_ingot", {"iron_ore": 1}, "iron_ingot"),
    Recipe("smelt_glass", {"silicon": 1}, "glass"),
    Recipe("smelt_titanium_ingot", {"titanium": 1}, "titanium_ingot"),
]

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

    def buildings(self, type_id=None):
        return [
            BuildingRef(component)
            for component in self._world.components.values()
            if getattr(component, "outpost", None) is self
            and getattr(component, "type_id", None)
            and (type_id is None or component.type_id == type_id)
        ]

    def harvesting_machines(self, type_id=None):
        return []

    def __repr__(self):
        return f"OutpostRef({self.id!r})"


class Store:
    """Home Inventory or a Warehouse: unit-capacity item store."""

    def __init__(self, world, store_id, type_id, outpost, capacity=1000, items=None):
        self._world = world
        self.id = store_id
        self.type_id = type_id
        self.outpost = outpost
        self.capacity_units = capacity
        self.items = dict(items or {})

    def count(self, item_id):
        return self.items.get(item_id, 0)

    def stacks(self):
        return [Stack(item_id, n) for item_id, n in self.items.items() if n > 0]

    def used(self):
        return sum(self.items.values())

    def space_for(self, item_id):
        return max(0, self.capacity_units - self.used())

    def capacity(self):
        return self.capacity_units

    def materials(self):
        return sorted(i for i, n in self.items.items() if n > 0)

    def total(self):
        return self.used()

    def fill_percent(self):
        return self.used() / self.capacity_units if self.capacity_units else 1.0

    def compact(self):
        return Result("no_op")

    def add(self, item_id, n):
        moved = min(n, self.space_for(item_id))
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


class Slot:
    """InputSlot / OutputSlot on a machine. `buffer` is the machine-side
    {item: units} dict the slot fills (input) or drains (output)."""

    def __init__(self, machine, buffer, capacity):
        self.machine = machine
        self.buffer = buffer
        self._capacity = capacity
        self.connected = None
        self.connect_log = []

    # -- shared --
    def capacity(self):
        return self._capacity

    def count(self, item_id=None):
        if item_id is None:
            return sum(self.buffer.values())
        return self.buffer.get(item_id, 0)

    def stacks(self):
        return [Stack(item_id, n) for item_id, n in self.buffer.items() if n > 0]

    def connected_id(self):
        return self.connected

    def connected_to(self):
        return self.connected

    def _resolve(self, target_id):
        """(store, status) for target_id as seen from this machine's outpost."""
        return self.machine.world.local_store(target_id, self.machine.outpost)

    def connect(self, target_id):
        self.connect_log.append(target_id)
        store, status = self._resolve(target_id)
        if store is None:
            return Result(status)
        self.connected = target_id
        return Result("ok")

    # -- input side --
    def take(self, item_id, count):
        store, status = self._resolve(self.connected)
        if store is None:
            return Result(status or "not_connected")
        room = self._capacity - self.machine.input_used()
        moved = store.remove(item_id, min(count, room))
        if moved > 0:
            self.buffer[item_id] = self.buffer.get(item_id, 0) + moved
        return Result("ok" if moved == count else ("partial" if moved > 0 else "empty"), moved)

    def eject(self, target_id, item_id, count):
        store, status = self._resolve(target_id)
        if store is None:
            return Result(status)
        n = min(count, self.buffer.get(item_id, 0))
        moved = store.add(item_id, n)
        if moved > 0:
            self.buffer[item_id] -= moved
            if self.buffer[item_id] <= 0:
                del self.buffer[item_id]
        return Result("ok" if moved == count else ("partial" if moved > 0 else "target_full"), moved)

    # -- output side --
    def send(self, item_id, count):
        store, status = self._resolve(self.connected)
        if store is None:
            return Result(status or "not_connected")
        n = min(count, self.buffer.get(item_id, 0))
        moved = store.add(item_id, n)
        if moved > 0:
            self.buffer[item_id] -= moved
            if self.buffer[item_id] <= 0:
                del self.buffer[item_id]
        return Result("ok" if moved == count else ("partial" if moved > 0 else "target_full"), moved)


class Machine:
    type_id = ""

    def __init__(self, world, machine_id, outpost, recipes):
        self.world = world
        self.id = machine_id
        self.outpost = outpost
        self._recipes = list(recipes)
        self.recipe = ""
        self.running = False
        self.input_buffer = {}
        self.output_buffer = {}

    def list_recipes(self):
        return list(self._recipes)

    def find_recipe(self, recipe_id):
        return next((r for r in self._recipes if r.id == recipe_id), None)

    def get_recipe(self):
        return self.recipe

    def set_recipe(self, recipe_id):
        if self.find_recipe(recipe_id) is None:
            return Result("unknown_recipe")
        self.recipe = recipe_id
        return Result("ok")

    def clear_recipe(self):
        self.recipe = ""
        return Result("ok")

    def is_running(self):
        return self.running

    def input_used(self):
        return sum(self.input_buffer.values())


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
        return self.input_used()

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
        self.expires_day = None


class Orders:
    """`orders` service: campaign orders only (no weekly ones)."""

    def __init__(self):
        self.orders = {}

    def list_orders(self):
        return list(self.orders.values())

    def list_weekly_orders(self):
        return []

    def get_order(self, order_id):
        return self.orders.get(order_id)


class SupplyDock(Machine):
    """Supply Dock: input port loads cargo into `input_buffer`; set_order()
    rejects while cargo is present. Nothing ships on its own."""
    type_id = "supply_dock"

    def __init__(self, world, dock_id, outpost):
        super().__init__(world, dock_id, outpost, [])
        self.input = Slot(self, self.input_buffer, 200)
        self.order = None
        self.enabled = False

    def current_order(self):
        return self.order

    def set_order(self, order_id):
        if self.total() > 0:
            return Result("cargo_present")
        order = self.world.services["orders"].get_order(order_id)
        if order is None:
            return Result("not_found")
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
        return [type("DockSlot", (), {"item_id": i, "count": n})() for i, n in self.input_buffer.items() if n > 0]

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        self.enabled = enabled
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

    def keys(self):
        return list(self.data.keys())


class Clock:
    def __init__(self):
        self.now = 1000
        self.hours = 0.0

    def tick(self):
        return self.now

    def elapsed_game_hours(self):
        return self.hours


class Commander:
    def __init__(self, credits=0):
        self.credits = credits

    def get_credits(self):
        return self.credits


class CatalogueEntry:
    def __init__(self, item_id, cost):
        self.id = item_id
        self.cost = cost


class Shop:
    """`shop`: catalogue prices only; buy() debits the commander."""

    def __init__(self, world, prices=None):
        self._world = world
        self.prices = dict(prices or {})

    def get_catalogue(self):
        return [CatalogueEntry(i, c) for i, c in self.prices.items()]

    def buy(self, item_id, qty):
        cost = self.prices.get(item_id, 0) * qty
        commander = self._world.services["commander"]
        if commander.credits < cost:
            return Result("insufficient_credits")
        commander.credits -= cost
        return Result("ok")


class Console:
    def __init__(self):
        self.lines = []
        self.time_of_day = "12:00:00"

    def now(self):
        return self.time_of_day

    def print(self, msg, level="info", **_kwargs):
        self.lines.append((level, msg))

    def text(self, level=None):
        return "\n".join(m for lv, m in self.lines if level is None or lv == level)


class OutpostNetwork:
    def __init__(self, world):
        self._world = world

    def home(self):
        return self._world.home

    def outposts(self):
        return list(self._world.outposts.values())


class Journal:
    def surveyed_sites(self, _planet):
        return []

    def cataloged_creatures(self, _planet):
        return []


class Construction:
    def __init__(self, job_id, required_item, required_count):
        self.id = job_id
        self.required_item = required_item
        self.required_count = required_count


class ConstructionBlueprints:
    def __init__(self):
        self.pending = []

    def pending_constructions(self):
        return list(self.pending)

    def paused_constructions(self):
        return []


class World:
    """One fake save. `get_component` is installed as the game builtin."""

    def __init__(self):
        self.components = {}
        self.outposts = {}
        self.notebook = Notebook()
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
        }
        self.services["shop"] = Shop(self)

    # -- building the world --
    def add_outpost(self, outpost_id, is_home=False):
        outpost = OutpostRef(self, outpost_id, is_home=is_home)
        self.outposts[outpost_id] = outpost
        return outpost

    def add_warehouse(self, warehouse_id, outpost, items=None, capacity=1000):
        store = Store(self, warehouse_id, "warehouse", outpost, capacity=capacity, items=items)
        self.components[warehouse_id] = store
        return store

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
        if component_id in self.services:
            return self.services[component_id]
        return self.components.get(component_id)

    def local_store(self, target_id, outpost):
        """(store, status) for a port at `outpost` connecting to target_id."""
        if target_id is None:
            return None, "not_connected"
        if target_id == "inventory":
            return (self.inventory, "ok") if outpost is self.home else (None, "not_local")
        store = self.components.get(target_id)
        if not isinstance(store, Store):
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
            if isinstance(component, Store) and (outpost is None or component.outpost is outpost):
                total += component.count(item_id)
        return total
