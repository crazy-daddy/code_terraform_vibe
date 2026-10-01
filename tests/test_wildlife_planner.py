import unittest

import harness
import atomic
import wildlife_common as wc
import wildlife_planner as wp
from wildlife_data import SPECIES, BONUS_TREES, FEED_PER_CRAFT, FORAGE_PER_CRAFT


def snap(habitats=2, statuses=None, insight=0.0, schedule=(), targets=(), prev_assign=None, feed_stock=None,
         recipes=None, recipe_inputs=None, parked=(), populations=None, mk2_packs=0, cataloged=None):
    ids = ["habitat_%d" % (i + 1) for i in range(habitats)]
    return {
        "tick": 1000,
        "habitat_ids": ids,
        "statuses": statuses or {},
        "parked": set(parked),
        "cataloged": set(SPECIES) if cataloged is None else set(cataloged),
        "recipes": set(wc.recipe_of(s) for s in SPECIES) if recipes is None else set(recipes),
        "recipe_inputs": recipe_inputs or {},
        "insight": insight,
        "schedule": tuple(schedule),
        "targets": list(targets),
        "prev_assign": prev_assign or {},
        "feed_stock": feed_stock or {},
        "form_stock": {},
        "populations": populations or {},
        "mk2_packs": mk2_packs,
    }


def established(species, pop=1000, rate=10.0, feed_level=50.0, bought=None, tier=1, parked=""):
    return {"species": species, "target": "", "established": True, "rearing": False, "pop": pop, "rate": rate,
            "feed_level": feed_level, "bought": bought or {}, "tier": tier, "parked": parked, "feed_item": wc.feed_item_of(species)}


class BootstrapTests(harness.StubTestCase):
    def test_bootstrap_assigns_both_commons_without_adaptation(self):
        plan = wp.build_plan(snap(habitats=3))
        assigned = {e["species"]: e for e in plan["assign"].values()}
        self.assertEqual(set(assigned), {"magmatic_annelid", "salt_tortoise"})
        self.assertFalse(any(e["adapt_first"] for e in assigned.values()))
        self.assertEqual(plan["buy"], {})
        self.assertEqual(plan["assign"]["habitat_1"]["species"], "magmatic_annelid")

    def test_reservation_demand_for_new_revival(self):
        plan = wp.build_plan(snap(habitats=2))
        row = plan["feed_demand"][wc.feed_item_of("magmatic_annelid")]
        self.assertEqual(row[1], wc.PRIO_RESERVE * wc.PRIO_RANK_SCALE)
        self.assertEqual(row[0], 2 + wc.REARING_FEED_EXTRA)
        self.assertGreater(plan["forage_reserve"], 0)


class ScheduleTests(harness.StubTestCase):
    def base_statuses(self):
        return {"habitat_1": established("magmatic_annelid"), "habitat_2": established("salt_tortoise")}

    def test_adaptation_queued_before_revive(self):
        plan = wp.build_plan(snap(habitats=3, statuses=self.base_statuses(), insight=1.2, schedule=[("revive", "spire_drake")]))
        self.assertEqual(plan["assign"]["habitat_3"], {"species": "spire_drake", "adapt_first": True, "tick": 1000})
        self.assertEqual(plan["buy"], {"habitat_3": "adaptation"})

    def test_revive_waits_for_insight_and_holds_later_steps(self):
        plan = wp.build_plan(snap(habitats=4, statuses=self.base_statuses(), insight=0.5,
                                  schedule=[("revive", "spire_drake"), ("revive_raw", "glacial_wyrm")]))
        self.assertNotIn("habitat_3", plan["assign"])
        self.assertNotIn("habitat_4", plan["assign"])
        self.assertEqual(plan["progress"]["waiting"][0], ["revive", "spire_drake"])

    def test_breakthrough_holds_insight_until_source_has_10000(self):
        statuses = self.base_statuses()
        plan = wp.build_plan(snap(habitats=3, statuses=statuses, insight=6, populations={"salt_tortoise": 5000},
                                  schedule=[("break", "salt_tortoise"), ("revive", "spire_drake")]))
        self.assertEqual(plan["buy"], {})
        self.assertEqual(plan["assign"], {})
        plan = wp.build_plan(snap(habitats=3, statuses=statuses, insight=6, populations={"salt_tortoise": 12000},
                                  schedule=[("break", "salt_tortoise"), ("revive", "spire_drake")]))
        self.assertEqual(plan["buy"], {"habitat_2": "breakthrough", "habitat_3": "adaptation"})

    def test_blocked_steps_skipped_with_reason(self):
        plan = wp.build_plan(snap(habitats=3, statuses=self.base_statuses(), insight=2,
                                  recipes=[wc.recipe_of(s) for s in SPECIES if s != "spire_drake"],
                                  schedule=[("revive", "spire_drake"), ("revive", "hive_sentinel")]))
        self.assertIn([["revive", "spire_drake"], "no_recipe"], plan["progress"]["skipped"])
        self.assertEqual(plan["assign"]["habitat_3"]["species"], "hive_sentinel")
        self.assertEqual(plan["readiness"]["missing_recipes"], ["spire_drake"])

    def test_no_free_habitat_skips_revive_but_runs_adapt(self):
        plan = wp.build_plan(snap(habitats=2, statuses=self.base_statuses(), insight=1,
                                  schedule=[("revive", "spire_drake"), ("adapt", "salt_tortoise")]))
        self.assertIn([["revive", "spire_drake"], "no_habitat"], plan["progress"]["skipped"])
        self.assertEqual(plan["buy"], {"habitat_2": "adaptation"})

    def test_bought_node_is_not_bought_again(self):
        statuses = self.base_statuses()
        statuses["habitat_2"]["bought"] = {"adaptation": True}
        plan = wp.build_plan(snap(habitats=2, statuses=statuses, insight=1, schedule=[("adapt", "salt_tortoise")]))
        self.assertEqual(plan["buy"], {})

    def test_pending_adaptation_stays_owed(self):
        statuses = self.base_statuses()
        statuses["habitat_3"] = {"species": "", "target": "spire_drake", "established": False, "bought": {"adaptation": False}}
        prev = {"habitat_3": {"species": "spire_drake", "adapt_first": True, "tick": 1}}
        plan = wp.build_plan(snap(habitats=3, statuses=statuses, insight=1, prev_assign=prev, schedule=[("adapt", "salt_tortoise")]))
        self.assertEqual(plan["buy"], {"habitat_3": "adaptation"})
        self.assertEqual(plan["progress"]["waiting"][0], ["adapt", "salt_tortoise"])

    def test_operator_targets_reorder_revivals(self):
        plan = wp.build_plan(snap(habitats=1, insight=1, targets=["salt_tortoise"]))
        self.assertEqual(plan["assign"]["habitat_1"]["species"], "salt_tortoise")


class FeedDemandTests(harness.StubTestCase):
    def test_slowest_growing_colony_first(self):
        statuses = {
            "habitat_1": established("magmatic_annelid", pop=100000, rate=150.0),
            "habitat_2": established("spire_drake", pop=1000, rate=5.0),
        }
        plan = wp.build_plan(snap(habitats=2, statuses=statuses))
        fast = plan["feed_demand"][wc.feed_item_of("magmatic_annelid")]
        slow = plan["feed_demand"][wc.feed_item_of("spire_drake")]
        self.assertLess(slow[1], fast[1])
        self.assertGreaterEqual(fast[1], wc.PRIO_GROWING * wc.PRIO_RANK_SCALE)

    def test_target_is_buffer_hours_of_use_and_stock_counts(self):
        statuses = {"habitat_1": established("magmatic_annelid", rate=100.0, feed_level=50.0)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        target = plan["feed_demand"][wc.feed_item_of("magmatic_annelid")][0]
        self.assertEqual(target, int(wc.FEED_BUFFER_H * 100.0 * 0.1 + 0.999))
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, feed_stock={wc.feed_item_of("magmatic_annelid"): target}))
        self.assertNotIn(wc.feed_item_of("magmatic_annelid"), plan["feed_demand"])
        self.assertEqual(plan["forage_reserve"], 0)

    def test_adaptation_feed_reduction_lowers_target(self):
        bought = {"adaptation": True}
        statuses = {"habitat_1": established("salt_tortoise", rate=100.0, bought=bought)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        target = plan["feed_demand"][wc.feed_item_of("salt_tortoise")][0]
        self.assertEqual(target, int(wc.FEED_BUFFER_H * 100.0 * 0.1 * 0.4 + 0.999))

    def test_capped_colony_needs_no_buffer(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=175000, rate=0.0)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        self.assertNotIn(wc.feed_item_of("salt_tortoise"), plan["feed_demand"])

    def test_forage_reserve_covers_crafts_plus_one(self):
        statuses = {"habitat_1": established("magmatic_annelid", rate=10.0, feed_level=50.0)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        need = plan["feed_demand"][wc.feed_item_of("magmatic_annelid")][2]
        crafts = (need + FEED_PER_CRAFT - 1) // FEED_PER_CRAFT
        self.assertEqual(plan["forage_reserve"], (crafts + 1) * FORAGE_PER_CRAFT)

    def test_form_targets_from_recipe_inputs(self):
        statuses = {"habitat_1": established("magmatic_annelid", rate=100.0)}
        inputs = {wc.recipe_of("magmatic_annelid"): {"forage": 100, "lava_algae": 1, "cave_moss": 1}}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, recipe_inputs=inputs))
        self.assertIn("lava_algae", plan["form_targets"])
        self.assertNotIn("forage", plan["form_targets"])
        self.assertGreaterEqual(plan["form_targets"]["lava_algae"], wc.FORM_REQUEST_MIN_CRAFTS)
        self.assertLessEqual(plan["form_targets"]["lava_algae"], wc.FORM_REQUEST_CAP)


class WakeAlertTests(harness.StubTestCase):
    def test_wakes_parked_no_feed_once_feed_in_stock(self):
        item = wc.feed_item_of("salt_tortoise")
        statuses = {"habitat_1": established("salt_tortoise", feed_level=0.0, parked=wc.PARK_NO_FEED)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"]))
        self.assertEqual(plan["wakes"], [])
        self.assertEqual(plan["alerts"][wc.PARK_NO_FEED], ["habitat_1"])
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"], feed_stock={item: wc.FEED_TOPUP_TARGET}))
        self.assertEqual(plan["wakes"], [("habitat_1", "feed in stock")])

    def test_capped_wakes_on_mk2_pack_and_alerts(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=175000, rate=0.0, parked=wc.PARK_CAPPED)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"]))
        self.assertEqual(plan["wakes"], [])
        self.assertIn("capped", wp.summary_line(plan))
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"], mk2_packs=1))
        self.assertEqual(plan["wakes"], [("habitat_1", "Mk II pack in Inventory")])

    def test_wakes_parked_empty_habitat_on_assignment(self):
        statuses = {"habitat_1": {"species": "", "target": "", "parked": wc.PARK_EMPTY}}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"]))
        self.assertEqual(plan["wakes"], [("habitat_1", "assigned magmatic_annelid")])

    def test_idle_summary(self):
        plan = wp.build_plan(snap(habitats=1, statuses={"habitat_1": established("salt_tortoise")}))
        self.assertEqual(wp.summary_line(plan), wp.IDLE_SUMMARY)


class AtomicTests(harness.StubTestCase):
    def test_build_plan_runs_as_one_callback(self):
        statuses = {"habitat_%d" % (i + 1): established(s, rate=50.0) for i, s in enumerate(sorted(SPECIES))}
        s = snap(habitats=16, statuses=statuses, insight=10, schedule=wp.schedule_for(16))
        self.assertEqual(atomic.run_atomic(wp.build_plan, s), wp.build_plan(s))


class SnapshotTests(harness.StubTestCase):
    def test_no_habitat_is_a_noop(self):
        self.assertEqual(wp.plan(self.world.components.get("clock")), wp.IDLE_SUMMARY)
        self.assertIsNone(self.world.notebook.data.get(wc.PLAN_KEY))


if __name__ == "__main__":
    unittest.main()
