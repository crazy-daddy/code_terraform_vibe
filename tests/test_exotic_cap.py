import unittest

from harness import StubTestCase
import exotic_cap


class _Port:
    def __init__(self, flow=0.0):
        self.flow = flow
        self.targets = []

    def flow_rate(self):
        return self.flow

    def connected_id(self):
        return None

    def connect(self, target_id):
        self.targets.append(target_id)


class _Deposit:
    def __init__(self, phase="active", fluid="ammonia"):
        self.phase = phase
        self.fluid_id = fluid

    def current_phase(self):
        return self.phase

    def fluid(self):
        return self.fluid_id


class _GasCap:
    id = "exotic_gas_cap_1"

    def __init__(self, deposit):
        self.site = deposit
        self.gas_out = _Port()
        self.throttles = []

    def deposit(self):
        return self.site

    def set_throttle(self, t):
        self.throttles.append(t)


class _SpringTap:
    id = "exotic_spring_tap_1"

    def __init__(self, deposit):
        self.site = deposit
        self.liquid_out = _Port()

    def deposit(self):
        return self.site


class ExoticCapTests(StubTestCase):
    def test_medium_picks_port_tanks_and_fluid(self):
        gas = exotic_cap.ExoticCapController(_GasCap(_Deposit(fluid="raw_chlorine")))
        self.assertEqual(gas.port_name, "gas_out")
        self.assertEqual(gas._router.type_ids, exotic_cap.GAS_TANK_TYPE_IDS)
        self.assertEqual(gas._router.fluid_id, "raw_chlorine")
        self.assertEqual(gas.parker.kind, "exotic_cap")
        tap = exotic_cap.ExoticCapController(_SpringTap(_Deposit(fluid="brine")))
        self.assertEqual(tap.port_name, "liquid_out")
        self.assertEqual(tap._router.type_ids, exotic_cap.fluid_routing.LIQUID_TANK_TYPE_IDS)
        self.assertEqual(tap._router.fluid_id, "brine")

    def test_dormant_only_once_buffer_stops_releasing(self):
        cap = _GasCap(_Deposit(phase="active"))
        ctl = exotic_cap.ExoticCapController(cap)
        self.assertFalse(ctl.well_dormant())
        cap.site.phase = "dormant"
        cap.gas_out.flow = 4.0
        self.assertFalse(ctl.well_dormant())
        cap.gas_out.flow = 0.0
        self.assertTrue(ctl.well_dormant())

    def test_dormant_step_closes_valve(self):
        cap = _GasCap(_Deposit(phase="dormant"))
        ctl = exotic_cap.ExoticCapController(cap)
        ctl.step()
        self.assertEqual(cap.throttles, [0.0])
        self.assertEqual(cap.gas_out.targets, [])

    def test_missing_deposit_is_idle(self):
        cap = _GasCap(None)
        ctl = exotic_cap.ExoticCapController(cap)
        self.assertTrue(ctl.well_dormant())


if __name__ == "__main__":
    unittest.main()
