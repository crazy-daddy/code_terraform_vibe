# Shared base of the two rescue/charging station controllers: lib/charging.py
# (Vehicle Charging Station, ground vehicles) and lib/drone_service.py (Drone
# Service Station, drones). Both queue docked units for charge, watch the fleet,
# dispatch the station's rescue unit, and coordinate with every other station of
# their kind so only the nearest awake one acts on a unit.
#
# Subclasses set MODULE, PARK_KIND, DEFAULT_NAME, RESCUER and RESCUE_STATUSES,
# and implement all_station_refs(), manage_docked() (True while this station
# has work), online_message() and the rescue hooks of manage_fleet_rescues()
# (rescue_units(), rescue_fuel(), return_floor_wh(), rescue_target_level(),
# _dispatch_rescue(); rescue_candidates() when not every station serves a unit).

from machine_controller import MachineController
from parking_client import ParkRequester, parked_ids, parked_nearest, wake_for_visit
from swallow import swallowed
from tree_console import TreeConsole


class StationController(MachineController):
    LABEL = "Station"

    def next_sleep(self, result, failed):
        return self.ACTIVE_POLL_SECONDS if not failed and result else self.IDLE_POLL_SECONDS

    MODULE = ""  # TreeConsole module and swallowed() prefix
    PARK_KIND = ""  # lib/script_parking.py kind (the station's type id)
    DEFAULT_NAME = ""  # name when the station exposes no id
    RETURN_SAFETY_MARGIN = 1.05
    # Poll cadence: ACTIVE while this station has work (bays charging or queued,
    # a rescue under way, a unit it is responsible for stranded/below floor/
    # heading home); IDLE otherwise.
    ACTIVE_POLL_SECONDS = 1.5
    IDLE_POLL_SECONDS = 5.0
    RESCUER = "Rescue unit"  # what the station dispatches, for log lines
    RESCUE_STATUSES = ()  # unit status() values that mean stranded

    def __init__(self, station: "ChargingStation | DroneServiceStation", target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", self.DEFAULT_NAME)
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")
        self.log = TreeConsole(module=self.MODULE)
        self.parker = ParkRequester(self.name, self.PARK_KIND)
        self.last_rescued = None  # unit the rescue unit was last reported assisting

    def all_station_refs(self):
        """[{"id": str, "coords": (x, y)}, ...] of every deployed station of this kind."""
        raise NotImplementedError

    def manage_docked(self):
        raise NotImplementedError

    # ---------- rescue loop hooks

    def rescue_units(self, fleet):
        """The `fleet` refs this kind of station watches (fleet.vehicles() / fleet.drones())."""
        raise NotImplementedError

    def rescue_candidates(self, unit_ref, refs, memo):
        """Station refs that can serve unit_ref (memo: a dict for this pass); None skips the unit."""
        return refs

    def rescue_fuel(self, unit_ref):
        """(Wh or t, level 0..1) of unit_ref's battery or tank."""
        raise NotImplementedError

    def return_floor_wh(self, unit_ref, distance=None):
        """Fuel unit_ref needs to reach a station `distance` m away under its own power."""
        raise NotImplementedError

    def rescue_target_level(self, unit_ref, floor=None):
        """Level the rescue unit charges unit_ref to."""
        raise NotImplementedError

    def _dispatch_rescue(self, unit_ref, is_stranded, wh, target_level, floor):
        """Announces distress and dispatches the rescue unit; True when the loop over units should stop."""
        raise NotImplementedError

    def manage_fleet_rescues(self):
        """
        Watches every unit of rescue_units() in the field. Only the nearest awake station
        acts on a unit; a unit whose nearest station is parked gets that station woken.
        A stranded unit (RESCUE_STATUSES) or one at or below its return floor gets the
        rescue unit; one only below its rescue target is watched (its own script budgets
        the way back). True while a rescue is in progress or a unit this station is
        responsible for is stranded, below floor or heading home.
        """
        if self.station.is_rescuing():
            target_name = self.station.get_rescue_target()
            if target_name and target_name != self.last_rescued:
                self.last_rescued = target_name
                self.log.print(f"[{self.name}] {self.RESCUER} currently in field assisting: {target_name}.")
            return True

        self.last_rescued = None
        if not self.fleet:
            return False
        try:
            units = self.rescue_units(self.fleet)
        except Exception as error:
            swallowed("station_controller.StationController.manage_fleet_rescues: rescue_units", error)
            return False

        # Parked stations (lib/script_parking.py) take no responsibility; a unit
        # needing attention whose nearest station is parked gets that station
        # woken instead, so the nearest station still watches and rescues it.
        refs = self.all_station_refs()
        parked = parked_ids(self.PARK_KIND)
        parked.discard(self.name)  # running, so awake whatever the archive says
        self_known = any(r["id"] == self.name for r in refs)
        verbose = self.log.verbose
        memo = {}
        busy = False
        for u_ref in units:
            if u_ref.is_docked or u_ref.is_being_rescued or u_ref.rescue_status != "none":
                continue
            candidates = self.rescue_candidates(u_ref, refs, memo)
            if candidates is None:
                continue
            # Every deployed station runs this same script against the same fleet
            # snapshot: only the nearest one acts, or every station in range would
            # dispatch its own rescue unit to the same unit.
            awake = [r for r in candidates if r["id"] not in parked] if parked else candidates
            is_mine, distance, _nearest = self.assess_stations(u_ref, awake, self_known)
            if not is_mine:
                continue

            # A unit's own drive never willingly drains below its return floor, so it can
            # sit there without ever registering as stranded: the floor is the backstop.
            is_stranded = u_ref.status in self.RESCUE_STATUSES
            wh, lvl = self.rescue_fuel(u_ref)
            floor = 0.0 if distance is None else self.return_floor_wh(u_ref, distance)
            target_level = self.rescue_target_level(u_ref, floor)
            is_below_floor = wh <= floor
            if verbose:
                self.log.trace(f"[{self.name}] Fleet check {u_ref.id}: status='{u_ref.status}', level={lvl * 100:.0f}%, fuel={wh:.1f}, return_floor={floor:.1f}, target_level={target_level * 100:.0f}%, stranded={is_stranded}, below_floor={is_below_floor}.")

            if parked and (is_stranded or is_below_floor or lvl < target_level):
                handoff = parked_nearest(u_ref, candidates, parked, distance)
                if handoff:
                    busy = True
                    wake_for_visit(handoff, f"{u_ref.name} needs its nearest station")
                    self.log.print(f"[{self.name}] {u_ref.name} ({lvl * 100:.0f}%) is nearest to parked '{handoff}'; woke it to take over.")
                    continue

            if is_stranded or is_below_floor:
                busy = True
                if self._dispatch_rescue(u_ref, is_stranded, wh, target_level, floor):
                    break
            elif lvl < target_level:
                busy = True
                self.log.debug(f"{u_ref.name}: level {lvl * 100:.0f}% below rescue target {target_level * 100:.0f}%, not yet stranded/below-floor; watching (it returns on its own budget).")
        return busy

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
        return is_mine, (None if best is None else best**0.5), best_coords

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
