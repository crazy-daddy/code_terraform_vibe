# Planting Harvester: keeps the field layout planted, tended and harvested.
#
# Composition (vehicle-mixin style, `_host` self-typing property):
#   HarvesterHeatMixin     (lib/harvester_heat.py)     -- heat-cheapest routes, just-in-time rests
#   HarvesterPavingMixin   (lib/harvester_paving.py)   -- items on a path joining the plant patches (+1 heat instead of +7)
#   HarvesterPlantingMixin (lib/harvester_planting.py) -- layout, seed demand, plant, harvest
#   HarvesterCareMixin     (lib/harvester_care.py)     -- light/water/salt, salt request
#   HarvesterMachinesMixin (lib/harvester_machines.py) -- field-machine kit orders, deploy on reserved cells, remove strays
#   HarvesterAmplifyMixin  (lib/harvester_amplify.py)  -- field-wide Yield Amplifier: apply, Fabricator order
#   HarvesterController    (lib/harvesting.py)         -- movement, heat, loose-item sweep
#
# Each step re-reads cells() and does the single most urgent task, cheapest
# route (heat) first within a priority:
#   A. Yield Amplifier: apply a dose once the last one ran out (no move;
#      conditions in lib/harvester_amplify.py)
#   0. full layout: remove a field machine the layout doesn't reserve
#      (left over from an older layout): it may sit on a layout cell, light
#      a shade crop or burn salt
#   1. full layout, build phase (a reserved machine is still missing): build
#      in field_layout.work_order() (garden row by row in a snake, then the
#      fill chunk by chunk): deploy a machine kit (Grow Lamp / Sprinkler /
#      Dispenser / Crop Automator) on its reserved cell, or plant one of its
#      own cells. First: every machine takes care work off the Harvester for
#      good, and behind care it never ran. Once every machine is in, the
#      machines do most of the work and this step is skipped: what is left
#      of the Harvester's cells goes through 2-5 like any other
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
from harvester_planting import HarvesterPlantingMixin, PLANT_STATUSES
from harvester_care import HarvesterCareMixin, CARE_BATCH_H
from harvester_machines import HarvesterMachinesMixin
from harvester_amplify import HarvesterAmplifyMixin
from storage import total_stock, discover_storage_buildings, mark_busy, recently_busy, inventory_count
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
from version_guard import validate_game_version
from game_clock import now_tick

STATUS_KEY = "plant.status"

PUBLISH_INTERVAL_TICKS = 600   # seed demand / salt request / status at most once a minute
LAYOUT_RECHECK_TICKS = 3000    # re-check layout mode (automation research) and chunks (~5 min)
IDLE_POLL_SECONDS = 3.0        # nothing due: re-check this often
LOOP_SLEEP_SECONDS = 0.2       # pause between steps
ACTION_RETRIES = 3             # busy/moving retries per Harvester action
INVENTORY_FULL_RETRY_TICKS = 3000  # after "inventory_full", skip harvesting this long (~5 min)
ITEM_SWEEP_MAX_HEAT = 40.0     # loose items only while heat is at most this (keep headroom for crops)
STAGE_STUCK_WARN_TICKS = 6000  # a Warehouse answering "busy" to staging this long (~10 min) gets one warning


def _home_outpost_id():
    network = get_component("outpost_network")
    if not network:
        return None
    try:
        for o in network.outposts():
            if getattr(o, "is_home", False):
                return o.id
    except Exception as error:
        swallowed("field_keeper._home_outpost_id: network.outposts", error)
    return None


class FieldKeeperController(HarvesterHeatMixin, HarvesterPavingMixin, HarvesterPlantingMixin, HarvesterCareMixin, HarvesterMachinesMixin, HarvesterAmplifyMixin, HarvesterController):
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
        self.stage_busy = False        # last failed stage(): every holder answered "busy"
        self.busy_since = {}           # {warehouse id: [first "busy" tick, warned]}, cleared on a non-busy answer
        self.step_statuses: "dict | None" = None
        self.step_view: "tuple | None" = None   # (cells, statuses, planted cells) of the current step
        self._rules = None
        self._rules_tick = -PUBLISH_INTERVAL_TICKS
        self._layout = None
        self._layout_tick = -LAYOUT_RECHECK_TICKS
        self.layout_mode = "starter"   # set by load_layout()
        self.reserved = {}             # {sector: machine kind}, set by load_layout()
        self.garden = []               # kept sectors (full garden / starter keepers), set by load_layout()
        self.work_groups = []          # field_layout.work_order() of the full layout
        self.step_mine = {}            # this step's harvester_layout(), for work_on_pass()
        self.step_machine_map = None   # deployed field machines, read once per step
        self.build_phase = None        # full layout: True while a reserved machine is missing
        self.step_start = 0            # tick the current step began (plan_note())
        self.step_mark = 0             # tick the last planning phase ended
        self.step_phases = []          # [(phase, ticks)] of the current step
        self.idle_since: "int | None" = None   # tick the current idle streak began
        saved = archive.get(STATUS_KEY, {})
        self.init_heat_model((saved.get(self.name) or {}).get("heat") if isinstance(saved, dict) else None)

    # -------------------------------------------------------------- helpers

    def inventory_count(self, item_id):
        return inventory_count(item_id)

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
        but load_seed()/dispense_salt()/amplify() read Inventory only, so each
        is staged right before use. The rebalance sweep may move a leftover
        back later. Warehouses that just answered "busy" (an Auto Feeder
        cycle) are tried last. On failure, self.stage_busy is True when every
        holder answered "busy" (a short wait fixes it); a Warehouse busy for
        STAGE_STUCK_WARN_TICKS gets one warning.
        """
        self.log.start(f"[{self.name}] stage", level="debug")
        self.stage_busy = False
        missing = n - self.inventory_count(item_id)
        if missing <= 0:
            self.log.end()
            return True
        self.stock_memo.pop(item_id, None)
        now = now_tick()
        holders = []
        for building in discover_storage_buildings():
            try:
                if building["component"].count(item_id) > 0:
                    holders.append(building)
            except Exception as error:
                swallowed("field_keeper.FieldKeeperController.stage: component.count", error)
        holders.sort(key=lambda b: 1 if recently_busy(b["id"], now) else 0)
        answers = []
        for building in holders:
            try:
                res = building["component"].transfer_to("inventory", item_id, missing)
            except Exception as error:
                swallowed("field_keeper.FieldKeeperController.stage: component.transfer_to", error)
                answers.append("error")
                continue
            status = getattr(res, "status", "")
            answers.append(status)
            self.note_busy(building["id"], status == "busy", now)
            self.log.debug(f"stage '{item_id}' from '{building['id']}': {status}, moved {getattr(res, 'moved', 0) or 0}.")
            missing -= getattr(res, "moved", 0) or 0
            if missing <= 0:
                self.log.debug(f"Staged {n}x '{item_id}' into Inventory.")
                self.log.end()
                return True
        self.stage_busy = bool(answers) and all(a == "busy" for a in answers)
        self.log.debug(f"Could not stage '{item_id}': {missing} short ({'all holders busy' if self.stage_busy else 'answers ' + str(answers or 'none: no Warehouse holds it')}).")
        self.log.end()
        return False

    def note_busy(self, building_id, busy, now):
        """Tracks how long building_id has answered "busy"; warns once past STAGE_STUCK_WARN_TICKS."""
        if not busy:
            self.busy_since.pop(building_id, None)
            return
        mark_busy(building_id, now)
        entry = self.busy_since.setdefault(building_id, [now, False])
        if not entry[1] and now - entry[0] >= STAGE_STUCK_WARN_TICKS:
            entry[1] = True
            self.log.level("warn").print(f"[{self.name}] Warehouse '{building_id}' busy for {self.game_time(now - entry[0])}: Auto Feeder stuck? Staging skips it while it stays busy.")

    def act(self, method, *args):
        """
        Calls a Harvester action: rests first if its (learned) heat cost would
        cross the cap, measures that cost on success, cools on "overheated"
        and retries "busy"/"moving".
        """
        fn = getattr(self.harvester, method, None)
        if fn is None:
            return None
        self.log.start(f"[{self.name}] {method}", level="debug")
        where = self.get_position()
        res = None
        for _ in range(ACTION_RETRIES):
            self.ensure_headroom(self.action_cost(method))
            before = self.get_heat()
            start_tick = now_tick()
            res = fn(*args)
            status = getattr(res, "status", "")
            took = self.game_time(now_tick() - start_tick)
            if status in ("ok", "partial", "dropped"):
                after = self.get_heat()
                self.learn_action(method, before, after)
                self.log.debug(f"at {where} -> {status} after {took}, heat {before:.1f} -> {after:.1f}.")
                self.log.end()
                return res
            self.log.debug(f"at {where} -> {status} after {took}: {getattr(res, 'message', '')}")
            if status == "overheated":
                self.cool_down()
            elif status in ("busy", "moving"):
                flush_all()
                sleep(1.0)
            else:
                self.log.end()
                return res
        self.log.end()
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
        unpaved = self.unpaved(layout, cells)
        for seed_id, n in self.paving_seed_demand(layout, cells, rules, len(spare_items), unpaved).items():
            now[seed_id] = now.get(seed_id, 0) + n
        self.publish_seed_demand(now, rotation, curr_tick, layout, rules)
        kit_order, automators_wanted = self.publish_kit_order(cells)
        amplifier_order = self.publish_amplifier_order(curr_tick)

        kept = self.kept_garden()
        scan = self.row_scan(cells, rules, kept)
        entry = {
            "planted": scan["planted"],
            "mature": scan["mature"],
            "stalled": scan["stalled"],
            "species_productive": scan["productive"],
            "layout": len(layout),
            "active": len(active),
            "care_due": len(self.care_targets(cells, rules, kept=kept)),
            "unpaved": len(unpaved),
            "mode": self.layout_mode,
            "machines_missing": len(self.missing_machines(cells)),
            "kit_order": kit_order,
            "automators_wanted": automators_wanted,
            "amplifier_order": amplifier_order,
            "amplifier_h": round(self.amplifier_hours(), 1),
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

    # ------------------------------------------------------ step profiling

    def mark(self, phase):
        """Ends a planning phase of the current step; plan_note() reports its ticks."""
        now = now_tick()
        self.step_phases.append((phase, now - self.step_mark))
        self.step_mark = now

    def plan_note(self):
        """
        "planned in <world time> (<ticks>: <phase> <ticks>, ...)" for the
        step's decision line. Planning runs on the script's step budget, so a
        step can take a sizeable part of a world hour before the Harvester
        moves. Also closes an idle streak.
        """
        self.mark("decide")
        total = sum(n for _, n in self.step_phases)
        parts = ", ".join(f"{phase} {n}" for phase, n in self.step_phases if n)
        note = f"planned in {self.game_time(total)} ({total} ticks{': ' + parts if parts else ''})"
        if self.idle_since is not None:
            note += f"; idle {self.game_time(self.step_start - self.idle_since)} before"
            self.idle_since = None
        return note

    def log_idle(self, cells, rules):
        """One debug line when an idle streak starts: why nothing is due and when care is next."""
        if self.idle_since is not None:
            return
        why = []
        hours = self.next_care_hours(cells, rules, self.kept_garden())
        why.append("no hand care kept up" if hours is None else f"next care in ~{hours:.1f} h")
        if self.inventory_full_tick is not None:
            why.append("harvest paused: Inventory full")
        self.log.debug(f"[{self.name}] Idle: nothing due ({', '.join(why)}); {self.plan_note()}; polling every {IDLE_POLL_SECONDS:.0f} s.")
        self.idle_since = self.step_start

    # ----------------------------------------------------------------- loop

    def step(self):
        curr_tick = now_tick()
        self.step_start = self.step_mark = curr_tick
        self.step_phases = []
        self.stock_memo = {}
        self.step_statuses = None
        self.step_view = None
        self.step_machine_map = None
        cells = self.read_cells()
        if not cells:
            flush_all()
            sleep(IDLE_POLL_SECONDS)
            return
        # One statuses dict per step: target choice (nearest) and the route
        # (move_to) then share a single heat map.
        statuses = {s: getattr(c, "status", None) for s, c in cells.items()}
        self.step_statuses = statuses
        self.step_view = (cells, statuses, {s: cells[s] for s, st in statuses.items() if st in PLANT_STATUSES})
        self.base_sector = self.base_from_cells(cells, statuses)
        self.mark("cells")
        # Recipes change only when the Seed Maker republishes; the layout only
        # on the switch to full or a new chunk. Neither is re-read every step.
        if self._rules is None or curr_tick - self._rules_tick >= PUBLISH_INTERVAL_TICKS:
            fresh = self.load_rules()
            if fresh != self._rules:   # an unchanged recipe set keeps its object, so the memos keyed on it stay valid
                self._rules = fresh
            self._rules_tick = curr_tick
            self.mark("rules")
        rules = self._rules
        if not self._layout or curr_tick - self._layout_tick >= LAYOUT_RECHECK_TICKS:
            loaded = self.load_layout(cells, rules)
            if loaded != self._layout:
                self._layout = loaded   # an unchanged layout keeps its object, so the memos keyed on it stay valid
            self._layout_tick = curr_tick
            self.work_groups = field_layout.work_order(self._layout, self.reserved, self.field_fill()) if self.layout_mode == "full" else []
            self.mark("reload")
        layout = self._layout
        inactive = self.inactive_species(rules)
        active = self.active_layout(layout, rules, inactive)
        self.mark("active")
        # The cells the Harvester plants itself (full layout: not automated).
        mine = self.harvester_layout(active, rules)
        self.step_mine = mine
        # Loose items off the path: paving material, else swept up. Items on
        # the path are its +1-heat roads and stay put.
        roads = set(self.road_cells(layout))
        spare_items = [s for s, st in statuses.items() if st == "item" and s not in roads]
        self.mark("layout")
        self.publish(active, layout, cells, rules, spare_items, curr_tick)
        self.mark("publish")

        # Something left in the held slot (e.g. after a restart) goes back to Inventory.
        self.store_held_if_any()

        # A. Yield Amplifier: field-wide, so no move; ahead of everything else.
        if self.amplify_step(curr_tick):
            return

        # 0. Full layout: remove a stray field machine (older layout).
        strays = self.stray_machines()
        self.mark("machines")
        if strays:
            target = self.nearest(list(strays), cells)
            self.log.debug(f"[{self.name}] {len(strays)} stray field machine(s) {strays}; nearest {target}; {self.plan_note()}.")
            if self.move_to(target):
                self.remove_here(strays[target])
            return

        # 1. Full layout, build phase: build (deploy a machine whose kit is at
        #    home, or plant one of its own cells) in field_layout.work_order():
        #    the garden row by row in a snake, then the fill chunk by chunk.
        #    Ahead of care: each machine takes a treatment (a Crop Automator a
        #    whole 5 x 5 area) off the Harvester for good, and behind care it
        #    never ran (hand care kept it busy). Ends once every reserved
        #    machine is deployed.
        building = self.layout_mode == "full" and bool(self.missing_machines(cells))
        if building != self.build_phase:
            if self.build_phase is not None:
                self.log.print(f"[{self.name}] Build phase {'resumed: machines missing' if building else 'done: every field machine deployed'}.")
            self.build_phase = building
        if building:
            deploys = self.deploy_targets(cells)
            build = dict(self.plant_targets(mine, cells))
            build.update(deploys)
            if build:
                rank = self.build_rank()
                target = min(build, key=lambda s: (rank.get(s, 1 << 30), s))
                self.log.debug(f"[{self.name}] Build: {len(deploys)} machine / {len(build) - len(deploys)} plant cell(s) ready; next in order {target} ({build[target]}); {self.plan_note()}.")
                what = f"deploy {deploys[target]}" if target in deploys else f"plant {build[target]}"
                self.log.start(f"[{self.name}] Build: {what} at {target}")
                if self.move_to(target):
                    if target in deploys:
                        done = self.deploy_here(deploys[target])
                    else:
                        done = self.plant_here(build[target])
                        if done:
                            self.care_current(rules)
                    self.log.end("Build step done" if done else "Build step not completed")
                else:
                    self.log.end("Build step aborted: target not reached")
                return

        self.mark("build")
        # 2. Care tour first: a lapsed treatment stalls growth, while a mature
        #    crop just waits with its Forage banked. Harvest-first starved care
        #    (7 plants stalled for a whole day with crops always mature).
        kept = self.kept_garden()
        batch = self.care_targets(cells, rules, CARE_BATCH_H, kept)
        self.care_batch = {s: k for s, k in batch.items() if s in self.care_batch}
        if not self.care_batch and self.care_targets(cells, rules, kept=kept):
            self.care_batch = batch
            self.log.debug(f"[{self.name}] Care tour: {len(batch)} cell(s) below {CARE_BATCH_H} h.")
        self.mark("care")
        if self.care_batch:
            target = self.nearest(list(self.care_batch), cells)
            self.log.debug(f"[{self.name}] Care tour: next {target} ({'+'.join(self.care_batch[target])}) of {len(self.care_batch)} queued; {self.plan_note()}.")
            self.log.start(f"[{self.name}] Care tour: {target} ({len(self.care_batch)} cell(s) queued)")
            if self.move_to(target):
                treated = self.care_here(self.care_batch[target])
                self.log.end("Treated" if treated else "Nothing treated")
            else:
                self.log.end("Target not reached")
            self.care_batch.pop(target, None)
            return

        # 3. Harvest (paused for a while after Inventory reported full).
        if self.inventory_full_tick is not None and curr_tick - self.inventory_full_tick >= INVENTORY_FULL_RETRY_TICKS:
            self.inventory_full_tick = None
        if self.inventory_full_tick is None:
            targets = self.harvest_targets(cells, layout)
            if targets:
                target = self.nearest(targets, cells)
                self.log.debug(f"[{self.name}] {len(targets)} mature crop(s); cheapest {target}; {self.plan_note()}.")
                self.log.start(f"[{self.name}] Harvest {target}")
                if self.move_to(target):
                    self.harvest_here()
                    self.plant_if_open(mine)
                    self.care_current(rules)
                    self.log.end("Harvest visit done")
                else:
                    self.log.end("Target not reached")
                return

        # 4. Clear plants in the layout's way (old layout after a version bump).
        targets = self.clear_targets(layout, cells)
        if targets:
            target = self.nearest(targets, cells)
            self.log.debug(f"[{self.name}] {len(targets)} plant(s) in the layout's way; cheapest {target}; {self.plan_note()}.")
            self.log.start(f"[{self.name}] Uproot {target}")
            if self.move_to(target) and self.uproot_here():
                self.plant_if_open(mine)
                self.log.end("Uprooted")
            else:
                self.log.end("Not uprooted")
            return

        # 5. Plant.
        targets = self.plant_targets(mine, cells)
        if targets:
            by_sector = dict(targets)
            target = self.nearest(list(by_sector), cells)
            self.log.debug(f"[{self.name}] {len(targets)} plantable cell(s); cheapest {target} ({by_sector[target]}); {self.plan_note()}.")
            self.log.start(f"[{self.name}] Plant {by_sector[target]} at {target}")
            if self.move_to(target) and self.plant_here(by_sector[target]):
                self.care_current(rules)
                self.log.end("Planted")
            else:
                self.log.end("Not planted")
            return

        # 6. With heat headroom: pave a path cell, else sweep a loose item.
        if self.get_heat() <= ITEM_SWEEP_MAX_HEAT and self.pave_step(layout, cells, rules, spare_items):
            self.idle_since = None
            return
        if spare_items and self.get_heat() <= ITEM_SWEEP_MAX_HEAT and not self.unpaved(layout, cells):
            target = self.nearest(spare_items, cells)
            self.log.debug(f"[{self.name}] Nothing to tend; collecting loose item off the path at {target}; {self.plan_note()}.")
            self.log.start(f"[{self.name}] Collect loose item at {target}")
            if self.move_to(target):
                self.collect_at_current()
                self.log.end("Collected")
            else:
                self.log.end("Target not reached")
            return

        # 7. Nothing due: wait in place and cool passively.
        self.log_idle(cells, rules)
        flush_all()
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
        here = self.get_position()
        cell = self.harvester.cell(here)
        due = self.care_due(cell, rules, CARE_BATCH_H, here in self.kept_garden())
        if due:
            self.care_here(due)

    def run(self):
        self.log.print(f"Field Keeper ({self.name}) online.")
        validate_game_version()
        while True:
            reset_all()
            try:
                self.step()
                flush_all()
                sleep(LOOP_SLEEP_SECONDS)
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Field Keeper exception: {e}")
                flush_all()
                sleep(5.0)
