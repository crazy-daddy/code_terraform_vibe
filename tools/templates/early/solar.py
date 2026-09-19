# ==============================================================================
# SOLAR GENERATOR & AUTONOMOUS BUILDING-BUYER (SPEEDRUN ROADMAP TO 150K TP)
# ==============================================================================
# Every panel runs elevation sun-tracking.
# The lowest-indexed solar panel (solar_1) is elected Master Building-Buyer:
#   - Evaluates Speedrun Milestones (0 -> 150k TP)
#   - Safely guards research gates via research.is_unlocked()
#   - Executes building swaps via computer.deploy() / computer.undeploy()
#   - Purchases kits and modules via shop.buy() and liquidates via shop.sell()
# ==============================================================================

clock = get_component("clock")
home = get_component("outpost_home")
research = get_component("research")
shop = get_component("shop")
nocturna = get_component("nocturna")

pressure_sensor = get_component("pressure_sensor")
oxygen_sensor = get_component("oxygen_sensor")
thermometer = get_component("thermometer")

last_eval_time = 0.0
last_heartbeat = 0.0

def get_master_solar_id():
    solar_b = home.buildings("solar_generator")
    if not solar_b:
        return self.id
    def s_key(b):
        parts = b.id.split("_")
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 999
    return min(solar_b, key=s_key).id

def is_tech_unlocked(tech_id):
    if not research:
        return False
    variants = [
        tech_id,
        tech_id.replace("research_", "") + "_unlock",
        "research_" + tech_id.replace("_unlock", ""),
        tech_id.replace("research_", "")
    ]
    for v in variants:
        try:
            if research.is_unlocked(v):
                return True
        except Exception:
            pass
    return False

def get_building_ids(type_id):
    if type_id in ("charging_station", "vehicle_charging_station"):
        return [b.id for b in home.buildings("charging_station")] + [b.id for b in home.buildings("vehicle_charging_station")]
    if type_id in ("temp_heater", "heater", "heat_generator"):
        return [b.id for b in home.buildings("temp_heater")] + [b.id for b in home.buildings("heater")]
    return [b.id for b in home.buildings(type_id)]

def count_buildings(type_id):
    return len(get_building_ids(type_id))

def count_vehicles(type_id):
    c = 0
    for i in range(1, 10):
        v = get_component(f"{type_id}_{i}")
        if v is not None:
            c += 1
    return c

def safe_undeploy_and_sell(computer, type_id, keep_count, item_id):
    current_ids = get_building_ids(type_id)
    to_remove = len(current_ids) - keep_count
    if to_remove <= 0:
        return 0
    removed = 0
    for b_id in reversed(current_ids):
        if removed >= to_remove:
            break
        res = computer.undeploy(b_id)
        if res.status == "ok":
            removed += 1
            print(f"[buyer] Undeployed {b_id} (freed slot)")
        else:
            print(f"[buyer] Undeploy {b_id} -> {res.status}: {res.message}")
    if removed > 0:
        sale = shop.sell(item_id, removed)
        if sale.status == "ok":
            print(f"[buyer] Sold {sale.units}x {item_id} (+{sale.credits} cr)")
    return removed

def safe_buy_and_deploy(computer, item_id, count_needed, tech_gate=None):
    if tech_gate and not is_tech_unlocked(tech_gate):
        return False
    try:
        free_slots = home.buildings_capacity - home.buildings_used
        count_needed = min(count_needed, max(0, free_slots))
    except Exception:
        pass
    if count_needed <= 0:
        return False
    b_res = shop.buy(item_id, count_needed)
    if b_res.status not in ("ok", "inventory_full"):
        print(f"[buyer] Shop buy {count_needed}x {item_id} -> {b_res.status}: {b_res.message}")
        return False
    deployed = 0
    for _ in range(count_needed):
        d_res = computer.deploy(item_id)
        if d_res.status == "ok":
            deployed += 1
            print(f"[buyer] Deployed {item_id} -> {d_res.machine_id}")
        else:
            print(f"[buyer] Deploy {item_id} -> {d_res.status}: {d_res.message}")
            break
    return deployed > 0

while True:
    # 1. Solar tracking (every panel)
    elev = clock.get_elevation()
    tilt = max(0, min(90, 90 - elev))
    self.set_tilt(tilt)

    # 2. Master Election
    is_master = (self.id == get_master_solar_id())
    if not is_master:
        sleep(2.0)
        continue

    # 3. Master Buyer Evaluation Loop
    now = clock.elapsed_seconds()
    if now - last_eval_time < 5.0:
        sleep(2.0)
        continue
    last_eval_time = now

    # Tech Guard: Ship Computer must be unlocked before using computer component
    if not is_tech_unlocked("research_computer"):
        sleep(5.0)
        continue

    computer = get_component("computer")
    if not computer:
        sleep(5.0)
        continue

    # Sensor Telemetry
    pressure = pressure_sensor.get_value() if pressure_sensor else 0.0
    o2 = oxygen_sensor.get_value() if oxygen_sensor else 0.0
    temp = thermometer.get_value() if thermometer else 0.0
    total_tp = nocturna.total_tp() if nocturna else 0.0

    if now - last_heartbeat >= 20.0:
        print(f"[buyer] Master on {self.id} | P: {pressure:.3f}/0.200 kPa | O2: {o2:.3f}/9.0 ppt | Temp: {temp:.1f}/12.0 HU | TP: {int(total_tp):,}")
        last_heartbeat = now

    # --------------------------------------------------------------------------
    # PHASE 1: Pressure Rush to 0.200 kPa
    # --------------------------------------------------------------------------
    if pressure < 0.200:
        p_count = count_buildings("pressure_generator")
        if p_count < 10:
            print(f"[buyer] Phase 1: Scaling Pressure Generators ({p_count}/10)...")
            safe_buy_and_deploy(computer, "pressure_generator", 10 - p_count)

    # --------------------------------------------------------------------------
    # PHASE 2: Oxygen Rush to 9.0 ppt (Smelter @ 5.0, Charger + Rover @ 9.0)
    # --------------------------------------------------------------------------
    elif o2 < 9.0:
        # Step A: Recycle 9 Pressure Generators down to 1
        safe_undeploy_and_sell(computer, "pressure_generator", 1, "pressure_generator")

        # Step B: Ensure 3 Batteries (1,500 Wh buffer for 11 O2 gens)
        bat_count = count_buildings("battery")
        if bat_count < 3:
            safe_buy_and_deploy(computer, "battery", 3 - bat_count)

        # Step C: Scale Oxygen Generators up to 11
        o2_count = count_buildings("oxygen_generator")
        if o2_count < 11:
            safe_buy_and_deploy(computer, "oxygen_generator", 11 - o2_count)

        # Step D: Deploy Smelter 1 if O2 >= 5.0 ppt
        if o2 >= 5.0 and is_tech_unlocked("research_smelter"):
            if count_buildings("smelter") == 0:
                print("[buyer] O2 >= 5.0 ppt: Deploying Smelter 1...")
                safe_buy_and_deploy(computer, "smelter", 1, "research_smelter")

    # --------------------------------------------------------------------------
    # PHASE 2 Transition: Vehicle Charging Station & Rover 1 (Unlocked @ 9.0 ppt)
    # --------------------------------------------------------------------------
    if o2 >= 9.0 and is_tech_unlocked("research_charging_station"):
        # Deploy Vehicle Charging Station 1
        if count_buildings("charging_station") == 0:
            print("[buyer] O2 >= 9.0 ppt: Deploying Vehicle Charging Station 1...")
            safe_buy_and_deploy(computer, "charging_station", 1, "research_charging_station")

        # Deploy Rover 1 and purchase modules into Inventory
        if count_vehicles("rover") == 0 and is_tech_unlocked("research_rover"):
            print("[buyer] Deploying Rover 1 and ordering modules...")
            if safe_buy_and_deploy(computer, "rover", 1, "research_rover"):
                shop.buy("nav_module", 1)
                shop.buy("sonar_module", 1)
                shop.buy("drill_module", 1)
                print("[buyer] Ordered Nav, Sonar, and Drill modules for Rover 1.")

    # --------------------------------------------------------------------------
    # PHASE 3: Heat Rush to 12.0 HU (Auto-Calibrated Heaters)
    # --------------------------------------------------------------------------
    if o2 >= 9.0 and temp < 12.0 and count_buildings("charging_station") >= 1:
        # Step A: Recycle 10 Oxygen Generators down to 1
        safe_undeploy_and_sell(computer, "oxygen_generator", 1, "oxygen_generator")

        # Step B: Recycle Smelter if needed to free flexible slot
        if count_buildings("smelter") > 0:
            safe_undeploy_and_sell(computer, "smelter", 0, "smelter")

        # Step C: Scale power to 7 Solar Panels + 4 Batteries (2,000 Wh)
        s_count = count_buildings("solar_generator")
        if s_count < 7:
            safe_buy_and_deploy(computer, "solar_generator", 7 - s_count)
        b_count = count_buildings("battery")
        if b_count < 4:
            safe_buy_and_deploy(computer, "battery", 4 - b_count)

        # Step D: Deploy 10 Heaters
        h_count = count_buildings("temp_heater")
        if h_count < 10:
            safe_buy_and_deploy(computer, "temp_heater", 10 - h_count)

    # --------------------------------------------------------------------------
    # PHASE 4: Pioneer Deployment (at 100k TP)
    # --------------------------------------------------------------------------
    if total_tp >= 100000 and is_tech_unlocked("research_pioneer"):
        if count_vehicles("pioneer") == 0:
            print("[buyer] 100k TP Milestone: Deploying Pioneer Chassis...")
            if safe_buy_and_deploy(computer, "pioneer", 1, "research_pioneer"):
                shop.buy("nav_module", 1)
                shop.buy("battery_holder_small", 1)
                shop.buy("portable_battery", 1)
                shop.buy("cargo_rack_small", 1)
                shop.buy("portable_bin", 1)
                print("[buyer] Ordered Pioneer expansion modules into base Inventory.")

    # --------------------------------------------------------------------------
    # PHASE 5: 150k TP Mid-Game Migration Signal
    # --------------------------------------------------------------------------
    if total_tp >= 150000:
        print("[MIGRATE] 150k TP reached! Bus, Archive & Control Panel unlocked. Ready for mid-game architecture.")

    sleep(2.0)
