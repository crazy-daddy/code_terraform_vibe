# Shared Library for Smelter Automation
# Manages automated ore intake, recipe execution, and finished metal extraction.
# The Inventory->Warehouse rebalance sweep is owned centrally by the headless
# automation panel, not by individual Smelter instances -- see
# docs/AI_CHEATSHEET.md.
from archive import archive
from production import SourceCache, craft_prefill_units, dock_remaining_requirements, get_raw_material_reason, get_smelter_demands, site_smelter_demands, smelter_recipe_peers, machine_outpost_id, claim_site_id, site_recipe_claims
from storage import take_item, drain_port_inventory_first, best_unload_target, local_port_target, outpost_is_home
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed

# A recipe claim (see claim_recipe()/release_recipe()) is only trusted while
# this fresh -- if the owning smelter stalls/crashes without releasing it
# (e.g. script exception, machine destroyed), a later smelter must still be
# able to pick up that ore rather than waiting forever. Generous margin,
# same reasoning as CONNECTION_GRACE_TICKS elsewhere: false-negative
# (missing a real conflict) is cheap, false-positive (blocking a legitimate
# claim) means an ore nobody's actually processing sits idle.
SMELTER_RECIPE_CLAIM_STALE_TICKS = 600
# Shape {outpost_id: {recipe_id: {"smelter": id, "tick": n}}}: claims only
# arbitrate Smelters at the same outpost (production.site_recipe_claims()).
RECIPE_CLAIMS_KEY = "smelter.recipe_claims"

# Per-call ceiling on ore loading: bounds any single grab (~2.5 s of
# Warehouse feeder lock). Fair sharing of contested ore is enforced by
# step()'s fair-share cap (available ore + peers' buffers, split across
# every Smelter on the recipe) together with recipe-scaled prefill cap.
SMELTER_LOAD_CHUNK_SIZE = 10

# Seconds of continuous crafting a Smelter's input buffer should cover --
# passed to production.craft_prefill_units(). Same value as the shared
# INPUT_PREFILL_SECONDS default, split out so it can be tuned for Smelters
# alone (tuned from the retired smelter.diag.* data, see below): once the
# demand trickle was fixed (production.get_smelter_demands()), refill
# capacity (SMELTER_LOAD_CHUNK_SIZE per poll) is far above consumption
# (~0.5 ore/s for a 0.08 h recipe), so buffer size was not the bottleneck.
# Fairness between Smelters sharing a scarce ore is handled by the fair-share
# cap in step(), not by keeping this small.
SMELTER_PREFILL_SECONDS = 30

# Each step's outcome is narrated via debug() (log_outcome()) -- "busy_all_sources"
# = every holder answered busy but the Smelter kept working from its buffer
# (harmless); "busy_starving" = every holder busy AND the buffer can't cover
# the next craft while idle (real lost time).
#
# Recipe switching hysteresis: see select_needed_ore()/switch_min_demand() --
# a Smelter only leaves a still-demanded recipe for an unclaimed one whose
# demand is at least one SMELTER_PREFILL_SECONDS window's worth of output.
# It likewise only JOINS a recipe a peer already claimed when demand >=
# switch_min_demand() x (workers after joining); otherwise it idles with
# outcome "demand_covered_by_peers".


class SmelterController:
    """
    Controls an industrial Smelter.
    Refines raw ores (iron_ore, silicon, titanium, etc.) into ingots/materials.
    Automatically clears recipes when idle -- power_draw only applies while a
    recipe is actively running (see docs), so idle draw is already 0 W without
    ever needing to power the breaker off; see is_shedded() for how Power Guard
    brownout shedding uses this same fact instead of cutting power.

    Multi-smelter aware: every smelter independently runs its own ore-selection/
    craft loop against the same shared get_smelter_demands() numbers, but
    claims the recipe it's about to work (claim_recipe()) so two smelters don't
    both start the same recipe while a second simultaneously-demanded ore sits
    untouched. The "inventory manager" sweep runs centrally by the headless
    automation panel (see module docstring), so no per-smelter election is needed.

    Outpost-aware: at home the ports use Inventory + home Warehouses; at any
    other outpost only that outpost's own Warehouses (Inventory is home-only,
    docs/components/smelter.md). Ore stock, fair share and output all stay
    local; demand is the network-wide get_smelter_demands(), raised to the
    site's own Fabricator need, home included (demands()).
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

        self.connected_in = False
        self.connected_out = False
        self._warned_no_local_storage = False
        self.log = TreeConsole(module="smelter")
        self._select_miss_reason = "no_demand"

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("smelter.SmelterController.get_current_tick: self.clock.tick", error)
        return 0

    def claim_recipe(self, recipe_id):
        """
        Claims recipe_id for this smelter at its outpost, or confirms/refreshes
        an existing claim already held by this smelter. Smelters at different
        outposts never block each other. Returns False if another smelter
        holds a still-fresh claim on it (see SMELTER_RECIPE_CLAIM_STALE_TICKS),
        so select_needed_ore() can move on to a different demanded ore instead
        of racing another smelter for the same one.
        """
        current_tick = self.get_current_tick()
        notes = []  # logged after the transaction: a log call inside the updater gets it rejected

        site_id = claim_site_id(self.smelter)

        def updater(claims):
            claims = site_recipe_claims(claims, "smelter")
            site = claims.setdefault(site_id, {})
            existing = site.get(recipe_id)
            if not isinstance(existing, dict):
                existing = None
            if existing is not None and existing.get("smelter") != self.name:
                age = current_tick - existing.get("tick", 0)
                # current_tick == 0 means the clock wasn't available to
                # measure real age -- treat that as "still held" (blocking),
                # not "unknown so allow override", same convention
                # vehicle_claims.py uses for the same edge case.
                if current_tick == 0 or age <= SMELTER_RECIPE_CLAIM_STALE_TICKS:
                    return claims  # still held by someone else, fresh -- leave untouched
                notes.append(f"[{self.name}] claim_recipe({recipe_id}): existing claim by '{existing.get('smelter')}' is stale (age={age} > {SMELTER_RECIPE_CLAIM_STALE_TICKS}), taking over")
            site[recipe_id] = {"smelter": self.name, "tick": current_tick}
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
        except Exception:
            self.log.debug(f"[{self.name}] claim_recipe({recipe_id}): archive transaction failed, assuming claim granted")
            return True  # can't verify; don't block production over an archive hiccup
        for note in notes:
            self.log.debug(note)

        claims = site_recipe_claims(archive.get(RECIPE_CLAIMS_KEY, {}), "smelter")
        owner = ((claims.get(site_id) or {}).get(recipe_id) or {}).get("smelter")
        won = owner == self.name
        self.log.debug(f"[{self.name}] claim_recipe({recipe_id}): {'won' if won else f'held by other smelter {owner!r}'}")
        return won

    def release_recipe(self, recipe_id):
        if not recipe_id:
            return

        site_id = claim_site_id(self.smelter)

        def updater(claims):
            claims = site_recipe_claims(claims, "smelter")
            site = claims.get(site_id) or {}
            if (site.get(recipe_id) or {}).get("smelter") == self.name:
                del site[recipe_id]
            if not site:
                claims.pop(site_id, None)
            return claims

        try:
            archive.transaction(RECIPE_CLAIMS_KEY, {}, updater)
            self.log.debug(f"[{self.name}] release_recipe({recipe_id}): released")
        except Exception as error:
            swallowed("smelter.SmelterController.release_recipe: archive.transaction", error)

    def outpost(self):
        """OutpostRef this Smelter is deployed at (None if not exposed = home)."""
        return getattr(self.smelter, "outpost", None)

    def at_home(self):
        return outpost_is_home(self.outpost())

    def demands(self, cache):
        """get_smelter_demands(), merged per item (max) with this site's own
        Fabricators' need (production.site_smelter_demands()), home
        included: network stock at another outpost only covers this site
        once site_supply hauls it, which counts as in flight here."""
        demands = get_smelter_demands(cache)
        for item_id, units in site_smelter_demands(self.outpost(), cache).items():
            if units > demands.get(item_id, 0):
                self.log.debug(f"[{self.name}] demands: {item_id} site need {units} > network {demands.get(item_id, 0)}")
                demands[item_id] = units
        return demands

    def ensure_connections(self):
        """Connects input and output ports to Inventory at home, or to a
        local Warehouse elsewhere (storage.local_port_target())."""
        if self.connected_in and self.connected_out:
            return
        target = local_port_target(self.outpost())
        if target is None:
            if not self._warned_no_local_storage:
                self._warned_no_local_storage = True
                self.log.level("warn").print(f"[{self.name}] No Warehouse at outpost '{machine_outpost_id(self.smelter)}' -- a remote Smelter can only feed from local storage.")
            return
        self._warned_no_local_storage = False

        if not self.connected_in and hasattr(self.smelter, "input"):
            try:
                result = self.smelter.input.connect(target)
                self.connected_in = getattr(result, "status", "ok") == "ok"
                self.log.debug(f"[{self.name}] ensure_connections: input -> '{target}' ({getattr(result, 'status', '?')})")
            except Exception as error:
                swallowed("smelter.SmelterController.ensure_connections: self.smelter.input.connect", error)

        if not self.connected_out and hasattr(self.smelter, "output"):
            try:
                result = self.smelter.output.connect(target)
                self.connected_out = getattr(result, "status", "ok") == "ok"
                self.log.debug(f"[{self.name}] ensure_connections: output -> '{target}' ({getattr(result, 'status', '?')})")
            except Exception as error:
                swallowed("smelter.SmelterController.ensure_connections: self.smelter.output.connect", error)

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
        would, without needing any external call to undo it once the deficit
        clears -- clearing power.shedded is all recovery ever needed to do.
        """
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

    def drain_output(self):
        """Sends all finished ingots from output buffer to Inventory, or to a
        Warehouse when Inventory is full or the Smelter is off-home
        (storage.drain_port_inventory_first())."""
        if not hasattr(self.smelter, "output"):
            return 0

        total = 0
        if self.smelter.get_output_count() > 0:
            at_home = self.at_home()
            for item_id, moved, destination, status, message in drain_port_inventory_first(self.smelter.output, outpost=self.outpost()):
                if moved > 0:
                    total += moved
                    if not at_home:
                        self.log.print(f"[{self.name}] Sent {moved}x {item_id} to a local Warehouse.")
                    elif destination == "warehouse":
                        self.log.level("warn").print(f"[{self.name}] Inventory full -- sent {moved}x {item_id} to a Warehouse instead.")
                    else:
                        self.log.print(f"[{self.name}] Sent {moved}x {item_id} to Inventory.")
                else:
                    self.log.debug(f"[{self.name}] drain_output: {item_id} not moved ({status} - {message})")
        return total

    def log_outcome(self, reason, **detail):
        """Narrates why this step did or didn't load ore, via debug()."""
        try:
            detail["in_buf"] = self.smelter.get_input_count()
        except Exception as error:
            swallowed("smelter.SmelterController.log_outcome: self.smelter.get_input_count", error)
        self.log.debug(f"[{self.name}] outcome: {reason} {detail}")

    def switch_min_demand(self, recipe, ore):
        """Smallest output demand worth pulling this Smelter off a recipe that
        still has work: one prefill window's worth (SMELTER_PREFILL_SECONDS of
        crafting, craft_prefill_units()), converted from ore units to output
        units -- 15 for a 2 s 1:1 recipe. Below that, the switch (eject buffer,
        change recipe, skip a step) costs about as much as the work gained."""
        prefill = craft_prefill_units(recipe, ore, SMELTER_PREFILL_SECONDS)
        per_run = (getattr(recipe, "inputs", {}) or {}).get(ore, 1) or 1
        output_count = max(1, getattr(recipe, "output_count", 1))
        return max(1, prefill * output_count // per_run)

    def local_ore(self, ore, cache):
        """Units of `ore` in storage this Smelter's input can reach (the
        step's SourceCache.local_stock(): Inventory + Warehouses at home,
        the outpost's own Warehouses elsewhere)."""
        return cache.local_stock(ore, self.outpost())

    def available_ore(self, ore, cache, dock_reserved):
        """Units of `ore` this Smelter may refine: local stock minus, at home,
        whatever an active Supply Dock order still needs to ship as raw ore
        (docks are home-only, so remote ore is never owed to one)."""
        reserved = (dock_reserved or {}).get(ore, 0) if self.at_home() else 0
        return max(0, self.local_ore(ore, cache) - reserved)

    def step(self):
        self.ensure_connections()

        # One stock snapshot + one demand map for the whole step (see
        # production.SourceCache) -- single snapshot avoids redundant
        # get_material_demands() walks and total_stock() calls.
        cache = SourceCache()

        # Step 1: Drain any completed products
        self.drain_output()
        output_blocked = self.smelter.get_output_count() >= 50

        if self.is_shedded():
            # Power Guard has flagged this Smelter for shedding (soft-shed --
            # see is_shedded()'s docstring): don't start or top up production.
            # Whatever's already loaded keeps running to completion (never
            # interrupted mid-craft), it just isn't fed more, so draw winds
            # down to 0 W on its own instead of an abrupt breaker cut.
            self.log_outcome("shedded")
            return

        demands = self.demands(cache)
        # Raw ore an active Supply Dock order still ships AS ore -- never
        # refined away, now that real ingot demand can be large enough to
        # consume every unit on hand (see available_ore()).
        dock_reserved = dock_remaining_requirements()

        # Step 2: Determine which recipe/ore to process
        in_buf = self.smelter.get_input_count()
        current_recipe = self.smelter.get_recipe()

        try:
            unlocked_recipes = {
                getattr(recipe, "id", ""): recipe
                for recipe in self.smelter.list_recipes()
                if getattr(recipe, "id", "")
            }
        except Exception as error:
            swallowed("smelter.SmelterController.step: self.smelter.list_recipes", error)
            unlocked_recipes = {}

        # A recipe can remain selected after its blueprint is no longer
        # available. Recover its staged input before clearing the stale state.
        if current_recipe and current_recipe not in unlocked_recipes:
            if not self.smelter.is_running():
                self.log.start(f"[{self.name}] Clearing locked recipe '{current_recipe}'")
                self.recover_input()
                clear_res = self.smelter.clear_recipe()
                if clear_res.status == "ok":
                    self.release_recipe(current_recipe)
                    self.log.end(f"[{self.name}] Cleared locked recipe '{current_recipe}'.")
                else:
                    self.log.end(f"[{self.name}] Locked recipe '{current_recipe}' not cleared ({clear_res.status}).")
                # Breaker cycling disabled: power_draw only applies while a
                # recipe is running (see docs), so idle draw is already 0 W.
                # self.power_down_if_idle()
            self.log_outcome("recipe_switch", recipe=current_recipe)
            return

        recipe, ore_to_process = self.select_needed_ore(unlocked_recipes, demands, cache, dock_reserved)

        # Do not keep refining material that has no downstream demand.
        if recipe is None:
            if current_recipe and not self.smelter.is_running() and self.smelter.get_input_count() == 0:
                clear_res = self.smelter.clear_recipe()
                if clear_res.status == "ok":
                    self.release_recipe(current_recipe)
                    # power_draw only applies while a recipe is actively running,
                    # so clearing it here is state hygiene, not a power saving.
                    self.log.print(f"[{self.name}] Recipe cleared (no demand): every refined output is already at its stock target or order requirement.")
            # Breaker cycling disabled: power_draw only applies while a
            # recipe is running (see docs), so idle draw is already 0 W.
            # self.power_down_if_idle()
            self.log_outcome("output_blocked" if output_blocked else self._select_miss_reason, demand=demands)
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
                        self.log_outcome("recipe_switch", recipe=recipe_id)
                        return
                set_res = self.smelter.set_recipe(recipe_id)
                if set_res.status == "ok":
                    # Hand the old recipe's claim back right away instead of
                    # letting it block peers until it goes stale.
                    if current_recipe:
                        self.release_recipe(current_recipe)
                    reason = get_raw_material_reason(ore_to_process, self.smelter)
                    output_item = getattr(recipe, "output_item", "?")
                    self.log.print(f"[{self.name}] Set recipe '{recipe_id}' to refine {ore_to_process} -> {output_item} for {reason}.")
            self.log_outcome("recipe_switch", recipe=recipe_id)
            return

        # Step 3: Top up the input buffer. take_item() tries only endpoints
        # that actually hold the ore -- Inventory first (never locks), then
        # Warehouses by most stock, recently-"busy" ones last.
        outcome = "buffer_full"
        outcome_detail = {"recipe": recipe_id, "ore": ore_to_process}
        if ore_to_process:
            recipe_inputs = getattr(recipe, "inputs", {}) or {}
            output_count = max(1, getattr(recipe, "output_count", 1))
            units_per_run = recipe_inputs.get(ore_to_process, 1)
            demand_qty = demands.get(getattr(recipe, "output_item", None), 0)
            worker_count, _network_buffered = smelter_recipe_peers(recipe_id)
            local_workers, peers_buffered = smelter_recipe_peers(recipe_id, machine_outpost_id(self.smelter))
            # This smelter's fair slice of the TOTAL current demand, ceil
            # divided across every Smelter on the network joined on this
            # recipe (demand is network-wide) -- mirrors lib/fabricator.py's
            # crafts_remaining split.
            share = -(-demand_qty // worker_count)
            max_ore_for_share = (share * units_per_run + output_count - 1) // output_count
            # Fair-share cap on what's actually AVAILABLE locally: (local ore
            # not reserved for a dock + ore already buffered by every peer on
            # this recipe at the same outpost, this one included) //
            # local_workers is the most any one should hold. Prevents
            # hoarding scarce stock; plentiful stock never binds.
            available = self.available_ore(ore_to_process, cache, dock_reserved)
            fair_total = (available + peers_buffered) // local_workers
            prefill_cap = craft_prefill_units(recipe, ore_to_process, SMELTER_PREFILL_SECONDS)
            caps = {
                "hardware": 50 - in_buf,
                "chunk": SMELTER_LOAD_CHUNK_SIZE,
                "demand_share": max_ore_for_share - in_buf,
                "prefill": prefill_cap - in_buf,
                "fair_share": fair_total - in_buf,
            }
            take_count = max(0, min(caps.values()))
            outcome_detail.update({"demand": demand_qty, "workers": worker_count, "local_workers": local_workers, "available": available, "fair_total": fair_total})
            self.log.debug(f"[{self.name}] ore intake for {ore_to_process}: in_buf={in_buf} demand_qty={demand_qty} workers={worker_count} local_workers={local_workers} peers_buffered={peers_buffered} available={available} caps={caps} -> take_count={take_count}")

            if take_count > 0:
                self.ensure_connections()
                report = {}
                # outpost=None keeps take_item() on the SourceCache's home
                # snapshot; off-home it counts the local Warehouses itself.
                take_outpost = None if self.at_home() else self.outpost()
                moved = take_item(self.smelter.input, ore_to_process, take_count, outpost=take_outpost, cache=cache, report=report)
                sources = report.get("sources", [])
                statuses = [entry[1] for entry in sources]
                outcome_detail["last_take"] = {"asked": take_count, "moved": moved, "sources": [list(entry) for entry in sources]}
                if moved > 0:
                    outcome = "took"
                    reason = get_raw_material_reason(ore_to_process, self.smelter)
                    self.log.print(f"[{self.name}] Loaded {moved}x {ore_to_process} (for {reason}).")
                elif statuses and all(status == "busy" for status in statuses):
                    # Busy only hurts if the buffer can't cover the next craft:
                    # a running Smelter (or one with a full craft's worth staged)
                    # keeps working through a failed top-up.
                    if self.smelter.is_running() or self.smelter.get_input_count() >= units_per_run:
                        outcome = "busy_all_sources"
                    else:
                        outcome = "busy_starving"
                else:
                    outcome = "no_ore"
            elif caps["fair_share"] <= 0 and min(v for k, v in caps.items() if k != "fair_share") > 0:
                outcome = "fair_share_capped"
        if output_blocked:
            outcome = "output_blocked"
        self.log_outcome(outcome, **outcome_detail)

        # Step 4: Check idle condition & power management
        in_buf = self.smelter.get_input_count()
        out_buf = self.smelter.get_output_count()
        is_active = self.smelter.is_running() or in_buf > 0 or out_buf > 0

        if not is_active:
            # Check if any demanded ore is pending (Inventory or a Warehouse)
            has_pending_ore = False
            for ore, pending_recipe_id in self.RECIPE_MAP.items():
                pending_recipe = unlocked_recipes.get(pending_recipe_id)
                if pending_recipe is None:
                    continue
                if demands.get(getattr(pending_recipe, "output_item", None), 0) > 0 and self.available_ore(ore, cache, dock_reserved) > 0:
                    has_pending_ore = True
                    break

            if not has_pending_ore:
                # Completely idle! power_draw only applies while a recipe is
                # running, so clearing it is cleanup, not what cuts the draw.
                if self.smelter.get_recipe() != "":
                    self.smelter.clear_recipe()
                    self.log.print(f"[{self.name}] No ore to smelt. Recipe cleared.")

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
        """Return staged material to Inventory (home) or a local Warehouse
        with room (elsewhere) before clearing a stale recipe."""
        if not hasattr(self.smelter, "input"):
            return False
        at_home = self.at_home()
        for stack in self.smelter.input.stacks():
            destination = "inventory" if at_home else best_unload_target(stack.id, 1, outpost=self.outpost())
            if destination is None:
                self.log.level("warn").print(f"[{self.name}] No local Warehouse has room for {stack.count}x {stack.id}; left in the input buffer.")
                continue
            result = self.smelter.input.eject(destination, stack.id, stack.count)
            if result.status in ["ok", "partial"]:
                self.log.print(f"[{self.name}] Recovered {result.moved}x {stack.id} from stale recipe input to '{destination}'.")
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
                    self.log.print(f"[{self.name}] Powering OFF smelter breaker while idle.")
                    self.power.set_powered(self.name, False)
            except Exception as error:
                swallowed("smelter.SmelterController.power_down_if_idle: self.power.can_power_off", error)

    def select_needed_ore(self, unlocked_recipes=None, demands=None, cache=None, dock_reserved=None):
        """
        Selects only ore whose unlocked recipe has an active downstream need,
        preferring a recipe no other live smelter already holds a fresh claim
        on (see claim_recipe()) -- so with several smelters and several
        simultaneously-demanded ores, each settles on a different one instead
        of racing to refine the same ore while another sits untouched.

        If every demanded, sourceable ore is already claimed by a different
        smelter (e.g. only ONE ore is currently demanded at all -- a single
        large order), joins the first one anyway rather than sitting
        completely idle: get_smelter_demands() nets against total stock
        (which includes what every other smelter has already produced), and
        step()'s demand-share + fair-share caps split the intake, so several
        smelters pulling the same ore in parallel self-throttle down to 0
        together once the target is met.

        `demands`/`cache`/`dock_reserved` are the step's shared
        get_smelter_demands() map, SourceCache and dock_remaining_requirements()
        (each computed on the spot when omitted). Ore an active Supply Dock
        order still ships raw doesn't count as sourceable. When nothing is
        returned, self._select_miss_reason says why (no_demand / no_ore /
        ore_reserved_for_dock) for the debug narration.
        """
        self._select_miss_reason = "no_demand"
        if not self.inventory or not hasattr(self.smelter, "list_recipes"):
            return None, None

        cache = SourceCache() if cache is None else cache
        demands = self.demands(cache) if demands is None else demands
        dock_reserved = dock_remaining_requirements() if dock_reserved is None else dock_reserved
        buffered_ore = set()
        if hasattr(self.smelter, "input") and hasattr(self.smelter.input, "stacks"):
            try:
                buffered_ore = {
                    getattr(stack, "id", "")
                    for stack in self.smelter.input.stacks()
                    if getattr(stack, "id", "") in self.RECIPE_MAP
                }
            except Exception as error:
                swallowed("smelter.SmelterController.select_needed_ore: self.smelter.input.stacks", error)
                buffered_ore = set()
        try:
            recipes = unlocked_recipes or {
                getattr(recipe, "id", ""): recipe
                for recipe in self.smelter.list_recipes()
                if getattr(recipe, "id", "")
            }
        except Exception as error:
            swallowed("smelter.SmelterController.select_needed_ore: self.smelter.list_recipes", error)
            return None, None

        sourceable = []
        demanded_any = False
        reserved_any = False
        for recipe in recipes.values():
            output_item = getattr(recipe, "output_item", None)
            if demands.get(output_item, 0) <= 0:
                self.log.trace(f"[{self.name}] select_needed_ore: {getattr(recipe, 'id', '?')} (output={output_item}) has no active demand, skipping")
                continue
            demanded_any = True
            inputs = getattr(recipe, "inputs", {}) or {}
            for ore in inputs:
                if ore not in self.RECIPE_MAP:
                    continue
                if ore not in buffered_ore and self.available_ore(ore, cache, dock_reserved) <= 0:
                    local = self.local_ore(ore, cache)
                    if local > 0:
                        reserved_any = True
                        self.log.debug(f"[{self.name}] select_needed_ore: {ore} in stock ({local}) but all of it is owed raw to a Supply Dock order ({dock_reserved.get(ore, 0)}), skipping")
                    continue
                sourceable.append((recipe, ore))
                self.log.debug(f"[{self.name}] select_needed_ore: candidate {getattr(recipe, 'id', '?')} via {ore} (demand={demands.get(output_item, 0)}, {'already buffered' if ore in buffered_ore else 'in stock'})")
                break  # one matching ore is enough to consider this recipe a candidate

        # Switching hysteresis: recipe changes eject the buffer, change recipe
        # and skip a step, so oscillating demand creates scheduling overhead.
        # While the current recipe is still demanded and sourceable:
        #   1. keep it outright if this Smelter holds (or can take) its claim;
        #   2. a joiner may still move to an unclaimed recipe (spreading work
        #      across ores is the point of claims), but only one whose demand
        #      is worth a switch -- at least switch_min_demand() output units.
        current_id = self.smelter.get_recipe()
        current = next(((r, o) for r, o in sourceable if getattr(r, "id", "") == current_id), None)
        if current is not None:
            if self.claim_recipe(current_id):
                self.log.debug(f"[{self.name}] select_needed_ore: staying on '{current_id}' (claim held, still demanded)")
                return current
            candidates = []
            for recipe, ore in sourceable:
                if recipe is current[0]:
                    continue
                demand = demands.get(getattr(recipe, "output_item", None), 0)
                minimum = self.switch_min_demand(recipe, ore)
                if demand < minimum:
                    self.log.debug(f"[{self.name}] select_needed_ore: not switching to '{getattr(recipe, 'id', '?')}' -- demand {demand} < switch minimum {minimum}")
                    continue
                candidates.append((recipe, ore))
        else:
            candidates = list(sourceable)

        for recipe, ore in candidates:
            recipe_id = getattr(recipe, "id", "")
            if self.claim_recipe(recipe_id):
                self.log.debug(f"[{self.name}] select_needed_ore: claimed '{recipe_id}' (ore={ore})")
                return recipe, ore
            # another smelter already has a fresh claim on this one -- try
            # the next candidate first; joining is the fallback below.
            self.log.debug(f"[{self.name}] select_needed_ore: '{recipe_id}' already claimed by another smelter, trying next candidate")

        if current is not None:
            self.log.debug(f"[{self.name}] select_needed_ore: staying joined on '{current_id}' (no unclaimed recipe worth switching to)")
            return current
        # Pile-on join onto a recipe a peer already holds -- only when the
        # demand is worth one more worker: demand >= switch_min_demand() x
        # (workers after joining), so a 1-unit demand cannot pull every
        # Smelter onto one recipe (each switch ejects the buffers).
        for recipe, ore in sourceable:
            recipe_id = getattr(recipe, "id", "")
            demand = demands.get(getattr(recipe, "output_item", None), 0)
            workers, _buffered = smelter_recipe_peers(recipe_id)
            workers_after = workers + (0 if current_id == recipe_id else 1)
            minimum = self.switch_min_demand(recipe, ore) * workers_after
            if demand < minimum:
                self.log.debug(f"[{self.name}] select_needed_ore: not joining '{recipe_id}' -- demand {demand} < {minimum} (switch minimum x {workers_after} workers)")
                continue
            if current_id != recipe_id:
                self.log.print(f"[{self.name}] Joining '{recipe_id}' alongside another Smelter (demand {demand} is worth {workers_after} workers).")
            return recipe, ore
        if sourceable:
            self._select_miss_reason = "demand_covered_by_peers"
            self.log.debug(f"[{self.name}] select_needed_ore: every demanded recipe is claimed and too small to join -- idling")
            return None, None
        if reserved_any:
            self._select_miss_reason = "ore_reserved_for_dock"
        elif demanded_any:
            self._select_miss_reason = "no_ore"
        self.log.debug(f"[{self.name}] select_needed_ore: no demanded+sourceable ore found at all ({self._select_miss_reason}) -- returning None")
        return None, None

    def run(self, poll_interval=2.0):
        self.log.print(f"Smelter Controller ({self.name}) online.")
        validate_game_version()
        while True:
            reset_all()
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Smelter exception: {e}")
            flush_all()
            sleep(poll_interval)
