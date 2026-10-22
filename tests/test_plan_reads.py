"""logistics_requests.PlanReads: one planning pass reads requests, pickups and
each outpost's stock once, and gives the same answers as the per-call reads
(outpost_deficits_tiered(), outpost_free_tiers(), fair_tier_caps())."""

import unittest
from types import SimpleNamespace
from unittest import mock

import drone_haul_plan
import harness
import job_haul
import logistics_snapshot
import priority
from harness import StubTestCase, logistics_requests
from tree_console import TreeConsole

R = harness.request


class PlanReadsTests(StubTestCase):
    def _world(self):
        w = self.world
        now = w.clock.now
        a = w.add_outpost("outpost_a")
        b = w.add_outpost("outpost_b")
        w.add_warehouse("wh_home", w.home, {"iron_ore": 40, "copper_ore": 5})
        w.add_warehouse("wh_a", a, {"iron_ore": 300, "copper_ore": 120, "salt": 7})
        w.add_warehouse("wh_b", b, {"copper_ore": 30})
        depot_a = w.add_drone_depot("depot_a", a)
        depot_a.output_buffer["iron_ore"] = 25
        w.add_drone_depot("depot_b", b)
        w.inventory.items["copper_ore"] = 11
        logistics_requests.set_requests("home", "smelter", {"iron_ore": (R(200, 80), 0), "copper_ore": (R(60), 0)}, now)
        logistics_requests.set_requests(
            "outpost_a", "fab", {"iron_ore": (R(100, 50), 0), "copper_ore": (R(50, 10), 0)}, now
        )
        logistics_requests.set_requests(
            "outpost_b", "fab", {"iron_ore": (R(90, 20), 0), "copper_ore": (R(40, 10), 30)}, now
        )
        logistics_requests.reserve_pickup("drone_2", "home", "iron_ore", 30, now, source_id="outpost_a")
        logistics_requests.reserve_pickup(
            "drone_3", "outpost_b", "copper_ore", 15, now, source_id="outpost_a", aboard=True
        )
        logistics_requests.reserve_pickup("drone_1", "outpost_b", "iron_ore", 9, now, source_id="outpost_a")
        return now, [w.home, a, b]

    def test_same_answers_as_per_call_reads(self):
        now, outposts = self._world()
        reads = logistics_requests.PlanReads(now)
        items = ["iron_ore", "copper_ore"]
        for outpost in outposts:
            for live in (True, False):
                self.assertEqual(
                    logistics_requests.outpost_deficits_tiered(outpost, now, live=live, reads=reads),
                    logistics_requests.outpost_deficits_tiered(outpost, now, live=live),
                )
            for vehicle in ("drone_1", None):
                for loader in (logistics_requests.LOADER_DRONE, logistics_requests.LOADER_VEHICLE):
                    self.assertEqual(
                        logistics_requests.outpost_free_tiers(
                            outpost, items, None, now, exclude_vehicle=vehicle, loader=loader, reads=reads
                        ),
                        logistics_requests.outpost_free_tiers(
                            outpost, items, None, now, exclude_vehicle=vehicle, loader=loader
                        ),
                    )
            # An item no request names is read on demand.
            self.assertEqual(
                logistics_requests.outpost_free_tiers(
                    outpost, ["salt"], None, now, loader=logistics_requests.LOADER_DRONE, reads=reads
                ),
                logistics_requests.outpost_free_tiers(
                    outpost, ["salt"], None, now, loader=logistics_requests.LOADER_DRONE
                ),
            )
            self.assertEqual(reads.in_flight(outpost.id), logistics_requests.in_flight(outpost.id, now))
            self.assertEqual(
                reads.reserved_from(outpost.id, "drone_1"),
                logistics_requests.reserved_from(outpost.id, now, exclude_vehicle="drone_1"),
            )
            buffer = {"iron_ore": 60, "copper_ore": 25}
            supply = {"iron_ore": 50, "copper_ore": 10}
            self.assertEqual(
                logistics_requests.fair_tier_caps(outpost.id, priority.STOCK, buffer, supply, now, reads=reads),
                logistics_requests.fair_tier_caps(outpost.id, priority.STOCK, buffer, supply, now),
            )

    def test_stock_read_once_per_outpost(self):
        now, outposts = self._world()
        warehouse = self.world.components["wh_a"]
        calls = []
        original = warehouse.stacks
        warehouse.stacks = lambda: calls.append(1) or original()
        reads = logistics_requests.PlanReads(now)
        a = outposts[1]
        logistics_requests.outpost_deficits_tiered(a, now, live=True, reads=reads)
        logistics_requests.outpost_free_tiers(
            a,
            ["iron_ore", "copper_ore"],
            None,
            now,
            exclude_vehicle="drone_1",
            loader=logistics_requests.LOADER_DRONE,
            reads=reads,
        )
        logistics_requests.outpost_free_tiers(
            a, ["copper_ore"], None, now, loader=logistics_requests.LOADER_DRONE, reads=reads
        )
        self.assertEqual(len(calls), 1)

    def test_pickups_snapshot_is_what_planning_sees(self):
        now, _outposts = self._world()
        seen = logistics_requests.pickups_snapshot()
        reads = logistics_requests.PlanReads(now, seen)
        # Reserved after `seen`: claim_pickups() trims for it, so planning must not count it too.
        logistics_requests.reserve_pickup("drone_4", "outpost_b", "iron_ore", 50, now, source_id="outpost_a")
        self.assertEqual(reads.in_flight("outpost_b"), {"iron_ore": 9, "copper_ore": 15})
        self.assertEqual(reads.reserved_from("outpost_a", "drone_1"), {"iron_ore": 30, "copper_ore": 15})


class _HaulerHost:
    name = "drone_1"

    def __init__(self, depots):
        self.log = TreeConsole(module="test_plan_reads")
        self._depots = depots
        self.haul_memory = drone_haul_plan.HaulMemory()

    def get_all_drone_depots(self):
        return list(self._depots)


def _hauler(depots):
    return _HaulerHost(depots)


class HaulerPlanReadsTests(StubTestCase):
    _world = PlanReadsTests._world

    def test_hauler_demand_and_sources_share_one_read(self):
        now, _outposts = self._world()
        hauler = _hauler(
            [
                {"id": "depot_a", "outpost_id": "outpost_a", "coords": (100.0, 0.0)},
                {"id": "depot_b", "outpost_id": "outpost_b", "coords": (0.0, 100.0)},
            ]
        )
        items = {"iron_ore", "copper_ore"}
        dests_alone = drone_haul_plan.haul_destinations(hauler, now)
        sources_alone = drone_haul_plan.outpost_sources(hauler, items, now)
        self.assertEqual(sorted(d["outpost_id"] for d in dests_alone), ["outpost_b"])
        self.assertEqual(sorted(s["id"] for s in sources_alone), ["outpost_a", "outpost_b"])

        calls = []
        for wh_id in ("wh_a", "wh_b"):
            warehouse = self.world.components[wh_id]
            warehouse.stacks = (lambda original: lambda: calls.append(1) or original())(warehouse.stacks)  # noqa: PLC3002 (binds this warehouse's original)
        reads = logistics_requests.PlanReads(now, logistics_requests.pickups_snapshot())
        layout = drone_haul_plan.depot_layout(hauler)
        self.assertEqual(drone_haul_plan.haul_destinations(hauler, now, reads, layout), dests_alone)
        self.assertEqual(drone_haul_plan.outpost_sources(hauler, items, now, reads, layout), sources_alone)
        self.assertEqual(len(calls), 2)  # outpost_b is destination and source: one stacks() per Warehouse, not 3


_DEPOTS = [
    {"id": "depot_a", "outpost_id": "outpost_a", "coords": (100.0, 0.0)},
    {"id": "depot_b", "outpost_id": "outpost_b", "coords": (0.0, 100.0)},
]
_ITEMS = ["iron_ore", "copper_ore"]


class _PlanningHost(_HaulerHost):
    """Enough of a DroneController for plan_haul_job() to read demand and stock, then stop at an empty hold."""

    engine = "electric"
    drone = SimpleNamespace(cargo=SimpleNamespace(capacity=lambda: 0, count=lambda: 0))


class SnapshotPlanTests(StubTestCase):
    _world = PlanReadsTests._world

    def _publish(self, now, outposts, tick=None):
        """Builds and stores a record of the stub world as it is now, stamped `tick` (default now)."""
        reads = logistics_requests.PlanReads(now)
        entries = {o.id: logistics_snapshot.build_entry(o, reads, _ITEMS) for o in outposts}
        self.assertTrue(logistics_snapshot.publish_snapshot(entries, now if tick is None else tick))

    def test_fresh_snapshot_matches_live_plan(self):
        now, outposts = self._world()
        hauler = _hauler(_DEPOTS)
        # plan_haul_job() releases the drone's own pickups before it reads anything.
        seen = logistics_requests.planning_snapshot(hauler.name)
        live_reads = logistics_requests.PlanReads(now, seen)
        layout = drone_haul_plan.depot_layout(hauler)
        live_dests = drone_haul_plan.haul_destinations(hauler, now, live_reads, layout)
        self._publish(now, outposts)

        reads = logistics_requests.PlanReads(now, seen)
        view = logistics_snapshot.view(reads, now, exclude_vehicle=hauler.name)
        assert view is not None
        with mock.patch.object(reads, "scan", side_effect=AssertionError("scan with a FRESH record")):
            dests = drone_haul_plan.haul_destinations(hauler, now, reads, layout, view=view)
            self.assertEqual(
                [(d["outpost_id"], d["tiers"]) for d in dests], [(d["outpost_id"], d["tiers"]) for d in live_dests]
            )
            self.assertTrue(dests)
            for tiers in (logistics_requests.TIERS, (priority.STOCK,)):
                live_sources = drone_haul_plan.outpost_sources(hauler, set(_ITEMS), now, live_reads, layout, tiers)
                sources = drone_haul_plan.outpost_sources(hauler, set(_ITEMS), now, reads, layout, tiers, view=view)
                self.assertEqual(
                    [(s["id"], s["tiers"], s["available"]) for s in sources],
                    [(s["id"], s["tiers"], s["available"]) for s in live_sources],
                )
                self.assertTrue(sources)

    def test_stale_snapshot_plans_live(self):
        now, outposts = self._world()
        self._publish(now, outposts, tick=now - logistics_snapshot.LOGISTICS_FRESH_TICKS - 1)
        hauler = _PlanningHost(_DEPOTS)
        scans = []
        original = logistics_requests.PlanReads.scan
        with (
            mock.patch.object(
                logistics_requests.PlanReads,
                "scan",
                autospec=True,
                side_effect=lambda reads, outpost: scans.append(outpost.id) or original(reads, outpost),
            ),
            mock.patch.object(hauler.log, "debug", wraps=hauler.log.debug) as debug,
        ):
            self.assertIsNone(drone_haul_plan.plan_haul_job(hauler, now))
        self.assertIn("outpost_b", scans)
        stale = [c.args[0] for c in debug.call_args_list if "snapshot" in c.args[0]]
        self.assertEqual(len(stale), 1, stale)
        self.assertIn("STALE", stale[0])

    def test_rivals_from_snapshot(self):
        now = self.world.clock.now
        reads = logistics_requests.PlanReads(now)
        # No request names the rival: only the record knows its deficit.
        record = {
            "v": logistics_snapshot.LOGISTICS_SNAPSHOT_VERSION,
            "tick": now,
            "outposts": {
                "outpost_d": {"deficits": {str(priority.STOCK): {"iron_ore": 60}}},
                "outpost_r": {
                    "deficits": {str(priority.STOCK): {"iron_ore": 40}, str(priority.NEED): {"iron_ore": 99}}
                },
            },
        }
        view = logistics_snapshot.TierView(record, reads)

        def dests():
            return [
                {"outpost_id": "outpost_d", "tiers": {priority.STOCK: {"iron_ore": 60}}, "deficits": {"iron_ore": 60}}
            ]

        sources = [{"kind": "drill", "id": "drill_1", "coords": (0.0, 0.0), "available": {"iron_ore": 50}}]
        live = dests()
        drone_haul_plan._cap_fair_tiers(live, sources, now, reads)
        self.assertEqual(live[0]["tiers"][priority.STOCK], {"iron_ore": 50})
        capped = dests()
        drone_haul_plan._cap_fair_tiers(capped, sources, now, reads, view=view)
        # 50 split 60:40 at STOCK (the NEED rival band is not a fair band): the larger claimant takes 50 - 50*40//100.
        self.assertEqual(capped[0]["tiers"][priority.STOCK], {"iron_ore": 30})
        self.assertEqual(capped[0]["deficits"], {"iron_ore": 30})


class _ClaimHost:
    name = "drone_9"

    def __init__(self):
        self.log = TreeConsole(module="test_plan_reads")

    def get_current_tick(self):
        return 0


class ClaimSnapshotPlanTests(StubTestCase):
    def _plan(self, dest, snapshot):
        now = self.world.clock.now
        plan = {
            "dest": {"outpost_id": dest.id, "outpost": dest, "deficits": {"iron_ore": 10}},
            "route": [({"kind": "drill", "id": "drill_1", "coords": (0.0, 0.0)}, [("iron_ore", 10)])],
            "units": 10,
            "wanted": 1,
            "seen": logistics_requests.pickups_snapshot(),
        }
        if snapshot:
            plan["snapshot"] = True
        return now, plan

    def test_claim_route_trims_snapshot_plan(self):
        w = self.world
        dest = w.add_outpost("outpost_d")
        logistics_requests.set_requests("outpost_d", "fab", {"iron_ore": (R(10), 0)}, w.clock.now)
        w.add_warehouse("wh_d", dest, {"iron_ore": 10})  # filled since the record was built
        job = job_haul.HaulJob(_ClaimHost())
        now, plan = self._plan(dest, snapshot=True)
        with mock.patch.object(logistics_requests, "claim_pickups", wraps=logistics_requests.claim_pickups) as claim:
            self.assertIsNone(job._claim_route(plan, now))
            claim.assert_not_called()
        self.assertEqual(logistics_requests.in_flight("outpost_d", now), {})

        # Without the flag the live deficit is not read: the claim goes through as before.
        now, plan = self._plan(dest, snapshot=False)
        route = job._claim_route(plan, now)
        assert route is not None
        self.assertEqual([(s["id"], loads) for s, loads in route], [("drill_1", [("iron_ore", 10)])])
        self.assertEqual(logistics_requests.in_flight("outpost_d", now), {"iron_ore": 10})

    def test_claim_route_keeps_live_deficit_of_snapshot_plan(self):
        w = self.world
        dest = w.add_outpost("outpost_d")
        logistics_requests.set_requests("outpost_d", "fab", {"iron_ore": (R(10), 0)}, w.clock.now)
        w.add_warehouse("wh_d", dest, {"iron_ore": 4})
        job = job_haul.HaulJob(_ClaimHost())
        now, plan = self._plan(dest, snapshot=True)
        route = job._claim_route(plan, now)
        assert route is not None
        self.assertEqual([(s["id"], loads) for s, loads in route], [("drill_1", [("iron_ore", 6)])])


if __name__ == "__main__":
    unittest.main()
