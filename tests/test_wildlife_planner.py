import unittest

import harness
import wildlife_common as wc
import wildlife_planner as wp
from wildlife_data import SPECIES, BONUS_TREES, FEED_PER_CRAFT, FORAGE_PER_CRAFT


def snap(habitats=2, statuses=None, insight=0.0, schedule=(), targets=(), prev_assign=None, feed_stock=None,
         recipes=None, recipe_inputs=None, parked=(), populations=None, mk2_packs=0, cataloged=None,
         fluid_stock=None, prev_supply=None, prev_ration=None, tick=1000):
    ids = ["habitat_%d" % (i + 1) for i in range(habitats)]
    return {
        "tick": tick,
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
        "prev_ration": prev_ration or {},
        "prev_supply": prev_supply or {},
        "fluid_stock": fluid_stock or {},
        "feed_stock": feed_stock or {},
        "form_stock": {},
        "populations": populations or {},
        "mk2_packs": mk2_packs,
    }


def established(species, pop=1000, rate=10.0, feed_level=50.0, bought=None, tier=1, parked="", gas=None, liquid=None):
    return {"species": species, "target": "", "established": True, "rearing": False, "pop": pop, "rate": rate,
            "feed_level": feed_level, "bought": bought or {}, "tier": tier, "parked": parked, "feed_item": wc.feed_item_of(species),
            "gas": gas, "liquid": liquid}


def gas_row(fluid, level=450.0, flow=0.0, band=(250.0, 650.0)):
    """Status medium entry: [held, level, band, required, flow]."""
    return [fluid if level > 0 else "", level, list(band), fluid, flow]


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
        plan = wp.build_plan(snap(habitats=2, statuses=statuses, feed_stock={wc.feed_item_of("magmatic_annelid"): 20}))
        fast = plan["feed_demand"][wc.feed_item_of("magmatic_annelid")]
        slow = plan["feed_demand"][wc.feed_item_of("spire_drake")]
        self.assertLess(slow[1], fast[1])
        self.assertGreaterEqual(fast[1], wc.PRIO_GROWING * wc.PRIO_RANK_SCALE)

    def test_empty_bin_is_urgent_before_buffers(self):
        statuses = {
            "habitat_1": established("salt_tortoise", pop=20000, rate=100.0, feed_level=0.0),
            "habitat_2": established("spire_drake", pop=1000, rate=5.0, gas=gas_row("sulfur_gas")),
        }
        plan = wp.build_plan(snap(habitats=2, statuses=statuses))
        starving = plan["feed_demand"][wc.feed_item_of("salt_tortoise")]
        buffered = plan["feed_demand"][wc.feed_item_of("spire_drake")]
        self.assertEqual(starving[1] // wc.PRIO_RANK_SCALE, wc.PRIO_URGENT)
        self.assertEqual(buffered[1] // wc.PRIO_RANK_SCALE, wc.PRIO_FLUID_HELD)
        self.assertEqual(starving[0], wc.FEED_TOPUP_TARGET)

    def test_urgent_ranks_emptiest_bin_first(self):
        statuses = {
            "habitat_1": established("spire_drake", pop=1000, rate=5.0, feed_level=20.0),
            "habitat_2": established("salt_tortoise", pop=20000, rate=100.0, feed_level=0.0),
        }
        plan = wp.build_plan(snap(habitats=2, statuses=statuses))
        empty = plan["feed_demand"][wc.feed_item_of("salt_tortoise")][1]
        low = plan["feed_demand"][wc.feed_item_of("spire_drake")][1]
        self.assertEqual(low // wc.PRIO_RANK_SCALE, wc.PRIO_URGENT)
        self.assertLess(empty, low)

    def test_covered_colony_returns_to_buffer_class(self):
        item = wc.feed_item_of("salt_tortoise")
        statuses = {"habitat_1": established("salt_tortoise", pop=20000, rate=100.0, feed_level=0.0)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, feed_stock={item: wc.FEED_TOPUP_TARGET}))
        row = plan["feed_demand"][item]
        self.assertEqual(row[1] // wc.PRIO_RANK_SCALE, wc.PRIO_GROWING)
        self.assertGreater(row[0], wc.FEED_TOPUP_TARGET)

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

    def test_starved_colony_keeps_feed_demand(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=800, rate=0.0, feed_level=0.0)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        row = plan["feed_demand"][wc.feed_item_of("salt_tortoise")]
        self.assertGreaterEqual(row[0], wc.FEED_TOPUP_TARGET)

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


class FeedPriorityTests(harness.StubTestCase):
    def test_fluid_holding_colony_before_rearing_and_feed_only(self):
        statuses = {
            "habitat_1": established("salt_tortoise", pop=30000, rate=100.0, gas=gas_row("swamp_gas")),
            "habitat_2": established("spire_drake", pop=1000, rate=5.0),
            "habitat_3": {"species": "hive_sentinel", "target": "", "established": False, "rearing": True, "feed_level": 5.0},
        }
        plan = wp.build_plan(snap(habitats=3, statuses=statuses))
        held = plan["feed_demand"][wc.feed_item_of("salt_tortoise")][1]
        rearing = plan["feed_demand"][wc.feed_item_of("hive_sentinel")][1]
        feed_only = plan["feed_demand"][wc.feed_item_of("spire_drake")][1]
        self.assertLess(held, rearing)
        self.assertLess(rearing, feed_only)
        self.assertEqual(held // wc.PRIO_RANK_SCALE, wc.PRIO_FLUID_HELD)

    def test_empty_buffer_is_feed_only(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=30000, rate=100.0, gas=gas_row("swamp_gas", level=0.0))}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses))
        self.assertEqual(plan["feed_demand"][wc.feed_item_of("salt_tortoise")][1] // wc.PRIO_RANK_SCALE, wc.PRIO_GROWING)

    def test_rank_uses_model_rate_not_live_rate(self):
        colonies = {"hollow_choir": "habitat_1", "salt_tortoise": "habitat_2"}
        statuses = {"habitat_1": established("hollow_choir", pop=1000, rate=3.0),
                    "habitat_2": established("salt_tortoise", pop=30000, rate=100.0)}
        before = wp._colony_model(colonies, statuses, set())
        statuses["habitat_1"]["rate"] = 0.0
        statuses["habitat_2"]["rate"] = 0.0
        self.assertEqual(wp._colony_model(colonies, statuses, set()), before)
        self.assertGreater(before["habitat_1"][0], before["habitat_2"][0])


class FluidRationTests(harness.StubTestCase):
    """Three swamp_gas colonies, slowest first: hollow_choir (rare), mycelial_husk (uncommon), salt_tortoise (common)."""

    def statuses(self, slow_level=450.0):
        return {
            "habitat_1": established("salt_tortoise", pop=30000, rate=100.0, gas=gas_row("swamp_gas", flow=0.4)),
            "habitat_2": established("mycelial_husk", pop=5000, rate=20.0, gas=gas_row("swamp_gas", flow=0.4)),
            "habitat_3": established("hollow_choir", pop=1000, rate=3.0, gas=gas_row("swamp_gas", level=slow_level, flow=0.4)),
        }

    def needs(self, statuses):
        colonies = {e["species"]: hid for hid, e in statuses.items()}
        model = wp._colony_model(colonies, statuses, set())
        return {row[0]: row[1] for row in wp._consumers(colonies, statuses, model)["swamp_gas"]}

    def plan(self, statuses, inflow, stock=0.0, prev_ration=None):
        # Steady state: same stock as last pass, so measured inflow = what the Habitats drew (3 x 0.4).
        prev = {"swamp_gas": [stock, inflow, 750]}
        return wp.build_plan(snap(habitats=3, statuses=statuses, fluid_stock={"swamp_gas": stock}, prev_supply=prev,
                                  prev_ration=prev_ration, tick=1000))

    def test_first_pass_grants_all_and_records_supply(self):
        plan = wp.build_plan(snap(habitats=3, statuses=self.statuses(), fluid_stock={"swamp_gas": 10.0}))
        self.assertEqual(plan["fluid_ration"], {})
        self.assertEqual(plan["fluid_supply"]["swamp_gas"][:3], [10.0, None, 1000])

    def test_ample_supply_grants_all(self):
        plan = self.plan(self.statuses(), inflow=1.2, stock=500.0)
        self.assertEqual(plan["fluid_ration"], {})
        self.assertEqual(plan["alerts"][wc.PARK_RATIONED], [])

    def test_short_supply_denies_fastest_first(self):
        statuses = self.statuses()
        needs = self.needs(statuses)
        self.assertLess(needs["habitat_3"] + needs["habitat_2"], 1.2)
        self.assertGreater(sum(needs.values()), 1.2)
        plan = self.plan(statuses, inflow=1.2)
        self.assertEqual(plan["fluid_ration"], {"habitat_1": ["swamp_gas"]})
        self.assertIn("1 fluid-rationed", wp.summary_line(plan))

    def test_walk_stops_at_slowest_that_does_not_fit(self):
        # The slowest colony needs a full fill: stock banks up for it, nobody faster gets gas.
        plan = self.plan(self.statuses(slow_level=0.0), inflow=1.2)
        self.assertEqual(set(plan["fluid_ration"]), {"habitat_1", "habitat_2", "habitat_3"})

    def test_hysteresis_keeps_a_denied_colony_denied_at_the_edge(self):
        statuses = self.statuses()
        total = sum(self.needs(statuses).values())
        # Budget just above the total need, but below it once the hysteresis margin is taken off.
        inflow = total / (1.0 - wc.RATION_HYSTERESIS / 2)
        for hid in statuses:
            statuses[hid]["gas"][wc.MEDIUM_FLOW] = inflow / 3
        plan = self.plan(statuses, inflow=inflow)
        self.assertEqual(plan["fluid_ration"], {})
        plan = self.plan(statuses, inflow=inflow, prev_ration={"habitat_1": ["swamp_gas"]})
        self.assertEqual(plan["fluid_ration"], {"habitat_1": ["swamp_gas"]})

    def test_capped_colony_is_not_a_consumer(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=175000, rate=0.0, gas=gas_row("swamp_gas"))}
        plan = self.plan(statuses, inflow=0.0)
        self.assertEqual(plan["fluid_ration"], {})
        self.assertNotIn("swamp_gas", plan["fluid_supply"])

    def test_inflow_is_smoothed_stock_change_plus_draw(self):
        self.assertIsNone(wp._inflow(100.0, 2.0, None, 1000))
        self.assertEqual(wp._inflow(100.0, 2.0, [50.0, None, 750], 1000), 52.0)
        self.assertAlmostEqual(wp._inflow(100.0, 2.0, [50.0, 1.0, 750], 1000) or 0.0, 1.0 + wc.RATION_INFLOW_ALPHA * 51.0)


class WakeAlertTests(harness.StubTestCase):
    def test_wakes_rationed_habitat_once_granted(self):
        statuses = {"habitat_1": established("salt_tortoise", pop=30000, gas=gas_row("swamp_gas", level=100.0), parked=wc.PARK_RATIONED)}
        plan = wp.build_plan(snap(habitats=1, statuses=statuses, parked=["habitat_1"], fluid_stock={"swamp_gas": 500.0},
                                  prev_supply={"swamp_gas": [500.0, 5.0, 750]}, prev_ration={"habitat_1": ["swamp_gas"]}))
        self.assertEqual(plan["fluid_ration"], {})
        self.assertEqual(plan["wakes"], [("habitat_1", "fluid granted")])

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


class SnapshotTests(harness.StubTestCase):
    def test_no_habitat_is_a_noop(self):
        self.assertEqual(wp.plan(self.world.components.get("clock")), wp.IDLE_SUMMARY)
        self.assertIsNone(self.world.notebook.data.get(wc.PLAN_KEY))


class _Tank:
    def __init__(self, tank_id, fluid, level):
        self.id, self._fluid, self._level = tank_id, fluid, level

    def fluid(self):
        return self._fluid

    def level(self):
        return self._level


class FluidStockTests(harness.StubTestCase):
    def setUp(self):
        super().setUp()
        self.tanks = {
            "gas": [_Tank("gas_tank_1", "ammonia", 100.0), _Tank("gas_tank_2", "steam", 50.0),
                    _Tank("gas_tank_3", "ammonia", 30.0), _Tank("gas_tank_4", "", 0.0)],
            "liquid": [_Tank("tank_1", "brine", 7.0)],
        }
        self.walks = []
        self._orig = (wp.fluid_routing.discover_network_buildings, wp.fluid_routing.get_tank_assignments)

        def discover(type_ids, resolve=True, fluid_id=None):
            medium = next(m for m, ids in wc.TANK_TYPE_IDS.items() if tuple(ids) == tuple(type_ids))
            self.walks.append((medium, fluid_id))
            return [(t, "outpost_home") for t in self.tanks[medium]]

        wp.fluid_routing.discover_network_buildings = discover
        wp.fluid_routing.get_tank_assignments = lambda: {"gas_tank_3": wp.fluid_routing.RETIRING_ASSIGNMENT}

    def tearDown(self):
        wp.fluid_routing.discover_network_buildings, wp.fluid_routing.get_tank_assignments = self._orig
        super().tearDown()

    def test_one_walk_per_medium_counts_latched_eligible_tanks(self):
        statuses = {
            "habitat_1": established("salt_tortoise", gas=["", 0, [], "ammonia", 0], liquid=["", 0, [], "brine", 0]),
            "habitat_2": established("veil_mantle", gas=["", 0, [], "steam", 0]),
        }
        self.assertEqual(wp._fluid_stock(statuses), {"ammonia": 100.0, "steam": 50.0, "brine": 7.0})
        self.assertEqual(sorted(self.walks), [("gas", None), ("liquid", None)])

    def test_no_required_fluid_walks_nothing(self):
        self.assertEqual(wp._fluid_stock({"habitat_1": established("salt_tortoise")}), {})
        self.assertEqual(self.walks, [])


if __name__ == "__main__":
    unittest.main()
