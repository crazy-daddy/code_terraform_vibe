# Shared Fabricator automation: maintain building stock and fulfill active orders.
from production import get_fabricator_targets, get_fabricator_active_recipe, can_source_item


class FabricatorController:
    """Selects unlocked pipe/power recipes and feeds them from Inventory."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "fabricator_1")
        self.inventory = get_component("inventory")
        self.connected_input = False
        self.connected_output = False
        self.smelter_wake_announced = False

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
        """Whether every input of this recipe has a currently known supply."""
        for item_id in (getattr(recipe, "inputs", {}) or {}):
            if not can_source_item(item_id):
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
        inventory = self.inventory
        try:
            recipes = self.machine.list_recipes()
        except Exception:
            return None

        candidates = []
        for recipe in recipes:
            target = targets.get(getattr(recipe, "output_item", None), 0)
            if target <= 0:
                continue
            current = inventory.count(recipe.output_item) if inventory and hasattr(inventory, "count") else 0
            output_buffer = self.machine.get_output_count()
            missing = max(0, target - current - output_buffer)
            if missing > 0:
                candidates.append((missing, recipe))

        # Prefer the biggest shortfall, but skip anything currently blocked on
        # an unavailable input (e.g. unsurveyed titanium) so the Fabricator
        # keeps building whatever else it actually can.
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        blocked = []
        for missing, recipe in candidates:
            if self.recipe_is_sourceable(recipe):
                return recipe
            blocked.append(getattr(recipe, "output_item", recipe))
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
            available = self.inventory.count(item_id) if self.inventory else 0
            if available <= 0:
                self.wake_smelter()
                continue
            amount = min(missing, available, remaining_capacity)
            result = self.machine.input.take(item_id, amount)
            if result.status in ["ok", "partial"]:
                moved = getattr(result, "moved", 0)
                if moved > 0:
                    print(f"[{self.name}] Loaded {moved}x {item_id} for {recipe.id}.")
                    remaining_capacity -= moved

    def wake_smelter(self):
        """Power on and resume the Smelter when refined inputs are missing."""
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
        recipe = self.choose_recipe()
        if recipe is None:
            # clear_recipe() preserves the stockpile (it's staged material,
            # not tied to the recipe), so a partial load must not block this.
            if self.machine.get_recipe() and not self.machine.is_running():
                print(f"[{self.name}] Clearing recipe: every buildable stock target/order item is met or unreachable.")
                self.machine.clear_recipe()
            return

        recipe_id = getattr(recipe, "id", "")
        if self.machine.get_recipe() != recipe_id:
            if not self.machine.is_running():
                result = self.machine.set_recipe(recipe_id)
                if result.status == "ok":
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