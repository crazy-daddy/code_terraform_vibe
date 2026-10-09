"""drain_port_to_storage() skips a Warehouse that answers "busy" and tries the next-best one."""
import unittest

from harness import StubTestCase, storage


class DrainBusyTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.maker = w.add_smelter("maker_1", w.home)
        self.port = self.maker.output
        self.wh_a = w.add_warehouse("wh_a", w.home, {"seed_x": 5})
        self.wh_b = w.add_warehouse("wh_b", w.home)
        self.port.buffer["seed_x"] = 1

    def test_busy_holder_falls_through_to_next_holder(self):
        wh_c = self.world.add_warehouse("wh_c", self.world.home, {"seed_x": 2})
        self.wh_a.busy = True
        moved = storage.drain_port_to_storage(self.port, outpost=self.world.home)
        self.assertEqual(moved, 1)
        self.assertEqual(wh_c.count("seed_x"), 3)
        self.assertEqual(self.wh_b.count("seed_x"), 0)
        self.assertEqual(self.port.connect_log, ["wh_a", "wh_c"])

    def test_busy_only_holder_waits_instead_of_opening_new_stack(self):
        self.wh_a.busy = True
        moved = storage.drain_port_to_storage(self.port, outpost=self.world.home)
        self.assertEqual(moved, 0)
        self.assertEqual(self.port.buffer["seed_x"], 1)
        self.assertEqual(self.wh_b.count("seed_x"), 0)
        self.assertEqual(self.world.inventory.count("seed_x"), 0)
        self.assertEqual(self.port.connect_log, ["wh_a"])

    def test_not_busy_sends_to_holder(self):
        moved = storage.drain_port_to_storage(self.port, outpost=self.world.home)
        self.assertEqual(moved, 1)
        self.assertEqual(self.wh_a.count("seed_x"), 6)

    def test_all_busy_leaves_stack_staged_not_inventory(self):
        self.wh_a.busy = True
        self.wh_b.busy = True
        moved = storage.drain_port_to_storage(self.port, outpost=self.world.home)
        self.assertEqual(moved, 0)
        self.assertEqual(self.port.buffer["seed_x"], 1)
        self.assertEqual(self.world.inventory.count("seed_x"), 0)

    def test_holders_only_skips_new_stacks(self):
        self.assertEqual(storage.best_unload_target("seed_x", 1, holders_only=True), "wh_a")
        self.assertIsNone(storage.best_unload_target("seed_x", 1, exclude=["wh_a"], holders_only=True))

    def test_exclude_skips_listed_warehouses(self):
        self.assertEqual(storage.best_unload_target("seed_x", 1, exclude=["wh_a"]), "wh_b")
        self.assertIsNone(storage.best_unload_target("seed_x", 1, exclude=["wh_a", "wh_b"]))


if __name__ == "__main__":
    unittest.main()
