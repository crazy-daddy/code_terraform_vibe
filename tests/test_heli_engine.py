"""Stub tests for the heli engine choice of new chassis (drone_upgrade.commission_engine())
and the heli commission spec (drone_commission.build_drone_spec())."""

import unittest

import drone_commission
import drone_depots
import drone_energy
import drone_upgrade
from game_stubs import MountSlot, Result
from harness import StubTestCase
from item_tiers import BATTERY_TIERS, CARGO_POD_TIERS, OIL_TANK_TIERS

HELI_PARTS = {"drone_large", "heli_thruster", "oil_tank_small", "cargo_pod_medium"}


def no_stock(_item_id):
    return 0


class CategoryLadderTests(unittest.TestCase):
    def test_ladder_by_category_and_engine(self):
        self.assertEqual(drone_upgrade.category_ladder("energy", "hauler", "heli"), OIL_TANK_TIERS)
        self.assertEqual(drone_upgrade.category_ladder("energy", "hauler", "electric"), BATTERY_TIERS)
        self.assertEqual(drone_upgrade.category_ladder("cargo", "hauler", "electric"), CARGO_POD_TIERS)
        self.assertEqual(drone_upgrade.category_ladder("role", "miner", "electric"), ["portable_bio_extractor"])
        self.assertEqual(drone_upgrade.category_ladder("role", "hauler", "electric"), [])
        self.assertEqual(drone_upgrade.category_ladder("other", "hauler", "electric"), [])


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

    def test_heli_spec_one_large_tank_frees_a_cargo_slot(self):
        parts = HELI_PARTS | {"oil_tank_large"}
        spec, _ = drone_commission.build_drone_spec("hauler", parts, no_stock, engine="heli")
        assert spec is not None
        self.assertEqual(spec["modules"], ["heli_thruster", "oil_tank_large"] + ["cargo_pod_medium"] * 4)

    def test_energy_modules_cover_target_range(self):
        self.assertEqual(drone_energy.energy_modules_needed("battery_pack", "electric"), 1)
        self.assertEqual(drone_energy.energy_modules_needed("battery_pack", "electric", plated=True), 1)
        self.assertEqual(drone_energy.energy_modules_needed("oil_tank_small", "heli"), 2)
        self.assertEqual(drone_energy.energy_modules_needed("oil_tank_small", "heli", plated=True), 2)
        self.assertEqual(drone_energy.energy_modules_needed("oil_tank_medium", "heli", plated=True), 1)

    def test_scout_keeps_its_energy_heavy_fit(self):
        self.assertEqual(drone_upgrade.fit_slot_plan("scout", "drone_large", "battery_pack"), ["role"] + ["energy"] * 4)

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


class _EngineRuleDrone:
    """Mounted modules plus the game's couple() engine rule: no Heli Thruster
    beside a Battery Pack, no Oil Tank on an electric drone or beside a Battery Pack."""

    def __init__(self, modules, inventory):
        self.mounted = list(modules)
        self.inventory = inventory

    def modules(self):
        return [MountSlot(i, "module", m) for i, m in enumerate(self.mounted)]

    def uncouple(self, index):
        self.inventory[self.mounted[index]] = self.inventory.get(self.mounted[index], 0) + 1
        self.mounted[index] = None
        return Result("ok")

    def couple(self, index, module_id):
        has_battery = "battery_pack" in self.mounted
        has_tank = any(m in drone_upgrade.OIL_TANK_TIERS for m in self.mounted)
        if (
            (module_id == "heli_thruster" and has_battery)
            or (module_id == "electric_thruster" and has_tank)
            or (module_id in drone_upgrade.OIL_TANK_TIERS and (self.mounted[0] == "electric_thruster" or has_battery))
            or (module_id == "battery_pack" and (self.mounted[0] == "heli_thruster" or has_tank))
        ):
            return Result("wrong_engine_for_module")
        if self.inventory.get(module_id, 0) <= 0:
            return Result("item_not_in_inventory")
        self.inventory[module_id] -= 1
        self.mounted[index] = module_id
        return Result("ok")


class _Log:
    def __getattr__(self, _name):
        return lambda *a, **k: self


class _Host(drone_upgrade.DroneUpgradeMixin):
    def __init__(self, drone):
        self.name = "drone_1"
        self.drone = drone
        self.log = _Log()
        self.engine = "electric"
        self.role = None

    def detect_engine(self, known=None):
        self.engine = "heli" if self.drone.mounted[0] == "heli_thruster" else "electric"


class SurplusEnergyTests(unittest.TestCase):
    def surplus(self, modules, engine, role=None):
        host = _Host(_EngineRuleDrone(modules, {}))
        host.engine = engine
        host.role = role
        slots = dict(enumerate(modules))
        return host._surplus_energy_slots(slots, sorted(i for i in slots if i))

    def test_second_large_tank_is_surplus(self):
        self.assertEqual(
            self.surplus(["heli_thruster", "oil_tank_large", "oil_tank_large", "cargo_pod_large"], "heli"), [1]
        )

    def test_smallest_tank_goes_first(self):
        self.assertEqual(
            self.surplus(["heli_thruster", "oil_tank_large", "oil_tank_small", "cargo_pod_large"], "heli"), [2]
        )

    def test_two_small_tanks_stay(self):
        self.assertEqual(
            self.surplus(["heli_thruster", "oil_tank_small", "oil_tank_small", "cargo_pod_large"], "heli"), []
        )

    def test_plated_electric_keeps_one_pack(self):
        modules = ["electric_thruster", "shield_plating", "battery_pack", "battery_pack", "cargo_pod_large"]
        self.assertEqual(self.surplus(modules, "electric", "aftermath"), [2])


class HeliConversionTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {"heli_thruster": 1, "oil_tank_large": 2}
        self.patches = {
            "heli_requested": lambda _n: True,
            "heli_ready": lambda _u, _c: True,
            "clear_heli_request": lambda _n: None,
            "inventory_count": lambda item: self.inventory.get(item, 0),
        }
        self.saved = {k: getattr(drone_upgrade, k) for k in self.patches}
        for k, v in self.patches.items():
            setattr(drone_upgrade, k, v)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(drone_upgrade, k, v)

    def test_batteries_leave_before_heli_thruster_couples(self):
        drone = _EngineRuleDrone(
            ["electric_thruster", "battery_pack", "battery_pack", "cargo_pod_large"], self.inventory
        )
        host = _Host(drone)
        self.assertEqual(host.convert_to_heli_if_requested({"oil_tank_large"}), {})
        # One Large tank covers TARGET_RANGE_M; the second battery slot is left for a Cargo Pod.
        self.assertEqual(drone.mounted, ["heli_thruster", "oil_tank_large", None, "cargo_pod_large"])
        self.assertEqual(host.engine, "heli")

    def test_failed_thruster_couple_restores_electric_parts(self):
        drone = _EngineRuleDrone(
            ["electric_thruster", "battery_pack", "battery_pack", "cargo_pod_large"], self.inventory
        )
        original = drone.couple
        drone.couple = lambda index, module_id: (
            Result("locked") if module_id == "heli_thruster" else original(index, module_id)
        )
        _Host(drone).convert_to_heli_if_requested({"oil_tank_large"})
        self.assertEqual(drone.mounted, ["electric_thruster", "battery_pack", "battery_pack", "cargo_pod_large"])


if __name__ == "__main__":
    unittest.main()
