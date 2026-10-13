"""Stub tests for the heli engine choice of new chassis (drone_upgrade.commission_engine())
and the heli commission spec (drone_commission.build_drone_spec())."""

import unittest

import drone_commission
import drone_depots
import drone_upgrade
from harness import StubTestCase

HELI_PARTS = {"drone_large", "heli_thruster", "oil_tank_small", "cargo_pod_medium"}


def no_stock(_item_id):
    return 0


class HeliSpecTests(unittest.TestCase):
    def test_heli_spec_uses_heli_thruster_and_oil_tanks(self):
        spec, reason = drone_commission.build_drone_spec("hauler", HELI_PARTS, no_stock, engine="heli")
        self.assertIsNone(reason)
        assert spec is not None
        self.assertEqual(spec["engine"], "heli")
        self.assertEqual(
            spec["modules"],
            [
                "heli_thruster",
                "oil_tank_small",
                "oil_tank_small",
                "cargo_pod_medium",
                "cargo_pod_medium",
                "cargo_pod_medium",
            ],
        )

    def test_heli_spec_blocks_without_oil_tank(self):
        spec, reason = drone_commission.build_drone_spec(
            "hauler", HELI_PARTS - {"oil_tank_small"}, no_stock, engine="heli"
        )
        self.assertIsNone(spec)
        self.assertIn("energy", reason)


class CommissionEngineTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.oil_ready = True
        self._orig = drone_depots.heli_oil_ready
        drone_depots.heli_oil_ready = lambda: self.oil_ready

    def tearDown(self):
        drone_depots.heli_oil_ready = self._orig
        super().tearDown()

    def test_electric_until_switch_research_parts_and_oil(self):
        self.assertEqual(drone_upgrade.commission_engine(HELI_PARTS, no_stock), "electric")
        drone_upgrade.set_heli_on_unlock(True)
        self.assertEqual(drone_upgrade.commission_engine(HELI_PARTS, no_stock), "electric")  # not researched
        self.world.research.unlocked.add(drone_depots.HELI_RESEARCH_ID)
        self.assertEqual(drone_upgrade.commission_engine(HELI_PARTS, no_stock), "heli")
        self.assertEqual(drone_upgrade.commission_engine(HELI_PARTS - {"heli_thruster"}, no_stock), "electric")
        self.oil_ready = False
        self.assertEqual(drone_upgrade.commission_engine(HELI_PARTS, no_stock), "electric")

    def test_heli_request_round_trip(self):
        drone_upgrade.request_heli("drone_1")
        self.assertTrue(drone_upgrade.heli_requested("drone_1"))
        drone_upgrade.clear_heli_request("drone_1")
        self.assertFalse(drone_upgrade.heli_requested("drone_1"))


if __name__ == "__main__":
    unittest.main()
