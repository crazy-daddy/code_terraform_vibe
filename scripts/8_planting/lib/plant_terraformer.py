from archive import archive
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from storage import take_item, best_unload_target
import logistics_requests
from plant_terraformer_common import STATUS_KEY, STATUS_STALE_TICKS, STOP_STATUSES, SUPPORT_HOLDER_CAP, FERTILIZER_ITEM_IDS, SUPPORT_REQUEST_BATCHES, PLANTS_BANDS, ceil_int, remaining_forage
from plant_terraformer_water import PlantTerraformerWaterMixin
from plant_terraformer_demand import PlantTerraformerDemandMixin

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
# + growth_accelerant (3.5M). Water comes through water_in
# (lib/plant_terraformer_water.py), items through storage.take_item() from
# Inventory (home) and local Warehouses.
#
# Demand (logistics.requests local stock targets) and the fleet's Fabricator
# orders for Fertilizer / Growth Accelerant: lib/plant_terraformer_demand.py.
#
# Loader order (_take()): away from home, local Drone Depots first, then
# Warehouses. At home, storage.take_item() -- for Forage that is clogged
# Crop Automators first, then Inventory, Warehouses, then the other
# automators (garden ones first within each; Forage stays in their output,
# no drain to storage) -- then Drone Depots. Home Forage stock (local_stock()) counts
# the automator outputs too.
# Source side: an item this outpost doesn't request itself (home Forage) is
# only consumed above what other outposts request (remote_retain()), so a
# home Terraformer can't eat the batch a hauler is coming for. At home it
# also leaves the Wildlife planner's Forage reserve for the Feed Makers
# (wildlife_reserve()): feed comes before Plants.
#
# Finish line (forage_to_go()): every machine publishes the km² its running
# batch adds (batch_km2); the Forage still to load fleet-wide is the rest of
# the ladder minus the unfinished part of every fresh in-flight batch. Once
# that is 0 the running batches reach 5,000,000 km² on their own: no more
# loading, requests or Fabricator orders, idle machines stay off. Below a full
# batch, the next batch's Forage (and the requests) shrink to what is left.
# At "complete" the script ejects its holders to local storage and ends; the
# Control Room Automation undeploys the empty machine (lib/plants_retire.py).

# Wildlife planner output; its forage_reserve is left for the Feed Makers.
WILDLIFE_PLAN_KEY = "wildlife.plan"

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

# Game-hours per cycle; km2_rate() spreads the running batch over it.
CYCLE_H = 3.0

# Another Terraformer's in-flight batch counts toward the finish line only
# while its telemetry is this fresh (10 ticks/s -> 1 min, 6 polls): a
# stopped script pauses its batch.
COMMIT_FRESH_TICKS = 600


def forage_to_go(phase, remaining_km2, committed_km2):
    """
    Forage the fleet still has to load: remaining_forage() minus the km² the
    in-flight batches add (committed_km2, at the current phase's km² per
    Forage). 0 once those batches reach 5,000,000 km²; None for an unknown
    phase (no cap).
    """
    if phase not in PLANTS_BANDS:
        return None
    return max(remaining_forage(phase, remaining_km2) - committed_km2 / PLANTS_BANDS[phase][0], 0.0)


class PlantTerraformerController(PlantTerraformerWaterMixin, PlantTerraformerDemandMixin):
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
        self._init_water()
        self._init_demand()
        self._finishing = False
        self._eject_warned = set()
        self._resume_pending = self._was_running()
        self._batch_km2 = self._last_batch_km2() if self._resume_pending else 0.0

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

    def _last_batch_km2(self):
        """Last published batch_km2 (script restart recovery while the batch is paused)."""
        status = archive.get(STATUS_KEY, {})
        if not isinstance(status, dict):
            return 0.0
        entry = status.get(self.name) or {}
        if not isinstance(entry, dict):
            return 0.0
        return float(entry.get("batch_km2", 0.0) or 0.0)

    # --------------------------------------------------------- finish line

    def own_committed_km2(self, in_flight, progress, km2_rate):
        """km² this machine's running batch still adds; remembers the batch's km² while km2_rate() reads 0 (paused)."""
        if not in_flight:
            self._batch_km2 = 0.0
            return 0.0
        if km2_rate > 0:
            self._batch_km2 = km2_rate * CYCLE_H
        return self._batch_km2 * max(1.0 - progress, 0.0)

    def fleet_committed_km2(self, curr_tick, own_km2):
        """own_km2 plus the unfinished km² of every other fresh, in-flight Terraformer batch (`plant.terraformer`)."""
        status = archive.get(STATUS_KEY, {})
        total = own_km2
        if not isinstance(status, dict):
            return total
        for machine_id, entry in status.items():
            if machine_id == self.name or not isinstance(entry, dict) or not entry.get("in_flight"):
                continue
            age = curr_tick - int(entry.get("tick", 0) or 0)
            if age < 0 or age >= COMMIT_FRESH_TICKS or entry.get("status") in STOP_STATUSES:
                continue
            total += float(entry.get("batch_km2", 0.0) or 0.0) * max(1.0 - float(entry.get("progress", 0.0) or 0.0), 0.0)
        return total

    @staticmethod
    def cap_batch(reqs, to_go):
        """
        reqs with the Forage batch cut to the Forage the fleet still has to
        load. Support items stay at the full batch's amounts (a few more than
        needed; the surplus is ejected at completion).
        """
        full = int(reqs.get("forage", 0) or 0)
        if to_go is None or full <= 0:
            return reqs
        need = ceil_int(to_go)
        if need >= full:
            return reqs
        capped = dict(reqs)
        capped["forage"] = need
        return capped

    @staticmethod
    def request_batches(full_batch, to_go):
        """Batches' worth of support items to request: SUPPORT_REQUEST_BATCHES, fewer when the ladder ends sooner."""
        if to_go is None or full_batch <= 0:
            return SUPPORT_REQUEST_BATCHES
        return max(min(SUPPORT_REQUEST_BATCHES, ceil_int(to_go / full_batch)), 1)

    def report_finishing(self, finishing, to_go, committed_km2):
        if finishing == self._finishing:
            return
        if finishing:
            self.log.print(f"[{self.name}] Running batches ({committed_km2:,.0f} km²) reach 5,000,000 km²: no more loading or requests.")
        else:
            self.log.print(f"[{self.name}] {to_go:,.0f} Forage still to load fleet-wide; loading again.")
        self._finishing = finishing

    def eject_holders(self, held):
        """Plants complete: ejects every holder stack to local storage (Warehouse, else Inventory at home, else a Drone Depot). Returns stacks moved."""
        stacks = [(item_id, count) for item_id, count in held.items() if count > 0]
        if not stacks:
            return 0
        self.log.start(f"[{self.name}] Plants complete: ejecting {len(stacks)} holder stack(s)")
        port = getattr(self.machine, "input", None)
        ejected = 0
        for item_id, count in (stacks if port else []):
            target = best_unload_target(item_id, 1, outpost=self.outpost)
            if target is None:
                depots = logistics_requests.local_depots(self.outpost)
                target = depots[0].id if depots else None
            if target is None:
                if item_id not in self._eject_warned:
                    self._eject_warned.add(item_id)
                    self.log.level("warn").print(f"[{self.name}] No local store has room for {count}x '{item_id}'; retrying.")
                continue
            try:
                res = port.eject(target, item_id, count)
            except Exception as error:
                self.log.level("warn").print(f"[{self.name}] eject({target!r}, '{item_id}', {count}) failed: {error}")
                continue
            moved = getattr(res, "moved", 0) or 0
            self.log.debug(f"eject {item_id} x{count} -> '{target}': {getattr(res, 'status', '?')}, moved {moved}.")
            if moved > 0:
                ejected += 1
                self._eject_warned.discard(item_id)
        self.log.end(f"ejected {ejected}/{len(stacks)} stack(s)")
        return ejected

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
            moved_total += logistics_requests.take_from_depots(port, item_id, amount, self.outpost)
            if moved_total >= amount:
                return moved_total

        # Next / Home primary: take_item() walks the holders in drain priority
        report = {}
        moved = take_item(port, item_id, amount - moved_total, outpost=self.outpost, report=report)
        self.log.debug(f"[{self.name}] take {item_id} x{amount - moved_total}: moved {moved}, sources {report.get('sources')}.")
        moved_total += moved

        # Home fallback: Drone Depots
        if moved_total < amount and self.is_home:
            moved_total += logistics_requests.take_from_depots(port, item_id, amount - moved_total, self.outpost)

        return moved_total

    def start_threshold(self, full_batch):
        """Batch (Forage) the loaded materials must support before an idle machine is enabled."""
        if full_batch <= 0:
            return MIN_START_FORAGE
        return max(min(full_batch, max(MIN_START_FORAGE, int(full_batch * START_BATCH_FRACTION))), 1)

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

    def decide(self, status, in_flight, supported, limiter, full_batch, finishing=False):
        """(enable, reason, blocker) for this step; blocker is the limiting material while idle, else None."""
        if status in STOP_STATUSES:
            return False, status, None
        if in_flight:
            return True, "batch in flight", None
        if finishing:
            return False, "running batches reach 5,000,000 km²", None
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
        """One poll. Returns True once Plants are complete and the holders are empty (the script can end)."""
        curr_tick = self.get_current_tick()
        status = str(self._call("status", "unknown"))
        phase = int(self._call("phase", 0))
        required = list(self._call("required_inputs", ["forage"]))
        reqs = dict(self._call("batch_requirements", {}))
        remaining_read = self._call("remaining", None)
        remaining = float(remaining_read or 0.0)
        progress = float(self._call("get_progress", 0.0))
        running = bool(self._call("is_running", False))
        in_flight = running or progress > 0 or self._resume_pending
        km2_rate = float(self._call("km2_rate", 0.0))

        self.report_transitions(status, phase, remaining)

        committed = self.fleet_committed_km2(curr_tick, self.own_committed_km2(in_flight, progress, km2_rate))
        # An unreadable remaining() must not look like the finish line.
        to_go = forage_to_go(phase, remaining, committed) if status not in STOP_STATUSES and remaining_read is not None else None
        finishing = to_go is not None and to_go <= 0
        self.report_finishing(finishing, to_go, committed)
        batches = self.request_batches(int(reqs.get("forage", 0) or 0), to_go)
        reqs = self.cap_batch(reqs, to_go)

        moved = {}
        if status not in STOP_STATUSES and not finishing:
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
            self.publish_requests(reqs, required, requests, curr_tick, batches)
            self.publish_fabricator_orders(*self.fabricator_orders(reqs, required, phase, remaining, self.fleet_size(curr_tick), to_go))
        else:
            self.withdraw_requests()
            # A Mk I machine ("needs_mk2") leaves the Mk II fleet's orders alone.
            if status == "complete" or finishing:
                self.publish_fabricator_orders({}, {})
            if status == "complete":
                self.eject_holders(self.onboard())

        held = self.onboard()
        full_batch = int(reqs.get("forage", 0) or 0)
        supported, limiter = self.supported_batch(reqs, required, held)
        enable, reason, blocker = self.decide(status, in_flight, supported, limiter, full_batch, finishing)
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
            "km2_rate": round(km2_rate, 1),
            "batch_km2": round(self._batch_km2, 1),
            "onboard": held,
            "enabled": enable,
            "blocker": blocker,
            "supported_batch": supported,
            "in_flight": running or progress > 0,
            "tick": curr_tick,
        }, curr_tick)
        return status == "complete" and not held

    def run(self, poll_interval=POLL_INTERVAL_S):
        self.log.print(f"Plant Terraformer ({self.name}) online, tier Mk {self._call('tier', 1)}.")
        validate_game_version()
        if not getattr(self.machine, "input", None):
            self.log.level("error").print(f"[{self.name}] No input slot; is this a Plant Terraformer?")
            return
        while True:
            reset_all()
            done = False
            try:
                done = self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Plant Terraformer exception: {error}")
            if done:
                self.log.print(f"[{self.name}] Plants complete, holders empty: script ends; the Control Room Automation undeploys the machine.")
                flush_all()
                return
            flush_all()
            sleep(poll_interval)
