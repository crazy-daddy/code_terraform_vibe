"""FieldKeeperController.choose() priority order and the FieldPass record (lib/field_keeper.py, lib/harvester_pass.py)."""

import unittest

import field_keeper
from field_keeper import INVENTORY_FULL_RETRY_TICKS, ITEM_SWEEP_MAX_HEAT, FieldKeeperController
from harness import StubTestCase
from harvester_pass import CHOICE_KINDS, Choice, FieldPass


class _Log:
    def __init__(self):
        self.lines = []

    def debug(self, msg):
        self.lines.append(msg)

    def print(self, msg):
        self.lines.append(msg)

    def start(self, msg, level=None):
        self.lines.append(msg)

    def end(self, msg=None):
        self.lines.append(msg)


def _keeper(**due):
    """
    A FieldKeeperController without the game: every task source is a stub
    returning what `due` names (all empty by default), so choose() runs its
    priority chain only.
    """
    k = FieldKeeperController.__new__(FieldKeeperController)
    k.name = "harvester_1"
    k.log = _Log()  # type: ignore[assignment]
    k.init_hub()
    if due.get("full"):
        k.set_layout_state("full", {"B2": "grow_lamp"}, [])
    k.care_batch = {}
    k.build_phase = None
    k.work_groups = []
    k.inventory_full_tick = due.get("inventory_full_tick")
    k.idle_since = None
    k.field_pass = FieldPass(1000)
    k.field_pass.set_view({"A1": None}, {"A1": "empty"}, {})
    k.field_pass.spare_items = due.get("spare_items", [])
    stubs = {
        "amplify_due": lambda tick: due.get("amplify", False),
        "stray_machines": lambda: dict(due.get("strays", {})),
        "missing_machines": lambda cells: dict(due.get("missing", {})),
        "deploy_targets": lambda cells: dict(due.get("deploys", {})),
        "plant_targets": lambda mine, cells: list(due.get("plant", [])),
        "build_rank": lambda groups: dict(due.get("rank", {})),
        "kept_garden": lambda: set(),
        "care_targets": lambda cells, rules, refresh_h=None, kept=None: dict(due.get("care", {})),
        "harvest_targets": lambda cells, layout=None: list(due.get("harvest", [])),
        "clear_targets": lambda layout, cells: list(due.get("uproot", [])),
        "get_heat": lambda: due.get("heat", 0.0),
        "unpaved": lambda layout, cells: list(due.get("unpaved", [])),
        "pave_due": lambda layout, cells: bool(due.get("unpaved")),
        "nearest": lambda sectors, cells: min(sectors),
        "plan_note": lambda: "planned",
    }
    for name, fn in stubs.items():
        setattr(k, name, fn)
    return k


ALL_DUE = {
    "amplify": True,
    "strays": {"C3": "sprinkler"},
    "full": True,
    "missing": {"B2": "grow_lamp"},
    "deploys": {"B2": "grow_lamp"},
    "care": {"D4": ["water"]},
    "harvest": ["E5"],
    "uproot": ["F6"],
    "plant": [("G7", "crowncap")],
    "unpaved": ["A2"],
    "spare_items": ["H8"],
}


class ChooseOrderTests(StubTestCase):
    def setUp(self):
        super().setUp()
        original = field_keeper.now_tick
        field_keeper.now_tick = lambda: 1000
        self.addCleanup(setattr, field_keeper, "now_tick", original)

    def choose(self, **due):
        k = _keeper(**due)
        return k, k.choose(k.field_pass)

    def test_priority_order(self):
        """Dropping the winning source each round walks CHOICE_KINDS in order."""
        due = dict(ALL_DUE)
        drop = {
            "amplify": ("amplify",),
            "stray": ("strays",),
            "build": ("missing", "deploys", "full"),
            "care": ("care",),
            "harvest": ("harvest",),
            "uproot": ("uproot",),
            "plant": ("plant",),
            "pave": ("unpaved",),
        }
        seen = []
        while True:
            _k, choice = self.choose(**due)
            seen.append(choice.kind)
            if choice.kind not in drop:
                break
            for key in drop[choice.kind]:
                due.pop(key, None)
        self.assertEqual(seen, ["amplify", "stray", "build", "care", "harvest", "uproot", "plant", "pave", "collect"])
        self.assertEqual(CHOICE_KINDS, (*seen, "idle"))

    def test_choice_targets(self):
        self.assertEqual(self.choose(strays={"C3": "sprinkler"})[1], Choice("stray", "C3", "sprinkler"))
        self.assertEqual(self.choose(care={"D4": ["water"]})[1], Choice("care", "D4", ["water"]))
        self.assertEqual(self.choose(plant=[("G7", "crowncap")])[1], Choice("plant", "G7", "crowncap"))

    def test_build_follows_work_order_rank(self):
        _k, choice = self.choose(
            full=True,
            missing={"B2": "grow_lamp"},
            deploys={"B2": "grow_lamp"},
            plant=[("A1", "crowncap")],
            rank={"B2": 0, "A1": 5},
        )
        self.assertEqual(choice, Choice("build", "B2", ("deploy", "grow_lamp")))
        _k, choice = self.choose(
            full=True,
            missing={"B2": "grow_lamp"},
            deploys={"B2": "grow_lamp"},
            plant=[("A1", "crowncap")],
            rank={"B2": 9, "A1": 5},
        )
        self.assertEqual(choice, Choice("build", "A1", ("plant", "crowncap")))

    def test_build_phase_without_ready_cell_falls_through(self):
        k, choice = self.choose(full=True, missing={"B2": "grow_lamp"}, care={"D4": ["light"]})
        self.assertEqual(choice.kind, "care")
        self.assertTrue(k.build_phase)

    def test_inventory_full_pauses_harvest(self):
        _k, choice = self.choose(harvest=["E5"], inventory_full_tick=1000 - INVENTORY_FULL_RETRY_TICKS + 1)
        self.assertEqual(choice.kind, "idle")
        k, choice = self.choose(harvest=["E5"], inventory_full_tick=1000 - INVENTORY_FULL_RETRY_TICKS)
        self.assertEqual(choice, Choice("harvest", "E5"))
        self.assertIsNone(k.inventory_full_tick)

    def test_collect_only_once_the_path_is_paved(self):
        hot = ITEM_SWEEP_MAX_HEAT + 1
        self.assertEqual(self.choose(spare_items=["H8"], unpaved=["A2"])[1].kind, "pave")
        self.assertEqual(self.choose(spare_items=["H8"], heat=hot, unpaved=["A2"])[1].kind, "idle")
        self.assertEqual(self.choose(spare_items=["H8"], heat=hot)[1].kind, "idle")
        k = _keeper(spare_items=["H8"])
        self.assertEqual(k.choose_tail(k.field_pass), Choice("collect", "H8"))

    def test_failed_pave_ends_idle(self):
        """A pave that started and failed leaves the path unpaved: no sweep, the pass idles."""
        k = _keeper(spare_items=["H8"], unpaved=["A2"])
        calls = []
        k.pave_step = lambda layout, cells, rules, spare_items: calls.append(("pave",)) or False
        k.idle = lambda fp: calls.append(("idle",))
        k.run_choice(k.field_pass, k.choose(k.field_pass))
        self.assertEqual(calls, [("pave",), ("idle",)])
        self.assertEqual(k.field_pass.choice, Choice("pave"))


class CompositeTests(StubTestCase):
    """Controller composites over the abilities (layer 4): harvest pause, route hook."""

    def setUp(self):
        super().setUp()
        original = field_keeper.now_tick
        field_keeper.now_tick = lambda: 1000
        self.addCleanup(setattr, field_keeper, "now_tick", original)

    def test_inventory_full_sets_the_pause(self):
        k = _keeper()
        k.harvest_here = lambda: "inventory_full"
        self.assertFalse(k.harvest_current())
        self.assertEqual(k.inventory_full_tick, 1000)
        k = _keeper()
        k.harvest_here = lambda: "partial"
        self.assertTrue(k.harvest_current())
        self.assertIsNone(k.inventory_full_tick)

    def test_work_on_pass_harvests_then_plants_with_the_pass_rules(self):
        k = _keeper()
        k.field_pass.mine = {"B2": "crowncap"}
        k.field_pass.rules = {"crowncap": {}}
        calls = []
        k.harvester = type("H", (), {"get_held": lambda self: ""})()
        k.harvest_here = lambda: calls.append("harvest") or "ok"
        k.plant_here = lambda species: calls.append(("plant", species)) or True
        k.care_current = lambda rules: calls.append(("care", rules))
        k.stock_count = lambda item_id: 1
        k.work_on_pass("B2", "mature")
        self.assertEqual(calls, ["harvest", ("plant", "crowncap"), ("care", {"crowncap": {}})])
        calls.clear()
        k.inventory_full_tick = 990  # harvest paused: a mature cell on the way is left alone
        k.work_on_pass("B2", "mature")
        k.work_on_pass("C3", "empty")  # not one of the Harvester's own cells
        self.assertEqual(calls, [])


class FieldPassTests(unittest.TestCase):
    def test_marks_and_note(self):
        fp = FieldPass(100)
        fp.mark("cells", 104)
        fp.mark("rules", 104)
        fp.mark("layout", 110)
        self.assertEqual(fp.phase_note(), (10, "cells 4, layout 6"))

    def test_view_identity(self):
        cells = {"A1": None}
        fp = FieldPass(0)
        self.assertFalse(fp.has_view(cells))
        fp.set_view(cells, {"A1": "empty"}, {})
        self.assertTrue(fp.has_view(cells))
        self.assertFalse(fp.has_view(dict(cells)))

    def test_last_action_carries_over(self):
        keeper = FieldKeeperController.__new__(FieldKeeperController)
        keeper.field_pass = FieldPass(0)
        keeper.note_action("harvest@A1")
        keeper.field_pass = FieldPass(10, keeper.last_action)
        self.assertEqual(keeper.last_action, "harvest@A1")


if __name__ == "__main__":
    unittest.main()
