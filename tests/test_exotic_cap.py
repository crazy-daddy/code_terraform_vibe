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
    def __init__(self, phase="active", fluid="ammonia", next_in=None):
        self.phase = phase
        self.fluid_id = fluid
        self.next_in = next_in

    def next_phase_in(self):
        return self.next_in

    def current_phase(self):
        return self.phase

    def fluid(self):
        return self.fluid_id


class _Event:
    kind = "healthy"


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

    def test_valve_stays_open_while_dormant(self):
        cap = _GasCap(_Deposit(phase="dormant"))
        ctl = exotic_cap.ExoticCapController(cap)
        ctl._router.ensure_connection = lambda *args: _Event()
        ctl.step()
        self.assertEqual(cap.throttles, [1.0])

    def test_short_dormancy_does_not_park(self):
        # 67 game-min at 25 real s/h = 279 ticks: below lead + minimum park time
        cap = _GasCap(_Deposit(phase="dormant", next_in=67))
        self.assertIsNone(exotic_cap.ExoticCapController(cap).park_wake_ticks())

    def test_long_dormancy_parks_until_just_before_active(self):
        cap = _GasCap(_Deposit(phase="dormant", next_in=600))
        ticks = exotic_cap.ExoticCapController(cap).park_wake_ticks()
        self.assertEqual(ticks, int(600 * 25.0 / 60.0 * 10.0) - exotic_cap.EXOTIC_WAKE_LEAD_TICKS)

    def test_no_park_while_active_releasing_or_without_timing(self):
        self.assertIsNone(exotic_cap.ExoticCapController(_GasCap(_Deposit(phase="active", next_in=600))).park_wake_ticks())
        releasing = _GasCap(_Deposit(phase="dormant", next_in=600))
        releasing.gas_out.flow = 3.0
        self.assertIsNone(exotic_cap.ExoticCapController(releasing).park_wake_ticks())
        self.assertIsNone(exotic_cap.ExoticCapController(_GasCap(_Deposit(phase="dormant"))).park_wake_ticks())
        self.assertIsNone(exotic_cap.ExoticCapController(_GasCap(None)).park_wake_ticks())

if __name__ == "__main__":
    unittest.main()
