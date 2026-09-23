# Drone mixin: drone-specific linear Wh/meter energy model, round-trip trip
# budgeting, and drone_service/drone_depot discovery. Mirrors
# vehicle_energy.py's "there-and-back" safety-margin + hard emergency-reserve
# floor pattern, but with a DIFFERENT (simpler, linear) travel model and TWO
# distinct "home" endpoints -- drone_service (power) and drone_depot (cargo)
# -- rather than ground vehicles' single combined base/charging-station pair.
#
# Game-confirmed constants (docs/components/drone.md): full throttle = 5 Wh/h
# burn, 300 m/h speed; both scale with throttle (speed linear, burn
# quadratic) -- collapsing to a flat linear Wh/meter model, structurally like
# Rover's own flat model (lib/vehicle_energy.py's ROVER_WH_PER_METER_PER_THROTTLE),
# just a different constant. Treat the drone's own range_remaining() as
# ground truth; this formula is for PLANNING only (trip feasibility, throttle
# selection), verified against the drone's live battery before committing.
# Scan/extract themselves cost no extra travel Wh in the documented model
# (hovering at throttle 0 costs 0), so there's deliberately no scan/extract
# term in calculate_trip_energy() below, unlike VehicleEnergyMixin's sonar/
# mining budget terms.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

DRONE_SERVICE_TYPE_ID = "drone_service_station"
# The in-game building's typeId is "drone_station", NOT "drone_depot" --
# "Drone Depot" is only the display name (docs/components/drone_depot.md's
# own item/recipe ids confirm the real scheme: "drone_station_kit",
# ship_computer.md's "missing_drone_station"/"drone_station_full"). Verified
# against a live save's building record: {"typeId":"drone_station", ...}
# under a "drone_station_2" instance id. Using "drone_depot" here silently
# made outpost.buildings() match nothing, so get_all_drone_depots() was
# always empty and every caller (home_coords/home_outpost resolution,
# _return_and_unload(), recall) fell back to (0.0, 0.0) with no depot id at
# all (bug found 2026-09-22 via a drone recall flying toward world origin).
DRONE_DEPOT_TYPE_ID = "drone_station"

# 5.0 Wh/h at 300 m/h full-throttle burn -> flat Wh/meter-per-throttle rate.
DRONE_WH_PER_METER_PER_THROTTLE = 5.0 / 300.0  # ~0.01667 Wh/m at throttle 1.0
MIN_SPEEDMODE_THROTTLE = 0.10
MAX_SPEEDMODE_THROTTLE = 1.0
SAFETY_MARGIN_MULTIPLIER = 1.05

# Smaller than VehicleEnergyMixin.MIN_EMERGENCY_RESERVE_WH=8.0 -- electric
# drone batteries are much smaller than a Rover/Pioneer's, so an 8 Wh floor
# would eat a large fraction of total capacity. Tune here and update
# docs/AI_CHEATSHEET.md's drone energy-budgeting section in the same change.
MIN_EMERGENCY_RESERVE_WH = 4.0

# Launch hysteresis: a drone below this state of charge tops up at its
# drone_service before starting a NEW mission, even if the trip itself is
# affordable. Without it a drone that just unloaded (depot and service share
# coords, so energy_needed_to_return_comfortably() is ~0 there) flew out on
# whatever charge was left (~26% seen), returned near the reserve floor, and
# cycled low. A floor only, never a ceiling: a far target needing more than
# this still falls through to the "none reachable" top-up-to-98% branch.
LAUNCH_MIN_SOC = 0.80

DEFAULT_CRUISE_THROTTLE_KEY = "drone.default_cruise_throttle"
DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5

# Pinned drone homes (see resolve_home_depot()): ONE shared dict
# {drone_name: outpost_id (pool) or depot_id (hardwired)}, like
# drone_claims.py's drone.recall, not a key per
# drone. Bounded by fleet size; entries of drones that no longer exist are
# pruned on every write.
HOME_DEPOTS_KEY = "drone.home_depots"


def _pin_home_depot(drone_name, depot_id):
    def updater(pins):
        if not isinstance(pins, dict):
            pins = {}
        pins[drone_name] = depot_id
        fleet = get_component("fleet")
        if fleet and hasattr(fleet, "drones"):
            try:
                live = {getattr(d, "id", "") for d in fleet.drones()}
            except Exception:
                live = set()
            if live:
                pins = {name: pin for name, pin in pins.items() if name in live or name == drone_name}
        return pins

    archive.transaction(HOME_DEPOTS_KEY, {}, updater)


def drone_wh_per_meter_at_throttle(throttle):
    """
    Standalone: linear Wh/meter for ANY electric drone at the given
    throttle -- no drone object needed, since the documented model has no
    per-drone/cargo/module term (unlike Pioneer's travel formula), just one
    flat rate for every electric drone.
    """
    if throttle <= 0:
        return 0.0
    return DRONE_WH_PER_METER_PER_THROTTLE * throttle


def drone_rescue_wh_per_meter():
    """
    Worst-case-safe Wh/meter for rescue/return budgeting, at the speedmode
    throttle floor -- mirrors vehicle_energy.py's rescue_wh_per_meter_for(),
    but needs no drone object at all since the model is a flat per-throttle
    rate with no vehicle-specific terms.
    """
    return drone_wh_per_meter_at_throttle(MIN_SPEEDMODE_THROTTLE)


def _extract_coords(pos):
    if pos is None:
        return None
    if isinstance(pos, (tuple, list)) and len(pos) >= 2:
        return (float(pos[0]), float(pos[1]))
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is not None and y is not None:
        return (float(x), float(y))
    return None


def discover_drone_buildings(type_id):
    """
    Standalone: every deployed building of type_id (drone_service_station or
    drone_depot) across every owned outpost, as
    [{"id": str, "name": str, "coords": (x, y), "outpost": OutpostRef|None,
    "outpost_id": str}, ...]. Mirrors
    vehicle_energy.py's get_all_charging_stations() discovery shape, but
    module-level so both DroneEnergyMixin and lib/drone_service.py's own
    station-side nearest-station arbitration (mirroring charging.py's
    is_nearest_station_to()) can share one implementation.
    """
    refs = []
    found_ids = set()
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            outposts = network.outposts()
        except Exception:
            outposts = []
        for outpost in outposts:
            if not hasattr(outpost, "buildings"):
                continue
            try:
                buildings = outpost.buildings(type_id)
            except Exception:
                continue
            for b in buildings:
                b_id = getattr(b, "id", "")
                if not b_id or b_id in found_ids:
                    continue
                pos = _extract_coords(getattr(b, "position", None))
                if not pos:
                    continue
                found_ids.add(b_id)
                refs.append({
                    "id": b_id,
                    "name": getattr(b, "name", "") or "",
                    "coords": pos,
                    "outpost": getattr(b, "outpost", None),
                    "outpost_id": getattr(b, "outpost_id", "") or "",
                })
    return refs


def discover_drone_services():
    return discover_drone_buildings(DRONE_SERVICE_TYPE_ID)


def discover_drone_depots():
    return discover_drone_buildings(DRONE_DEPOT_TYPE_ID)


class DroneEnergyMixin:
    """
    Battery telemetry, linear travel Wh/meter model, and drone_service/
    drone_depot discovery, mixed into DroneController. Depends on
    DroneNavigationMixin for position()/distance_between().
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    DRONE_WH_PER_METER_PER_THROTTLE = DRONE_WH_PER_METER_PER_THROTTLE
    MIN_SPEEDMODE_THROTTLE = MIN_SPEEDMODE_THROTTLE
    MAX_SPEEDMODE_THROTTLE = MAX_SPEEDMODE_THROTTLE
    SAFETY_MARGIN_MULTIPLIER = SAFETY_MARGIN_MULTIPLIER
    MIN_EMERGENCY_RESERVE_WH = MIN_EMERGENCY_RESERVE_WH
    LAUNCH_MIN_SOC = LAUNCH_MIN_SOC

    def default_cruise_throttle(self):
        value = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, None)
        if value is None:
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        try:
            value = float(value)
        except (TypeError, ValueError):
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        return max(self.MIN_SPEEDMODE_THROTTLE, min(self.MAX_SPEEDMODE_THROTTLE, value))

    def get_battery(self):
        """
        Returns (current_wh, capacity_wh, fraction 0-1). Electric drones only
        this pass -- .battery raises ReferenceError on a heli drone (see
        drone.md); DroneController is only ever constructed for an electric
        DroneRef this pass (heli support deferred, see the module docstring
        in lib/drone.py).
        """
        try:
            wh = self._host.drone.battery.level()
            cap = self._host.drone.battery.capacity()
            lvl = self._host.drone.battery.percent()
            return wh, cap, lvl
        except Exception:
            return 0.0, 100.0, 0.0

    def wh_per_meter_at_throttle(self, throttle):
        return drone_wh_per_meter_at_throttle(throttle)

    def minimum_wh_per_meter(self):
        return self.wh_per_meter_at_throttle(self.MIN_SPEEDMODE_THROTTLE)

    def energy_wh_for_leg(self, distance_m, throttle):
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        return distance_m * self.wh_per_meter_at_throttle(throttle)

    def get_all_drone_services(self):
        return discover_drone_services()

    def get_all_drone_depots(self):
        return discover_drone_depots()

    def get_nearest_drone_service(self, from_coords=None):
        """
        Returns (coords, station_info_dict) for the nearest drone_service_station
        -- this drone's power "home". Falls back to (0.0, 0.0)/{} when none is
        deployed yet, EXCEPT it prefers self.home_coords if already resolved
        (getattr default avoids an AttributeError during DroneController.__init__,
        before self.home_coords is assigned).
        """
        ref_coords = from_coords if from_coords is not None else self._host.position()
        stations = self.get_all_drone_services()
        if not stations:
            fallback = getattr(self, "home_coords", (0.0, 0.0))
            self._host.log.trace(f"[{self._host.name}] get_nearest_drone_service: no drone_service_station deployed yet; falling back to home_coords {fallback}.")
            return fallback, {"id": "", "coords": fallback}
        best = min(stations, key=lambda st: self._host.distance_between(ref_coords, st["coords"]))
        self._host.log.trace(f"[{self._host.name}] get_nearest_drone_service: {len(stations)} candidate(s) from {ref_coords}, nearest '{best.get('id')}' at {best['coords']} ({self._host.distance_between(ref_coords, best['coords']):.1f}m).")
        return best["coords"], best

    def get_nearest_drone_depot(self, from_coords=None):
        """
        Returns (coords, depot_info_dict) for the nearest drone_depot -- this
        drone's cargo "home", a DISTINCT endpoint from get_nearest_drone_service()
        (see module docstring). Same fallback shape as get_nearest_drone_service().
        """
        ref_coords = from_coords if from_coords is not None else self._host.position()
        depots = self.get_all_drone_depots()
        if not depots:
            fallback = getattr(self, "home_coords", (0.0, 0.0))
            self._host.log.trace(f"[{self._host.name}] get_nearest_drone_depot: no drone_depot deployed yet; falling back to home_coords {fallback}.")
            return fallback, {"id": "", "coords": fallback}
        best = min(depots, key=lambda d: self._host.distance_between(ref_coords, d["coords"]))
        self._host.log.trace(f"[{self._host.name}] get_nearest_drone_depot: {len(depots)} candidate(s) from {ref_coords}, nearest '{best.get('id')}' at {best['coords']} ({self._host.distance_between(ref_coords, best['coords']):.1f}m).")
        return best["coords"], best

    def resolve_home_depot(self, home_depot=None):
        """
        Picks and pins this drone's home. The home is either one specific
        Drone Depot ("hardwired") or a whole outpost ("pool": any depot in
        that outpost; get_home_depot() picks a free one per trip, since all
        depots of an outpost share its coords). Sets
        self._host.home_depot_pool to the pool's outpost id, or None when
        hardwired. Returns a representative depot info dict (coords/outpost
        for home_biome etc.), or {} when no Depot is deployed. Priority:
          1. home_depot override (the HOME_DEPOT script variable): a depot
             id or display name (hardwired), or an outpost id (pool).
          2. The pin persisted in archive by a previous run (depot id or
             outpost id, same matching), so a script restart while the drone
             is out in the field does not re-home it to whichever depot
             happens to be nearest there.
          3. Nearest depot to the drone's current position (first run),
             pinned as a pool of that depot's outpost.
        The pin is written back to archive (HOME_DEPOTS_KEY dict).
        """
        self._host.home_depot_pool = None
        depots = self.get_all_drone_depots()
        if not depots:
            self._host.log.debug(f"[{self._host.name}] resolve_home_depot(): no Drone Depot deployed; no home depot.")
            return {}

        def match(wanted):
            """(representative_depot, pool_outpost_id or None) for a depot id/name or outpost id."""
            depot = next((d for d in depots if wanted in (d["id"], d.get("name"))), None)
            if depot:
                return depot, None
            pool = [d for d in depots if d.get("outpost_id") == wanted]
            if pool:
                return pool[0], wanted
            return None, None

        chosen, pool_id, source = None, None, None
        if home_depot:
            wanted = str(home_depot)
            chosen, pool_id = match(wanted)
            if chosen:
                source = "HOME_DEPOT override"
            else:
                self._host.log.level("warn").print(f"[{self._host.name}] HOME_DEPOT '{wanted}' matches no Drone Depot id, name or outpost id; falling back to auto-detection.")
        if chosen is None:
            pins = archive.get(HOME_DEPOTS_KEY, {}) or {}
            pinned = pins.get(self._host.name) if isinstance(pins, dict) else None
            if pinned:
                chosen, pool_id = match(str(pinned))
                if chosen:
                    source = "archived pin"
                else:
                    self._host.log.debug(f"[{self._host.name}] resolve_home_depot(): archived pin '{pinned}' no longer exists; re-resolving.")
        if chosen is None:
            _, chosen = self.get_nearest_drone_depot()
            pool_id = chosen.get("outpost_id") or None
            source = "nearest to current position"

        self._host.home_depot_pool = pool_id
        _pin_home_depot(self._host.name, pool_id or chosen["id"])
        home_desc = f"any Drone Depot in '{pool_id}'" if pool_id else f"Drone Depot '{chosen['id']}' (hardwired)"
        self._host.log.debug(f"[{self._host.name}] Home pinned to {home_desc} via {source}.")
        return chosen

    def _home_depot_candidates(self):
        """Live depot dicts making up this drone's home (the pool outpost's depots, or the one hardwired depot)."""
        depots = self.get_all_drone_depots()
        pool_id = getattr(self._host, "home_depot_pool", None)
        if pool_id:
            return [d for d in depots if d.get("outpost_id") == pool_id]
        depot_id = (getattr(self._host, "home_depot", None) or {}).get("id")
        return [d for d in depots if d["id"] == depot_id] if depot_id else []

    def _pick_free_depot(self, candidates, prefer_id=None):
        """
        Best depot of candidates for this trip: the one this drone is
        already docked at, else free bay first, then prefer_id (the depot
        already queued for, so an all-full pool doesn't churn between
        queues), then free cargo slots, then nearest. Bay/slot counts are read live via get_component(depot_id);
        an unreadable depot sorts as full but stays eligible.
        """
        current = self._host.current_station()
        for d in candidates:
            if d["id"] == current:
                return d
        if len(candidates) == 1:
            return candidates[0]

        pos = self._host.position()
        scored = []
        for d in candidates:
            free_bays, free_slots = 0, 0
            try:
                depot = get_component(d["id"])
                if depot is not None:
                    free_bays = depot.bay_count() - depot.bays_occupied()
                    free_slots = depot.slot_capacity() - depot.slots_used()
            except Exception as e:
                self._host.log.debug(f"[{self._host.name}] _pick_free_depot(): could not read '{d['id']}': {e}")
            scored.append(((free_bays <= 0, d["id"] != prefer_id, free_slots <= 0, self._host.distance_between(pos, d["coords"]), d["id"]), d, free_bays, free_slots))
        scored.sort(key=lambda s: s[0])
        self._host.log.debug(
            f"[{self._host.name}] _pick_free_depot(): "
            + ", ".join(f"{d['id']}(bays free={fb}, slots free={fs})" for _, d, fb, fs in scored)
            + f" -> '{scored[0][1]['id']}'."
        )
        return scored[0][1]

    def get_home_depot(self, prefer_id=None):
        """
        Returns (coords, depot_info_dict) for the depot this drone should use
        now -- where it unloads and re-equips, regardless of which depot is
        nearest right now. With a pool home, re-picks per call so a drone
        never queues for a busy depot while a sibling in the same outpost
        is free (see _pick_free_depot()). Re-homes
        (DroneController.resolve_home()) when the home no longer has any
        depot. Same fallback shape as get_nearest_drone_depot() when no
        depot exists at all.
        """
        candidates = self._home_depot_candidates()
        if not candidates:
            if getattr(self._host, "home_depot", None):
                # resolve_home_depot() skips (and overwrites) the stale pin itself.
                self._host.log.level("warn").print(f"[{self._host.name}] Home Drone Depot no longer exists; re-homing.")
            self._host.resolve_home()
            candidates = self._home_depot_candidates()
        if candidates:
            depot = self._pick_free_depot(candidates, prefer_id=prefer_id)
            return depot["coords"], depot
        return self.get_nearest_drone_depot()

    def get_home_service(self):
        """
        Returns (coords, station_info_dict) for this drone's home
        drone_service: the one in the home depot's outpost (nearest to the
        depot if there are several), else the service nearest to the home
        depot. Falls back to get_nearest_drone_service() without a home
        depot. This is the PLANNING/charging target; the hard in-flight
        survival floor (return_floor_wh()) still uses the nearest service.
        """
        depot = getattr(self._host, "home_depot", None) or {}
        services = self.get_all_drone_services()
        if not depot or not services:
            return self.get_nearest_drone_service()
        depot_coords = depot["coords"]
        same_outpost = [s for s in services if depot.get("outpost_id") and s.get("outpost_id") == depot.get("outpost_id")]
        pool = same_outpost or services
        best = min(pool, key=lambda s: self._host.distance_between(depot_coords, s["coords"]))
        return best["coords"], best

    def wh_to_reach(self, target_coords, from_coords=None):
        """Reserve-inclusive Wh to reach target_coords at the speedmode throttle floor."""
        pos = from_coords if from_coords is not None else self._host.position()
        dist = self._host.distance_between(pos, target_coords)
        return (dist * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def return_floor_wh(self, from_coords=None):
        """
        Wh needed on board right now to safely reach the nearest drone_service
        (power home) at the speedmode throttle floor -- the hard survival
        floor, mirroring vehicle_energy.py's energy_needed_to_return_now().
        Deliberately the NEAREST service, not the home one: this is the
        in-flight abort threshold, where any charger is better than none.
        """
        pos = from_coords if from_coords is not None else self._host.position()
        nearest, _ = self.get_nearest_drone_service(from_coords=pos)
        return self.wh_to_reach(nearest, from_coords=pos)

    def energy_needed_to_return_now(self):
        return self.return_floor_wh()

    def energy_needed_to_return_comfortably(self):
        """
        Same as return_floor_wh() but at self.cruise_throttle rather than the
        speedmode floor -- the proactive "time to head back" trigger for field
        loops, not the hard abort (mirrors VehicleEnergyMixin's own
        floor-vs-comfortable distinction). Measured to the HOME service,
        since that's where return_to_service_for_charge() heads first.
        """
        pos = self._host.position()
        home_service, _ = self.get_home_service()
        dist = self._host.distance_between(pos, home_service)
        drive_wh = dist * self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def return_to_service_for_charge(self, log, reason):
        """
        Flies to (and docks at) the home drone_service (get_home_service()),
        or the nearest one when the home service is out of reach on the
        current battery, unless already docked there. Shared by both the proactive low-battery return AND the
        "candidates exist but none reachable on current battery" idle
        fallback in run_scout_loop()/run_miner_loop() -- without the latter,
        a drone whose battery is too low for ANY trip but still above
        energy_needed_to_return_comfortably() (i.e. it's in no danger where
        it's parked) would sit idling forever, since nothing else in the
        loop ever sends it home to top up. Returns True if a return was
        issued, False if already at the service.
        """
        service_coords, service_info = self.get_home_service()
        curr_wh, _, _ = self.get_battery()
        home_wh = self.wh_to_reach(service_coords)
        if curr_wh < home_wh:
            nearest_coords, nearest_info = self.get_nearest_drone_service()
            if nearest_info.get("id") != service_info.get("id"):
                log.debug(f"[{self._host.name}] Home drone_service '{service_info.get('id')}' out of reach ({curr_wh:.1f} Wh < {home_wh:.1f} Wh needed); charging at nearest '{nearest_info.get('id')}' instead.")
                service_coords, service_info = nearest_coords, nearest_info
        service_id = service_info.get("id")
        # Docked-at check by id, not by coords: a Drone Depot and Drone
        # Service Station often share the same outpost coords, so a drone
        # hovering at (or queued for) the Depot would otherwise count as
        # "already at the service" and never dock there to charge.
        if service_id:
            if self._host.current_station() == service_id:
                return False
        elif self._host.is_at(service_coords, precision=3.0):
            return False
        log.debug(f"[{self._host.name}] {reason}; returning to drone_service.")
        self._host.publish_telemetry("RETURNING_TO_SERVICE")
        if not (service_id and self._host.fly_to_station(service_id, target_coords=service_coords)):
            self._host.fly_to(service_coords[0], service_coords[1], precision=3.0)
        return True

    def hold_for_launch_charge(self, log):
        """
        Launch hysteresis gate, checked right before picking a new mission.
        Returns True (and sends/keeps the drone docked at its drone_service)
        while charge is below LAUNCH_MIN_SOC; the caller should sleep and
        re-check. Unreadable battery reads as 0%, so it fails safe to
        charging.
        """
        _, _, lvl = self.get_battery()
        if lvl >= self.LAUNCH_MIN_SOC:
            return False
        log.debug(f"[{self._host.name}] Launch gate: {lvl*100:.0f}% < {self.LAUNCH_MIN_SOC*100:.0f}% launch floor; charging before next mission.")
        self.return_to_service_for_charge(log, f"Topping up before launch ({lvl*100:.0f}%)")
        self._host.publish_telemetry("CHARGING")
        return True

    def calculate_trip_energy(self, target_coords, wh_per_meter=None):
        """
        Round-trip budget: outbound flight to target_coords + return flight
        from target_coords to the home drone_service (get_home_service() --
        where the drone actually goes back to, not whichever service happens
        to be nearest the target),
        buffered by SAFETY_MARGIN_MULTIPLIER plus a hard
        MIN_EMERGENCY_RESERVE_WH floor. No scan/extract term (see module
        docstring).
        """
        current_pos = self._host.position()
        dist_outbound = self._host.distance_between(current_pos, target_coords)
        nearest_service, _ = self.get_home_service()
        dist_inbound = self._host.distance_between(target_coords, nearest_service)

        rate = wh_per_meter if wh_per_meter is not None else self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        drive_out_wh = dist_outbound * rate
        drive_home_wh = dist_inbound * rate
        net_wh = drive_out_wh + drive_home_wh
        buffered_wh = net_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_wh + self.MIN_EMERGENCY_RESERVE_WH

        curr_wh, cap_wh, lvl = self.get_battery()
        is_achievable = curr_wh >= total_required_wh
        self._host.log.trace(
            f"[{self._host.name}] calculate_trip_energy to {target_coords}: "
            f"out={drive_out_wh:.2f}Wh ({dist_outbound:.1f}m), home={drive_home_wh:.2f}Wh ({dist_inbound:.1f}m to '{nearest_service}'), "
            f"buffered={buffered_wh:.2f}Wh (x{self.SAFETY_MARGIN_MULTIPLIER}), reserve={self.MIN_EMERGENCY_RESERVE_WH:.1f}Wh, "
            f"total_required={total_required_wh:.2f}Wh, current={curr_wh:.2f}Wh -> achievable={is_achievable}."
        )
        return {
            "dist_outbound": dist_outbound,
            "dist_inbound": dist_inbound,
            "nearest_service_coords": nearest_service,
            "drive_out_wh": drive_out_wh,
            "drive_home_wh": drive_home_wh,
            "net_expedition_wh": net_wh,
            "total_required_wh": total_required_wh,
            "current_wh": curr_wh,
            "is_achievable": is_achievable,
        }

    def max_safe_throttle_for_leg(self, target_coords):
        """
        Highest throttle for which flying to target_coords still leaves a
        safe reserve to reach the nearest drone_service from there. Unlike
        Pioneer's sqrt(throttle) relationship (vehicle_energy.py), the
        drone's Wh/m is LINEAR in throttle, so the bound solves directly:
            leg_wh(t) = distance * DRONE_WH_PER_METER_PER_THROTTLE * t
            leg_wh(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= available_for_leg / (distance * DRONE_WH_PER_METER_PER_THROTTLE * SAFETY_MARGIN_MULTIPLIER)
        """
        distance = self._host.distance_between(self._host.position(), target_coords)
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_service, _ = self.get_nearest_drone_service(from_coords=target_coords)
        reserve_needed = (self._host.distance_between(target_coords, nearest_service) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: no energy available for leg (current={curr_wh:.2f}Wh, reserve_needed={reserve_needed:.2f}Wh); throttle=0%.")
            return 0.0

        denom = distance * self.DRONE_WH_PER_METER_PER_THROTTLE * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            return self.MAX_SPEEDMODE_THROTTLE
        throttle = max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / denom))
        self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: distance={distance:.1f}m, available={available_for_leg:.2f}Wh, reserve_needed={reserve_needed:.2f}Wh -> max_safe_throttle={throttle*100:.0f}%.")
        return throttle

    def select_cruise_throttle(self, target_coords):
        baseline = min(self._host.cruise_throttle, self.MAX_SPEEDMODE_THROTTLE)
        max_safe = self.max_safe_throttle_for_leg(target_coords)
        if max_safe >= baseline:
            self._host.log.debug(f"[{self._host.name}] select_cruise_throttle: baseline {baseline*100:.0f}% is within safe max ({max_safe*100:.0f}%); using baseline.")
            return baseline
        throttle = max(self.MIN_SPEEDMODE_THROTTLE, min(baseline, max_safe))
        self._host.log.debug(f"[{self._host.name}] select_cruise_throttle: baseline {baseline*100:.0f}% exceeds safe max ({max_safe*100:.0f}%); capping to {throttle*100:.0f}%.")
        return throttle
