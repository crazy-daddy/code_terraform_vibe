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


if __name__ == "__main__":
    unittest.main()
