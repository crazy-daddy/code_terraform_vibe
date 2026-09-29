"""reevaluate_unassigned_near_outpost() claims only markers that name no outpost yet."""
import unittest
from types import SimpleNamespace

from harness import StubTestCase, outpost_mining


class FakeMarkers:
    def __init__(self, markers):
        self.markers = {m.id: m for m in markers}

    def list(self, prefix=""):
        return [m for m in self.markers.values() if m.id.startswith(prefix)]

    def place(self, id, x, y, label, icon, color, note):
        self.markers[id] = SimpleNamespace(id=id, x=x, y=y, label=label, icon=icon, color=color, note=note)
        return SimpleNamespace(status="ok")


def marker(marker_id, note, x=0.0, y=0.0):
    return SimpleNamespace(id=marker_id, x=x, y=y, label=marker_id, icon="pin", color="#fff", note=note)


class ReevaluateUnassignedTests(StubTestCase):
    def test_claims_unassigned_and_leaves_assigned_alone(self):
        w = self.world
        new = w.add_outpost("outpost_new")
        new.x, new.y = 0.0, 0.0
        fake = FakeMarkers([marker("resource.free", ""), marker("resource.taken", "outpost_old"),
                            marker("resource.far", "", x=5000.0)])
        w.components["markers"] = fake
        self.assertEqual(outpost_mining.reevaluate_unassigned_near_outpost("outpost_new", range_m=200), 1)
        self.assertEqual(fake.markers["resource.free"].note, "outpost_new")
        self.assertEqual(fake.markers["resource.taken"].note, "outpost_old")
        self.assertEqual(fake.markers["resource.far"].note, "")


if __name__ == "__main__":
    unittest.main()
