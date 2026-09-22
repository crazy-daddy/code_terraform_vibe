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

def get_free_base_slots():
    try:
        cap_val = home.buildings_capacity() if callable(getattr(home, "buildings_capacity", None)) else getattr(home, "buildings_capacity", 25)
        used_val = home.buildings_used() if callable(getattr(home, "buildings_used", None)) else getattr(home, "buildings_used", 0)
        return max(0, int(cap_val) - int(used_val))
    except Exception:
        return max(0, 25 - len(home.buildings()))

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
    # Mobile vehicles (rover, pioneer) do not consume base building slots
    is_building = item_id not in ("rover", "pioneer")
    if is_building:
        free_slots = get_free_base_slots()
        count_needed = min(count_needed, free_slots)
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
            pc = get_component("power_control")
            if pc and hasattr(pc, "set_powered"):
                try:
                    pc.set_powered(d_res.machine_id, True)
                except Exception:
                    pass
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

    # Sensor Telemetry - no Ship Computer needed, these are direct sensor/planet reads
    pressure = pressure_sensor.get_value() if pressure_sensor else 0.0
    o2 = oxygen_sensor.get_value() if oxygen_sensor else 0.0
    temp = thermometer.get_value() if thermometer else 0.0
    total_tp = nocturna.total_tp() if nocturna else 0.0

    if now - last_heartbeat >= 20.0:
        print(f"[buyer] Master on {self.id} | P: {pressure:.3f}/0.200 kPa | O2: {o2:.3f}/9.0 ppt | Temp: {temp:.1f}/12.0 HU | TP: {int(total_tp):,}")
        last_heartbeat = now

    # --------------------------------------------------------------------------
    # POWER-ON PASS (power_control only - no Ship Computer needed)
    # --------------------------------------------------------------------------
    # Deliberately runs before the Ship Computer gate below: powering a building on/off
    # goes through power_control, never through computer.deploy()/undeploy(). Ship
    # Computer (research_computer) doesn't unlock until 10,000 TP, which can trail
    # behind 1.0 ppt Oxygen - nesting this under that gate (as it used to be) meant the
    # Bio-Loop stayed powered off long after Auto Feeders unlocked, for a tech reason
    # that was never actually a real dependency of this step.
    pc = get_component("power_control")
    if pc and hasattr(pc, "set_powered"):
        for b in home.buildings():
            # Keep bio unpowered if o2 < 1.0 or feeder not unlocked.
            # Must be the public research id ("research_auto_feeders", per docs/components/
            # research.md's is_unlocked() example) - the catalog's internal "Tech id" field
            # ("feeder_unlock") is a different namespace read from save-state unlockedTech
            # lists (see early_game.py's scan_and_deploy_machines), not what is_unlocked()
            # accepts. Passing "feeder_unlock" here made is_tech_unlocked()'s variant-guessing
            # (strip/append research_/_unlock) permanently return False, since it can never
            # derive "research_auto_feeders" from "feeder_unlock" - the two don't share a
            # stem - which kept every Bio-Loop building powered off even past 1.0 ppt O2.
            if "bio_" in b.id and (o2 < 1.0 or not is_tech_unlocked("research_auto_feeders")):
                continue
            try:
                if hasattr(pc, "is_powered") and not pc.is_powered(b.id):
                    res = pc.set_powered(b.id, True)
                    print(f"[buyer] Powered ON {b.id}: {res.status}")
                elif not hasattr(pc, "is_powered"):
                    pc.set_powered(b.id, True)
            except Exception as e:
                pass

    # Tech Guard: Ship Computer must be unlocked before using the computer component
    # (deploy/undeploy/buy) - everything below this point needs it, nothing above does.
    if not is_tech_unlocked("research_computer"):
        sleep(5.0)
        continue

    computer = get_component("computer")
    if not computer:
        sleep(5.0)
        continue

    # --------------------------------------------------------------------------
    # POWER GRID ANCHOR (3 Batteries + 6 Solar)
    # --------------------------------------------------------------------------
    # Batteries arrive pre-charged with 500 Wh (+1,000 Wh instant buffer from shop!)
    s_count = count_buildings("solar_generator")
    b_count = count_buildings("battery")
    p_count = count_buildings("pressure_generator")
    o2_count = count_buildings("oxygen_generator")

    # Maintain power grid anchor: 3 Batteries + 6 Solar Panels (9 slots)
    if b_count < 3:
        safe_buy_and_deploy(computer, "battery", 3 - b_count)
    elif b_count > 3 and pressure < 0.200:
        # Recycle surplus batteries down to 3 during early game to free slots
        safe_undeploy_and_sell(computer, "battery", 3, "battery")

    if s_count < 6:
        safe_buy_and_deploy(computer, "solar_generator", 6 - s_count)

    # --------------------------------------------------------------------------
    # MID-FLIGHT GUARD: Finish active Pressure rush if already near 0.200 kPa
    # --------------------------------------------------------------------------
    if pressure < 0.200 and p_count >= 8:
        # Recycle any lingering O2 gens (0% atmospheric gas decay!)
        if o2 >= 9.0 and o2_count > 0:
            safe_undeploy_and_sell(computer, "oxygen_generator", 0, "oxygen_generator")
        if count_buildings("charging_station") == 0 and is_tech_unlocked("research_charging_station"):
            safe_buy_and_deploy(computer, "charging_station", 1, "research_charging_station")
        if p_count < 12:
            safe_buy_and_deploy(computer, "pressure_generator", 12 - p_count)

    # --------------------------------------------------------------------------
    # PHASE 1: Oxygen Rush to 9.0 ppt (Bio-Loop @ 1.0, Contracts @ 3.0, Smelter @ 5.0, Charger @ 9.0)
    # --------------------------------------------------------------------------
    elif o2 < 9.0:
        # Scale Oxygen Generators up to 13 (occupies exact 25/25 slots: 6 Solar + 3 Bat + 3 Bio + 13 O2)
        if o2_count < 13:
            print(f"[buyer] Phase 1: Scaling Oxygen Generators ({o2_count}/13)...")
            safe_buy_and_deploy(computer, "oxygen_generator", 13 - o2_count)

    # --------------------------------------------------------------------------
    # PHASE 2: Pressure Rush to 0.200 kPa (Charging Station deployed, rush Rover tech)
    # --------------------------------------------------------------------------
    elif pressure < 0.200:
        # Step A: Deploy Vehicle Charging Station 1 (unlocked at 9.0 ppt O2)
        if count_buildings("charging_station") == 0 and is_tech_unlocked("research_charging_station"):
            print("[buyer] O2 >= 9.0 ppt: Deploying Vehicle Charging Station 1...")
            safe_buy_and_deploy(computer, "charging_station", 1, "research_charging_station")

        # Step B: Recycle all 13 Oxygen Generators down to 0 (0% atmospheric gas decay, recovers 13 slots!)
        safe_undeploy_and_sell(computer, "oxygen_generator", 0, "oxygen_generator")

        # Step C: Scale Pressure Generators up to 12 (occupies exact 25/25 slots: 6 Solar + 3 Bat + 3 Bio + 1 Charger + 12 Pres)
        # Note: Resonance sweep gauge takes ~4 sweeps to reach 100% sync efficiency.
        if p_count < 12:
            print(f"[buyer] Phase 2: Scaling Pressure Generators ({p_count}/12)...")
            safe_buy_and_deploy(computer, "pressure_generator", 12 - p_count)

    # --------------------------------------------------------------------------
    # PHASE 2 Transition: Vehicle Charging Station, Smelter & 2 Rovers (@ 0.200 kPa & 9.0 ppt O2)
    # --------------------------------------------------------------------------
    if count_buildings("charging_station") == 0 and is_tech_unlocked("research_charging_station"):
        print("[buyer] Deploying Vehicle Charging Station 1...")
        safe_buy_and_deploy(computer, "charging_station", 1, "research_charging_station")

    if pressure >= 0.200 and count_buildings("charging_station") >= 1:
        # Deploy Smelter 1 (unlocked at 5.0 ppt O2)
        if count_buildings("smelter") == 0 and is_tech_unlocked("research_smelter"):
            print("[buyer] Deploying Smelter 1 for Rover ore processing...")
            safe_buy_and_deploy(computer, "smelter", 1, "research_smelter")

        # Deploy 2 Rovers and order modules (unlocked at 0.200 kPa Pressure)
        r_count = count_vehicles("rover")
        if r_count < 2 and is_tech_unlocked("research_rover") and is_tech_unlocked("research_deep_extraction"):
            needed_rovers = 2 - r_count
            print(f"[buyer] Deploying {needed_rovers}x Rover chassis...")
            for _ in range(needed_rovers):
                if safe_buy_and_deploy(computer, "rover", 1, "research_rover"):
                    shop.buy("nav_module", 1)
                    shop.buy("sonar_module", 1)
                    shop.buy("drill_module", 1)
                    print("[buyer] Ordered Nav, Sonar, and Drill modules into base Inventory.")

    # --------------------------------------------------------------------------
    # PHASE 3: Heat Rush to 12.0 HU (Strict 25/25 Base Slots, 0% Penalty)
    # --------------------------------------------------------------------------
    if pressure >= 0.200 and o2 >= 9.0 and temp < 12.0 and count_buildings("charging_station") >= 1:
        # Step A: Recycle 11 Pressure Generators down to 1 (recovers 11 slots and credits)
        safe_undeploy_and_sell(computer, "pressure_generator", 1, "pressure_generator")

        # Step B: Scale power to 7 Solar Panels + 4 Batteries (2,000 Wh reserve)
        s_count = count_buildings("solar_generator")
        if s_count < 7:
            safe_buy_and_deploy(computer, "solar_generator", 7 - s_count)
        b_count = count_buildings("battery")
        if b_count < 4:
            safe_buy_and_deploy(computer, "battery", 4 - b_count)

        # Step C: Deploy 7 Heaters (Exact 25/25 slots: 7 Solar + 4 Bat + 3 Bio + 1 Charger + 1 Smelter + 1 Pres + 7 Heat = 24 slots, +1 spare!)
        # Run the Heat Rush at full capacity - trimming a Heater up front to
        # pre-reserve a slot for Supply Dock (110k TP, tens of thousands of TP
        # later) just meant idling at 23/25 the whole time. Sell one instead,
        # below, once it's actually needed.
        h_count = count_buildings("temp_heater")
        if h_count < 7:
            safe_buy_and_deploy(computer, "temp_heater", 7 - h_count)

    # --------------------------------------------------------------------------
    # PHASE 4.5: Supply Dock Deployment (Supply Logistics @ 110k TP)
    # --------------------------------------------------------------------------
    # research_orders_system unlocks Orders + Supply Dock purchasing at 110,000 TP,
    # squarely inside the ~50k TP gap between the Phase 4 Pioneer breakout (100k) and
    # the Phase 5 mid-game migration (150k). One dock is enough to start clearing the
    # first few Earth Orders for credits early — see templates/early/supply_dock.py.
    if total_tp >= 110000 and is_tech_unlocked("research_orders_system"):
        if count_buildings("supply_dock") == 0:
            # Heat Rush finished tens of thousands of TP ago by now - the full
            # 7-Heater rush capacity isn't earning its slot anymore. Sell one to
            # make room instead of having idled at 23/25 (or 24/25) since Phase 3
            # just so a slot would already be free whenever this milestone hit.
            if get_free_base_slots() < 1:
                h_count = count_buildings("temp_heater")
                if h_count > 5:
                    safe_undeploy_and_sell(computer, "temp_heater", h_count - 1, "temp_heater")
            print("[buyer] 110k TP Milestone: Deploying Supply Dock 1 for Earth Order fulfillment...")
            safe_buy_and_deploy(computer, "supply_dock", 1, "research_orders_system")

    # --------------------------------------------------------------------------
    # PHASE 4: Pioneer Deployment (at 100k TP)
    # --------------------------------------------------------------------------
    if total_tp >= 100000 and is_tech_unlocked("research_pioneer"):
        if count_vehicles("pioneer") == 0:
            print("[buyer] 100k TP Milestone: Deploying Pioneer Chassis...")
            if safe_buy_and_deploy(computer, "pioneer", 1, "research_pioneer"):
                # Scout loadout only (see mount_vehicle.py): Wide Sonar needs Pressure
                # 6.0 kPa and Constructor Module needs Heat 10 HU, both confirmed live
                # as not yet unlocked at the 100k TP Pioneer breakout under this
                # speedrun's Pressure/Heat Rush targets (0.200 kPa / 12.0 HU) - buying
                # them here was pure waste. No Cargo Rack either: a pure Scout has
                # nothing to haul. Basic Sonar + 6x Battery Holder (max range) instead.
                shop.buy("nav_module", 1)
                shop.buy("sonar_module", 1)
                shop.buy("battery_holder_small", 6)
                shop.buy("portable_battery", 6)
                print("[buyer] Ordered Pioneer Scout modules into base Inventory.")

    # --------------------------------------------------------------------------
    # PHASE 5: 150k TP Mid-Game Migration Signal
    # --------------------------------------------------------------------------
    if total_tp >= 150000:
        print("[MIGRATE] 150k TP reached! Bus, Archive & Control Panel unlocked. Ready for mid-game architecture.")

    sleep(2.0)

