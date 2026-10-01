import unittest

from harness import StubTestCase
from tree_console import TreeConsole
import drone_weather
import weather_signals


class _Collect:
    def __init__(self, status, collected=0, item_id="storm_glass"):
        self.status = status
        self.collected = collected
        self.item_id = item_id
        self.message = ""


class _Drone:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def collect(self):
        self.calls += 1
        return self.results.pop(0) if self.results else _Collect("nothing_here")

    def exposure(self):
        return 0.0


class _Cask:
    type_id = "lead_cask"

    def __init__(self, cask_id, outpost, material="", count=0, capacity=100):
        self.id = cask_id
        self.outpost = outpost
        self._material = material
        self._count = count
        self._capacity = capacity

    def material(self):
        return self._material

    def capacity(self):
        return self._capacity

    def count(self, item_id):
        return self._count if item_id == self._material else 0


class _Collector(drone_weather.DroneWeatherMixin):
    """Just the host methods _collect_at_site() and _aftermath_candidates() use."""

    def __init__(self, drone, plated=True, home_outpost=None, space=10):
        self.drone = drone
        self.name = "drone_1"
        self.plated = plated
        self.home_outpost = home_outpost
        self.cruise_throttle = 0.5
        self.space = space
        self.log = TreeConsole(module="drone_weather")
        self.released = []

    def refresh_biosite_claim(self, key):
        pass

    def release_biosite_claim(self, key=None):
        self.released.append(key)

    def space_for(self, item_id):
        return self.space

    def publish_telemetry(self, state, target=None):
        pass

    def position(self):
        return (0.0, 0.0)

    def is_at(self, coords, precision=1.5):
        return True

    def fly_to(self, x, y, precision=1.5):
        return True

    def distance_between(self, a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def flight_speed_m_per_h(self, throttle=1.0):
        return 300.0 * throttle


def _entry(kind="storm_glass", x=150, y=0, ready=10.0, expires=100.0, **extra):
    entry = {"kind": kind, "x": x, "y": y, "units_min": 2, "units_max": 4, "ready_gh": ready, "expires_gh": expires, "decoded_gh": 0.0}
    entry.update(extra)
    return entry


def _target(event_id="storm_1", kind="storm_glass", limit=None):
    return {"event_id": event_id, "target_key": drone_weather.aftermath_target_key(event_id), "kind": kind,
            "item": drone_weather.ITEM_BY_KIND[kind], "coords": (150, 0), "ready_gh": 10.0, "expires_gh": 100.0, "limit": limit}


class PureTests(unittest.TestCase):
    def test_key_matches_weather_signals(self):
        self.assertEqual(drone_weather.AFTERMATHS_KEY, weather_signals.AFTERMATHS_KEY)

    def test_open_sites_filters_kind_exhausted_and_expiry(self):
        entries = {
            "a": _entry(),
            "b": _entry(kind="uranium"),
            "c": _entry(exhausted=True),
            "d": _entry(expires=50.5),
        }
        self.assertEqual([e for e, _ in drone_weather.open_sites(entries, 50.0, ("storm_glass",))], ["a"])
        self.assertEqual(sorted(e for e, _ in drone_weather.open_sites(entries, 50.0, ("storm_glass", "uranium"))), ["a", "b"])

    def test_launch_due_when_arrival_after_ready(self):
        self.assertFalse(drone_weather.launch_due(_entry(ready=10.0), 5.0, 2.0))
        self.assertTrue(drone_weather.launch_due(_entry(ready=10.0), 8.0, 2.0))


class CollectorTests(StubTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.world.add_outpost("outpost_home", is_home=True)
        self.world.clock.hours = 20.0

    def _publish(self, entries):
        drone_weather.archive.set(drone_weather.AFTERMATHS_KEY, entries)

    def test_glass_collected_until_exhausted(self):
        self._publish({"storm_1": _entry()})
        drone = _Drone([_Collect("moving"), _Collect("ok", 3), _Collect("nothing_here")])
        units, outcome = _Collector(drone)._collect_at_site(_target())
        self.assertEqual((units, outcome), (3, "site exhausted"))
        entry = drone_weather.aftermath_entries()["storm_1"]
        self.assertEqual((entry["collected"], entry["exhausted"]), (3, True))

    def test_repeated_nothing_here_marks_exhausted(self):
        self._publish({"storm_1": _entry()})
        drone = _Drone([])
        units, _outcome = _Collector(drone)._collect_at_site(_target())
        self.assertEqual(units, 0)
        self.assertEqual(drone.calls, drone_weather.NOTHING_HERE_LIMIT)
        self.assertTrue(drone_weather.aftermath_entries()["storm_1"]["exhausted"])

    def test_uranium_stops_at_cask_room(self):
        self._publish({"storm_2": _entry(kind="uranium")})
        drone = _Drone([_Collect("ok", 5, "raw_uranium")] * 4)
        units, outcome = _Collector(drone)._collect_at_site(_target("storm_2", "uranium", limit=10))
        self.assertEqual(units, 10)
        self.assertIn("Lead Cask", outcome)
        self.assertFalse(drone_weather.aftermath_entries()["storm_2"].get("exhausted"))

    def test_unplated_never_targets_uranium(self):
        self._publish({"storm_2": _entry(kind="uranium", ready=19.0), "storm_1": _entry(ready=19.0)})
        collector = _Collector(_Drone([]), plated=False, home_outpost=self.home)
        self.assertEqual([c["event_id"] for c in collector._aftermath_candidates(collector.aftermath_kinds())], ["storm_1"])

    def test_uranium_needs_cask_room_and_research(self):
        self._publish({"storm_2": _entry(kind="uranium", ready=19.0)})
        collector = _Collector(_Drone([]), home_outpost=self.home)
        self.assertEqual(collector._aftermath_candidates(collector.aftermath_kinds()), [])
        self.world.components["lead_cask_1"] = _Cask("lead_cask_1", self.home, material="raw_uranium", count=70)
        self.world.components["lead_cask_2"] = _Cask("lead_cask_2", self.home, material="fuel_rod", count=10)
        self.assertEqual(drone_weather.cask_room(self.home), 30)
        self.assertEqual(collector._aftermath_candidates(collector.aftermath_kinds()), [])

        class _Research:
            def is_unlocked(self, research_id):
                return research_id == drone_weather.HOT_CARGO_RESEARCH

        self.world.components["research"] = _Research()
        candidates = collector._aftermath_candidates(collector.aftermath_kinds())
        self.assertEqual([(c["event_id"], c["limit"]) for c in candidates], [("storm_2", 30)])

    def test_not_launched_before_arrival_would_be_ready(self):
        # 150 m at 150 m/h = 1 h away.
        self._publish({"storm_1": _entry(ready=22.0)})
        collector = _Collector(_Drone([]), home_outpost=self.home)
        self.assertEqual(collector._aftermath_candidates(("storm_glass",)), [])
        self.world.clock.hours = 21.0
        self.assertEqual(len(collector._aftermath_candidates(("storm_glass",))), 1)


if __name__ == "__main__":
    unittest.main()
