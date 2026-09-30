"""Stub tests for retiring Pioneers and drones (lib/fleet_decommission.py):
request -> machine marks ready -> coordinator undeploys, sells Pioneer parts
only, and drops the machine's archive entries."""
import unittest

from harness import StubTestCase
from game_stubs import Result
import fleet_decommission
import fleet_status
from vehicle_claims import is_vehicle_recalled, RECALL_KEY
from drone_claims import is_drone_recalled
from vehicle_claims import VehicleClaimsMixin
from tree_console import TreeConsole


class Ref:
    def __init__(self, ref_id, current_station=""):
        self.id = ref_id
        self.current_station = current_station


class Fleet:
    def __init__(self):
        self.vehicle_ids = []
        self.drone_refs = []

    def vehicles(self):
        return [Ref(v) for v in self.vehicle_ids]

    def drones(self):
        return list(self.drone_refs)


class Cargo:
    def __init__(self, n=0):
        self.n = n

    def count(self):
        return self.n


class Slot:
    def __init__(self, module_id, internal_items=()):
        self.module_id = module_id
        self.internal_items = list(internal_items)


class Machine:
    def __init__(self, slots=(), cargo=0):
        self.slots = list(slots)
        self.cargo = Cargo(cargo)

    def modules(self):
        return self.slots


class Depot:
    def __init__(self, depot_id, outpost):
        self.id = depot_id
        self.type_id = "drone_station"
        self.outpost = outpost


class Computer:
    def __init__(self, world, fleet, returns):
        self.world = world
        self.fleet = fleet
        self.returns = returns  # machine_id -> {item_id: n} put into Inventory on undeploy
        self.status = "ok"
        self.calls = []

    def undeploy(self, machine_id):
        self.calls.append(machine_id)
        if self.status != "ok":
            return Result(self.status)
        for item_id, n in self.returns.get(machine_id, {}).items():
            self.world.inventory.add(item_id, n)
        self.fleet.vehicle_ids = [v for v in self.fleet.vehicle_ids if v != machine_id]
        self.fleet.drone_refs = [d for d in self.fleet.drone_refs if d.id != machine_id]
        return Result("ok")


class RunControl:
    def is_running(self, machine_id):
        return True

    def stop(self, machine_id):
        return Result("ok")

    def start(self, machine_id):
        return Result("ok")


class SaleResult(Result):
    def __init__(self, status, credits=0):
        super().__init__(status)
        self.credits = credits


class Shop:
    def __init__(self, world):
        self.world = world
        self.sold = {}

    def sell(self, item_id, n):
        if self.world.inventory.count(item_id) < n:
            return SaleResult("no_stock")
        self.world.inventory.remove(item_id, n)
        self.sold[item_id] = self.sold.get(item_id, 0) + n
        return SaleResult("ok", 10 * n)


PIONEER_SLOTS = [Slot("nav_module"), Slot("battery_holder_small", ["portable_battery", "portable_battery"]), Slot(None)]
PIONEER_RETURNS = {"pioneer": 1, "nav_module": 1, "battery_holder_small": 1, "portable_battery": 2}


class DecommissionTestCase(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        self.fleet = Fleet()
        self.fleet.vehicle_ids = ["pioneer_1"]
        self.fleet.drone_refs = [Ref("drone_1", "depot_1")]
        w.components["pioneer_1"] = Machine(PIONEER_SLOTS)
        w.components["drone_1"] = Machine()
        w.components["depot_1"] = Depot("depot_1", w.home)
        self.computer = Computer(w, self.fleet, {"pioneer_1": PIONEER_RETURNS, "drone_1": {"drone_small": 1, "battery_pack": 1}})
        self.shop = Shop(w)
        w.services.update({"fleet": self.fleet, "computer": self.computer, "run_control": RunControl(), "shop": self.shop})
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
        self.assertEqual(self.computer.calls, ["pioneer_1"], self.debug_log())
        self.assertEqual(self.shop.sold, PIONEER_RETURNS)
        self.assertEqual(self.world.inventory.count("portable_battery"), 5)
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"))
        self.assertIsNone(fleet_status.get("pioneer_1"))
        self.assertNotIn("pioneer_1", self.world.notebook.get(RECALL_KEY) or {})

    def test_drone_parts_stay_in_inventory(self):
        fleet_decommission.request_decommission("drone_1", "drone")
        self.assertTrue(is_drone_recalled("drone_1"))
        fleet_decommission.mark_decommission_ready("drone_1")
        self.step()
        self.assertEqual(self.computer.calls, ["drone_1"], self.debug_log())
        self.assertEqual(self.shop.sold, {})
        self.assertEqual(self.world.inventory.count("drone_small"), 1)
        self.assertFalse(is_drone_recalled("drone_1"))

    def test_cargo_aboard_sends_back_to_requested(self):
        self.world.components["pioneer_1"].cargo.n = 3
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        fleet_decommission.mark_decommission_ready("pioneer_1")
        self.step()
        self.assertEqual(self.computer.calls, [])
        self.assertEqual((fleet_decommission.decommission_entry("pioneer_1") or {}).get("state"), "requested")

    def test_undocked_drone_sends_back_to_requested(self):
        self.fleet.drone_refs = [Ref("drone_1", "")]
        fleet_decommission.request_decommission("drone_1", "drone")
        fleet_decommission.mark_decommission_ready("drone_1")
        self.step()
        self.assertEqual(self.computer.calls, [])
        self.assertEqual((fleet_decommission.decommission_entry("drone_1") or {}).get("state"), "requested")

    def test_repeated_refusal_blocks_and_releases_recall(self):
        self.computer.status = "cargo_present"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS):
            fleet_decommission.mark_decommission_ready("pioneer_1")
            self.step()
        entry = fleet_decommission.decommission_entry("pioneer_1")
        assert entry is not None
        self.assertEqual(entry["state"], "blocked")
        self.assertFalse(is_vehicle_recalled("pioneer_1"))

    def test_vanished_machine_entry_dropped(self):
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        self.fleet.vehicle_ids = []
        self.step()
        self.assertIsNone(fleet_decommission.decommission_entry("pioneer_1"))
        self.assertFalse(is_vehicle_recalled("pioneer_1"))


class StripSlot:
    def __init__(self, index, module_id, internal_items=()):
        self.index = index
        self.module_id = module_id
        self.internal_items = list(internal_items)


class StripVehicle:
    """Pioneer with self-only unmount()/uninstall() that return parts to Inventory."""

    def __init__(self, world, slots):
        self.world = world
        self.slots = slots

    def modules(self):
        return [StripSlot(s.index, s.module_id, s.internal_items) for s in self.slots]

    def uninstall(self, slot_index, internal_index):
        slot = self.slots[slot_index]
        self.world.inventory.add(slot.internal_items[internal_index], 1)
        slot.internal_items[internal_index] = None
        return Result("ok")

    def unmount(self, slot_index):
        slot = self.slots[slot_index]
        if any(slot.internal_items):
            return Result("holder_not_empty")
        self.world.inventory.add(slot.module_id, 1)
        slot.module_id = None
        return Result("ok")


class StripHost(VehicleClaimsMixin):
    def __init__(self, vehicle):
        self.vehicle = vehicle
        self.name = "pioneer_1"
        self.log = TreeConsole(module="test")


class StripTests(DecommissionTestCase):
    def test_strip_sells_every_part_but_nav(self):
        vehicle = StripVehicle(self.world, [
            StripSlot(0, "nav_module"),
            StripSlot(1, "battery_holder_small", ["portable_battery", "portable_battery"]),
            StripSlot(2, None),
        ])
        sold, credits, failure = StripHost(vehicle)._strip_and_sell_parts()
        self.assertIsNone(failure, self.debug_log())
        self.assertEqual(sold, 3)
        self.assertEqual(credits, 30)
        self.assertEqual(self.shop.sold, {"battery_holder_small": 1, "portable_battery": 2})
        self.assertEqual([s.module_id for s in vehicle.slots], ["nav_module", None, None])

    def test_inventory_full_not_counted_as_refusal(self):
        self.computer.status = "inventory_full"
        fleet_decommission.request_decommission("pioneer_1", "pioneer")
        for _ in range(fleet_decommission.MAX_UNDEPLOY_ATTEMPTS + 1):
            fleet_decommission.mark_decommission_ready("pioneer_1")
            self.step()
        entry = fleet_decommission.decommission_entry("pioneer_1") or {}
        self.assertEqual(entry.get("state"), "requested")
        self.assertEqual(entry.get("attempts"), 0)
        self.assertTrue(is_vehicle_recalled("pioneer_1"))


if __name__ == "__main__":
    unittest.main()
