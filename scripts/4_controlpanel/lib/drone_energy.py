# Drone mixin: engine-aware (electric battery / heli oil) linear energy
# model, round-trip trip budgeting, and drone_service/drone_depot discovery.
# Mirrors vehicle_energy.py's "there-and-back" safety-margin + hard
# emergency-reserve floor pattern, but with a DIFFERENT (simpler, linear)
# travel model and TWO distinct "home" endpoints -- drone_service (power/oil)
# and drone_depot (cargo) -- rather than ground vehicles' single combined
# base/charging-station pair.
#
# Game-confirmed constants (docs/components/drone.md, equipment_modules.md):
#   electric: full throttle = 5 Wh/h burn, 300 m/h speed
#   heli:     full throttle = 5 t/h Oil burn, 900 m/h speed
# Both scale with throttle (speed linear, burn quadratic) -- collapsing to a
# flat linear energy-per-meter model per engine (ENGINE_PROFILES). Shield
# Plating raises burn 1.5x. "Energy" throughout this mixin means the
# drone's own fuel unit: Wh for electric, tons of Oil for heli -- every
# budget/floor below is in that unit, so callers never branch on engine.
# The engine is auto-detected per drone (detect_engine()). Treat the drone's
# own range_remaining() as ground truth; this formula is for PLANNING only
# (trip feasibility, throttle selection), verified against the drone's live
# fuel before committing. Scan/extract themselves cost no extra travel energy
# in the documented model (hovering at throttle 0 costs 0), so there's
# deliberately no scan/extract term in calculate_trip_energy() below, unlike
# VehicleEnergyMixin's sonar/mining budget terms.

from archive import archive
from drone_upgrade import retiring_depot_ids
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
# Every Depot size: outpost.buildings(type_id) matches one exact typeId, and
# the Medium/Large kits deploy distinct types (decompiled simworker's machine
# catalog; confirmed live for drone_station_large at Outpost 5). Their
# instance/script ids differ again: drone_station_med_N / drone_station_lrg_N.
DRONE_DEPOT_TYPE_IDS = (DRONE_DEPOT_TYPE_ID, "drone_station_medium", "drone_station_large")

# 5.0 Wh/h at 300 m/h full-throttle burn -> flat Wh/meter-per-throttle rate.
DRONE_WH_PER_METER_PER_THROTTLE = 5.0 / 300.0  # ~0.01667 Wh/m at throttle 1.0
# 5.0 t/h Oil at 900 m/h full-throttle burn -> flat t/meter-per-throttle rate.
HELI_T_PER_METER_PER_THROTTLE = 5.0 / 900.0  # ~0.00556 t/m (5.6 t/km) at throttle 1.0
# docs/components/drone.md is_plated(): Shield Plating raises burn 1.5x.
PLATING_BURN_MULTIPLIER = 1.5
MIN_SPEEDMODE_THROTTLE = 0.10
MAX_SPEEDMODE_THROTTLE = 1.0
SAFETY_MARGIN_MULTIPLIER = 1.05

# Smaller than VehicleEnergyMixin.MIN_EMERGENCY_RESERVE_WH=8.0 -- electric
# drone batteries are much smaller than a Rover/Pioneer's, so an 8 Wh floor
# would eat a large fraction of total capacity. Tune here and update
# docs/AI_CHEATSHEET.md's drone energy-budgeting section in the same change.
MIN_EMERGENCY_RESERVE_WH = 4.0
# Heli equivalent, in tons of Oil: ~0.9 km at full throttle, ~9 km at the
# speedmode floor. Oil tanks are 30/75/150 t, so this is a small slice.
HELI_MIN_EMERGENCY_RESERVE_T = 5.0

# Per-engine planning profile. "energy" = Wh (electric) or t Oil (heli).
ENGINE_PROFILES = {
    "electric": {"per_meter": DRONE_WH_PER_METER_PER_THROTTLE, "speed_m_per_h": 300.0, "reserve": MIN_EMERGENCY_RESERVE_WH, "unit": "Wh"},
    "heli": {"per_meter": HELI_T_PER_METER_PER_THROTTLE, "speed_m_per_h": 900.0, "reserve": HELI_MIN_EMERGENCY_RESERVE_T, "unit": "t"},
}
DEFAULT_ENGINE = "electric"

# A drone_service_station counts as able to refuel a heli when its oil_in
# buffer (100 t max) holds at least this much, or oil is flowing in right
# now. Dry stations are skipped as refuel/return targets (still used as a
# last resort when no station has oil, see get_all_drone_services()).
SERVICE_MIN_OIL_T = 10.0

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


def engine_profile(engine):
    """ENGINE_PROFILES entry for engine ("electric"/"heli"), electric for unknown/""."""
    return ENGINE_PROFILES.get(engine or DEFAULT_ENGINE, ENGINE_PROFILES[DEFAULT_ENGINE])


def drone_energy_per_meter_at_throttle(throttle, engine=DEFAULT_ENGINE, plated=False):
    """
    Standalone: linear energy/meter (Wh or t Oil, see ENGINE_PROFILES) for
    ANY drone of that engine at the given throttle -- no drone object
    needed, since the documented model has no per-drone/cargo term (unlike
    Pioneer's travel formula), just one flat rate per engine, times
    PLATING_BURN_MULTIPLIER with Shield Plating.
    """
    if throttle <= 0:
        return 0.0
    rate = engine_profile(engine)["per_meter"] * throttle
    return rate * PLATING_BURN_MULTIPLIER if plated else rate


def drone_wh_per_meter_at_throttle(throttle):
    """Electric-only shorthand for drone_energy_per_meter_at_throttle()."""
    return drone_energy_per_meter_at_throttle(throttle, "electric")


def drone_rescue_energy_per_meter(engine=DEFAULT_ENGINE):
    """
    Worst-case-safe energy/meter for rescue/return budgeting, at the
    speedmode throttle floor -- mirrors vehicle_energy.py's
    rescue_wh_per_meter_for(), but needs no drone object at all since the
    model is a flat per-throttle rate with no vehicle-specific terms.
    Plating unknown from a DroneRef, so assumed (conservative).
    """
    return drone_energy_per_meter_at_throttle(MIN_SPEEDMODE_THROTTLE, engine, plated=True)


def drone_rescue_wh_per_meter():
    """Electric-only shorthand for drone_rescue_energy_per_meter()."""
    return drone_rescue_energy_per_meter("electric")


def service_oil_state(service_id):
    """
    (wired, buffer_t, flow_t_per_h) of a drone_service_station's oil_in.
    "wired" uses connections() (every effective peer, including a link the
    Oil Pump/tank declared from its side -- connected_to() only shows this
    port's own declaration). Unreadable reads as (False, 0.0, 0.0).
    """
    try:
        station = get_component(service_id)
        port = getattr(station, "oil_in", None) if station else None
        if port is None:
            return (False, 0.0, 0.0)
        wired = bool(port.connections()) or bool(port.connected_to())
        return (wired, float(port.level() or 0.0), float(port.flow_rate() or 0.0))
    except Exception:
        return (False, 0.0, 0.0)


def service_has_oil_feed(service_id):
    """True when a drone_service_station's oil_in has any oil source wired (docs/components/drone_service_station.md)."""
    return service_oil_state(service_id)[0]


def service_can_refuel(service_id):
    """True when the station holds >= SERVICE_MIN_OIL_T in its oil_in buffer or oil is flowing in now."""
    _wired, buffer_t, flow = service_oil_state(service_id)
    return buffer_t >= SERVICE_MIN_OIL_T or flow > 0.0


def heli_capable_services(services):
    """
    (subset, tier) of `services` (discover_drone_services() dicts) usable
    by a heli drone: tier "oil" = service_can_refuel() stations; else
    "wired" = wired but dry (may refill); else "all" (a rescue still works,
    and the station itself warns about the missing oil). Shared by
    DroneEnergyMixin (the drone's own choice) and lib/drone_service.py
    (rescue/nudge arbitration), so both skip dry stations the same way.
    """
    if not services:
        return services, "all"
    states = {s["id"]: service_oil_state(s["id"]) for s in services}
    usable = [s for s in services if states[s["id"]][1] >= SERVICE_MIN_OIL_T or states[s["id"]][2] > 0.0]
    if usable:
        return usable, "oil"
    wired = [s for s in services if states[s["id"]][0]]
    if wired:
        return wired, "wired"
    return services, "all"


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
    drone_depot; a tuple of type ids matches any of them) across every owned outpost, as
    [{"id": str, "name": str, "coords": (x, y), "outpost": OutpostRef|None,
    "outpost_id": str}, ...]. Mirrors
    vehicle_energy.py's get_all_charging_stations() discovery shape, but
    module-level so both DroneEnergyMixin and lib/drone_service.py's own
    station-side nearest-station arbitration (mirroring charging.py's
    is_nearest_station_to()) can share one implementation.
    """
    refs = []
    found_ids = set()
    type_ids = type_id if isinstance(type_id, (tuple, list)) else (type_id,)
    network = get_component("outpost_network")
    if network and hasattr(network, "outposts"):
        try:
            outposts = network.outposts()
        except Exception:
            outposts = []
        for outpost in outposts:
            if not hasattr(outpost, "buildings"):
                continue
            buildings = []
            for t_id in type_ids:
                try:
                    buildings.extend(outpost.buildings(t_id))
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
    """Every Drone Depot drones may use: all sizes, minus the ones a fleet
    upgrade is retiring (lib/drone_upgrade.py), so homes, deliveries and
    recalls move to the replacement while the old one drains."""
    depots = discover_drone_buildings(DRONE_DEPOT_TYPE_IDS)
    retiring = retiring_depot_ids()
    return [d for d in depots if d["id"] not in retiring] if retiring else depots


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

    def detect_engine(self):
        """
        "electric" or "heli", auto-detected: this drone's own DroneRef.engine
        from fleet.drones() first, else a live probe -- .oil_tank/.battery
        methods raise ReferenceError on the other powertrain (drone.md).
        Falls back to DEFAULT_ENGINE when neither answers (no thruster
        mounted yet). Also caches Shield Plating (is_plated()) for the burn
        multiplier. Re-run after a re-equip (DroneController.run() does).
        """
        engine, source = "", None
        fleet = get_component("fleet")
        if fleet and hasattr(fleet, "drones"):
            try:
                for ref in fleet.drones():
                    if getattr(ref, "id", None) == self._host.name:
                        engine = getattr(ref, "engine", "") or ""
                        source = "fleet.drones()"
                        break
            except Exception:
                pass
        if engine not in ENGINE_PROFILES:
            engine = ""
            for candidate, attr in (("heli", "oil_tank"), ("electric", "battery")):
                try:
                    getattr(self._host.drone, attr).capacity()
                    engine, source = candidate, f"{attr} probe"
                    break
                except Exception:
                    continue
        if not engine:
            engine, source = DEFAULT_ENGINE, "fallback (no thruster/fuel module readable)"
        try:
            self._host.plated = bool(self._host.drone.is_plated())
        except Exception:
            self._host.plated = False
        self._host.engine = engine
        self._host.log.debug(f"[{self._host.name}] Engine detected: '{engine}' via {source}; plated={self._host.plated}.")
        return engine

    def energy_unit(self):
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["unit"]

    def emergency_reserve(self):
        """Hard reserve floor in this drone's fuel unit (MIN_EMERGENCY_RESERVE_WH / HELI_MIN_EMERGENCY_RESERVE_T)."""
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["reserve"]

    def flight_speed_m_per_h(self, throttle=1.0):
        return engine_profile(getattr(self._host, "engine", DEFAULT_ENGINE))["speed_m_per_h"] * throttle

    def get_battery(self):
        """
        Returns (current, capacity, fraction 0-1) of this drone's fuel store
        in its own unit: battery Wh (electric) or oil tank tons (heli).
        Named for its electric origin; every budget in this mixin uses the
        same unit (see module docstring). Unreadable reads as empty, so
        every gate fails safe toward refuelling.
        """
        store = "oil_tank" if getattr(self._host, "engine", DEFAULT_ENGINE) == "heli" else "battery"
        try:
            module = getattr(self._host.drone, store)
            return module.level(), module.capacity(), module.percent()
        except Exception:
            return 0.0, 100.0, 0.0

    def wh_per_meter_at_throttle(self, throttle):
        """Energy/meter in this drone's fuel unit (engine + plating aware)."""
        return drone_energy_per_meter_at_throttle(throttle, getattr(self._host, "engine", DEFAULT_ENGINE), getattr(self._host, "plated", False))

    def minimum_wh_per_meter(self):
        return self.wh_per_meter_at_throttle(self.MIN_SPEEDMODE_THROTTLE)

    def energy_wh_for_leg(self, distance_m, throttle):
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        return distance_m * self.wh_per_meter_at_throttle(throttle)

    def get_all_drone_services(self):
        """
        Every drone_service_station -- for a heli drone only the ones that
        can refuel it right now (service_can_refuel(): oil in the buffer or
        flowing in), so dry stations are skipped for refuel, parking and
        return budgeting. Falls back to wired-but-dry stations (they may
        refill), then to all of them (a rescue still works, and the station
        itself warns about the missing oil).
        """
        services = discover_drone_services()
        if getattr(self._host, "engine", DEFAULT_ENGINE) != "heli" or not services:
            return services
        chosen, tier = heli_capable_services(services)
        if tier == "oil":
            skipped = [s["id"] for s in services if s not in chosen]
            if skipped:
                self._host.log.trace(f"[{self._host.name}] Skipping dry drone_service_station(s) for heli: {skipped}.")
        else:
            self._host.log.debug(
                f"[{self._host.name}] No drone_service_station has oil (>= {SERVICE_MIN_OIL_T:.0f} t or inflow); "
                + (f"falling back to {len(chosen)} wired but dry." if tier == "wired" else f"none wired; considering all {len(chosen)}.")
            )
        return chosen

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
        return (dist * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()

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
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()

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
                log.debug(f"[{self._host.name}] Home drone_service '{service_info.get('id')}' out of reach ({curr_wh:.1f} {self.energy_unit()} < {home_wh:.1f} {self.energy_unit()} needed); charging at nearest '{nearest_info.get('id')}' instead.")
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
        total_required_wh = buffered_wh + self.emergency_reserve()

        curr_wh, cap_wh, lvl = self.get_battery()
        is_achievable = curr_wh >= total_required_wh
        self._host.log.trace(
            f"[{self._host.name}] calculate_trip_energy to {target_coords}: "
            f"out={drive_out_wh:.2f} {self.energy_unit()} ({dist_outbound:.1f}m), home={drive_home_wh:.2f} {self.energy_unit()} ({dist_inbound:.1f}m to '{nearest_service}'), "
            f"buffered={buffered_wh:.2f} {self.energy_unit()} (x{self.SAFETY_MARGIN_MULTIPLIER}), reserve={self.emergency_reserve():.1f} {self.energy_unit()}, "
            f"total_required={total_required_wh:.2f} {self.energy_unit()}, current={curr_wh:.2f} {self.energy_unit()} -> achievable={is_achievable}."
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
            leg(t) = distance * per_meter(1.0) * t
            leg(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= available_for_leg / (distance * per_meter(1.0) * SAFETY_MARGIN_MULTIPLIER)
        """
        distance = self._host.distance_between(self._host.position(), target_coords)
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_service, _ = self.get_nearest_drone_service(from_coords=target_coords)
        reserve_needed = (self._host.distance_between(target_coords, nearest_service) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.emergency_reserve()
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: no energy available for leg (current={curr_wh:.2f} {self.energy_unit()}, reserve_needed={reserve_needed:.2f} {self.energy_unit()}); throttle=0%.")
            return 0.0

        denom = distance * self.wh_per_meter_at_throttle(1.0) * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            return self.MAX_SPEEDMODE_THROTTLE
        throttle = max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, available_for_leg / denom))
        self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg to {target_coords}: distance={distance:.1f}m, available={available_for_leg:.2f} {self.energy_unit()}, reserve_needed={reserve_needed:.2f} {self.energy_unit()} -> max_safe_throttle={throttle*100:.0f}%.")
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
