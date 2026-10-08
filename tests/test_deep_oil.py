"""Tests for lib/deep_oil.py (Seismic deep-oil prospecting state) and the Pioneer Seismic upgrade gate."""
import unittest

from harness import StubTestCase
from game_stubs import Journal, MountSlot, Site, SonarModule
import deep_oil
import pioneer_upgrade
import vehicle_survey
from tree_console import TreeConsole


def formation(n, status="unscanned"):
    return Site("inert", 100.0 * n, 0.0, site_id=f"geological_anomaly_{n}", seismic_status=status)


def confirmed_well(n):
    return Site("oil", 100.0 * n, 0.0, site_id=f"geological_anomaly_{n}")


class ProspectTests(unittest.TestCase):
    def test_all_unscanned_share_the_three_reservoirs(self):
        state = deep_oil.prospect([formation(n) for n in range(1, 7)])
        self.assertEqual(len(state["unscanned"]), 6)
        self.assertEqual(state["remaining"], 3)
        self.assertAlmostEqual(state["odds"], 0.5)
        self.assertTrue(deep_oil.open_work(state))

    def test_potential_and_found_lower_the_odds(self):
        sites = [formation(1, "potential"), confirmed_well(2), formation(3, "dry"), formation(4), formation(5),
                 Site("oil", 9, 9, site_id="oil_well_1")]
        state = deep_oil.prospect(sites)
        self.assertEqual((state["found"], len(state["potential"]), state["dry"]), (1, 1, 1))
        self.assertEqual(state["remaining"], 1)
        self.assertAlmostEqual(state["odds"], 0.5)
        self.assertEqual([s.id for s in deep_oil.targets(state)],
                         ["geological_anomaly_1", "geological_anomaly_4", "geological_anomaly_5"])

    def test_unscanned_formations_drop_once_every_reservoir_is_known(self):
        sites = [confirmed_well(1), confirmed_well(2), formation(3, "potential"), formation(4), formation(5, "dry")]
        state = deep_oil.prospect(sites)
        self.assertEqual(state["remaining"], 0)
        self.assertEqual(state["odds"], 0.0)
        self.assertEqual([s.id for s in deep_oil.targets(state)], ["geological_anomaly_3"])

    def test_no_work_when_all_settled(self):
        state = deep_oil.prospect([confirmed_well(1), confirmed_well(2), confirmed_well(3), formation(4)])
        self.assertFalse(deep_oil.open_work(state))
        self.assertFalse(deep_oil.open_work(deep_oil.prospect([])))


class Scout(pioneer_upgrade.PioneerUpgradeMixin):
    def __init__(self, vehicle):
        self.name = vehicle.id
        self.vehicle = vehicle
        self.log = TreeConsole()


class SeismicGateTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.world.research.unlocked.update(deep_oil.SEISMIC_RESEARCH_IDS)
        self.world.services["journal"] = Journal(discovered=[formation(1), formation(2)])

    def scout(self, pioneer_id, sonar_id):
        pioneer = self.world.add_pioneer(pioneer_id, slots=[MountSlot(0, "universal", "nav_module"),
                                                            MountSlot(1, "universal", sonar_id)])
        return Scout(pioneer)

    def test_deep_scout_may_step_to_seismic(self):
        self.assertEqual(self.scout("pioneer_1", "sonar_module_deep")._sonar_ladder(), pioneer_upgrade.SONAR_TIERS)

    def test_lower_tiers_keep_the_default_ladder(self):
        ladder = self.scout("pioneer_1", "sonar_module_wide")._sonar_ladder()
        self.assertEqual(ladder, pioneer_upgrade.SONAR_UPGRADE_TIERS)

    def test_only_one_seismic_scout(self):
        self.scout("pioneer_1", "sonar_module_seismic")
        ladder = self.scout("pioneer_2", "sonar_module_deep")._sonar_ladder()
        self.assertEqual(ladder, pioneer_upgrade.SONAR_UPGRADE_TIERS)

    def test_needs_both_researches(self):
        self.world.research.unlocked.discard("research_advanced_oil_extraction")
        ladder = self.scout("pioneer_1", "sonar_module_deep")._sonar_ladder()
        self.assertEqual(ladder, pioneer_upgrade.SONAR_UPGRADE_TIERS)

    def test_no_step_without_open_work(self):
        self.world.services["journal"] = Journal(discovered=[confirmed_well(1), confirmed_well(2), confirmed_well(3)])
        ladder = self.scout("pioneer_1", "sonar_module_deep")._sonar_ladder()
        self.assertEqual(ladder, pioneer_upgrade.SONAR_UPGRADE_TIERS)


class Surveyor(vehicle_survey.VehicleSurveyMixin):
    def __init__(self, vehicle):
        self.name = vehicle.id
        self.vehicle = vehicle
        self.log = TreeConsole()
        self.assigned_slot_coords = (0.0, 0.0)

    def distance_between(self, p1, p2):
        return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5


class SurveyTargetTests(StubTestCase):
    def surveyor(self, tier):
        pioneer = self.world.add_pioneer("pioneer_1")
        setattr(pioneer, "sonar", SonarModule(tier, 4, 280.0))
        return Surveyor(pioneer)

    def test_ordinary_sonar_never_routes_to_formations(self):
        self.world.services["journal"] = Journal(discovered=[formation(1)])
        self.assertEqual(self.surveyor("deep").deep_oil_targets(), [])

    def test_seismic_targets_nearest_first(self):
        self.world.services["journal"] = Journal(discovered=[formation(3), formation(1, "dry"), formation(2, "potential")])
        targets = self.surveyor("seismic").deep_oil_targets()
        self.assertEqual([s.id for s in targets], ["geological_anomaly_2", "geological_anomaly_3"])

    def test_survey_everything_not_known_dry(self):
        surveyor = self.surveyor("seismic")
        self.assertTrue(surveyor._needs_deep_oil_survey(formation(1)))
        self.assertTrue(surveyor._needs_deep_oil_survey(formation(1, "potential")))
        self.assertFalse(surveyor._needs_deep_oil_survey(formation(1, "dry")))
        self.assertFalse(surveyor._needs_deep_oil_survey(Site("mineral", site_id="m1")))


if __name__ == "__main__":
    unittest.main()
