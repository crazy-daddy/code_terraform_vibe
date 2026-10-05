# Archive helpers shared by the ground-vehicle (lib/vehicle_claims.py) and drone
# (lib/drone_claims.py) claim mixins. Each mixin keeps its own archive keys and
# owner field; these functions take the key and an owns(claim) predicate.
#
# Shapes (one shared dict per concern, CODE_GUIDES.md#archive):
#   recall flags  {unit_name: True}            -- absent = not recalled
#   missions      {unit_name: {target_key, target, kind, tick}}
#   claims        {target_key: {<owner field(s)>, coords, name, tick, ...}}
# A log call inside an archive.transaction() updater gets the write rejected, so
# every helper collects notes and the caller logs them afterwards.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole


def is_flagged(key, name):
    """True when name is set in the {name: True} dict under key."""
    flags = archive.get(key, {}) or {}
    if not isinstance(flags, dict):
        return False
    return bool(flags.get(name, False))


def set_flagged(key, name, on):
    """Sets or clears name in the {name: True} dict under key."""
    def updater(flags):
        if not isinstance(flags, dict):
            flags = {}
        if on:
            flags[name] = True
        else:
            flags.pop(name, None)
        return flags

    archive.transaction(key, {}, updater)


def save_mission(key, name, target_key, kind, target, tick):
    archive.set_entry(key, name, {"target_key": target_key, "target": target, "kind": kind, "tick": tick})


def clear_mission(key, name):
    # Plain read first: a transaction always writes back, and this runs on
    # every claim release, mostly with no mission stored.
    if archive.get_entry(key, name) is not None:
        archive.pop_entry(key, name)


def read_mission(key, legacy_prefix, name, log: "TreeConsole"):
    """name's stored mission record, moving a pre-consolidation <legacy_prefix><name>
    key into the shared dict on first read. None when nothing is stored."""
    record = archive.get_entry(key, name)
    if record is not None:
        return record if isinstance(record, dict) else None
    legacy_key = f"{legacy_prefix}{name}"
    record = archive.get(legacy_key, None)
    if record is None:
        return None
    archive.delete(legacy_key)
    if not isinstance(record, dict):
        return None
    archive.set_entry(key, name, record)
    log.debug(f"[{name}] load_mission: migrated legacy '{legacy_key}' into {key}.")
    return record


def try_claim(key, target_key, name, owner_of, record, tick, stale_ticks, notes):
    """
    Writes record as the claim on target_key unless another unit holds a claim
    younger than stale_ticks (any claim counts while tick == 0, clock not ready).
    owner_of(claim) -> owner name. Appends what happened to notes. True when won.
    """
    claimed = [False]

    def updater(claims):
        if not isinstance(claims, dict):
            claims = {}
        existing = claims.get(target_key)
        if existing:
            owner = owner_of(existing)
            age = tick - existing.get("tick", 0)
            if owner != name:
                if tick == 0 or age < stale_ticks:
                    claimed[0] = False
                    notes.append(f"[{name}] claim('{target_key}'): lost -- held by '{owner}' (age={age} ticks < stale threshold {stale_ticks}).")
                    return claims
                notes.append(f"[{name}] claim('{target_key}'): claim by '{owner}' is stale (age={age} ticks >= {stale_ticks}); taking over.")
        claims[target_key] = record
        claimed[0] = True
        return claims

    if not archive.transaction(key, {}, updater):
        notes.append(f"[{name}] claim('{target_key}'): {key} write rejected; treating as lost.")
        return False
    return claimed[0]


def refresh_claim(key, target_key, owns, tick):
    """Renews the heartbeat tick on target_key's claim when owns(claim)."""
    def updater(claims):
        if isinstance(claims, dict) and target_key in claims and owns(claims[target_key]):
            claims[target_key]["tick"] = tick
        return claims

    archive.transaction(key, {}, updater)


def release_claims(key, target_key, owns):
    """Drops target_key's claim (or, with target_key None, every claim) where owns(claim). Returns the released keys."""
    released = []

    def updater(claims):
        del released[:]
        if not isinstance(claims, dict):
            return {}
        keys = [target_key] if target_key else list(claims.keys())
        for k in keys:
            claim = claims.get(k)
            if isinstance(claim, dict) and owns(claim):
                del claims[k]
                released.append(k)
        return claims

    archive.transaction(key, {}, updater)
    return released


def drop_stale_claims(key, tick, stale_ticks):
    """Removes claims (and non-dict entries) older than stale_ticks. Returns how many expired."""
    expired = [0]

    def updater(claims):
        if not isinstance(claims, dict):
            return {}
        active = {}
        for k, claim in claims.items():
            if not isinstance(claim, dict):
                continue
            if tick - claim.get("tick", 0) < stale_ticks:
                active[k] = claim
            else:
                expired[0] += 1
        return active

    archive.transaction(key, {}, updater)
    return expired[0]
