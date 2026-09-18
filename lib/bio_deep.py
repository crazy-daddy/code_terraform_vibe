# Deep biome processor: Bio Conditioner QC automation.
# See docs/components/bio_conditioner.md. Imports its shared pipeline helpers from
# bio.py -- see that module's own header comment for why the split exists.
#
# The rulebook below is not documented by the in-game API (only vague combo hints
# like "brightness reads glow"). It was recovered from the decompiled game client
# (internals/terraform_decompiled/simworker/deobfuscated.js, the $q predicate table)
# and cross-checked against real accept()/reject() outcomes logged to
# archive["bio.conditioner_observations"] during the prior diagnostic-only phase
# (every observed green/red light matched these predicates). See
# docs/AI_CHEATSHEET.md#1g for the rule summary and provenance note.
from archive import archive
from bio import get_my_biome, local_sibling, _local_sources, _local_stock_snapshot, _focus_local_order, _order_fragment_remaining
from storage import best_unload_target, drain_port_to_storage
from version_guard import validate_game_version
from tree_console import TreeConsole

# Bounded history length for bio.conditioner_observations, per the Data Archive
# rule (fixed-size histories, never unbounded logs) -- see docs/AI_CHEATSHEET.md.
CONDITIONER_OBSERVATION_HISTORY_LIMIT = 200

# Pass/fail predicate for each of the 10 QC properties, each given the full
# report() dict since some rules read a sibling property (brightness reads glow,
# weight reads gunk, sound reads cracks) -- see module docstring for provenance.
CONDITIONER_RULEBOOK = {
    "glow": lambda r: r.get("glow") in ("blue", "green", "purple"),
    "brightness": lambda r: (
        45 <= r.get("brightness", -1) <= 80 if r.get("glow") in ("blue", "green")
        else 20 <= r.get("brightness", -1) <= 50 if r.get("glow") == "purple"
        else False
    ),
    "smell": lambda r: r.get("smell") in ("salty", "fishy"),
    "gunk": lambda r: 70 <= r.get("gunk", -1) <= 85,
    "cracks": lambda r: r.get("cracks") in ("none", "small"),
    "feel": lambda r: r.get("feel") == "hard",
    "twitch": lambda r: r.get("twitch") in ("weak", "still"),
    "bugs": lambda r: 1 <= r.get("bugs", -1) <= 3,
    "weight": lambda r: 180 <= r.get("weight", -1) <= (300 if r.get("gunk", 0) >= 70 else 260),
    "sound": lambda r: (
        True if r.get("sound") == "ding"
        else r.get("cracks") in ("none", "small") if r.get("sound") == "thud"
        else False
    ),
}


class BioConditionerController:
    """
    Loads a raw local Deep sample the pipeline needs and drives its 5-stage QC run
    to completion automatically: each stage's quizzed property is looked up in
    CONDITIONER_RULEBOOK against the full report() and accept()/reject()'d
    accordingly. Every decision and its outcome is still recorded to
    archive["bio.conditioner_observations"] for auditing.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_conditioner")
        self.comms = get_component("comms")
        self.console = TreeConsole()

    def _find_local_order(self, orders, snapshot, fragment_id=None):
        """Delegates to bio.py's _focus_local_order() -- shared with
        BioCollectorController's own harvest preference, mirroring
        BioLuminizerController's _find_coastal_order()."""
        my_biome = get_my_biome(self.machine)
        return _focus_local_order(orders, snapshot, my_biome, fragment_id)

    def _notify_heartbeat(self):
        """Broadcasts once every step() cycle regardless of outcome -- see
        BioLabController._wait_for_processor()'s docstring for why this must be
        unconditional, not just fired when a run resolves."""
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
                properties = getattr(stack, "properties", None)
                if properties and properties.get("conditioned"):
                    # Already-conditioned samples carry {'conditioned': True} in
                    # .properties (confirmed live) -- never treat one as raw QC
                    # input, it belongs to the Exchange for delivery.
                    continue
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
            properties = getattr(stack, "properties", None)
            if properties and properties.get("conditioned"):
                # Already-conditioned (confirmed live: {'conditioned': True}) --
                # never reload it into the chamber, recover it to storage for the
                # Exchange to pick up instead. Mirrors the Luminizer's equivalent
                # already-tinted-sample fix.
                try:
                    destination = best_unload_target(staged_id, count, outpost=outpost)
                    self.machine.input.eject(destination, staged_id, count, properties, "exact")
                    self.console.debug(f"[{self.name}] Recovered already-conditioned {staged_id} to '{destination}'.")
                except Exception:
                    pass
                continue
            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_local_order(orders, snapshot, staged_id)
            if order and _order_fragment_remaining(order, staged_id, snapshot) > 0:
                # load() both pulls the sample into the chamber AND starts a fresh
                # 5-stage run, per docs/components/bio_conditioner.md.
                load_res = self.machine.load(staged_id, properties, "exact")
                if load_res.status == "ok":
                    self.console.print(f"[{self.name}] Loaded {staged_id}, QC run started.")
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
            return

        order = self._find_local_order(orders, snapshot)
        if not order:
            return

        for fragment_id in (order.requires or {}).keys():
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
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                self.console.print(f"[{self.name}] Loaded {fragment_id}, QC run started.")
            return

    def _record_observation(self, fragment_id, stage, prop_name, prop_value, decision, outcome):
        entry = {
            "fragment_id": fragment_id,
            "stage": stage,
            "property": prop_name,
            "value": prop_value,
            "decision": decision,
            "outcome": outcome,
        }
        try:
            def append_bounded(history):
                history = list(history or [])
                history.append(entry)
                return history[-CONDITIONER_OBSERVATION_HISTORY_LIMIT:]
            archive.transaction("bio.conditioner_observations", [], append_bounded)
        except Exception:
            pass

    def _run_qc_stage(self):
        """Looks up the current stage's quizzed property in CONDITIONER_RULEBOOK
        against the full report() and calls accept()/reject() accordingly. See
        module docstring for the rulebook's provenance."""
        fragment_id = self.machine.fragment()
        stage = self.machine.stage()
        current = self.machine.current()
        report = self.machine.report() or {}
        lights = self.machine.lights()
        prop_value = report.get(current) if current else None
        self.console.debug(
            f"[{self.name}] fragment={fragment_id} stage={stage} current={current} "
            f"value={prop_value} report={report} lights={lights}"
        )

        rule = CONDITIONER_RULEBOOK.get(current)
        if rule is None:
            # Every quizzed property should be one of the 10 known ids; an
            # unrecognized one means the rulebook is stale -- don't guess blind.
            self.console.print(f"[{self.name}] WARNING: unrecognized QC property '{current}', halting to avoid a blind guess.")
            sleep(1.0)
            return

        decision = "accept" if rule(report) else "reject"
        action_res = self.machine.accept() if decision == "accept" else self.machine.reject()
        self._record_observation(fragment_id, stage, current, prop_value, decision, action_res.status)
        self.console.print(f"[{self.name}] {decision}() at stage {stage} ({current}={prop_value}) -> {action_res.status}.")
        if action_res.status == "burned":
            self.console.print(f"[{self.name}] WARNING: specimen burned -- rulebook may be wrong for '{current}'.")
        elif action_res.status == "conditioned":
            self.console.print(f"[{self.name}] Conditioned {fragment_id} successfully.")

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

        if self.machine.is_running():
            self._run_qc_stage()
            return

        if self.machine.fragment() is not None:
            # stage()==0 with a fragment still present means a run just resolved but
            # the result hasn't drained, or something's stuck -- eject rather than
            # ever calling load()/accept()/reject() blind.
            self.console.debug(f"[{self.name}] Fragment present with no active run -- ejecting.")
            self.machine.eject()
            sleep(0.5)
            return

        self._load_next_sample(orders, snapshot)
        sleep(0.5)

    def run(self):
        self.console.print(f"Bio Conditioner ({self.name}) online via Shared Library -- automated QC via recovered rulebook.")
        validate_game_version()
        while True:
            self.step()
