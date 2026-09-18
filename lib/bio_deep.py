# Deep biome processor: Bio Conditioner QC quiz -- DIAGNOSTIC ONLY.
# See docs/components/bio_conditioner.md. Imports its shared pipeline helpers from
# bio.py -- see that module's own header comment for why the split exists.
#
# The docs never expose the actual pass/fail rule for any of the 10 inspected
# properties (only vague combo hints like "brightness reads glow"), and a wrong
# accept()/reject() call burns (destroys) the whole specimen with no way to learn
# the rule risk-free from the API alone. So this controller never calls
# accept()/reject() automatically: it logs report()/current()/lights() every cycle
# and only acts on an explicit "accept" or "reject" command sent via the machine's
# Script Commands tab (docs/guide/editor_and_tools.md's "Script Commands" section),
# recording the (property, value, decision, outcome) into a bounded archive history
# so real observations accumulate across sessions toward working out the rulebook.
# Full automatic order fulfillment for Deep orders is a follow-up once that
# rulebook is known -- see TODO.md.
from archive import archive
from bio import (
    get_my_biome,
    local_sibling,
    _local_sources,
    _local_stock_snapshot,
    _focus_local_order,
    _order_fragment_remaining,
)
from storage import best_unload_target, drain_port_to_storage
from version_guard import validate_game_version
from tree_console import TreeConsole

# Bounded history length for bio.conditioner_observations, per the Data Archive
# rule (fixed-size histories, never unbounded logs) -- see docs/AI_CHEATSHEET.md.
CONDITIONER_OBSERVATION_HISTORY_LIMIT = 200


class BioConditionerController:
    """
    DIAGNOSTIC ONLY. Loads a raw local Deep sample the pipeline needs and, while its
    5-stage QC run is live, logs report()/current()/lights() every cycle without
    ever calling accept()/reject() on its own -- see module docstring for why. Only
    an explicit "accept" or "reject" Script Command from the operator resolves a
    stage; every decision and its outcome is recorded to
    archive["bio.conditioner_observations"] for later rulebook analysis.
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
            properties = getattr(stack, "properties", None) or {}
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

    def _observe_and_wait_for_command(self):
        """Logs the current QC stage's full context, then only acts on an explicit
        operator command -- never decides accept/reject on its own. See module
        docstring."""
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

        cmd_res = self.machine.next_command()
        if cmd_res.status != "ok":
            sleep(0.5)
            return
        cmd = cmd_res.command
        if cmd.name not in ("accept", "reject"):
            self.console.print(f"[{self.name}] Ignoring unrecognized command '{cmd.name}' -- send 'accept' or 'reject'.")
            sleep(0.2)
            return

        action_res = self.machine.accept() if cmd.name == "accept" else self.machine.reject()
        self._record_observation(fragment_id, stage, current, prop_value, cmd.name, action_res.status)
        self.console.print(f"[{self.name}] Operator called {cmd.name}() at stage {stage} ({current}={prop_value}) -> {action_res.status}.")
        if action_res.status == "burned":
            self.console.print(f"[{self.name}] WARNING: specimen burned.")
        sleep(0.2)

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
            self._observe_and_wait_for_command()
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
        self.console.print(f"Bio Conditioner ({self.name}) online via Shared Library -- DIAGNOSTIC MODE, no automatic accept/reject.")
        validate_game_version()
        while True:
            self.step()
