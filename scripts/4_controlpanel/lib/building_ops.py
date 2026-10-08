"""
Building executor: deploy, upgrade and retire jobs for machines inside outposts
(docs/plans/building_planner.md, "Shape: one executor, one decider").

Jobs live in one archive dict, JOBS_KEY {job_id: job}, written by request_*()
and stepped by step_jobs() from whoever owns the loop (the autoplay planner).
Every state is written before the game call it leads to, so a restart picks
the job up where it stopped:
  deploy   kit -> deploying -> attach -> done
           "deploying" stores the ids of that type already at the outpost; a
           restart that finds a new one adopts it instead of deploying twice.
           "attach" starts the new machine's script (scripts_sync placed it);
           with a status_key the job waits until the machine reports there.
  upgrade  kit -> upgrading -> done (computer.upgrade(), pack from Inventory)
  retire   emptying -> undeploying -> done
           with handshake=True the machine's own script empties itself
           (eject is self-only) once retire_requested() says so, then calls
           mark_retire_ready(); without it the machine is undeployed at once.
A job without its kit in Inventory waits in "kit" (sourcing is the decider's
part). Fatal refusals end in "blocked" with the status kept for the panel.

undeploy() is the one computer.undeploy() wrapper with the shared status
table; the retire flows (plants, biomass, Habitats, fleet decommission,
building swaps) use it too.
"""
from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
from components import component
from script_parking import start_script
from storage import inventory_count
from game_clock import now_tick
from outpost_mining import outpost_by_id

JOBS_KEY = "build.jobs"
# {machine_id: {"job": job_id, "state": "requested" | "ready", "tick": tick}}: retire handshake.
RETIRE_KEY = "build.retire"

# One status table for deploy(), upgrade() and undeploy() answers.
# Transient: "not right now", retried next step.
TRANSIENT_STATUSES = ("inventory_full", "cargo_present", "docked_drone", "construction_dependency",
                      "drone_station_full", "under_construction", "not_enough_power", "tier_not_ready")
# The kit or pack is not in Inventory: back to kit sourcing.
KIT_STATUSES = ("no_kit", "item_not_in_inventory")
# The machine is gone already: an undeploy has nothing left to do.
GONE_STATUSES = ("not_found",)

ACTIVE_STATES = ("kit", "deploying", "attach", "upgrading", "emptying", "undeploying")
DONE_KEEP_TICKS = 36000  # done and blocked jobs stay visible for an hour, then go

log = TreeConsole(module="building_ops")


def classify(status):
    """"ok", "gone", "transient", "kit" or "fatal" for a game status string."""
    if status == "ok":
        return "ok"
    if status in GONE_STATUSES:
        return "gone"
    if status in TRANSIENT_STATUSES:
        return "transient"
    if status in KIT_STATUSES:
        return "kit"
    return "fatal"


def undeploy(machine_id, logger: "TreeConsole | None" = None, warned=None, computer=None, tag=""):
    """
    computer.undeploy(machine_id). Returns its status ("ok", "not_found", a
    refusal), "error" when the call raised, "no_computer" without one.
    Transient refusals log at debug; any other refusal warns once per machine
    and status while `warned` ({machine_id: status}) remembers it.
    """
    logger = logger or log
    computer = computer or component("computer")
    if computer is None:
        return "no_computer"
    try:
        res = computer.undeploy(machine_id)
    except Exception as error:
        swallowed("building_ops.undeploy: computer.undeploy", error)
        return "error"
    status = getattr(res, "status", "") or "?"
    if classify(status) in ("ok", "gone"):
        if warned is not None:
            warned.pop(machine_id, None)
        return status
    level = "debug" if classify(status) == "transient" else "warn"
    if level == "debug" or warned is None or warned.get(machine_id) != status:
        if warned is not None:
            warned[machine_id] = status
        logger.level(level).print(f"{tag}[{machine_id}] undeploy -> {status}: {getattr(res, 'message', '')}")
    return status


# ---------- retire handshake (machine side) ----------

def retire_requested(machine_id):
    """True while a retire job waits for this machine to empty itself."""
    entry = archive.get_entry(RETIRE_KEY, machine_id)
    return isinstance(entry, dict) and entry.get("state") == "requested"


def mark_retire_ready(machine_id):
    """Called by the machine's own script once it is empty; the job undeploys it next step."""
    tick = now_tick("building_ops.mark_retire_ready")

    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        entry = cur.get(machine_id)
        if isinstance(entry, dict):
            entry["state"] = "ready"
            entry["tick"] = tick
        return cur
    return archive.transaction(RETIRE_KEY, {}, updater)


# ---------- requests ----------

def jobs():
    raw = archive.get(JOBS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _new_id(cur, kind):
    n = 1
    while f"{kind}_{n}" in cur:
        n += 1
    return f"{kind}_{n}"


def _request(kind, fields, same, state="kit"):
    """Adds a job in `state` unless an active one matches `same` (dict of fields; None: never).
    Returns the job id, None on a rejected write."""
    out = [None]
    tick = now_tick("building_ops._request")

    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        for job_id, job in cur.items():
            if (same is not None and isinstance(job, dict) and job.get("kind") == kind
                    and job.get("state") in ACTIVE_STATES and all(job.get(k) == v for k, v in same.items())):
                out[0] = job_id
                return cur
        job_id = _new_id(cur, kind)
        job = {"kind": kind, "state": state, "status": "", "tick": tick, "created": tick}
        job.update(fields)
        cur[job_id] = job
        out[0] = job_id
        return cur
    if not archive.transaction(JOBS_KEY, {}, updater):
        return None
    return out[0]


def request_deploy(type_id, outpost_id, requester, why, status_key=None, ref=None, kit_id=None):
    """Deploy one `type_id` at outpost_id (None = home) from kit kit_id (default: type_id). `ref` (e.g. a
    proposal id) makes the request idempotent: an active job with the same ref is returned instead.
    Without it every call is a new job."""
    fields = {"type_id": type_id, "kit": kit_id or type_id, "outpost": outpost_id, "requester": requester,
              "why": why, "status_key": status_key, "ref": ref}
    return _request("deploy", fields, {"ref": ref} if ref else None)


def request_upgrade(machine_id, item_id, requester, why):
    """Apply upgrade pack `item_id` to machine_id in place (computer.upgrade())."""
    return _request("upgrade", {"machine_id": machine_id, "item_id": item_id, "requester": requester, "why": why},
                    {"machine_id": machine_id, "item_id": item_id})


def request_retire(machine_id, requester, why, handshake=True):
    """Empty (handshake) and undeploy machine_id; one active retire job per machine."""
    state = "emptying" if handshake else "undeploying"
    job_id = _request("retire", {"machine_id": machine_id, "requester": requester, "why": why,
                                 "handshake": handshake}, {"machine_id": machine_id}, state)
    if job_id is not None and handshake:
        tick = now_tick("building_ops.request_retire")
        archive.transaction(RETIRE_KEY, {}, lambda cur: _set_retire(cur, machine_id, job_id, tick))
    return job_id


def _set_retire(cur, machine_id, job_id, tick):
    cur = cur if isinstance(cur, dict) else {}
    entry = cur.get(machine_id)
    if not isinstance(entry, dict) or entry.get("job") != job_id:
        cur[machine_id] = {"job": job_id, "state": "requested", "tick": tick}
    return cur


def _patch(job_id, **fields):
    tick = now_tick("building_ops._patch")

    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        job = cur.get(job_id)
        if isinstance(job, dict):
            job.update(fields)
            job["tick"] = tick
        return cur
    return archive.transaction(JOBS_KEY, {}, updater)


def _prune(now):
    """Drops done and blocked jobs older than DONE_KEEP_TICKS and handshake entries of finished jobs."""
    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        return {k: j for k, j in cur.items()
                if isinstance(j, dict) and (j.get("state") in ACTIVE_STATES or now - (j.get("tick") or 0) < DONE_KEEP_TICKS)}
    archive.transaction(JOBS_KEY, {}, updater)
    live = {j.get("machine_id") for j in jobs().values() if j.get("kind") == "retire" and j.get("state") in ACTIVE_STATES}
    stale = [m for m in (archive.get(RETIRE_KEY, {}) or {}) if m not in live]
    for machine_id in stale:
        archive.pop_entry(RETIRE_KEY, machine_id)


# ---------- executor ----------

def _ids_at(type_id, outpost_id):
    """Ids of the `type_id` buildings at the outpost (None = home); None when unreadable."""
    if outpost_id is None:
        network = component("outpost_network")
        try:
            outpost = network.home() if network else None
        except Exception as error:
            swallowed("building_ops._ids_at: outpost_network.home", error)
            outpost = None
    else:
        outpost = outpost_by_id(outpost_id)
    if outpost is None:
        return None
    try:
        return sorted(b.id for b in outpost.buildings(type_id))
    except Exception as error:
        swallowed("building_ops._ids_at: outpost.buildings", error)
        return None


class BuildingOps:
    """Steps every active job once per call; see module header."""

    def __init__(self, logger: "TreeConsole | None" = None):
        self.log = logger or log
        self.warned = {}

    def step_jobs(self):
        """One pass over every active job. Returns one summary line per job that is not done."""
        notes = []
        for job_id, job in sorted(jobs().items()):
            if not isinstance(job, dict) or job.get("state") not in ACTIVE_STATES:
                continue
            kind = job.get("kind")
            if kind == "deploy":
                note = self._step_deploy(job_id, job)
            elif kind == "upgrade":
                note = self._step_upgrade(job_id, job)
            elif kind == "retire":
                note = self._step_retire(job_id, job)
            else:
                _patch(job_id, state="blocked", status="unknown_kind")
                note = f"{job_id}: unknown kind {kind}"
            if note:
                notes.append(note)
        _prune(now_tick("building_ops.step_jobs"))
        return notes

    def _block(self, job_id, job, status):
        _patch(job_id, state="blocked", status=status)
        self.log.level("warn").print(f"[build] {job_id} ({job.get('kind')} {job.get('type_id') or job.get('machine_id')}"
                                     f" for {job.get('requester')}): {status}; blocked.")
        return f"{job_id}: blocked ({status})"

    def _step_deploy(self, job_id, job):
        type_id, outpost_id = job.get("type_id"), job.get("outpost")
        kit = job.get("kit") or type_id
        where = outpost_id or "home"
        state = job.get("state")
        if state == "kit":
            if inventory_count(kit) <= 0:
                if job.get("status") != "no_kit":
                    _patch(job_id, status="no_kit")
                return f"{job_id}: waiting for a {kit} kit"
            known = _ids_at(type_id, outpost_id)
            if known is None:
                return f"{job_id}: {where} unreadable"
            _patch(job_id, state="deploying", known=known, status="")
            job = dict(job, state="deploying", known=known)
            state = "deploying"
        if state == "deploying":
            now = _ids_at(type_id, outpost_id)
            if now is None:
                return f"{job_id}: {where} unreadable"
            new_id = next((m for m in now if m not in (job.get("known") or [])), None)
            if new_id is None:
                computer = component("computer")
                if computer is None:
                    return f"{job_id}: no Ship Computer"
                try:
                    res = computer.deploy(kit, outpost_id)
                except Exception as error:
                    swallowed("building_ops._step_deploy: computer.deploy", error)
                    return f"{job_id}: deploy error"
                status = getattr(res, "status", "") or "?"
                verdict = classify(status)
                if verdict == "kit":
                    _patch(job_id, state="kit", status=status)
                    return f"{job_id}: {status}"
                if verdict == "transient":
                    _patch(job_id, status=status)
                    return f"{job_id}: deploy {status}"
                if verdict != "ok":
                    return self._block(job_id, job, status)
                new_id = getattr(res, "machine_id", None)
            _patch(job_id, state="attach", machine_id=new_id, status="")
            self.log.print(f"[build] {job_id}: deployed {new_id} at {where} for {job.get('requester')} ({job.get('why')}).")
            return f"{job_id}: deployed {new_id}"
        machine_id = job.get("machine_id")
        status_key = job.get("status_key")
        if status_key and isinstance(archive.get_entry(status_key, machine_id), dict):
            _patch(job_id, state="done", status="ok")
            return None
        started = start_script(machine_id)
        if started != "ok":
            _patch(job_id, status=f"script {started}")
            return f"{job_id}: waiting for a script on {machine_id} (run scripts_sync)"
        if status_key:
            return f"{job_id}: {machine_id} started, waiting for its {status_key} entry"
        _patch(job_id, state="done", status="ok")
        return None

    def _step_upgrade(self, job_id, job):
        machine_id, item_id = job.get("machine_id"), job.get("item_id")
        if job.get("state") == "kit":
            if inventory_count(item_id) <= 0:
                if job.get("status") != "no_kit":
                    _patch(job_id, status="no_kit")
                return f"{job_id}: waiting for {item_id}"
            _patch(job_id, state="upgrading", status="")
        computer = component("computer")
        if computer is None:
            return f"{job_id}: no Ship Computer"
        try:
            res = computer.upgrade(item_id, machine_id)
        except Exception as error:
            swallowed("building_ops._step_upgrade: computer.upgrade", error)
            return f"{job_id}: upgrade error"
        status = getattr(res, "status", "") or "?"
        verdict = classify(status)
        if verdict == "ok":
            _patch(job_id, state="done", status="ok")
            self.log.print(f"[build] {job_id}: {machine_id} upgraded with {item_id} for {job.get('requester')}.")
            return None
        if verdict == "kit":
            _patch(job_id, state="kit", status=status)
            return f"{job_id}: {status}"
        if verdict == "transient":
            _patch(job_id, status=status)
            return f"{job_id}: upgrade {status}"
        return self._block(job_id, job, status)

    def _step_retire(self, job_id, job):
        machine_id = job.get("machine_id")
        if job.get("state") == "emptying":
            entry = archive.get_entry(RETIRE_KEY, machine_id)
            if not isinstance(entry, dict) or entry.get("state") != "ready":
                if not isinstance(entry, dict):
                    tick = now_tick("building_ops._step_retire")
                    archive.transaction(RETIRE_KEY, {}, lambda cur: _set_retire(cur, machine_id, job_id, tick))
                start_script(machine_id)  # an ended script can't empty the machine
                return f"{job_id}: {machine_id} emptying"
            _patch(job_id, state="undeploying")
        status = undeploy(machine_id, self.log, self.warned, tag="[build] ")
        verdict = classify(status)
        if verdict in ("ok", "gone"):
            _patch(job_id, state="done", status=status)
            archive.pop_entry(RETIRE_KEY, machine_id)
            if verdict == "ok":
                self.log.print(f"[build] {job_id}: {machine_id} undeployed for {job.get('requester')} ({job.get('why')}); kit in Inventory.")
            return None
        if verdict == "transient" or status in ("error", "no_computer"):
            _patch(job_id, status=status)
            return f"{job_id}: undeploy {status}"
        return self._block(job_id, job, status)
