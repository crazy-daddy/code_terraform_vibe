from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
import fluid_routing
from plant_terraformer_common import STATUS_KEY, STATUS_STALE_TICKS

# Plants completion: undeploy the Plant Terraformers (Control Room
# Automation, every storage pass). At 5,000,000 km² every Terraformer reads
# status() "complete" and has nothing left to do, but a deployed machine
# keeps a building slot, and its script kept running.
#
# Emptying is self-only (input.eject()), so each Terraformer's own script
# ejects its holders to local storage and then ends
# (lib/plant_terraformer.py; keys in lib/plant_terraformer_common.py). This
# pass, once any `plant.terraformer` entry reads "complete":
#   - a Terraformer not yet "complete" (batch still running) is left alone;
#   - a complete one with items in its holders gets its script started again
#     if it is not running, so it ejects them;
#   - a complete, empty one is undeployed (kit + Mk II pack go to Inventory)
#     and its telemetry entry is pruned.
# Refused undeploys (Inventory full, cargo arriving) are retried next pass.
# Ejected items land in Warehouses; the haulers and the consolidation sweep
# clear them over time.

TERRAFORMER_TYPE_ID = "plant_terraformer"

# undeploy() answers that only mean "not right now".
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full", "cargo_present")

IDLE_SUMMARY = "plants retire idle"

log = TreeConsole(module="plants_retire")


def _telemetry():
    raw = archive.get(STATUS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def plants_complete():
    """True once any Terraformer published status "complete" (Plants are global, so every machine reads it)."""
    return any(isinstance(e, dict) and e.get("status") == "complete" for e in _telemetry().values())


def _call(obj, method, default):
    try:
        return getattr(obj, method)()
    except Exception as error:
        swallowed("plants_retire._call: getattr(obj, method)", error)
        return default


class PlantsRetirement:
    """One pass per storage tick of control_room_automation.py; see module header."""

    def __init__(self, computer: "Computer | None" = None, run_control: "RunControl | None" = None):
        self.computer = computer or get_component("computer")
        self.run_control = run_control or get_component("run_control")
        self._warned = {}

    def _restart_script(self, machine_id):
        """Starts the Terraformer's script when it is not running; True when it is running now."""
        run = self.run_control
        if run is None:
            return False
        try:
            if run.is_running(machine_id):
                return True
            res = run.start(machine_id)
        except Exception as error:
            swallowed("plants_retire.PlantsRetirement._restart_script: run_control.start", error)
            return False
        ok = getattr(res, "status", "") == "ok"
        log.debug(f"[{machine_id}] holders not empty, script stopped: start() -> {getattr(res, 'status', '?')} {getattr(res, 'message', '')}")
        return ok

    def _undeploy(self, machine_id):
        """undeploy() status ("ok", "not_found", a transient refusal, ...); "error" when the call raised."""
        computer = self.computer
        if computer is None:
            return "error"
        try:
            res = computer.undeploy(machine_id)
        except Exception as error:
            swallowed("plants_retire.PlantsRetirement._undeploy: computer.undeploy", error)
            return "error"
        status = getattr(res, "status", "") or "?"
        if status not in ("ok", "not_found"):
            level = "debug" if status in TRANSIENT_UNDEPLOY_STATUSES else "warn"
            if level == "debug" or self._warned.get(machine_id) != status:
                self._warned[machine_id] = status
                log.level(level).print(f"[{machine_id}] undeploy -> {status}: {getattr(res, 'message', '')}")
        return status

    def step(self, current_tick=0):
        """One pass. Returns the AUTOMATION card summary (IDLE_SUMMARY when there is nothing to do)."""
        if not plants_complete() or self.computer is None:
            return IDLE_SUMMARY
        found = []
        undeployed = []
        emptying = []
        running = []
        for building, _outpost_id in fluid_routing.discover_network_buildings(TERRAFORMER_TYPE_ID, resolve=True):
            machine_id = getattr(building, "id", None)
            if not machine_id:
                continue
            found.append(machine_id)
            status = _call(building, "status", "")
            if status != "complete":
                running.append(machine_id)
                continue
            port = getattr(building, "input", None)
            held = _call(port, "count", 0) if port is not None else 0
            if held > 0:
                emptying.append(machine_id)
                self._restart_script(machine_id)
                continue
            result = self._undeploy(machine_id)
            if result in ("ok", "not_found"):
                undeployed.append(machine_id)
                archive.pop_entry(STATUS_KEY, machine_id)
                self._warned.pop(machine_id, None)
                if result == "ok":
                    log.print(f"[{machine_id}] Plants complete: Plant Terraformer undeployed; kit back in Inventory.")
            else:
                emptying.append(machine_id)
        # Entries of Terraformers no longer deployed have no publisher left.
        # An empty discovery may be a failed read, so then only entries
        # older than STATUS_STALE_TICKS go.
        for machine_id, entry in _telemetry().items():
            stale = not isinstance(entry, dict) or current_tick - int(entry.get("tick", 0) or 0) >= STATUS_STALE_TICKS
            if machine_id not in found and (found or stale):
                archive.pop_entry(STATUS_KEY, machine_id)
        log.debug(f"plants retire: found={found} undeployed={undeployed} waiting={emptying} still running={running}.")
        if not emptying and not running:
            return IDLE_SUMMARY if not undeployed else f"plants complete: undeployed {len(undeployed)} Terraformer(s)"
        parts = []
        if emptying:
            parts.append(f"emptying {', '.join(sorted(emptying))}")
        if running:
            parts.append(f"finishing {', '.join(sorted(running))}")
        return f"plants complete: {'; '.join(parts)}"
