"""Garden-aligned starter layout and its slow-crop harvest rule (lib/field_layout.py, lib/harvester_planting.py)."""

import builtins
import unittest

import field_layout
from field_keeper import FieldKeeperController
from harness import StubTestCase
from harvester_pass import FieldPass


def _starter():
    block = field_layout.parse_block(field_layout.STARTER_LAYOUT)
    machines = field_layout.parse_machines(field_layout.STARTER_LAYOUT)
    return field_layout.anchor_layout(field_layout.FULL_LAYOUT_BASE, {}, block, machines, field_layout.STARTER_ANCHOR)


class StarterLayoutTests(unittest.TestCase):
    def test_every_starter_cell_is_a_full_crowncap_cell(self):
        anchor, cells, reserved = _starter()
        self.assertEqual(anchor, "A1")
        self.assertEqual(reserved, {})
        full, _reserved, _garden = field_layout.full_layout(field_layout.full_chunk_count("crowncap"), "crowncap")
        for sector, species in cells.items():
            self.assertEqual(full.get(sector), species, sector)

    def test_valid_with_13_species(self):
        _anchor, cells, _reserved = _starter()
        self.assertEqual(field_layout.validate(cells), [])
        self.assertEqual(len(set(cells.values())), 13)
        self.assertNotIn("sunspur", cells.values())
        self.assertNotIn("pondmoss", cells.values())

    def test_keepers_are_the_fast_starter_species(self):
        _anchor, cells, _reserved = _starter()
        slow = set(field_layout.slow_species(field_layout.FALLBACK_RULES))
        self.assertEqual(set(field_layout.STARTER_KEEP), set(cells.values()) - slow)
        self.assertEqual(
            set(cells.values()) & slow, {"crowncap", "glowvine", "saltbloom", "saltmate", "brinethorn", "grandbloom"}
        )

    def test_path_joins_the_patches(self):
        _anchor, cells, _reserved = _starter()
        self.assertEqual(field_layout.path_cells(cells, [field_layout.FULL_LAYOUT_BASE]), ["A2", "A4", "B3", "C2"])

    def test_anchor_falls_back_to_search_when_blocked(self):
        block = field_layout.parse_block(field_layout.STARTER_LAYOUT)
        machines = field_layout.parse_machines(field_layout.STARTER_LAYOUT)
        anchor, cells, _reserved = field_layout.anchor_layout("E13", {"A1": "provider"}, block, machines, "A1")
        self.assertNotEqual(anchor, "A1")
        self.assertTrue(cells)


def _row(status, plant, growth):
    return (status, plant, growth, None, None, None, False, False, False)


class SlowCropHoldTests(StubTestCase):
    def keeper(self, mode="starter", stock=None, rows=None, plants=None):
        _anchor, layout, _reserved = _starter()
        k = FieldKeeperController.__new__(FieldKeeperController)
        k.name = "harvester_1"
        k.init_hub()
        k.set_layout_state(mode, {}, field_layout.starter_kept(layout))
        k.field_pass = FieldPass(1000)
        k.field_pass.rules = field_layout.FALLBACK_RULES
        k.field_pass.layout = layout
        stock = stock or {}
        k.stock_count = lambda item_id: stock.get(item_id, 0)
        k.planted_rows = lambda cells: list(rows or [])
        plants = plants or {}
        k.harvester = builtins.type(
            "H", (), {"cell": lambda self, s: builtins.type("C", (), {"plant": plants.get(s)})()}
        )()
        return k, layout

    # A5/A6: Crowncap, F2: Saltbloom, A1: Brinethorn, A3: Lonethorn (kept), C1: empty layout gap.
    ROWS = [
        ("A5", _row("mature", "crowncap", 1.0)),
        ("A6", _row("growing", "crowncap", 1.0)),
        ("B5", _row("growing", "crowncap", 0.5)),
        ("F2", _row("mature", "saltbloom", 1.0)),
        ("A3", _row("mature", "lonethorn", 1.0)),
        ("C1", _row("mature", "crowncap", 1.0)),
    ]

    def test_hold_without_seed(self):
        k, layout = self.keeper(stock={"seed_saltbloom": 1}, rows=self.ROWS)
        self.assertEqual(sorted(k.starter_hold(layout, {}, field_layout.FALLBACK_RULES)), ["A5", "A6"])

    def test_replace_demand(self):
        k, layout = self.keeper(stock={"seed_crowncap": 1, "seed_saltbloom": 2}, rows=self.ROWS)
        self.assertEqual(k.replace_demand(layout, {}, field_layout.FALLBACK_RULES), {"seed_crowncap": 1})

    def test_full_layout_holds_nothing(self):
        k, layout = self.keeper(mode="full", rows=self.ROWS)
        self.assertEqual(k.starter_hold(layout, {}, field_layout.FALLBACK_RULES), [])
        self.assertEqual(k.replace_demand(layout, {}, field_layout.FALLBACK_RULES), {})

    def test_held_crops_are_kept_and_cared(self):
        k, layout = self.keeper(rows=self.ROWS)
        k.field_pass.held = k.starter_hold(layout, {}, field_layout.FALLBACK_RULES)
        self.assertEqual(k.kept_garden(), set(field_layout.starter_kept(layout)) | {"A5", "A6", "F2"})
        # Seed demand still counts held crops as rotation crops (stored garden only).
        self.assertEqual(set(k.garden), set(field_layout.starter_kept(layout)))

    def test_harvest_blocked_live(self):
        k, _layout = self.keeper(plants={"A5": "crowncap", "A3": "lonethorn", "C1": "crowncap"})
        self.assertTrue(k.harvest_blocked("A5"))
        self.assertFalse(k.harvest_blocked("C1"))  # not a layout cell
        self.assertFalse(k.harvest_blocked("A3"))  # keeper: kept_garden() handles it
        k, _layout = self.keeper(stock={"seed_crowncap": 1}, plants={"A5": "crowncap"})
        self.assertFalse(k.harvest_blocked("A5"))
        k, _layout = self.keeper(mode="full", plants={"A5": "crowncap"})
        self.assertFalse(k.harvest_blocked("A5"))


class PaveFirstTests(StubTestCase):
    RULES = {"sunpetal": {"blend": ["ice_algae", "snow_moss", "frost_lichen"], "seed_id": "seed_sunpetal"}}

    def keeper(self, mode="starter", stock=0, unpaved=("A2",)):
        k = FieldKeeperController.__new__(FieldKeeperController)
        k.name = "harvester_1"
        k.init_hub()
        k.set_layout_state(mode, {}, [])
        k.field_pass = FieldPass(1000)
        k.unpaved = lambda layout, cells: list(unpaved)
        k.stock_count = lambda item_id: stock
        k.cell_statuses = lambda cells: {"E1": "empty"}
        return k

    def test_material_rules(self):
        mine = {"E1": "sunpetal"}
        self.assertTrue(self.keeper().pave_first({}, {}, self.RULES, ["H8"], mine, 1000))  # loose item
        self.assertFalse(self.keeper(stock=1).pave_first({}, {}, self.RULES, [], mine, 1000))  # seed needed by E1
        self.assertTrue(self.keeper(stock=2).pave_first({}, {}, self.RULES, [], mine, 1000))
        self.assertFalse(self.keeper(unpaved=()).pave_first({}, {}, self.RULES, ["H8"], mine, 1000))
        self.assertFalse(self.keeper(mode="full").pave_first({}, {}, self.RULES, ["H8"], mine, 1000))

    def test_failed_pave_cools_down(self):
        k = self.keeper()
        k._pave_fail_tick = 900
        self.assertFalse(k.pave_first({}, {}, self.RULES, ["H8"], {}, 1000))
        self.assertTrue(k.pave_first({}, {}, self.RULES, ["H8"], {}, 900 + 3000))


if __name__ == "__main__":
    unittest.main()
