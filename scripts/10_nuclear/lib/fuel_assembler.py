# Fuel Assembler controller: one per Fuel Assembler (thin nuclear/fuel_assembler.py).
# Two recipes, both 4 Raw Uranium + Lead Plates (docs/components/fuel_assembler.md):
#   craft_fuel_rod         4 U + 2 plates, 6 game h, 1,800 W  -> Fuel Rod (hot)
#   craft_nuclear_battery  4 U + 3 plates, 4 game h, 1,200 W  -> Nuclear Battery
#   - What to make: Fuel Rods first, to a stock of the local consumers' reserve
#     (lead_cask.consumer_rod_reserve(): Reactors and Mk IV heater/pressure/O2
#     generators at this outpost) + rods owed to Supply Dock orders here.
#     Supply Docks leave that reserve in the casks. Counted in this outpost's
#     Lead Casks, the consumers' input slots and the output buffer. Nuclear
#     Batteries next, for manual orders (`fabricator.manual_orders`), Supply
#     Dock orders and Construction Blueprints, against network stock.
#   - Lead Casks (lib/lead_cask.py): keeps one cask per outpost in the
#     "fuel_rod" role (`lead_cask.roles`) and repairs it when a Depot filled
#     it with uranium: into the other casks, else into this assembler's own
#     stockpile (up to one craft's worth), so the cask unlatches even with
#     every uranium cask full. Fuel Rods leave only into that cask; Supply Docks,
#     Reactors and Mk IV generators pull from it themselves.
#   - Inputs: the input port holds one source at a time. Raw Uranium comes from
#     the Lead Casks here (lead_cask.take_from_casks()); Lead Plates from
#     Inventory (home) or local Warehouses via storage.take_item(). Stages at
#     most STAGED_CRAFTS crafts and never more than the shortfall.
#   - Lead Plates: every Fuel Assembler outpost keeps a stockpile
#     (site_supply.SITE_STOCK_TARGETS). At home a standing upgrade order
#     (`fabricator.upgrade_orders`, requester "fuel_assembler") also asks the
#     Fabricators for the next PLATE_ORDER_CRAFTS crafts' plates, cleared when
#     nothing is short. Not posted off home: upgrade-order roots are consumed
#     at home (production.fabricator_root_targets()), so they would pull plates
#     away from a remote assembler.
#   - Power: a craft draws 1.2-1.8 kW while it advances. New inputs are staged
#     only while this grid's reserve (lower of battery and combined
#     battery+steam fraction, lib/power.py) is at least START_RESERVE_FRACTION,
#     so crafts run as bursts on a full bank. The Power Guard hard-sheds
#     `fuel_assembler_*` in tier 1 (progress survives the breaker cut).
#   - Idle (nothing short, or no uranium/plates): clears the recipe and parks.

from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item, takeable_stock, total_stock, drain_port_inventory_first, outpost_is_home, send_stack
from production import get_manual_orders, consume_manual_order, blueprint_required_items, dock_remaining_requirements, set_upgrade_order
from script_parking import ParkRequester
import lead_cask
import power

ROD_RECIPE = "craft_fuel_rod"
BATTERY_RECIPE = "craft_nuclear_battery"
ROD_ITEM = "fuel_rod"
BATTERY_ITEM = "nuclear_battery"
URANIUM_ITEM = "raw_uranium"
PLATE_ITEM = "lead_plate"
SUPPLY_DOCK_TYPE_ID = "supply_dock"
# Used when list_recipes() is unreadable; the game's own recipe table.
FALLBACK_RECIPES = {
    ROD_RECIPE: {"output": ROD_ITEM, "inputs": {URANIUM_ITEM: 4, PLATE_ITEM: 2}},
    BATTERY_RECIPE: {"output": BATTERY_ITEM, "inputs": {URANIUM_ITEM: 4, PLATE_ITEM: 3}},
}

# Crafts staged in the 40-unit stockpile at once (one craft = 6-7 units).
STAGED_CRAFTS = 2
# Raw Uranium the stockpile may hold when taking it out of a latched rod cask
# (leaves room for the plates of the crafts it feeds).
UNLATCH_STAGE_UNITS = 24
# Crafts' worth of Lead Plates requested from the Fabricators ahead of need.
PLATE_ORDER_CRAFTS = 2
PLATE_ORDER_REQUESTER = "fuel_assembler"
# No new inputs are staged below this grid reserve fraction.
START_RESERVE_FRACTION = 0.6

ACTIVE_POLL_S = 5.0      # a rod craft is 6 game h = 150 s real
IDLE_POLL_S = 20.0
RECIPE_REFRESH_TICKS = 1200


class FuelAssemblerController:
    """Crafts Fuel Rods to the local consumers' stock target, then Nuclear Batteries to open demand."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "fuel_assembler")
        self.outpost = getattr(machine, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.clock = get_component("clock")
        self.power = get_component("power_control")
        self.log = TreeConsole(module="fuel_assembler")
        self.parker = ParkRequester(self.name, "fuel_assembler")
        self._recipes = {}
        self._recipes_tick = None
        self._last_blocker = None
        self._last_cask_note = None

    def tick(self):
        try:
            return self.clock.tick() if self.clock else 0
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController.tick: clock.tick", error)
            return 0

    def _call(self, method, default, *args):
        fn = getattr(self.machine, method, None)
        if fn is None:
            return default
        try:
            value = fn(*args)
        except Exception as error:
            swallowed(f"fuel_assembler.FuelAssemblerController._call: {method}", error)
            return default
        return default if value is None else value

    def at_home(self):
        return outpost_is_home(self.outpost)

    def take_outpost(self):
        """storage.take_item()'s outpost argument: None at home (Inventory + home Warehouses), else this outpost."""
        return None if self.at_home() else self.outpost

    def crafting(self):
        """A craft is advancing or paused mid-way (set_recipe() answers busy then)."""
        return bool(self._call("is_running", False)) or float(self._call("get_progress", 0.0)) > 0

    # ------------------------------------------------------------ recipes

    def recipes(self, curr_tick):
        """{recipe_id: {"output": item, "inputs": {item: qty}}} of unlocked recipes, refreshed every RECIPE_REFRESH_TICKS."""
        if self._recipes_tick is not None and 0 <= curr_tick - self._recipes_tick < RECIPE_REFRESH_TICKS:
            return self._recipes
        self._recipes_tick = curr_tick
        out = {}
        listed = self._call("list_recipes", None)
        if listed is None:
            out = {rid: {"output": r["output"], "inputs": dict(r["inputs"])} for rid, r in FALLBACK_RECIPES.items()}
        else:
            for recipe in listed:
                recipe_id = getattr(recipe, "id", None)
                if recipe_id:
                    out[recipe_id] = {"output": getattr(recipe, "output_item", ""), "inputs": dict(getattr(recipe, "inputs", None) or {})}
        self._recipes = out
        return out

    # -------------------------------------------------------- local world

    def _buildings(self, type_id):
        """Components of type_id at this outpost."""
        if self.outpost is None or not hasattr(self.outpost, "buildings"):
            return []
        try:
            refs = self.outpost.buildings(type_id)
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController._buildings: outpost.buildings", error)
            return []
        out = []
        for ref in refs or []:
            component = get_component(getattr(ref, "id", ""))
            if component is not None:
                out.append(component)
        return out

    def rod_consumers(self):
        """(reactors, mk4 generators) at this outpost."""
        return lead_cask.rod_consumers(self.outpost)

    def dock_rods_owed(self):
        """Fuel Rods still owed to the orders of Supply Docks at this outpost."""
        owed_total = 0
        for dock in self._buildings(SUPPLY_DOCK_TYPE_ID):
            try:
                order = dock.current_order() if hasattr(dock, "current_order") else None
                required = (getattr(order, "requires", None) or {}).get(ROD_ITEM, 0) if order else 0
                if required <= 0:
                    continue
                shipped = (getattr(order, "shipped", None) or {}).get(ROD_ITEM, 0)
                owed_total += max(0, required - shipped - int(dock.count(ROD_ITEM)))
            except Exception as error:
                swallowed("fuel_assembler.FuelAssemblerController.dock_rods_owed: dock read", error)
        return owed_total

    def output_counts(self):
        out = {}
        try:
            for stack in self.machine.output.stacks():
                out[stack.id] = out.get(stack.id, 0) + stack.count
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController.output_counts: output.stacks", error)
        return out

    # ------------------------------------------------------------- demand

    def shortfalls(self, casks, recipes):
        """[(recipe_id, crafts short)] in priority order (rods first), only recipes that are unlocked and short.

        A craft in progress counts as made, so the shortfall never includes it."""
        current = self._call("get_recipe", "")
        in_progress = 1 if self.crafting() else 0
        buffered = self.output_counts()
        out = []
        if ROD_RECIPE in recipes:
            reactors, mk4 = self.rod_consumers()
            docks = self.dock_rods_owed()
            target = lead_cask.consumer_rod_reserve(reactors, mk4) + docks
            have = lead_cask.cask_stock(ROD_ITEM, casks=casks) + lead_cask.staged_rods(reactors + mk4) + buffered.get(ROD_ITEM, 0)
            have += in_progress if current == ROD_RECIPE else 0
            self.log.debug(f"rods: target={target} ({len(reactors)} reactor(s), {len(mk4)} Mk IV, {docks} for docks) have={have}")
            if target > have:
                out.append((ROD_RECIPE, target - have))
        if BATTERY_RECIPE in recipes:
            manual = get_manual_orders().get(BATTERY_ITEM, 0)
            open_need = self.dock_battery_need() + blueprint_required_items().get(BATTERY_ITEM, 0)
            pending = buffered.get(BATTERY_ITEM, 0) + (in_progress if current == BATTERY_RECIPE else 0)
            short = manual + max(0, open_need - total_stock(BATTERY_ITEM)) - pending
            self.log.debug(f"batteries: manual={manual} docks+blueprints={open_need} pending={pending} -> short={short}")
            if short > 0:
                out.append((BATTERY_RECIPE, short))
        return out

    @staticmethod
    def dock_battery_need():
        """Nuclear Batteries still owed to every active Supply Dock order (shipped and loaded units subtracted)."""
        try:
            return max(0, dock_remaining_requirements().get(BATTERY_ITEM, 0))
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController.dock_battery_need: dock_remaining_requirements", error)
            return 0

    def reserve_ok(self):
        """(ok, fraction): this grid's reserve allows staging a new craft. No measurable storage counts as ok."""
        grid = None
        if self.power is not None and hasattr(self.power, "grid"):
            try:
                grid = self.power.grid(self.name)
            except Exception as error:
                swallowed("fuel_assembler.FuelAssemblerController.reserve_ok: power.grid", error)
        if grid is None or not hasattr(power, "measure_grid"):
            return True, None
        try:
            now = power.measure_grid(grid, power.grid_steam_tank_ids(grid))
            fractions = [f for f in (power.reserve_fraction(now), now["bat_wh"] / now["bat_cap"] if now["bat_cap"] > 0 else None) if f is not None]
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController.reserve_ok: power.measure_grid", error)
            return False, None
        if not fractions:
            return True, None
        fraction = min(fractions)
        return fraction >= START_RESERVE_FRACTION, fraction

    # ------------------------------------------------------------ crafting

    def stockpile(self):
        return dict(self._call("get_stockpile", {}))

    def available(self, item_id, casks):
        """Units of item_id this assembler can pull at its outpost."""
        if item_id == URANIUM_ITEM:
            return lead_cask.cask_stock(URANIUM_ITEM, casks=casks)
        return takeable_stock(item_id, self.take_outpost())

    def can_stage(self, inputs, casks):
        """True when the stockpile plus local stock covers one craft."""
        staged = self.stockpile()
        return all(staged.get(item, 0) + self.available(item, casks) >= qty for item, qty in inputs.items())

    def pick(self, shortfalls, recipes, casks):
        """First short recipe one craft of which can be staged, or (None, 0)."""
        for recipe_id, crafts in shortfalls:
            if self.can_stage(recipes[recipe_id]["inputs"], casks):
                return recipe_id, crafts
        return None, 0

    def switch_to(self, recipe_id):
        """True once recipe_id is set. Both recipes take the same inputs, so the stockpile stays."""
        current = self._call("get_recipe", "")
        if current == recipe_id:
            return True
        if self.crafting():
            return False
        self.log.start(f"[{self.name}] Recipe '{current or '-'}' -> '{recipe_id}'")
        result = self._call("set_recipe", None, recipe_id)
        status = getattr(result, "status", "")
        self.log.end(status or "no result")
        return status == "ok"

    def load(self, recipe_id, inputs, crafts, casks):
        """Stages inputs for min(crafts, STAGED_CRAFTS) crafts. Returns units moved."""
        staged = self.stockpile()
        want = min(crafts, STAGED_CRAFTS)
        moved = 0
        loaded = []
        for item, qty in inputs.items():
            need = qty * want - staged.get(item, 0)
            if need <= 0:
                continue
            if item == URANIUM_ITEM:
                got = lead_cask.take_from_casks(self.machine.input, URANIUM_ITEM, need, casks=casks)
            else:
                got = take_item(self.machine.input, item, need, outpost=self.take_outpost())
            if got > 0:
                loaded.append(f"{got}x {item}")
            moved += got
        if loaded:
            self.log.print(f"[{self.name}] Loaded {', '.join(loaded)} for {recipe_id}.")
        return moved

    def tend_casks(self, casks):
        """Keeps a "fuel_rod" cask assigned here and empties uranium out of it. Returns the rod cask id or None."""
        rod_cask, note = lead_cask.ensure_rod_cask(self.outpost, casks)
        if note and note != self._last_cask_note:
            level = "info" if rod_cask else "warn"
            self.log.level(level).print(f"[{self.name}] Lead Casks at '{self.outpost_id}': {note}.")
        self._last_cask_note = note
        moved = lead_cask.repair(self.outpost, casks)
        if moved:
            self.log.print(f"[{self.name}] Moved {moved}x {URANIUM_ITEM} out of the Fuel Rod cask '{rod_cask}'.")
        self.unlatch_rod_cask(rod_cask, casks)
        return rod_cask

    def unlatch_rod_cask(self, rod_cask, casks):
        """Takes Raw Uranium that repair() had no room for out of the rod cask into this
        assembler's stockpile, up to UNLATCH_STAGE_UNITS staged. Otherwise finished rods
        could never leave the output buffer and the Reactors would run dry."""
        entry = next((c for c in casks if c["id"] == rod_cask), None)
        if entry is None or entry["material"] != URANIUM_ITEM or entry["count"] <= 0:
            return 0
        room = UNLATCH_STAGE_UNITS - self.stockpile().get(URANIUM_ITEM, 0)
        if room <= 0:
            self.log.debug(f"rod cask '{rod_cask}' holds {entry['count']}x {URANIUM_ITEM}, stockpile already holds {UNLATCH_STAGE_UNITS}")
            return 0
        if not self._call("get_recipe", "") and not self.switch_to(ROD_RECIPE):
            return 0
        moved = lead_cask.take_from_casks(self.machine.input, URANIUM_ITEM, min(room, entry["count"]), casks=[entry])
        if moved:
            self.log.print(f"[{self.name}] Staged {moved}x {URANIUM_ITEM} from the Fuel Rod cask '{rod_cask}' (no other cask had room).")
        return moved

    def drain_output(self, rod_cask):
        """Moves finished products out. Returns True when anything moved."""
        counts = self.output_counts()
        moved_any = False
        rods = counts.get(ROD_ITEM, 0)
        if rods > 0 and rod_cask is None:
            self.log.debug(f"{rods} Fuel Rod(s) waiting for a Fuel Rod cask")
        elif rods > 0:
            moved, status, message = send_stack(self.machine.output, ROD_ITEM, rods, rod_cask)
            if moved > 0:
                moved_any = True
                self.log.print(f"[{self.name}] Sent {moved}x {ROD_ITEM} to '{rod_cask}'.")
            elif status not in ("busy", "exception"):
                self.log.level("warn").print(f"[{self.name}] Rod output to '{rod_cask}': {status} - {message}")
        if counts.get(BATTERY_ITEM, 0) > 0:
            for item_id, moved, destination, status, message in drain_port_inventory_first(self.machine.output, outpost=self.outpost):
                if moved > 0:
                    moved_any = True
                    self.log.print(f"[{self.name}] Sent {moved}x {item_id} to {destination}.")
                    consume_manual_order(item_id, moved, self.outpost)
                elif status not in ("busy", "no_op"):
                    self.log.level("warn").print(f"[{self.name}] Output notice: {status} - {message}")
        return moved_any

    def clear_idle_recipe(self):
        """Clears the recipe so staged leftovers can't start an unwanted craft."""
        current = self._call("get_recipe", "")
        if not current or self.crafting():
            return
        result = self._call("clear_recipe", None)
        status = getattr(result, "status", "")
        if status == "ok":
            self.log.print(f"[{self.name}] Nothing short: cleared recipe '{current}'.")
        else:
            self.log.debug(f"clear_recipe(): {status or 'no result'}, retrying next poll")

    def order_plates(self, shortfalls, recipes):
        """Standing Lead Plate order for the next PLATE_ORDER_CRAFTS crafts; cleared when nothing is short or off home."""
        plates = 0
        if not self.at_home():
            shortfalls = []
        crafts_left = PLATE_ORDER_CRAFTS
        for recipe_id, crafts in shortfalls:
            take = min(crafts, crafts_left)
            plates += recipes[recipe_id]["inputs"].get(PLATE_ITEM, 0) * take
            crafts_left -= take
            if crafts_left <= 0:
                break
        try:
            set_upgrade_order(PLATE_ORDER_REQUESTER, {PLATE_ITEM: plates} if plates > 0 else None)
        except Exception as error:
            swallowed("fuel_assembler.FuelAssemblerController.order_plates: set_upgrade_order", error)

    # ---------------------------------------------------------------- loop

    def shed(self):
        shedded = archive.get("power.shedded", []) or []
        return isinstance(shedded, list) and self.name in shedded

    def step(self):
        """One poll. Returns the sleep before the next one."""
        curr_tick = self.tick()
        recipes = self.recipes(curr_tick)
        casks = lead_cask.casks_at(self.outpost)
        rod_cask = self.tend_casks(casks)
        worked = self.drain_output(rod_cask)
        if worked:
            casks = lead_cask.casks_at(self.outpost)  # rods just moved into a cask
        running = bool(self._call("is_running", False))
        self.log.start(f"[{self.name}] plan", level="debug")
        shortfalls = self.shortfalls(casks, recipes)
        self.order_plates(shortfalls, recipes)
        blocker = None
        recipe_id, crafts = None, 0
        if not shortfalls:
            blocker = "no_demand"
        elif self.shed():
            blocker = "shed"
        else:
            # Without a Fuel Rod cask finished rods could not leave the output buffer.
            pickable = [s for s in shortfalls if s[0] != ROD_RECIPE or rod_cask is not None]
            recipe_id, crafts = self.pick(pickable, recipes, casks)
            if recipe_id is None:
                blocker = "no_inputs" if pickable else "no_rod_cask"
        self.log.debug(f"shortfalls={shortfalls} pick={recipe_id} crafts={crafts} blocker={blocker}")
        self.log.end()

        if recipe_id is not None and self.switch_to(recipe_id):
            ok, fraction = self.reserve_ok()
            if ok:
                worked = self.load(recipe_id, recipes[recipe_id]["inputs"], crafts, casks) > 0 or worked
            else:
                blocker = "low_reserve"
                shown = "unreadable" if fraction is None else f"{fraction:.0%}"
                self.log.debug(f"grid reserve {shown} < {START_RESERVE_FRACTION:.0%}, not staging a new craft")
        elif blocker == "no_demand":
            self.clear_idle_recipe()

        if blocker != self._last_blocker:
            if blocker == "no_inputs":
                short = ", ".join(f"{rid} x{n}" for rid, n in shortfalls)
                self.log.print(f"[{self.name}] Short {short}, but Raw Uranium (Lead Cask) or Lead Plates are missing at '{self.outpost_id}'.")
            elif blocker == "low_reserve":
                self.log.print(f"[{self.name}] Waiting for the grid reserve to reach {START_RESERVE_FRACTION:.0%} before the next craft.")
            self._last_blocker = blocker
        busy = running or worked or (recipe_id is not None and blocker is None)
        return ACTIVE_POLL_S if busy or blocker == "low_reserve" else IDLE_POLL_S

    def run(self):
        self.log.print(f"Fuel Assembler ({self.name}) online at '{self.outpost_id}'.")
        validate_game_version()
        while True:
            reset_all()
            delay = IDLE_POLL_S
            try:
                delay = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Fuel Assembler exception: {error}")
            self.parker.update(delay == IDLE_POLL_S)
            flush_all()
            sleep(delay)
