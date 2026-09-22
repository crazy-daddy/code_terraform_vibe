# Geothermal biome processor: DNA Sequencer gene-splicing.
# See docs/components/dna_sequencer.md. Imports its shared pipeline helpers from
# bio.py -- see that module's own header comment for why the split exists.
from bio import get_my_biome, local_sibling, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining
from storage import best_unload_target, drain_port_to_storage
from version_guard import validate_game_version
from tree_console import TreeConsole


class DnaSequencerController:
    """
    Splices a raw Geothermal sample's genes to match the local Bio Exchange's active
    order (BioOrder.required_genes[fragment_id]), docs/components/dna_sequencer.md.
    A sample whose fragment doesn't need splicing (no active local order requiring
    it) is passed through unchanged via discard(). "One splice per fragment" per the
    docs -- an already-spliced chamber fragment is never spliced again, just left to
    flow to output/delivery.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "dna_sequencer")
        self.comms = get_component("comms")
        self.log = TreeConsole(module="bio_geothermal")
        self._gene_catalog = None  # fixed hardware, read once

    def _known_genes(self):
        if self._gene_catalog is None:
            try:
                self._gene_catalog = set(self.machine.gene_catalog() or [])
            except Exception:
                self._gene_catalog = set()
        return self._gene_catalog

    def _find_local_order(self, orders, snapshot, fragment_id=None):
        """Delegates to bio.py's _focus_local_order() -- shared with
        BioCollectorController's own harvest preference, mirroring
        BioLuminizerController's _find_coastal_order()."""
        my_biome = get_my_biome(self.machine)
        return _focus_local_order(orders, snapshot, my_biome, fragment_id)

    def _notify_heartbeat(self):
        """Broadcasts once every step() cycle regardless of outcome -- see
        BioLabController._wait_for_processor()'s docstring for why this must be
        unconditional, not just fired on a successful load."""
        if not self.comms:
            return
        try:
            self.comms.broadcast("biome_processor_heartbeat", {"chamber_empty": self.machine.chamber is None})
        except Exception:
            pass

    def _target_genes_for(self, orders, snapshot, fragment_id):
        order = self._find_local_order(orders, snapshot, fragment_id)
        if not order:
            return None
        required_genes = getattr(order, "required_genes", None) or {}
        return required_genes.get(fragment_id)

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
        self.log.trace(f"[{self.name}] _load_next_sample: entry")

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
            properties = getattr(stack, "properties", None) or {}
            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_local_order(orders, snapshot, staged_id)
            remaining = _order_fragment_remaining(order, staged_id, snapshot) if order else 0
            self.log.debug(f"[{self.name}] Staged raw candidate {staged_id}: focus_order={getattr(order, 'id', None)} remaining_needed={remaining}")
            if order and remaining > 0:
                load_res = self.machine.load(staged_id, properties, "exact")
                if load_res.status == "ok":
                    self.log.print(f"[{self.name}] Loaded already-staged {staged_id} into chamber.")
                else:
                    self.log.debug(f"[{self.name}] load({staged_id}) -> {load_res.status}: {getattr(load_res, 'message', '')}")
                return
            try:
                count = self.machine.input.count()
                destination = best_unload_target(staged_id, count, outpost=outpost)
                self.machine.input.eject(destination, staged_id, count, properties, "exact")
                self.log.debug(f"[{self.name}] Recovered stale staged {staged_id} to '{destination}' (no longer needed).")
            except Exception:
                pass
            return

        if staged_stacks:
            self.log.trace(f"[{self.name}] _load_next_sample: exit, {len(staged_stacks)} stack(s) already staged -- nothing to do this cycle.")
            return

        order = self._find_local_order(orders, snapshot)
        if not order:
            self.log.trace(f"[{self.name}] _load_next_sample: exit, no local order to focus on.")
            return

        for fragment_id in (order.requires or {}).keys():
            remaining = _order_fragment_remaining(order, fragment_id, snapshot)
            if remaining <= 0:
                self.log.debug(f"[{self.name}] {order.id} fragment {fragment_id}: remaining={remaining} -- already covered, skipping.")
                continue
            found = self._find_raw_stack(fragment_id, outpost)
            if not found:
                self.log.debug(f"[{self.name}] {order.id} still needs {remaining}x {fragment_id}, but no raw stack found locally.")
                continue
            source_id, properties, count = found
            self.log.debug(f"[{self.name}] Pulling raw {fragment_id} (remaining={remaining}, found {count} at '{source_id}') for {order.id}.")
            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                self.log.debug(f"[{self.name}] take({fragment_id}) from '{source_id}' -> {take_res.status}: {getattr(take_res, 'message', '')}")
                continue
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                self.log.print(f"[{self.name}] Loaded {fragment_id} into chamber.")
            else:
                self.log.debug(f"[{self.name}] load({fragment_id}) -> {load_res.status}: {getattr(load_res, 'message', '')}")
            return
        self.log.trace(f"[{self.name}] _load_next_sample: exit, no fragment of {order.id} both needed and locally available as raw stock.")

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
        self.log.trace(f"[{self.name}] step: entry, {len(orders)} order(s) fetched, chamber_empty={self.machine.chamber is None}")

        chamber = self.machine.chamber
        if chamber is None:
            self._load_next_sample(orders, snapshot)
            sleep(0.5)
            return

        if chamber.spliced:
            # Already spliced by an earlier cycle -- "One splice per fragment" per
            # docs/components/dna_sequencer.md, so just let it flow to delivery.
            self.log.debug(f"[{self.name}] {chamber.fragment_id} already spliced -- discarding to flow toward delivery.")
            self.machine.discard()
            sleep(0.5)
            return

        target_genes = self._target_genes_for(orders, snapshot, chamber.fragment_id)
        if not target_genes:
            # No local order needs this fragment spliced right now -- pass through unchanged.
            self.log.debug(f"[{self.name}] No local order requires {chamber.fragment_id} spliced right now -- discarding unchanged.")
            self.machine.discard()
            sleep(0.5)
            return

        known = self._known_genes()
        unknown = [g for g in target_genes if known and g not in known]
        self.log.debug(f"[{self.name}] Target genes for {chamber.fragment_id}: {target_genes}, recognized_catalog_size={len(known)}, unrecognized={unknown}")
        if unknown:
            self.log.debug(f"[{self.name}] Target genes {target_genes} include unrecognized ids {unknown} -- discarding rather than risk splice().")
            self.machine.discard()
            sleep(0.5)
            return

        splice_res = self.machine.splice(target_genes)
        if splice_res.status == "ok":
            self.log.print(f"[{self.name}] Spliced {chamber.fragment_id} to genes {target_genes}.")
        elif splice_res.status == "destroyed":
            self.log.print(f"[{self.name}] WARNING: splice({target_genes}) on {chamber.fragment_id} destroyed the target.", channel="")
        elif splice_res.status != "busy":
            self.log.debug(f"[{self.name}] splice() -> {splice_res.status}: {splice_res.message}")
        sleep(0.5)

    def run(self):
        self.log.print(f"DNA Sequencer ({self.name}) online via Shared Library.")
        validate_game_version()
        while True:
            self.step()
