# Retiring Pioneers, Rovers and drones: recall home, empty, undeploy (builder_automation.py).
#
# Operator-triggered only: the "retire" button on the FLEET card's Ground or
# Drones tab (vehicles_panel.py) calls request_decommission(), which writes a
# "requested" entry and raises the machine's recall flag. Pressing it again
# (cancel_decommission()) drops the entry and clears the recall.
#
#   1. requested -- the machine's own script handles the recall as usual
#      (lib/vehicle_claims.py / lib/drone_claims.py handle_recall_if_active())
#      and, once home, calls its prepare step: a Pioneer unloads its cargo at
#      HOME_BASE, charges to DECOMMISSION_MIN_SOC (Portable Batteries sell
#      for their charge %), then uninstalls/unmounts and sells its parts one
#      at a time -- undeploy() refuses with inventory_full when Inventory has
#      no slot for every returned part. A Rover does the same minus the
#      charge (integrated battery). A drone unloads into the Depot it is
#      docked at. Then it marks the entry "ready". Unloading and stripping
#      are self-only, so the coordinator never skips this step.
#   2. ready -- the coordinator re-checks the machine is empty (drone: still
#      docked at a Drone Depot), snapshots a vehicle's remaining parts
#      (chassis kit, plus any module the strip left), stops its script and
#      computer.undeploy()s it: the hardware goes to Inventory. Refused ->
#      back to "requested" (script restarted); MAX_UNDEPLOY_ATTEMPTS refusals
#      -> "blocked" and the recall is cleared. inventory_full is not counted
#      as a refusal (retried until a slot frees up).
#   3. undeployed -- a vehicle's snapshot is sold at the Shop (only the
#      units the undeploy returned). Drone hardware stays in Inventory for
#      the next commission/upgrade: drone parts are not sellable. Then every
#      per-machine archive entry is dropped (recall, mission, fleet.status,
#      pickups, yield reservations, Depot stage, home-Depot pin, upgrade
#      orders/state, sport nav request, commission lineage).
#
# State: one dict, fleet.decommission = {machine_id: entry} (CODE_GUIDES.md#archive)
#   entry = {"kind": "pioneer" | "rover" | "drone", "state": "requested" | "ready" | "blocked",
#            "attempts": int, "reason": str}
# Kept free of heavy imports: vehicle_claims.py/drone_claims.py import it
# inside functions, and the cards import it at load. The cleanup imports its
# modules inside _forget_machine().

from archive import archive
from vehicle_claims import set_vehicle_recalled
from drone_claims import set_drone_recalled
from tree_console import TreeConsole
from components import component
from swallow import swallowed
from script_parking import start_script
from storage import inventory_count
from item_tiers import DEPOT_TYPE_TIERS

DECOMMISSION_KEY = "fleet.decommission"
# Vehicle kinds whose chassis kit the coordinator sells after the undeploy.
VEHICLE_KIT_IDS = {"pioneer": "pioneer", "rover": "rover"}
# A Pioneer charges to this before it reports ready: Portable Batteries sell
# for their retained charge (50% floor, docs/components/shop.md). A Rover's
# battery is integrated, so it skips the charge.
DECOMMISSION_MIN_SOC = 0.98
# Undeploy refusals before an entry is "blocked" and the machine released.
MAX_UNDEPLOY_ATTEMPTS = 5
# undeploy() answers that only mean "not right now"; never counted as a refusal.
RETRY_STATUSES = ("inventory_full",)


def decommission_state():
    """The whole {machine_id: entry} dict (empty when missing/malformed)."""
    state = archive.get(DECOMMISSION_KEY, {})
    return state if isinstance(state, dict) else {}


def decommission_entry(machine_id):
    entry = decommission_state().get(machine_id)
    return entry if isinstance(entry, dict) else None


def _update(mutate):
    def updater(state):
        if not isinstance(state, dict):
            state = {}
        mutate(state)
        return state
    archive.transaction(DECOMMISSION_KEY, {}, updater)


def _set_recalled(machine_id, kind, on):
    if kind == "drone":
        set_drone_recalled(machine_id, on)
    else:
        set_vehicle_recalled(machine_id, on)


def request_decommission(machine_id, kind):
    """Card button: queue machine_id ("pioneer", "rover" or "drone") for retirement and recall it."""
    _update(lambda s: s.update({machine_id: {"kind": kind, "state": "requested", "attempts": 0}}))
    _set_recalled(machine_id, kind, True)


def cancel_decommission(machine_id):
    """Card button, second press: drop the request and clear the recall."""
    entry = decommission_entry(machine_id)
    _update(lambda s: s.pop(machine_id, None))
    _set_recalled(machine_id, (entry or {}).get("kind"), False)


def mark_decommission_ready(machine_id):
    """Machine side: home and empty; the coordinator may undeploy it now."""
    def mutate(s):
        entry = s.get(machine_id)
        if isinstance(entry, dict) and entry.get("state") == "requested":
            entry["state"] = "ready"
    _update(mutate)


def is_decommission_requested(machine_id):
    """True while the machine's own script still has to empty itself ("requested")."""
    entry = decommission_entry(machine_id)
    return bool(entry) and entry.get("state") == "requested"


class FleetDecommissionCoordinator:
    """Host side: undeploys ready machines, sells vehicle parts, cleans the archive. State lives in the archive."""

    def __init__(self):
        self.log = TreeConsole(module="fleet_decommission")

    # ------------------------------------------------------------ lookups

    def _fleet_ids(self):
        """({vehicle_id}, {drone_id: DroneRef}); (None, None) when the fleet is unreadable."""
        fleet = component("fleet")
        if not fleet:
            return None, None
        try:
            vehicles = {str(getattr(v, "id", "")) for v in fleet.vehicles()}
            drones = {str(getattr(d, "id", "")): d for d in fleet.drones()}
        except Exception as error:
            swallowed("fleet_decommission.FleetDecommissionCoordinator._fleet_ids: fleet", error)
            return None, None
        return vehicles, drones

    def _depot_ids(self):
        network = component("outpost_network")
        ids = set()
        try:
            for outpost in (network.outposts() if network else []):
                for type_id in DEPOT_TYPE_TIERS:
                    ids.update(getattr(ref, "id", "") for ref in outpost.buildings(type_id))
        except Exception as error:
            swallowed("fleet_decommission.FleetDecommissionCoordinator._depot_ids: outpost_network", error)
        return ids

    def _cargo_count(self, machine_id):
        machine = component(machine_id)
        cargo = getattr(machine, "cargo", None) if machine else None
        try:
            return int(cargo.count() or 0) if cargo else 0
        except Exception as error:
            swallowed("fleet_decommission.FleetDecommissionCoordinator._cargo_count: cargo.count", error)
            return 0

    def _vehicle_parts(self, machine_id, kind):
        """{item_id: count} the undeploy returns: chassis kit, modules and their portables."""
        parts = {VEHICLE_KIT_IDS[kind]: 1}
        machine = component(machine_id)
        try:
            slots = machine.modules() if machine and hasattr(machine, "modules") else []
        except Exception as error:
            swallowed("fleet_decommission.FleetDecommissionCoordinator._vehicle_parts: modules", error)
            slots = []
        for slot in slots:
            for item_id in [getattr(slot, "module_id", None)] + list(getattr(slot, "internal_items", None) or []):
                if item_id:
                    parts[item_id] = parts.get(item_id, 0) + 1
        return parts

    def _stop_script(self, machine_id):
        run = component("run_control")
        try:
            if run and run.is_running(machine_id):
                run.stop(machine_id)
        except Exception as error:
            swallowed("fleet_decommission.FleetDecommissionCoordinator._stop_script: run_control", error)

    def _patch(self, machine_id, **fields):
        def mutate(s):
            entry = s.get(machine_id)
            if isinstance(entry, dict):
                entry.update(fields)
        _update(mutate)

    # ------------------------------------------------------------ main step

    def step(self, current_tick):
        """One pass over every entry. Returns a short summary for builder_automation's summary line."""
        state = decommission_state()
        if not state:
            return "decommission idle"
        vehicles, drones = self._fleet_ids()
        if vehicles is None:
            return "decommission: fleet unreadable"
        computer = component("computer")
        if not computer or not hasattr(computer, "undeploy"):
            return "decommission: no Ship Computer"

        notes = []
        for machine_id, entry in list(state.items()):
            if not isinstance(entry, dict):
                _update(lambda s, k=machine_id: s.pop(k, None))
                continue
            kind = entry.get("kind")
            present = machine_id in drones if kind == "drone" else machine_id in vehicles
            if not present:
                self._forget_machine(machine_id, kind)
                _update(lambda s, k=machine_id: s.pop(k, None))
                self.log.print(f"[decommission] '{machine_id}' no longer exists; entry and archive state dropped.")
                continue
            if entry.get("state") == "ready":
                notes.append(self._retire(machine_id, entry, drones, computer))
            else:
                notes.append(f"{machine_id} {entry.get('state')}")
        return "decommission: " + ", ".join(notes) if notes else "decommission idle"

    def _retire(self, machine_id, entry, drones, computer: "Computer"):
        kind = entry.get("kind")
        self.log.start(f"[decommission] Retiring {kind} '{machine_id}'")
        if self._cargo_count(machine_id) > 0:
            self._patch(machine_id, state="requested")
            self.log.end("cargo aboard again; back to requested")
            return f"{machine_id} not empty"
        if kind == "drone" and getattr(drones.get(machine_id), "current_station", "") not in self._depot_ids():
            self._patch(machine_id, state="requested")
            self.log.end("not docked at a Drone Depot; back to requested")
            return f"{machine_id} not docked"

        parts = self._vehicle_parts(machine_id, kind) if kind in VEHICLE_KIT_IDS else {}
        before = {item_id: inventory_count(item_id) for item_id in parts}
        self._stop_script(machine_id)
        res = computer.undeploy(machine_id)
        if res.status != "ok":
            attempts = int(entry.get("attempts", 0)) + (0 if res.status in RETRY_STATUSES else 1)
            start_script(machine_id)
            if attempts >= MAX_UNDEPLOY_ATTEMPTS:
                self._patch(machine_id, state="blocked", attempts=attempts, reason=res.status)
                _set_recalled(machine_id, kind, False)
                self.log.level("warn").print(f"[decommission] '{machine_id}': undeploy refused {attempts}x ({res.status}: {res.message}); blocked, back to work.")
                self.log.end("blocked")
                return f"{machine_id} blocked ({res.status})"
            self._patch(machine_id, state="requested", attempts=attempts)
            self.log.debug(f"undeploy('{machine_id}') -> {res.status}: {res.message}; attempt {attempts}/{MAX_UNDEPLOY_ATTEMPTS}.")
            self.log.end(f"undeploy {res.status}, retrying")
            return f"{machine_id} undeploy {res.status}"

        sold = self._sell_returned(parts, before) if parts else "hardware kept in Inventory"
        self._forget_machine(machine_id, kind)
        _update(lambda s: s.pop(machine_id, None))
        self.log.end(f"undeployed; {sold}")
        return f"{machine_id} retired"

    def _sell_returned(self, parts, before):
        """Sells what the undeploy returned of each part (Inventory gain, capped at the snapshot count)."""
        shop = component("shop")
        if not shop:
            return "no Shop, parts left in Inventory"
        credits = 0
        unsold = []
        for item_id, count in parts.items():
            units = min(count, inventory_count(item_id) - before.get(item_id, 0))
            if units <= 0:
                continue
            try:
                res = shop.sell(item_id, units)
            except Exception as error:
                swallowed("fleet_decommission.FleetDecommissionCoordinator._sell_returned: shop.sell", error)
                unsold.append(item_id)
                continue
            if res.status == "ok":
                credits += int(getattr(res, "credits", 0) or 0)
                self.log.debug(f"Sold {units}x {item_id} for {getattr(res, 'credits', 0)} cr.")
            else:
                unsold.append(item_id)
                self.log.debug(f"sell('{item_id}', {units}) -> {res.status}: {res.message}")
        text = f"sold parts for {credits} cr"
        return text + (f"; unsold (left in Inventory): {', '.join(unsold)}" if unsold else "")

    def _forget_machine(self, machine_id, kind):
        """Drops every per-machine archive entry of a machine that is gone."""
        import fleet_status
        import logistics_requests
        import mining_reservations
        from vehicle_claims import RECALL_KEY, MISSION_KEY
        from drone_claims import DRONE_RECALL_KEY, MISSION_KEY as DRONE_MISSION_KEY
        from production import set_upgrade_order
        fleet_status.forget(machine_id)
        logistics_requests.release_pickups(machine_id)
        mining_reservations.release_yield(machine_id)
        set_upgrade_order(machine_id, {})
        if kind == "drone":
            import depot_stage
            from drone_energy import HOME_DEPOTS_KEY
            from drone_upgrade import update_fleet_upgrade
            depot_stage.clear_stage(machine_id)
            keys = (DRONE_RECALL_KEY, DRONE_MISSION_KEY, HOME_DEPOTS_KEY)
            def drop_upgrade(s):
                s.get("drones", {}).pop(machine_id, None)
                s.get("lineage", {}).pop(machine_id, None)
            update_fleet_upgrade(drop_upgrade)
        else:
            from pioneer_upgrade import clear_sport_nav_request
            from pioneer_commission import update_commission
            clear_sport_nav_request(machine_id)
            keys = (RECALL_KEY, MISSION_KEY)
            update_commission(lambda s: s.get("lineage", {}).pop(machine_id, None))
        for key in keys:
            if archive.get_entry(key, machine_id) is not None:
                archive.pop_entry(key, machine_id)
