"""Stub tests for retiring Pioneers, Rovers and drones (lib/fleet_decommission.py):
request -> machine marks ready -> coordinator undeploys, sells vehicle parts
only, and drops the machine's archive entries."""

import unittest
from unittest import mock

import fleet_decommission
import fleet_status
from drone_claims import is_drone_recalled
from game_stubs import MountSlot, Shop
from harness import StubTestCase
from tree_console import TreeConsole
from vehicle_claims import RECALL_KEY, is_vehicle_recalled
from vehicle_recall import VehicleRecallMixin


def pioneer_slots():
    return [
        MountSlot(0, "universal", "nav_module"),
        MountSlot(1, "universal", "battery_holder_small", ["portable_battery", "portable_battery"]),
        MountSlot(2, "universal"),
    ]


PIONEER_RETURNS = {"pioneer": 1, "nav_module": 1, "battery_holder_small": 1, "portable_battery": 2}


class DecommissionTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.add_pioneer("pioneer_1", slots=pioneer_slots())
        w.add_drone_depot("depot_1", w.home).ref_position = [0.0, 0.0]
        w.add_drone("drone_1", w.home, station="depot_1", slots=[MountSlot(0, "battery", "battery_pack")])
        w.run_control.running.update({"pioneer_1", "drone_1"})
        self.computer = w.computer
        self.shop = Shop(w, {item_id: 10 for item_id in PIONEER_RETURNS})
        w.services["shop"] = self.shop
        self.coordinator = fleet_decommission.FleetDecommissionCoordinator()

    def step(self):
        return self.coordinator.step(self.world.clock.now)


class DecommissionTests(DecommissionTestCase):
    def test_request_recalls_and_cancel_releases(self):
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        self.assertTrue(is_vehicle_recalled("pioneer_1"))
        fleet_decommission.cancel_decommission("pioneer_1")
        self.assertFalse(is_vehicle_recalled("pioneer_1"))
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"))

    def test_waits_until_machine_marks_ready(self):
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        self.step()
        self.assertEqual(self.computer.calls, [])

    def test_pioneer_undeployed_and_only_its_parts_sold(self):
        self.world.inventory.add("portable_battery", 5)  # spare stock, not the Pioneer's
        fleet_status.publish("pioneer_1", {"name": "pioneer_1", "state": "RECALLED", "tick": 1})
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        fleet_decommission.mark_decommission_ready("pioneer_1")
        self.step()
        self.assertEqual(self.computer.calls, [("undeploy", "pioneer_1")], self.debug_log())
        self.assertEqual(self.shop.sold, PIONEER_RETURNS)
        self.assertEqual(self.world.inventory.count("portable_battery"), 5)
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"))
        self.assertIsNone(fleet_status.get("pioneer_1"))
        self.assertNotIn("pioneer_1", self.world.notebook.get(RECALL_KEY) or {})

    def test_rover_undeployed_and_chassis_sold(self):
        self.world.add_rover("rover_1", slots=[MountSlot(0, "universal", "nav_module"), MountSlot(1, "universal")])
        self.shop.prices["rover"] = 10
        fleet_decommission.request_decommission("rover_1", "rover")
        self.assertTrue(is_vehicle_recalled("rover_1"))
        fleet_decommission.mark_decommission_ready("rover_1")
        self.step()
        self.assertEqual(self.computer.calls, [("undeploy", "rover_1")], self.debug_log())
        self.assertEqual(self.shop.sold, {"rover": 1, "nav_module": 1})
        self.assertIsNone(fleet_decommission.decommission_entry("rover_1"))
        self.assertFalse(is_vehicle_recalled("rover_1"))

    def test_drone_parts_stay_in_inventory(self):
        fleet_decommission.request_decommission("drone_1", "drone")
        self.assertTrue(is_drone_recalled("drone_1"))
        fleet_decommission.mark_decommission_ready("drone_1")
        self.step()
        self.assertEqual(self.computer.calls, [("undeploy", "drone_1")], self.debug_log())
        self.assertEqual(self.shop.sold, {})
        self.assertEqual(self.world.inventory.count("drone_small"), 1)
        self.assertFalse(is_drone_recalled("drone_1"))

    def test_cargo_aboard_sends_back_to_requested(self):
        self.world.components["pioneer_1"].cargo.items["iron_ore"] = 3
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        fleet_decommission.mark_decommission_ready("pioneer_1")
        self.step()
        self.assertEqual(self.computer.calls, [])
        self.assertEqual((fleet_decommission.decommission_entry("pioneer_1") or {}).get("state"), "requested")

    def test_undocked_drone_sends_back_to_requested(self):
        self.world.components["drone_1"].station = ""
        fleet_decommission.request_decommission("drone_1", "drone")
        fleet_decommission.mark_decommission_ready("drone_1")
        self.step()
        self.assertEqual(self.computer.calls, [])
        self.assertEqual((fleet_decommission.decommission_entry("drone_1") or {}).get("state"), "requested")

    def test_repeated_refusal_blocks_and_releases_recall(self):
        self.computer.forced_status = "cargo_present"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS):
            fleet_decommission.mark_decommission_ready("pioneer_1")
            self.step()
        entry = fleet_decommission.decommission_entry("pioneer_1")
        assert entry is not None
        self.assertEqual(entry["state"], "blocked")
        self.assertFalse(is_vehicle_recalled("pioneer_1"))

    def test_not_found_counts_as_done_and_forgets_the_machine(self):
        self.computer.forced_status = "not_found"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        fleet_decommission.mark_decommission_ready("pioneer_1")
        self.step()
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"), self.debug_log())
        self.assertFalse(is_vehicle_recalled("pioneer_1"))

    def test_undeploy_that_raises_waits_without_counting_an_attempt(self):
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        with mock.patch.object(self.computer, "undeploy", side_effect=RuntimeError("boom")) as undeploy_stub:
            for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS + 2):
                fleet_decommission.mark_decommission_ready("pioneer_1")
                self.step()
        undeploy_stub.assert_called()
        entry = fleet_decommission.decommission_entry("pioneer_1")
        assert entry is not None
        self.assertEqual(entry["state"], "ready", self.debug_log())
        self.assertEqual(entry.get("attempts", 0), 0)
        self.assertNotIn("pioneer_1", self.world.run_control.running)

    def test_depot_ids_cover_every_size_and_outpost(self):
        w = self.world
        far = w.add_outpost("outpost_2")
        w.add_drone_depot("depot_2", far, "drone_station_large").ref_position = [5.0, 5.0]
        w.add_drone_depot("depot_3", far, "drone_station_medium").ref_position = [6.0, 6.0]
        self.assertEqual(self.coordinator._depot_ids(), {"depot_1", "depot_2", "depot_3"})

    def test_depot_ids_empty_when_discovery_raises(self):
        with mock.patch.object(fleet_decommission, "discover_drone_depots", side_effect=RuntimeError("boom")):
            self.assertEqual(self.coordinator._depot_ids(), set())

    def test_fatal_refusal_blocks_after_max_attempts(self):
        self.computer.forced_status = "not_undeployable"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS):
            fleet_decommission.mark_decommission_ready("pioneer_1")
            self.step()
        entry = fleet_decommission.decommission_entry("pioneer_1")
        assert entry is not None
        self.assertEqual(entry["state"], "blocked")
        self.assertEqual(entry["attempts"], fleet_decommission.MAX_UNDEPLOY_ATTEMPTS)

    def test_vanished_machine_entry_dropped(self):
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        del self.world.components["pioneer_1"]
        self.step()
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"))
        self.assertFalse(is_vehicle_recalled("pioneer_1"))


class StripHost(VehicleRecallMixin):
    def __init__(self, vehicle):
        self.vehicle = vehicle
        self.name = "pioneer_1"
        self.log = TreeConsole(module="test")


class LowBatteryRoverHost(StripHost):
    def __init__(self, vehicle):
        super().__init__(vehicle)
        self.name = "rover_1"

    def get_battery(self):
        return 10.0, 100.0, 0.1

    def recharge_at_station(self, target_level=1.0):
        raise AssertionError("Rover charged before retirement")

    def publish_telemetry(self, state):
        pass


class StripTests(DecommissionTestCase):
    def test_strip_sells_every_part_but_nav(self):
        vehicle = self.world.components["pioneer_1"]
        sold, credits, failure = StripHost(vehicle)._strip_and_sell_parts()
        self.assertIsNone(failure, self.debug_log())
        self.assertEqual(sold, 3)
        self.assertEqual(credits, 30)
        self.assertEqual(self.shop.sold, {"battery_holder_small": 1, "portable_battery": 2})
        self.assertEqual([s.module_id for s in vehicle.slots], ["nav_module", None, None])

    def test_rover_skips_charge_before_ready(self):
        host = LowBatteryRoverHost(self.world.add_rover("rover_1"))
        fleet_decommission.request_decommission("rover_1", "rover")
        host._prepare_decommission()
        self.assertEqual(
            (fleet_decommission.decommission_entry("rover_1") or {}).get("state"), "ready", self.debug_log()
        )

    def test_inventory_full_not_counted_as_refusal(self):
        self.computer.forced_status = "inventory_full"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS + 1):
            fleet_decommission.mark_decommission_ready("pioneer_1")
            self.step()
        entry = fleet_decommission.decommission_entry("pioneer_1") or {}
        self.assertEqual(entry.get("state"), "requested")
        self.assertEqual(entry.get("attempts"), 0)
        self.assertTrue(is_vehicle_recalled("pioneer_1"))


class ForgetMachineTests(StubTestCase):
    def test_swap_keeps_upgrade_state_and_drops_the_rest(self):
        import drone_upgrade
        from archive import archive
        from drone_claims import DRONE_RECALL_KEY

        drone_upgrade.update_fleet_upgrade(lambda s: s.update({"drones": {"drone_1": {"state": "attach"}}}))
        archive.transaction(DRONE_RECALL_KEY, {}, lambda flags: {"drone_1": True})
        fleet_decommission.forget_machine("drone_1", "drone", upgrade_state=False)
        self.assertIn("drone_1", drone_upgrade.fleet_upgrade_state().get("drones", {}))
        self.assertIsNone(archive.get_entry(DRONE_RECALL_KEY, "drone_1"))
        fleet_decommission.forget_machine("drone_1", "drone")
        self.assertNotIn("drone_1", drone_upgrade.fleet_upgrade_state().get("drones", {}))


if __name__ == "__main__":
    unittest.main()
