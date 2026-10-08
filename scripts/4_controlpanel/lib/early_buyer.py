# Early-game building buyer, 70k TP (lib tier) until the Control Room (150k TP).
#
# Stepped by the headless control_room_automation.py. Tier-0 power/solar.py
# plays the same build order from Ship Computer (10k TP) up to the lib tier;
# this pass takes it over there, so the Rovers and the scout Pioneer that
# arrive between 70k and 150k start on the tier-4 scripts.
#
# Build order (docs/autoplay/early_optimization.md): one pillar's generators
# fill every free base slot at a time. The first stage whose target is unmet
# is active; the other pillars' generators are sold (full refund; atmosphere
# and heat don't decay). Keeps POWER_KEEP power, buys the Charging Station with
# the Rovers or the scout Pioneers (whichever is ready first), ROVERS Rover
# chassis plus their modules (each Rover mounts its own, lib/rover.py), and at
# PIONEER_TP, once the scout's whole preset is unlocked, queues SCOUTS scout
# Pioneers on the commission queue, one per evaluation (lib/fleet_commission.py
# buys, deploys and fits them). ROVERS is 0: a Rover mines only H1 ore and
# arrives close to the scouts (docs/gameknowledge/unlock_paths.md).
#
# Tail from MK2_GATE kPa (Pressure Mk II research): power rises to
# TAIL_POWER_KEEP (a slot-filling generator is sold for each missing building),
# then every Pressure Generator left gets a Mk II pack, bought one at a time and
# applied with computer.upgrade() (25x output, 5x draw). Packs wait for the power
# counts. The slots fix the pack count: 25 minus 15 power, the Charging Station and
# the Bio-Loop leaves 6 generators.
#
# Breakers are left to PowerGridManager; a fresh deploy is switched on once.
#
# State in the archive dict early_buyer (CODE_GUIDES.md#archive):
#   {"done": bool,        # Control Room researched: idle from then on, later
#                         # phases own the base slots
#    "generators": bool,  # build order + power + Charging Station (default True)
#    "rovers": int,       # Rover chassis to keep (default ROVERS)
#    "pioneer": bool,     # queue scout Pioneers (default True)
#    "scouts": int}       # scout Pioneers to reach (default SCOUTS)
# The headless build-order search (devtools/headless/run.mjs --policy) sets
# generators False: its plan places the buildings, this pass the vehicles.

from archive import archive
from components import component
from game_clock import now_tick
from storage import inventory_count
from swallow import swallowed
from tree_console import TreeConsole
import fleet_commission

STATE_KEY = "early_buyer"
DONE_RESEARCH = "research_custom_panels"
EVAL_TICKS = 50                 # one evaluation per ~5 s
HEARTBEAT_TICKS = 200           # info status line at most every ~20 s

STAGES = (
    ({"o2": 2.2}, "oxygen_generator"),
    ({"heat": 12.0}, "temp_heater"),
    ({"o2": 10.0}, "oxygen_generator"),
    ({"pressure": 1.2}, "pressure_generator"),
    ({}, "pressure_generator"),     # tail: TAIL_POWER_KEEP, Mk II packs
)
TAIL_STAGE = len(STAGES) - 1
GENERATORS = ("oxygen_generator", "temp_heater", "pressure_generator")
POWER_KEEP = (("battery", 3), ("solar_generator", 6))
TAIL_POWER_KEEP = (("battery", 5), ("solar_generator", 10))
MK2_PACK = "pressure_upgrade_pack_mk2"
MK2_RESEARCH = "research_pressure_mk2_pack"
MK2_TIER = 2
ROVERS = 0
SCOUTS = 3
PIONEER_TP = 100000
PIONEER_ROLE = "scout"
# Modules each Rover mounts from Inventory (lib/rover.py ROVER_LOADOUT).
ROVER_GEAR = ("nav_module", "sonar_module", "drill_module")
# Take no base slot and have no breaker.
MOBILE_ITEMS = ("rover", "pioneer")
CHARGING_STATION_TYPES = ("charging_station", "vehicle_charging_station")
HEATER_TYPES = ("temp_heater", "heater")

log = TreeConsole(module="early_buyer")


def active_stage(pillars):
    """Index of the first stage whose `until` targets are not all met (last stage otherwise)."""
    for i, (until, _generator) in enumerate(STAGES):
        for key, target in until.items():
            if pillars[key] < target:
                return i
    return len(STAGES) - 1


def is_unlocked(research_id):
    research = component("research")
    if not research:
        return False
    try:
        return bool(research.is_unlocked(research_id))
    except Exception as error:
        swallowed("early_buyer.is_unlocked: research.is_unlocked", error)
        return False


def _types(type_id):
    if type_id in CHARGING_STATION_TYPES:
        return CHARGING_STATION_TYPES
    if type_id in HEATER_TYPES:
        return HEATER_TYPES
    return (type_id,)


def building_ids(home, type_id):
    ids = []
    for t in _types(type_id):
        ids += [b.id for b in home.buildings(t)]
    return ids


def machine_tier(machine_id):
    """Installed Mk tier of a deployed machine, 1 when unreadable."""
    machine = component(machine_id)
    try:
        return int(machine.tier()) if machine else 1
    except Exception as error:
        swallowed("early_buyer.machine_tier: machine.tier", error)
        return 1


def free_base_slots(home):
    try:
        return max(0, int(home.buildings_capacity()) - int(home.buildings_used()))
    except Exception as error:
        swallowed("early_buyer.free_base_slots: home.buildings_capacity", error)
        return 0


def vehicles(kind):
    """Vehicle refs of kind ("rover"/"pioneer"), [] when the fleet can't be read."""
    fleet = component("fleet")
    if not fleet:
        return []
    try:
        return [v for v in fleet.vehicles() if getattr(v, "kind", "") == kind]
    except Exception as error:
        swallowed("early_buyer.vehicles: fleet.vehicles", error)
        return []


def mounted_modules(vehicle_id):
    vehicle = component(vehicle_id)
    try:
        return [s.module_id for s in vehicle.modules() if s.module_id] if vehicle else []
    except Exception as error:
        swallowed("early_buyer.mounted_modules: vehicle.modules", error)
        return []


def free_material_stack(shop):
    """Clears the largest ore (else ingot) item from Inventory: sell it, or drop it
    when it can't be sold. Rover ore fills Inventory before there are Warehouses,
    and every gear buy fails with inventory_full. True when something was cleared."""
    inventory = component("inventory")
    if not inventory:
        return False
    totals = {}
    try:
        for stack in inventory.stacks():
            if stack.id.endswith("_ore") or stack.id.endswith("_ingot"):
                totals[stack.id] = totals.get(stack.id, 0) + stack.count
    except Exception as error:
        swallowed("early_buyer.free_material_stack: inventory.stacks", error)
        return False
    if not totals:
        return False
    item_id = max(totals, key=lambda i: (i.endswith("_ore"), totals[i]))
    sale = shop.sell_all(item_id)
    if sale.status == "ok":
        log.print(f"[early_buyer] Inventory full: sold {sale.units}x {item_id} (+{sale.credits} cr)")
        return True
    dropped = inventory.drop_all(item_id)
    log.print(f"[early_buyer] Inventory full: dropped {item_id} -> {dropped.status}")
    return dropped.status == "ok"


class EarlyBuyer:
    """One instance in control_room_automation.py; step() every loop pass."""

    def __init__(self):
        self.last_eval = 0
        self.last_heartbeat = 0
        self.summary = "early buyer idle"

    def config(self):
        state = archive.get(STATE_KEY, {})
        return state if isinstance(state, dict) else {}

    def step(self, tick=None):
        """One evaluation when due. Returns the summary line."""
        now = now_tick() if tick is None else tick
        if self.last_eval and now - self.last_eval < EVAL_TICKS:
            return self.summary
        self.last_eval = now
        config = self.config()
        if config.get("done"):
            self.summary = "early buyer done"
            return self.summary
        if is_unlocked(DONE_RESEARCH):
            archive.set(STATE_KEY, {"done": True})
            log.print("[early_buyer] Control Room researched: build order handed over.")
            self.summary = "early buyer done"
            return self.summary
        home = component("outpost_home")
        computer = component("computer")
        shop = component("shop")
        if not home or not computer or not shop:
            self.summary = "early buyer: no outpost/computer/shop"
            return self.summary
        self.evaluate(home, computer, shop, now, config)
        return self.summary

    def pillars(self):
        pressure = component("pressure_sensor")
        oxygen = component("oxygen_sensor")
        atmosphere = component("atmosphere")
        nocturna = component("nocturna")
        try:
            return {
                "pressure": pressure.get_value() if pressure else 0.0,
                "o2": oxygen.get_value() if oxygen else 0.0,
                "heat": atmosphere.get_heat() if atmosphere else 0.0,
                "tp": nocturna.total_tp() if nocturna else 0.0,
            }
        except Exception as error:
            swallowed("early_buyer.EarlyBuyer.pillars: sensor reads", error)
            return None

    def evaluate(self, home, computer, shop, now, config):
        pillars = self.pillars()
        if pillars is None:
            self.summary = "early buyer: sensors unreadable"
            return
        stage = active_stage(pillars)
        filler = STAGES[stage][1]
        self.summary = f"early buyer: stage {stage} {filler}"
        if now - self.last_heartbeat >= HEARTBEAT_TICKS:
            self.last_heartbeat = now
            log.print(f"[early_buyer] stage {stage}: {filler} | P {pillars['pressure']:.3f} kPa | O2 {pillars['o2']:.3f} ppt | Heat {pillars['heat']:.1f} HU | TP {int(pillars['tp']):,}")

        wanted_rovers = int(config.get("rovers", ROVERS))
        rovers_ready = wanted_rovers > 0 and is_unlocked("research_rover") and is_unlocked("research_deep_extraction")
        scouts = int(config.get("scouts", SCOUTS))
        scout_ready = bool(config.get("pioneer", True)) and pillars["tp"] >= PIONEER_TP and self.scout_spec(shop, scouts) is not None
        if config.get("generators", True):
            tail = stage == TAIL_STAGE
            self.place_buildings(home, computer, shop, filler, rovers_ready or scout_ready,
                                 TAIL_POWER_KEEP if tail else POWER_KEEP)
            if tail and all(len(building_ids(home, t)) >= keep for t, keep in TAIL_POWER_KEEP):
                self.apply_mk2_packs(home, computer, shop)

        if building_ids(home, "charging_station"):
            rovers = vehicles("rover")
            if len(rovers) < wanted_rovers and rovers_ready:
                log.print(f"[early_buyer] Deploying {wanted_rovers - len(rovers)}x Rover chassis.")
                for _ in range(wanted_rovers - len(rovers)):
                    self.buy_and_deploy(home, computer, shop, "rover", 1)
            self.top_up_rover_gear(shop, vehicles("rover"))
            if scout_ready:
                self.commission_scout()

    def place_buildings(self, home, computer, shop, filler, station_wanted, power_keep=POWER_KEEP):
        """Sells the other pillars' generators, keeps power_keep, adds the Charging Station (for the Rovers or
        the scout Pioneer, whichever is ready first), fills free slots with filler."""
        # Sell first: other pillars' generators free slots and credits for the buys.
        for generator in GENERATORS:
            if generator != filler:
                self.undeploy_and_sell(home, computer, shop, generator, 0)
                if inventory_count(generator) > 0:
                    stray = shop.sell_all(generator)
                    if stray.status == "ok":
                        log.print(f"[early_buyer] Sold {stray.units}x stray {generator} kit (+{stray.credits} cr)")

        for type_id, keep in power_keep:
            short = keep - len(building_ids(home, type_id))
            if short <= 0:
                continue
            # Power before generators: sell filler for the missing slots.
            if free_base_slots(home) < short:
                self.undeploy_and_sell(home, computer, shop, filler, len(building_ids(home, filler)) - (short - free_base_slots(home)))
            self.buy_and_deploy(home, computer, shop, type_id, short)

        # Charging Station: home of the Rovers and the Pioneer, bought with whichever comes first.
        if not building_ids(home, "charging_station") and station_wanted and is_unlocked("research_charging_station"):
            if free_base_slots(home) < 1:
                self.undeploy_and_sell(home, computer, shop, filler, len(building_ids(home, filler)) - 1)
            log.print("[early_buyer] Deploying Vehicle Charging Station.")
            self.buy_and_deploy(home, computer, shop, "charging_station", 1)

        # One at a time: a short balance still buys what it can afford.
        free = free_base_slots(home)
        while free > 0 and self.buy_and_deploy(home, computer, shop, filler, 1):
            free -= 1

    def undeploy_and_sell(self, home, computer, shop, type_id, keep):
        ids = building_ids(home, type_id)
        to_remove = len(ids) - keep
        if to_remove <= 0:
            return 0
        removed = 0
        for b_id in reversed(ids):
            if removed >= to_remove:
                break
            res = computer.undeploy(b_id)
            if res.status == "ok":
                removed += 1
                log.print(f"[early_buyer] Undeployed {b_id} (freed slot)")
            else:
                log.print(f"[early_buyer] Undeploy {b_id} -> {res.status}: {res.message}")
        if removed > 0:
            sale = shop.sell(type_id, removed)
            if sale.status == "ok":
                log.print(f"[early_buyer] Sold {sale.units}x {type_id} (+{sale.credits} cr)")
        return removed

    def buy_and_deploy(self, home, computer, shop, item_id, count):
        """Buys and deploys up to count item_id (base buildings capped by free slots). True when one deployed."""
        mobile = item_id in MOBILE_ITEMS
        if not mobile:
            count = min(count, free_base_slots(home))
            if count <= 0:
                return False
        bought = shop.buy(item_id, count)
        if bought.status not in ("ok", "inventory_full"):
            log.debug(f"[early_buyer] Shop buy {count}x {item_id} -> {bought.status}: {bought.message}")
            return False
        deployed = 0
        power = component("power_control")
        for _ in range(count):
            res = computer.deploy(item_id)
            if res.status != "ok":
                log.print(f"[early_buyer] Deploy {item_id} -> {res.status}: {res.message}")
                break
            deployed += 1
            log.print(f"[early_buyer] Deployed {item_id} -> {res.machine_id}")
            if power and not mobile:
                try:
                    power.set_powered(res.machine_id, True)
                except Exception as error:
                    swallowed("early_buyer.EarlyBuyer.buy_and_deploy: power.set_powered", error)
        return deployed > 0

    def apply_mk2_packs(self, home, computer, shop):
        """Raises every Pressure Generator to Mk II, buying one pack at a time."""
        if not is_unlocked(MK2_RESEARCH):
            return
        for b_id in building_ids(home, "pressure_generator"):
            if machine_tier(b_id) >= MK2_TIER:
                continue
            if inventory_count(MK2_PACK) < 1:
                bought = shop.buy(MK2_PACK, 1)
                if bought.status != "ok":
                    log.debug(f"[early_buyer] Shop buy {MK2_PACK} -> {bought.status}: {bought.message}")
                    return
            res = computer.upgrade(MK2_PACK, b_id)
            if res.status != "ok":
                log.print(f"[early_buyer] Upgrade {b_id} with {MK2_PACK} -> {res.status}: {res.message}")
                return
            log.print(f"[early_buyer] Upgraded {b_id} to Pressure Mk II.")

    def top_up_rover_gear(self, shop, rovers):
        """Buys the ROVER_GEAR modules the Rovers lack (no module of that kind mounted) and Inventory doesn't hold."""
        want = {}
        for rover in rovers:
            mounted = mounted_modules(rover.id)
            for item_id in ROVER_GEAR:
                if not any(m.startswith(item_id) for m in mounted):
                    want[item_id] = want.get(item_id, 0) + 1
        for item_id, count in want.items():
            short = count - inventory_count(item_id)
            if short <= 0:
                continue
            res = shop.buy(item_id, short)
            if res.status == "inventory_full" and free_material_stack(shop):
                res = shop.buy(item_id, short)
            if res.status == "ok":
                log.print(f"[early_buyer] Ordered {short}x {item_id} for Rover loadouts.")
            else:
                log.debug(f"[early_buyer] Rover gear {short}x {item_id} -> {res.status}: {res.message} (retrying)")

    def scout_spec(self, shop, scouts=SCOUTS):
        """The scout Pioneer's spec while Pioneers plus queued Pioneer jobs are fewer than `scouts`
        and its whole preset is unlocked, else None."""
        jobs = fleet_commission.commission_state().get("jobs") or []
        queued = sum(1 for j in jobs if isinstance(j, dict) and fleet_commission.job_kind(j) == "pioneer")
        if len(vehicles("pioneer")) + queued >= scouts:
            return None
        try:
            catalogue = {entry.id: entry.cost for entry in shop.get_catalogue()}
        except Exception as error:
            swallowed("early_buyer.EarlyBuyer.scout_spec: shop.get_catalogue", error)
            return None
        # A job whose spec can't be built blocks until cancelled on the COMMISSION
        # card, which doesn't exist before the Control Room: queue only a buildable one.
        spec, reason = fleet_commission.build_spec(PIONEER_ROLE, catalogue)
        if spec is None:
            log.debug(f"[early_buyer] Scout Pioneer waits: {reason}.")
        return spec

    def commission_scout(self):
        """Queues the scout Pioneer (scout_spec() checked it is due and buildable this pass)."""
        job_id = fleet_commission.queue_pioneer(PIONEER_ROLE)
        log.print(f"[early_buyer] {int(PIONEER_TP):,} TP: queued scout Pioneer {job_id}.")
