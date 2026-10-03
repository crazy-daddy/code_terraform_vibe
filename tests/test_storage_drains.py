"""Stub tests for lib/storage.py send_stack() and drain_port_storage_first()."""
import unittest

from harness import StubTestCase
import storage


class SendStackTests(StubTestCase):
    def test_connects_and_reports_moved(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 3
        moved, status, _message = storage.send_stack(f.output, "steel_plate", 3, "inventory")
        self.assertEqual((moved, status), (3, "ok"))
        self.assertEqual(f.output.connected_id(), "inventory")
        self.assertEqual(w.inventory.count("steel_plate"), 3)

    def test_raising_send_reports_exception(self):
        class Broken:
            def connected_id(self):
                return ""

            def connect(self, _target):
                raise RuntimeError("boom")

        self.assertEqual(storage.send_stack(Broken(), "steel_plate", 1, "inventory"), (0, "exception", "boom"))


class DrainStorageFirstTests(StubTestCase):
    def test_warehouse_before_inventory(self):
        w = self.world
        warehouse = w.add_warehouse("warehouse_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 4
        self.assertEqual(storage.drain_port_storage_first(f.output, outpost=w.home), 4)
        self.assertEqual(warehouse.count("steel_plate"), 4)
        self.assertEqual(w.inventory.count("steel_plate"), 0)

    def test_inventory_when_no_warehouse_has_room(self):
        w = self.world
        w.add_warehouse("warehouse_1", w.home, capacity=0)
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 4
        self.assertEqual(storage.drain_port_storage_first(f.output, outpost=w.home), 4)
        self.assertEqual(w.inventory.count("steel_plate"), 4)


if __name__ == "__main__":
    unittest.main()
