import unittest

from harness import StubTestCase
from archive import archive
import machine_activity
from machine_activity import ACTIVITY_KEY, HALF_LIFE_TICKS, fleet_class, record, spare_quantile
from script_census import snapshot
from fleet_status import FLEET_STATUS_KEY
from script_parking import PARKED_KEY, PARK_REQUESTS_KEY


class MachineActivityTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        machine_activity.last_summary_tick = None
        w.add_building("smelter_1", w.home, "smelter")
        w.add_building("smelter_2", w.home, "smelter")
        w.add_building("smelter_3", w.home, "smelter")
        w.add_building("turbine_1", w.home, "steam_turbine")
        w.add_building("bin_1", w.home, "storage_bin")
        for drone_id in ("drone_1", "drone_2", "drone_3"):
            w.add_drone(drone_id, w.home)
        w.run_control.running.update({"smelter_1", "smelter_2", "turbine_1", "drone_1", "drone_2", "drone_3"})
        archive.set(PARKED_KEY, {"smelter_3": {"kind": "smelter", "mode": "breaker", "since": 0}})
        archive.set(PARK_REQUESTS_KEY, {"smelter_2": {"kind": "smelter", "tick": 0}})
        self.set_fleet({"drone_1": "OUTBOUND", "drone_2": "IDLE_NO_TARGETS", "drone_3": "WAITING_DEPOT_SPACE"})

    def set_fleet(self, states):
        archive.set(FLEET_STATUS_KEY, {name: {"name": name, "state": state, "role": "miner"} for name, state in states.items()})

    def machine_class(self, state, machine_id):
        counts = state["machines"][machine_id]["c"]
        return max(counts, key=counts.get)

    def test_classifies_each_machine(self):
        state = record(snapshot(), 1000)
        self.assertEqual(self.machine_class(state, "smelter_1"), "active")
        self.assertEqual(self.machine_class(state, "smelter_2"), "idle")
        self.assertEqual(self.machine_class(state, "smelter_3"), "parked")
        self.assertEqual(self.machine_class(state, "drone_1"), "active")
        self.assertEqual(self.machine_class(state, "drone_2"), "idle")
        self.assertEqual(self.machine_class(state, "drone_3"), "waiting")
        # No member of the turbine group ever filed a park request: activity unknown.
        self.assertEqual(self.machine_class(state, "turbine_1"), "running")
        # Never running nor parked: not tracked.
        self.assertNotIn("bin_1", state["machines"])
        self.assertEqual(archive.get(ACTIVITY_KEY)["samples"], 1)

    def test_groups_pool_members_by_role(self):
        state = record(snapshot(), 1000)
        miners = state["groups"]["drone:miner"]
        self.assertEqual(miners["n"], 3)
        self.assertEqual(miners["spare"], [0, 0, 1])
        self.assertEqual(miners["retire"], 2)
        smelters = state["groups"]["smelter"]
        self.assertTrue(smelters["sig"])
        self.assertEqual(smelters["retire"], 2)

    def test_retire_uses_busiest_samples(self):
        for i in range(9):
            record(snapshot(), 1000 + i)
        self.set_fleet({"drone_1": "OUTBOUND", "drone_2": "MINING", "drone_3": "OUTBOUND"})
        state = record(snapshot(), 1010)
        miners = state["groups"]["drone:miner"]
        # 9 of 10 samples had 2 spare miners, 1 had none: 2 at the 90% quantile.
        self.assertEqual(miners["retire"], 2)
        self.assertAlmostEqual(miners["spare_mean"], 1.8, places=2)
        self.set_fleet({"drone_1": "OUTBOUND", "drone_2": "MINING", "drone_3": "OUTBOUND"})
        state = record(snapshot(), 1011)
        self.assertEqual(state["groups"]["drone:miner"]["retire"], 0)

    def test_counts_decay_with_half_life(self):
        record(snapshot(), 1000)
        state = record(snapshot(), 1000 + HALF_LIFE_TICKS)
        self.assertAlmostEqual(state["machines"]["drone_1"]["c"]["active"], 1.5, places=3)
        self.assertAlmostEqual(state["groups"]["drone:miner"]["w"], 1.5, places=3)

    def test_prunes_removed_machines(self):
        record(snapshot(), 1000)
        del self.world.components["drone_3"]
        state = record(snapshot(), 1300)
        self.assertNotIn("drone_3", state["machines"])
        self.assertEqual(state["groups"]["drone:miner"]["n"], 2)

    def test_logs_summary_once_per_interval(self):
        record(snapshot(), 1000)
        record(snapshot(), 1300)
        lines = [line for line in self.debug_log().splitlines() if "drone:miner: 3 machines" in line]
        self.assertEqual(len(lines), 1)
        self.assertIn("retire 2", lines[0])

    def test_fleet_class(self):
        self.assertEqual(fleet_class("IDLE_AT_BASE"), "idle")
        self.assertEqual(fleet_class("READY_AT_OUTPOST"), "idle")
        self.assertEqual(fleet_class("WAITING_DEPOT_BAY"), "waiting")
        self.assertEqual(fleet_class("DELIVERING"), "active")
        self.assertEqual(fleet_class(None), "active")

    def test_spare_quantile(self):
        self.assertEqual(spare_quantile([]), 0)
        self.assertEqual(spare_quantile([1, 0, 9]), 2)
        self.assertEqual(spare_quantile([2, 0, 8]), 0)


if __name__ == "__main__":
    unittest.main()
