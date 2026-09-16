# Shared Library for Smelter Automation
# Manages automated ore intake, recipe execution, finished metal extraction,
# and intelligent power-down when idle to conserve grid energy.
from archive import archive
from production import get_material_demands, get_raw_material_reason, discover_smelter_ids
from storage import take_item, total_stock, rebalance_inventory_to_warehouses

# A recipe claim (see claim_recipe()/release_recipe()) is only trusted while
# this fresh -- if the owning smelter stalls/crashes without releasing it
# (e.g. script exception, machine destroyed), a later smelter must still be
# able to pick up that ore rather than waiting forever. Generous margin,
# same reasoning as CONNECTION_GRACE_TICKS elsewhere: false-negative
# (missing a real conflict) is cheap, false-positive (blocking a legitimate
# claim) means an ore nobody's actually processing sits idle.
SMELTER_RECIPE_CLAIM_STALE_TICKS = 600
RECIPE_CLAIMS_KEY = "smelter.recipe_claims"

# Ore loading used to request up to a full 50-unit top-up in one take_item()
# call -- with several smelters contested for the same ore, whichever polled
# first could take the entire available stock in a single grab, leaving a
# peer smelter at 0 even though demand called for splitting it (same real
# case that motivated lib/fabricator.py's FABRICATOR_LOAD_CHUNK_SIZE, just
# for ore instead of Fabricator ingredients). Capping each call to this many
# units spreads a big top-up across several step() cycles instead of one,
# giving a peer smelter's own poll a chance to interleave in between.
SMELTER_LOAD_CHUNK_SIZE = 10


class SmelterController:
    """
    Controls an industrial Smelter.
    Refines raw ores (iron_ore, silicon, titanium, etc.) into ingots/materials.
    Automatically clears recipes when idle -- power_draw only applies while a
    recipe is actively running (see docs), so idle draw is already 0 W without
    ever needing to power the breaker off; see is_shedded() for how Power Guard
    brownout shedding uses this same fact instead of cutting power.

    Multi-smelter aware: elects a single Leader per home outpost (mirrors
    lib/solar.py's SolarController.check_master() -- same Archive+run_control
    approach, no Signal Bus, sorted-by-numeric-id with liveness check via
    run_control.is_running()) so the "inventory manager" sweep
    (rebalance_inventory_to_warehouses()) only runs once per cycle instead of
    once per smelter. Every smelter (Leader or Follower) still independently
    runs its own ore-selection/craft loop against the same shared
    get_material_demands() numbers, but claims the recipe it's about to work
    (claim_recipe()) so two smelters don't both start the same recipe while a
    second simultaneously-demanded ore sits untouched.
    """
    RECIPE_MAP = {
        "iron_ore": "smelt_iron_ingot",
        "silicon": "smelt_glass",
        "titanium": "smelt_titanium_ingot",
        "cobalt": "smelt_cobalt_ingot",
        "rare_earth": "smelt_rare_earth_core",
        "neutronium": "smelt_neutronium_bar",
        "lead_ore": "smelt_lead_ingot",
    }

    def __init__(self, smelter, target_ore="iron_ore"):
        self.smelter = smelter
        self.name = getattr(smelter, "id", "smelter_1")
        self.target_ore = target_ore
        self.inventory = get_component("inventory")
        self.power = get_component("power_control")
        self.clock = get_component("clock")
        self.run_ctrl = get_component("run_control")

        self.connected_in = False
        self.connected_out = False
        self.is_leader = False

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def check_leader(self):
        """
        Elects a single Leader among every discovered Smelter: lowest numeric
        id currently running() wins (mirrors SolarController.check_master()
        exactly). Recomputed every step() -- no persisted lease, no
        heartbeat/timeout; if the current Leader stops running, the next
        poll simply produces a different (correct) answer.
        """
        ids = discover_smelter_ids()
        if not ids:
            ids = [self.name]

        def sort_key(s_id):
            try:
                return int(s_id.split("_")[-1])
            except Exception:
                return 9999

        ids = sorted(set(ids), key=sort_key)

        if self.run_ctrl and hasattr(self.run_ctrl, "is_running"):
            try:
                for cand in ids:
                    if self.run_ctrl.is_running(cand):
                        return self.name == cand
            except Exception:
                pass
        return self.name == ids[0]

    def update_role(self):
        was_leader = self.is_leader
        self.is_leader = self.check_leader()
        if self.is_leader and not was_leader:
            print(f"[{self.name}] Promoted to Smelter Leader (runs the inventory-manager sweep).")
        elif was_leader and not self.is_leader:
            print(f"[{self.name}] Demoted to Follower.")
        return self.is_leader

    def claim_recipe(self, recipe_id):
        """
        Claims recipe_id for this smelter, or confirms/refreshes an existing
        claim already held by this smelter. Returns False if another smelter
        holds a still-fresh claim on it (see SMELTER_RECIPE_CLAIM_STALE_TICKS),
        so select_needed_ore() can move on to a different demanded ore instead
        of racing another smelter for the same one.
        """
        current_tick = self.get_current_tick()

        def updater(claims):
            claims = dict(claims or {})
            existing = claims.get(recipe_id)
            if isinstance(existing, dict) and existing.get("smelter") != self.name:
                age = current_tick - existing.get("tick", 0)
                # current_tick == 0 means the clock wasn't available to
                # measure real age -- treat that as "still held" (blocking),
                # not "unknown so allow override", same convention
                # vehicle_claims.py uses for the same edge case.
                if current_tick == 0 or age <= SMELTER_RECIPE_CLAIM_STALE_TICKS:
                    return claims  # still held by someone else, fresh -- leave untouched
            claims[recipe_id] = {"smelter": self.name, "tick": current_tick}
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
        except Exception:
            return True  # can't verify; don't block production over an archive hiccup

        claims = archive.get(RECIPE_CLAIMS_KEY, {}) or {}
        owner = (claims.get(recipe_id) or {}).get("smelter")
        return owner == self.name

    def release_recipe(self, recipe_id):
        if not recipe_id:
            return

        def updater(claims):
            claims = dict(claims or {})
            if (claims.get(recipe_id) or {}).get("smelter") == self.name:
                del claims[recipe_id]
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
        except Exception:
            pass

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

    def is_shedded(self):
        """
        True when the Power Guard (lib/power.py's PowerGridManager, via
        SOFT_SHED_PATTERNS) has marked this Smelter for shedding. Smelter/
        Fabricator are soft-shed -- Power Guard tracks them in power.shedded
        but deliberately never calls set_powered() on them (see
        SOFT_SHED_PATTERNS' comment): a Smelter only draws its recipe's
        power_draw while actively running a craft, so idle draw is already
        0 W (see this class's docstring) -- simply not starting/topping-up
        production already achieves the same power saving a breaker cut
        would, without losing Leader status (the inventory-manager sweep) or
        needing any external call to undo it once the deficit clears --
        clearing power.shedded is all recovery ever needed to do.
        """
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

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
        self.update_role()

        # Inventory manager sweep: move bulk stock (ore, ingots) out to a
        # Warehouse once it piles up. See lib/storage.py for the full rule.
        # Leader-only -- with several smelters, every one of them running this
        # every cycle would be N redundant identical sweeps for one shared
        # Inventory/Warehouse set.
        if self.is_leader:
            rebalance_inventory_to_warehouses()

        # Step 1: Drain any completed products
        self.drain_output()

        if self.is_shedded():
            # Power Guard has flagged this Smelter for shedding (soft-shed --
            # see is_shedded()'s docstring): don't start or top up production.
            # Whatever's already loaded keeps running to completion (never
            # interrupted mid-craft), it just isn't fed more, so draw winds
            # down to 0 W on its own instead of an abrupt breaker cut.
            return

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
                    self.release_recipe(current_recipe)
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
                    self.release_recipe(current_recipe)
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

        # Step 3: If input buffer has room and ore is available (Inventory or
        # a Warehouse), pull it -- take_item() tries whatever's currently
        # connected first, then rotates through Warehouses if that's short.
        if ore_to_process and in_buf < 40:
            # Capped to SMELTER_LOAD_CHUNK_SIZE per call -- see its comment
            # above -- so a big top-up is spread across several step()
            # cycles instead of one smelter monopolizing a contested ore in
            # a single grab.
            take_count = min(50 - in_buf, SMELTER_LOAD_CHUNK_SIZE)
            if take_count > 0:
                self.ensure_connections()
                moved = take_item(self.smelter.input, ore_to_process, take_count)
                if moved > 0:
                    reason = get_raw_material_reason(ore_to_process, self.smelter)
                    print(f"[{self.name}] Loaded {moved}x {ore_to_process} (for {reason}).")
                    in_buf = self.smelter.get_input_count()

        # Step 4: Check idle condition & power management
        in_buf = self.smelter.get_input_count()
        out_buf = self.smelter.get_output_count()
        is_active = self.smelter.is_running() or in_buf > 0 or out_buf > 0

        if not is_active:
            # Check if any ore is pending (Inventory or a Warehouse)
            has_pending_ore = False
            demands = get_material_demands()
            for ore, recipe_id in self.RECIPE_MAP.items():
                if total_stock(ore) > 0:
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
                # the breaker off saves nothing and would need an external
                # wake call to undo -- deliberately not automated, see
                # lib/vehicle_cargo.py's module docstring.
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
        """
        Selects only ore whose unlocked recipe has an active downstream need,
        preferring a recipe no other live smelter already holds a fresh claim
        on (see claim_recipe()) -- so with several smelters and several
        simultaneously-demanded ores, each settles on a different one instead
        of racing to refine the same ore while another sits untouched.

        If every demanded, sourceable ore is already claimed by a different
        smelter (e.g. only ONE ore is currently demanded at all -- a single
        large order), joins the first one anyway rather than sitting
        completely idle: unlike Fabricator's crafts_remaining, this doesn't
        need an explicit even split -- get_material_demands() already nets
        against total_stock() (which includes what every other smelter has
        already produced), so several smelters pulling the same ore in
        parallel each cycle self-throttles down to 0 together once the
        target is met, rather than each independently re-committing to the
        FULL remaining shortfall the way a Fabricator's pre-loaded stockpile
        batch would.
        """
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

        sourceable = []
        for recipe in recipes.values():
            output_item = getattr(recipe, "output_item", None)
            if demands.get(output_item, 0) <= 0:
                continue
            inputs = getattr(recipe, "inputs", {}) or {}
            for ore in inputs:
                if ore in self.RECIPE_MAP and (ore in buffered_ore or total_stock(ore) > 0):
                    sourceable.append((recipe, ore))
                    break  # one matching ore is enough to consider this recipe a candidate

        for recipe, ore in sourceable:
            recipe_id = getattr(recipe, "id", "")
            if self.claim_recipe(recipe_id):
                return recipe, ore
            # another smelter already has a fresh claim on this one -- try
            # the next candidate first; joining is the fallback below.

        if sourceable:
            recipe, ore = sourceable[0]
            print(f"[{self.name}] Joining '{getattr(recipe, 'id', '?')}' alongside another Smelter (no other demanded ore to refine instead).")
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
