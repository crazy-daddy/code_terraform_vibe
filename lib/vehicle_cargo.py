# Vehicle mixin: cargo offloading into Base Inventory (or a Warehouse for
# bulk items) and cooperative smelter wake-up. Shared by Rover and Pioneer
# via VehicleController (lib/vehicle.py).

from archive import archive
from storage import best_unload_target


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    def unload_cargo(self):
        """Transfers mined/gathered minerals and items into Base Inventory,
        preferring a Warehouse when one has room -- see storage.best_unload_target()."""
        if not hasattr(self.vehicle, "cargo"):
            return 0

        cargo_count = self.vehicle.cargo.count()
        if cargo_count == 0:
            return 0

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
            at this vehicle's own outpost (see storage.best_unload_target())
            and falling back to Inventory. Returns (moved, went_full) for the
            caller's bookkeeping."""
            target = best_unload_target(item_id, count, outpost=self.home_outpost)
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
                    # Waking the Smelter only makes sense when this vehicle
                    # unloaded at the production/home outpost -- ore that
                    # just arrived at a remote outpost's own Warehouse (a
                    # stationed miner, see run_stationed_mining_loop()) isn't
                    # reachable by the Smelter until a transporter hauls it
                    # home (TODO.md Phase 3, Phase D).
                    if self.home_base is None and item_id in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore"]:
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
