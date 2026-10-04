from archive import archive
from swallow import swallowed

# Script restart requests (docs/cheatsheet/archive_ipc.md, script.restart_requests).
#
# The game binds a script's `self` API once, when the script starts. An
# attribute the machine gains while the script runs stays missing until the
# next start: a Mk III upgrade pack applied under a running Heat / Pressure /
# Oxygen Generator script leaves `self.steam_in` / `self.water_in` unbound.
# A script can't restart itself (run_control.stop() on its own machine ends
# it), so it files a request here and control_room_automation.py stops and
# starts it (process_restart_requests()).
#
# One entry per machine: {machine_id: {"reason", "restarts", "state", "tick"}}.
#   - state "requested": waiting for the control room.
#   - state "restarted": the control room restarted the script `restarts`
#     times for this reason.
#   - state "gave_up": the script asked again after MAX_RESTARTS restarts;
#     it stays as it is and the AUTOMATION card names it.
# The machine clears its own entry once the API it missed is there
# (clear_restart()), so a later fault with another reason (Mk III port, then
# Mk IV magazine) starts from zero restarts. A request with a new reason
# resets the count too. Callers: lib/terraforming.py UnboundPortRestart. ArchiveCleaner drops entries of machines that are gone.

RESTART_REQUESTS_KEY = "script.restart_requests"

# Two restarts: one failed restart can be a fluke.
MAX_RESTARTS = 2

STATE_REQUESTED = "requested"
STATE_RESTARTED = "restarted"
STATE_GAVE_UP = "gave_up"


def request_restart(machine_id, reason, tick):
    """Files a restart request for machine_id's script. Returns the entry's new
    state (STATE_REQUESTED, or STATE_GAVE_UP after MAX_RESTARTS restarts for the
    same reason), or None when the archive write failed."""
    outcome = [STATE_REQUESTED]

    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        entry = requests.get(machine_id)
        if not isinstance(entry, dict) or entry.get("reason") != reason:
            entry = {"reason": reason, "restarts": 0}
        entry["state"] = STATE_GAVE_UP if entry.get("restarts", 0) >= MAX_RESTARTS else STATE_REQUESTED
        entry["tick"] = tick
        requests[machine_id] = entry
        outcome[0] = entry["state"]
        return requests

    if not archive.transaction(RESTART_REQUESTS_KEY, {}, updater):
        return None
    return outcome[0]


def clear_restart(machine_id, reason):
    """Drops machine_id's entry if it was filed for reason. Returns the dropped
    entry, or None when there was none. An entry with another reason stays: that
    fault is not known to be fixed."""
    entry = archive.get_entry(RESTART_REQUESTS_KEY, machine_id)
    if not isinstance(entry, dict) or entry.get("reason") != reason:
        return None
    archive.pop_entry(RESTART_REQUESTS_KEY, machine_id)
    return entry


def gave_up_ids():
    """Machine ids whose restarts ran out, sorted."""
    requests = archive.get(RESTART_REQUESTS_KEY, {}) or {}
    if not isinstance(requests, dict):
        return []
    return sorted(i for i, e in requests.items() if isinstance(e, dict) and e.get("state") == STATE_GAVE_UP)


def _mark_restarted(machine_id, tick):
    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        entry = requests.get(machine_id)
        if isinstance(entry, dict) and entry.get("state") == STATE_REQUESTED:
            entry["restarts"] = entry.get("restarts", 0) + 1
            entry["state"] = STATE_RESTARTED
            entry["tick"] = tick
        return requests
    return archive.transaction(RESTART_REQUESTS_KEY, {}, updater)


def process_restart_requests(run_control, tick):
    """Stops and starts every script with a "requested" entry. Returns
    (restarted ids, {id: refusal status}) for the caller to log. A refused start
    keeps the request, so the next pass retries it."""
    from script_parking import start_script
    requests = archive.get(RESTART_REQUESTS_KEY, {}) or {}
    if not isinstance(requests, dict) or not run_control:
        return [], {}
    restarted = []
    refused = {}
    for machine_id in sorted(requests):
        entry = requests[machine_id]
        if not isinstance(entry, dict) or entry.get("state") != STATE_REQUESTED:
            continue
        try:
            run_control.stop(machine_id)
        except Exception as error:
            swallowed("script_restart.process_restart_requests: run_control.stop", error)
        status = start_script(machine_id)
        if status != "ok":
            refused[machine_id] = status
            continue
        _mark_restarted(machine_id, tick)
        restarted.append(machine_id)
    return restarted, refused
