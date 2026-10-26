"""script_parking._members(): the grid member index built in atomic _member_rows() slices."""

import unittest
from types import SimpleNamespace
from unittest import mock

import harness  # sets up the lib import path; keep first
import script_parking

StubTestCase = harness.StubTestCase
ScriptParking = script_parking.ScriptParking


def _member(member_id, type_id, powered=True):
    return SimpleNamespace(id=member_id, type_id=type_id, powered=powered)


def _grid(anchor_id, members):
    return SimpleNamespace(anchor_id=anchor_id, members=members)


GRIDS = [
    _grid(
        "battery_1",
        [
            _member("solar_1", "solar_panel"),
            _member("", "solar_panel"),  # no id: skipped
            _member("pump_1", "water_pump", False),
            _member("solar_2", "solar_panel"),
            _member("smelter_1", "smelter", 0),  # falsy powered: stored as False
        ],
    ),
    _grid("battery_2", [_member("solar_3", "solar_panel", False), _member("pump_2", "water_pump")]),
    _grid("battery_3", []),
]

MEMBERS = {
    "solar_1": ("battery_1", "solar_panel", True),
    "pump_1": ("battery_1", "water_pump", False),
    "solar_2": ("battery_1", "solar_panel", True),
    "smelter_1": ("battery_1", "smelter", False),
    "solar_3": ("battery_2", "solar_panel", False),
    "pump_2": ("battery_2", "water_pump", True),
}
BY_TYPE = {
    "solar_panel": ["solar_1", "solar_2", "solar_3"],
    "water_pump": ["pump_1", "pump_2"],
    "smelter": ["smelter_1"],
}
DARK = ["pump_1", "smelter_1", "solar_3"]


class MemberIndexTests(StubTestCase):
    def _index(self):
        parking = SimpleNamespace()
        members = ScriptParking._members(parking, GRIDS)
        return members, parking._by_type, parking._dark

    def test_index_matches_at_every_chunk_size(self):
        for chunk in (1, 2, 3, 150):
            with self.subTest(chunk=chunk), mock.patch.object(script_parking, "MEMBER_CHUNK", chunk):
                members, by_type, dark = self._index()
                self.assertEqual(members, MEMBERS)
                self.assertEqual(list(members), list(MEMBERS))
                self.assertEqual(by_type, BY_TYPE)
                self.assertEqual(dark, DARK)

    def test_powered_is_a_bool(self):
        members, _, _ = self._index()
        self.assertIs(members["smelter_1"][2], False)


if __name__ == "__main__":
    unittest.main()
