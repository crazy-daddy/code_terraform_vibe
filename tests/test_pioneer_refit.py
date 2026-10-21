"""Stub tests for lib/pioneer_refit.py: the service-area rectangle, which
modules a refit keeps, the sale order of one slot, the name rule and the
refit job the commission coordinator buys for and finishes."""

import unittest
from types import SimpleNamespace
from unittest import mock

import cash
import fleet_commission
import fleet_status
import pioneer_commission
import pioneer_refit
import pioneer_stock
import production_core
from game_stubs import Commander, MountSlot, Result, Shop
from harness import StubTestCase
from pioneer import PioneerController
from tree_console import TreeConsole
from vehicle_recall import sell_slot

PAD = pioneer_refit.SERVICE_PAD_M
SIZE = pioneer_refit.FOOTPRINT_M


class ServiceAreaTests(unittest.TestCase):
    def test_corners(self):
        origin = (-420.0, 120.0)
        ox, oy = origin
        self.assertTrue(pioneer_refit.in_service_area(origin, origin))
        self.assertTrue(pioneer_refit.in_service_area((ox - PAD, oy - SIZE - PAD), origin))
        self.assertTrue(pioneer_refit.in_service_area((ox + SIZE + PAD - 0.01, oy + PAD - 0.01), origin))
        self.assertFalse(pioneer_refit.in_service_area((ox + SIZE + PAD, oy), origin))
        self.assertFalse(pioneer_refit.in_service_area((ox, oy + PAD), origin))
        self.assertFalse(pioneer_refit.in_service_area((ox - PAD - 0.01, oy), origin))
        self.assertFalse(pioneer_refit.in_service_area((ox, oy - SIZE - PAD - 0.01), origin))
        self.assertFalse(pioneer_refit.in_service_area(None, origin))


class PlanTests(unittest.TestCase):
    CONSTRUCTOR = [
        "nav_module",
        "constructor_module",
        "battery_holder_large",
        "battery_holder_large",
        "battery_holder_large",
        "battery_holder_large",
        "cargo_rack_large",
        "cargo_rack_large",
    ]

    def test_hauler_to_constructor_keeps_nav_and_categories(self):
        slots = [
            (0, "nav_module"),
            (1, "battery_holder_small"),
            (2, "battery_holder_large"),
            (3, "cargo_rack_small"),
            (4, "cargo_rack_large"),
            (5, "cargo_rack_medium"),
            (6, "cargo_rack_small"),
            (7, "cargo_rack_small"),
        ]
        keep, sell, modules = pioneer_refit.plan_refit(slots, self.CONSTRUCTOR)
        self.assertEqual(keep, [0, 1, 2, 4, 5])  # best racks first
        self.assertEqual(sell, [3, 6, 7])
        self.assertEqual(
            sorted(modules),
            sorted(
                [
                    "nav_module",
                    "constructor_module",
                    "battery_holder_large",
                    "battery_holder_small",
                    "battery_holder_large",
                    "battery_holder_large",
                    "cargo_rack_large",
                    "cargo_rack_medium",
                ]
            ),
        )
        self.assertEqual(len(modules), 8)

    def test_role_module_and_unknown_module_sold(self):
        slots = [(0, "nav_module"), (1, "drill_module"), (2, "mystery_module")]
        keep, sell, modules = pioneer_refit.plan_refit(slots, self.CONSTRUCTOR)
        self.assertEqual((keep, sell), ([0], [1, 2]))
        self.assertEqual(modules, self.CONSTRUCTOR)

    def test_seismic_sonar_kept_for_scout(self):
        scout = ["nav_module", "sonar_module_deep", "battery_holder_small"]
        keep, sell, modules = pioneer_refit.plan_refit([(0, "nav_module"), (1, "sonar_module_seismic")], scout)
        self.assertEqual((keep, sell), ([0, 1], []))
        self.assertEqual(modules, ["nav_module", "sonar_module_seismic", "battery_holder_small"])

    def test_nav_always_stays(self):
        keep, sell, _ = pioneer_refit.plan_refit([(0, "nav_module")], ["battery_holder_small"])
        self.assertEqual((keep, sell), ([0], []))


class NameTests(unittest.TestCase):
    def test_code_names(self):
        self.assertTrue(pioneer_refit.is_code_name("pioneer_14", "pioneer_14"))
        self.assertTrue(pioneer_refit.is_code_name("O3_miner_14", "pioneer_14"))
        self.assertTrue(pioneer_refit.is_code_name("H_hauler_14", "pioneer_14"))
        self.assertFalse(pioneer_refit.is_code_name("O3_miner_15", "pioneer_14"))
        self.assertFalse(pioneer_refit.is_code_name("Big Bertha", "pioneer_14"))
        self.assertFalse(pioneer_refit.is_code_name("O3_digger_14", "pioneer_14"))
        self.assertTrue(pioneer_refit.is_code_name("H_constructor_14", "pioneer_14"))  # former role name
        self.assertEqual(pioneer_commission.canonical_role("constructor"), "builder")

    def test_former_role_name_migrates(self):
        self.assertEqual(pioneer_refit.renamed_role_name("O2_constructor_14", "pioneer_14"), "O2_builder_14")
        self.assertIsNone(pioneer_refit.renamed_role_name("O2_builder_14", "pioneer_14"))
        self.assertIsNone(pioneer_refit.renamed_role_name("O2_constructor_15", "pioneer_14"))
        self.assertIsNone(pioneer_refit.renamed_role_name("pioneer_14", "pioneer_14"))


class SellSlotTests(StubTestCase):
    def test_bays_before_holder(self):
        w = self.world
        shop = Shop(w, {"battery_holder_small": 10, "portable_battery": 5})
        vehicle = w.add_pioneer(
            "pioneer_1",
            slots=[
                MountSlot(0, "universal", "nav_module"),
                MountSlot(1, "universal", "battery_holder_small", ["portable_battery", "portable_battery"]),
            ],
        )
        calls = []
        original_uninstall, original_unmount = vehicle.uninstall, vehicle.unmount
        setattr(vehicle, "uninstall", lambda s, i: calls.append(("uninstall", s, i)) or original_uninstall(s, i))
        setattr(vehicle, "unmount", lambda s: calls.append(("unmount", s)) or original_unmount(s))
        tally = [0, 0]
        failure = sell_slot(vehicle, vehicle.slots[1], shop, TreeConsole(module="test"), "pioneer_1", tally)
        self.assertIsNone(failure)
        self.assertEqual(calls, [("uninstall", 1, 0), ("uninstall", 1, 1), ("unmount", 1)])
        self.assertEqual(tally, [3, 20])
        self.assertEqual(shop.sold, {"portable_battery": 2, "battery_holder_small": 1})

    def test_refused_unmount_reported(self):
        w = self.world
        shop = Shop(w, {"drill_module": 10})
        vehicle = w.add_pioneer("pioneer_1", slots=[MountSlot(0, "universal", "drill_module")])
        setattr(vehicle, "unmount", lambda s: Result("not_at_service_point"))
        failure = sell_slot(vehicle, vehicle.slots[0], shop, TreeConsole(module="test"), "pioneer_1")
        self.assertIn("not_at_service_point", failure or "")


class SellRefusedTests(StubTestCase):
    def test_refused_sale_stops_the_slot(self):
        w = self.world
        shop = Shop(w, {"battery_holder_small": 10}, not_sellable=("portable_battery",))
        vehicle = w.add_pioneer(
            "pioneer_1", slots=[MountSlot(0, "universal", "battery_holder_small", ["portable_battery"])]
        )
        failure = sell_slot(vehicle, vehicle.slots[0], shop, TreeConsole(module="test"), "pioneer_1")
        self.assertIn("portable_battery", failure or "")
        self.assertEqual(vehicle.slots[0].module_id, "battery_holder_small")


class RefitJobTests(StubTestCase):
    def setUp(self):
        super().setUp()
        w = self.world
        w.add_pioneer("pioneer_1")
        w.services.update(
            {
                "shop": Shop(
                    w,
                    {
                        i: 10
                        for i in ("pioneer", "nav_module", "cargo_rack_small", "battery_holder_small", "portable_bin")
                    },
                ),
                "commander": Commander(cash.LEGACY_RESERVE * 10),
            }
        )
        self.coordinator = fleet_commission.FleetCommissionCoordinator()

    def enqueue(self, missing=None):
        spec = {
            "modules": ["nav_module", "cargo_rack_small"],
            "battery_fill": "portable_battery",
            "bin_fill": "portable_bin",
        }
        job, lineage = pioneer_refit.refit_job("pioneer_1", "hauler", "outpost_home", spec, 5)
        lineage["missing"] = missing or {}
        lineage["passes"] = 2
        pioneer_commission.update_commission(lambda s: pioneer_refit.enqueue_refit(s, job, lineage))
        return job["id"]

    def jobs(self):
        return pioneer_commission.commission_state().get("jobs") or []

    def test_refit_goes_ahead_of_queued_commissions(self):
        queued = fleet_commission.queue_pioneer("miner")
        job_id = self.enqueue()
        self.assertEqual([j["id"] for j in self.jobs()], [job_id, queued])
        self.assertEqual((pioneer_commission.lineage_entry("pioneer_1") or {}).get("job"), job_id)

    def test_refit_not_blocked_by_commission_waiting_for_script(self):
        pioneer_commission.update_commission(
            lambda s: s.setdefault("jobs", []).append(
                {"id": "p9", "kind": "pioneer", "role": "scout", "state": "attach", "new_id": "pioneer_9"}
            )
        )
        self.enqueue({"portable_bin": 1})
        fleet_status.publish("pioneer_1", {"name": "pioneer_1", "state": "FITTING", "home": "outpost_home", "tick": 1})
        self.coordinator.step(self.world.clock.now)
        self.assertEqual(self.world.inventory.count("portable_bin"), 1, self.debug_log())

    def test_coordinator_buys_missing_and_finishes(self):
        job_id = self.enqueue({"portable_bin": 1})
        fleet_status.publish("pioneer_1", {"name": "pioneer_1", "state": "FITTING", "home": "outpost_home", "tick": 1})
        self.coordinator.step(self.world.clock.now)
        self.assertEqual(self.world.inventory.count("portable_bin"), 1, self.debug_log())
        pioneer_commission.update_commission(
            lambda s: s["lineage"]["pioneer_1"].update({"fitted": True, "missing": {}})
        )
        self.coordinator.step(self.world.clock.now + 1)
        self.assertEqual([j["id"] for j in self.jobs() if j["id"] == job_id], [])
        self.assertIsNone(pioneer_commission.lineage_entry("pioneer_1"))


class _Restation(pioneer_refit.PioneerRefitMixin):
    """A miner with the miner preset mounted; the Shop must not be needed."""

    def __init__(self, modules):
        self.name, self.role, self.base_id = "pioneer_1", "miner", "outpost_home"
        self.vehicle = SimpleNamespace(name="Digger")  # operator name: no rename
        self.log = TreeConsole(module="test")
        self.modules, self.telemetry = modules, []

    def get_current_tick(self):
        return 100

    def _slots(self):
        return [MountSlot(i, "universal", m) for i, m in enumerate(self.modules)]

    def set_base(self, outpost_id):
        self.base_id = outpost_id
        return True

    def publish_telemetry(self, state, target_desc=None):
        self.telemetry.append((state, target_desc))

    def _shop(self):
        raise AssertionError("a re-station buys nothing")

    def get_outpost_ref(self, outpost_id):
        return None  # every outpost but the shortcut's is gone


class RestationTests(unittest.TestCase):
    MINER = ["nav_module", "drill_module", "battery_holder_small", "cargo_rack_small"]

    def test_same_role_same_parts_only_moves_base(self):
        host = _Restation(self.MINER)
        self.assertTrue(host.refit("miner", {"modules": self.MINER}, base="outpost_2"))
        self.assertEqual((host.base_id, host.telemetry), ("outpost_2", [("REFIT", "miner at outpost_2")]))

    def test_missing_part_takes_the_shop_path(self):
        host = _Restation(self.MINER[:-1])
        with self.assertRaises(AssertionError):
            host.refit("miner", {"modules": self.MINER}, base="outpost_2")

    def test_gone_target_outpost_refits_nothing(self):
        host = _Restation(self.MINER[:-1])
        setattr(host, "_shop", lambda: object())
        self.assertFalse(host.refit("miner", {"modules": self.MINER}, base="outpost_9"))
        self.assertEqual((host.base_id, host.telemetry), ("outpost_home", []))


class _MinerToBuilder(_Restation):
    """A miner commissioned at outpost_7 (HOME_BASE), stationed there; the hardware steps are stubbed out."""

    def __init__(self, modules):
        super().__init__(modules)
        self.base_id, self.home_base = "outpost_7", "outpost_7"

    def _shop(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        return object()

    def get_outpost_ref(self, outpost_id):  # pyright: ignore[reportIncompatibleMethodOverride]
        return object()

    def _park_for_service(self):
        return True

    def _ensure_full_charge_for_sale(self):
        pass

    def _sell_slots(self, sell):  # pyright: ignore[reportIncompatibleMethodOverride]
        return None

    def _fit_role(self, role, spec):
        pass

    def _rename_for(self, role):
        pass


class _StockHost(pioneer_stock.ConstructionStockMixin):
    """Only what material_wait_reason() and fair_share_batch() touch."""

    def get_current_tick(self):
        return 100

    def publish_telemetry(self, state, target_desc=None):
        pass

    def cargo_count(self, item_id):
        return 0

    def __init__(self):
        self.log = TreeConsole(module="test")
        self.name, self.home_base, self.base_id, self.home_outpost = "pioneer_7", "outpost_7", "outpost_home", None


class ConstructorBaseTests(StubTestCase):
    BUILDER = ["nav_module", "constructor_module", "battery_holder_small", "cargo_rack_small"]

    def test_refit_to_builder_uses_constructor_base(self):
        host = _MinerToBuilder(["nav_module", "drill_module", "battery_holder_small", "cargo_rack_small"])
        with mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"):
            self.assertTrue(host.refit("builder", {"modules": self.BUILDER}))
        self.assertEqual((host.role, host.base_id), ("builder", "outpost_home"))

    def test_refit_to_builder_ignores_an_explicit_base(self):
        host = _MinerToBuilder(["nav_module", "drill_module", "battery_holder_small", "cargo_rack_small"])
        with mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"):
            self.assertTrue(host.refit("builder", {"modules": self.BUILDER}, base="outpost_2"))
        self.assertEqual(host.base_id, "outpost_home")

    def test_builder_restore_keeps_constructor_base(self):
        moved = []
        host = SimpleNamespace(name="pioneer_1", base_id="outpost_7", set_base=lambda base: moved.append(base) or True)
        fleet_status.publish(
            "pioneer_1", {"name": "pioneer_1", "role": "builder", "home": "outpost_7", "base": "outpost_7", "tick": 5}
        )
        with mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"):
            PioneerController._restore_constructor_base(host)
        self.assertEqual(moved, ["outpost_home"])

    def _stock_host(self):
        """A builder refit from a miner at outpost_7: HOME_BASE outpost_7, based at the constructor base."""
        return _StockHost()

    def test_stock_wait_reads_constructor_base(self):
        host = self._stock_host()
        with (
            mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"),
            mock.patch.object(pioneer_stock, "takeable_stock", lambda item, outpost=None: 0),
            mock.patch.object(
                pioneer_stock.logistics_requests,
                "in_flight",
                lambda site, tick: {"steel_plate": 4} if site == "outpost_home" else {},
            ),
            mock.patch.object(
                pioneer_stock.logistics_requests,
                "active_requests",
                lambda tick: {"outpost_home": {"steel_plate": {"by": "site_supply", "target": 5}}},
            ),
        ):
            reason = host.material_wait_reason("steel_plate")
        self.assertIn("4 en route", reason)
        self.assertIn("requested by site_supply", reason)

    def test_fair_share_counts_home_born_peers(self):
        host = self._stock_host()
        fleet_status.publish(
            "pioneer_1",
            {
                "name": "pioneer_1",
                "role": "builder",
                "home": "outpost_home",
                "base": "outpost_home",
                "state": "BUILDING",
                "tick": 100,
            },
        )
        with (
            mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"),
            mock.patch.object(pioneer_stock, "takeable_stock", lambda item, outpost=None: 10),
        ):
            share = host.fair_share_batch("steel_plate", 10)
        self.assertLess(share, 10)

    def test_construction_stock_at_constructor_base(self):
        fleet_status.publish(
            "pioneer_1", {"name": "pioneer_1", "role": "builder", "home": "outpost_7", "base": "outpost_7", "tick": 9}
        )
        with mock.patch.object(production_core, "home_outpost_id", lambda: "outpost_home"):
            self.assertEqual(production_core.construction_site_id(), "outpost_home")


if __name__ == "__main__":
    unittest.main()
