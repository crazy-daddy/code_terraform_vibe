# Refiner controller: one per Refiner (thin fluids/refiner.py).
# Turns raw exotic feedstock + tar into creature-grade gas or liquid:
#   - Recipes (docs/database/recipes_refiner.md), 4 t raw + tar -> 4 t refined:
#       refine_sulfur_gas  (gas,    2 tar, 0.3 h, 30 W)
#       refine_cryofluid   (liquid, 2 tar, 0.3 h, 30 W)
#       refine_chlorine    (gas,    5 tar, 0.4 h, 48 W)
#       refine_quicksilver (liquid, 5 tar, 0.4 h, 48 W)
#   - What to refine: one network-wide tank sweep (every TOTALS_REFRESH_TICKS)
#     sums level/capacity per fluid over every Gas/Liquid Tank latched to it or
#     assigned to it (fluid_routing.get_tank_assignments()). A recipe is a
#     candidate when its raw fluid holds >= RAW_MIN_TONS (or its input port
#     already holds a craft) and its refined fluid has tank capacity below
#     REFINED_FULL_FRACTION. The candidate with the lowest refined fill wins.
#     Exotic Caps/Taps stand in the field, outside any outpost, and fill raw
#     tanks (lib/exotic_cap.py); the Refiner draws from those tanks.
#   - No flip-flopping, no starving: a recipe runs at least MIN_RECIPE_TICKS;
#     after that another candidate takes over when its refined fill is
#     SWITCH_MARGIN lower, or once the recipe has run MAX_RECIPE_TICKS.
#     No candidate -> the current recipe stays set (idle, parked).
#   - Switching: disconnect the old input port and let the staged raw fluid
#     craft out (up to SWITCH_DRAIN_TICKS), drain a shared output port through
#     the old output router (set_recipe() rejects "output_busy" otherwise),
#     purge a shared input port, then set_recipe(). The ports latch to the
#     first fluid they see and report no fluid id, so only a port the old
#     recipe shared is purged.
#   - Ports: gas_in / liquid_in from tanks eligible for the raw fluid (own
#     outpost first, FluidInputRouter), only while the recipe has raw supply; gas_out / liquid_out to tanks eligible
#     for the refined fluid (FluidOutputRouter).
#   - Tar (input, 50-unit bin): refilled to full via take_item() from this
#     outpost's storage once it drops to TAR_REFILL_AT. The outpost's tar
#     stockpile is requested by lib/site_supply.py (SITE_STOCK_TARGETS["refiner"]).
#   - Soft-shed (power.shedded, Tier 2): clear_recipe() once the running craft
#     ends, so nothing new starts (the Refiner crafts on its own while a recipe
#     is set); staged tar and feedstock stay. The recipe is picked again after.
#   - Commands: "recipe <id>" pins a recipe, "auto" unpins, "purge" vents inputs.
#   - Parked (ParkRequester, kind "refiner") while idle.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item
from script_parking import ParkRequester
import fluid_routing

ACTIVE_POLL_S = 2.0   # a craft takes 0.3-0.4 game h = 7.5-10 s
IDLE_POLL_S = 15.0

RECIPE_REFRESH_TICKS = 1200
TOTALS_REFRESH_TICKS = 300

RAW_MIN_TONS = 4.0
REFINED_FULL_FRACTION = 0.95
MIN_RECIPE_TICKS = 1200
MAX_RECIPE_TICKS = 6000
SWITCH_MARGIN = 0.20
SWITCH_DRAIN_TICKS = 600

TAR_ITEM_ID = "tar"
TAR_REFILL_AT = 20

STATUS_KEY = "refiner.status"
STATUS_REFRESH_TICKS = 600
STATUS_STALE_TICKS = 36000

GAS_TANK_TYPE_IDS = ("gas_tank",)

# Fallback when a Recipe object lacks fluid_inputs / fluid_outputs / inputs.
REFINER_RECIPES = {
    "refine_sulfur_gas": {"raw_fluid": "raw_sulfur_gas", "refined_fluid": "sulfur_gas", "input_port": "gas_in", "output_port": "gas_out", "tar": 2},
    "refine_cryofluid": {"raw_fluid": "raw_cryofluid", "refined_fluid": "cryofluid", "input_port": "liquid_in", "output_port": "liquid_out", "tar": 2},
    "refine_chlorine": {"raw_fluid": "raw_chlorine", "refined_fluid": "chlorine", "input_port": "gas_in", "output_port": "gas_out", "tar": 5},
    "refine_quicksilver": {"raw_fluid": "raw_quicksilver", "refined_fluid": "quicksilver", "input_port": "liquid_in", "output_port": "liquid_out", "tar": 5},
}


def tank_types(port_name):
    return GAS_TANK_TYPE_IDS if port_name.startswith("gas") else fluid_routing.LIQUID_TANK_TYPE_IDS


def fluid_totals():
    """{fluid_id: [level t, capacity t]} over every network tank latched or assigned to a fluid
    (retiring tanks skipped). One outpost_network sweep."""
    assignments = fluid_routing.get_tank_assignments()
    totals = {}
    for tank, _outpost_id in fluid_routing.discover_network_buildings(fluid_routing.TANK_TYPE_IDS, resolve=True):
        tank_id = getattr(tank, "id", None)
        if assignments.get(tank_id) == fluid_routing.RETIRING_ASSIGNMENT:
            continue
        try:
            fluid = tank.fluid() or assignments.get(tank_id)
            if not fluid:
                continue
            row = totals.setdefault(fluid, [0.0, 0.0])
            row[0] += float(tank.level())
            row[1] += float(tank.capacity())
        except Exception as error:
            swallowed("refiner.fluid_totals: tank read", error)
    return totals


def recipe_candidates(unlocked, totals, staged=None):
    """{recipe_id: refined fill 0-1} for recipes with raw feedstock available (>= RAW_MIN_TONS in
    tanks, or staged[recipe_id] True: a craft already in the input port) and refined tank room
    (capacity > 0, fill < REFINED_FULL_FRACTION)."""
    staged = staged or {}
    out = {}
    for rid, spec in unlocked.items():
        raw = totals.get(spec["raw_fluid"]) or [0.0, 0.0]
        if raw[0] < RAW_MIN_TONS and not staged.get(rid):
            continue
        level, capacity = totals.get(spec["refined_fluid"]) or [0.0, 0.0]
        if capacity <= 0:
            continue
        fill = level / capacity
        if fill < REFINED_FULL_FRACTION:
            out[rid] = fill
    return out


def choose_recipe(candidates, current, age_ticks):
    """Recipe to run: the current one while it is a candidate and younger than MIN_RECIPE_TICKS;
    then the neediest other candidate if SWITCH_MARGIN emptier, or any other once current ran
    MAX_RECIPE_TICKS. A non-candidate current yields to the neediest candidate; none -> current."""
    if not candidates:
        return current or None
    if current not in candidates:
        return min(candidates, key=lambda r: candidates[r])
    if age_ticks < MIN_RECIPE_TICKS:
        return current
    others = [r for r in candidates if r != current]
    if not others:
        return current
    best = min(others, key=lambda r: candidates[r])
    if candidates[best] <= candidates[current] - SWITCH_MARGIN or age_ticks >= MAX_RECIPE_TICKS:
        return best
    return current


class RefinerController:
    """Refines raw exotic feedstock + tar into the creature-grade fluid whose tanks are emptiest."""

    def __init__(self, refiner):
        self.refiner = refiner
        self.name = getattr(refiner, "id", "refiner")
        self.outpost = getattr(refiner, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.clock = get_component("clock")
        self.log = TreeConsole(module="refiner")
        self.parker = ParkRequester(self.name, "refiner")
        self.pinned = None
        self._recipes = {}
        self._recipes_tick = -RECIPE_REFRESH_TICKS
        self._totals = {}
        self._totals_tick = -TOTALS_REFRESH_TICKS
        self._routers = {}
        self._since = None
        self._switch_to = None
        self._switch_tick = 0
        # Recipe ids with raw feedstock available (last pick_recipe()); None = pinned, always route.
        self._raw_ok = None
        self._last_status = None
        self._status_tick = -STATUS_REFRESH_TICKS

    def tick(self):
        try:
            return self.clock.tick() if self.clock else 0
        except Exception as error:
            swallowed("refiner.RefinerController.tick: clock.tick", error)
            return 0

    def _call(self, method, default, *args):
        fn = getattr(self.refiner, method, None)
        if fn is None:
            return default
        try:
            value = fn(*args)
        except Exception as error:
            swallowed(f"refiner.RefinerController._call: {method}", error)
            return default
        return default if value is None else value

    def _port(self, name):
        return getattr(self.refiner, name, None)

    def _level(self, port):
        if port is None or not hasattr(port, "level"):
            return 0.0
        try:
            return float(port.level())
        except Exception as error:
            swallowed("refiner.RefinerController._level: port.level", error)
            return 0.0

    def raw_available(self, rid):
        """Whether rid had raw feedstock (tank stock or a staged craft) at the last pick; pinned -> True."""
        return self._raw_ok is None or rid in self._raw_ok

    def shed(self):
        return self.name in (archive.get("power.shedded", []) or [])

    # ----------------------------------------------------------- commands

    def process_commands(self):
        while self._call("command_count", 0) > 0:
            cmd = self._call("next_command", None)
            if not cmd:
                break
            parts = str(cmd).strip().split()
            if not parts:
                continue
            action = parts[0].lower()
            if action in ("recipe", "set_recipe") and len(parts) > 1:
                self.pinned = parts[1]
                self.log.print(f"[{self.name}] Recipe pinned to '{self.pinned}'.")
            elif action == "auto":
                self.pinned = None
                self.log.print(f"[{self.name}] Recipe selection back to auto.")
            elif action == "purge":
                res = self._call("purge_input", None)
                self.log.print(f"[{self.name}] purge_input() -> {getattr(res, 'status', '?')}.")

    # ------------------------------------------------------------ recipes

    def unlocked_recipes(self, curr_tick):
        """{recipe_id: spec}, refreshed every RECIPE_REFRESH_TICKS."""
        if self._recipes and curr_tick - self._recipes_tick < RECIPE_REFRESH_TICKS:
            return self._recipes
        self._recipes_tick = curr_tick
        out = {}
        for recipe in self._call("list_recipes", []):
            rid = getattr(recipe, "id", None)
            if not rid:
                continue
            spec = REFINER_RECIPES.get(rid, {})
            fluid_inputs = dict(getattr(recipe, "fluid_inputs", None) or {})
            fluid_outputs = dict(getattr(recipe, "fluid_outputs", None) or {})
            inputs = dict(getattr(recipe, "inputs", None) or {})
            in_port = next(iter(fluid_inputs), None) or spec.get("input_port")
            out_port = next(iter(fluid_outputs), None) or spec.get("output_port")
            raw = getattr(recipe, "input_fluid", "") or spec.get("raw_fluid")
            refined = getattr(recipe, "output_fluid", "") or spec.get("refined_fluid")
            if not (in_port and out_port and raw and refined):
                continue
            out[rid] = {
                "raw_fluid": raw,
                "refined_fluid": refined,
                "input_port": in_port,
                "output_port": out_port,
                "raw_tons": float(fluid_inputs.get(in_port, 4.0)),
                "tar": int(inputs.get(TAR_ITEM_ID, spec.get("tar", 2))),
            }
        self._recipes = out
        return out

    def totals(self, curr_tick):
        if curr_tick - self._totals_tick >= TOTALS_REFRESH_TICKS:
            self._totals = fluid_totals()
            self._totals_tick = curr_tick
        return self._totals

    def pick_recipe(self, unlocked, current, curr_tick):
        if self.pinned:
            self._raw_ok = None
            return self.pinned if self.pinned in unlocked else current or None
        staged = {}
        if current in unlocked:
            spec = unlocked[current]
            staged[current] = self._level(self._port(spec["input_port"])) >= spec["raw_tons"]
        candidates = recipe_candidates(unlocked, self.totals(curr_tick), staged)
        self._raw_ok = set(candidates)
        if self._since is None:
            self._since = curr_tick
        choice = choose_recipe(candidates, current if current in unlocked else None, curr_tick - self._since)
        if choice != current:
            fills = ", ".join(f"{r}={f:.2f}" for r, f in sorted(candidates.items()))
            self.log.debug(f"[{self.name}] wants '{choice}' over '{current or '-'}' (refined fill: {fills or 'no candidate'})")
        return choice

    # ------------------------------------------------------------ routing

    def routers(self, rid, spec):
        if rid not in self._routers:
            raw, refined = spec["raw_fluid"], spec["refined_fluid"]
            in_types = tank_types(spec["input_port"])
            out_id = self.outpost_id

            def discover():
                pairs = fluid_routing.discover_network_buildings(in_types, resolve=False, fluid_id=raw)
                return fluid_routing.rank_own_outpost_first(pairs, out_id)

            self._routers[rid] = (
                fluid_routing.FluidInputRouter(
                    discover=discover,
                    rescan_interval_ticks=300,
                    discovery_cache_interval_ticks=100,
                    neutral_grace_steps=5,
                    stall_streak_threshold=5,
                    label=f"{self.name}.{spec['input_port']}",
                ),
                fluid_routing.FluidOutputRouter(
                    type_ids=tank_types(spec["output_port"]),
                    rebalance_fill_fraction=0.98,
                    connection_grace_ticks=2,
                    rescan_interval_ticks=300,
                    discovery_cache_interval_ticks=100,
                    fluid_id=refined,
                    label=f"{self.name}.{spec['output_port']}",
                ),
            )
        return self._routers[rid]

    def route_output(self, rid, spec, curr_tick):
        port = self._port(spec["output_port"])
        if port is None:
            return
        try:
            full = self._level(port) >= float(port.capacity()) - 0.5
        except Exception as error:
            swallowed("refiner.route_output: port.capacity", error)
            full = False
        self.routers(rid, spec)[1].ensure_connection(port, curr_tick, full and self._call("is_stalled", False))

    def route_input(self, rid, spec, curr_tick):
        port = self._port(spec["input_port"])
        if port is None:
            return
        starved = self._level(port) < spec["raw_tons"]
        self.routers(rid, spec)[0].ensure(port, curr_tick, starved)

    # ---------------------------------------------------------- switching

    def switch_step(self, current, target, unlocked, curr_tick):
        """Advances a switch current -> target by one step. True once target is set."""
        old = unlocked.get(current) if current else None
        new = unlocked[target]
        if self._switch_to != target:
            self._switch_to = target
            self._switch_tick = curr_tick
            if old:
                in_port = self._port(old["input_port"])
                if in_port is not None and hasattr(in_port, "disconnect"):
                    in_port.disconnect()
                self.log.debug(f"[{self.name}] switch '{current}' -> '{target}': input disconnected, crafting out staged feedstock")
        if old:
            self.route_output(current, old, curr_tick)
            draining = self._call("is_running", False) or self._level(self._port(old["input_port"])) >= old["raw_tons"]
            if draining and curr_tick - self._switch_tick < SWITCH_DRAIN_TICKS:
                return False
            if self._call("is_running", False):
                return False
            if old["output_port"] == new["output_port"] and self._level(self._port(old["output_port"])) > 0.01:
                self.log.debug(f"[{self.name}] switch waits for {old['output_port']} to drain")
                return False
        if old and old["input_port"] == new["input_port"] and self._level(self._port(new["input_port"])) > 0:
            self._call("purge_input", None)
        self.log.start(f"[{self.name}] Recipe '{current or '-'}' -> '{target}'")
        res = self._call("set_recipe", None, target)
        status = getattr(res, "status", "no result")
        self.log.end(status)
        if status != "ok":
            return False
        self._switch_to = None
        self._since = curr_tick
        return True

    # ---------------------------------------------------------------- tar

    def top_up_tar(self):
        slot = self._port("input")
        if slot is None:
            return
        try:
            count = slot.count()
            capacity = slot.capacity()
        except Exception as error:
            swallowed("refiner.top_up_tar: input read", error)
            return
        if count <= TAR_REFILL_AT:
            moved = take_item(slot, TAR_ITEM_ID, capacity - count, outpost=self.outpost)
            self.log.trace(f"[{self.name}] tar {count}/{capacity}, took {moved}")

    def tar_count(self):
        slot = self._port("input")
        try:
            return slot.count() if slot is not None else 0
        except Exception as error:
            swallowed("refiner.tar_count: input.count", error)
            return 0

    # ------------------------------------------------------------- status

    def blocker(self, rid, spec):
        if self.shed():
            return "shed"
        if not spec:
            return "no_recipe"
        if self._switch_to:
            return "switching"
        if not self.raw_available(rid):
            return "no_raw_supply"
        if self.tar_count() < spec["tar"]:
            return "no_tar"
        if self._level(self._port(spec["input_port"])) < spec["raw_tons"]:
            return "no_feedstock"
        if self._call("is_stalled", False):
            return "output_blocked"
        return None

    def publish_status(self, rid, blocker, curr_tick):
        status = (rid, blocker)
        if status == self._last_status and curr_tick - self._status_tick < STATUS_REFRESH_TICKS:
            return
        if blocker != (self._last_status or (None, None))[1]:
            self.log.debug(f"[{self.name}] state: {blocker or 'refining'} (recipe {rid or '-'})")
        self._last_status = status
        self._status_tick = curr_tick
        entry = {"recipe": rid or "", "blocker": blocker, "outpost": self.outpost_id, "tick": curr_tick}

        def updater(stored):
            if not isinstance(stored, dict):
                stored = {}
            for other in [k for k, v in stored.items() if not isinstance(v, dict) or curr_tick - v.get("tick", 0) > STATUS_STALE_TICKS]:
                del stored[other]
            stored[self.name] = entry
            return stored

        if not archive.transaction(STATUS_KEY, {}, updater):
            self.log.level("warn").print(f"[{self.name}] {STATUS_KEY} write rejected.")

    # --------------------------------------------------------------- loop

    def step(self):
        """One control pass; returns the sleep delay (IDLE_POLL_S = idle)."""
        curr_tick = self.tick()
        self.process_commands()
        unlocked = self.unlocked_recipes(curr_tick)
        current = self._call("get_recipe", "") or None
        running = bool(self._call("is_running", False))

        if self.shed():
            self._switch_to = None
            if current and not running:
                res = self._call("clear_recipe", None)
                self.log.debug(f"[{self.name}] shed: clear_recipe() -> {getattr(res, 'status', '?')}")
                current = None
            if current in unlocked:
                self.route_output(current, unlocked[current], curr_tick)
            self.publish_status(current, "shed", curr_tick)
            return ACTIVE_POLL_S if running else IDLE_POLL_S

        target = self.pick_recipe(unlocked, current, curr_tick)
        if target and target != current:
            if self.switch_step(current, target, unlocked, curr_tick):
                current = target
        else:
            self._switch_to = None

        spec = unlocked.get(current) if current else None
        if spec and not self._switch_to:
            self.top_up_tar()
            # No raw stock anywhere: leave the input alone instead of starving and blacklisting empty tanks.
            if self.raw_available(current):
                self.route_input(current, spec, curr_tick)
            self.route_output(current, spec, curr_tick)

        blocker = self.blocker(current, spec)
        self.publish_status(current, blocker, curr_tick)
        busy = running or blocker in (None, "switching")
        return ACTIVE_POLL_S if busy else IDLE_POLL_S

    def run(self):
        self.log.print(f"Refiner Controller ({self.name}) online at '{self.outpost_id}'.")
        validate_game_version()
        while True:
            reset_all()
            delay = IDLE_POLL_S
            try:
                delay = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Refiner exception: {error}")
            self.parker.update(delay == IDLE_POLL_S)
            flush_all()
            sleep(delay)
