import unittest

import harness
from archive import ArchiveClient, archive
from game_stubs import Notebook


class GetDictTests(harness.StubTestCase):
    def test_get_dict_missing_reads_empty(self):
        self.assertEqual(archive.get_dict("t.k"), {})

    def test_get_dict_non_dict_reads_empty(self):
        for stored in ([1, 2], "x", 0):
            archive.set("t.k", stored)
            self.assertEqual(archive.get_dict("t.k"), {}, stored)

    def test_get_dict_returns_stored_dict(self):
        archive.set("t.k", {"a": 1})
        self.assertEqual(archive.get_dict("t.k"), {"a": 1})

    def test_get_dict_adds_no_copy(self):
        # The object the notebook returns, like get(): a caller that mutates
        # it must copy. The stub notebook deep-copies, so use one that does not.
        stored = {"a": 1}

        class _SharingNotebook(Notebook):
            def get(self, key, default=None):
                return stored

        client = ArchiveClient(_SharingNotebook())
        self.assertIs(client.get_dict("t.k"), stored)
        self.assertIs(client.get_dict("t.k"), client.get("t.k"))

    def test_get_dict_without_notebook_reads_empty(self):
        client = ArchiveClient()
        client.notebook = None
        self.assertEqual(client.get_dict("t.k"), {})


class MutateTests(harness.StubTestCase):
    def test_mutate_edits_in_place_and_writes_back(self):
        archive.set("t.k", {"a": 1})
        self.assertTrue(archive.mutate("t.k", lambda state: state.update(b=2)))
        self.assertEqual(archive.get("t.k"), {"a": 1, "b": 2})

    def test_mutate_coerces_non_dict(self):
        for stored in ([1, 2], "x", 0):
            archive.set("t.k", stored)
            self.assertTrue(archive.mutate("t.k", lambda state: state.update(b=2)), stored)
            self.assertEqual(archive.get("t.k"), {"b": 2}, stored)

    def test_mutate_missing_key_starts_empty(self):
        self.assertTrue(archive.mutate("t.k", lambda state: state.update(b=2)))
        self.assertEqual(archive.get("t.k"), {"b": 2})

    def test_mutate_returns_false_without_notebook(self):
        client = ArchiveClient()
        client.notebook = None
        self.assertFalse(client.mutate("t.k", lambda state: state.update(b=2)))

    def test_pop_entries_drops_listed_keeps_rest(self):
        archive.set("t.k", {"a": 1, "b": 2, "c": 3})
        self.assertTrue(archive.pop_entries("t.k", ["a", "c", "zz"]))
        self.assertEqual(archive.get("t.k"), {"b": 2})

    def test_pop_entries_non_dict_writes_empty(self):
        archive.set("t.k", [1, 2])
        self.assertTrue(archive.pop_entries("t.k", ["a"]))
        self.assertEqual(archive.get("t.k"), {})


class DictEntryTests(harness.StubTestCase):
    def test_dict_entry_walks_path(self):
        archive.set("t.k", {"drones": {"d1": {"x": 1}}})
        self.assertEqual(archive.dict_entry("t.k", "drones", "d1"), {"x": 1})

    def test_dict_entry_missing_reads_none(self):
        archive.set("t.k", {"drones": {}})
        self.assertIsNone(archive.dict_entry("t.k", "drones", "d1"))
        self.assertIsNone(archive.dict_entry("t.missing", "a"))

    def test_dict_entry_non_dict_leaf_reads_none(self):
        archive.set("t.k", {"drones": {"d1": [1], "d2": "s"}, "flat": 3})
        self.assertIsNone(archive.dict_entry("t.k", "drones", "d1"))
        self.assertIsNone(archive.dict_entry("t.k", "drones", "d2"))
        self.assertIsNone(archive.dict_entry("t.k", "flat", "x"))

    def test_dict_entry_no_path_reads_whole_dict(self):
        archive.set("t.k", {"a": 1})
        self.assertEqual(archive.dict_entry("t.k"), {"a": 1})


if __name__ == "__main__":
    unittest.main()
