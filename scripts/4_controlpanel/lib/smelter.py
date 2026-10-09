# Shared Library for Smelter Automation
# Manages automated ore intake, recipe execution, and finished metal extraction.
# The Inventory->Warehouse rebalance sweep is owned centrally by
# orchestrator_automation.py, not by individual Smelter instances -- see
# docs/AI_CHEATSHEET.md.
from archive import archive
from production import SourceCache, claim_site_id, craft_prefill_units, machine_speed, dock_delivery_targets, dock_remaining_requirements, fabricator_wants_for, home_outpost_id, site_ingot_refill, get_raw_material_reason, get_smelter_demands, site_smelter_demands, smelter_recipe_peers, machine_outpost_id
from production_core import SMELTER_INPUT_CAP, SMELTER_PREFILL_SECONDS, SMELTER_WANTS_KEY, WANTS_REFRESH_TICKS, WANTS_STALE_TICKS
from game_clock import now_tick
from storage import take_item, drain_port_storage_first, push_to_targets, best_unload_target, local_port_target, outpost_is_home
from tree_console import TreeConsole
from swallow import swallowed
from script_parking import ParkRequester
from recipe_claims import RecipeClaimMixin
from machine_controller import MachineController, port_counts

# Recipe claims (lib/recipe_claims.py): {outpost_id: {recipe_id: {"smelter": id, "tick": n}}}.
RECIPE_CLAIMS_KEY = "smelter.recipe_claims"

# Per-call ceiling on ore loading: bounds any single grab (~2.5 s of
# Warehouse feeder lock). Fair sharing of contested ore is enforced by
# load_ore()'s fair-share cap (available ore + peers' buffers, split across
# every Smelter on the recipe) together with recipe-scaled prefill cap.
SMELTER_LOAD_CHUNK_SIZE = 10

# run() poll cadence: fast while the Smelter has work in flight (running, or
# input/output buffered, or a recipe/ore was just set/loaded), slow when idle.
ACTIVE_POLL_SECONDS = 1.0
IDLE_POLL_SECONDS = 2.0

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


class SmelterController(RecipeClaimMixin, MachineController):
    LABEL = "Smelter"

    def online_message(self):
        return f"Smelter Controller ({self.name}) online."

    def next_sleep(self, result, failed):
        active = failed or bool(result)
        self.parker.update(not active)
        return ACTIVE_POLL_SECONDS if active else IDLE_POLL_SECONDS

    RECIPE_CLAIMS_KEY = RECIPE_CLAIMS_KEY
    CLAIM_OWNER_FIELD = "smelter"

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
    untouched. The "inventory manager" sweep runs centrally in
    orchestrator_automation.py (see module docstring), so no per-smelter election is needed.

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

    def __init__(self, smelter: "Smelter", target_ore="iron_ore"):
        self.smelter = smelter
        self.name = getattr(smelter, "id", "smelter_1")
        self.target_ore = target_ore
        # {(fabricator_id, item_id): (want entry tick, units pushed against it)}
        self._pushed = {}
        self._want_ticks = {}
        self.inventory = get_component("inventory")

        self.connected_in = False
        self.connected_out = False
        self._warned_no_local_storage = False
        self.log = TreeConsole(module="smelter")
        self._select_miss_reason = "no_demand"
        self._claim_ticks = {}
        self.parker = ParkRequester(self.name, "smelter")  # recipe_id -> tick of the last archive-confirmed claim
        # (ore, fill_to) a Drone Depot may push into the input this step (SMELTER_WANTS_KEY).
        self._want = None
        self._want_published = None
        self._want_tick = 0

    def _claim_machine(self):
        return self.smelter

    def outpost(self):
        """OutpostRef this Smelter is deployed at (None if not exposed = home)."""
        return getattr(self.smelter, "outpost", None)

    def at_home(self):
        return outpost_is_home(self.outpost())

    def demands(self, cache: "SourceCache"):
        """get_smelter_demands(), merged per item (max) with this site's own
        Fabricators' need (production.site_smelter_demands()), home
        included: network stock at another outpost only covers this site
        once site_supply hauls it, which counts as in flight here."""
        demands = get_smelter_demands(cache)
        self.log.start(f"[{self.name}] demands", level="debug")
        for item_id, units in site_smelter_demands(self.outpost(), cache).items():
            if units > demands.get(item_id, 0):
                self.log.debug(f"{item_id} site need {units} > network {demands.get(item_id, 0)}")
                demands[item_id] = units
        self.log.end()
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

        self.log.start(f"[{self.name}] ensure_connections", level="debug")
        if not self.connected_in and hasattr(self.smelter, "input"):
            try:
                result = self.smelter.input.connect(target)
                self.connected_in = getattr(result, "status", "ok") == "ok"
                self.log.debug(f"input -> '{target}' ({getattr(result, 'status', '?')})")
            except Exception as error:
                swallowed("smelter.SmelterController.ensure_connections: self.smelter.input.connect", error)

        if not self.connected_out and hasattr(self.smelter, "output"):
            try:
                result = self.smelter.output.connect(target)
                self.connected_out = getattr(result, "status", "ok") == "ok"
                self.log.debug(f"output -> '{target}' ({getattr(result, 'status', '?')})")
            except Exception as error:
                swallowed("smelter.SmelterController.ensure_connections: self.smelter.output.connect", error)
        self.log.end()

    def fabricator_targets(self, item_id, site_id):
        """[(fabricator_id, units)] for local Fabricators short of item_id, less
        what this Smelter already pushed against the same published want."""
        targets = []
        self._want_ticks = {}
        for fab_id, units, tick in fabricator_wants_for(item_id, site_id):
            self._want_ticks[fab_id] = tick
            pushed_tick, pushed = self._pushed.get((fab_id, item_id), (None, 0))
            left = units - (pushed if pushed_tick == tick else 0)
            if left > 0:
                targets.append((fab_id, left))
        return targets

    def drain_output(self):
        """Sends finished ingots straight into a local Fabricator still short
        of them (production.fabricator_wants_for()), then a local Supply Dock
        whose order owes them (production.dock_delivery_targets()), then a
        local Warehouse (storage.best_unload_target(), which keeps an ore and
        its ingot apart), and only what no Warehouse takes to Inventory at
        home (storage.drain_port_storage_first()). Returns units moved."""
        if not hasattr(self.smelter, "output") or self.smelter.get_output_count() <= 0:
            return 0
        staged = port_counts(self.smelter.output, "smelter.SmelterController.drain_output: self.smelter.output.stacks")
        site_id = claim_site_id(self.smelter)
        sent = []
        total = 0
        for item_id, count in staged.items():
            delivered = push_to_targets(self.smelter.output, item_id, count, self.fabricator_targets(item_id, site_id))
            for target, moved in delivered:
                tick, pushed = self._pushed.get((target, item_id), (None, 0))
                self._pushed[(target, item_id)] = (self._want_ticks.get(target), (pushed if tick == self._want_ticks.get(target) else 0) + moved)
            left = count - sum([moved for _target, moved in delivered])
            if left > 0:
                delivered += push_to_targets(self.smelter.output, item_id, left, dock_delivery_targets(item_id, left, self.outpost()))
            for target, moved in delivered:
                sent.append(f"{moved}x {item_id} to '{target}'")
                total += moved
        stored = drain_port_storage_first(self.smelter.output, outpost=self.outpost())
        if stored > 0:
            sent.append(f"{stored}x {', '.join(staged)} to storage")
            total += stored
        if sent:
            self.log.print(f"[{self.name}] Sent {', '.join(sent)}.")
        else:
            self.log.debug(f"[{self.name}] drain_output: {', '.join(staged)} not moved, no local destination has room")
        return total

    def log_outcome(self, reason, **detail):
        """Narrates why this step did or didn't load ore, via debug()."""
        try:
            detail["in_buf"] = self.smelter.get_input_count()
        except Exception as error:
            swallowed("smelter.SmelterController.log_outcome: self.smelter.get_input_count", error)
        self.log.debug(f"[{self.name}] outcome: {reason} {detail}")

    def switch_min_demand(self, recipe: "Recipe", ore):
        """Smallest output demand worth pulling this Smelter off a recipe that
        still has work: one prefill window's worth (SMELTER_PREFILL_SECONDS of
        crafting, craft_prefill_units()), converted from ore units to output
        units -- 15 for a 2 s 1:1 recipe. Below that, the switch (eject buffer,
        change recipe, skip a step) costs about as much as the work gained."""
        prefill = craft_prefill_units(recipe, ore, SMELTER_PREFILL_SECONDS, machine_speed(self.smelter))
        per_run = (getattr(recipe, "inputs", {}) or {}).get(ore, 1) or 1
        output_count = max(1, getattr(recipe, "output_count", 1))
        return max(1, prefill * output_count // per_run)

    def local_ore(self, ore, cache: "SourceCache"):
        """Units of `ore` in storage this Smelter's input can reach (the
        step's SourceCache.local_stock(): Inventory + Warehouses at home,
        the outpost's own Warehouses elsewhere)."""
        return cache.local_stock(ore, self.outpost())

    def intake_reason(self, ore, refilling):
        """Why this Smelter refines `ore`, for the recipe/load log lines."""
        if refilling:
            return "the fab-site ingot buffer"
        return get_raw_material_reason(ore, self.smelter)

    def site_id(self):
        """Outpost id this Smelter stands at (home when not exposed), as production._dock_order_sites() names it."""
        return machine_outpost_id(self.smelter) or home_outpost_id()

    def available_ore(self, ore, cache: "SourceCache", dock_reserved):
        """Units of `ore` this Smelter may refine: local stock minus whatever
        an active Supply Dock order at this outpost still needs to ship as raw
        ore. `dock_reserved` = dock_remaining_requirements(self.site_id())."""
        return max(0, self.local_ore(ore, cache) - (dock_reserved or {}).get(ore, 0))

    def is_busy(self):
        """True while the Smelter has work in flight: running, or input/output buffered."""
        return bool(self.smelter.is_running() or self.smelter.get_input_count() > 0 or self.smelter.get_output_count() > 0)

    def step(self):
        """One control pass. Returns True when the Smelter is active (see
        is_busy(), or ore/recipe was just loaded/set) so run() polls faster."""
        self._want = None
        active = self._step()
        self.publish_want()
        return active

    def publish_want(self):
        """Writes this step's (ore, fill_to) to SMELTER_WANTS_KEY when it
        changes, else every WANTS_REFRESH_TICKS while set; no want removes the
        entry, so a Depot stops feeding once demand is met."""
        now = now_tick()
        want = self._want
        if want == self._want_published and (want is None or now - self._want_tick < WANTS_REFRESH_TICKS):
            return
        site_id = claim_site_id(self.smelter)

        def updater(stored):
            stored = dict(stored) if isinstance(stored, dict) else {}
            for smelter_id in [k for k, e in stored.items() if not isinstance(e, dict) or now - (e.get("tick") or 0) >= WANTS_STALE_TICKS]:
                del stored[smelter_id]
            if want:
                stored[self.name] = {"site": site_id, "ore": want[0], "fill_to": want[1], "tick": now}
            else:
                stored.pop(self.name, None)
            return stored

        if archive.transaction(SMELTER_WANTS_KEY, {}, updater):
            self._want_published = want
            self._want_tick = now
            self.log.debug(f"[{self.name}] depot feed want {want or 'nothing'}")

    def _step(self):
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
            return self.is_busy()

        demands = self.demands(cache)
        # Raw ore an active Supply Dock order still ships AS ore -- never
        # refined away, now that real ingot demand can be large enough to
        # consume every unit on hand (see available_ore()).
        dock_reserved = dock_remaining_requirements(self.site_id())

        # Step 2: Determine which recipe/ore to process
        current_recipe = self.smelter.get_recipe()
        unlocked_recipes = self.unlocked_recipes()

        # A recipe can remain selected after its blueprint is no longer
        # available. Recover its staged input before clearing the stale state.
        if current_recipe and current_recipe not in unlocked_recipes:
            self.clear_locked_recipe(current_recipe)
            self.log_outcome("recipe_switch", recipe=current_recipe)
            return self.is_busy()

        recipe, ore_to_process, refilling, demands = self.select_recipe(unlocked_recipes, demands, cache, dock_reserved)

        # Do not keep refining material that has no downstream demand.
        if recipe is None:
            self.clear_unneeded_recipe(current_recipe)
            self.log_outcome("output_blocked" if output_blocked else self._select_miss_reason, demand=demands)
            return self.is_busy()

        recipe_set = False
        if current_recipe != getattr(recipe, "id", ""):
            recipe_set = self.switch_recipe(recipe, ore_to_process, current_recipe, refilling)
            if not recipe_set:
                return self.is_busy()

        # Step 3: Top up the input buffer.
        loaded = self.load_ore(recipe, ore_to_process, demands, cache, dock_reserved, refilling, output_blocked)

        # Step 4: Check idle condition
        return self.settle_idle(unlocked_recipes, demands, cache, dock_reserved, loaded or recipe_set)

    def unlocked_recipes(self):
        """{recipe_id: recipe} for every recipe this Smelter can run ({} on error)."""
        try:
            return {
                getattr(recipe, "id", ""): recipe
                for recipe in self.smelter.list_recipes()
                if getattr(recipe, "id", "")
            }
        except Exception as error:
            swallowed("smelter.SmelterController.unlocked_recipes: self.smelter.list_recipes", error)
            return {}

    def clear_locked_recipe(self, current_recipe):
        """Recovers the staged input of a recipe whose blueprint is no longer
        unlocked, then clears it. A running craft is left to finish first."""
        if self.smelter.is_running():
            return
        self.log.start(f"[{self.name}] Clearing locked recipe '{current_recipe}'")
        self.recover_input()
        clear_res = self.smelter.clear_recipe()
        if clear_res.status == "ok":
            self.release_recipe(current_recipe)
            self.log.end(f"[{self.name}] Cleared locked recipe '{current_recipe}'.")
        else:
            self.log.end(f"[{self.name}] Locked recipe '{current_recipe}' not cleared ({clear_res.status}).")

    def select_recipe(self, unlocked_recipes, demands, cache: "SourceCache", dock_reserved):
        """Picks (recipe, ore, refilling, demands) for this step. Idle time goes
        to this fab site's ingot buffer (production.site_ingot_refill()), only
        when no real demand is sourceable: a real demand found next step wins
        the selection again, so a refill never holds up an order. `demands` in
        the result is the map the choice was made against (the refill map when
        refilling). recipe is None when nothing is worth refining."""
        recipe, ore = self.select_needed_ore(unlocked_recipes, demands, cache, dock_reserved)
        if recipe is not None:
            return recipe, ore, False, demands
        refill = site_ingot_refill(self.outpost(), cache)
        if not refill:
            return None, None, False, demands
        miss_reason = self._select_miss_reason
        self.log.debug(f"[{self.name}] no real demand ({miss_reason}), trying ingot buffer refill {refill}")
        recipe, ore = self.select_needed_ore(unlocked_recipes, refill, cache, dock_reserved)
        if recipe is None:
            self._select_miss_reason = miss_reason
            return None, None, False, demands
        return recipe, ore, True, refill

    def clear_unneeded_recipe(self, current_recipe):
        """Clears a recipe with no downstream demand once its craft and staged
        input are done. power_draw only applies while a recipe is actively
        running, so this is state hygiene, not a power saving."""
        if not current_recipe or self.smelter.is_running() or self.smelter.get_input_count() != 0:
            return
        clear_res = self.smelter.clear_recipe()
        if clear_res.status == "ok":
            self.release_recipe(current_recipe)
            self.log.print(f"[{self.name}] Recipe cleared (no demand): every refined output is already at its stock target or order requirement.")

    def switch_recipe(self, recipe: "Recipe", ore, current_recipe, refilling):
        """Switches the Smelter from current_recipe to recipe. Waits (returns
        False) while a craft is running or foreign input can't be recovered
        yet. Returns True once the new recipe is set."""
        recipe_id = getattr(recipe, "id", "")
        if self.smelter.is_running():
            self.log_outcome("recipe_switch", recipe=recipe_id)
            return False
        recipe_inputs = set((getattr(recipe, "inputs", {}) or {}).keys())
        buffered_items = {getattr(stack, "id", "") for stack in self.smelter.input.stacks()}
        if buffered_items - recipe_inputs:
            self.recover_input()
            if self.smelter.get_input_count() > 0:
                self.log_outcome("recipe_switch", recipe=recipe_id)
                return False
        set_res = self.smelter.set_recipe(recipe_id)
        if set_res.status != "ok":
            self.log_outcome("recipe_switch", recipe=recipe_id)
            return False
        # Hand the old recipe's claim back right away instead of letting it
        # block peers until it goes stale.
        if current_recipe:
            self.release_recipe(current_recipe)
        reason = self.intake_reason(ore, refilling)
        output_item = getattr(recipe, "output_item", "?")
        self.log.print(f"[{self.name}] Set recipe '{recipe_id}' to refine {ore} -> {output_item} for {reason}.")
        return True

    def load_ore(self, recipe: "Recipe", ore_to_process, demands, cache: "SourceCache", dock_reserved, refilling, output_blocked):
        """Tops up the input buffer with ore_to_process, capped by hardware,
        chunk size, demand share, prefill and fair share. take_item() tries
        only endpoints that actually hold the ore -- Inventory first (never
        locks), then Warehouses by most stock, recently-"busy" ones last.
        Logs the step's outcome; returns True when ore was loaded."""
        recipe_id = getattr(recipe, "id", "")
        in_buf = self.smelter.get_input_count()
        outcome = "buffer_full"
        outcome_detail = {"recipe": recipe_id, "ore": ore_to_process, "refill": refilling}
        loaded = False
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
            prefill_cap = craft_prefill_units(recipe, ore_to_process, SMELTER_PREFILL_SECONDS, machine_speed(self.smelter))
            caps = {
                "hardware": SMELTER_INPUT_CAP - in_buf,
                "chunk": SMELTER_LOAD_CHUNK_SIZE,
                "demand_share": max_ore_for_share - in_buf,
                "prefill": prefill_cap - in_buf,
                "fair_share": fair_total - in_buf,
            }
            take_count = max(0, min(caps.values()))
            # Depot feed bound: same caps minus chunk (a Depot push is fast) and
            # fair_share (its `available` can't see Depot freight). None while a
            # Supply Dock order still ships this ore raw or the output is blocked.
            feed_room = min(caps["hardware"], caps["demand_share"], caps["prefill"])
            if feed_room > 0 and not output_blocked and not (dock_reserved or {}).get(ore_to_process, 0):
                self._want = (ore_to_process, in_buf + feed_room)
            outcome_detail.update({"demand": demand_qty, "workers": worker_count, "local_workers": local_workers, "available": available, "fair_total": fair_total})
            self.log.debug(f"[{self.name}] ore intake for {ore_to_process}: in_buf={in_buf} demand_qty={demand_qty} workers={worker_count} local_workers={local_workers} peers_buffered={peers_buffered} available={available} caps={caps} -> take_count={take_count}")

            # Refill hysteresis: a running Smelter with at least half its
            # prefill cap (and a full craft) staged skips the blocking take;
            # the next top-up then moves a bigger batch.
            if take_count > 0 and in_buf >= max(units_per_run, prefill_cap // 2) and self.smelter.is_running():
                take_count = 0
                outcome = "buffer_ok"
                self.log.debug(f"[{self.name}] buffer_ok: in_buf={in_buf} >= half of prefill cap {prefill_cap}, running -- skipping top-up")

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
                    loaded = True
                    outcome = "took"
                    reason = self.intake_reason(ore_to_process, refilling)
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
        return loaded

    def settle_idle(self, unlocked_recipes, demands, cache: "SourceCache", dock_reserved, changed):
        """Returns whether the Smelter is active (is_busy(), or `changed` =
        ore/recipe was just loaded/set). A fully idle Smelter with no demanded
        ore pending in reachable storage clears its recipe -- power_draw only
        applies while a recipe is running, so this is cleanup, not what cuts
        the draw."""
        if changed or self.is_busy():
            return True
        for ore, pending_recipe_id in self.RECIPE_MAP.items():
            pending_recipe = unlocked_recipes.get(pending_recipe_id)
            if pending_recipe is None:
                continue
            if demands.get(getattr(pending_recipe, "output_item", None), 0) > 0 and self.available_ore(ore, cache, dock_reserved) > 0:
                return False
        if self.smelter.get_recipe() != "":
            self.smelter.clear_recipe()
            self.log.print(f"[{self.name}] No ore to smelt. Recipe cleared.")
        return False

    def recover_input(self):
        """Return staged material to a local Warehouse with room
        (storage.best_unload_target(); Inventory at home when none has room)
        before clearing a stale recipe."""
        if not hasattr(self.smelter, "input"):
            return False
        for stack in self.smelter.input.stacks():
            destination = best_unload_target(stack.id, 1, outpost=self.outpost())
            if destination is None:
                self.log.level("warn").print(f"[{self.name}] No local Warehouse has room for {stack.count}x {stack.id}; left in the input buffer.")
                continue
            result = self.smelter.input.eject(destination, stack.id, stack.count)
            if result.status in ["ok", "partial"]:
                self.log.print(f"[{self.name}] Recovered {result.moved}x {stack.id} from stale recipe input to '{destination}'.")
        return self.smelter.get_input_count() == 0

    def select_needed_ore(self, unlocked_recipes=None, demands=None, cache: "SourceCache | None" = None, dock_reserved=None):
        """Logs the decision trail as one debug block around _select_needed_ore()."""
        self.log.start(f"[{self.name}] select_needed_ore", level="debug")
        choice = self._select_needed_ore(unlocked_recipes, demands, cache, dock_reserved)
        self.log.end()
        return choice

    def _select_needed_ore(self, unlocked_recipes, demands, cache: "SourceCache | None", dock_reserved):
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
        load_ore()'s demand-share + fair-share caps split the intake, so several
        smelters pulling the same ore in parallel self-throttle down to 0
        together once the target is met.

        `demands`/`cache`/`dock_reserved` are the step's shared
        get_smelter_demands() map, SourceCache and this site's
        dock_remaining_requirements() (each computed on the spot when omitted). Ore an active Supply Dock
        order still ships raw doesn't count as sourceable. When nothing is
        returned, self._select_miss_reason says why (no_demand / no_ore /
        ore_reserved_for_dock) for the debug narration.
        """
        self._select_miss_reason = "no_demand"
        if not self.inventory or not hasattr(self.smelter, "list_recipes"):
            return None, None

        cache = SourceCache() if cache is None else cache
        demands = self.demands(cache) if demands is None else demands
        dock_reserved = dock_remaining_requirements(self.site_id()) if dock_reserved is None else dock_reserved
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
                self.log.trace(f"{getattr(recipe, 'id', '?')} (output={output_item}) has no active demand, skipping")
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
                        self.log.debug(f"{ore} in stock ({local}) but all of it is owed raw to a Supply Dock order ({dock_reserved.get(ore, 0)}), skipping")
                    continue
                sourceable.append((recipe, ore))
                self.log.debug(f"candidate {getattr(recipe, 'id', '?')} via {ore} (demand={demands.get(output_item, 0)}, {'already buffered' if ore in buffered_ore else 'in stock'})")
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
                self.log.debug(f"staying on '{current_id}' (claim held, still demanded)")
                return current
            candidates = []
            for recipe, ore in sourceable:
                if recipe is current[0]:
                    continue
                demand = demands.get(getattr(recipe, "output_item", None), 0)
                minimum = self.switch_min_demand(recipe, ore)
                if demand < minimum:
                    self.log.debug(f"not switching to '{getattr(recipe, 'id', '?')}' -- demand {demand} < switch minimum {minimum}")
                    continue
                candidates.append((recipe, ore))
        else:
            candidates = list(sourceable)

        for recipe, ore in candidates:
            recipe_id = getattr(recipe, "id", "")
            if self.claim_recipe(recipe_id):
                self.log.debug(f"claimed '{recipe_id}' (ore={ore})")
                return recipe, ore
            # another smelter already has a fresh claim on this one -- try
            # the next candidate first; joining is the fallback below.
            self.log.debug(f"'{recipe_id}' already claimed by another smelter, trying next candidate")

        if current is not None:
            self.log.debug(f"staying joined on '{current_id}' (no unclaimed recipe worth switching to)")
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
                self.log.debug(f"not joining '{recipe_id}' -- demand {demand} < {minimum} (switch minimum x {workers_after} workers)")
                continue
            if current_id != recipe_id:
                self.log.print(f"[{self.name}] Joining '{recipe_id}' alongside another Smelter (demand {demand} is worth {workers_after} workers).")
            return recipe, ore
        if sourceable:
            self._select_miss_reason = "demand_covered_by_peers"
            self.log.debug(f"every demanded recipe is claimed and too small to join -- idling")
            return None, None
        if reserved_any:
            self._select_miss_reason = "ore_reserved_for_dock"
        elif demanded_any:
            self._select_miss_reason = "no_ore"
        self.log.debug(f"no demanded+sourceable ore found at all ({self._select_miss_reason}) -- returning None")
        return None, None
