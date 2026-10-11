# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and the pull hauler's loading at a source (outpost stores and
# Drone Depots, drills, pumps, the Shop). Shared by Rover and Pioneer via
# VehicleController (lib/vehicle.py). Pull planning: lib/pull_plan.py; the
# hauler role: PullJob (lib/job_pull.py).
#
# No cooperative Smelter wake-up here on purpose: the Smelter is soft-shed
# (lib/power.py's SOFT_SHED_PATTERNS) so Power Guard never actually powers it
# off, and if the operator manually stopped/powered it down themselves, a
# fresh ore delivery arriving should not override that -- the Smelter's own
# step() loop already polls for new ore on its normal cycle whenever it IS
# running.

from storage import best_unload_target, take_item, inventory_stack_size, top_up_bin, inventory_room, outpost_is_home, INVENTORY_FREE_SLOTS_KEEP
import logistics_requests
import drill_sites
import pump_salt
import cash
from swallow import swallowed
from game_rules import RAW_ORE_ITEM_IDS
from pull_plan import PULL_MIN_LEG_THROTTLE
from typing import TYPE_CHECKING
from tree_console import flush_all

if TYPE_CHECKING:
    from vehicle import VehicleController


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def unload_cargo(self, outpost: "OutpostRef | None" = None):
        """Transfers mined/gathered minerals and items into outpost's Inventory/
        Warehouse (default: this vehicle's own self.home_outpost -- see
        storage.best_unload_target()), or at an explicit `outpost`."""
        if not hasattr(self._host.vehicle, "cargo"):
            return 0

        cargo_count = self._host.vehicle.cargo.count()
        self._host.log.trace(f"[{self._host.name}] unload_cargo() enter: outpost={outpost!r}, cargo_count={cargo_count}")
        if cargo_count == 0:
            self._host.log.trace(f"[{self._host.name}] unload_cargo() exit: cargo empty, nothing to unload.")
            return 0

        target_outpost = outpost if outpost is not None else self._host.home_outpost

        self._host.log.start(f"[{self._host.name}] Offloading {cargo_count} items")
        self._host.publish_telemetry("UNLOADING")

        out_port = getattr(self._host.vehicle, "output", None)
        if not out_port:
            for attr in ["output_1", "port_out", "out"]:
                if hasattr(self._host.vehicle, attr):
                    out_port = getattr(self._host.vehicle, attr)
                    break

        if not out_port:
            self._host.log.level("error").print(f"[{self._host.name}] Error: No output port found on vehicle!")
            self._host.log.end(f"[{self._host.name}] Offload failed: no output port")
            return 0

        unloaded = 0
        inventory_full = False
        stacks = []
        if hasattr(self._host.vehicle.cargo, "stacks"):
            try:
                stacks = self._host.vehicle.cargo.stacks()
            except Exception as error:
                swallowed("vehicle_cargo.VehicleCargoMixin.unload_cargo: self._host.vehicle.cargo.stacks", error)
                stacks = []

        if not stacks and hasattr(out_port, "stacks"):
            try:
                stacks = out_port.stacks()
            except Exception as error:
                swallowed("vehicle_cargo.VehicleCargoMixin.unload_cargo: out_port.stacks", error)
                stacks = []

        def unload_one(item_id, count):
            """Sends count units of item_id to storage.best_unload_target() at
            target_outpost: a Warehouse with room, Inventory as the home
            fallback, and Inventory first at home for Inventory-only items.
            Inventory takes at most storage.inventory_room(): a stack that
            only partly fits lands partly and reports went_full.
            storage.top_up_bin() first fills the Storage Bin already holding
            the item when no holder takes the whole stack.
            Returns (moved, went_full) for the caller's bookkeeping."""
            topped = top_up_bin(out_port, item_id, count, outpost=target_outpost)
            if topped > 0:
                self._host.log.print(f"[{self._host.name}] Topped up the bin holding {item_id} with {topped}x.")
                count -= topped
                if count <= 0:
                    return topped, False
            target = best_unload_target(item_id, count, outpost=target_outpost)
            short = False
            if target is None and outpost_is_home(target_outpost):
                # No store takes the whole stack: what fits in Inventory
                # above its free-slot reserve, the rest stays aboard.
                room = min(count, inventory_room(item_id))
                if room > 0:
                    target, count, short = "inventory", room, True
            if target is None:
                self._host.log.level("warn").print(f"[{self._host.name}] WARNING: no local storage at destination has room for {item_id} (Inventory keeps {INVENTORY_FREE_SLOTS_KEEP} slot(s) free). Cargo remains aboard.")
                return topped, True
            self._host.log.debug(f"[{self._host.name}] best_unload_target({item_id}, {count}) -> '{target}' at outpost {target_outpost!r}.")
            if getattr(out_port, "connected_to", None) and out_port.connected_to() != target:
                c_res = out_port.connect(target)
                if c_res.status != "ok":
                    self._host.log.level("warn").print(f"[{self._host.name}] Connect to '{target}' notice: {c_res.status} - {c_res.message}")

            retries = 0
            while retries < 10:
                res = out_port.send(item_id, count)
                if res.status == "ok":
                    moved = getattr(res, "moved", count)
                    self._host.log.print(f"[{self._host.name}] Transferred {moved}x {item_id} to '{target}'.")
                    return topped + moved, short
                elif res.status == "busy":
                    flush_all()
                    sleep(0.5)
                    retries += 1
                elif res.status in ["target_full", "slots_full", "inventory_full"]:
                    self._host.log.level("warn").print(f"[{self._host.name}] WARNING: '{target}' is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self._host.name}] Storage Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception as error:
                        swallowed("vehicle_cargo.VehicleCargoMixin.unload_cargo.unload_one: notify", error)
                    return topped, True
                else:
                    self._host.log.level("warn").print(f"[{self._host.name}] Offload notice: {res.status} - {res.message}")
                    return topped, False
                flush_all()
                sleep(0.3)
            return topped, False

        # If stacks are listed, transfer each stack (may span more than one
        # item id, so the destination is chosen per stack, not once overall)
        if stacks:
            self._host.log.debug(f"[{self._host.name}] unload_cargo(): routing {len(stacks)} cargo stack(s) individually.")
            for stack in stacks:
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                if not item_id or count <= 0:
                    continue
                moved, went_full = unload_one(item_id, count)
                unloaded += moved
                if went_full:
                    inventory_full = True
                    break
        else:
            # Fallback for common mined minerals if stacks() returned empty but hold has cargo
            for cand in RAW_ORE_ITEM_IDS:
                if self._host.vehicle.cargo.count() == 0:
                    break
                moved, went_full = unload_one(cand, self._host.vehicle.cargo.count())
                unloaded += moved
                if went_full:
                    inventory_full = True
                    break
                if moved > 0:
                    break

        result = -1 if inventory_full else unloaded
        self._host.log.end(f"[{self._host.name}] Offloaded {unloaded} unit(s)" + ("; storage full, cargo remains aboard" if inventory_full else ""))
        self._host.log.trace(f"[{self._host.name}] unload_cargo() exit: unloaded={unloaded}, inventory_full={inventory_full}, result={result}")
        return result

    # ------------------------------------------------------------ pull hauler loading

    def _buy_and_take(self, item_id, amount, outpost: "OutpostRef"):
        """
        Buys up to `amount` of item_id at the Shop one Inventory stack at a
        time and take_item()s each stack into cargo before buying the next,
        so the purchase never needs more than about one free Inventory slot.
        Stops at the first refused purchase (credits, Shop stock) or failed
        take. Returns units loaded.
        """
        self._host.log.start(f"[{self._host.name}] _buy_and_take", level="debug")
        shop = get_component("shop")
        if not shop:
            self._host.log.end()
            return 0
        stack_size = inventory_stack_size()
        loaded = 0
        while loaded < amount:
            qty = min(amount - loaded, stack_size)
            cost = qty * cash.shop_price(item_id)
            cash_id = f"pioneer_reagents:{self._host.name}"
            if not cash.can_spend(cash_id, cost, label=f"{qty}x {item_id}"):
                self._host.log.debug(f"{qty}x {item_id} ({cost} cr): cash manager holds it back.")
                break
            res = shop.buy(item_id, qty)
            if res.status != "ok":
                cash.release(cash_id)
                self._host.log.level("warn").print(f"[{self._host.name}] Shop refused {qty}x {item_id}: {res.status} - {getattr(res, 'message', '')}")
                break
            cash.spent(cash_id, cost)
            moved = take_item(self._host.vehicle.input, item_id, qty, outpost=outpost)
            self._host.log.debug(f"Bought {qty}x {item_id}, loaded {moved}.")
            if moved <= 0:
                break
            loaded += moved
        self._host.log.end()
        return loaded

    def pull_from_source(self, source, loads, home_id, curr_tick, unviable: "dict | None" = None):
        """
        Drives to one planned source and loads its items; returns
        {item_id: moved}, or None when the source couldn't be reached.
        Corrects this vehicle's pickup reservations there to what actually
        got loaded. An outpost stop take()s from its stores first, then its
        Drone Depots (_take_from_depots()). A drill that refuses the connection (wrong recorded
        position) yields nothing and is warned about. A Shop stop buys what
        it loads (_buy_and_take()). A leg refused as too slow even on a full
        battery (PULL_MIN_LEG_THROTTLE) is recorded as {source id: tick} in
        `unviable` when given (PullJob passes its dict for first stops only),
        so planning leaves the source out for a while.
        """
        moved_by_item = {}
        coords = source["coords"]
        is_drill = source["kind"] == "drill"
        is_pump = source["kind"] == "pump"
        is_shop = source["kind"] == "shop"
        self._host.publish_telemetry("OUTBOUND", f"pickup at {source['kind']} '{source['id']}'")
        if is_drill:
            precision = drill_sites.DRILL_ARRIVAL_PRECISION_M
        elif is_pump:
            precision = pump_salt.PUMP_ARRIVAL_PRECISION_M
        else:
            precision = 1.5
        if not self._host.drive_with_recharge(coords[0], coords[1], precision=precision, min_throttle=PULL_MIN_LEG_THROTTLE):
            if unviable is not None and self._host.full_battery_throttle((float(coords[0]), float(coords[1]))) < PULL_MIN_LEG_THROTTLE:
                unviable[source["id"]] = self._host.get_current_tick()
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach '{source['id']}'; heading home with what's aboard.")
            return None

        if is_drill or is_pump:
            # connect_to_drill()/take_from_drill() are plain port operations,
            # valid for any pickup structure (drill or pump).
            if not drill_sites.connect_to_drill(self._host.vehicle.input, source["id"]):
                self._host.log.level("warn").print(f"[{self._host.name}] {source['kind'].capitalize()} '{source['id']}' refused the connection at {coords}.")
                for item_id, _amount in loads:
                    logistics_requests.reserve_pickup(self._host.name, home_id, item_id, 0, curr_tick, source_id=source["id"])
                return moved_by_item

        for item_id, amount in loads:
            if is_drill or is_pump:
                moved = drill_sites.take_from_drill(self._host.vehicle.input, item_id, amount)
            elif is_shop:
                moved = self._buy_and_take(item_id, amount, source["outpost"])
            else:
                moved = take_item(self._host.vehicle.input, item_id, amount, outpost=source["outpost"])
                if moved < amount:
                    moved += self._take_from_depots(item_id, amount - moved, source)
            self._host.log.print(f"[{self._host.name}] Picked up {moved}/{amount}x {item_id} at '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, home_id, item_id, moved, curr_tick, source_id=source["id"], aboard=True)
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved

        if not (is_drill or is_pump) and self._host.find_charging_station(source["outpost"]) is not None:
            self._host.recharge_at_station(target_level=1.0)
        return moved_by_item

    def _take_from_depots(self, item_id, amount, source):
        """
        take()s up to `amount` more item_id from the Drone Depots at a source
        outpost once its stores ran dry, sparing what the Depots are about to
        push (logistics_requests.take_from_depots(spare_holds=True)). Logs
        every Depot's take status; one that moves nothing is a warning.
        Returns units moved.
        """
        report = {}
        moved = logistics_requests.take_from_depots(self._host.vehicle.input, item_id, amount, source["outpost"], spare_holds=True, report=report)
        for depot_id, status, units in report.get("sources", []):
            if units > 0:
                self._host.log.print(f"[{self._host.name}] Took {units}x {item_id} from Drone Depot '{depot_id}' ({status}).")
            else:
                self._host.log.level("warn").print(f"[{self._host.name}] Drone Depot '{depot_id}' gave no {item_id}: {status}.")
        return moved

    def cargo_totals(self):
        """{item_id: units} physically aboard."""
        totals = {}
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception as error:
            swallowed("vehicle_cargo.VehicleCargoMixin.cargo_totals: self._host.vehicle.cargo.stacks", error)
            stacks = []
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if item_id and count > 0:
                totals[item_id] = totals.get(item_id, 0) + count
        return totals
