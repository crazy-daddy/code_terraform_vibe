# Planting Harvester: keeps the field layout planted, tended and harvested.
#
# Composition (vehicle-mixin style, `_host` self-typing property):
#   HarvesterHeatMixin     (lib/harvester_heat.py)     -- heat-cheapest routes, just-in-time rests
#   HarvesterPavingMixin   (lib/harvester_paving.py)   -- items on a path joining the plant patches (+1 heat instead of +7)
#   HarvesterPlantingMixin (lib/harvester_planting.py) -- layout, seed demand, plant, harvest
#   HarvesterCareMixin     (lib/harvester_care.py)     -- light/water/salt, salt request
#   HarvesterMachinesMixin (lib/harvester_machines.py) -- field-machine kit orders, deploy on reserved cells
#   HarvesterController    (lib/harvesting.py)         -- movement, heat, loose-item sweep
#
# Each step re-reads cells() and does the single most urgent task, cheapest
# route (heat) first within a priority:
#   1. full layout: build in field_layout.work_order() (garden row by row in
#      a snake, then the fill chunk by chunk): deploy a machine kit (Grow
#      Lamp / Sprinkler / Dispenser / Crop Automator) on its reserved cell,
#      or plant one of its own cells. First: every machine takes care work
#      off the Harvester for good, and behind care it never ran
#   2. care tour: once any treatment drops below CARE_REFRESH_H, every
#      treatment below CARE_BATCH_H is renewed in one tour, so renewals line
#      up and the field needs fewer separate trips. Ahead of harvesting: a
#      lapsed treatment stalls growth, a mature crop just waits
#   3. harvest a mature crop (Forage lands in home Inventory)
#   4. uproot a growing plant in the layout's way (after a layout change;
#      the seed goes back to Inventory)
#   5. plant an open layout cell whose seed is at home (staged into Inventory)
# In the full layout, cells a deployed Crop Automator serves are its work
# (lib/crop_automator.py): the Harvester only plants and harvests the rest.
#   6. with heat headroom: pave a path cell (carry a loose item there, or
#      drop a cheap seed), else collect a loose item off the path (seeds from
#      an older layout's path come back to Inventory this way)
#   7. wait where it stands (no trip back to the base pad: it costs heat and
#      nothing needs the base)
# Standing on a cell for any reason, every treatment below CARE_BATCH_H there
# is renewed right away, since it costs no extra move. Passing through a
# layout cell on a route, a mature crop there is harvested and an open cell
# planted if it is one of the Harvester's own cells
# (harvester_planting.work_on_pass()): the next pass costs +1 heat, not +7.
#
# Telemetry: `plant.status` = {harvester_id: {...}} (one shared dict).

from archive import archive
import field_layout
from harvesting import HarvesterController
from harvester_heat import HarvesterHeatMixin
from harvester_paving import HarvesterPavingMixin
from harvester_planting import HarvesterPlantingMixin
from harvester_care import HarvesterCareMixin, CARE_BATCH_H
from harvester_machines import HarvesterMachinesMixin
from storage import total_stock, discover_storage_buildings
from tree_console import TreeConsole
from version_guard import validate_game_version

STATUS_KEY = "plant.status"

PUBLISH_INTERVAL_TICKS = 600   # seed demand / salt request / status at most once a minute
LAYOUT_RECHECK_TICKS = 3000    # re-check layout mode (automation research) and chunks (~5 min)
IDLE_POLL_SECONDS = 10.0       # nothing due: re-check this often
ACTION_RETRIES = 3             # busy/moving retries per Harvester action
INVENTORY_FULL_RETRY_TICKS = 3000  # after "inventory_full", skip harvesting this long (~5 min)
ITEM_SWEEP_MAX_HEAT = 40.0     # loose items only while heat is at most this (keep headroom for crops)


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
        return 0


def _home_outpost_id():
    network = get_component("outpost_network")
    if not network:
        return None
    try:
        for o in network.outposts():
            if getattr(o, "is_home", False):
                return o.id
    except Exception:
        pass
    return None


class FieldKeeperController(HarvesterHeatMixin, HarvesterPavingMixin, HarvesterPlantingMixin, HarvesterCareMixin, HarvesterMachinesMixin, HarvesterController):
    """Plants, tends and harvests the field layout; falls back to the loose-item sweep."""

    def __init__(self, harvester):
        super().__init__(harvester)
        self.log = TreeConsole(module="field_keeper")
        self.home_id = _home_outpost_id()
        self.last_action = ""
        self.inventory_full_tick: "int | None" = None
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self.care_batch = {}
        # Per-step caches (the script has a step budget per tick; see step()).
        self.stock_memo = {}
        self.step_statuses: "dict | None" = None
        self._rules = None
        self._rules_tick = -PUBLISH_INTERVAL_TICKS
        self._layout = None
        self._layout_tick = -LAYOUT_RECHECK_TICKS
        self.layout_mode = "starter"   # set by load_layout()
        self.reserved = {}             # {sector: machine kind}, set by load_layout()
        self.garden = []               # garden sectors, set by load_layout()
        self.work_groups = []          # field_layout.work_order() of the full layout
        self.step_mine = {}            # this step's harvester_layout(), for work_on_pass()
        self.step_machine_map = None   # deployed field machines, read once per step
        saved = archive.get(STATUS_KEY, {})
        self.init_heat_model((saved.get(self.name) or {}).get("heat") if isinstance(saved, dict) else None)

    # -------------------------------------------------------------- helpers

    def inventory_count(self, item_id):
        inventory = get_component("inventory")
        if not inventory:
            return 0
        try:
            return int(inventory.count(item_id))
        except Exception:
            return 0

    def stock_count(self, item_id):
        """
        Home stock of item_id (Inventory + home Warehouses), memoised per
        step: each total_stock() walks every Warehouse, and one step asks for
        up to 24 seeds, which burned the script's per-tick step budget.
        """
        found = self.stock_memo.get(item_id)
        if found is None:
            found = total_stock(item_id)
            self.stock_memo[item_id] = found
        return found

    def stage(self, item_id, n=1):
        """
        Pulls item_id from a home Warehouse into Inventory until n are there.
        Seeds and salt are kept in Warehouses so they don't clutter Inventory,
        but load_seed()/dispense_salt() read Inventory only, so each is staged
        right before use. The rebalance sweep may move a leftover back later.
        """
        missing = n - self.inventory_count(item_id)
        if missing <= 0:
            return True
        self.stock_memo.pop(item_id, None)
        for building in discover_storage_buildings():
            component = building["component"]
            try:
                if component.count(item_id) <= 0:
                    continue
                res = component.transfer_to("inventory", item_id, missing)
            except Exception as e:
                self.log.debug(f"[{self.name}] stage '{item_id}' from '{building['id']}' raised: {e}")
                continue
            missing -= getattr(res, "moved", 0) or 0
            if missing <= 0:
                self.log.debug(f"[{self.name}] Staged {n}x '{item_id}' into Inventory.")
                return True
        self.log.debug(f"[{self.name}] Could not stage '{item_id}': {missing} short.")
        return missing <= 0

    def act(self, method, *args):
        """
        Calls a Harvester action: rests first if its (learned) heat cost would
        cross the cap, measures that cost on success, cools on "overheated"
        and retries "busy"/"moving".
        """
        fn = getattr(self.harvester, method, None)
        if fn is None:
            return None
        res = None
        for _ in range(ACTION_RETRIES):
            self.ensure_headroom(self.action_cost(method))
            before = self.get_heat()
            res = fn(*args)
            status = getattr(res, "status", "")
            if status in ("ok", "partial", "dropped"):
                self.learn_action(method, before, self.get_heat())
                return res
            if status == "overheated":
                self.cool_down()
            elif status in ("busy", "moving"):
                sleep(1.0)
            else:
                return res
        return res

    def read_cells(self):
        try:
            return {c.id: c for c in self.harvester.cells()}
        except Exception as e:
            self.log.debug(f"[{self.name}] cells() failed: {e}")
            return {}

    def nearest(self, sectors, cells):
        """Target with the heat-cheapest route from here."""
        statuses = self.step_statuses
        if statuses is None:
            statuses = {s: getattr(c, "status", None) for s, c in cells.items()}
        return self.cheapest(sectors, statuses)

    def publish(self, active, layout, cells, rules, spare_items, curr_tick, force=False):
        if not force and curr_tick - self._last_publish_tick < PUBLISH_INTERVAL_TICKS:
            return
        self._last_publish_tick = curr_tick
        now, rotation = self.seed_demand(self.seed_layout(active, self.step_mine), cells, rules)
        for seed_id, n in self.paving_seed_demand(layout, cells, rules, len(spare_items)).items():
            now[seed_id] = now.get(seed_id, 0) + n
        self.publish_seed_demand(now, rotation, curr_tick)
        self.publish_salt_request(layout, rules, self.home_id, curr_tick)
        kit_order, automators_wanted = self.publish_kit_order(cells)

        counts = {"growing": 0, "stalled": 0, "mature": 0}
        productive = set()
        for c in cells.values():
            st = getattr(c, "status", "")
            if st in counts:
                counts[st] += 1
                if st != "stalled" and getattr(c, "plant", None):
                    productive.add(c.plant)
        entry = {
            "planted": counts["growing"] + counts["stalled"] + counts["mature"],
            "mature": counts["mature"],
            "stalled": counts["stalled"],
            "species_productive": len(productive),
            "layout": len(layout),
            "active": len(active),
            "care_due": len(self.care_targets(cells, rules)),
            "unpaved": len(self.unpaved(layout, cells)),
            "mode": self.layout_mode,
            "machines_missing": len(self.missing_machines(cells)),
            "kit_order": kit_order,
            "automators_wanted": automators_wanted,
            "last_action": self.last_action,
            "heat": self.heat_model(),
            "tick": curr_tick,
        }

        def updater(status):
            if not isinstance(status, dict):
                status = {}
            status[self.name] = entry
            return status

        archive.transaction(STATUS_KEY, {}, updater)
        self.log.debug(f"[{self.name}] demand now={now} rotation={len(rotation)} species; status={entry}")

    # ----------------------------------------------------------------- loop

    def step(self):
        curr_tick = _now_tick()
        self.stock_memo = {}
        self.step_statuses = None
        self.step_machine_map = None
        cells = self.read_cells()
        if not cells:
            sleep(IDLE_POLL_SECONDS)
            return
        # One statuses dict per step: target choice (nearest) and the route
        # (move_to) then share a single heat map.
        self.step_statuses = {s: getattr(c, "status", None) for s, c in cells.items()}
        self.base_sector = self.base_from_cells(cells)
        # Recipes change only when the Seed Maker republishes; the layout only
        # on the switch to full or a new chunk. Neither is re-read every step.
        if self._rules is None or curr_tick - self._rules_tick >= PUBLISH_INTERVAL_TICKS:
            self._rules = self.load_rules()
            self._rules_tick = curr_tick
        rules = self._rules
        if not self._layout or curr_tick - self._layout_tick >= LAYOUT_RECHECK_TICKS:
            self._layout = self.load_layout(cells, rules)
            self._layout_tick = curr_tick
            self.work_groups = field_layout.work_order(self._layout, self.reserved) if self.layout_mode == "full" else []
        layout = self._layout
        inactive = self.inactive_species(rules)
        active = self.active_layout(layout, rules, inactive)
        # The cells the Harvester plants itself (full layout: not automated).
        mine = self.harvester_layout(active, rules)
        self.step_mine = mine
        # Loose items off the path: paving material, else swept up. Items on
        # the path are its +1-heat roads and stay put.
        roads = set(self.road_cells(layout))
        spare_items = [s for s, c in cells.items() if getattr(c, "status", "") == "item" and s not in roads]
        self.publish(active, layout, cells, rules, spare_items, curr_tick)

        # Something left in the held slot (e.g. after a restart) goes back to Inventory.
        self.store_held_if_any()

        # 1. Full layout: build (deploy a machine whose kit is at home, or
        #    plant one of its own cells) in field_layout.work_order(): the
        #    garden row by row in a snake, then the fill chunk by chunk.
        #    Ahead of care: each machine takes a treatment (a Crop Automator a
        #    whole 5 x 5 area) off the Harvester for good, and behind care it
        #    never ran (hand care kept it busy).
        if self.layout_mode == "full":
            deploys = self.deploy_targets(cells)
            build = dict(self.plant_targets(mine, cells))
            build.update(deploys)
            if build:
                rank = self.build_rank()
                target = min(build, key=lambda s: (rank.get(s, 1 << 30), s))
                self.log.debug(f"[{self.name}] Build: {len(deploys)} machine / {len(build) - len(deploys)} plant cell(s) ready; next in order {target} ({build[target]}).")
                if self.move_to(target):
                    if target in deploys:
                        self.deploy_here(deploys[target])
                    elif self.plant_here(build[target]):
                        self.care_current(rules)
                return

        # 2. Care tour first: a lapsed treatment stalls growth, while a mature
        #    crop just waits with its Forage banked. Harvest-first starved care
        #    (7 plants stalled for a whole day with crops always mature).
        batch = self.care_targets(cells, rules, CARE_BATCH_H)
        self.care_batch = {s: k for s, k in batch.items() if s in self.care_batch}
        if not self.care_batch and self.care_targets(cells, rules):
            self.care_batch = batch
            self.log.debug(f"[{self.name}] Care tour: {len(batch)} cell(s) below {CARE_BATCH_H} h.")
        if self.care_batch:
            target = self.nearest(list(self.care_batch), cells)
            if self.move_to(target):
                self.care_here(self.care_batch[target])
            self.care_batch.pop(target, None)
            return

        # 3. Harvest (paused for a while after Inventory reported full).
        if self.inventory_full_tick is not None and curr_tick - self.inventory_full_tick >= INVENTORY_FULL_RETRY_TICKS:
            self.inventory_full_tick = None
        if self.inventory_full_tick is None:
            targets = self.harvest_targets(cells, layout)
            if targets:
                target = self.nearest(targets, cells)
                self.log.debug(f"[{self.name}] {len(targets)} mature crop(s); cheapest {target} (planned in {_now_tick() - curr_tick} ticks).")
                if self.move_to(target):
                    self.harvest_here()
                    self.plant_if_open(mine)
                    self.care_current(rules)
                return

        # 4. Clear plants in the layout's way (old layout after a version bump).
        targets = self.clear_targets(layout, cells)
        if targets:
            target = self.nearest(targets, cells)
            self.log.debug(f"[{self.name}] {len(targets)} plant(s) in the layout's way; cheapest {target}.")
            if self.move_to(target) and self.uproot_here():
                self.plant_if_open(mine)
            return

        # 5. Plant.
        targets = self.plant_targets(mine, cells)
        if targets:
            by_sector = dict(targets)
            target = self.nearest(list(by_sector), cells)
            self.log.debug(f"[{self.name}] {len(targets)} plantable cell(s); cheapest {target} ({by_sector[target]}, planned in {_now_tick() - curr_tick} ticks).")
            if self.move_to(target) and self.plant_here(by_sector[target]):
                self.care_current(rules)
            return

        # 6. With heat headroom: pave a path cell, else sweep a loose item.
        if self.get_heat() <= ITEM_SWEEP_MAX_HEAT and self.pave_step(layout, cells, rules, spare_items):
            return
        if spare_items and self.get_heat() <= ITEM_SWEEP_MAX_HEAT and not self.unpaved(layout, cells):
            target = self.nearest(spare_items, cells)
            self.log.debug(f"[{self.name}] Nothing to tend; collecting loose item off the path at {target}.")
            if self.move_to(target):
                self.collect_at_current()
            return

        # 7. Nothing due: wait in place and cool passively.
        sleep(IDLE_POLL_SECONDS)

    def plant_if_open(self, active):
        """After a harvest the cell is free: replant it on the spot if its seed is on hand."""
        here = self.get_position()
        species = active.get(here)
        if not species or self.stock_count("seed_" + species) < 1:
            return
        cell = self.harvester.cell(here)
        if getattr(cell, "status", "") in ("empty", "unknown"):
            self.plant_here(species)

    def care_current(self, rules):
        """Renews every treatment below CARE_BATCH_H on the current cell (no move needed)."""
        cell = self.harvester.cell(self.get_position())
        due = self.care_due(cell, rules, CARE_BATCH_H)
        if due:
            self.care_here(due)

    def run(self):
        self.log.print(f"Field Keeper ({self.name}) online. Home outpost: {self.home_id}.")
        validate_game_version()
        while True:
            try:
                self.step()
                sleep(0.5)
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Field Keeper exception: {e}")
                sleep(5.0)
