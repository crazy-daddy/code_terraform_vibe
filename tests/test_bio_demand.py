"""Stub tests for bio_orders.bio_demand_totals(): demand from the outpost's own Bio Exchange orders."""

import unittest
from types import SimpleNamespace

import bio_orders
from harness import StubTestCase


def _order(biome, requires, delivered=None, in_transit=None, status="active", percent=0):
    return SimpleNamespace(
        biome=biome,
        requires=requires,
        delivered=delivered or {},
        in_transit=in_transit or {},
        status=status,
        percent=percent,
    )


class BioDemandTotalsTests(StubTestCase):
    def test_local_incomplete_orders_net_of_delivered_and_in_transit(self):
        orders = [
            _order(
                "geothermal",
                {"ma_ganglion_node": 38, "gw_cardiac_node": 10},
                delivered={"ma_ganglion_node": 8},
                in_transit={"gw_cardiac_node": 10},
            ),
            _order("geothermal", {"ma_ganglion_node": 5}),
        ]
        self.assertEqual(bio_orders.bio_demand_totals(orders, "geothermal"), {"ma_ganglion_node": 35})

    def test_other_biomes_and_complete_orders_are_ignored(self):
        orders = [
            _order("coastal", {"vm_ventral_photophore": 29}),
            _order("geothermal", {"ma_ganglion_node": 38}, status="complete"),
            _order("geothermal", {"st_limb_claw": 28}, percent=100),
        ]
        self.assertEqual(bio_orders.bio_demand_totals(orders, "geothermal"), {})


if __name__ == "__main__":
    unittest.main()
