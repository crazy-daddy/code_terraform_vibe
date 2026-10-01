import unittest

from harness import StubTestCase
import weather_signals as weather


def _checksum(data):
    return sum(ord(c) for c in data)


class _Copy:
    def __init__(self, event_id, number, total, dx, dy, expires=50.0, data=None, checksum=None):
        self.event_id = event_id
        self.number = number
        self.total = total
        self.data = data if data is not None else f"{event_id}|{number}|{total}|{dx}|{dy}"
        self.checksum = checksum if checksum is not None else _checksum(self.data)
        self.expires_at_gh = expires


class _Receiver:
    def __init__(self):
        self.copies = []

    def transmissions(self):
        return list(self.copies)


class _Board:
    def __init__(self):
        self.resolved = []

    def resolve(self, event_id, info):
        self.resolved.append((event_id, info))


class _Station:
    type_id = "weather_station"

    def __init__(self, station_id, outpost):
        self.id = station_id
        self.outpost = outpost
        self.signal_receiver = _Receiver()
        self.signal_board = _Board()


def _message(event_id, steps, expires=50.0):
    """Valid copies for a movement sequence; the first step is always (0, 0)."""
    total = len(steps)
    return [_Copy(event_id, n + 1, total, dx, dy, expires) for n, (dx, dy) in enumerate(steps)]


class ParseTests(unittest.TestCase):
    def test_valid_record_from_save(self):
        self.assertEqual(weather.parse_record("storm_1469", 1, 4, "storm_1469|1|4|0|0", 1565), [0, 0])

    def test_noise_copy_rejected(self):
        valid = "storm_9|2|4|-400|0"
        noise = "storm_9|2|4|-398|0"
        self.assertIsNone(weather.parse_record("storm_9", 2, 4, noise, _checksum(valid)))

    def test_field_mismatch_rejected(self):
        data = "storm_9|3|4|10|5"
        self.assertIsNone(weather.parse_record("storm_9", 2, 4, data, _checksum(data)))

    def test_assemble(self):
        packets = {"1": [0, 0], "2": [350, -250], "3": [-300, 200]}
        self.assertEqual(weather.assemble(packets, 3), [50, -50])
        self.assertIsNone(weather.assemble(packets, 4))


class ControllerTests(StubTestCase):
    def _stations(self, biomes):
        stations = []
        for n, biome in enumerate(biomes):
            outpost = self.world.add_outpost(f"outpost_{n}", is_home=(n == 0))
            setattr(outpost, "biome", biome)
            station = _Station(f"weather_station_{n + 1}", outpost)
            self.world.components[station.id] = station
            stations.append(station)
        return stations

    def test_non_leader_ends(self):
        stations = self._stations(["frozen", "coastal"])
        self.assertFalse(weather.WeatherController(stations[1]).step())

    def test_thunder_decoded_noise_ignored_and_not_reopened(self):
        stations = self._stations(["frozen"])
        copies = _message("storm_7", [(0, 0), (-400, 0), (100, 50), (-362, -203)])
        noise = _Copy("storm_7", 2, 4, 0, 0, data="storm_7|2|4|-398|0", checksum=copies[1].checksum)
        stations[0].signal_receiver.copies = [noise] + copies
        controller = weather.WeatherController(stations[0])
        self.world.clock.hours = 10.0
        self.assertTrue(controller.step())
        entry = weather.archive.get(weather.AFTERMATHS_KEY, {})["storm_7"]
        self.assertEqual((entry["kind"], entry["x"], entry["y"]), ("storm_glass", -662, -153))
        self.assertEqual(entry["ready_gh"], 46.0)
        self.assertEqual(entry["expires_gh"], 142.0)
        self.assertEqual(stations[0].signal_board.resolved[0][0], "storm_7")
        controller.step()
        self.assertNotIn("storm_7", controller.signals)

    def test_dust_needs_every_biome(self):
        stations = self._stations(["frozen", "coastal"])
        steps = [(0, 0)] + [(10, 1)] * 7
        copies = _message("storm_dust_1", steps)
        stations[0].signal_receiver.copies = copies[:4]
        stations[1].signal_receiver.copies = copies[4:6]
        controller = weather.WeatherController(stations[0])
        controller.step()
        self.assertEqual(len(controller.signals["storm_dust_1"]["packets"]), 6)
        self.assertEqual(weather.missing_biomes(controller.stations), ["geothermal", "volcanic", "deep"])
        stations[1].signal_receiver.copies = copies[4:]
        controller.step()
        entry = weather.archive.get(weather.AFTERMATHS_KEY, {})["storm_dust_1"]
        self.assertEqual((entry["kind"], entry["x"], entry["y"]), ("uranium", 70, 7))

    def test_packets_survive_restart_and_expired_message_dropped(self):
        stations = self._stations(["frozen"])
        stations[0].signal_receiver.copies = _message("storm_3", [(0, 0), (5, 5), (1, 1), (2, 2)])[:2]
        weather.WeatherController(stations[0]).step()
        stations[0].signal_receiver.copies = []
        restarted = weather.WeatherController(stations[0])
        self.assertEqual(len(restarted.signals["storm_3"]["packets"]), 2)
        self.world.clock.hours = 60.0
        restarted.step()
        self.assertNotIn("storm_3", restarted.signals)


if __name__ == "__main__":
    unittest.main()
