"""PullJob (lib/job_pull.py): cargo-aboard delivery, idle reasons, floating destinations (band groups, set_base()), the unviable-first-stop record shared with VehicleCargoMixin.pull_from_source(), and pull_plan's destination grouping, best_pull_route() from an origin and drop_unviable_sources() pruning."""

import builtins
import unittest
from unittest import mock

import harness
import logistics_requests
import outpost_flow
import priority
import pull_plan
from game_stubs import Cargo
from job_pull import NO_DEMAND, SHORT, PullJob
from mission import Mission
from tree_console import TreeConsole
from vehicle import VehicleController
from vehicle_cargo import VehicleCargoMixin


class _Outpost:
    def __init__(self, outpost_id, coords=(0.0, 0.0), is_home=False):
        self.id = outpost_id
        self._coords = coords
        self.is_home = is_home

    def coords(self):
        return self._coords


class _Network:
    def __init__(self, outposts):
        self._outposts = outposts

    def outposts(self):
        return list(self._outposts)


class _Vehicle:
    def __init__(self, cargo=0):
        self.cargo = Cargo(capacity=400, items={"ore": cargo} if cargo else None)


class _Host(VehicleCargoMixin):
    """The VehicleController surface PullJob and pull_from_source() read; driving always fails."""

    name = "pioneer_8"
    home_base = "outpost_1"

    def __init__(self, cargo=0, unload=5, throttle=0.1):
        self.log = TreeConsole()
        self.vehicle = _Vehicle(cargo)
        self.home_outpost = _Outpost("outpost_1")
        self.intent = None
        self.unload_result = unload
        self.throttle = throttle
        self.calls = []

    def set_base(self, outpost_id):
        self.home_outpost = _Outpost(outpost_id)
        return True

    def handle_upgrade_cycle_if_idle(self):
        self.calls.append("upgrade")

    def get_current_tick(self):
        return 42

    def get_position(self):
        return (0.0, 0.0)

    def is_at_base(self):
        return False

    def set_intent(self, text):
        self.intent = text

    def publish_telemetry(self, state, *args):
        self.calls.append(state)

    def return_to_base(self):
        self.calls.append("return")
        return True

    def unload_cargo(self, outpost=None):
        self.calls.append("unload")
        self.vehicle.cargo.items = {}
        return self.unload_result

    def recharge_at_station(self, target_level=1.0):
        self.calls.append("recharge")

    def drive_with_recharge(self, x, y, precision=1.5, min_throttle=None):
        return False

    def full_battery_throttle(self, coords):
        return self.throttle


class PullJobTests(harness.StubTestCase):
    def test_cargo_aboard_is_delivered_before_planning(self):
        host = _Host(cargo=12)
        job = PullJob(host)
        with (
            mock.patch.object(pull_plan, "pull_destinations") as dests,
            mock.patch.object(logistics_requests, "pickup_dest", return_value="outpost_5"),
        ):
            self.assertEqual(job.step(), 0)
        dests.assert_not_called()
        self.assertEqual(host.home_outpost.id, "outpost_5")
        self.assertEqual(host.calls, ["upgrade", "RETURNING", "return", "unload", "recharge", "READY_AT_OUTPOST"])

    def test_blocked_unload_waits_poll_interval(self):
        host = _Host(cargo=12, unload=-1)
        self.assertEqual(PullJob(host, poll_interval=7.0).step(), 7.0)
        self.assertIn("WAITING_INVENTORY_SPACE", host.calls)

    def test_no_demand_parks_idle(self):
        host = _Host()
        job = PullJob(host)
        with (
            mock.patch.object(pull_plan, "pull_destinations", return_value=[]),
            mock.patch.object(
                builtins, "get_component", return_value=_Network([_Outpost("outpost_1"), _Outpost("outpost_2")])
            ),
        ):
            self.assertEqual(job.step(), 10.0)
        self.assertEqual(job.wait, NO_DEMAND)
        self.assertIsNone(job.dispersed_tick)
        self.assertEqual(host.calls, ["upgrade", "return", "IDLE_AT_OUTPOST"])

    def test_no_demand_disperses_to_busiest_source(self):
        host = _Host()
        job = PullJob(host)
        outposts = [_Outpost("outpost_1"), _Outpost("outpost_2", (50.0, 0.0))]
        outpost_flow.record(42, sent={"outpost_2": 40})
        with (
            mock.patch.object(pull_plan, "pull_destinations", return_value=[]),
            mock.patch.object(builtins, "get_component", return_value=_Network(outposts)),
        ):
            job.step()
            self.assertEqual(host.home_outpost.id, "outpost_2")
            self.assertEqual(job.dispersed_tick, 42)
            # Within the cooldown no second move, even toward a busier outpost.
            outpost_flow.record(42, sent={"outpost_1": 400})
            job.step()
        self.assertEqual(host.home_outpost.id, "outpost_2")
        self.assertEqual(
            host.calls,
            ["upgrade", "IDLE_AT_OUTPOST", "return", "IDLE_AT_OUTPOST", "upgrade", "return", "IDLE_AT_OUTPOST"],
        )

    def test_delivery_records_received_flow(self):
        host = _Host(cargo=12)
        with mock.patch.object(logistics_requests, "pickup_dest", return_value=None):
            PullJob(host).step()
        self.assertEqual(outpost_flow.read(42), {"outpost_1": (0.0, 5.0)})

    def test_plan_below_minimum_waits(self):
        host = _Host()
        job = PullJob(host)
        with (
            mock.patch.object(
                pull_plan, "pull_destinations", return_value=[[(_Outpost("outpost_3"), {"need": {"ore": 50}})]]
            ),
            mock.patch.object(pull_plan, "plan_pull_route", return_value=([], 0, None)),
            mock.patch.object(builtins, "get_component", return_value=_Network([_Outpost("outpost_1")])),
        ):
            self.assertEqual(job.step(), 10.0)
        self.assertEqual(job.wait, SHORT)
        self.assertIsNone(job.dispersed_tick)
        self.assertEqual(host.calls, ["upgrade", "return", "IDLE_AT_OUTPOST"])
        self.assertEqual(host.home_outpost.id, "outpost_1")

    def test_short_disperses_like_no_demand(self):
        host = _Host()
        job = PullJob(host)
        outposts = [_Outpost("outpost_1"), _Outpost("outpost_2", (50.0, 0.0))]
        outpost_flow.record(42, sent={"outpost_2": 40})
        with (
            mock.patch.object(
                pull_plan, "pull_destinations", return_value=[[(_Outpost("outpost_3"), {"need": {"ore": 50}})]]
            ),
            mock.patch.object(pull_plan, "plan_pull_route", return_value=([], 0, None)),
            mock.patch.object(builtins, "get_component", return_value=_Network(outposts)),
        ):
            job.step()
        self.assertEqual(job.wait, SHORT)
        self.assertEqual(host.home_outpost.id, "outpost_2")
        self.assertEqual(job.dispersed_tick, 42)
        self.assertEqual(host.calls, ["upgrade", "IDLE_AT_OUTPOST", "return", "IDLE_AT_OUTPOST"])

    def _pick(self, groups, plans):
        """PullJob.pick() over `groups` with plan_pull_route() answering `plans` ({dest id: (route, reachable, rank)}); claims grant everything."""
        host = _Host()
        job = PullJob(host)

        def plan(_host, dest, *_args):
            return plans.get(dest.id, ([], 0, None))

        def claim(_name, dest_id, legs, _seen, _tick):
            return list(legs)

        with (
            mock.patch.object(pull_plan, "pull_destinations", return_value=groups),
            mock.patch.object(pull_plan, "plan_pull_route", side_effect=plan) as planned,
            mock.patch.object(logistics_requests, "min_load_units", return_value=1),
            mock.patch.object(logistics_requests, "claim_pickups", side_effect=claim) as claimed,
        ):
            mission = job.pick()
        assert mission is not None
        return host, mission, planned, claimed

    def test_best_rank_in_the_top_band_group_wins_and_moves_the_base(self):
        src = {"kind": "outpost", "id": "outpost_9", "coords": (50.0, 0.0), "outpost": None}
        need = {priority.NEED: {"ore": 50}}
        groups = [[(_Outpost("outpost_2"), need), (_Outpost("outpost_3"), need)], [(_Outpost("outpost_4"), need)]]
        plans = {
            "outpost_2": ([(src, [("ore", 10)])], 10, (0.1,)),
            "outpost_3": ([(src, [("ore", 20)])], 20, (0.2,)),
            "outpost_4": ([(src, [("ore", 90)])], 90, (0.9,)),
        }
        host, mission, planned, _claimed = self._pick(groups, plans)
        self.assertEqual(mission.target["dest"], "outpost_3")
        self.assertEqual(host.home_outpost.id, "outpost_3")
        # The lower band group is never planned while a higher one has a trip.
        self.assertEqual([c.args[1].id for c in planned.call_args_list], ["outpost_2", "outpost_3"])

    def test_group_without_a_trip_falls_through_to_the_next(self):
        src = {"kind": "outpost", "id": "outpost_9", "coords": (50.0, 0.0), "outpost": None}
        need = {priority.NEED: {"ore": 50}}
        groups = [[(_Outpost("outpost_2"), need)], [(_Outpost("outpost_4"), need)]]
        plans = {"outpost_4": ([(src, [("ore", 30)])], 30, (0.3,))}
        host, mission, _planned, _claimed = self._pick(groups, plans)
        self.assertEqual(mission.target["dest"], "outpost_4")
        self.assertEqual(host.home_outpost.id, "outpost_4")

    def test_resumed_mission_restores_its_base(self):
        host = _Host()
        job = PullJob(host)
        first = {"kind": "outpost", "id": "outpost_2", "coords": (100.0, 0.0), "outpost": None}
        job.execute(
            Mission(
                kind="pull",
                target_key="outpost_2",
                target={"route": [(first, [("ore", 10)])], "dest": "outpost_7"},
                tick=42,
            )
        )
        self.assertEqual(host.home_outpost.id, "outpost_7")

    def test_unreachable_first_stop_is_recorded_on_the_job(self):
        host = _Host()
        job = PullJob(host)
        first = {"kind": "outpost", "id": "outpost_2", "coords": (100.0, 0.0), "outpost": None}
        later = {"kind": "outpost", "id": "outpost_3", "coords": (200.0, 0.0), "outpost": None}
        route = [(first, [("ore", 10)]), (later, [("ore", 5)])]
        delay = job.execute(Mission(kind="pull", target_key="outpost_2", target={"route": route}, tick=42))
        self.assertEqual(delay, job.poll_interval)
        self.assertEqual(job.unviable, {"outpost_2": 42})
        self.assertIn("return", host.calls)

    def test_viable_but_failed_leg_is_not_recorded(self):
        host = _Host(throttle=0.9)
        unviable = {}
        source = {"kind": "outpost", "id": "outpost_2", "coords": (100.0, 0.0), "outpost": None}
        self.assertIsNone(host.pull_from_source(source, [("ore", 10)], "outpost_1", 42, unviable=unviable))
        self.assertEqual(unviable, {})


class _PlanHost:
    name = "pioneer_8"

    def __init__(self, position):
        self.log = TreeConsole()
        self.position = position

    def get_position(self):
        return self.position


class PullDestinationTests(harness.StubTestCase):
    def test_top_band(self):
        self.assertIsNone(pull_plan.top_band({}))
        self.assertIsNone(pull_plan.top_band({priority.NEED: {"ore": 0}}))
        self.assertEqual(pull_plan.top_band({priority.BLOCKER: {"ore": 1}, priority.STOCK: {"ore": 1}}), 0)
        self.assertEqual(pull_plan.top_band({priority.STOCK: {"ore": 1}}), len(logistics_requests.TIERS) - 1)

    def test_groups_by_top_band_highest_first(self):
        a, b, c, d = _Outpost("a"), _Outpost("b"), _Outpost("c"), _Outpost("d")
        tiers = {
            "a": {priority.STOCK: {"ore": 5}},
            "b": {priority.BLOCKER: {"ore": 1}, priority.STOCK: {"ore": 5}},
            "c": {},
            "d": {priority.STOCK: {"ice": 2}},
        }
        with (
            mock.patch.object(builtins, "get_component", return_value=_Network([a, b, c, d])),
            mock.patch.object(pull_plan, "pull_deficits_tiered", side_effect=lambda o, _t, _r=None: tiers[o.id]),
        ):
            groups = pull_plan.pull_destinations(42)
        self.assertEqual([[o.id for o, _t in g] for g in groups], [["b"], ["a", "d"]])


class BestPullRouteTests(harness.StubTestCase):
    def test_scores_from_origin_to_dest(self):
        dest = _Outpost("dest", coords=(1000.0, 0.0))
        near = {"kind": "drill", "id": "near", "coords": (900.0, 0.0), "available": {"ore": 50}, "outpost": None}
        far = {"kind": "drill", "id": "far", "coords": (-900.0, 0.0), "available": {"ore": 50}, "outpost": None}
        deficits = {priority.NEED: {"ore": 50}}
        host = _PlanHost(position=(-1000.0, 0.0))
        # From the given origin next to the dest, the source beside the dest wins.
        route, reachable, rank = pull_plan.best_pull_route(
            host, dest, deficits, [far, near], 400, 42, origin=(950.0, 0.0)
        )
        self.assertEqual(route[0][0]["id"], "near")
        self.assertEqual(reachable, 50)
        self.assertIsNotNone(rank)
        # Without an origin the trip starts at the host, far west: it ranks lower.
        route, _reachable, west_rank = pull_plan.best_pull_route(host, dest, deficits, [far, near], 400, 42)
        self.assertTrue(logistics_requests.rank_beats(rank, west_rank))

    def test_no_sources_has_no_rank(self):
        route, reachable, rank = pull_plan.best_pull_route(
            _PlanHost((0.0, 0.0)), _Outpost("dest"), {priority.NEED: {"ore": 5}}, [], 400, 42
        )
        self.assertEqual((route, reachable, rank), ([], 0, None))


class _BaseHost:
    """VehicleController.set_base()/base_id over stub outpost lookups."""

    set_base = VehicleController.set_base
    base_id = VehicleController.base_id
    name = "pioneer_8"
    home_base = "outpost_1"

    def __init__(self, outposts):
        self.log = TreeConsole()
        self.outposts = outposts
        self.home_outpost = outposts["outpost_1"]
        self.home_charging_station = "station_outpost_1"
        self.assigned_slot_coords = self.home_coords = (0.0, 0.0)

    def get_outpost_ref(self, outpost_id=None):
        return self.outposts.get(outpost_id or "outpost_1")

    def find_charging_station(self, outpost):
        return f"station_{outpost.id}"

    def get_home_slot_coords(self):
        return self.home_outpost.coords()


class SetBaseTests(harness.StubTestCase):
    def test_moves_outpost_station_and_slot_keeping_home_base(self):
        host = _BaseHost({"outpost_1": _Outpost("outpost_1"), "outpost_2": _Outpost("outpost_2", coords=(50.0, 5.0))})
        self.assertTrue(host.set_base("outpost_2"))
        self.assertEqual(host.base_id, "outpost_2")
        self.assertEqual(host.home_charging_station, "station_outpost_2")
        self.assertEqual((host.assigned_slot_coords, host.home_coords), ((50.0, 5.0), (50.0, 5.0)))
        self.assertEqual(host.home_base, "outpost_1")

    def test_unknown_outpost_changes_nothing(self):
        host = _BaseHost({"outpost_1": _Outpost("outpost_1")})
        self.assertFalse(host.set_base("outpost_9"))
        self.assertEqual(host.base_id, "outpost_1")
        self.assertEqual(host.home_charging_station, "station_outpost_1")


class PickupDestTests(harness.StubTestCase):
    def test_aboard_entry_wins_and_others_are_ignored(self):
        now = logistics_requests.now_tick()
        self.assertIsNone(logistics_requests.pickup_dest("pioneer_8"))
        logistics_requests.reserve_pickup("pioneer_8", "outpost_3", "ore", 5, now, source_id="a")
        logistics_requests.reserve_pickup("pioneer_9", "outpost_7", "ore", 5, now, source_id="a", aboard=True)
        self.assertEqual(logistics_requests.pickup_dest("pioneer_8"), "outpost_3")
        logistics_requests.reserve_pickup("pioneer_8", "outpost_4", "ore", 5, now, source_id="b", aboard=True)
        self.assertEqual(logistics_requests.pickup_dest("pioneer_8"), "outpost_4")

    def test_stale_entries_are_ignored(self):
        old = logistics_requests.now_tick() - logistics_requests.PICKUP_STALE_TICKS - 1
        logistics_requests.reserve_pickup("pioneer_8", "outpost_3", "ore", 5, old, source_id="a", aboard=True)
        self.assertIsNone(logistics_requests.pickup_dest("pioneer_8"))


class DropUnviableTests(unittest.TestCase):
    def test_prunes_expired_and_drops_the_rest(self):
        unviable = {"a": 0, "b": pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS}
        sources = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        kept = pull_plan.drop_unviable_sources(sources, unviable, pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS + 1)
        self.assertEqual([s["id"] for s in kept], ["a", "c"])
        self.assertEqual(unviable, {"b": pull_plan.PULL_UNVIABLE_COOLDOWN_TICKS})


if __name__ == "__main__":
    unittest.main()
