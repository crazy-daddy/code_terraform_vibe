"""FieldKeeperController.choose() priority order and the FieldPass record (lib/field_keeper.py, lib/harvester_pass.py)."""

import unittest

import field_keeper
from field_keeper import (
    INVENTORY_FULL_RELIEVED_RETRY_TICKS,
    INVENTORY_FULL_RETRY_TICKS,
    ITEM_SWEEP_MAX_HEAT,
    LOCAL_ROUTE_COST,
    PAVE_ITEM_MAX_COST,
    REBALANCE_COOLDOWN_TICKS,
    SWEEP_REACH_COST,
    FieldKeeperController,
)
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

    def level(self, name):
        return self


def _within(costs, sectors, limit):
    """nearest_within() over a {sector: route cost} map (unnamed sectors cost 100)."""
    if not sectors:
        return None
    cost, target = min([(costs.get(s, 100.0), s) for s in sectors])
    return (cost, target) if cost <= limit else None


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
    k.inventory_full_wait = INVENTORY_FULL_RETRY_TICKS
    k.rebalance_tick = -REBALANCE_COOLDOWN_TICKS
    k.sweeping = due.get("sweeping", False)
    k.idle_since = None
    k.real_seconds_per_hour = 1.0
    k.harvester = type("H", (), {"cell": lambda self, sector: _Cell(None)})()
    costs = due.get("costs", {})  # route cost per target; unnamed targets are far
    k.field_pass = FieldPass(1000)
    k.field_pass.set_view({"A1": None}, {"A1": "empty"}, {})
    k.field_pass.spare_items = due.get("spare_items", [])
    k.field_pass.clear_items = due.get("clear_items", [])
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
        "stale_targets": lambda layout, cells: dict(due.get("stale", {})),
        "pave_cooling": lambda tick: due.get("pave_cooling", False),
        "get_heat": lambda: due.get("heat", 0.0),
        "unpaved": lambda layout, cells: list(due.get("unpaved", [])),
        "pave_due": lambda layout, cells: bool(due.get("unpaved")),
        "pave_first": lambda layout, cells, rules, spare_items, mine, curr_tick: bool(due.get("pave_first")),
        "pave_seed_ready": lambda cells, rules, mine: due.get("pave_seed", False),
        "get_position": lambda: "B2",
        "nearest": lambda sectors, cells: min([(costs.get(s, 100.0), s) for s in sectors])[1],
        "nearest_within": lambda sectors, cells, limit: _within(costs, sectors, limit),
        "plan_note": lambda: "planned",
        "game_time": lambda ticks: f"{ticks} ticks",
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
    "stale": {"F6": "uproot"},
    "plant": [("G7", "crowncap")],
    "unpaved": ["A2"],
    "spare_items": ["H8"],
    "clear_items": ["H9"],
    "costs": {"E5": 5.0, "F6": 5.0, "G7": 5.0, "A2": 5.0, "H8": 5.0, "H9": 5.0},  # all local: rank order decides
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
            "sweep": ("stale",),
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
        self.assertEqual(seen, ["amplify", "stray", "build", "care", "harvest", "sweep", "plant", "pave", "collect"])
        self.assertEqual(CHOICE_KINDS, (*seen, "idle"))

    def test_far_sweep_waits_for_other_work(self):
        """No local work: a far stale crop doesn't start a sweep while anything else is due (seen live: 11 hops for one crop past 11 plantable cells)."""
        due = {"stale": {"F11": "harvest"}, "costs": {"F11": 75.0, "G7": 30.0}}
        k, choice = self.choose(plant=[("G7", "crowncap")], **due)
        self.assertEqual(choice, Choice("plant", "G7", "crowncap"))
        self.assertFalse(k.sweeping)
        # A local stale crop still starts it ahead of planting.
        self.assertEqual(
            self.choose(plant=[("G7", "crowncap")], stale={"F11": "harvest"}, costs={"F11": 5.0, "G7": 5.0})[1].kind,
            "sweep",
        )
        # Nothing else due: the far sweep starts.
        k, choice = self.choose(**due)
        self.assertEqual(choice, Choice("sweep", "F11", "harvest"))
        self.assertTrue(k.sweeping)

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

    def test_build_deploys_nearest_crop_automator_first(self):
        _k, choice = self.choose(
            full=True,
            missing={"B2": "grow_lamp", "C7": "crop_automator", "F12": "crop_automator"},
            deploys={"B2": "grow_lamp", "C7": "crop_automator", "F12": "crop_automator"},
            plant=[("A1", "crowncap")],
            rank={"A1": 0, "B2": 1, "C7": 2, "F12": 3},
            costs={"A1": 1.0, "B2": 1.0, "C7": 30.0, "F12": 10.0},
        )
        self.assertEqual(choice, Choice("build", "F12", ("deploy", "crop_automator")))

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

    def test_clear_only_unreserved_items_with_headroom(self):
        hot = ITEM_SWEEP_MAX_HEAT + 1
        self.assertEqual(self.choose(spare_items=["H8"], clear_items=["H9"], unpaved=["A2"])[1].kind, "pave")
        self.assertEqual(self.choose(spare_items=["H8"], clear_items=["H9"], heat=hot, unpaved=["A2"])[1].kind, "idle")
        self.assertEqual(self.choose(clear_items=["H9"], heat=hot)[1].kind, "idle")
        self.assertEqual(self.choose(spare_items=["H8"])[1].kind, "idle")  # kept for paving: never cleared
        self.assertEqual(self.choose(spare_items=["H8"], clear_items=["H9"])[1], Choice("collect", "H9"))
        self.assertEqual(
            self.choose(spare_items=["H8"], clear_items=["H9"], unpaved=["A2"], pave_cooling=True)[1],
            Choice("collect", "H9"),
        )

    def test_locality_near_plant_beats_far_harvest(self):
        """A plant within LOCAL_ROUTE_COST wins over a farther harvest; both far: rank order."""
        due = {"harvest": ["E5"], "plant": [("G7", "crowncap")], "costs": {"E5": 40.0, "G7": LOCAL_ROUTE_COST}}
        self.assertEqual(self.choose(**due)[1], Choice("plant", "G7", "crowncap"))
        due["costs"] = {"E5": 40.0, "G7": LOCAL_ROUTE_COST + 0.5}
        self.assertEqual(self.choose(**due)[1], Choice("harvest", "E5"))
        due["costs"] = {"E5": 3.0, "G7": 2.0}  # both local: rank order
        self.assertEqual(self.choose(**due)[1], Choice("harvest", "E5"))

    def test_locality_never_preempts_hard_priorities(self):
        """Care, pave_first (material near), build and strays stay strict: a nearer plant does not jump them."""
        near = {"plant": [("G7", "crowncap")], "costs": {"G7": 0.0, "D4": 90.0, "C3": 90.0, "A2": LOCAL_ROUTE_COST}}
        self.assertEqual(self.choose(care={"D4": ["water"]}, **near)[1].kind, "care")
        self.assertEqual(self.choose(pave_first=True, unpaved=["A2"], **near)[1].kind, "pave")
        self.assertEqual(self.choose(strays={"C3": "sprinkler"}, **near)[1].kind, "stray")
        self.assertEqual(self.choose(amplify=True, **near)[1].kind, "amplify")

    def test_sweep_starts_and_stays_nearest_first(self):
        """A started sweep takes the nearest stale crop in reach ahead of harvest and plant; mature -> harvest, growing -> uproot."""
        stale = {"A10": "harvest", "A11": "uproot", "A12": "uproot"}
        costs = {"A10": 30.0, "A11": 50.0, "A12": 60.0, "E5": 40.0, "G7": 40.0}
        k, choice = self.choose(stale=stale, costs=costs)
        self.assertEqual(choice, Choice("sweep", "A10", "harvest"))
        self.assertTrue(k.sweeping)
        # Running: nearest in reach wins over a (farther, higher-ranked) harvest and a plant.
        costs = {"A11": 2.5, "A12": 5.0, "E5": 40.0, "G7": 40.0}
        k, choice = self.choose(
            stale={"A11": "uproot", "A12": "uproot"},
            harvest=["E5"],
            plant=[("G7", "crowncap")],
            costs=costs,
            sweeping=True,
        )
        self.assertEqual(choice, Choice("sweep", "A11", "uproot"))
        self.assertTrue(k.sweeping)
        # Even a local harvest waits while a stale crop is in reach.
        costs = {"A12": 5.0, "E5": 1.0}
        self.assertEqual(
            self.choose(stale={"A12": "uproot"}, harvest=["E5"], costs=costs, sweeping=True)[1],
            Choice("sweep", "A12", "uproot"),
        )
        # Sparse old zone: the next stale crop is beyond the reach but still nearer than any layout work.
        costs = {"A12": SWEEP_REACH_COST + 10, "E5": 60.0, "G7": 70.0}
        k, choice = self.choose(
            stale={"A12": "uproot"}, harvest=["E5"], plant=[("G7", "crowncap")], costs=costs, sweeping=True
        )
        self.assertEqual(choice, Choice("sweep", "A12", "uproot"))
        self.assertTrue(k.sweeping)
        # Layout work as near as the nearest stale crop beyond reach: the zone is behind, the sweep ends.
        costs = {"A12": SWEEP_REACH_COST + 10, "E5": SWEEP_REACH_COST + 5}
        k, choice = self.choose(stale={"A12": "uproot"}, harvest=["E5"], costs=costs, sweeping=True)
        self.assertEqual(choice, Choice("harvest", "E5"))
        self.assertFalse(k.sweeping)

    def test_running_sweep_beats_care_and_pave_first(self):
        """A running sweep with stale crops in its zone goes ahead of care (even a lapsing one) and pave_first."""
        due = {"stale": {"A11": "uproot"}, "costs": {"A11": 2.5}, "sweeping": True}
        # Seen live: a care tour pulled the Harvester 10 empty hops back from the old zone after one crop.
        k, choice = self.choose(care={"D4": ["water"]}, **due)
        self.assertEqual(choice, Choice("sweep", "A11", "uproot"))
        self.assertTrue(k.sweeping)
        # Zone done (no stale crop in reach, layout work nearer): care is back first.
        done = {
            "stale": {"A11": "uproot"},
            "harvest": ["E5"],
            "costs": {"A11": SWEEP_REACH_COST + 10, "E5": SWEEP_REACH_COST + 5},
            "sweeping": True,
        }
        k, choice = self.choose(care={"D4": ["water"]}, **done)
        self.assertEqual(choice.kind, "care")
        self.assertFalse(k.sweeping)
        # Not sweeping: care still preempts starting one.
        self.assertEqual(
            self.choose(care={"D4": ["water"]}, stale={"A11": "uproot"}, costs={"A11": 2.5})[1].kind, "care"
        )
        # Seen live: the paving item was near, so pave_first carried it out of the old zone mid-sweep.
        self.assertEqual(self.choose(pave_first=True, unpaved=["A2"], **due)[1], Choice("sweep", "A11", "uproot"))
        # Zone behind (layout work nearer than the last stale crop): the sweep is done, pave_first is strict again.
        far = {
            "stale": {"A11": "uproot"},
            "harvest": ["E5"],
            "costs": {"A11": SWEEP_REACH_COST + 10, "E5": SWEEP_REACH_COST + 5},
            "sweeping": True,
        }
        self.assertEqual(self.choose(pave_first=True, unpaved=["A2"], **far)[1].kind, "pave")

    def test_inventory_full_pauses_the_sweep(self):
        """During the harvest pause stale crops wait too (harvest and uproot both fill Inventory)."""
        due = {"stale": {"A11": "uproot"}, "inventory_full_tick": 999, "sweeping": True}
        k, choice = self.choose(**due)
        self.assertEqual(choice.kind, "idle")
        self.assertFalse(k.sweeping)

    def test_starter_paves_before_harvest_and_plant(self):
        """pave_first() (starter, material at hand) ranks after care, ahead of harvest, sweep and plant, at any heat."""
        due = {
            "harvest": ["E5"],
            "stale": {"F6": "uproot"},
            "plant": [("G7", "crowncap")],
            "unpaved": ["A2"],
            "pave_first": True,
            "heat": 95.0,
            "costs": {"A2": 5.0},  # material near: strict
        }
        self.assertEqual(self.choose(**due)[1].kind, "pave")
        self.assertEqual(self.choose(care={"D4": ["water"]}, **due)[1].kind, "care")
        due.pop("pave_first")
        self.assertEqual(self.choose(**due)[1].kind, "harvest")

    def test_far_paving_item_does_not_starve_planting(self):
        """A far spare item: plant first; the item is taken once local (carry-along) or once nothing is plantable."""
        due = {
            "plant": [("G7", "crowncap")],
            "unpaved": ["A2"],
            "spare_items": ["H8"],
            "pave_first": True,
            "heat": 95.0,
        }
        due["costs"] = {"H8": 30.0, "G7": 40.0}
        self.assertEqual(self.choose(**due)[1], Choice("plant", "G7", "crowncap"))
        due["costs"] = {"H8": LOCAL_ROUTE_COST, "G7": 40.0}  # near the item now: strict, at any heat
        self.assertEqual(self.choose(**due)[1], Choice("pave", None, "item"))
        due["costs"] = {"H8": 30.0, "G7": 5.0}
        self.assertEqual(self.choose(**due)[1].kind, "plant")
        due.pop("plant")  # nothing plantable: strict again
        self.assertEqual(self.choose(**due)[1], Choice("pave", None, "item"))

    def test_item_beyond_max_cost_paves_with_a_seed(self):
        """A spare item beyond PAVE_ITEM_MAX_COST is left when a paving seed is at home; without one the item is fetched."""
        due = {
            "unpaved": ["A2"],
            "spare_items": ["H8"],
            "pave_first": True,
            "costs": {"H8": PAVE_ITEM_MAX_COST + 1, "A2": 5.0},
        }
        self.assertEqual(self.choose(pave_seed=True, **due)[1], Choice("pave", None, "seed"))
        self.assertEqual(self.choose(**due)[1], Choice("pave", None, "item"))
        k = _keeper(pave_seed=True, **due)
        seen = []
        k.pave_step = lambda layout, cells, rules, spare_items: seen.append(list(spare_items)) or True
        k.run_choice(k.field_pass, k.choose(k.field_pass))
        self.assertEqual(seen, [[]])  # a seed: no item handed to pave_step()

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
        self.rebalances = []
        self.room = 0
        for name, fn in (
            ("rebalance_inventory_to_warehouses", lambda: self.rebalances.append(field_keeper.now_tick())),
            ("inventory_room", lambda item_id, keep=0: self.room),
        ):
            self.addCleanup(setattr, field_keeper, name, getattr(field_keeper, name))
            setattr(field_keeper, name, fn)

    def test_clear_crop_before_deploy(self):
        k = _keeper()
        cell = _Cell("mature")
        k.harvester = type("H", (), {"cell": lambda self, sector: cell})()
        k.harvest_current = lambda: setattr(cell, "status", "empty") or True
        self.assertTrue(k.clear_crop_here())
        cell.status = "growing"
        k.uproot_current = lambda: setattr(cell, "status", "empty") or True
        self.assertTrue(k.clear_crop_here())
        cell.status = "stalled"
        k.uproot_current = lambda: False
        self.assertFalse(k.clear_crop_here())
        self.assertEqual(k._deploy_failures(), {"B2": 1000})

    def test_inventory_full_sets_the_pause(self):
        k = _keeper()
        k.harvest_here = lambda: "inventory_full"
        self.assertFalse(k.harvest_current())
        self.assertEqual(k.inventory_full_tick, 1000)
        k = _keeper()
        k.harvest_here = lambda: "partial"
        self.assertTrue(k.harvest_current())
        self.assertIsNone(k.inventory_full_tick)

    def test_partial_harvest_waits_for_room_and_harvests_the_rest(self):
        """partial: wait for Inventory room, then the rest on the spot; still no room -> no retry."""
        k = _keeper()
        answers = ["partial", "ok"]
        k.harvest_here = lambda: answers.pop(0)
        self.room = 20
        self.assertTrue(k.harvest_current())
        self.assertEqual((answers, self.rebalances), ([], []))
        self.assertIsNone(k.inventory_full_tick)
        k = _keeper()
        answers = ["partial", "ok"]
        k.harvest_here = lambda: answers.pop(0)
        self.room = 0
        self.assertTrue(k.harvest_current())
        self.assertEqual(answers, ["ok"])
        # inventory_full with room after the wait: harvested at once, no pause.
        k = _keeper()
        answers = ["inventory_full", "partial"]
        k.harvest_here = lambda: answers.pop(0)
        self.room = 20
        self.assertTrue(k.harvest_current())
        self.assertIsNone(k.inventory_full_tick)

    def test_inventory_full_rebalances_with_cooldown(self):
        """inventory_full: one early rebalance per REBALANCE_COOLDOWN_TICKS; room for Forage afterwards -> short pause."""
        k = _keeper()
        k.harvest_here = lambda: "inventory_full"
        self.room = 20
        k.harvest_current()
        self.assertEqual(self.rebalances, [1000])
        self.assertEqual(k.inventory_full_wait, INVENTORY_FULL_RELIEVED_RETRY_TICKS)
        self.assertFalse(k.harvest_ready(1000 + INVENTORY_FULL_RELIEVED_RETRY_TICKS - 1))
        self.assertTrue(k.harvest_ready(1000 + INVENTORY_FULL_RELIEVED_RETRY_TICKS))
        # Full again inside the cooldown: no second rebalance, the long pause.
        field_keeper.now_tick = lambda: 1000 + INVENTORY_FULL_RELIEVED_RETRY_TICKS
        k.harvest_current()
        self.assertEqual(self.rebalances, [1000])
        self.assertEqual(k.inventory_full_wait, INVENTORY_FULL_RETRY_TICKS)
        # After the cooldown: rebalance again; still no room -> the long pause.
        field_keeper.now_tick = lambda: 1000 + REBALANCE_COOLDOWN_TICKS
        self.room = 0
        k.uproot_here = lambda: "inventory_full"
        self.assertFalse(k.uproot_current())
        self.assertEqual(self.rebalances, [1000, 1000 + REBALANCE_COOLDOWN_TICKS])
        self.assertEqual(k.inventory_full_wait, INVENTORY_FULL_RETRY_TICKS)

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


class _Cell:
    def __init__(self, status, plant=None):
        self.status = status
        self.plant = plant


def _field(planted=None, items=()):
    """{sector: _Cell} of the whole grid: empty, plus `planted` {sector: (status, plant)} and item cells."""
    cells = {FieldKeeperController.rc_to_sector(r, c): _Cell("empty") for r in range(8) for c in range(1, 25)}
    for s in items:
        cells[s] = _Cell("item")
    for s, (status, plant) in (planted or {}).items():
        cells[s] = _Cell(status, plant)
    return cells


def _real_keeper(cells, position="A1"):
    """A FieldKeeperController over `cells` with the real heat search, stale and harvest selection."""
    k = FieldKeeperController.__new__(FieldKeeperController)
    k.name = "harvester_1"
    k.log = _Log()  # type: ignore[assignment]
    k.init_hub()
    k.init_heat_model(None)
    k.get_position = lambda: position
    k.field_pass = FieldPass(1000)
    statuses = {s: c.status for s, c in cells.items()}
    k.field_pass.set_view(
        cells, statuses, {s: c for s, c in cells.items() if c.status in ("growing", "stalled", "mature")}
    )
    return k


class SelectionTests(StubTestCase):
    """The real target sources behind choose(): nearest_within() over the route map, stale vs layout crops."""

    def test_nearest_within_reads_route_cost(self):
        cells = _field(items=("A2",))
        k = _real_keeper(cells)
        # A1 -> A2 (item, 1 + 1.5) -> A3 (empty, 7 + 1.5) = 11.
        self.assertEqual(k.nearest_within(["A3", "H24"], cells, LOCAL_ROUTE_COST), (11.0, "A3"))
        self.assertIsNone(k.nearest_within(["A3"], cells, 10.5))
        self.assertIsNone(k.nearest_within(["H24"], cells, LOCAL_ROUTE_COST))
        self.assertEqual(k.cheapest(["A3", "H24"], k.field_pass.statuses), "A3")  # same map, unbounded
        self.assertIsNone(k.nearest_within([], cells, 99.0))

    def test_stale_crops_outside_the_layout(self):
        """Mature stale -> harvest, growing/stalled stale -> uproot (unused species too); layout crops stay harvest_targets()."""
        layout = {"A1": "sunpetal", "A3": "dewmoss"}
        planted = {
            "A1": ("mature", "sunpetal"),  # layout crop
            "A3": ("growing", "sunpetal"),  # wrong species on a layout cell
            "C14": ("mature", "dewmoss"),  # old zone, mature
            "C15": ("growing", "dewmoss"),  # old zone, growing
            "D16": ("stalled", "brinethorn"),  # old zone, species unused by the layout
        }
        cells = _field(planted)
        k = _real_keeper(cells)
        self.assertEqual(
            k.stale_targets(layout, cells), {"A3": "uproot", "C14": "harvest", "C15": "uproot", "D16": "uproot"}
        )
        self.assertEqual(k.harvest_targets(cells, layout), ["A1"])
        k._plant_failures()["C15"] = 900  # a failed uproot cools down
        self.assertNotIn("C15", k.stale_targets(layout, cells))

    def test_sweep_walks_the_stale_zone_nearest_first(self):
        """From inside the old zone each step takes the nearest stale crop, ahead of a far layout harvest."""
        layout = {"A1": "sunpetal"}
        planted = {
            "A1": ("mature", "sunpetal"),
            "C14": ("growing", "dewmoss"),
            "C15": ("mature", "dewmoss"),
            "C17": ("growing", "dewmoss"),
        }
        order = []
        position = "C13"
        sweeping = True
        while True:
            cells = _field(planted)
            k = _real_keeper(cells, position)
            for name, fn in {
                "amplify_due": lambda tick: False,
                "stray_machines": dict,
                "missing_machines": lambda cells: {},
                "care_targets": lambda cells, rules, refresh_h=None, kept=None: {},
                "pave_first": lambda *a: False,
                "pave_due": lambda layout, cells: False,
                "plant_targets": lambda mine, cells: [],
                "automated_cells": lambda: set(),
                "get_heat": lambda: 0.0,
                "plan_note": lambda: "planned",
            }.items():
                setattr(k, name, fn)
            k.care_batch, k.build_phase, k.work_groups, k.sweeping = {}, None, [], sweeping
            k.inventory_full_tick, k.inventory_full_wait = None, INVENTORY_FULL_RETRY_TICKS
            k.field_pass.layout, k.field_pass.mine, k.field_pass.spare_items, k.field_pass.clear_items = (
                layout,
                {},
                [],
                [],
            )
            choice = k.choose(k.field_pass)
            if choice.kind != "sweep":
                break
            order.append((choice.target, choice.detail))
            position, sweeping = choice.target, k.sweeping
            del planted[choice.target]
        self.assertEqual(order, [("C14", "uproot"), ("C15", "harvest"), ("C17", "uproot")])
        self.assertEqual(choice, Choice("harvest", "A1"))

    def test_care_tour_skips_stale_crops(self):
        """A stale crop with a treatment due gets none (no salt before its uproot); a layout crop still does."""
        layout = {"A1": "sunpetal"}
        cells = _field({"A1": ("growing", "sunpetal"), "C14": ("growing", "saltbloom")})

        def choose(care):
            k = _real_keeper(cells, "C13")
            for name, fn in {
                "amplify_due": lambda tick: False,
                "stray_machines": dict,
                "missing_machines": lambda cells: {},
                "care_targets": lambda cells, rules, refresh_h=None, kept=None: dict(care),
                "pave_first": lambda *a: False,
                "pave_due": lambda layout, cells: False,
                "plant_targets": lambda mine, cells: [],
                "automated_cells": lambda: set(),
                "get_heat": lambda: 0.0,
                "plan_note": lambda: "planned",
            }.items():
                setattr(k, name, fn)
            k.care_batch, k.build_phase, k.work_groups, k.sweeping = {}, None, [], False
            k.inventory_full_tick, k.inventory_full_wait = None, INVENTORY_FULL_RETRY_TICKS
            fp = k.field_pass
            fp.layout, fp.mine, fp.spare_items, fp.clear_items = layout, {}, [], []
            return k.choose(fp)

        self.assertEqual(choose({"C14": ["salt"]}), Choice("sweep", "C14", "uproot"))
        self.assertEqual(choose({"C14": ["salt"], "A1": ["light"]}), Choice("care", "A1", ["light"]))


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
