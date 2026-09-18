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
from bio import get_my_biome, local_sibling, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining
from storage import take_item, best_unload_target, drain_port_to_storage
from version_guard import validate_game_version
from tree_console import TreeConsole

# Reduced heat/cool knob percentage once within this many degrees C of the recipe's
# required_range() edge, to avoid overshoot given the full-knob +/-2400 C/h rate
# against this script's own ~0.5s poll interval. Tune once live-verified against a
# real forge run -- see docs/AI_CHEATSHEET.md.
CASTER_APPROACH_BAND_C = 50.0
CASTER_APPROACH_PCT = 25.0


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
        self.console = TreeConsole()

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
        except Exception:
            pass

    def _find_raw_stack(self, fragment_id, outpost):
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception:
                continue
            for stack in stacks:
                if getattr(stack, "id", None) != fragment_id:
                    continue
                count = getattr(stack, "count", 0)
                if count <= 0:
                    continue
                properties = getattr(stack, "properties", None) or {}
                return source_id, properties, count
        return None

    def _load_next_sample(self, orders, snapshot):
        outpost = self.machine.outpost

        staged_stacks = []
        if hasattr(self.machine.input, "stacks"):
            try:
                staged_stacks = self.machine.input.stacks()
            except Exception:
                staged_stacks = []

        raw_candidate = None
        for stack in staged_stacks:
            staged_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not staged_id or count <= 0:
                continue
            if self.machine.find_recipe(staged_id) is None:
                continue  # a staged fabricated material, not a forgeable raw fragment
            properties = getattr(stack, "properties", None) or {}
            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_local_order(orders, snapshot, staged_id)
            if order and _order_fragment_remaining(order, staged_id, snapshot) > 0:
                set_res = self.machine.set_recipe(staged_id)
                if set_res.status == "ok":
                    load_res = self.machine.load(staged_id, properties, "exact")
                    if load_res.status == "ok":
                        self.console.print(f"[{self.name}] Loaded {staged_id} into crucible.")
                return
            try:
                count = self.machine.input.count()
                destination = best_unload_target(staged_id, count, outpost=outpost)
                self.machine.input.eject(destination, staged_id, count, properties, "exact")
                self.console.debug(f"[{self.name}] Recovered stale staged {staged_id} to '{destination}' (no longer needed).")
            except Exception:
                pass
            return

        if staged_stacks:
            return  # everything staged is a fabricated material waiting for its recipe

        order = self._find_local_order(orders, snapshot)
        if not order:
            return

        for fragment_id in (order.requires or {}).keys():
            if self.machine.find_recipe(fragment_id) is None:
                continue  # not a Bio Caster recipe -- some other biome's fragment
            if _order_fragment_remaining(order, fragment_id, snapshot) <= 0:
                continue
            found = self._find_raw_stack(fragment_id, outpost)
            if not found:
                continue
            source_id, properties, _ = found
            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                continue
            set_res = self.machine.set_recipe(fragment_id)
            if set_res.status != "ok":
                continue
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                self.console.print(f"[{self.name}] Loaded {fragment_id} into crucible.")
            return

    def _load_materials(self, required_materials, outpost):
        """Stages the first still-short fabricated material into self.input from
        local storage, one material per cycle (mirrors BioLabController's reagent
        loop) -- see the module header's live-verification note on how staged
        materials actually reach the crucible's materials() count."""
        loaded = self.machine.materials() or {}
        for material_id, required_qty in required_materials.items():
            have = loaded.get(material_id, 0)
            missing = required_qty - have
            if missing <= 0:
                continue
            moved = take_item(self.machine.input, material_id, missing, outpost=outpost)
            self.console.debug(f"[{self.name}] Staged {moved}x {material_id} toward {required_qty} required.")
            return

    def _drive_temperature(self, target_range):
        low, high = target_range
        temp = self.machine.temperature()
        if temp < low - CASTER_APPROACH_BAND_C:
            self.machine.set_cool(0)
            self.machine.set_heat(100)
        elif temp < low:
            self.machine.set_cool(0)
            self.machine.set_heat(CASTER_APPROACH_PCT)
        elif temp > high + CASTER_APPROACH_BAND_C:
            self.machine.set_heat(0)
            self.machine.set_cool(100)
        elif temp > high:
            self.machine.set_heat(0)
            self.machine.set_cool(CASTER_APPROACH_PCT)
        else:
            self.machine.set_heat(0)
            self.machine.set_cool(0)
        self.console.debug(
            f"[{self.name}] temperature={temp:.1f}C target=[{low:.1f},{high:.1f}] "
            f"heat={self.machine.heat()} cool={self.machine.cool()}"
        )

    def step(self):
        self._notify_heartbeat()
        drain_port_to_storage(self.machine.output, self.machine.outpost)

        outpost = self.machine.outpost
        exchange = local_sibling(outpost, "bio_exchange")

        orders = []
        if exchange:
            try:
                orders = exchange.orders()
            except Exception:
                orders = []
        snapshot = _local_stock_snapshot(outpost)

        fragment_id = self.machine.fragment()
        if fragment_id is None:
            self.machine.set_heat(0)
            self.machine.set_cool(0)
            self._load_next_sample(orders, snapshot)
            sleep(0.5)
            return

        order = self._find_local_order(orders, snapshot, fragment_id)
        if not order or _order_fragment_remaining(order, fragment_id, snapshot) <= 0:
            # Nothing local needs this fragment forged right now -- pass through unchanged.
            self.machine.eject()
            sleep(0.5)
            return

        required_range = self.machine.required_range()
        required_materials = self.machine.required_materials() or {}
        if not required_range:
            self.console.debug(f"[{self.name}] No recipe selected despite a loaded fragment -- ejecting.")
            self.machine.eject()
            sleep(0.5)
            return

        materials_ready = all(
            (self.machine.materials() or {}).get(m, 0) >= qty
            for m, qty in required_materials.items()
        )
        self._drive_temperature(required_range)
        if not materials_ready:
            self._load_materials(required_materials, outpost)
            sleep(0.5)
            return

        temp = self.machine.temperature()
        low, high = required_range
        if low <= temp <= high:
            cast_res = self.machine.cast()
            if cast_res.status == "ok":
                self.console.print(f"[{self.name}] Cast {fragment_id} at {temp:.1f}C.")
            elif cast_res.status != "busy":
                self.console.debug(f"[{self.name}] cast() -> {cast_res.status}: {cast_res.message}")
        sleep(0.5)

    def run(self):
        self.console.print(f"Bio Caster ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
