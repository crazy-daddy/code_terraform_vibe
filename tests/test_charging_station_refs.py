"""lib/charging.py all_station_refs: one read of charging_stations.all_stations(), the own station as fallback."""

from types import SimpleNamespace
from unittest import mock

import charging
from harness import StubTestCase


def _controller(name="station_1", x=10.0, y=20.0):
    return SimpleNamespace(name=name, station=SimpleNamespace(outpost=SimpleNamespace(x=x, y=y)))


class AllStationRefsTests(StubTestCase):
    def refs(self, controller):
        return charging.ChargingStationController.all_station_refs(controller)  # pyright: ignore[reportArgumentType]

    def test_reads_all_stations_as_id_and_coords(self):
        found = [{"id": "station_1", "coords": (1.0, 2.0), "outpost": "o", "component": object()}]
        with mock.patch.object(charging, "all_stations", return_value=found):
            self.assertEqual(self.refs(_controller()), [{"id": "station_1", "coords": (1.0, 2.0)}])

    def test_all_stations_raise_falls_back_to_own_station(self):
        with mock.patch.object(charging, "all_stations", side_effect=RuntimeError("scan offline")):
            self.assertEqual(self.refs(_controller()), [{"id": "station_1", "coords": (10.0, 20.0)}])
