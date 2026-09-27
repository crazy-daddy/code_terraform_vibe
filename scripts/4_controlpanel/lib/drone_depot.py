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
#
# Once biomass is complete (lib/biomass_retire.py) the Liquifier is gone, so
# no wiring. Staging is unchanged; what can't be staged waits in the Depot for
# a local Waste Processor (lib/waste_sink.py, which reuses buffer_target() and
# lifeform_buffer_cap() below) or a hauler drone. When the stockpile is full
# and a drone is waiting to unload, flush_surplus() discards life forms whose
# Warehouse stash is full and alone covers every request for them.
#
# (5) Hauler pickups (lib/drone_hauler.py): a hauler drone planning to load
# here writes a stage request (lib/depot_stage.py); fulfil_stage() take()s the
# items from local storage into the stockpile, and drain/staging leave staged
# items alone until the drone clears the request.

from archive import archive
from storage import discover_storage_buildings, warehouse_stock, drain_port_to_storage
import logistics_requests
from tree_console import TreeConsole
from swallow import swallowed
from version_guard import validate_game_version
from drone_upgrade import retiring_depot_ids
from biomass_retire import biomass_complete
from storage import take_item
import depot_stage
import fleet_status

# One shared dict {depot_id: telemetry} (not one key per depot, CLAUDE.md
# rule 7). Old per-depot "drone_depot.status.<id>" keys are purged by
# ArchiveCleaner.clean_retired_keys().
DEPOT_STATUS_KEY = "drone_depot.status"
LIQUIFIER_TYPE_ID = "essence_liquifier"

# Depot -> Warehouse life-form buffer (stage_life_forms()): at most this many
# Warehouse stacks (slots) per life form per outpost, so samples can't crowd
# ore/cargo out of the Warehouse; and never open a new slot unless this many
# more stay empty in that Warehouse.
LIFEFORM_BUFFER_SLOTS = 2
WAREHOUSE_FREE_SLOTS_KEEP = 1
WAREHOUSE_SLOT_FALLBACK_UNITS = 2000  # docs/components/warehouse.md: 5 x 2,000

# Poll interval (s) while freight sits in the stockpile or a drone is docked,
# so a hauler unloading several Depot-fulls in a row isn't held up by the
# idle 10 s cycle.
FREIGHT_POLL_INTERVAL = 2.0

# flush_surplus() only acts for a drone that reported WAITING_DEPOT_SPACE at
# this Depot within this many ticks (10 ticks/s -> 10 minutes), or one docked.
WAITING_DRONE_FRESH_TICKS = 6000


def slot_capacity(outpost):
    """Units per Warehouse slot at `outpost` (first slot seen), else WAREHOUSE_SLOT_FALLBACK_UNITS."""
    for building in discover_storage_buildings(outpost):
        try:
            for slot in building["component"].slots():
                if slot.capacity:
                    return slot.capacity
        except Exception as error:
            swallowed("drone_depot.slot_capacity: building['component'].slots", error)
            continue
    return WAREHOUSE_SLOT_FALLBACK_UNITS


def buffer_target(item_id, outpost):
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
        except Exception as error:
            swallowed("drone_depot.buffer_target: building['component'].slots", error)
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


def lifeform_buffer_cap(outpost):
    """Units of one life form kept in `outpost`'s Warehouses: LIFEFORM_BUFFER_SLOTS full slots."""
    return slot_capacity(outpost) * LIFEFORM_BUFFER_SLOTS


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
        except Exception as error:
            swallowed("drone_depot.DroneDepotController._find_local_liquifier: outpost.buildings", error)
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
        if self._wired or biomass_complete():
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


    def stage_life_forms(self):
        """
        Moves life-form samples from this Depot's stockpile into a local
        Warehouse, keeping at most LIFEFORM_BUFFER_SLOTS Warehouse stack(s)
        per form at this outpost. The Warehouse stash is the Liquifier's
        buffer (lib/essence_liquifier.py feed_from_warehouse()) and a pull
        hauler's take() source (lib/vehicle_cargo.py run_pull_loop()), and
        the Depot's small mixed stockpile stays free for drone unloads. Once
        a form's stack is full it stays in the Depot for the Liquifier, or,
        after biomass completion, for the Waste Processor.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "output", None)
        if not outpost or not port or not hasattr(port, "send"):
            self._log_stage_state("no_port", f"cannot stage (outpost={getattr(outpost, 'id', None)!r}, output port usable={bool(port and hasattr(port, 'send'))}).")
            return
        stock = logistics_requests.depot_stock(self.station)
        staged = depot_stage.staged_items(self.name)
        forms = {i: u for i, u in stock.items() if u > 0 and self._is_life_form(i) and i not in staged}
        if not forms:
            self._log_stage_state("empty", "no unstaged life forms in the Depot to stage.")
            return
        cap = lifeform_buffer_cap(outpost)
        self._log_stage_state("active", f"staging life forms to Warehouse (cap {cap} per form): {forms}.")
        for item_id, units in forms.items():
            want = min(units, cap - warehouse_stock(item_id, outpost))
            if want <= 0:
                self.log.trace(f"[{self.name}] stage: '{item_id}' Warehouse buffer full (>= {cap}); leaving {units} in the Depot.")
                continue
            target, room = buffer_target(item_id, outpost)
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
        left to stage_life_forms()/the Liquifier, items staged for a hauler
        (lib/depot_stage.py) stay put. Returns units moved.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "output", None)
        if not outpost or not port:
            return 0
        staged = depot_stage.staged_items(self.name)
        moved = drain_port_to_storage(port, outpost=outpost, include=lambda i: not self._is_life_form(i) and i not in staged, allow_partial=True)
        if moved > 0:
            self.log.print(f"[{self.name}] Drained {moved} unit(s) of freight to local storage.")
            self._wired = False  # output now points at storage; re-declare the Liquifier link next step
        return moved

    def has_freight_activity(self):
        """True while freight sits in the stockpile, a stage request is open or any drone is docked (fast-poll trigger)."""
        try:
            if list(self.station.get_docked()):
                return True
        except Exception as error:
            swallowed("drone_depot.DroneDepotController.has_freight_activity: self.station.get_docked", error)
        if depot_stage.staged_for(self.name):
            return True
        stock = logistics_requests.depot_stock(self.station)
        return any(u > 0 and not self._is_life_form(i) for i, u in stock.items())

    def _is_life_form(self, item_id):
        if not self.nocturna:
            return False
        try:
            return bool(self.nocturna.life_form_biome(item_id))
        except Exception as error:
            swallowed("drone_depot.DroneDepotController._is_life_form: self.nocturna.life_form_biome", error)
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
        except Exception as error:
            swallowed("drone_depot.DroneDepotController.publish_telemetry: self.station.get_docked", error)
            docked = []
        try:
            bay_count = self.station.bay_count()
            bays_occupied = self.station.bays_occupied()
        except Exception as error:
            swallowed("drone_depot.DroneDepotController.publish_telemetry: self.station.bay_count", error)
            bay_count = bays_occupied = 0
        try:
            slots_used = self.station.slots_used()
            slot_capacity = self.station.slot_capacity()
        except Exception as error:
            swallowed("drone_depot.DroneDepotController.publish_telemetry: self.station.slots_used", error)
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

    # ------------------------------------------------------------ hauler staging / surplus

    def _stockpile_room(self, stock):
        """(free units, free material slots) in the stockpile; unreadable -> (0, 0)."""
        try:
            units = self.station.input.capacity() - sum(stock.values())
            slots = self.station.slot_capacity() - self.station.slots_used()
        except Exception as error:
            swallowed("drone_depot.DroneDepotController._stockpile_room: self.station.input.capacity", error)
            return 0, 0
        return max(0, units), max(0, slots)

    def fulfil_stage(self):
        """
        Pulls items a hauler drone asked for (lib/depot_stage.py) out of local
        storage (Warehouses, Inventory at home) into the stockpile, up to the
        requested units minus what is already there, within free units and
        material slots. A new material with no slot free first gets the
        stockpile drained/staged/flushed, then one retry. Returns units moved.
        """
        wanted = depot_stage.staged_for(self.name)
        if not wanted:
            return 0
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "input", None)
        if not outpost or not port:
            return 0
        moved_total = 0
        for item_id, units in wanted.items():
            stock = logistics_requests.depot_stock(self.station)
            missing = units - stock.get(item_id, 0)
            if missing <= 0:
                self.log.trace(f"[{self.name}] stage for hauler: {item_id} ready ({stock.get(item_id, 0)} >= {units}).")
                continue
            room, slots = self._stockpile_room(stock)
            if item_id not in stock and slots <= 0:
                self.log.debug(f"[{self.name}] stage for hauler: no free material slot for {item_id}; draining the stockpile first.")
                self.drain_freight()
                self.stage_life_forms()
                self.flush_surplus(for_stage=True)
                stock = logistics_requests.depot_stock(self.station)
                room, slots = self._stockpile_room(stock)
                if item_id not in stock and slots <= 0:
                    self.log.debug(f"[{self.name}] stage for hauler: still no free slot for {item_id} (stockpile {stock}); retrying next cycle.")
                    continue
            amount = min(missing, room)
            if amount <= 0:
                self.log.debug(f"[{self.name}] stage for hauler: stockpile full ({stock}); {missing}x {item_id} waits for the drone to load.")
                continue
            report = {}
            moved = take_item(port, item_id, amount, outpost=outpost, report=report)
            moved_total += moved
            if moved > 0:
                self.log.print(f"[{self.name}] Staged {moved}x {item_id} for a hauler drone ({stock.get(item_id, 0) + moved}/{units}).")
            else:
                self.log.debug(f"[{self.name}] stage for hauler: {item_id} x{amount} not available locally ({report.get('sources')}).")
        return moved_total

    def _drone_waiting(self):
        """True when a drone is docked here or reported WAITING_DEPOT_SPACE for this Depot recently."""
        try:
            if list(self.station.get_docked()):
                return True
        except Exception as error:
            swallowed("drone_depot.DroneDepotController._drone_waiting: self.station.get_docked", error)
        tick = logistics_requests._now_tick()
        for entry in fleet_status.get_all().values():
            if not isinstance(entry, dict):
                continue
            if entry.get("state") == "WAITING_DEPOT_SPACE" and entry.get("target") == self.name and tick - (entry.get("tick", 0) or 0) < WAITING_DRONE_FRESH_TICKS:
                return True
        return False

    def flush_surplus(self, for_stage=False):
        """
        Discards surplus life forms when the stockpile is full (units or
        material slots) and a drone needs the room (one docked or waiting to
        unload here, or a hauler stage request with for_stage). A form is
        surplus when nobody staged it, its local Warehouse stash is at
        lifeform_buffer_cap(), and that stash alone covers retain_amount() plus
        the network-wide deficit for it. InputSlot.flush() discards the whole
        stockpile, so everything else is drained first and the flush only
        runs when nothing but surplus is left. Returns units destroyed.
        """
        outpost = getattr(self.station, "outpost", None)
        port = getattr(self.station, "input", None)
        if not outpost or not port or not hasattr(port, "flush"):
            return 0
        stock = logistics_requests.depot_stock(self.station)
        if not stock:
            return 0
        room, slots = self._stockpile_room(stock)
        if room > 0 and slots > 0:
            return 0
        if not for_stage and not self._drone_waiting():
            self.log.trace(f"[{self.name}] flush: stockpile full but no drone waiting; keeping {stock}.")
            return 0
        staged = depot_stage.staged_items(self.name)
        requests = logistics_requests.active_requests()
        deficits = logistics_requests.network_deficits()
        cap = lifeform_buffer_cap(outpost)
        outpost_id = getattr(outpost, "id", None)
        surplus = {}
        for item_id, units in stock.items():
            if item_id in staged or not self._is_life_form(item_id):
                continue
            stash = warehouse_stock(item_id, outpost)
            needed = logistics_requests.retain_amount(item_id, outpost_id, requests) + deficits.get(item_id, 0)
            if stash >= cap and stash >= needed:
                surplus[item_id] = units
            else:
                self.log.debug(f"[{self.name}] flush: keep {item_id} (stash {stash}/{cap}, requests need {needed}).")
        if not surplus:
            self.log.debug(f"[{self.name}] flush: stockpile full ({stock}) but nothing is surplus.")
            return 0
        port_out = getattr(self.station, "output", None)
        if port_out:
            drain_port_to_storage(port_out, outpost=outpost, include=lambda i: i not in surplus and i not in staged, allow_partial=True)
            self._wired = False
        left = logistics_requests.depot_stock(self.station)
        blockers = {i: u for i, u in left.items() if i not in surplus and u > 0}
        if blockers:
            self.log.level("warn").print(f"[{self.name}] Surplus {surplus} can't be flushed: {blockers} still in the stockpile (no local room or staged for a hauler).")
            return 0
        try:
            res = port.flush()
        except Exception as e:
            self.log.level("warn").print(f"[{self.name}] flush() failed: {e}")
            return 0
        status = getattr(res, "status", "ok")
        if status not in ("ok", None):
            self.log.level("warn").print(f"[{self.name}] flush() notice: {status} - {getattr(res, 'message', '')}")
            return 0
        destroyed = sum(left.values())
        self.log.print(f"[{self.name}] Flushed surplus life forms {left} ({destroyed} unit(s)): Warehouse stash full and covers every request.")
        return destroyed

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
        self.fulfil_stage()
        self.drain_freight()
        self.stage_life_forms()
        self.flush_surplus()
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
