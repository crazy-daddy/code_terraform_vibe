from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole
from storage import take_item
import fluid_routing
import logistics_requests
from production import FLUID_SOURCE_TYPE_IDS, fluid_building_is_viable

# Plant Terraformer: the only machine that turns harvested Forage into
# permanent Plants km² (docs/components/plant_terraformer.md,
# docs/guide/plant_terraformer_guide.md). The machine does the conversion on
# its own once enabled; this controller only keeps it fed and decides when
# it's worth running.
#
# Facts it relies on:
#   - The input holders fit ONE full batch (Mk I 1,200 Forage, Mk II 6,600)
#     plus that batch's Salt and up to 10 of each Fertilizer tier and Growth
#     Accelerant. There is no separate intake buffer.
#   - Everything is consumed when a cycle starts, so the holders are empty
#     again while the 3 h cycle runs -- the next batch is preloaded then.
#   - A cycle takes 3 h no matter how many Forage it holds, and the machine
#     draws power (Mk I 180 W) the whole time it is enabled. The km² per
#     Forage is fixed per phase, so a small batch loses no km², only power.
#     Forage supply (one field) is far below the machine's 400 Forage/h, so
#     the machine is never the bottleneck: it waits for MIN_START_FORAGE
#     before starting, and is disabled while it has nothing to do. An enabled
#     machine starts the next batch the moment one ends, so while a batch
#     runs, Forage is only preloaded once enough is in stock to reach
#     MIN_START_FORAGE -- otherwise a trickle would become a 3 h mini-batch.
#   - Blocked on Water/Salt/etc. with Forage onboard, the machine stays
#     enabled: disabled, status() reads "disabled" and hides what's missing.
#   - Stopping the script resets enabled to False and pauses an in-flight
#     batch in place. On restart the batch is found again from get_progress()
#     or the last published state, and the machine is re-enabled.
#
# Material ladder (cumulative, required_inputs()): forage -> + water
# (500k km²) -> + salt (1.25M) -> + fertilizer potency, Mk II (2.25M) ->
# + growth_accelerant (3.5M). Water comes through water_in (one
# FluidInputRouter, same as the Fabricator's), items through
# storage.take_item() from Inventory (home) and local Warehouses.
#
# Demand advertisement (lib/logistics_requests.py, requester
# "plant_terraformer"): every material the phase needs is published as a
# LOCAL STOCK target -- the next batch staged in this outpost's Warehouses /
# Drone Depots, on top of what sits in the holders. That's the shape every
# hauler already reads: the Pioneer pull hauler and the floating drone
# hauler plan from outpost_deficits() (target - Warehouses - Depots -
# in-flight pickups), miner drones from network_deficits(). Drone freight
# lands in the Depot; drone_depot.py drains non-life-form items into a
# Warehouse, and the loader also takes straight from a local Depot.
#   - Forage: one full batch, only away from home -- the field's Harvester
#     delivers to home Inventory, so home is a SOURCE of Forage, not a sink.
#   - Salt / Growth Accelerant: SUPPORT_REQUEST_BATCHES batches' worth.
#   - Fertilizer: requested as Mk I (`fertilizer`), counted in Mk I potency
#     equivalents across all tiers.
#   logistics.requests holds one entry per item per outpost; an item another
#   requester (e.g. the field Harvester's salt) already owns here is left
#   alone -- its target keeps the outpost stocked, and the Terraformer draws
#   from the same stock.
# Source side: an item this outpost doesn't request itself (home Forage) is
# only consumed above what other outposts request (remote_retain()), so a
# home Terraformer can't eat the batch a hauler is coming for. Nothing here
# makes the Fabricator craft Fertilizer/Accelerant yet (TODO.md).

STATUS_KEY = "plant.terraformer"
REQUESTER_ID = "plant_terraformer"

# 10 ticks/s -> 1 h. Entries of Terraformers that stopped publishing are
# pruned by the next publish (one shared dict, CLAUDE.md rule 7).
STATUS_STALE_TICKS = 36000

# A cycle is 3 game-hours; loading a full Mk I batch takes ~19 s (Fast
# Feeders: ~9 s). Polling every 10 s loses nothing.
POLL_INTERVAL_S = 10.0

# Onboard Forage needed before an idle machine is enabled (or the full
# batch_requirements() amount, when that is smaller -- e.g. right before a
# phase threshold). Keeps the 3 h cycle's power cost from being spent on a
# handful of Forage.
MIN_START_FORAGE = 100

# Salt / Growth Accelerant / each Fertilizer tier: onboard holder cap.
SUPPORT_HOLDER_CAP = 10

# Fertilizer item ids, best potency first (fertilizer_potency(): 50/30/10).
FERTILIZER_ITEM_IDS = ("fertilizer_mk3", "fertilizer_mk2", "fertilizer")

# Salt / Growth Accelerant / Fertilizer staged at the outpost, in batches'
# worth (Mk I full batch: 3 Salt; Mk II: 14 Salt, 27 potency, 1
# Accelerant; per-batch amounts capped by the holder), so one batch is on
# hand while a hauler brings the next.
SUPPORT_REQUEST_BATCHES = 2

# Requests are republished at least this often (well inside
# logistics_requests.REQUEST_STALE_TICKS = 3000) and at once when a target
# changes; 10 ticks/s -> 1 min.
REQUEST_REFRESH_TICKS = 600

# Water input routing, same values as the Fabricator's water_in router
# (lib/fabricator.py).
FLUID_STALL_STREAK_BLACKLIST_THRESHOLD = 5
FLUID_RESCAN_INTERVAL_TICKS = 150
FLUID_DISCOVERY_CACHE_INTERVAL_TICKS = 100
FLUID_NEUTRAL_GRACE_STEPS = 5

# Statuses where the machine can't use power at all: switched off.
STOP_STATUSES = ("complete", "needs_mk2")


class PlantTerraformerController:
    """Keeps one Plant Terraformer fed with Forage, Water and support items and runs it in full-ish batches."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "plant_terraformer")
        self.outpost = getattr(machine, "outpost", None)
        self.outpost_id = getattr(self.outpost, "id", None)
        self.is_home = bool(getattr(self.outpost, "is_home", False))
        self.clock = get_component("clock")
        self.log = TreeConsole(module="plant_terraformer")
        self._last_status = None
        self._last_phase = None
        self._water_router = None
        self._published_targets = None
        self._published_tick = None
        self._resume_pending = self._was_running()

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    # ------------------------------------------------------------ readings

    def _call(self, method, default):
        fn = getattr(self.machine, method, None)
        if fn is None:
            return default
        try:
            value = fn()
        except Exception as error:
            self.log.debug(f"[{self.name}] {method}() failed: {error}")
            return default
        return default if value is None else value

    def onboard(self):
        """{item_id: units} currently in the input holders."""
        held = {}
        port = getattr(self.machine, "input", None)
        if port and hasattr(port, "stacks"):
            try:
                for stack in port.stacks():
                    held[stack.id] = held.get(stack.id, 0) + stack.count
            except Exception as error:
                self.log.debug(f"[{self.name}] input stacks read failed: {error}")
        return held

    def _was_running(self):
        """Last published state said a batch was in flight (script restart recovery)."""
        status = archive.get(STATUS_KEY, {})
        if not isinstance(status, dict):
            return False
        entry = status.get(self.name) or {}
        return bool(entry.get("in_flight")) if isinstance(entry, dict) else False

    # ------------------------------------------------------------- feeding

    def local_stock(self, item_id):
        """Units at this outpost a local InputSlot can take(): Warehouses + Drone Depots (+ Inventory at home) + Crop Automators (for forage)."""
        stock = logistics_requests.outpost_stock([item_id], self.outpost).get(item_id, 0)
        if item_id == "forage" and self.is_home:
            stock += self.crop_automator_forage_stock()
        return stock

    def crop_automator_forage_stock(self):
        """Total forage currently in output ports of local Crop Automators."""
        if not self.outpost or not hasattr(self.outpost, "harvesting_machines"):
            return 0
        total = 0
        try:
            for m in self.outpost.harvesting_machines():
                if getattr(m, "type_id", None) == "crop_automator":
                    ca = get_component(getattr(m, "id", None)) or m
                    port = getattr(ca, "output", None)
                    if port and hasattr(port, "count"):
                        total += int(port.count("forage") or 0)
        except Exception:
            pass
        return total

    def remote_retain(self, item_id, requests):
        """
        Units of item_id to leave for OTHER outposts' requests -- only when
        this outpost is a source of it (doesn't request it itself). A sink
        never holds back, else two requesting outposts would each guard the
        other's target and neither would ever consume.
        """
        if not self.outpost_id or item_id in requests.get(self.outpost_id, {}):
            return 0
        retain = 0
        for o_id, items in requests.items():
            if o_id == self.outpost_id or not isinstance(items, dict):
                continue
            entry = items.get(item_id) or {}
            if isinstance(entry, dict):
                retain = max(retain, int(entry.get("target", 0) or 0))
        return retain

    def available(self, item_id, requests):
        return max(self.local_stock(item_id) - self.remote_retain(item_id, requests), 0)

    def _take(self, item_id, amount, requests):
        """
        Pulls up to `amount` into the holders:
        For remote outposts: Drone Depots first, then local Warehouses.
        For home outpost: Warehouses/Inventory first (to drain existing forage),
        then directly from Crop Automators, then Drone Depots.
        """
        amount = min(amount, self.available(item_id, requests))
        if amount <= 0:
            return 0
        port = getattr(self.machine, "input", None)
        if not port:
            return 0

        moved_total = 0
        # Remote outposts: prefer local Drone Depot directly (brought by drones/pioneers)
        if not self.is_home:
            moved_total += self._take_from_depots(port, item_id, amount)
            if moved_total >= amount:
                return moved_total

        # Next / Home primary: Warehouses and Inventory (drains remaining warehouse forage)
        report = {}
        moved = take_item(port, item_id, amount - moved_total, outpost=self.outpost, report=report)
        self.log.debug(f"[{self.name}] take {item_id} x{amount - moved_total}: moved {moved}, sources {report.get('sources')}.")
        moved_total += moved

        # For forage at home: if warehouses empty, pull directly from Crop Automators!
        if moved_total < amount and item_id == "forage" and self.is_home:
            moved_total += self._take_from_crop_automators(port, amount - moved_total)

        # Home fallback: Drone Depots
        if moved_total < amount and self.is_home:
            moved_total += self._take_from_depots(port, item_id, amount - moved_total)

        return moved_total

    def _take_from_crop_automators(self, port, amount):
        """Pulls forage directly from Crop Automator output buffers."""
        if not self.outpost or not hasattr(self.outpost, "harvesting_machines") or amount <= 0:
            return 0
        moved_total = 0
        try:
            automators = [m for m in self.outpost.harvesting_machines() if getattr(m, "type_id", None) == "crop_automator"]
        except Exception:
            automators = []

        for m in automators:
            if moved_total >= amount:
                break
            ca_id = getattr(m, "id", None)
            if not ca_id:
                continue
            ca = get_component(ca_id) or m
            out_port = getattr(ca, "output", None)
            if not out_port or not hasattr(out_port, "count"):
                continue
            try:
                available = int(out_port.count("forage") or 0)
            except Exception:
                available = 0
            if available <= 0:
                continue
            want = min(amount - moved_total, available)
            try:
                if hasattr(port, "connected_id") and port.connected_id() != ca_id:
                    port.connect(ca_id)
                res = port.take("forage", want)
            except Exception as error:
                self.log.debug(f"[{self.name}] take forage from Crop Automator '{ca_id}' raised: {error}")
                continue
            moved = getattr(res, "moved", 0) or 0
            self.log.debug(f"[{self.name}] take forage x{want} from Crop Automator '{ca_id}': {getattr(res, 'status', None)}, moved {moved}.")
            moved_total += moved
        return moved_total

    def _take_from_depots(self, port, item_id, amount):
        moved_total = 0
        for depot in logistics_requests.local_depots(self.outpost):
            if moved_total >= amount:
                break
            want = min(amount - moved_total, logistics_requests.depot_stock(depot).get(item_id, 0))
            if want <= 0:
                continue
            try:
                if port.connected_id() != depot.id:
                    port.connect(depot.id)
                res = port.take(item_id, want)
            except Exception as error:
                self.log.debug(f"[{self.name}] take {item_id} from depot '{depot.id}' raised: {error}")
                continue
            moved = getattr(res, "moved", 0) or 0
            self.log.debug(f"[{self.name}] take {item_id} x{want} from depot '{depot.id}': {getattr(res, 'status', None)}, moved {moved}.")
            moved_total += moved
        return moved_total

    def start_threshold(self, full_batch):
        """Onboard Forage an idle machine waits for before it is enabled."""
        return max(min(MIN_START_FORAGE, full_batch) if full_batch > 0 else MIN_START_FORAGE, 1)

    def load_forage(self, wanted, held, in_flight, requests):
        """Top the holders up to `wanted` Forage. Returns units moved."""
        onboard = held.get("forage", 0)
        missing = wanted - onboard
        if missing <= 0:
            return 0
        if in_flight:
            start_at = self.start_threshold(wanted)
            available = self.available("forage", requests)
            if onboard + available < start_at:
                self.log.debug(f"[{self.name}] batch running; not preloading {available} Forage (next batch starts at {start_at}).")
                return 0
        return self._take("forage", missing, requests)

    def load_salt(self, need, held, requests):
        want = min(need, SUPPORT_HOLDER_CAP)
        return self._take("salt", want - held.get("salt", 0), requests)

    def load_accelerant(self, need, held, requests):
        want = min(need, SUPPORT_HOLDER_CAP)
        return self._take("growth_accelerant", want - held.get("growth_accelerant", 0), requests)

    def _potency(self, item_id):
        try:
            return int(self.machine.fertilizer_potency(item_id))
        except Exception:
            return {"fertilizer_mk3": 50, "fertilizer_mk2": 30, "fertilizer": 10}.get(item_id, 0)

    def load_fertilizer(self, need_potency, held, requests):
        """
        Loads Fertilizer until the unopened items onboard cover `need_potency`,
        best tier first. Potency already opened inside the machine isn't
        readable, so this can load one item more than needed; the surplus
        stays for the next batch.
        """
        have = sum(held.get(i, 0) * self._potency(i) for i in FERTILIZER_ITEM_IDS)
        moved_total = 0
        for item_id in FERTILIZER_ITEM_IDS:
            if have >= need_potency:
                break
            potency = self._potency(item_id)
            if potency <= 0:
                continue
            room = SUPPORT_HOLDER_CAP - held.get(item_id, 0)
            count = min(room, -(-(need_potency - have) // potency))
            moved = self._take(item_id, count, requests)
            have += moved * potency
            moved_total += moved
        if have < need_potency:
            self.log.debug(f"[{self.name}] fertilizer potency {have}/{need_potency} after loading; short.")
        return moved_total

    def feed(self, reqs, required, in_flight, requests):
        """Loads every material the current recipe needs. Returns {item_id: moved}."""
        moved = {}
        held = self.onboard()
        forage = int(reqs.get("forage", 0) or 0)
        if forage > 0:
            moved["forage"] = self.load_forage(forage, held, in_flight, requests)
        if "salt" in required and reqs.get("salt"):
            moved["salt"] = self.load_salt(int(reqs["salt"]), held, requests)
        if reqs.get("fertilizer_potency"):
            moved["fertilizer"] = self.load_fertilizer(int(reqs["fertilizer_potency"]), held, requests)
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            moved["growth_accelerant"] = self.load_accelerant(int(reqs["growth_accelerant"]), held, requests)
        return {k: v for k, v in moved.items() if v}

    # --------------------------------------------------------------- water

    def _discover_water_sources(self):
        type_ids = FLUID_SOURCE_TYPE_IDS["water_in"]
        pairs = []
        network = get_component("outpost_network")
        if network and hasattr(network, "outposts"):
            try:
                for outpost in network.outposts():
                    o_id = getattr(outpost, "id", None)
                    for type_id in type_ids:
                        for building in outpost.buildings(type_id):
                            b_id = getattr(building, "id", None)
                            if b_id and fluid_building_is_viable("water_in", type_id, building):
                                pairs.append((b_id, o_id))
            except Exception as error:
                self.log.debug(f"[{self.name}] water source discovery failed: {error}")
        ids = fluid_routing.rank_own_outpost_first(pairs, self.outpost_id)
        self.log.debug(f"[{self.name}] water_in: sources (own outpost first): {ids}.")
        return ids

    @staticmethod
    def _port_starved(port):
        """flow_rate() == 0 with room left -- a full port also reads 0, not a stall."""
        try:
            level = port.level() if hasattr(port, "level") else 0
            capacity = port.capacity() if hasattr(port, "capacity") else 0
            flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
            return flow == 0 and (not capacity or level < capacity)
        except Exception:
            return False

    def ensure_water(self, curr_tick):
        port = getattr(self.machine, "water_in", None)
        if not port:
            return
        if self._water_router is None:
            self._water_router = fluid_routing.FluidInputRouter(
                discover=self._discover_water_sources,
                rescan_interval_ticks=FLUID_RESCAN_INTERVAL_TICKS,
                discovery_cache_interval_ticks=FLUID_DISCOVERY_CACHE_INTERVAL_TICKS,
                stall_streak_threshold=FLUID_STALL_STREAK_BLACKLIST_THRESHOLD,
                neutral_grace_steps=FLUID_NEUTRAL_GRACE_STEPS,
                label=f"{self.name}.water_in",
            )

        def on_dropped(source_id, reason):
            self.log.level("warn").print(f"[{self.name}] Dropping water source '{source_id}': {reason}. Picking another.")

        def on_connect_notice(source_id, status, message):
            self.log.level("warn").print(f"[{self.name}] water_in connect notice for '{source_id}': {status} - {message}")

        event = self._water_router.ensure(port, curr_tick, self._port_starved(port), on_dropped, on_connect_notice)
        if event.kind == "connected":
            self.log.print(f"[{self.name}] Connected water_in -> '{event.source_id}'.")
        elif event.kind == "not_found":
            self.log.debug(f"[{self.name}] no water source on the network.")

    # ------------------------------------------------------------ requests

    def demand_targets(self, reqs, required):
        """{item_id: local stock target} for the next batch(es), before ownership checks."""
        targets = {}
        if not self.is_home and reqs.get("forage"):
            targets["forage"] = int(reqs["forage"])
        if "salt" in required and reqs.get("salt"):
            targets["salt"] = min(int(reqs["salt"]), SUPPORT_HOLDER_CAP) * SUPPORT_REQUEST_BATCHES
        if reqs.get("fertilizer_potency"):
            per_batch = -(-int(reqs["fertilizer_potency"]) // max(self._potency("fertilizer"), 1))
            targets["fertilizer"] = min(per_batch, SUPPORT_HOLDER_CAP) * SUPPORT_REQUEST_BATCHES
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            targets["growth_accelerant"] = min(int(reqs["growth_accelerant"]), SUPPORT_HOLDER_CAP) * SUPPORT_REQUEST_BATCHES
        return targets

    def _have(self, item_id):
        """Published "have": local stock; Fertilizer in Mk I potency equivalents over all tiers."""
        if item_id != "fertilizer":
            return self.local_stock(item_id)
        unit = max(self._potency("fertilizer"), 1)
        return sum(self.local_stock(i) * self._potency(i) for i in FERTILIZER_ITEM_IDS) // unit

    def publish_requests(self, reqs, required, requests, curr_tick):
        """Advertises this Terraformer's demand in logistics.requests (see module header)."""
        if not self.outpost_id:
            return
        here = requests.get(self.outpost_id) or {}
        targets = {}
        for item_id, target in self.demand_targets(reqs, required).items():
            entry = here.get(item_id) or {}
            owner = entry.get("by") if isinstance(entry, dict) else None
            if owner in (None, REQUESTER_ID):
                targets[item_id] = target
            else:
                self.log.debug(f"[{self.name}] {item_id} already requested here by '{owner}'; not overriding.")

        due = (
            targets != self._published_targets
            or self._published_tick is None
            or curr_tick < self._published_tick
            or curr_tick - self._published_tick >= REQUEST_REFRESH_TICKS
        )
        if not due:
            return
        wants = {item_id: (target, self._have(item_id)) for item_id, target in targets.items()}
        logistics_requests.set_requests(self.outpost_id, REQUESTER_ID, wants, curr_tick)
        if targets != self._published_targets:
            if targets:
                self.log.print(f"[{self.name}] Advertising demand at {self.outpost_id}: {wants}.")
            elif self._published_targets:
                self.log.print(f"[{self.name}] Demand withdrawn at {self.outpost_id}.")
        self._published_targets = targets
        self._published_tick = curr_tick

    # ------------------------------------------------------------- control

    def set_enabled(self, enabled, reason):
        if bool(self._call("is_enabled", False)) == enabled:
            return
        try:
            self.machine.set_enabled(enabled)
        except Exception as error:
            self.log.level("warn").print(f"[{self.name}] set_enabled({enabled}) failed: {error}")
            return
        self.log.debug(f"[{self.name}] {'enabled' if enabled else 'disabled'}: {reason}.")

    def decide(self, status, in_flight, onboard_forage, full_batch):
        """(enable, reason) for this step."""
        if status in STOP_STATUSES:
            return False, status
        if in_flight:
            return True, "batch in flight"
        start_at = self.start_threshold(full_batch)
        if onboard_forage >= start_at:
            return True, f"{onboard_forage} Forage onboard (start at {start_at})"
        return False, f"{onboard_forage} Forage onboard, waiting for {start_at}"

    def report_transitions(self, status, phase, remaining):
        if phase != self._last_phase:
            if self._last_phase is not None:
                self.log.print(f"[{self.name}] Plants phase {self._last_phase} -> {phase}; needs {self._call('required_inputs', [])}.")
            self._last_phase = phase
        if status == self._last_status:
            return
        if status == "needs_mk2":
            self.log.level("warn").print(f"[{self.name}] Mk I limit reached ({remaining:,.0f} km² to next phase). Install a Mk II pack to continue.")
        elif status == "complete":
            self.log.print(f"[{self.name}] Plants complete (5,000,000 km²). Machine switched off.")
        elif status == "no_power":
            self.log.level("warn").print(f"[{self.name}] No power; batch paused.")
        elif status in ("no_water", "no_salt", "no_fertilizer", "no_accelerant") and self._last_status == "running":
            self.log.level("warn").print(f"[{self.name}] Waiting: {status}.")
        elif status == "running" and self._last_status is not None:
            self.log.print(f"[{self.name}] Batch running.")
        self.log.debug(f"[{self.name}] status {self._last_status} -> {status}.")
        self._last_status = status

    def publish_telemetry(self, entry, curr_tick):
        # The updater must stay pure (docs/components/data_archive.md): a log
        # call inside it gets the whole transaction rejected, so collect and
        # log after.
        pruned = []

        def updater(status):
            if not isinstance(status, dict):
                status = {}
            for machine_id in list(status.keys()):
                other = status[machine_id]
                if machine_id != self.name and (not isinstance(other, dict) or curr_tick - other.get("tick", 0) >= STATUS_STALE_TICKS):
                    pruned.append(machine_id)
                    del status[machine_id]
            status[self.name] = entry
            return status

        del pruned[:]
        if not archive.transaction(STATUS_KEY, {}, updater):
            self.log.level("warn").print(f"[{self.name}] {STATUS_KEY} write rejected; telemetry not published this cycle.")
            return
        for other_id in pruned:
            self.log.debug(f"[{self.name}] pruned stale {STATUS_KEY}['{other_id}'].")

    def step(self):
        curr_tick = self.get_current_tick()
        status = str(self._call("status", "unknown"))
        phase = int(self._call("phase", 0))
        required = list(self._call("required_inputs", ["forage"]))
        reqs = dict(self._call("batch_requirements", {}))
        remaining = float(self._call("remaining", 0.0))
        progress = float(self._call("get_progress", 0.0))
        running = bool(self._call("is_running", False))
        in_flight = running or progress > 0 or self._resume_pending

        self.report_transitions(status, phase, remaining)

        moved = {}
        if status not in STOP_STATUSES:
            requests = logistics_requests.active_requests(curr_tick) or {}
            if "water" in required:
                self.ensure_water(curr_tick)
            moved = self.feed(reqs, required, in_flight, requests)
            self.publish_requests(reqs, required, requests, curr_tick)
        elif self._published_targets is None or self._published_targets:
            logistics_requests.clear_requests(REQUESTER_ID, self.outpost_id)
            self._published_targets = {}

        held = self.onboard()
        onboard_forage = held.get("forage", 0)
        full_batch = int(reqs.get("forage", 0) or 0)
        enable, reason = self.decide(status, in_flight, onboard_forage, full_batch)
        self.set_enabled(enable, reason)
        if self._resume_pending:
            # One enabled step is enough to see whether a batch really was in flight.
            self.log.debug(f"[{self.name}] restart: resumed last known batch; trusting live readings from now on.")
            self._resume_pending = False

        self.log.debug(
            f"[{self.name}] status={status} phase={phase} progress={progress:.2f} running={running} "
            f"reqs={reqs} onboard={held} moved={moved} -> {'on' if enable else 'off'} ({reason})."
        )
        self.publish_telemetry({
            "status": status,
            "tier": int(self._call("tier", 1)),
            "phase": phase,
            "remaining_km2": round(remaining),
            "progress": round(progress, 3),
            "batch": int(self._call("batch_size", 0)),
            "km2_rate": round(float(self._call("km2_rate", 0.0)), 1),
            "onboard": held,
            "enabled": enable,
            "in_flight": running or progress > 0,
            "tick": curr_tick,
        }, curr_tick)

    def run(self, poll_interval=POLL_INTERVAL_S):
        self.log.print(f"Plant Terraformer ({self.name}) online, tier Mk {self._call('tier', 1)}.")
        validate_game_version()
        if not getattr(self.machine, "input", None):
            self.log.level("error").print(f"[{self.name}] No input slot; is this a Plant Terraformer?")
            return
        while True:
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Plant Terraformer exception: {error}")
            sleep(poll_interval)
