# Shared Library for Drone Service Station (charging/rescue) Management.
# Shares lib/station_controller.py's StationController with lib/charging.py:
# docked charge queue, fleet-wide stranded/scrambled detection via fleet.drones(),
# rescue dispatch, multi-station nearest-station coordination, power-gating.
# Engine-aware: electric drones are charge()d, heli drones refuel()ed from
# oil_in; floors/targets use each drone's own fuel unit (Wh / t Oil, see
# lib/drone_energy.py ENGINE_PROFILES).
#
# No "return home" command to a low drone: moving another machine is a remote
# write the game blocks (docs/AI_CHEATSHEET.md "Remote writes are blocked"),
# and a drone whose script could read a signal already budgets its own way
# back (lib/drone_energy.py). This station watches and rescues.
#
# Oil intake: once Heli-Drones is researched, the station keeps oil_in on a
# reachable oil tank or Oil Pump (fluid_routing.FluidInputRouter, same
# routing as lib/oil_generator.py). Before that it leaves oil_in alone.

import fluid_routing
import geometry
from components import drone
from drone_depots import SERVICE_MIN_OIL_T, discover_drone_services, heli_capable_services, heli_unlocked, service_has_oil_feed
from drone_energy import HELI_MIN_EMERGENCY_RESERVE_T, drone_rescue_energy_per_meter
from drone_navigation import STRANDED_STATUSES
from station_controller import StationController
from swallow import swallowed
from tree_console import method_block

# Oil source routing (FluidInputRouter) -- same meaning as
# lib/steam_turbine.py's constants of the same names.
STALL_STREAK_BLACKLIST_THRESHOLD = 5
RESCAN_INTERVAL_TICKS = 150
DISCOVERY_CACHE_INTERVAL_TICKS = 100
NEUTRAL_GRACE_STEPS = 5

OIL_TANK_TYPE_IDS = ("liquid_tank", "bulk_liquid_reservoir")


class DroneServiceController(StationController):
    """
    Automates a Drone Service Station.
    - Manages charging queues for docked electric drones.
    - Monitors the entire drone fleet via get_component("fleet").
    - Detects stranded/scrambled drones or low-battery drones in the field
      and auto-dispatches the recovery vehicle.
    """

    MODULE = "drone_service"
    PARK_KIND = "drone_service_station"
    DEFAULT_NAME = "drone_service_station"
    RESCUER = "Recovery vehicle"
    RESCUE_STATUSES = STRANDED_STATUSES
    # Smaller than ChargingStationController's 8.0 Wh reserves -- electric
    # drone batteries are much smaller than a Rover/Pioneer's (see
    # lib/drone_energy.py's MIN_EMERGENCY_RESERVE_WH note).
    RETURN_EMERGENCY_RESERVE_WH = 2.0
    RESCUE_EXTRA_RESERVE_WH = 2.0
    # Heli equivalents in tons of Oil (tanks are 30/75/150 t).
    RETURN_EMERGENCY_RESERVE_T = HELI_MIN_EMERGENCY_RESERVE_T / 2.0
    RESCUE_EXTRA_RESERVE_T = HELI_MIN_EMERGENCY_RESERVE_T / 2.0

    def __init__(self, station: "DroneServiceStation", target_charge_level=1.0):
        super().__init__(station, target_charge_level)
        self.station: DroneServiceStation = station
        self._oil_warned = False
        self._oil_router = fluid_routing.FluidInputRouter(
            discover=self._discover_oil_sources,
            rescan_interval_ticks=RESCAN_INTERVAL_TICKS,
            discovery_cache_interval_ticks=DISCOVERY_CACHE_INTERVAL_TICKS,
            stall_streak_threshold=STALL_STREAK_BLACKLIST_THRESHOLD,
            neutral_grace_steps=NEUTRAL_GRACE_STEPS,
            label=f"{self.name}.oil_in",
        )

    # ------------------------------------------------------------------
    # Oil input
    # ------------------------------------------------------------------
    def _discover_oil_sources(self):
        """Oil-eligible Liquid Tanks / Large Liquid Tanks network-wide, own outpost first, then Oil Pumps."""
        own_outpost_id = getattr(getattr(self.station, "outpost", None), "id", None)
        tiers = [(type_id, "oil") for type_id in OIL_TANK_TYPE_IDS] + [("oil_pump", None)]
        return fluid_routing.discover_ranked(tiers, own_outpost_id)

    def oil_starved(self):
        """True while the oil_in buffer is below SERVICE_MIN_OIL_T and nothing flows in."""
        try:
            port = self.station.oil_in
            return float(port.level() or 0.0) < SERVICE_MIN_OIL_T and float(port.flow_rate() or 0.0) <= 0.0
        except Exception as error:
            swallowed("drone_service.DroneServiceController.oil_starved: self.station.oil_in", error)
            return False

    def ensure_oil_feed(self):
        """Keeps oil_in on a reachable oil source once Heli-Drones is researched. A tank has no script,
        so this station declares the link. Returns the router event, or None before the research."""
        if not heli_unlocked():
            return None
        port = getattr(self.station, "oil_in", None)
        if port is None:
            return None
        return fluid_routing.ensure_input_logged(
            self._oil_router,
            port,
            self.get_current_tick(),
            self.oil_starved(),
            self.log,
            self.name,
            "oil_in",
            "No oil-eligible tank or Oil Pump found network-wide yet (an empty tank needs a fluid_routing.tank_assignments entry for 'oil').",
        )

    def step(self):
        """StationController.step() plus the oil feed. Stays awake while a source is waiting on its
        blacklist expiry, so the retry isn't lost to parking."""
        if not self.is_station_powered():
            self.parker.update(False)
            return False
        event = self.ensure_oil_feed()
        docked_busy = self.manage_docked()
        rescue_busy = self.manage_fleet_rescues()
        busy = docked_busy or rescue_busy
        self.parker.update(not busy and getattr(event, "kind", None) != "waiting")
        return busy

    def all_station_refs(self):
        return discover_drone_services()

    def station_refs_for(self, drone_ref: "DroneRef"):
        """Stations that can serve drone_ref: all for electric, oil-holding ones for heli (heli_capable_services(), dry skipped)."""
        refs = self.all_station_refs()
        if getattr(drone_ref, "engine", "") == "heli":
            refs, _tier = heli_capable_services(refs)
        return refs

    def station_coords(self, drone_ref: "DroneRef | None" = None):
        refs = self.station_refs_for(drone_ref) if drone_ref is not None else self.all_station_refs()
        return [r["coords"] for r in refs]

    @staticmethod
    def fuel_of(drone_ref: "DroneRef"):
        """(current, capacity, fraction) from a DroneRef in its own unit: Wh (electric) or t Oil (heli)."""
        if drone_ref.engine == "heli":
            return (drone_ref.oil_tons or 0.0, drone_ref.oil_capacity or 0.0, drone_ref.oil_level or 0.0)
        return (drone_ref.battery_wh or 0.0, drone_ref.battery_capacity or 0.0, drone_ref.battery_level or 0.0)

    def return_floor_wh(self, unit_ref: "DroneRef", distance=None):
        """
        Fuel (Wh, or t Oil for heli) a drone needs on board right now to
        safely self-navigate to the nearest drone_service -- mirrors
        ChargingStationController's own return_floor_wh(), but the drone
        model needs no drone object at all (drone_rescue_energy_per_meter()
        is a flat per-engine constant, unlike the ground-vehicle model's
        per-chassis/module/cargo terms). distance: metres to the nearest
        serving station when the caller already has it (None = look up).
        """
        if distance is None:
            stations = self.station_coords(unit_ref)
            if not stations:
                return 0.0
            distance = min(geometry.distance((unit_ref.x, unit_ref.y), s) for s in stations)
        reserve = self.RETURN_EMERGENCY_RESERVE_T if unit_ref.engine == "heli" else self.RETURN_EMERGENCY_RESERVE_WH
        return (distance * drone_rescue_energy_per_meter(unit_ref.engine) * self.RETURN_SAFETY_MARGIN) + reserve

    def rescue_target_level(self, unit_ref: "DroneRef", floor=None):
        """Charge/refuel target for a rescue: enough to reach the nearest station with a safety reserve. floor: precomputed return_floor_wh()."""
        current, capacity, _ = self.fuel_of(unit_ref)
        if not capacity or capacity <= 0:
            return 1.0
        extra = self.RESCUE_EXTRA_RESERVE_T if unit_ref.engine == "heli" else self.RESCUE_EXTRA_RESERVE_WH
        if floor is None:
            floor = self.return_floor_wh(unit_ref)
        target = max(current, floor + extra)
        return min(1.0, target / capacity)

    def _queue_service(self, d_id, heli, lvl):
        """charge() an electric / refuel() a heli docked drone; logs the outcome."""
        verb = "refuel" if heli else "charge"
        res = self.station.refuel(d_id, self.target_charge_level) if heli else self.station.charge(d_id, self.target_charge_level)
        if res.status in ("charging", "refueling", "queued"):
            self.log.print(f"[{self.name}] Queued docked drone {d_id} ({lvl * 100:.0f}%) for {verb}.")
            if heli:
                self._oil_warned = False
        elif res.status == "no_oil":
            if not self._oil_warned:
                hint = "oil_in wired but source dry" if service_has_oil_feed(self.name) else "oil_in not wired -- connect it to an Oil Pump/tank"
                self.log.level("warn").print(f"[{self.name}] Cannot refuel heli {d_id}: no oil ({hint}).")
                self._oil_warned = True
        elif res.status != "target_reached":
            self.log.level("warn").print(f"[{self.name}] {verb.capitalize()} queue notice for {d_id}: {res.status} - {res.message}")

    @method_block(lambda self, *_, **__: f"[{self.name}] manage_docked()")
    def manage_docked(self):
        """Queues docked drones below target level: charge() for electric, refuel() for heli. True while bays are active or queued."""
        self.log.trace("manage_docked() entry.")
        try:
            docked_ids = self.station.get_docked()
        except Exception as error:
            swallowed("drone_service.DroneServiceController.manage_docked: self.station.get_docked", error)
            return False
        if not docked_ids:
            self.log.trace("no docked drones this cycle.")
            return False

        active_bays = self.station.get_active()
        queued = self.station.get_queue()
        busy = bool(active_bays) or bool(queued)

        for d_id in docked_ids:
            try:
                d = drone(d_id)
                if not d:
                    continue
                # Probe, not hasattr(): drones expose both .battery and
                # .oil_tank; the wrong powertrain's methods raise ReferenceError.
                heli = False
                try:
                    lvl = d.battery.percent()
                except Exception:
                    try:
                        lvl = d.oil_tank.percent()
                        heli = True
                    except Exception:
                        self.log.debug(f"Docked drone {d_id} has no readable battery or oil tank; skipping.")
                        continue
                if lvl < (self.target_charge_level - 0.02):
                    if d_id not in active_bays and d_id not in queued:
                        self._queue_service(d_id, heli, lvl)
                        busy = True
                    else:
                        self.log.debug(f"Docked drone {d_id} ({lvl * 100:.0f}%) below target but already active/queued; not re-queuing.")
                elif self.log.verbose:
                    self.log.trace(f"Docked drone {d_id} at {lvl * 100:.0f}%, at or above target {self.target_charge_level * 100:.0f}%; no charge needed.")
            except Exception as error:
                swallowed("drone_service.DroneServiceController.manage_docked: get_component", error)
        self.log.trace(f"manage_docked() exit: {len(docked_ids)} docked drone(s) evaluated.")
        return busy

    def _dispatch_rescue(self, unit_ref: "DroneRef", is_stranded, wh, target_level, floor):
        """Announces distress and dispatches the recovery vehicle; True when the loop over drones should stop."""
        unit = "t Oil" if unit_ref.engine == "heli" else "Wh"
        reason = "STRANDED/SCRAMBLED" if is_stranded else f"CRITICAL FUEL ({wh:.1f} {unit}, below {floor:.1f} {unit} return floor)"
        self.log.start(f"[{self.name}] Rescue {unit_ref.name}")
        self.log.level("warn").print(f"[{self.name}] Emergency! Drone {unit_ref.name} ({unit_ref.id}) in distress: {reason} at ({unit_ref.x:.1f}, {unit_ref.y:.1f}).")
        try:
            notify(f"[RESCUE DISPATCH] Sending recovery vehicle to {unit_ref.name} ({reason})!", level="warn", duration_seconds=10.0)
        except Exception as error:
            swallowed("drone_service.DroneServiceController._dispatch_rescue: notify", error)

        res = self.station.dispatch_rescue(unit_ref.id, target_level)
        if res.status == "ok":
            self.log.print(f"[{self.name}] Rescue dispatched to {unit_ref.id}; target charge {target_level * 100:.0f}%.")
            self.last_rescued = unit_ref.id
            self.log.end("dispatched")
            return True
        if res.status == "already_dispatched":
            self.log.debug(f"[{self.name}] Rescue for {unit_ref.id} already dispatched; not re-issuing.")
            self.log.end("already dispatched")
            return True
        self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")
        self.log.end(f"rejected ({res.status})")
        return False

    def rescue_units(self, fleet):
        return fleet.drones()

    def rescue_candidates(self, unit_ref, refs, memo):
        """All stations for an electric drone, the oil-holding ones (one lookup per pass) for a heli; none without a thruster."""
        engine = unit_ref.engine
        if engine == "electric":
            return refs
        if engine != "heli":
            return None  # no thruster mounted yet
        if "heli" not in memo:
            memo["heli"], _tier = heli_capable_services(refs)
        return memo["heli"]

    def rescue_fuel(self, unit_ref):
        current, _, level = self.fuel_of(unit_ref)
        return current, level

    @method_block(lambda self, *_, **__: f"[{self.name}] manage_fleet_rescues")
    def manage_fleet_rescues(self):
        """StationController.manage_fleet_rescues() over every owned drone (electric and heli)."""
        return super().manage_fleet_rescues()

    def online_message(self):
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        return f"Drone Service Station ({self.name}) online via Shared Library ({bay_count} bay(s))."
