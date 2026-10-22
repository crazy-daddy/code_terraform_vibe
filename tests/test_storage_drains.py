"""Stub tests for lib/storage_unload.py send_stack(), drain_port_storage_first() and
the home-outpost reading of best_unload_target() and
storage_take._holder_candidates()."""

import unittest
from unittest import mock

import storage
import storage_take
import storage_unload
from game_stubs import OutpostComponent
from harness import StubTestCase


class HomeResolutionTests(StubTestCase):
    def test_unload_fallback_counts_no_outpost_as_home(self):
        with mock.patch.object(storage.components, "home_outpost", lambda: None):
            self.assertEqual(storage_unload.best_unload_target("steel_plate"), "inventory")

    def test_holder_candidates_call_outpost_component_is_home(self):
        w = self.world
        w.inventory.add("steel_plate", 5)
        remote = OutpostComponent(w, w.add_outpost("outpost_2"))
        home = OutpostComponent(w, w.home)
        with mock.patch.object(storage_take, "discover_storage_buildings", lambda outpost=None: []):
            self.assertEqual(storage_take._holder_candidates("steel_plate", outpost=remote), [])
            self.assertEqual(
                [source for source, _units in storage_take._holder_candidates("steel_plate", outpost=home)],
                ["inventory"],
            )


class SendStackTests(StubTestCase):
    def test_connects_and_reports_moved(self):
        w = self.world
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 3
        moved, status, _message = storage_unload.send_stack(f.output, "steel_plate", 3, "inventory")
        self.assertEqual((moved, status), (3, "ok"))
        self.assertEqual(f.output.connected_id(), "inventory")
        self.assertEqual(w.inventory.count("steel_plate"), 3)

    def test_raising_send_reports_exception(self):
        class Broken:
            def connected_id(self):
                return ""

            def connect(self, _target):
                raise RuntimeError("boom")

        self.assertEqual(storage_unload.send_stack(Broken(), "steel_plate", 1, "inventory"), (0, "exception", "boom"))


class DrainStorageFirstTests(StubTestCase):
    def test_warehouse_before_inventory(self):
        w = self.world
        warehouse = w.add_warehouse("warehouse_1", w.home)
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 4
        self.assertEqual(storage_unload.drain_port_storage_first(f.output, outpost=w.home), 4)
        self.assertEqual(warehouse.count("steel_plate"), 4)
        self.assertEqual(w.inventory.count("steel_plate"), 0)

    def test_inventory_when_no_warehouse_has_room(self):
        w = self.world
        w.add_warehouse("warehouse_1", w.home, capacity=0)
        f = w.add_fabricator("fabricator_1", w.home)
        f.output_buffer["steel_plate"] = 4
        self.assertEqual(storage_unload.drain_port_storage_first(f.output, outpost=w.home), 4)
        self.assertEqual(w.inventory.count("steel_plate"), 4)


if __name__ == "__main__":
    unittest.main()
