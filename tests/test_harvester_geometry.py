import unittest

from harness import StubTestCase
import field_layout
from harvester_planting import GEOMETRY_KEY, HarvesterPlantingMixin


class StoredChunkCountTests(StubTestCase):
    def test_count_is_stored_and_reused(self):
        mixin = HarvesterPlantingMixin()
        expected = field_layout.full_chunk_count("crowncap")
        self.assertEqual(mixin.stored_chunk_count("crowncap"), expected)
        stored = self.world.notebook.data[GEOMETRY_KEY]
        self.assertEqual(stored["chunk_count"]["crowncap"], expected)
        stored["chunk_count"]["crowncap"] = 99  # a stored value is used as-is while the source matches
        self.assertEqual(mixin.stored_chunk_count("crowncap"), 99)

    def test_changed_layout_constants_invalidate_the_stored_count(self):
        mixin = HarvesterPlantingMixin()
        self.world.notebook.data[GEOMETRY_KEY] = {"source": "old layout", "chunk_count": {"crowncap": 99}}
        self.assertEqual(mixin.stored_chunk_count("crowncap"), field_layout.full_chunk_count("crowncap"))
        self.assertEqual(self.world.notebook.data[GEOMETRY_KEY]["source"], field_layout.geometry_source())


if __name__ == "__main__":
    unittest.main()
