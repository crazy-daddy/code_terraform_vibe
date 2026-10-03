# Shared base of the two rescue/charging station controllers: lib/charging.py
# (Vehicle Charging Station, ground vehicles) and lib/drone_service.py (Drone
# Service Station, drones). Both queue docked units for charge, watch the fleet,
# dispatch the station's rescue unit, and coordinate with every other station of
# their kind so only the nearest awake one acts on a unit.
#
# Subclasses set MODULE, PARK_KIND and DEFAULT_NAME, and implement
# all_station_refs(), manage_docked() and manage_fleet_rescues() (both return
# True while this station has work) and online_message().

from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester
from version_guard import validate_game_version


class StationController:
    MODULE = ""          # TreeConsole module and swallowed() prefix
    PARK_KIND = ""       # lib/script_parking.py kind (the station's type id)
    DEFAULT_NAME = ""    # name when the station exposes no id
    RETURN_SAFETY_MARGIN = 1.05
    # Poll cadence: ACTIVE while this station has work (bays charging or queued,
    # a rescue under way, a unit it is responsible for stranded/below floor/
    # heading home); IDLE otherwise.
    ACTIVE_POLL_SECONDS = 1.5
    IDLE_POLL_SECONDS = 5.0

    def __init__(self, station, target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", self.DEFAULT_NAME)
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")
        self.log = TreeConsole(module=self.MODULE)
        self.parker = ParkRequester(self.name, self.PARK_KIND)

    def all_station_refs(self):
        """[{"id": str, "coords": (x, y)}, ...] of every deployed station of this kind."""
        raise NotImplementedError

    def manage_docked(self):
        raise NotImplementedError

    def manage_fleet_rescues(self):
        raise NotImplementedError

    def online_message(self):
        raise NotImplementedError

    def my_coords(self):
        """This station's own coordinates, from the shared station-ref list."""
        for r in self.all_station_refs():
            if r["id"] == self.name:
                return r["coords"]
        return None

    def assess_stations(self, unit_ref, candidates, self_known):
        """
        One pass over candidate stations: (is_mine, nearest_distance, nearest_coords).
        Every deployed station runs its own copy of this script against the same
        fleet snapshot, so only the nearest one may act on a unit. is_mine is True
        when this station's own position is unknown (never deadlock silent), False
        when it is not among the candidates (e.g. a dry station for a heli),
        otherwise True unless another candidate is strictly closer.
        nearest_* are None when there are no candidates.
        """
        x = unit_ref.x
        y = unit_ref.y
        best = None
        best_coords = None
        mine = None
        for ref in candidates:
            coords = ref["coords"]
            dist_sq = (x - coords[0]) ** 2 + (y - coords[1]) ** 2
            if ref["id"] == self.name:
                mine = dist_sq
            if best is None or dist_sq < best:
                best = dist_sq
                best_coords = coords
        if not self_known:
            is_mine = True
        elif mine is None:
            is_mine = False
        else:
            is_mine = best is None or mine <= best
        return is_mine, (None if best is None else best ** 0.5), best_coords

    def is_station_powered(self):
        """Whether this station currently has grid power (True when unreadable)."""
        if self.power and hasattr(self.power, "is_powered"):
            try:
                return self.power.is_powered(self.name)
            except Exception as error:
                swallowed(f"{self.MODULE}.is_station_powered: self.power.is_powered", error)
        return True

    def step(self):
        """One supervision cycle for dock charging and field rescue; returns True while this station has work (poll fast)."""
        if not self.is_station_powered():
            self.parker.update(False)
            return False
        docked_busy = self.manage_docked()
        rescue_busy = self.manage_fleet_rescues()
        busy = docked_busy or rescue_busy
        self.parker.update(not busy)
        return busy

    def run(self, poll_interval=None, idle_poll_seconds=None):
        """Continuous supervision loop."""
        poll_interval = self.ACTIVE_POLL_SECONDS if poll_interval is None else poll_interval
        idle_poll_seconds = self.IDLE_POLL_SECONDS if idle_poll_seconds is None else idle_poll_seconds
        self.log.print(self.online_message())
        validate_game_version()
        while True:
            reset_all()
            busy = False
            try:
                busy = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error in supervision cycle: {e}")
            flush_all()
            sleep(poll_interval if busy else idle_poll_seconds)
