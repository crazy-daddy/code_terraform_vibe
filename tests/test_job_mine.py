"""MineJob (lib/job_mine.py) with RoverTargets and OutpostStockpile: pick order, resume with cargo aboard, a poi and a mine trip, idle stand-by (and the no-charger recharge rule), error release."""
import unittest

import harness
import mining_reservations
import vehicle_claims
from archive import archive
from fleet_unit import FleetUnitMixin
from game_stubs import Cargo
from job_mine import MineJob, OutpostStockpile, RoverTargets
from mission import Mission
from priority import NEED, STOCK
from tree_console import TreeConsole
from vehicle_mining import VehicleMiningMixin


class _Vehicle:
    def __init__(self, cargo):
        self.cargo = cargo


class _Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y


def _site(key, item, coords, band=STOCK):
    return {"key": key, "type": "mine", "coords": coords, "name": key, "harvest_item": item, "reason": "test", "priority": 2, "band": band}


class _Host(VehicleMiningMixin):
    """The VehicleController surface MineJob reads; the real select_best_mining_target(), cargo_matches_target(), cargo_full_for_resume()."""
    name = "rover_1"

    def __init__(self, cargo=None, at_base=True, level=1.0, charger=True, pois=(), sites=(), achievable=True):
        self.log = TreeConsole()
        self.vehicle = _Vehicle(cargo if cargo is not None else Cargo(100, {}))
        self.mission: "Mission | None" = None
        self.home_charging_station = object() if charger else None
        self.assigned_slot_coords = (0.0, 0.0)
        self.cruise_throttle = 0.5
        self.stockpile_empty_reason = "no ore assigned to this outpost"
        self.at_base = at_base
        self.level = level
        self.pois = list(pois)
        self.sites = list(sites)
        self.achievable = achievable
        self.calls = []

    # position, energy
    def is_at_base(self, threshold=3.0):
        return self.at_base

    def get_position(self):
        return (0.0, 0.0)

    def get_home_slot_coords(self):
        return self.assigned_slot_coords

    def distance_between(self, a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def get_battery(self):
        return self.level * 200.0, 200.0, self.level

    def calculate_trip_energy(self, coords, planned_drill_units=0, planned_scans=0, mine_item_id=None, mine_purity=None):
        return {"is_achievable": self.achievable, "total_required_wh": 100.0, "current_wh": self.level * 200.0, "dist_inbound": 10.0, "nearest_cs_coords": (0.0, 0.0)}

    def max_mineable_units(self, coords, item_id, purity=None):
        return 10

    def leg_speed_m_per_hour(self, x, y):
        return 100.0

    def mine_hours_per_unit(self, item_id, purity=None):
        return 0.1

    def get_nearest_charging_station(self, from_coords=None):
        return (0.0, 0.0), {"id": "charging_station_1"}

    def energy_wh_for_leg(self, distance_m, throttle, cargo_units=None):
        return distance_m * 0.15

    # candidates, claims
    def cleanup_stale_claims(self):
        pass

    def unscanned_pois(self):
        return self.pois

    def build_mineral_site_candidates(self, deprioritize_hardness_at_or_below=None):
        return [dict(s) for s in self.sites]

    def build_local_stockpile_candidates(self, outpost_id):
        return [dict(s) for s in self.sites]

    def home_ore_demand(self):
        return {"iron_ore": 10}

    def get_claims(self):
        return {}

    def stockpile_headroom(self, outpost_id, item_id):
        return 40

    def stockpile_need(self, outpost_id):
        return {}

    def begin_mission(self, mission, claimed=False) -> bool:
        self.calls.append(("begin", mission.target_key))
        self.mission = mission
        return True

    def release_target_claim(self, target_key=None):
        self.calls.append("release")
        self.mission = None

    def end_mission(self, release_claim=True):
        self.calls.append("end_mission")
        self.mission = None

    # actions
    def recharge_at_station(self, target_level=1.0, station_coords=None, station_id=None):
        self.calls.append("recharge")
        self.level = target_level
        return True

    def return_to_base(self):
        self.calls.append("return")
        self.at_base = True
        return True

    def unload_cargo(self):
        self.calls.append("unload")
        self.vehicle.cargo.items.clear()
        return 1

    def publish_telemetry(self, state, target_desc=None):
        self.calls.append(state)

    def set_intent(self, text):
        pass

    def drive_with_recharge(self, x, y, precision=None):
        self.calls.append(("drive", x, y))
        self.at_base = False
        return True

    def scan_and_survey(self, mission=None):
        self.calls.append(("scan", mission.target_key if mission else None))
        return []

    def mine_until_full_or_exhausted(self, target_coords, max_units=None):
        self.calls.append(("mine", max_units))


class MineJobPickTests(harness.StubTestCase):
    def test_rover_poi_beats_mineral_site(self):
        host = _Host(pois=[_Point(5, 5)], sites=[_site("site_1", "iron_ore", (3, 3))])
        mission = MineJob(host, RoverTargets()).pick()
        assert mission is not None
        self.assertEqual(mission.target_key, "poi_5_5")
        self.assertIs(mission, host.mission)
        self.assertEqual(host.calls, [("begin", "poi_5_5")])

    def test_stockpile_higher_band_first(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3)), _site("site_2", "silicon_ore", (40, 40), band=NEED)])
        mission = MineJob(host, OutpostStockpile("outpost_1")).pick()
        assert mission is not None
        self.assertEqual(mission.target_key, "site_2")
        self.assertEqual(mission.target["estimated_units"], 10)

    def test_resumed_mission_beats_candidates(self):
        host = _Host(pois=[_Point(5, 5)])
        resumed = Mission(kind="mine", target_key="site_9", target=_site("site_9", "iron_ore", (8, 8)))
        host.mission = resumed
        mission = MineJob(host, RoverTargets()).pick()
        assert mission is not None
        self.assertEqual(mission.target_key, "site_9")
        self.assertIsNotNone(mission.budget)
        self.assertIs(host.mission, resumed)  # a copy carries the budget
        self.assertIsNone(resumed.budget)
        self.assertEqual(host.calls, [])


class MineJobPrepareTests(harness.StubTestCase):
    def test_resume_keeps_matching_cargo_aboard(self):
        host = _Host(cargo=Cargo(100, {"iron_ore": 20}), at_base=False)
        host.mission = Mission(kind="mine", target_key="site_9", target=_site("site_9", "iron_ore", (8, 8)))
        self.assertIsNone(MineJob(host, OutpostStockpile("outpost_1")).prepare())
        self.assertEqual(host.calls, [])

    def test_mismatched_cargo_goes_home_first_and_keeps_mission(self):
        host = _Host(cargo=Cargo(100, {"silicon_ore": 20}), at_base=False)
        host.mission = Mission(kind="mine", target_key="site_9", target=_site("site_9", "iron_ore", (8, 8)))
        self.assertEqual(MineJob(host, RoverTargets()).prepare(), 0)
        self.assertEqual(host.calls, ["return", "unload"])
        self.assertIsNotNone(host.mission)

    def test_full_hold_unloads_before_resuming(self):
        host = _Host(cargo=Cargo(100, {"iron_ore": 100}))
        host.mission = Mission(kind="mine", target_key="site_9", target=_site("site_9", "iron_ore", (8, 8)))
        self.assertEqual(MineJob(host, RoverTargets()).prepare(), 0)
        self.assertEqual(host.calls, ["unload"])

    def test_blocked_unload_waits(self):
        host = _Host(cargo=Cargo(100, {"iron_ore": 20}))
        host.unload_cargo = lambda: host.calls.append("unload") or -1  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, RoverTargets()).prepare(), 10.0)
        self.assertEqual(host.calls, ["unload", "WAITING_INVENTORY_SPACE"])

    def test_partial_unload_waits(self):
        host = _Host(cargo=Cargo(100, {"iron_ore": 20}))
        host.unload_cargo = lambda: host.calls.append("unload") or 0  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, RoverTargets()).prepare(), 10.0)

    def test_stockpile_transfers_to_base_slot(self):
        host = _Host(at_base=False)
        self.assertEqual(MineJob(host, OutpostStockpile("outpost_1")).prepare(), 0)
        self.assertEqual(host.calls, ["return"])

    def test_rover_plans_from_where_it_stands(self):
        host = _Host(at_base=False)
        self.assertIsNone(MineJob(host, RoverTargets()).prepare())
        self.assertEqual(host.calls, [])

    def test_rover_tops_off_without_local_charger(self):
        host = _Host(level=0.87, charger=False)
        self.assertIsNone(MineJob(host, RoverTargets()).prepare())
        self.assertEqual(host.calls, ["recharge"])

    def test_stockpile_tops_off_only_at_local_charger(self):
        host = _Host(level=0.87, charger=False)
        MineJob(host, OutpostStockpile("outpost_1")).prepare()
        self.assertEqual(host.calls, [])
        host = _Host(level=0.87, charger=True)
        MineJob(host, OutpostStockpile("outpost_1")).prepare()
        self.assertEqual(host.calls, ["recharge"])


class MineJobExecuteTests(harness.StubTestCase):
    def test_poi_trip_scans_and_releases(self):
        host = _Host(pois=[_Point(5, 5)])
        job = MineJob(host, RoverTargets())
        self.assertEqual(job.step(), 0)
        self.assertEqual(host.calls, [
            ("begin", "poi_5_5"), "OUTBOUND", ("drive", 5, 5), ("scan", "poi_5_5"),
            "return", "release", "unload", "recharge", "READY_AT_BASE",
        ])
        self.assertIsNone(host.mission)

    def test_mine_trip_mines_stockpile_headroom(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3))], charger=False)
        self.assertEqual(MineJob(host, OutpostStockpile("outpost_1")).step(), 0)
        self.assertIn(("mine", 40), host.calls)
        self.assertEqual(host.calls[-4:], ["return", "release", "unload", "READY_AT_OUTPOST"])  # no charger: no recharge

    def test_rover_mine_trip_mines_reserved_yield(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3))])
        MineJob(host, RoverTargets()).step()
        self.assertIn(("mine", 10), host.calls)

    def test_incomplete_return_keeps_mission(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3))])
        host.return_to_base = lambda: host.calls.append("return") and False  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, RoverTargets()).step(), 5.0)
        self.assertNotIn("release", host.calls)
        self.assertIsNotNone(host.mission)


    def test_outbound_failure_returns_home_and_keeps_claim(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3))])
        host.drive_with_recharge = lambda x, y, precision=None: host.calls.append("drive") and False  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, RoverTargets()).step(), 0)
        self.assertEqual(host.calls[-2:], ["drive", "return"])
        self.assertNotIn("release", host.calls)
        self.assertIsNotNone(host.mission)

    def test_blocked_unload_after_trip_waits(self):
        host = _Host(sites=[_site("site_1", "iron_ore", (3, 3))])
        host.unload_cargo = lambda: host.calls.append("unload") or -1  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, RoverTargets()).step(), 10.0)
        self.assertEqual(host.calls[-2:], ["unload", "WAITING_INVENTORY_SPACE"])
        self.assertNotIn("recharge", host.calls)

    def test_resumed_mine_mission_units(self):
        target = dict(_site("site_9", "iron_ore", (8, 8)), estimated_units=7)
        for targets, units in ((OutpostStockpile("outpost_1"), 40), (RoverTargets(), 7)):
            host = _Host()
            host.mission = Mission(kind="mine", target_key="site_9", target=dict(target))
            job = MineJob(host, targets)
            self.assertEqual(job.step(), 0)
            self.assertIn(("mine", units), host.calls)
            self.assertIn("release", host.calls)


class MineJobIdleTests(harness.StubTestCase):
    def test_rover_idles_with_reason(self):
        host = _Host()
        job = MineJob(host, RoverTargets())
        self.assertEqual(job.step(), 10.0)
        self.assertEqual(host.calls, ["IDLE_AT_BASE"])
        self.assertIn("no surveyed mineral or unscanned POI", self.debug_log())

    def test_stockpile_idles_with_empty_reason(self):
        host = _Host()
        self.assertEqual(MineJob(host, OutpostStockpile("outpost_1")).step(), 30.0)
        self.assertEqual(host.calls, ["IDLE_AT_OUTPOST"])
        self.assertIn("no ore assigned to this outpost", self.debug_log())

    def test_no_charger_recharges_when_full_battery_reaches_site(self):
        host = _Host(level=0.3, charger=False, sites=[_site("site_1", "iron_ore", (3, 3))], achievable=False)
        host.max_mineable_units = lambda *args, **kwargs: 0  # type: ignore[method-assign]
        self.assertEqual(MineJob(host, OutpostStockpile("outpost_1")).step(), 0)
        self.assertEqual(host.calls, ["recharge"])

    def test_no_charger_stands_by_when_transfer_eats_the_gain(self):
        host = _Host(level=0.3, charger=False, sites=[_site("site_1", "iron_ore", (3, 3))], achievable=False)
        host.max_mineable_units = lambda *args, **kwargs: 0  # type: ignore[method-assign]
        host.assigned_slot_coords = (800.0, 0.0)  # 120 Wh transfer: 200 - 120 < 100 needed
        self.assertEqual(MineJob(host, OutpostStockpile("outpost_1")).step(), 30.0)
        self.assertEqual(host.calls, ["IDLE_AT_OUTPOST"])
        self.assertIn("out of energy range", self.debug_log())


class MineJobErrorTests(harness.StubTestCase):
    def test_on_error_releases_claims_and_mission(self):
        host = _Host()
        host.mission = Mission(kind="mine", target_key="site_9", target=_site("site_9", "iron_ore", (8, 8)), reserved_yield=True)
        MineJob(host, OutpostStockpile("outpost_1")).on_error()
        self.assertEqual(host.calls, ["release"])
        self.assertIsNone(host.mission)


class _ClaimsHost(vehicle_claims.VehicleClaimsMixin, FleetUnitMixin, _Host):
    """_Host with the real claims, mission record and yield reservation."""

    def _owns(self, claim):
        return claim.get("vehicle") == self.name


class MineJobClaimsTests(harness.StubTestCase):
    def test_pick_saves_one_mission_and_on_error_clears_it(self):
        host = _ClaimsHost(sites=[_site("site_1", "iron_ore", (3, 3))])
        job = MineJob(host, RoverTargets())
        mission = job.pick()
        assert mission is not None
        self.assertIs(mission, host.mission)
        self.assertEqual(list(archive.get(host.MISSION_KEY, {})), ["rover_1"])
        self.assertTrue(host.get_claims())
        self.assertIsNotNone(mining_reservations.reservation_of("rover_1"))
        job.on_error()
        self.assertIsNone(host.mission)
        self.assertEqual(host.get_claims(), {})
        self.assertIsNone(archive.get_entry(host.MISSION_KEY, "rover_1"))
        self.assertIsNone(mining_reservations.reservation_of("rover_1"))


if __name__ == "__main__":
    unittest.main()
