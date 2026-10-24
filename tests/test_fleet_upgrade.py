"""Stub tests for the Drone Depot half of the fleet upgrade coordinator
(lib/fleet_upgrade.py): in-place computer.upgrade() with a larger Depot kit."""

import unittest
from unittest import mock

import drone_depots
import drone_upgrade
import fleet_upgrade
import production
from harness import StubTestCase


class SwappedNameTests(unittest.TestCase):
    def test_own_name_takes_new_number(self):
        self.assertEqual(fleet_upgrade.swapped_name("O3_miner_14", "drone_14", "drone_21"), "O3_miner_21")
        self.assertEqual(fleet_upgrade.swapped_name("H_hauler_9", "drone_9", "drone_22"), "H_hauler_22")

    def test_player_name_kept(self):
        for name in ("Bessie", "O3_miner_7", "my_miner_14", "Ox_miner_14", "O3_miner_14_b"):
            self.assertEqual(fleet_upgrade.swapped_name(name, "drone_14", "drone_21"), name)


class DroneSwapUndeployTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.outpost = w.add_outpost("outpost_2")
        self.depot = w.add_drone_depot("drone_station_1", self.outpost)
        w.add_drone("drone_1", self.outpost, station=self.depot.id)
        self.coordinator = fleet_upgrade.FleetUpgradeCoordinator()
        self.entry = {
            "state": "swapping",
            "target_kind": "drone_small",
            "outpost": self.outpost.id,
            "known": ["drone_1"],
        }
        drone_upgrade.update_fleet_upgrade(lambda s: s.setdefault("drones", {}).update({"drone_1": dict(self.entry)}))

    def swap(self):
        drones = self.coordinator._drones()
        return self.coordinator._swap_drone("drone_1", self.entry, drones, self.world.computer)

    def drone_entry(self):
        return drone_upgrade.fleet_upgrade_state()["drones"]["drone_1"]

    def test_not_found_continues_to_the_deploy_step(self):
        w = self.world
        w.computer.forced_status = "not_found"
        text = self.swap()
        self.assertTrue(any(c[0] == "deploy" for c in w.computer.calls), self.debug_log())
        self.assertIn("deploy not_found", text)
        self.assertEqual(self.drone_entry()["state"], "swapping")
        self.assertNotIn("Undeployed", self.debug_log())

    def test_undeploy_that_raises_waits_without_counting_an_attempt(self):
        w = self.world
        with mock.patch.object(w.computer, "undeploy", side_effect=RuntimeError("boom")):
            texts = [self.swap() for _ in range(fleet_upgrade.MAX_UNDEPLOY_ATTEMPTS + 2)]
        self.assertEqual(set(texts), {"drone_1: undeploy error"})
        self.assertEqual(self.drone_entry().get("attempts", 0), 0)
        self.assertEqual(self.drone_entry()["state"], "swapping")

    def test_fatal_refusal_blocks_after_max_attempts(self):
        self.world.computer.forced_status = "not_undeployable"
        for _ in range(fleet_upgrade.MAX_UNDEPLOY_ATTEMPTS):
            self.entry = dict(self.drone_entry())
            self.swap()
        self.assertEqual(self.drone_entry()["state"], "blocked")


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
        return self.world.notebook.get(production.ORDERS_KEY) or {}

    def test_depot_deployed_in_same_tick_is_seen(self):
        # the network depot walk memoizes; _advance_depot must not read through it
        drone_depots._DISCOVERY.ttl_ticks = drone_depots.DISCOVERY_TTL_TICKS
        drone_depots.discover_drone_depots()
        new_depot = self.world.add_drone_depot("drone_station_2", self.outpost)
        self.assertNotIn(new_depot.id, {d["id"] for d in drone_depots.discover_drone_depots()})
        self.assertIn(new_depot.id, {d["id"] for d in self.coordinator._depots()})

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

    def test_upgrade_call_that_raises_waits_and_never_blocks(self):
        w = self.world
        w.inventory.add("drone_station_kit_large", 1)
        self.steps(1)
        self.assertEqual(self.depot_entries()["drone_station_1"]["state"], "ordered", self.debug_log())

        with mock.patch.object(w.computer, "upgrade", side_effect=RuntimeError("boom")):
            for _ in range(2):
                status = self.coordinator.step(w.clock.now)
                self.assertIn("drone_station_1: upgrade error", status, self.debug_log())
        self.assertEqual(self.depot_entries()["drone_station_1"]["state"], "ordered", self.debug_log())
        self.assertEqual(self.depot.type_id, "drone_station")
        self.assertEqual(w.inventory.count("drone_station_kit_large"), 1)

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
        drone_upgrade.update_fleet_upgrade(
            lambda s: s.update(
                {
                    "depots": {
                        "drone_station_1": {
                            "state": "draining",
                            "target_kit": "drone_station_kit_large",
                            "new_id": "drone_station_lrg_1",
                        }
                    },
                    "retiring_depots": ["drone_station_1"],
                }
            )
        )
        self.steps(1)
        state = drone_upgrade.fleet_upgrade_state()
        self.assertNotIn("drone_station_1", state.get("depots") or {}, self.debug_log())
        self.assertNotIn("retiring_depots", state)


if __name__ == "__main__":
    unittest.main()
