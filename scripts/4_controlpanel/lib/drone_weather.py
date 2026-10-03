# Drone role: storm aftermath collector. Detected when Shield Plating is
# mounted (DroneController.detect_role()); idle haulers also take Storm Glass
# sites (try_aftermath_pickup(), called from drone_hauler.py).
#
# Sites come from weather.aftermaths, which lib/weather_signals.py (tier
# 7_miningdrills) decodes from Weather Station transmissions. An aftermath
# exists only from ready_gh (storm end) to expires_gh, and only at the exact
# integer coordinate: go_to() lands exactly on it, and collect() returns
# "nothing_here" for an early, nearby, expired or exhausted site alike
# (docs/guide/weather_system.md). So a drone launches once it would arrive
# after ready_gh, hovers on the spot until then, and treats repeated
# "nothing_here" after ready_gh as exhausted.
#
# Raw Uranium (dust storms, 14-28 units) is plated-only: an unplated batch
# adds 40 exposure and the drone scrambles at 100. A plated drone unloads it
# at its home Depot, which puts hot cargo into a Lead Cask at that outpost
# (research_shielded_depot_ops required; "cask_missing" otherwise), so a
# uranium site is only taken while the home outpost has cask room (casks
# reserved for Fuel Rods in lead_cask.roles don't count). That room is shared
# by every plated drone homed there, so a drone reserves its share in
# lead_cask.inbound when it claims the site (reserve_inbound(); the grant is
# the trip's limit), narrows it to the units collected, and drops it once no
# uranium is aboard. One collect() takes up to COLLECT_BATCH_UNITS, so a
# uranium trip's limit is whole batches (batch_limit()): less room than one
# batch launches nothing, else the overshoot stays aboard and the Depot drops
# it into the next empty cask, the Fuel Rod cask included. Room is also capped
# by uranium_want(): lead_cask.URANIUM_STOCK_TARGET plus Supply Dock orders at
# home, less the uranium already in the casks.
# Storm Glass (thunderstorms, 2-4 units) is ordinary cargo.
#
# One drone per site at a time: an exclusive claim in biosite.claims under
# AFTERMATH_KEY_PREFIX + event_id (drone_claims.py). A site that needs more
# than one trip is claimed again after the unload, by whichever drone is
# free. Collected units and exhaustion are written back into the site's
# weather.aftermaths entry, which weather_signals.py prunes after expiry.

from archive import archive
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
import fleet_intent
import lead_cask
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController

# Same key as weather_signals.AFTERMATHS_KEY (tests/test_drone_weather.py checks).
AFTERMATHS_KEY = "weather.aftermaths"
ITEM_BY_KIND = {"uranium": "raw_uranium", "storm_glass": "storm_glass"}
AFTERMATH_KEY_PREFIX = "aftermath_"
HOT_CARGO_RESEARCH = "research_shielded_depot_ops"

# Wait this long past ready_gh before the first collect(), so the aftermath
# exists when the drone asks.
READY_MARGIN_GH = 0.1
# A site expiring sooner than this after the drone's arrival is skipped.
EXPIRY_MARGIN_GH = 1.0
# "nothing_here" this many times in a row at the exact coordinate, after
# ready_gh and before any unit came out, marks the site exhausted.
NOTHING_HERE_LIMIT = 3
# Most units one collect() moves (docs/guide/weather_system.md).
COLLECT_BATCH_UNITS = 5
# "moving"/"busy" retries while the drone settles into its hover.
SETTLE_RETRIES = 10
# A hauler takes a Storm Glass site before its next haul job when the site
# expires within this many hours; otherwise only when it has no haul job.
HAULER_GLASS_URGENT_GH = 24.0
# Poll while hovering on a site before ready_gh, and while idle.
WAIT_POLL_S = 10.0
IDLE_POLL_S = 30.0


def aftermath_target_key(event_id):
    return f"{AFTERMATH_KEY_PREFIX}{event_id}"


def aftermath_entries():
    entries = archive.get(AFTERMATHS_KEY, {})
    return entries if isinstance(entries, dict) else {}


def open_sites(entries, now, kinds):
    """[(event_id, entry)] of kind in kinds, not exhausted, and not expiring within EXPIRY_MARGIN_GH."""
    sites = []
    for event_id, entry in entries.items():
        if not isinstance(entry, dict) or entry.get("kind") not in kinds or entry.get("exhausted"):
            continue
        if entry.get("expires_gh", 0) - EXPIRY_MARGIN_GH <= now:
            continue
        sites.append((event_id, entry))
    return sites


def launch_due(entry, now, travel_h):
    """True once a drone leaving now arrives at or after the aftermath appears."""
    return now + travel_h >= entry.get("ready_gh", 0)


def record_collection(event_id, units, exhausted):
    """Adds units to the site's "collected" count and flags it exhausted; no-op once the entry is pruned."""
    def updater(entries):
        if not isinstance(entries, dict):
            return {}
        entry = entries.get(event_id)
        if isinstance(entry, dict):
            entry["collected"] = entry.get("collected", 0) + units
            if exhausted:
                entry["exhausted"] = True
        return entries

    return archive.transaction(AFTERMATHS_KEY, {}, updater)


def now_gh():
    clock = get_component("clock")
    if clock is None:
        return 0.0
    try:
        return float(clock.elapsed_game_hours())
    except Exception as error:
        swallowed("drone_weather.now_gh: clock.elapsed_game_hours", error)
        return 0.0


def hot_cargo_unlocked():
    research = get_component("research")
    if research is None:
        return False
    try:
        return bool(research.is_unlocked(HOT_CARGO_RESEARCH))
    except Exception as error:
        swallowed("drone_weather.hot_cargo_unlocked: research.is_unlocked", error)
        return False


def cask_room(outpost, item_id="raw_uranium"):
    """Free Lead Cask units for item_id at outpost (lead_cask.room_for(): casks reserved for Fuel Rods left out)."""
    if outpost is None:
        return 0
    return lead_cask.room_for(item_id, outpost)


def uranium_want(outpost):
    """Raw Uranium still wanted in outpost's casks: lead_cask.URANIUM_STOCK_TARGET plus
    what Supply Dock orders there still owe, minus the cask stock."""
    from production import dock_remaining_requirements
    owed = 0
    try:
        owed = int(dock_remaining_requirements(getattr(outpost, "id", None)).get(lead_cask.URANIUM_ITEM, 0))
    except Exception as error:
        swallowed("drone_weather.uranium_want: dock_remaining_requirements", error)
    return lead_cask.URANIUM_STOCK_TARGET + owed - lead_cask.cask_stock(lead_cask.URANIUM_ITEM, outpost)


def batch_limit(units):
    """Largest whole number of collect() batches that fits in units."""
    return max(0, units) // COLLECT_BATCH_UNITS * COLLECT_BATCH_UNITS


class DroneWeatherMixin:
    """Aftermath collection, mixed into DroneController: the plated "aftermath" role loop and the hauler's Storm Glass pickup."""

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def aftermath_kinds(self):
        return ("uranium", "storm_glass") if self._host.plated else ("storm_glass",)

    def _aftermath_candidates(self, kinds, urgent_within=None):
        """
        Sites this drone could leave for now, soonest expiry first:
        [{"event_id", "target_key", "kind", "item", "coords", "ready_gh",
        "expires_gh", "limit"}]. limit caps the units one trip takes (Lead
        Cask room for uranium, else None).
        """
        now = now_gh()
        sites = open_sites(aftermath_entries(), now, kinds)
        if not sites:
            return []
        uranium_room = 0
        if "uranium" in kinds and any(entry["kind"] == "uranium" for _e, entry in sites):
            home_id = getattr(self._host.home_outpost, "id", None)
            if hot_cargo_unlocked():
                room = cask_room(self._host.home_outpost)
                promised = lead_cask.inbound_units(home_id, self._host.get_current_tick(), exclude=self._host.name)
                want = uranium_want(self._host.home_outpost)
                uranium_room = batch_limit(min(room, want) - promised)
                self._host.log.trace(f"[{self._host.name}] Lead Cask room at '{home_id}': {room} free, {want} wanted, {promised} reserved by other drones, {uranium_room} in whole batches.")
            if uranium_room <= 0:
                self._host.log.debug(f"[{self._host.name}] Uranium aftermath(s) known but less than {COLLECT_BATCH_UNITS} unreserved, wanted Lead Cask room at '{home_id}' (or {HOT_CARGO_RESEARCH} missing); skipping them.")
        speed = self._host.flight_speed_m_per_h(self._host.cruise_throttle)
        pos = self._host.position()
        candidates = []
        for event_id, entry in sites:
            kind = entry["kind"]
            item = ITEM_BY_KIND.get(kind)
            if item is None or (kind == "uranium" and uranium_room <= 0):
                continue
            if urgent_within is not None and entry.get("expires_gh", 0) - now > urgent_within:
                continue
            coords = (int(entry["x"]), int(entry["y"]))
            travel_h = self._host.distance_between(pos, coords) / speed if speed > 0 else 0.0
            if now + travel_h + EXPIRY_MARGIN_GH >= entry.get("expires_gh", 0):
                continue
            if not launch_due(entry, now, travel_h):
                self._host.log.trace(f"[{self._host.name}] Aftermath {event_id}: ready at {entry.get('ready_gh', 0):.1f} gh, {travel_h:.1f} h away at {now:.1f} gh; not launching yet.")
                continue
            if self._host.space_for(item) <= 0:
                continue
            candidates.append({
                "event_id": event_id,
                "target_key": aftermath_target_key(event_id),
                "kind": kind,
                "item": item,
                "coords": coords,
                "ready_gh": entry.get("ready_gh", 0),
                "expires_gh": entry.get("expires_gh", 0),
                "limit": uranium_room if kind == "uranium" else None,
            })
        candidates.sort(key=lambda c: (c["expires_gh"], self._host.distance_between(pos, c["coords"])))
        return candidates

    def _select_aftermath_target(self, candidates):
        """First candidate the drone can afford there and back and wins the claim for; (candidate, budget) or (None, None)."""
        claims = self._host.get_biosite_claims()
        tick = self._host.get_current_tick()
        for candidate in candidates:
            claim = claims.get(candidate["target_key"]) or {}
            holder = claim.get("drone")
            age = tick - claim.get("tick", 0)
            if holder and holder != self._host.name and age < self._host.CLAIM_STALE_TICKS:
                self._host.log.trace(f"Aftermath {candidate['event_id']}: held by '{holder}'; skipping.")
                continue
            budget = self._host.calculate_trip_energy(candidate["coords"])
            if not budget["is_achievable"]:
                self._host.log.trace(f"Aftermath {candidate['event_id']}: {budget['total_required_wh']:.1f} {self._host.energy_unit()} required, not achievable; skipping.")
                continue
            if not self._host.claim_biosite(candidate["target_key"], {"coords": candidate["coords"], "name": candidate["target_key"]}):
                self._host.log.debug(f"Lost claim race on aftermath {candidate['event_id']}; trying next candidate.")
                continue
            if candidate["kind"] == "uranium" and not self._reserve_cask_room(candidate):
                self._host.release_biosite_claim(candidate["target_key"])
                continue
            return candidate, budget
        return None, None

    def _reserve_cask_room(self, candidate):
        """Reserves the uranium trip's Lead Cask room at home; narrows candidate["limit"] to the grant. False when none is left."""
        home = self._host.home_outpost
        home_id = getattr(home, "id", None)
        tick = self._host.get_current_tick()
        granted = lead_cask.reserve_inbound(self._host.name, home_id, min(cask_room(home), uranium_want(home)), candidate["limit"], tick)
        whole = batch_limit(granted)
        if whole <= 0:
            if granted > 0:
                lead_cask.release_inbound(self._host.name)
            self._host.log.debug(f"Aftermath {candidate['event_id']}: {granted} Lead Cask unit(s) left at '{home_id}' after other drones' reservations, less than one {COLLECT_BATCH_UNITS}-unit collect(); skipping.")
            return False
        if whole < granted:
            lead_cask.set_inbound(self._host.name, home_id, whole, tick)
            granted = whole
        if granted < candidate["limit"]:
            self._host.log.debug(f"Aftermath {candidate['event_id']}: reserved {granted} of {candidate['limit']} Lead Cask unit(s) at '{home_id}'.")
        candidate["limit"] = granted
        return True

    def _sync_cask_reservation(self):
        """Matches this drone's lead_cask.inbound entry to the Raw Uranium aboard (none aboard: released)."""
        aboard = self._host.cargo_count(ITEM_BY_KIND["uranium"])
        if aboard > 0:
            lead_cask.set_inbound(self._host.name, getattr(self._host.home_outpost, "id", None), aboard, self._host.get_current_tick())
        else:
            lead_cask.release_inbound(self._host.name)

    def _end_trip_intent(self, target, units):
        """After a trip: the fleet card shows the load heading home, or no job."""
        if units > 0:
            self._host.set_intent(fleet_intent.describe("hauling", [target["item"]], source=target["event_id"], dest=getattr(self._host.home_outpost, "id", None)))
        else:
            self._host.set_intent(None)

    def _wait_for_ready(self, target):
        """Hovers on the site until ready_gh + READY_MARGIN_GH. False when the site expires first."""
        while True:
            now = now_gh()
            if now >= target["ready_gh"] + READY_MARGIN_GH:
                return True
            if now >= target["expires_gh"]:
                return False
            self._host.refresh_biosite_claim(target["target_key"])
            self._host.publish_telemetry("WAITING_AFTERMATH", target["event_id"])
            self._host.log.debug(f"[{self._host.name}] On site {target['coords']}; aftermath appears at {target['ready_gh']:.1f} gh (now {now:.1f}).")
            flush_all()
            sleep(WAIT_POLL_S)

    def _collect_at_site(self, target):
        """
        Repeats collect() at the site until it is exhausted, cargo is full,
        target["limit"] units came aboard, or the drone scrambles. Records
        the result in weather.aftermaths. Returns (units collected, outcome text).
        """
        coords = target["coords"]
        limit = target.get("limit")
        collected = 0
        misses = 0
        settle = SETTLE_RETRIES
        exhausted = False
        outcome = "stopped"
        self._host.publish_telemetry("COLLECTING", target["event_id"])
        while True:
            if limit is not None and collected >= limit:
                outcome = f"Lead Cask room ({limit}) reached"
                break
            self._host.refresh_biosite_claim(target["target_key"])
            try:
                res = self._host.drone.collect()
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] collect() failed at {coords}: {e}")
                outcome = "collect() error"
                break
            status = res.status
            if status == "ok":
                collected += int(getattr(res, "collected", 0) or 0)
                misses = 0
                self._host.log.debug(f"[{self._host.name}] Collected {res.collected} {res.item_id} at {coords} ({collected} this trip).")
                if self._host.space_for(target["item"]) <= 0:
                    outcome = "cargo full"
                    break
                continue
            if status in ("moving", "busy") and settle > 0:
                settle -= 1
                flush_all()
                sleep(1.0)
                continue
            if status == "nothing_here":
                if collected > 0:
                    exhausted = True
                    outcome = "site exhausted"
                    break
                misses += 1
                if misses >= NOTHING_HERE_LIMIT:
                    exhausted = True
                    outcome = f"nothing_here {misses}x at {self._host.position()}; marked exhausted"
                    break
                if not self._host.is_at(coords, precision=0.01):
                    self._host.fly_to(coords[0], coords[1], precision=0.01)
                flush_all()
                sleep(2.0)
                continue
            if status == "scrambled":
                self._host.log.level("warn").print(f"[{self._host.name}] Scrambled while collecting at {coords} (exposure {self._exposure():.0f}); awaiting rescue.")
                outcome = "scrambled"
                break
            if status == "no_cargo_space":
                outcome = "no cargo space"
                break
            self._host.log.level("warn").print(f"[{self._host.name}] collect() notice at {coords}: {status} - {res.message}")
            outcome = status
            break
        record_collection(target["event_id"], collected, exhausted)
        return collected, outcome

    def _exposure(self):
        try:
            return float(self._host.drone.exposure())
        except Exception as error:
            swallowed("drone_weather.DroneWeatherMixin._exposure: drone.exposure", error)
            return 0.0

    def _fly_and_collect(self, target):
        """Flies to the claimed site, waits for ready_gh, collects. Returns (units, outcome text); releases the claim on failure."""
        self._host.publish_telemetry("OUTBOUND", target["event_id"])
        coords = target["coords"]
        if not self._host.fly_to(coords[0], coords[1], precision=0.01):
            self._host.release_biosite_claim(target["target_key"])
            return 0, "site unreachable, claim released"
        if not self._wait_for_ready(target):
            record_collection(target["event_id"], 0, True)
            self._host.release_biosite_claim(target["target_key"])
            return 0, "site expired before it appeared"
        return self._collect_at_site(target)

    def _set_aftermath_mission(self, target):
        saved = dict(target)
        saved["coords"] = list(target["coords"])
        self.current_target_key = target["target_key"]
        self.current_target = saved
        self._host.save_mission("aftermath", saved)
        self._host.set_intent(fleet_intent.describe("collecting", [target["item"]], at=target["event_id"]))

    def _resumed_aftermath(self) -> "dict | None":
        """The saved aftermath target after a script reload (load_mission() kept its claim), else None."""
        key = getattr(self, "current_target_key", None)
        saved = getattr(self, "current_target", None)
        if not isinstance(key, str) or not key.startswith(AFTERMATH_KEY_PREFIX) or not isinstance(saved, dict):
            return None
        target = dict(saved)
        target["coords"] = tuple(saved.get("coords") or (0, 0))
        return target

    # ------------------------------------------------------------ plated role

    def run_aftermath_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_weather")
        log.print(f"Aftermath collector ({self._host.name}) online; plated={self._host.plated}, home {getattr(self._host.home_outpost, 'id', None)}.")
        if not self._host.plated:
            log.level("warn").print(f"[{self._host.name}] No Shield Plating: collecting Storm Glass only.")
        while True:
            reset_all()
            try:
                if self._host.is_stranded():
                    log.level("warn").print(f"[{self._host.name}] {self._host.status()}; awaiting drone_service rescue.")
                    self._host.publish_telemetry("STRANDED")
                    flush_all()
                    sleep(poll_interval)
                    continue
                if self._host.handle_recall_if_active() or self._host.handle_upgrade_request_if_active():
                    flush_all()
                    sleep(poll_interval)
                    continue
                self._host.cleanup_stale_biosite_claims()

                target = self._resumed_aftermath()
                if target is None:
                    target = self._next_aftermath_target(log, poll_interval)
                    if target is None:
                        continue
                    self._set_aftermath_mission(target)
                log.start(f"[{self._host.name}] Aftermath {target['event_id']}: {target['kind']} at {target['coords']}")
                units, outcome = self._fly_and_collect(target)
                # Releasing also clears the mission; cargo aboard is unloaded below or next cycle.
                self._host.release_biosite_claim(target["target_key"])
                self._sync_cask_reservation()
                self._end_trip_intent(target, units)
                if units > 0 and not self._host._return_and_unload():
                    log.end(f"{units} unit(s), {outcome}; unload deferred")
                    flush_all()
                    sleep(poll_interval)
                    continue
                self._sync_cask_reservation()
                self._host.set_intent(None)
                log.end(f"{units} unit(s), {outcome}")
            except Exception as e:
                log.level("error").print(f"[{self._host.name}] Aftermath loop exception: {e}")
                try:
                    self._host.release_biosite_claim()
                except Exception as error:
                    swallowed("drone_weather.DroneWeatherMixin.run_aftermath_loop: release_biosite_claim", error)
                flush_all()
                sleep(5.0)

    def _next_aftermath_target(self, log, poll_interval):
        """
        Between trips: unloads cargo aboard, charges, then claims the next
        site. Returns the claimed target, or None after sleeping (the caller
        starts the next cycle).
        """
        self._sync_cask_reservation()
        if self._host.cargo_count() > 0:
            if not self._host._return_and_unload():
                flush_all()
                sleep(poll_interval)
            self._sync_cask_reservation()
            return None
        curr_wh, _, _ = self._host.get_battery()
        if curr_wh <= self._host.energy_needed_to_return_comfortably():
            self._host.return_to_service_for_charge(log, f"Battery low ({curr_wh:.1f} {self._host.energy_unit()})")
            flush_all()
            sleep(poll_interval)
            return None
        candidates = self._aftermath_candidates(self.aftermath_kinds())
        if not candidates:
            self._host.publish_telemetry("IDLE_NO_TARGETS")
            flush_all()
            sleep(IDLE_POLL_S)
            return None
        if self._host.hold_for_launch_charge(log):
            flush_all()
            sleep(poll_interval)
            return None
        target, budget = self._select_aftermath_target(candidates)
        if target is None or budget is None:
            log.debug(f"[{self._host.name}] {len(candidates)} aftermath site(s), none reachable and claimable.")
            self._host.publish_telemetry("IDLE_OUT_OF_RANGE")
            _, _, lvl = self._host.get_battery()
            if lvl < 0.98:
                self._host.return_to_service_for_charge(log, f"No aftermath reachable at {lvl*100:.0f}% charge")
            flush_all()
            sleep(15.0)
            return None
        log.debug(f"[{self._host.name}] Claimed aftermath {target['event_id']}; trip needs {budget['total_required_wh']:.1f} {self._host.energy_unit()}.")
        return target

    # ------------------------------------------------------------ hauler pickup

    def try_aftermath_pickup(self, urgent_only):
        """
        Hauler hook, run with empty cargo: flies one Storm Glass site and
        collects it (urgent_only: only sites expiring within
        HAULER_GLASS_URGENT_GH). The glass stays aboard; the hauler loop's
        cargo-aboard branch delivers it. True when a trip was made.
        """
        target = self._resumed_aftermath()
        if target is None:
            if not open_sites(aftermath_entries(), now_gh(), ("storm_glass",)):
                return False
            candidates = self._aftermath_candidates(("storm_glass",), HAULER_GLASS_URGENT_GH if urgent_only else None)
            target, _budget = self._select_aftermath_target(candidates)
            if target is None:
                return False
            self._set_aftermath_mission(target)
        self._host.log.start(f"[{self._host.name}] Storm Glass pickup {target['event_id']} at {target['coords']}")
        units, outcome = self._fly_and_collect(target)
        self._host.release_biosite_claim(target["target_key"])
        # The cargo-aboard delivery sets its own hauling intent.
        self._host.set_intent(None)
        self._host.log.end(f"{units} unit(s), {outcome}")
        return True
