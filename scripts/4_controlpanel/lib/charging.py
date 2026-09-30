# Shared Library for Vehicle Charging Station & Fleet Rescue Management
# Manages docked vehicle fast-charging, queue optimization, and automated rescue
# drone dispatch for stranded or critically low-battery vehicles in the field.
from vehicle_energy import rescue_wh_per_meter_for
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester, parked_ids, parked_nearest, wake_for_visit

class ChargingStationController:
    """
    Automates a Vehicle Charging Station.
    - Manages charging queues for docked vehicles (Rovers, Pioneers).
    - Monitors the entire fleet via get_component("fleet").
    - Detects stranded vehicles or low-battery vehicles in the field and auto-dispatches the rescue drone.
    - Broadcasts fleet charge status and rescue events via popup toasts (notify).
    """
    RETURN_SAFETY_MARGIN = 1.05
    RETURN_EMERGENCY_RESERVE_WH = 8.0
    RESCUE_EXTRA_RESERVE_WH = 8.0
    # Poll cadence: ACTIVE while this station has work (bays charging or queued,
    # a rescue under way, a vehicle it is responsible for stranded/below floor/
    # heading home); IDLE otherwise.
    ACTIVE_POLL_SECONDS = 1.5
    IDLE_POLL_SECONDS = 5.0

    def __init__(self, station, target_charge_level=1.0):
        self.station = station
        self.name = getattr(station, "id", "vehicle_charging_station")
        self.target_charge_level = target_charge_level
        self.fleet = get_component("fleet")
        self.power = get_component("power_control")

        self.last_rescued_vehicle = None
        self.log = TreeConsole(module="charging")
        self.parker = ParkRequester(self.name, "charging_station")

    def all_station_refs(self):
        """
        Returns [{"id": str, "coords": (x, y)}, ...] for every deployed charging
        station. BuildingRef.position is a plain (x, y) tuple, but OutpostRef.position
        is a *method* (returns a Position snapshot) -- OutpostRef.x/.y are the plain
        floats to use instead. Treating OutpostRef.position as a tuple raises
        "'native_fn' object has no attribute 'x'" every cycle.
        """
        refs = []

        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    for building in outpost.buildings("charging_station"):
                        pos = getattr(building, "position", None)
                        b_id = getattr(building, "id", None)
                        if b_id and pos and len(pos) >= 2:
                            coord = (float(pos[0]), float(pos[1]))
                            if not any(r["id"] == b_id for r in refs):
                                refs.append({"id": b_id, "coords": coord})
            except Exception as error:
                swallowed("charging.ChargingStationController.all_station_refs: network.outposts", error)

        if not any(r["id"] == self.name for r in refs):
            station_outpost = getattr(self.station, "outpost", None)
            if station_outpost is not None:
                x = getattr(station_outpost, "x", None)
                y = getattr(station_outpost, "y", None)
                if x is not None and y is not None:
                    refs.append({"id": self.name, "coords": (float(x), float(y))})
        return refs

    def charging_station_coords(self):
        """Returns known charging-station coordinates, nearest first when available."""
        return [r["coords"] for r in self.all_station_refs()]

    def my_coords(self):
        """This station's own coordinates, from the shared station-ref list."""
        for r in self.all_station_refs():
            if r["id"] == self.name:
                return r["coords"]
        return None

    def is_nearest_station_to(self, vehicle_ref):
        """
        True when this station is the closest known charging station to
        vehicle_ref. Every deployed station runs its own independent copy of
        this script and polls the same fleet snapshot, so without this check
        every station within range would dispatch its own rescue drone to the
        same stranded vehicle. Ties (e.g. a solo station, or coordinates that
        can't be resolved) default to True rather than deadlocking silent.
        """
        my_pos = self.my_coords()
        if my_pos is None:
            return True
        my_dist = ((vehicle_ref.x - my_pos[0]) ** 2 + (vehicle_ref.y - my_pos[1]) ** 2) ** 0.5
        for ref in self.all_station_refs():
            if ref["id"] == self.name:
                continue
            other_dist = ((vehicle_ref.x - ref["coords"][0]) ** 2 + (vehicle_ref.y - ref["coords"][1]) ** 2) ** 0.5
            if other_dist < my_dist:
                return False
        return True

    def assess_stations(self, vehicle_ref, refs, self_known):
        """
        One pass over station refs: (is_mine, nearest_distance, nearest_coords).
        is_mine matches is_nearest_station_to(): True when this station's own
        position is unknown, otherwise True unless another station is strictly
        closer. nearest_* are None when there are no stations.
        """
        x = vehicle_ref.x
        y = vehicle_ref.y
        best = None
        best_coords = None
        mine = None
        for ref in refs:
            coords = ref["coords"]
            dist_sq = (x - coords[0]) ** 2 + (y - coords[1]) ** 2
            if ref["id"] == self.name:
                mine = dist_sq
            if best is None or dist_sq < best:
                best = dist_sq
                best_coords = coords
        is_mine = (not self_known) or mine is None or mine <= best
        return is_mine, (None if best is None else best ** 0.5), best_coords

    def return_floor_wh(self, vehicle_ref, distance=None):
        """
        Wh a vehicle needs on board right now to safely self-navigate to the
        nearest known charging station -- the same floor drive_to()'s own hard
        abort (energy_needed_to_return_now()) enforces from the vehicle's own
        side. Falling below this means the vehicle can no longer reach a
        station under its own power and genuinely needs a rescue, regardless
        of what fraction of its (not necessarily known here) capacity that
        represents -- a fixed battery-level percentage doesn't track a
        per-vehicle, per-distance floor like this does. distance: metres to
        the nearest station when the caller already has it (None = look up).
        """
        if distance is None:
            stations = self.charging_station_coords()
            if not stations:
                return 0.0
            distance = min(
                ((vehicle_ref.x - x) ** 2 + (vehicle_ref.y - y) ** 2) ** 0.5
                for x, y in stations
            )

        vehicle = None
        try:
            vehicle = get_component(vehicle_ref.id)
        except Exception as error:
            swallowed("charging.ChargingStationController.return_floor_wh: get_component", error)
            vehicle = None

        # Rescue is a last-resort case, so rate the leg at the speedmode throttle
        # floor (cheapest possible Wh/m) -- rescue_wh_per_meter_for() already
        # handles the "vehicle unreachable" fallback internally.
        wh_per_meter = rescue_wh_per_meter_for(vehicle)
        return (distance * wh_per_meter * self.RETURN_SAFETY_MARGIN) + self.RETURN_EMERGENCY_RESERVE_WH

    def rescue_target_level(self, vehicle_ref, floor=None):
        """Calculates charge needed to reach the nearest station with safety reserve. floor: precomputed return_floor_wh()."""
        capacity = getattr(vehicle_ref, "battery_capacity", None)
        current_wh = getattr(vehicle_ref, "battery_wh", 0.0)
        if not capacity:
            try:
                vehicle = get_component(vehicle_ref.id)
                capacity = vehicle.battery.capacity()
                current_wh = vehicle.battery.wh()
            except Exception as error:
                swallowed("charging.ChargingStationController.rescue_target_level: get_component", error)
                capacity = None
        if not capacity or capacity <= 0:
            return 1.0

        if floor is None:
            floor = self.return_floor_wh(vehicle_ref)
        target_wh = max(current_wh, floor + self.RESCUE_EXTRA_RESERVE_WH)
        return min(1.0, target_wh / capacity)

    def is_station_powered(self):
        """Verifies whether this charging station currently has grid power."""
        if self.power and hasattr(self.power, "is_powered"):
            try:
                return self.power.is_powered(self.name)
            except Exception as error:
                swallowed("charging.ChargingStationController.is_station_powered: self.power.is_powered", error)
        return True

    def manage_docked_vehicles(self):
        """Inspects all docked vehicles and ensures they are actively charging up to target level. True while bays are active or queued."""
        docked_ids = self.station.get_docked()
        if not docked_ids:
            return False

        active_bays = self.station.get_active()
        queued = self.station.get_queue()
        busy = bool(active_bays) or bool(queued)

        for v_id in docked_ids:
            try:
                v = get_component(v_id)
                if not v or not hasattr(v, "battery"):
                    continue

                lvl = v.battery.level()
                wh = v.battery.wh()

                # If vehicle is below target and not active or queued, queue it for charging
                if lvl < (self.target_charge_level - 0.02):
                    if v_id not in active_bays and v_id not in queued:
                        res = self.station.charge(v_id, self.target_charge_level)
                        busy = True
                        if res.status in ["ok", "charging", "queued"]:
                            self.log.print(f"[{self.name}] Queued docked vehicle {v_id} ({lvl*100:.0f}%, {wh:.1f} Wh) for charge.")
                        elif res.status != "target_reached":
                            self.log.level("warn").print(f"[{self.name}] Charge queue notice for {v_id}: {res.status} - {res.message}")
            except Exception as e:
                swallowed("charging.ChargingStationController.manage_docked_vehicles: get_component", e)
        return busy

    def manage_fleet_rescues(self):
        """
        Monitors all vehicles in the field.
        If any rover or pioneer is stranded, stalled, or critically low on battery,
        and not already docked or being rescued, dispatch the rescue drone!
        Only the nearest station does the battery/floor work for a vehicle.
        True while a rescue is in progress or a vehicle this station is
        responsible for is stranded, below floor or heading home.
        """
        if self.station.is_rescuing():
            target_name = self.station.get_rescue_target()
            if target_name and target_name != self.last_rescued_vehicle:
                self.last_rescued_vehicle = target_name
                self.log.print(f"[{self.name}] Rescue drone currently in field assisting: {target_name}.")
            return True

        self.last_rescued_vehicle = None

        if not self.fleet:
            return False

        # Check all owned ground vehicles
        try:
            vehicles = self.fleet.vehicles()
        except Exception as error:
            swallowed("charging.ChargingStationController.manage_fleet_rescues: self.fleet.vehicles", error)
            return False

        # Parked stations (lib/script_parking.py) take no responsibility; a vehicle
        # needing attention whose nearest station is parked gets that station
        # woken instead, so the nearest station still watches and rescues it.
        refs = self.all_station_refs()
        parked = parked_ids("charging_station")
        parked.discard(self.name)  # running, so awake whatever the archive says
        awake = [r for r in refs if r["id"] not in parked]
        self_known = any(r["id"] == self.name for r in awake)
        verbose = self.log.verbose
        busy = False
        for v_ref in vehicles:
            # Do not rescue docked vehicles or those already being rescued
            if v_ref.is_docked or v_ref.is_being_rescued or v_ref.rescue_status != "none":
                continue

            # Every deployed station runs this same script independently
            # against the same fleet snapshot -- only the nearest one acts,
            # or every station in range would dispatch its own drone to the
            # same vehicle.
            is_mine, distance, _nearest = self.assess_stations(v_ref, awake, self_known)
            if not is_mine:
                continue

            v_id = v_ref.id
            v_name = v_ref.name
            v_status = v_ref.status
            v_lvl = v_ref.battery_level
            v_wh = v_ref.battery_wh

            # A vehicle below its safe return target is only watched (its own
            # script budgets the way back). Rescue is reserved for a stranded
            # vehicle or one that can no longer reach a station under its own power (see return_floor_wh() -- a vehicle's
            # own drive_to() never willingly drains below this same floor, so it
            # can sit there forever without ever registering as engine-"stranded";
            # this is the backstop for that limbo state).
            is_stranded = v_status in ["stranded", "stalled_no_battery"]
            return_floor = 0.0 if distance is None else self.return_floor_wh(v_ref, distance)
            target_level = self.rescue_target_level(v_ref, return_floor)
            is_below_floor = v_wh <= return_floor
            if verbose:
                self.log.trace(f"[{self.name}] Fleet check {v_id}: status='{v_status}', level={v_lvl*100:.0f}%, wh={v_wh:.1f}, return_floor={return_floor:.1f} Wh, target_level={target_level*100:.0f}%, stranded={is_stranded}, below_floor={is_below_floor}.")

            if parked and (is_stranded or is_below_floor or v_lvl < target_level):
                handoff = parked_nearest(v_ref, refs, parked, distance)
                if handoff:
                    busy = True
                    wake_for_visit(handoff, f"{v_name} needs its nearest station")
                    self.log.print(f"[{self.name}] {v_name} ({v_lvl*100:.0f}%) is nearest to parked '{handoff}'; woke it to take over.")
                    continue

            if v_lvl < target_level and not is_stranded and not is_below_floor:
                # Low but able to reach a station: the vehicle's own script budgets
                # its way back (lib/vehicle_energy.py); this station only watches.
                busy = True
                continue

            if is_stranded or is_below_floor:
                busy = True
                reason = "STRANDED" if is_stranded else f"CRITICAL BATTERY ({v_lvl*100:.0f}%, {v_wh:.1f} Wh, below {return_floor:.1f} Wh return floor)"
                self.log.start(f"[{self.name}] Rescue {v_name} ({v_id})")
                self.log.level("warn").print(f"[{self.name}] Emergency! Vehicle {v_name} ({v_id}) in distress: {reason} at ({v_ref.x:.1f}, {v_ref.y:.1f}).")

                try:
                    notify(f"[RESCUE DISPATCH] Sending rescue drone to {v_name} ({reason})!", level="warn", duration_seconds=10.0)
                except Exception as error:
                    swallowed("charging.ChargingStationController.manage_fleet_rescues: notify", error)

                # Dispatch rescue drone
                self.log.debug(f"[{self.name}] {v_id} selected for rescue this cycle ({reason}); only one drone dispatch is attempted per step(), any other distressed vehicle waits for the next cycle.")
                res = self.station.dispatch_rescue(v_id, target_level)
                if res.status == "ok":
                    self.log.print(f"[{self.name}] Rescue drone launched to {v_id}; target charge {target_level*100:.0f}% for safe station return.")
                    self.last_rescued_vehicle = v_id
                    self.log.end(f"[{self.name}] Rescue dispatched to {v_id}")
                    break
                elif res.status == "already_dispatched":
                    self.log.end(f"[{self.name}] Rescue already dispatched for {v_id}")
                    break
                else:
                    self.log.level("warn").print(f"[{self.name}] Dispatch rejection: {res.status} - {res.message}")
                    self.log.end(f"[{self.name}] Rescue dispatch rejected for {v_id}")
        return busy

    def step(self):
        """Single supervision cycle for dock charging and field rescue; returns True while this station has work (poll fast)."""
        if not self.is_station_powered():
            self.parker.update(False)
            return False

        docked_busy = self.manage_docked_vehicles()
        rescue_busy = self.manage_fleet_rescues()
        busy = docked_busy or rescue_busy
        self.parker.update(not busy)
        return busy

    def run(self, poll_interval=ACTIVE_POLL_SECONDS, idle_poll_seconds=IDLE_POLL_SECONDS):
        """Continuous supervision loop."""
        bay_count = getattr(self.station, "get_bay_count", lambda: 1)()
        bay_rate = getattr(self.station, "get_bay_rate", lambda: 30)()
        self.log.print(f"Charging Station ({self.name}) online via Shared Library ({bay_count} bay(s), {bay_count * bay_rate} W max pool).")
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
