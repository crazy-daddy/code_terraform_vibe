# Crop Automator: harvests and replants the full-layout cells in its 5 x 5
# area (thin entrypoint harvesting/crop_automator.py). Deployed by the
# Harvester on the cells the full layout reserves for it
# (lib/harvester_machines.py); the kits come from the Shop.
#
# Each step (POLL_INTERVAL_S):
#   0. the deployed-machine map, owned cells and per-cell service checks are
#      cached for DEPLOYED_CACHE_TICKS (or until the layout size changes);
#      a step that queued nothing with an empty queue sleeps IDLE_POLL_SECONDS
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
#      growth >= 1.0) the output has room for, except garden crops (field_layout.kept_crop()): they
#      are planted once and never harvested, since a mature crop still
#      counts toward the species multiplier. A garden automator only plants.
#      Output room: a harvest that finds the output short keeps what fits
#      and discards the rest (result "partial"), so harvests are only queued
#      while free output space covers one learned harvest yield each
#      (harvest_budget(); yield = largest recent harvest, HARVEST_YIELD_*).
#      Queued harvests beyond that budget are canceled (trim_harvests());
#      the cell stays mature until room frees up.
#   6. plant every open layout cell it owns, once the machines beside the
#      cell give every care service the species needs (Crop Automators only
#      apply Fertilizer / Growth Accelerant: light, water and salt must come
#      from Grow Lamps, Sprinklers and Dispensers). Seeds in the input are
#      netted against plant jobs already queued (queued_jobs_info()); when
#      none are spare, SEED_PULL_BATCH are loaded at once from Inventory /
#      home Warehouses (storage.take_item()) instead of one per job. The
#      Harvester's plant.seed_demand covers the automated cells, so the Seed
#      Maker makes them.
#   7. Forage stays in its output (up to OUTPUT_CAP units): no drain to
#      Warehouses, so auto-loaders stay free. A clogged automator is
#      accepted over clogged Warehouses. Consumers (the Plant Terraformer via
#      storage.take_item()) take it from there directly, after any Forage in
#      Inventory or Warehouses, clogged automators first
#      (storage.crop_automator_forage()). An automator parked with
#      mature crops waiting for room is woken by take_item() only once the
#      pull leaves room for one harvest (storage.crop_automator_wake_free()).
# Nothing is queued while the Power Guard has shed it (`power.shedded`) or
# while the layout is still the starter one. Loose items on its cells are
# swept by the Harvester (a plant job needs an empty cell).
#
# Telemetry: `plant.automators` = {machine_id: {"sector", "status", "queue",
# "cells", "mature", "open", "waiting_machines", "forage", "harvest_yield",
# "garden", "tick"}} (one shared dict, stale entries pruned). "forage" =
# Forage in the output; "harvest_yield" = the learned Forage per harvest;
# "garden" = the automator sits in the diversity garden (columns
# 1..field_layout.garden_cols(fill)), read by storage.crop_automator_forage().
# An automator the full layout doesn't reserve (left over from an older
# layout) queues no jobs; the Harvester removes it once its output is empty.

from archive import archive
import field_layout
from storage import take_item, hit_slot_cap, eject_unneeded
from seed_supply import seed_buffer
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from script_parking import ParkRequester
from version_guard import validate_game_version
from game_clock import now_tick

LAYOUT_KEY = "plant.layout"        # same key as harvester_planting.LAYOUT_KEY
RECIPES_KEY = "plant.recipes"      # same key as seed_supply.RECIPES_KEY
SEED_DEMAND_KEY = "plant.seed_demand"  # same key as seed_supply.SEED_DEMAND_KEY
STATUS_KEY = "plant.automators"

POLL_INTERVAL_S = 10.0             # while jobs are queued or being consumed
IDLE_POLL_SECONDS = 30.0           # nothing queued, nothing to do: poll less often
DEPLOYED_CACHE_TICKS = 600         # deployed-machine map, owned cells and service checks are reused this long (~1 min)
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
OUTPUT_CAP = 50000                 # output buffer (docs/components/crop_automator.md)
HARVEST_YIELD_DEFAULT = 1000       # Forage per harvest until one is seen (Crowncap ~900 with the Yield Amplifier)
HARVEST_YIELD_DECAY = 0.95         # per harvest seen: estimate = max(this harvest, estimate x decay)


def _position(ref):
    return getattr(ref, "position", None)


class CropAutomatorController:
    """Queues harvest and plant jobs for the full-layout cells this Crop Automator owns."""

    def __init__(self, machine: "CropAutomator"):
        self.machine = machine
        self.name = getattr(machine, "id", "crop_automator")
        self.parker = ParkRequester(self.name, "crop_automator")
        self.parkable = False  # set by step(): in the layout, not shed, nothing queued or finished
        self.log = TreeConsole(module="crop_automator")
        self.sector = self._read_sector()
        self._failed = {}                  # {sector: tick of last failed job}
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self._last_state = None
        self._deployed = None              # cached deployed_machines()
        self._deployed_tick = None
        self._deployed_sig = None
        self._automators = []
        self._mine = []
        self._ready = {}                   # {(sector, species): services_ready}
        self._harvest_yield = HARVEST_YIELD_DEFAULT  # learned Forage per harvest (learn_yield())

    def get_current_tick(self):
        return now_tick()

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

    def _cached_ready(self, sector, species, rules, deployed):
        key = (sector, species)
        ready = self._ready.get(key)
        if ready is None:
            ready = self._ready[key] = self.services_ready(sector, species, rules, deployed)
        return ready

    def _field_view(self, curr_tick, layout_cells, reserved):
        """(deployed, automators, mine), reused for DEPLOYED_CACHE_TICKS unless the layout size changed."""
        sig = (len(layout_cells), len(reserved))
        if (self._deployed is not None and sig == self._deployed_sig
                and curr_tick - self._deployed_tick < DEPLOYED_CACHE_TICKS):
            return self._deployed, self._automators, self._mine
        deployed = self.deployed_machines()
        automators = [s for s, k in deployed.items() if k == "crop_automator" and reserved.get(s) == "crop_automator"] or [self.sector]
        mine = self.owned_cells(layout_cells, automators)
        if deployed:
            self._deployed, self._deployed_tick, self._deployed_sig = deployed, curr_tick, sig
            self._automators, self._mine = automators, mine
            self._ready = {}
        return deployed, automators, mine

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
        """Drains finished job results; returns how many were consumed."""
        self.log.start(f"[{self.name}] consume_results", level="debug")
        consumed = 0
        for _ in range(MAX_RESULTS_PER_STEP):
            try:
                if self.machine.result_count() <= 0:
                    break
                res = self.machine.next_result()
            except Exception as e:
                self.log.debug(f"next_result() failed: {e}")
                break
            status = getattr(res, "status", "?")
            if status == "empty":
                break
            consumed += 1
            action = getattr(res, "action", None)
            sector = getattr(res, "sector", None)
            if action == "harvest" and status in ("ok", "partial"):
                self.learn_yield((getattr(res, "collected", 0) or 0) + (getattr(res, "discarded", 0) or 0))
            if status == "ok":
                collected = getattr(res, "collected", 0) or 0
                self.log.debug(f"{action} {sector} ok{' +' + str(collected) + ' Forage' if collected else ''}.")
            elif status == "partial":
                self.log.level("warn").print(f"[{self.name}] Harvest {sector}: output full, kept {getattr(res, 'collected', 0)}, discarded {getattr(res, 'discarded', 0)} Forage.")
            else:
                self.log.debug(f"{action} {sector} -> {status}: {getattr(res, 'message', '')}")
                if sector:
                    self._failed[sector] = curr_tick
        self.log.end()
        return consumed

    def learn_yield(self, harvested):
        """Feeds one harvest's Forage (kept + discarded) into the yield estimate."""
        if harvested <= 0:
            return
        estimate = max(int(harvested), int(self._harvest_yield * HARVEST_YIELD_DECAY))
        if estimate != self._harvest_yield:
            self.log.trace(f"[{self.name}] Harvest yield estimate {self._harvest_yield} -> {estimate} Forage.")
        self._harvest_yield = estimate

    def harvest_budget(self):
        """(harvests the free output space holds at the learned yield, free units)."""
        free = OUTPUT_CAP - self.output_forage()
        return max(0, free // max(1, self._harvest_yield)), free

    def queued_jobs_info(self):
        """
        Returns (queued_sectors: set, committed_seeds: dict[seed_id, int],
        blocked_job: CropJob | None, harvests: list[CropJob]); harvests in
        FIFO order, the active job first.
        """
        sectors = set()
        committed = {}
        blocked = None
        try:
            jobs = list(self.machine.get_queue() or [])
            current = self.machine.current_job()
            if current is not None:
                jobs.insert(0, current)
                if getattr(current, "state", None) == "blocked" or getattr(current, "blocker", None):
                    blocked = current
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.queued_jobs_info: self.machine.get_queue", error)
            return None, {}, None, []
        harvests = [job for job in jobs if getattr(job, "action", None) == "harvest"]
        for job in jobs:
            s = getattr(job, "sector", None)
            if s:
                sectors.add(s)
            if getattr(job, "action", None) == "plant":
                item_id = getattr(job, "item_id", None)
                if item_id:
                    committed[item_id] = committed.get(item_id, 0) + 1
        return sectors, committed, blocked, harvests

    def trim_harvests(self, harvests, budget, queued):
        """
        Cancels queued harvests (FIFO) beyond `budget`, so none runs into a
        full output and discards Forage. A harvest already working is left
        to finish. Canceled
        sectors leave `queued`. Returns (harvests still queued, canceled jobs).
        """
        kept = 0
        canceled = []
        for job in harvests:
            running = getattr(job, "state", None) == "working" and not getattr(job, "blocker", None)
            job_id = getattr(job, "id", None)
            if kept < budget or running or job_id is None:
                kept += 1
                continue
            res = self.machine.cancel_job(job_id)
            sector = getattr(job, "sector", None)
            if getattr(res, "status", None) == "ok":
                queued.discard(sector)
                canceled.append(job)
            else:
                kept += 1
                self.log.debug(f"[{self.name}] cancel_job({job_id}) for harvest {sector} -> {getattr(res, 'status', '?')}.")
        if canceled:
            self.log.debug(f"[{self.name}] Output room for {budget} harvest(s): canceled {len(canceled)} queued harvest(s) "
                           f"{[getattr(job, 'sector', '?') for job in canceled]}.")
        return kept, canceled

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

    def eject_unused_seeds(self, mine, layout_cells, rules):
        """Ejects seeds no owned cell plants to Inventory, freeing material slots; other inputs (Fertilizer) stay."""
        port = getattr(self.machine, "input", None)
        if not port:
            return
        keep = set()
        for sector in mine:
            species = layout_cells.get(sector)
            if species:
                keep.add((rules.get(species) or {}).get("seed_id") or "seed_" + species)
        try:
            keep.update(st.id for st in port.stacks() if not st.id.startswith("seed_"))
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.eject_unused_seeds: port.stacks", error)
            return
        ejected = eject_unneeded(port, keep, "inventory")
        if ejected:
            self.log.print(f"[{self.name}] Input material slots full: ejected unused seeds {', '.join(ejected)}.")

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
        self.log.start(f"[{self.name}] Unblocking head job {job_id} ({action}@{sector})")
        self.log.level("warn").print(f"[{self.name}] Head job {job_id} ({action}@{sector}) blocked: {blocker}.")
        outcome = f"Left blocked ({blocker})"
        if blocker == "no_seed" and item_id:
            outcome = self._resolve_no_seed(job_id, sector, item_id, curr_tick) or outcome
        self.log.end(outcome)

    def _resolve_no_seed(self, job_id, sector, item_id, curr_tick):
        """Loads one seed for a seed-starved head job, else cancels it. Returns the outcome, or None if neither applied."""
        port = getattr(self.machine, "input", None)
        if port and take_item(port, item_id, 1) > 0:
            self.log.print(f"[{self.name}] Unblocked job {job_id}: loaded emergency seed '{item_id}'.")
            return "Unblocked with an emergency seed"
        if job_id is not None:
            res = self.machine.cancel_job(job_id)
            # Not requeued right away: the cell waits JOB_FAIL_COOLDOWN_TICKS.
            self._failed[sector] = curr_tick
            self.log.level("warn").print(f"[{self.name}] Canceled seed-starved plant job {job_id}@{sector} -> {getattr(res, 'status', '?')}.")
            return "Canceled the seed-starved job"
        return None

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

    def empty_for_removal(self):
        """
        Stray (not in the layout): clears the job queue and ejects the input
        (seeds, Fertilizer) to Inventory, so the Harvester can undeploy it
        once the output's Forage has drained (eject() is self-only).
        """
        try:
            if self.machine.queue_count():
                res = self.machine.clear_queue()
                self.log.print(f"[{self.name}] Not in the field layout: cleared the job queue -> {getattr(res, 'status', '?')}.")
            port = self.machine.input
            for stack in port.stacks():
                res = port.eject("inventory", stack.id, stack.count)
                self.log.print(f"[{self.name}] Not in the field layout: ejected {stack.count} {stack.id} to Inventory -> {getattr(res, 'status', '?')}.")
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.empty_for_removal: machine", error)

    def in_garden(self):
        _r, c = field_layout.sector_to_rc(self.sector) if self.sector else (None, None)
        layout = archive.get(LAYOUT_KEY, {})
        fill = layout.get("fill") if isinstance(layout, dict) else None
        return c is not None and c <= field_layout.garden_cols(fill)

    # ----------------------------------------------------------------- step

    def step(self):
        """One poll. Returns True while it has work in flight (results, queued jobs, new jobs)."""
        self.parkable = False
        curr_tick = self.get_current_tick()
        if not self.sector:
            self.sector = self._read_sector()
        consumed = self.consume_results(curr_tick) > 0
        busy = consumed

        layout = archive.get(LAYOUT_KEY, {})
        layout = layout if isinstance(layout, dict) else {}
        layout_cells = layout.get("cells") or {}
        if layout.get("mode") != "full" or not layout_cells:
            self._note_state("waiting for the full field layout (Harvester)")
            return busy
        reserved = layout.get("reserved") or {}
        if reserved.get(self.sector) != "crop_automator":
            self._note_state("not in the field layout: no jobs, input emptied (the Harvester removes it)")
            self.empty_for_removal()
            return busy
        if self.is_shedded():
            self._note_state("shed by the Power Guard: no new jobs")
            return busy

        rules = field_layout.rules_from_published(archive.get(RECIPES_KEY, {}))
        deployed, automators, mine = self._field_view(curr_tick, layout_cells, reserved)
        self.refresh_seed_demand_if_stale(curr_tick, layout, rules, automators)
        queued, committed_seeds, blocked_job, harvests = self.queued_jobs_info()
        if queued is None:
            return True
        budget, free = self.harvest_budget()
        harvests_queued, canceled = self.trim_harvests(harvests, budget, queued)
        harvest_room = max(0, budget - harvests_queued)
        if blocked_job is not None and blocked_job in canceled:
            blocked_job = None
        if blocked_job is not None:
            busy = True
            self.unblock_queue(blocked_job, curr_tick)
        try:
            queue_count = self.machine.queue_count()
            room = QUEUE_LIMIT - queue_count
        except Exception as error:
            swallowed("crop_automator.CropAutomatorController.step: self.machine.queue_count", error)
            queue_count, room = 1, 0
        if queue_count or queued:
            busy = True
        try:
            cells = {getattr(c, "id", None): c for c in self.machine.cells()}
        except Exception as e:
            self.log.debug(f"[{self.name}] cells() failed: {e}")
            return True

        garden = set(layout.get("garden") or [])
        failed = self._failed
        mature = []
        open_cells = []
        waiting = []
        for sector in mine:
            if sector in queued:
                continue
            failed_at = failed.get(sector)
            if failed_at is not None and curr_tick - failed_at < JOB_FAIL_COOLDOWN_TICKS:
                continue
            species = layout_cells.get(sector)
            if species is None:
                continue
            cell = cells.get(sector)
            status = getattr(cell, "status", "unknown")
            plant = getattr(cell, "plant", None)
            if plant and (status == "mature" or (getattr(cell, "growth", 0) or 0) >= 1.0):
                if not field_layout.kept_crop(sector, plant, layout_cells, garden):
                    mature.append(sector)
            elif status == "empty" or status == "unknown":
                if self._cached_ready(sector, species, rules, deployed):
                    open_cells.append(sector)
                else:
                    waiting.append(sector)
        self.log.debug(f"[{self.name}] owns {len(mine)} cell(s): {len(mature)} mature, {len(open_cells)} open, "
                       f"{len(waiting)} waiting for machines, queue room {room}, output free {free} "
                       f"= room for {harvest_room} more harvest(s) at {self._harvest_yield} Forage each.")

        for sector in mature:
            if room <= 0 or harvest_room <= 0:
                break
            if self.submit("harvest", sector):
                room -= 1
                harvest_room -= 1
                busy = True
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
                    report = {}
                    pulled = take_item(port, seed_id, SEED_PULL_BATCH, report=report)
                    if pulled:
                        self.log.debug(f"[{self.name}] Batch-loaded {pulled}x {seed_id}.")
                        available += pulled
                    elif hit_slot_cap(report):
                        self.eject_unused_seeds(mine, layout_cells, rules)
            if available < 1:
                continue
            if self.submit("plant", sector, seed_id):
                room -= 1
                busy = True
                committed_seeds[seed_id] = committed_seeds.get(seed_id, 0) + 1
        full = " (output full)" if mature and harvest_room <= 0 else ""
        self._note_state(f"{len(mine)} cell(s), {len(mature)} to harvest{full}, {len(open_cells)} to plant, {len(waiting)} waiting for machines")
        self.publish(curr_tick, mine, mature, open_cells, waiting)
        # Mature crops waiting for output room are no work: it parks, and
        # storage.take_item() wakes it once a pull leaves room for a harvest.
        self.parkable = not busy
        return busy

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
                 "forage": self.output_forage(), "harvest_yield": self._harvest_yield, "garden": self.in_garden(), "tick": curr_tick}

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
            reset_all()
            busy = True
            try:
                busy = self.step()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Crop Automator exception: {e}")
                self.parkable = False
            self.parker.update(self.parkable)
            flush_all()
            sleep(POLL_INTERVAL_S if busy else IDLE_POLL_SECONDS)
