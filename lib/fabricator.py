# Shared Fabricator automation: maintain building stock and fulfill active orders.
from production import get_fabricator_targets, get_fabricator_active_recipe, can_source_item, can_source_fluid, find_dock_order_requiring, get_manual_orders, consume_manual_order, craft_prefill_units, fluid_building_is_viable, FLUID_SOURCE_TYPE_IDS
from archive import archive
from storage import take_item, total_stock, best_unload_target

# Mirrors lib/smelter.py's SMELTER_RECIPE_CLAIM_STALE_TICKS/RECIPE_CLAIMS_KEY
# exactly, same reasoning: with several Fabricators, choose_recipe() picking
# strictly by biggest-shortfall would have every one of them converge on the
# SAME top-shortfall recipe while other demanded outputs sit untouched. A
# claim on the recipe id it's about to set lets a Fabricator move on to its
# next-best sourceable candidate if another Fabricator already holds it.
FABRICATOR_RECIPE_CLAIM_STALE_TICKS = 600
RECIPE_CLAIMS_KEY = "fabricator.recipe_claims"

# load_inputs() used to request its ENTIRE remaining batch (required_per_craft
# * crafts_remaining, up to several dozen units) in one take_item() call --
# found from a real case: two Fabricators both needing Glass, one polled
# first and took() the whole available stock (e.g. 44 units) in a single
# transfer, leaving the other at 0 with nothing left to grab even though
# demand called for splitting it. Capping each take_item() call to this many
# units bounds any single grab. The main fix for sharing a contested source
# fairly is now lib/production.py's craft_prefill_units() -- see
# load_inputs()'s own comment -- which keeps every Fabricator's total ask
# small and recipe-scaled instead of racing for the full shortfall; this
# constant remains as a simple per-call ceiling on top of that. Supply Dock
# deliberately does NOT use either (see lib/supply_dock.py) -- it has no
# sibling competing for the same order's materials, so there's nothing to
# share fairly with.
FABRICATOR_LOAD_CHUNK_SIZE = 10

# ensure_fluid_connections() mirrors lib/steam_turbine.py's
# ensure_input_connection() almost exactly -- both are an INPUT FluidPort
# declaring its own upstream source (a Gas/Liquid Tank has no script of its
# own, so nothing else ever calls connect() on the other side of the pipe).
# The Fabricator has no is_stalled() of its own (unlike Steam Turbine/Thermal
# Cap/Water Pump), so reachability is instead inferred from flow_rate()
# staying 0 for several consecutive ticks while the port still has room to
# receive (level() < capacity()) -- connect()'s "ok" status alone never
# verifies a completed pipe route exists (docs/guide/infrastructure_and_pipes.md).
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
# Same per-entry (not shared-clock) blacklist expiry as every other
# discover/connect/blacklist controller in this project -- see
# lib/thermal_cap.py's RESCAN_INTERVAL_TICKS for the full reasoning.
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_STEPS = 20


class FabricatorController:
    """Selects unlocked pipe/power recipes and feeds them from Inventory or a Warehouse."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "fabricator_1")
        self.connected_input = False
        self.connected_output = False
        self.clock = get_component("clock")

        # Per-fluid-key (water_in/steam_in/oil_in) connection state -- see
        # ensure_fluid_connections(). Keyed dicts rather than one shared value
        # since a recipe can need more than one fluid at once (e.g. an
        # oil-refining recipe needs both oil_in and water_in), and each port's
        # own source is entirely independent of the others.
        self._fluid_connected = {}
        self._fluid_stall_streak = {}
        self._fluid_unreachable = {}          # fluid_key -> {source_id: tick}
        self._fluid_cached_candidates = {}    # fluid_key -> [ids]
        self._fluid_ticks_since_discovery = {}

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def claim_recipe(self, recipe_id):
        """Claims recipe_id for this Fabricator, or refreshes its own existing claim. See lib/smelter.py's claim_recipe() -- identical shape/reasoning, separate archive key."""
        current_tick = self.get_current_tick()

        def updater(claims):
            claims = dict(claims or {})
            existing = claims.get(recipe_id)
            if isinstance(existing, dict) and existing.get("fabricator") != self.name:
                age = current_tick - existing.get("tick", 0)
                if current_tick == 0 or age <= FABRICATOR_RECIPE_CLAIM_STALE_TICKS:
                    return claims  # still held by someone else, fresh -- leave untouched
            claims[recipe_id] = {"fabricator": self.name, "tick": current_tick}
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
        except Exception:
            return True  # can't verify; don't block production over an archive hiccup

        claims = archive.get(RECIPE_CLAIMS_KEY, {}) or {}
        owner = (claims.get(recipe_id) or {}).get("fabricator")
        return owner == self.name

    def release_recipe(self, recipe_id):
        if not recipe_id:
            return

        def updater(claims):
            claims = dict(claims or {})
            if (claims.get(recipe_id) or {}).get("fabricator") == self.name:
                del claims[recipe_id]
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
        except Exception:
            pass

    def is_shedded(self):
        """
        True when the Power Guard (lib/power.py's PowerGridManager, via
        SOFT_SHED_PATTERNS) has marked this Fabricator for shedding.
        Smelter/Fabricator are soft-shed -- tracked in power.shedded but
        never actually powered off, since a Fabricator only draws power
        while actively crafting; simply not starting/topping-up production
        already achieves the same saving a breaker cut would, without an
        external wake call needed to undo it. See lib/smelter.py's
        SmelterController.is_shedded() -- identical shape, separate machine.
        """
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

    def ensure_connection(self):
        if not self.connected_input and hasattr(self.machine, "input"):
            result = self.machine.input.connect("inventory")
            self.connected_input = result.status == "ok"
            if not self.connected_input and result.status not in ["busy"]:
                print(f"[{self.name}] Input connection notice: {result.status} - {result.message}")
        if not self.connected_output and hasattr(self.machine, "output"):
            result = self.machine.output.connect("inventory")
            self.connected_output = result.status == "ok"
            if not self.connected_output and result.status not in ["busy"]:
                print(f"[{self.name}] Output connection notice: {result.status} - {result.message}")

    def _fluid_is_blacklisted(self, fluid_key, source_id, curr_tick):
        """Per-entry blacklist expiry -- see lib/thermal_cap.py's identical is_blacklisted()."""
        blacklisted_at = self._fluid_unreachable.get(fluid_key, {}).get(source_id)
        if blacklisted_at is None:
            return False
        age = curr_tick - blacklisted_at
        return curr_tick == 0 or age < FLUID_RESCAN_INTERVAL_TICKS

    def _discover_fluid_candidates_cached(self, fluid_key, type_ids):
        """
        Candidate source ids network-wide for fluid_key (e.g. every
        water_pump/steam_condenser/liquid_tank/large_liquid_tank for
        "water_in" -- see production.FLUID_SOURCE_TYPE_IDS), refreshed at
        most every FLUID_DISCOVERY_CACHE_INTERVAL_STEPS calls. Only reached
        from ensure_fluid_connections()'s slow path (a healthy connection
        returns long before this).
        """
        ticks = self._fluid_ticks_since_discovery.get(fluid_key, 0)
        cached = self._fluid_cached_candidates.get(fluid_key)
        if cached is None or ticks >= FLUID_DISCOVERY_CACHE_INTERVAL_STEPS:
            ids = []
            network = get_component("outpost_network")
            if network and hasattr(network, "outposts"):
                try:
                    for outpost in network.outposts():
                        for type_id in type_ids:
                            for building in outpost.buildings(type_id):
                                if not fluid_building_is_viable(fluid_key, type_id, building):
                                    continue  # e.g. a Liquid Tank latched to a different fluid, or empty with no producer to ever fill it -- see production.fluid_building_is_viable()
                                b_id = getattr(building, "id", None)
                                if b_id:
                                    ids.append(b_id)
                except Exception:
                    pass
            self._fluid_cached_candidates[fluid_key] = ids
            self._fluid_ticks_since_discovery[fluid_key] = 0
        else:
            self._fluid_ticks_since_discovery[fluid_key] = ticks + 1
        return self._fluid_cached_candidates[fluid_key]

    def ensure_fluid_connections(self, recipe):
        """
        Connects each fluid_input the active recipe declares (recipe.fluid_inputs,
        e.g. {"water_in": 1.0} -- a separate field from .inputs, delivered via
        a FluidPort, not an Inventory/Warehouse take) to a reachable source
        building network-wide. A Liquid/Gas Tank or Water Pump has no script
        of its own, so nothing else ever calls connect() on the other side of
        the pipe -- this Fabricator's own script must declare the link, same
        role lib/steam_turbine.py's ensure_input_connection() plays for
        steam_in. See production.FLUID_SOURCE_TYPE_IDS for which building
        types satisfy each fluid_key.
        """
        if not recipe:
            return
        fluid_inputs = getattr(recipe, "fluid_inputs", {}) or {}
        if not fluid_inputs:
            return

        curr_tick = self.get_current_tick()

        for fluid_key, type_ids in FLUID_SOURCE_TYPE_IDS.items():
            if fluid_key not in fluid_inputs:
                continue
            port = getattr(self.machine, fluid_key, None)
            if not port or not hasattr(port, "connect"):
                continue

            # No is_stalled() exists on the Fabricator itself (unlike Steam
            # Turbine/Thermal Cap/Water Pump), so infer reachability from
            # flow_rate() staying 0 while there's still room to receive
            # (level() < capacity()) -- a legitimately full port also reads
            # flow_rate()==0, and that's not a stall.
            is_starved = False
            try:
                level = port.level() if hasattr(port, "level") else 0
                capacity = port.capacity() if hasattr(port, "capacity") else 0
                flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
                is_starved = flow == 0 and (not capacity or level < capacity)
            except Exception:
                is_starved = False

            was_connected = self._fluid_connected.get(fluid_key, False)
            streak = self._fluid_stall_streak.get(fluid_key, 0)
            streak = streak + 1 if (was_connected and is_starved) else 0
            self._fluid_stall_streak[fluid_key] = streak

            if was_connected:
                if streak < FLUID_STALL_STREAK_BLACKLIST_THRESHOLD:
                    continue
                current_id = None
                try:
                    current_id = port.connected_to() if hasattr(port, "connected_to") else None
                except Exception:
                    pass
                if current_id:
                    self._fluid_unreachable.setdefault(fluid_key, {})[current_id] = curr_tick
                    print(f"[{self.name}] '{current_id}' ({fluid_key}) starved for {streak} consecutive ticks -- likely no completed pipe route. Blacklisting and picking a different source.")
                self._fluid_connected[fluid_key] = False
                self._fluid_stall_streak[fluid_key] = 0

            all_known_candidates = self._discover_fluid_candidates_cached(fluid_key, type_ids)
            candidates = [c for c in all_known_candidates if not self._fluid_is_blacklisted(fluid_key, c, curr_tick)]
            if not candidates:
                # Every known source is still within its own blacklist window
                # (or none exist at all) -- deliberately do NOT wipe the
                # blacklist here; each entry expires on its own schedule.
                if all_known_candidates:
                    print(f"[{self.name}] Every known {fluid_key} source is still within its blacklist window; waiting for one to expire.")
                continue

            for source_id in candidates:
                try:
                    res = port.connect(source_id)
                except Exception:
                    continue
                if res.status == "ok":
                    self._fluid_connected[fluid_key] = True
                    print(f"[{self.name}] Connected {fluid_key} -> '{source_id}'.")
                    break
                elif res.status != "busy":
                    print(f"[{self.name}] {fluid_key} connect notice for '{source_id}': {res.status} - {res.message}")

    def recipe_is_sourceable(self, recipe):
        """Whether every input of this recipe -- solid and fluid alike -- has a currently known supply."""
        for item_id in (getattr(recipe, "inputs", {}) or {}):
            if not can_source_item(item_id):
                return False
        # fluid_inputs (e.g. {"water_in": 1.0}) is a separate field from
        # .inputs -- delivered via a FluidPort connection, not an
        # Inventory/Warehouse take (docs/components/fabricator.md). Without
        # this check a recipe needing Water/Steam/Oil with no such building
        # anywhere on the network would still look "sourceable" off its solid
        # ingredients alone, get set as the active recipe, and stall forever
        # since there's nothing to connect .water_in/.steam_in/.oil_in to.
        for fluid_key in (getattr(recipe, "fluid_inputs", {}) or {}):
            if not can_source_fluid(fluid_key):
                return False
        return True

    def target_reason(self, item_id):
        """Describes the active demand driving a target quantity for item_id."""
        if item_id in get_manual_orders():
            return "manual build order"
        _, order = find_dock_order_requiring(item_id)
        if order:
            return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"
        return "building stock target"

    def choose_recipe(self):
        targets = get_fabricator_targets()
        manual_items = get_manual_orders()
        try:
            recipes = self.machine.list_recipes()
        except Exception:
            return None

        candidates = []
        for recipe in recipes:
            target = targets.get(getattr(recipe, "output_item", None), 0)
            if target <= 0:
                continue
            # total_stock() (not just Inventory) since the rebalance sweep
            # (storage.rebalance_inventory_to_warehouses()) can move a
            # finished fabricated item out to a Warehouse too once it piles
            # up -- an Inventory-only count would look artificially low and
            # over-produce past the real target.
            current = total_stock(recipe.output_item)
            output_buffer = self.machine.get_output_count()
            missing = max(0, target - current - output_buffer)
            if missing > 0:
                candidates.append((missing, recipe))

        # Prefer a manual build order (get_manual_orders()) over every other demanded recipe
        # regardless of shortfall size -- an operator asking for "2x drone (small)" right now
        # shouldn't wait behind whichever recipe happens to have the biggest shortfall this poll.
        # Within each group (manual vs. not), prefer the biggest shortfall, but skip anything
        # currently blocked on an unavailable input (e.g. unsurveyed titanium) so the Fabricator
        # keeps building whatever else it actually can. Also skip a recipe another Fabricator
        # already holds a fresh claim on (see claim_recipe()) -- otherwise, with several
        # Fabricators, all of them would converge on the same single biggest-shortfall recipe
        # while every other demanded output goes unbuilt.
        candidates.sort(key=lambda pair: (getattr(pair[1], "output_item", None) not in manual_items, -pair[0]))
        blocked = []
        sourceable = []
        for missing, recipe in candidates:
            if not self.recipe_is_sourceable(recipe):
                blocked.append(getattr(recipe, "output_item", recipe))
                continue
            sourceable.append(recipe)
            recipe_id = getattr(recipe, "id", "")
            if self.claim_recipe(recipe_id):
                return recipe
            # another Fabricator already has a fresh claim on this one -- try
            # the next candidate first, rather than piling on immediately;
            # piling on is the fallback below, only once every candidate has
            # been tried.
        if blocked:
            print(f"[{self.name}] Skipping unreachable recipe(s) for now: {', '.join(blocked)}.")

        # Every demanded, sourceable recipe is already claimed by a different
        # Fabricator -- with only ONE demanded recipe (a single large order),
        # that used to mean every other Fabricator just sat idle forever
        # instead of ever helping, since there was never a second demanded
        # recipe for them to fall back to. Joining the biggest-shortfall
        # sourceable recipe anyway (without holding the claim -- claim_recipe()
        # already refused it above) splits that one order's remaining work
        # across every idle Fabricator instead of leaving them idle while a
        # single Fabricator works through the whole shortfall alone.
        # get_fabricator_active_recipe() divides crafts_remaining by how many
        # Fabricators currently have this same recipe selected, so joining
        # doesn't also cause every joiner to independently load the FULL
        # remaining shortfall (see production.py).
        if sourceable:
            recipe = sourceable[0]
            print(f"[{self.name}] Joining '{getattr(recipe, 'id', '?')}' alongside another Fabricator (biggest remaining shortfall, no other demanded recipe to work instead).")
            return recipe
        return None

    def drain_output(self):
        if not hasattr(self.machine, "output"):
            return
        for stack in self.machine.output.stacks():
            result = self.machine.output.send(stack.id, stack.count)
            if result.status == "no_connection":
                reconnect = self.machine.output.connect("inventory")
                self.connected_output = reconnect.status == "ok"
                if self.connected_output:
                    result = self.machine.output.send(stack.id, stack.count)
            if result.status in ["ok", "partial"]:
                print(f"[{self.name}] Sent {result.moved}x {stack.id} to Inventory.")
                consume_manual_order(stack.id, result.moved)
            elif result.status not in ["busy", "no_op"]:
                print(f"[{self.name}] Output notice: {result.status} - {result.message}")

    def load_inputs(self, recipe):
        # Fill the stockpile with enough for several crafts at once (not just
        # one) so the Auto Feeder isn't paid every craft, but cap it at what's
        # still actually needed: once running, the machine burns through the
        # whole staged batch on its own before the script gets another look,
        # so over-loading here directly overshoots the target/order.
        capacity = self.machine.get_stockpile_capacity()
        used = self.machine.get_stockpile_used()
        remaining_capacity = max(0, capacity - used)
        if remaining_capacity <= 0:
            return

        _, crafts_remaining = get_fabricator_active_recipe(self.machine)
        if crafts_remaining <= 0:
            return

        stockpile = self.machine.get_stockpile() or {}
        for item_id, required in (getattr(recipe, "inputs", {}) or {}).items():
            if remaining_capacity <= 0:
                break
            staged = stockpile.get(item_id, 0)
            missing = max(0, (required * crafts_remaining) - staged)
            if missing <= 0:
                continue
            # Capped to FABRICATOR_LOAD_CHUNK_SIZE (see its comment above),
            # and to craft_prefill_units() -- this recipe's
            # ~INPUT_PREFILL_SECONDS-of-crafting buffer target for item_id,
            # in ore/ingredient units, scaled by the recipe's own craft time
            # (see lib/production.py). The prefill cap is what actually keeps
            # a heavy batch from being monopolized in a single grab: rather
            # than every Fabricator racing to fill the full remaining
            # shortfall (whoever polls first wins it all), each one only
            # ever asks for its own short, recipe-scaled prefill window, so
            # it stops requesting more once topped up and leaves frequent
            # openings for a peer Fabricator to get its own share too.
            amount = min(missing, remaining_capacity, FABRICATOR_LOAD_CHUNK_SIZE, max(0, craft_prefill_units(recipe, item_id) - staged))
            # take_item() checks Inventory first, then rotates through any
            # Warehouse holding this item -- see lib/storage.py.
            moved = take_item(self.machine.input, item_id, amount)
            if moved <= 0:
                continue
            print(f"[{self.name}] Loaded {moved}x {item_id} for {recipe.id}.")
            remaining_capacity -= moved

    def eject_excess_inputs(self):
        """
        Recovers input-stockpile material this Fabricator no longer needs
        back into circulation (Inventory or a Warehouse) via
        InputSlot.eject() -- never .flush(), which permanently discards
        (docs/components/fabricator.md). set_recipe()/clear_recipe() both
        preserve the stockpile untouched, so without this, staged material
        gets stranded inside the Fabricator (up to its combined 200-unit
        cap) instead of being usable by anything else on the network. Two
        cases, both driven off the currently ACTIVE recipe (before this
        step's own choose_recipe() potentially switches it):
          - staged material for an item the active recipe doesn't need at
            all (leftover from a prior recipe, or no recipe set) -- ejects
            all of it.
          - staged material for an item the active recipe DOES need, beyond
            required_per_craft * crafts_remaining -- the same cap
            load_inputs() itself loads up to -- e.g. crafts_remaining
            dropped since this batch was staged (target lowered, or the
            shortfall got covered elsewhere) -- ejects just the excess,
            keeping enough staged for the batch still in flight.
        eject() itself safely no-ops on any portion still reserved for an
        in-progress craft (transactional, per docs/types/storage_and_inventory.md),
        so calling this every step is harmless even mid-craft.
        """
        if not hasattr(self.machine, "input") or not hasattr(self.machine.input, "eject"):
            return
        stockpile = self.machine.get_stockpile() or {}
        if not stockpile:
            return

        recipe, crafts_remaining = get_fabricator_active_recipe(self.machine)
        needed = dict(getattr(recipe, "inputs", {}) or {}) if recipe else {}

        for item_id, staged in stockpile.items():
            if staged <= 0:
                continue
            keep = needed.get(item_id, 0) * crafts_remaining
            excess = staged - keep
            if excess <= 0:
                continue
            destination = best_unload_target(item_id, excess)
            try:
                result = self.machine.input.eject(destination, item_id, excess)
            except Exception:
                continue
            moved = getattr(result, "moved", 0) or 0
            if moved > 0:
                print(f"[{self.name}] Ejected {moved}x {item_id} from the stockpile back to '{destination}' (no longer needed for the active batch).")

    def step(self):
        self.ensure_connection()
        self.drain_output()
        self.eject_excess_inputs()

        if self.is_shedded():
            # Power Guard has flagged this Fabricator for shedding (soft-shed
            # -- see is_shedded()'s docstring): don't start or top up
            # production. Whatever's already staged/running keeps going to
            # completion (never interrupted mid-craft), it just isn't fed
            # more, so draw winds down to 0 W on its own instead of an
            # abrupt breaker cut.
            return

        active_recipe, _ = get_fabricator_active_recipe(self.machine)
        self.ensure_fluid_connections(active_recipe)
        prior_recipe_id = self.machine.get_recipe()
        recipe = self.choose_recipe()
        if recipe is None:
            # clear_recipe() preserves the stockpile (it's staged material,
            # not tied to the recipe), so a partial load must not block this.
            if prior_recipe_id and not self.machine.is_running():
                print(f"[{self.name}] Clearing recipe: every buildable stock target/order item is met or unreachable.")
                self.machine.clear_recipe()
                self.release_recipe(prior_recipe_id)
            return

        recipe_id = getattr(recipe, "id", "")
        if prior_recipe_id != recipe_id:
            if not self.machine.is_running():
                result = self.machine.set_recipe(recipe_id)
                if result.status == "ok":
                    if prior_recipe_id:
                        self.release_recipe(prior_recipe_id)
                    output_item = getattr(recipe, "output_item", "?")
                    reason = self.target_reason(output_item)
                    print(f"[{self.name}] Set recipe '{recipe_id}' to build {output_item} for {reason}.")
            return

        if self.machine.get_stockpile_used() < self.machine.get_stockpile_capacity():
            self.load_inputs(recipe)

    def run(self, poll_interval=2.0):
        print(f"Fabricator Controller ({self.name}) online. Building stock targets enabled.")
        while True:
            try:
                self.step()
            except Exception as error:
                print(f"[{self.name}] Fabricator exception: {error}")
            sleep(poll_interval)