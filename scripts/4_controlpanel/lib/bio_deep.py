# Deep biome processor: Bio Conditioner QC automation.
# See docs/components/bio_conditioner.md. Sample loading, heartbeat and run loop come
# from bio_processor.py's BioProcessorController.
#
# The rulebook below is not documented by the in-game API (only vague combo hints
# like "brightness reads glow"). It was recovered from the decompiled game client
# (internals/terraform_decompiled/simworker/deobfuscated.js, the $q predicate table)
# and cross-checked against real accept()/reject() outcomes logged to
# archive["bio.conditioner_observations"] during the prior diagnostic-only phase
# (every observed green/red light matched these predicates). See
# docs/AI_CHEATSHEET.md#1g for the rule summary and provenance note.
from archive import archive
from bio_processor import BioProcessorController, STACK_RAW, STACK_FINISHED
from tree_console import flush_all
from swallow import swallowed

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


class BioConditionerController(BioProcessorController):
    """
    Loads a raw local Deep sample the pipeline needs and drives its 5-stage QC run
    to completion automatically: each stage's quizzed property is looked up in
    CONDITIONER_RULEBOOK against the full report() and accept()/reject()'d
    accordingly. Every decision and its outcome is still recorded to
    archive["bio.conditioner_observations"] for auditing.
    """
    TYPE_ID = "bio_conditioner"
    MODULE = "bio_deep"
    DISPLAY_NAME = "Bio Conditioner"
    ONLINE_SUFFIX = " -- automated QC via recovered rulebook"
    LOADED_SUFFIX = ", QC run started."  # load() also starts a fresh 5-stage run
    FINISHED_LABEL = "already-conditioned"

    def _chamber_empty(self):
        return self.machine.fragment() is None

    def _classify_stack(self, stack, orders):
        """Conditioned samples carry {'conditioned': True} (confirmed live) and belong
        to the Exchange for delivery, never back in the chamber."""
        properties = self._stack_properties(stack)
        if properties and properties.get("conditioned"):
            return STACK_FINISHED, properties
        return STACK_RAW, properties

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
        except Exception as error:
            swallowed("bio_deep.BioConditionerController._record_observation: history.append", error)

    def _run_qc_stage(self):
        """Looks up the current stage's quizzed property in CONDITIONER_RULEBOOK
        against the full report() and calls accept()/reject() accordingly. See
        module docstring for the rulebook's provenance."""
        self.log.trace(f"[{self.name}] _run_qc_stage: entry")
        fragment_id = self.machine.fragment()
        stage = self.machine.stage()
        current = self.machine.current()
        report = self.machine.report() or {}
        lights = self.machine.lights()
        prop_value = report.get(current) if current else None
        self.log.debug(
            f"[{self.name}] fragment={fragment_id} stage={stage} current={current} "
            f"value={prop_value} report={report} lights={lights}"
        )

        rule = CONDITIONER_RULEBOOK.get(current)
        if rule is None:
            # Every quizzed property should be one of the 10 known ids; an
            # unrecognized one means the rulebook is stale -- don't guess blind.
            self.log.print(f"[{self.name}] WARNING: unrecognized QC property '{current}', halting to avoid a blind guess.")
            flush_all()
            sleep(1.0)
            return

        self.log.start(f"[{self.name}] QC stage {stage}: {current}")
        passed = rule(report)
        decision = "accept" if passed else "reject"
        self.log.debug(f"[{self.name}] QC quiz: property='{current}' value={prop_value} rulebook_predicate_passed={passed} -> decision={decision}()")
        action_res = self.machine.accept() if decision == "accept" else self.machine.reject()
        self._record_observation(fragment_id, stage, current, prop_value, decision, action_res.status)
        self.log.print(f"[{self.name}] {decision}() at stage {stage} ({current}={prop_value}) -> {action_res.status}.")
        if action_res.status == "burned":
            self.log.print(f"[{self.name}] WARNING: specimen burned -- rulebook may be wrong for '{current}'.")
        elif action_res.status == "conditioned":
            self.log.print(f"[{self.name}] Conditioned {fragment_id} successfully.")
        self.log.trace(f"[{self.name}] _run_qc_stage: exit, result={action_res.status}")
        self.log.end(f"[{self.name}] Stage {stage} {decision}ed -> {action_res.status}")

    def step(self):
        _, _, orders, snapshot = self._begin_step()
        self.log.trace(f"[{self.name}] step: entry, {len(orders)} order(s) fetched, is_running={self.machine.is_running()}")

        if self.machine.is_running():
            self._run_qc_stage()
            return

        if self.machine.fragment() is not None:
            # stage()==0 with a fragment still present means a run just resolved but
            # the result hasn't drained, or something's stuck -- eject rather than
            # ever calling load()/accept()/reject() blind.
            self.log.debug(f"[{self.name}] Fragment present with no active run -- ejecting.")
            self.machine.eject()
            self._idle()
            return

        self._load_next_sample(orders, snapshot)
        self._idle()
