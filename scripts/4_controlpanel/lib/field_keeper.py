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
#   S. a running sweep: the nearest stale crop while it is within
#      SWEEP_REACH_COST or nearer than any layout work (sweep_next(), see 4).
#      Ahead of care, even a lapsing treatment: leaving the old zone
#      mid-sweep costs two field crossings, a lapse only stalls growth
#   2. care tour: once any treatment drops below CARE_REFRESH_H, every
#      treatment below CARE_BATCH_H is renewed in one tour, so renewals line
#      up and the field needs fewer separate trips. Ahead of harvesting: a
#      lapsed treatment stalls growth, a mature crop just waits
#   2b. starter: pave an unpaved path cell (as in 6, at any heat) while
#      there is a loose item or a spare paving seed: unpaved gap cells cost
#      +7 heat per hop, and the rests they force left no low-heat window.
#      Strict only while the material is within LOCAL_ROUTE_COST or nothing
#      is plantable; else it waits in 3-6 behind planting and is taken once
#      the Harvester is near it. An item beyond PAVE_ITEM_MAX_COST is left
#      for a paving seed (choose_pave_first())
#   3-6 rank as listed, but the highest-ranked one with a target within
#   LOCAL_ROUTE_COST wins over a farther one of a higher rank (choose_local()),
#   so the Harvester finishes the work around it before crossing the field:
#   3. harvest a mature layout crop (Forage lands in home Inventory); in the
#      starter a slow crop only while its seed is at home to replant it
#   4. start a sweep of the stale crops (not on a layout cell of their own
#      species, e.g. after a rebuild): harvest a mature one, uproot a growing
#      one (its seed goes back to Inventory); S then keeps clearing them.
#      Only a local stale crop starts it ahead of 5-6; a far one waits
#      until nothing else is due (choose_local())
#   5. plant an open layout cell whose seed is at home (staged into Inventory)
#   6. with heat headroom: pave a path cell (carry a loose item there, or
#      drop a cheap seed), else collect a loose item off the path that is not
#      kept for paving and sell it (a seed of a layout species goes to
#      Inventory instead; split_loose(), clear_here())
# In the full layout, cells a deployed Crop Automator serves are its work
# (lib/crop_automator.py): the Harvester only plants and harvests the rest.
# After "inventory_full" harvest and sweep pause (inventory_full(): an early
# Inventory rebalance, then a short or a long pause).
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
from storage import inventory_room, rebalance_inventory_to_warehouses
from swallow import swallowed
from tree_console import flush_all

STATUS_KEY = "plant.status"

PUBLISH_INTERVAL_TICKS = 600  # seed demand / salt request / status at most once a minute
LAYOUT_RECHECK_TICKS = 3000  # re-check layout mode (automation research) and chunks (~5 min)
IDLE_POLL_SECONDS = 3.0  # nothing due: re-check this often
LOOP_SLEEP_SECONDS = 0.2  # pause between steps
INVENTORY_FULL_RETRY_TICKS = 3000  # after "inventory_full", skip harvesting this long (~5 min)
INVENTORY_FULL_RELIEVED_RETRY_TICKS = 300  # ... only this long (~30 s) once an early rebalance left room for Forage
REBALANCE_COOLDOWN_TICKS = 3000  # at most one early Inventory rebalance per this many ticks (~5 min)
PARTIAL_WAIT_H = 1.0  # after a partial harvest, wait on the cell at most this long (world hours) for Inventory room
PARTIAL_WAIT_STEP_H = 0.25  # ... re-checking the room this often
ITEM_SWEEP_MAX_HEAT = 40.0  # loose items only while heat is at most this (keep headroom for crops)
LOCAL_ROUTE_COST = 17.0  # non-urgent work within this route cost (2 empty hops) beats farther work of a higher rank
SWEEP_ANY_COST = 1.0e6  # route cost cap for "any stale crop" (sweep_next())
SWEEP_REACH_COST = 26.0  # a running sweep takes the next stale crop within this route cost (3 empty hops)
PAVE_ITEM_MAX_COST = 43.0  # starter: a spare loose item farther than this route cost (5 empty hops) is left; pave with a seed


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
        self.inventory_full_wait = INVENTORY_FULL_RETRY_TICKS  # length of the current harvest pause
        self.rebalance_tick = -REBALANCE_COOLDOWN_TICKS  # last early rebalance (inventory_full())
        self.sweeping = False  # a stale-crop sweep is running (choose(), step S)
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
        self.publish_seed_demand(now, rotation, curr_tick, layout, rules, self.replace_demand(layout, cells, rules))
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
        # Starter: mature slow crops wait (with care) for a replanting seed.
        fp.held = self.starter_hold(layout, cells, rules)
        # Loose items off the path: the cheapest, one per unpaved path cell,
        # are paving material; the rest are collected and sold. Items on the
        # path are its +1-heat roads and stay put.
        roads = set(self.road_cells(layout))
        loose = [s for s, st in statuses.items() if st == "item" and s not in roads]
        fp.spare_items, fp.clear_items = self.split_loose(layout, cells, loose)
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
        # S. A running sweep clears the nearest stale crop before care and
        #    every other non-urgent work while it is still in the old zone
        #    (sweep_next()): the zone is cleared in one visit instead of one
        #    crossing per crop. Seen live: a care tour pulled the Harvester
        #    10 empty hops (+7 heat each) back from the old zone after one
        #    crop. A lapsed treatment only stalls growth until the tour.
        #    The harvest pause (Inventory full) holds the sweep too: harvest
        #    and uproot both put their result in Inventory (work_view()).
        view = None
        if self.sweeping:
            view = self.work_view(fp)
            stale, sweep_next = view[0], view[3]
            if sweep_next is not None:
                cost, target = sweep_next
                self.log.debug(f"[{self.name}] Sweep: next {target} ({stale[target]}, route {cost:.1f}) of {len(stale)} stale; {self.plan_note()}.")
                return Choice("sweep", target, stale[target])
            self.sweeping = False
            self.log.debug(f"[{self.name}] Sweep done: no stale crop left in the zone ({len(stale)} elsewhere).")

        # 2. Care tour first: a lapsed treatment stalls growth, while a mature
        #    crop just waits with its Forage banked. Harvest-first starved care
        #    (7 plants stalled for a whole day with crops always mature).
        #    Only crops on a layout cell of their own species: a stale crop
        #    (older layout) is uprooted or harvested by the sweep, so treating
        #    it first only burns salt and Harvester time.
        kept = self.kept_garden()
        layout = layout or {}

        def on_layout(targets):
            return {s: k for s, k in targets.items() if layout.get(s) == getattr(cells.get(s), "plant", None)}

        batch = on_layout(self.care_targets(cells, rules, CARE_BATCH_H, kept))
        self.care_batch = {s: k for s, k in batch.items() if s in self.care_batch}
        if not self.care_batch and on_layout(self.care_targets(cells, rules, kept=kept)):
            self.care_batch = batch
            self.log.debug(f"[{self.name}] Care tour: {len(batch)} cell(s) below {CARE_BATCH_H} h.")
        self.mark("care")
        if self.care_batch:
            target = self.nearest(list(self.care_batch), cells)
            self.log.debug(f"[{self.name}] Care tour: next {target} ({'+'.join(self.care_batch[target])}) of {len(self.care_batch)} queued; {self.plan_note()}.")
            return Choice("care", target, self.care_batch[target])

        # 2b. Starter: pave the path ahead of harvest and planting, at any heat
        #     (pave_first()). Unpaved, the gap cells cost +7 heat per hop and
        #     the rests that forces leave no low-heat window to pave in.
        #     Strict only while the material is near or nothing is plantable
        #     (choose_pave_first()); else paving joins 3-6 as a local task.
        #     A running sweep with stale crops still in reach went first (S):
        #     the paving item would be carried out of the old zone mid-sweep
        #     (one crossing per pave).
        stale, plant, mature, _sweep_next = view or self.work_view(fp)
        pave_source = None
        if self.pave_first(layout, cells, rules, fp.spare_items, fp.mine, curr_tick):
            pave_source, strict = self.choose_pave_first(fp, plant)
            if strict:
                self.log.debug(f"[{self.name}] Paving the path first with {'a loose item' if pave_source == 'item' else 'a seed'} ({len(self.unpaved(layout, cells))} cell(s) unpaved); {self.plan_note()}.")
                return Choice("pave", None, pave_source)

        # 3-6. Non-urgent work.
        heat_ok = self.get_heat() <= ITEM_SWEEP_MAX_HEAT
        pave = []
        if pave_source is not None:  # deferred pave_first: at any heat, taken once it is local or nothing else is
            pave = fp.spare_items if pave_source == "item" else self.unpaved(layout, cells)
        elif heat_ok and self.pave_due(layout, cells) and not self.pave_cooling(curr_tick):
            pave = fp.spare_items or self.unpaved(layout, cells)
        ranked = (
            ("harvest", mature),
            ("sweep", list(stale)),
            ("plant", list(plant)),
            ("pave", pave),
            ("collect", fp.clear_items if heat_ok else []),
        )
        return self.choose_local(fp, ranked, stale, plant, pave_source)

    def work_view(self, fp):
        """
        (stale, plant, mature, sweep_next) for choose() S and 2b-6: stale
        crops {sector: "harvest" | "uproot"}, plantable cells {sector:
        species}, mature layout crops, and the running sweep's next stale
        crop (None when not sweeping or the zone is done). The harvest pause
        (Inventory full) empties stale and mature.
        """
        cells, layout = fp.cells, fp.layout or {}
        harvest_ok = self.harvest_ready(fp.tick)
        stale = self.stale_targets(layout, cells) if harvest_ok else {}
        plant = dict(self.plant_targets(fp.mine, cells))
        mature = self.harvest_targets(cells, layout) if harvest_ok else []
        sweep_next = self.sweep_next(stale, cells, list(plant) + list(mature)) if self.sweeping else None
        return stale, plant, mature, sweep_next

    def sweep_next(self, stale, cells, work):
        """
        (route cost, sector) of the stale crop a running sweep takes next, or
        None when the sweep is done. The nearest stale crop counts while it
        is within SWEEP_REACH_COST, or nearer than any layout work in `work`
        (open plantable cells, mature layout crops): from inside the old zone
        the layout is farther than every crop left there, however sparse the
        zone is. Seen headless: a fixed 3-hop reach ended the sweep after
        every crop of a sparse old field, one crossing each.
        """
        if not stale:
            return None
        near = self.nearest_within(list(stale), cells, SWEEP_REACH_COST)
        if near is not None:
            return near
        near = self.nearest_within(list(stale), cells, SWEEP_ANY_COST)
        if near is None or self.nearest_within(work, cells, near[0]) is not None:
            return None
        return near

    def choose_pave_first(self, fp, plant):
        """
        (source, strict) for a due pave_first(). Source: "item" (fetch the
        nearest spare loose item), or "seed" when there is no spare item or
        the nearest one's route costs more than PAVE_ITEM_MAX_COST and a
        paving seed is at home. Strict (pave ahead of 3-6) when nothing is
        plantable or the material (the item, or for a seed the unpaved cell)
        is within LOCAL_ROUTE_COST; else planting goes first and the pave
        waits in 3-6 until it is local (carried along) or nothing else is due.
        """
        cells = fp.cells
        source, targets = "seed", self.unpaved(fp.layout, cells)
        if fp.spare_items:
            if self.nearest_within(fp.spare_items, cells, PAVE_ITEM_MAX_COST) is not None or not self.pave_seed_ready(cells, fp.rules, fp.mine):
                source, targets = "item", fp.spare_items
        if not plant or self.nearest_within(targets, cells, LOCAL_ROUTE_COST) is not None:
            return source, True
        self.log.debug(f"[{self.name}] Paving deferred: {len(plant)} plantable cell(s), paving {source} farther than route {LOCAL_ROUTE_COST:.0f}.")
        return source, False

    def choose_local(self, fp, ranked, stale, plant, pave_source=None):
        """
        Picks among the non-urgent kinds `ranked` [(kind, targets)] (choose()
        3-6): the highest-ranked kind with a target within LOCAL_ROUTE_COST of
        the Harvester, else the highest-ranked kind with any target, each at
        its cheapest target. Both read the step's single-source route map.
        A far sweep ranks last: stale crops lose nothing by waiting, a trip
        to them costs +7 heat per empty hop, so they wait until one is local
        or nothing else is due. A sweep choice starts the sweep
        (self.sweeping). None due: idle.
        """
        pick = None
        for kind, targets in ranked:
            near = self.nearest_within(targets, fp.cells, LOCAL_ROUTE_COST) if targets else None
            if near is not None:
                pick = (kind, near[1], f"local (route {near[0]:.1f})")
                break
        if pick is None:
            far = [(k, t) for k, t in ranked if k != "sweep"] + [(k, t) for k, t in ranked if k == "sweep"]
            for kind, targets in far:
                if targets:
                    pick = (kind, self.nearest(targets, fp.cells), "cheapest")
                    break
        if pick is None:
            return Choice("idle")
        kind, target, why = pick
        counts = ", ".join([f"{k} {len(t)}" for k, t in ranked if t])
        self.log.debug(f"[{self.name}] {kind} {target}: {why} of {counts}; {self.plan_note()}.")
        if kind == "sweep":
            self.sweeping = True
            self.log.debug(f"[{self.name}] Sweep started: {len(stale)} stale crop(s) outside the layout.")
            return Choice("sweep", target, stale[target])
        if kind == "plant":
            return Choice("plant", target, plant[target])
        if kind == "pave":
            return Choice("pave", None, pave_source)
        return Choice(kind, target)

    def harvest_ready(self, curr_tick):
        """
        False during the harvest pause after "inventory_full"
        (inventory_full_wait ticks: INVENTORY_FULL_RETRY_TICKS, or
        INVENTORY_FULL_RELIEVED_RETRY_TICKS after an early rebalance freed
        room); clears the pause once it ran out.
        """
        if self.inventory_full_tick is not None and curr_tick - self.inventory_full_tick >= self.inventory_full_wait:
            self.inventory_full_tick = None
        return self.inventory_full_tick is None

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
        elif kind == "sweep":
            self.log.start(f"[{self.name}] Sweep: {choice.detail} stale crop at {target}")
            if not self.move_to(target):
                self.log.end("Target not reached")
            elif self.harvest_current() if choice.detail == "harvest" else self.uproot_current():
                self.plant_if_open(fp.mine)
                self.log.end("Cleared")
            else:
                self.log.end("Not cleared")
        elif kind == "plant":
            self.log.start(f"[{self.name}] Plant {choice.detail} at {target}")
            if self.move_to(target) and self.plant_here(choice.detail):
                self.care_current(fp.rules)
                self.log.end("Planted")
            else:
                self.log.end("Not planted")
        elif kind == "pave":
            # "seed": the spare items are too far (choose_pave_first()), pave_step() drops a seed.
            if self.pave_step(fp.layout, fp.cells, fp.rules, [] if choice.detail == "seed" else fp.spare_items):
                self.idle_since = None
            else:
                # Started but nothing paved (no item or seed to carry, a move or drop failed): the
                # path is still unpaved, so no sweep either; the pass ends idle.
                self.idle(fp)
        elif kind == "collect":
            self.log.start(f"[{self.name}] Clear loose item at {target}")
            if self.move_to(target):
                self.log.end("Cleared" if self.clear_here() else "Nothing there")
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
        harvest_here() plus the harvest pause on "inventory_full"
        (inventory_full()). True when the crop was harvested. A held starter
        crop (harvest_blocked(): no replanting seed at home any more) is left
        standing. After a "partial" or "inventory_full" harvest it waits on the
        cell for Inventory room (wait_for_forage_room()) and harvests the
        rest: Inventory holds 20 Forage per slot, so one crop (Crowncap 60 x
        13 diversity = 780) can fill it, and a later visit would cost a trip
        or a harvest pause.
        """
        here = self.get_position()
        if self.harvest_blocked(here):
            self.log.debug(f"[{self.name}] Not harvesting {here}: no seed at home to replant it.")
            return False
        status = self.harvest_here()
        harvested = status in ("ok", "partial")
        if status in ("partial", "inventory_full") and self.wait_for_forage_room(here):
            self.log.debug(f"[{self.name}] Harvest {status} at {here}: Inventory has room again, harvesting the rest.")
            status = self.harvest_here()
            harvested = harvested or status in ("ok", "partial")
        if status == "inventory_full":
            self.inventory_full()
        return harvested

    def wait_for_forage_room(self, here):
        """
        Waits on the cell, PARTIAL_WAIT_STEP_H at a time and at most
        PARTIAL_WAIT_H, until Inventory has room for the crop's remaining
        Forage (cell.forage). True when Inventory has any room for Forage
        then. The Plant Terraformers pull Forage out within ~30 min; moving
        it to a Warehouse ourselves (rebalance_inventory_to_warehouses())
        took ~4.6 game hours of script time headless.
        """
        need = max(1, int(getattr(self.harvester.cell(here), "forage", 0) or 0))
        waited = 0.0
        while inventory_room("forage", keep=0) < need and waited < PARTIAL_WAIT_H:
            flush_all()
            sleep(PARTIAL_WAIT_STEP_H * self.real_seconds_per_hour)
            waited += PARTIAL_WAIT_STEP_H
        return inventory_room("forage", keep=0) > 0

    def uproot_current(self):
        """uproot_here() plus the harvest pause on "inventory_full" (inventory_full()). True when uprooted."""
        status = self.uproot_here()
        if status == "inventory_full":
            self.inventory_full()
        return status == "ok"

    def inventory_full(self):
        """
        Starts the harvest pause (inventory_full_tick, its one setter;
        harvest_ready() ends it) and, at most once per REBALANCE_COOLDOWN_TICKS,
        runs storage.rebalance_inventory_to_warehouses() right away. If
        Inventory then has room for Forage, the pause lasts only
        INVENTORY_FULL_RELIEVED_RETRY_TICKS, else INVENTORY_FULL_RETRY_TICKS.
        Never sells to make room.
        """
        curr_tick = now_tick()
        self.inventory_full_tick = curr_tick
        self.inventory_full_wait = INVENTORY_FULL_RETRY_TICKS
        if curr_tick - self.rebalance_tick < REBALANCE_COOLDOWN_TICKS:
            self.log.debug(f"[{self.name}] Inventory full: early rebalance ran {self.game_time(curr_tick - self.rebalance_tick)} ago; harvest paused {self.game_time(self.inventory_full_wait)}.")
            return
        self.rebalance_tick = curr_tick
        self.log.start(f"[{self.name}] Inventory full: early rebalance to the Warehouses")
        try:
            rebalance_inventory_to_warehouses()
        except Exception as error:
            swallowed("field_keeper.inventory_full: rebalance_inventory_to_warehouses", error)
        if inventory_room("forage", keep=0) > 0:
            self.inventory_full_wait = INVENTORY_FULL_RELIEVED_RETRY_TICKS
        self.log.end(f"Harvest paused {self.game_time(self.inventory_full_wait)}")

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
