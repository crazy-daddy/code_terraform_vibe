# Drone mixin: charging and refuelling. Flies to a drone_service and waits
# while its station script charges/refuels: the home-service return
# (return_to_service_for_charge), the LAUNCH_MIN_SOC launch gate
# (hold_for_launch_charge) and the nearest-service refuel the floating hauler
# uses (go_to_nearest_service, refuel). Layer above DroneEnergyMixin (battery,
# budgets, service discovery wrappers) and DroneNavigationMixin
# (fly_to_station, fly_to); the role mixins call it. Station discovery is in
# lib/drone_depots.py. Mirrors lib/vehicle_charging.py.

from typing import TYPE_CHECKING

from script_parking import wake_for_visit
from tree_console import flush_all

if TYPE_CHECKING:
    from drone import DroneController
    from tree_console import TreeConsole

# Launch hysteresis: a drone below this state of charge tops up at its
# drone_service before starting a NEW mission, even if the trip itself is
# affordable. Without it a drone that just unloaded (depot and service share
# coords, so energy_needed_to_return_comfortably() is ~0 there) flew out on
# whatever charge was left (~26% seen), returned near the reserve floor, and
# cycled low. A floor only, never a ceiling: a far target needing more than
# this still falls through to the "none reachable" top-up-to-98% branch.
LAUNCH_MIN_SOC = 0.80
# Refuel/charge wait at a drone_service before giving up for this cycle.
REFUEL_TIMEOUT_S = 900.0
REFUEL_FULL_LEVEL = 0.98


class DroneChargingMixin:
    """
    Charging behavior mixed into DroneController: dock at a drone_service and
    wait for a charge/refuel. Depends on DroneEnergyMixin (get_battery,
    service wrappers, wh_to_reach) and DroneNavigationMixin (fly_to_station,
    fly_to, current_station).
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    LAUNCH_MIN_SOC = LAUNCH_MIN_SOC

    def return_to_service_for_charge(self, log: "TreeConsole", reason):
        """
        Flies to (and docks at) the home drone_service (get_home_service()),
        or the nearest one when the home service is out of reach on the
        current battery, unless already docked there. Shared by both the proactive low-battery return AND the
        "candidates exist but none reachable on current battery" idle
        fallback of the drone jobs (lib/drone_job.py charge_if_low(),
        top_up_if_unreachable()) -- without the latter, a drone whose battery
        is too low for ANY trip but still above
        energy_needed_to_return_comfortably() (i.e. it's in no danger where
        it's parked) would sit idling forever, since nothing else in the
        job ever sends it home to top up. Returns True if a return was
        issued, False if already at the service.
        """
        service_coords, service_info = self._host.get_home_service()
        curr_wh, _, _ = self._host.get_battery()
        home_wh = self._host.wh_to_reach(service_coords)
        if curr_wh < home_wh:
            nearest_coords, nearest_info = self._host.get_nearest_drone_service()
            if nearest_info.get("id") != service_info.get("id"):
                log.debug(f"[{self._host.name}] Home drone_service '{service_info.get('id')}' out of reach ({curr_wh:.1f} {self._host.energy_unit()} < {home_wh:.1f} {self._host.energy_unit()} needed); charging at nearest '{nearest_info.get('id')}' instead.")
                service_coords, service_info = nearest_coords, nearest_info
        service_id = service_info.get("id")
        if service_id:
            # Switches a parked station back on (lib/script_parking.py) and holds it
            # awake; hold_for_launch_charge() calls this again while we charge.
            wake_for_visit(service_id, f"{self._host.name} charging")
        # Docked-at check by id, not by coords: a Drone Depot and Drone
        # Service Station often share the same outpost coords, so a drone
        # hovering at (or queued for) the Depot would otherwise count as
        # "already at the service" and never dock there to charge.
        if service_id:
            if self._host.current_station() == service_id:
                return False
        elif self._host.is_at(service_coords, precision=3.0):
            return False
        log.start(f"[{self._host.name}] {reason}; returning to drone_service '{service_id or service_coords}'")
        self._host.publish_telemetry("RETURNING_TO_SERVICE")
        docked = bool(service_id) and self._host.fly_to_station(service_id, target_coords=service_coords)
        if not docked:
            docked = self._host.fly_to(service_coords[0], service_coords[1], precision=3.0)
        log.end(f"[{self._host.name}] Return to drone_service: {'arrived' if docked else 'not reached'}")
        return True

    def hold_for_launch_charge(self, log: "TreeConsole"):
        """
        Launch hysteresis gate, checked right before picking a new mission.
        Returns True (and sends/keeps the drone docked at its drone_service)
        while charge is below LAUNCH_MIN_SOC; the caller should sleep and
        re-check. Unreadable battery reads as 0%, so it fails safe to
        charging. Above the floor it still holds while the station's
        charge/refuel job runs: that job owns the drone, so every route
        call answers "busy" until the station's target level is reached.
        """
        _, _, lvl = self._host.get_battery()
        if lvl >= LAUNCH_MIN_SOC:
            status = self._host.status()
            if status not in ("charging", "refueling"):
                return False
            log.debug(f"[{self._host.name}] Launch gate: {lvl * 100:.0f}% but station job still {status}; waiting for it to finish.")
            self._host.publish_telemetry("CHARGING")
            return True
        log.debug(f"[{self._host.name}] Launch gate: {lvl * 100:.0f}% < {LAUNCH_MIN_SOC * 100:.0f}% launch floor; charging before next mission.")
        self._host.return_to_service_for_charge(log, f"Topping up before launch ({lvl * 100:.0f}%)")
        self._host.publish_telemetry("CHARGING")
        return True

    def docked_at_service(self):
        station = self._host.current_station()
        return bool(station) and any(s["id"] == station for s in self._host.get_all_drone_services())

    def go_to_nearest_service(self, reason):
        """Docks at the nearest (engine-suitable) drone_service unless already docked at one. False if none/unreachable."""
        if self._host.docked_at_service():
            return True
        coords, info = self._host.get_nearest_drone_service()
        service_id = info.get("id")
        if not service_id:
            self._host.log.level("warn").print(f"[{self._host.name}] {reason}, but no drone_service_station is deployed.")
            return False
        self._host.log.debug(f"[{self._host.name}] {reason}; heading to drone_service '{service_id}'.")
        wake_for_visit(service_id, f"{self._host.name} refuelling")
        return self._host.fly_to_station(service_id, target_coords=coords)

    def refuel(self, needed, reason):
        """Refuels at a drone_service inside a log block; see refuel_at_service()."""
        self._host.log.start(f"[{self._host.name}] Refuelling: {reason}")
        ok = self._host.refuel_at_service(needed, reason)
        self._host.log.end("refuelled" if ok else "not refuelled")
        return ok

    def refuel_at_service(self, needed, reason):
        """
        Flies to the nearest drone_service and waits while its station
        script charges/refuels this drone, until full (REFUEL_FULL_LEVEL) or
        at least `needed` with the service job finished. False on timeout or
        when no service is reachable.
        """
        self._host.publish_telemetry("REFUELING", reason)
        if not self._host.go_to_nearest_service(reason):
            return False
        waited = 0.0
        warned_oil = False
        while waited < REFUEL_TIMEOUT_S:
            level, _cap, frac = self._host.get_battery()
            status = self._host.status()
            if frac >= REFUEL_FULL_LEVEL or (level >= needed and status not in ("charging", "refueling", "waiting_service")):
                self._host.log.debug(f"[{self._host.name}] Refuel done: {level:.1f} {self._host.energy_unit()} ({frac * 100:.0f}%), status={status}.")
                return True
            if int(waited) % 30 == 0:
                wake_for_visit(self._host.current_station(), f"{self._host.name} refuelling")
            if status == "waiting_oil" and not warned_oil:
                self._host.log.level("warn").print(f"[{self._host.name}] Service station has no oil; waiting.")
                warned_oil = True
            flush_all()
            sleep(2.0)
            waited += 2.0
        self._host.log.level("warn").print(f"[{self._host.name}] Refuel timed out after {REFUEL_TIMEOUT_S:.0f}s.")
        return False
