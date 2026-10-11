# Planting Harvester: keeps the field layout planted, tended and harvested.
#
# Composition (vehicle-mixin style, `_host` self-typing property), by layer;
# each layer calls only the layers below it:
#   0 HarvesterController    (lib/harvesting.py)         -- Harvester handle, grid, position/heat/cells() reads,
#                                                           held slot, collect_at_current() (rests via cool_down())
#   1 HarvesterHeatMixin     (lib/harvester_heat.py)     -- heat model: calibration, just-in-time rests,
#                                                           heat-cheapest routes, nearest(), move_to()
#   2 HarvesterHubMixin      (lib/harvester_hub.py)      -- act, stage, stock_count, note_action, layout state,
#                                                           deployed-machine reads, cell views
#   3 abilities, siblings that never call each other:
#     HarvesterPavingMixin   (lib/harvester_paving.py)   -- items on a path joining the plant patches (+1 heat instead of +7)
#     HarvesterPlantingMixin (lib/harvester_planting.py) -- layout, seed demand, plant, harvest, uproot
#     HarvesterCareMixin     (lib/harvester_care.py)     -- light/water/salt, the care/status row scan
#     HarvesterMachinesMixin (lib/harvester_machines.py) -- field-machine kit orders, deploy on reserved cells, remove strays
#     HarvesterAmplifyMixin  (lib/harvester_amplify.py)  -- field-wide Yield Amplifier: apply, Fabricator order
#   4 FieldKeeperController (this file)                  -- the pass: prepare_pass(), choose(), run_choice(), and
#                                                           the composites that combine abilities (work_on_pass(),
#                                                           plant_if_open(), care_current(), harvest_current())
# One hook goes up: move_to() (layer 1) calls work_on_pass() (layer 4) on every cell a route passes;
# collect_at_current() (layer 0) rests through cool_down() (layer 1).
# Pure inputs: harvester_pure (scans, tables), harvester_pass (FieldPass / Choice records).
#
# Each step is one FieldPass (lib/harvester_pass.py): prepare_pass() re-reads
# cells() and publishes, choose() picks the single most urgent task as a
# Choice, run_choice() drives there and does it. Cheapest route (heat) first
# within a priority:
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
# (work_on_pass()): the next pass costs +1 heat, not +7.
#
# Telemetry: `plant.status` = {harvester_id: {...}} (one shared dict).

import field_layout
from archive import archive
from components import home_outpost_id
from game_clock import now_tick
from harvester_amplify import HarvesterAmplifyMixin
from harvester_care import CARE_BATCH_H, HarvesterCareMixin
from harvester_heat import HarvesterHeatMixin
from harvester_hub import PLANT_STATUSES, HarvesterHubMixin, field_fill, load_rules
from harvester_machines import HarvesterMachinesMixin
from harvester_pass import Choice, FieldPass
from harvester_paving import HarvesterPavingMixin
from harvester_planting import HarvesterPlantingMixin
from harvesting import HarvesterController
from tree_console import flush_all

STATUS_KEY = "plant.status"

PUBLISH_INTERVAL_TICKS = 600  # seed demand / salt request / status at most once a minute
LAYOUT_RECHECK_TICKS = 3000  # re-check layout mode (automation research) and chunks (~5 min)
IDLE_POLL_SECONDS = 3.0  # nothing due: re-check this often
LOOP_SLEEP_SECONDS = 0.2  # pause between steps
INVENTORY_FULL_RETRY_TICKS = 3000  # after "inventory_full", skip harvesting this long (~5 min)
ITEM_SWEEP_MAX_HEAT = 40.0  # loose items only while heat is at most this (keep headroom for crops)


class FieldKeeperController(HarvesterHubMixin, HarvesterHeatMixin, HarvesterPavingMixin, HarvesterPlantingMixin, HarvesterCareMixin, HarvesterMachinesMixin, HarvesterAmplifyMixin, HarvesterController):
    """Plants, tends and harvests the field layout; falls back to the loose-item sweep."""

    LABEL = "Field Keeper"
    LOG_MODULE = "field_keeper"
    POLL_S = LOOP_SLEEP_SECONDS
    ERROR_POLL_S = 5.0

    def online_message(self):
        return f"Field Keeper ({self.name}) online."

    def __init__(self, harvester):
        super().__init__(harvester)
        self.home_id = home_outpost_id()
        self.inventory_full_tick: int | None = None
        self._last_publish_tick = -PUBLISH_INTERVAL_TICKS
        self.care_batch = {}
        # Per-step caches (the script has a step budget per tick; see step()).
        self.init_hub()
        self.field_pass = FieldPass(0)  # the current (else the last) step's pass; a placeholder until the first step
        self._rules = None
        self._rules_tick = -PUBLISH_INTERVAL_TICKS
        self._layout = None
        self._layout_tick = -LAYOUT_RECHECK_TICKS
        self.work_groups = []  # field_layout.work_order() of the full layout
        self.build_phase = None  # full layout: True while a reserved machine is missing
        self.idle_since: int | None = None  # tick the current idle streak began
        saved = archive.get(STATUS_KEY, {})
        self.init_heat_model((saved.get(self.name) or {}).get("heat") if isinstance(saved, dict) else None)

    # -------------------------------------------------------------- publish

    def publish(self, active, layout, cells, rules, spare_items, curr_tick, force=False):
        if not force and curr_tick - self._last_publish_tick < PUBLISH_INTERVAL_TICKS:
            return
        self._last_publish_tick = curr_tick
        now, rotation = self.seed_demand(self.seed_layout(active, self.field_pass.mine), cells, rules)
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
        }
        archive.publish_status(STATUS_KEY, self.name, entry, curr_tick, self.log)
        self.log.debug(f"[{self.name}] demand now={now} rotation={len(rotation)} species; status={entry}")

    # ------------------------------------------------------ step profiling

    def mark(self, phase):
        """Ends a planning phase of the current step; plan_note() reports its ticks."""
        self.field_pass.mark(phase, now_tick())

    def plan_note(self):
        """
        "planned in <world time> (<ticks>: <phase> <ticks>, ...)" for the
        step's decision line. Planning runs on the script's step budget, so a
        step can take a sizeable part of a world hour before the Harvester
        moves. Also closes an idle streak.
        """
        self.mark("decide")
        total, parts = self.field_pass.phase_note()
        note = f"planned in {self.game_time(total)} ({total} ticks{': ' + parts if parts else ''})"
        if self.idle_since is not None:
            note += f"; idle {self.game_time(self.field_pass.tick - self.idle_since)} before"
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
        self.idle_since = self.field_pass.tick

    # ----------------------------------------------------------------- loop

    def step(self):
        """One pass: prepare_pass() reads and publishes, choose() picks the most urgent task, run_choice() does it."""
        fp = self.prepare_pass(now_tick())
        if fp is None:
            flush_all()
            sleep(IDLE_POLL_SECONDS)
            return
        self.run_choice(fp, self.choose(fp))

    def prepare_pass(self, curr_tick):
        """
        Starts a new FieldPass: reads the cells once, refreshes rules and
        layout on their intervals, derives the active and own cells, publishes
        (rate-limited) and stores a leftover held item. None when no cells read.
        """
        fp = FieldPass(curr_tick, self.last_action, self.reset_step_memo())
        self.field_pass = fp
        cells = self.read_cells()
        if not cells:
            return None
        # One statuses dict per step: target choice (nearest) and the route
        # (move_to) then share a single heat map.
        statuses = {s: getattr(c, "status", None) for s, c in cells.items()}
        fp.set_view(cells, statuses, {s: cells[s] for s, st in statuses.items() if st in PLANT_STATUSES})
        self.base_sector = self.base_from_cells(cells, statuses)
        self.mark("cells")
        # Recipes change only when the Seed Maker republishes; the layout only
        # on the switch to full or a new chunk. Neither is re-read every step.
        if self._rules is None or curr_tick - self._rules_tick >= PUBLISH_INTERVAL_TICKS:
            fresh = load_rules()
            if fresh != self._rules:  # an unchanged recipe set keeps its object, so the memos keyed on it stay valid
                self._rules = fresh
            self._rules_tick = curr_tick
            self.mark("rules")
        fp.rules = rules = self._rules
        if not self._layout or curr_tick - self._layout_tick >= LAYOUT_RECHECK_TICKS:
            loaded = self.load_layout(cells, rules)
            if loaded != self._layout:
                self._layout = loaded  # an unchanged layout keeps its object, so the memos keyed on it stay valid
            self._layout_tick = curr_tick
            self.work_groups = field_layout.work_order(self._layout, self.reserved, field_fill()) if self.layout_mode == "full" else []
            self.mark("reload")
        fp.layout = layout = self._layout
        inactive = self.inactive_species(rules)
        fp.active = active = self.active_layout(layout, rules, inactive)
        self.mark("active")
        # The cells the Harvester plants itself (full layout: not automated).
        fp.mine = self.harvester_layout(active, self.work_groups)
        # Loose items off the path: paving material, else swept up. Items on
        # the path are its +1-heat roads and stay put.
        roads = set(self.road_cells(layout))
        fp.spare_items = [s for s, st in statuses.items() if st == "item" and s not in roads]
        self.mark("layout")
        self.publish(active, layout, cells, rules, fp.spare_items, curr_tick)
        self.mark("publish")

        # Something left in the held slot (e.g. after a restart) goes back to Inventory.
        self.store_held_if_any()
        return fp

    def choose(self, fp):
        """
        The most urgent task of the pass (module header, A and 0-7), as a
        Choice. No world actions: reads, controller bookkeeping (build phase,
        care batch, harvest pause) and the decision's debug line.
        """
        cells, rules, layout = fp.cells, fp.rules, fp.layout
        curr_tick = fp.tick

        # A. Yield Amplifier: field-wide, so no move; ahead of everything else.
        if self.amplify_due(curr_tick):
            return Choice("amplify")

        # 0. Full layout: remove a stray field machine (older layout).
        strays = self.stray_machines()
        self.mark("machines")
        if strays:
            target = self.nearest(list(strays), cells)
            self.log.debug(f"[{self.name}] {len(strays)} stray field machine(s) {strays}; nearest {target}; {self.plan_note()}.")
            return Choice("stray", target, strays[target])

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
            build = dict(self.plant_targets(fp.mine, cells))
            build.update(deploys)
            if build:
                rank = self.build_rank(self.work_groups)
                target = min(build, key=lambda s: (rank.get(s, 1 << 30), s))
                self.log.debug(f"[{self.name}] Build: {len(deploys)} machine / {len(build) - len(deploys)} plant cell(s) ready; next in order {target} ({build[target]}); {self.plan_note()}.")
                return Choice("build", target, ("deploy", deploys[target]) if target in deploys else ("plant", build[target]))

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
            return Choice("care", target, self.care_batch[target])

        # 3. Harvest (paused for a while after Inventory reported full).
        if self.inventory_full_tick is not None and curr_tick - self.inventory_full_tick >= INVENTORY_FULL_RETRY_TICKS:
            self.inventory_full_tick = None
        if self.inventory_full_tick is None:
            targets = self.harvest_targets(cells, layout)
            if targets:
                target = self.nearest(targets, cells)
                self.log.debug(f"[{self.name}] {len(targets)} mature crop(s); cheapest {target}; {self.plan_note()}.")
                return Choice("harvest", target)

        # 4. Clear plants in the layout's way (old layout after a version bump).
        targets = self.clear_targets(layout, cells)
        if targets:
            target = self.nearest(targets, cells)
            self.log.debug(f"[{self.name}] {len(targets)} plant(s) in the layout's way; cheapest {target}; {self.plan_note()}.")
            return Choice("uproot", target)

        # 5. Plant.
        targets = self.plant_targets(fp.mine, cells)
        if targets:
            by_sector = dict(targets)
            target = self.nearest(list(by_sector), cells)
            self.log.debug(f"[{self.name}] {len(targets)} plantable cell(s); cheapest {target} ({by_sector[target]}); {self.plan_note()}.")
            return Choice("plant", target, by_sector[target])

        return self.choose_tail(fp)

    def choose_tail(self, fp):
        """
        6-7 of choose(): with heat headroom pave a path cell while one is
        unpaved (pave_due()), else sweep a loose item once the path is paved,
        else idle.
        """
        if self.get_heat() <= ITEM_SWEEP_MAX_HEAT and self.pave_due(fp.layout, fp.cells):
            return Choice("pave")
        if fp.spare_items and self.get_heat() <= ITEM_SWEEP_MAX_HEAT and not self.unpaved(fp.layout, fp.cells):
            target = self.nearest(fp.spare_items, fp.cells)
            self.log.debug(f"[{self.name}] Nothing to tend; collecting loose item off the path at {target}; {self.plan_note()}.")
            return Choice("collect", target)
        return Choice("idle")

    def run_choice(self, fp, choice):
        """Carries out the pass's Choice: drives to its target and acts there."""
        fp.choice = choice
        kind, target = choice.kind, choice.target
        if kind == "amplify":
            self.amplify_apply(fp.tick)
        elif kind == "stray":
            if self.move_to(target):
                self.remove_here(choice.detail)
        elif kind == "build":
            action, item = choice.detail  # type: ignore[misc]
            self.log.start(f"[{self.name}] Build: {action} {item} at {target}")
            if self.move_to(target):
                if action == "deploy":
                    done = self.deploy_here(item)
                else:
                    done = self.plant_here(item)
                    if done:
                        self.care_current(fp.rules)
                self.log.end("Build step done" if done else "Build step not completed")
            else:
                self.log.end("Build step aborted: target not reached")
        elif kind == "care":
            self.log.start(f"[{self.name}] Care tour: {target} ({len(self.care_batch)} cell(s) queued)")
            if self.move_to(target):
                treated = self.care_here(self.care_batch[target])
                self.log.end("Treated" if treated else "Nothing treated")
            else:
                self.log.end("Target not reached")
            self.care_batch.pop(target, None)
        elif kind == "harvest":
            self.log.start(f"[{self.name}] Harvest {target}")
            if self.move_to(target):
                self.harvest_current()
                self.plant_if_open(fp.mine)
                self.care_current(fp.rules)
                self.log.end("Harvest visit done")
            else:
                self.log.end("Target not reached")
        elif kind == "uproot":
            self.log.start(f"[{self.name}] Uproot {target}")
            if self.move_to(target) and self.uproot_here():
                self.plant_if_open(fp.mine)
                self.log.end("Uprooted")
            else:
                self.log.end("Not uprooted")
        elif kind == "plant":
            self.log.start(f"[{self.name}] Plant {choice.detail} at {target}")
            if self.move_to(target) and self.plant_here(choice.detail):
                self.care_current(fp.rules)
                self.log.end("Planted")
            else:
                self.log.end("Not planted")
        elif kind == "pave":
            if self.pave_step(fp.layout, fp.cells, fp.rules, fp.spare_items):
                self.idle_since = None
            else:
                # Started but nothing paved (no item or seed to carry, a move or drop failed): the
                # path is still unpaved, so no sweep either; the pass ends idle.
                self.idle(fp)
        elif kind == "collect":
            self.log.start(f"[{self.name}] Collect loose item at {target}")
            if self.move_to(target):
                self.collect_at_current()
                self.log.end("Collected")
            else:
                self.log.end("Target not reached")
        else:
            self.idle(fp)

    def idle(self, fp):
        """7. Nothing due: wait in place and cool passively."""
        self.log_idle(fp.cells, fp.rules)
        flush_all()
        sleep(IDLE_POLL_SECONDS)

    # ------------------------------------------------- ability composites

    def work_on_pass(self, sector, status):
        """
        The heat model's route hook: move_to() calls it on every cell a route
        passes through (not its target). Harvests a mature crop and plants an
        open cell right there, if the cell is one of the Harvester's own
        (FieldPass.mine, harvester_layout()). The hop is already paid for, and
        a plant costs a fraction of the +7 heat an empty cell costs on every
        later pass.
        """
        fp = self.field_pass
        species = fp.mine.get(sector)
        if not species or self.harvester.get_held():
            return
        if self.plant_cooling(sector, now_tick()):
            return
        if status == "mature":
            if sector in self.kept_garden():
                return
            if self.inventory_full_tick is not None or not self.harvest_current():
                return
            status = "empty"
        if status in ("empty", "unknown") and self.stock_count("seed_" + species) >= 1:
            self.log.start(f"[{self.name}] Passing {sector}: planting {species} on the way")
            if self.plant_here(species):
                self.care_current(fp.rules or load_rules())
                self.log.end("Planted on the way")
            else:
                self.log.end("Not planted")

    def harvest_current(self):
        """
        harvest_here() plus the harvest pause: "inventory_full" sets
        inventory_full_tick (its one setter; choose() clears it after
        INVENTORY_FULL_RETRY_TICKS). True when the crop was harvested.
        """
        status = self.harvest_here()
        if status == "inventory_full":
            self.inventory_full_tick = now_tick()
        return status in ("ok", "partial")

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
