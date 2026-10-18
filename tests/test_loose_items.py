"""Loose field items: the early Harvester leaves the cheapest for paving; the Field Keeper keeps those for its path
and sells the rest (scripts/0_cold_boot/harvesting/harvester.py, lib/harvester_paving.py, lib/harvester_hub.py)."""

import ast
import os
import unittest

import harvester_paving
from field_keeper import FieldKeeperController
from harness import StubTestCase
from harvester_pass import FieldPass
from harvester_paving import rank_loose
from tree_console import TreeConsole

EARLY_HARVESTER = os.path.join(os.path.dirname(__file__), "..", "scripts", "0_cold_boot", "harvesting", "harvester.py")


def _early_harvester():
    """The early Harvester's constants and functions, without its game reads and main loop."""
    with open(EARLY_HARVESTER, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            exec(compile(ast.Module([node], []), EARLY_HARVESTER, "exec"), ns)  # noqa: S102 -- our own script
        elif isinstance(node, ast.Assign) and not any(isinstance(n, ast.Call) for n in ast.walk(node.value)):
            exec(compile(ast.Module([node], []), EARLY_HARVESTER, "exec"), ns)  # noqa: S102 -- constants only, no game reads
    return ns


class EarlyHarvesterKeepTests(unittest.TestCase):
    def setUp(self):
        self.h = _early_harvester()
        self.parse = self.h["parse"]

    def test_keeps_the_four_nearest_the_path_never_the_base_pad(self):
        """Nearest the starter path cells first, value second: a cheap item far off loses to a dear one beside the path."""
        h = self.h
        base = h["BASE"]
        pts = {
            base: 0.1,
            self.parse("A1"): 5,  # 1 hop from A2
            self.parse("A2"): 9,  # on the path
            self.parse("B5"): 2,  # 2 hops
            self.parse("C3"): 2,  # 1 hop
            self.parse("D9"): 1,  # 8 hops: cheapest, but far
            self.parse("D14"): 0.5,
            self.parse("H24"): 9,
        }
        keep = h["kept"](pts)
        self.assertEqual(h["PAVE_KEEP_ITEMS"], 4)
        self.assertEqual(keep, {self.parse(s) for s in ("A1", "A2", "B5", "C3")})
        self.assertNotIn(base, keep)
        # Same distance: the cheaper one.
        pts = {self.parse(s): v for s, v in (("A1", 5), ("A3", 2), ("A5", 3), ("B2", 4), ("B4", 1))}
        self.assertEqual(h["kept"](pts), {self.parse(s) for s in ("A3", "A5", "B2", "B4")})

    def test_pave_path_matches_the_starter_layout(self):
        """The early Harvester's PAVE_PATH constant is field_layout.path_cells() of the starter block at its anchor."""
        import field_layout

        block = field_layout.parse_block(field_layout.STARTER_LAYOUT)
        machines = field_layout.parse_machines(field_layout.STARTER_LAYOUT)
        _anchor, cells, _reserved = field_layout.anchor_layout(
            field_layout.FULL_LAYOUT_BASE, {}, block, machines, field_layout.STARTER_ANCHOR
        )
        self.assertEqual(tuple(field_layout.path_cells(cells, [field_layout.FULL_LAYOUT_BASE])), self.h["PAVE_PATH"])

    def test_dear_items_are_never_left(self):
        """An item worth more than PAVE_MAX_VALUE is a target even on a path cell; the library uses the same cap."""
        h = self.h
        self.assertEqual(h["PAVE_MAX_VALUE"], harvester_paving.PAVE_MAX_VALUE)
        pts = {self.parse(s): v for s, v in (("A4", 1700), ("A2", 50), ("B3", 125), ("C2", 250), ("H24", 50))}
        self.assertEqual(h["kept"](pts), {self.parse(s) for s in ("A2", "B3", "C2", "H24")})

    def test_fewer_items_are_all_left(self):
        pts = {self.parse("A2"): 1, self.parse("B5"): 2}
        self.assertEqual(self.h["kept"](pts), set(pts))

    def test_kept_items_are_never_targets_but_still_stepping_stones(self):
        h = self.h
        h["ATOMIC"] = False
        pts = {self.parse(s): v for s, v in (("A2", 1), ("A3", 1), ("A4", 1), ("A5", 1), ("A6", 50))}
        keep = h["kept"](pts)
        targets = {q: v for q, v in pts.items() if q not in keep}
        target, hop, _rate = h["plan"](self.parse("A1"), targets, 0.0, pts)
        self.assertEqual(target, self.parse("A6"))
        self.assertEqual(hop, self.parse("A2"))  # route runs over the kept items (+1 heat)
        target, _hop, _rate = h["plan"](self.parse("A1"), {}, 0.0, pts)
        self.assertIsNone(target)


class RankLooseTests(unittest.TestCase):
    def test_cheapest_first_seed_last_unknown_last(self):
        values = {"B1": (5, "scrap"), "B2": (1, "seed_sunpetal"), "B3": (1, "pebble"), "B4": (0.5, "bolt")}
        self.assertEqual(rank_loose(["B1", "B2", "B3", "B4", "B0"], values), ["B4", "B3", "B2", "B1", "B0"])


def _keeper(world, unpaved=("A2", "A4", "B3", "C2"), layout=None, rules=None):
    k = FieldKeeperController.__new__(FieldKeeperController)
    k.name = "harvester_1"
    k.log = TreeConsole(module="field_keeper")
    k.init_hub()
    k.field_pass = FieldPass(1000)
    k.field_pass.layout = layout or {}
    k.field_pass.rules = rules or {}
    k.harvester = world.components["harvester_1"]
    k.unpaved = lambda layout, cells: list(unpaved)
    k.collect_at_current = lambda store=True: _collect(k, store)
    k.store_held_if_any = lambda: k.harvester.store().status in ("ok", "empty")
    return k


def _collect(k, store):
    res = k.harvester.collect()
    if res.status == "ok" and store:
        k.harvester.store()
    return res.status == "ok"


class FieldKeeperLooseTests(StubTestCase):
    ITEMS = {
        "D1": ("bolt", 2.0),
        "D2": ("scrap", 8.0),
        "D3": ("pebble", 1.0),
        "D4": ("wire", 3.0),
        "D5": ("gear", 12.0),
        "D6": ("seed_sunpetal", 2.5),
    }

    def test_reserves_the_cheapest_for_paving(self):
        self.world.add_field_harvester(self.ITEMS)
        k = _keeper(self.world)
        paving, clear = k.split_loose({}, {}, list(self.ITEMS))
        self.assertEqual(paving, ["D3", "D1", "D6", "D4"])
        self.assertEqual(sorted(clear), ["D2", "D5"])
        k = _keeper(self.world, unpaved=("A2",))  # three cells already paved: one item kept
        self.assertEqual(k.split_loose({}, {}, list(self.ITEMS))[0], ["D3"])

    def test_full_layout_clears_everything_without_a_scan(self):
        self.world.add_field_harvester(self.ITEMS)
        k = _keeper(self.world, unpaved=())
        k.loose_values = lambda loose: self.fail("Scanner read without an unpaved path cell")
        self.assertEqual(k.split_loose({}, {}, list(self.ITEMS)), ([], list(self.ITEMS)))

    def test_dear_items_never_pave_and_are_swapped_off_the_path(self):
        cap = harvester_paving.PAVE_MAX_VALUE
        items = {
            "D1": ("crystal_shard", cap + 1),
            "D2": ("soil_sample", 50.0),
            "A4": ("crystal_shard", 1700.0),  # on the path
            "A2": ("soil_sample", 50.0),  # on the path
            "B3": ("seed_crowncap", cap + 5),  # on the path: a paving seed stays
        }
        self.world.add_field_harvester(items)
        k = _keeper(self.world, unpaved=("C2",))
        paving, clear = k.split_loose({}, {}, ["D1", "D2"], ["A4", "A2", "B3"])
        self.assertEqual(paving, ["D2"])
        self.assertEqual(clear, ["D1", "A4"])
        k = _keeper(self.world, unpaved=())  # paved path, nothing loose: the dear road item still goes
        self.assertEqual(k.split_loose({}, {}, [], ["A4", "A2", "B3"]), ([], ["A4"]))

    def test_no_scanner_keeps_by_sector(self):
        self.world.add_field_harvester(self.ITEMS, scanner=False)
        k = _keeper(self.world, unpaved=("A2", "A4"))
        self.assertEqual(k.split_loose({}, {}, ["D5", "D2", "D1"]), (["D1", "D2"], ["D5"]))

    def test_clear_sells_but_keeps_layout_seeds(self):
        shop = self.world.services["shop"]
        shop.prices.update({"scrap": 8, "seed_sunpetal": 2})
        field = self.world.add_field_harvester(self.ITEMS, position="D2")
        layout = {"E1": "sunpetal"}
        k = _keeper(self.world, unpaved=(), layout=layout, rules={"sunpetal": {"seed_id": "seed_sunpetal"}})
        self.assertTrue(k.clear_here())
        self.assertEqual(shop.sold, {"scrap": 1})
        self.assertEqual(self.world.inventory.count("scrap"), 0)
        field.position_id = "D6"
        self.assertTrue(k.clear_here())
        self.assertEqual(shop.sold, {"scrap": 1})  # a layout seed is kept
        self.assertEqual(self.world.inventory.count("seed_sunpetal"), 1)
        field.position_id = "A9"
        self.assertFalse(k.clear_here())  # nothing there
        self.assertEqual(field.held, "")

    def test_unsellable_item_stays_in_inventory(self):
        self.world.services["shop"].not_sellable.add("bolt")
        self.world.add_field_harvester(self.ITEMS, position="D1")
        k = _keeper(self.world, unpaved=())
        self.assertTrue(k.clear_here())
        self.assertEqual(self.world.inventory.count("bolt"), 1)

    def test_scanner_values_are_cached_per_loose_set(self):
        field = self.world.add_field_harvester(self.ITEMS)
        k = _keeper(self.world)
        reads = []
        scanner = self.world.components[harvester_paving.SCANNER_ID]
        original = scanner.get_scanned
        scanner.get_scanned = lambda: reads.append(1) or original()
        k.loose_values(["D1", "D2"])
        k.loose_values(["D2", "D1"])
        self.assertEqual(len(reads), 1)
        field.items.pop("D1")
        self.assertEqual(k.loose_values(["D2"]), {"D2": (8.0, "scrap")})
        self.assertEqual(len(reads), 2)


if __name__ == "__main__":
    unittest.main()
