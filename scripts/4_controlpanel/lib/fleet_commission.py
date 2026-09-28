# Fleet commissioning coordinator: launches new Pioneers queued on the
# COMMISSION card (control_panel/fleet_commission_panel.py). Run by the headless
# automation_panel.py every storage tick. Operator-triggered only: nothing is
# queued here on its own.
#
# One job at a time, head of fleet.commission["jobs"] (layout in
# lib/pioneer_commission.py). Each pass re-reads the dict, advances the head
# job at most one state and writes back, so a restart resumes where it stopped.
#
#   queued    -> spec built from the role preset at the best unlocked tiers
#                (Shop catalogue); a locked part blocks the job
#   buying    -> buys the chassis and every part the Inventory doesn't already
#                hold, all at once, only while credits stay above
#                WAREHOUSE_UPGRADE_CREDIT_RESERVE afterwards
#   deploying -> snapshot of owned Pioneers first (a restart adopts a new one
#                instead of deploying twice), then computer.deploy("pioneer")
#   attach    -> a deployed machine has no script and scripts cannot attach
#                one: waits for devtools/scripts_sync.py (or the operator) to
#                fill the slot, retrying run_control.start() until the
#                Pioneer reports in fleet.status
#   fitting   -> the Pioneer mounts/installs its own parts
#                (PioneerFittingMixin); parts it reports missing are bought
#   blocked   -> refused for good (locked part, deploy_limit, vehicle gone);
#                skipped by later passes until the operator cancels it on the
#                card. Bought parts stay in Inventory and are reused by the
#                next job.

import fleet_status
from pioneer_commission import PIONEER_KIT_ID, commission_state, update_commission, build_spec, spec_parts
from warehouse_upgrade import WAREHOUSE_UPGRADE_CREDIT_RESERVE
from tree_console import TreeConsole
from swallow import swallowed

# States the COMMISSION card may cancel: nothing deployed yet (or given up).
CANCELLABLE_STATES = ("queued", "buying", "blocked")
DEPLOY_BLOCKING_STATUSES = ("deploy_limit", "location_not_found", "not_deployable", "locked", "wrong_biome_for_machine")


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception as error:
        swallowed("fleet_commission._component: get_component", error)
        return None


def queue_pioneer(role, outpost_id=None):
    """Appends a Pioneer job (COMMISSION card button). Returns the job id."""
    created = []

    def mutate(state):
        seq = int(state.get("seq", 0)) + 1
        state["seq"] = seq
        created[:] = [f"p{seq}"]
        state.setdefault("jobs", []).append({"id": created[0], "role": role, "outpost": outpost_id, "state": "queued"})
    update_commission(mutate)
    return created[0] if created else ""


def cancel_job(job_id):
    """Drops a job that hasn't deployed anything (CANCELLABLE_STATES). Returns True if dropped."""
    dropped = []

    def mutate(state):
        jobs = state.get("jobs") or []
        keep = [j for j in jobs if not (j.get("id") == job_id and j.get("state") in CANCELLABLE_STATES)]
        dropped[:] = [len(keep) != len(jobs)]
        state["jobs"] = keep
    update_commission(mutate)
    return bool(dropped and dropped[0])


class FleetCommissionCoordinator:
    """Host-side state machine for new Pioneers. One instance, reused across cycles."""

    def __init__(self):
        self.log = TreeConsole(module="fleet_commission")

    # ------------------------------------------------------------ lookups

    def _catalogue(self):
        shop = _component("shop")
        try:
            return {entry.id: entry.cost for entry in shop.get_catalogue()} if shop else {}
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._catalogue: shop.get_catalogue", error)
            return {}

    def _credits(self):
        commander = _component("commander")
        try:
            return int(commander.get_credits()) if commander else 0
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._credits: commander.get_credits", error)
            return 0

    def _inventory_count(self, item_id):
        inventory = _component("inventory")
        try:
            return int(inventory.count(item_id) or 0) if inventory else 0
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._inventory_count: inventory.count", error)
            return 0

    def _pioneers(self):
        """Sorted ids of every owned Pioneer, or None when the fleet can't be read."""
        fleet = _component("fleet")
        if not fleet:
            return None
        try:
            return sorted(getattr(v, "id", "") for v in fleet.vehicles() if getattr(v, "kind", "") == "pioneer" and getattr(v, "id", ""))
        except Exception as error:
            swallowed("fleet_commission.FleetCommissionCoordinator._pioneers: fleet.vehicles", error)
            return None

    def _start_script(self, machine_id):
        """run_control.start(), treating already_running as success. Returns the status."""
        run = _component("run_control")
        if not run:
            return "no_run_control"
        try:
            res = run.start(machine_id)
        except Exception as e:
            swallowed("fleet_commission.FleetCommissionCoordinator._start_script: run.start", e)
            return f"error: {e}"
        return "ok" if res.status in ("ok", "already_running") else res.status

    def _patch(self, job_id, **fields):
        def mutate(state):
            for job in state.get("jobs") or []:
                if job.get("id") == job_id:
                    job.update(fields)
        update_commission(mutate)

    def _set_status(self, text):
        if commission_state().get("status") != text:
            update_commission(lambda s: s.update({"status": text}))

    def _block(self, job, reason):
        self._patch(job["id"], state="blocked", reason=reason)
        self.log.level("warn").print(f"[fleet_commission] {job['id']} ({job.get('role')}) blocked: {reason}. Cancel it on the COMMISSION card.")
        return f"{job['id']} blocked ({reason})"

    def _buy_missing(self, parts, catalogue, label):
        """
        Buys whatever of parts {item_id: n} the Inventory lacks, all or nothing
        against the credit reserve. Returns None once everything is in
        Inventory, else a short waiting reason.
        """
        needed = {item: n - self._inventory_count(item) for item, n in parts.items()}
        needed = {item: n for item, n in needed.items() if n > 0}
        if not needed:
            return None
        unpriced = [item for item in needed if item not in catalogue]
        if unpriced:
            return f"{label}: not in Shop {unpriced}"
        cost = sum(catalogue[item] * n for item, n in needed.items())
        credits = self._credits()
        if credits - cost < WAREHOUSE_UPGRADE_CREDIT_RESERVE:
            self.log.debug(f"[fleet_commission] {label}: needs {cost}cr for {needed}, have {credits}cr, reserve {WAREHOUSE_UPGRADE_CREDIT_RESERVE}cr.")
            return f"{label}: waiting for credits ({cost}cr + {WAREHOUSE_UPGRADE_CREDIT_RESERVE}cr reserve)"
        shop = _component("shop")
        if not shop:
            return f"{label}: no Shop"
        for item, n in needed.items():
            res = shop.buy(item, n)
            self.log.debug(f"[fleet_commission] {label}: buy('{item}', {n}) -> {res.status}")
            if res.status != "ok":
                return f"{label}: buy {item} {res.status}"
        self.log.print(f"[fleet_commission] {label}: bought {needed} for {cost}cr.")
        return None

    # ------------------------------------------------------------ main step

    def step(self, current_tick):
        """One coordinator pass. Returns a short summary for automation_panel's automation line."""
        state = commission_state()
        pioneers = self._pioneers()
        self._prune(state, pioneers)
        jobs = [j for j in (commission_state().get("jobs") or []) if isinstance(j, dict)]
        if not jobs:
            self._set_status("idle")
            return "commission idle"
        # Blocked jobs wait for the operator's cancel; the next one goes on.
        job = next((j for j in jobs if j.get("state") != "blocked"), None)
        blocked = sum(1 for j in jobs if j.get("state") == "blocked")
        queued = sum(1 for j in jobs if j is not job and j.get("state") != "blocked")
        text = self._advance(job, pioneers) if job else "nothing to do"
        extras = [f"+{queued} queued"] if queued else []
        extras += [f"{blocked} blocked"] if blocked else []
        text = f"{text} ({', '.join(extras)})" if extras else text
        self._set_status(text)
        return f"commission: {text}"

    def _advance(self, job, pioneers):
        job_id, role, outpost_id, state = job["id"], job.get("role"), job.get("outpost"), job.get("state")
        label = f"{job_id} {role}"
        self.log.debug(f"[fleet_commission] {label}: state '{state}'.")

        if state == "queued":
            spec, reason = build_spec(role, self._catalogue())
            if spec is None:
                return self._block(job, reason)
            self._patch(job_id, state="buying", spec=spec)
            self.log.print(f"[fleet_commission] {label} at '{outpost_id or 'home'}': {spec['modules']}, bays {spec['battery_fill']}/{spec['bin_fill']}.")
            return f"{label}: buying"

        spec = job.get("spec") or {}
        if state == "buying":
            parts = spec_parts(spec)
            parts[PIONEER_KIT_ID] = parts.get(PIONEER_KIT_ID, 0) + 1
            waiting = self._buy_missing(parts, self._catalogue(), label)
            if waiting:
                return waiting
            if pioneers is None:
                return f"{label}: fleet unreadable"
            self._patch(job_id, state="deploying", known=pioneers)
            return f"{label}: deploying"

        if state == "deploying":
            if pioneers is None:
                return f"{label}: fleet unreadable"
            known = set(job.get("known") or [])
            new_id = next((p for p in pioneers if p not in known), None)
            if new_id is None:
                computer = _component("computer")
                if not computer or not hasattr(computer, "deploy"):
                    return f"{label}: no Ship Computer"
                res = computer.deploy(PIONEER_KIT_ID, outpost_id)
                if res.status != "ok":
                    if res.status in DEPLOY_BLOCKING_STATUSES:
                        return self._block(job, f"deploy {res.status}")
                    if res.status == "no_kit":
                        self._patch(job_id, state="buying")
                    self.log.debug(f"[fleet_commission] {label}: deploy -> {res.status} - {res.message}")
                    return f"{label}: deploy {res.status}"
                new_id = res.machine_id
            lineage = {"role": role, "job": job_id, "spec": spec, "fitted": False, "missing": {}}

            def mutate(s):
                for j in s.get("jobs") or []:
                    if j.get("id") == job_id:
                        j.update({"state": "attach", "new_id": new_id})
                s.setdefault("lineage", {})[new_id] = lineage
            update_commission(mutate)
            self.log.print(f"[fleet_commission] {label}: deployed '{new_id}' at '{outpost_id or 'home'}'; waiting for its script.")
            return f"{label}: deployed {new_id}"

        new_id = job.get("new_id")
        if state == "attach":
            fitted = ((commission_state().get("lineage") or {}).get(new_id) or {}).get("fitted")
            if fitted or fleet_status.get(new_id) is not None:
                self._patch(job_id, state="fitting")
                return f"{label}: {new_id} running"
            if self._start_script(new_id) != "ok":
                return f"{label}: waiting for a script on {new_id} (run scripts_sync)"
            return f"{label}: started {new_id}"

        if state == "fitting":
            entry = (commission_state().get("lineage") or {}).get(new_id) or {}
            if entry.get("fitted"):
                def finish(s):
                    s["jobs"] = [j for j in s.get("jobs") or [] if j.get("id") != job_id]
                    s.get("lineage", {}).pop(new_id, None)
                update_commission(finish)
                self.log.print(f"[fleet_commission] {label}: '{new_id}' fitted and running.")
                return f"{label}: {new_id} done"
            missing = entry.get("missing") or {}
            if missing:
                waiting = self._buy_missing(missing, self._catalogue(), f"{label} refit")
                if waiting:
                    return waiting
            status = fleet_status.get(new_id) or {}
            return f"{label}: {new_id} fitting ({status.get('target') or status.get('state', '?')})"

        return f"{label}: unknown state {state!r}"

    # ------------------------------------------------------------ pruning

    def _prune(self, state, pioneers):
        """Blocks jobs whose deployed Pioneer vanished and drops orphan lineage. Skipped when the fleet can't be read."""
        if pioneers is None:
            return
        alive = set(pioneers)
        gone_jobs = [j.get("id") for j in state.get("jobs") or []
                     if isinstance(j, dict) and j.get("state") in ("attach", "fitting") and j.get("new_id") not in alive]
        job_ids = {j.get("id") for j in state.get("jobs") or [] if isinstance(j, dict)}
        orphans = [k for k, e in (state.get("lineage") or {}).items()
                   if k not in alive or not isinstance(e, dict) or e.get("job") not in job_ids]
        if not gone_jobs and not orphans:
            return

        def mutate(s):
            for j in s.get("jobs") or []:
                if j.get("id") in gone_jobs:
                    j.update({"state": "blocked", "reason": "vehicle gone"})
            for k in orphans:
                s.get("lineage", {}).pop(k, None)
        update_commission(mutate)
        self.log.debug(f"[fleet_commission] Pruned: jobs blocked {gone_jobs}, lineage dropped {orphans}.")
