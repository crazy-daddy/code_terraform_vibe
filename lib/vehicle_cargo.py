# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and cooperative smelter wake-up. Shared by Rover and Pioneer
# via VehicleController (lib/vehicle.py).

from archive import archive
from production import get_raw_material_demands
from storage import best_unload_target, take_item, total_stock


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

    def run_supply_run_loop(self, item_id, poll_interval=10.0):
        """
        Demand-driven transporter role (TODO.md Phase 3, Phase D). Construct
        this vehicle with home_base=<mining outpost id> (same as Phase C's
        stationed miners -- see VehicleController.__init__) so it idles and
        recharges at that outpost between runs via the existing
        is_at_base()/return_to_base(), and only drives explicitly to the
        production/home outpost for the delivery leg itself.

        Each cycle: checks home's live unmet demand for item_id
        (get_raw_material_demands(), already net of home's own stock) and
        only drives out when there's an actual deficit -- no preemptive/
        opportunistic top-off (confirmed with the user: demand-driven only).
        Loads up to min(unmet demand, cargo capacity, stock actually at this
        outpost), delivers, unloads at home explicitly (unload_cargo(outpost=...)
        override -- this vehicle's OWN home_outpost is the mining outpost, not
        home, so the default target would be wrong here), then returns to its
        stationed outpost to wait for the next deficit.
        """
        print(f"[{self.name}] Supply Run Controller online. Hauling {item_id} from '{self.home_base}' to home on demand.")
        home_outpost = self.get_outpost_ref(None)
        while True:
            try:
                if self.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                unmet = get_raw_material_demands().get(item_id, 0)
                if unmet <= 0 and self.vehicle.cargo.count() == 0:
                    if not self.is_at_base():
                        self.return_to_base()
                    self.publish_telemetry("IDLE_AT_OUTPOST", f"no demand for {item_id}")
                    sleep(poll_interval)
                    continue

                if not home_outpost or not hasattr(home_outpost, "coords"):
                    print(f"[{self.name}] Supply run: home outpost unavailable this cycle.")
                    sleep(poll_interval)
                    continue

                # Cargo already aboard (e.g. resuming after a reload) skips
                # straight to delivery instead of loading again.
                if self.vehicle.cargo.count() == 0:
                    available = total_stock(item_id, outpost=self.home_outpost)
                    amount = min(unmet, self.vehicle.cargo.capacity(), available)
                    if amount <= 0:
                        self.publish_telemetry("IDLE_AT_OUTPOST", f"no {item_id} at '{self.home_base}' yet")
                        sleep(poll_interval)
                        continue
                    if not hasattr(self.vehicle, "input"):
                        print(f"[{self.name}] Supply run requires an input port and Auto Feeders.")
                        sleep(poll_interval)
                        continue
                    moved = take_item(self.vehicle.input, item_id, amount, outpost=self.home_outpost)
                    if moved <= 0:
                        print(f"[{self.name}] Could not load {item_id} at '{self.home_base}'.")
                        sleep(poll_interval)
                        continue
                    print(f"[{self.name}] Loaded {moved}x {item_id} at '{self.home_base}'.")

                home_coords = home_outpost.coords()
                self.publish_telemetry("OUTBOUND", f"delivering {item_id} home")
                if not self.drive_with_recharge(home_coords[0], home_coords[1]):
                    print(f"[{self.name}] Could not reach home outpost this cycle; will retry.")
                    sleep(poll_interval)
                    continue

                delivered = self.vehicle.cargo.count()
                if self.unload_cargo(outpost=home_outpost) < 0:
                    self.publish_telemetry("WAITING_INVENTORY_SPACE")
                    sleep(poll_interval)
                    continue
                print(f"[{self.name}] Delivered {delivered}x {item_id} to home.")

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
