# ==============================================================================
# SOLAR GENERATOR & AUTONOMOUS BUILDING-BUYER (SHIP COMPUTER TO THE LIB TIER)
# ==============================================================================
# Every panel runs elevation sun-tracking.
# The lowest-indexed solar panel (solar_1) is elected Master Building-Buyer:
#   - Plays the build order (STAGES below) from Ship Computer (10k TP) to the
#     lib tier (Data Archive, 70k TP). There scripts_sync swaps in the tier-4
#     scripts and control_room_automation.py's lib/early_buyer.py takes the
#     build order over, Charging Station, Rovers and Pioneer included.
#   - Safely guards research gates via research.is_unlocked()
#   - Executes building swaps via computer.deploy() / computer.undeploy()
#   - Purchases kits and modules via shop.buy() and liquidates via shop.sell()
# ==============================================================================

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import solar as self

def need(component):
    # Core component this script cannot run without; fail loudly at start if missing.
    assert component is not None
    return component


clock = need(get_component("clock"))
home = need(get_component("outpost_home"))
research = get_component("research")
shop = need(get_component("shop"))
nocturna = get_component("nocturna")
inventory = get_component("inventory")

pressure_sensor = get_component("pressure_sensor")
oxygen_sensor = get_component("oxygen_sensor")
# Heat units (the 12 HU gate), not the thermometer's display °C.
atmosphere = get_component("atmosphere")

last_eval_time = 0.0
last_heartbeat = 0.0

# Build order, from the headless build-order search
# (docs/autoplay/early_optimization.md, plan "feeders2.2: heat>o2>pressure 12/10/0.3 pw6/3").
# One pillar's generators fill every free base slot at a time. The first stage
# whose target is unmet is active; the other pillars' generators are sold (full
# refund; atmosphere and heat don't decay). O2 to 2.2 ppt gives the 10k TP for
# Ship Computer, so this buyer takes over from there. Heat stops at the Battery
# Holder gate (12 HU), O2 at its phase-1 cap (10 ppt), pressure fills the tail.
STAGES = (
    ({"o2": 2.2}, "oxygen_generator"),
    ({"heat": 12.0}, "temp_heater"),
    ({"o2": 10.0}, "oxygen_generator"),
    ({}, "pressure_generator"),
)
GENERATORS = ("oxygen_generator", "temp_heater", "pressure_generator")
POWER_KEEP = (("battery", 3), ("solar_generator", 6))


def active_stage(pillars):
    """Index of the first stage whose `until` targets are not all met (last stage otherwise)."""
    for i, (until, _generator) in enumerate(STAGES):
        for key, target in until.items():
            if pillars[key] < target:
                return i
    return len(STAGES) - 1

# No lib/ access in this tier: local stand-in for lib/swallow.py's swallowed().
# Logs a caught-and-recovered error at debug level (repeats at one site once).
_SWALLOW_LAST = {}


def _swallowed(where, error):
    message = f"{error!r}"
    if _SWALLOW_LAST.get(where) == message:
        return
    _SWALLOW_LAST[where] = message
    console = get_component("console")
    if console:
        console.debug(f"[swallowed] {where}: {message}")


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
        except Exception as error:
            _swallowed("solar.is_tech_unlocked: research.is_unlocked", error)
    return False

def get_building_ids(type_id):
    if type_id in ("temp_heater", "heater", "heat_generator"):
        return [b.id for b in home.buildings("temp_heater")] + [b.id for b in home.buildings("heater")]
    return [b.id for b in home.buildings(type_id)]

def count_buildings(type_id):
    return len(get_building_ids(type_id))

def get_free_base_slots():
    try:
        cap_val = home.buildings_capacity() if callable(getattr(home, "buildings_capacity", None)) else getattr(home, "buildings_capacity", 25)
        used_val = home.buildings_used() if callable(getattr(home, "buildings_used", None)) else getattr(home, "buildings_used", 0)
        return max(0, int(cap_val) - int(used_val))
    except Exception as error:
        _swallowed("solar.get_free_base_slots: home.buildings_capacity", error)
        return max(0, 25 - len(home.buildings()))

def safe_undeploy_and_sell(computer: "Computer", type_id, keep_count, item_id):
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

def safe_buy_and_deploy(computer: "Computer", item_id, count_needed, tech_gate=None):
    if tech_gate and not is_tech_unlocked(tech_gate):
        return False
    count_needed = min(count_needed, get_free_base_slots())
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
                except Exception as error:
                    _swallowed("solar: pc.set_powered", error)
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
    heat = atmosphere.get_heat() if atmosphere else 0.0
    total_tp = nocturna.total_tp() if nocturna else 0.0

    stage = active_stage({"o2": o2, "pressure": pressure, "heat": heat})
    filler = STAGES[stage][1]

    if now - last_heartbeat >= 20.0:
        print(f"[buyer] Master on {self.id} | stage {stage}: {filler} | P: {pressure:.3f} kPa | O2: {o2:.3f} ppt | Heat: {heat:.1f} HU | TP: {int(total_tp):,}")
        last_heartbeat = now

    # --------------------------------------------------------------------------
    # POWER-ON PASS (power_control only - no Ship Computer needed)
    # --------------------------------------------------------------------------
    # Deliberately runs before the Ship Computer gate below: powering a building on/off
    # goes through power_control, never through computer.deploy()/undeploy(). Ship
    # Computer (research_computer) doesn't unlock until 10,000 TP, which can trail
    # behind 1.0 ppt Oxygen, so this gate must run independently.
    pc = get_component("power_control")
    if pc and hasattr(pc, "set_powered"):
        for b in home.buildings():
            # Keep bio unpowered if o2 < 1.0 or feeder not unlocked.
            # Must be the public research id ("research_auto_feeders", per docs/components/
            # research.md's is_unlocked() example) - the catalog's internal "Tech id" field
            # ("feeder_unlock") is a different namespace read from save-state unlockedTech
            # lists (see devtools/scripts_sync.py's read_save_state), not what is_unlocked()
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
                    # A script refused or stopped while the machine was unpowered stays stopped: run it now.
                    run = get_component("run_control")
                    if run and hasattr(run, "start"):
                        started = run.start(b.id)
                        print(f"[buyer] Started {b.id} script: {started.status}")
                elif not hasattr(pc, "is_powered"):
                    pc.set_powered(b.id, True)
            except Exception as error:
                _swallowed("solar: pc.is_powered", error)

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
    # BUILD ORDER (STAGES): power anchor, active pillar's generators
    # --------------------------------------------------------------------------
    # Sell first: other pillars' generators free slots and credits for the buys.
    for generator in GENERATORS:
        if generator != filler:
            safe_undeploy_and_sell(computer, generator, 0, generator)
            # Kits left in Inventory (a buy whose deploy failed) are never undeployed.
            if inventory and inventory.count(generator) > 0:
                stray = shop.sell_all(generator)
                if stray.status == "ok":
                    print(f"[buyer] Sold {stray.units}x stray {generator} kit (+{stray.credits} cr)")

    for type_id, keep in POWER_KEEP:
        have = count_buildings(type_id)
        if have < keep:
            safe_buy_and_deploy(computer, type_id, keep - have)

    # One at a time: a short balance still buys what it can afford.
    free = get_free_base_slots()
    while free > 0 and safe_buy_and_deploy(computer, filler, 1):
        free -= 1

    sleep(2.0)

