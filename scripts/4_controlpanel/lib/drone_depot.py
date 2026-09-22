# Shared Library for Drone Depot (cargo logistics endpoint) automation.
#
# Mostly passive: no active drain/rescue-style verb exists for a Depot --
# cargo moves via the drone's own cargo.load()/unload() while docked, and
# ports drain passively once connected (same pattern as Warehouse Auto
# Feeders elsewhere in this codebase). This controller's job is (1) one-time
# idempotent port wiring to the outpost's Essence Liquifier, only when
# unambiguous, and (2) lightweight periodic telemetry.

from archive import archive
from tree_console import TreeConsole
from version_guard import validate_game_version

DEPOT_STATUS_KEY_PREFIX = "drone_depot.status."
LIQUIFIER_TYPE_ID = "essence_liquifier"


class DroneDepotController:
    """Automates a Drone Depot: idempotent output wiring + periodic telemetry publish."""

    def __init__(self, station):
        self.station = station
        self.name = getattr(station, "id", "drone_station")
        self._wired = False
        self.log = TreeConsole(module="drone_depot")

    def _find_local_liquifier(self):
        """
        The single same-outpost Essence Liquifier, or None if there isn't
        exactly one -- wiring only when unambiguous (exactly one candidate)
        per the plan, never guessing between several.
        """
        outpost = getattr(self.station, "outpost", None)
        if not outpost or not hasattr(outpost, "buildings"):
            return None
        try:
            liquifiers = outpost.buildings(LIQUIFIER_TYPE_ID)
        except Exception:
            return None
        if len(liquifiers) != 1:
            if len(liquifiers) > 1:
                self.log.level("warn").print(f"[{self.name}] {len(liquifiers)} Essence Liquifiers found at this outpost; leaving output unwired for manual routing.")
            else:
                self.log.debug(f"[{self.name}] No Essence Liquifier found at this outpost; nothing to wire yet.")
            return None
        return get_component(liquifiers[0].id)

    def wire_output_to_liquifier(self):
        """
        One-time idempotent port wiring: connects this Depot's .output to
        the outpost's Essence Liquifier .input, ONLY when unambiguous
        (exactly one same-outpost Liquifier). Otherwise logs once and
        leaves it for manual wiring via the Control Panel.
        """
        if self._wired:
            return
        if not hasattr(self.station, "output"):
            self.log.debug(f"[{self.name}] Station has no .output port; skipping wiring check.")
            return
        liquifier = self._find_local_liquifier()
        if liquifier is None:
            return

        try:
            connected_to = self.station.output.connected_to() if hasattr(self.station.output, "connected_to") else None
            if connected_to == liquifier.id:
                self.log.debug(f"[{self.name}] Output already wired to '{liquifier.id}'; marking wired without reconnecting.")
                self._wired = True
                return
            self.log.debug(f"[{self.name}] Output not yet wired (currently connected_to={connected_to!r}); connecting to '{liquifier.id}'.")
            res = self.station.output.connect(liquifier.id)
            if getattr(res, "status", "") == "ok":
                self.log.print(f"[{self.name}] Wired output -> Essence Liquifier '{liquifier.id}'.")
                self._wired = True
            else:
                self.log.level("warn").print(f"[{self.name}] Output wiring to '{liquifier.id}' notice: {res.status} - {res.message}")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Could not wire output to Essence Liquifier: {e}")

    def publish_telemetry(self):
        """
        Lightweight periodic telemetry publish (bay/slot occupancy) to
        archive, mirroring VehicleController.publish_telemetry()'s
        bounded/compact style -- useful for dashboards and for miner/scout
        drones' own "is my depot full" decisions.
        """
        self.log.trace(f"[{self.name}] publish_telemetry() entry.")
        try:
            docked = list(self.station.get_docked())
        except Exception:
            docked = []
        try:
            bay_count = self.station.bay_count()
            bays_occupied = self.station.bays_occupied()
        except Exception:
            bay_count = bays_occupied = 0
        try:
            slots_used = self.station.slots_used()
            slot_capacity = self.station.slot_capacity()
        except Exception:
            slots_used = slot_capacity = 0

        telemetry = {
            "name": self.name,
            "docked": docked,
            "bay_count": bay_count,
            "bays_occupied": bays_occupied,
            "slots_used": slots_used,
            "slot_capacity": slot_capacity,
            "is_full": slot_capacity > 0 and slots_used >= slot_capacity,
        }
        archive.set(f"{DEPOT_STATUS_KEY_PREFIX}{self.name}", telemetry)
        self.log.trace(f"[{self.name}] publish_telemetry() exit: bays {bays_occupied}/{bay_count}, slots {slots_used}/{slot_capacity}.")

    def step(self):
        self.wire_output_to_liquifier()
        self.publish_telemetry()

    def run(self, poll_interval=10.0):
        bay_count = getattr(self.station, "bay_count", lambda: 1)()
        self.log.print(f"Drone Depot Controller ({self.name}) online ({bay_count} bay(s)).")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error in supervision cycle: {e}")
            sleep(poll_interval)
