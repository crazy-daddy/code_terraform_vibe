from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item
import fluid_routing
import logistics_requests
from production import FLUID_SOURCE_TYPE_IDS, fluid_building_is_viable, fabricator_unlocked_outputs, set_upgrade_order, set_backlog_order

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
#     draws power (Mk I 180 W, Mk II 900 W) the whole time it is enabled,
#     blocked or not. The km² per Forage is fixed per phase, so a small batch
#     loses no km², but its whole-item Salt / Growth Accelerant and the power.
#     When Forage is the bottleneck, waiting for a full batch costs no km².
#   - A cycle commits the largest Forage batch EVERY loaded material supports
#     (a half-full water tank halves the batch). supported_batch() computes
#     that from the holders and the water_in level; an idle machine is
#     enabled only once it reaches start_threshold() (START_BATCH_FRACTION of
#     a full batch) and is disabled otherwise -- also while an input (e.g.
#     Fertilizer nobody crafts yet) is missing entirely. The limiting
#     material is logged and published as `blocker`.
#   - An enabled machine starts the next batch the moment one ends -- or, if
#     it is idle, the moment its holders support one Forage, even while a
#     timed transfer is still filling them. Salt and Growth Accelerant are
#     whole items per batch, so a 200-Forage batch burns the same Accelerant
#     as a full one. Hence: an idle machine is disabled before anything is
#     loaded; while a batch runs, Forage is preloaded first (only once
#     onboard + local stock of every material can reach start_threshold())
#     and the support items only after the onboard Forage reaches it, so the
#     holders stay unstartable until the next batch is full.
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
# Loader order (_take()): away from home, local Drone Depots first, then
# Warehouses. At home, storage.take_item() -- for Forage that is clogged
# Crop Automators first, then Inventory, Warehouses, then the other
# automators (garden ones first within each; Forage stays in their output,
# no drain to storage) -- then Drone Depots. Home Forage stock (local_stock()) counts
# the automator outputs too.
#   - Forage: one full batch, only away from home -- the field's Harvester
#     delivers to home Inventory, so home is a SOURCE of Forage, not a sink.
#   - Salt / Growth Accelerant: SUPPORT_REQUEST_BATCHES batches' worth.
#   - Fertilizer: requested as the tier the Fabricator crafts
#     (craft_fertilizer_item()), counted in that tier's potency units across
#     all tiers.
#   logistics.requests holds one entry per item per outpost; an item another
#   requester (e.g. the field Harvester's salt) already owns here is left
#   alone -- its target keeps the outpost stocked, and the Terraformer draws
#   from the same stock.
# Source side: an item this outpost doesn't request itself (home Forage) is
# only consumed above what other outposts request (remote_retain()), so a
# home Terraformer can't eat the batch a hauler is coming for. At home it
# also leaves the Wildlife planner's Forage reserve for the Feed Makers
# (wildlife_reserve()): feed comes before Plants.
#
# Fabricator orders (fabricator_orders()): Fertilizer and Growth Accelerant
# are crafted at any fab site. Every Mk II Terraformer writes the same two orders
# for the whole fleet (fleet_size() from `plant.terraformer` telemetry):
#   - need: NEED_BATCHES batches per machine, a standing upgrade order
#     (production.set_upgrade_order(), ranked above Earth orders);
#   - backlog: BACKLOG_BATCHES batches per machine, a backlog order
#     (production.set_backlog_order(), crafted only in idle Fabricator time).
# Both net against network stock (production.SourceCache.network_stock(),
# Drone Depots included), so units at a remote fab site count; the local
# request above hauls them in.
# Both are capped by what the rest of the Plants ladder still needs
# (remaining_forage()), so they shrink to 0 near completion.

STATUS_KEY = "plant.terraformer"
REQUESTER_ID = "plant_terraformer"
# Wildlife planner output; its forage_reserve is left for the Feed Makers.
WILDLIFE_PLAN_KEY = "wildlife.plan"

# 10 ticks/s -> 1 h. Entries of Terraformers that stopped publishing are
# pruned by the next publish (one shared dict, CLAUDE.md rule 7).
STATUS_STALE_TICKS = 36000

# A cycle is 3 game-hours; loading a full Mk I batch takes ~19 s (Fast
# Feeders: ~9 s). Polling every 10 s loses nothing.
POLL_INTERVAL_S = 10.0

# Share of a full batch (batch_requirements()["forage"], which already
# shrinks near a phase threshold) the loaded materials must support before
# an idle machine is enabled. A partial batch spends the same whole Salt /
# Growth Accelerant items and 3 h of power as a full one.
START_BATCH_FRACTION = 1.0

# Floor on the start threshold (a full batch below it is used as is).
MIN_START_FORAGE = 100

# Forage one Salt item treats (plant_terraformer_guide: 1 Salt per 500).
SALT_FORAGE_PER_ITEM = 500

# Growth Accelerant / each Fertilizer tier: onboard holder cap. The Salt
# holder fits a full batch's need (Mk II: 14).
SUPPORT_HOLDER_CAP = 10

# Fertilizer item ids, best potency first (fertilizer_potency(): 50/30/10).
FERTILIZER_ITEM_IDS = ("fertilizer_mk3", "fertilizer_mk2", "fertilizer")

# Fertilizer tier the Fabricator is asked for, cheapest first: per potency,
# Mk II needs less Fabricator time and Tar than Mk I, and Mk III's Neutron
# Capacitor chain costs about 5x Mk II (§1k). The first unlocked one wins.
FERTILIZER_CRAFT_PREFERENCE = ("fertilizer_mk2", "fertilizer")

# Fabricator need order: batches per running Mk II Terraformer (2 machines:
# 20 Growth Accelerant, 18 Fertilizer Mk II). Fabricators sit at other
# outposts, so this covers ~30 h of use while a hauler brings a load in.
NEED_BATCHES = 10

# Fabricator backlog order: the stock kept on the network, batches per
# machine (2 machines: 200 Growth Accelerant), crafted in idle Fabricator
# time. Capped by the rest of the ladder, so it ends with the Plants phase.
BACKLOG_BATCHES = 100

# Plants ladder (plant_terraformer_guide.md): phase -> (km² per Forage, band
# Forage). Phase 6 is Continental complete.
PLANTS_BANDS = {1: (20.0, 25000), 2: (5.0, 150000), 3: (5.0 / 3, 600000), 4: (1.0, 1250000), 5: (1.0 / 3, 4500000)}

# First phase each Fabricator-crafted input is needed in (cumulative after).
CRAFTED_SUPPORT_FIRST_PHASE = {"fertilizer": 4, "growth_accelerant": 5}

# Salt / Growth Accelerant / Fertilizer staged at the outpost, in batches'
# worth (Mk I full batch: 3 Salt; Mk II: 14 Salt, 27 potency, 1
# Accelerant; Fertilizer/Accelerant capped by the holder), so several
# batches are on hand while a hauler brings more in one load.
SUPPORT_REQUEST_BATCHES = 10

# Requests are republished at least this often (well inside
# logistics_requests.REQUEST_STALE_TICKS = 6000) and at once when a target
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


def remaining_forage(phase, remaining_km2, from_phase=1):
    """Forage still to convert from phase `from_phase` on: the rest of the current band plus every later band."""
    total = 0.0
    if phase in PLANTS_BANDS and phase >= from_phase:
        total += max(remaining_km2, 0.0) / PLANTS_BANDS[phase][0]
    for band_phase, (_, band_forage) in PLANTS_BANDS.items():
        if band_phase > phase and band_phase >= from_phase:
            total += band_forage
    return total


def _ceil(value):
    whole = int(value)
    return whole + 1 if value > whole else whole


def order_sizes(per_batch, full_batch, machines, forage_left):
    """
    (need, backlog) item counts for one crafted input. per_batch = items per
    full batch of full_batch Forage (fractional for Fertilizer potency).
    Both are capped by forage_left; backlog is never below need.
    """
    if per_batch <= 0 or full_batch <= 0 or machines <= 0:
        return 0, 0
    left = _ceil(forage_left * per_batch / full_batch)
    need = min(_ceil(NEED_BATCHES * machines * per_batch), left)
    backlog = min(_ceil(BACKLOG_BATCHES * machines * per_batch), left)
    return need, max(need, backlog)


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
        self._last_blocker = None
        self._water_router = None
        self._published_targets = None
        self._published_tick = None
        self._published_orders = None
        self._order_detail = []
        self._foreign_owners = {}
        self._craft_fertilizer = None
        self._craft_fertilizer_tick = 0
        self._resume_pending = self._was_running()

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("plant_terraformer.PlantTerraformerController.get_current_tick: self.clock.tick", error)
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
        """Units at this outpost a local InputSlot can take(): Warehouses + Drone Depots (+ Inventory and Crop Automator Forage at home)."""
        return logistics_requests.outpost_stock([item_id], self.outpost).get(item_id, 0)

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

    def wildlife_reserve(self, item_id):
        """
        Home Forage the Feed Makers need for the feed the Wildlife planner
        wants (`wildlife.plan.forage_reserve`, lib/wildlife_planner.py): feed
        comes first, the Terraformer uses what is left.
        """
        if item_id != "forage" or not self.is_home:
            return 0
        plan = archive.get(WILDLIFE_PLAN_KEY, {}) or {}
        return int(plan.get("forage_reserve", 0) or 0) if isinstance(plan, dict) else 0

    def available(self, item_id, requests):
        return max(self.local_stock(item_id) - self.remote_retain(item_id, requests) - self.wildlife_reserve(item_id), 0)

    def _take(self, item_id, amount, requests):
        """
        Pulls up to `amount` into the holders:
        For remote outposts: Drone Depots first, then local Warehouses.
        For home outpost: storage.take_item() (Forage: clogged Crop Automators,
        Inventory, Warehouses, other Crop Automators, garden ones first), then
        Drone Depots.
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

        # Next / Home primary: take_item() walks the holders in drain priority
        report = {}
        moved = take_item(port, item_id, amount - moved_total, outpost=self.outpost, report=report)
        self.log.debug(f"[{self.name}] take {item_id} x{amount - moved_total}: moved {moved}, sources {report.get('sources')}.")
        moved_total += moved

        # Home fallback: Drone Depots
        if moved_total < amount and self.is_home:
            moved_total += self._take_from_depots(port, item_id, amount - moved_total)

        return moved_total

    def _take_from_depots(self, port, item_id, amount):
        self.log.start(f"[{self.name}] _take_from_depots", level="debug")
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
                self.log.debug(f"take {item_id} from depot '{depot.id}' raised: {error}")
                continue
            moved = getattr(res, "moved", 0) or 0
            self.log.debug(f"take {item_id} x{want} from depot '{depot.id}': {getattr(res, 'status', None)}, moved {moved}.")
            moved_total += moved
        self.log.end()
        return moved_total

    def start_threshold(self, full_batch):
        """Batch (Forage) the loaded materials must support before an idle machine is enabled."""
        if full_batch <= 0:
            return MIN_START_FORAGE
        return max(min(full_batch, max(MIN_START_FORAGE, int(full_batch * START_BATCH_FRACTION))), 1)

    def water_level(self):
        port = getattr(self.machine, "water_in", None)
        if not port or not hasattr(port, "level"):
            return 0.0
        try:
            return float(port.level() or 0.0)
        except Exception as error:
            swallowed("plant_terraformer.PlantTerraformerController.water_level: port.level", error)
            return 0.0

    def support_limits(self, reqs, required, held):
        """
        {material: Forage it supports} for every non-Forage input the phase
        needs, from the holders and the water_in level. Fertilizer counts
        unopened items only (opened potency isn't readable), so it errs low.
        """
        full = int(reqs.get("forage", 0) or 0)
        if full <= 0:
            return {}
        limits = {}
        if "water" in required and reqs.get("water"):
            limits["water"] = int(self.water_level() * full / float(reqs["water"]))
        if "salt" in required and reqs.get("salt"):
            limits["salt"] = held.get("salt", 0) * SALT_FORAGE_PER_ITEM
        if reqs.get("fertilizer_potency"):
            potency = sum(held.get(i, 0) * self._potency(i) for i in FERTILIZER_ITEM_IDS)
            limits["fertilizer"] = potency * full // int(reqs["fertilizer_potency"])
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            limits["growth_accelerant"] = held.get("growth_accelerant", 0) * full // int(reqs["growth_accelerant"])
        return limits

    def supported_batch(self, reqs, required, held):
        """(Forage batch the loaded materials support, limiting material)."""
        limits = self.support_limits(reqs, required, held)
        limits["forage"] = held.get("forage", 0)
        limiter = min(limits, key=lambda k: limits[k])
        return limits[limiter], limiter

    def load_forage(self, wanted, held, in_flight, requests, support_limit):
        """Top the holders up to `wanted` Forage. Returns units moved."""
        self.log.start(f"[{self.name}] load_forage", level="debug")
        onboard = held.get("forage", 0)
        missing = wanted - onboard
        if missing <= 0:
            self.log.end()
            return 0
        if in_flight:
            start_at = self.start_threshold(wanted)
            if support_limit < start_at:
                self.log.debug(f"batch running; not preloading Forage: other inputs support {support_limit} (next batch starts at {start_at}).")
                self.log.end()
                return 0
            available = self.available("forage", requests)
            if onboard + available < start_at:
                self.log.debug(f"batch running; not preloading {available} Forage (next batch starts at {start_at}).")
                self.log.end()
                return 0
        _ret = self._take("forage", missing, requests)
        self.log.end()
        return _ret

    def load_salt(self, need, held, requests):
        return self._take("salt", need - held.get("salt", 0), requests)

    def load_accelerant(self, need, held, requests):
        want = min(need, SUPPORT_HOLDER_CAP)
        return self._take("growth_accelerant", want - held.get("growth_accelerant", 0), requests)

    def _potency(self, item_id):
        try:
            return int(self.machine.fertilizer_potency(item_id))
        except Exception as error:
            swallowed("plant_terraformer.PlantTerraformerController._potency: self.machine.fertilizer_potency", error)
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

    def reachable_support(self, reqs, required, held, requests):
        """Onboard support items plus what local stock can still load (holder caps applied), for support_limits()."""
        reach = dict(held)
        items = []
        if "salt" in required and reqs.get("salt"):
            items.append("salt")
        if reqs.get("fertilizer_potency"):
            items.extend(FERTILIZER_ITEM_IDS)
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            items.append("growth_accelerant")
        for item_id in items:
            total = held.get(item_id, 0) + self.available(item_id, requests)
            reach[item_id] = total if item_id == "salt" else min(total, SUPPORT_HOLDER_CAP)
        return reach

    def load_support(self, reqs, required, held, requests):
        moved = {}
        if "salt" in required and reqs.get("salt"):
            moved["salt"] = self.load_salt(int(reqs["salt"]), held, requests)
        if reqs.get("fertilizer_potency"):
            moved["fertilizer"] = self.load_fertilizer(int(reqs["fertilizer_potency"]), held, requests)
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            moved["growth_accelerant"] = self.load_accelerant(int(reqs["growth_accelerant"]), held, requests)
        return moved

    def feed(self, reqs, required, in_flight, requests):
        """
        Loads every material the current recipe needs. Returns {item_id: moved}.

        A batch that ends while the machine is enabled starts the next one at
        once from whatever is onboard, and Forage arrives in timed chunks. So
        while a batch runs, Forage loads first and the support items only once
        the onboard Forage reaches start_threshold(): until then a support item
        the last batch consumed is missing and no partial batch can start.
        Idle, step() disables the machine before loading, so support items
        load first and the Forage gate sees them.
        """
        moved = {}
        held = self.onboard()
        forage = int(reqs.get("forage", 0) or 0)
        if in_flight and forage > 0:
            limits = self.support_limits(reqs, required, self.reachable_support(reqs, required, held, requests))
            moved["forage"] = self.load_forage(forage, held, in_flight, requests, min(limits.values()) if limits else forage)
            if moved["forage"]:
                held = self.onboard()
            start_at = self.start_threshold(forage)
            if held.get("forage", 0) < start_at:
                self.log.debug(f"[{self.name}] batch running; support items held back: {held.get('forage', 0)} Forage onboard, next batch starts at {start_at}.")
                return {k: v for k, v in moved.items() if v}
        moved.update(self.load_support(reqs, required, held, requests))
        if not in_flight and forage > 0:
            if any(moved.values()):
                held = self.onboard()
            limits = self.support_limits(reqs, required, held)
            moved["forage"] = self.load_forage(forage, held, in_flight, requests, min(limits.values()) if limits else forage)
        return {k: v for k, v in moved.items() if v}

    # --------------------------------------------------------------- water

    def _discover_water_sources(self):
        self.log.start(f"[{self.name}] _discover_water_sources", level="debug")
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
                self.log.debug(f"water source discovery failed: {error}")
        ids = fluid_routing.rank_own_outpost_first(pairs, self.outpost_id)
        self.log.debug(f"water_in: sources (own outpost first): {ids}.")
        self.log.end()
        return ids

    @staticmethod
    def _port_starved(port):
        """flow_rate() == 0 with room left -- a full port also reads 0, not a stall."""
        try:
            level = port.level() if hasattr(port, "level") else 0
            capacity = port.capacity() if hasattr(port, "capacity") else 0
            flow = port.flow_rate() if hasattr(port, "flow_rate") else 0
            return flow == 0 and (not capacity or level < capacity)
        except Exception as error:
            swallowed("plant_terraformer.PlantTerraformerController._port_starved: port.level", error)
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
                reserve_fluid="water",
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
            targets["salt"] = int(reqs["salt"]) * SUPPORT_REQUEST_BATCHES
        if reqs.get("fertilizer_potency"):
            item_id = self.craft_fertilizer_item()
            per_batch = -(-int(reqs["fertilizer_potency"]) // max(self._potency(item_id), 1))
            targets[item_id] = min(per_batch, SUPPORT_HOLDER_CAP) * SUPPORT_REQUEST_BATCHES
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            targets["growth_accelerant"] = min(int(reqs["growth_accelerant"]), SUPPORT_HOLDER_CAP) * SUPPORT_REQUEST_BATCHES
        return targets

    def _have(self, item_id):
        """Published "have": local stock; Fertilizer in item_id's potency units over all tiers."""
        if item_id not in FERTILIZER_ITEM_IDS:
            return self.local_stock(item_id)
        unit = max(self._potency(item_id), 1)
        return sum(self.local_stock(i) * self._potency(i) for i in FERTILIZER_ITEM_IDS) // unit

    def publish_requests(self, reqs, required, requests, curr_tick):
        """Advertises this Terraformer's demand in logistics.requests (see module header)."""
        if not self.outpost_id:
            return
        here = requests.get(self.outpost_id) or {}
        targets = {}
        foreign = {}
        for item_id, target in self.demand_targets(reqs, required).items():
            entry = here.get(item_id) or {}
            owner = entry.get("by") if isinstance(entry, dict) else None
            if owner in (None, REQUESTER_ID):
                targets[item_id] = target
            else:
                foreign[item_id] = owner
        if foreign != self._foreign_owners:
            for item_id, owner in foreign.items():
                self.log.debug(f"[{self.name}] {item_id} already requested here by '{owner}'; not overriding.")
            self._foreign_owners = foreign

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

    # -------------------------------------------------- Fabricator orders

    def craft_fertilizer_item(self, curr_tick=None):
        """First FERTILIZER_CRAFT_PREFERENCE item the Fabricator has unlocked; curr_tick re-reads it every REQUEST_REFRESH_TICKS."""
        due = self._craft_fertilizer is None or (
            curr_tick is not None
            and (curr_tick < self._craft_fertilizer_tick or curr_tick - self._craft_fertilizer_tick >= REQUEST_REFRESH_TICKS)
        )
        if due:
            unlocked = fabricator_unlocked_outputs()
            item_id = next((i for i in FERTILIZER_CRAFT_PREFERENCE if i in unlocked), FERTILIZER_CRAFT_PREFERENCE[-1])
            if item_id != self._craft_fertilizer:
                self.log.debug(f"[{self.name}] Fertilizer to craft: {item_id} (unlocked: {sorted(i for i in unlocked if i in FERTILIZER_ITEM_IDS)}).")
            self._craft_fertilizer = item_id
            self._craft_fertilizer_tick = curr_tick or 0
        return self._craft_fertilizer

    def fleet_size(self, curr_tick):
        """Mk II Terraformers on the ladder: fresh, non-stopped `plant.terraformer` entries plus this one."""
        status = archive.get(STATUS_KEY, {})
        count = 1
        if not isinstance(status, dict):
            return count
        for machine_id, entry in status.items():
            if machine_id == self.name or not isinstance(entry, dict):
                continue
            if curr_tick - entry.get("tick", 0) >= STATUS_STALE_TICKS or entry.get("status") in STOP_STATUSES:
                continue
            if int(entry.get("tier", 1) or 1) >= 2:
                count += 1
        return count

    def fabricator_orders(self, reqs, required, phase, remaining, machines):
        """({item_id: need}, {item_id: backlog}) for the Fabricator-crafted inputs this phase needs (see module header)."""
        need, backlog = {}, {}
        self._order_detail = []
        full = int(reqs.get("forage", 0) or 0)
        if full <= 0:
            return need, backlog
        crafted = []
        if reqs.get("fertilizer_potency"):
            item_id = self.craft_fertilizer_item()
            per_batch = int(reqs["fertilizer_potency"]) / float(max(self._potency(item_id), 1))
            crafted.append((item_id, per_batch, CRAFTED_SUPPORT_FIRST_PHASE["fertilizer"]))
        if "growth_accelerant" in required and reqs.get("growth_accelerant"):
            crafted.append(("growth_accelerant", float(reqs["growth_accelerant"]), CRAFTED_SUPPORT_FIRST_PHASE["growth_accelerant"]))
        for item_id, per_batch, first_phase in crafted:
            forage_left = remaining_forage(phase, remaining, first_phase)
            n, b = order_sizes(per_batch, full, machines, forage_left)
            self._order_detail.append(f"[{self.name}] {item_id}: {per_batch:.2f}/batch x {machines} machine(s), {forage_left:,.0f} Forage left -> need {n}, backlog {b}.")
            if n > 0:
                need[item_id] = n
            if b > 0:
                backlog[item_id] = b
        return need, backlog

    def publish_fabricator_orders(self, need, backlog):
        """Writes both orders (production skips unchanged writes); info line and fabricator_orders()' sizing trail when they change."""
        orders = (need, backlog)
        if orders == self._published_orders:
            return
        for line in self._order_detail:
            self.log.debug(line)
        set_upgrade_order(REQUESTER_ID, need)
        set_backlog_order(REQUESTER_ID, backlog)
        if need or backlog:
            self.log.print(f"[{self.name}] Fabricator orders: need {need}, backlog {backlog}.")
        elif self._published_orders:
            self.log.print(f"[{self.name}] Fabricator orders withdrawn.")
        self._published_orders = orders

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

    def decide(self, status, in_flight, supported, limiter, full_batch):
        """(enable, reason, blocker) for this step; blocker is the limiting material while idle, else None."""
        if status in STOP_STATUSES:
            return False, status, None
        if in_flight:
            return True, "batch in flight", None
        start_at = self.start_threshold(full_batch)
        if supported >= start_at:
            return True, f"loaded inputs support {supported} Forage (start at {start_at})", None
        return False, f"{limiter} supports {supported} Forage, waiting for {start_at}", limiter

    def report_blocker(self, blocker, supported, full_batch):
        """Info line when the idle machine's limiting input changes; the per-step reason stays debug."""
        if blocker == self._last_blocker:
            return
        if blocker:
            self.log.print(f"[{self.name}] Idle, switched off: {blocker} supports {supported}/{full_batch} Forage.")
        elif self._last_blocker:
            self.log.print(f"[{self.name}] Inputs ready ({self._last_blocker} no longer short).")
        self._last_blocker = blocker

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
            if not in_flight:
                # An enabled idle machine starts a batch as soon as its holders
                # support one Forage, so loading into it would start a partial one.
                self.set_enabled(False, "idle, loading inputs")
            requests = logistics_requests.active_requests(curr_tick) or {}
            if "water" in required:
                self.ensure_water(curr_tick)
            if reqs.get("fertilizer_potency"):
                self.craft_fertilizer_item(curr_tick)
            moved = self.feed(reqs, required, in_flight, requests)
            self.publish_requests(reqs, required, requests, curr_tick)
            self.publish_fabricator_orders(*self.fabricator_orders(reqs, required, phase, remaining, self.fleet_size(curr_tick)))
        else:
            if self._published_targets is None or self._published_targets:
                logistics_requests.clear_requests(REQUESTER_ID, self.outpost_id)
                self._published_targets = {}
            # A Mk I machine ("needs_mk2") leaves the Mk II fleet's orders alone.
            if status == "complete":
                self.publish_fabricator_orders({}, {})

        held = self.onboard()
        full_batch = int(reqs.get("forage", 0) or 0)
        supported, limiter = self.supported_batch(reqs, required, held)
        enable, reason, blocker = self.decide(status, in_flight, supported, limiter, full_batch)
        self.report_blocker(blocker, supported, full_batch)
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
            "blocker": blocker,
            "supported_batch": supported,
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
            reset_all()
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Plant Terraformer exception: {error}")
            flush_all()
            sleep(poll_interval)
