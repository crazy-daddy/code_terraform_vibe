# Shared live-telemetry dict for every ground vehicle and drone. One archive
# key "fleet.status" = {name: {name, state, x, y, wh, level, target, intent, tick}}
# (both add "home": home outpost id, and "role": job designation, None until
# detected; drones also "unit", "engine")
# instead of one key per vehicle -- the Data Archive has a fixed key-count cap
# (CODE_GUIDES.md#archive). Written by VehicleController/DroneController
# publish_telemetry(); the FLEET/DRONE FLEET cards read "intent" from it.
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

# publish_telemetry() states that end a job: the controller's intent (one
# line from lib/fleet_intent.py describe(), shown on the fleet cards) is
# cleared on them.
IDLE_STATES = ("IDLE", "IDLE_AT_OUTPOST", "IDLE_AT_BASE", "READY_AT_OUTPOST", "RECALLED", "AWAITING_MODULES", "SURVEY_COMPLETE", "UPGRADE_HOLD")

# Intent column (fleet.status[id]["intent"], lib/fleet_intent.py): what the
# job is and whom it serves. Word-wrapped onto up to INTENT_LINES lines of
# the room left of the right-hand controls, at INTENT_CHAR_PX per character
# (font size 10); the last line is cut with "..".
INTENT_CHAR_PX = 6
INTENT_LINES = 2
INTENT_LINE_PX = 13


def wrap_text(text, width_px, max_lines=INTENT_LINES):
    """text word-wrapped to width_px at INTENT_CHAR_PX per character, at most
    max_lines lines; an overlong last line or word is cut with ".."."""
    chars = int(width_px // INTENT_CHAR_PX)
    if chars <= 2:
        return []
    lines, line = [], ""
    for word in text.split(" "):
        candidate = f"{line} {word}" if line else word
        if len(candidate) <= chars or not line:
            line = candidate
            continue
        lines.append(line)
        line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:chars - 2] + ".."
    return [l if len(l) <= chars else l[:chars - 2] + ".." for l in lines]

# name -> (payload without "tick", tick last written). Per script process.
_last_published = {}


# Drawing helpers shared by drones_panel.py and vehicles_panel.py; `panel` is the
# script's injected panel global.

def draw_intent(panel, x, y, text, width_px):
    """Intent text wrapped by wrap_text(), INTENT_LINE_PX apart (Control Room fleet cards)."""
    for index, line in enumerate(wrap_text(text, width_px)):
        panel.draw_text(x, y + index * INTENT_LINE_PX, line, 10, "text-value")


def outpost_names():
    """{outpost id: display name} for the home column; empty without outpost_network."""
    network = get_component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        return {}
    return {o.id: o.name for o in network.outposts()}


def draw_assignment(panel, x, y, status, names, width_px):
    """Role and home outpost (fleet.status "role"/"home") on two lines; blank until the script publishes them."""
    chars = max(0, int(width_px // INTENT_CHAR_PX))
    role = status.get("role")
    home = status.get("home")
    if role:
        panel.draw_text(x, y, str(role)[:chars], 10, "text-value")
    if home:
        panel.draw_text(x, y + INTENT_LINE_PX, str(names.get(home, home))[:chars], 10, "text-secondary")


# A switch keeps its own stored state; default_on only seeds it once. Code
# also changes a recall flag (retire request, blocked retirement), so the
# switch is kept in step with the archive: a stored state that moved since
# the last tick is a click, any other mismatch is overwritten from the archive.
_switch_seen = {}


def synced_switch(panel, key, x, y, value, label):
    stored = panel.get_switch(key)
    clicked = stored is not None and key in _switch_seen and stored != _switch_seen[key]
    if not clicked and stored is not None and stored != value:
        panel.set_switch(key, value)
    on = panel.switch(key, x, y, value, label)
    _switch_seen[key] = on
    return on


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

