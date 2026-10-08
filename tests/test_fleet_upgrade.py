"""Stub tests for the Drone Depot half of the fleet upgrade coordinator
(lib/fleet_upgrade.py): in-place computer.upgrade() with a larger Depot kit."""
import unittest

from harness import StubTestCase
import drone_upgrade
import fleet_upgrade
import production


class DepotUpgradeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_2")
        self.depot = w.add_drone_depot("drone_station_1", self.outpost)
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"phase_reached": True}))
        self.coordinator = fleet_upgrade.FleetUpgradeCoordinator()

    def steps(self, n):
        for _ in range(n):
            self.coordinator.step(self.world.clock.now)
            self.world.clock.now += 1

    def depot_entries(self):
        return drone_upgrade.fleet_upgrade_state().get("depots") or {}

    def orders(self) -> dict:
        return self.world.notebook.get(production.UPGRADE_ORDERS_KEY) or {}

    def test_upgrades_in_place_and_keeps_docked_drone(self):
        w = self.world
        w.add_drone("drone_1", self.outpost, station=self.depot.id)
        w.inventory.add("drone_station_kit_large", 1)
        self.steps(3)
        self.assertEqual(self.depot.type_id, "drone_station_large", self.debug_log())
        self.assertEqual(self.depot.bay_count(), 4)
        self.assertEqual(self.depot.get_docked(), ["drone_1"])
        self.assertIn("drone_station_1", w.components)
        self.assertEqual(w.inventory.count("drone_station_kit_large"), 0)
        self.assertEqual(w.inventory.count("drone_station_kit"), 1)
        self.assertEqual(self.depot_entries(), {})
        self.assertNotIn(("undeploy", "drone_station_1"), w.computer.calls)

    def test_orders_kit_then_waits_out_power(self):
        w = self.world
        w.inventory.add("drone_station_kit_large", 1)
        w.computer.forced_status = "not_enough_power"
        self.steps(2)
        self.assertEqual(self.depot_entries()["drone_station_1"]["state"], "ordered", self.debug_log())
        self.assertEqual(self.depot.type_id, "drone_station")
        w.computer.forced_status = None
        self.steps(1)
        self.assertEqual(self.depot.type_id, "drone_station_large", self.debug_log())
        self.assertEqual(self.orders().get(fleet_upgrade.REQUESTER) or {}, {})

    def test_hand_upgraded_depot_is_dropped(self):
        w = self.world
        w.inventory.add("drone_station_kit_large", 1)
        self.steps(1)
        self.assertEqual(self.depot_entries()["drone_station_1"]["state"], "ordered", self.debug_log())
        self.depot.type_id = "drone_station_large"
        self.steps(1)
        self.assertEqual(self.depot_entries(), {}, self.debug_log())
        self.assertNotIn("upgrade", [c[0] for c in w.computer.calls])

    def test_legacy_swap_state_is_dropped(self):
        drone_upgrade.update_fleet_upgrade(lambda s: s.update({
            "depots": {"drone_station_1": {"state": "draining", "target_kit": "drone_station_kit_large", "new_id": "drone_station_lrg_1"}},
            "retiring_depots": ["drone_station_1"],
        }))
        self.steps(1)
        state = drone_upgrade.fleet_upgrade_state()
        self.assertNotIn("drone_station_1", state.get("depots") or {}, self.debug_log())
        self.assertNotIn("retiring_depots", state)


if __name__ == "__main__":
    unittest.main()
