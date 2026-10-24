"""
Retired machines: machines switched off for good because their job is done
(e.g. the essence chain at Full Biomass, lib/biomass_retire.py).

One archive dict, RETIRED_KEY = {machine_id: {"by": retirement name, "since": tick}}.
A retirement registers its machines with retire() before it switches their
breakers off and calls release() once they are undeployed. Script parking
(lib/script_parking.py) never treats a registered machine as stray dark; the
archive cleaner drops ids that no longer exist. sell_kits() sells what an
undeploy returned, for every retirement that sells (biomass, bio chains).
"""

from archive import archive
from game_clock import now_tick
from swallow import swallowed

RETIRED_KEY = "machine.retired"


def retired():
    """The RETIRED_KEY dict ({} when unreadable)."""
    return archive.get_dict(RETIRED_KEY)


def retired_ids(by=None):
    """Ids registered as retired (by the retirement `by`, if given)."""
    return {m for m, e in retired().items() if by is None or (isinstance(e, dict) and e.get("by") == by)}


def retire(machine_ids, by):
    """Registers machine_ids as retired by `by`; ids already registered keep their entry."""
    new = [m for m in machine_ids if m]
    if not new:
        return
    now = now_tick()

    def register(entries):
        for machine_id in new:
            if machine_id not in entries:
                entries[machine_id] = {"by": by, "since": now}

    try:
        archive.mutate(RETIRED_KEY, register)
    except Exception as error:
        swallowed("retired_machines.retire: archive.mutate", error)


def release(machine_ids):
    """Drops machine_ids from the registry (undeployed, or back in service)."""
    gone = [m for m in machine_ids if m]
    if not gone:
        return

    try:
        archive.pop_entries(RETIRED_KEY, gone)
    except Exception as error:
        swallowed("retired_machines.release: archive.pop_entries", error)


def sell_kits(shop: "Shop", item_ids, logger, warn=True):
    """
    Sells one unit of each id in item_ids from Inventory (the kits and packs an
    undeploy returned). Returns (credits earned, [ids not sold]); a retirement
    keeps the unsold ids and retries them next pass, with warn=False so a
    refusal warns only the first time.
    """
    credits = 0
    unsold = []
    for item_id in item_ids:
        try:
            res = shop.sell(item_id, 1)
        except Exception as error:
            swallowed("retired_machines.sell_kits: shop.sell", error)
            unsold.append(item_id)
            continue
        if getattr(res, "status", "") != "ok":
            if warn:
                logger.level("warn").print(f"sell('{item_id}') -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Retrying next pass.")
            unsold.append(item_id)
            continue
        credits += getattr(res, "credits", 0) or 0
    return credits, unsold
