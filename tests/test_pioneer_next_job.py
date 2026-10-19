"""Stub tests for PioneerController.next_job() (lib/pioneer.py): the idle
timer, the refit cooldown, the keep floor, slot contention and the
fallback to hauler, against a published fleet.role_demand."""

import unittest

import role_demand
from archive import archive
from harness import StubTestCase
from pioneer import PioneerController
from pioneer_refit import REFIT_COOLDOWN_TICKS, REFIT_IDLE_TICKS
from priority import BUILD, NONE, ORDER
from tree_console import TreeConsole

OLD_JOB = object()


class FakePioneer:
    """The attributes next_job() reads; refit() and job_for_role() are recorded, not run."""

    next_job = PioneerController.next_job
    _claim_role_slot = PioneerController._claim_role_slot

    def __init__(self, name, role, world, refit_ok=True):
        self.name = name
        self.role = role
        self.world = world
        self.state = "IDLE_AT_BASE"
        self.mission = None
        self.cargo = {}
        self.recalled = False
        self.refit_ok = refit_ok
        self.refits = []
        self.locked = set()
        self.log = TreeConsole(module="test")
        self.role_slot = None
        self.slot_tick = None
        self.idle_since = None
        self.refit_tick = -REFIT_COOLDOWN_TICKS

    def get_current_tick(self):
        return self.world.clock.now

    def cargo_counts(self):
        return self.cargo

    def is_recalled(self):
        return self.recalled

    def refit_spec(self, role):
        return None if role in self.locked else {"modules": [role]}

    def refit(self, role, spec=None):
        self.refits.append(role)
        self.refit_tick = self.get_current_tick()
        if self.refit_ok:
            self.role = role
        return self.refit_ok

    def job_for_role(self, role):
        return f"{role} job"


class NextJobTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.clock.now = 1000

    def demand(self, **roles):
        base = {
            "hauler": {"band": NONE, "wanted": 0, "keep": 1, "outposts": {}},
            "constructor": {"band": NONE, "wanted": 0, "keep": 0, "outposts": {}},
            "scout": {"band": NONE, "wanted": 0, "keep": 0, "outposts": {}},
            "miner": {"band": NONE, "wanted": 0, "keep": 0, "outposts": {}},
        }
        base.update(roles)
        self.roles = base
        archive.set(role_demand.ROLE_DEMAND_KEY, role_demand.stored({"tick": self.world.clock.now, "roles": base}))

    def pioneer(self, name="pioneer_1", role="constructor", **kw):
        unit = FakePioneer(name, role, self.world, **kw)
        unit.next_job(OLD_JOB)  # first cycle: claims its slot, starts the idle timer
        return unit

    def advance(self, ticks):
        """Moves the clock; the Automation keeps the demand record fresh meanwhile."""
        self.world.clock.now += ticks
        archive.set(
            role_demand.ROLE_DEMAND_KEY, role_demand.stored({"tick": self.world.clock.now, "roles": self.roles})
        )

    def test_idle_timer_gates_refit(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer()
        self.advance(REFIT_IDLE_TICKS - 1)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.advance(1)
        self.assertEqual(unit.next_job(OLD_JOB), "hauler job")
        self.assertEqual(unit.refits, ["hauler"])
        self.assertEqual(unit.role_slot, "hauler:0")
        self.assertNotIn("constructor:0", role_demand.read_claims())

    def test_work_resets_idle_timer(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer()
        self.advance(REFIT_IDLE_TICKS)
        unit.state = "DRIVING"
        unit.next_job(OLD_JOB)
        unit.state = "IDLE_AT_BASE"
        unit.next_job(OLD_JOB)
        self.advance(REFIT_IDLE_TICKS - 1)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)

    def test_cargo_mission_recall_block(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer()
        self.advance(REFIT_IDLE_TICKS)
        unit.cargo = {"iron_ore": 3}
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        unit.cargo = {}
        unit.recalled = True
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertEqual(unit.refits, [])

    def test_failed_refit_cools_down_and_frees_slot(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer(refit_ok=False)
        self.advance(REFIT_IDLE_TICKS)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertNotIn("hauler:0", role_demand.read_claims())
        self.assertEqual(unit.role_slot, "constructor:0")
        self.advance(REFIT_COOLDOWN_TICKS - 1)
        unit.next_job(OLD_JOB)
        self.assertEqual(unit.refits, ["hauler"])
        self.advance(1)
        unit.next_job(OLD_JOB)
        self.assertEqual(unit.refits, ["hauler", "hauler"])

    def test_keep_floor_holds_last_of_role(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1}, constructor={"band": BUILD, "wanted": 1, "keep": 1})
        unit = self.pioneer(role="hauler")
        self.advance(REFIT_IDLE_TICKS)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertEqual(unit.refits, [])

    def test_two_idle_pioneers_one_slot(self):
        self.demand(constructor={"band": BUILD, "wanted": 1, "keep": 1}, hauler={"band": ORDER, "wanted": 1, "keep": 1})
        a = self.pioneer("pioneer_1", role="hauler")
        b = self.pioneer("pioneer_2", role="hauler")
        self.advance(REFIT_IDLE_TICKS)
        self.assertEqual(a.next_job(OLD_JOB), "constructor job")
        self.assertIs(b.next_job(OLD_JOB), OLD_JOB)
        self.assertEqual(b.refits, [])
        self.assertEqual(
            role_demand.claimed_counts(role_demand.read_claims(), self.world.clock.now), {"constructor": 1, "hauler": 1}
        )

    def test_role_without_work_falls_back_to_hauler(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        self.pioneer("pioneer_9", role="hauler")  # the haulers' one wanted slot is taken
        unit = self.pioneer(role="constructor")
        self.advance(REFIT_IDLE_TICKS)
        self.assertEqual(unit.next_job(OLD_JOB), "hauler job")
        self.assertEqual(unit.role_slot, "hauler:1")

    def test_idle_hauler_stays_without_better_band(self):
        self.demand(hauler={"band": NONE, "wanted": 0, "keep": 1})
        self.pioneer("pioneer_9", role="hauler")
        unit = self.pioneer(role="hauler")
        self.advance(REFIT_IDLE_TICKS)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertEqual(unit.refits, [])

    def test_locked_role_skipped_for_next(self):
        self.demand(constructor={"band": BUILD, "wanted": 1, "keep": 1}, hauler={"band": ORDER, "wanted": 2, "keep": 1})
        unit = self.pioneer(role="scout")
        unit.locked = {"constructor"}
        self.advance(REFIT_IDLE_TICKS)
        self.assertEqual(unit.next_job(OLD_JOB), "hauler job")
        self.assertNotIn("constructor:0", role_demand.read_claims())

    def test_stale_demand_ignored(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer()
        self.world.clock.now += REFIT_IDLE_TICKS + role_demand.ROLE_DEMAND_STALE_TICKS
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertEqual(unit.refits, [])

    def test_refit_exception_keeps_job_and_frees_slot(self):
        self.demand(hauler={"band": ORDER, "wanted": 1, "keep": 1})
        unit = self.pioneer()

        def boom(role, spec=None):
            raise RuntimeError("refit broke")

        unit.refit = boom
        self.advance(REFIT_IDLE_TICKS)
        self.assertIs(unit.next_job(OLD_JOB), OLD_JOB)
        self.assertNotIn("hauler:0", role_demand.read_claims())
        self.world.console.lines.clear()  # the swallowed() warning is expected here


if __name__ == "__main__":
    unittest.main()
