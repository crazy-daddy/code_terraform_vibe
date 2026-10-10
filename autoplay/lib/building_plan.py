# Building pass of planner_loop.run_planner() (docs/plans/building_planner.md):
# compares what each outpost's designation wants with the buildings standing
# there and turns the difference into proposals. Nothing is built until the
# operator approves a proposal on the BUILD card (autoplay/build_panel.py);
# an approved proposal becomes building_ops jobs.
#
# Providers (pure, over the outpost_needs snapshot):
#   roles      one building per group a designated role lacks
#              (autoplay_roles.role_gaps()); the first alternative whose kit
#              can be had (snapshot "kits"); the Warehouse group is left to
#              the storage provider.
#   storage    once the Warehouse kit can be had: Warehouse slots the designation stocks (stock_slots()) beyond
#              the slots standing there; ceil(deficit / per_warehouse) of
#              the kind the snapshot builds (Large Warehouse once its kit is
#              available, building_planner.md "Storage replaces the fixed 2:1
#              swap"); at least one where a designated role needs a Warehouse.
#   retire     a Refiner that published retire "ready" (refiner.status).
# Gate: the building cap. A deploy that takes an outpost over its capacity
# while it holds a penalized machine (storage.PENALIZED_TYPES) is shown
# blocked and can't be approved (founding plan §capacity).
#
# Archive autoplay.build_proposals {proposal_id: entry}, rewritten only on change:
#   kind      "deploy" | "retire"
#   outpost, type_id, kit, count (deploy) / machine_id (retire)
#   provider, why, kit_source ("inventory" | "available" | None), blocked
#   status    proposed | approved | queued | rejected
#   jobs      building_ops job ids once queued
#   tick      proposed / rejected / queued at
# Ids: "deploy:<outpost>:<type_id>", "retire:<machine_id>". A rejected entry
# holds its id out for REJECT_HOLD_TICKS. A queued entry goes once all its
# jobs are done; a blocked job puts the entry back to proposed with the
# job's status in `blocked`.

from archive import archive
from swallow import swallowed
from storage import PENALIZED_TYPES, inventory_count
import autoplay_roles
from autoplay_roles import role_gaps, kit_id, stock_slots, warehouse_slots, WAREHOUSES, WAREHOUSE_SLOTS
import outpost_needs
import building_ops
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

PROPOSALS_KEY = "autoplay.build_proposals"
REQUESTER = "building_plan"
REFINER_STATUS_KEY = "refiner.status"
RETIRE_READY = "ready"
PASS_TICKS = 6000            # full pass at most this often (10 sim min)
REJECT_HOLD_TICKS = 864000   # 24 sim hours a rejected proposal stays out
OPEN = ("proposed", "approved", "queued")


def _tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("building_plan._tick: clock.tick", error)
        return 0


# ---------- providers (pure) ----------

def _pick(group, kits):
    """First alternative of a building group whose kit can be had; None when all are locked."""
    for type_id in group:
        if kit_id(type_id) in kits:
            return type_id
    return None


def role_wants(entry, kits):
    """[(type_id, 1, why)] for every building group a designated role lacks at this outpost (Warehouses left out)."""
    types = entry.get("types") or {}
    out = []
    seen = []
    for role in role_gaps(entry.get("roles"), types)["missing"]:
        for group in autoplay_roles.building_groups(role):
            if group == WAREHOUSES or group in seen or any(types.get(t, 0) > 0 for t in group):
                continue
            seen.append(group)
            type_id = _pick(group, kits)
            if type_id is not None:
                out.append((type_id, 1, f"role {role} lacks {type_id}"))
    return out


def storage_wants(entry, snap):
    """[(warehouse type, count, why)] for the Warehouse slots the designation stocks beyond what stands there."""
    roles = entry.get("roles") or []
    types = entry.get("types") or {}
    per = snap.get("per_warehouse") or WAREHOUSE_SLOTS["warehouse"]
    type_id = "large_warehouse" if per == WAREHOUSE_SLOTS["large_warehouse"] else "warehouse"
    if kit_id(type_id) not in (snap.get("kits") or ()):
        return []   # before Warehouse research: Storage Bins, sized by the machine scripts
    want = stock_slots(roles, snap.get("stock") or {})
    have, buildings = warehouse_slots(types)
    count = (max(0, want - have) + per - 1) // per
    if count:
        return [(type_id, count, f"stock needs {want} slots, {have} standing")]
    needs_one = any(WAREHOUSES in autoplay_roles.building_groups(role) for role in autoplay_roles.role_list(roles))
    if needs_one and not buildings:
        return [(type_id, 1, "designated role needs a Warehouse")]
    return []


def cap_block(entry, type_id, count):
    """Reason the deploy would break the cap gate, else None."""
    used, cap = entry.get("used", 0), entry.get("capacity", 0)
    if not cap or used + count <= cap:
        return None
    types = entry.get("types") or {}
    if type_id in PENALIZED_TYPES or any(types.get(t, 0) > 0 for t in PENALIZED_TYPES):
        return f"over cap ({used}+{count} > {cap}) with a penalized machine"
    return None


def fresh_proposals(snap, inventory, refiners):
    """
    {proposal_id: entry} the providers want now. inventory = {kit_id: units};
    refiners = refiner.status {machine_id: entry}.
    """
    kits = snap.get("kits") or set()
    out = {}
    for entry in snap.get("outposts") or []:
        oid = entry["id"]
        for provider, wants in (("roles", role_wants(entry, kits)), ("storage", storage_wants(entry, snap))):
            for type_id, count, why in wants:
                kit = kit_id(type_id)
                source = "inventory" if inventory.get(kit, 0) >= count else ("available" if kit in kits else None)
                out[f"deploy:{oid}:{type_id}"] = {
                    "kind": "deploy", "outpost": oid, "type_id": type_id, "kit": kit, "count": count,
                    "provider": provider, "why": why, "kit_source": source,
                    "blocked": cap_block(entry, type_id, count)}
    for machine_id, status in sorted((refiners or {}).items()):
        if isinstance(status, dict) and status.get("retire") == RETIRE_READY:
            out[f"retire:{machine_id}"] = {
                "kind": "retire", "machine_id": machine_id, "outpost": status.get("outpost"), "type_id": "refiner",
                "provider": "retire", "why": "wildlife complete, Refiner emptied", "kit_source": None, "blocked": None}
    return out


def merge(old, fresh, tick):
    """New proposals dict: open entries keep their status, rejected ones hold their id, dropped proposals go."""
    out = {}
    for pid, entry in old.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "rejected" and tick - (entry.get("tick") or 0) < REJECT_HOLD_TICKS:
            out[pid] = entry
        elif status in ("approved", "queued"):
            out[pid] = dict(entry, **{k: v for k, v in (fresh.get(pid) or {}).items() if k != "count"})
    for pid, entry in fresh.items():
        if pid in out:
            continue
        prev = old.get(pid) if isinstance(old.get(pid), dict) else {}
        out[pid] = dict(entry, status="proposed", tick=prev.get("tick", tick) if prev.get("status") == "proposed" else tick)
    return out


def advance(entry, jobs):
    """Status of a queued entry from its jobs: "done" (all done), "blocked: <status>" or "queued"."""
    states = [(jobs.get(j) or {}) for j in entry.get("jobs") or []]
    for job in states:
        if job.get("state") == "blocked":
            return "blocked: " + str(job.get("status"))
    if states and all(job.get("state") == "done" for job in states):
        return "done"
    if not states:
        return "done"
    return "queued"


# ---------- operator answers (BUILD card) ----------

def load():
    raw = archive.get(PROPOSALS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def answer(proposal_id, approve):
    """Operator approve / reject of an open proposal; False when it is not open, blocked or the write failed."""
    tick = _tick()
    done = [False]

    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        entry = cur.get(proposal_id)
        if not isinstance(entry, dict) or entry.get("status") != "proposed":
            return cur
        if approve and entry.get("blocked"):
            return cur
        entry["status"] = "approved" if approve else "rejected"
        entry["tick"] = tick
        done[0] = True
        return cur
    return archive.transaction(PROPOSALS_KEY, {}, updater) and done[0]


# ---------- pass ----------

def _read_inventory(kits):
    out = {}
    for kit in kits:
        out[kit] = inventory_count(kit)
    return out


class BuildingPlanner:
    """
    The building pass. run_pass(snap) returns "idle" (nothing proposed or
    queued), "waiting" (proposals wait for the operator) or "working" (jobs
    run). snap: the founding pass's outpost_needs snapshot when fresh, else
    None (read here).
    """

    def __init__(self, log: "TreeConsole"):
        self.log = log
        self.ops = building_ops.BuildingOps(log)
        self.full_tick = None

    def due(self):
        return self.full_tick is None or _tick() - self.full_tick >= PASS_TICKS

    def run_pass(self, snap=None):
        tick = _tick()
        stored = load()
        proposals = dict([(pid, dict(e)) for pid, e in stored.items() if isinstance(e, dict)])
        if self.due():
            snap = snap if snap is not None else outpost_needs.snapshot()
            refiners = archive.get(REFINER_STATUS_KEY, {}) or {}
            kits = sorted(set([e["kit"] for e in fresh_proposals(snap, {}, refiners).values() if e.get("kit")]))
            wanted = fresh_proposals(snap, _read_inventory(kits), refiners)
            proposals = merge(proposals, wanted, tick)
            self.full_tick = tick
        lines = self._queue(proposals, tick)
        notes = self.ops.step_jobs()
        lines += self._settle(proposals)
        if proposals != stored:
            archive.transaction(PROPOSALS_KEY, {}, lambda _old: proposals)
        opened = [pid for pid, e in proposals.items() if e.get("status") == "proposed" and stored.get(pid, {}).get("status") != "proposed"]
        if lines or opened:
            self.log.start("Building proposals")
            for pid in opened:
                e = proposals[pid]
                what = f"{e.get('count', 1)}x {e['type_id']}" if e["kind"] == "deploy" else e["machine_id"]
                self.log.print(f"Proposed {e['kind']} {what} at {e.get('outpost') or 'home'}: {e['why']}"
                               + (f" (blocked: {e['blocked']})" if e.get("blocked") else ""))
            for line in lines:
                self.log.print(line)
            self.log.end(f"{len([e for e in proposals.values() if e.get('status') in OPEN])} open")
        if notes:
            self.log.debug("Build jobs: " + "; ".join(notes))
        if any(e.get("status") == "queued" for e in proposals.values()):
            return "working"
        return "waiting" if any(e.get("status") == "proposed" for e in proposals.values()) else "idle"

    def _queue(self, proposals, tick):
        """Approved proposals become executor jobs."""
        lines = []
        for pid, entry in sorted(proposals.items()):
            if entry.get("status") != "approved":
                continue
            jobs = []
            if entry["kind"] == "deploy":
                for n in range(int(entry.get("count", 1))):
                    jobs.append(building_ops.request_deploy(entry["type_id"], entry["outpost"], REQUESTER, entry["why"],
                                                            ref=f"{pid}#{n}", kit_id=entry.get("kit")))
            else:
                # The Refiner emptied itself already (its retire flag), so no handshake.
                jobs.append(building_ops.request_retire(entry["machine_id"], REQUESTER, entry["why"], handshake=False))
            if None in jobs:
                lines.append(f"{pid}: job write rejected; retried next pass.")
                continue
            entry.update({"status": "queued", "jobs": jobs, "tick": tick})
            lines.append(f"{pid} approved: {len(jobs)} job(s) queued.")
        return lines

    def _settle(self, proposals):
        """Queued entries whose jobs finished go; a blocked job sends its entry back to proposed."""
        jobs = building_ops.jobs()
        lines = []
        for pid in sorted(proposals):
            entry = proposals[pid]
            if entry.get("status") != "queued":
                continue
            state = advance(entry, jobs)
            if state == "done":
                del proposals[pid]
                lines.append(f"{pid}: done.")
            elif state.startswith("blocked"):
                entry.update({"status": "proposed", "blocked": state[len("blocked: "):], "jobs": []})
                lines.append(f"{pid}: job {state}; back to proposed.")
        return lines
