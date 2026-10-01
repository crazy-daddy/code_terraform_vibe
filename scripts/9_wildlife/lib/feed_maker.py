# Feed Maker controller: one per Feed Maker (thin bio/feed_maker.py), same
# shape as lib/seed_supply.py (deficits -> pick -> craft, parked while idle).
#   - Publishes its unlocked recipes ({recipe_id: inputs}) in
#     `wildlife.feed[id]`; the Wildlife planner reads them for readiness and
#     life-form targets, and publishes the life-form requests itself.
#   - What to make: `wildlife.plan.feed_demand` ({feed_item: [home stock
#     target, priority, short]}) against live home stock (Inventory + home
#     Warehouses) and its own output bin. Lowest priority class first, then the
#     largest deficit, among recipes whose inputs are all at home. A recipe
#     another fresh Feed Maker is running is left to it unless its deficit is
#     larger than one craft.
#   - Switching recipe: waits for the running craft, ejects the leftovers
#     (clear_recipe() rejects `material_present`), then set_recipe().
#   - Stocks one craft at a time and the next one once the 200-unit stockpile
#     has room; finished feed goes to a home Warehouse (Inventory fallback).
#   - Soft-shed (`power.shedded`, lib/power.py): starts no new craft.
# Never crafts past the target; idle (no deficit or no inputs) -> parked.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item, total_stock, drain_port_to_storage, local_port_target
from script_parking import ParkRequester
import logistics_requests
import wildlife_common as wc
from wildlife_data import FEED_PER_CRAFT

ACTIVE_POLL_S = 2.0          # a craft takes 0.3 game h = 7.5 s (Mk II 5 s)
IDLE_POLL_S = 20.0
RECIPE_REFRESH_TICKS = 1200  # republish unlocked recipes at least this often


class FeedMakerController:
    """Crafts creature feed to the planner's home stock targets."""

    def __init__(self, maker):
        self.maker = maker
        self.name = getattr(maker, "id", "feed_maker")
        self.outpost = getattr(maker, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.clock = get_component("clock")
        self.log = TreeConsole(module="feed_maker")
        self.parker = ParkRequester(self.name, "feed_maker")
        self._recipes = {}
        self._recipes_tick = -RECIPE_REFRESH_TICKS
        self._last_blocker = None

    def tick(self):
        try:
            return self.clock.tick() if self.clock else 0
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.tick: clock.tick", error)
            return 0

    def _call(self, method, default, *args):
        fn = getattr(self.maker, method, None)
        if fn is None:
            return default
        try:
            value = fn(*args)
        except Exception as error:
            swallowed(f"feed_maker.FeedMakerController._call: {method}", error)
            return default
        return default if value is None else value

    # ------------------------------------------------------------ recipes

    def recipes(self, curr_tick):
        """{recipe_id: {"output": item, "inputs": {item: qty}}}, refreshed every RECIPE_REFRESH_TICKS."""
        if curr_tick - self._recipes_tick < RECIPE_REFRESH_TICKS and self._recipes:
            return self._recipes
        self._recipes_tick = curr_tick
        out = {}
        for recipe in self._call("list_recipes", []):
            recipe_id = getattr(recipe, "id", None)
            if recipe_id:
                out[recipe_id] = {"output": getattr(recipe, "output_item", ""), "inputs": dict(getattr(recipe, "inputs", None) or {})}
        self._recipes = out
        return out

    # ------------------------------------------------------------- demand

    def claims(self, curr_tick):
        """{recipe_id: feed_maker_id} running on other fresh Feed Makers."""
        feed = archive.get(wc.FEED_KEY, {}) or {}
        out = {}
        for other, entry in (feed.items() if isinstance(feed, dict) else []):
            if other != self.name and wc.fresh(entry, curr_tick) and entry.get("recipe"):
                out[entry["recipe"]] = other
        return out

    def deficits(self, recipes):
        """{recipe_id: (priority, feed short)} against live home stock and this output bin."""
        plan = archive.get(wc.PLAN_KEY, {}) or {}
        demand = (plan.get("feed_demand") or {}) if isinstance(plan, dict) else {}
        by_output = {r["output"]: rid for rid, r in recipes.items()}
        output = self.output_counts()
        out = {}
        for item, row in demand.items():
            rid = by_output.get(item)
            if not rid or not isinstance(row, list) or len(row) < 2:
                continue
            short = int(row[0]) - total_stock(item, self.outpost) - output.get(item, 0)
            if short > 0:
                out[rid] = (int(row[1]), short)
        return out

    def output_counts(self):
        out = {}
        try:
            for stack in self.maker.output.stacks():
                out[stack.id] = out.get(stack.id, 0) + stack.count
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.output_counts: output.stacks", error)
        return out

    @staticmethod
    def has_inputs(inputs, loaded, stock):
        """Every input for one craft is in the stockpile or at home."""
        return all(loaded.get(item, 0) + stock.get(item, 0) >= qty for item, qty in inputs.items())

    def pick(self, recipes, deficits, loaded, claims):
        current = self._call("get_recipe", "")
        items = sorted(set(i for rid in deficits for i in recipes[rid]["inputs"]))
        stock = logistics_requests.outpost_stock(items, self.outpost) if items else {}
        ready = []
        for rid, (prio, short) in deficits.items():
            if rid in claims and rid != current and short <= FEED_PER_CRAFT:
                continue
            if self.has_inputs(recipes[rid]["inputs"], loaded, stock):
                ready.append((prio, -short, 0 if rid == current else 1, rid))
        if not ready:
            return None
        ready.sort()
        return ready[0][3]

    # ------------------------------------------------------------ crafting

    def stockpile(self):
        return dict(self._call("get_stockpile", {}))

    def eject_all(self):
        target = local_port_target(self.outpost)
        for item, count in self.stockpile().items():
            if count <= 0 or not target:
                continue
            try:
                self.maker.input.eject(target, item, count)
            except Exception as error:
                swallowed("feed_maker.FeedMakerController.eject_all: input.eject", error)

    def switch_to(self, rid):
        """True once `rid` is the set recipe; ejects the old recipe's leftovers first."""
        current = self._call("get_recipe", "")
        if current == rid:
            return True
        if self._call("is_running", False):
            return False
        self.log.start(f"[{self.name}] Switching recipe '{current or '-'}' -> '{rid}'")
        self.eject_all()
        if current:
            self._call("clear_recipe", None)
        result = self._call("set_recipe", None, rid)
        status = getattr(result, "status", "")
        self.log.end(status or "no result")
        return status == "ok"

    def load(self, inputs):
        """Loads one craft's inputs while the shared stockpile has room for them."""
        loaded = self.stockpile()
        room = int(self._call("get_stockpile_capacity", 200)) - int(self._call("get_stockpile_used", 0))
        need = {item: qty - loaded.get(item, 0) for item, qty in inputs.items() if loaded.get(item, 0) < qty}
        if not need:
            # Current craft covered: preload the next one if it fits.
            if room < sum(inputs.values()):
                return 0
            need = dict(inputs)
        moved = 0
        for item, qty in need.items():
            moved += take_item(self.maker.input, item, qty, outpost=self.outpost)
        return moved

    def drain_output(self):
        if int(self._call("get_output_count", 0)) <= 0:
            return
        try:
            moved = drain_port_to_storage(self.maker.output, outpost=self.outpost)
            if moved:
                self.log.debug(f"[{self.name}] {moved} feed to a Warehouse.")
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.drain_output: drain_port_to_storage", error)
        target = local_port_target(self.outpost)
        if int(self._call("get_output_count", 0)) <= 0 or not target:
            return
        try:
            self.maker.output.connect(target)
            for item, count in self.output_counts().items():
                self.maker.output.send(item, count)
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.drain_output: output.send", error)

    # ---------------------------------------------------------------- loop

    def publish(self, recipes, blocker, curr_tick):
        entry = {
            "recipes": {rid: r["inputs"] for rid, r in recipes.items()},
            "recipe": self._call("get_recipe", ""),
            "running": bool(self._call("is_running", False)),
            "progress": round(float(self._call("get_progress", 0.0)), 3),
            "output": int(self._call("get_output_count", 0)),
            "stockpile": self.stockpile(),
            "tier": int(self._call("tier", 1)),
            "blocker": blocker,
            "tick": curr_tick,
        }

        def updater(status):
            if not isinstance(status, dict):
                status = {}
            for other in list(status.keys()):
                if other != self.name and not wc.fresh(status[other], curr_tick):
                    del status[other]
            status[self.name] = entry
            return status

        if not archive.transaction(wc.FEED_KEY, {}, updater):
            self.log.level("warn").print(f"[{self.name}] {wc.FEED_KEY} write rejected.")

    def shed(self):
        return self.name in (archive.get("power.shedded", []) or [])

    def step(self):
        curr_tick = self.tick()
        self.drain_output()
        recipes = self.recipes(curr_tick)
        deficits = self.deficits(recipes)
        running = bool(self._call("is_running", False))
        blocker = None
        rid = None
        if self.shed():
            blocker = "shed"
        elif deficits:
            rid = self.pick(recipes, deficits, self.stockpile(), self.claims(curr_tick))
            blocker = None if rid else "no_inputs"
        if rid and self.switch_to(rid):
            self.load(recipes[rid]["inputs"])
        if blocker != self._last_blocker:
            if blocker == "no_inputs":
                self.log.print(f"[{self.name}] Feed short {sorted(deficits)} but no recipe has all inputs at home.")
            self._last_blocker = blocker
        self.publish(recipes, blocker, curr_tick)
        busy = running or rid is not None
        return ACTIVE_POLL_S if busy else IDLE_POLL_S

    def run(self):
        self.log.print(f"Feed Maker ({self.name}) online at '{self.outpost_id}'.")
        validate_game_version()
        while True:
            reset_all()
            delay = IDLE_POLL_S
            try:
                delay = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Feed Maker exception: {error}")
            self.parker.update(delay == IDLE_POLL_S)
            flush_all()
            sleep(delay)
