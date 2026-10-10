# Shared base for the biome processor controllers (bio_coastal.py, bio_volcanic.py,
# bio_deep.py, bio_geothermal.py). Holds the parts every processor runs the same
# way: the focus-order lookup, the Lab heartbeat, the per-step order/stock fetch,
# picking and loading the next raw sample, and the run loop. Each subclass adds
# only its biome-specific processing step. Like the subclasses, this module
# imports bio.py and bio.py never imports it.
from bio import get_my_biome, is_local_order, local_sibling, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining, processor_fragment_preference
from storage import best_unload_target, drain_port_to_storage
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from game_clock import now_tick

# Seconds a processor step sleeps when it has nothing more to do this cycle.
PROCESSOR_IDLE_SLEEP_S = 0.5
# Clock ticks to wait after a take()/eject() on self.input before reading its stacks
# again (a take of 6 units lands over ~8 ticks; the step loop runs every ~5 ticks).
STAGE_SETTLE_TICKS = 20

# _classify_stack() kinds.
STACK_RAW = "raw"            # unprocessed sample load() accepts
STACK_FINISHED = "finished"  # already processed; belongs in storage for the Exchange
STACK_IGNORE = "ignore"      # not a sample at all (e.g. a staged Bio Caster material)


class BioProcessorController:
    """
    Base for one biome processor building. Subclasses set TYPE_ID, MODULE,
    DISPLAY_NAME, LOADED_SUFFIX and FINISHED_LABEL, implement step(), and override
    the hooks below where their machine differs.
    """
    TYPE_ID = "bio_processor"
    MODULE = "bio_processor"
    DISPLAY_NAME = "Bio Processor"
    ONLINE_SUFFIX = ""
    LOADED_SUFFIX = " into chamber."
    FINISHED_LABEL = "processed"
    # Property this processor's output carries (luminous, forged, ...). Finished
    # stock no open local order needs is destroyed (_load_next_sample_inner()).
    FINISHED_MARKER = None

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", self.TYPE_ID)
        self.comms = get_component("comms")
        self.log = TreeConsole(module=self.MODULE)
        self.last_stage_tick = None

    # --- hooks -----------------------------------------------------------------

    def _chamber_empty(self):
        return self.machine.chamber is None

    def _classify_stack(self, stack, orders) -> "tuple[str, dict | None]":
        """(kind, properties) for one stack: kind is STACK_RAW, STACK_FINISHED or
        STACK_IGNORE; properties is what load()/take()/eject() pass with "exact",
        normally _stack_properties(stack). Default: a stack with FINISHED_MARKER is
        finished (load() refuses it), every other one raw."""
        properties = self._stack_properties(stack)
        if self.FINISHED_MARKER and (properties or {}).get(self.FINISHED_MARKER):
            return STACK_FINISHED, properties
        return STACK_RAW, properties

    def _candidate_fragments(self, order: "BioOrder"):
        """Fragment ids of order this processor can load, in preference order
        (bio.processor_fragment_preference(), the same ranking the Collector uses)."""
        return processor_fragment_preference(self.machine, self.TYPE_ID, (order.requires or {}).keys())

    def _load(self, fragment_id, properties):
        """Loads fragment_id from self.input into the chamber; returns the load()
        result, or None when a preparatory call failed (already logged)."""
        return self.machine.load(fragment_id, properties, "exact")

    def _order_takes(self, order: "BioOrder", fragment_id, properties):
        """True when order still waits for deliveries of fragment_id that a finished
        stack with these properties satisfies. Coastal adds the glow check."""
        if getattr(order, "status", None) == "complete":
            return False
        needed = (order.requires or {}).get(fragment_id, 0)
        return needed - (order.delivered or {}).get(fragment_id, 0) > 0

    def _is_leftover(self, fragment_id, properties, orders):
        """True for finished output (FINISHED_MARKER set) that no open local order
        still takes: overproduction from a completed order. load() refuses it, so
        it only fills storage."""
        if not self.FINISHED_MARKER or not (properties or {}).get(self.FINISHED_MARKER):
            return False
        if not orders:
            return False  # no Exchange or orders() failed: nothing is known to be done
        my_biome = get_my_biome(self.machine)
        for order in orders:
            if is_local_order(order, my_biome) and self._order_takes(order, fragment_id, properties):
                return False
        return True

    def _on_only_nonraw_staged(self, staged_stacks):
        """self.input holds stacks, none of them a sample (all STACK_IGNORE)."""
        self.log.trace(f"exit, {len(staged_stacks)} non-raw stack(s) staged -- nothing to load this cycle.")

    # --- shared pipeline -------------------------------------------------------

    @staticmethod
    def _stack_properties(stack):
        """stack.properties for an "exact" match: None for a propertyless stack, since
        only None + "exact" selects propertyless items ({} matches nothing)."""
        return getattr(stack, "properties", None) or None

    def _tick(self):
        return now_tick()

    def _staging_settling(self):
        """True within STAGE_SETTLE_TICKS of the last take()/eject() on self.input:
        a transfer lands over several ticks, so stacks read before it lands would
        take or return the same units twice."""
        if self.last_stage_tick is None:
            return False
        elapsed = self._tick() - self.last_stage_tick
        if elapsed < STAGE_SETTLE_TICKS:
            self.log.trace(f"[{self.name}] Input transfer settling ({elapsed}/{STAGE_SETTLE_TICKS} ticks).")
            return True
        return False

    def _eject_staged(self, staged_id, count, properties, reason):
        """Returns count units of one exact staged variant from self.input to local storage."""
        try:
            destination = best_unload_target(staged_id, count, outpost=self.machine.outpost)
            if destination is None:
                return
            res = self.machine.input.eject(destination, staged_id, count, properties, "exact")
        except Exception as error:
            swallowed(f"{self.MODULE}._eject_staged: self.machine.input.eject", error)
            return
        status = getattr(res, "status", None)
        if status in ("ok", "partial"):
            self.last_stage_tick = self._tick()
        self.log.debug(f"Returned {count}x {reason} {staged_id} {properties} to '{destination}' -> {status}.")

    def _idle(self):
        flush_all()
        sleep(PROCESSOR_IDLE_SLEEP_S)

    def _find_local_order(self, orders, snapshot, fragment_id=None):
        """
        The order this processor works on, optionally one that requires fragment_id.
        Delegates to bio.py's _focus_local_order(), which BioCollectorController also
        uses, so Collector and processor concentrate on the same order. Deliberately
        not exchange.active_order(): BioExchangeController's delivery sweep
        reassigns that pointer to whatever order it last delivered to, any biome.
        """
        return _focus_local_order(orders, snapshot, get_my_biome(self.machine), fragment_id)

    def _notify_heartbeat(self):
        """
        Broadcasts biome_processor_heartbeat once every step(), whatever the step
        did. BioLabController waits on it via comms.wait_broadcast(), which only
        sees broadcasts published after the call, so a heartbeat sent only on a
        successful load would leave the Lab waiting forever once this processor
        goes idle. See BioLabController._wait_for_processor().
        """
        if not self.comms:
            return
        try:
            self.comms.broadcast("biome_processor_heartbeat", {"chamber_empty": self._chamber_empty()})
        except Exception as error:
            swallowed(f"{self.MODULE}._notify_heartbeat: self.comms.broadcast", error)

    def _port_stacks(self, port: "InputSlot | OutputSlot", where):
        if not hasattr(port, "stacks"):
            return []
        try:
            return port.stacks() or []
        except Exception as error:
            swallowed(where, error)
            return []

    def _begin_step(self):
        """Heartbeat and output drain, then exchange.orders() and the local stock
        snapshot, each read once per step and passed to every helper (re-reading per
        fragment cost seconds per cycle). Returns (outpost, exchange, orders, snapshot)."""
        self._notify_heartbeat()
        outpost = self.machine.outpost
        drain_port_to_storage(self.machine.output, outpost)
        exchange = local_sibling(outpost, "bio_exchange")
        orders = []
        if exchange:
            try:
                orders = exchange.orders()
            except Exception as error:
                swallowed(f"{self.MODULE}._begin_step: exchange.orders", error)
                orders = []
        return outpost, exchange, orders, _local_stock_snapshot(outpost)

    def _find_raw_stack(self, orders, fragment_id, outpost: "OutpostRef"):
        """(source_id, properties, count) for the first local fragment_id stack that
        _classify_stack() calls raw, or None. Finished stacks are left for delivery."""
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception as error:
                swallowed(f"{self.MODULE}._find_raw_stack: component.stacks", error)
                continue
            for stack in stacks:
                if getattr(stack, "id", None) != fragment_id:
                    continue
                count = getattr(stack, "count", 0)
                if count <= 0:
                    continue
                kind, properties = self._classify_stack(stack, orders)
                if kind == STACK_RAW:
                    return source_id, properties, count
        return None

    def _log_load(self, fragment_id, load_res):
        if load_res is None:
            return
        if load_res.status == "ok":
            self.log.print(f"[{self.name}] Loaded {fragment_id}{self.LOADED_SUFFIX}")
        else:
            self.log.debug(f"load({fragment_id}) -> {load_res.status}: {getattr(load_res, 'message', '')}")

    def _load_next_sample(self, orders, snapshot):
        self.log.start(f"[{self.name}] _load_next_sample", level="debug")
        self._load_next_sample_inner(orders, snapshot)
        self.log.end()

    def _load_next_sample_inner(self, orders, snapshot):
        """
        Chamber is empty. self.input latches to whatever is staged until load()
        clears it, so staged stacks come first: a finished one goes back to storage,
        a raw one is loaded if the focus order still needs it, else returned as
        stale. With nothing staged, pulls one raw sample of the focus order's first
        still-needed fragment from local storage and loads it. At most one transfer
        per cycle, none while the last one is still landing.
        """
        if self._staging_settling():
            return
        outpost = self.machine.outpost
        staged_stacks = self._port_stacks(self.machine.input, f"{self.MODULE}._load_next_sample: self.machine.input.stacks")

        raw_candidate = None
        leftovers = []
        other_staged = False
        for stack in staged_stacks:
            staged_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not staged_id or count <= 0:
                continue
            kind, properties = self._classify_stack(stack, orders)
            if kind == STACK_IGNORE:
                self.log.debug(f"Staged {staged_id} is not a sample this processor loads -- skipping.")
                other_staged = True
                continue
            if kind == STACK_FINISHED:
                if self._is_leftover(staged_id, properties, orders):
                    leftovers.append((staged_id, properties, count))
                    continue
                self._eject_staged(staged_id, count, properties, self.FINISHED_LABEL)
                return
            if raw_candidate is None:
                raw_candidate = (staged_id, properties, count)

        if leftovers:
            if raw_candidate is None and not other_staged:
                self._flush_leftovers(leftovers)
                return
            # flush() would take the other staged stacks with it: return these.
            staged_id, properties, count = leftovers[0]
            self._eject_staged(staged_id, count, properties, "leftover")
            return

        if raw_candidate:
            staged_id, properties, count = raw_candidate
            order = self._find_local_order(orders, snapshot, staged_id)
            remaining = _order_fragment_remaining(order, staged_id, snapshot) if order else 0
            self.log.debug(f"Staged raw candidate {staged_id}: focus_order={getattr(order, 'id', None)} remaining_needed={remaining}")
            if order and remaining > 0:
                self._log_load(staged_id, self._load(staged_id, properties))
                return
            self._eject_staged(staged_id, count, properties, "stale (no longer needed)")
            return

        if staged_stacks:
            self._on_only_nonraw_staged(staged_stacks)
            return

        order = self._find_local_order(orders, snapshot)
        if not order:
            self.log.trace("no local order to focus on.")
        elif self._pull_raw_for(order, orders, snapshot, outpost):
            return
        self._stage_leftover(orders, snapshot, outpost)

    def _pull_raw_for(self, order: "BioOrder", orders, snapshot, outpost: "OutpostRef"):
        """Pulls and loads one raw sample of order's first still-needed fragment.
        True when a sample was taken into self.input."""
        for fragment_id in self._candidate_fragments(order):
            remaining = _order_fragment_remaining(order, fragment_id, snapshot)
            if remaining <= 0:
                self.log.trace(f"{order.id} fragment {fragment_id}: remaining={remaining} -- already covered, skipping.")
                continue
            found = self._find_raw_stack(orders, fragment_id, outpost)
            if not found:
                self.log.trace(f"{order.id} still needs {remaining}x {fragment_id}, but no raw stack found locally.")
                continue
            source_id, properties, count = found
            self.log.debug(f"Pulling raw {fragment_id} (remaining={remaining}, found {count} at '{source_id}') for {order.id}.")
            self._connect_input(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                self.log.debug(f"take({fragment_id}) from '{source_id}' -> {take_res.status}: {getattr(take_res, 'message', '')}")
                continue
            self.last_stage_tick = self._tick()
            self._log_load(fragment_id, self._load(fragment_id, properties))
            return True
        self.log.trace(f"no fragment of {order.id} both needed and locally available as raw stock.")
        return False

    def _connect_input(self, source_id):
        if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
            self.machine.input.connect(source_id)

    def _stage_leftover(self, orders, snapshot, outpost: "OutpostRef"):
        """With no raw sample to load, takes one leftover stack (_is_leftover()) from
        local storage into self.input; the next cycle flushes it. The snapshot
        tells whether any exists, so storage is only walked when one does."""
        _, by_properties = snapshot
        wanted = {
            item_id for (item_id, key), count in by_properties.items()
            if count > 0 and self._is_leftover(item_id, dict(key), orders)
        }
        if not wanted:
            return
        for source_id, component in _local_sources(outpost):
            for stack in self._port_stacks(component, f"{self.MODULE}._stage_leftover: component.stacks"):
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                if item_id not in wanted or count <= 0:
                    continue
                properties = self._stack_properties(stack)
                if not self._is_leftover(item_id, properties, orders):
                    continue
                self._connect_input(source_id)
                take_res = self.machine.input.take(item_id, count, properties, "exact")
                self.log.debug(f"Staging {count}x leftover {item_id} {properties} from '{source_id}' to destroy -> {take_res.status}.")
                if take_res.status in ("ok", "partial"):
                    self.last_stage_tick = self._tick()
                return

    def _flush_leftovers(self, leftovers):
        """Destroys self.input's staged stacks; every one is a leftover."""
        try:
            res = self.machine.input.flush()
        except Exception as error:
            swallowed(f"{self.MODULE}._flush_leftovers: self.machine.input.flush", error)
            return
        summary = ", ".join(f"{count}x {item_id}" for item_id, _, count in leftovers)
        self.log.print(f"[{self.name}] Destroyed leftover {summary} (no open order takes it) -> {res.status}.")

    def step(self):
        raise NotImplementedError

    def run(self):
        self.log.print(f"{self.DISPLAY_NAME} ({self.name}) online via Shared Library{self.ONLINE_SUFFIX}.")
        validate_game_version()
        while True:
            reset_all()
            self.step()
