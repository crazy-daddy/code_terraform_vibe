"""lib/production_demand_record.py: the shared demand record's freshness, lease and parsing."""

import unittest

import demand_publisher
import production_demand_record as record
from harness import StubTestCase


def body(network=None, plan=None, **parts):
    return record.new_record(plan or {}, network or {"gas_pipe_segment": [[600, 10]]}, **parts)


class FreshnessTests(StubTestCase):
    def test_missing_without_a_record(self):
        self.assertEqual(record.read_record(now=1000), (None, record.MISSING))
        self.assertEqual(record.record_tick(), 0)

    def test_fresh_then_stale_then_missing_by_age(self):
        w = self.world
        self.assertTrue(record.publish_record(body(), now=w.clock.now))
        self.assertEqual(record.record_tick(), w.clock.now)
        stored, state = record.read_record(now=w.clock.now + record.DEMAND_FRESH_TICKS)
        self.assertEqual(state, record.FRESH)
        self.assertEqual(record.network_entry(stored), {"gas_pipe_segment": [[600, 10]]})
        _stored, state = record.read_record(now=w.clock.now + record.DEMAND_FRESH_TICKS + 1)
        self.assertEqual(state, record.STALE)
        self.assertEqual(
            record.read_record(now=w.clock.now + record.DEMAND_MAX_STALE_TICKS + 1), (None, record.MISSING)
        )

    def test_another_version_or_site_plan_is_missing(self):
        w = self.world
        record.publish_record(body(plan={"gas_pipe_segment": ["outpost_2"]}), now=w.clock.now)
        self.assertEqual(record.read_record(now=w.clock.now, plan={"gas_pipe_segment": ["outpost_2"]})[1], record.FRESH)
        self.assertEqual(record.read_record(now=w.clock.now, plan={})[1], record.MISSING)
        self.assertEqual(record.read_record(now=w.clock.now)[1], record.FRESH)  # no plan check
        w.notebook.data[record.DEMAND_KEY]["v"] = record.DEMAND_VERSION + 1
        self.assertEqual(record.read_record(now=w.clock.now), (None, record.MISSING))

    def test_publish_without_a_clock_tick_is_refused(self):
        self.assertFalse(record.publish_record(body(), now=0))
        self.assertEqual(record.read_record(now=1000), (None, record.MISSING))

    def test_a_stale_record_is_still_usable(self):
        record.publish_record(body(), now=1000)
        self.assertEqual(record.read_record(now=1000 + record.DEMAND_MAX_STALE_TICKS)[1], record.STALE)
        self.assertEqual(record.read_record(now=1000 + record.DEMAND_MAX_STALE_TICKS + 1), (None, record.MISSING))

    def test_a_record_outlives_the_gap_to_the_next_publish(self):
        # A record is stamped when its round starts; the next round starts DEMAND_BACKSTOP_TICKS
        # after that stamp and a round plus its start lag took up to longest_round on save 0839
        # (stamp to next publish 3,032-3,389). Shorter, and every Smelter polling in the gap walks.
        longest_round, margin = 1600, 1000
        self.assertGreaterEqual(
            record.DEMAND_MAX_STALE_TICKS, demand_publisher.DEMAND_BACKSTOP_TICKS + longest_round + margin
        )
        record.publish_record(body(), now=1000)
        self.assertEqual(record.read_record(now=1000 + 3389)[1], record.STALE)

    def test_a_newer_record_is_not_overwritten_by_an_older_publish(self):
        record.publish_record(body({"a": [[600, 5]]}), now=2000)
        record.publish_record(body({"b": [[600, 7]]}), now=1500)
        stored, _state = record.read_record(now=2000)
        self.assertEqual(record.network_entry(stored), {"a": [[600, 5]]})
        record.publish_record(body({"c": [[600, 9]]}), now=2100)
        stored, _state = record.read_record(now=2100)
        self.assertEqual(record.network_entry(stored), {"c": [[600, 9]]})


class ParsingTests(StubTestCase):
    def test_site_and_smelter_entries_round_trip(self):
        sites = {
            "outpost_2": (
                {"gas_pipe_segment": [[600, 4]], "circuit_panel": [[600, 2], [100, 6]]},
                {"iron_ingot": [8, 600]},
                {"gas_pipe_segment": 3},
            )
        }
        smelter_sites = {"outpost_2": ({"iron_ingot": [[600, 16]]}, {"iron_ingot": 5})}
        record.publish_record(
            body(sites=sites, smelter_network={"iron_ingot": [[600, 20]]}, smelter_sites=smelter_sites), now=1000
        )
        stored, _state = record.read_record(now=1000)
        targets, ship, have = record.site_entry(stored, "outpost_2")
        self.assertEqual(targets, {"gas_pipe_segment": [[600, 4]], "circuit_panel": [[600, 2], [100, 6]]})
        self.assertEqual(ship, {"iron_ingot": [8, 600]})
        self.assertEqual(have, {"gas_pipe_segment": 3})
        self.assertEqual(record.site_entry(stored, "home"), ({}, {}, {}))
        self.assertEqual(record.smelter_entry(stored), ({"iron_ingot": [[600, 20]]}, {}))
        self.assertEqual(record.smelter_entry(stored, "outpost_2"), ({"iron_ingot": [[600, 16]]}, {"iron_ingot": 5}))
        self.assertEqual(record.smelter_entry(stored, "home"), ({}, {}))

    def test_malformed_values_are_dropped(self):
        record.publish_record(body({"a": [[600, 5]]}), now=1000)
        stored = self.world.notebook.data[record.DEMAND_KEY]
        stored["network"] = {"a": [[600, 5], "junk"], "b": "junk", "c": [[600, 0]]}
        stored["sites"] = {
            "home": {
                "targets": {"a": [[600, 2]]},
                "ship": {"a": [0, 600], "b": [3, 600], "c": "junk"},
                "have": {"a": 2, "b": "junk"},
            }
        }
        stored["smelter"] = "junk"
        read, _state = record.read_record(now=1000)
        self.assertEqual(record.network_entry(read), {"a": [[600, 5]]})
        self.assertEqual(record.site_entry(read, "home"), ({"a": [[600, 2]]}, {"b": [3, 600]}, {"a": 2}))
        self.assertEqual(record.smelter_entry(read), ({}, {}))

    def test_new_record_copies_its_ladders(self):
        network = {"a": [[600, 5]]}
        built = record.new_record({}, network)
        network["a"][0][1] = 99
        self.assertEqual(built["network"], {"a": [[600, 5]]})


class SignatureTests(StubTestCase):
    def test_changes_on_demand_writers_and_blueprint_jobs(self):
        w = self.world
        base = record.demand_signature({})
        w.notebook.set("fabricator.manual_orders", {"drone_small": 2})
        with_manual = record.demand_signature({})
        self.assertNotEqual(with_manual, base)
        self.assertEqual(with_manual[("fabricator", "fabricator.manual_orders", "drone_small")], 2)
        w.add_blueprint("job_1", "thermal_cap_kit", 1)
        with_job = record.demand_signature({})
        self.assertIn(("fabricator", "blueprint", "job_1"), with_job)
        self.assertIn(("smelter", "blueprint", "job_1"), with_job)
        with_dock = record.demand_signature({"supply_dock_1": "order_1"})
        self.assertIn(("smelter", "dock_plan", "dock order order_1"), with_dock)
        self.assertEqual(record.demand_signature({"supply_dock_1": None}), with_job)


if __name__ == "__main__":
    unittest.main()
