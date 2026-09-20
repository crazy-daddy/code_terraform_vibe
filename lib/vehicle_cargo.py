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

    def unload_cargo(self, outpost=None):
        """Transfers mined/gathered minerals and items into outpost's Inventory/
        Warehouse (default: this vehicle's own self.home_outpost -- see
        storage.best_unload_target()). The explicit outpost override is for
        run_haul_loop() below: a transporter stationed at a mining
        outpost (its own home_outpost) still needs to unload at the
        destination outpost specifically for its delivery leg, not wherever
        it happens to be stationed."""
        if not hasattr(self.vehicle, "cargo"):
            return 0

        cargo_count = self.vehicle.cargo.count()
        self.log.trace(f"[{self.name}] unload_cargo() enter: outpost={outpost!r}, cargo_count={cargo_count}")
        if cargo_count == 0:
            self.log.trace(f"[{self.name}] unload_cargo() exit: cargo empty, nothing to unload.")
            return 0

        target_outpost = outpost if outpost is not None else self.home_outpost

        self.log.print(f"[{self.name}] Offloading {cargo_count} items...")
        self.publish_telemetry("UNLOADING")

        out_port = getattr(self.vehicle, "output", None)
        if not out_port:
            for attr in ["output_1", "port_out", "out"]:
                if hasattr(self.vehicle, attr):
                    out_port = getattr(self.vehicle, attr)
                    break

        if not out_port:
            self.log.level("error").print(f"[{self.name}] Error: No output port found on vehicle!")
            return 0

        unloaded = 0
        inventory_full = False
        stacks = []
        if hasattr(self.vehicle.cargo, "stacks"):
            try:
                stacks = self.vehicle.cargo.stacks()
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
                self.log.level("warn").print(f"[{self.name}] WARNING: no local storage at destination has room for {item_id}. Cargo remains aboard.")
                return 0, True
            self.log.debug(f"[{self.name}] best_unload_target({item_id}, {count}) -> '{target}' at outpost {target_outpost!r}.")
            if getattr(out_port, "connected_to", None) and out_port.connected_to() != target:
                c_res = out_port.connect(target)
                if c_res.status != "ok":
                    self.log.level("warn").print(f"[{self.name}] Connect to '{target}' notice: {c_res.status} - {c_res.message}")

            retries = 0
            while retries < 10:
                res = out_port.send(item_id, count)
                if res.status == "ok":
                    moved = getattr(res, "moved", count)
                    self.log.print(f"[{self.name}] Transferred {moved}x {item_id} to '{target}'.")
                    return moved, False
                elif res.status == "busy":
                    sleep(0.5)
                    retries += 1
                elif res.status in ["target_full", "slots_full", "inventory_full"]:
                    self.log.level("warn").print(f"[{self.name}] WARNING: '{target}' is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self.name}] Storage Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass
                    return 0, True
                else:
                    self.log.level("warn").print(f"[{self.name}] Offload notice: {res.status} - {res.message}")
                    return 0, False
                sleep(0.3)
            return 0, False

        # If stacks are listed, transfer each stack (may span more than one
        # item id, so the destination is chosen per stack, not once overall)
        if stacks:
            self.log.debug(f"[{self.name}] unload_cargo(): routing {len(stacks)} cargo stack(s) individually.")
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
                if self.vehicle.cargo.count() == 0:
                    break
                moved, went_full = unload_one(cand, self.vehicle.cargo.count())
                unloaded += moved
                if went_full:
                    inventory_full = True
                    break
                if moved > 0:
                    break

        result = -1 if inventory_full else unloaded
        self.log.trace(f"[{self.name}] unload_cargo() exit: unloaded={unloaded}, inventory_full={inventory_full}, result={result}")
        return result

    def _current_supply_items(self):
        """All item ids already loaded (e.g. resuming a mixed delivery after a reload), or [] if the hold is empty."""
        if self.vehicle.cargo.count() == 0:
            return []
        try:
            stacks = self.vehicle.cargo.stacks()
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
            self.log.debug(f"[{self.name}] _plan_haul_load(): no haul demand at destination '{dest_outpost_id}'.")
            return []
        self.log.debug(f"[{self.name}] _plan_haul_load(): demand at '{dest_outpost_id}': {demands}")
        source_is_home = getattr(self.home_outpost, "is_home", True)
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
                available = total_stock(item_id, outpost=self.home_outpost)
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
        self.log.debug(f"[{self.name}] _plan_haul_load(): planned {plan} (capacity={capacity}).")
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
        source_is_home = getattr(self.home_outpost, "is_home", True)
        shop = get_component("shop") if source_is_home else None
        stack_size = inventory_stack_size()

        loaded_summary = []
        loaded_amounts = {}
        for item_id, amount in plan:
            moved_for_item = 0
            remaining = amount
            while remaining > 0:
                on_hand = total_stock(item_id, outpost=self.home_outpost)
                if on_hand <= 0 and shop:
                    buy_qty = min(remaining, stack_size)
                    buy_res = shop.buy(item_id, buy_qty)
                    if buy_res.status != "ok":
                        break
                elif on_hand <= 0:
                    break

                moved = take_item(self.vehicle.input, item_id, min(remaining, stack_size), outpost=self.home_outpost)
                if moved <= 0:
                    break
                moved_for_item += moved
                remaining -= moved

            if moved_for_item > 0:
                loaded_summary.append(f"{moved_for_item}x {item_id}")
                loaded_amounts[item_id] = moved_for_item
        return loaded_summary, loaded_amounts

    def _haul_reservation_key(self, item_id):
        return f"haul:{self.name}:{item_id}"

    def _reserve_home_haul(self, loaded_amounts):
        """
        Debits loaded_amounts from home's raw-ore deficit
        (mining_reservations, shared with lib/mining.py's in-flight-mining
        debit) for the duration of the delivery leg -- otherwise a second
        transporter stationed at a different mining outpost would see the
        same still-uncovered home buffer/production deficit on its own next
        cycle and load a redundant amount before this vehicle's cargo ever
        lands, overshooting the target (e.g. two haulers each bringing 380
        of an ore with only 380 of room). Only meaningful for a home-bound
        delivery -- get_raw_material_demands() is home-specific, so a
        reagent-hauler's remote-outpost delivery has nothing to debit here.
        """
        curr_tick = self.get_current_tick()
        for item_id, amount in loaded_amounts.items():
            if amount > 0:
                mining_reservations.reserve_yield(self.name, self._haul_reservation_key(item_id), item_id, amount, curr_tick)

    def _release_home_haul(self, loaded_amounts):
        for item_id in loaded_amounts:
            mining_reservations.release_yield(self.name, self._haul_reservation_key(item_id))

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
        self.log.print(f"[{self.name}] Haul Controller online. Hauling from '{self.home_base}' to '{dest_outpost_id}' on demand.")
        dest_outpost = self.get_outpost_ref(dest_outpost_id)
        is_home_delivery = dest_outpost_id is None or dest_outpost_id == "outpost_home"
        validate_game_version()
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                if not dest_outpost or not hasattr(dest_outpost, "coords"):
                    self.log.level("warn").print(f"[{self.name}] Haul: destination outpost unavailable this cycle.")
                    sleep(poll_interval)
                    continue

                # Cargo already aboard (e.g. resuming after a reload) skips
                # straight to delivery instead of (re-)planning a load.
                haul_amounts = {}
                loaded_items = self._current_supply_items()
                if not loaded_items:
                    plan = self._plan_haul_load(self.vehicle.cargo.capacity(), dest_outpost_id)
                    if not plan:
                        if not self.is_at_base():
                            self.return_to_base()
                        self.publish_telemetry("IDLE_AT_OUTPOST", "no demand for candidate items")
                        sleep(poll_interval)
                        continue
                    if not hasattr(self.vehicle, "input"):
                        self.log.level("warn").print(f"[{self.name}] Haul requires an input port and Auto Feeders.")
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
                    if not self.is_at_base():
                        self.publish_telemetry("RETURNING", f"returning to '{self.home_base}' to load")
                        if not self.return_to_base():
                            self.log.level("warn").print(f"[{self.name}] Could not reach '{self.home_base}' to load; will retry.")
                            sleep(poll_interval)
                            continue

                    loaded_summary, loaded_amounts = self._load_haul_plan(plan)
                    if not loaded_summary:
                        self.log.level("warn").print(f"[{self.name}] Could not load any planned item at '{self.home_base}'.")
                        sleep(poll_interval)
                        continue
                    self.log.print(f"[{self.name}] Loaded {', '.join(loaded_summary)} at '{self.home_base}'.")

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
                    for stack in self.vehicle.cargo.stacks():
                        item_id = getattr(stack, "id", None)
                        count = getattr(stack, "count", 0)
                        if item_id and count > 0:
                            haul_amounts[item_id] = haul_amounts.get(item_id, 0) + count
                    self._reserve_home_haul(haul_amounts)

                dest_coords = dest_outpost.coords()
                self.publish_telemetry("OUTBOUND", "delivering mixed cargo to the destination outpost")
                if not self.drive_with_recharge(dest_coords[0], dest_coords[1]):
                    self.log.level("warn").print(f"[{self.name}] Could not reach the destination outpost this cycle; will retry.")
                    sleep(poll_interval)
                    continue

                delivered = self.vehicle.cargo.count()
                if self.unload_cargo(outpost=dest_outpost) < 0:
                    self.publish_telemetry("WAITING_INVENTORY_SPACE")
                    sleep(poll_interval)
                    continue
                self.log.print(f"[{self.name}] Delivered {delivered} units to the destination outpost.")

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
                self.publish_telemetry("CHARGING_AT_BASE")
                self.recharge_at_station(target_level=1.0)

                self.publish_telemetry("RETURNING", f"returning to '{self.home_base}'")
                if self.return_to_base():
                    self.recharge_at_station(target_level=1.0)
                self.publish_telemetry("READY_AT_OUTPOST")
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Haul exception: {error}")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
            sleep(poll_interval)

