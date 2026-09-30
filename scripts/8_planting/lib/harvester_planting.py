# Harvester mixin: field layout, seed demand, planting and harvesting.
# Composed by FieldKeeperController (lib/field_keeper.py).
#
# The layout is built from lib/field_layout.py and stored in `plant.layout`,
# so a restart (or a Harvester that stopped mid-field) keeps the same cells.
# Three phases:
#   1. "starter" (field_layout.STARTER_LAYOUT) until Field Automation is
#      researched. Its STARTER_KEEP cells (field_layout.starter_kept(), stored
#      as "garden") are planted once, cared for and never harvested; the
#      rest is harvested and replanted. Rebuilt only when STARTER_VERSION
#      changes (machines unlocked earlier aren't worth a rebuild; an older
#      stored layout without "mode" counts as starter).
#   2. "full" with the crowncap fill: garden + solid Crowncap over the whole
#      field (no machines, power or water; Crowncap Forage and life forms are
#      never wasted). Built in field_layout.work_order(): the garden row by
#      row in a snake, then the fill chunk by chunk (one Crop Automator area
#      each). The Harvester plants only the garden and the next
#      HARVESTER_FILL_CHUNKS fill chunk(s) without an automator; one
#      Harvester can't keep up with 170 cells, so deployed automators (kits
#      bought by harvester_machines.py) take the rest. Garden crops are
#      planted once and never harvested (field_layout.kept_crop()): a mature
#      crop still counts toward the species multiplier, and a replant risks a
#      species whose seed is missing. Garden cells need no replant seeds.
#   3. "full" with the grandbloom fill (checkerboard), once Mk II+ lamps and
#      sprinklers (and the power/water for ~75 machines) make it pay. The
#      operator switches by setting the Data Archive key `plant.field_fill`
#      to "grandbloom"; that rebuilds the full layout once. On a rebuild, plants in the new layout's way are
# uprooted (seed back to Inventory); the rest finish their cycle and are
# harvested but not replanted. Everything else is re-read from cells() each
# step: the game keeps plants, growth and treatment timers, so there is no
# mission state to persist.
#
# Archive (one shared dict per concern, CLAUDE.md rule 7):
#   plant.layout      = {"version", "mode", "fill", "chunks", "base", "anchor",
#                        "starter_version", "cells": {sector: species},
#                        "reserved": {sector: machine kind}, "garden": [kept sectors]}
#   plant.seed_demand = {"now": {seed_id: n}, "rotation": {seed_id: cells},
#                        "priority": [garden seed_id], "tick"}
#                       read by lib/seed_supply.py (garden seeds first)

from archive import archive
from atomic import run_atomic
import field_layout
import harvester_pure
from seed_supply import RECIPES_KEY, SEED_DEMAND_KEY, seed_buffer
from swallow import swallowed
from script_parking import wake_kind
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

LAYOUT_KEY = "plant.layout"
# {"source": field_layout.geometry_source(), "chunk_count": {fill: n}}: full_chunk_count() walks the
# whole full layout (~48k interpreter steps), so its result survives script restarts here.
GEOMETRY_KEY = "plant.geometry"
# Bump when field_layout changes what a full layout looks like: a stored full
# layout from an older version is rebuilt once.
# 5 = hand-cared CROWNCAP_GARDEN in columns 1-4, no garden machines.
LAYOUT_VERSION = 5
# Same for the starter layout: a stored starter with an older
# "starter_version" is rebuilt once. 2 = keepers + Crowncap (STARTER_KEEP).
STARTER_VERSION = 2
TERRAFORMER_KEY = "plant.terraformer"
FIELD_FILL_KEY = "plant.field_fill"   # operator override: "crowncap" | "grandbloom"

# A layout crop at or past this growth (Cell.growth, 0-1) counts toward seed
# demand already, so its replacement seed is made before the harvest.
SEED_PREFETCH_GROWTH = 0.75

PLANT_STATUSES = ("growing", "stalled", "mature")
# Cell statuses a layout cell may still be planted from (after clearing an item).
OPEN_STATUSES = ("empty", "unknown", "item")
# Fill chunks (work_order() groups past the garden) the Harvester plants and
# harvests itself ahead of their Crop Automator: one at a time, so the field
# grows chunk by chunk without burying one Harvester in fill.
HARVESTER_FILL_CHUNKS = 1

# A cell whose load_seed/plant just failed is skipped this long (~5 min), so a
# refusing cell can't pin the Harvester in a retry loop.
PLANT_FAIL_COOLDOWN_TICKS = 3000


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("harvester_planting._now_tick: get_component", error)
        return 0


class HarvesterPlantingMixin:
    """Layout, seed demand, planting and harvesting, mixed into FieldKeeperController."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    # ---------------------------------------------------------------- rules

    def load_rules(self):
        return field_layout.rules_from_published(archive.get(RECIPES_KEY, {}))

    # --------------------------------------------------------------- layout

    def cell_statuses(self, cells):
        """{sector: Cell.status} of `cells`: the step's shared dict when `cells` is the step's read, else a fresh one."""
        view = self._host.step_view
        if view is not None and view[0] is cells:
            return view[1]
        return {s: getattr(c, "status", None) for s, c in cells.items()}

    def planted_cells(self, cells):
        """{sector: Cell} of the growing / stalled / mature cells (the step's shared dict when `cells` is the step's read)."""
        view = self._host.step_view
        if view is not None and view[0] is cells:
            return view[2]
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
        rows = [(sector, (getattr(c, "status", ""), getattr(c, "plant", None), getattr(c, "growth", 0),
                          getattr(c, "manual_light_remaining", 0), getattr(c, "manual_water_remaining", 0),
                          getattr(c, "manual_salt_remaining", 0), getattr(c, "lit", False),
                          getattr(c, "watered", False), getattr(c, "salted", False)))
                for sector, c in planted.items()]
        self._rows_memo = (planted, rows)
        return rows

    def row_scan(self, cells, rules, kept):
        """
        {"planted", "mature", "stalled", "productive" (species count), "care" ({sector: [(kind, hours)]}, see
        HarvesterCareMixin.hand_care())} over the planted cells, in atomic chunks of harvester_pure.ROW_CHUNK rows.
        Memoised on the cells dict, the rules object and the kept set; the result is shared and read-only.
        """
        memo = getattr(self, "_row_scan_memo", None)
        if memo is not None and memo[0] is cells and memo[1] is rules and memo[2] == kept:
            return memo[3]
        rows = self.planted_rows(cells)
        table = self._host.care_kind_table(rules)
        salt_ok = any("salt" in kinds for kinds in table.values()) and self._host.salt_in_inventory() >= 1
        slots = harvester_pure.care_slots(table, salt_ok)
        size = harvester_pure.ROW_CHUNK
        parts = [run_atomic(harvester_pure.scan_rows, rows[i:i + size], slots, kept) for i in range(0, len(rows), size)]
        care = {}
        productive = set()
        for part_care, _mature, _stalled, part_productive in parts:
            care.update(part_care)
            productive |= part_productive
        scan = {"planted": len(rows), "mature": sum([p[1] for p in parts]), "stalled": sum([p[2] for p in parts]),
                "productive": len(productive), "care": care}
        self._row_scan_memo = (cells, rules, kept, scan)
        return scan

    def base_from_cells(self, cells, statuses=None):
        """The depot pad sector (Cell.status == "base"), else the constructor's guess."""
        statuses = statuses if statuses is not None else self.cell_statuses(cells)
        return next((s for s, st in statuses.items() if st == "base"), self._host.base_sector)

    def field_fill(self):
        """The full layout's fill: the plant.field_fill override, else field_layout.FIELD_FILL."""
        fill = archive.get(FIELD_FILL_KEY, None)
        return fill if fill in field_layout.FILL_SPECIES else field_layout.FIELD_FILL

    def desired_chunks(self, fill=None):
        """
        Full-layout chunks: the whole field for the crowncap fill, else what
        the Plant Terraformers' Forage demand calls for (at least 1; the
        grandbloom fill needs a powered, watered machine per plant).
        """
        fill = fill or self.field_fill()
        if fill == "crowncap":
            return self.stored_chunk_count(fill)
        demand = field_layout.terraformer_demand(archive.get(TERRAFORMER_KEY, {}))
        return field_layout.chunks_for_demand(demand, self.load_rules(), fill or self.field_fill())

    def stored_chunk_count(self, fill):
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

    def wanted_layout(self, stored):
        """(mode, fill, chunks) the layout should have now, given the stored one."""
        if not self._host.automation_unlocked():
            return "starter", None, 0
        fill = self.field_fill()
        chunks = self.desired_chunks(fill)
        if stored.get("mode") == "full" and stored.get("fill", "grandbloom") == fill:
            chunks = max(chunks, int(stored.get("chunks") or 0))   # a full layout only grows
        return "full", fill, chunks

    def load_layout(self, cells, rules):
        """
        {sector: species}. Builds and stores a layout on first use, on the
        switch to full, and when a full layout grows by a chunk; otherwise
        returns the stored one. Sets self.layout_mode, self.reserved and
        self.garden.
        """
        stored = archive.get(LAYOUT_KEY, {})
        stored = stored if isinstance(stored, dict) else {}
        mode, fill, chunks = self.wanted_layout(stored)
        stored_mode = stored.get("mode") or "starter"
        same_fill = mode == "starter" or stored.get("fill", "grandbloom") == fill
        if mode == "starter":
            current = int(stored.get("starter_version") or 1) >= STARTER_VERSION
        else:
            current = int(stored.get("version") or 0) >= LAYOUT_VERSION
        if stored.get("cells") and stored_mode == mode and same_fill and current and (mode == "starter" or int(stored.get("chunks") or 0) >= chunks):
            self.layout_mode = stored_mode
            self.reserved = dict(stored.get("reserved") or {})
            self.garden = list(stored.get("garden") or [])
            return dict(stored["cells"])

        self._host.log.start(f"[{self._host.name}] Building field layout ({mode})")
        layout = self._build_layout(cells, rules, stored, mode, fill, chunks, stored_mode)
        self._host.log.end(f"Layout ready: {len(layout)} plant(s)")
        return layout

    def _build_layout(self, cells, rules, stored, mode, fill, chunks, stored_mode):
        status = {s: getattr(c, "status", None) for s, c in cells.items()}
        base = self.base_from_cells(cells)
        if mode == "full" and base != field_layout.FULL_LAYOUT_BASE:
            self._host.log.level("error").print(f"[{self._host.name}] Base pad at {base}, not {field_layout.FULL_LAYOUT_BASE}: FULL_LAYOUT doesn't fit. Staying on the current layout.")
            mode = stored_mode if stored.get("cells") else "starter"
            if stored.get("cells"):
                self.layout_mode = stored_mode
                self.reserved = dict(stored.get("reserved") or {})
                self.garden = list(stored.get("garden") or [])
                return dict(stored["cells"])
        if mode == "full":
            layout, reserved, garden = field_layout.full_layout(chunks, fill)
            offset = "A1"
        else:
            block = field_layout.parse_block(field_layout.STARTER_LAYOUT)
            machines = field_layout.parse_machines(field_layout.STARTER_LAYOUT)
            offset, layout, reserved = field_layout.anchor_layout(base, status, block, machines)
            garden = field_layout.starter_kept(layout)
            if not layout:
                self._host.log.level("error").print(f"[{self._host.name}] No room on the field for the planting block.")
                return {}
            if field_layout.LAYOUT_EXPANSION_ENABLED:
                blocked = [s for s, st in status.items() if st in ("base", "provider")] + list(reserved)
                before = len(layout)
                layout = field_layout.expand_layout(layout, rules, blocked=blocked)
                self._host.log.debug(f"[{self._host.name}] Layout expanded {before} -> {len(layout)} plants (care {field_layout.daily_care(layout, rules)}/day).")
        self.layout_mode = mode
        self.reserved = reserved
        self.garden = garden
        bad = field_layout.validate(layout, rules)
        if bad:
            self._host.log.level("warn").print(f"[{self._host.name}] Layout breaks {len(bad)} rule(s): {bad[:5]}")
        archive.set(LAYOUT_KEY, {"version": LAYOUT_VERSION, "starter_version": STARTER_VERSION, "mode": mode, "fill": fill, "chunks": chunks,
                                 "base": base, "anchor": offset, "cells": layout, "reserved": reserved, "garden": garden})
        wake_kind("field_provider", "field layout changed")
        self._host.log.print(f"[{self._host.name}] Field layout set ({mode}{', ' + str(fill) + ' fill, ' + str(chunks) + ' chunk(s)' if mode == 'full' else ''}): "
                             f"{len(layout)} plants, {len(set(layout.values()))} species, {len(reserved)} machine cells, "
                             f"~{round(field_layout.forage_per_hour(layout, rules, garden))} Forage/h at Mk I (base {base}).")
        return layout

    def active_layout(self, layout, rules, inactive_species):
        """
        {sector: species} of the layout cells whose species has a rule and is
        sustainable. Memoised on the layout and rules objects and the inactive
        species; the returned dict is shared and read-only.
        """
        memo = getattr(self, "_active_memo", None)
        if memo is not None and memo[0] is layout and memo[1] is rules and memo[2] == inactive_species:
            return memo[3]
        active = {s: sp for s, sp in layout.items() if sp not in inactive_species and sp in rules}
        self._active_memo = (layout, rules, list(inactive_species), active)
        return active

    def harvester_layout(self, active, rules):
        """
        The part of `active` the Harvester plants itself. Starter: all of it.
        Full: cells no deployed Crop Automator serves, in the garden and in
        the first HARVESTER_FILL_CHUNKS work_order() fill groups whose
        automator isn't deployed yet. Later fill waits: the Harvester can't
        keep up with a whole field. Memoised on the active dict, the work
        groups, the garden and the deployed automators; the result is shared
        and read-only.
        """
        if self.layout_mode != "full":
            return active
        deployed = self._host.deployed_automators()
        groups = self._host.work_groups
        memo = getattr(self, "_mine_memo", None)
        if memo is not None and memo[0] is active and memo[1] is groups and memo[2] is self.garden and memo[3] == deployed:
            return memo[4]
        automated = self._host.automated_cells()
        groups = groups or []
        scope = set(groups[0]) if groups else set(self.garden or [])
        taken = 0
        for group in groups[1:]:
            if taken >= HARVESTER_FILL_CHUNKS:
                break
            if group[0] in deployed:
                continue
            scope |= set(group)
            taken += 1
        scope -= automated
        mine = {s: sp for s, sp in active.items() if s in scope}
        self._mine_memo = (active, self._host.work_groups, self.garden, list(deployed), mine)
        return mine

    def seed_layout(self, active, mine):
        """
        The part of `active` that gets planted soon, so seed demand covers it:
        starter all of it; full the Harvester's cells (`mine`) plus cells a
        deployed Crop Automator serves.
        """
        if self.layout_mode != "full":
            return active
        automated = self._host.automated_cells()
        memo = getattr(self, "_seed_layout_memo", None)
        if memo is not None and memo[0] is active and memo[1] is mine and memo[2] is automated:
            return memo[3]
        items = list(active.items())
        size = harvester_pure.ITEM_CHUNK
        seeded = {}
        for i in range(0, len(items), size):
            seeded.update(run_atomic(harvester_pure.seeded_items, items[i:i + size], mine, automated))
        self._seed_layout_memo = (active, mine, automated, seeded)
        return seeded

    def build_rank(self):
        """{sector: position} in work_order() (garden snake, then fill chunks); memoised on the work groups."""
        groups = self._host.work_groups
        memo = getattr(self, "_rank_memo", None)
        if memo is not None and memo[0] is groups:
            return memo[1]
        rank = {}
        for group in groups or []:
            for s in group:
                rank.setdefault(s, len(rank))
        self._rank_memo = (groups, rank)
        return rank

    def clear_targets(self, layout, cells):
        """Growing/stalled plants in the layout's way (mature ones get harvested instead)."""
        statuses = self.cell_statuses(cells)
        planted = {s: p for s, p in [(s, getattr(c, "plant", None)) for s, c in self.planted_cells(cells).items()
                                     if statuses[s] in ("growing", "stalled")] if p}
        now_tick = _now_tick()
        failed = self._plant_failures()
        return [s for s in field_layout.misplaced(layout, self.reserved, planted)
                if now_tick - failed.get(s, -PLANT_FAIL_COOLDOWN_TICKS) >= PLANT_FAIL_COOLDOWN_TICKS]

    def uproot_here(self):
        """Uproots the plant in the current cell; its seed goes back to Inventory."""
        here = self._host.get_position()
        plant = getattr(self._host.harvester.cell(here), "plant", None)
        res = self._host.act("uproot")
        status = getattr(res, "status", "?")
        if status == "ok":
            self._host.log.print(f"[{self._host.name}] Uprooted {plant} at {here} (not in the layout); seed back to Inventory.")
            self._host.last_action = f"uproot@{here}"
            return True
        self._host.log.level("warn").print(f"[{self._host.name}] uproot at {here} -> {status}: {getattr(res, 'message', '')}")
        self._plant_failures()[here] = _now_tick()
        return False

    # ---------------------------------------------------------- seed demand

    def kept_garden(self):
        """Sectors whose crops are never harvested (full-layout garden, starter keepers; field_layout.kept_crop())."""
        return set(self.garden or [])

    def seed_demand(self, active, cells, rules):
        """
        (now, rotation) as {seed_id: n}: seeds needed soon, and cells per
        species. Kept garden cells (kept_garden()) are planted once: an open
        one needs a seed now, but they add no rotation, buffer or prefetch.
        """
        kept = self.kept_garden()
        seed_ids = self.seed_id_map(rules)
        rotation = self.seed_rotation(active, kept, seed_ids)
        statuses = self.cell_statuses(cells)
        rows = self.planted_rows(cells)
        size = harvester_pure.SOON_CHUNK
        # Non-kept planted cells whose replacement seed is needed before the harvest.
        soon = set()
        for i in range(0, len(rows), size):
            soon.update(run_atomic(harvester_pure.soon_sectors, rows[i:i + size], active, kept, SEED_PREFETCH_GROWTH))
        items = list(active.items())
        size = harvester_pure.ITEM_CHUNK
        now = harvester_pure.merge_counts([run_atomic(harvester_pure.needed_seeds, items[i:i + size], statuses, OPEN_STATUSES, soon, seed_ids)
                                           for i in range(0, len(items), size)])
        for seed_id, count in rotation.items():
            now[seed_id] = now.get(seed_id, 0) + seed_buffer(count)
        return now, dict(rotation)

    def seed_id_map(self, rules):
        """{species: seed item id}; memoised on the rules object."""
        memo = getattr(self, "_seed_ids_memo", None)
        if memo is not None and memo[0] is rules:
            return memo[1]
        seed_ids = {sp: r.get("seed_id", "seed_" + sp) for sp, r in rules.items()}
        self._seed_ids_memo = (rules, seed_ids)
        return seed_ids

    def seed_rotation(self, active, kept, seed_ids):
        """{seed_id: non-kept cells} of `active`; memoised on the active dict, the kept set and the seed ids."""
        memo = getattr(self, "_rotation_memo", None)
        if memo is not None and memo[0] is active and memo[1] == kept and memo[2] == seed_ids:
            return memo[3]
        items = list(active.items())
        size = harvester_pure.ITEM_CHUNK
        rotation = harvester_pure.merge_counts([run_atomic(harvester_pure.rotation_counts, items[i:i + size], kept, seed_ids)
                                                for i in range(0, len(items), size)])
        self._rotation_memo = (active, kept, seed_ids, rotation)
        return rotation

    def publish_seed_demand(self, now, rotation, curr_tick, layout=None, rules=None):
        """Full layout: also "priority" (field_layout.priority_seeds()), garden seeds the Seed Maker makes first."""
        priority = []
        if self.layout_mode == "full" and layout and rules:
            priority = self.priority_seeds(layout, rules)
        archive.set(SEED_DEMAND_KEY, {"now": now, "rotation": rotation, "priority": priority, "tick": curr_tick})

    def priority_seeds(self, layout, rules):
        """field_layout.priority_seeds() of the full layout; memoised on the layout, garden and fill (rules compared by value)."""
        fill = self.field_fill()
        memo = getattr(self, "_priority_memo", None)
        if memo is not None and memo[0] is layout and memo[1] is self.garden and memo[2] == fill and memo[3] == rules:
            return list(memo[4])
        priority = field_layout.priority_seeds(layout, self.garden, fill, rules)
        self._priority_memo = (layout, self.garden, fill, rules, list(priority))
        return priority

    # ---------------------------------------------------------------- tasks

    def harvest_targets(self, cells, layout=None):
        """Every mature crop, layout or not, except layout cells a Crop Automator harvests and kept garden crops."""
        automated = self._host.automated_cells() if self.layout_mode == "full" else set()
        kept = self.kept_garden()
        layout = layout or {}
        mature = [s for s, st in self.cell_statuses(cells).items() if st == "mature"]
        return [s for s in mature
                if not (s in automated and s in layout)
                and not (s in kept and field_layout.kept_crop(s, getattr(cells[s], "plant", None), layout, kept))]

    def plant_targets(self, active, cells):
        """[(sector, species)] of open layout cells whose seed is at home (Inventory or Warehouse)."""
        statuses = self.cell_statuses(cells)
        open_cells = [(s, sp) for s, sp in active.items() if statuses.get(s, "unknown") in OPEN_STATUSES]
        out = []
        if not open_cells:
            return out
        now_tick = _now_tick()
        failed = self._plant_failures()
        for sector, species in open_cells:
            if now_tick - failed.get(sector, -PLANT_FAIL_COOLDOWN_TICKS) < PLANT_FAIL_COOLDOWN_TICKS:
                continue
            if statuses.get(sector, "unknown") != "item" and self._host.stock_count("seed_" + species) < 1:
                continue
            out.append((sector, species))
        return out

    def plant_here(self, species):
        """Clears a loose item, loads the seed and sows it in the current cell."""
        h = self._host.harvester
        here = self._host.get_position()
        cell = h.cell(here)
        if getattr(cell, "status", "") == "item":
            self._host.collect_at_current()
            if self._host.stock_count("seed_" + species) < 1:
                return False
        seed_id = "seed_" + species
        held = h.get_held()
        if held and held != seed_id:
            self._host.store_held_if_any()
        if h.get_held() != seed_id:
            self._host.stage(seed_id)
            res = self._host.act("load_seed", seed_id)
            if res is None or res.status != "ok":
                self._host.log.debug(f"[{self._host.name}] load_seed('{seed_id}') -> {getattr(res, 'status', '?')}")
                self._plant_failures()[here] = _now_tick()
                return False
        res = self._host.act("plant", seed_id)
        if res is not None and res.status == "ok":
            # stock_count() is memoised per step: without this a second cell
            # on the same route (work_on_pass()) plans with a seed that's gone.
            memo = self._host.stock_memo
            if seed_id in memo:
                memo[seed_id] = max(memo[seed_id] - 1, 0)
            self._host.log.print(f"[{self._host.name}] Planted {species} at {here}.")
            self._host.last_action = f"plant {species}@{here}"
            return True
        self._host.log.level("warn").print(f"[{self._host.name}] plant('{seed_id}') at {here} -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}")
        self._plant_failures()[here] = _now_tick()
        self._host.store_held_if_any()
        return False

    def _plant_failures(self):
        """{sector: tick of last failed plant attempt}, in memory only."""
        if not hasattr(self, "_plant_fail_ticks"):
            self._plant_fail_ticks = {}
        return self._plant_fail_ticks

    def work_on_pass(self, sector, status):
        """
        Called by move_to() on every cell a route passes through (not its
        target): harvests a mature crop and plants an open cell right there,
        if the cell is one of the Harvester's own (harvester_layout()). The
        hop is already paid for, and a plant costs a fraction of the +7 heat
        an empty cell costs on every later pass.
        """
        h = self._host
        species = (getattr(h, "step_mine", None) or {}).get(sector)
        if not species or h.harvester.get_held():
            return
        if _now_tick() - self._plant_failures().get(sector, -PLANT_FAIL_COOLDOWN_TICKS) < PLANT_FAIL_COOLDOWN_TICKS:
            return
        if status == "mature":
            if sector in self.kept_garden():
                return
            if h.inventory_full_tick is not None or not self.harvest_here():
                return
            status = "empty"
        if status in ("empty", "unknown") and h.stock_count("seed_" + species) >= 1:
            h.log.start(f"[{h.name}] Passing {sector}: planting {species} on the way")
            if self.plant_here(species):
                rules = getattr(h, "_rules", None) or self.load_rules()
                h.care_current(rules)
                h.log.end("Planted on the way")
            else:
                h.log.end("Not planted")

    def harvest_here(self):
        here = self._host.get_position()
        res = self._host.act("harvest")
        status = getattr(res, "status", "?")
        if status in ("ok", "partial"):
            self._host.stock_memo.pop("forage", None)
            self._host.log.print(f"[{self._host.name}] Harvested {here}: {status}.")
            self._host.last_action = f"harvest@{here}"
            return True
        if status == "inventory_full":
            self._host.log.level("warn").print(f"[{self._host.name}] Inventory full; crop at {here} stays banked.")
            self._host.inventory_full_tick = _now_tick()
        else:
            self._host.log.debug(f"[{self._host.name}] harvest at {here} -> {status}: {getattr(res, 'message', '')}")
        return False
