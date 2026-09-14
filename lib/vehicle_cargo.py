# Vehicle mixin: cargo offloading into Base Inventory and cooperative
# smelter wake-up. Shared by Rover and Pioneer via VehicleController
# (lib/vehicle.py).

from archive import archive


class VehicleCargoMixin:
    """Cargo offload behavior mixed into VehicleController."""

    def unload_cargo(self):
        """Transfers mined/gathered minerals and items into Base Inventory."""
        if not hasattr(self.vehicle, "cargo"):
            return 0

        cargo_count = self.vehicle.cargo.count()
        if cargo_count == 0:
            return 0

        print(f"[{self.name}] Offloading {cargo_count} items into Base Inventory...")
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

        if hasattr(out_port, "connected_to"):
            if out_port.connected_to() != "inventory":
                c_res = out_port.connect("inventory")
                if c_res.status != "ok":
                    print(f"[{self.name}] Connect to inventory notice: {c_res.status} - {c_res.message}")

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

        # If stacks are listed, transfer each stack
        if stacks:
            for stack in stacks:
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                if not item_id or count <= 0:
                    continue

                retries = 0
                while retries < 10:
                    res = out_port.send(item_id, count)
                    if res.status == "ok":
                        moved = getattr(res, "moved", count)
                        unloaded += moved
                        print(f"[{self.name}] Transferred {moved}x {item_id} to Inventory.")

                        # If ore was delivered, cooperatively wake up Smelter
                        if item_id in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "lead_ore"]:
                            self.wake_smelter()
                        break
                    elif res.status == "busy":
                        sleep(0.5)
                        retries += 1
                    elif res.status in ["target_full", "slots_full", "inventory_full"]:
                        inventory_full = True
                        print(f"[{self.name}] WARNING: Base inventory is full. Cargo remains aboard until space is available.")
                        try:
                            notify(f"[{self.name}] Base Inventory Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                        except Exception:
                            pass
                        break
                    else:
                        print(f"[{self.name}] Offload notice: {res.status} - {res.message}")
                        break
                    sleep(0.3)
        else:
            # Fallback for common mined minerals if stacks() returned empty but hold has cargo
            for cand in ["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "lead_ore"]:
                if self.vehicle.cargo.count() == 0:
                    break
                res = out_port.send(cand, self.vehicle.cargo.count())
                if res.status == "ok":
                    moved = getattr(res, "moved", 1)
                    unloaded += moved
                    print(f"[{self.name}] Transferred {moved}x {cand} to Inventory.")
                    self.wake_smelter()
                    break
                if res.status in ["target_full", "slots_full", "inventory_full"]:
                    inventory_full = True
                    print(f"[{self.name}] WARNING: Base inventory is full. Cargo remains aboard until space is available.")
                    try:
                        notify(f"[{self.name}] Base Inventory Full! Free space before the next expedition.", level="warn", duration_seconds=8.0)
                    except Exception:
                        pass
                    break
                sleep(0.3)

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
