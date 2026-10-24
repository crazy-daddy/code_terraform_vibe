# Shared Fabricator automation: maintain building stock and fulfill active orders.
# A step has two paths. The plan path (_replan()) walks the demand cascade
# (active recipe shortfall, choose_recipe()) and sets or clears the recipe; it
# runs only when plan_due() says so (backstop age, new shared demand record,
# recipe changed, crafts spent, an input starved, a dock order's tail went to
# storage, idle). The feed path runs
# every poll: drains, then tops up the stockpile for the planned recipe, its
# crafts_remaining lowered by what this Fabricator has finished since.
from production_demand_record import record_tick
from production import get_site_fabricator_ladders, get_fabricator_active_recipe, get_fabricator_worker_count, get_fabricator_pipeline, can_source_item, can_source_fluid, find_dock_order_requiring, dock_delivery_targets, FABRICATOR_WANTS_KEY, WANTS_REFRESH_TICKS, WANTS_STALE_TICKS, consume_manual_order, recipe_depths, craft_prefill_units, discover_fluid_sources, FLUID_SOURCE_TYPE_IDS, FLUID_LATCH_IDS, SourceCache, machine_outpost_id, claim_site_id, discover_smelter_ids  # fmt: skip
from logistics_requests import in_flight
from priority import NONE, ORDER, band, band_name, fine, ladder_total, top_deficit
from archive import archive
from storage import local_port_target, outpost_is_home
from storage_unload import best_unload_target, drain_port_to_storage, drain_port_storage_first, push_to_targets
from storage_take import take_item
from tree_console import TreeConsole, method_block
from swallow import swallowed
from parking_client import ParkRequester, parked_ids, wake_for_visit
import fluid_routing
from recipe_claims import RecipeClaimMixin
from hysteresis import HysteresisLatch
from machine_controller import MachineController, port_counts
from status_warning import StatusWarning

# A plan (recipe, crafts remaining) older than this is recomputed even when no
# trigger fired (plan_due()).
PLAN_BACKSTOP_TICKS = 1800

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
# outpost's parked Smelters (parking_client.wake_for_visit()) instead of
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
# with fluid plus items) drawing from the same tanks run dry. So a fluid-only recipe
# pauses (feed cut, recipe skipped) while the fill of the tanks its port can switch to
# (FluidInputRouter.reachable_tank_fill(): candidates not blacklisted, so a tank on another pipe
# network drops out once tried) is below FLUID_ONLY_PAUSE_BELOW, until it is back at
# FLUID_ONLY_RESUME_AT. The supply sets the throughput either way; the pause only batches it.
# No reachable tank of that fluid: never paused. The fill is re-read every FLUID_ONLY_RESERVE_REFRESH_TICKS.
FLUID_ONLY_PAUSE_BELOW = 0.05
FLUID_ONLY_RESUME_AT = 0.20
FLUID_ONLY_RESERVE_REFRESH_TICKS = 100


class FabricatorController(RecipeClaimMixin, MachineController):
    LABEL = "Fabricator"

    def online_message(self):
        return f"Fabricator Controller ({self.name}) online."

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
        # fluid_key -> (tick, fill) of the last reachable_tank_fill() read.
        self._fluid_fill = {}
        # recipe_id -> tick of the last claim this Fabricator won and wrote to the archive.
        self._claim_ticks = {}
        self.parker = ParkRequester(self.name, "fabricator")
        # item_id -> tick of the last wake_local_smelters() pass for it.
        self._smelter_wake_ticks = {}
        # Inputs still short after this step's load_inputs() (FABRICATOR_WANTS_KEY).
        self._wants = {}
        # (recipe_id, inputs the last load_inputs() left below one craft).
        self._short_inputs = ("", ())
        self._wants_published = None
        self._wants_tick = 0
        # Last plan (see _replan()/plan_due()), output units drained this step
        # ({item: units}) and how many of them went to a local Supply Dock,
        # output units still held after the drain ({item: units}), whether the
        # last load_inputs() left a wanted input unmoved, and whether the
        # machine was idle after the last step.
        self._plan: dict = {}
        self._drained = {}
        self._docked = {}
        self._held = {}
        self._starved = False
        self._last_idle = False

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
            fluid_routing.ensure_input_logged(router, port, curr_tick, fluid_routing.port_starved(port), self.log, self.name, fluid_key, f"No {fluid_key} source on the network.")

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
        for fluid_key in getattr(recipe, "fluid_inputs", {}) or {}:
            fluid_id = FLUID_LATCH_IDS.get(fluid_key)
            if not fluid_id:
                continue
            read = self._fluid_fill.get(fluid_key)
            if read is None or not 0 <= now - read[0] < FLUID_ONLY_RESERVE_REFRESH_TICKS:
                tons = self._fluid_router(fluid_key, FLUID_SOURCE_TYPE_IDS.get(fluid_key, ())).reachable_tank_fill(now)
                read = (now, tons[0] / tons[1] if tons else None)
                self._fluid_fill[fluid_key] = read
            fill = read[1]
            latch = self._fluid_low.setdefault(fluid_key, HysteresisLatch(FLUID_ONLY_PAUSE_BELOW, FLUID_ONLY_RESUME_AT, on_above=False, unknown=False))
            flip = latch.update(fill)
            fill_str = f"{fill * 100:.1f}%" if fill is not None else "n/a (no tank)"
            if flip == "on":
                self.log.print(f"[{self.name}] {fluid_id} tanks at {fill_str}: pausing '{getattr(recipe, 'id', '?')}' until {FLUID_ONLY_RESUME_AT * 100:.0f}%.")
            elif flip == "off":
                self.log.print(f"[{self.name}] {fluid_id} tanks at {fill_str}: '{getattr(recipe, 'id', '?')}' may run again.")
            if latch.active:
                return f"{fluid_id} tanks below {FLUID_ONLY_RESUME_AT * 100:.0f}%, paused to keep a buffer"
        return None

    def stop_fluid_feed(self, recipe: "Recipe | None"):
        """Disconnects every fluid port the recipe feeds from, so no new
        craft starts. ensure_fluid_connections() reconnects once a recipe
        needing that fluid is active again."""
        for fluid_key in getattr(recipe, "fluid_inputs", {}) or {}:
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
        for item_id in getattr(recipe, "inputs", {}) or {}:
            if not can_source_item(item_id, cache):
                return f"no known source for input '{item_id}'"
        # fluid_inputs (e.g. {"water_in": 1.0}) is a separate field from
        # .inputs -- delivered via a FluidPort connection, not an
        # Inventory/Warehouse take (docs/components/fabricator.md). Without
        # this check a recipe needing Water/Steam/Oil with no such building
        # anywhere on the network would still look "sourceable" off its solid
        # ingredients alone, get set as the active recipe, and stall forever
        # since there's nothing to connect .water_in/.steam_in/.oil_in to.
        for fluid_key in getattr(recipe, "fluid_inputs", {}) or {}:
            if not can_source_fluid(fluid_key, cache):
                return f"no known source for fluid '{fluid_key}'"
        return None

    def target_reason(self, item_id, cache: "SourceCache | None" = None):
        """Describes the demand driving the target for item_id: the band of
        its top open level (lib/priority.py), the Supply Dock order for an
        ORDER-band one."""
        cache = SourceCache() if cache is None else cache
        levels = get_site_fabricator_ladders(claim_site_id(self.machine), cache).get(item_id, [])
        prio, _missing = top_deficit(levels, cache.fab_have(item_id, self.outpost()))
        if prio <= NONE:
            return "no open demand"
        if band(prio) == ORDER:
            _, order = find_dock_order_requiring(item_id)
            if order:
                return f"Supply Dock Order {getattr(order, 'name', getattr(order, 'id', 'active'))} (prio {prio})"
        return f"{band_name(prio)} demand (prio {prio})"

    def starved(self, recipe: "Recipe", cache: "SourceCache", site_id):
        """True when some input of `recipe` has less than one craft's worth in
        local stock and nothing in flight to this site: the recipe cannot
        continue by waiting, so a same-band candidate that can run now takes
        over (choose_recipe())."""
        outpost = self.outpost()
        flying = None
        for item_id, per_craft in (getattr(recipe, "inputs", {}) or {}).items():
            if cache.local_stock(item_id, outpost) >= per_craft:
                continue
            if flying is None:
                flying = in_flight(site_id)
            if flying.get(item_id, 0) <= 0:
                return True
        return False

    @method_block(lambda self, *_, **__: f"[{self.name}] choose_recipe")
    def choose_recipe(self, cache: "SourceCache | None" = None):
        # One snapshot for the whole pass (step() shares its own): targets, stock,
        # pipeline and the sourceability checks below all read it.
        cache = SourceCache() if cache is None else cache
        site_id = claim_site_id(self.machine)
        outpost = self.outpost()
        # This site's share of every root target and its own intermediates
        # (production.get_site_fabricator_ladders(); the global targets with
        # only home Fabricators), each a priority ladder.
        ladders = get_site_fabricator_ladders(site_id, cache)
        try:
            recipes = self.machine.list_recipes()
        except Exception as error:
            swallowed("fabricator.FabricatorController.choose_recipe: self.machine.list_recipes", error)
            return None

        # Output buffers + in-progress crafts of every Fabricator at this
        # site, not just this one's -- see production.get_fabricator_pipeline().
        # Units staged in their stockpiles count too (SourceCache.fab_have()).
        pipeline = get_fabricator_pipeline(cache, site_id)
        depths = recipe_depths(cache)

        candidates = []
        rank = {}  # recipe id -> (prio of the top open level, units missing there)
        for recipe in recipes:
            levels = ladders.get(getattr(recipe, "output_item", ""))
            if not levels:
                continue
            # Local stock: Inventory + home Warehouses at home (the rebalance
            # sweep moves finished goods out to Warehouses too), only the
            # outpost's own Warehouses elsewhere -- a site's stock counts
            # only for its own targets.
            current = cache.held_stock(recipe.output_item, outpost)
            in_pipeline = pipeline.get(recipe.output_item, 0) + cache.staged_units(recipe.output_item, site_id)
            have = current + in_pipeline
            missing = max(0, ladder_total(levels) - have)
            if missing > 0:
                candidates.append((missing, recipe))
                rank[getattr(recipe, "id", "")] = top_deficit(levels, have)
                if self.log.verbose:
                    self.log.trace(f"candidate {recipe.output_item} target={levels} current={current} in_pipeline+staged={in_pipeline} -> missing={missing}, top={rank[getattr(recipe, 'id', '')]}")

        # Ranking (lib/priority.py): the band of the top open level first (a
        # manual order before an Earth order before a buffer), then the
        # deeper recipe inside one band (an intermediate its parent cannot be
        # built without, production.recipe_depths()), then the fine prio
        # (dock score, blueprint priority), then the units missing at that
        # level. A target's lower levels never lift it: a buffer top-up of an
        # item with an open order ranks by the order's units only.
        # Skip anything currently blocked on an unavailable input (e.g.
        # unsurveyed titanium) so the Fabricator keeps building whatever else
        # it actually can. Also skip a recipe another Fabricator already
        # holds a fresh claim on (see claim_recipe()) -- otherwise, with
        # several Fabricators, all of them would converge on the same single
        # top recipe while every other demanded output goes unbuilt.
        def _sort_key(pair):
            recipe = pair[1]
            prio, top_missing = rank[getattr(recipe, "id", "")]
            return (-band(prio), -depths.get(getattr(recipe, "output_item", ""), 0), -fine(prio), -top_missing)

        candidates.sort(key=_sort_key)
        # Hysteresis inside a band: the current recipe stays while it is still
        # short, sourceable and not starved (starved()) and no candidate of a
        # higher band is; depth and fine prio never switch it. A switch ejects
        # the staged inputs back to storage (eject_excess_inputs()) and loads
        # new ones: two feeder trips per unit.
        current_id = self.machine.get_recipe() if hasattr(self.machine, "get_recipe") else None
        current = next((r for _missing, r in candidates if getattr(r, "id", None) == current_id), None) if current_id else None
        current_band = band(rank[current_id][0]) if current is not None else NONE
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
            prio, top_missing = rank[recipe_id]
            sticky = current is not None and recipe is not current and band(prio) <= current_band
            if sticky and current is not None and self.recipe_unsourceable_reason(current, cache) is None and self.fluid_low_reason(current) is None:
                if self.starved(current, cache, site_id) and not self.starved(recipe, cache, site_id):
                    self.log.debug(f"'{current_id}' is starved of an input; '{recipe_id}' can run now")
                elif self.claim_recipe(current_id):
                    self.log.debug(f"keeping '{current_id}' over '{recipe_id}' (same band, still short)")
                    return current
            if self.claim_recipe(recipe_id):
                self.log.debug(f"claimed '{recipe_id}' (missing={missing}, {band_name(prio)} prio {prio}, {top_missing} at that level)")
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
        """Returns True when anything left the output buffer. The units that
        left, per item, are kept in self._drained (those a Supply Dock took in
        self._docked) and the units still held in self._held, all for the
        plan."""
        self._drained = {}
        self._docked = {}
        self._held = {}
        staged = port_counts(getattr(self.machine, "output", None), "fabricator.FabricatorController.drain_output: output.stacks")
        if not staged:
            return False
        # A local Supply Dock whose order owes the item takes it straight from
        # the output (no storage hop); the rest goes to a local Warehouse,
        # Inventory only for Inventory-only items or when no Warehouse has room
        # (storage_unload.drain_port_storage_first()).
        sent = []
        docked = {}
        for item_id, count in staged.items():
            targets = dock_delivery_targets(item_id, count, self.outpost())
            for dock_id, moved in push_to_targets(self.machine.output, item_id, count, targets):
                sent.append(f"{moved}x {item_id} to '{dock_id}'")
                docked[item_id] = docked.get(item_id, 0) + moved
                self._drained[item_id] = self._drained.get(item_id, 0) + moved
        drain_port_storage_first(self.machine.output, outpost=self.outpost())
        left = self.output_counts()
        self._held = left
        self._docked = docked
        for item_id, count in staged.items():
            stored = count - left.get(item_id, 0) - docked.get(item_id, 0)
            if stored > 0:
                self._drained[item_id] = self._drained.get(item_id, 0) + stored
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
        self.byproduct_warning.update(bool(capacity) and left >= capacity, f"Byproduct buffer full ({left}/{capacity}) and no storage has room -- recipe will stall until space frees up.")
        return moved > 0

    def load_inputs(self, recipe: "Recipe", crafts_remaining, remaining_capacity, cache: "SourceCache | None" = None, prio=NONE):
        """Tops the stockpile up for `recipe` (crafts_remaining, the free
        stockpile room and the recipe's prio come from step()); returns the
        units loaded. Units it could not take are published as wants at
        `prio` (publish_wants())."""
        # Fill the stockpile with enough for several crafts at once (not just
        # one) so the Auto Feeder isn't paid every craft, but cap it at what's
        # still actually needed: once running, the machine burns through the
        # whole staged batch on its own before the script gets another look,
        # so over-loading here directly overshoots the target/order.
        if remaining_capacity <= 0 or crafts_remaining <= 0:
            return 0

        loaded = []
        short = []
        stockpile = self.machine.get_stockpile() or {}
        # While the last pass left an input below one craft, the others load
        # one craft's worth at most: the machine can't use a full prefill yet,
        # and scarce inputs it hoards starve the Fabricators that can.
        last_recipe_id, last_short = self._short_inputs
        blocked = last_short if last_recipe_id == recipe.id else ()
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
            # this machine's Mk tier (the game's Recipe includes it). The prefill cap is what actually keeps
            # a heavy batch from being monopolized in a single grab: rather
            # than every Fabricator racing to fill the full remaining
            # shortfall (whoever polls first wins it all), each one only
            # ever asks for its own short, recipe-scaled prefill window, so
            # it stops requesting more once topped up and leaves frequent
            # openings for a peer Fabricator to get its own share too.
            prefill_cap = craft_prefill_units(recipe, item_id)
            if blocked and item_id not in blocked:
                prefill_cap = min(prefill_cap, required)
            amount = min(missing, remaining_capacity, FABRICATOR_LOAD_CHUNK_SIZE, max(0, prefill_cap - staged))
            self.log.debug(f"[{self.name}] load_inputs({recipe.id}): {item_id} staged={staged} missing={missing} remaining_capacity={remaining_capacity} prefill_cap={prefill_cap}{f' (one craft: {sorted(blocked)} short)' if blocked and item_id not in blocked else ''} -> amount={amount}")
            # take_item() checks Inventory first (home only), then rotates
            # through any local Warehouse holding this item -- see lib/storage.py.
            # The step-wide cache's stock snapshot only picks the holders to try; the
            # transfer itself reports what actually moved.
            moved = take_item(self.machine.input, item_id, amount, outpost=None if self.at_home() else self.outpost(), cache=cache)
            want = min(required * crafts_remaining, prefill_cap) - staged - max(0, moved)
            if want > 0:
                self._wants[item_id] = [want, prio]
            if staged + max(0, moved) < required:
                short.append(item_id)
            if moved <= 0:
                self._starved = self._starved or want > 0
                self.wake_local_smelters(item_id, cache)
                continue
            loaded.append(f"{moved}x {item_id}")
            remaining_capacity -= moved
        self._short_inputs = (recipe.id, tuple(short))
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
        self._starved = False
        active = self._step()
        self._last_idle = not self.machine.is_running() and self.machine.get_stockpile_used() <= 0
        self.publish_wants()
        return active

    def publish_wants(self):
        """Writes this step's input wants ({item: [units, prio]}) to
        FABRICATOR_WANTS_KEY when the wanted items change, a want shrinks (so
        a Smelter doesn't push the same units twice) or its prio changes,
        else every WANTS_REFRESH_TICKS while non-empty; an empty want removes
        the entry."""
        now = self.get_current_tick()
        published = self._wants_published
        unchanged = published is not None and set(self._wants) == set(published) and all(self._wants[i][0] >= published[i][0] and self._wants[i][1] == published[i][1] for i in self._wants)
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

    def plan_due(self, now):
        """True when the plan (recipe, crafts remaining) must be recomputed:
        none yet; older than PLAN_BACKSTOP_TICKS; a new shared demand record; the
        machine's recipe is not the planned one; the planned crafts (netted by
        what this Fabricator finished) are spent; the last load left a wanted
        input unmoved (the plan may switch); output that fed a local Supply
        Dock under this plan went to storage (the order no longer owes it,
        often done before the next demand record); a fluid-only recipe is
        winding down (tanks low); or the machine was idle after the last
        step."""
        plan = self._plan
        if not plan or now - plan["tick"] >= PLAN_BACKSTOP_TICKS:
            return True
        if record_tick() != plan["record_tick"]:
            return True
        recipe = plan["recipe"]
        if self.machine.get_recipe() != (getattr(recipe, "id", "") if recipe is not None else ""):
            return True
        if recipe is not None:
            if self.planned_crafts() <= 0:
                return True
            if self._starved:
                return True
            if self.dock_tail(recipe):
                return True
            if self.is_fluid_only(recipe) and self.fluid_low_reason(recipe) is not None:
                return True
        return self._last_idle

    def dock_tail(self, recipe: "Recipe"):
        """True when the planned output fed a local Supply Dock earlier in this
        plan and some of this step's drained units went to storage instead."""
        output_item = getattr(recipe, "output_item", None)
        stored = self._drained.get(output_item, 0) - self._docked.get(output_item, 0)
        return self._plan.get("docked", 0) > 0 and stored > 0

    def planned_crafts(self):
        """The planned crafts remaining, lowered by the crafts this Fabricator
        finished since the plan (output units drained, plus the growth of the
        output buffer when no destination had room, / units per craft)."""
        plan = self._plan
        recipe = plan["recipe"]
        output_count = max(1, getattr(recipe, "output_count", 1))
        held = self._held.get(getattr(recipe, "output_item", None), 0)
        made = plan["made"] + max(0, held - plan.get("held", 0))
        return max(0, plan["crafts_remaining"] - (-(-made // output_count)))

    def _fluid_feed(self, recipe: "Recipe | None", remaining):
        """Cuts the fluid feed of a fluid-only recipe whose target is met or whose
        tanks run low (it never goes idle while its fluid flows), else connects
        the recipe's fluid ports. Returns True when winding down."""
        winding_down = self.is_fluid_only(recipe) and (remaining <= 0 or self.fluid_low_reason(recipe) is not None)
        if winding_down:
            self.log.debug(f"[{self.name}] step: fluid-only recipe '{getattr(recipe, 'id', '?')}' target met or tanks low, cutting the fluid feed")
            self.stop_fluid_feed(recipe)
        else:
            self.ensure_fluid_connections(recipe)
        return winding_down

    def _replan(self, cache, now, active_recipe, active_remaining, active_prio):
        """The plan path: recipe choice and any recipe clear/set/switch, stored in
        self._plan. Returns (feed, worked): feed is True when the planned recipe is
        set and the stockpile should be topped up this step."""
        worked = False
        winding_down = self._fluid_feed(active_recipe, active_remaining)
        prior_recipe_id = self.machine.get_recipe()
        recipe = self.choose_recipe(cache)
        # get_fabricator_active_recipe() already counted the units held now.
        held = self._held.get(getattr(recipe, "output_item", None), 0)
        self._plan = {"recipe": recipe, "crafts_remaining": 0, "prio": NONE, "tick": now, "record_tick": record_tick(), "made": 0, "held": held}
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
            return False, worked

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
                # The shortfall read belongs to the old recipe: plan again next poll.
                self._plan = {}
                return False, worked
            self.log.debug(f"[{self.name}] step: '{recipe_id}' preferred over running '{prior_recipe_id}', switching once the current craft finishes")
            return False, True  # running, or the branch above would have switched
        self._plan.update({"crafts_remaining": active_remaining, "prio": active_prio})
        return True, worked

    def _step(self):
        self.ensure_connection()
        worked = self.drain_output()
        worked = self.drain_byproduct() or worked
        # One snapshot for the rest of the step, taken after the drains changed stock:
        # active-recipe shortfall, recipe choice and the input takes all read it.
        cache = SourceCache()
        now = self.get_current_tick()
        due = self.plan_due(now)
        if due:
            recipe, remaining, prio = get_fabricator_active_recipe(self.machine, cache)
        else:
            plan = self._plan
            recipe = plan["recipe"]
            output_item = getattr(recipe, "output_item", None)
            plan["made"] += self._drained.get(output_item, 0)
            plan["docked"] = plan.get("docked", 0) + self._docked.get(output_item, 0)
            remaining = self.planned_crafts() if recipe is not None else 0
            prio = plan["prio"]
        worked = self.eject_excess_inputs(recipe, remaining) or worked

        if self.is_shedded():
            # Power Guard has flagged this Fabricator for shedding (soft-shed
            # -- see is_shedded()'s docstring): don't start or top up
            # production. Whatever's already staged/running keeps going to
            # completion (never interrupted mid-craft), it just isn't fed
            # more, so draw winds down to 0 W on its own instead of an
            # abrupt breaker cut.
            self.log.debug(f"[{self.name}] step: shedded by Power Guard, not starting or topping up production")
            return worked or self.machine.is_running()

        if due:
            feed, replanned = self._replan(cache, now, recipe, remaining, prio)
            worked = worked or replanned
            if not feed:
                return worked or self.machine.is_running()
        elif recipe is not None:
            self.renew_claim(getattr(recipe, "id", ""))
            self._fluid_feed(recipe, remaining)
        if recipe is None:
            return worked or self.machine.is_running()

        capacity = self.machine.get_stockpile_capacity()
        used = self.machine.get_stockpile_used()
        if used < capacity:
            worked = self.load_inputs(recipe, remaining, capacity - used, cache, prio) > 0 or worked
        return worked or self.machine.is_running()
