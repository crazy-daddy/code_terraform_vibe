"""
Retired machines: machines switched off for good because their job is done
(e.g. the essence chain at Full Biomass, lib/biomass_retire.py).

One archive dict, RETIRED_KEY = {machine_id: {"by": retirement name, "since": tick}}.
A retirement registers its machines with retire() before it switches their
breakers off and calls release() once they are undeployed. Script parking
(lib/script_parking.py) never treats a registered machine as stray dark; the
archive cleaner drops ids that no longer exist.
"""

from archive import archive
from swallow import swallowed

RETIRED_KEY = "machine.retired"


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("retired_machines._now_tick: clock.tick", error)
        return 0


def retired():
    """The RETIRED_KEY dict ({} when unreadable)."""
    try:
        value = archive.get(RETIRED_KEY, {}) or {}
    except Exception as error:
        swallowed("retired_machines.retired: archive.get", error)
        return {}
    return value if isinstance(value, dict) else {}


def retired_ids(by=None):
    """Ids registered as retired (by the retirement `by`, if given)."""
    return {m for m, e in retired().items() if by is None or (isinstance(e, dict) and e.get("by") == by)}


def retire(machine_ids, by):
    """Registers machine_ids as retired by `by`; ids already registered keep their entry."""
    new = [m for m in machine_ids if m]
    if not new:
        return
    now = _now_tick()

    def updater(entries):
        entries = entries if isinstance(entries, dict) else {}
        for machine_id in new:
            if machine_id not in entries:
                entries[machine_id] = {"by": by, "since": now}
        return entries

    try:
        archive.transaction(RETIRED_KEY, {}, updater)
    except Exception as error:
        swallowed("retired_machines.retire: archive.transaction", error)


def release(machine_ids):
    """Drops machine_ids from the registry (undeployed, or back in service)."""
    gone = [m for m in machine_ids if m]
    if not gone:
        return

    def updater(entries):
        entries = entries if isinstance(entries, dict) else {}
        for machine_id in gone:
            entries.pop(machine_id, None)
        return entries

    try:
        archive.transaction(RETIRED_KEY, {}, updater)
    except Exception as error:
        swallowed("retired_machines.release: archive.transaction", error)
