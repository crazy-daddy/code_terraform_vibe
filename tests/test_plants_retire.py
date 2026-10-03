"""Stub tests for the Plants finish line (8_planting/lib/plant_terraformer.py:
no loading or requests once running batches reach 5,000,000 km², eject and end
at "complete") and the Automation's undeploy pass (8_planting/lib/plants_retire.py)."""
import unittest

from harness import StubTestCase
from game_stubs import Result

import plant_terraformer
import plants_retire


class FinishLineMathTests(unittest.TestCase):
    def test_forage_to_go_nets_running_batches(self):
        # Phase 5: 3 Forage per km². 3,000 km² left, 2,000 km² running.
        self.assertEqual(plant_terraformer.forage_to_go(5, 3000, 2000), 3000)
        self.assertEqual(plant_terraformer.forage_to_go(5, 3000, 3000), 0)
        self.assertEqual(plant_terraformer.forage_to_go(5, 3000, 5000), 0)
        self.assertIsNone(plant_terraformer.forage_to_go(0, 3000, 0))

    def test_cap_batch_cuts_forage_only(self):
        reqs = {"forage": 6600, "salt": 14, "growth_accelerant": 1}
        capped = plant_terraformer.PlantTerraformerController.cap_batch(reqs, 1200.5)
        self.assertEqual(capped, {"forage": 1201, "salt": 14, "growth_accelerant": 1})
        self.assertIs(plant_terraformer.PlantTerraformerController.cap_batch(reqs, 9000), reqs)
        self.assertIs(plant_terraformer.PlantTerraformerController.cap_batch(reqs, None), reqs)

    def test_request_batches_shrink_near_the_end(self):
        batches = plant_terraformer.PlantTerraformerController.request_batches
        self.assertEqual(batches(6600, None), plant_terraformer.SUPPORT_REQUEST_BATCHES)
        self.assertEqual(batches(6600, 1e9), plant_terraformer.SUPPORT_REQUEST_BATCHES)
        self.assertEqual(batches(6600, 7000), 2)
        self.assertEqual(batches(6600, 100), 1)


class _Outpost:
    id = "outpost_home"
    is_home = True


class _Input:
    def __init__(self, held):
        self.held = dict(held)
        self.ejects = []

    def stacks(self):
        return [type("Stack", (), {"id": k, "count": v})() for k, v in self.held.items() if v > 0]

    def count(self):
        return sum(self.held.values())

    def eject(self, target, item_id, count):
        self.ejects.append((target, item_id, count))
        self.held[item_id] = self.held.get(item_id, 0) - count
        return Result("ok", moved=count)


class _Terraformer:
    type_id = "plant_terraformer"

    def __init__(self, machine_id="plant_terraformer_1", status="running", held=None, phase=5, remaining=3000.0,
                 running=True, progress=0.5, km2_rate=1000.0):
        self.id = machine_id
        self.outpost = _Outpost()
        self.input = _Input(held or {})
        self._status = status
        self._phase = phase
        self._remaining = remaining
        self._running = running
        self._progress = progress
        self._km2_rate = km2_rate
        self.enabled = True

    def status(self):
        return self._status

    def phase(self):
        return self._phase

    def remaining(self):
        return self._remaining

    def is_running(self):
        return self._running

    def get_progress(self):
        return self._progress

    def km2_rate(self):
        return self._km2_rate

    def required_inputs(self):
        return ["forage", "water", "salt", "fertilizer", "growth_accelerant"]

    def batch_requirements(self):
        return {"forage": 6600, "water": 330, "salt": 14, "fertilizer_potency": 27, "growth_accelerant": 1}

    def tier(self):
        return 2

    def batch_size(self):
        return 6600

    def is_enabled(self):
        return self.enabled

    def set_enabled(self, enabled):
        self.enabled = enabled

    def fertilizer_potency(self, item_id):
        return {"fertilizer_mk3": 50, "fertilizer_mk2": 30, "fertilizer": 10}[item_id]


class _FeedRecordingController(plant_terraformer.PlantTerraformerController):
    """Records each feed() call instead of loading, with no water to manage."""

    def __init__(self, machine):
        super().__init__(machine)
        self.fed = []

    def feed(self, *args, **kwargs):
        self.fed.append(args)
        return {}

    def ensure_water(self, *args, **kwargs):
        return None

    def water_level(self):
        return 0.0


class TerraformerFinishTests(StubTestCase):
    def controller(self, machine):
        return _FeedRecordingController(machine)

    def test_running_batch_reaching_the_end_stops_loading(self):
        # 1,000 km²/h x 3 h x half left = 1,500 km² still to come; another
        # machine's fresh batch adds 1,500 more: 3,000 km² left is covered.
        self.world.notebook.set(plant_terraformer.STATUS_KEY, {
            "plant_terraformer_2": {"status": "running", "in_flight": True, "batch_km2": 3000.0, "progress": 0.5, "tick": 1000},
        })
        machine = _Terraformer()
        ctrl = self.controller(machine)
        published = []
        ctrl.publish_fabricator_orders = lambda need, backlog, **kwargs: published.append((need, backlog))
        self.assertFalse(ctrl.step())
        self.assertEqual(ctrl.fed, [])
        self.assertEqual(published, [({}, {})])
        self.assertTrue(machine.enabled)

    def test_short_of_the_end_keeps_loading(self):
        machine = _Terraformer(remaining=30000.0)
        ctrl = self.controller(machine)
        ctrl.publish_requests = lambda *args, **kwargs: None
        ctrl.publish_fabricator_orders = lambda *args, **kwargs: None
        ctrl.step()
        self.assertEqual(len(ctrl.fed), 1)
        # 30,000 - 1,500 km² left = 85,500 Forage: a full batch.
        self.assertEqual(ctrl.fed[0][0]["forage"], 6600)

    def test_stale_other_batch_does_not_count(self):
        self.world.notebook.set(plant_terraformer.STATUS_KEY, {
            "plant_terraformer_2": {"status": "running", "in_flight": True, "batch_km2": 3000.0, "progress": 0.5, "tick": -10000},
        })
        ctrl = self.controller(_Terraformer())
        ctrl.publish_requests = lambda *args, **kwargs: None
        ctrl.publish_fabricator_orders = lambda *args, **kwargs: None
        ctrl.step()
        # 3,000 - 1,500 km² left = 4,500 Forage: next batch capped.
        self.assertEqual(ctrl.fed[0][0]["forage"], 4500)

    def test_complete_ejects_holders_then_ends(self):
        machine = _Terraformer(status="complete", held={"forage": 500, "salt": 3}, phase=6, remaining=0.0,
                               running=False, progress=0.0, km2_rate=0.0)
        ctrl = self.controller(machine)
        self.assertTrue(ctrl.step())
        self.assertEqual({e[1] for e in machine.input.ejects}, {"forage", "salt"})
        self.assertFalse(machine.enabled)
        self.assertEqual(ctrl.fed, [])


class PlantsRetirementTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self._discover = plants_retire.fluid_routing.discover_network_buildings
        self.machines = []
        self.computer, self.run_control = self.world.computer, self.world.run_control
        plants_retire.fluid_routing.discover_network_buildings = lambda type_id, resolve=True: [(m, "outpost_home") for m in self.machines]

    def tearDown(self):
        plants_retire.fluid_routing.discover_network_buildings = self._discover
        super().tearDown()

    def place(self, *machines):
        self.machines = list(machines)
        self.world.components.update({m.id: m for m in machines})

    def retire(self):
        return plants_retire.PlantsRetirement(self.computer, self.run_control)

    def publish(self, statuses):
        self.world.notebook.set(plant_terraformer.STATUS_KEY, {i: {"status": s, "tick": 0} for i, s in statuses.items()})

    def test_idle_before_completion(self):
        self.place(_Terraformer())
        self.publish({"plant_terraformer_1": "running"})
        self.assertEqual(self.retire().step(0), plants_retire.IDLE_SUMMARY)
        self.assertEqual(self.computer.calls, [])

    def test_empty_complete_machine_undeployed_and_pruned(self):
        self.place(_Terraformer(status="complete"))
        self.publish({"plant_terraformer_1": "complete"})
        summary = self.retire().step(0)
        self.assertEqual(self.computer.calls, [("undeploy", "plant_terraformer_1")])
        self.assertIn("undeployed 1", summary)
        self.assertEqual(self.world.notebook.get(plant_terraformer.STATUS_KEY), {})

    def test_full_holders_restart_script_instead_of_undeploy(self):
        self.place(_Terraformer(status="complete", held={"forage": 10}))
        self.publish({"plant_terraformer_1": "complete"})
        summary = self.retire().step(0)
        self.assertEqual(self.computer.calls, [])
        self.assertEqual(self.run_control.running, {"plant_terraformer_1"})
        self.assertIn("emptying plant_terraformer_1", summary)

    def test_still_running_machine_left_alone_and_refusal_retried(self):
        self.place(_Terraformer(status="complete"), _Terraformer("plant_terraformer_2", status="running"))
        self.publish({"plant_terraformer_1": "complete", "plant_terraformer_2": "running"})
        self.computer.forced_status = "inventory_full"
        retire = self.retire()
        summary = retire.step(0)
        self.assertEqual(self.computer.calls, [("undeploy", "plant_terraformer_1")])
        self.assertIn("finishing plant_terraformer_2", summary)
        self.computer.forced_status = None
        retire.step(0)
        self.assertEqual(self.computer.calls, [("undeploy", "plant_terraformer_1")] * 2)


if __name__ == "__main__":
    unittest.main()
