# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and demand-driven hauler roles. Shared by Rover and Pioneer via
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
from storage import best_unload_target, take_item, total_stock, inventory_stack_size
import outpost_reagents
import mining_reservations
import logistics_requests
import drill_sites
from typing import TYPE_CHECKING

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
# Candidate pull trips (one per possible first stop) are scored
# units / (round-trip m + this overhead), like the drone hauler's
# HAUL_TRIP_OVERHEAD_M, so a nearby source holding a 1-unit top-up can't
# shadow a farther one holding what's actually missing.
PULL_TRIP_OVERHEAD_M = 300


def _outpost_haul_demand(dest_outpost_id):
    """
    {item_id: deficit} demand at dest_outpost_id, pulled fresh every haul
    cycle rather than fixed at loop construction -- there's no reason to
    decide in advance what a hauler will ever be asked to carry, only where
    it's headed. dest_outpost_id alone disambiguates which of this codebase's
    two demand sources applies: None/home means the production outpost's raw-
    material shortfall (only home ever needs ore hauled in); any other
    outpost id means that outpost's own Bio Lab reagent shortfall (only a
    remote outpost's Lab needs reagents hauled out to it).
    """
    if dest_outpost_id is None or dest_outpost_id == "outpost_home":
        return get_raw_material_demands()
    return outpost_reagents.get_outpost_reagent_demand(dest_outpost_id)


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def unload_cargo(self, outpost=None):
        """Transfers mined/gathered minerals and items into outpost's Inventory/
        Warehouse (default: this vehicle's own self.home_outpost -- see
        storage.best_unload_target()). The explicit outpost override is for
        run_haul_loop() below: a transporter stationed at a mining
        outpost (its own home_outpost) still needs to unload at the
        destination outpost specifically for its delivery leg, not wherever
        it happens to be stationed."""
        if not hasattr(self._host.vehicle, "cargo"):
            return 0

        cargo_count = self._host.vehicle.cargo.count()
        self._host.log.trace(f"[{self._host.name}] unload_cargo() enter: outpost={outpost!r}, cargo_count={cargo_count}")
        if cargo_count == 0:
            self._host.log.trace(f"[{self._host.name}] unload_cargo() exit: cargo empty, nothing to unload.")
            return 0

        target_outpost = outpost if outpost is not None else self._host.home_outpost

        self._host.log.print(f"[{self._host.name}] Offloading {cargo_count} items...")
        self._host.publish_telemetry("UNLOADING")

        out_port = getattr(self._host.vehicle, "output", None)
        if not out_port:
            for attr in ["output_1", "port_out", "out"]:
                if hasattr(self._host.vehicle, attr):
                    out_port = getattr(self._host.vehicle, attr)
                    break

        if not out_port:
            self._host.log.level("error").print(f"[{self._host.name}] Error: No output port found on vehicle!")
            return 0

        unloaded = 0
        inventory_full = False
        stacks = []
        if hasattr(self._host.vehicle.cargo, "stacks"):
            try:
                stacks = self._host.vehicle.cargo.stacks()
            except Exception:
                stacks = []

        if not stacks and hasattr(out_port, "stacks"):
            try:
                stacks = out_port.stacks()
            except Exception:
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
                    sleep(0.5)
                    retries += 1
                elif res.status in ["target_full", "slots_full", "inventory_full"]:
                    self._host.log.level("warn").print(f"[{self._host.name}] WARNING: '{target}' is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self._host.name}] Storage Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass
                    return 0, True
                else:
                    self._host.log.level("warn").print(f"[{self._host.name}] Offload notice: {res.status} - {res.message}")
                    return 0, False
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
        self._host.log.trace(f"[{self._host.name}] unload_cargo() exit: unloaded={unloaded}, inventory_full={inventory_full}, result={result}")
        return result

    def _current_supply_items(self):
        """All item ids already loaded (e.g. resuming a mixed delivery after a reload), or [] if the hold is empty."""
        if self._host.vehicle.cargo.count() == 0:
            return []
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception:
            stacks = []
        return [item_id for item_id in (getattr(s, "id", None) for s in stacks) if item_id]

    def _plan_haul_load(self, capacity, dest_outpost_id):
        """
        Plans a MIXED load across whatever _outpost_haul_demand(dest_outpost_id)
        currently shows as a deficit, filling up to capacity units total rather
        than being limited to a single item per trip (e.g. 50 titanium + 30
        silicon in one run) -- a source can have several haulable items at once,
        and hauling only one per trip would leave the others piling up unused
        there. No separate "what can this source supply" candidate list is
        needed: an item with no stock at a non-home source is filtered out
        below anyway (available <= 0), so ranking a few items the source
        happens not to carry costs nothing but a skipped iteration. Ranks by
        deficit descending, keeping only items with stock sitting at the
        source right now OR (when the source is home) buyable at the Shop,
        then greedily takes min(deficit, available, remaining capacity) from
        each in that order until either capacity runs out or no more
        qualifying item remains. Returns [(item_id, amount), ...], possibly
        empty.
        """
        demands = _outpost_haul_demand(dest_outpost_id)
        if not demands:
            self._host.log.debug(f"[{self._host.name}] _plan_haul_load(): no haul demand at destination '{dest_outpost_id}'.")
            return []
        self._host.log.debug(f"[{self._host.name}] _plan_haul_load(): demand at '{dest_outpost_id}': {demands}")
        source_is_home = getattr(self._host.home_outpost, "is_home", True)
        # Stock a pull hauler (run_pull_loop()) already promised itself here
        # isn't ours to load -- it would arrive to an emptied Warehouse.
        pulled = {} if source_is_home else logistics_requests.reserved_from(getattr(self._host.home_outpost, "id", None), exclude_vehicle=self._host.name)
        ranked = []
        for item_id, unmet in demands.items():
            if unmet <= 0:
                continue
            if source_is_home:
                # A shortfall at home can always be bought at the Shop (see
                # _load_haul_plan()'s buy-before-load step), so treat the full
                # deficit as available -- capacity is still the real ceiling below.
                available = unmet
            else:
                # No Shop delivery anywhere but home: real stock on hand is the
                # hard ceiling, same as before this role was generalized.
                available = total_stock(item_id, outpost=self._host.home_outpost) - pulled.get(item_id, 0)
                if available <= 0:
                    continue
            ranked.append((unmet, item_id, available))
        ranked.sort(reverse=True)

        plan = []
        remaining = capacity
        for unmet, item_id, available in ranked:
            if remaining <= 0:
                break
            amount = min(unmet, available, remaining)
            if amount <= 0:
                continue
            plan.append((item_id, amount))
            remaining -= amount
        self._host.log.debug(f"[{self._host.name}] _plan_haul_load(): planned {plan} (capacity={capacity}).")
        return plan

    def _load_haul_plan(self, plan):
        """
        Loads each planned (item_id, amount) into vehicle.input, buying any shortfall
        at the Shop first -- but only when this vehicle's source is home (nowhere else
        has direct Shop delivery). Bought one Inventory-stack at a time, immediately
        take_item()-ing each stack into cargo before buying the next, rather than one
        shop.buy(item_id, full_shortfall) call: the total planned amount is already
        capped by cargo capacity in _plan_haul_load(), but buying it all into Inventory
        in a single call could still stall on a full Inventory before the vehicle gets
        a chance to pull any of it back out, especially for a reagent Inventory has
        never stocked before. Draining stack-by-stack keeps that transient footprint to
        about one slot regardless of the total planned amount. Returns
        (["Nx item_id", ...], {item_id: moved}) -- the dict lets run_haul_loop()
        reserve exactly what got physically loaded (mining_reservations),
        rather than the originally planned amount, in case a shortfall (Shop
        out of stock, storage race) meant less was actually loaded.
        """
        source_is_home = getattr(self._host.home_outpost, "is_home", True)
        shop = get_component("shop") if source_is_home else None
        stack_size = inventory_stack_size()

        loaded_summary = []
        loaded_amounts = {}
        for item_id, amount in plan:
            moved_for_item = 0
            remaining = amount
            while remaining > 0:
                on_hand = total_stock(item_id, outpost=self._host.home_outpost)
                if on_hand <= 0 and shop:
                    buy_qty = min(remaining, stack_size)
                    buy_res = shop.buy(item_id, buy_qty)
                    if buy_res.status != "ok":
                        break
                elif on_hand <= 0:
                    break

                moved = take_item(self._host.vehicle.input, item_id, min(remaining, stack_size), outpost=self._host.home_outpost)
                if moved <= 0:
                    break
                moved_for_item += moved
                remaining -= moved

            if moved_for_item > 0:
                loaded_summary.append(f"{moved_for_item}x {item_id}")
                loaded_amounts[item_id] = moved_for_item
        return loaded_summary, loaded_amounts

    def _haul_reservation_key(self, item_id):
        return f"haul:{self._host.name}:{item_id}"

    def _reserve_home_haul(self, loaded_amounts):
        """
        Debits loaded_amounts from home's raw-ore deficit
        (mining_reservations, shared with lib/vehicle_mining.py's in-flight-mining
        debit) for the duration of the delivery leg -- otherwise a second
        transporter stationed at a different mining outpost would see the
        same still-uncovered home buffer/production deficit on its own next
        cycle and load a redundant amount before this vehicle's cargo ever
        lands, overshooting the target (e.g. two haulers each bringing 380
        of an ore with only 380 of room). Only meaningful for a home-bound
        delivery -- get_raw_material_demands() is home-specific, so a
        reagent-hauler's remote-outpost delivery has nothing to debit here.
        """
        curr_tick = self._host.get_current_tick()
        for item_id, amount in loaded_amounts.items():
            if amount > 0:
                mining_reservations.reserve_yield(self._host.name, self._haul_reservation_key(item_id), item_id, amount, curr_tick)

    def _release_home_haul(self, loaded_amounts):
        for item_id in loaded_amounts:
            mining_reservations.release_yield(self._host.name, self._haul_reservation_key(item_id))

    def run_haul_loop(self, dest_outpost_id, poll_interval=10.0):
        """
        Generic demand-driven hauler shared by every transporter role (TODO.md Phase
        3's ore-hauler and the reagent-hauler both reduce to this -- construct
        directly with the right home_base/dest_outpost_id combo rather than
        going through a role-specific wrapper method). The vehicle is always
        stationed at its home_base (idles/recharges there between runs via
        is_at_base()/return_to_base(), same as before) and drives out only to
        dest_outpost_id, only when _outpost_haul_demand(dest_outpost_id) shows
        a deficit for something actually available at the stationed outpost
        (or buyable at the Shop, when stationed at home). Which end is "home"
        differs per role -- an ore-hauler stations at the mining outpost and
        delivers to dest_outpost_id=None (home); a reagent-hauler stations at
        home (home_base=None) and delivers to an explicit remote outpost id --
        but the shape is otherwise identical, right down to "when the source is
        home, missing stock gets bought at the Shop before loading" falling out
        for free instead of needing its own method. What to haul is never
        decided at construction time -- only dest_outpost_id is fixed up front,
        and every other detail (which items, how much) is re-derived fresh each
        cycle from live demand (_outpost_haul_demand()), since there's no
        reason to lock that in ahead of when it's actually needed.

        dest_outpost = self.get_outpost_ref(dest_outpost_id), resolved once (this
        vehicle's own self.home_outpost is the STATIONED/source outpost, never
        confused with `dest_outpost` here).

        Each cycle: plans a MIXED load (_plan_haul_load()) across however many
        items currently have an actual deficit at the destination -- no
        preemptive/opportunistic top-off. Cargo already aboard (resuming after a
        reload) is identified from the cargo itself (_current_supply_items()) rather
        than re-deciding mid-delivery. Delivers, unloads at the destination explicitly
        (unload_cargo(outpost=...) override, since the default target would be this
        vehicle's own stationed outpost), recharges fully at the destination before
        heading back (so the return leg can run at full throttle), then returns to
        the stationed outpost to wait for the next deficit.
        """
        self._host.log.print(f"[{self._host.name}] Haul Controller online. Hauling from '{self._host.home_base}' to '{dest_outpost_id}' on demand.")
        dest_outpost = self._host.get_outpost_ref(dest_outpost_id)
        is_home_delivery = dest_outpost_id is None or dest_outpost_id == "outpost_home"
        validate_game_version()
        while True:
            try:
                if self._host.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                # Pioneer-only auto-upgrade/Sport-Nav-request pass -- see
                # lib/vehicle_upgrade.py. Self-guarded (only acts once
                # actually idle at base), and hasattr-gated since this loop is
                # shared with RoverController, which never mixes in
                # VehicleUpgradeMixin.
                upgrade_cycle = getattr(self._host, "handle_upgrade_cycle_if_idle", None)
                if upgrade_cycle is not None:
                    upgrade_cycle()

                if not dest_outpost or not hasattr(dest_outpost, "coords"):
                    self._host.log.level("warn").print(f"[{self._host.name}] Haul: destination outpost unavailable this cycle.")
                    sleep(poll_interval)
                    continue

                # Cargo already aboard (e.g. resuming after a reload) skips
                # straight to delivery instead of (re-)planning a load.
                haul_amounts = {}
                loaded_items = self._current_supply_items()
                if not loaded_items:
                    plan = self._plan_haul_load(self._host.vehicle.cargo.capacity(), dest_outpost_id)
                    if not plan:
                        if not self._host.is_at_base():
                            self._host.return_to_base()
                        self._host.publish_telemetry("IDLE_AT_OUTPOST", "no demand for candidate items")
                        sleep(poll_interval)
                        continue
                    if not hasattr(self._host.vehicle, "input"):
                        self._host.log.level("warn").print(f"[{self._host.name}] Haul requires an input port and Auto Feeders.")
                        sleep(poll_interval)
                        continue

                    # Loading below needs the vehicle physically within the
                    # stationed outpost's service area to connect to its
                    # Warehouse/Inventory -- unlike the no-demand idle branch
                    # above, this path used to skip straight to loading
                    # without ever driving here first, so a transporter
                    # starting (or left) anywhere else -- e.g. still at the
                    # destination after its last delivery -- would just fail
                    # to load forever instead of returning to its stationed
                    # outpost.
                    if not self._host.is_at_base():
                        self._host.publish_telemetry("RETURNING", f"returning to '{self._host.home_base}' to load")
                        if not self._host.return_to_base():
                            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach '{self._host.home_base}' to load; will retry.")
                            sleep(poll_interval)
                            continue

                    loaded_summary, loaded_amounts = self._load_haul_plan(plan)
                    if not loaded_summary:
                        self._host.log.level("warn").print(f"[{self._host.name}] Could not load any planned item at '{self._host.home_base}'.")
                        sleep(poll_interval)
                        continue
                    self._host.log.print(f"[{self._host.name}] Loaded {', '.join(loaded_summary)} at '{self._host.home_base}'.")

                    # Debit what just got loaded from home's own raw-ore
                    # deficit for the length of the delivery leg -- see
                    # _reserve_home_haul() -- so a peer transporter stationed
                    # at a different mining outpost doesn't also chase the
                    # same now-already-covered deficit before this delivery
                    # lands.
                    if is_home_delivery:
                        haul_amounts = loaded_amounts
                        self._reserve_home_haul(haul_amounts)
                elif is_home_delivery:
                    # Resuming with cargo already aboard (e.g. after a script
                    # restart mid-delivery) -- the reservation from the
                    # original loading cycle may no longer exist (archive
                    # survives, but nothing re-asserts it after a restart),
                    # so rebuild it from what's physically in the hold right
                    # now rather than skipping it.
                    for stack in self._host.vehicle.cargo.stacks():
                        item_id = getattr(stack, "id", None)
                        count = getattr(stack, "count", 0)
                        if item_id and count > 0:
                            haul_amounts[item_id] = haul_amounts.get(item_id, 0) + count
                    self._reserve_home_haul(haul_amounts)

                dest_coords = dest_outpost.coords()
                self._host.publish_telemetry("OUTBOUND", "delivering mixed cargo to the destination outpost")
                if not self._host.drive_with_recharge(dest_coords[0], dest_coords[1]):
                    self._host.log.level("warn").print(f"[{self._host.name}] Could not reach the destination outpost this cycle; will retry.")
                    sleep(poll_interval)
                    continue

                delivered = self._host.vehicle.cargo.count()
                if self.unload_cargo(outpost=dest_outpost) < 0:
                    self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
                    sleep(poll_interval)
                    continue
                self._host.log.print(f"[{self._host.name}] Delivered {delivered} units to the destination outpost.")

                # Cargo has physically landed and is now reflected in
                # total_stock() at the destination -- release the in-flight
                # debit so it doesn't linger subtracting from a deficit that
                # no longer exists (would otherwise only self-correct once
                # mining_reservations.RESERVATION_STALE_TICKS elapses).
                if haul_amounts:
                    self._release_home_haul(haul_amounts)

                # Recharge fully at the destination before heading back --
                # get_nearest_charging_station() (used internally by
                # recharge_at_station() when no station is given) resolves by
                # current position, not self.home_base, so this correctly
                # finds the destination's own station even though this
                # vehicle's home_base/home_outpost (for navigation/
                # is_at_base() purposes) is its stationed outpost. Starting
                # the return leg fully charged lets it run at full throttle
                # without drive_with_recharge() needing to plan an
                # intermediate stop for it -- faster round trips than only
                # recharging back at the stationed outpost.
                self._host.publish_telemetry("CHARGING_AT_BASE")
                self._host.recharge_at_station(target_level=1.0)

                self._host.publish_telemetry("RETURNING", f"returning to '{self._host.home_base}'")
                if self._host.return_to_base():
                    self._host.recharge_at_station(target_level=1.0)
                self._host.publish_telemetry("READY_AT_OUTPOST")
            except Exception as error:
                self._host.log.level("error").print(f"[{self._host.name}] Haul exception: {error}")
                try:
                    self._host.vehicle.nav.brake()
                except Exception:
                    pass
            sleep(poll_interval)

    # ------------------------------------------------------------ pull (reverse) hauling

    def _pull_deficits(self, curr_tick):
        """
        {item_id: units} this vehicle's home outpost still needs: its live
        pull-request deficits (logistics_requests, already net of in-flight
        pickups), plus -- when home is the production outpost -- the raw-ore
        demand normal haulers and miners chase (get_raw_material_demands(),
        already net of mining.reserved_yield). The larger of the two per
        item, never the sum: both measure a target against the same stock.
        """
        home = self._host.home_outpost
        deficits = logistics_requests.outpost_deficits(home, curr_tick, live=True)
        if getattr(home, "is_home", False):
            raw = get_raw_material_demands()
            self._host.log.debug(f"[{self._host.name}] pull: requests={deficits}, raw-ore demand={raw}.")
            for item_id, units in raw.items():
                if units > deficits.get(item_id, 0):
                    deficits[item_id] = units
        return deficits

    def _pull_sources(self, items, curr_tick):
        """
        Every place holding free stock of `items`, as dicts {"kind", "id",
        "coords", "available", "outpost"}: other outposts
        (logistics_requests.outpost_free_stock(), computed live) and field
        Mining Drills advertising in drill.status (lib/drill_sites.py), each
        net of what other haulers already reserved there. A drill with no
        recorded position (drill.positions) is skipped, warned about once.
        """
        home_id = getattr(self._host.home_outpost, "id", None)
        requests = logistics_requests.active_requests(curr_tick)
        sources = []
        if not hasattr(self, "_unlocated_drills_warned"):
            self._unlocated_drills_warned = set()

        network = get_component("outpost_network")
        try:
            outposts = list(network.outposts()) if network else []
        except Exception:
            outposts = []
        for outpost in outposts:
            if getattr(outpost, "id", None) == home_id or not hasattr(outpost, "coords"):
                continue
            available = logistics_requests.outpost_free_stock(outpost, items, requests, curr_tick, exclude_vehicle=self._host.name)
            if available:
                sources.append({"kind": "outpost", "id": outpost.id, "coords": outpost.coords(), "available": available, "outpost": outpost})

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

        self._host.log.debug(f"[{self._host.name}] pull: {len(sources)} source(s) hold wanted items: " + ", ".join(f"{src['kind']}:{src['id']}={src['available']}" for src in sources))
        return sources

    def _plan_pull_route(self, deficits, capacity, curr_tick):
        """
        Multi-stop pickup plan for this vehicle's home outpost. Every source
        holding something from `deficits` is tried as the first stop; from
        there the chain greedily visits the nearest (from the previous stop)
        remaining source, taking the largest deficits first, until capacity,
        PULL_MAX_STOPS_PER_TRIP or the deficits run out. Stops after the
        first must pass _pull_chain_worthwhile() (no driving past home). The
        chain with the best units / (round-trip m + PULL_TRIP_OVERHEAD_M)
        wins. Returns [(source, [(item_id, amount), ...]), ...].
        """
        sources = self._pull_sources(list(deficits.keys()), curr_tick)

        home_coords = None
        try:
            home_coords = self._host.home_outpost.coords() if self._host.home_outpost else None
        except Exception:
            home_coords = None
        start = self._host.get_position()

        best_route, best_score = [], -1.0
        for first in sources:
            route = self._plan_pull_chain(first, sources, deficits, capacity, start, home_coords)
            if not route:
                continue
            units = sum(a for _src, loads in route for _i, a in loads)
            meters, pos = 0.0, start
            for source, _loads in route:
                meters += self._host.distance_between(pos, source["coords"])
                pos = source["coords"]
            meters += self._host.distance_between(pos, home_coords) if home_coords is not None else 0.0
            score = units / (meters + PULL_TRIP_OVERHEAD_M)
            self._host.log.debug(f"[{self._host.name}] pull: candidate via '{first['id']}' -> {units} unit(s) over {meters:.0f}m ({len(route)} stop(s)), score {score:.4f}.")
            if score > best_score:
                best_route, best_score = route, score
        return best_route

    def _plan_pull_chain(self, first, sources, deficits, capacity, start, home_coords):
        """One candidate trip for _plan_pull_route(), starting at `first`."""
        remaining = dict(deficits)
        cap_left = capacity
        pos = start
        pending = list(sources)
        route = []
        while pending and cap_left > 0 and remaining and len(route) < PULL_MAX_STOPS_PER_TRIP:
            useful = [src for src in pending if any(remaining.get(i, 0) > 0 and u > 0 for i, u in src["available"].items())]
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
            for item_id in sorted(source["available"].keys(), key=lambda i: -remaining.get(i, 0)):
                amount = min(remaining.get(item_id, 0), source["available"][item_id], cap_left)
                if amount <= 0:
                    continue
                loads.append((item_id, amount))
                remaining[item_id] -= amount
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
        (mining.reserved_yield, same debit run_haul_loop() and home-demand
        miners write), so a normal hauler or miner doesn't also chase ore
        this trip already covers -- and vice versa, since this vehicle's own
        _pull_deficits() reads the same debited demand. Only for a home-based
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
        position) yields nothing and is warned about.
        """
        moved_by_item = {}
        coords = source["coords"]
        is_drill = source["kind"] == "drill"
        self._host.publish_telemetry("OUTBOUND", f"pickup at {source['kind']} '{source['id']}'")
        precision = drill_sites.DRILL_ARRIVAL_PRECISION_M if is_drill else 1.5
        if not self._host.drive_with_recharge(coords[0], coords[1], precision=precision):
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach '{source['id']}'; heading home with what's aboard.")
            return None

        if is_drill:
            if not drill_sites.connect_to_drill(self._host.vehicle.input, source["id"]):
                self._host.log.level("warn").print(f"[{self._host.name}] Drill '{source['id']}' refused the connection at {coords}; check its drill.positions entry.")
                for item_id, _amount in loads:
                    logistics_requests.reserve_pickup(self._host.name, home_id, item_id, 0, curr_tick, source_id=source["id"])
                return moved_by_item

        for item_id, amount in loads:
            if is_drill:
                moved = drill_sites.take_from_drill(self._host.vehicle.input, item_id, amount)
            else:
                moved = take_item(self._host.vehicle.input, item_id, amount, outpost=source["outpost"])
            self._host.log.print(f"[{self._host.name}] Picked up {moved}/{amount}x {item_id} at '{source['id']}'.")
            logistics_requests.reserve_pickup(self._host.name, home_id, item_id, moved, curr_tick, source_id=source["id"])
            moved_by_item[item_id] = moved_by_item.get(item_id, 0) + moved

        if not is_drill and self._host.find_charging_station(source["outpost"]) is not None:
            self._host.recharge_at_station(target_level=1.0)
        return moved_by_item

    def _cargo_totals(self):
        """{item_id: units} physically aboard."""
        totals = {}
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception:
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
        is missing (_pull_deficits(): pull requests, plus raw-ore demand when
        parked at home) from any other outpost's free stock or any field
        Mining Drill's stockpile, and brings it home (Pioneer entrypoint
        with DESTINATION_OUTPOST_ID="*"). One trip can chain up to
        PULL_MAX_STOPS_PER_TRIP sources, nearest-neighbour ordered. Every leg
        goes through drive_with_recharge(), which already refuses a leg
        unless the vehicle can still reach a charging station afterwards.

        Plays nice with other haulers on both ends: planned amounts are
        reserved per source (logistics.pickups "source", so nobody else
        plans the same units there) and, for home-bound ore, debited from
        home raw-ore demand (mining.reserved_yield, shared with
        run_haul_loop() and home-demand miners), so a normal hauler already
        bringing 800 ore makes this one see 800 less demand, and vice versa.
        """
        home = self._host.home_outpost
        home_id = getattr(home, "id", None)
        self._host.log.print(f"[{self._host.name}] Pull Controller online. Fetching what '{home_id}' needs from outposts and drills.")
        validate_game_version()
        while True:
            try:
                if self._host.handle_recall_if_active():
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
                deficits = self._pull_deficits(curr_tick)
                if not deficits:
                    if not self._host.is_at_base():
                        self._host.return_to_base()
                    self._host.publish_telemetry("IDLE_AT_OUTPOST", "no demand")
                    sleep(poll_interval)
                    continue
                self._host.log.debug(f"[{self._host.name}] pull: deficits at '{home_id}': {deficits}")

                capacity = self._host.vehicle.cargo.capacity()
                route = self._plan_pull_route(deficits, capacity, curr_tick)
                planned = sum(a for _src, loads in route for _i, a in loads)
                wanted = min(PULL_MIN_LOAD_UNITS, sum(deficits.values()))
                if not route or planned < wanted:
                    self._host.log.debug(f"[{self._host.name}] pull: planned {planned} unit(s) < minimum {wanted}; waiting.")
                    self._host.publish_telemetry("IDLE_AT_OUTPOST", "wanted items not available anywhere yet")
                    sleep(poll_interval)
                    continue

                legs = []
                planned_totals = {}
                for source, loads in route:
                    legs.append(source["id"] + " (" + ", ".join(str(a) + "x " + i for i, a in loads) + ")")
                    for item_id, amount in loads:
                        logistics_requests.reserve_pickup(self._host.name, home_id, item_id, amount, curr_tick, source_id=source["id"])
                        planned_totals[item_id] = planned_totals.get(item_id, 0) + amount
                self._reserve_pull_yield(planned_totals, curr_tick)
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
                except Exception:
                    pass
            sleep(poll_interval)

    def _finish_pull_delivery(self, poll_interval):
        """Drives home, unloads, releases this vehicle's pickup debits and recharges."""
        self._host.publish_telemetry("RETURNING", f"returning to '{self._host.home_base}' with pickups")
        if not self._host.return_to_base():
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach home to unload; will retry.")
            sleep(poll_interval)
            return
        if self.unload_cargo() < 0:
            self._host.publish_telemetry("WAITING_INVENTORY_SPACE")
            sleep(poll_interval)
            return
        logistics_requests.release_pickups(self._host.name)
        # A pull hauler holds no other yield reservations (roles are exclusive per script).
        mining_reservations.release_yield(self._host.name)
        self._host.recharge_at_station(target_level=1.0)
        self._host.publish_telemetry("READY_AT_OUTPOST")

