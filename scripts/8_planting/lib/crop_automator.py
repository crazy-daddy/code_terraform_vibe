# Crop Automator: harvests and replants the full-layout cells in its 5 x 5
# area (thin entrypoint harvesting/crop_automator.py). Deployed by the
# Harvester on the cells the full layout reserves for it
# (lib/harvester_machines.py); the kits come from the Shop.
#
# Each step (POLL_INTERVAL_S):
#   1. consume finished job results (a full result inbox pauses the machine)
#   2. seed demand fallback: if `plant.seed_demand` is older than
#      SEED_DEMAND_FALLBACK_TICKS (Harvester offline), the first deployed
#      automator republishes it for the automated cells
#      (refresh_seed_demand_if_stale()), so the Seed Maker keeps making seeds
#   3. ownership: automator areas overlap, so every layout cell belongs to
#      the nearest deployed automator (Chebyshev distance, then Manhattan,
#      then sector id). Each automator only queues jobs for its own cells.
#   4. a blocked head job would freeze the FIFO executor (unblock_queue()):
#      `no_seed` -> load one seed, else cancel the job (cell cooldown);
#      `output_full` -> wait until a consumer pulls (see 7); QUIET_BLOCKERS
#      are normal states, logged at debug only
#   5. harvest every mature layout crop it owns (status "mature" or
#      growth >= 1.0), except garden crops (field_layout.kept_crop()): they
#      are planted once and never harvested, since a mature crop still
#      counts toward the species multiplier. A garden automator only plants.
#   6. plant every open layout cell it owns, once the machines beside the
#      cell give every care service the species needs (Crop Automators only
#      apply Fertilizer / Growth Accelerant: light, water and salt must come
#      from Grow Lamps, Sprinklers and Dispensers). Seeds in the input are
#      netted against plant jobs already queued (queued_jobs_info()); when
#      none are spare, SEED_PULL_BATCH are loaded at once from Inventory /
#      home Warehouses (storage.take_item()) instead of one per job. The
#      Harvester's plant.seed_demand covers the automated cells, so the Seed
#      Maker makes them.
#   7. Forage stays in its output (up to 50,000 units): no drain to
#      Warehouses, so auto-loaders stay free. A clogged automator is
#      accepted over clogged Warehouses. Consumers (the Plant Terraformer via
#      storage.take_item()) take it from there directly, clogged automators
#      first (storage.crop_automator_forage())
# Nothing is queued while the Power Guard has shed it (`power.shedded`) or
# while the layout is still the starter one. Loose items on its cells are
# swept by the Harvester (a plant job needs an empty cell).
#
# Telemetry: `plant.automators` = {machine_id: {"sector", "status", "queue",
# "cells", "mature", "open", "waiting_machines", "forage", "garden", "tick"}}
# (one shared dict, stale entries pruned). "forage" = Forage in the output;
# "garden" = the automator sits in the diversity garden (columns
# 1..field_layout.GARDEN_COLS), read by storage.crop_automator_forage().

from archive import archive
import field_layout
from storage import take_item
from seed_supply import seed_buffer
from tree_console import TreeConsole
from swallow import swallowed
from version_guard import validate_game_version

LAYOUT_KEY = "plant.layout"        # same key as harvester_planting.LAYOUT_KEY
RECIPES_KEY = "plant.recipes"      # same key as seed_supply.RECIPES_KEY
SEED_DEMAND_KEY = "plant.seed_demand"  # same key as seed_supply.SEED_DEMAND_KEY
STATUS_KEY = "plant.automators"

POLL_INTERVAL_S = 10.0
PUBLISH_INTERVAL_TICKS = 600       # telemetry at most once a minute
STATUS_STALE_TICKS = 36000         # an automator silent this long (~1 h) is dropped from telemetry
QUEUE_LIMIT = 45                   # the machine takes 50; leave room for a manual job
JOB_FAIL_COOLDOWN_TICKS = 3000     # a cell whose job failed is left alone this long (~5 min)
MAX_RESULTS_PER_STEP = 50          # the inbox holds at most 50
SEED_DEMAND_FALLBACK_TICKS = 3000  # Harvester's plant.seed_demand older than this (~5 min) -> automator republishes it
# Head-job blockers that are normal states (brownout shedding, not yet
# placed, result inbox full -- consume_results() empties it): debug only.
QUIET_BLOCKERS = ("no_power", "not_placed", "results_full")
SEED_PULL_BATCH = 10               # batch-load seeds into input to avoid per-job storage transfers


def _position(ref):
    return getattr(ref, "position", None)


class CropAutomatorController:
    """Queues harvest and plant jobs for the full-layout cells this Crop Automator owns."""

    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "crop_automator")
        self.clock = get_component("clock")
        self.log = TreeConsole(module="crop_automator")
        self.sector = self._read_sector()
        self._failed = {}                  # {sector: tick of last failed job}
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self._last_state = None

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception as error:
                swallowed("crop_automator.CropAutomatorController.get_current_tick: self.clock.tick", error)
        return 0

    def _read_sector(self):
        try:
            return self.machine.position()
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController._read_sector: self.machine.position", error)
            return None

    # ------------------------------------------------------------ discovery

    def deployed_machines(self):
        """{sector: kind} of every field machine on the home field ({} if unreadable)."""
        try:
            network = get_component("outpost_network")
            home = network.home() if network and hasattr(network, "home") else None
            if home is None and network:
                home = next((o for o in network.outposts() if getattr(o, "is_home", False)), None)
            if home is None:
                return {}
            return {_position(m): m.type_id for m in home.harvesting_machines()}
        except Exception as e:
            self.log.debug(f"[{self.name}] harvesting_machines() failed: {e}")
            return {}

    def owned_cells(self, layout_cells, automators):
        """Layout sectors in this automator's area that no nearer automator owns."""
        me = self.sector
        return [s for s in field_layout.automator_area(me)
                if s in layout_cells and field_layout.automator_owner(s, automators) == me]

    def services_ready(self, sector, species, rules, deployed):
        served = [field_layout.MACHINE_SERVICE.get(deployed.get(n) or "") for n in field_layout.neighbours(sector)]
        return all(k in served for k in field_layout.care_kinds(rules, species))

    def is_shedded(self):
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

    def refresh_seed_demand_if_stale(self, curr_tick, layout, rules, automators):
        """
        Fallback while the Harvester is offline: the first deployed automator
        republishes plant.seed_demand once it is SEED_DEMAND_FALLBACK_TICKS
        old. Only automated fill cells count (layout cells in some
        automator's area): nobody plants the rest while the Harvester is
        away, and garden cells are planted once, never replanted.
        """
        if not automators or automators[0] != self.sector:
            return
        raw = archive.get(SEED_DEMAND_KEY)
        if isinstance(raw, dict) and curr_tick - (raw.get("tick") or 0) < SEED_DEMAND_FALLBACK_TICKS:
            return
        layout_cells = layout.get("cells") or {}
        served = set()
        for ca in automators:
            served |= set(field_layout.automator_area(ca))
        rotation = {}
        garden = set(layout.get("garden") or [])
        for sector, species in layout_cells.items():
            if sector in served and sector not in garden:
                seed_id = (rules.get(species) or {}).get("seed_id") or "seed_" + species
                rotation[seed_id] = rotation.get(seed_id, 0) + 1
        priority = field_layout.priority_seeds(layout_cells, layout.get("garden"), layout.get("fill"), rules)
        demand = {"now": {seed_id: seed_buffer(n) for seed_id, n in rotation.items()}, "rotation": rotation,
                  "priority": priority, "tick": curr_tick}
        wrote = []

        def updater(state):
            # The Harvester may have published since the read above: keep that.
            if isinstance(state, dict) and curr_tick - (state.get("tick") or 0) < SEED_DEMAND_FALLBACK_TICKS:
                return state
            wrote.append(True)
            return demand

        archive.transaction(SEED_DEMAND_KEY, {}, updater)
        if wrote:
            self.log.debug(f"[{self.name}] '{SEED_DEMAND_KEY}' stale; republished for {sum(rotation.values())} automated cell(s) as fallback.")

    # ----------------------------------------------------------------- jobs

    def consume_results(self, curr_tick):
        for _ in range(MAX_RESULTS_PER_STEP):
            try:
                if self.machine.result_count() <= 0:
                    return
                res = self.machine.next_result()
            except Exception as e:
                self.log.debug(f"[{self.name}] next_result() failed: {e}")
                return
            status = getattr(res, "status", "?")
            if status == "empty":
                return
            action = getattr(res, "action", None)
            sector = getattr(res, "sector", None)
            if status == "ok":
                collected = getattr(res, "collected", 0) or 0
                self.log.debug(f"[{self.name}] {action} {sector} ok{' +' + str(collected) + ' Forage' if collected else ''}.")
            elif status == "partial":
                self.log.level("warn").print(f"[{self.name}] Harvest {sector}: output full, kept {getattr(res, 'collected', 0)}, discarded {getattr(res, 'discarded', 0)} Forage.")
            else:
                self.log.debug(f"[{self.name}] {action} {sector} -> {status}: {getattr(res, 'message', '')}")
                if sector:
                    self._failed[sector] = curr_tick

    def queued_jobs_info(self):
        """Returns (queued_sectors: set, committed_seeds: dict[seed_id, int], blocked_job: CropJob | None)."""
        sectors = set()
        committed = {}
        blocked = None
        try:
            jobs = list(self.machine.get_queue() or [])
            current = self.machine.current_job()
            if current is not None:
                jobs.append(current)
                if getattr(current, "state", None) == "blocked" or getattr(current, "blocker", None):
                    blocked = current
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.queued_jobs_info: self.machine.get_queue", error)
            return None, {}, None
        for job in jobs:
            s = getattr(job, "sector", None)
            if s:
                sectors.add(s)
            if getattr(job, "action", None) == "plant":
                item_id = getattr(job, "item_id", None)
                if item_id:
                    committed[item_id] = committed.get(item_id, 0) + 1
        return sectors, committed, blocked

    def seed_stock_in_port(self, seed_id):
        """Physical seeds of seed_id currently inside the machine input port."""
        port = getattr(self.machine, "input", None)
        if not port:
            return 0
        try:
            return sum(getattr(st, "count", 0) for st in port.stacks() if getattr(st, "id", None) == seed_id)
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.seed_stock_in_port: port.stacks", error)
            return 0

    def unblock_queue(self, blocked_job, curr_tick):
        """Resolves or cancels a blocked FIFO head job so the executor doesn't freeze."""
        if blocked_job is None:
            return
        blocker = getattr(blocked_job, "blocker", None)
        job_id = getattr(blocked_job, "id", None)
        action = getattr(blocked_job, "action", "")
        sector = getattr(blocked_job, "sector", "?")
        item_id = getattr(blocked_job, "item_id", None)
        if blocker == "output_full":
            # Accepted: Forage waits here for a consumer, which drains
            # clogged automators first (storage.crop_automator_forage()).
            self.log.debug(f"[{self.name}] Output full: {action}@{sector} waits for a Forage pull.")
            return
        if blocker in QUIET_BLOCKERS:
            self.log.debug(f"[{self.name}] Head job {job_id} ({action}@{sector}) waits: {blocker}.")
            return
        self.log.level("warn").print(f"[{self.name}] Head job {job_id} ({action}@{sector}) blocked: {blocker}.")
        if blocker == "no_seed" and item_id:
            port = getattr(self.machine, "input", None)
            if port and take_item(port, item_id, 1) > 0:
                self.log.print(f"[{self.name}] Unblocked job {job_id}: loaded emergency seed '{item_id}'.")
                return
            if job_id is not None:
                res = self.machine.cancel_job(job_id)
                # Not requeued right away: the cell waits JOB_FAIL_COOLDOWN_TICKS.
                self._failed[sector] = curr_tick
                self.log.level("warn").print(f"[{self.name}] Canceled seed-starved plant job {job_id}@{sector} -> {getattr(res, 'status', '?')}.")

    def submit(self, method, *args):
        res = getattr(self.machine, method)(*args)
        status = getattr(res, "status", "?")
        if status != "queued":
            self.log.debug(f"[{self.name}] {method}{args} -> {status}: {getattr(res, 'message', '')}")
        return status == "queued"

    def output_forage(self):
        port = getattr(self.machine, "output", None)
        try:
            # OutputSlot.count() takes no item id; sum the Forage stacks instead.
            return int(sum(s.count for s in port.stacks() if s.id == "forage")) if port else 0
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.output_forage: port.stacks", error)
            return 0

    def in_garden(self):
        _r, c = field_layout.sector_to_rc(self.sector) if self.sector else (None, None)
        return c is not None and c <= field_layout.GARDEN_COLS

    # ----------------------------------------------------------------- step

    def step(self):
        curr_tick = self.get_current_tick()
        if not self.sector:
            self.sector = self._read_sector()
        self.consume_results(curr_tick)

        layout = archive.get(LAYOUT_KEY, {})
        layout = layout if isinstance(layout, dict) else {}
        layout_cells = layout.get("cells") or {}
        if layout.get("mode") != "full" or not layout_cells:
            self._note_state("waiting for the full field layout (Harvester)")
            return
        if self.is_shedded():
            self._note_state("shed by the Power Guard: no new jobs")
            return

        rules = field_layout.rules_from_published(archive.get(RECIPES_KEY, {}))
        deployed = self.deployed_machines()
        automators = [s for s, k in deployed.items() if k == "crop_automator"] or [self.sector]
        self.refresh_seed_demand_if_stale(curr_tick, layout, rules, automators)
        mine = self.owned_cells(layout_cells, automators)
        queued, committed_seeds, blocked_job = self.queued_jobs_info()
        if queued is None:
            return
        self.unblock_queue(blocked_job, curr_tick)
        try:
            room = QUEUE_LIMIT - self.machine.queue_count()
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.step: self.machine.queue_count", error)
            room = 0
        cells = {}
        try:
            for c in self.machine.cells():
                cells[getattr(c, "id", None)] = c
        except Exception as e:
            self.log.debug(f"[{self.name}] cells() failed: {e}")
            return

        garden = set(layout.get("garden") or [])
        mature = []
        open_cells = []
        waiting = []
        for sector in mine:
            if sector in queued or curr_tick - self._failed.get(sector, -JOB_FAIL_COOLDOWN_TICKS) < JOB_FAIL_COOLDOWN_TICKS:
                continue
            cell = cells.get(sector)
            status = getattr(cell, "status", "unknown")
            species = layout_cells[sector]
            plant = getattr(cell, "plant", None)
            growth = getattr(cell, "growth", 0) or 0
            if (status == "mature" or growth >= 1.0) and plant:
                if not field_layout.kept_crop(sector, plant, layout_cells, garden):
                    mature.append(sector)
            elif status in ("empty", "unknown"):
                if self.services_ready(sector, species, rules, deployed):
                    open_cells.append(sector)
                else:
                    waiting.append(sector)
        self.log.debug(f"[{self.name}] owns {len(mine)} cell(s): {len(mature)} mature, {len(open_cells)} open, "
                       f"{len(waiting)} waiting for machines, queue room {room}.")

        for sector in mature:
            if room <= 0:
                break
            if self.submit("harvest", sector):
                room -= 1
        for sector in open_cells:
            if room <= 0:
                break
            species = layout_cells[sector]
            seed_id = (rules.get(species) or {}).get("seed_id") or "seed_" + species
            in_port = self.seed_stock_in_port(seed_id)
            in_flight = committed_seeds.get(seed_id, 0)
            available = in_port - in_flight
            if available < 1:
                port = getattr(self.machine, "input", None)
                if port:
                    pulled = take_item(port, seed_id, SEED_PULL_BATCH)
                    if pulled:
                        self.log.debug(f"[{self.name}] Batch-loaded {pulled}x {seed_id}.")
                        available += pulled
            if available < 1:
                continue
            if self.submit("plant", sector, seed_id):
                room -= 1
                committed_seeds[seed_id] = committed_seeds.get(seed_id, 0) + 1
        self._note_state(f"{len(mine)} cell(s), {len(mature)} to harvest, {len(open_cells)} to plant, {len(waiting)} waiting for machines")
        self.publish(curr_tick, mine, mature, open_cells, waiting)

    def _note_state(self, text):
        if text != self._last_state:
            self.log.print(f"[{self.name}] {text}.")
            self._last_state = text

    def publish(self, curr_tick, mine, mature, open_cells, waiting):
        if curr_tick - self._last_publish_tick < PUBLISH_INTERVAL_TICKS:
            return
        self._last_publish_tick = curr_tick
        try:
            status = self.machine.status()
            queue = self.machine.queue_count()
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.publish: self.machine.status", error)
            status, queue = "?", None
        entry = {"sector": self.sector, "status": status, "queue": queue, "cells": len(mine),
                 "mature": len(mature), "open": len(open_cells), "waiting_machines": len(waiting),
                 "forage": self.output_forage(), "garden": self.in_garden(), "tick": curr_tick}

        def updater(state):
            if not isinstance(state, dict):
                state = {}
            state[self.name] = entry
            for k in [k for k, e in state.items()
                      if k != self.name and (not isinstance(e, dict) or curr_tick - (e.get("tick") or 0) > STATUS_STALE_TICKS)]:
                state.pop(k, None)
            return state

        archive.transaction(STATUS_KEY, {}, updater)

    def run(self):
        self.log.print(f"Crop Automator ({self.name}) online at {self.sector}.")
        validate_game_version()
        while True:
            try:
                self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Crop Automator exception: {e}")
            sleep(POLL_INTERVAL_S)
