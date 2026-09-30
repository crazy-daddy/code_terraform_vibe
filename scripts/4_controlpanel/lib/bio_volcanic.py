# Volcanic biome processor: Bio Caster forge-casting.
# See docs/components/bio_caster.md. Imports its shared pipeline helpers from
# bio.py -- see that module's own header comment for why the split exists.
#
# LIVE-VERIFICATION NOTE: the docs describe self.input as accepting both the raw
# sample and fabricated materials via take(...), and materials() reads back
# "materials currently loaded in the crucible" compared against
# required_materials() before cast() -- but no method distinct from
# load(fragment_id) is documented for moving a material from self.input into the
# crucible. This controller assumes cast() (or the input buffer itself) auto-applies
# staged materials up to required_materials(), the same way a Fabricator/Smelter
# recipe auto-consumes its stockpile. Verify this once bio_caster is actually
# deployed and a first recipe attempted -- flip on debug() console output to see
# required_materials() vs materials() vs what's staged in self.input if a cast()
# unexpectedly returns "wrong_materials".
from bio import get_my_biome, local_sibling, is_local_order, is_order_incomplete, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining, processor_fragment_preference
from storage import take_item, best_unload_target, drain_port_to_storage
from production import set_upgrade_order, fabricator_unlocked_outputs, FLUID_SOURCE_TYPE_IDS, fluid_building_is_viable, SECONDS_PER_GAME_HOUR
import logistics_requests
import fluid_routing
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed

# Crucible temperature control (_drive_temperature): proportional toward the
# required_range() midpoint. The knob is sized so the remaining error closes over
# CASTER_CONVERGE_STEPS measured step intervals, so a step that runs up to that many
# times longer than estimated still does not overshoot the midpoint. Full knob is
# +/-2400 C/h = +/-96 C/s at 25 s per game hour, which crosses a whole band in
# under one step.
CASTER_FULL_RATE_C_PER_H = 2400.0
CASTER_PASSIVE_COOL_C_PER_H = 20.0
CASTER_CONVERGE_STEPS = 3.0
# Step interval estimate in game seconds before the first measurement, the EMA
# weight of each new measurement, and the clamp on a measured sample.
CASTER_STEP_SECONDS_DEFAULT = 1.0
CASTER_STEP_EMA_ALPHA = 0.5
CASTER_STEP_SECONDS_MIN = 0.5
CASTER_STEP_SECONDS_MAX = 5.0
CLOCK_TICKS_PER_SECOND = 10.0

# Requester id for the caster's material demand in fabricator.upgrade_orders and
# logistics.requests; listed in production.STANDING_ORDER_REQUESTERS.
REQUESTER_ID = "bio_caster"
# Minimum clock ticks between two material-demand publishes (10 ticks/s -> 60 s).
MATERIAL_PUBLISH_INTERVAL_TICKS = 600
# Clock ticks to wait after a take()/eject() on self.input before reading its counts
# again (a take of 6 units lands over ~8 ticks; the step loop runs every ~5 ticks).
STAGE_SETTLE_TICKS = 20

# steam_in/water_in source routing (fluid_routing.FluidInputRouter), same values as
# the Plant Terraformer's water router.
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5
# Caster port attribute -> FLUID_SOURCE_TYPE_IDS key.
CASTER_FLUID_PORTS = ("steam_in", "water_in")


class BioCasterController:
    """
    Forges a raw Volcanic sample into its recipe's fragment: drives crucible
    temperature into required_range() while required_materials() are staged, then
    casts (docs/components/bio_caster.md). A sample whose fragment doesn't need
    forging right now (no active local order requiring it) is passed through
    unchanged via eject() -- bio_caster has no discard(); eject() is the documented
    non-destructive pass-through, safe before any cast() is attempted.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_caster")
        self.comms = get_component("comms")
        self.log = TreeConsole(module="bio_volcanic")
        self.recipe_cache = {}
        self.last_publish_tick = None
        self.published_demand = None
        self.fluid_routers = {}
        self.last_stage_tick = None
        self.last_drive_tick = None
        self.step_seconds = CASTER_STEP_SECONDS_DEFAULT

    def _find_local_order(self, orders, snapshot, fragment_id=None):
        """Delegates to bio.py's _focus_local_order() -- shared with
        BioCollectorController's own harvest preference so both concentrate on the
        same order at the same time, mirroring BioLuminizerController's
        _find_coastal_order()."""
        my_biome = get_my_biome(self.machine)
        return _focus_local_order(orders, snapshot, my_biome, fragment_id)

    def _notify_heartbeat(self):
        """Broadcasts once every step() cycle regardless of outcome -- see
        BioLabController._wait_for_processor()'s docstring for why this must be
        unconditional, not just fired on a successful load."""
        if not self.comms:
            return
        try:
            self.comms.broadcast("biome_processor_heartbeat", {"chamber_empty": self.machine.fragment() is None})
        except Exception as error:
            swallowed("bio_volcanic.BioCasterController._notify_heartbeat: self.comms.broadcast", error)

    def _find_raw_stack(self, fragment_id, outpost):
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController._find_raw_stack: component.stacks", error)
                continue
            for stack in stacks:
                if getattr(stack, "id", None) != fragment_id:
                    continue
                count = getattr(stack, "count", 0)
                if count <= 0:
                    continue
                if getattr(stack, "properties", None):
                    continue  # forged marker: finished output, not a raw sample load() accepts
                return source_id, None, count  # None + "exact" = propertyless only
        return None

    def _load_next_sample(self, orders, snapshot):
        self.log.start(f"[{self.name}] _load_next_sample", level="debug")
        outpost = self.machine.outpost
        self.log.trace("entry")

        staged_stacks = []
        if hasattr(self.machine.input, "stacks"):
            try:
                staged_stacks = self.machine.input.stacks()
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController._load_next_sample: self.machine.input.stacks", error)
                staged_stacks = []

        raw_candidate = None
        for stack in staged_stacks:
            staged_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not staged_id or count <= 0:
                continue
            if self.machine.find_recipe(staged_id) is None:
                self.log.debug(f"Staged {staged_id} has no matching recipe -- treating as a fabricated material, not a raw fragment.")
                continue  # a staged fabricated material, not a forgeable raw fragment
            properties = getattr(stack, "properties", None) or None  # None + "exact" = propertyless only; {} matches nothing
            if properties:
                # Forged marker: load() only takes raw samples, so return it to storage.
                try:
                    destination = best_unload_target(staged_id, count, outpost=outpost)
                    eject_res = self.machine.input.eject(destination, staged_id, count, properties, "exact")
                    self.log.debug(f"Staged {staged_id} {properties} is forged, not raw -- eject {count} to '{destination}' -> {getattr(eject_res, 'status', None)}.")
                except Exception as error:
                    swallowed("bio_volcanic.BioCasterController._load_next_sample: self.machine.input.eject forged", error)
                self.log.end()
                return
            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_local_order(orders, snapshot, staged_id)
            remaining = _order_fragment_remaining(order, staged_id, snapshot) if order else 0
            self.log.trace(f"Staged raw candidate {staged_id}: focus_order={getattr(order, 'id', None)} remaining_needed={remaining}")
            if order and remaining > 0:
                set_res = self.machine.set_recipe(staged_id)
                if set_res.status == "ok":
                    load_res = self.machine.load(staged_id, properties, "exact")
                    if load_res.status == "ok":
                        self.log.print(f"[{self.name}] Loaded {staged_id} into crucible.")
                    else:
                        self.log.debug(f"load({staged_id}) -> {load_res.status}: {getattr(load_res, 'message', '')}")
                else:
                    self.log.debug(f"set_recipe({staged_id}) -> {set_res.status}: {getattr(set_res, 'message', '')}")
                self.log.end()
                return
            try:
                count = self.machine.input.count()
                destination = best_unload_target(staged_id, count, outpost=outpost)
                self.machine.input.eject(destination, staged_id, count, properties, "exact")
                self.log.debug(f"Recovered stale staged {staged_id} to '{destination}' (no longer needed).")
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController._load_next_sample: self.machine.input.count", error)
            self.log.end()
            return

        if staged_stacks:
            # Only fabricated materials left with an empty chamber: return them. The Lab
            # hands over the next sample only once self.input is empty
            # (bio._processor_is_idle()), so leftovers here block the pipeline.
            self._return_staged_surplus({}, "chamber empty")
            self.log.end()
            return

        order = self._find_local_order(orders, snapshot)
        if not order:
            self.log.trace("exit, no local order to focus on.")
            self.log.end()
            return

        for fragment_id in processor_fragment_preference(self.machine, "bio_caster", (order.requires or {}).keys()):
            if self.machine.find_recipe(fragment_id) is None:
                continue  # not a Bio Caster recipe -- some other biome's fragment
            remaining = _order_fragment_remaining(order, fragment_id, snapshot)
            if remaining <= 0:
                self.log.trace(f"{order.id} fragment {fragment_id}: remaining={remaining} -- already covered, skipping.")
                continue
            found = self._find_raw_stack(fragment_id, outpost)
            if not found:
                self.log.trace(f"{order.id} still needs {remaining}x {fragment_id}, but no raw stack found locally.")
                continue
            source_id, properties, count = found
            self.log.debug(f"Pulling raw {fragment_id} (remaining={remaining}, found {count} at '{source_id}') for {order.id}.")
            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                self.log.debug(f"take({fragment_id}) from '{source_id}' -> {take_res.status}: {getattr(take_res, 'message', '')}")
                continue
            set_res = self.machine.set_recipe(fragment_id)
            if set_res.status != "ok":
                self.log.debug(f"set_recipe({fragment_id}) -> {set_res.status}: {getattr(set_res, 'message', '')}")
                continue
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                self.log.print(f"[{self.name}] Loaded {fragment_id} into crucible.")
            else:
                self.log.debug(f"load({fragment_id}) -> {load_res.status}: {getattr(load_res, 'message', '')}")
            self.log.end()
            return
        self.log.trace(f"exit, no fragment of {order.id} both needed and locally available as raw stock.")
        self.log.end()

    def _load_materials(self, required_materials, outpost):
        """Stages the first still-short fabricated material into self.input from
        local storage, one material per cycle (mirrors BioLabController's reagent
        loop) -- see the module header's live-verification note on how staged
        materials actually reach the crucible's materials() count."""
        self.log.start(f"[{self.name}] _load_materials", level="debug")
        if self._staging_settling():
            self.log.end()
            return
        if self.machine.output.count() > 0:
            self.log.trace("Output not drained yet -- holding material staging.")
            self.log.end()
            return
        loaded = self.machine.materials() or {}
        for material_id, required_qty in required_materials.items():
            have = loaded.get(material_id, 0)
            missing = required_qty - have
            if missing <= 0:
                self.log.trace(f"Material {material_id}: have={have} required={required_qty} -- already sufficient.")
                continue
            moved = take_item(self.machine.input, material_id, missing, outpost=outpost)
            if moved > 0:
                self.last_stage_tick = self._tick()
            self.log.debug(f"Staged {moved}x {material_id} toward {required_qty} required (have={have}, missing={missing}).")
            self.log.end()
            return
        self.log.end()

    def _tick(self):
        clock = get_component("clock")
        return clock.tick() if clock else 0

    def _staging_settling(self):
        """True within STAGE_SETTLE_TICKS of the last take()/eject() on self.input:
        a transfer lands over several ticks, so counts read before it lands would
        stage or return the same units twice."""
        if self.last_stage_tick is None:
            return False
        elapsed = self._tick() - self.last_stage_tick
        if elapsed < STAGE_SETTLE_TICKS:
            self.log.trace(f"[{self.name}] Input transfer settling ({elapsed}/{STAGE_SETTLE_TICKS} ticks).")
            return True
        return False

    def _return_staged_surplus(self, required_materials, reason):
        """Ejects staged fabricated materials beyond required_materials back to local
        storage, one stack per call. cast() needs materials() to match
        required_materials() exactly, and the Lab's hand-off needs an empty input once
        the chamber is empty. Returns True when an eject was issued."""
        if self._staging_settling():
            return True
        outpost = self.machine.outpost
        for stack in self._port_stacks(self.machine.input, "bio_volcanic.BioCasterController._return_staged_surplus: self.machine.input.stacks"):
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not item_id or count <= 0 or self._recipe_materials(item_id) is not None:
                continue  # raw/forged fragments are handled by _load_next_sample()
            surplus = count - required_materials.get(item_id, 0)
            if surplus <= 0:
                continue
            properties = getattr(stack, "properties", None) or None
            try:
                destination = best_unload_target(item_id, surplus, outpost=outpost)
                if not destination:
                    self.log.debug(f"[{self.name}] No local storage has room for {surplus}x surplus {item_id}.")
                    continue
                res = self.machine.input.eject(destination, item_id, surplus, properties, "exact")
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController._return_staged_surplus: self.machine.input.eject", error)
                continue
            status = getattr(res, "status", None)
            self.log.print(f"[{self.name}] Returned {surplus}x {item_id} to '{destination}' ({reason}) -> {status}.")
            if status in ("ok", "partial"):
                self.last_stage_tick = self._tick()
            return True
        return False

    def _recipe_materials(self, fragment_id):
        """{material_id: qty} for one cast of fragment_id, or None when the caster has no
        recipe (not a Volcanic fragment, or not readable). Cached: recipes are fixed hardware."""
        if fragment_id in self.recipe_cache:
            return self.recipe_cache[fragment_id]
        materials = None
        try:
            recipe = self.machine.find_recipe(fragment_id)
            if recipe is not None:
                materials = dict(getattr(recipe, "materials", None) or {})
        except Exception as error:
            swallowed("bio_volcanic.BioCasterController._recipe_materials: self.machine.find_recipe", error)
        if not materials:
            materials = None
        self.recipe_cache[fragment_id] = materials
        return materials

    def _port_stacks(self, port, where):
        if not hasattr(port, "stacks"):
            return []
        try:
            return port.stacks() or []
        except Exception as error:
            swallowed(where, error)
            return []

    def _aggregate_material_demand(self, orders, snapshot):
        """
        (need, urgent): {material_id: units} still needed at this outpost to cast
        every fragment all open local orders still want, and the part of it the
        current focus order (the delivery being worked on) still needs. Every unit already committed is
        subtracted once: delivered/in-transit samples via the order's own counters,
        forged samples in local storage and the caster output, the fragment in the
        crucible and its loaded materials, and materials staged in self.input.
        Material stock in local storage and on haulers is left to the consumers
        (_publish_material_demand()).
        """
        self.log.start(f"[{self.name}] _aggregate_material_demand", level="debug")
        my_biome = get_my_biome(self.machine)
        _, by_properties = snapshot

        casts = {}
        for order in orders:
            if not is_order_incomplete(order) or not is_local_order(order, my_biome):
                continue
            requires = order.requires or {}
            delivered = order.delivered or {}
            in_transit = order.in_transit or {}
            for fragment_id, needed in requires.items():
                open_units = needed - delivered.get(fragment_id, 0) - in_transit.get(fragment_id, 0)
                if open_units <= 0:
                    continue
                if not self._recipe_materials(fragment_id):
                    self.log.debug(f"{getattr(order, 'id', '?')} {fragment_id}: no caster recipe/materials known -- skipped in material demand.")
                    continue
                casts[fragment_id] = casts.get(fragment_id, 0) + open_units

        # A forged fragment carries a marker property; a raw one from the Lab has none.
        output_forged = {}
        for stack in self._port_stacks(self.machine.output, "bio_volcanic.BioCasterController._aggregate_material_demand: self.machine.output.stacks"):
            if getattr(stack, "properties", None):
                item_id = getattr(stack, "id", None)
                output_forged[item_id] = output_forged.get(item_id, 0) + getattr(stack, "count", 0)
        loaded_fragment = self.machine.fragment()
        current_cast_wanted = loaded_fragment is not None and loaded_fragment in casts

        for fragment_id in list(casts.keys()):
            ordered = casts[fragment_id]
            forged_local = sum(count for (item_id, _), count in by_properties.items() if item_id == fragment_id)
            forged_output = output_forged.get(fragment_id, 0)
            in_crucible = 1 if loaded_fragment == fragment_id else 0
            casts[fragment_id] = max(0, ordered - forged_local - forged_output - in_crucible)
            self.log.debug(
                f"[{self.name}] demand {fragment_id}: ordered={ordered} forged_local={forged_local} "
                f"forged_output={forged_output} in_crucible={in_crucible} -> casts={casts[fragment_id]}"
            )

        need = {}
        for fragment_id, count in casts.items():
            for material_id, qty in (self._recipe_materials(fragment_id) or {}).items():
                need[material_id] = need.get(material_id, 0) + qty * count

        # Urgent tier: everything the order the pipeline is working on right now (the
        # same focus order the Collector and _load_next_sample() use) still needs,
        # capped by the global casts so forged stock is never counted twice. The cast
        # in the crucible was taken out of casts above; add only what it still lacks.
        focus = self._find_local_order(orders, snapshot, loaded_fragment) if loaded_fragment is not None else self._find_local_order(orders, snapshot)
        urgent = {}
        if focus is not None:
            requires = focus.requires or {}
            delivered = focus.delivered or {}
            in_transit = focus.in_transit or {}
            for fragment_id, needed in requires.items():
                if fragment_id not in casts:
                    continue
                open_units = needed - delivered.get(fragment_id, 0) - in_transit.get(fragment_id, 0)
                if loaded_fragment == fragment_id:
                    open_units -= 1
                focus_casts = min(max(0, open_units), casts[fragment_id])
                for material_id, qty in (self._recipe_materials(fragment_id) or {}).items():
                    urgent[material_id] = urgent.get(material_id, 0) + qty * focus_casts
            self.log.debug(f"urgent tier = focus order {getattr(focus, 'id', '?')}: {urgent}")
        if current_cast_wanted:
            loaded = self.machine.materials() or {}
            for material_id, qty in (self.machine.required_materials() or {}).items():
                missing = qty - loaded.get(material_id, 0)
                if missing > 0:
                    need[material_id] = need.get(material_id, 0) + missing
                    urgent[material_id] = urgent.get(material_id, 0) + missing

        staged = {}
        for stack in self._port_stacks(self.machine.input, "bio_volcanic.BioCasterController._aggregate_material_demand: self.machine.input.stacks"):
            item_id = getattr(stack, "id", None)
            if item_id and self._recipe_materials(item_id) is None:
                staged[item_id] = staged.get(item_id, 0) + getattr(stack, "count", 0)
        for material_id, count in staged.items():
            if material_id in need:
                need[material_id] = max(0, need[material_id] - count)
            if material_id in urgent:
                urgent[material_id] = max(0, urgent[material_id] - count)

        need = {m: q for m, q in need.items() if q > 0}
        urgent = {m: min(q, need.get(m, 0)) for m, q in urgent.items() if q > 0 and m in need}
        self.log.end()
        return need, urgent

    def _publish_material_demand(self, orders, snapshot):
        """Publishes the material demand at most every MATERIAL_PUBLISH_INTERVAL_TICKS:
        a standing Fabricator order for the urgent tier only (build what the current
        delivery needs), and a logistics request at this outpost for the full demand
        (haul it here; urgent tier = need, rest = buffer from existing stock)."""
        outpost = self.machine.outpost
        outpost_id = getattr(outpost, "id", None)
        if not outpost_id:
            return
        clock = get_component("clock")
        tick = clock.tick() if clock else 0
        if self.last_publish_tick is not None and tick - self.last_publish_tick < MATERIAL_PUBLISH_INTERVAL_TICKS:
            return
        self.last_publish_tick = tick

        need, urgent = self._aggregate_material_demand(orders, snapshot)
        totals, _ = snapshot
        try:
            if not need:
                set_upgrade_order(REQUESTER_ID, {})
                logistics_requests.clear_requests(REQUESTER_ID, outpost_id)
            else:
                flying = logistics_requests.in_flight(outpost_id, tick)
                buildable = fabricator_unlocked_outputs()
                floor = {}
                for material_id, qty in need.items():
                    # Fabricator builds only the urgent tier (the current delivery); the
                    # floor moves on to the next order's parts once this one completes.
                    floor_qty = max(0, urgent.get(material_id, 0) - flying.get(material_id, 0))
                    if material_id in buildable and floor_qty > 0:
                        floor[material_id] = floor_qty
                    self.log.debug(
                        f"[{self.name}] material {material_id}: need={qty} local_have={totals.get(material_id, 0)} "
                        f"in_flight={flying.get(material_id, 0)} urgent={urgent.get(material_id, 0)} "
                        f"-> fabricator_floor={floor.get(material_id, 0)} buildable={material_id in buildable}"
                    )
                set_upgrade_order(REQUESTER_ID, floor)
                wants = {m: (q, totals.get(m, 0), urgent.get(m, 0)) for m, q in need.items()}
                logistics_requests.set_requests(outpost_id, REQUESTER_ID, wants, tick)
        except Exception as error:
            swallowed("bio_volcanic.BioCasterController._publish_material_demand: publish", error)
            return
        if need != self.published_demand:
            self.published_demand = need
            if need:
                self.log.print(f"[{self.name}] Material demand for all open orders: {need}")
            else:
                self.log.print(f"[{self.name}] No material demand -- cleared orders and requests.")

    def _discover_fluid_sources(self, fluid_key):
        """Network-wide source ids for fluid_key (FLUID_SOURCE_TYPE_IDS), own outpost first.
        Buffer tanks count only when latched to the right fluid (fluid_building_is_viable())."""
        own_outpost_id = getattr(self.machine.outpost, "id", None)
        pairs = []
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    o_id = getattr(outpost, "id", None)
                    for type_id in FLUID_SOURCE_TYPE_IDS[fluid_key]:
                        for building in outpost.buildings(type_id):
                            b_id = getattr(building, "id", None)
                            if b_id and fluid_building_is_viable(fluid_key, type_id, building):
                                pairs.append((b_id, o_id))
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController._discover_fluid_sources: network.outposts", error)
        ids = fluid_routing.rank_own_outpost_first(pairs, own_outpost_id)
        self.log.debug(f"[{self.name}] {fluid_key}: sources (own outpost first): {ids}.")
        return ids

    @staticmethod
    def _port_starved(port):
        """flow_rate() == 0 with room left -- a full port also reads 0, not a stall."""
        try:
            level = port.level() if hasattr(port, "level") else 0
            capacity = port.capacity() if hasattr(port, "capacity") else 0
            flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
            return flow == 0 and (not capacity or level < capacity)
        except Exception as error:
            swallowed("bio_volcanic.BioCasterController._port_starved: port.level", error)
            return False

    @staticmethod
    def _port_level(port):
        try:
            return port.level() if port and hasattr(port, "level") else 0
        except Exception as error:
            swallowed("bio_volcanic.BioCasterController._port_level: port.level", error)
            return 0

    def _ensure_fluid_inputs(self):
        """Keeps steam_in and water_in connected to a reachable source, network-wide."""
        clock = get_component("clock")
        curr_tick = clock.tick() if clock else 0
        for fluid_key in CASTER_FLUID_PORTS:
            port = getattr(self.machine, fluid_key, None)
            if not port:
                continue
            router = self.fluid_routers.get(fluid_key)
            if router is None:
                router = fluid_routing.FluidInputRouter(
                    discover=lambda key=fluid_key: self._discover_fluid_sources(key),
                    rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                    discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                    stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                    neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                    label=f"{self.name}.{fluid_key}",
                )
                self.fluid_routers[fluid_key] = router

            def on_dropped(source_id, reason, key=fluid_key):
                self.log.level("warn").print(f"[{self.name}] Dropping {key} source '{source_id}': {reason}. Picking another.")

            def on_connect_notice(source_id, status, message, key=fluid_key):
                self.log.level("warn").print(f"[{self.name}] {key} connect notice for '{source_id}': {status} - {message}")

            event = router.ensure(port, curr_tick, self._port_starved(port), on_dropped, on_connect_notice)
            if event.kind == "connected":
                self.log.print(f"[{self.name}] Connected {fluid_key} -> '{event.source_id}'.")
            elif event.kind == "not_found":
                self.log.debug(f"[{self.name}] no {fluid_key} source on the network.")

    def _set_knobs(self, heat_pct, cool_pct):
        """Sets heat/cool only when the value changes. A knob above 0 needs fluid in its
        buffer (set_heat()/set_cool() return "empty" otherwise), so it stays at 0 while
        steam_in/water_in is dry; _ensure_fluid_inputs() is what refills them."""
        self.log.start(f"[{self.name}] _set_knobs", level="debug")
        if heat_pct > 0 and self._port_level(getattr(self.machine, "steam_in", None)) <= 0:
            self.log.trace(f"steam_in empty -- holding heat at 0 (wanted {heat_pct}).")
            heat_pct = 0
        if cool_pct > 0 and self._port_level(getattr(self.machine, "water_in", None)) <= 0:
            self.log.trace(f"water_in empty -- holding cool at 0 (wanted {cool_pct}).")
            cool_pct = 0
        for knob, pct, setter in (("heat", heat_pct, self.machine.set_heat), ("cool", cool_pct, self.machine.set_cool)):
            current = self.machine.heat() if knob == "heat" else self.machine.cool()
            if current == pct:
                continue
            res = setter(pct)
            if res.status != "ok":
                self.log.debug(f"set_{knob}({pct}) -> {res.status}: {getattr(res, 'message', '')}")
        self.log.end()

    def _measure_step_seconds(self):
        """EMA of game seconds between consecutive _drive_temperature() calls. A gap
        above CASTER_STEP_SECONDS_MAX (idle chamber, script restart) is not a step
        interval and is ignored."""
        now = self._tick()
        last = self.last_drive_tick
        self.last_drive_tick = now
        if last is None or now <= last:
            return self.step_seconds
        sample = (now - last) / CLOCK_TICKS_PER_SECOND
        if sample > CASTER_STEP_SECONDS_MAX:
            return self.step_seconds
        sample = max(CASTER_STEP_SECONDS_MIN, sample)
        self.step_seconds += CASTER_STEP_EMA_ALPHA * (sample - self.step_seconds)
        return self.step_seconds

    def _drive_temperature(self, target_range):
        """Proportional control toward the band midpoint: the knob rate closes the
        error over CASTER_CONVERGE_STEPS step intervals, plus a feed-forward for
        passive cooling. Positive rate is heat, negative is cool."""
        low, high = target_range
        temp = self.machine.temperature()
        step_seconds = self._measure_step_seconds()
        target = (low + high) / 2.0
        error = target - temp
        rate_c_per_h = error / (CASTER_CONVERGE_STEPS * step_seconds) * SECONDS_PER_GAME_HOUR + CASTER_PASSIVE_COOL_C_PER_H
        pct = max(-100, min(100, int(round(rate_c_per_h / CASTER_FULL_RATE_C_PER_H * 100.0))))
        if pct >= 0:
            self._set_knobs(pct, 0)
        else:
            self._set_knobs(0, -pct)
        self.log.debug(
            f"[{self.name}] temperature={temp:.1f}C target=[{low:.1f},{high:.1f}] mid={target:.1f}C "
            f"error={error:+.1f}C step={step_seconds:.2f}s rate_wanted={rate_c_per_h:+.0f}C/h "
            f"-> heat={self.machine.heat()} cool={self.machine.cool()} temp_rate={self.machine.temp_rate():+.0f}C/h"
        )

    def step(self):
        self._notify_heartbeat()
        drain_port_to_storage(self.machine.output, self.machine.outpost)
        self._ensure_fluid_inputs()

        outpost = self.machine.outpost
        exchange = local_sibling(outpost, "bio_exchange")

        orders = []
        if exchange:
            try:
                orders = exchange.orders()
            except Exception as error:
                swallowed("bio_volcanic.BioCasterController.step: exchange.orders", error)
                orders = []
        snapshot = _local_stock_snapshot(outpost)
        if exchange:
            self._publish_material_demand(orders, snapshot)
        self.log.trace(f"[{self.name}] step: entry, {len(orders)} order(s) fetched, fragment_loaded={self.machine.fragment() is not None}")

        fragment_id = self.machine.fragment()
        if fragment_id is None:
            self._set_knobs(0, 0)
            self._load_next_sample(orders, snapshot)
            flush_all()
            sleep(0.5)
            return

        order = self._find_local_order(orders, snapshot, fragment_id)
        remaining = _order_fragment_remaining(order, fragment_id, snapshot) if order else 0
        if not order or remaining <= 0:
            # Nothing local needs this fragment forged right now -- pass through unchanged.
            self.log.debug(f"[{self.name}] {fragment_id}: focus_order={getattr(order, 'id', None)} remaining_needed={remaining} -- nothing needs it forged, ejecting unchanged.")
            self.machine.eject()
            flush_all()
            sleep(0.5)
            return

        required_range = self.machine.required_range()
        required_materials = self.machine.required_materials() or {}
        if not required_range:
            self.log.debug(f"[{self.name}] No recipe selected despite a loaded fragment -- ejecting.")
            self.machine.eject()
            flush_all()
            sleep(0.5)
            return

        if self._return_staged_surplus(required_materials, f"surplus for {fragment_id}"):
            self._drive_temperature(required_range)
            flush_all()
            sleep(0.5)
            return

        materials_ready = all(
            (self.machine.materials() or {}).get(m, 0) >= qty
            for m, qty in required_materials.items()
        )
        self.log.trace(f"[{self.name}] {fragment_id}: required_materials={required_materials} materials_ready={materials_ready} required_range={required_range}")
        self._drive_temperature(required_range)
        if not materials_ready:
            self._load_materials(required_materials, outpost)
            flush_all()
            sleep(0.5)
            return

        temp = self.machine.temperature()
        low, high = required_range
        if low <= temp <= high:
            self.log.debug(f"[{self.name}] temperature={temp:.1f}C within target [{low:.1f},{high:.1f}] and materials ready -- attempting cast().")
            cast_res = self.machine.cast()
            if cast_res.status == "ok":
                self.log.print(f"[{self.name}] Cast {fragment_id} at {temp:.1f}C.")
            elif cast_res.status != "busy":
                self.log.debug(f"[{self.name}] cast() -> {cast_res.status}: {cast_res.message}")
        else:
            self.log.trace(f"[{self.name}] temperature={temp:.1f}C outside target [{low:.1f},{high:.1f}] -- holding cast(), still driving toward range.")
        flush_all()
        sleep(0.5)

    def run(self):
        self.log.print(f"Bio Caster ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            reset_all()
            self.step()
