# Weather Station signal receiver: recovers storm aftermath coordinates
# (Raw Uranium from dust storms, Storm Glass from thunderstorms) from live
# transmissions and publishes them to the archive for drone collection.
#
# Reception (docs/guide/weather_system.md, simworker Fre()): a powered station hears
# every "broadcast" packet plus the dust packets on its own biome's channel, from
# anywhere on the planet; distance does not matter. Thunder messages are all
# broadcast. A dust message spreads its packets over all five biome channels, so it
# completes only with one powered station in every biome. signal_receiver is a
# read-only property, so one script reads every station: the station with the lowest
# id among powered stations is the leader; every other station's script ends at once.
#
# Validation: a copy is valid when sum(ord(c) for c in data) == checksum and data
# reads event_id|number|total|dx|dy matching the copy's own fields. Noise copies
# reuse the valid packet's checksum with a changed dx or dy, so the checksum rejects
# them. Packet dx/dy offsets summed in number order from (0, 0) give the absolute
# world coordinate of the aftermath.
#
# Timing: a message is audible from storm start until storm end + SIGNAL_GRACE_GH,
# which is the copy's expires_at_gh. The aftermath appears at storm end and stays
# AFTERMATH_WINDOW_GH[kind] hours, so the coordinate is often known before the
# aftermath exists.
#
# Archive (docs/cheatsheet/archive_ipc.md §4):
#   weather.signals    {event_id: {"total", "expires_gh", "packets": {"<n>": [dx, dy]}}}
#                      incomplete messages, so a restart keeps packets already heard.
#   weather.aftermaths {event_id: {"kind", "x", "y", "units_min", "units_max",
#                      "ready_gh", "expires_gh", "decoded_gh"}} for the collector.

from archive import archive
from tree_console import TreeConsole, flush_all, reset_all
from version_guard import validate_game_version
from components import weather_station
from swallow import swallowed

BIOMES = ("frozen", "coastal", "geothermal", "volcanic", "deep")
BROADCAST_CHANNEL = "broadcast"
STATION_TYPE_ID = "weather_station"

SIGNALS_KEY = "weather.signals"
AFTERMATHS_KEY = "weather.aftermaths"

# Game constants (simworker weather config).
DUST_PACKET_TOTAL = 8
SIGNAL_GRACE_GH = 4.0
AFTERMATH_WINDOW_GH = {"uranium": 48.0, "storm_glass": 96.0}
AFTERMATH_UNITS = {"uranium": (14, 28), "storm_glass": (2, 4)}

# Sweep every this many world-clock hours. The shortest listening window is
# SIGNAL_GRACE_GH after storm end, so this leaves several sweeps per window.
SWEEP_GAME_HOURS = 1.0
# Re-discover stations (and re-check leadership) every this many sweeps.
STATION_REFRESH_SWEEPS = 10
# Fallback when clock.real_seconds_per_hour() is unreadable.
DEFAULT_REAL_SECONDS_PER_HOUR = 25.0


def parse_record(event_id, number, total, data, checksum):
    """[dx, dy] of a valid transmission copy, or None for noise / malformed data."""
    if not isinstance(data, str) or sum([ord(c) for c in data]) != checksum:
        return None
    parts = data.split("|")
    if len(parts) != 5 or parts[0] != event_id:
        return None
    try:
        if int(parts[1]) != number or int(parts[2]) != total:
            return None
        return [int(parts[3]), int(parts[4])]
    except Exception as error:
        swallowed("weather_signals.parse_record: int", error)
        return None


def assemble(packets, total):
    """Aftermath [x, y] from a complete {"<n>": [dx, dy]} packet set, or None while incomplete."""
    x = 0
    y = 0
    for number in range(1, total + 1):
        step = packets.get(str(number))
        if step is None:
            return None
        x += step[0]
        y += step[1]
    return [x, y]


def aftermath_kind(total):
    """Aftermath item a message of `total` packets describes."""
    return "uranium" if total == DUST_PACKET_TOTAL else "storm_glass"


def missing_biomes(stations):
    """Biomes without a powered station, in BIOMES order. stations: [(id, biome, powered)]."""
    covered = set([biome for _id, biome, powered in stations if powered])
    return [biome for biome in BIOMES if biome not in covered]


def discover_stations():
    """[(station_id, biome, powered)] for every Weather Station on the outpost network."""
    stations = []
    network = get_component("outpost_network")
    if network is None:
        return stations
    for outpost in network.outposts():
        biome = getattr(outpost, "biome", None)
        for ref in outpost.buildings(STATION_TYPE_ID):
            stations.append((ref.id, biome, bool(getattr(ref, "powered", False))))
    return stations


def leader_id(stations):
    """Lowest id among powered stations, or None when none is powered."""
    powered = sorted([station_id for station_id, _biome, powered in stations if powered])
    return powered[0] if powered else None


class WeatherController:
    """Leader-elected sweep of every Weather Station receiver; decodes aftermath coordinates into the archive."""

    def __init__(self, station):
        self.station = station
        self.name = station.id
        self.log = TreeConsole(module="weather_signals")
        self.clock = get_component("clock")
        self.stations = []
        self.sweeps = 0
        self.last_missing = None
        signals = archive.get(SIGNALS_KEY, {})
        self.signals = signals if isinstance(signals, dict) else {}
        # Decoded events still audible: {event_id: listening-window end gh}, so a re-heard
        # copy does not open the message again.
        self.done = {}
        aftermaths = archive.get(AFTERMATHS_KEY, {})
        if isinstance(aftermaths, dict):
            for event_id, entry in aftermaths.items():
                if isinstance(entry, dict):
                    self.done[event_id] = entry.get("ready_gh", 0) + SIGNAL_GRACE_GH
        # Decoded entries whose archive write failed; retried next sweep.
        self.unpublished = []

    def now_gh(self):
        if self.clock is None:
            return 0.0
        try:
            return float(self.clock.elapsed_game_hours())
        except Exception as error:
            swallowed("weather_signals.WeatherController.now_gh: clock.elapsed_game_hours", error)
            return 0.0

    def sweep_seconds(self):
        seconds_per_hour = DEFAULT_REAL_SECONDS_PER_HOUR
        if self.clock is not None:
            try:
                seconds_per_hour = float(self.clock.real_seconds_per_hour())
            except Exception as error:
                swallowed("weather_signals.WeatherController.sweep_seconds: clock.real_seconds_per_hour", error)
        return seconds_per_hour * SWEEP_GAME_HOURS

    def refresh_stations(self):
        """Re-discover stations; False when this station is not the leader."""
        try:
            self.stations = discover_stations()
        except Exception as error:
            swallowed("weather_signals.WeatherController.refresh_stations: discover_stations", error)
            return True
        leader = leader_id(self.stations)
        if leader is not None and leader != self.name:
            self.log.print(f"[{self.name}] {leader} is the weather leader; this script ends.")
            return False
        missing = missing_biomes(self.stations)
        if missing != self.last_missing:
            if missing:
                self.log.level("warn").print(f"[{self.name}] No powered Weather Station in {', '.join(missing)}: dust (Raw Uranium) messages cannot complete.")
            else:
                self.log.print(f"[{self.name}] All 5 biomes covered: dust and thunder messages can complete.")
            self.last_missing = missing
        return True

    def listen(self):
        """Store every new valid packet heard by any powered station. Returns (new packets, noise copies)."""
        added = 0
        noise = 0
        for station_id, _biome, powered in self.stations:
            if not powered:
                continue
            try:
                station = self.station if station_id == self.name else weather_station(station_id)
                if station is None:
                    continue
                heard = station.signal_receiver.transmissions()
            except Exception as error:
                swallowed("weather_signals.WeatherController.listen: signal_receiver.transmissions", error)
                continue
            for copy in heard:
                if copy.event_id in self.done:
                    continue
                event = self.signals.get(copy.event_id)
                if event is None:
                    event = {"total": copy.total, "expires_gh": copy.expires_at_gh, "packets": {}}
                    self.signals[copy.event_id] = event
                key = str(copy.number)
                if key in event["packets"]:
                    continue
                step = parse_record(copy.event_id, copy.number, copy.total, copy.data, copy.checksum)
                if step is None:
                    noise += 1
                    continue
                event["packets"][key] = step
                added += 1
        return added, noise

    def decode(self, now):
        """Move complete messages to weather.aftermaths; drop expired ones. Returns (decoded, missed) entry lists."""
        decoded = []
        missed = []
        for event_id in list(self.signals.keys()):
            event = self.signals[event_id]
            point = assemble(event["packets"], event["total"])
            if point is not None:
                kind = aftermath_kind(event["total"])
                ready = event["expires_gh"] - SIGNAL_GRACE_GH
                units = AFTERMATH_UNITS[kind]
                decoded.append((event_id, {
                    "kind": kind, "x": point[0], "y": point[1],
                    "units_min": units[0], "units_max": units[1],
                    "ready_gh": ready, "expires_gh": ready + AFTERMATH_WINDOW_GH[kind],
                    "decoded_gh": now,
                }))
                self.done[event_id] = event["expires_gh"]
                del self.signals[event_id]
            elif event["expires_gh"] < now:
                missed.append((event_id, event))
                del self.signals[event_id]
        for event_id in [e for e, until in self.done.items() if until < now]:
            del self.done[event_id]
        return decoded, missed

    def publish(self, decoded, now):
        """Write decoded aftermaths and prune expired ones; returns the write status."""
        def updater(entries):
            if not isinstance(entries, dict):
                entries = {}
            for event_id, entry in decoded:
                entries[event_id] = entry
            for event_id in list(entries.keys()):
                entry = entries[event_id]
                if not isinstance(entry, dict) or entry.get("expires_gh", 0) < now:
                    del entries[event_id]
            return entries
        return archive.transaction(AFTERMATHS_KEY, {}, updater)

    def show_on_board(self, event_id, entry):
        """Show the newest decoded aftermath on this station's Signal Board."""
        try:
            self.station.signal_board.resolve(event_id, {
                "item": entry["kind"],
                "x": entry["x"],
                "y": entry["y"],
                "ready_gh": round(entry["ready_gh"], 1),
                "expires_gh": round(entry["expires_gh"], 1),
            })
        except Exception as error:
            swallowed("weather_signals.WeatherController.show_on_board: signal_board.resolve", error)

    def step(self):
        """One sweep. Returns False when this script should end (not the leader)."""
        if self.sweeps % STATION_REFRESH_SWEEPS == 0 and not self.refresh_stations():
            return False
        self.sweeps += 1
        now = self.now_gh()
        added, noise = self.listen()
        decoded, missed = self.decode(now)
        if added:
            self.log.debug(f"[{self.name}] {added} new valid packet(s), {noise} noise copy(ies) rejected; {len(self.signals)} message(s) incomplete.")
        if added or decoded or missed:
            archive.set(SIGNALS_KEY, self.signals)
        if not decoded and not missed:
            if self.unpublished or self.sweeps % STATION_REFRESH_SWEEPS == 0:
                if self.publish(self.unpublished, now):
                    self.unpublished = []
            return True
        self.log.start("Weather messages")
        if self.publish(self.unpublished + decoded, now):
            self.unpublished = []
        else:
            self.log.level("warn").print(f"Archive write to {AFTERMATHS_KEY} failed; retrying next sweep.")
            self.unpublished = self.unpublished + decoded
        for event_id, entry in decoded:
            ready_in = entry["ready_gh"] - now
            when = f"ready in {ready_in:.1f} h" if ready_in > 0 else "ready now"
            self.log.print(f"{event_id}: {entry['kind']} at ({entry['x']}, {entry['y']}), {when}, expires at {entry['expires_gh']:.1f} gh.")
        for event_id, event in missed:
            self.log.print(f"{event_id}: listening window closed with {len(event['packets'])}/{event['total']} packets; aftermath lost.")
        if decoded:
            event_id, entry = decoded[-1]
            self.show_on_board(event_id, entry)
        self.log.end(f"{len(decoded)} decoded, {len(missed)} missed")
        return True

    def run(self):
        self.log.print(f"Weather Controller ({self.name}) online.")
        validate_game_version()
        while True:
            reset_all()
            try:
                if not self.step():
                    flush_all()
                    return
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Weather sweep exception: {error}")
            flush_all()
            sleep(self.sweep_seconds())
