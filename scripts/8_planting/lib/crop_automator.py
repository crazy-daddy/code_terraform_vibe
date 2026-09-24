# Crop Automator: harvests and replants the full-layout cells in its 5 x 5
# area (thin entrypoint harvesting/crop_automator.py). Deployed by the
# Harvester on the cells the full layout reserves for it
# (lib/harvester_machines.py); the kits come from the Shop.
#
# Each step (POLL_INTERVAL_S):
#   1. consume finished job results (a full result inbox pauses the machine)
#   2. ownership: automator areas overlap, so every layout cell belongs to
#      the nearest deployed automator (Chebyshev distance, then Manhattan,
#      then sector id). Each automator only queues jobs for its own cells.
#   3. harvest every mature layout crop it owns
#   4. plant every open layout cell it owns, once the machines beside the
#      cell give every care service the species needs (Crop Automators only
#      apply Fertilizer / Growth Accelerant: light, water and salt must come
#      from Grow Lamps, Sprinklers and Dispensers). Seeds are loaded into
#      its input from Inventory / home Warehouses just before the job
#      (storage.take_item()); the Harvester's plant.seed_demand covers the
#      whole layout, so the Seed Maker makes them.
#   5. drain Forage from its output to home storage (Inventory first, then
#      Warehouses), where the Plant Terraformer takes it from
# Nothing is queued while the Power Guard has shed it (`power.shedded`) or
# while the layout is still the starter one. Loose items on its cells are
# swept by the Harvester (a plant job needs an empty cell).
#
# Telemetry: `plant.automators` = {machine_id: {"sector", "status", "queue",
# "cells", "mature", "open", "waiting_machines", "forage_out", "tick"}} (one
# shared dict, stale entries pruned).

from archive import archive
import field_layout
from storage import take_item, drain_port_to_storage
from tree_console import TreeConsole
from version_guard import validate_game_version

LAYOUT_KEY = "plant.layout"        # same key as harvester_planting.LAYOUT_KEY
RECIPES_KEY = "plant.recipes"      # same key as seed_supply.RECIPES_KEY
STATUS_KEY = "plant.automators"

POLL_INTERVAL_S = 10.0
PUBLISH_INTERVAL_TICKS = 600       # telemetry at most once a minute
STATUS_STALE_TICKS = 36000         # an automator silent this long (~1 h) is dropped from telemetry
QUEUE_LIMIT = 45                   # the machine takes 50; leave room for a manual job
OUTPUT_DRAIN_ABOVE = 100           # drain Forage once the output holds at least this much
JOB_FAIL_COOLDOWN_TICKS = 3000     # a cell whose job failed is left alone this long (~5 min)
MAX_RESULTS_PER_STEP = 50          # the inbox holds at most 50


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
        self._forage_out = 0
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self._last_state = None

    def get_current_tick(self):
        if self.clock and hasattr(self.clock, "tick"):
            try:
                return self.clock.tick()
            except Exception:
                pass
        return 0

    def _read_sector(self):
        try:
            return self.machine.position()
        except Exception:
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
        mine = []
        for sector in field_layout.automator_area(me):
            if sector not in layout_cells:
                continue
            r, c = field_layout.sector_to_rc(sector)
            if r is None or c is None:
                continue

            def rank(ca, r=r, c=c):
                ar, ac = field_layout.sector_to_rc(ca)
                if ar is None or ac is None:
                    return (99, 99, ca)
                return (max(abs(ar - r), abs(ac - c)), abs(ar - r) + abs(ac - c), ca)

            reach = [ca for ca in automators if sector in field_layout.automator_area(ca)]
            if reach and min(reach, key=rank) == me:
                mine.append(sector)
        return mine

    def services_ready(self, sector, species, rules, deployed):
        served = [field_layout.MACHINE_SERVICE.get(deployed.get(n) or "") for n in field_layout.neighbours(sector)]
        return all(k in served for k in field_layout.care_kinds(rules, species))

    def is_shedded(self):
        shedded = archive.get("power.shedded", [])
        return isinstance(shedded, list) and self.name in shedded

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

    def queued_sectors(self):
        out = set()
        try:
            jobs = list(self.machine.get_queue() or [])
            current = self.machine.current_job()
            if current is not None:
                jobs.append(current)
        except Exception:
            return None
        for job in jobs:
            out.add(getattr(job, "sector", None))
        return out

    def submit(self, method, *args):
        res = getattr(self.machine, method)(*args)
        status = getattr(res, "status", "?")
        if status != "queued":
            self.log.debug(f"[{self.name}] {method}{args} -> {status}: {getattr(res, 'message', '')}")
        return status == "queued"

    def ensure_seed(self, seed_id, need):
        """Loads seeds into the input until `need` are there. Returns True if at least one is."""
        port = getattr(self.machine, "input", None)
        if not port:
            return False
        try:
            have = sum(getattr(st, "count", 0) for st in port.stacks() if getattr(st, "id", None) == seed_id)
        except Exception:
            have = 0
        if have < need:
            moved = take_item(port, seed_id, need - have)
            if moved:
                self.log.debug(f"[{self.name}] Loaded {moved}x {seed_id} ({have} -> {have + moved}).")
            have += moved
        return have > 0

    def drain_output(self):
        port = getattr(self.machine, "output", None)
        try:
            if not port or port.count() < OUTPUT_DRAIN_ABOVE:
                return
        except Exception:
            return
        moved = drain_port_to_storage(port, allow_partial=True)
        if moved:
            self._forage_out += moved
            self.log.debug(f"[{self.name}] Sent {moved} Forage to storage.")
        else:
            self.log.debug(f"[{self.name}] Output holds Forage but no home storage has room.")

    # ----------------------------------------------------------------- step

    def step(self):
        curr_tick = self.get_current_tick()
        if not self.sector:
            self.sector = self._read_sector()
        self.consume_results(curr_tick)
        self.drain_output()

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
        mine = self.owned_cells(layout_cells, automators)
        queued = self.queued_sectors()
        if queued is None:
            return
        try:
            room = QUEUE_LIMIT - self.machine.queue_count()
        except Exception:
            room = 0
        cells = {}
        try:
            for c in self.machine.cells():
                cells[getattr(c, "id", None)] = c
        except Exception as e:
            self.log.debug(f"[{self.name}] cells() failed: {e}")
            return

        mature = []
        open_cells = []
        waiting = []
        for sector in mine:
            if sector in queued or curr_tick - self._failed.get(sector, -JOB_FAIL_COOLDOWN_TICKS) < JOB_FAIL_COOLDOWN_TICKS:
                continue
            cell = cells.get(sector)
            status = getattr(cell, "status", "unknown")
            species = layout_cells[sector]
            if status == "mature" and getattr(cell, "plant", None) == species:
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
            if not self.ensure_seed(seed_id, 1):
                continue
            if self.submit("plant", sector, seed_id):
                room -= 1
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
        except Exception:
            status, queue = "?", None
        entry = {"sector": self.sector, "status": status, "queue": queue, "cells": len(mine),
                 "mature": len(mature), "open": len(open_cells), "waiting_machines": len(waiting),
                 "forage_out": self._forage_out, "tick": curr_tick}

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
