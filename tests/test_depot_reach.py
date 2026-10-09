"""Ground haulers and Drone Depots: outpost_free_tiers() offers a LOADER_VEHICLE
the Depot stockpile above depot_holds() (hauler drone stage requests, Smelter
wants), and take_from_depots(spare_holds=True) loads only that part."""
import unittest

from harness import StubTestCase, logistics_requests
from production_core import SMELTER_WANTS_KEY
import depot_stage

DRONE, VEHICLE = logistics_requests.LOADER_DRONE, logistics_requests.LOADER_VEHICLE


class _Port:
    """Records take()s; the Depot hands over whatever is asked for."""

    def __init__(self):
        self.connected = None
        self.taken = []

    def connected_id(self):
        return self.connected

    def connect(self, target_id):
        self.connected = target_id

    def take(self, item_id, count):
        self.taken.append((self.connected, item_id, count))
        return type("Res", (), {"status": "ok", "moved": count})()


class DepotReachTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        self.depot = w.add_drone_depot("depot_remote", self.remote)
        self.depot.output_buffer.update({"iron_ore": 20, "biomass_x": 6})
        self.now = w.clock.now

    def free(self, loader, item_id="iron_ore", **kw):
        need, buffer = logistics_requests.outpost_free_tiers(self.remote, [item_id], None, self.now, loader=loader, **kw)
        return need.get(item_id, 0), buffer.get(item_id, 0)

    def want(self, fill_to):
        self.world.notebook.set(SMELTER_WANTS_KEY, {"smelter_9": {"site": "outpost_2", "ore": "iron_ore", "fill_to": fill_to, "tick": self.now}})

    def test_vehicle_reaches_depot_stock(self):
        self.assertEqual(self.free(VEHICLE), (50, 50))
        self.assertEqual(self.free(DRONE), (50, 50))

    def test_smelter_want_held_back_from_vehicle_only(self):
        self.want(12)
        self.assertEqual(self.free(VEHICLE), (38, 38))
        self.assertEqual(self.free(DRONE), (50, 50))
        self.want(80)  # an upper bound never takes more than the Depot holds
        self.assertEqual(self.free(VEHICLE), (30, 30))

    def test_staged_pickup_counted_once(self):
        # A drone claimed 15 and its Depot staged them: the claim and the hold are the same units.
        logistics_requests.reserve_pickup("drone_1", "home", "iron_ore", 15, self.now, source_id="outpost_2")
        depot_stage.request_stage("depot_remote", "drone_1", "iron_ore", 15, self.now)
        self.assertEqual(self.free(VEHICLE), (35, 35))
        self.assertEqual(self.free(DRONE), (35, 35))
        # Another ground hauler's claim comes out of the stores as well.
        logistics_requests.reserve_pickup("pioneer_2", "home", "iron_ore", 10, self.now, source_id="outpost_2")
        self.assertEqual(self.free(VEHICLE), (25, 25))

    def test_own_request_keeps_back_before_reach_cap(self):
        logistics_requests.set_requests("outpost_2", "fab", {"iron_ore": (40, 0, 20)}, self.now)
        self.want(20)
        self.assertEqual(self.free(VEHICLE), (30, 10))

    def test_take_from_depots_spares_holds(self):
        self.want(12)
        depot_stage.request_stage("depot_remote", "drone_1", "biomass_x", 4, self.now)
        port, report = _Port(), {}
        self.assertEqual(logistics_requests.take_from_depots(port, "iron_ore", 50, self.remote, spare_holds=True, report=report), 8)
        self.assertEqual(report["sources"], [("depot_remote", "ok", 8)])
        self.assertEqual(logistics_requests.take_from_depots(port, "biomass_x", 50, self.remote, spare_holds=True), 2)
        self.assertEqual(logistics_requests.take_from_depots(port, "iron_ore", 50, self.remote), 20)
        self.assertEqual(port.taken, [("depot_remote", "iron_ore", 8), ("depot_remote", "biomass_x", 2), ("depot_remote", "iron_ore", 20)])


if __name__ == "__main__":
    unittest.main()
