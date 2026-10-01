"""Stub tests for lib/pump_salt.py's home salt request."""
import unittest

from harness import StubTestCase, logistics_requests
import pump_salt


class _Sensor:
    def __init__(self, km2):
        self.km2 = km2

    def get_value(self):
        return self.km2


class SaltToFinishTests(unittest.TestCase):
    def test_full_need_below_salt_bands(self):
        # 600k + 1.25m + 4.5m Forage = 6.35m: 12,700 salt + one item per Mk II batch.
        self.assertEqual(pump_salt.salt_to_finish(0), 13663)
        self.assertEqual(pump_salt.salt_to_finish(None), 13663)
        self.assertEqual(pump_salt.salt_to_finish(1250000), 13663)

    def test_shrinks_inside_bands(self):
        # 3.5m-5m only: 4.5m Forage.
        self.assertEqual(pump_salt.salt_to_finish(3500000), 9682)
        self.assertLess(pump_salt.salt_to_finish(4990000), 100)

    def test_zero_when_complete(self):
        self.assertEqual(pump_salt.salt_to_finish(5000000), 0)


class HomeSaltRequestTests(StubTestCase):
    def setUp(self):
        super().setUp()
        pump_salt._published.update({"target": -1, "tick": -1})

    def request(self):
        return logistics_requests.active_requests(0)[self.world.home.id]["salt"]

    def test_field_plus_terraformers_capped_by_room(self):
        w = self.world
        w.components["plants_sensor"] = _Sensor(4990000)
        w.add_warehouse("large_warehouse_1", w.home, items={"salt": 500}, capacity=100000)
        target = pump_salt.publish_home_salt_request(w.home, 0)
        self.assertEqual(target, pump_salt.SALT_FIELD_UNITS + pump_salt.salt_to_finish(4990000))
        entry = self.request()
        self.assertEqual(entry["by"], pump_salt.SALT_REQUESTER_ID)
        self.assertEqual(entry["min"], pump_salt.SALT_FIELD_UNITS)


    def test_target_keeps_warehouse_room_free(self):
        w = self.world
        w.components["plants_sensor"] = _Sensor(0)
        # 7,000 capacity, 500 salt: 6,500 free, 4,000 kept free -> 2,500 more fit.
        w.add_warehouse("large_warehouse_1", w.home, items={"salt": 500}, capacity=7000)
        self.assertEqual(pump_salt.publish_home_salt_request(w.home, 0), 3000)

    def test_room_cap_never_drops_below_field_need(self):
        w = self.world
        w.add_warehouse("large_warehouse_1", w.home, capacity=1000)
        self.assertEqual(pump_salt.publish_home_salt_request(w.home, 0), pump_salt.SALT_FIELD_UNITS)

    def test_complete_plants_is_all_need(self):
        w = self.world
        w.components["plants_sensor"] = _Sensor(5000000)
        w.add_warehouse("large_warehouse_1", w.home, capacity=100000)
        self.assertEqual(pump_salt.publish_home_salt_request(w.home, 0), pump_salt.SALT_FIELD_UNITS)
        self.assertNotIn("min", self.request())


if __name__ == "__main__":
    unittest.main()
