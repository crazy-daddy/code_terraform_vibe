# Self-contained vehicle module mounting utility (runs directly on Rover or Pioneer)
# Inspects chassis mount slots and mounts target modules present in base Inventory,
# then fills any container module's internal bays (Battery Holder -> Portable Battery)
# from Inventory too.

print(f"[mount] Vehicle {self.id} starting module mounting sequence...")

# Target modules to mount by vehicle type
TARGET_MODULES_ROVER = ["nav_module", "sonar_module", "drill_module"]

# Pioneer Scout loadout (100k-150k TP window, before lib/pioneer.py takes over - see
# pioneer_scout.py). Wide Sonar (`research_sonar_wide`, needs Pressure 6.0 kPa) and
# Constructor Module (`research_constructor_module`, needs Heat 10 HU) are both well
# past what this speedrun's Pressure/Heat Rush actually reaches by the time Pioneer
# Chassis unlocks at 100k TP - confirmed live: neither was actually purchasable, so
# those purchase/mount attempts were pure waste. A pure Scout has nothing to haul
# either, so no Cargo Rack. Basic Sonar (unlocked at Pressure 0.15, definitely already
# crossed) covers exploration; every slot not spent on Nav+Sonar goes to a Battery
# Holder instead, maximizing range on the one thing that actually limits a Scout run.
TARGET_MODULES_PIONEER = ["nav_module", "sonar_module"] + ["battery_holder_small"] * 6

# Portable item each container module type needs installed in its internal bay(s)
# (module mounts onto the chassis; the portable item goes inside it separately).
INTERNAL_ITEM_FOR = {
    "battery_holder_small": "portable_battery",
    "battery_holder_medium": "portable_battery",
    "cargo_rack_small": "portable_bin",
    "cargo_rack_medium": "portable_bin",
}

target_list = TARGET_MODULES_PIONEER if getattr(self, "type_id", "") == "pioneer" else TARGET_MODULES_ROVER


def mounted_counts():
    counts = {}
    for s in self.modules():
        if s.module_id is not None:
            counts[s.module_id] = counts.get(s.module_id, 0) + 1
    return counts


# --- Phase 1: mount chassis-level modules, by target COUNT (a Scout wants 6x the ----
# --- same battery_holder_small, not just "at least one") ---------------------------

wanted_counts = {}
for mod_id in target_list:
    wanted_counts[mod_id] = wanted_counts.get(mod_id, 0) + 1

for mod_id, wanted in wanted_counts.items():
    have = mounted_counts().get(mod_id, 0)
    if have >= wanted:
        print(f"[mount] {mod_id}: {have}/{wanted} already mounted.")
        continue

    while have < wanted:
        progressed = False
        for s in self.modules():
            if s.module_id is not None:
                continue
            res = self.mount(s.index, mod_id)
            if res.status == "ok":
                print(f"[mount] Successfully mounted {mod_id} into slot {s.index}! ({have + 1}/{wanted})")
                have += 1
                progressed = True
                break
            elif res.status in ("slot_not_compatible", "capability_already_mounted"):
                continue
            elif res.status == "item_not_in_inventory":
                print(f"[mount] {mod_id} not yet in Inventory ({have}/{wanted} so far) - waiting for shop delivery.")
                break
            else:
                print(f"[mount] Mount {mod_id} -> {res.status}: {res.message}")
                break
        if not progressed:
            break

# --- Phase 2: fill container internal bays (e.g. Battery Holder -> Portable Battery) -

for s in self.modules():
    item_id = INTERNAL_ITEM_FOR.get(s.module_id)
    if not item_id or not s.internal_count:
        continue
    bay = len(s.internal_items or [])
    while bay < s.internal_count:
        res = self.install(s.index, bay, item_id)
        if res.status == "ok":
            print(f"[mount] Installed {item_id} into slot {s.index} bay {bay}!")
            bay += 1
        elif res.status == "internal_slot_occupied":
            bay += 1
        elif res.status == "item_not_in_inventory":
            print(f"[mount] {item_id} not yet in Inventory - slot {s.index} bay {bay} waiting.")
            break
        else:
            print(f"[mount] Install {item_id} -> {res.status}: {res.message} (slot {s.index} bay {bay})")
            break

print(f"[mount] Sequence complete for {self.id}. Mounted: {mounted_counts()}")
