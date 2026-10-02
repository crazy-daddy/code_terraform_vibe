"""Stub tests for the Harvester's Yield Amplifier (8_planting/lib/harvester_amplify.py)."""
import unittest
from types import SimpleNamespace

from harness import StubTestCase

import field_keeper
import harvester_amplify
from field_keeper import FieldKeeperController, STAGE_STUCK_WARN_TICKS
from harvester_amplify import HarvesterAmplifyMixin, AMPLIFIER_ITEM_ID, AMPLIFIER_REQUESTER, AMPLIFY_RETRY_TICKS, AMPLIFY_BUSY_RETRY_TICKS


class _Log:
    def __init__(self):
        self.lines = []

    def debug(self, msg):
        self.lines.append(msg)

    def start(self, msg, level=None):
        self.lines.append(msg)

    def end(self, msg=None):
        self.lines.append(msg)


class _Harvester:
    def __init__(self, remaining=0.0, status="ok"):
        self.remaining = remaining
        self.status = status
        self.calls = 0

    def amplifier_remaining(self):
        return self.remaining

    def amplify(self):
        self.calls += 1
        if self.status == "ok":
            self.remaining += 24.0
        return SimpleNamespace(status=self.status, message="")


class _Keeper(HarvesterAmplifyMixin):
    def __init__(self, harvester, stock=1, statuses=None, machines=None):
        self.name = "harvester_1"
        self.harvester = harvester
        self.log = _Log()
        self.stock_memo = {}
        self.last_action = ""
        self.stage_busy = False
        self.stage_result: "str | None" = None
        self.stock = stock
        statuses = statuses if statuses is not None else {"A1": "growing", "A2": "growing", "A3": "mature"}
        self.step_view = ({}, statuses, {s: None for s in statuses})
        self.machines = machines or {}

    def stock_count(self, item_id):
        return self.stock if item_id == AMPLIFIER_ITEM_ID else 0

    def step_machines(self):
        return self.machines

    def stage(self, item_id, n=1):
        if self.stage_result is not None:
            self.stage_busy = self.stage_result == "busy"
            return False
        return self.stock >= n

    def act(self, method):
        return getattr(self.harvester, method)()


class AmplifyTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.clogged = []
        self.orders = {}
        patches = {
            "crop_automator_forage": lambda: self.clogged,
            "fabricator_unlocked_outputs": lambda: {AMPLIFIER_ITEM_ID},
            "set_upgrade_order": lambda r, items: self.orders.__setitem__(("upgrade", r), dict(items)),
            "set_backlog_order": lambda r, items: self.orders.__setitem__(("backlog", r), dict(items)),
        }
        for name, fn in patches.items():
            original = getattr(harvester_amplify, name)
            setattr(harvester_amplify, name, fn)
            self.addCleanup(setattr, harvester_amplify, name, original)

    def test_applies_when_expired(self):
        keeper = _Keeper(_Harvester())
        self.assertTrue(keeper.amplify_step(100))
        self.assertEqual(keeper.harvester.calls, 1)
        self.assertEqual(keeper.last_action, "amplify")

    def test_waits_while_running(self):
        keeper = _Keeper(_Harvester(remaining=0.5))
        self.assertFalse(keeper.amplify_step(100))
        self.assertEqual(keeper.harvester.calls, 0)

    def test_no_dose_at_home(self):
        keeper = _Keeper(_Harvester(), stock=0)
        self.assertFalse(keeper.amplify_step(100))

    def test_too_few_growing(self):
        keeper = _Keeper(_Harvester(), statuses={"A1": "growing", "A2": "mature", "A3": "stalled"})
        self.assertFalse(keeper.amplify_step(100))

    def test_majority_clogged_blocks(self):
        machines = {"B1": "crop_automator", "B2": "crop_automator", "B3": "crop_automator", "B4": "grow_lamp"}
        keeper = _Keeper(_Harvester(), machines=machines)
        self.clogged = [("ca_1", 50000, True, False), ("ca_2", 49000, True, False), ("ca_3", 10, False, False)]
        self.assertFalse(keeper.amplify_step(100))
        self.clogged = [("ca_1", 50000, True, False), ("ca_3", 10, False, False)]
        self.assertTrue(keeper.amplify_step(100))

    def test_failed_apply_cools_down(self):
        keeper = _Keeper(_Harvester(status="locked"))
        self.assertTrue(keeper.amplify_step(100))
        self.assertFalse(keeper.amplify_step(100 + AMPLIFY_RETRY_TICKS - 1))
        self.assertTrue(keeper.amplify_step(100 + AMPLIFY_RETRY_TICKS))
        self.assertEqual(keeper.harvester.calls, 2)

    def test_busy_warehouses_retry_soon(self):
        keeper = _Keeper(_Harvester())
        keeper.stage_result = "busy"
        self.assertTrue(keeper.amplify_step(100))
        keeper.stage_result = None
        self.assertFalse(keeper.amplify_step(100 + AMPLIFY_BUSY_RETRY_TICKS - 1))
        self.assertTrue(keeper.amplify_step(100 + AMPLIFY_BUSY_RETRY_TICKS))
        self.assertEqual(keeper.harvester.calls, 1)

    def test_other_stage_failure_retries_late(self):
        keeper = _Keeper(_Harvester())
        keeper.stage_result = "source_empty"
        self.assertTrue(keeper.amplify_step(100))
        keeper.stage_result = None
        self.assertFalse(keeper.amplify_step(100 + AMPLIFY_BUSY_RETRY_TICKS))

    def test_skip_reason_logged_once(self):
        keeper = _Keeper(_Harvester(remaining=5.0))
        keeper.amplify_step(100)
        keeper.harvester.remaining = 4.0
        keeper.amplify_step(101)
        self.assertEqual(len(keeper.log.lines), 1)

    def test_orders_need_and_backlog(self):
        keeper = _Keeper(_Harvester())
        need = keeper.publish_amplifier_order(100)
        self.assertEqual(need, {AMPLIFIER_ITEM_ID: harvester_amplify.AMPLIFIER_NEED})
        self.assertEqual(self.orders[("backlog", AMPLIFIER_REQUESTER)], {AMPLIFIER_ITEM_ID: harvester_amplify.AMPLIFIER_STOCK})

    def test_no_recipe_clears_orders(self):
        harvester_amplify.fabricator_unlocked_outputs = lambda: set()
        keeper = _Keeper(_Harvester())
        self.assertEqual(keeper.publish_amplifier_order(100), {})
        self.assertEqual(self.orders[("upgrade", AMPLIFIER_REQUESTER)], {})
        self.assertEqual(self.orders[("backlog", AMPLIFIER_REQUESTER)], {})

    def test_requester_is_standing_and_recurring(self):
        import production
        self.assertIn(AMPLIFIER_REQUESTER, production.STANDING_ORDER_REQUESTERS)
        self.assertIn(AMPLIFIER_REQUESTER, production.RECURRING_ORDER_REQUESTERS)


class _Store:
    def __init__(self, held, answer):
        self.held = held
        self.answer = answer
        self.calls = 0

    def count(self, item_id):
        return self.held

    def transfer_to(self, target, item_id, count):
        self.calls += 1
        moved = min(count, self.held) if self.answer == "ok" else 0
        return SimpleNamespace(status=self.answer, moved=moved, requested=count)


class _ConsoleLog(_Log):
    def __init__(self):
        super().__init__()
        self.warnings = []

    def level(self, name):
        log = self

        class _Level:
            def print(self, msg):
                log.warnings.append((name, msg))
        return _Level()


class StageTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.tick = 1000
        self.stores = []
        patches = {
            "discover_storage_buildings": lambda: [{"id": i, "component": c} for i, c in self.stores],
            "_now_tick": lambda: self.tick,
        }
        for name, fn in patches.items():
            original = getattr(field_keeper, name)
            setattr(field_keeper, name, fn)
            self.addCleanup(setattr, field_keeper, name, original)
        keeper = FieldKeeperController.__new__(FieldKeeperController)
        keeper.name = "harvester_1"
        self.console = _ConsoleLog()
        keeper.log = self.console  # type: ignore[assignment]
        keeper.stock_memo = {}
        keeper.stage_busy = False
        keeper.busy_since = {}
        keeper.inventory_count = lambda item_id: 0
        keeper.game_time = lambda ticks: f"{ticks} ticks"
        self.keeper = keeper

    def test_all_busy_flags_stage_busy(self):
        self.stores = [("wh_1", _Store(2, "busy")), ("wh_2", _Store(1, "busy"))]
        self.assertFalse(self.keeper.stage(AMPLIFIER_ITEM_ID))
        self.assertTrue(self.keeper.stage_busy)

    def test_busy_one_falls_through(self):
        self.stores = [("wh_1", _Store(5, "busy")), ("wh_2", _Store(1, "ok"))]
        self.assertTrue(self.keeper.stage(AMPLIFIER_ITEM_ID))
        self.assertFalse(self.keeper.stage_busy)

    def test_recently_busy_tried_last(self):
        busy, free = _Store(5, "busy"), _Store(1, "ok")
        self.stores = [("wh_1", busy), ("wh_2", free)]
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.tick += 1
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.assertEqual(busy.calls, 1)
        self.assertEqual(free.calls, 2)

    def test_empty_is_not_busy(self):
        self.stores = [("wh_1", _Store(0, "busy"))]
        self.assertFalse(self.keeper.stage(AMPLIFIER_ITEM_ID))
        self.assertFalse(self.keeper.stage_busy)

    def test_stuck_warehouse_warns_once(self):
        store = _Store(1, "busy")
        self.stores = [("wh_1", store)]
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.assertEqual(self.console.warnings, [])
        self.tick += STAGE_STUCK_WARN_TICKS
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.tick += 10
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.assertEqual(len(self.console.warnings), 1)
        self.assertEqual(self.console.warnings[0][0], "warn")
        store.answer = "ok"
        self.keeper.stage(AMPLIFIER_ITEM_ID)
        self.assertNotIn("wh_1", self.keeper.busy_since)


if __name__ == "__main__":
    unittest.main()
