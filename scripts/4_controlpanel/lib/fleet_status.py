# Shared live-telemetry dict for every ground vehicle and drone. One archive
# key "fleet.status" = {name: {name, state, x, y, wh, level, target, tick}}
# instead of one key per vehicle -- the Data Archive has a fixed key-count cap
# (CLAUDE.md rule 7). Written by VehicleController/DroneController
# publish_telemetry(); intended as the data source for a future fleet panel.
#
# Replaces three legacy per-entity families: fleet.status.<id> plus the exact
# duplicates rover.status.<id> (rovers) and drone.status.<id> (drones).
# Nothing reads those, so they're left in place until
# lib/archive_cleaner.py's clean_telemetry() deletes them (it also prunes dict
# entries of vehicles/drones that no longer exist).

from archive import archive
from tree_console import TreeConsole

log = TreeConsole(module="fleet_status")

FLEET_STATUS_KEY = "fleet.status"
LEGACY_FLEET_STATUS_PREFIXES = ("fleet.status.", "rover.status.", "drone.status.")

# Every writer rewrites the whole shared dict, so an unchanged payload is only
# re-published as a heartbeat (fresh "tick", lets a reader tell a stopped
# script apart from an idle one) at most this often. Any changed field
# (state, position, battery, target) publishes immediately. 50 ticks ~= 5 s.
FLEET_STATUS_MIN_INTERVAL_TICKS = 50

# name -> (payload without "tick", tick last written). Per script process.
_last_published = {}


def publish(name, telemetry):
    """
    Atomically stores telemetry under fleet.status[name], skipping the write
    when nothing but "tick" changed within FLEET_STATUS_MIN_INTERVAL_TICKS.
    Returns True if a write was issued.
    """
    tick = telemetry.get("tick", 0) or 0
    payload = {k: v for k, v in telemetry.items() if k != "tick"}
    last = _last_published.get(name)
    if last is not None and last[0] == payload and 0 <= tick - last[1] < FLEET_STATUS_MIN_INTERVAL_TICKS:
        log.trace(f"publish({name!r}): unchanged, {tick - last[1]} < {FLEET_STATUS_MIN_INTERVAL_TICKS} ticks since last write; skipped.")
        return False

    def updater(status):
        if not isinstance(status, dict):
            status = {}
        status[name] = telemetry
        return status

    archive.transaction(FLEET_STATUS_KEY, {}, updater)
    _last_published[name] = (payload, tick)
    return True


def get_all():
    """Returns the whole {name: telemetry} dict (empty if missing/malformed)."""
    status = archive.get(FLEET_STATUS_KEY, {})
    return status if isinstance(status, dict) else {}


def get(name):
    """Returns name's last published telemetry dict, or None."""
    entry = get_all().get(name)
    return entry if isinstance(entry, dict) else None


def forget(name):
    """Drops name's entry, e.g. once the vehicle/drone no longer exists."""
    def updater(status):
        if isinstance(status, dict):
            status.pop(name, None)
        return status

    archive.transaction(FLEET_STATUS_KEY, {}, updater)
    _last_published.pop(name, None)

