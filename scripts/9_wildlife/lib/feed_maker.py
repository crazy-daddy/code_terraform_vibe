# Feed Maker controller: one per Feed Maker (thin bio/feed_maker.py), same
# shape as lib/seed_supply.py (deficits -> pick -> craft, parked while idle).
#   - Publishes its unlocked recipes ({recipe_id: inputs}) in
#     `wildlife.feed[id]`; the Wildlife planner reads them for readiness and
#     life-form targets, and publishes the life-form requests itself.
#   - What to make: `wildlife.plan.feed_demand` ({feed_item: [home stock
#     target, priority, short]}) against live home stock (Inventory + home
#     Warehouses) and its own output bin. Lowest priority class first, then the
#     largest deficit, among recipes whose inputs are all at home. The set
#     recipe stays while it is short and no recipe of a better class is; rank
#     changes inside a class don't switch. At most MAX_MAKERS_PER_RECIPE fresh
#     Feed Makers pick one recipe, and no more than its deficit has crafts;
#     when too many share one, the lowest ids keep it.
#   - Switching recipe: waits for the running craft, then set_recipe(), which
#     takes a loaded stockpile (only a foreign feed in the output bin blocks
#     it). The loaded Forage stays for the next recipe; items the new recipe
#     doesn't use are ejected only when they leave no room for its craft.
#   - Stocks one craft at a time, the forms before the Forage, and takes the
#     Forage only once every form is in: its landing starts the craft, which
#     ends during the Forage cooldown. The next one is preloaded once the
#     stockpile has room. Finished feed goes straight into the local Habitat
#     housing its species (`wildlife.status`: fresh, unparked, bin below the
#     top-up target), the rest to a home Warehouse (Inventory fallback).
#   - While a craft of the picked recipe runs nothing is decided: the stock
#     walk and the pick run once it has ended.
#   - Soft-shed (`power.shedded`, lib/power.py): starts no new craft.
# Never crafts past the target; idle (no deficit or no inputs) -> parked.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed, call_or
from storage import take_item, drain_port_storage_first, push_to_targets, local_port_target, hit_slot_cap, eject_unneeded
from script_parking import ParkRequester
import logistics_requests
import wildlife_common as wc

ACTIVE_POLL_S = 2.0          # a craft takes 0.3 game h = 7.5 s (Mk II 5 s)
# After a step that moved items: the call returns once its feeder transfer is
# done, and the craft ran during the Forage transfer, so the next step is due now.
FAST_POLL_S = 0.2
IDLE_POLL_S = 20.0
RECIPE_REFRESH_TICKS = 1200  # republish unlocked recipes at least this often
PUBLISH_REFRESH_TICKS = 600  # status rewritten on change, else at least this often
HABITAT_MAP_REFRESH_TICKS = 3000  # local Habitat ids re-listed at least this often
# Feed Makers on one recipe at a time: a Habitat bin holds FEED_TOPUP_TARGET
# (50) feed, two crafts fill it, and more makers only queue on its feeder.
MAX_MAKERS_PER_RECIPE = 2


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
        self._published = None
        self._published_tick = -PUBLISH_REFRESH_TICKS
        self._habitat_ids = None
        self._habitat_ids_tick = 0
        self._picked = None

    def tick(self):
        try:
            return self.clock.tick() if self.clock else 0
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.tick: clock.tick", error)
            return 0

    def _call(self, method, default, *args):
        return call_or("feed_maker.FeedMakerController._call", self.maker, method, default, *args)

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
        """{recipe_id: [feed_maker_id]} picked by other fresh Feed Makers."""
        feed = archive.get(wc.FEED_KEY, {}) or {}
        out = {}
        for other, entry in (feed.items() if isinstance(feed, dict) else []):
            if other != self.name and wc.fresh(entry, curr_tick) and entry.get("picked"):
                out.setdefault(entry["picked"], []).append(other)
        return out

    @staticmethod
    def demand():
        """The planner's `feed_demand` ({feed_item: [target, priority, short]})."""
        plan = archive.get(wc.PLAN_KEY, {}) or {}
        return (plan.get("feed_demand") or {}) if isinstance(plan, dict) else {}

    def home_stock(self, recipes, demand):
        """{item_id: units} at home of every demanded feed and every recipe input, in one walk."""
        items = set(demand)
        for recipe in recipes.values():
            items.update(recipe["inputs"])
        return logistics_requests.outpost_stock(sorted(items), self.outpost)

    def deficits(self, recipes, demand, stock):
        """{recipe_id: (priority, feed short)} against home stock and this output bin."""
        by_output = {r["output"]: rid for rid, r in recipes.items()}
        output = self.output_counts()
        out = {}
        for item, row in demand.items():
            rid = by_output.get(item)
            if not rid or not isinstance(row, list) or len(row) < 2:
                continue
            short = int(row[0]) - stock.get(item, 0) - output.get(item, 0)
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

    def crowded(self, rid, short, claims, current):
        """True when enough other Feed Makers picked `rid`: MAX_MAKERS_PER_RECIPE,
        or fewer when the deficit has fewer crafts. On the current recipe only
        makers with a lower id count, so of a crowd the lowest ids stay."""
        others = claims.get(rid, [])
        if rid == current:
            others = [other for other in others if other < self.name]
        return len(others) >= min(MAX_MAKERS_PER_RECIPE, wc.crafts_for(short))

    def pick(self, recipes, deficits, loaded, claims, stock, current):
        ready = []
        for rid, (prio, short) in deficits.items():
            if self.crowded(rid, short, claims, current):
                continue
            if self.has_inputs(recipes[rid]["inputs"], loaded, stock):
                ready.append((prio, -short, 0 if rid == current else 1, rid))
        if not ready:
            return None
        ready.sort()
        best_class = ready[0][0] // wc.PRIO_RANK_SCALE
        for prio, _short, _not_current, rid in ready:
            if rid == current and prio // wc.PRIO_RANK_SCALE <= best_class:
                return current
        return ready[0][3]

    # ------------------------------------------------------------ crafting

    def stockpile(self):
        return dict(self._call("get_stockpile", {}))

    def eject_strays(self, inputs, slots_full=False):
        """Ejects stockpile items `inputs` doesn't use, only when they leave no room for its craft.

        Room is counted in units; `slots_full=True` (a take() hit the
        stockpile's material-slot cap, storage.hit_slot_cap()) ejects them
        regardless of unit room.
        """
        loaded = self.stockpile()
        room = int(self._call("get_stockpile_capacity", 200)) - int(self._call("get_stockpile_used", 0))
        missing = sum(max(0, qty - loaded.get(item, 0)) for item, qty in inputs.items())
        target = local_port_target(self.outpost)
        if (room >= missing and not slots_full) or not target:
            return
        ejected = eject_unneeded(self.maker.input, inputs, target)
        if ejected:
            reason = "material slots full" if slots_full else f"room {room} < {missing}"
            self.log.debug(f"[{self.name}] Ejected strays ({reason}): {', '.join(ejected)}")

    def switch_to(self, rid, inputs):
        """True once `rid` is the set recipe; the loaded stockpile carries over."""
        current = self._call("get_recipe", "")
        if current == rid:
            return True
        if self._call("is_running", False) or float(self._call("get_progress", 0.0)) > 0:
            return False
        self.eject_strays(inputs)
        result = self._call("set_recipe", None, rid)
        status = getattr(result, "status", "")
        self.log.debug(f"[{self.name}] Recipe '{current or '-'}' -> '{rid}': {status or 'no result'}")
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
        # Stock lands when a transfer starts; the feeder then cools down for the
        # units moved. Forms first, Forage (100 units) last and only once every
        # form is in: the craft starts with the Forage and ends during its
        # cooldown, which is longer than the craft.
        order = sorted(need.items(), key=lambda kv: kv[1])
        moved = 0
        missing = False
        for index, (item, qty) in enumerate(order):
            if missing and index == len(order) - 1:
                self.log.debug(f"[{self.name}] {item} held back: a form is still missing.")
                break
            report = {}
            got = take_item(self.maker.input, item, qty, outpost=self.outpost, report=report)
            moved += got
            if hit_slot_cap(report):
                # Leftovers of earlier recipes hold every material slot.
                self.eject_strays(inputs, slots_full=True)
                break
            missing = missing or got < qty
        return moved

    def local_habitat_ids(self, curr_tick):
        """Habitat ids at this outpost, refreshed every HABITAT_MAP_REFRESH_TICKS (placements rarely change)."""
        if self._habitat_ids is not None and curr_tick - self._habitat_ids_tick < HABITAT_MAP_REFRESH_TICKS:
            return self._habitat_ids
        ids = []
        try:
            ids = [getattr(ref, "id", None) for ref in self.outpost.buildings("habitat")] if self.outpost else []
        except Exception as error:
            swallowed("feed_maker.FeedMakerController.local_habitat_ids: outpost.buildings", error)
        self._habitat_ids = [i for i in ids if i]
        self._habitat_ids_tick = curr_tick
        return self._habitat_ids

    def habitat_targets(self, item, curr_tick):
        """[(habitat_id, units)] for local Habitats whose published status wants
        `item` as feed: fresh, not parked (a parked Habitat is woken on storage
        stock only), bin below FEED_TOPUP_TARGET."""
        status = archive.get(wc.STATUS_KEY, {}) or {}
        targets = []
        for hid in self.local_habitat_ids(curr_tick):
            entry = status.get(hid) if isinstance(status, dict) else None
            if not isinstance(entry, dict) or not wc.fresh(entry, curr_tick) or entry.get("feed_item") != item or entry.get("parked"):
                continue
            room = int(wc.FEED_TOPUP_TARGET - float(entry.get("feed_level") or 0.0))
            if room > 0:
                targets.append((hid, room))
        return targets

    def drain_output(self, curr_tick):
        """Empties the output bin: feed first straight into the local Habitat
        housing its species, the rest to a home Warehouse (Inventory fallback).
        True when it held feed."""
        if int(self._call("get_output_count", 0)) <= 0:
            return False
        for item, count in self.output_counts().items():
            for hid, moved in push_to_targets(self.maker.output, item, count, self.habitat_targets(item, curr_tick)):
                self.log.debug(f"[{self.name}] {moved} {item} -> '{hid}'.")
        moved = drain_port_storage_first(self.maker.output, outpost=self.outpost)
        if moved:
            self.log.debug(f"[{self.name}] {moved} feed to storage.")
        return True

    # ---------------------------------------------------------------- loop

    def publish(self, recipes, blocker, curr_tick):
        """Writes `wildlife.feed[id]` when recipe, run state or blocker change, else every PUBLISH_REFRESH_TICKS."""
        key = (self._call("get_recipe", ""), self._picked, bool(self._call("is_running", False)), blocker, len(recipes))
        if key == self._published and curr_tick - self._published_tick < PUBLISH_REFRESH_TICKS:
            return
        entry = {
            "recipes": {rid: r["inputs"] for rid, r in recipes.items()},
            "recipe": self._call("get_recipe", ""),
            "picked": self._picked,
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
            return
        self._published = key
        self._published_tick = curr_tick

    def shed(self):
        return self.name in (archive.get("power.shedded", []) or [])

    def step(self):
        curr_tick = self.tick()
        drained = self.drain_output(curr_tick)
        recipes = self.recipes(curr_tick)
        running = bool(self._call("is_running", False))
        current = self._call("get_recipe", "")
        blocker = None
        rid = None
        deficits = {}
        if self.shed():
            blocker = "shed"
        elif running and self._picked == current and current in recipes:
            # Its inputs are in; only a preload of the same recipe can follow.
            rid = current
        else:
            demand = self.demand()
            stock = self.home_stock(recipes, demand) if demand else {}
            deficits = self.deficits(recipes, demand, stock)
            if deficits:
                rid = self.pick(recipes, deficits, self.stockpile(), self.claims(curr_tick), stock, current)
                blocker = None if rid else "no_inputs"
        self._picked = rid
        moved = 0
        if rid and self.switch_to(rid, recipes[rid]["inputs"]):
            moved = self.load(recipes[rid]["inputs"])
        if blocker != self._last_blocker:
            if blocker == "no_inputs":
                self.log.print(f"[{self.name}] Feed short {sorted(deficits)} but no recipe has all inputs at home.")
            self._last_blocker = blocker
        self.publish(recipes, blocker, curr_tick)
        if moved or drained:
            return FAST_POLL_S
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
