import logistics_requests
from archive import archive
from storage import take_item, discover_storage_buildings, warehouse_stock
from biomass_retire import biomass_complete
from drone_depot import buffer_target, lifeform_buffer_cap
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed

# Waste Processor automation: destroys surplus items at its own outpost.
# The processor only destroys while the script that armed it keeps running
# (docs/components/waste_processor.md), so this runs as the processor's own
# script and re-arms "items" mode every step. Its input only takes from
# same-outpost sources, so each outpost with surplus needs its own processor.
#
# Surplus streams:
#   - Life forms, once biomass is complete (lib/biomass_retire.py). A
#     Warehouse slot holds one material however few units it has, so each
#     form keeps what the Drone Depot stages anyway: lifeform_buffer_cap()
#     (LIFEFORM_BUFFER_SLOTS full slots, lib/drone_depot.py), or a larger
#     request retain_amount(). Destroyed: stored stock (Warehouses, home
#     Inventory) above that, plus Drone Depot stock that can't be staged
#     (stash full, or buffer_target() finds no slot) -- first, so drones
#     always have room to unload.

# Input buffer holds 200 mixed units; only take() once this much room is free.
FEED_MIN_ROOM_UNITS = 10

STATUS_KEY = "waste_sink.status"   # {processor_id: telemetry}


class WasteSinkController:
    """Arms a Waste Processor in items mode and feeds it surplus from local storage."""

    def __init__(self, processor):
        self.processor = processor
        self.name = getattr(processor, "id", "waste_processor")
        self.nocturna = get_component("nocturna")
        self.log = TreeConsole(module="waste_sink")
        self._destroyed = {}   # {item_id: units staged for destruction since start}

    def _outpost(self):
        return getattr(self.processor, "outpost", None)

    def _is_life_form(self, item_id):
        if not self.nocturna:
            return False
        try:
            return bool(self.nocturna.life_form_biome(item_id))
        except Exception as error:
            swallowed("waste_sink.WasteSinkController._is_life_form: self.nocturna.life_form_biome", error)
            return False

    def arm(self):
        """Items mode + enabled; both are idempotent."""
        try:
            if self.processor.mode() != "items":
                self.processor.set_mode("items")
                self.log.debug(f"[{self.name}] mode -> items.")
            if not self.processor.is_enabled():
                self.processor.set_enabled(True)
                self.log.print(f"[{self.name}] Armed (items mode).")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] arm failed: {e}")

    def _input_room(self):
        try:
            return self.processor.input.capacity() - self.processor.input.count()
        except Exception as error:
            swallowed("waste_sink.WasteSinkController._input_room: self.processor.input.capacity", error)
            return 0

    def life_form_surplus(self, depots):
        """[(item_id, {depot_id: units}, stored_units)] to destroy per life form here, largest first."""
        if not biomass_complete():
            return []
        outpost = self._outpost()
        outpost_id = getattr(outpost, "id", None)
        is_home = bool(getattr(outpost, "is_home", False))
        inventory = get_component("inventory") if is_home else None
        in_depots = {}
        for depot in depots:
            for item_id, units in logistics_requests.depot_stock(depot).items():
                if units > 0:
                    in_depots.setdefault(item_id, {})[depot.id] = units
        ids = set(in_depots)
        for building in discover_storage_buildings(outpost):
            try:
                ids.update(building["component"].materials())
            except Exception as error:
                swallowed("waste_sink.WasteSinkController.life_form_surplus: materials", error)
        requests = logistics_requests.active_requests()
        cap = lifeform_buffer_cap(outpost)
        out = []
        for item_id in ids:
            if not self._is_life_form(item_id):
                continue
            keep = max(cap, logistics_requests.retain_amount(item_id, outpost_id, requests))
            stored = warehouse_stock(item_id, outpost)
            if inventory is not None:
                try:
                    stored += inventory.count(item_id)
                except Exception as error:
                    swallowed("waste_sink.WasteSinkController.life_form_surplus: inventory.count", error)
            stored_surplus = max(0, stored - keep)
            depot_units = in_depots.get(item_id, {})
            stuck = bool(depot_units) and (stored >= keep or buffer_target(item_id, outpost)[0] is None)
            depot_surplus = depot_units if stuck else {}
            total = stored_surplus + sum(depot_surplus.values())
            if total > 0:
                out.append((item_id, depot_surplus, stored_surplus))
                self.log.debug(f"[{self.name}] '{item_id}': stored {stored}, keep {keep}, Depot {sum(depot_units.values())} ({'unstageable' if stuck else 'stageable'}) -> destroy {total}.")
        out.sort(key=lambda entry: -(entry[2] + sum(entry[1].values())))
        return out

    def _take_from_depot(self, depot_id, item_id, want):
        port = self.processor.input
        try:
            if port.connected_id() != depot_id:
                res = port.connect(depot_id)
                if getattr(res, "status", "") != "ok":
                    self.log.debug(f"[{self.name}] connect '{depot_id}': {getattr(res, 'status', '?')}")
                    return 0
            res = port.take(item_id, want, None, "any")
        except Exception as e:
            self.log.level("warn").print(f"[{self.name}] take('{item_id}', {want}) from '{depot_id}' failed: {e}")
            return 0
        return getattr(res, "moved", 0) or 0

    def feed(self):
        room = self._input_room()
        if room < FEED_MIN_ROOM_UNITS:
            self.log.trace(f"[{self.name}] input room {room} < {FEED_MIN_ROOM_UNITS}; waiting.")
            return
        depots = logistics_requests.local_depots(self._outpost())
        surplus = self.life_form_surplus(depots)
        if not surplus:
            return
        fed = 0
        self.log.start(f"[{self.name}] Feeding surplus ({len(surplus)} life form(s), room {room})")
        for item_id, depot_surplus, stored_surplus in surplus:
            if room < FEED_MIN_ROOM_UNITS:
                break
            moved = 0
            for depot_id, units in depot_surplus.items():
                want = min(room - moved, units)
                if want <= 0:
                    break
                moved += self._take_from_depot(depot_id, item_id, want)
            want = min(room - moved, stored_surplus)
            if want > 0:
                moved += take_item(self.processor.input, item_id, want, outpost=self._outpost())
            if moved > 0:
                room -= moved
                fed += moved
                self._destroyed[item_id] = self._destroyed.get(item_id, 0) + moved
                self.log.print(f"[{self.name}] Staged {moved}x surplus '{item_id}' for destruction.")
        self.log.end(f"[{self.name}] Staged {fed} unit(s) for destruction")

    def publish_telemetry(self):
        try:
            status = self.processor.status()
            rate = self.processor.item_throughput()
            staged = self.processor.input.count()
        except Exception as error:
            swallowed("waste_sink.WasteSinkController.publish_telemetry: self.processor.status", error)
            status, rate, staged = "unknown", 0.0, 0
        archive.set_entry(STATUS_KEY, self.name, {
            "status": status,
            "rate": rate,
            "staged": staged,
            "destroyed": dict(self._destroyed),
        })

    def step(self):
        self.arm()
        self.feed()
        self.publish_telemetry()

    def run(self, poll_interval=10.0):
        self.log.print(f"Waste Sink Controller ({self.name}) online at '{getattr(self._outpost(), 'id', '?')}'.")
        validate_game_version()
        while True:
            reset_all()
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Waste sink exception: {error}")
            flush_all()
            sleep(poll_interval)
