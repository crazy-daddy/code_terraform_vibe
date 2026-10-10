"""vehicle_mining.mine_until_full_or_exhausted(): a battery stop at base ends
the job after unloading, and max_units bounds the whole job."""
import unittest

import harness
import vehicle_mining
from game_stubs import Cargo


class _Log:
    def start(self, *_):
        pass

    def end(self, *_):
        pass

    def print(self, *_):
        pass

    def trace(self, *_):
        pass


class _Vehicle:
    def __init__(self):
        self.cargo = Cargo(100)


class _Miner(vehicle_mining.VehicleMiningMixin):
    """Mines `per_charge` units per battery charge; the charging station is at `base`."""

    name = "pioneer_9"
    current_target_key = None
    current_target = None

    def __init__(self, per_charge, base):
        self.vehicle = _Vehicle()
        self.log = _Log()
        self.per_charge = per_charge
        self.base = base
        self.unloaded = 0
        self.mine_calls = []

    def mine_current_site(self, max_units=None) -> int:
        self.mine_calls.append(max_units)
        free = self.vehicle.cargo.capacity() - self.vehicle.cargo.count()
        n = min(self.per_charge, free if max_units is None else max_units, free)
        self.vehicle.cargo.items["titanium"] = self.vehicle.cargo.items.get("titanium", 0) + n
        self.mining_interrupted_battery = n == self.per_charge
        return n

    def is_recalled(self):
        return False

    def get_nearest_charging_station(self):
        return (0, 0), None

    def drive_to(self, *_, **__):
        return True

    def drive_with_recharge(self, *_, **__):
        return True

    def is_at_base(self):
        return self.base

    def unload_cargo(self):
        self.unloaded += self.vehicle.cargo.count()
        self.vehicle.cargo.items.clear()
        return 1

    def recharge_at_station(self, *_, **__):
        pass

    def publish_telemetry(self, *_):
        pass


class MiningJobBoundTests(harness.StubTestCase):
    def test_base_stop_unloads_and_ends_the_job(self):
        miner = _Miner(per_charge=39, base=True)
        miner.mine_until_full_or_exhausted((290, 170), max_units=1240)
        self.assertEqual(miner.unloaded, 39)
        self.assertEqual(miner.mine_calls, [1240])

    def test_field_stop_resumes_within_max_units(self):
        miner = _Miner(per_charge=30, base=False)
        miner.mine_until_full_or_exhausted((290, 170), max_units=70)
        self.assertEqual(miner.vehicle.cargo.count(), 70)
        self.assertEqual(miner.mine_calls, [70, 40, 10])


if __name__ == "__main__":
    unittest.main()
