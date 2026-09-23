# Vehicle mixin: battery accounting, round-trip energy budgeting, and
# charging-station discovery/docking. Shared by Rover and Pioneer via
# VehicleController (lib/vehicle.py).
#
# Travel energy uses developer-confirmed exact power/speed models (not an
# empirically-calibrated Wh/meter -- that whole archive-backed calibration
# system was intentionally dropped in favor of these validated theoretical
# models) -- but Pioneer and Rover are two DIFFERENT models, not one formula
# with the other vehicle's terms zeroed out:
#
# Pioneer (VehicleEnergyMixin base implementation, used as-is):
#   power (W)   = (BASE_TRAVEL_POWER_W + MODULE_TRAVEL_POWER_W * active_modules
#                  + CARGO_UNIT_TRAVEL_POWER_W * cargo_units)
#                 * throttle^1.5 * nav_power_multiplier
#   speed (m/h) = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle * nav_speed_multiplier
# active_modules = mounted functional modules (Nav/Drill/Sonar/Constructor family,
# including upgraded variants -- they share the same id prefix); passive
# containers (Battery Holder, Cargo Rack) don't count. cargo_units = live cargo
# count, so a full return trip after mining costs more than the empty outbound
# leg. nav_power_multiplier/nav_speed_multiplier come from mounted Sport Nav
# modules (docs/components/nav_module.md: 1 Sport Nav = 2x speed / 2.6x power).
#
# Rover (RoverController overrides wh_per_meter_at_throttle()/
# max_safe_throttle_for_leg() in lib/rover.py -- see there):
#   Wh/meter = ROVER_WH_PER_METER_PER_THROTTLE * throttle
# Developer-confirmed (Spyros - CT Dev, in-game Discord #playtest-chat,
# 2026-08-28): "the rover is very simple wh = distance x throttle x 0.2" --
# deliberately independent of active_modules/cargo_units/nav multipliers,
# unlike Pioneer. Note this is linear in throttle (implying power scales as
# throttle^2 at Rover's fixed 100 m/h-per-throttle speed), not the throttle^1.5
# curve above, so it is a genuinely different model, not a parameterization of
# Pioneer's.

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController

def is_rover_chassis_for(vehicle):
    """
    Standalone chassis-type probe for a raw get_component() object (no live
    VehicleController instance available) -- used by the module-level _for()
    helpers below so callers like lib/charging.py's rescue-cost estimate pick
    the right travel-energy model without needing one. Matches the existing
    "rover"-prefixed id/name convention already used for telemetry keying in
    VehicleController.publish_telemetry() (lib/vehicle.py); RoverController
    itself never needs this probe since its own overrides apply directly via
    normal polymorphism.
    """
    if vehicle is None:
        return False
    name = getattr(vehicle, "id", getattr(vehicle, "name", ""))
    return str(name).startswith("rover")

from archive import archive

# Building type id as returned by OutpostRef.buildings() / Machine.typeId
# ("charging_station"), not the component doc name
# ("vehicle_charging_station"), which never matches and silently made every
# station lookup fall back to the home slot.
CHARGING_STATION_TYPE_ID = "charging_station"

# Fleet-wide default cruise_throttle, settable via the Data Archive Notebook
# (e.g. bump to 1.0 once battery capacity supports full-throttle driving)
# without touching any vehicle's own thin entrypoint script. Replaces the old
# binary vehicle.speedmode ("conserve"/"highspeed") flag: a single numeric
# default is strictly more expressive (any value in between, not just two
# presets), and select_cruise_throttle() already safely scales any
# self.cruise_throttle down per-leg (via max_safe_throttle_for_leg()) when the
# full value wouldn't leave a safe return reserve -- so there's no separate
# "highspeed" logic path needed at all, just one throttle number. See
# VehicleEnergyMixin.default_cruise_throttle()/select_cruise_throttle().
DEFAULT_CRUISE_THROTTLE_KEY = "vehicle.default_cruise_throttle"
DEFAULT_CRUISE_THROTTLE_FALLBACK = 0.5

ACTIVE_MODULE_ID_PREFIXES = ("nav_module", "drill_module", "sonar_module", "constructor_module")

# Developer-confirmed travel power/speed model (see module docstring above).
# Module-level (not just class attributes) so non-VehicleController callers
# without a live instance -- e.g. lib/charging.py estimating a stranded
# vehicle's rescue-return cost -- can import these and travel_wh_per_meter_for()
# directly, rather than duplicating the formula. Single source of truth either way.
DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE = 100.0
BASE_TRAVEL_POWER_W = 3.0
MODULE_TRAVEL_POWER_W = 8.0
CARGO_UNIT_TRAVEL_POWER_W = 0.04
MIN_SPEEDMODE_THROTTLE = 0.10
MAX_SPEEDMODE_THROTTLE = 1.0

# Rover's own developer-confirmed travel model (see module docstring above) --
# a flat Wh/meter-per-throttle rate, not a power/speed pair like Pioneer's.
ROVER_WH_PER_METER_PER_THROTTLE = 0.2

# Exact mining Wh/unit inputs, both developer-confirmed/documented (unlike
# construction, see CONSTRUCTION_WH_PER_PROGRESS_DEFAULT below): per-ore dig
# time (docs/database/items_minerals.md) and drill power draw by hardness
# tier (docs/components/drill_module.md: basic=10W/industrial=20W/heavy=30W,
# keyed here by drill.hardness_limit() since that's what's live-queryable --
# there's no .power_draw() method). DrillModule.mine()'s own documented time
# formula is `mineral_base_minutes * drill.speed_multiplier() / site_purity`
# (drill_module.md line 29); PURITY_DIVISOR mirrors the same "standard"=1x/
# "rich"=2x/"pure"=3x yield multiplier from docs/types/world_and_sites.md's
# `.purity` field, which IS that site_purity divisor. See mine_wh_per_unit_for().
ORE_DIG_MINUTES = {
    "iron_ore": 15.0,
    "silicon": 15.0,
    "titanium": 20.0,
    "cobalt": 20.0,
    "lead_ore": 18.0,
    "rare_earth": 25.0,
    "neutronium": 30.0,
}
DRILL_POWER_W_BY_HARDNESS_LIMIT = {1: 10.0, 3: 20.0, 4: 30.0}
PURITY_DIVISOR = {"standard": 1.0, "rich": 2.0, "pure": 3.0}
DEFAULT_ORE_DIG_MINUTES = 15.0  # fallback for an unknown/undocumented item_id -- matches the cheapest (H1) ore
DEFAULT_DRILL_POWER_W = 10.0  # fallback matching the basic drill


def active_modules_count_for(vehicle):
    """Standalone: count of mounted functional (power-drawing) modules for a live vehicle object."""
    if hasattr(vehicle, "modules"):
        try:
            return sum(
                1 for slot in vehicle.modules()
                if getattr(slot, "module_id", None) and str(slot.module_id).startswith(ACTIVE_MODULE_ID_PREFIXES)
            )
        except Exception:
            pass
    return sum(1 for attr in ("nav", "drill", "sonar", "constructor") if hasattr(vehicle, attr))


def cargo_units_count_for(vehicle):
    """Standalone: live cargo unit count for a live vehicle object."""
    if hasattr(vehicle, "cargo") and hasattr(vehicle.cargo, "count"):
        try:
            return vehicle.cargo.count()
        except Exception:
            pass
    return 0


def nav_speed_multiplier_for(vehicle):
    """Standalone: Sport Nav top-speed multiplier for a live vehicle object."""
    if hasattr(vehicle, "nav") and hasattr(vehicle.nav, "speed_multiplier"):
        try:
            return float(vehicle.nav.speed_multiplier())
        except Exception:
            pass
    return 1.0


def nav_power_multiplier_for(vehicle):
    """Standalone: Sport Nav movement-power multiplier matching nav_speed_multiplier_for()."""
    speed_mult = nav_speed_multiplier_for(vehicle)
    return 1.0 + 1.6 * (speed_mult - 1.0)


def travel_wh_per_meter_for(vehicle, throttle, cargo_units=None):
    """
    Standalone travel Wh/meter for a live vehicle object, for callers without a
    VehicleController instance. Branches by chassis (is_rover_chassis_for()) --
    Rover's flat linear model, kept in sync with RoverController's own
    wh_per_meter_at_throttle() override by construction since both read
    ROVER_WH_PER_METER_PER_THROTTLE; Pioneer's throttle^1.5 model otherwise,
    kept in sync with VehicleEnergyMixin.wh_per_meter_at_throttle() the same way.
    """
    if throttle <= 0:
        return 0.0
    if is_rover_chassis_for(vehicle):
        return ROVER_WH_PER_METER_PER_THROTTLE * throttle
    if cargo_units is None:
        cargo_units = cargo_units_count_for(vehicle)
    base_w = BASE_TRAVEL_POWER_W + (MODULE_TRAVEL_POWER_W * active_modules_count_for(vehicle)) + (CARGO_UNIT_TRAVEL_POWER_W * cargo_units)
    power = base_w * (throttle ** 1.5) * nav_power_multiplier_for(vehicle)
    speed = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle * nav_speed_multiplier_for(vehicle)
    return power / speed


def mine_wh_per_unit_for(vehicle, item_id, purity=None):
    """
    Standalone exact mining Wh/unit for a live vehicle object: 1 unit of
    item_id, at the vehicle's actually-mounted drill's real speed_multiplier()/
    hardness_limit() and the site's purity, from the documented formula (see
    the module-level ORE_DIG_MINUTES/DRILL_POWER_W_BY_HARDNESS_LIMIT/
    PURITY_DIVISOR comment above) -- not a flat per-unit average across every
    ore/drill/purity combination. Falls back to the basic-drill/standard-purity
    rate for an unmounted drill, an unrecognized item_id, or unsurveyed purity
    (None), rather than guessing.
    """
    base_minutes = ORE_DIG_MINUTES.get(item_id, DEFAULT_ORE_DIG_MINUTES)
    speed_mult = 1.0
    hardness_limit = 1
    drill = getattr(vehicle, "drill", None)
    if drill is not None:
        if hasattr(drill, "speed_multiplier"):
            try:
                speed_mult = float(drill.speed_multiplier())
            except Exception:
                pass
        if hasattr(drill, "hardness_limit"):
            try:
                hardness_limit = int(drill.hardness_limit())
            except Exception:
                pass
    power_w = DRILL_POWER_W_BY_HARDNESS_LIMIT.get(hardness_limit, DEFAULT_DRILL_POWER_W)
    purity_divisor = PURITY_DIVISOR.get(str(purity or "standard"), 1.0)
    time_hours = (base_minutes / 60.0) * speed_mult / purity_divisor
    return time_hours * power_w


def rescue_wh_per_meter_for(vehicle):
    """
    Standalone worst-case-safe travel Wh/meter for rescue-return budgeting, at
    the speedmode throttle floor (cheapest possible Wh/m). One-call entry
    point for callers like lib/charging.py that only have a raw get_component()
    object (or None, if the vehicle couldn't be reached) and shouldn't need to
    import every formula constant just to size a rescue trip.
    """
    if vehicle is not None:
        rate = travel_wh_per_meter_for(vehicle, MIN_SPEEDMODE_THROTTLE)
        if rate:
            return rate
    # Bare-module fallback (no live vehicle object to read modules/cargo/nav from).
    return (BASE_TRAVEL_POWER_W + MODULE_TRAVEL_POWER_W) * (MIN_SPEEDMODE_THROTTLE ** 1.5) / (DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * MIN_SPEEDMODE_THROTTLE)


class VehicleEnergyMixin:
    """
    Battery telemetry, developer-confirmed travel power/speed model, and
    outpost-aware charging-station discovery, mixed into VehicleController.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    SONAR_WH_BUDGET = 2.0
    # Flat fallback only, used when calculate_trip_energy() isn't given a
    # mine_item_id (e.g. a non-mining candidate) -- see mine_wh_per_unit()/
    # mine_wh_per_unit_for() above for the exact per-ore/per-drill/per-purity
    # formula every real mining call site now passes instead. This value
    # happens to equal the exact rate for the cheapest case (basic drill,
    # iron ore, standard purity): (15 min/60) * 1.0 * 10 W = 2.5 Wh.
    MINE_WH_PER_UNIT = 2.5
    SAFETY_MARGIN_MULTIPLIER = 1.05
    MIN_EMERGENCY_RESERVE_WH = 8.0

    # Wh to take a Constructor Module job from 0% to 100% progress. Uncalibrated
    # starting assumption -- calibrate_wh_per_progress() refines it per-vehicle
    # from observed execute() calls once real samples exist. (Construction
    # progress energy has no developer-confirmed formula, unlike travel energy
    # below, so this one still uses empirical calibration.)
    CONSTRUCTION_WH_PER_PROGRESS_DEFAULT = 40.0

    # Class-attribute aliases of the module-level constants above, so existing
    # self.CONST call sites keep working unchanged.
    DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE = DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE
    BASE_TRAVEL_POWER_W = BASE_TRAVEL_POWER_W
    MODULE_TRAVEL_POWER_W = MODULE_TRAVEL_POWER_W
    CARGO_UNIT_TRAVEL_POWER_W = CARGO_UNIT_TRAVEL_POWER_W
    MIN_SPEEDMODE_THROTTLE = MIN_SPEEDMODE_THROTTLE
    MAX_SPEEDMODE_THROTTLE = MAX_SPEEDMODE_THROTTLE

    def active_modules_count(self):
        """
        Count of mounted functional modules that draw power while driving --
        Nav/Drill/Sonar/Constructor family, including upgraded variants (they
        share the same id prefix, e.g. "drill_module_heavy" starts with
        "drill_module"). Passive containers (Battery Holder, Cargo Rack) don't
        count. See docs/database/equipment_modules.md.
        """
        return active_modules_count_for(self._host.vehicle)

    def cargo_units_count(self):
        """Live cargo unit count, for the travel power formula's cargo-weight term."""
        return cargo_units_count_for(self._host.vehicle)

    def nav_speed_multiplier(self):
        """Top-speed multiplier from mounted Sport Nav modules: 1.0 basic, 1+Sport Nav count (docs/components/nav_module.md .speed_multiplier())."""
        return nav_speed_multiplier_for(self._host.vehicle)

    def mine_wh_per_unit(self, item_id, purity=None):
        """Exact mining Wh/unit for this vehicle's actually-mounted drill (see mine_wh_per_unit_for())."""
        return mine_wh_per_unit_for(self._host.vehicle, item_id, purity)

    def nav_power_multiplier(self):
        """
        Movement power multiplier matching nav_speed_multiplier(). Docs confirm
        1 Sport Nav = 2x speed / 2.6x power exactly; scaling for additional Sport
        Navs isn't precisely documented ("raises draw faster"), so this linearly
        extrapolates the same +1.6x power per +1.0x speed above the 1.0 baseline.
        """
        return nav_power_multiplier_for(self._host.vehicle)

    def default_cruise_throttle(self):
        """
        Fleet-wide default cruise_throttle from the archive
        (DEFAULT_CRUISE_THROTTLE_KEY), falling back to
        DEFAULT_CRUISE_THROTTLE_FALLBACK=0.5 if never set or unreadable.
        VehicleController.__init__ calls this exactly once at construction
        when the thin entrypoint script passes cruise_throttle=None, so
        raising the archive value (e.g. to 1.0) speeds up every such vehicle
        without editing each one's script -- a vehicle constructed with an
        explicit cruise_throttle instead keeps that override regardless of
        this archive value.
        """
        value = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, None)
        if value is None:
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        try:
            value = float(value)
        except (TypeError, ValueError):
            return DEFAULT_CRUISE_THROTTLE_FALLBACK
        return max(self.MIN_SPEEDMODE_THROTTLE, min(self.MAX_SPEEDMODE_THROTTLE, value))

    def construction_calibration_key(self):
        return f"vehicle.wh_per_progress:{self._host.name}"

    def load_wh_per_progress(self):
        value = archive.get(self.construction_calibration_key(), None)
        if value is None:
            value = archive.get("fleet.wh_per_progress", None)
        return value if value is not None else self.CONSTRUCTION_WH_PER_PROGRESS_DEFAULT

    def calibrate_wh_per_progress(self, delta_progress, delta_wh):
        """Dynamically calibrates actual Wh per 100% construction progress from observed execute() calls."""
        if delta_progress > 0.01 and delta_wh > 0.1:
            observed_wh_per_progress = delta_wh / delta_progress
            if 1.0 <= observed_wh_per_progress <= 500.0:
                base_val = self.wh_per_progress if self.wh_per_progress is not None else self.CONSTRUCTION_WH_PER_PROGRESS_DEFAULT
                self.wh_per_progress = (base_val * 0.70) + (observed_wh_per_progress * 0.30)
                archive.set(self.construction_calibration_key(), self.wh_per_progress)

    def get_battery(self):
        """Returns (current_wh, capacity_wh, fraction 0-1)."""
        try:
            wh = self._host.vehicle.battery.wh()
            cap = self._host.vehicle.battery.capacity()
            lvl = self._host.vehicle.battery.level()
            return wh, cap, lvl
        except Exception:
            return 0.0, 100.0, 0.0

    def wh_per_meter_at_throttle(self, throttle, cargo_units=None):
        """Wh/meter at a specific throttle and cargo load, from the travel power/speed model."""
        if throttle <= 0:
            return 0.0
        return self._drive_power_watts(throttle, cargo_units=cargo_units) / self._drive_speed_m_per_hour(throttle)

    def minimum_wh_per_meter(self, cargo_units=None):
        """
        Best-case Wh/meter at the speedmode throttle floor (MIN_SPEEDMODE_THROTTLE).
        This is the true lower bound for a "permanently unreachable" verdict: conserve
        mode can always throttle down this far to stretch a tight budget, so a hard
        infeasibility check must rate distances against this, not the typical
        cruise-throttle rate.
        """
        return self.wh_per_meter_at_throttle(self.MIN_SPEEDMODE_THROTTLE, cargo_units=cargo_units)

    def calculate_trip_energy(self, target_coords, planned_drill_units=0, planned_scans=1, planned_construction_progress=0.0, wh_per_meter=None, mine_item_id=None, mine_purity=None):
        """
        Accurately calculates total energy required for a round-trip expedition:
        1. Energy to drive to target: dist_to_target * outbound Wh/m (current cargo load)
        2. Energy to scan & survey: planned_scans * SONAR_WH_BUDGET
        3. Energy to mine: planned_drill_units * exact Wh/unit for mine_item_id at this
           vehicle's mounted drill and mine_purity (mine_wh_per_unit() -- see its docstring
           and the module-level ORE_DIG_MINUTES/DRILL_POWER_W_BY_HARDNESS_LIMIT/PURITY_DIVISOR
           comment). Falls back to the flat MINE_WH_PER_UNIT average when mine_item_id isn't
           given at all (e.g. a non-mining candidate) -- callers that DO know the target ore
           (vehicle_mining.py/pioneer.py/rover.py's mining candidates always carry harvest_item/purity)
           should always pass it, since the exact rate can run up to ~3.6x the flat average
           for a heavy drill on neutronium vs. a basic drill on iron ore.
        4. Energy to build: planned_construction_progress * wh_per_progress
        5. Energy to drive to nearest charging station from target: dist_target_to_nearest_cs *
           return Wh/m (current cargo + planned_drill_units -- mined ore weighs down the return leg)
        6. Safety buffer (SAFETY_MARGIN_MULTIPLIER) + hard emergency floor (8 Wh)

        wh_per_meter overrides the rate for BOTH legs (e.g. pass self.minimum_wh_per_meter()
        to test best-case feasibility at the speedmode throttle floor). Defaults to the
        cruise-throttle rate, computed separately per leg since cargo differs between them.
        """
        self._host.log.trace(
            f"[{self._host.name}] calculate_trip_energy(target={target_coords}, planned_drill_units={planned_drill_units}, "
            f"planned_scans={planned_scans}, planned_construction_progress={planned_construction_progress}, "
            f"wh_per_meter={wh_per_meter}, mine_item_id={mine_item_id}, mine_purity={mine_purity}) called."
        )
        current_pos = self._host.get_position()
        dist_outbound = self._host.distance_between(current_pos, target_coords)
        nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
        dist_inbound = self._host.distance_between(target_coords, nearest_cs_from_target)

        if wh_per_meter is not None:
            outbound_rate = wh_per_meter
            inbound_rate = wh_per_meter
        else:
            curr_cargo = self.cargo_units_count()
            outbound_rate = self.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=curr_cargo)
            inbound_rate = self.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=curr_cargo + planned_drill_units)

        drive_out_wh = dist_outbound * outbound_rate
        drive_home_wh = dist_inbound * inbound_rate
        sonar_wh = planned_scans * self.SONAR_WH_BUDGET
        mine_rate = self.mine_wh_per_unit(mine_item_id, mine_purity) if mine_item_id else self.MINE_WH_PER_UNIT
        mining_wh = planned_drill_units * mine_rate
        construction_wh = planned_construction_progress * self.wh_per_progress

        net_expedition_wh = drive_out_wh + drive_home_wh + sonar_wh + mining_wh + construction_wh
        buffered_expedition_wh = net_expedition_wh * self.SAFETY_MARGIN_MULTIPLIER
        total_required_wh = buffered_expedition_wh + self.MIN_EMERGENCY_RESERVE_WH

        curr_wh, cap_wh, lvl = self.get_battery()
        is_achievable = curr_wh >= total_required_wh

        self._host.log.debug(
            f"[{self._host.name}] Trip budget: drive_out={drive_out_wh:.1f} Wh ({dist_outbound:.1f}m), "
            f"drive_home={drive_home_wh:.1f} Wh ({dist_inbound:.1f}m to {nearest_cs_from_target}), "
            f"sonar={sonar_wh:.1f} Wh, mining={mining_wh:.1f} Wh ({planned_drill_units} units @ {mine_rate:.2f} Wh/unit), "
            f"construction={construction_wh:.1f} Wh -> net={net_expedition_wh:.1f} Wh, "
            f"+{(self.SAFETY_MARGIN_MULTIPLIER - 1) * 100:.0f}% safety margin = {buffered_expedition_wh:.1f} Wh, "
            f"+{self.MIN_EMERGENCY_RESERVE_WH:.1f} Wh emergency reserve = {total_required_wh:.1f} Wh required "
            f"vs {curr_wh:.1f} Wh on board -> {'achievable' if is_achievable else 'NOT achievable'} "
            f"({'surplus' if is_achievable else 'short by'} {abs(curr_wh - total_required_wh):.1f} Wh)."
        )

        result = {
            "dist_outbound": dist_outbound,
            "dist_inbound": dist_inbound,
            "nearest_cs_coords": nearest_cs_from_target,
            "drive_out_wh": drive_out_wh,
            "drive_home_wh": drive_home_wh,
            "sonar_wh": sonar_wh,
            "mining_wh": mining_wh,
            "construction_wh": construction_wh,
            "net_expedition_wh": net_expedition_wh,
            "total_required_wh": total_required_wh,
            "current_wh": curr_wh,
            "is_achievable": is_achievable
        }
        self._host.log.trace(f"[{self._host.name}] calculate_trip_energy() -> {result}.")
        return result

    def max_mineable_units(self, target_coords, item_id, purity=None):
        """
        Max units of item_id affordable on the battery currently on board, for
        a round trip to target_coords and back to the nearest charging station
        from there -- an upfront energy-based trip size (mine exactly what's
        affordable) rather than a cargo-capacity assumption. With mining
        outposts stockpiling ahead of demand, mine-till-full-then-recharge-
        and-resume trips (mine_until_full_or_exhausted()) are no longer the
        common case, so this replaces cargo.capacity() as the default
        estimate wherever one's needed -- mine_until_full_or_exhausted() still
        exists as a safety net if the real trip runs richer/leaner than
        estimated.

        Solves calculate_trip_energy()'s own budget equation directly for
        units instead of guessing-and-checking: every cost term below is
        either fixed (outbound drive, base return drive) or exactly linear in
        units (mined Wh via mine_wh_per_unit(), extra return-drive Wh from the
        added cargo weight), so the max affordable count follows in one step.
        """
        current_pos = self._host.get_position()
        dist_outbound = self._host.distance_between(current_pos, target_coords)
        nearest_cs_from_target, _ = self.get_nearest_charging_station(from_coords=target_coords)
        dist_inbound = self._host.distance_between(target_coords, nearest_cs_from_target)

        curr_cargo = self.cargo_units_count()
        outbound_rate = self.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=curr_cargo)
        inbound_rate_base = self.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=curr_cargo)
        inbound_rate_plus_one = self.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=curr_cargo + 1)
        marginal_inbound_rate_per_unit = inbound_rate_plus_one - inbound_rate_base

        fixed_wh = (dist_outbound * outbound_rate) + (dist_inbound * inbound_rate_base)
        marginal_wh_per_unit = (dist_inbound * marginal_inbound_rate_per_unit) + self.mine_wh_per_unit(item_id, purity)

        curr_wh, _, _ = self.get_battery()
        available_for_units = curr_wh - self.MIN_EMERGENCY_RESERVE_WH - (fixed_wh * self.SAFETY_MARGIN_MULTIPLIER)
        if available_for_units <= 0 or marginal_wh_per_unit <= 0:
            self._host.log.debug(f"[{self._host.name}] max_mineable_units({item_id}, purity={purity}): 0 units affordable (available_for_units={available_for_units:.1f} Wh, marginal_wh_per_unit={marginal_wh_per_unit:.2f} Wh -- fixed_wh={fixed_wh:.1f}, curr_wh={curr_wh:.1f}, reserve={self.MIN_EMERGENCY_RESERVE_WH:.1f}).")
            return 0

        max_units = int(available_for_units // (marginal_wh_per_unit * self.SAFETY_MARGIN_MULTIPLIER))
        cargo_capacity = self._host.vehicle.cargo.capacity() if hasattr(self._host.vehicle, "cargo") else max_units
        final_units = max(0, min(max_units, cargo_capacity))
        self._host.log.debug(f"[{self._host.name}] max_mineable_units({item_id}, purity={purity}): energy-affordable={max_units} (available={available_for_units:.1f} Wh / {marginal_wh_per_unit:.2f} Wh/unit), cargo_capacity={cargo_capacity} -> {final_units} units.")
        return final_units

    def energy_needed_to_reach(self, target_coords):
        """Calculates minimum energy required to reach target coordinates with safety buffer."""
        dist = self._host.distance_between(self._host.get_position(), target_coords)
        drive_wh = dist * self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def energy_needed_to_reach_base(self):
        """Calculates energy required to drive back to home base staging slot."""
        return self.energy_needed_to_reach(self._host.assigned_slot_coords)

    def energy_needed_to_return_now(self):
        """
        Calculates minimum energy strictly required to drive to the nearest charging
        station right now. This is the true floor (uses minimum_wh_per_meter(), the
        speedmode throttle-floor rate) -- conserve mode can always crawl home at
        MIN_SPEEDMODE_THROTTLE to stretch a tight budget, so a panic/abort-safety
        check must not assume the typical cruise-throttle cost.
        """
        nearest_cs, _ = self.get_nearest_charging_station()
        dist_cs = self._host.distance_between(self._host.get_position(), nearest_cs)
        drive_wh = dist_cs * self.minimum_wh_per_meter()
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def energy_needed_to_return_comfortably(self):
        """
        Energy required to reach the nearest charging station right now at the
        normal cruise throttle (self.cruise_throttle), not the speedmode floor.

        Field-work loops (mining, construction, survey) should use this -- not
        energy_needed_to_return_now() -- as the *proactive* "time to head back"
        trigger. Grinding right up to the bare survival floor means the return
        leg itself can then only afford the slowest possible throttle (conserve
        mode has nothing left to spend), turning a routine return trip into a
        multi-hour crawl. Stopping a little earlier, with enough reserve for a
        normal-speed return, sacrifices a small amount of extra work for a much
        shorter trip home -- a simple heuristic rather than an exact optimum
        (computing the true time/output tradeoff would need to weigh real-world
        wait time against ore/progress value, which has no clean in-game unit).

        The hard mid-drive abort net inside drive_to() intentionally keeps using
        the true floor (energy_needed_to_return_now()) -- that one is a last-resort
        safety check, not a scheduling decision, and must never be softened.
        """
        nearest_cs, _ = self.get_nearest_charging_station()
        dist_cs = self._host.distance_between(self._host.get_position(), nearest_cs)
        drive_wh = dist_cs * self.wh_per_meter_at_throttle(self._host.cruise_throttle)
        return (drive_wh * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH

    def _drive_speed_m_per_hour(self, throttle):
        """speed (m/h) = 100.0 * throttle * Sport Nav speed multiplier."""
        return self.DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * throttle * self.nav_speed_multiplier()

    def _drive_power_watts(self, throttle, cargo_units=None):
        """
        Developer-confirmed travel power formula:
        power (W) = (BASE_TRAVEL_POWER_W + MODULE_TRAVEL_POWER_W * active_modules
                     + CARGO_UNIT_TRAVEL_POWER_W * cargo_units) * throttle^1.5 * nav_power_multiplier
        """
        if cargo_units is None:
            cargo_units = self.cargo_units_count()
        base_w = self.BASE_TRAVEL_POWER_W + (self.MODULE_TRAVEL_POWER_W * self.active_modules_count()) + (self.CARGO_UNIT_TRAVEL_POWER_W * cargo_units)
        return base_w * (throttle ** 1.5) * self.nav_power_multiplier()

    def energy_wh_for_leg(self, distance_m, throttle, cargo_units=None):
        """
        Energy to cover distance_m at a constant throttle and cargo load.
        Routes through wh_per_meter_at_throttle() (mathematically identical to
        the old power*time computation: power/speed*distance == wh_per_meter*
        distance) so a chassis-specific override -- e.g. RoverController's
        linear model in lib/rover.py -- is honored here too, not just by
        direct wh_per_meter_at_throttle() callers.
        """
        if distance_m <= 0 or throttle <= 0:
            return 0.0
        return distance_m * self.wh_per_meter_at_throttle(throttle, cargo_units=cargo_units)

    def max_safe_throttle_for_leg(self, target_coords):
        """
        Highest throttle for which driving to target_coords still leaves enough
        charge (at the speedmode throttle floor -- the safe assumption for
        whatever's left over) to reach the nearest charging station from there
        afterward. Returns 0.0 if even the slowest throttle would not leave a
        safe reserve.

        Solved analytically: under the travel power model, Wh/m for a leg scales
        with sqrt(throttle) (power ~ throttle^1.5, speed ~ throttle), not throttle
        itself, so the bound is solved via that relationship rather than a linear
        one:
            leg_wh(t) = distance * coeff * sqrt(t), where
            coeff = (BASE_TRAVEL_POWER_W + MODULE_TRAVEL_POWER_W*active_modules
                     + CARGO_UNIT_TRAVEL_POWER_W*cargo_units) * nav_power_multiplier
                    / (DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * nav_speed_multiplier)
            leg_wh(t) * SAFETY_MARGIN_MULTIPLIER <= available_for_leg
            => t <= (available_for_leg / (distance * coeff * SAFETY_MARGIN_MULTIPLIER)) ** 2
        """
        distance = self._host.distance_to(target_coords[0], target_coords[1])
        if distance <= 0:
            return self.MAX_SPEEDMODE_THROTTLE

        curr_wh, _, _ = self.get_battery()
        nearest_cs, _ = self.get_nearest_charging_station(from_coords=target_coords)
        reserve_needed = (self._host.distance_between(target_coords, nearest_cs) * self.minimum_wh_per_meter() * self.SAFETY_MARGIN_MULTIPLIER) + self.MIN_EMERGENCY_RESERVE_WH
        available_for_leg = curr_wh - reserve_needed
        if available_for_leg <= 0:
            self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg({target_coords}): 0.0 (no safe reserve -- {curr_wh:.1f} Wh on board < {reserve_needed:.1f} Wh needed to reach {nearest_cs} afterward).")
            return 0.0

        base_w = self.BASE_TRAVEL_POWER_W + (self.MODULE_TRAVEL_POWER_W * self.active_modules_count()) + (self.CARGO_UNIT_TRAVEL_POWER_W * self.cargo_units_count())
        coeff = (base_w * self.nav_power_multiplier()) / (self.DRIVE_SPEED_M_PER_HOUR_PER_THROTTLE * self.nav_speed_multiplier())
        denom = distance * coeff * self.SAFETY_MARGIN_MULTIPLIER
        if denom <= 0:
            self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg({target_coords}): {self.MAX_SPEEDMODE_THROTTLE} (zero-cost leg, denom={denom}).")
            return self.MAX_SPEEDMODE_THROTTLE

        sqrt_t_max = available_for_leg / denom
        result = max(0.0, min(self.MAX_SPEEDMODE_THROTTLE, sqrt_t_max ** 2))
        self._host.log.debug(f"[{self._host.name}] max_safe_throttle_for_leg({target_coords}): {result*100:.0f}% (available_for_leg={available_for_leg:.1f} Wh, distance={distance:.1f}m, reserve_needed={reserve_needed:.1f} Wh).")
        return result

    def select_cruise_throttle(self, target_x, target_y):
        """
        Picks this leg's driving throttle: self.cruise_throttle (set at
        construction, or the archive-backed default_cruise_throttle() when
        the entrypoint script passed None -- see VehicleController.__init__),
        capped down only as far as needed to still leave a safe reserve to
        reach a charging station from the destination
        (max_safe_throttle_for_leg()). Never higher than requested, never
        lower than MIN_SPEEDMODE_THROTTLE.

        Set self.cruise_throttle to MAX_SPEEDMODE_THROTTLE (1.0) -- directly,
        or by raising DEFAULT_CRUISE_THROTTLE_KEY in the archive -- for the
        old "highspeed" behavior (fastest throttle the battery safely
        allows): this single formula already produces exactly that, since
        capping only ever throttles DOWN from whatever baseline was
        requested, never up past it.
        """
        baseline = min(self._host.cruise_throttle, self.MAX_SPEEDMODE_THROTTLE)
        max_safe = self.max_safe_throttle_for_leg((target_x, target_y))
        if max_safe >= baseline:
            return baseline
        return max(self.MIN_SPEEDMODE_THROTTLE, min(baseline, max_safe))

    def get_all_charging_stations(self):
        """
        Discovers every deployed Vehicle Charging Station across all owned outposts
        (outpost_network.outposts() already includes home), filtered by exact
        type_id so any number of stations is found regardless of id numbering.
        Returns a list of dicts: [{"id": str, "coords": (float, float), "component": obj}]
        """
        stations = []
        found_ids = set()

        outpost_net = get_component("outpost_network")
        if outpost_net and hasattr(outpost_net, "outposts"):
            try:
                outposts = outpost_net.outposts()
            except Exception:
                outposts = []

            for op in outposts:
                if not hasattr(op, "buildings"):
                    continue
                try:
                    buildings = op.buildings(CHARGING_STATION_TYPE_ID)
                except Exception:
                    continue
                for b in buildings:
                    b_id = getattr(b, "id", "")
                    if not b_id or b_id in found_ids:
                        continue
                    pos = self._host.extract_coords(getattr(b, "position", None))
                    if not pos:
                        continue
                    found_ids.add(b_id)
                    stations.append({
                        "id": b_id,
                        "coords": pos,
                        "component": get_component(b_id) or b
                    })

        return stations

    def get_nearest_charging_station(self, from_coords=None):
        """
        Returns the closest known charging station tuple: (coords, station_info_dict).
        If no station is detected, falls back to (self.home_coords, {}).
        """
        ref_coords = from_coords if from_coords is not None else self._host.get_position()
        stations = self.get_all_charging_stations()
        if not stations:
            self._host.log.debug(f"[{self._host.name}] get_nearest_charging_station({ref_coords}): no stations discovered network-wide, falling back to home slot {self._host.home_coords}.")
            return self._host.home_coords, {"id": "home_slot", "coords": self._host.home_coords, "component": self._host.home_charging_station}

        best_station = min(
            stations,
            key=lambda st: self._host.distance_between(ref_coords, st["coords"])
        )
        self._host.log.debug(f"[{self._host.name}] get_nearest_charging_station({ref_coords}): chose '{best_station.get('id')}' at {best_station['coords']} ({self._host.distance_between(ref_coords, best_station['coords']):.1f}m), out of {len(stations)} candidate(s).")
        return best_station["coords"], best_station

    def get_outpost_ref(self, outpost_id=None):
        """
        Resolves outpost_id to its live OutpostRef, or the home outpost if
        outpost_id is None. A one-off lookup-by-id utility -- VehicleController
        calls this exactly once at construction to populate self.home_outpost
        (see __init__), so prefer reading that cached field over calling this
        again for the vehicle's own home outpost. Still useful standalone for
        resolving some *other* outpost id (e.g. a future transporter's source
        outpost, distinct from this vehicle's own home_base).
        """
        network = get_component("outpost_network")
        if not network:
            return None
        if outpost_id is None:
            return network.home() if hasattr(network, "home") else None
        if hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    if getattr(outpost, "id", None) == outpost_id:
                        return outpost
            except Exception:
                pass
        return None

    def find_charging_station(self, outpost):
        """
        First Vehicle Charging Station building object at outpost (an
        already-resolved outpost object, not an id -- see get_outpost_ref()).
        Called once at construction to populate self.home_charging_station;
        prefer that cached field over calling this again for the vehicle's
        own home outpost.
        """
        if not outpost or not hasattr(outpost, "buildings"):
            return None
        try:
            for b in outpost.buildings(CHARGING_STATION_TYPE_ID):
                if self._host.extract_coords(getattr(b, "position", None)):
                    return b
        except Exception:
            pass
        return None

    def get_home_slot_coords(self):
        """
        Calculates the base / charging station staging coordinates for this
        vehicle, at whichever outpost self.home_base names (None = the
        production/home outpost). All vehicles dock within the ~2m common
        service area of base & charging station. Reads self.home_outpost/
        self.home_charging_station -- resolved once at construction (see
        VehicleController.__init__), not re-walked here. Falls back to the
        outpost's own coords() if it has no charging station yet, and only to
        a literal (0, 0) if outpost_network itself was unavailable at
        construction time.
        """
        if self._host.home_charging_station is not None:
            pos = self._host.extract_coords(getattr(self._host.home_charging_station, "position", None))
            if pos:
                return pos
        if self._host.home_outpost is not None and hasattr(self._host.home_outpost, "coords"):
            try:
                coords = self._host.home_outpost.coords()
                if coords:
                    return (float(coords[0]), float(coords[1]))
            except Exception:
                pass
        return (0.0, 0.0)

    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        """
        Parks at Vehicle Charging Station / base staging slot and charges until target level.
        Cooperates with the station controller (charging_station_*.py) which handles hardware
        charge() calls locally.
        """
        curr_wh, cap_wh, lvl = self.get_battery()
        if lvl >= target_level - 0.02:
            self._host.log.print(f"[{self._host.name}] Battery already charged ({lvl*100:.0f}%).")
            return True

        cs = None
        if station_coords is None:
            station_coords, st_info = self.get_nearest_charging_station()
            if not station_id:
                station_id = st_info.get("id")
            cs = st_info.get("component")
        else:
            station_coords = (float(station_coords[0]), float(station_coords[1]))
            if station_id:
                cs = get_component(station_id)
            if not cs:
                for st in self.get_all_charging_stations():
                    if self._host.distance_between(st["coords"], station_coords) < 2.0:
                        cs = st.get("component")
                        if not station_id:
                            station_id = st.get("id")
                        break

        if not cs:
            if station_id:
                cs = get_component(station_id)
            if not cs:
                stations = self.get_all_charging_stations()
                if stations:
                    fallback = stations[0]
                    cs = fallback.get("component")
                    if not station_id:
                        station_id = fallback.get("id")

        cs_coords = station_coords or self._host.home_coords

        # Verify whether vehicle is actually inside the station's docked set
        is_docked = False
        if cs and hasattr(cs, "get_docked"):
            try:
                docked_fn = getattr(cs, "get_docked")
                is_docked = self._host.name in docked_fn()
            except Exception:
                pass

        if not is_docked:
            # drive_to() already short-circuits instantly when already within
            # precision, so there's no need to special-case "close but not yet
            # registered docked" with a heavier self.return_to_base() detour
            # (which also drives to assigned_slot_coords, not necessarily
            # cs_coords, and releases the current target claim) -- just always
            # re-issue the drive command toward the actual station coords.
            dist_to_cs = self._host.distance_to(cs_coords[0], cs_coords[1])
            self._host.log.print(f"[{self._host.name}] Position is {dist_to_cs:.1f}m from charging station '{station_id or 'station'}'. Driving to docking pad...")
            self._host.drive_to(cs_coords[0], cs_coords[1], precision=1.0)

        if hasattr(self._host.vehicle, "nav"):
            try:
                self._host.vehicle.nav.brake()
            except Exception:
                pass

        sleep(0.5)
        self._host.publish_telemetry("CHARGING")
        self._host.log.print(f"[{self._host.name}] Docked at station '{station_id or 'station'}'. Waiting for charge ({lvl*100:.0f}% -> {target_level*100:.0f}%)...")

        wait_cycles = 0
        last_reported_lvl = lvl

        while True:
            curr_wh, cap_wh, lvl = self.get_battery()
            if lvl >= target_level - 0.01:
                self._host.log.print(f"[{self._host.name}] Charging complete ({curr_wh:.1f} Wh, {lvl*100:.0f}%).")
                break

            if abs(lvl - last_reported_lvl) >= 0.10:
                self._host.log.print(f"[{self._host.name}] Charging in progress... ({lvl*100:.0f}%, {curr_wh:.1f} Wh)")
                last_reported_lvl = lvl

            wait_cycles += 1
            if wait_cycles % 5 == 0 and cs:
                try:
                    get_docked_fn = getattr(cs, "get_docked", None)
                    docked = get_docked_fn() if get_docked_fn else []
                    if self._host.name not in docked:
                        self._host.log.level("warn").print(f"[{self._host.name}] Not yet registered in station dock area. Re-aligning to charging station ({cs_coords})...")
                        self._host.drive_to(cs_coords[0], cs_coords[1], precision=1.0)
                        if hasattr(self._host.vehicle, "nav"):
                            self._host.vehicle.nav.brake()
                    else:
                        get_active_fn = getattr(cs, "get_active", None)
                        get_queue_fn = getattr(cs, "get_queue", None)
                        active = get_active_fn() if get_active_fn else []
                        queued = get_queue_fn() if get_queue_fn else []
                        if self._host.name not in active and self._host.name not in queued:
                            st_script = f"{station_id}.py" if station_id and "charging_station" in station_id else "charging_station_1.py"
                            self._host.log.level("warn").print(f"[{self._host.name}] Advisory: Vehicle is docked, but charging station '{station_id}' has not queued it yet. Ensure '{st_script}' is running!")
                            try:
                                notify(f"[{self._host.name}] Docked and waiting. Ensure '{st_script}' is running!", level="info", duration_seconds=8.0)
                            except Exception:
                                pass
                except Exception:
                    pass

            sleep(2.0)

        return True
