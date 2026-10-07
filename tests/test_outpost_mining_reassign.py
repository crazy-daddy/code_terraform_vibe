"""Resource markers go only to mining-designated outposts and never change owner."""
import unittest
from types import SimpleNamespace

from harness import StubTestCase, outpost_mining, archive


class FakeMarkers:
    def __init__(self, markers):
        self.markers = {m.id: m for m in markers}

    def list(self, prefix=""):
        return [m for m in self.markers.values() if m.id.startswith(prefix)]

    def get(self, marker_id):
        return self.markers.get(marker_id)

    def place(self, id, x, y, label, icon, color, note):
        self.markers[id] = SimpleNamespace(id=id, x=x, y=y, label=label, icon=icon, color=color, note=note)
        return SimpleNamespace(status="ok")


def marker(marker_id, note, x=0.0, y=0.0):
    return SimpleNamespace(id=marker_id, x=x, y=y, label=marker_id, icon="pin", color="#fff", note=note)


class AssignUnassignedTests(StubTestCase):
    def outpost(self, outpost_id, x, y):
        outpost = self.world.add_outpost(outpost_id)
        outpost.x, outpost.y = x, y

    def test_claims_unassigned_for_mining_outpost_only(self):
        self.outpost("outpost_mine", 100.0, 0.0)
        self.outpost("outpost_factory", 0.0, 0.0)
        archive.archive.set(outpost_mining.OUTPOST_ROLES_KEY, {"outpost_mine": ["mining"], "outpost_factory": "factory"})
        fake = FakeMarkers([marker("resource.free", ""), marker("resource.taken", "outpost_old"),
                            marker("resource.far", "", x=5000.0)])
        self.world.components["markers"] = fake
        self.assertEqual(outpost_mining.assign_unassigned_sites(range_m=200), 1)
        self.assertEqual(fake.markers["resource.free"].note, "outpost_mine")
        self.assertEqual(fake.markers["resource.taken"].note, "outpost_old")
        self.assertEqual(fake.markers["resource.far"].note, "")

    def test_no_mining_designation_leaves_sites_unassigned(self):
        self.outpost("outpost_factory", 0.0, 0.0)
        archive.archive.set(outpost_mining.OUTPOST_ROLES_KEY, {"outpost_factory": "factory"})
        fake = FakeMarkers([marker("resource.free", "")])
        self.world.components["markers"] = fake
        self.assertEqual(outpost_mining.assign_unassigned_sites(range_m=200), 0)
        self.assertEqual(fake.markers["resource.free"].note, "")

    def test_new_site_goes_to_closest_mining_outpost(self):
        self.outpost("outpost_near", 50.0, 0.0)
        self.outpost("outpost_mine", 150.0, 0.0)
        archive.archive.set(outpost_mining.OUTPOST_ROLES_KEY, {"outpost_near": "factory", "outpost_mine": "mining"})
        fake = FakeMarkers([])
        self.world.components["markers"] = fake
        site = SimpleNamespace(x=0.0, y=0.0, item_id="iron_ore", purity="rich")
        self.assertEqual(outpost_mining.auto_assign_new_site(site, range_m=200), "outpost_mine")
        self.assertEqual(fake.markers[outpost_mining.resource_marker_id(0.0, 0.0)].label, "Iron Ore - Rich")


if __name__ == "__main__":
    unittest.main()
