# Shared Library for Smelter Automation
# Manages automated ore intake, recipe execution, finished metal extraction,
# and intelligent power-down when idle to conserve grid energy.
from production import get_material_demands, get_raw_material_reason

class SmelterController:
    """
    Controls an industrial Smelter.
    Refines raw ores (iron_ore, silicon, titanium, etc.) into ingots/materials.
    Automatically clears recipes and powers down when idle to eliminate power draw.
    """
    RECIPE_MAP = {
        "iron_ore": "smelt_iron_ingot",
        "silicon": "smelt_glass",
        "titanium": "smelt_titanium_ingot",
        "cobalt": "smelt_cobalt_ingot",
        "lead_ore": "smelt_lead_ingot",
    }

    def __init__(self, smelter, target_ore="iron_ore"):
        self.smelter = smelter
        self.name = getattr(smelter, "id", "smelter_1")
        self.target_ore = target_ore
        self.inventory = get_component("inventory")
        self.power = get_component("power_control")

        self.connected_in = False
        self.connected_out = False

    def ensure_connections(self):
        """Ensures input and output ports are connected to home inventory."""
        if not self.connected_in and hasattr(self.smelter, "input"):
            try:
                self.smelter.input.connect("inventory")
                self.connected_in = True
            except Exception:
                pass

        if not self.connected_out and hasattr(self.smelter, "output"):
            try:
                self.smelter.output.connect("inventory")
                self.connected_out = True
            except Exception:
                pass

    def drain_output(self):
        """Sends all finished ingots from output buffer to inventory."""
        if not hasattr(self.smelter, "output"):
            return 0

        out_count = self.smelter.get_output_count()
        if out_count > 0:
            self.ensure_connections()
            for stack in self.smelter.output.stacks():
                res = self.smelter.output.send(stack.id, stack.count)
                if res.status in ["ok", "partial"]:
                    moved = getattr(res, "moved", 0)
                    print(f"[{self.name}] Sent {moved}x {stack.id} to Inventory.")
                    return moved
        return 0

    def step(self):
        self.ensure_connections()

        # Step 1: Drain any completed products
        self.drain_output()

        # Step 2: Determine which recipe/ore to process
        in_buf = self.smelter.get_input_count()
        current_recipe = self.smelter.get_recipe()

        try:
            unlocked_recipes = {
                getattr(recipe, "id", ""): recipe
                for recipe in self.smelter.list_recipes()
                if getattr(recipe, "id", "")
            }
        except Exception:
            unlocked_recipes = {}

        # A recipe can remain selected after its blueprint is no longer
        # available. Recover its staged input before clearing the stale state.
        if current_recipe and current_recipe not in unlocked_recipes:
            if not self.smelter.is_running():
                self.recover_input()
                clear_res = self.smelter.clear_recipe()
                if clear_res.status == "ok":
                    print(f"[{self.name}] Cleared locked recipe '{current_recipe}'.")
                # Breaker cycling disabled: power_draw only applies while a
                # recipe is running (see docs), so idle draw is already 0 W.
                # self.power_down_if_idle()
            return

        recipe, ore_to_process = self.select_needed_ore(unlocked_recipes)

        # Do not keep refining material that has no downstream demand.
        if recipe is None:
            if current_recipe and not self.smelter.is_running() and self.smelter.get_input_count() == 0:
                clear_res = self.smelter.clear_recipe()
                if clear_res.status == "ok":
                    # power_draw only applies while a recipe is actively running,
                    # so clearing it here is state hygiene, not a power saving.
                    print(f"[{self.name}] Recipe cleared (no demand): every refined output is already at its stock target or order requirement.")
            # Breaker cycling disabled: power_draw only applies while a
            # recipe is running (see docs), so idle draw is already 0 W.
            # self.power_down_if_idle()
            return

        recipe_id = getattr(recipe, "id", "")
        if current_recipe != recipe_id:
            if not self.smelter.is_running():
                recipe_inputs = set((getattr(recipe, "inputs", {}) or {}).keys())
                buffered_items = {
                    getattr(stack, "id", "")
                    for stack in self.smelter.input.stacks()
                }
                if buffered_items - recipe_inputs:
                    self.recover_input()
                    if self.smelter.get_input_count() > 0:
                        return
                set_res = self.smelter.set_recipe(recipe_id)
                if set_res.status == "ok":
                    reason = get_raw_material_reason(ore_to_process, self.smelter)
                    output_item = getattr(recipe, "output_item", "?")
                    print(f"[{self.name}] Set recipe '{recipe_id}' to refine {ore_to_process} -> {output_item} for {reason}.")
            return

        # Step 3: If input buffer has room and inventory has ore, pull it
        if ore_to_process and in_buf < 40:
            avail = self.inventory.count(ore_to_process)
            take_count = min(avail, 50 - in_buf)
            if take_count > 0:
                self.ensure_connections()
                res = self.smelter.input.take(ore_to_process, take_count)
                if res.status in ["ok", "partial"]:
                    moved = getattr(res, "moved", 0)
                    reason = get_raw_material_reason(ore_to_process, self.smelter)
                    print(f"[{self.name}] Loaded {moved}x {ore_to_process} from Inventory (for {reason}).")
                    in_buf = self.smelter.get_input_count()

        # Step 4: Check idle condition & power management
        in_buf = self.smelter.get_input_count()
        out_buf = self.smelter.get_output_count()
        is_active = self.smelter.is_running() or in_buf > 0 or out_buf > 0

        if not is_active:
            # Check if any ore is pending in inventory
            has_pending_ore = False
            demands = get_material_demands()
            if self.inventory and hasattr(self.inventory, "count"):
                for ore, recipe_id in self.RECIPE_MAP.items():
                    if self.inventory.count(ore) > 0:
                        for recipe in self.smelter.list_recipes():
                            if getattr(recipe, "id", None) == recipe_id and demands.get(getattr(recipe, "output_item", None), 0) > 0:
                                has_pending_ore = True
                                break
                    if has_pending_ore:
                        break

            if not has_pending_ore:
                # Completely idle! power_draw only applies while a recipe is
                # running, so clearing it is cleanup, not what cuts the draw.
                if self.smelter.get_recipe() != "":
                    self.smelter.clear_recipe()
                    print(f"[{self.name}] No ore to smelt. Recipe cleared.")

                # Breaker cycling disabled: idle draw is already 0 W per docs
                # (Recipe.power_draw applies only while running), so switching
                # the breaker off saves nothing and only adds a dependency on
                # an external wake call (e.g. Fabricator.wake_smelter()).
                # if self.power and hasattr(self.power, "set_powered"):
                #     try:
                #         if self.power.can_power_off(self.name) and self.power.is_powered(self.name):
                #             print(f"[{self.name}] Powering OFF smelter breaker while idle. Rover/grid will wake on ore delivery.")
                #             self.power.set_powered(self.name, False)
                #             return
                #     except Exception:
                #         pass

    def recover_input(self):
        """Return staged material to Inventory before clearing a stale recipe."""
        if not hasattr(self.smelter, "input"):
            return False
        for stack in self.smelter.input.stacks():
            result = self.smelter.input.eject("inventory", stack.id, stack.count)
            if result.status in ["ok", "partial"]:
                print(f"[{self.name}] Recovered {result.moved}x {stack.id} from stale recipe input.")
        return self.smelter.get_input_count() == 0

    def power_down_if_idle(self):
        """Power off an idle Smelter after demand has been cleared. Currently
        unused/disabled: per docs, power_draw only applies while a recipe is
        actively running, so idle draw is already 0 W without this."""
        if self.smelter.is_running() or self.smelter.get_input_count() > 0 or self.smelter.get_output_count() > 0:
            return
        if self.power and hasattr(self.power, "set_powered"):
            try:
                if self.power.can_power_off(self.name) and self.power.is_powered(self.name):
                    print(f"[{self.name}] Powering OFF smelter breaker while idle.")
                    self.power.set_powered(self.name, False)
            except Exception:
                pass

    def select_needed_ore(self, unlocked_recipes=None):
        """Selects only ore whose unlocked recipe has an active downstream need."""
        if not self.inventory or not hasattr(self.smelter, "list_recipes"):
            return None, None

        demands = get_material_demands()
        buffered_ore = set()
        if hasattr(self.smelter, "input") and hasattr(self.smelter.input, "stacks"):
            try:
                buffered_ore = {
                    getattr(stack, "id", "")
                    for stack in self.smelter.input.stacks()
                    if getattr(stack, "id", "") in self.RECIPE_MAP
                }
            except Exception:
                buffered_ore = set()
        try:
            recipes = unlocked_recipes or {
                getattr(recipe, "id", ""): recipe
                for recipe in self.smelter.list_recipes()
                if getattr(recipe, "id", "")
            }
        except Exception:
            return None, None

        for recipe in recipes.values():
            output_item = getattr(recipe, "output_item", None)
            if demands.get(output_item, 0) <= 0:
                continue
            inputs = getattr(recipe, "inputs", {}) or {}
            for ore in inputs:
                if ore in self.RECIPE_MAP and (ore in buffered_ore or self.inventory.count(ore) > 0):
                    return recipe, ore
        return None, None

    def run(self, poll_interval=2.0):
        print(f"Smelter Controller ({self.name}) online.")
        while True:
            try:
                self.step()
            except Exception as e:
                print(f"[{self.name}] Smelter exception: {e}")
            sleep(poll_interval)
