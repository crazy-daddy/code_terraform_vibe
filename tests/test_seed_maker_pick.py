import unittest
from unittest import mock

import harness  # noqa: F401  (puts the script libs on sys.path)
import seed_maker

FORMS = [f"f{n:02d}" for n in range(12)]
TICK = 10_000


def _reference_pick(ranked, tried, tick):
    """The pick as one unchunked scan in (k, i, j) order."""
    for k in range(2, len(ranked)):
        for i in range(k - 1):
            for j in range(i + 1, k):
                key = seed_maker.combo_key(ranked[i], ranked[j], ranked[k])
                entry = tried.get(key)
                if entry is None or (entry is not True and not seed_maker._claim_is_live(entry, tick)):
                    return key, [ranked[i], ranked[j], ranked[k]]
    return None


def _chunked_pick(ranked, tried, tick):
    state = {"ranked": ranked, "tried": tried, "tick": tick, "pos": (2, 0, 1), "found": None}
    calls = 0
    while not seed_maker._pick_chunk(state):
        calls += 1
        assert calls < 10_000, "pick never finished"
    return state["found"]


def _all_keys(ranked):
    n = len(ranked)
    return [
        seed_maker.combo_key(ranked[i], ranked[j], ranked[k])
        for k in range(2, n)
        for i in range(k - 1)
        for j in range(i + 1, k)
    ]


class PickChunkTest(unittest.TestCase):
    """_pick_chunk() resumed across chunks finds the same triple as one full scan."""

    def _check(self, ranked, tried):
        expected = _reference_pick(ranked, tried, TICK)
        for chunk in (1, 2, 3, 7, 150):
            with self.subTest(chunk=chunk), mock.patch.object(seed_maker, "PICK_CHUNK", chunk):
                self.assertEqual(_chunked_pick(ranked, tried, TICK), expected)

    def test_open_triple_at_every_scan_position(self):
        keys = _all_keys(FORMS)
        for pos in (0, 1, 2, 9, 54, len(keys) // 2, len(keys) - 1):
            tried = {key: True for key in keys[:pos]}
            with self.subTest(pos=pos):
                self._check(FORMS, tried)
                self.assertEqual(_chunked_pick(FORMS, tried, TICK)[0], keys[pos])

    def test_live_claims_skipped_and_stale_claims_open(self):
        keys = _all_keys(FORMS)
        tried = {key: True for key in keys}
        live = {"by": "seed_maker_2", "tick": TICK - 10, "stage": "loading"}
        stale = {"by": "seed_maker_2", "tick": TICK - seed_maker.SEED_CLAIM_STALE_TICKS, "stage": "loading"}
        tried[keys[40]] = live
        tried[keys[100]] = stale
        self._check(FORMS, tried)
        self.assertEqual(_chunked_pick(FORMS, tried, TICK)[0], keys[100])

    def test_none_when_every_triple_tried(self):
        tried = dict.fromkeys(_all_keys(FORMS), True)
        self._check(FORMS, tried)
        self.assertIsNone(_chunked_pick(FORMS, tried, TICK))

    def test_fewer_than_three_forms(self):
        for ranked in ([], ["fa"], ["fa", "fb"]):
            with self.subTest(n=len(ranked)):
                self.assertIsNone(_chunked_pick(ranked, {}, TICK))


if __name__ == "__main__":
    unittest.main()
