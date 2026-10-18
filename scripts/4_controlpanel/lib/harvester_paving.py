# Harvester ability: pave a path between the plant patches. Composed by
# FieldKeeperController (lib/field_keeper.py); calls only the hub
# (lib/harvester_hub.py), the heat model (nearest(), move_to()) and
# HarvesterController, never another ability mixin. Starter layout only: the full
# layout is wall-to-wall plants and machines, which the Harvester drives over.
#
# Moving onto a cell that holds an item costs +1 heat, an empty cell +7, and
# a dropped seed counts as an item (dev-confirmed). Plant cells measure at about +1 too
# (live calibration), so the expensive cells in the block are the empty gaps
# the rules force between patches. Heat is the Harvester's real budget
# (lib/harvester_heat.py), so a short path of gap cells joining every patch
# (field_layout.path_cells(); 4 cells for the starter block) gets one item
# each, once, ahead of harvest and planting (pave_first()):
#   1. free: a loose item from elsewhere on the field is collected, carried
#      over and drop()ped. The early Harvester leaves its cheapest items on
#      the field for this (PAVE_KEEP_ITEMS in 0_cold_boot/harvesting/harvester.py);
#   2. otherwise, with PAVE_WITH_SEEDS, one seed of the species whose blend
#      uses the cheapest life forms is loaded from Inventory and dropped
#      (3 t of life forms per cell, one-off). The Seed Maker gets that demand
#      through `plant.seed_demand`, at most PAVE_SEED_BATCH at a time.
# Items on the path stay put, except one worth more than PAVE_MAX_VALUE (not a
# seed): it is collected and sold, and its cell is paved again with a cheap
# item. Of the loose items off the path, the cheapest (Scanner value,
# split_loose()) up to PAVE_MAX_VALUE, one per unpaved path cell, are kept as
# paving material; every other one is collected and sold
# (HarvesterHubMixin.clear_here(); a seed of a layout species goes to
# Inventory). The full layout has no path, so every loose item is sold.

from typing import TYPE_CHECKING

import field_layout
from components import component
from game_clock import now_tick
from swallow import swallowed

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

SCANNER_ID = "scanner_1"  # the home Scanner: get_scanned() gives each loose item's id and value


def rank_loose(loose, values):
    """
    `loose` sectors cheapest first: by value from `values` {sector: (value,
    item id)}, unknown last; at equal value a non-seed first, then by sector.
    """
    big = float("inf")
    return sorted(loose, key=lambda s: (values[s][0], str(values[s][1]).startswith("seed_"), s) if s in values else (big, False, s))


PAVING_ENABLED = True
PAVE_WITH_SEEDS = True
PAVE_SEED_BATCH = 5  # paving seeds requested from the Seed Maker at a time
PAVE_FAIL_COOLDOWN_TICKS = 3000  # after a pave_step() that paved nothing, pave_first() stays off this long (~5 min)
PAVE_MAX_VALUE = 250  # Scanner value: a dearer item never paves; one on a path cell is swapped out and sold


class HarvesterPavingMixin:
    """Drops items on the path cells so moves there cost +1 heat instead of +7."""

    @property
    def _host(self) -> "FieldKeeperController":
        return self  # type: ignore[return-value]

    def road_cells(self, layout):
        """The path cells joining every plant patch (cached per layout); none in the full layout."""
        if getattr(self._host, "layout_mode", "starter") == "full":
            return []
        reserved = getattr(self._host, "reserved", {}) or {}
        key = (tuple(sorted(layout)), self._host.base_sector, tuple(sorted(reserved)))
        cache = getattr(self, "_path_cache", None)
        if cache is None or cache[0] != key:
            blocked = [self._host.base_sector] + list(reserved)
            cache = (key, field_layout.path_cells(layout, blocked))
            self._path_cache = cache
        return cache[1]

    def unpaved(self, layout, cells):
        return [s for s in self.road_cells(layout) if getattr(cells.get(s), "status", "unknown") in ("empty", "unknown")]

    def split_loose(self, layout, cells, loose, on_path=()):
        """
        (paving, clear) of the loose items: of those off the path (`loose`),
        the cheapest (rank_loose()) up to PAVE_MAX_VALUE, one per unpaved path
        cell, stay as paving material; the rest are to be collected and sold.
        Of the items on path cells (`on_path`), one worth more than
        PAVE_MAX_VALUE (not a seed) is cleared too, so its cell gets a cheap
        item instead. No unpaved cell and nothing on the path (full layout):
        every loose item is cleared, and the Scanner is not read.
        """
        n = len(self.unpaved(layout, cells)) if loose else 0
        if n == 0 and not on_path:
            return [], list(loose)
        values = self.loose_values(list(loose) + list(on_path))
        dear = [s for s in on_path if s in values and values[s][0] > PAVE_MAX_VALUE and not str(values[s][1]).startswith("seed_")]
        ranked = rank_loose(loose, values)
        cheap = [s for s in ranked if s not in values or values[s][0] <= PAVE_MAX_VALUE][:n]
        return cheap, [s for s in ranked if s not in cheap] + dear

    def loose_values(self, loose):
        """{sector: (value, item id)} of the loose items, from the Scanner; re-read only when the set of loose sectors changes."""
        key = tuple(sorted(loose))
        cache = getattr(self, "_loose_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        values = {}
        scanner = component(SCANNER_ID)
        if scanner is not None:
            try:
                scanned = scanner.get_scanned() or {}
            except Exception as error:
                swallowed("harvester_paving.loose_values: scanner.get_scanned", error)
                return values
            for s in loose:
                res = scanned.get(s)
                if res is not None and getattr(res, "status", "") == "ok":
                    values[s] = (getattr(res, "value", 0) or 0, getattr(res, "id", "") or "")
        self._loose_cache = (key, values)
        return values

    def pave_due(self, layout, cells):
        """True when paving is on and a path cell is unpaved: choose() picks "pave" only then, so pave_step() has work."""
        return PAVING_ENABLED and bool(self.unpaved(layout, cells))

    def pave_first(self, layout, cells, rules, spare_items, mine, curr_tick):
        """
        Starter: True when a path cell is unpaved and there is something to
        pave it with, so choose() paves ahead of harvest and planting (while
        the material is near or nothing is plantable: choose_pave_first()). A
        loose item always counts; a paving seed only beyond the open cells
        of its own species in `mine` (paving never takes a seed a layout
        cell is waiting for). No heat gate: the path is a one-off, and each
        hop rests just in time (lib/harvester_heat.py). Unpaved, the gap cells
        cost +7 heat per hop and the hand-cared garden keeps heat near the
        cap, so a low-heat gate would never open. Off for
        PAVE_FAIL_COOLDOWN_TICKS after a pave_step() that paved nothing.
        """
        if getattr(self._host, "layout_mode", "starter") == "full" or not self.pave_due(layout, cells):
            return False
        if self.pave_cooling(curr_tick):
            return False
        return bool(spare_items) or self.pave_seed_ready(cells, rules, mine)

    def pave_seed_ready(self, cells, rules, mine):
        """True when seed paving is on and a paving seed is at home beyond the open cells of its species in `mine`."""
        if not PAVE_WITH_SEEDS:
            return False
        seed_id = self.pave_seed_id(rules or {})
        if not seed_id:
            return False
        statuses = self._host.cell_statuses(cells)
        open_cells = sum(1 for s, sp in (mine or {}).items() if (rules or {}).get(sp, {}).get("seed_id", "seed_" + sp) == seed_id and statuses.get(s, "unknown") in ("empty", "unknown", "item"))
        return self._host.stock_count(seed_id) > open_cells

    def pave_cooling(self, curr_tick):
        """True inside PAVE_FAIL_COOLDOWN_TICKS of a pave_step() that paved nothing."""
        return curr_tick - getattr(self, "_pave_fail_tick", -PAVE_FAIL_COOLDOWN_TICKS) < PAVE_FAIL_COOLDOWN_TICKS

    def pave_seed_id(self, rules):
        """Seed whose blend costs the least (common life forms)."""
        with_blend = [sp for sp in rules if rules[sp].get("blend")]
        if not with_blend:
            return None
        best = min(with_blend, key=lambda sp: (field_layout.blend_cost(rules, sp), sp))
        return rules[best].get("seed_id", "seed_" + best)

    def paving_seed_demand(self, layout, cells, rules, spare_items, unpaved=None):
        """{seed_id: n} seeds still needed for paving after using spare loose items (`unpaved`: unpaved(), when the caller has it)."""
        if not (PAVING_ENABLED and PAVE_WITH_SEEDS):
            return {}
        need = len(self.unpaved(layout, cells) if unpaved is None else unpaved) - spare_items
        seed_id = self.pave_seed_id(rules)
        if need <= 0 or not seed_id:
            return {}
        return {seed_id: min(need, PAVE_SEED_BATCH)}

    def pave_step(self, layout, cells, rules, spare_items):
        """Paves one path cell. Returns True if it did something (False also when it started and failed)."""
        if not PAVING_ENABLED:
            return False
        unpaved = self.unpaved(layout, cells)
        if not unpaved:
            return False
        h = self._host
        h.log.start(f"[{h.name}] Paving ({len(unpaved)} path cell(s) unpaved)")
        paved = self._pave(layout, cells, rules, spare_items, unpaved)
        h.log.end("Paved a path cell" if paved else "Nothing paved")
        if not paved:
            self._pave_fail_tick = now_tick()
        return paved

    def _pave(self, layout, cells, rules, spare_items, unpaved):
        h = self._host
        h.log.start("_pave", level="debug")
        if h.harvester.get_held():
            h.store_held_if_any()

        source = None
        if spare_items:
            source = h.nearest(spare_items, cells)
            if not h.move_to(source):
                h.log.end()
                return False
            res = h.act("collect")
            if getattr(res, "status", "") != "ok":
                h.log.debug(f"[{h.name}] Paving: collect at {source} -> {getattr(res, 'status', '?')}")
                h.log.end()
                return False
        elif PAVE_WITH_SEEDS:
            seed_id = self.pave_seed_id(rules)
            if not seed_id or h.stock_count(seed_id) < 1:
                h.log.end()
                return False
            h.stage(seed_id)
            res = h.act("load_seed", seed_id)
            if getattr(res, "status", "") != "ok":
                h.log.debug(f"[{h.name}] Paving: load_seed('{seed_id}') -> {getattr(res, 'status', '?')}")
                h.log.end()
                return False
        else:
            h.log.end()
            return False

        target = h.nearest(unpaved, cells)
        held = h.harvester.get_held()
        if not h.move_to(target):
            h.store_held_if_any()
            h.log.end()
            return False
        res = h.act("drop")
        status = getattr(res, "status", "?")
        if status == "dropped":
            h.log.print(f"[{h.name}] Paved {target} with '{held}'{' from ' + source if source else ''}.")
            h.note_action(f"pave@{target}")
            h.log.end()
            return True
        h.log.debug(f"[{h.name}] Paving: drop at {target} -> {status}: {getattr(res, 'message', '')}")
        h.store_held_if_any()
        h.log.end()
        return False
