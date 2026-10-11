# Constructor archive I/O as module functions (layer 0 of the vehicle mixins,
# docs/plans/mixin_refactor/README.md): construction.lots, construction.priority,
# construction.hold and construction.power_tiles reads and transactions, the
# sweep of a Pioneer's build_* claims on dead blueprints, and the blueprint
# job-list reads. Callers pass the Pioneer's name, tick and log; no vehicle
# mixin imports. Pure planning math stays in
# lib/construction_plan.py; lib/job_build.py (BuildJob) and
# lib/pioneer_construction.py call these.

import construction_plan
import fleet_status
from archive import archive
from fleet_claims_common import LEGACY_ROVER_CLAIMS_KEY, SURVEY_CLAIMS_KEY
from swallow import swallowed


def release_finished_claims(name, live_job_ids, existing_claims, log):
    """
    Drops every build_* claim `name` holds whose blueprint is no longer live
    (not in pending/active/paused): finished or removed while this script
    wasn't the one to observe it (restart mid-build, or claims leaked before
    get_construction_progress() learned that "gone" means done). One
    transaction per claims key, and only when something actually needs
    releasing (checked first against existing_claims, which the caller
    already fetched). Returns the number released.
    """
    mine = [
        key for key, claim in (existing_claims or {}).items()
        if key.startswith("build_") and isinstance(claim, dict)
        and (claim.get("vehicle") == name or claim.get("rover") == name)
        and key[len("build_"):] not in live_job_ids
    ]
    if not mine:
        return 0
    dead = set(mine)

    def updater(claims):
        if not isinstance(claims, dict):
            return {}
        return {k: v for k, v in claims.items() if k not in dead}

    archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
    archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
    log.print(f"[{name}] Released {len(dead)} build claim(s) on finished/removed blueprints.")
    return len(dead)


def read_priorities():
    """{blueprint_id: int} from the construction.priority archive dict ({} when absent or unreadable)."""
    try:
        return construction_plan.clean_priorities(archive.get(construction_plan.PRIORITY_KEY, {}))
    except Exception as error:
        swallowed("construction_lots.read_priorities: archive.get", error)
        return {}


def read_hold(tick):
    """Job kinds held by a fresh construction.hold (construction_plan.held_kinds()); empty when absent or unreadable."""
    try:
        return construction_plan.held_kinds(archive.get(construction_plan.HOLD_KEY, None), tick)
    except Exception as error:
        swallowed("construction_lots.read_hold: archive.get", error)
        return set()


def active_lot_owners(name, tick):
    """Active Constructor peers of `name`, any home (construction_plan.peer_builders()): whose lots count."""
    return construction_plan.peer_builders(
        fleet_status.get_all(), name, None, tick, construction_plan.PEER_BUILDER_ACTIVE_TICKS,
    )


def read_lots(name, tick):
    """(job ids in active peers' lots, job ids in `name`'s own lot) from construction.lots."""
    try:
        lots = construction_plan.clean_lots(archive.get(construction_plan.LOTS_KEY, {}))
    except Exception as error:
        swallowed("construction_lots.read_lots: archive.get", error)
        return set(), set()
    if not lots:
        return set(), set()
    return construction_plan.taken_ids(lots, active_lot_owners(name, tick)), set(lots.get(name, ()))


def write_lot(name, tick, rows):
    """
    Sets `name`'s construction.lots entry to rows' ids (none: drops it). A
    job a peer reserved meanwhile stays the peer's. Entries of builders no
    longer active are pruned in the same transaction. Returns the ids kept.
    """
    active = set(active_lot_owners(name, tick))
    ids = [row["id"] for row in rows]
    kept = []

    def updater(current):
        out = {}
        if isinstance(current, dict):
            out = {k: v for k, v in current.items() if k in active}
        taken = construction_plan.taken_ids(construction_plan.clean_lots(out), active)
        kept[:] = [job_id for job_id in ids if job_id not in taken]
        if kept:
            out[name] = {"ids": list(kept), "tick": tick}
        return out

    archive.transaction(construction_plan.LOTS_KEY, {}, updater)
    return kept


def release_lot(name, tick, log):
    """Drops `name`'s construction.lots entry, if any."""
    try:
        lots = archive.get(construction_plan.LOTS_KEY, {})
    except Exception as error:
        swallowed("construction_lots.release_lot: archive.get", error)
        return
    if isinstance(lots, dict) and name in lots:
        write_lot(name, tick, [])
        log.debug(f"[{name}] Released construction lot.")


def note_finished_power_job(name, kind, coords, log):
    """Records a finished power-line, power-bridge or deconstruction job in construction.power_tiles."""
    if kind not in (construction_plan.POWER_LINE_KIND, construction_plan.POWER_BRIDGE_KIND, construction_plan.DECONSTRUCT_KIND):
        return
    if not coords:
        return

    def updater(current):
        return construction_plan.note_power_job(current, kind, coords[0], coords[1])

    archive.transaction(construction_plan.POWER_TILES_KEY, construction_plan.empty_power_ledger(), updater)
    log.debug(f"[{name}] Power ledger: noted {kind} at ({coords[0]:.0f}, {coords[1]:.0f}).")


def prune_priorities(name, priorities, live_job_ids, log):
    """
    Drops construction.priority entries whose blueprint is not live.
    priorities must be read before the job lists, so an entry written
    after its blueprint was queued is never mistaken for a dead one.
    Returns the number dropped.
    """
    stale = construction_plan.stale_priorities(priorities, live_job_ids)
    if not stale:
        return 0
    dead = set(stale)

    def updater(current):
        if not isinstance(current, dict):
            return {}
        return {k: v for k, v in current.items() if k not in dead}

    archive.transaction(construction_plan.PRIORITY_KEY, {}, updater)
    log.debug(f"[{name}] Pruned {len(dead)} construction.priority entr(ies) of finished/removed blueprints.")
    return len(dead)


def sweep_dead_jobs(name, live_ids, claims, priorities, log):
    """Drops `name`'s build claims and the construction.priority entries of blueprints no longer live."""
    release_finished_claims(name, live_ids, claims, log)
    prune_priorities(name, priorities, live_ids, log)


def planned_progress_for_job(job, cap):
    """Remaining progress of a blueprint job, capped at cap (PioneerConstructionMixin.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP), for trip budgeting."""
    remaining = max(0.0, 1.0 - (getattr(job, "progress", 0.0) or 0.0))
    return min(remaining, cap)


def read_jobs(bp, getter_name):
    """(jobs, ok) from one construction_blueprint list; ok is False only when the read raised."""
    if not bp or not hasattr(bp, getter_name):
        return [], True
    try:
        return getattr(bp, getter_name)() or [], True
    except Exception as error:
        swallowed(f"construction_lots.read_jobs: bp.{getter_name}", error)
        return [], False
