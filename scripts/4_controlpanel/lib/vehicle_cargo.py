# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and the demand-driven pull hauler role. Shared by Rover and Pioneer via
# VehicleController (lib/vehicle.py).
#
# No cooperative Smelter wake-up here on purpose: the Smelter is soft-shed
# (lib/power.py's SOFT_SHED_PATTERNS) so Power Guard never actually powers it
# off, and if the operator manually stopped/powered it down themselves, a
# fresh ore delivery arriving should not override that -- the Smelter's own
# step() loop already polls for new ore on its normal cycle whenever it IS
# running.

from production import get_raw_material_demands
from version_guard import validate_game_version
from storage import best_unload_target, take_item, inventory_stack_size
import mining_reservations
import logistics_requests
import drill_sites
import pump_salt
import fleet_intent
import cash
from swallow import swallowed
from typing import TYPE_CHECKING
from tree_console import flush_all, reset_all

if TYPE_CHECKING:
    from vehicle import VehicleController

# Reverse ("pull") hauler, run_pull_loop(): source outposts visited per trip,
# and the smallest load worth a trip (or the whole outstanding deficit, if
# that's smaller).
PULL_MAX_STOPS_PER_TRIP = 3
PULL_MIN_LOAD_UNITS = 10
# A further stop is only chained onto a pull trip when driving there directly
# from the previous stop is at most this fraction of going via home instead
# (prev -> home -> next). Home lying on or near the chain leg means dropping
# the cargo off first costs (almost) nothing extra, so the stop is left for
# the next trip instead of driving straight past home.
PULL_CHAIN_MAX_DETOUR_RATIO = 0.75
# Candidate pull trips (one per possible first stop) are ranked by
# units / (round-trip m + this overhead), like the drone hauler's
# HAUL_TRIP_OVERHEAD_M, so a nearby source holding a 1-unit top-up can't
# shadow a farther one holding what's actually missing.
PULL_TRIP_OVERHEAD_M = 300


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def unload_cargo(self, outpost=None):
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
            """Sends count units of item_id, preferring a Warehouse with room
            at target_outpost (see storage.best_unload_target()) and falling
            back to Inventory. Returns (moved, went_full) for the caller's
            bookkeeping."""
            target = best_unload_target(item_id, count, outpost=target_outpost)
            if target is None:
                self._host.log.level("warn").print(f"[{self._host.name}] WARNING: no local storage at destination has room for {item_id}. Cargo remains aboard.")
                return 0, True
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
                    return moved, False
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
                    return 0, True
                else:
                    self._host.log.level("warn").print(f"[{self._host.name}] Offload notice: {res.status} - {res.message}")
                    return 0, False
                flush_all()
                sleep(0.3)
            return 0, False

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
            for cand in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore"]:
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

    # ------------------------------------------------------------ pull (reverse) hauling

    def _pull_deficits_tiered(self, curr_tick):
        """
        ({item_id: need units}, {item_id: buffer units}) this vehicle's home
        outpost still misses: its live pull-request deficits
        (logistics_requests.outpost_deficits_tiered(), already net of
        in-flight pickups), plus -- when home is the production outpost --
        the raw-ore demand normal haulers and miners chase
        (get_raw_material_demands(), net of mining.reserved_yield) as need
        tier. The larger of request vs ore demand per item, never the sum:
        both measure a target against the same stock.
        """
        home = self._host.home_outpost
        need, buffer = logistics_requests.outpost_deficits_tiered(home, curr_tick, live=True)
        if getattr(home, "is_home", False):
            raw = get_raw_material_demands()
            self._host.log.debug(f"[{self._host.name}] pull: requests need={need} buffer={buffer}, raw-ore demand={raw}.")
            for item_id, units in raw.items():
                if units > need.get(item_id, 0) + buffer.get(item_id, 0):
                    need[item_id] = units
                    buffer.pop(item_id, None)
        return need, buffer

    def _pull_sources(self, items, curr_tick):
        """
        Every place holding free stock of `items`, as dicts {"kind", "id",
        "coords", "available", "outpost"}: other outposts
        (logistics_requests.outpost_free_stock(), computed live) and field
        Mining Drills advertising in drill.status (lib/drill_sites.py), each
        net of what other haulers already reserved there. A drill with no
        recorded position (drill.positions) is skipped, warned about once.
        Water Pumps holding byproduct salt (lib/pump_salt.py) are added when
        salt is wanted, home pumps included. With the FLEET card's drone
        yield switch on, sources drone haulers can serve are dropped
        (logistics_requests.drone_served_source()).
        """
        self._host.log.start(f"[{self._host.name}] _pull_sources", level="debug")
        home_id = getattr(self._host.home_outpost, "id", None)
        requests = logistics_requests.active_requests(curr_tick)
        sources = []
        if not hasattr(self, "_unlocated_drills_warned"):
            self._unlocated_drills_warned = set()

        network = get_component("outpost_network")
        try:
            outposts = list(network.outposts()) if network else []
        except Exception as error:
            swallowed("vehicle_cargo.VehicleCargoMixin._pull_sources: network.outposts", error)
            outposts = []
        for outpost in outposts:
            if getattr(outpost, "id", None) == home_id or not hasattr(outpost, "coords"):
                continue
            for_need, for_buffer = logistics_requests.outpost_free_tiers(outpost, items, requests, curr_tick, exclude_vehicle=self._host.name)
            if for_need:
                sources.append({"kind": "outpost", "id": outpost.id, "coords": outpost.coords(), "available": for_need, "available_buffer": for_buffer, "outpost": outpost})

        positions = drill_sites.known_positions()
        for drill_id, entry in drill_sites.advertised_drills(curr_tick).items():
            taken = logistics_requests.reserved_from(drill_id, curr_tick, exclude_vehicle=self._host.name)
            available = {}
            for item_id, units in (entry.get("items") or {}).items():
                free = units - taken.get(item_id, 0)
                if item_id in items and free > 0:
                    available[item_id] = free
            if not available:
                continue
            coords = drill_sites.position_of(drill_id, positions)
            if not coords:
                if drill_id not in self._unlocated_drills_warned:
                    self._host.log.level("warn").print(f"[{self._host.name}] Drill '{drill_id}' holds {available} but its position is unknown; seed drill.positions to include it.")
                    self._unlocated_drills_warned.add(drill_id)
                continue
            sources.append({"kind": "drill", "id": drill_id, "coords": coords, "available": available, "outpost": None})

        if pump_salt.SALT_ITEM_ID in items:
            for pump_id, entry in pump_salt.salt_sources(curr_tick).items():
                taken = logistics_requests.reserved_from(pump_id, curr_tick, exclude_vehicle=self._host.name)
                free = entry["available"] - taken.get(pump_salt.SALT_ITEM_ID, 0)
                if free > 0:
                    sources.append({"kind": "pump", "id": pump_id, "coords": entry["coords"], "available": {pump_salt.SALT_ITEM_ID: free}, "outpost": None})

        kept = []
        for src in sources:
            reason = logistics_requests.drone_served_source(src, self._host.home_outpost)
            if reason:
                self._host.log.debug(f"pull: skip {src['kind']}:{src['id']} ({reason}; drone yield on).")
            else:
                kept.append(src)
        sources = kept

        self._host.log.debug(f"[{self._host.name}] pull: {len(sources)} source(s) hold wanted items: " + ", ".join(f"{src['kind']}:{src['id']}={src['available']}" for src in sources))
        self._host.log.end()
        return sources

    def _plan_pull_route(self, need, buffer, capacity, curr_tick):
        """
        Multi-stop pickup plan for this vehicle's home outpost. Sources are
        _pull_sources() plus, for buyable requests, the Shop
        (_shop_source(); listed last, so free stock at the home outpost
        wins a tie). The buffer
        tier is first capped at home's fair share of what the sources hold
        (logistics_requests.fair_buffer_caps()). Every source holding
        something wanted is tried as the first stop; from there the chain
        greedily visits the nearest (from the previous stop) remaining
        source, need tier first, then largest deficits, until capacity,
        PULL_MAX_STOPS_PER_TRIP or the deficits run out. Stops after the
        first must pass _pull_chain_worthwhile() (no driving past home). The
        chain with the most need-tier units, then all units, per
        (round-trip m + PULL_TRIP_OVERHEAD_M) wins
        (logistics_requests.haul_rank()). Returns (route, reachable): route is
        [(source, [(item_id, amount), ...]), ...], reachable the units of
        the (capped) deficits any source can cover at all.
        """
        items = set(need.keys()) | set(buffer.keys())
        sources = self._pull_sources(list(items), curr_tick)
        shop = self._shop_source(need, buffer, curr_tick)
        if shop:
            sources.append(shop)
        home_id = getattr(self._host.home_outpost, "id", None)
        if buffer:
            supply = {}
            for src in sources:
                for item_id, units in src.get("available_buffer", src["available"]).items():
                    if item_id in buffer:
                        supply[item_id] = supply.get(item_id, 0) + units
            buffer = {i: u for i, u in logistics_requests.fair_buffer_caps(home_id, buffer, supply, curr_tick).items() if u > 0}
        supply_all = {}
        for src in sources:
            for item_id, units in src["available"].items():
                supply_all[item_id] = supply_all.get(item_id, 0) + units
        reachable = 0
        for item_id in items:
            reachable += min(need.get(item_id, 0) + buffer.get(item_id, 0), supply_all.get(item_id, 0))

        home_coords = None
        try:
            home_coords = self._host.home_outpost.coords() if self._host.home_outpost else None
        except Exception as error:
            swallowed("vehicle_cargo.VehicleCargoMixin._plan_pull_route: self._host.home_outpost.coords", error)
            home_coords = None
        start = self._host.get_position()

        best_route, best_rank = [], None
        for first in sources:
            route = self._plan_pull_chain(first, sources, need, buffer, capacity, start, home_coords)
            if not route:
                continue
            units = sum(a for _src, loads in route for _i, a in loads)
            planned = {}
            for _src, loads in route:
                for item_id, amount in loads:
                    planned[item_id] = planned.get(item_id, 0) + amount
            need_units = sum(min(a, need.get(i, 0)) for i, a in planned.items())
            meters, pos = 0.0, start
            for source, _loads in route:
                meters += self._host.distance_between(pos, source["coords"])
                pos = source["coords"]
            meters += self._host.distance_between(pos, home_coords) if home_coords is not None else 0.0
            rank = logistics_requests.haul_rank(units, need_units, meters, PULL_TRIP_OVERHEAD_M)
            self._host.log.debug(f"[{self._host.name}] pull: candidate via '{first['id']}' -> {units} unit(s) ({need_units} need) over {meters:.0f}m ({len(route)} stop(s)), need rate {rank[0]:.4f}, rate {rank[1]:.4f}.")
            if logistics_requests.rank_beats(rank, best_rank):
                best_route, best_rank = route, rank
        return best_route, reachable

    def _shop_source(self, need, buffer, curr_tick):
        """
        Virtual pull source for the Shop, or None: only for a hauler whose
        home is NOT the home outpost, and only for deficits whose request is
        flagged buyable (logistics_requests.buyable_deficits()). Sits at the
        home outpost's coords (Shop purchases land in home Inventory);
        "available" is the whole buyable deficit. The id is per destination
        (SHOP_SOURCE_ID:<home id>), so two haulers buying for different
        outposts never trim each other's shop legs in claim_pickups().
        """
        home = self._host.home_outpost
        if home is None or getattr(home, "is_home", True) or not get_component("shop"):
            return None
        buy_need, buy_buffer = logistics_requests.buyable_deficits(home, need, buffer, curr_tick)
        available = dict(buy_need)
        for item_id, units in buy_buffer.items():
            available[item_id] = available.get(item_id, 0) + units
        if not available:
            return None
        base = self._host.get_outpost_ref(None)
        if base is None or not hasattr(base, "coords"):
            return None
        self._host.log.debug(f"[{self._host.name}] pull: Shop source for buyable deficits {available}.")
        return {"kind": "shop", "id": f"{logistics_requests.SHOP_SOURCE_ID}:{getattr(home, 'id', None)}", "coords": base.coords(), "available": available, "outpost": base}

    def _buy_and_take(self, item_id, amount, outpost):
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

    def _plan_pull_chain(self, first, sources, need, buffer, capacity, start, home_coords):
        """One candidate trip for _plan_pull_route(), starting at `first` (need tier before buffer, logistics_requests.plan_take())."""
        need_left = dict(need)
        buffer_left = dict(buffer)
        cap_left = capacity
        pos = start
        pending = list(sources)
        route = []
        while pending and cap_left > 0 and len(route) < PULL_MAX_STOPS_PER_TRIP:
            useful = [src for src in pending if any(sum(logistics_requests.plan_take(src, i, need_left, buffer_left, cap_left)) > 0 for i in src["available"])]
            if not route:
                useful = [src for src in useful if src["id"] == first["id"]]
            elif home_coords is not None:
                useful = [src for src in useful if self._pull_chain_worthwhile(pos, src, home_coords)]
            if not useful:
                break
            useful.sort(key=lambda src: self._host.distance_between(pos, src["coords"]))
            source = useful[0]
            pending = [src for src in pending if src["id"] != source["id"]]
            loads = []
            for item_id in sorted(source["available"].keys(), key=lambda i: (-need_left.get(i, 0), -buffer_left.get(i, 0))):
                take_need, take_buffer = logistics_requests.plan_take(source, item_id, need_left, buffer_left, cap_left)
                amount = take_need + take_buffer
                if amount <= 0:
                    continue
                loads.append((item_id, amount))
                need_left[item_id] = need_left.get(item_id, 0) - take_need
                buffer_left[item_id] = buffer_left.get(item_id, 0) - take_buffer
                cap_left -= amount
                if cap_left <= 0:
                    break
            if loads:
                route.append((source, loads))
                pos = source["coords"]
        return route

    def _pull_chain_worthwhile(self, prev_coords, source, home_coords):
        """
        True when chaining `source` straight after prev_coords beats
        dropping off at home first: direct leg <= PULL_CHAIN_MAX_DETOUR_RATIO
        * (prev -> home -> source). Rejects stops that lie "behind" home.
        """
        coords = source["coords"]
        direct = self._host.distance_between(prev_coords, coords)
        via_home = self._host.distance_between(prev_coords, home_coords) + self._host.distance_between(home_coords, coords)
        ok = via_home > 0 and direct <= PULL_CHAIN_MAX_DETOUR_RATIO * via_home
        self._host.log.debug(f"[{self._host.name}] pull: chain to '{source['id']}' direct={direct:.0f}m vs via-home={via_home:.0f}m -> {'chain' if ok else 'skip (home is on the way; next trip)'}.")
        return ok

    def _pull_yield_key(self, item_id):
        return f"pull:{self._host.name}:{item_id}"

    def _reserve_pull_yield(self, totals, curr_tick):
        """
        Debits {item_id: units} headed home from get_raw_material_demands()
        (mining.reserved_yield, same debit drone haulers and home-demand
        miners write), so another hauler or miner doesn't also chase ore
        this trip already covers -- and vice versa, since this vehicle's own
        _pull_deficits_tiered() reads the same debited demand. Only for a home-based
        pull hauler; elsewhere raw-ore demand isn't read at all.
        """
        if not getattr(self._host.home_outpost, "is_home", False):
            return
        for item_id, units in totals.items():
            if units > 0:
                mining_reservations.reserve_yield(self._host.name, self._pull_yield_key(item_id), item_id, units, curr_tick)
            else:
                mining_reservations.release_yield(self._host.name, self._pull_yield_key(item_id))

    def _pull_from_source(self, source, loads, home_id, curr_tick):
        """
        Drives to one planned source and loads its items; returns
        {item_id: moved}, or None when the source couldn't be reached.
        Corrects this vehicle's pickup reservations there to what actually
        got loaded. A drill that refuses the connection (wrong recorded
        position) yields nothing and is warned about. A Shop stop buys what
        it loads (_buy_and_take()).
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
        if not self._host.drive_with_recharge(coords[0], coords[1], precision=precision):
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
            self._host.log.print(f"[{self._host.name}] Picked up {moved}/{amount}x {item_id} at '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, home_id, item_id, moved, curr_tick, source_id=source["id"])
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved

        if not (is_drill or is_pump) and self._host.find_charging_station(source["outpost"]) is not None:
            self._host.recharge_at_station(target_level=1.0)
        return moved_by_item

    def _cargo_totals(self):
        """{item_id: units} physically aboard."""
        totals = {}
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception as error:
            swallowed("vehicle_cargo.VehicleCargoMixin._cargo_totals: self._host.vehicle.cargo.stacks", error)
            stacks = []
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if item_id and count > 0:
                totals[item_id] = totals.get(item_id, 0) + count
        return totals

    def run_pull_loop(self, poll_interval=10.0):
        """
        Reverse hauler: parked at self.home_base, fetches what this outpost
        is missing (_pull_deficits_tiered(): pull requests, plus raw-ore demand when
        parked at home) from any other outpost's free stock or any field
        Mining Drill's stockpile, and brings it home (every hauler-role
        Pioneer). Buyable requests at a non-home HOME_BASE (remote Bio Lab
        reagents) can also be bought at the Shop on a stop at the home
        outpost (_shop_source()). One trip can chain up to
        PULL_MAX_STOPS_PER_TRIP sources, nearest-neighbour ordered. Every leg
        goes through drive_with_recharge(), which already refuses a leg
        unless the vehicle can still reach a charging station afterwards.

        Plays nice with other haulers on both ends: planned amounts are
        reserved per source (logistics.pickups "source", so nobody else
        plans the same units there) and, for home-bound ore, debited from
        home raw-ore demand (mining.reserved_yield, shared with drone
        haulers and home-demand miners), so a drone already bringing 800
        ore makes this one see 800 less demand, and vice versa.
        """
        home = self._host.home_outpost
        home_id = getattr(home, "id", None)
        self._host.log.print(f"[{self._host.name}] Pull Controller online. Fetching what '{home_id}' needs from outposts and drills.")
        validate_game_version()
        while True:
            reset_all()
            try:
                if self._host.handle_recall_if_active():
                    flush_all()
                    sleep(poll_interval)
                    continue
                upgrade_cycle = getattr(self._host, "handle_upgrade_cycle_if_idle", None)
                if upgrade_cycle is not None:
                    upgrade_cycle()

                if self._host.vehicle.cargo.count() > 0:
                    self._host.log.debug(f"[{self._host.name}] pull: cargo aboard; delivering home first.")
                    # After a restart the in-flight yield debit may be gone;
                    # re-assert it from what's physically aboard.
                    self._reserve_pull_yield(self._cargo_totals(), self._host.get_current_tick())
                    self._finish_pull_delivery(poll_interval)
                    continue

                curr_tick = self._host.get_current_tick()
                seen = logistics_requests.pickups_snapshot()  # before any demand/stock read; see claim_pickups()
                need, buffer = self._pull_deficits_tiered(curr_tick)
                capacity = self._host.vehicle.cargo.capacity()
                route, planned, wanted = [], 0, 0
                if need or buffer:
                    self._host.log.debug(f"[{self._host.name}] pull: deficits at '{home_id}': need={need} buffer={buffer}")
                    route, reachable = self._plan_pull_route(need, buffer, capacity, curr_tick)
                    planned = sum(a for _src, loads in route for _i, a in loads)
                    # Minimum trip only over what some source can actually give:
                    # deficits nobody holds (or that were left to drones) must not
                    # keep a small but real delivery waiting.
                    wanted = min(PULL_MIN_LOAD_UNITS, reachable)
                if not route or planned <= 0 or planned < wanted:
                    # Nothing requested can move: the lowest-priority job is
                    # the home salt reserve (lib/pump_salt.py).
                    route, planned, wanted = self._plan_salt_reserve(capacity, curr_tick)
                if not route or planned <= 0 or planned < wanted:
                    if not need and not buffer:
                        if not self._host.is_at_base():
                            self._host.return_to_base()
                        self._host.publish_telemetry("IDLE_AT_OUTPOST", "no demand")
                    else:
                        self._host.log.debug(f"[{self._host.name}] pull: planned {planned} unit(s) < minimum {wanted}; waiting.")
                        self._host.publish_telemetry("IDLE_AT_OUTPOST", "wanted items not available anywhere yet")
                    flush_all()
                    sleep(poll_interval)
                    continue

                # Atomic claim: trimmed by whatever another hauler reserved
                # since `seen` (e.g. two haulers planning on the same tick).
                granted = logistics_requests.claim_pickups(self._host.name, home_id, [(src["id"], i, a) for src, loads in route for i, a in loads], seen, curr_tick)
                grant_by_leg = {(s, i): g for s, i, g in granted}
                route = [(src, [(i, grant_by_leg.get((src["id"], i), 0)) for i, _a in loads if grant_by_leg.get((src["id"], i), 0) > 0]) for src, loads in route]
                route = [(src, loads) for src, loads in route if loads]
                claimed = sum(a for _src, loads in route for _i, a in loads)
                if claimed < planned:
                    self._host.log.debug(f"[{self._host.name}] pull: another hauler reserved part of this trip since planning; {planned} -> {claimed} unit(s).")
                if not route or claimed < wanted:
                    self._host.log.debug(f"[{self._host.name}] pull: {claimed} unit(s) left after claim < minimum {wanted}; replanning next cycle.")
                    logistics_requests.release_pickups(self._host.name)
                    flush_all()
                    sleep(poll_interval)
                    continue

                legs = []
                planned_totals = {}
                for source, loads in route:
                    legs.append(source["id"] + " (" + ", ".join(str(a) + "x " + i for i, a in loads) + ")")
                    for item_id, amount in loads:
                        planned_totals[item_id] = planned_totals.get(item_id, 0) + amount
                self._reserve_pull_yield(planned_totals, curr_tick)
                source_ids = [src["id"] for src, _loads in route]
                source_label = source_ids[0] + (f" +{len(source_ids) - 1}" if len(source_ids) > 1 else "")
                self._host.set_intent(fleet_intent.describe("hauling", planned_totals, source_label, home_id, fleet_intent.haul_root(planned_totals, home_id, curr_tick)))
                self._host.log.start(f"[{self._host.name}] Pull trip: " + " -> ".join(legs))

                loaded_totals = {item_id: 0 for item_id in planned_totals}
                for index, (source, loads) in enumerate(route):
                    moved_by_item = self._pull_from_source(source, loads, home_id, curr_tick)
                    if moved_by_item is None:
                        # Unreachable: drop this and every later stop's reservations.
                        for later_source, later_loads in route[index:]:
                            for item_id, _amount in later_loads:
                                logistics_requests.reserve_pickup(self._host.name, home_id, item_id, 0, curr_tick, source_id=later_source["id"])
                        break
                    for item_id, moved in moved_by_item.items():
                        loaded_totals[item_id] = loaded_totals.get(item_id, 0) + moved
                self._reserve_pull_yield(loaded_totals, curr_tick)
                self._host.log.end(f"[{self._host.name}] Pickups done; {self._host.vehicle.cargo.count()} unit(s) aboard.")

                if self._host.vehicle.cargo.count() > 0:
                    self._finish_pull_delivery(poll_interval)
                else:
                    logistics_requests.release_pickups(self._host.name)
                    mining_reservations.release_yield(self._host.name)
                    if not self._host.is_at_base():
                        self._host.return_to_base()
            except Exception as error:
                self._host.log.level("error").print(f"[{self._host.name}] Pull exception: {error}")
                try:
                    self._host.vehicle.nav.brake()
                except Exception as exc:
                    swallowed("vehicle_cargo.VehicleCargoMixin.run_pull_loop: self._host.vehicle.nav.brake", exc)
            flush_all()
            sleep(poll_interval)

    def _plan_salt_reserve(self, capacity, curr_tick):
        """
        (route, planned, wanted) for a salt reserve top-up from the Water
        Pumps (pump_salt.salt_reserve_deficit(), home only); an empty route
        when the reserve is full or the pumps hold less than
        SALT_RESERVE_MIN_LOAD.
        """
        deficit = pump_salt.salt_reserve_deficit(self._host.home_outpost, curr_tick)
        if deficit <= 0:
            return [], 0, 0
        route, _reachable = self._plan_pull_route({}, {pump_salt.SALT_ITEM_ID: deficit}, capacity, curr_tick)
        # Pumps only: salt in another outpost's Warehouse is already stored.
        route = [(src, loads) for src, loads in route if src.get("kind") == "pump"]
        planned = sum(a for _src, loads in route for _i, a in loads)
        wanted = min(pump_salt.SALT_RESERVE_MIN_LOAD, capacity, deficit)
        self._host.log.debug(f"[{self._host.name}] pull: nothing requested can move; salt reserve wants {deficit}, trip plans {planned} (minimum {wanted}).")
        return route, planned, wanted

    def _finish_pull_delivery(self, poll_interval):
        """Drives home, unloads, releases this vehicle's pickup debits and recharges."""
        self._host.log.start(f"[{self._host.name}] Delivering pickups to '{self._host.home_base}'")
        outcome = self._deliver_pull_cargo(poll_interval)
        self._host.log.end(f"[{self._host.name}] {outcome}")

    def _deliver_pull_cargo(self, poll_interval):
        if not self._host.intent:
            home_id = getattr(self._host.home_outpost, "id", None)
            aboard = self._cargo_totals()
            self._host.set_intent(fleet_intent.describe("hauling", aboard, dest=home_id, root=fleet_intent.haul_root(aboard, home_id)))
        self._host.publish_telemetry("RETURNING", f"returning to '{self._host.home_base}' with pickups")
        if not self._host.return_to_base():
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach home to unload; will retry.")
            flush_all()
            sleep(poll_interval)
            return "Delivery incomplete: home not reached"
        if self.unload_cargo() < 0:
            self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
            flush_all()
            sleep(poll_interval)
            return "Delivery blocked: no inventory space"
        logistics_requests.release_pickups(self._host.name)
        # A pull hauler holds no other yield reservations (roles are exclusive per script).
        mining_reservations.release_yield(self._host.name)
        self._host.recharge_at_station(target_level=1.0)
        self._host.publish_telemetry("READY_AT_OUTPOST")
        return "Delivered and recharged"
