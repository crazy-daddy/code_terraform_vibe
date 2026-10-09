"""Every public stock counter against one world, so a new counter or a changed
scope shows up as a changed number here. One row per (counter, outpost).

World: home has Inventory 5, Warehouse 10, Storage Bin 40, Drone Depot 3 of
iron_ore; remote has Warehouse 30 + 3, Bin 7, Depot 2; a hauler carries 4
aboard (reserve_pickup aboard=True)."""
import unittest

from harness import StubTestCase, production, storage, logistics_requests
import stock_scan


class StockScopeTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.remote = w.add_outpost("outpost_2")
        w.inventory.add("iron_ore", 5)
        w.add_warehouse("wh_home", w.home, {"iron_ore": 10})
        w.add_storage_bin("bin_home", w.home, "iron_ore", 40)
        w.add_drone_depot("depot_home", w.home).output_buffer["iron_ore"] = 3
        w.add_warehouse("wh_remote", self.remote, {"iron_ore": 30})
        w.add_warehouse("wh_remote_2", self.remote, {"iron_ore": 3, "silicon": 2})
        w.add_storage_bin("bin_remote", self.remote, "iron_ore", 7)
        w.add_drone_depot("depot_remote", self.remote).output_buffer["iron_ore"] = 2
        logistics_requests.reserve_pickup("pioneer_1", "home", "iron_ore", 4, w.clock.now, source_id="outpost_2", aboard=True)

    HOME_LOCAL, HOME_DEPOT = 55, 3
    REMOTE_LOCAL, REMOTE_DEPOT = 40, 2

    def test_scan_scopes(self):
        home, remote = stock_scan.scan(self.world.home), stock_scan.scan(self.remote)
        self.assertEqual(home.units("iron_ore", stock_scan.LOCAL), self.HOME_LOCAL)
        self.assertEqual(home.units("iron_ore", stock_scan.HELD), self.HOME_LOCAL + self.HOME_DEPOT)
        self.assertEqual(home.units("iron_ore", stock_scan.STORES), 50)
        self.assertEqual(remote.units("iron_ore", stock_scan.LOCAL), self.REMOTE_LOCAL)
        self.assertEqual(remote.units("iron_ore", stock_scan.HELD), self.REMOTE_LOCAL + self.REMOTE_DEPOT)
        self.assertEqual(remote.units("iron_ore", stock_scan.DEPOTS), self.REMOTE_DEPOT)
        self.assertEqual(remote.totals(stock_scan.HELD, ["iron_ore", "silicon", "glass"]), {"iron_ore": 42, "silicon": 2, "glass": 0})
        self.assertEqual(sorted(home.holders("iron_ore", (stock_scan.INVENTORY,) + stock_scan.STORES)), [("bin_home", 40), ("inventory", 5), ("wh_home", 10)])
        self.assertEqual(stock_scan.scan(None).units("iron_ore", stock_scan.HELD), self.HOME_LOCAL + self.HOME_DEPOT)
        self.assertEqual(stock_scan.held_units("iron_ore", self.remote), 42)

    def test_source_cache_scopes(self):
        cache = production.SourceCache()
        home = self.world.home
        self.assertEqual(cache.stock("iron_ore"), self.HOME_LOCAL)
        self.assertEqual(cache.local_stock("iron_ore", home), self.HOME_LOCAL)
        self.assertEqual(cache.local_stock("iron_ore", self.remote), self.REMOTE_LOCAL)
        self.assertEqual(cache.depot_stock("iron_ore", self.remote), self.REMOTE_DEPOT)
        self.assertEqual(cache.held_stock("iron_ore"), self.HOME_LOCAL + self.HOME_DEPOT)
        self.assertEqual(cache.held_stock("iron_ore", self.remote), self.REMOTE_LOCAL + self.REMOTE_DEPOT)
        self.assertEqual(cache.network_stock("iron_ore"), 58 + 42 + 4)
        self.assertEqual(sorted(cache.building_stock("iron_ore")), [("bin_home", 40), ("inventory", 5), ("wh_home", 10)])

    def test_request_side_scopes(self):
        home = self.world.home
        self.assertEqual(logistics_requests.outpost_stock(["iron_ore"], home), {"iron_ore": 58})
        self.assertEqual(logistics_requests.outpost_stock(["iron_ore"], self.remote), {"iron_ore": 42})
        self.assertEqual(logistics_requests.outpost_stock(["iron_ore"], None), {"iron_ore": 0})
        for loader in (logistics_requests.LOADER_DRONE, logistics_requests.LOADER_VEHICLE):
            self.assertEqual(logistics_requests.outpost_free_tiers(self.remote, ["iron_ore"], loader=loader), ({"iron_ore": 38}, {"iron_ore": 38}))  # 42 held - 4 reserved by pioneer_1
        reads = logistics_requests.PlanReads(self.world.clock.now)
        self.assertEqual(reads.stock(home, ["iron_ore"]), {"iron_ore": 58})

    def test_storage_counters_leave_depots_out(self):
        self.assertEqual(storage.total_stock("iron_ore"), self.HOME_LOCAL)
        self.assertEqual(storage.total_stock("iron_ore", self.world.home), self.HOME_LOCAL)
        self.assertEqual(storage.total_stock("iron_ore", self.remote), self.REMOTE_LOCAL)
        self.assertEqual(storage.warehouse_stock("iron_ore"), 50)
        self.assertEqual(storage.warehouse_stock("iron_ore", self.remote), self.REMOTE_LOCAL)
        self.assertEqual(storage.inventory_count("iron_ore"), 5)
        self.assertEqual(storage.takeable_stock("iron_ore"), self.HOME_LOCAL)
        self.assertEqual(storage.takeable_stock("iron_ore", self.remote), self.REMOTE_LOCAL)


if __name__ == "__main__":
    unittest.main()
