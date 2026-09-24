# Drone mixin + shared state for the fleet hardware upgrade (Phase 7).
#
# Two halves, one shared archive key:
#   - lib/fleet_upgrade.py (host side, panel_4.py) swaps Drone Depots and
#     drone chassis for bigger ones: it orders the kit/chassis, deploys and
#     undeploys. It never touches a drone's modules.
#   - This mixin (drone side) does everything that needs the drone's own
#     script: couple()/uncouple() are self-only and need the drone docked at
#     a Drone Depot (docs/components/drone.md). So the drone answers a swap
#     request (charge, dock at home, hold), fits its loadout after a chassis
#     swap, and upgrades its modules in place when a better tier unlocks.
#
# The game has no call listing which module sits in which drone slot (a drone
# has no modules(), unlike Rover/Pioneer), so each drone keeps its own slot
# record in DRONE_LOADOUTS_KEY. A new chassis starts from an empty, known
# layout. An existing drone builds the record once, docked and empty, by
# uncoupling each slot, seeing which module lands in Inventory, and coupling
# it straight back (_discover_slots()).
#
# Kept free of heavy imports: lib/drone_energy.py imports retiring_depot_ids()
# from here, and lib/production.py is only imported inside functions.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

# One shared dict (CLAUDE.md rule 7), written by both halves via transaction():
#   {"enabled": bool,
#    "status": str,                         # coordinator's one-line summary (panel_5.py)
#    "depots": {old_depot_id: {...}},       # swap state per Depot (fleet_upgrade.py)
#    "retiring_depots": [old_depot_id],     # hidden from drones while they drain
#    "drones": {old_drone_id: {...}},       # swap state per drone
#    "lineage": {new_drone_id: {"from", "role", "engine", "kind", "params", "fitted"}},
#    "warehouse_swap": {...}, "warehouse_status": str}  # lib/warehouse_upgrade.py
FLEET_UPGRADE_KEY = "fleet.upgrade"
# {drone_id: {"kind": chassis, "slots": {"0": thruster, "1": module_id or None, ...}}}
DRONE_LOADOUTS_KEY = "drone.loadouts"

# Worst -> best. Only Cargo Pods and Oil Tanks have tiers; the engine type
# never changes (electric <-> heli needs an oil-distribution check first,
# see TODO.md).
CARGO_POD_TIERS = ["cargo_pod_small", "cargo_pod_medium", "cargo_pod_large"]
OIL_TANK_TIERS = ["oil_tank_small", "oil_tank_medium", "oil_tank_large"]
BATTERY_TIERS = ["battery_pack"]
THRUSTER_BY_ENGINE = {"electric": "electric_thruster", "heli": "heli_thruster"}
ROLE_MODULE_ITEMS = {"miner": "portable_bio_extractor", "scout": "portable_bio_scanner"}
# Module slots after the thruster slot 0 (docs/database/equipment_mining.md).
MODULE_SLOTS = {"drone_small": 2, "drone_medium": 3, "drone_large": 5}

# Role loadout per chassis, one category per module slot (1..N). "energy" is
# battery_pack (electric) or the best Oil Tank (heli); "cargo" the best
# Cargo Pod. Scouts are never upgraded (one-off, retired once every site is
# scanned). See docs/AI_CHEATSHEET.md.
LOADOUTS = {
    "miner": {
        "drone_small": ["role", "energy"],
        "drone_medium": ["role", "energy", "cargo"],
        "drone_large": ["role", "energy", "energy", "cargo", "cargo"],
    },
    "hauler": {
        "drone_small": ["energy", "cargo"],
        "drone_medium": ["energy", "cargo", "cargo"],
        "drone_large": ["energy", "energy", "cargo", "cargo", "cargo"],
    },
}

ALL_MODULE_IDS = tuple(
    CARGO_POD_TIERS + OIL_TANK_TIERS + BATTERY_TIERS
    + list(THRUSTER_BY_ENGINE.values()) + list(ROLE_MODULE_ITEMS.values()) + ["shield_plating"]
)

# Charge a drone tops up to at its drone_service before holding for a swap
# (the undeployed drone's Battery Packs / Oil Tanks go back to Inventory
# with whatever they hold, and the new chassis gets them).
UPGRADE_MIN_SOC = 0.98
# Swap states in which the drone must stay parked at its Depot.
HOLD_STATES = ("ready", "announced", "swapping")
# uncouple()/couple() are "hardware service orders"; poll Inventory this
# long for the result to show before giving up on identifying a module.
SERVICE_POLL_S = 0.5
SERVICE_POLL_TRIES = 10


def fleet_upgrade_state():
    """The whole FLEET_UPGRADE_KEY dict (empty when missing/malformed)."""
    state = archive.get(FLEET_UPGRADE_KEY, {})
    return state if isinstance(state, dict) else {}


def update_fleet_upgrade(mutate):
    """Atomically applies mutate(state_dict) to FLEET_UPGRADE_KEY (mutate edits in place)."""
    def updater(state):
        if not isinstance(state, dict):
            state = {}
        mutate(state)
        return state

    return archive.transaction(FLEET_UPGRADE_KEY, {}, updater)


def is_upgrade_enabled():
    """Operator switch (panel_5.py); on unless explicitly turned off."""
    return bool(fleet_upgrade_state().get("enabled", True))


def upgrade_phase_reached():
    """
    True once the save is in the mining-drill phase (same condition as
    scripts/7_miningdrills/.criteria: any mining drill deployed). Upgrading
    earlier would compete with expanding. Monotonic: the first positive check
    is stored as fleet.upgrade["phase_reached"], so later calls (drones, on
    every unload) are one archive read instead of a power-grid walk.
    """
    if fleet_upgrade_state().get("phase_reached"):
        return True
    try:
        from drill_sites import discover_drill_ids
        reached = bool(discover_drill_ids())
    except Exception:
        reached = False
    if reached:
        update_fleet_upgrade(lambda s: s.update({"phase_reached": True}))
    return reached


def upgrades_active():
    """Operator switch on AND mining-drill phase reached: gates every new swap and in-place module upgrade."""
    return is_upgrade_enabled() and upgrade_phase_reached()


def set_upgrade_enabled(on):
    update_fleet_upgrade(lambda s: s.update({"enabled": bool(on)}))


def retiring_depot_ids():
    """Depot ids a swap is retiring; lib/drone_energy.py hides them from drones."""
    ids = fleet_upgrade_state().get("retiring_depots") or []
    return set(ids) if isinstance(ids, list) else set()


def drone_swap_entry(drone_id):
    entry = (fleet_upgrade_state().get("drones") or {}).get(drone_id)
    return entry if isinstance(entry, dict) else None


def lineage_entry(drone_id):
    entry = (fleet_upgrade_state().get("lineage") or {}).get(drone_id)
    return entry if isinstance(entry, dict) else None


def inherited_params(drone_id):
    """HOME_DEPOT/CRUISE_THROTTLE the drone this one replaced was running with
    ({} if it isn't a replacement). DroneController uses them for any script
    variable left at its default (None), so a hand-pasted or default-filled
    script still behaves like the old drone."""
    entry = lineage_entry(drone_id)
    params = entry.get("params") if entry else None
    return params if isinstance(params, dict) else {}


def module_category(item_id):
    if item_id in THRUSTER_BY_ENGINE.values():
        return "thruster"
    if item_id in ROLE_MODULE_ITEMS.values():
        return "role"
    if item_id in BATTERY_TIERS or item_id in OIL_TANK_TIERS:
        return "energy"
    if item_id in CARGO_POD_TIERS:
        return "cargo"
    return "other"


def tier_ladder(item_id):
    """The tier ladder item_id sits on, or None (single-tier or untiered module)."""
    for ladder in (CARGO_POD_TIERS, OIL_TANK_TIERS):
        if item_id in ladder:
            return ladder
    return None


def get_loadout_record(drone_id):
    record = archive.get_entry(DRONE_LOADOUTS_KEY, drone_id)
    return record if isinstance(record, dict) and isinstance(record.get("slots"), dict) else None


def set_loadout_record(drone_id, kind, slots):
    archive.set_entry(DRONE_LOADOUTS_KEY, drone_id, {"kind": kind, "slots": dict(slots)})


class DroneUpgradeMixin:
    """
    Swap handshake, new-chassis fitting and in-place module upgrades, mixed
    into DroneController. Depends on DroneEnergyMixin (get_battery(),
    get_home_depot(), return_to_service_for_charge()), DroneNavigationMixin
    (current_station(), fly_to_station()) and DroneCargoMixin (cargo_count()).
    """

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    # ------------------------------------------------------------ lookups

    def _inventory_count(self, item_id):
        inventory = get_component("inventory")
        if not inventory or not hasattr(inventory, "count"):
            return 0
        try:
            return int(inventory.count(item_id) or 0)
        except Exception:
            return 0

    def _chassis_kind(self):
        """This drone's chassis (DroneRef.kind), or None if unreadable."""
        fleet = get_component("fleet")
        if fleet and hasattr(fleet, "drones"):
            try:
                for ref in fleet.drones():
                    if getattr(ref, "id", None) == self._host.name:
                        return getattr(ref, "kind", None)
            except Exception:
                pass
        return None

    def _unlocked_outputs(self):
        try:
            from production import fabricator_unlocked_outputs
            return fabricator_unlocked_outputs()
        except Exception:
            return set()

    def _category_ladder(self, category, role):
        if category == "energy":
            return OIL_TANK_TIERS if self._host.engine == "heli" else BATTERY_TIERS
        if category == "cargo":
            return CARGO_POD_TIERS
        if category == "role":
            item = ROLE_MODULE_ITEMS.get(role)
            return [item] if item else []
        return []

    def _best_in_inventory(self, ladder):
        for item_id in reversed(ladder):
            if self._inventory_count(item_id) > 0:
                return item_id
        return None

    def _best_obtainable(self, ladder, unlocked):
        """Highest tier the Fabricator can build or Inventory already holds."""
        for item_id in reversed(ladder):
            if item_id in unlocked or self._inventory_count(item_id) > 0:
                return item_id
        return None

    def _slot_plan(self, role, kind):
        return list((LOADOUTS.get(role) or {}).get(kind) or [])

    def _couple(self, slot_index, item_id):
        try:
            res = self._host.drone.couple(slot_index, item_id)
        except Exception as e:
            self._host.log.level("warn").print(f"[{self._host.name}] couple({slot_index}, '{item_id}') raised: {e}")
            return "error"
        if res.status != "ok":
            self._host.log.debug(f"[{self._host.name}] couple({slot_index}, '{item_id}'): {res.status} - {res.message}")
        return res.status

    def _uncouple(self, slot_index):
        try:
            res = self._host.drone.uncouple(slot_index)
        except Exception as e:
            self._host.log.level("warn").print(f"[{self._host.name}] uncouple({slot_index}) raised: {e}")
            return "error"
        if res.status not in ("ok", "module_not_mounted"):
            self._host.log.debug(f"[{self._host.name}] uncouple({slot_index}): {res.status} - {res.message}")
        return res.status

    def _docked_at_depot(self):
        station = self._host.current_station()
        return bool(station) and any(d["id"] == station for d in self._host.get_all_drone_depots())

    # ------------------------------------------------------------ swap handshake

    def swap_params(self):
        """This drone's script variables as the old slot had them ("None" = default)."""
        home = getattr(self._host, "home_depot_override", None)
        throttle = getattr(self._host, "cruise_throttle_override", None)
        return {
            "HOME_DEPOT": str(home) if home else "None",
            "CRUISE_THROTTLE": str(throttle) if throttle is not None else "None",
        }

    def handle_upgrade_request_if_active(self):
        """
        Answers a chassis swap request from lib/fleet_upgrade.py. Call once
        per loop cycle, right after handle_recall_if_active(); True means
        "parked for the swap, skip the normal cycle":
            if self.handle_upgrade_request_if_active():
                sleep(poll_interval)
                continue
        Work in flight finishes first (cargo aboard or a claimed target:
        returns False). Then the drone charges to UPGRADE_MIN_SOC at its
        drone_service, docks at its home Depot and marks itself "ready" with
        its script variables, and holds there until the coordinator swaps it.
        """
        entry = drone_swap_entry(self._host.name)
        state = entry.get("state") if entry else None
        if state in HOLD_STATES:
            if not self._docked_at_depot():
                # Knocked off the berth (rescue, operator): request again.
                self._host.log.level("warn").print(f"[{self._host.name}] Upgrade hold: no longer docked at a Drone Depot; re-docking.")
                update_fleet_upgrade(lambda s: s.get("drones", {}).get(self._host.name, {}).update({"state": "requested"}))
                return True
            self._host.publish_telemetry("UPGRADE_HOLD", f"waiting for chassis swap ({state})")
            return True
        if state != "requested":
            return False

        if self._host.current_target_key or self._host.cargo_count() > 0:
            self._host.log.trace(f"[{self._host.name}] Upgrade requested; finishing current work first.")
            return False

        _, _, level = self._host.get_battery()
        if level < UPGRADE_MIN_SOC:
            self._host.return_to_service_for_charge(self._host.log, f"Charging to {UPGRADE_MIN_SOC*100:.0f}% before chassis swap ({level*100:.0f}%)")
            self._host.publish_telemetry("UPGRADE_CHARGING")
            return True

        depot_coords, depot = self._host.get_home_depot()
        depot_id = depot.get("id")
        if not depot_id:
            self._host.log.level("warn").print(f"[{self._host.name}] Upgrade requested but no home Drone Depot found; waiting.")
            return True
        if self._host.current_station() != depot_id:
            self._host.log.debug(f"[{self._host.name}] Upgrade requested; docking at home Drone Depot '{depot_id}'.")
            self._host.publish_telemetry("UPGRADE_DOCKING", depot_id)
            self._host.fly_to_station(depot_id, target_coords=depot_coords)
            return True

        params = self.swap_params()
        outpost_id = depot.get("outpost_id") or ""
        role = getattr(self._host, "role", None)
        engine = self._host.engine

        def mark_ready(s):
            e = s.get("drones", {}).get(self._host.name)
            if isinstance(e, dict) and e.get("state") == "requested":
                e.update({"state": "ready", "params": params, "depot": depot_id, "outpost": outpost_id, "role": role, "engine": engine})

        update_fleet_upgrade(mark_ready)
        self._host.log.print(f"[{self._host.name}] Ready for chassis swap: docked at '{depot_id}', cargo empty, {level*100:.0f}% charge.")
        self._host.publish_telemetry("UPGRADE_HOLD", "ready for chassis swap")
        return True

    # ------------------------------------------------------------ new chassis

    def fit_loadout_if_new(self):
        """
        After a chassis swap: couples thruster, role module and the LOADOUTS
        entry from Inventory into the new, empty drone. Call from
        DroneController.run() before detect_role(), in a loop until it
        returns True (a bare drone has no role to detect). True when this
        drone is no replacement, or is fitted enough to work (thruster,
        energy, plus the role module / a Cargo Pod). Slots with nothing in
        Inventory stay empty and are ordered; maintain_modules_at_depot()
        fills them later.
        """
        lineage = lineage_entry(self._host.name)
        if not lineage or lineage.get("fitted"):
            return True
        role = lineage.get("role")
        engine = lineage.get("engine") or "electric"
        self._host.engine = engine  # nothing coupled yet, so detect_engine() can't tell
        kind = self._chassis_kind() or lineage.get("kind")
        if not self._host.current_station():
            self._host.log.level("warn").print(f"[{self._host.name}] New chassis is not docked at a Drone Depot; cannot couple modules.")
            return False

        record = get_loadout_record(self._host.name)
        slots = dict(record["slots"]) if record and record.get("kind") == kind else {}
        self._host.log.start(f"[{self._host.name}] Fitting new {kind} as {role} ({engine})")

        thruster = THRUSTER_BY_ENGINE.get(engine)
        if not slots.get("0") and thruster:
            status = self._couple(0, thruster)
            if status in ("ok", "slot_occupied"):
                slots["0"] = thruster

        unlocked = self._unlocked_outputs()
        wanted = {}
        for index, category in enumerate(self._slot_plan(role, kind), start=1):
            if slots.get(str(index)):
                continue
            ladder = self._category_ladder(category, role)
            item_id = self._best_in_inventory(ladder)
            if item_id and self._couple(index, item_id) == "ok":
                slots[str(index)] = item_id
                self._host.log.debug(f"[{self._host.name}] Slot {index} ({category}): coupled '{item_id}'.")
                continue
            slots[str(index)] = None
            best = self._best_obtainable(ladder, unlocked)
            if best and best in unlocked:
                wanted[best] = wanted.get(best, 0) + 1
            self._host.log.debug(f"[{self._host.name}] Slot {index} ({category}): nothing in Inventory; ordering '{best}'." if best in unlocked else f"[{self._host.name}] Slot {index} ({category}): nothing in Inventory and nothing to order.")

        set_loadout_record(self._host.name, kind, slots)
        self._request_modules(wanted)

        coupled = [m for i, m in slots.items() if i != "0" and m]
        categories = {module_category(m) for m in coupled}
        viable = bool(slots.get("0")) and "energy" in categories and (
            (role == "miner" and "role" in categories) or (role == "hauler" and "cargo" in categories)
        )
        if viable:
            update_fleet_upgrade(lambda s: s.get("lineage", {}).get(self._host.name, {}).update({"fitted": True}))
            self._host.log.end(f"[{self._host.name}] Fitted: " + ", ".join(f"{i}={m}" for i, m in sorted(slots.items()) if m))
            return True
        self._host.log.end(f"[{self._host.name}] Not flyable yet (have {sorted(categories) or 'nothing'}); waiting for modules: {wanted or 'none orderable'}.")
        return False

    # ------------------------------------------------------------ in place

    def _request_modules(self, wanted):
        try:
            from production import set_upgrade_order
            set_upgrade_order(self._host.name, wanted)
        except Exception as e:
            self._host.log.debug(f"[{self._host.name}] set_upgrade_order failed: {e}")

    def _wait_for_inventory_gain(self, before):
        """Module ids whose Inventory count rose above before{}, polled briefly."""
        for _ in range(SERVICE_POLL_TRIES):
            gained = [m for m in ALL_MODULE_IDS if self._inventory_count(m) > before.get(m, 0)]
            if gained:
                return gained
            sleep(SERVICE_POLL_S)
        return []

    def _discover_slots(self, kind):
        """
        One-time slot survey for a drone without a loadout record: uncouple
        each module slot, see which module lands in Inventory, couple it
        straight back. Needs the drone docked at a Depot with empty cargo
        (Cargo Pods must be empty to uncouple). Returns the slots dict, or
        None if a slot could not be read (nothing recorded then).
        """
        slots = {"0": THRUSTER_BY_ENGINE.get(self._host.engine)}
        self._host.log.start(f"[{self._host.name}] Surveying module slots of {kind} (one-time)")
        for index in range(1, MODULE_SLOTS.get(kind, 0) + 1):
            before = {m: self._inventory_count(m) for m in ALL_MODULE_IDS}
            status = self._uncouple(index)
            if status == "module_not_mounted":
                slots[str(index)] = None
                continue
            if status != "ok":
                self._host.log.end(f"[{self._host.name}] Slot survey stopped at slot {index} ({status}).")
                return None
            gained = self._wait_for_inventory_gain(before)
            if len(gained) != 1:
                self._host.log.level("warn").print(f"[{self._host.name}] Slot {index}: could not identify the uncoupled module (Inventory gained {gained or 'nothing'}).")
            module = gained[0] if gained else None
            if module and self._couple(index, module) == "ok":
                slots[str(index)] = module
            else:
                slots[str(index)] = None
                self._host.log.level("error").print(f"[{self._host.name}] Slot {index}: module '{module}' left in Inventory; the loadout pass refills the slot.")
        self._host.log.end(f"[{self._host.name}] Slots: " + ", ".join(f"{i}={m}" for i, m in sorted(slots.items())))
        return slots

    def maintain_modules_at_depot(self):
        """
        In-place module upkeep, called right after a successful unload while
        still docked at a Depot with empty cargo (drone_hauler._deliver(),
        drone_mining._return_and_unload()):
          1. a coupled Cargo Pod / Oil Tank with a better unlocked tier is
             swapped for it once one is in Inventory (else ordered);
          2. an empty slot gets whatever LOADOUTS still lacks for this role.
        Never changes the engine type or a module's category. Scouts and
        drones with no known role are left alone, and nothing happens while
        the panel_5.py switch is off or before the mining-drill phase
        (upgrades_active()) -- an order placed earlier is withdrawn.
        """
        role = getattr(self._host, "role", None)
        if role not in LOADOUTS or self._host.cargo_count() > 0 or not self._docked_at_depot():
            return
        if not upgrades_active():
            self._request_modules({})
            return
        kind = self._chassis_kind()
        if kind not in MODULE_SLOTS:
            return
        record = get_loadout_record(self._host.name)
        if record is None or record.get("kind") != kind:
            slots = self._discover_slots(kind)
            if slots is None:
                return
            set_loadout_record(self._host.name, kind, slots)
        else:
            slots = dict(record["slots"])

        unlocked = self._unlocked_outputs()
        wanted = {}
        changed = False

        for index in range(1, MODULE_SLOTS[kind] + 1):
            current = slots.get(str(index))
            ladder = tier_ladder(current) if current else None
            if not current or not ladder:
                continue
            best = self._best_obtainable(ladder, unlocked)
            if not best or ladder.index(best) <= ladder.index(current):
                continue
            if self._inventory_count(best) <= 0:
                wanted[best] = wanted.get(best, 0) + 1
                continue
            if self._uncouple(index) != "ok":
                continue
            if self._couple(index, best) == "ok":
                slots[str(index)] = best
                self._host.log.print(f"[{self._host.name}] Upgraded slot {index}: '{current}' -> '{best}'.")
            elif self._couple(index, current) != "ok":
                slots[str(index)] = None
                self._host.log.level("error").print(f"[{self._host.name}] Slot {index}: could not couple '{best}' or put '{current}' back; left empty.")
            changed = True

        plan = self._slot_plan(role, kind)
        have = [module_category(m) for i, m in slots.items() if i != "0" and m]
        missing = list(plan)
        for category in have:
            if category in missing:
                missing.remove(category)
        for index in range(1, MODULE_SLOTS[kind] + 1):
            if slots.get(str(index)) or not missing:
                continue
            category = missing[0]
            ladder = self._category_ladder(category, role)
            item_id = self._best_in_inventory(ladder)
            if item_id and self._couple(index, item_id) == "ok":
                slots[str(index)] = item_id
                missing.pop(0)
                changed = True
                self._host.log.print(f"[{self._host.name}] Filled empty slot {index} with '{item_id}' ({category}).")
                continue
            best = self._best_obtainable(ladder, unlocked)
            if best and best in unlocked:
                wanted[best] = wanted.get(best, 0) + 1
            missing.pop(0)

        if changed:
            set_loadout_record(self._host.name, kind, slots)
            self._host.detect_engine()
        self._request_modules(wanted)
        if wanted:
            self._host.log.debug(f"[{self._host.name}] Module upkeep: ordered {wanted}.")
