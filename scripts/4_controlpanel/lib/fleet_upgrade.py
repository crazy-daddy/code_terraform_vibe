# Fleet hardware upgrade coordinator (Phase 7), run from the headless
# control-room calculator (control_panel/panel_4.py) every storage tick.
#
# Only once the save reaches the mining-drill phase (any mining drill
# deployed, same condition as scripts/7_miningdrills/.criteria) and while the
# panel_5.py switch is on -- earlier, expanding beats upgrading.
#
# Swaps, one at a time fleet-wide, Depots first:
#   - every Drone Depot for the best unlocked Depot kit (small -> large
#     directly; Medium only while Large is still locked), and
#   - every miner/hauler drone for the best unlocked chassis. Scouts are
#     never touched (one-off, retired once every site is scanned).
# Within each kind the lowest tier goes first, so small ones jump straight to
# the top tier before any Medium is touched.
#
# This side only orders (lib/production.py's fabricator.upgrade_orders,
# ranked below manual orders and blueprint demand), deploys, undeploys and
# renames. Everything that needs the drone's own script -- charging and
# docking for the swap, coupling the new chassis' modules -- is
# lib/drone_upgrade.py. Both share the fleet.upgrade archive dict; every step
# below re-reads it, advances at most one state, and writes back, so a
# restart at any point resumes where it stopped.
#
# A new machine lands with no script, and scripts cannot attach one
# (run_control.apply_variant() needs a variant the operator saved, and
# variants don't carry across drone sizes -- see TODO.md). So the "attach"
# state waits for devtools/scripts_sync.py (any mode) or the operator to fill
# the slot, retrying run_control.start() until the machine reports in. For a
# drone, the swap is written to the archive ("announced") and left to reach
# the save file before the deploy, so scripts_sync can match the new slot to
# the old drone and fill it without asking.

from archive import archive
import fleet_status
from drone_upgrade import DRONE_LOADOUTS_KEY, fleet_upgrade_state, update_fleet_upgrade, is_upgrade_enabled, upgrade_phase_reached
from drone_energy import HOME_DEPOTS_KEY
from drone_claims import DRONE_RECALL_KEY, MISSION_KEY
from drone_depot import DEPOT_STATUS_KEY
from production import set_upgrade_order, fabricator_unlocked_outputs, UPGRADE_ORDERS_KEY, STANDING_ORDER_REQUESTERS
from tree_console import TreeConsole

# Worst -> best, kit id -> the Depot typeId it deploys (lib/drone_energy.py).
DEPOT_KIT_TIERS = ["drone_station_kit", "drone_station_kit_medium", "drone_station_kit_large"]
DEPOT_TYPE_TIERS = ["drone_station", "drone_station_medium", "drone_station_large"]
DRONE_CHASSIS_TIERS = ["drone_small", "drone_medium", "drone_large"]
UPGRADE_ROLES = ("miner", "hauler")

# fabricator.upgrade_orders requester id for the coordinator's own orders
# (drones order their modules under their own id).
REQUESTER = "fleet_upgrade"

# How long an "announced" drone swap waits before deploying, so the
# announcement reaches the save file (autosave ~every 30 s real time) before
# the new drone's script slot appears. 1800 ticks = 3 game minutes; still
# > 30 s real at 4x game speed.
ANNOUNCE_SAVE_WAIT_TICKS = 1800
# A drone is only picked for a swap while its script is alive: fleet.status
# heartbeat no older than this (lib/fleet_status.py writes >= every 50 ticks).
DRONE_ALIVE_TICKS = 600
# Undeploy failures before a swap gives up ("blocked") and hands the
# machine back to its script. The operator clears a blocked entry by
# deleting it from fleet.upgrade in the Data Archive Notebook.
MAX_UNDEPLOY_ATTEMPTS = 5

DEPOT_ACTIVE_STATES = ("ordered", "deploying", "attach", "draining", "undeploying", "renaming")
DRONE_ACTIVE_STATES = ("ordered", "requested", "ready", "announced", "swapping", "attach", "fitting")
# Swaps the panel_5.py switch can still cancel: nothing deployed/undeployed yet.
DEPOT_CANCELLABLE_STATES = ("ordered",)
DRONE_CANCELLABLE_STATES = ("ordered", "requested", "ready", "announced")


def _component(component_id):
    try:
        return get_component(component_id)
    except Exception:
        return None


class FleetUpgradeCoordinator:
    """Host-side state machine for Depot and drone chassis swaps. One instance, reused across cycles."""

    def __init__(self):
        self.log = TreeConsole(module="fleet_upgrade")

    # ------------------------------------------------------------ lookups

    def _inventory_count(self, item_id):
        inventory = _component("inventory")
        try:
            return int(inventory.count(item_id) or 0) if inventory else 0
        except Exception:
            return 0

    def _unlocked(self, ladder, unlocked_outputs):
        """Items of ladder the Fabricator can build or Inventory holds."""
        return [i for i in ladder if i in unlocked_outputs or self._inventory_count(i) > 0]

    def _depots(self):
        """[{id, name, type_id, outpost_id}] for every Drone Depot of every size."""
        found = []
        network = _component("outpost_network")
        try:
            outposts = network.outposts() if network else []
        except Exception:
            outposts = []
        for outpost in outposts:
            for type_id in DEPOT_TYPE_TIERS:
                try:
                    refs = outpost.buildings(type_id)
                except Exception:
                    continue
                for ref in refs:
                    found.append({
                        "id": getattr(ref, "id", ""),
                        "name": getattr(ref, "name", "") or "",
                        "type_id": type_id,
                        "outpost_id": getattr(outpost, "id", ""),
                    })
        return [d for d in found if d["id"]]

    def _drones(self):
        """{drone_id: DroneRef} for every owned drone."""
        fleet = _component("fleet")
        try:
            return {getattr(d, "id", ""): d for d in fleet.drones()} if fleet else {}
        except Exception:
            return {}

    def _start_script(self, machine_id):
        """run_control.start(), treating already_running as success. Returns the status."""
        run = _component("run_control")
        if not run:
            return "no_run_control"
        try:
            res = run.start(machine_id)
        except Exception as e:
            return f"error: {e}"
        return "ok" if res.status in ("ok", "already_running") else res.status

    def _stop_script(self, machine_id):
        run = _component("run_control")
        try:
            if run and run.is_running(machine_id):
                run.stop(machine_id)
        except Exception as e:
            self.log.debug(f"[fleet_upgrade] stop({machine_id}) raised: {e}")

    def _patch(self, section, key, **fields):
        """Atomically merges fields into fleet.upgrade[section][key]."""
        def mutate(state):
            state.setdefault(section, {}).setdefault(key, {}).update(fields)
        update_fleet_upgrade(mutate)

    def _drop(self, section, key):
        update_fleet_upgrade(lambda s: s.get(section, {}).pop(key, None))

    def _set_status(self, text):
        if fleet_upgrade_state().get("status") != text:
            update_fleet_upgrade(lambda s: s.update({"status": text}))

    # ------------------------------------------------------------ main step

    def step(self, current_tick):
        """One coordinator pass. Returns a short summary for panel_4's automation line."""
        enabled = is_upgrade_enabled()
        if enabled and not upgrade_phase_reached():
            self._set_status("waiting for mining drills")
            return "fleet upgrade: waiting for mining drills"
        if not enabled:
            self._cancel_unstarted_swaps()
        computer = _component("computer")
        if not computer or not hasattr(computer, "deploy"):
            self._set_status("no Ship Computer")
            return "fleet upgrade: no Ship Computer"

        unlocked_outputs = fabricator_unlocked_outputs()
        depots = self._depots()
        drones = self._drones()
        self._prune(depots, drones)
        state = fleet_upgrade_state()

        # 1. A swap already in flight gets advanced; nothing new starts meanwhile.
        #    With the switch off, only swaps past the point of no return are
        #    left here (_cancel_unstarted_swaps()) and they still finish.
        prefix = "upgrade" if enabled else "upgrade off, finishing"
        for old_id, entry in (state.get("depots") or {}).items():
            if isinstance(entry, dict) and entry.get("state") in DEPOT_ACTIVE_STATES:
                text = self._advance_depot(old_id, entry, depots, computer, current_tick)
                self._set_status(text if enabled else f"off, finishing: {text}")
                return f"{prefix}: {text}"
        for old_id, entry in (state.get("drones") or {}).items():
            if isinstance(entry, dict) and entry.get("state") in DRONE_ACTIVE_STATES:
                text = self._advance_drone(old_id, entry, drones, computer, current_tick)
                self._set_status(text if enabled else f"off, finishing: {text}")
                return f"{prefix}: {text}"

        set_upgrade_order(REQUESTER, {})
        if not enabled:
            self._set_status("disabled")
            return "fleet upgrade off"

        # 2. Nothing in flight: pick the next machine, Depots first.
        text = self._start_next_depot(state, depots, unlocked_outputs) or self._start_next_drone(state, drones, unlocked_outputs, current_tick)
        text = text or "fleet up to date"
        self._set_status(text)
        return f"upgrade: {text}"

    def _cancel_unstarted_swaps(self):
        """
        Switch turned off: drops every swap that hasn't touched hardware yet
        (Depot "ordered"; drone "ordered"/"requested"/"ready"/"announced"),
        so a drone parked for its swap goes back to work, and withdraws the
        coordinator's order. Swaps that already deployed or undeployed
        something are kept and finished -- stopping them halfway would leave
        a retiring Depot hidden or a new drone without modules.
        """
        state = fleet_upgrade_state()
        depots = [k for k, e in (state.get("depots") or {}).items() if isinstance(e, dict) and e.get("state") in DEPOT_CANCELLABLE_STATES]
        drones = [k for k, e in (state.get("drones") or {}).items() if isinstance(e, dict) and e.get("state") in DRONE_CANCELLABLE_STATES]
        if not depots and not drones:
            return
        def mutate(s):
            for k in depots:
                s.get("depots", {}).pop(k, None)
            for k in drones:
                s.get("drones", {}).pop(k, None)
        update_fleet_upgrade(mutate)
        set_upgrade_order(REQUESTER, {})
        self.log.print(f"[fleet_upgrade] Switched off: cancelled swaps not started yet (depots {depots}, drones {drones}).")

    # ------------------------------------------------------------ selection

    def _start_next_depot(self, state, depots, unlocked_outputs):
        available = self._unlocked(DEPOT_KIT_TIERS, unlocked_outputs)
        if not available:
            return None
        target_kit = available[-1]
        target_tier = DEPOT_KIT_TIERS.index(target_kit)
        entries = state.get("depots") or {}
        candidates = [
            d for d in depots
            if DEPOT_TYPE_TIERS.index(d["type_id"]) < target_tier and d["id"] not in entries
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda d: (DEPOT_TYPE_TIERS.index(d["type_id"]), d["id"]))
        pick = candidates[0]
        self._patch("depots", pick["id"], state="ordered", target_kit=target_kit, outpost=pick["outpost_id"], old_name=pick["name"], new_id=None)
        self.log.print(f"[fleet_upgrade] Depot '{pick['id']}' ({pick['type_id']}) at '{pick['outpost_id']}' -> '{target_kit}'.")
        self.log.debug(f"[fleet_upgrade] Depot candidates below {target_kit}: {[c['id'] for c in candidates]}.")
        return f"{pick['id']}: ordering {target_kit}"

    def _start_next_drone(self, state, drones, unlocked_outputs, current_tick):
        available = self._unlocked(DRONE_CHASSIS_TIERS, unlocked_outputs)
        if not available:
            return None
        target_kind = available[-1]
        target_tier = DRONE_CHASSIS_TIERS.index(target_kind)
        entries = state.get("drones") or {}
        telemetry = fleet_status.get_all()
        candidates = []
        for drone_id, ref in drones.items():
            kind = getattr(ref, "kind", "")
            if kind not in DRONE_CHASSIS_TIERS or DRONE_CHASSIS_TIERS.index(kind) >= target_tier or drone_id in entries:
                continue
            status = telemetry.get(drone_id) or {}
            role = status.get("role")
            if role not in UPGRADE_ROLES:
                self.log.trace(f"[fleet_upgrade] Skipping drone '{drone_id}': role {role!r} (not {UPGRADE_ROLES}).")
                continue
            if current_tick - (status.get("tick") or 0) > DRONE_ALIVE_TICKS:
                self.log.trace(f"[fleet_upgrade] Skipping drone '{drone_id}': no recent heartbeat.")
                continue
            candidates.append((DRONE_CHASSIS_TIERS.index(kind), drone_id, role, getattr(ref, "engine", "") or "electric"))
        if not candidates:
            return None
        candidates.sort()
        _, drone_id, role, engine = candidates[0]
        old_name = getattr(drones[drone_id], "name", "") or ""
        self._patch("drones", drone_id, state="ordered", target_kind=target_kind, role=role, engine=engine, old_name=old_name, new_id=None)
        self.log.print(f"[fleet_upgrade] Drone '{drone_id}' ({role}, {engine}) -> '{target_kind}'.")
        return f"{drone_id}: ordering {target_kind}"

    # ------------------------------------------------------------ Depot swap

    def _advance_depot(self, old_id, entry, depots, computer, current_tick):
        state = entry.get("state")
        kit = entry.get("target_kit")
        outpost_id = entry.get("outpost")
        new_type = DEPOT_TYPE_TIERS[DEPOT_KIT_TIERS.index(kit)] if kit in DEPOT_KIT_TIERS else None
        self.log.debug(f"[fleet_upgrade] Depot '{old_id}': state '{state}'.")

        if state == "ordered":
            if self._inventory_count(kit) <= 0:
                set_upgrade_order(REQUESTER, {kit: 1})
                return f"{old_id}: waiting for {kit}"
            set_upgrade_order(REQUESTER, {})
            known = [d["id"] for d in depots if d["outpost_id"] == outpost_id and d["type_id"] == new_type]
            self._patch("depots", old_id, state="deploying", known=known)
            return f"{old_id}: deploying {kit}"

        if state == "deploying":
            known = set(entry.get("known") or [])
            adopted = next((d["id"] for d in depots if d["outpost_id"] == outpost_id and d["type_id"] == new_type and d["id"] not in known), None)
            if adopted is None:
                res = computer.deploy(kit, outpost_id)
                if res.status != "ok":
                    if res.status in ("duplicate_outpost_machine", "deploy_limit", "wrong_biome_for_machine", "location_not_found"):
                        self._patch("depots", old_id, state="blocked", reason=res.status)
                        self.log.level("warn").print(f"[fleet_upgrade] Depot '{old_id}': deploy('{kit}', '{outpost_id}') refused ({res.status}: {res.message}); swap blocked.")
                        return f"{old_id}: blocked ({res.status})"
                    if res.status == "no_kit":
                        self._patch("depots", old_id, state="ordered")
                    return f"{old_id}: deploy {res.status}"
                adopted = res.machine_id
            def mutate(s):
                s.setdefault("depots", {}).setdefault(old_id, {}).update({"state": "attach", "new_id": adopted})
                retiring = s.setdefault("retiring_depots", [])
                if old_id not in retiring:
                    retiring.append(old_id)
            update_fleet_upgrade(mutate)
            self.log.print(f"[fleet_upgrade] Deployed '{adopted}' ({new_type}) at '{outpost_id}'; retiring '{old_id}'.")
            return f"{old_id}: deployed {adopted}"

        new_id = entry.get("new_id")
        if state == "attach":
            if archive.get_entry(DEPOT_STATUS_KEY, new_id) is not None:
                self._patch("depots", old_id, state="draining")
                return f"{old_id}: {new_id} running"
            started = self._start_script(new_id)
            if started != "ok":
                return f"{old_id}: waiting for a script on {new_id} (run scripts_sync or paste drone_station.py)"
            return f"{old_id}: started {new_id}"

        if state == "draining":
            old = _component(old_id)
            bays, slots = 0, 0  # already gone: undeploy() then reports not_found, which counts as done
            if old is not None:
                try:
                    bays, slots = old.bays_occupied(), old.slots_used()
                except Exception as e:
                    self.log.debug(f"[fleet_upgrade] Depot '{old_id}': occupancy unreadable ({e}); trying undeploy.")
            if bays or slots:
                return f"{old_id}: draining ({bays} bay(s), {slots} slot(s) in use)"
            self._patch("depots", old_id, state="undeploying")
            return f"{old_id}: empty"

        if state == "undeploying":
            self._stop_script(old_id)
            res = computer.undeploy(old_id)
            if res.status not in ("ok", "not_found"):
                attempts = int(entry.get("attempts", 0)) + 1
                self._start_script(old_id)  # keep draining meanwhile
                if attempts >= MAX_UNDEPLOY_ATTEMPTS:
                    self._patch("depots", old_id, state="blocked", reason=res.status)
                    update_fleet_upgrade(lambda s: s.get("retiring_depots", []).remove(old_id) if old_id in s.get("retiring_depots", []) else None)
                    self.log.level("warn").print(f"[fleet_upgrade] Depot '{old_id}': undeploy refused {attempts}x ({res.status}: {res.message}); swap blocked, Depot back in service.")
                    return f"{old_id}: blocked ({res.status})"
                self._patch("depots", old_id, state="draining", attempts=attempts)
                return f"{old_id}: undeploy {res.status}"
            self._patch("depots", old_id, state="renaming")
            self.log.print(f"[fleet_upgrade] Undeployed '{old_id}'; its kit is back in Inventory.")
            return f"{old_id}: undeployed"

        if state == "renaming":
            old_name = entry.get("old_name")
            if old_name and old_name != old_id:
                res = computer.rename(new_id, old_name)
                if res.status != "ok":
                    self.log.debug(f"[fleet_upgrade] rename('{new_id}', '{old_name}'): {res.status}; keeping its own name.")
            self._repin_homes(old_id, new_id)
            def finish(s):
                s.get("depots", {}).pop(old_id, None)
                if old_id in s.get("retiring_depots", []):
                    s["retiring_depots"].remove(old_id)
            update_fleet_upgrade(finish)
            self.log.print(f"[fleet_upgrade] Depot swap done: '{old_id}' -> '{new_id}'.")
            return f"{old_id} -> {new_id} done"

        return f"{old_id}: unknown state {state!r}"

    def _repin_homes(self, old_id, new_id):
        pins = archive.get(HOME_DEPOTS_KEY, {})
        if not isinstance(pins, dict) or old_id not in pins.values():
            return
        def updater(current):
            if not isinstance(current, dict):
                return {}
            return {k: (new_id if v == old_id else v) for k, v in current.items()}
        archive.transaction(HOME_DEPOTS_KEY, {}, updater)

    # ------------------------------------------------------------ drone swap

    def _advance_drone(self, old_id, entry, drones, computer, current_tick):
        state = entry.get("state")
        kind = entry.get("target_kind")
        self.log.debug(f"[fleet_upgrade] Drone '{old_id}': state '{state}'.")

        if state == "ordered":
            if old_id not in drones:
                self._drop("drones", old_id)
                return f"{old_id}: gone, swap dropped"
            if self._inventory_count(kind) <= 0:
                set_upgrade_order(REQUESTER, {kind: 1})
                return f"{old_id}: waiting for {kind}"
            set_upgrade_order(REQUESTER, {})
            self._patch("drones", old_id, state="requested")
            self.log.print(f"[fleet_upgrade] '{kind}' in Inventory; asking '{old_id}' to dock for the swap.")
            return f"{old_id}: requested"

        if state == "requested":
            status = fleet_status.get(old_id) or {}
            return f"{old_id}: waiting for drone ({status.get('state', 'no telemetry')})"

        if state == "ready":
            self._patch("drones", old_id, state="announced", announced_tick=current_tick)
            return f"{old_id}: announced"

        if state == "announced":
            waited = current_tick - int(entry.get("announced_tick") or current_tick)
            if waited < ANNOUNCE_SAVE_WAIT_TICKS:
                return f"{old_id}: waiting for autosave ({waited}/{ANNOUNCE_SAVE_WAIT_TICKS} ticks)"
            self._patch("drones", old_id, state="swapping", known=sorted(drones.keys()))
            return f"{old_id}: swapping"

        if state == "swapping":
            return self._swap_drone(old_id, entry, drones, computer)

        new_id = entry.get("new_id")
        if state == "attach":
            if fleet_status.get(new_id) is not None:
                self._patch("drones", old_id, state="fitting")
                return f"{old_id}: {new_id} running"
            started = self._start_script(new_id)
            if started != "ok":
                return f"{old_id}: waiting for a script on {new_id} (run scripts_sync or paste drone.py)"
            return f"{old_id}: started {new_id}"

        if state == "fitting":
            lineage = (fleet_upgrade_state().get("lineage") or {}).get(new_id) or {}
            if not lineage.get("fitted"):
                status = fleet_status.get(new_id) or {}
                return f"{old_id}: {new_id} fitting modules ({status.get('state', '?')})"
            # The old drone is undeployed by now, so its display name is free.
            old_name = entry.get("old_name")
            if old_name and old_name != old_id:
                res = computer.rename(new_id, old_name)
                if res.status != "ok":
                    self.log.debug(f"[fleet_upgrade] rename('{new_id}', '{old_name}'): {res.status}; keeping its own name.")
            self._drop("drones", old_id)
            self.log.print(f"[fleet_upgrade] Drone swap done: '{old_id}' -> '{new_id}' ({kind}).")
            return f"{old_id} -> {new_id} done"

        return f"{old_id}: unknown state {state!r}"

    def _swap_drone(self, old_id, entry, drones, computer):
        kind = entry.get("target_kind")
        outpost_id = entry.get("outpost")
        new_id = entry.get("new_id")

        if old_id in drones and not new_id:
            ref = drones[old_id]
            drone = _component(old_id)
            try:
                cargo = drone.cargo.count() if drone else 0
            except Exception:
                cargo = 0
            depot_ids = {d["id"] for d in self._depots()}
            if getattr(ref, "current_station", "") not in depot_ids or cargo:
                # Left the berth or picked something up: let it re-dock.
                self._patch("drones", old_id, state="requested")
                return f"{old_id}: not docked/empty any more, re-requested"
            self._stop_script(old_id)
            res = computer.undeploy(old_id)
            if res.status != "ok":
                attempts = int(entry.get("attempts", 0)) + 1
                if attempts >= MAX_UNDEPLOY_ATTEMPTS:
                    self._patch("drones", old_id, state="blocked", reason=res.status)
                    self._start_script(old_id)
                    self.log.level("warn").print(f"[fleet_upgrade] Drone '{old_id}': undeploy refused {attempts}x ({res.status}: {res.message}); swap blocked, drone back to work.")
                    return f"{old_id}: blocked ({res.status})"
                self._patch("drones", old_id, attempts=attempts)
                return f"{old_id}: undeploy {res.status}"
            self.log.print(f"[fleet_upgrade] Undeployed '{old_id}'; its modules are back in Inventory.")
            drones = self._drones()

        if not new_id:
            known = set(entry.get("known") or [])
            new_id = next((d_id for d_id, ref in drones.items() if d_id not in known and getattr(ref, "kind", "") == kind), None)
            if new_id is None:
                res = computer.deploy(kind, outpost_id)
                if res.status != "ok":
                    if res.status == "no_kit":
                        set_upgrade_order(REQUESTER, {kind: 1})
                    self.log.debug(f"[fleet_upgrade] deploy('{kind}', '{outpost_id}'): {res.status} - {res.message}")
                    return f"{old_id}: deploy {res.status}, retrying"
                new_id = res.machine_id
            set_upgrade_order(REQUESTER, {})

        lineage = {
            "from": old_id, "role": entry.get("role"), "engine": entry.get("engine"),
            "kind": kind, "params": entry.get("params") or {}, "fitted": False,
        }

        def mutate(s):
            s.setdefault("drones", {}).setdefault(old_id, {}).update({"state": "attach", "new_id": new_id})
            s.setdefault("lineage", {})[new_id] = lineage
        update_fleet_upgrade(mutate)
        self._migrate_drone_keys(old_id, new_id)
        self.log.print(f"[fleet_upgrade] Deployed '{new_id}' ({kind}) at '{outpost_id}' replacing '{old_id}'.")
        return f"{old_id}: deployed {new_id}"

    def _migrate_drone_keys(self, old_id, new_id):
        """Moves the old drone's home pin to the new id and drops its other per-drone entries."""
        pin = archive.get_entry(HOME_DEPOTS_KEY, old_id)
        if pin is not None:
            def repin(pins):
                if not isinstance(pins, dict):
                    pins = {}
                pins.pop(old_id, None)
                pins[new_id] = pin
                return pins
            archive.transaction(HOME_DEPOTS_KEY, {}, repin)
        for key in (DRONE_RECALL_KEY, MISSION_KEY, DRONE_LOADOUTS_KEY):
            if archive.get_entry(key, old_id) is not None:
                archive.pop_entry(key, old_id)
        fleet_status.forget(old_id)
        set_upgrade_order(old_id, {})

    # ------------------------------------------------------------ pruning

    def _prune(self, depots, drones):
        """Drops idle entries of machines that no longer exist. Skipped when discovery came back empty."""
        if not drones and not depots:
            return
        depot_ids = {d["id"] for d in depots}
        state = fleet_upgrade_state()
        stale_depots = [k for k, e in (state.get("depots") or {}).items()
                        if k not in depot_ids and isinstance(e, dict) and e.get("state") in ("ordered", "blocked")]
        stale_drones = [k for k, e in (state.get("drones") or {}).items()
                        if drones and k not in drones and isinstance(e, dict) and e.get("state") in ("ordered", "requested", "blocked")]
        stale_lineage = [k for k in (state.get("lineage") or {}) if drones and k not in drones]
        if stale_depots or stale_drones or stale_lineage:
            def mutate(s):
                for k in stale_depots:
                    s.get("depots", {}).pop(k, None)
                for k in stale_drones:
                    s.get("drones", {}).pop(k, None)
                for k in stale_lineage:
                    s.get("lineage", {}).pop(k, None)
            update_fleet_upgrade(mutate)
            self.log.debug(f"[fleet_upgrade] Pruned stale entries: depots={stale_depots}, drones={stale_drones}, lineage={stale_lineage}.")

        if drones:
            loadouts = archive.get(DRONE_LOADOUTS_KEY, {})
            gone = [k for k in (loadouts if isinstance(loadouts, dict) else {}) if k not in drones]
            for k in gone:
                archive.pop_entry(DRONE_LOADOUTS_KEY, k)
            orders = archive.get(UPGRADE_ORDERS_KEY, {})
            dead = [k for k in (orders if isinstance(orders, dict) else {})
                    if k != REQUESTER and k not in STANDING_ORDER_REQUESTERS and k not in drones]
            for k in dead:
                archive.pop_entry(UPGRADE_ORDERS_KEY, k)
