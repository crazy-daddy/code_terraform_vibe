# Shared Library for Drone Depot (cargo logistics endpoint) automation.
#
# Mostly passive: no active drain/rescue-style verb exists for a Depot --
# cargo moves via the drone's own cargo.load()/unload() while docked. Ports
# do NOT drain passively -- a declared link moves nothing until someone calls
# take()/send(); the Essence Liquifier's own controller does the take()
# (lib/essence_liquifier.py). This controller's job is (1) one-time
# idempotent port wiring to the outpost's Essence Liquifier, only when
# unambiguous, (2) buffering life forms in a local Warehouse (one stack per
# form) so the Depot stays free for drones, the Liquifier has a reserve and a
# pull hauler can take() them, (3) draining freight (every non-life-form
# item, e.g. ore a hauler drone dropped off -- lib/drone_hauler.py) into
# local storage, and (4) lightweight periodic telemetry.
#
# (3) is what makes a Depot usable as a hauler endpoint at all: its
# stockpile is tiny (50/100/200 units, 3/4/6 material slots) next to a Large
# hauler's up-to-2000-unit load, so the drone unloads in several rounds while
# this controller keeps draining (FREIGHT_POLL_INTERVAL while freight or a
# docked drone is present).

from archive import archive
from storage import discover_storage_buildings, warehouse_stock, drain_port_to_storage
import logistics_requests
from tree_console import TreeConsole
from version_guard import validate_game_version
from drone_upgrade import retiring_depot_ids

# One shared dict {depot_id: telemetry} (not one key per depot, CLAUDE.md
# rule 7). Old per-depot "drone_depot.status.<id>" keys are purged by
# ArchiveCleaner.clean_retired_keys().
DEPOT_STATUS_KEY = "drone_depot.status"
LIQUIFIER_TYPE_ID = "essence_liquifier"

# Depot -> Warehouse life-form buffer (stage_life_forms()): at most this many
# Warehouse stacks (slots) per life form per outpost, so samples can't crowd
# ore/cargo out of the Warehouse; and never open a new slot unless this many
# more stay empty in that Warehouse.
LIFEFORM_BUFFER_SLOTS = 1
WAREHOUSE_FREE_SLOTS_KEEP = 1
WAREHOUSE_SLOT_FALLBACK_UNITS = 2000  # docs/components/warehouse.md: 5 x 2,000

# Poll interval (s) while freight sits in the stockpile or a drone is docked,
# so a hauler unloading several Depot-fulls in a row isn't held up by the
# idle 10 s cycle.
FREIGHT_POLL_INTERVAL = 2.0


class DroneDepotController:
    """Automates a Drone Depot: idempotent output wiring + periodic telemetry publish."""

    def __init__(self, station):
        self.station = station
        self.name = getattr(station, "id", "drone_station")
        self._wired = False
        self._stage_state = None  # last logged staging state; debug line only on change
        self.nocturna = get_component("nocturna")
        self.log = TreeConsole(module="drone_depot")

    def _find_local_liquifier(self):
        """
        The single same-outpost Essence Liquifier, or None if there isn't
        exactly one -- wiring only when unambiguous (exactly one candidate)
        per the plan, never guessing between several.
        """
        outpost = getattr(self.station, "outpost", None)
        if not outpost or not hasattr(outpost, "buildings"):
            return None
        try:
            liquifiers = outpost.buildings(LIQUIFIER_TYPE_ID)
        except Exception:
            return None
        if len(liquifiers) != 1:
            if len(liquifiers) > 1:
                self.log.level("warn").print(f"[{self.name}] {len(liquifiers)} Essence Liquifiers found at this outpost; leaving output unwired for manual routing.")
            else:
                self.log.debug(f"[{self.name}] No Essence Liquifier found at this outpost; nothing to wire yet.")
            return None
        return get_component(liquifiers[0].id)

    def wire_output_to_liquifier(self):
        """
        One-time idempotent port wiring: connects this Depot's .output to
        the outpost's Essence Liquifier .input, ONLY when unambiguous
        (exactly one same-outpost Liquifier). Otherwise logs once and
        leaves it for manual wiring via the Control Panel.
        """
        if self._wired:
            return
        if not hasattr(self.station, "output"):
            self.log.debug(f"[{self.name}] Station has no .output port; skipping wiring check.")
            return
        liquifier = self._find_local_liquifier()
        if liquifier is None:
            return

        try:
            connected_to = self.station.output.connected_to() if hasattr(self.station.output, "connected_to") else None
            if connected_to == liquifier.id:
                self.log.debug(f"[{self.name}] Output already wired to '{liquifier.id}'; marking wired without reconnecting.")
                self._wired = True
                return
            self.log.debug(f"[{self.name}] Output not yet wired (currently connected_to={connected_to!r}); connecting to '{liquifier.id}'.")
            res = self.station.output.connect(liquifier.id)
            if getattr(res, "status", "") == "ok":
                self.log.print(f"[{self.name}] Wired output -> Essence Liquifier '{liquifier.id}'.")
                self._wired = True
            else:
                self.log.level("warn").print(f"[{self.name}] Output wiring to '{liquifier.id}' notice: {res.status} - {res.message}")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] Could not wire output to Essence Liquifier: {e}")

    def _slot_capacity(self, outpost):
        """Units per Warehouse slot at `outpost` (first slot seen), else WAREHOUSE_SLOT_FALLBACK_UNITS."""
        for building in discover_storage_buildings(outpost):
            try:
                for slot in building["component"].slots():
                    if slot.capacity:
                        return slot.capacity
            except Exception:
                continue
        return WAREHOUSE_SLOT_FALLBACK_UNITS

    def _buffer_target(self, item_id, outpost):
        """
        (warehouse_id, room) to stage item_id into, else (None, 0). A Warehouse
        whose slot already holds item_id wins (tops that one stack up); an
        empty slot is only taken while the Warehouse keeps
        WAREHOUSE_FREE_SLOTS_KEEP further empty slots for ore/cargo unloads.
        """
        fallback = (None, 0)
        for building in discover_storage_buildings(outpost):
            try:
                slots = list(building["component"].slots())
            except Exception:
                continue
            holding = [s for s in slots if s.item == item_id and not s.properties]
            if holding:
                room = sum(max(0, s.capacity - s.count) for s in holding)
                if room > 0:
                    return (building["id"], room)
                continue
            empty = [s for s in slots if not s.item or s.count <= 0]
            if fallback[0] is None and len(empty) > WAREHOUSE_FREE_SLOTS_KEEP:
                fallback = (building["id"], empty[0].capacity)
        return fallback

    def stage_life_forms(self):
        """
        Moves life-form samples from this Depot's stockpile into a local
        Warehouse, keeping at most LIFEFORM_BUFFER_SLOTS Warehouse stack(s)
        per form at this outpost. The Warehouse stash is the Liquifier's
        buffer (lib/essence_liquifier.py feed_from_warehouse()) and a pull
        hauler's take() source (lib/vehicle_cargo.py run_pull_loop()), and
        the Depot's small mixed stockpile stays free for drone unloads. Once
        a form's stack is full it stays in the Depot for the Liquifier.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "output", None)
        if not outpost or not port or not hasattr(port, "send"):
            self._log_stage_state("no_port", f"cannot stage (outpost={getattr(outpost, 'id', None)!r}, output port usable={bool(port and hasattr(port, 'send'))}).")
            return
        stock = logistics_requests.depot_stock(self.station)
        forms = {i: u for i, u in stock.items() if u > 0 and self._is_life_form(i)}
        if not forms:
            self._log_stage_state("empty", "no life forms in the Depot to stage.")
            return
        cap = self._slot_capacity(outpost) * LIFEFORM_BUFFER_SLOTS
        self._log_stage_state("active", f"staging life forms to Warehouse (cap {cap} per form): {forms}.")
        for item_id, units in forms.items():
            want = min(units, cap - warehouse_stock(item_id, outpost))
            if want <= 0:
                self.log.trace(f"[{self.name}] stage: '{item_id}' Warehouse buffer full (>= {cap}); leaving {units} in the Depot.")
                continue
            target, room = self._buffer_target(item_id, outpost)
            if target is None:
                self.log.debug(f"[{self.name}] stage: no Warehouse slot for '{item_id}' (would leave < {WAREHOUSE_FREE_SLOTS_KEEP} free slot(s)); leaving {units} in the Depot.")
                continue
            want = min(want, room)
            try:
                if port.connected_id() != target:
                    port.connect(target)
                res = port.send(item_id, want)
            except Exception as e:
                self.log.level("warn").print(f"[{self.name}] stage '{item_id}' -> '{target}' failed: {e}")
                continue
            moved = getattr(res, "moved", 0) or 0
            if moved > 0:
                self.log.print(f"[{self.name}] Staged {moved}x '{item_id}' -> '{target}' (buffer cap {cap}).")
                self._wired = False  # output now points at the Warehouse; re-declare the Liquifier link next step
            else:
                self.log.debug(f"[{self.name}] stage '{item_id}' -> '{target}': {getattr(res, 'status', '?')}")

    def drain_freight(self):
        """
        Sends every non-life-form stack in the Depot stockpile to local
        storage (Warehouse, or Inventory at home -- storage.best_unload_target()),
        trickling partial amounts into whatever room exists. Life forms are
        left to stage_life_forms()/the Liquifier. Returns units moved.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "output", None)
        if not outpost or not port:
            return 0
        moved = drain_port_to_storage(port, outpost=outpost, include=lambda i: not self._is_life_form(i), allow_partial=True)
        if moved > 0:
            self.log.print(f"[{self.name}] Drained {moved} unit(s) of freight to local storage.")
            self._wired = False  # output now points at storage; re-declare the Liquifier link next step
        return moved

    def has_freight_activity(self):
        """True while freight sits in the stockpile or any drone is docked (fast-poll trigger)."""
        try:
            if list(self.station.get_docked()):
                return True
        except Exception:
            pass
        stock = logistics_requests.depot_stock(self.station)
        return any(u > 0 and not self._is_life_form(i) for i, u in stock.items())

    def _is_life_form(self, item_id):
        if not self.nocturna:
            return False
        try:
            return bool(self.nocturna.life_form_biome(item_id))
        except Exception:
            return False

    def _log_stage_state(self, state, message):
        if state != self._stage_state:
            self._stage_state = state
            self.log.debug(f"[{self.name}] stage: {message}")

    def publish_telemetry(self):
        """
        Lightweight periodic telemetry publish (bay/slot occupancy) to
        archive, mirroring VehicleController.publish_telemetry()'s
        bounded/compact style -- useful for dashboards and for miner/scout
        drones' own "is my depot full" decisions.
        """
        self.log.trace(f"[{self.name}] publish_telemetry() entry.")
        try:
            docked = list(self.station.get_docked())
        except Exception:
            docked = []
        try:
            bay_count = self.station.bay_count()
            bays_occupied = self.station.bays_occupied()
        except Exception:
            bay_count = bays_occupied = 0
        try:
            slots_used = self.station.slots_used()
            slot_capacity = self.station.slot_capacity()
        except Exception:
            slots_used = slot_capacity = 0

        telemetry = {
            "name": self.name,
            "docked": docked,
            "bay_count": bay_count,
            "bays_occupied": bays_occupied,
            "slots_used": slots_used,
            "slot_capacity": slot_capacity,
            "is_full": slot_capacity > 0 and slots_used >= slot_capacity,
        }
        archive.set_entry(DEPOT_STATUS_KEY, self.name, telemetry)
        self.log.trace(f"[{self.name}] publish_telemetry() exit: bays {bays_occupied}/{bay_count}, slots {slots_used}/{slot_capacity}.")

    def drain_everything(self):
        """
        Retiring Depot (a fleet upgrade is replacing it, lib/fleet_upgrade.py):
        empties the whole stockpile, life forms included, into local storage.
        computer.undeploy() refuses a Depot with cargo_present, and a life
        form left for the Liquifier could otherwise pin it forever.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "output", None)
        if not outpost or not port:
            return 0
        moved = drain_port_to_storage(port, outpost=outpost, allow_partial=True)
        if moved > 0:
            self.log.print(f"[{self.name}] Retiring: drained {moved} unit(s) to local storage.")
        return moved

    def step(self):
        if self.name in retiring_depot_ids():
            self.drain_everything()
            self.publish_telemetry()
            return
        self.drain_freight()
        self.stage_life_forms()
        self.wire_output_to_liquifier()
        self.publish_telemetry()

    def run(self, poll_interval=10.0):
        bay_count = getattr(self.station, "bay_count", lambda: 1)()
        self.log.print(f"Drone Depot Controller ({self.name}) online ({bay_count} bay(s)).")
        validate_game_version()
        while True:
            interval = poll_interval
            try:
                self.step()
                if self.has_freight_activity():
                    interval = min(poll_interval, FREIGHT_POLL_INTERVAL)
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Error in supervision cycle: {e}")
            sleep(interval)
