# Drone ability: floating freight hauling legs (field Mining Drills, Drone
# Depot outposts and Shop buys at home -> Drone Depots). The role (detected when a drone
# carries Cargo Pods but no bio module, see DroneController.detect_role())
# is HaulJob (lib/job_haul.py); this mixin flies its legs: load at a drill
# or a staged Depot, dock, deliver, hover idle.
#
# "Floating": no home Depot. Every cycle the job picks the best haul
# network-wide -- which outpost (with a Drone Depot) needs what, and which
# drills or other Depot outposts hold it -- the drone flies there, loads,
# delivers to that outpost's Depot, and moves on. It refuels at whichever
# drone_service_station is nearest when a job's fuel budget demands it, and
# hovers in place when there is nothing to do (never holds a bay while idle).
#
# Loading: cargo.load() works only at a docked Drone Depot or a field Mining
# Drill, cargo.unload() only into a docked Depot (drone.md, DroneCargo). A
# drill needs no staging. An outpost pickup asks the source Depot to pull the
# items out of local storage first (lib/depot_stage.py, fulfilled by
# lib/drone_depot.py fulfil_stage()) while the drone is on its way, then
# loads in rounds as the small stockpile refills. A Shop pickup (buyable
# requests, drone_haul_plan.shop_sources()) docks at a home Depot, buys into
# home Inventory and has the Depot stage only what it bought.
#
# Planning (demand, sources, route scoring, stall cooldowns) lives in
# lib/drone_haul_plan.py (module functions). The delivery in progress is the
# drone's Mission of kind "haul" (target {"dest": outpost_id}, no claim key;
# HaulJob begins and ends it).
#
# The Depot controller (lib/drone_depot.py drain_freight()) drains unloaded
# freight into local storage while the drone unloads in rounds.
#
# Between haul jobs the hauler also collects Storm Glass aftermaths
# (lib/drone_weather.py pick_aftermath_pickup()/collect_aftermath()) and
# delivers the glass like any other cargo aboard.

from typing import TYPE_CHECKING

import cash
import depot_stage
import drone_haul_plan
import logistics_requests
import outpost_flow
from drone_charging import REFUEL_FULL_LEVEL
from storage import inventory_room, inventory_stack_size
from swallow import swallowed
from tree_console import flush_all

if TYPE_CHECKING:
    from drone import DroneController

# Unloading into a small Depot stockpile happens in rounds while
# drone_depot.py drains it; give up (keep cargo, retry later) after this.
DEPOT_UNLOAD_TIMEOUT_S = 300.0
DEPOT_UNLOAD_RETRY_S = 2.0
# Waiting at a Depot whose bays are all taken.
DEPOT_BAY_WAIT_S = 60.0
# Loading at a source Depot happens in rounds while drone_depot.py stages
# more from storage; give up (keep what's aboard) after this.
DEPOT_LOAD_TIMEOUT_S = 120.0
# Docked at a Depot with no load/unload progress for this long -> leave the
# bay, hover, retry later.
DOCK_IDLE_MAX_S = 60.0
# Between jobs (no cargo aboard), below this charge the hauler docks at the
# nearest drone_service, where the LAUNCH_MIN_SOC launch floor holds it until
# topped up. Outpost buffers keep short, cheap jobs available nearly all the
# time, so without this trigger the per-job budget alone lets the hauler
# chain jobs down to the emergency reserve and never charge. Read by HaulJob.
HAUL_RECHARGE_SOC = 0.30
# Idle (no haul job) this many ticks in a row -> dock at the nearest
# drone_service and top up instead of hovering; it then waits there, ready,
# instead of starting the next job half charged. Tracked by HaulJob.
HAUL_IDLE_CHARGE_TICKS = 1200


class DroneHaulerMixin:
    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ reservations

    def release_haul_reservations(self):
        """Drops this drone's pickup reservations (logistics.pickups) and Depot stage requests."""
        logistics_requests.release_pickups(self._host.name)
        depot_stage.clear_stage(self._host.name)

    def cargo_contents(self):
        try:
            return {i: int(n) for i, n in dict(self._host.drone.cargo.contents()).items() if n > 0}
        except Exception as error:
            swallowed("drone_hauler.DroneHaulerMixin.cargo_contents: dict(self._host.drone.cargo.contents()).items", error)
            return {}

    # ------------------------------------------------------------ service stations

    def hover_idle(self, reason, idle_ticks=0):
        """
        Nothing to do: stay docked if already at a drone_service, fly to one
        below LAUNCH_MIN_SOC or, short of a full tank, after idle_ticks
        reaches HAUL_IDLE_CHARGE_TICKS; else leave any Depot bay and hover
        in place.
        """
        if self._host.docked_at_service():
            self._host.publish_telemetry("IDLE", reason)
            return
        _, _, frac = self._host.get_battery()
        if frac < self._host.LAUNCH_MIN_SOC:
            self._host.publish_telemetry("IDLE", reason)
            self._host.go_to_nearest_service(f"{reason}, {frac * 100:.0f}% charge")
            return
        if idle_ticks >= HAUL_IDLE_CHARGE_TICKS and frac < REFUEL_FULL_LEVEL:
            self._host.publish_telemetry("IDLE", reason)
            self._host.go_to_nearest_service(f"{reason} for {idle_ticks} ticks, {frac * 100:.0f}% charge")
            return
        self._host.log.debug(f"[{self._host.name}] {reason}; hovering in place ({frac * 100:.0f}% charge).")
        self._host.hover_wait("IDLE", reason)

    # ------------------------------------------------------------ legs

    def load_at_drill(self, source, loads, dest_id, curr_tick):
        """Flies to one drill and loads; returns {item: moved}, or None if unreachable. Corrects reservations to what loaded."""
        self._host.log.start(f"[{self._host.name}] load_at_drill", level="debug")
        self._host.publish_telemetry("OUTBOUND", f"pickup at drill '{source['id']}'")
        if not self._host.fly_to_drill(source["id"], target_coords=source["coords"]):
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach drill '{source['id']}'.")
            self._host.log.end()
            return None
        moved_by_item = {}
        for item_id, amount in loads:
            want = min(amount, drone_haul_plan.item_room(self._host, item_id))
            moved = 0
            if want > 0:
                try:
                    res = self._host.drone.cargo.load(item_id, want)
                    moved = int(getattr(res, "moved", 0) or 0)
                    if res.status not in ("ok", "partial"):
                        self._host.log.debug(f"load {item_id} at '{source['id']}': {res.status} - {res.message}")
                except Exception as e:
                    self._host.log.debug(f"load {item_id} at '{source['id']}' raised: {e}")
            self._host.log.print(f"[{self._host.name}] Loaded {moved}/{amount}x {item_id} at drill '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved, curr_tick, source_id=source["id"], aboard=True)
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved
        self._host.log.end()
        return moved_by_item

    def dock_at_depot(self, candidates, prefer=None):
        """
        Docks at a free Depot among candidates (waiting up to DEPOT_BAY_WAIT_S
        in "waiting_bay"). Returns the depot dict, or None.
        """
        waited = 0.0
        while True:
            depot = self._host._pick_free_depot(candidates, prefer_id=prefer)
            prefer = depot["id"]
            if self._host.current_station() == depot["id"] or self._host.fly_to_station(depot["id"], target_coords=depot["coords"]):
                return depot
            if self._host.status() != "waiting_bay" or waited >= DEPOT_BAY_WAIT_S:
                self._host.log.level("warn").print(f"[{self._host.name}] Could not dock at Drone Depot '{depot['id']}' (status {self._host.status()}).")
                return None
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S

    def stage_depot_for(self, source):
        """The Depot of an outpost source to load at: the one holding most of what's planned, else a free one."""
        if len(source["depots"]) == 1:
            return source["depots"][0]
        planned = [i for i in source["available"]]
        best, best_units = None, 0
        for depot in source["depots"]:
            comp = get_component(depot["id"])
            stock = logistics_requests.depot_stock(comp) if comp else {}
            units = sum(stock.get(i, 0) for i in planned)
            if units > best_units:
                best, best_units = depot, units
        return best or self._host._pick_free_depot(source["depots"])

    def load_at_depot(self, source, loads, dest_id, curr_tick, depot=None):
        """
        Docks at the source outpost's staged Depot (depot, as the job
        requested the staging at; else stage_depot_for()) and loads in rounds
        while drone_depot.py stages more from storage (the stage request
        shrinks to what is still missing after each round). A Shop source
        first buys each round what is neither aboard nor bought yet
        (buy_at_shop(), within home Inventory room) and stages only the
        bought units not yet aboard, so free home stock stays for its own
        haulers; an item that buys nothing with nothing bought left to load
        is dropped. Stops when done, after DOCK_IDLE_MAX_S without progress,
        or DEPOT_LOAD_TIMEOUT_S overall. Returns {item: moved}, or None if
        no Depot could be docked at. Corrects reservations to what loaded,
        clears the stage request and leaves the bay.
        """
        self._host.log.start(f"[{self._host.name}] load_at_depot", level="debug")
        depot = depot or self.stage_depot_for(source)
        self._host.publish_telemetry("OUTBOUND", f"pickup at Depot '{depot['id']}' ({source['id']})")
        docked = self.dock_at_depot(source["depots"], prefer=depot["id"])
        if docked is None:
            drone_haul_plan.note_failure(self._host, "source", source["id"], "could not dock")
            self._host.log.end()
            return None
        shop = source.get("kind") == "shop"
        if docked["id"] != depot["id"]:
            for item_id, amount in loads:
                depot_stage.request_stage(depot["id"], self._host.name, item_id, 0, curr_tick)
                if not shop:
                    depot_stage.request_stage(docked["id"], self._host.name, item_id, amount, curr_tick)
            depot = docked

        remaining = {i: a for i, a in loads}
        moved_by_item = {}
        bought = {}
        waited = idle = 0.0
        while remaining and waited < DEPOT_LOAD_TIMEOUT_S and idle < DOCK_IDLE_MAX_S:
            if shop:
                self._buy_round(remaining, moved_by_item, bought, depot["id"])
                if not remaining:
                    break
            moved_round = 0
            for item_id in list(remaining.keys()):
                want = min(remaining[item_id], drone_haul_plan.item_room(self._host, item_id))
                if want <= 0:
                    self._host.log.debug(f"load {item_id} at '{depot['id']}': no cargo room left for it.")
                    remaining.pop(item_id)
                    continue
                moved = 0
                try:
                    res = self._host.drone.cargo.load(item_id, want)
                    moved = int(getattr(res, "moved", 0) or 0)
                    if res.status not in ("ok", "partial"):
                        self._host.log.trace(f"load {item_id} at '{depot['id']}': {res.status} - {res.message}")
                except Exception as e:
                    self._host.log.debug(f"load {item_id} at '{depot['id']}' raised: {e}")
                if moved:
                    moved_round += moved
                    moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved
                    remaining[item_id] -= moved
                    stage = bought.get(item_id, 0) - moved_by_item[item_id] if shop else remaining[item_id]
                    depot_stage.request_stage(depot["id"], self._host.name, item_id, max(0, stage), self._host.get_current_tick())
                    if remaining[item_id] <= 0:
                        remaining.pop(item_id)
            if not remaining:
                break
            idle = 0.0 if moved_round else idle + DEPOT_UNLOAD_RETRY_S
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S

        for item_id, amount in loads:
            logistics_requests.reserve_pickup(self._host.name, dest_id, item_id, moved_by_item.get(item_id, 0), curr_tick, source_id=source["id"], aboard=True)
        depot_stage.clear_stage(self._host.name, depot["id"])
        total = sum(moved_by_item.values())
        self._host.log.print(f"[{self._host.name}] Loaded {moved_by_item} at Depot '{depot['id']}' ({source['id']})" + (f"; {remaining} not staged in time." if remaining else "."))
        if total > 0:
            drone_haul_plan.note_success(self._host, "source", source["id"])
        else:
            drone_haul_plan.note_failure(self._host, "source", source["id"], "nothing loaded")
        self._host.leave_station()
        self._host.log.end()
        return moved_by_item

    def _buy_round(self, remaining, moved_by_item, bought, depot_id):
        """
        One Shop round of load_at_depot(): per item in `remaining`, buys
        what is neither aboard nor bought yet (buy_at_shop()) and stages
        the bought units not yet aboard at depot_id. Updates `bought`;
        drops an item from `remaining` when it bought nothing and has
        nothing bought left to load.
        """
        tick = self._host.get_current_tick()
        for item_id in list(remaining.keys()):
            pending = max(0, bought.get(item_id, 0) - moved_by_item.get(item_id, 0))
            got = self.buy_at_shop(item_id, remaining[item_id] - pending)
            if got:
                bought[item_id] = bought.get(item_id, 0) + got
                pending += got
                depot_stage.request_stage(depot_id, self._host.name, item_id, pending, tick)
            elif pending <= 0:
                self._host.log.debug(f"Shop pickup: nothing more of {item_id} bought or waiting to load; dropping its remaining {remaining[item_id]}.")
                remaining.pop(item_id)

    def buy_at_shop(self, item_id, units):
        """
        Buys up to `units` of item_id into home Inventory, one Inventory
        stack at a time within inventory_room(), each cleared with the cash
        manager (consumer drone_reagents:<drone>, operating). Stops at the
        first denial, refused purchase or full Inventory. Returns units bought.
        """
        shop = get_component("shop")
        if not shop or units <= 0:
            return 0
        stack_size = inventory_stack_size()
        cash_id = f"drone_reagents:{self._host.name}"
        bought = 0
        while bought < units:
            qty = min(units - bought, stack_size, inventory_room(item_id))
            if qty <= 0:
                self._host.log.debug(f"buy {item_id}: home Inventory has no room; {bought}/{units} bought.")
                break
            cost = qty * cash.shop_price(item_id)
            if not cash.can_spend(cash_id, cost, label=f"{qty}x {item_id}"):
                self._host.log.debug(f"buy {qty}x {item_id} ({cost} cr): cash manager holds it back.")
                break
            res = shop.buy(item_id, qty)
            if res.status != "ok":
                cash.release(cash_id)
                self._host.log.level("warn").print(f"[{self._host.name}] Shop refused {qty}x {item_id}: {res.status} - {getattr(res, 'message', '')}")
                break
            cash.spent(cash_id, cost)
            bought += qty
        if bought:
            self._host.log.debug(f"Bought {bought}x {item_id} at the Shop.")
        return bought

    def pick_delivery_outpost(self, contents, saved=None):
        """
        Where cargo already aboard goes (resume after a reload or a failed
        delivery): saved (the haul mission's outpost) if it still has a
        Depot, else the Depot outpost with the most demand for what's aboard,
        else home, else the nearest Depot.
        """
        depots = self._host.get_all_drone_depots()
        tick = self._host.get_current_tick()
        depot_outposts = {d.get("outpost_id") for d in depots if not drone_haul_plan.is_cooling(self._host, "dest", d.get("outpost_id"), tick)}
        if saved in depot_outposts:
            return saved
        best, best_units = None, 0
        for dest in drone_haul_plan.haul_destinations(self._host, self._host.get_current_tick()):
            units = sum(min(n, dest["deficits"].get(i, 0)) for i, n in contents.items())
            if units > best_units:
                best, best_units = dest["outpost_id"], units
        if best:
            return best
        home = next((o for o in drone_haul_plan.outposts_by_id().values() if getattr(o, "is_home", False)), None)
        if home is not None and home.id in depot_outposts:
            return home.id
        _, nearest = self._host.get_nearest_drone_depot()
        nearest_id = nearest.get("outpost_id") or None
        return nearest_id if nearest_id in depot_outposts else None

    def deliver(self, dest_id):
        """
        Docks at a free Depot of dest_id and unloads in rounds while the
        Depot controller drains to storage. True when cargo is empty (the
        reservations and the haul mission are released). Gives up after
        DOCK_IDLE_MAX_S without progress or DEPOT_UNLOAD_TIMEOUT_S overall:
        the cargo stays aboard (reservations and mission kept), the drone
        leaves the bay reporting WAITING_DEPOT_SPACE for that Depot (so it
        may flush surplus), and the failure counts towards dest_id's stall
        cooldown.
        """
        candidates = [d for d in self._host.get_all_drone_depots() if d.get("outpost_id") == dest_id]
        if not candidates:
            self._host.log.level("warn").print(f"[{self._host.name}] No Drone Depot at '{dest_id}' to deliver to.")
            return False

        self._host.publish_telemetry("DELIVERING", f"to '{dest_id}'")
        depot = self.dock_at_depot(candidates)
        if depot is None:
            drone_haul_plan.note_failure(self._host, "dest", dest_id, "could not dock")
            return False

        self._host.log.start(f"[{self._host.name}] Unloading at '{depot['id']}' ({dest_id})")
        delivered = {}
        waited = idle = 0.0
        while waited < DEPOT_UNLOAD_TIMEOUT_S and idle < DOCK_IDLE_MAX_S:
            contents = self.cargo_contents()
            if not contents:
                break
            moved_round = 0
            for item_id, count in contents.items():
                try:
                    res = self._host.drone.cargo.unload(item_id, count)
                    moved = int(getattr(res, "moved", 0) or 0)
                except Exception as e:
                    self._host.log.debug(f"[{self._host.name}] unload {item_id} raised: {e}")
                    moved = 0
                if moved:
                    delivered[item_id] = delivered.get(item_id, 0) + moved
                    moved_round += moved
            if moved_round == 0:
                self._host.log.trace(f"[{self._host.name}] Depot stockpile full; waiting for it to drain ({idle:.0f}s idle).")
                idle += DEPOT_UNLOAD_RETRY_S
            else:
                idle = 0.0
            flush_all()
            sleep(DEPOT_UNLOAD_RETRY_S)
            waited += DEPOT_UNLOAD_RETRY_S
        left = self.cargo_contents()
        outpost_flow.record(self._host.get_current_tick(), received={dest_id: sum(delivered.values())})
        self._host.log.end(f"[{self._host.name}] Delivered {delivered} to '{dest_id}'" + (f"; {left} still aboard (Depot not draining -- storage full or Depot script not running?)" if left else "."))
        if left:
            drone_haul_plan.note_failure(self._host, "dest", dest_id, f"Depot '{depot['id']}' took no more after {idle:.0f}s")
            self._host.hover_wait("WAITING_DEPOT_SPACE", depot["id"])
            return False

        drone_haul_plan.note_success(self._host, "dest", dest_id)
        self.release_haul_reservations()
        self._host.end_mission()
        self._host.set_intent(None)
        # Docked and empty: the one moment couple()/uncouple() can run.
        self._host.maintain_modules_at_depot()
        self._host.leave_station()
        self._host.log.debug(f"[{self._host.name}] Delivery to '{dest_id}' complete; reservations released.")
        return True
