# Harvester mixin, layer 2: the shared hub every harvester ability calls down into.
# Composed by FieldKeeperController (lib/field_keeper.py).
#
#   act()            -- a Harvester action with heat-aware rest and busy/overheated retries
#   stage()          -- pull an item from a home Warehouse into Inventory
#   stock_count()    -- home stock, memoised per step
#   note_action()    -- the one writer of last_action (FieldPass.last_action)
#   layout state     -- layout_mode / reserved / garden, written only by set_layout_state()
#                       (HarvesterPlantingMixin.load_layout() decides them)
#   machine reads    -- deployable_kits() / automation_unlocked() (research), step_machines() /
#                       forget_machines() (the pass's deployed-machine map), deployed_automators(),
#                       automated_cells()
#   cell views       -- cell_statuses(), planted_cells(), planted_rows() of the pass's cell read
# Module functions (archive and world inputs, no host): load_rules(), field_fill(),
# stored_chunk_count(), desired_chunks(), deployed_machines(), deployed_machine_ids().
#
# Owns the per-step memo `stock_memo`, the staging state `stage_busy` / `busy_since` and the layout
# state; init_hub() is their only initialiser, reset_step_memo() clears the memo at the start of a step
# (FieldKeeperController.prepare_pass() hands the new memo to the FieldPass as `stock`).
# Calls only the heat model (harvester_heat), HarvesterController and the FieldPass record, never an
# ability mixin (paving, planting, care, machines, amplify).

from typing import TYPE_CHECKING

import field_layout
import harvester_pure
from archive import archive
from components import home_outpost
from game_clock import now_tick
from seed_supply import RECIPES_KEY
from storage import discover_storage_buildings, inventory_count, mark_busy, recently_busy, total_stock
from swallow import swallowed
from tree_console import flush_all

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

ACTION_RETRIES = 3  # busy/moving retries per Harvester action
STAGE_STUCK_WARN_TICKS = 6000  # a Warehouse answering "busy" to staging this long (~10 min) gets one warning

PLANT_STATUSES = ("growing", "stalled", "mature")

# {"source": field_layout.geometry_source(), "chunk_count": {fill: n}}: full_chunk_count() walks the
# whole full layout (~48k interpreter steps), so its result survives script restarts here.
GEOMETRY_KEY = "plant.geometry"
TERRAFORMER_KEY = "plant.terraformer"
FIELD_FILL_KEY = "plant.field_fill"  # operator override: "crowncap" | "grandbloom"

AUTOMATOR_KIT = "crop_automator_kit"  # deployable once Field Automation is researched
# deployables() is research state: re-read this often.
DEPLOYABLES_REFRESH_TICKS = 3000


# ------------------------------------------------------------ layout inputs


def load_rules():
    """The Seed Maker's published recipes as field_layout rules."""
    return field_layout.rules_from_published(archive.get(RECIPES_KEY, {}))


def field_fill():
    """The full layout's fill: the plant.field_fill override, else field_layout.FIELD_FILL."""
    fill = archive.get(FIELD_FILL_KEY, None)
    return fill if fill in field_layout.FILL_SPECIES else field_layout.FIELD_FILL


def stored_chunk_count(fill):
    """field_layout.full_chunk_count(fill), read from GEOMETRY_KEY while the layout constants are unchanged."""
    source = field_layout.geometry_source()
    stored = archive.get(GEOMETRY_KEY, {}) or {}
    stored = stored if isinstance(stored, dict) else {}
    counts = stored.get("chunk_count") if stored.get("source") == source else None
    counts = counts if isinstance(counts, dict) else {}
    if fill in counts:
        return int(counts[fill])
    count = field_layout.full_chunk_count(fill)
    counts = dict(counts)
    counts[fill] = count
    archive.set(GEOMETRY_KEY, {"source": source, "chunk_count": counts})
    return count


def desired_chunks(fill=None):
    """
    Full-layout chunks: the whole field for the crowncap fill, else what
    the Plant Terraformers' Forage demand calls for (at least 1; the
    grandbloom fill needs a powered, watered machine per plant).
    """
    fill = fill or field_fill()
    if fill == "crowncap":
        return harvester_pure.desired_chunks(fill, stored_chunk_count(fill), None, None)
    return harvester_pure.desired_chunks(fill, 0, archive.get(TERRAFORMER_KEY, {}), load_rules())


# -------------------------------------------------------- deployed machines


def deployed_machines():
    """{sector: kind} of the field machines on the home field, or None if unreadable."""
    refs = deployed_machine_ids()
    return None if refs is None else {s: kind for s, (kind, _id) in refs.items()}


def deployed_machine_ids():
    """{sector: (kind, machine id)} of the field machines on the home field, or None if unreadable."""
    try:
        home = home_outpost()
        if home is None:
            return None
        return {m.position: (m.type_id, m.id) for m in home.harvesting_machines()}
    except Exception as error:
        swallowed("harvester_hub.deployed_machine_ids: _home", error)
        return None


class HarvesterHubMixin:
    """Staging, stock reads, acting and the shared field state for the harvester ability mixins."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def init_hub(self):
        """Sets the hub's state; called once from the controller's __init__."""
        self.stock_memo = {}  # {item id: home stock}, per step
        self.stage_busy = False  # last failed stage(): every holder answered "busy"
        self.busy_since = {}  # {warehouse id: [first "busy" tick, warned]}, cleared on a non-busy answer
        self.set_layout_state("starter", {}, [])  # until the first load_layout()

    def reset_step_memo(self):
        """Drops the per-step stock memo; called at the start of each step. Returns the new memo (FieldPass.stock)."""
        self._host.stock_memo = {}
        return self._host.stock_memo

    def inventory_count(self, item_id):
        return inventory_count(item_id)

    def stock_count(self, item_id):
        """
        Home stock of item_id (Inventory + home Warehouses), memoised per
        step: each total_stock() walks every Warehouse, and one step asks for
        up to 24 seeds, which burned the script's per-tick step budget.
        """
        found = self._host.stock_memo.get(item_id)
        if found is None:
            found = total_stock(item_id)
            self._host.stock_memo[item_id] = found
        return found

    def stage(self, item_id, n=1):
        """
        Pulls item_id from a home Warehouse into Inventory until n are there.
        Seeds and salt are kept in Warehouses so they don't clutter Inventory,
        but load_seed()/dispense_salt()/amplify() read Inventory only, so each
        is staged right before use. The rebalance sweep may move a leftover
        back later. Warehouses that just answered "busy" (an Auto Feeder
        cycle) are tried last. On failure, self._host.stage_busy is True when every
        holder answered "busy" (a short wait fixes it); a Warehouse busy for
        STAGE_STUCK_WARN_TICKS gets one warning.
        """
        self._host.log.start(f"[{self._host.name}] stage", level="debug")
        self._host.stage_busy = False
        missing = n - self._host.inventory_count(item_id)
        if missing <= 0:
            self._host.log.end()
            return True
        self._host.stock_memo.pop(item_id, None)
        now = now_tick()
        holders = []
        for building in discover_storage_buildings():
            try:
                if building["component"].count(item_id) > 0:
                    holders.append(building)
            except Exception as error:
                swallowed("harvester_hub.HarvesterHubMixin.stage: component.count", error)
        holders.sort(key=lambda b: 1 if recently_busy(b["id"], now) else 0)
        answers = []
        for building in holders:
            try:
                res = building["component"].transfer_to("inventory", item_id, missing)
            except Exception as error:
                swallowed("harvester_hub.HarvesterHubMixin.stage: component.transfer_to", error)
                answers.append("error")
                continue
            status = getattr(res, "status", "")
            answers.append(status)
            self._host.note_busy(building["id"], status == "busy", now)
            self._host.log.debug(f"stage '{item_id}' from '{building['id']}': {status}, moved {getattr(res, 'moved', 0) or 0}.")
            missing -= getattr(res, "moved", 0) or 0
            if missing <= 0:
                self._host.log.debug(f"Staged {n}x '{item_id}' into Inventory.")
                self._host.log.end()
                return True
        self._host.stage_busy = bool(answers) and all(a == "busy" for a in answers)
        self._host.log.debug(f"Could not stage '{item_id}': {missing} short ({'all holders busy' if self._host.stage_busy else 'answers ' + str(answers or 'none: no Warehouse holds it')}).")
        self._host.log.end()
        return False

    def note_busy(self, building_id, busy, now):
        """Tracks how long building_id has answered "busy"; warns once past STAGE_STUCK_WARN_TICKS."""
        if not busy:
            self._host.busy_since.pop(building_id, None)
            return
        mark_busy(building_id, now)
        entry = self._host.busy_since.setdefault(building_id, [now, False])
        if not entry[1] and now - entry[0] >= STAGE_STUCK_WARN_TICKS:
            entry[1] = True
            self._host.log.level("warn").print(f"[{self._host.name}] Warehouse '{building_id}' busy for {self._host.game_time(now - entry[0])}: Auto Feeder stuck? Staging skips it while it stays busy.")

    def act(self, method, *args):
        """
        Calls a Harvester action: rests first if its (learned) heat cost would
        cross the cap, measures that cost on success, cools on "overheated"
        and retries "busy"/"moving".
        """
        fn = getattr(self._host.harvester, method, None)
        if fn is None:
            return None
        self._host.log.start(f"[{self._host.name}] {method}", level="debug")
        where = self._host.get_position()
        res = None
        for _ in range(ACTION_RETRIES):
            self._host.ensure_headroom(self._host.action_cost(method))
            before = self._host.get_heat()
            start_tick = now_tick()
            res = fn(*args)
            status = getattr(res, "status", "")
            took = self._host.game_time(now_tick() - start_tick)
            if status in ("ok", "partial", "dropped"):
                after = self._host.get_heat()
                self._host.learn_action(method, before, after)
                self._host.log.debug(f"at {where} -> {status} after {took}, heat {before:.1f} -> {after:.1f}.")
                self._host.log.end()
                return res
            self._host.log.debug(f"at {where} -> {status} after {took}: {getattr(res, 'message', '')}")
            if status == "overheated":
                self._host.cool_down()
            elif status in ("busy", "moving"):
                flush_all()
                sleep(1.0)
            else:
                self._host.log.end()
                return res
        self._host.log.end()
        return res

    # ------------------------------------------------------------ last action

    @property
    def last_action(self):
        """Last completed world action ("plant <species>@<sector>", ...), reported in plant.status."""
        return self._host.field_pass.last_action

    def note_action(self, action):
        """The one writer of last_action: an ability reports a world action it completed."""
        self._host.field_pass.last_action = action

    # ----------------------------------------------------------- layout state

    def set_layout_state(self, mode, reserved, garden):
        """
        The one writer of the layout state: mode ("starter" | "full"),
        reserved ({sector: machine kind}) and garden (kept sectors: full
        garden / starter keepers). Readers use the read-only properties.
        """
        self._layout_mode = mode
        self._reserved = reserved
        self._garden = garden

    @property
    def layout_mode(self):
        return self._layout_mode

    @property
    def reserved(self):
        return self._reserved

    @property
    def garden(self):
        return self._garden

    def kept_garden(self):
        """Sectors whose crops are never harvested (full-layout garden, starter keepers; field_layout.kept_crop())."""
        return set(self.garden or [])

    # ---------------------------------------------------------- machine reads

    def deployable_kits(self):
        """Kit ids the Harvester can deploy (research), cached."""
        now = now_tick()
        cache = getattr(self, "_deployables_cache", None)
        if cache is None or now - cache[0] >= DEPLOYABLES_REFRESH_TICKS:
            try:
                kits = list(self._host.harvester.deployables() or [])
            except Exception as error:
                swallowed("harvester_hub.HarvesterHubMixin.deployable_kits: self._host.harvester.deployables", error)
                kits = []
            cache = (now, kits)
            self._deployables_cache = cache
            self._host.log.debug(f"[{self._host.name}] deployables(): {kits}.")
        return cache[1]

    def automation_unlocked(self):
        """True once Field Automation is researched (Crop Automator kit deployable)."""
        return AUTOMATOR_KIT in self.deployable_kits()

    def step_machines(self):
        """deployed_machines(), read once per step: kept on the FieldPass (a new step starts without it)."""
        fp = self._host.field_pass
        if fp.machine_map is None:
            fp.machine_map = deployed_machines()
        return fp.machine_map

    def forget_machines(self):
        """Drops the step's deployed-machine read after a deploy/undeploy changed the field."""
        self._host.field_pass.machine_map = None

    def deployed_automators(self):
        """
        Sectors of the Crop Automators on the field that the full layout
        reserves (one left over from an older layout does no jobs). Memoised
        on the step's machine map and the reserved dict; the list is shared
        and read-only.
        """
        deployed = self.step_machines()
        reserved = self.reserved
        memo = getattr(self, "_automators_memo", None)
        if memo is not None and deployed is not None and memo[0] is deployed and memo[1] is reserved:
            return memo[2]
        found = [s for s, k in (deployed or {}).items() if k == "crop_automator" and (reserved or {}).get(s) == "crop_automator"]
        self._automators_memo = (deployed, reserved, found)
        return found

    def automated_cells(self):
        """Sectors a deployed Crop Automator serves (its jobs, not the Harvester's); memoised on the automators, the set is shared and read-only."""
        automators = self.deployed_automators()
        memo = getattr(self, "_automated_memo", None)
        if memo is not None and memo[0] == automators:
            return memo[1]
        out = set()
        for ca in automators:
            out |= set(field_layout.automator_area(ca))
        self._automated_memo = (list(automators), out)
        return out

    # ------------------------------------------------------------- cell views

    def cell_statuses(self, cells):
        """{sector: Cell.status} of `cells`: the step's shared dict when `cells` is the step's read, else a fresh one."""
        fp = self._host.field_pass
        if fp.statuses is not None and fp.cells is cells:
            return fp.statuses
        return {s: getattr(c, "status", None) for s, c in cells.items()}

    def planted_cells(self, cells):
        """{sector: Cell} of the growing / stalled / mature cells (the step's shared dict when `cells` is the step's read)."""
        fp = self._host.field_pass
        if fp.has_view(cells):
            return fp.planted
        return {s: c for s, c in cells.items() if getattr(c, "status", "") in PLANT_STATUSES}

    def planted_rows(self, cells):
        """
        [(sector, (status, plant, growth, light_h, water_h, salt_h, lit, watered, salted))] of the planted cells
        (harvester_pure.ROW_ATTRS): the one place the per-cell attributes of the publish/care scans are read,
        so the scans themselves are pure. Memoised on the planted dict.
        """
        planted = self.planted_cells(cells)
        memo = getattr(self, "_rows_memo", None)
        if memo is not None and memo[0] is planted:
            return memo[1]
        # Game Cell objects: read outside any atomic callback, one explicit tuple per cell (no `operator` module in
        # the game's interpreter). Order and defaults follow harvester_pure.ROW_ATTRS.
        rows = [
            (sector, (getattr(c, "status", ""), getattr(c, "plant", None), getattr(c, "growth", 0), getattr(c, "manual_light_remaining", 0), getattr(c, "manual_water_remaining", 0), getattr(c, "manual_salt_remaining", 0), getattr(c, "lit", False), getattr(c, "watered", False), getattr(c, "salted", False)))
            for sector, c in planted.items()
        ]
        self._rows_memo = (planted, rows)
        return rows
