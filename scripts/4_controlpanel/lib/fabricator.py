# Shared Fabricator automation: maintain building stock and fulfill active orders.
from production import get_site_fabricator_targets, get_fabricator_active_recipe, get_fabricator_worker_count, get_fabricator_pipeline, can_source_item, can_source_fluid, find_dock_order_requiring, dock_delivery_targets, FABRICATOR_WANTS_KEY, WANTS_REFRESH_TICKS, WANTS_STALE_TICKS, get_manual_orders, get_manual_order_blocking_items, consume_manual_order, get_upgrade_orders, get_backlog_orders, blueprint_demand_items, craft_prefill_units, machine_speed, discover_fluid_sources, FLUID_SOURCE_TYPE_IDS, FLUID_LATCH_IDS, SourceCache, machine_outpost_id, claim_site_id, discover_smelter_ids
from archive import archive
from storage import take_item, best_unload_target, drain_port_to_storage, drain_port_storage_first, push_to_targets, local_port_target, outpost_is_home
from tree_console import TreeConsole, method_block
from swallow import swallowed
from script_parking import ParkRequester, parked_ids, wake_for_visit
import fluid_routing
from recipe_claims import RecipeClaimMixin
from hysteresis import HysteresisLatch
from machine_controller import MachineController, port_counts
from status_warning import StatusWarning

# run() sleep between steps: short while the machine is running or moved
# material this step, long when there is nothing to do.
ACTIVE_POLL_SECONDS = 1.0
IDLE_POLL_SECONDS = 2.0
# Recipe claims (lib/recipe_claims.py): {outpost_id: {recipe_id: {"fabricator": id, "tick": n}}}.
RECIPE_CLAIMS_KEY = "fabricator.recipe_claims"

# load_inputs() caps each take_item() call to this many units, preventing
# any single Fabricator from hoarding contested stock. Fair sharing across
# multiple Fabricators is coordinated by lib/production.py's craft_prefill_units()
# (see load_inputs()'s own comment), which keeps every Fabricator's total ask
# small and recipe-scaled. Supply Dock does NOT use either (see lib/supply_dock.py)
# -- it has no competing sibling for the same order's materials.
FABRICATOR_LOAD_CHUNK_SIZE = 10

# A load_inputs() take of a Smelter output that finds no stock wakes this
# outpost's parked Smelters (script_parking.wake_for_visit()) instead of
# leaving them to their timed re-check. At most once per item per this many
# ticks, so a starving Fabricator does not wake on every poll.
SMELTER_WAKE_THROTTLE_TICKS = 100

# ensure_fluid_connections() drives one fluid_routing.FluidInputRouter per
# recipe fluid port -- the same consumer-side router lib/steam_turbine.py and
# lib/biomass_mixer.py use (a Gas/Liquid Tank has no script of its own, so
# nothing else ever calls connect() on the other side of the pipe). The
# Fabricator has no is_stalled() of its own, so the router's starvation signal
# is flow_rate() staying 0 while the port still has room to receive
# (level() < capacity()) -- a legitimately full port also reads 0 and must not
# count.
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
# Same per-entry (not shared-clock) blacklist expiry as every other
# discover/connect/blacklist controller in this project -- see
# lib/thermal_cap.py's RESCAN_INTERVAL_TICKS for the full reasoning.
FLUID_RESCAN_INTERVAL_TICKS = 150
# Simulation ticks, not calls -- see DESIGN_HISTORY §1c-6.
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
# Declared link still "neutral" after this many checks is dropped, only if another candidate exists.
FLUID_NEUTRAL_GRACE_STEPS = 5

# A fluid-only recipe (craft_tar) can draw its fluid faster than the tanks refill. The source tank
# then sits near 0 t, and the consumers that never pause (Oil Generators on last resort, recipes
# with fluid plus items) share an empty tank. So a fluid-only recipe
# pauses (feed cut, recipe skipped) while the network-wide fill of its fluid's tanks
# (fluid_routing.fluid_reserve_fraction()) is below FLUID_ONLY_PAUSE_BELOW, until it is back at
# FLUID_ONLY_RESUME_AT. The supply sets the throughput either way; the pause only batches it.
# No tank of that fluid: never paused. The fill is re-read every FLUID_ONLY_RESERVE_REFRESH_TICKS.
FLUID_ONLY_PAUSE_BELOW = 0.05
FLUID_ONLY_RESUME_AT = 0.20
FLUID_ONLY_RESERVE_REFRESH_TICKS = 100


class FabricatorController(RecipeClaimMixin, MachineController):
    LABEL = "Fabricator"

    def online_message(self):
        return f"Fabricator Controller ({self.name}) online."

    def next_sleep(self, result, failed):
        active = failed or bool(result)
        self.parker.update(not active)
        return ACTIVE_POLL_SECONDS if active else IDLE_POLL_SECONDS

    RECIPE_CLAIMS_KEY = RECIPE_CLAIMS_KEY
    CLAIM_OWNER_FIELD = "fabricator"

    """Selects unlocked pipe/power recipes and feeds them from Inventory or a Warehouse.

    Outpost-aware: at home the ports use Inventory + home Warehouses; at any
    other outpost only that outpost's own Warehouses (Inventory is home-only,
    docs/components/fabricator.md). Demand, targets and worker splits stay
    network-wide."""

    def __init__(self, machine: "Fabricator"):
        self.machine = machine
        self.name = getattr(machine, "id", "fabricator_1")
        self.connected_input = False
        self.connected_output = False
        self._warned_no_local_storage = False
        self.log = TreeConsole(module="fabricator")
        self.byproduct_warning = StatusWarning(self.log, self.name, "Byproduct buffer full")

        # fluid_key (water_in/steam_in/oil_in) -> FluidInputRouter, created lazily -- a recipe can
        # need more than one fluid at once (e.g. oil refining needs oil_in + water_in), and each
        # port's source is independent of the others.
        self._fluid_routers = {}
        # fluid_key -> HysteresisLatch, active while that fluid's tanks are too low for fluid-only recipes.
        self._fluid_low = {}
        # fluid_key -> (tick, fill) of the last fluid_reserve_fraction() read.
        self._fluid_fill = {}
        # recipe_id -> tick of the last claim this Fabricator won and wrote to the archive.
        self._claim_ticks = {}
        self.parker = ParkRequester(self.name, "fabricator")
        # item_id -> tick of the last wake_local_smelters() pass for it.
        self._smelter_wake_ticks = {}
        # Inputs still short after this step's load_inputs() (FABRICATOR_WANTS_KEY).
        self._wants = {}
        self._wants_published = None
        self._wants_tick = 0

    def _claim_machine(self):
        return self.machine

    def outpost(self):
        """OutpostRef this Fabricator is deployed at (None if not exposed = home)."""
        return getattr(self.machine, "outpost", None)

    def at_home(self):
        return outpost_is_home(self.outpost())

    def ensure_connection(self):
        """Connects input and output ports to Inventory at home, or to a
        local Warehouse elsewhere (storage.local_port_target())."""
        if self.connected_input and self.connected_output:
            return
        target = local_port_target(self.outpost())
        if target is None:
            if not self._warned_no_local_storage:
                self._warned_no_local_storage = True
                self.log.level("warn").print(f"[{self.name}] No Warehouse at outpost '{machine_outpost_id(self.machine)}' -- a remote Fabricator can only feed from local storage.")
            return
        self._warned_no_local_storage = False
        if not self.connected_input and hasattr(self.machine, "input"):
            result = self.machine.input.connect(target)
            self.connected_input = result.status == "ok"
            if not self.connected_input and result.status not in ["busy"]:
                self.log.level("warn").print(f"[{self.name}] Input connection notice: {result.status} - {result.message}")
        if not self.connected_output and hasattr(self.machine, "output"):
            result = self.machine.output.connect(target)
            self.connected_output = result.status == "ok"
            if not self.connected_output and result.status not in ["busy"]:
                self.log.level("warn").print(f"[{self.name}] Output connection notice: {result.status} - {result.message}")

    def _discover_fluid_candidates(self, fluid_key, type_ids):
        """
        Candidate source ids network-wide for fluid_key (e.g. every
        water_pump/steam_condenser/liquid_tank/bulk_liquid_reservoir for
        "water_in" -- see production.FLUID_SOURCE_TYPE_IDS), own outpost
        first, dropping any production.fluid_building_is_viable() rejects
        (e.g. a Liquid Tank latched to a different fluid, or empty with no
        producer to ever fill it). Called by this fluid's FluidInputRouter,
        which caches it (game_clock.TickCache).
        """
        own_outpost_id = getattr(getattr(self.machine, "outpost", None), "id", None)
        ids = discover_fluid_sources(fluid_key, own_outpost_id, type_ids)
        self.log.debug(f"[{self.name}] {fluid_key}: rediscovered sources (own outpost first): {ids}.")
        return ids

    def _fluid_router(self, fluid_key, type_ids):
        router = self._fluid_routers.get(fluid_key)
        if router is None:
            router = fluid_routing.FluidInputRouter(
                discover=lambda: self._discover_fluid_candidates(fluid_key, type_ids),
                rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                label=f"{self.name}.{fluid_key}",
                reserve_fluid="water" if fluid_key == "water_in" else None,
            )
            self._fluid_routers[fluid_key] = router
        return router

    def ensure_fluid_connections(self, recipe: "Recipe | None"):
        """
        Connects each fluid_input the active recipe declares (recipe.fluid_inputs,
        e.g. {"water_in": 1.0} -- a separate field from .inputs, delivered via
        a FluidPort, not an Inventory/Warehouse take) to a reachable source
        building network-wide, via one fluid_routing.FluidInputRouter per port.
        See production.FLUID_SOURCE_TYPE_IDS for which building types satisfy
        each fluid_key.
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
            router = self._fluid_router(fluid_key, type_ids)
            fluid_routing.ensure_input_logged(router, port, curr_tick, fluid_routing.port_starved(port), self.log, self.name, fluid_key,
                                              f"No {fluid_key} source on the network.")

    @staticmethod
    def is_fluid_only(recipe: "Recipe | None"):
        """True for a recipe with fluid inputs and no item inputs (e.g. craft_tar)."""
        return bool(recipe) and not (getattr(recipe, "inputs", {}) or {}) and bool(getattr(recipe, "fluid_inputs", {}) or {})

    def fluid_low_reason(self, recipe: "Recipe | None"):
        """For a fluid-only recipe: why it is paused (its fluid's tanks are low, see
        FLUID_ONLY_PAUSE_BELOW), else None."""
        if not self.is_fluid_only(recipe):
            return None
        now = self.get_current_tick()
        for fluid_key in (getattr(recipe, "fluid_inputs", {}) or {}):
            fluid_id = FLUID_LATCH_IDS.get(fluid_key)
            if not fluid_id:
                continue
            read = self._fluid_fill.get(fluid_key)
            if read is None or not 0 <= now - read[0] < FLUID_ONLY_RESERVE_REFRESH_TICKS:
                read = (now, fluid_routing.fluid_reserve_fraction(fluid_id, curr_tick=now))
                self._fluid_fill[fluid_key] = read
            fill = read[1]
            latch = self._fluid_low.setdefault(fluid_key, HysteresisLatch(FLUID_ONLY_PAUSE_BELOW, FLUID_ONLY_RESUME_AT, on_above=False, unknown=False))
            flip = latch.update(fill)
            fill_str = f"{fill*100:.1f}%" if fill is not None else "n/a (no tank)"
            if flip == "on":
                self.log.print(f"[{self.name}] {fluid_id} tanks at {fill_str}: pausing '{getattr(recipe, 'id', '?')}' until {FLUID_ONLY_RESUME_AT*100:.0f}%.")
            elif flip == "off":
                self.log.print(f"[{self.name}] {fluid_id} tanks at {fill_str}: '{getattr(recipe, 'id', '?')}' may run again.")
            if latch.active:
                return f"{fluid_id} tanks below {FLUID_ONLY_RESUME_AT*100:.0f}%, paused to keep a buffer"
        return None

    def stop_fluid_feed(self, recipe: "Recipe | None"):
        """Disconnects every fluid port the recipe feeds from, so no new
        craft starts. ensure_fluid_connections() reconnects once a recipe
        needing that fluid is active again."""
        for fluid_key in (getattr(recipe, "fluid_inputs", {}) or {}):
            port = getattr(self.machine, fluid_key, None)
            if not port or not hasattr(port, "disconnect"):
                continue
            try:
                if hasattr(port, "connected_id") and not port.connected_id():
                    continue
                result = port.disconnect()
                self.log.print(f"[{self.name}] Stopping fluid-only '{getattr(recipe, 'id', '?')}': disconnected {fluid_key} ({getattr(result, 'status', '?')}).")
            except Exception as error:
                swallowed("fabricator.FabricatorController.stop_fluid_feed: port.disconnect", error)

    def recipe_is_sourceable(self, recipe: "Recipe", cache: "SourceCache | None" = None):
        """Whether every input of this recipe -- solid and fluid alike -- has a currently known supply."""
        return self.recipe_unsourceable_reason(recipe, cache) is None

    def recipe_unsourceable_reason(self, recipe: "Recipe | None", cache: "SourceCache | None" = None):
        """None if every input of this recipe -- solid and fluid alike -- has a currently known
        supply, else a short human-readable reason naming the first unsourceable input (used to
        annotate the "Skipping unreachable recipe(s)" log in choose_recipe()).

        Pass a shared `cache` (production.SourceCache) when checking several
        recipes in one pass (see choose_recipe()) -- otherwise each call
        re-runs Smelter/Fabricator discovery, list_recipes(), and the fluid
        outpost.buildings() scan from scratch."""
        cache = SourceCache() if cache is None else cache
        for item_id in (getattr(recipe, "inputs", {}) or {}):
            if not can_source_item(item_id, cache):
                return f"no known source for input '{item_id}'"
        # fluid_inputs (e.g. {"water_in": 1.0}) is a separate field from
        # .inputs -- delivered via a FluidPort connection, not an
        # Inventory/Warehouse take (docs/components/fabricator.md). Without
        # this check a recipe needing Water/Steam/Oil with no such building
        # anywhere on the network would still look "sourceable" off its solid
        # ingredients alone, get set as the active recipe, and stall forever
        # since there's nothing to connect .water_in/.steam_in/.oil_in to.
        for fluid_key in (getattr(recipe, "fluid_inputs", {}) or {}):
            if not can_source_fluid(fluid_key, cache):
                return f"no known source for fluid '{fluid_key}'"
        return None

    def target_reason(self, item_id, cache: "SourceCache | None" = None):
        """Describes the active demand driving a target quantity for item_id."""
        try:
            fabricator_outputs = {getattr(r, "output_item", None) for r in self.machine.list_recipes()} - {None}
            if item_id in get_manual_order_blocking_items(fabricator_outputs, cache=cache):
                return "blocking a manual order's own input"
        except Exception as error:
            swallowed("fabricator.FabricatorController.target_reason: self.machine.list_recipes", error)
        if item_id in get_manual_orders():
            return "manual build order"
        if item_id in blueprint_demand_items(cache):
            return "construction blueprint demand"
        if item_id in get_upgrade_orders():
            return "fleet upgrade order"
        _, order = find_dock_order_requiring(item_id)
        if order:
            return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))}"
        if item_id in get_backlog_orders():
            return "backlog order"
        return "intermediate or site demand"

    @staticmethod
    def backlog_only(item_id, have, upgrade_items):
        """True when item_id's upgrade order is met (`have` = local stock +
        pipeline) and no Supply Dock order needs it, so what's still missing
        is backlog."""
        if have < upgrade_items.get(item_id, 0):
            return False
        _, order = find_dock_order_requiring(item_id)
        return not order

    @method_block(lambda self, *_, **__: f"[{self.name}] choose_recipe")
    def choose_recipe(self, cache: "SourceCache | None" = None):
        # One snapshot for the whole pass (step() shares its own): targets, stock,
        # pipeline and the sourceability checks below all read it.
        cache = SourceCache() if cache is None else cache
        site_id = claim_site_id(self.machine)
        outpost = self.outpost()
        # This site's share of every root target and its own intermediates
        # (production.get_site_fabricator_targets(); the global targets with
        # only home Fabricators).
        targets = get_site_fabricator_targets(site_id, cache)
        manual_items = get_manual_orders()
        upgrade_items = get_upgrade_orders()
        backlog_items = get_backlog_orders()
        try:
            recipes = self.machine.list_recipes()
        except Exception as error:
            swallowed("fabricator.FabricatorController.choose_recipe: self.machine.list_recipes", error)
            return None

        fabricator_outputs = {getattr(r, "output_item", None) for r in recipes} - {None}
        blocking_items = get_manual_order_blocking_items(fabricator_outputs, cache=cache)
        # Computed once per pass, not per candidate (each is a stock walk).
        blueprint_demand = blueprint_demand_items(cache)
        upgrade_blocking = get_manual_order_blocking_items(fabricator_outputs, upgrade_items, cache=cache) if upgrade_items else set()
        # Output buffers + in-progress crafts of every Fabricator at this
        # site, not just this one's -- see production.get_fabricator_pipeline().
        # Units staged in their stockpiles count too (SourceCache.fab_have()).
        pipeline = get_fabricator_pipeline(cache, site_id)

        candidates = []
        have_by_item = {}
        for recipe in recipes:
            target = targets.get(getattr(recipe, "output_item", None), 0)
            if target <= 0:
                continue
            # Local stock: Inventory + home Warehouses at home (the rebalance
            # sweep moves finished goods out to Warehouses too), only the
            # outpost's own Warehouses elsewhere -- a site's stock counts
            # only for its own targets.
            current = cache.held_stock(recipe.output_item, outpost)
            in_pipeline = pipeline.get(recipe.output_item, 0) + cache.staged_units(recipe.output_item, site_id)
            missing = max(0, target - current - in_pipeline)
            if missing > 0:
                candidates.append((missing, recipe))
                have_by_item[recipe.output_item] = current + in_pipeline
                if self.log.verbose:
                    self.log.trace(f"candidate {recipe.output_item} target={target} current={current} in_pipeline+staged={in_pipeline} -> missing={missing}")

        # Six priority tiers, biggest shortfall first within each:
        #   0. An item a manual order transitively needs as an INPUT (e.g.
        #      machine_frame under a manual drone_service_station_kit order) --
        #      see production.get_manual_order_blocking_items(). The manual
        #      order literally cannot be built without this first, so it
        #      outranks even the manual order itself -- otherwise the
        #      Fabricator holding that manual order just keeps re-selecting
        #      it (can_source_item() says a recipe path for the missing
        #      input exists, so it never looks "blocked") and sits idle
        #      forever waiting on an input nothing is ever producing.
        #   1. A manual build order (get_manual_orders()) itself -- an
        #      operator asking for "2x drone (small)" right now shouldn't
        #      wait behind whichever recipe happens to have the biggest
        #      shortfall this poll.
        #   2. Construction Blueprint demand (production.blueprint_demand_items())
        #      -- building new things beats upgrading working old ones. Only
        #      while stock + pipeline is below the blueprint demand, ranked by
        #      that blueprint shortfall: the rest of a bigger stock target
        #      falls through to its own tier.
        #   3. A fleet upgrade order (production.get_upgrade_orders(): Depot
        #      kits, bigger drone chassis/modules, lib/fleet_upgrade.py) or an
        #      input it is blocked on.
        #   4. Everything else (Earth Orders, Supply Dock, intermediates),
        #      biggest shortfall first.
        #   5. A backlog order (production.get_backlog_orders()) whose upgrade
        #      order is already met -- filler for idle time.
        # Skip anything currently blocked on an unavailable input (e.g.
        # unsurveyed titanium) so the Fabricator keeps building whatever else
        # it actually can. Also skip a recipe another Fabricator already
        # holds a fresh claim on (see claim_recipe()) -- otherwise, with
        # several Fabricators, all of them would converge on the same single
        # biggest-shortfall recipe while every other demanded output goes
        # unbuilt.
        def blueprint_short(output_item):
            return max(0, blueprint_demand.get(output_item, 0) - have_by_item.get(output_item, 0))

        def _priority_tier(recipe: "Recipe"):
            output_item = getattr(recipe, "output_item", None)
            if output_item in blocking_items:
                return 0
            if output_item in manual_items:
                return 1
            if blueprint_short(output_item) > 0:
                return 2
            if output_item in backlog_items and self.backlog_only(output_item, have_by_item.get(output_item, 0), upgrade_items):
                return 5
            if output_item in upgrade_items or output_item in upgrade_blocking:
                return 3
            return 4
        def _sort_key(pair):
            tier = _priority_tier(pair[1])
            shortfall = blueprint_short(getattr(pair[1], "output_item", None)) if tier == 2 else pair[0]
            return (tier, -shortfall)
        candidates.sort(key=_sort_key)
        # Sticky recipe: the current recipe stays while it is still short and
        # no recipe of a better tier is; a bigger shortfall in the same tier
        # doesn't switch. A switch ejects the staged inputs back to storage
        # (eject_excess_inputs()) and loads new ones: two feeder trips per unit.
        current_id = self.machine.get_recipe() if hasattr(self.machine, "get_recipe") else None
        current = next((r for _missing, r in candidates if getattr(r, "id", None) == current_id), None) if current_id else None
        blocked = []
        sourceable = []
        held_by_others = self.foreign_claims(site_id) if candidates else {}
        for missing, recipe in candidates:
            paused = self.fluid_low_reason(recipe)
            if paused is not None:
                # Logged once on the latch flip (fluid_low_reason()), not as a warn every poll.
                self.log.debug(f"skipping '{getattr(recipe, 'id', '?')}': {paused}")
                continue
            reason = self.recipe_unsourceable_reason(recipe, cache)
            if reason is not None:
                output_item = getattr(recipe, "output_item", recipe)
                blocked.append(f"{output_item} ({reason})")
                continue
            sourceable.append((missing, recipe))
            recipe_id = getattr(recipe, "id", "")
            # A fresh claim another Fabricator held at the start of this pass
            # would make claim_recipe() refuse anyway; skip its transaction.
            # A claim this Fabricator renewed recently still goes through
            # claim_recipe(), which keeps it without reading the archive.
            if recipe_id in held_by_others and recipe_id not in self._claim_ticks:
                self.log.debug(f"'{recipe_id}' already claimed by {held_by_others[recipe_id]!r}, trying next candidate")
                continue
            sticky = current is not None and recipe is not current and _priority_tier(current) == _priority_tier(recipe)
            if sticky and self.recipe_unsourceable_reason(current, cache) is None and self.fluid_low_reason(current) is None and self.claim_recipe(current_id):
                self.log.debug(f"keeping '{current_id}' over '{recipe_id}' (same tier, still short)")
                return current
            if self.claim_recipe(recipe_id):
                output_item = getattr(recipe, "output_item", None)
                tier_reason = ("blocking a manual order's own input", "manual order", "blueprint demand", "fleet upgrade order", "biggest sourceable shortfall", "backlog order")[_priority_tier(recipe)]
                self.log.debug(f"claimed '{recipe_id}' (missing={missing}, {tier_reason})")
                return recipe
            # another Fabricator already has a fresh claim on this one -- try
            # the next candidate first, rather than piling on immediately;
            # piling on is the fallback below, only once every candidate has
            # been tried.
            self.log.debug(f"'{recipe_id}' already claimed by another fabricator, trying next candidate")
        if blocked:
            self.log.level("warn").print(f"[{self.name}] Skipping unreachable recipe(s) for now: {', '.join(blocked)}.")

        # Every demanded, sourceable recipe is already claimed by another
        # Fabricator. For a single large order, joining the biggest-shortfall
        # sourceable recipe anyway (without holding the claim -- claim_recipe()
        # already refused it above) distributes the work across idle Fabricators.
        # get_fabricator_active_recipe() divides crafts_remaining by how many
        # Fabricators currently have this same recipe selected, so joining
        # doesn't cause every joiner to independently load the FULL remaining
        # shortfall (see production.py).
        # Only join while there are more crafts left than Fabricators already
        # on it: the split rounds UP, so every joiner builds at least one craft.
        # Without this check, a 1-craft order gets one craft per joiner.
        for missing, recipe in sourceable:
            recipe_id = getattr(recipe, "id", "?")
            crafts_needed = -(-missing // max(1, getattr(recipe, "output_count", 1)))  # ceil division
            workers = get_fabricator_worker_count(recipe_id, site_id)
            if current_id == recipe_id:
                workers -= 1  # don't count ourselves as a peer
            if crafts_needed <= workers:
                self.log.debug(f"not joining '{recipe_id}' -- {crafts_needed} craft(s) left, {workers} Fabricator(s) already on it")
                continue
            self.log.print(f"[{self.name}] Joining '{recipe_id}' alongside {workers} other Fabricator(s) ({crafts_needed} crafts left, no unclaimed demanded recipe to work instead).")
            return recipe
        self.log.debug("no candidates at all (target-met, unreachable, or empty demand) -- returning None")
        return None

    def drain_output(self):
        """Returns True when anything left the output buffer."""
        staged = port_counts(getattr(self.machine, "output", None), "fabricator.FabricatorController.drain_output: output.stacks")
        if not staged:
            return False
        # A local Supply Dock whose order owes the item takes it straight from
        # the output (no storage hop); the rest goes to a local Warehouse,
        # Inventory only for Inventory-only items or when no Warehouse has room
        # (storage.drain_port_storage_first()).
        sent = []
        docked = {}
        for item_id, count in staged.items():
            targets = dock_delivery_targets(item_id, count, self.outpost())
            for dock_id, moved in push_to_targets(self.machine.output, item_id, count, targets):
                sent.append(f"{moved}x {item_id} to '{dock_id}'")
                docked[item_id] = docked.get(item_id, 0) + moved
        drain_port_storage_first(self.machine.output, outpost=self.outpost())
        left = self.output_counts()
        for item_id, count in staged.items():
            stored = count - left.get(item_id, 0) - docked.get(item_id, 0)
            if stored > 0:
                sent.append(f"{stored}x {item_id} to storage")
                consume_manual_order(item_id, stored, self.outpost())
        if sent:
            self.log.print(f"[{self.name}] Sent {', '.join(sent)}.")
        elif left:
            self.log.debug(f"[{self.name}] drain_output: {left} not moved, no local destination has room")
        return bool(sent)

    def output_counts(self):
        """{item_id: units} in the output buffer ({} when unreadable)."""
        return port_counts(getattr(self.machine, "output", None), "fabricator.FabricatorController.output_counts: output.stacks")

    def drain_byproduct(self):
        """Returns True when anything was moved out of the buffer.

        Empties the byproduct buffer (tar from lubricant/plastic/rubber --
        docs/components/fabricator.md) into Inventory or a local Warehouse.
        The recipe stalls once this 20-unit buffer can't take the next
        craft's byproduct, independent of .output, so drain_output() alone
        isn't enough. Drained every step (not only when full) so a craft never
        waits on it; allow_partial lets it trickle into a nearly full Warehouse.
        """
        port = getattr(self.machine, "byproduct", None)
        if not port or not hasattr(port, "stacks"):
            return False
        staged = sum(port_counts(port, "fabricator.FabricatorController.drain_byproduct: port.stacks").values())
        if staged <= 0:
            self.byproduct_warning.update(False)
            return False
        moved = drain_port_to_storage(port, outpost=self.outpost(), allow_partial=True)
        if moved > 0:
            self.log.print(f"[{self.name}] Drained {moved}x byproduct to storage.")
        capacity = port.capacity() if hasattr(port, "capacity") else 0
        left = staged - moved
        self.log.debug(f"[{self.name}] drain_byproduct: staged={staged} moved={moved} left={left} capacity={capacity}")
        self.byproduct_warning.update(
            bool(capacity) and left >= capacity,
            f"Byproduct buffer full ({left}/{capacity}) and no storage has room -- recipe will stall until space frees up.")
        return moved > 0

    def load_inputs(self, recipe: "Recipe", crafts_remaining, remaining_capacity, cache: "SourceCache | None" = None):
        """Tops the stockpile up for `recipe` (crafts_remaining and the free
        stockpile room come from step()); returns the units loaded."""
        # Fill the stockpile with enough for several crafts at once (not just
        # one) so the Auto Feeder isn't paid every craft, but cap it at what's
        # still actually needed: once running, the machine burns through the
        # whole staged batch on its own before the script gets another look,
        # so over-loading here directly overshoots the target/order.
        if remaining_capacity <= 0 or crafts_remaining <= 0:
            return 0

        loaded = []
        stockpile = self.machine.get_stockpile() or {}
        speed = machine_speed(self.machine)
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
            # in ore/ingredient units, scaled by the recipe's craft time on
            # this machine's Mk tier (see lib/production.py). The prefill cap is what actually keeps
            # a heavy batch from being monopolized in a single grab: rather
            # than every Fabricator racing to fill the full remaining
            # shortfall (whoever polls first wins it all), each one only
            # ever asks for its own short, recipe-scaled prefill window, so
            # it stops requesting more once topped up and leaves frequent
            # openings for a peer Fabricator to get its own share too.
            prefill_cap = craft_prefill_units(recipe, item_id, speed=speed)
            amount = min(missing, remaining_capacity, FABRICATOR_LOAD_CHUNK_SIZE, max(0, prefill_cap - staged))
            self.log.debug(f"[{self.name}] load_inputs({recipe.id}): {item_id} staged={staged} missing={missing} remaining_capacity={remaining_capacity} prefill_cap={prefill_cap} -> amount={amount}")
            # take_item() checks Inventory first (home only), then rotates
            # through any local Warehouse holding this item -- see lib/storage.py.
            # The step-wide cache's stock snapshot only picks the holders to try; the
            # transfer itself reports what actually moved.
            moved = take_item(self.machine.input, item_id, amount, outpost=None if self.at_home() else self.outpost(), cache=cache)
            want = min(required * crafts_remaining, prefill_cap) - staged - max(0, moved)
            if want > 0:
                self._wants[item_id] = want
            if moved <= 0:
                self.wake_local_smelters(item_id, cache)
                continue
            loaded.append(f"{moved}x {item_id}")
            remaining_capacity -= moved
        if loaded:
            self.log.print(f"[{self.name}] Loaded {', '.join(loaded)} for {recipe.id}.")
        return len(loaded)

    def wake_local_smelters(self, item_id, cache: "SourceCache | None" = None):
        """Wakes the parked Smelters at this outpost when item_id (a Smelter
        output) found no stock, throttled per item (SMELTER_WAKE_THROTTLE_TICKS).
        Returns the ids woken."""
        outpost = self.outpost()
        if outpost is None:
            return []
        cache = SourceCache() if cache is None else cache
        if item_id not in {getattr(r, "output_item", None) for r in cache.smelter_recipes()}:
            return []
        now = self.get_current_tick()
        last = self._smelter_wake_ticks.get(item_id)
        if last is not None and 0 <= now - last < SMELTER_WAKE_THROTTLE_TICKS:
            return []
        self._smelter_wake_ticks[item_id] = now
        parked = parked_ids("smelter")
        woken = [i for i in discover_smelter_ids(outpost) if i in parked and wake_for_visit(i, f"{self.name} has no {item_id}", hold=False)]
        self.log.debug(f"[{self.name}] no {item_id} in stock: woke parked Smelter(s) {woken or 'none'}")
        return woken

    def eject_excess_inputs(self, recipe: "Recipe | None", crafts_remaining):
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
        `recipe`/`crafts_remaining` are the active recipe and its remaining
        crafts (get_fabricator_active_recipe()). Returns True when anything
        was ejected.
        """
        if not hasattr(self.machine, "input") or not hasattr(self.machine.input, "eject"):
            return False
        stockpile = self.machine.get_stockpile() or {}
        if not stockpile:
            return False

        ejected = False
        needed = dict(getattr(recipe, "inputs", {}) or {}) if recipe else {}

        for item_id, staged in stockpile.items():
            if staged <= 0:
                continue
            keep = needed.get(item_id, 0) * crafts_remaining
            excess = staged - keep
            if excess <= 0:
                continue
            destination = best_unload_target(item_id, excess, outpost=self.outpost())
            if destination is None:
                self.log.debug(f"[{self.name}] eject_excess_inputs: no local storage has room for {excess}x {item_id}, keeping it staged")
                continue
            try:
                result = self.machine.input.eject(destination, item_id, excess)
            except Exception as error:
                swallowed("fabricator.FabricatorController.eject_excess_inputs: self.machine.input.eject", error)
                continue
            moved = getattr(result, "moved", 0) or 0
            if moved > 0:
                ejected = True
                self.log.print(f"[{self.name}] Ejected {moved}x {item_id} from the stockpile back to '{destination}' (no longer needed for the active batch).")
        return ejected

    def step(self):
        """One poll. Returns True when the machine is active (it moved material,
        changed its recipe, or is running), so run() can poll faster."""
        self._wants = {}
        active = self._step()
        self.publish_wants()
        return active

    def publish_wants(self):
        """Writes this step's input wants to FABRICATOR_WANTS_KEY when the
        wanted items change or a want shrinks (so a Smelter doesn't push the
        same units twice), else every WANTS_REFRESH_TICKS while non-empty; an
        empty want removes the entry."""
        now = self.get_current_tick()
        published = self._wants_published
        unchanged = published is not None and set(self._wants) == set(published) and all(self._wants[i] >= published[i] for i in self._wants)
        if unchanged and (not self._wants or now - self._wants_tick < WANTS_REFRESH_TICKS):
            return
        wants = dict(self._wants)
        site_id = claim_site_id(self.machine)

        def updater(stored):
            stored = dict(stored) if isinstance(stored, dict) else {}
            for fab_id in [f for f, e in stored.items() if not isinstance(e, dict) or now - (e.get("tick") or 0) >= WANTS_STALE_TICKS]:
                del stored[fab_id]
            if wants:
                stored[self.name] = {"site": site_id, "wants": wants, "tick": now}
            else:
                stored.pop(self.name, None)
            return stored

        if archive.transaction(FABRICATOR_WANTS_KEY, {}, updater):
            self._wants_published = wants
            self._wants_tick = now
            self.log.debug(f"[{self.name}] wants {wants or 'nothing'}")

    def _step(self):
        self.ensure_connection()
        worked = self.drain_output()
        worked = self.drain_byproduct() or worked
        # One snapshot for the rest of the step, taken after the drains changed stock:
        # active-recipe shortfall, recipe choice and the input takes all read it.
        cache = SourceCache()
        active_recipe, active_remaining = get_fabricator_active_recipe(self.machine, cache)
        worked = self.eject_excess_inputs(active_recipe, active_remaining) or worked

        if self.is_shedded():
            # Power Guard has flagged this Fabricator for shedding (soft-shed
            # -- see is_shedded()'s docstring): don't start or top up
            # production. Whatever's already staged/running keeps going to
            # completion (never interrupted mid-craft), it just isn't fed
            # more, so draw winds down to 0 W on its own instead of an
            # abrupt breaker cut.
            self.log.debug(f"[{self.name}] step: shedded by Power Guard, not starting or topping up production")
            return worked or self.machine.is_running()

        # A fluid-only recipe (e.g. craft_tar) never goes idle while its
        # fluid flows, so the idle-only switch below would never fire: once
        # its target is met or its tanks run low (fluid_low_reason()), cut
        # the feed and switch even while running.
        winding_down = self.is_fluid_only(active_recipe) and (active_remaining <= 0 or self.fluid_low_reason(active_recipe) is not None)
        if winding_down:
            self.log.debug(f"[{self.name}] step: fluid-only recipe '{getattr(active_recipe, 'id', '?')}' target met or tanks low, cutting the fluid feed")
            self.stop_fluid_feed(active_recipe)
        else:
            self.ensure_fluid_connections(active_recipe)
        prior_recipe_id = self.machine.get_recipe()
        recipe = self.choose_recipe(cache)
        if recipe is None:
            # clear_recipe() preserves the stockpile (it's staged material,
            # not tied to the recipe), so a partial load must not block this.
            if prior_recipe_id and (winding_down or not self.machine.is_running()):
                result = self.machine.clear_recipe()
                if result.status == "ok":
                    self.log.print(f"[{self.name}] Clearing recipe: every buildable order item is met or unreachable.")
                    self.release_recipe(prior_recipe_id)
                    worked = True
                else:
                    self.log.debug(f"[{self.name}] clear_recipe(): {result.status} - retrying next poll")
            return worked or self.machine.is_running()

        recipe_id = getattr(recipe, "id", "")
        if prior_recipe_id != recipe_id:
            if winding_down or not self.machine.is_running():
                result = self.machine.set_recipe(recipe_id)
                if result.status == "ok":
                    worked = True
                    if prior_recipe_id:
                        self.release_recipe(prior_recipe_id)
                    output_item = getattr(recipe, "output_item", "?")
                    reason = self.target_reason(output_item, cache)
                    self.log.print(f"[{self.name}] Set recipe '{recipe_id}' to build {output_item} for {reason}.")
                else:
                    self.log.debug(f"[{self.name}] set_recipe({recipe_id}): {result.status} - retrying next poll")
                return worked
            self.log.debug(f"[{self.name}] step: '{recipe_id}' preferred over running '{prior_recipe_id}', switching once the current craft finishes")
            return True  # running, or the branch above would have switched

        capacity = self.machine.get_stockpile_capacity()
        used = self.machine.get_stockpile_used()
        if used < capacity:
            worked = self.load_inputs(recipe, active_remaining, capacity - used, cache) > 0 or worked
        return worked or self.machine.is_running()
