"""Autoplay planning flow: planner_loop.run_planner() over a medium sample world.

The real run loop (founding, building, map read, power, fluid and extractor
passes) runs a few passes against the shared fakes, with outposts spread
over the map and surveyed sites next to them. Asserted from the outside, on
the blueprints the passes queued: every extractor sits on a surveyed site of
its kind, no two extractor footprints overlap, none overlaps an outpost
footprint, and no pipe run crosses an outpost or extractor footprint
between its two end pieces.
"""

import builtins
import unittest

import harness  # first: installs game builtins and lib paths

# isort: split
import autoplay_roles as roles
import grid_geom as g
import planner_loop
import sample_world
from construction_plan import EXTRACTOR_KITS, POWER_LINE_KIND, POWER_TILES_KEY
from fluid_plan import PIPE_ITEMS
from power_plan import POWER_ITEM
from test_autoplay_extractor import Blueprints
from test_autoplay_power import Job, Journal, Result, Site

PASSES = 4
# Remote outposts of the medium world: (x, y) and role.
SPREAD = {"outpost_1": ((1000.0, 0.0), "factory"), "outpost_2": ((2000.0, 600.0), "power")}
SITE_KINDS = {
    "water_pump": "water",
    "oil_pump": "oil",
    "thermal_cap": "thermal",
    "mining_drill": "mineral",
    "mining_drill_industrial": "mineral",
    "mining_drill_heavy": "mineral",
}


class _Stop(Exception):
    """Ends run_planner()'s endless loop after PASSES passes."""


class _MapBlueprints(Blueprints):
    """Extractor/pipe fake whose power lines stay as pending jobs (one per
    piece, like plan_pipe) and whose map has no power piece to deconstruct."""

    def plan_power_line(self, x1, y1, x2, y2):
        result = super().plan_power_line(x1, y1, x2, y2)
        sx = (x2 > x1) - (x2 < x1)
        sy = (y2 > y1) - (y2 < y1)
        for i, jid in enumerate(result.blueprint_ids):
            mid = (x1 + sx * (i + 0.5) * g.TILE_M, y1 + sy * (i + 0.5) * g.TILE_M)
            self.pending.append(Job(jid, POWER_LINE_KIND, None, mid[0], mid[1]))
        return result

    def mark_deconstruct(self, x, y, layer="auto", target_id=""):
        return Result("nothing_here")


class PlannerFlowTest(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.sample = sample_world.build_sample_world("medium")
        self.world = self.sample.world
        world = self.world
        world.home.x, world.home.y = 0.0, 0.0
        for outpost in self.sample.remotes:
            (outpost.x, outpost.y), _role = SPREAD[outpost.id]
        world.notebook.set(roles.ROLES_KEY, {oid: role for oid, (_xy, role) in SPREAD.items()})
        # Built pumps/caps (a machine id) get pipes; the rest get extractors.
        self.sites = [
            Site("water", 205, 5, "wp1", site_id="well_home"),
            Site("water", 1105, 205, site_id="well_factory"),
            Site("oil", 1405, 205, site_id="oil_far"),
            Site("thermal", 2205, 605, site_id="vent_a"),
            Site("thermal", 1805, 405, "tc1", site_id="vent_b"),
            Site("mineral", 1205, 5, site_id="ore_site", item="ore_0", hardness=1),
        ]
        world.services["journal"] = Journal(self.sites)
        # The one-off map survey already ran and found no power line.
        world.notebook.set(POWER_TILES_KEY, {"surveyed": world.clock.now, "rows": {}, "dirty": []})
        self.blueprints = _MapBlueprints()
        world.services["construction_blueprint"] = self.blueprints
        for item in (*EXTRACTOR_KITS.values(), *PIPE_ITEMS, POWER_ITEM):
            world.inventory.add(item, 500)
        setattr(builtins, "list_pipes", list)
        self.passes = 0

        def sleep(seconds):
            world.clock.now += int(seconds * 10)
            if seconds in (planner_loop.PASS_SLEEP_S, planner_loop.WATCH_SLEEP_S):
                self.passes += 1
                if self.passes >= PASSES:
                    raise _Stop

        builtins.sleep = sleep  # type: ignore[attr-defined]

    def tearDown(self):
        delattr(builtins, "list_pipes")
        super().tearDown()

    def _outpost_tiles(self):
        tiles = set()
        for outpost in [self.world.home, *self.sample.remotes]:
            tiles |= set(g.outpost_tiles(outpost.x, outpost.y))
        return tiles

    def test_passes_queue_extractors_on_sites_without_overlaps(self):
        with self.assertRaises(_Stop):
            planner_loop.run_planner()
        self.assertEqual(self.passes, PASSES)
        calls = self.blueprints.calls
        structures = [c for c in calls if c[0] == "structure"]
        self.assertTrue(structures, "no extractor queued")
        self.assertTrue(any(c[0] == "pipe" for c in calls), "no pipe queued")

        by_xy = {(site.x, site.y): site for site in self.sites}
        outposts = self._outpost_tiles()
        taken: set = set()
        for _, kind, x, y in structures:
            site = by_xy.get((x, y))
            self.assertIsNotNone(site, f"{kind} at ({x}, {y}) is no surveyed site")
            assert site is not None
            self.assertEqual(site.kind(), SITE_KINDS[kind], f"{kind} on a {site.kind()} site")
            tiles = set(g.extractor_tiles(x, y))
            self.assertFalse(tiles & outposts, f"{kind} at ({x}, {y}) overlaps an outpost")
            self.assertFalse(tiles & taken, f"{kind} at ({x}, {y}) overlaps another extractor")
            taken |= tiles

        blocked = outposts | taken
        runs = [c[2:] for c in calls if c[0] == "pipe"] + [c[1:] for c in calls if c[0] == "power"]
        self.assertTrue(any(c[0] == "power" for c in calls), "no power line queued")
        for x1, y1, x2, y2 in runs:
            pieces = g.run_tiles(g.tile_at(x1, y1), g.tile_at(x2, y2))
            inner = set(pieces[1:-1])
            self.assertFalse(inner & blocked, f"run ({x1}, {y1})-({x2}, {y2}) crosses a footprint")


if __name__ == "__main__":
    unittest.main()
