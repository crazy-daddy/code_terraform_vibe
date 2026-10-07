"""vehicle_mining.VehicleMiningMixin.cargo_full_for_resume(): a reload with a
full hold unloads before resuming the restored mining claim."""
import unittest

import harness
import vehicle_mining
from game_stubs import Cargo


class _Vehicle:
    def __init__(self, cargo):
        self.cargo = cargo


class _Miner(vehicle_mining.VehicleMiningMixin):
    name = "pioneer_5"

    def __init__(self, cargo=None):
        self.vehicle = _Vehicle(cargo) if cargo is not None else object()


class CargoFullForResumeTests(harness.StubTestCase):
    def test_full_hold(self):
        self.assertTrue(_Miner(Cargo(100, {"iron_ore": 100})).cargo_full_for_resume())

    def test_partial_hold(self):
        self.assertFalse(_Miner(Cargo(100, {"iron_ore": 91})).cargo_full_for_resume())

    def test_no_cargo_module(self):
        self.assertFalse(_Miner().cargo_full_for_resume())


if __name__ == "__main__":
    unittest.main()
