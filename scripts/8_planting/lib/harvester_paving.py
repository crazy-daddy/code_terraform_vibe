# Harvester mixin: pave a path between the plant patches. Composed by
# FieldKeeperController (lib/field_keeper.py). Starter layout only: the full
# layout is wall-to-wall plants and machines, which the Harvester drives over.
#
# Moving onto a cell that holds an item costs +1 heat, an empty cell +7, and
# a dropped seed counts as an item (confirmed by the dev, 2026-09-24). Plant
# cells measure at about +1 too (live calibration), so the expensive cells in
# the block are the empty gaps the rules force between patches. Heat is the
# Harvester's real budget (lib/harvester_heat.py), so a short path of gap
# cells joining every patch (field_layout.path_cells(), 4-5 cells for v1) gets
# one item each, once:
#   1. free: a loose item from elsewhere on the field is collected, carried
#      over and drop()ped (fresh saves only -- the early sweep collects them);
#   2. otherwise, with PAVE_WITH_SEEDS, one seed of the species whose blend
#      uses the cheapest life forms is loaded from Inventory and dropped
#      (3 t of life forms per cell, one-off). The Seed Maker gets that demand
#      through `plant.seed_demand`, at most PAVE_SEED_BATCH at a time.
# Only items on the path stay put. Any other loose item (e.g. seeds from an
# older layout's path) is carried onto an unpaved path cell first, and once
# the path is paved the rest are collected back into Inventory (field_keeper).

import field_layout
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from field_keeper import FieldKeeperController

PAVING_ENABLED = True
PAVE_WITH_SEEDS = True
PAVE_SEED_BATCH = 5          # paving seeds requested from the Seed Maker at a time


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

    def pave_seed_id(self, rules):
        """Seed whose blend costs the least (common life forms)."""
        with_blend = [sp for sp in rules if rules[sp].get("blend")]
        if not with_blend:
            return None
        best = min(with_blend, key=lambda sp: (field_layout.blend_cost(rules, sp), sp))
        return rules[best].get("seed_id", "seed_" + best)

    def paving_seed_demand(self, layout, cells, rules, spare_items):
        """{seed_id: n} seeds still needed for paving after using spare loose items."""
        if not (PAVING_ENABLED and PAVE_WITH_SEEDS):
            return {}
        need = len(self.unpaved(layout, cells)) - spare_items
        seed_id = self.pave_seed_id(rules)
        if need <= 0 or not seed_id:
            return {}
        return {seed_id: min(need, PAVE_SEED_BATCH)}

    def pave_step(self, layout, cells, rules, spare_items):
        """Paves one path cell. Returns True if it did something."""
        if not PAVING_ENABLED:
            return False
        unpaved = self.unpaved(layout, cells)
        if not unpaved:
            return False
        h = self._host
        if h.harvester.get_held():
            h.store_held_if_any()

        source = None
        if spare_items:
            source = h.nearest(spare_items, cells)
            if not h.move_to(source):
                return False
            res = h.act("collect")
            if getattr(res, "status", "") != "ok":
                h.log.debug(f"[{h.name}] Paving: collect at {source} -> {getattr(res, 'status', '?')}")
                return False
        elif PAVE_WITH_SEEDS:
            seed_id = self.pave_seed_id(rules)
            if not seed_id or h.stock_count(seed_id) < 1:
                return False
            h.stage(seed_id)
            res = h.act("load_seed", seed_id)
            if getattr(res, "status", "") != "ok":
                h.log.debug(f"[{h.name}] Paving: load_seed('{seed_id}') -> {getattr(res, 'status', '?')}")
                return False
        else:
            return False

        target = h.nearest(unpaved, cells)
        held = h.harvester.get_held()
        if not h.move_to(target):
            h.store_held_if_any()
            return False
        res = h.act("drop")
        status = getattr(res, "status", "?")
        if status == "dropped":
            h.log.print(f"[{h.name}] Paved {target} with '{held}'{' from ' + source if source else ''}.")
            h.last_action = f"pave@{target}"
            return True
        h.log.debug(f"[{h.name}] Paving: drop at {target} -> {status}: {getattr(res, 'message', '')}")
        h.store_held_if_any()
        return False
