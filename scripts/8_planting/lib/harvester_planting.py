# Harvester mixin: field layout, seed demand, planting and harvesting.
# Composed by FieldKeeperController (lib/field_keeper.py).
#
# The layout is built from lib/field_layout.py and stored in `plant.layout`,
# so a restart (or a Harvester that stopped mid-field) keeps the same cells.
# Three phases:
#   1. "starter" (the 2 x 4 block) until Field Automation is researched.
#      Never rebuilt (machines unlocked earlier aren't worth it; an older
#      stored layout without "mode" counts as starter).
#   2. "full" with the crowncap fill: garden + solid Crowncap over the whole
#      field right away (no machines, power or water; Crowncap Forage and life
#      forms are never wasted). Outside the garden only Crop Automators plant
#      and harvest: one Harvester can't keep up with 170 cells, so a fill cell
#      stays empty until its automator is in (kits bought by
#      harvester_machines.py).
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
#                        "cells": {sector: species}, "reserved": {sector: machine kind},
#                        "garden": [sectors]}
#   plant.seed_demand = {"now": {seed_id: n}, "rotation": {seed_id: cells}, "tick"}
#                       read by lib/seed_supply.py

from archive import archive
import field_layout
from seed_supply import RECIPES_KEY, SEED_DEMAND_KEY, SEED_BUFFER_PER_SPECIES
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

LAYOUT_KEY = "plant.layout"
# Bump when field_layout changes what a full layout looks like: a stored full
# layout from an older version is rebuilt once (starter layouts never are).
# 4 = CROWNCAP_GARDEN (replaced the FULL_LAYOUT garden + FILL_KEEP C7).
LAYOUT_VERSION = 4
TERRAFORMER_KEY = "plant.terraformer"
FIELD_FILL_KEY = "plant.field_fill"   # operator override: "crowncap" | "grandbloom"

# A layout crop at or past this growth (Cell.growth, 0-1) counts toward seed
# demand already, so its replacement seed is made before the harvest.
SEED_PREFETCH_GROWTH = 0.75

PLANT_STATUSES = ("growing", "stalled", "mature")
# Cell statuses a layout cell may still be planted from (after clearing an item).
OPEN_STATUSES = ("empty", "unknown", "item")
# A cell whose load_seed/plant just failed is skipped this long (~5 min), so a
# refusing cell can't pin the Harvester in a retry loop.
PLANT_FAIL_COOLDOWN_TICKS = 3000


def _now_tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception:
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

    def base_from_cells(self, cells):
        """The depot pad sector (Cell.status == "base"), else the constructor's guess."""
        for sector, cell in cells.items():
            if getattr(cell, "status", "") == "base":
                return sector
        return self._host.base_sector

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
            return field_layout.full_chunk_count(fill)
        demand = field_layout.terraformer_demand(archive.get(TERRAFORMER_KEY, {}))
        return field_layout.chunks_for_demand(demand, self.load_rules(), fill or self.field_fill())

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
        current = mode == "starter" or int(stored.get("version") or 0) >= LAYOUT_VERSION
        if stored.get("cells") and stored_mode == mode and same_fill and current and (mode == "starter" or int(stored.get("chunks") or 0) >= chunks):
            self.layout_mode = stored_mode
            self.reserved = dict(stored.get("reserved") or {})
            self.garden = list(stored.get("garden") or [])
            return dict(stored["cells"])

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
            garden = sorted(layout)
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
        archive.set(LAYOUT_KEY, {"version": LAYOUT_VERSION, "mode": mode, "fill": fill, "chunks": chunks, "base": base, "anchor": offset,
                                 "cells": layout, "reserved": reserved, "garden": garden})
        self._host.log.print(f"[{self._host.name}] Field layout set ({mode}{', ' + str(fill) + ' fill, ' + str(chunks) + ' chunk(s)' if mode == 'full' else ''}): "
                             f"{len(layout)} plants, {len(set(layout.values()))} species, {len(reserved)} machine cells, "
                             f"~{round(field_layout.forage_per_hour(layout, rules))} Forage/h at Mk I (base {base}).")
        return layout

    def active_layout(self, layout, rules, inactive_species):
        return {s: sp for s, sp in layout.items() if sp not in inactive_species and sp in rules}

    def harvester_layout(self, active, rules):
        """
        The part of `active` the Harvester plants itself. Starter: all of it.
        Full: garden cells no deployed Crop Automator serves. Fill cells are
        automator work only: the Harvester can't keep up with a whole field.
        """
        if self.layout_mode != "full":
            return active
        automated = self._host.automated_cells()
        garden = set(self.garden or [])
        return {s: sp for s, sp in active.items() if s in garden and s not in automated}

    def seed_layout(self, active):
        """
        The part of `active` that gets planted soon, so seed demand covers it:
        starter all of it; full the garden plus cells a deployed Crop
        Automator serves (fill cells without one stay empty).
        """
        if self.layout_mode != "full":
            return active
        scope = set(self.garden or []) | self._host.automated_cells()
        return {s: sp for s, sp in active.items() if s in scope}

    def clear_targets(self, layout, cells):
        """Growing/stalled plants in the layout's way (mature ones get harvested instead)."""
        planted = {s: getattr(c, "plant", None) for s, c in cells.items()
                   if getattr(c, "status", "") in ("growing", "stalled") and getattr(c, "plant", None)}
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

    def seed_demand(self, active, cells, rules):
        """(now, rotation) as {seed_id: n}: seeds needed soon, and cells per species."""
        now = {}
        rotation = {}
        for sector, species in active.items():
            seed_id = rules[species].get("seed_id", "seed_" + species)
            rotation[seed_id] = rotation.get(seed_id, 0) + 1
            cell = cells.get(sector)
            status = getattr(cell, "status", "unknown")
            plant = getattr(cell, "plant", None)
            if status in OPEN_STATUSES:
                now[seed_id] = now.get(seed_id, 0) + 1
            elif plant == species and (status == "mature" or (getattr(cell, "growth", 0) or 0) >= SEED_PREFETCH_GROWTH):
                now[seed_id] = now.get(seed_id, 0) + 1
        for seed_id in rotation:
            now[seed_id] = now.get(seed_id, 0) + SEED_BUFFER_PER_SPECIES
        return now, rotation

    def publish_seed_demand(self, now, rotation, curr_tick):
        archive.set(SEED_DEMAND_KEY, {"now": now, "rotation": rotation, "tick": curr_tick})

    # ---------------------------------------------------------------- tasks

    def harvest_targets(self, cells, layout=None):
        """Every mature crop, layout or not, except layout cells a Crop Automator harvests."""
        automated = self._host.automated_cells() if self.layout_mode == "full" else set()
        layout = layout or {}
        return [s for s, c in cells.items()
                if getattr(c, "status", "") == "mature" and not (s in automated and s in layout)]

    def plant_targets(self, active, cells):
        """[(sector, species)] of open layout cells whose seed is at home (Inventory or Warehouse)."""
        out = []
        now_tick = _now_tick()
        failed = self._plant_failures()
        for sector, species in active.items():
            if now_tick - failed.get(sector, -PLANT_FAIL_COOLDOWN_TICKS) < PLANT_FAIL_COOLDOWN_TICKS:
                continue
            status = getattr(cells.get(sector), "status", "unknown")
            if status not in OPEN_STATUSES:
                continue
            if status != "item" and self._host.stock_count("seed_" + species) < 1:
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

    def harvest_here(self):
        here = self._host.get_position()
        res = self._host.act("harvest")
        status = getattr(res, "status", "?")
        if status in ("ok", "partial"):
            self._host.log.print(f"[{self._host.name}] Harvested {here}: {status}.")
            self._host.last_action = f"harvest@{here}"
            return True
        if status == "inventory_full":
            self._host.log.level("warn").print(f"[{self._host.name}] Inventory full; crop at {here} stays banked.")
            self._host.inventory_full_tick = _now_tick()
        else:
            self._host.log.debug(f"[{self._host.name}] harvest at {here} -> {status}: {getattr(res, 'message', '')}")
        return False
