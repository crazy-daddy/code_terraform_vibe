# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and cooperative smelter wake-up. Shared by Rover and Pioneer
# via VehicleController (lib/vehicle.py).

from archive import archive
from production import get_raw_material_demands
from storage import best_unload_target, take_item, total_stock
import outpost_mining


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    def unload_cargo(self, outpost=None):
        """Transfers mined/gathered minerals and items into outpost's Inventory/
        Warehouse (default: this vehicle's own self.home_outpost -- see
        storage.best_unload_target()). The explicit outpost override is for
        run_supply_run_loop() below: a transporter stationed at a mining
        outpost (its own home_outpost) still needs to unload at the
        production outpost specifically for its delivery leg, not wherever
        it happens to be stationed."""
        if not hasattr(self.vehicle, "cargo"):
            return 0

        cargo_count = self.vehicle.cargo.count()
        if cargo_count == 0:
            return 0

        target_outpost = outpost if outpost is not None else self.home_outpost

        print(f"[{self.name}] Offloading {cargo_count} items...")
        self.publish_telemetry("UNLOADING")

        out_port = getattr(self.vehicle, "output", None)
        if not out_port:
            for attr in ["output_1", "port_out", "out"]:
                if hasattr(self.vehicle, attr):
                    out_port = getattr(self.vehicle, attr)
                    break

        if not out_port:
            print(f"[{self.name}] Error: No output port found on vehicle!")
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
            if getattr(out_port, "connected_to", None) and out_port.connected_to() != target:
                c_res = out_port.connect(target)
                if c_res.status != "ok":
                    print(f"[{self.name}] Connect to '{target}' notice: {c_res.status} - {c_res.message}")

            retries = 0
            while retries < 10:
                res = out_port.send(item_id, count)
                if res.status == "ok":
                    moved = getattr(res, "moved", count)
                    print(f"[{self.name}] Transferred {moved}x {item_id} to '{target}'.")
                    # Waking the Smelter only makes sense when this delivery
                    # actually landed at the production/home outpost -- ore
                    # that just arrived at a remote outpost's own Warehouse
                    # (a stationed miner, see run_stationed_mining_loop())
                    # isn't reachable by the Smelter until a transporter
                    # hauls it home (TODO.md Phase 3, Phase D) -- checked via
                    # target_outpost.is_home, NOT self.home_base, since a
                    # transporter's own home_base is its stationed mining
                    # outpost even while its delivery leg targets home.
                    if getattr(target_outpost, "is_home", False) and item_id in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore"]:
                        self.wake_smelter()
                    return moved, False
                elif res.status == "busy":
                    sleep(0.5)
                    retries += 1
                elif res.status in ["target_full", "slots_full", "inventory_full"]:
                    print(f"[{self.name}] WARNING: '{target}' is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self.name}] Storage Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass
                    return 0, True
                else:
                    print(f"[{self.name}] Offload notice: {res.status} - {res.message}")
                    return 0, False
                sleep(0.3)
            return 0, False

        # If stacks are listed, transfer each stack (may span more than one
        # item id, so the destination is chosen per stack, not once overall)
        if stacks:
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

        return -1 if inventory_full else unloaded

    def _current_supply_items(self):
        """All item ids already loaded (e.g. resuming a mixed delivery after a reload), or [] if the hold is empty."""
        if self.vehicle.cargo.count() == 0:
            return []
        try:
            stacks = self.vehicle.cargo.stacks()
        except Exception:
            stacks = []
        return [item_id for item_id in (getattr(s, "id", None) for s in stacks) if item_id]

    def _plan_supply_load(self, capacity):
        """
        Plans a MIXED load across this outpost's assigned ores (lib/outpost_mining.py),
        filling up to capacity units total rather than being limited to a
        single item per trip (e.g. 50 titanium + 30 silicon in one run) --
        a mining outpost can have several assigned ores at once (Phase B),
        and hauling only one per trip would leave the others piling up
        unused there. Ranks assigned ores by unmet home demand
        (get_raw_material_demands()) descending, keeping only those that
        actually have stock sitting at this outpost right now, then greedily
        takes min(unmet demand, stock on hand, remaining capacity) from each
        in that order until either capacity runs out or no more qualifying
        ore remains. Returns [(item_id, amount), ...], possibly empty.
        """
        assigned = outpost_mining.assigned_ores_for(self.home_base)
        if not assigned:
            return []
        demands = get_raw_material_demands()
        ranked = []
        for item_id in assigned:
            unmet = demands.get(item_id, 0)
            if unmet <= 0:
                continue
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
        return plan

    def run_supply_run_loop(self, poll_interval=10.0):
        """
        Demand-driven transporter role (TODO.md Phase 3, Phase D). Construct
        this vehicle with home_base=<mining outpost id> (same as Phase C's
        stationed miners -- see VehicleController.__init__) so it idles and
        recharges at that STATIONED outpost between runs via the existing
        is_at_base()/return_to_base(), and only drives explicitly to the
        production outpost (Nocturna Base -- get_outpost_ref(None), i.e.
        outpost_network.home(), never self.home_base) for the delivery leg
        itself. This vehicle's own self.home_outpost (cached from home_base,
        see VehicleController.__init__) is therefore the STATIONED outpost,
        not the production outpost -- the local `production_outpost`
        variable below is a deliberately distinct name so the two are never
        confused reading this function.

        The load can mix several different assigned ores in one trip (e.g.
        50 titanium + 30 silicon), not just one item per run -- see
        _plan_supply_load()'s docstring. Which items/amounts to haul is
        decided fresh each cycle, not fixed at construction. Cargo already
        aboard (resuming after a reload) is identified from the cargo itself
        (_current_supply_items()) rather than re-deciding mid-delivery.

        Each cycle: checks the production outpost's live unmet demand per
        assigned ore (get_raw_material_demands(), already net of its own
        stock) and only drives out when at least one has an actual deficit
        -- no preemptive/opportunistic top-off (confirmed with the user:
        demand-driven only). Loads up to cargo capacity total across however
        many qualifying ores, delivers, unloads at the production outpost
        explicitly (unload_cargo(outpost=...) override -- this vehicle's OWN
        home_outpost is the stationed outpost, so the default target would be
        wrong here; unload_cargo() already sends each cargo stack to its own
        destination, so a mixed load needs no special handling there),
        recharges fully at the production outpost before heading back (so the
        return leg can run at full throttle rather than a conservative one),
        then returns to its stationed outpost to wait for the next deficit.
        """
        print(f"[{self.name}] Supply Run Controller online. Hauling from '{self.home_base}' to the production outpost on demand.")
        production_outpost = self.get_outpost_ref(None)
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                if not production_outpost or not hasattr(production_outpost, "coords"):
                    print(f"[{self.name}] Supply run: production outpost unavailable this cycle.")
                    sleep(poll_interval)
                    continue

                # Cargo already aboard (e.g. resuming after a reload) skips
                # straight to delivery instead of (re-)planning a load.
                loaded_items = self._current_supply_items()
                if not loaded_items:
                    plan = self._plan_supply_load(self.vehicle.cargo.capacity())
                    if not plan:
                        if not self.is_at_base():
                            self.return_to_base()
                        self.publish_telemetry("IDLE_AT_OUTPOST", "no demand for assigned ores")
                        sleep(poll_interval)
                        continue
                    if not hasattr(self.vehicle, "input"):
                        print(f"[{self.name}] Supply run requires an input port and Auto Feeders.")
                        sleep(poll_interval)
                        continue

                    # take_item() below needs the vehicle physically within
                    # the stationed outpost's service area to connect to its
                    # Warehouse -- unlike the no-demand idle branch above,
                    # this path used to skip straight to loading without
                    # ever driving here first, so a transporter starting (or
                    # left) anywhere else -- e.g. still at the production
                    # outpost after its last delivery -- would just fail to
                    # load forever, sitting wherever it was instead of
                    # returning to its stationed outpost.
                    if not self.is_at_base():
                        self.publish_telemetry("RETURNING", f"returning to '{self.home_base}' to load")
                        if not self.return_to_base():
                            print(f"[{self.name}] Could not reach '{self.home_base}' to load; will retry.")
                            sleep(poll_interval)
                            continue

                    loaded_summary = []
                    for item_id, amount in plan:
                        moved = take_item(self.vehicle.input, item_id, amount, outpost=self.home_outpost)
                        if moved > 0:
                            loaded_summary.append(f"{moved}x {item_id}")
                    if not loaded_summary:
                        print(f"[{self.name}] Could not load any planned item at '{self.home_base}'.")
                        sleep(poll_interval)
                        continue
                    print(f"[{self.name}] Loaded {', '.join(loaded_summary)} at '{self.home_base}'.")

                production_coords = production_outpost.coords()
                self.publish_telemetry("OUTBOUND", "delivering mixed cargo to the production outpost")
                if not self.drive_with_recharge(production_coords[0], production_coords[1]):
                    print(f"[{self.name}] Could not reach the production outpost this cycle; will retry.")
                    sleep(poll_interval)
                    continue

                delivered = self.vehicle.cargo.count()
                if self.unload_cargo(outpost=production_outpost) < 0:
                    self.publish_telemetry("WAITING_INVENTORY_SPACE")
                    sleep(poll_interval)
                    continue
                print(f"[{self.name}] Delivered {delivered} units to the production outpost.")

                # Recharge fully at the production outpost before heading
                # back -- get_nearest_charging_station() (used internally by
                # recharge_at_station() when no station is given) resolves by
                # current position, not self.home_base, so this correctly
                # finds the production outpost's own station even though
                # this vehicle's home_base/home_outpost (for navigation/
                # is_at_base() purposes) is its stationed mining outpost.
                # Starting the return leg fully charged lets it run at full
                # throttle without drive_with_recharge() needing to plan an
                # intermediate stop for it -- faster round trips than only
                # recharging back at the stationed outpost.
                self.publish_telemetry("CHARGING_AT_BASE")
                self.recharge_at_station(target_level=1.0)

                self.publish_telemetry("RETURNING", f"returning to '{self.home_base}'")
                if self.return_to_base():
                    self.recharge_at_station(target_level=1.0)
                self.publish_telemetry("READY_AT_OUTPOST")
            except Exception as error:
                print(f"[{self.name}] Supply run exception: {error}")
                try:
                    self.vehicle.nav.brake()
                except Exception:
                    pass
            sleep(poll_interval)

    def wake_smelter(self):
        """Cooperatively powers on and resumes smelter when fresh ore arrives."""
        shedded = archive.get("power.shedded", [])
        if any("smelter" in m for m in shedded):
            print(f"[{self.name}] Smelter wake deferred: currently shedded by Power Guard for grid preservation.")
            return

        pwr = get_component("power_control")
        if pwr and hasattr(pwr, "set_powered"):
            try:
                pwr.set_powered("smelter_1", True)
            except Exception:
                pass

        run_ctrl = get_component("run_control")
        if run_ctrl and hasattr(run_ctrl, "is_running") and hasattr(run_ctrl, "start"):
            try:
                if not run_ctrl.is_running("smelter_1"):
                    if pwr and hasattr(pwr, "is_powered"):
                        if pwr.is_powered("smelter_1"):
                            run_ctrl.start("smelter_1")
                    else:
                        run_ctrl.start("smelter_1")
            except Exception:
                pass
