"""supply_dock.plan_signature(): what makes the automation panel replan the docks."""
import unittest

from harness import StubTestCase, supply_dock


class PlanSignatureTests(StubTestCase):
    def test_changes_on_new_or_finished_orders_and_docks_only(self):
        w = self.world
        w.add_supply_dock("supply_dock_1", w.home)
        order = w.add_order("order_1", {"iron_ingot": 10})
        base = supply_dock.plan_signature()
        order.shipped["iron_ingot"] = 4  # shipping progress: no replan
        self.assertEqual(supply_dock.plan_signature(), base)
        order.status = "completed"
        self.assertNotEqual(supply_dock.plan_signature(), base)
        order.status = "active"
        w.add_order("order_2", {"glass": 5})
        self.assertNotEqual(supply_dock.plan_signature(), base)
        after_order = supply_dock.plan_signature()
        w.add_supply_dock("supply_dock_2", w.home)
        self.assertNotEqual(supply_dock.plan_signature(), after_order)


if __name__ == "__main__":
    unittest.main()
