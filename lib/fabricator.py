# Shared Fabricator automation: maintain building stock and fulfill active orders.
from production import get_fabricator_targets, get_fabricator_active_recipe, can_source_item, can_source_fluid
from archive import archive
from storage import take_item, total_stock

# Mirrors lib/smelter.py's SMELTER_RECIPE_CLAIM_STALE_TICKS/RECIPE_CLAIMS_KEY
# exactly, same reasoning: with several Fabricators, choose_recipe() picking
# strictly by biggest-shortfall would have every one of them converge on the
# SAME top-shortfall recipe while other demanded outputs sit untouched. A
# claim on the recipe id it's about to set lets a Fabricator move on to its
# next-best sourceable candidate if another Fabricator already holds it.
FABRICATOR_RECIPE_CLAIM_STALE_TICKS = 600
RECIPE_CLAIMS_KEY = "fabricator.recipe_claims"


class FabricatorController:
    """Selects unlocked pipe/power recipes and feeds them from Inventory or a Warehouse."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "fabricator_1")
        self.connected_input = False
        self.connected_output = False
        self.smelter_wake_announced = False
        self.clock = get_component("clock")

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
        dock = get_component("supply_dock_1")
        if dock and hasattr(dock, "current_order"):
            try:
                order = dock.current_order()
                if order and item_id in (getattr(order, "requires", {}) or {}):
                    return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"
            except Exception:
                pass
        return "building stock target"

    def choose_recipe(self):
        targets = get_fabricator_targets()
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

        # Prefer the biggest shortfall, but skip anything currently blocked on
        # an unavailable input (e.g. unsurveyed titanium) so the Fabricator
        # keeps building whatever else it actually can. Also skip a recipe
        # another Fabricator already holds a fresh claim on (see
        # claim_recipe()) -- otherwise, with several Fabricators, all of them
        # would converge on the same single biggest-shortfall recipe while
        # every other demanded output goes unbuilt.
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        blocked = []
        for missing, recipe in candidates:
            if not self.recipe_is_sourceable(recipe):
                blocked.append(getattr(recipe, "output_item", recipe))
                continue
            recipe_id = getattr(recipe, "id", "")
            if not self.claim_recipe(recipe_id):
                continue  # another Fabricator already has this one -- try the next candidate
            return recipe
        if blocked:
            print(f"[{self.name}] Skipping unreachable recipe(s) for now: {', '.join(blocked)}.")
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
            amount = min(missing, remaining_capacity)
            # take_item() checks Inventory first, then rotates through any
            # Warehouse holding this item -- see lib/storage.py.
            moved = take_item(self.machine.input, item_id, amount)
            if moved <= 0:
                self.wake_smelter()
                continue
            print(f"[{self.name}] Loaded {moved}x {item_id} for {recipe.id}.")
            remaining_capacity -= moved

    def wake_smelter(self):
        """Power on and resume the Smelter when refined inputs are missing."""
        shedded = archive.get("power.shedded", [])
        if any("smelter" in m for m in shedded):
            return

        power = get_component("power_control")
        try:
            if power and hasattr(power, "set_powered"):
                power.set_powered("smelter_1", True)

            run_control = get_component("run_control")
            if run_control and hasattr(run_control, "is_running") and hasattr(run_control, "start"):
                if not run_control.is_running("smelter_1"):
                    run_control.start("smelter_1")

            if not self.smelter_wake_announced:
                print(f"[{self.name}] Smelter awakened for missing Fabricator inputs.")
                self.smelter_wake_announced = True
        except Exception:
            pass

    def step(self):
        self.ensure_connection()
        self.drain_output()
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