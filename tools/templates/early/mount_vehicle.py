# Self-contained vehicle module mounting utility (runs directly on Rover or Pioneer)
# Inspects chassis mount slots and mounts target modules present in base Inventory.

print(f"[mount] Vehicle {self.id} starting module mounting sequence...")

# Target modules to mount by vehicle type
TARGET_MODULES_ROVER = ["nav_module", "sonar_module", "drill_module"]
TARGET_MODULES_PIONEER = [
    "nav_module",
    "battery_holder_small",
    "cargo_rack_small",
    "sonar_module_wide",
    "constructor_module",
]

target_list = TARGET_MODULES_PIONEER if getattr(self, "type_id", "") == "pioneer" else TARGET_MODULES_ROVER

slots = self.modules()
mounted_ids = {s.module_id for s in slots if s.module_id is not None}

for mod_id in target_list:
    if mod_id in mounted_ids:
        print(f"[mount] Module {mod_id} already mounted.")
        continue

    # Find first compatible empty slot
    mounted = False
    for s in self.modules():
        if s.module_id is None:
            # Check slot type compatibility
            slot_type = getattr(s, "type", "universal")
            # For rover: slots might be function-specific (nav, sonar, drill) or universal
            # Attempt mount
            res = self.mount(s.index, mod_id)
            if res.status == "ok":
                print(f"[mount] Successfully mounted {mod_id} into slot {s.index}!")
                mounted_ids.add(mod_id)
                mounted = True
                break
            elif res.status in ("slot_not_compatible", "capability_already_mounted"):
                continue
            elif res.status == "item_not_in_inventory":
                print(f"[mount] Module {mod_id} not yet in Inventory (waiting for shop delivery).")
                break
            else:
                print(f"[mount] Mount {mod_id} -> {res.status}: {res.message}")

print(f"[mount] Sequence complete for {self.id}. Mounted modules: {list(mounted_ids)}")

