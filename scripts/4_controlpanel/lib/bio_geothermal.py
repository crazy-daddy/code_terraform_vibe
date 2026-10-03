# Geothermal biome processor: DNA Sequencer gene-splicing.
# See docs/components/dna_sequencer.md. Sample loading, heartbeat and run loop come
# from bio_processor.py's BioProcessorController.
from bio_processor import BioProcessorController
from swallow import swallowed


class DnaSequencerController(BioProcessorController):
    """
    Splices a raw Geothermal sample's genes to match the local Bio Exchange's active
    order (BioOrder.required_genes[fragment_id]), docs/components/dna_sequencer.md.
    A sample whose fragment doesn't need splicing (no active local order requiring
    it) is passed through unchanged via discard(). "One splice per fragment" per the
    docs -- an already-spliced chamber fragment is never spliced again, just left to
    flow to output/delivery.
    """
    TYPE_ID = "dna_sequencer"
    MODULE = "bio_geothermal"
    DISPLAY_NAME = "DNA Sequencer"

    def __init__(self, machine):
        BioProcessorController.__init__(self, machine)
        self._gene_catalog = None  # fixed hardware, read once

    def _known_genes(self):
        if self._gene_catalog is None:
            try:
                self._gene_catalog = set(self.machine.gene_catalog() or [])
            except Exception as error:
                swallowed("bio_geothermal.DnaSequencerController._known_genes: self.machine.gene_catalog", error)
                self._gene_catalog = set()
        return self._gene_catalog

    def _target_genes_for(self, orders, snapshot, fragment_id):
        order = self._find_local_order(orders, snapshot, fragment_id)
        if not order:
            return None
        required_genes = getattr(order, "required_genes", None) or {}
        return required_genes.get(fragment_id)

    def step(self):
        _, _, orders, snapshot = self._begin_step()
        chamber = self.machine.chamber
        self.log.trace(f"[{self.name}] step: entry, {len(orders)} order(s) fetched, chamber_empty={chamber is None}")

        if chamber is None:
            self._load_next_sample(orders, snapshot)
            self._idle()
            return

        if chamber.spliced:
            # Already spliced by an earlier cycle -- "One splice per fragment" per
            # docs/components/dna_sequencer.md, so just let it flow to delivery.
            self.log.debug(f"[{self.name}] {chamber.fragment_id} already spliced -- discarding to flow toward delivery.")
            self.machine.discard()
            self._idle()
            return

        target_genes = self._target_genes_for(orders, snapshot, chamber.fragment_id)
        if not target_genes:
            # No local order needs this fragment spliced right now -- pass through unchanged.
            self.log.debug(f"[{self.name}] No local order requires {chamber.fragment_id} spliced right now -- discarding unchanged.")
            self.machine.discard()
            self._idle()
            return

        known = self._known_genes()
        unknown = [g for g in target_genes if known and g not in known]
        self.log.debug(f"[{self.name}] Target genes for {chamber.fragment_id}: {target_genes}, recognized_catalog_size={len(known)}, unrecognized={unknown}")
        if unknown:
            self.log.debug(f"[{self.name}] Target genes {target_genes} include unrecognized ids {unknown} -- discarding rather than risk splice().")
            self.machine.discard()
            self._idle()
            return

        splice_res = self.machine.splice(target_genes)
        if splice_res.status == "ok":
            self.log.print(f"[{self.name}] Spliced {chamber.fragment_id} to genes {target_genes}.")
        elif splice_res.status == "destroyed":
            self.log.print(f"[{self.name}] WARNING: splice({target_genes}) on {chamber.fragment_id} destroyed the target.", channel="")
        elif splice_res.status != "busy":
            self.log.debug(f"[{self.name}] splice() -> {splice_res.status}: {splice_res.message}")
        self._idle()
