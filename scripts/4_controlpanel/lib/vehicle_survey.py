# Vehicle mixin: sonar scanning/surveying, POI discovery, known-contact
# routes (contacts in autoplay.survey_requests areas ahead of the rest) and
# outward spiral waypoints. Shared by Rover and Pioneer via VehicleController
# (lib/vehicle.py). No loop: the Scout role is SurveyJob (lib/job_survey.py).
# Drilling lives in lib/vehicle_mining.py's VehicleMiningMixin.

from typing import TYPE_CHECKING

import deep_oil
import outpost_mining
from archive import archive
from game_clock import is_fresh
from mission import Mission
from scan_groups import COVER_MARGIN, OUTPOST_WEIGHT, plan_stops_atomic
from survey_requests import read_requests, request_at
from swallow import swallowed
from tree_console import flush_all
from vehicle_claims import sonar_range

if TYPE_CHECKING:
    from vehicle import VehicleController

SURVEY_SPIRAL_KEY = "survey.spiral"
LEGACY_PIONEER_SPIRAL_KEY = "pioneer.survey_spiral"


def spiral_next_index(default=0):
    """Next unscanned spiral waypoint index (SURVEY_SPIRAL_KEY "next_index");
    default when missing or the stored progress is not a dict."""
    return archive.get_dict(SURVEY_SPIRAL_KEY).get("next_index", default)


class VehicleSurveyMixin:
    """
    Sonar field operations, mixed into VehicleController; SurveyJob
    (lib/job_survey.py) runs them as the Scout role. Depends on
    VehicleClaimsMixin for target reservation and VehicleEnergyMixin/
    VehicleNavigationMixin for trip budgeting & driving.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def scan_and_survey(self, mission=None):
        """
        Scans the local area and surveys discovered sites. mission is the
        target being scanned (default: the vehicle's current mission); an
        unresolved contact is blacklisted under its target_key.
        """
        log = self._host.log
        if mission is None:
            mission = self._host.mission
        target_key = mission.target_key if mission is not None else None
        log.trace(f"[{self._host.name}] scan_and_survey() enter")
        self.last_scan_status = "unavailable"
        if not hasattr(self._host.vehicle, "sonar"):
            log.level("error").print(f"[{self._host.name}] Error: No SonarModule mounted!")
            return []

        log.start(f"[{self._host.name}] Sonar sweep")
        log.debug(f"[{self._host.name}] scan_and_survey(): target_key={target_key!r}")
        self._host.publish_telemetry("SCANNING", mission.target.get("name") if mission is not None else None)
        res = self._host.vehicle.sonar.scan()
        self.last_scan_status = res.status
        blocked = getattr(res, "blocked", [])
        log.debug(f"[{self._host.name}] sonar.scan() -> status={res.status!r}, message={getattr(res, 'message', '')!r}, sites={[getattr(s, 'id', s) for s in getattr(res, 'sites', [])]}, blocked={[(c.x, c.y, c.reason) for c in blocked]}")
        if res.status not in ["ok", "too_hard", "tier_too_low", "research_required", "wrong_scanner"]:
            log.level("warn").print(f"[{self._host.name}] Sonar scan status: {res.status} - {res.message}")
            log.end(f"[{self._host.name}] Sonar sweep failed: {res.status}")
            return []

        # A wide/deep sonar's range routinely covers several "?" contacts at
        # once (scan stops group them, lib/scan_groups.py), each possibly blocked
        # for a DIFFERENT reason -- so this can't collapse onto a single
        # single target_key the way scan()'s own top-level .status
        # does (that's one verdict for the whole sweep: "ok" as soon as ANY
        # contact in range resolves, even if the vehicle's own target stayed
        # unclassified). SonarScanResult.blocked gives the real per-contact
        # x/y/reason/message instead (see docs/types/fleet_and_vehicles.md
        # BlockedContact), so blacklist each one by its own coordinates.
        for contact in blocked:
            key = f"poi_{contact.x}_{contact.y}"
            log.level("warn").print(f"[{self._host.name}] Blocked contact at ({contact.x}, {contact.y}): {contact.reason} - {contact.message}")
            log.debug(f"[{self._host.name}] Blacklisting {key} (reason={contact.reason!r}).")
            self._host.blacklist_target(key, contact.reason, contact.message, scanner_type="sonar")

        sites = getattr(res, "sites", [])
        if res.status == "ok" and target_key:
            still_blocked = any(f"poi_{c.x}_{c.y}" == target_key for c in blocked)
            if not still_blocked:
                log.debug(f"[{self._host.name}] Scan resolved cleanly; clearing any prior unsupported entry for {target_key!r}.")
                self._host.clear_unsupported_target(target_key)

        # The sweep also resolves other contacts in range, which may carry a
        # blacklist entry (and marker) from an earlier weaker sonar. A Site
        # sits at its "?" contact's exact coordinates, and .sites never holds
        # a blocked contact, so each resolved site clears its own poi_X_Y.
        for s in sites:
            try:
                key = f"poi_{int(s.x)}_{int(s.y)}"
            except (AttributeError, TypeError, ValueError):
                continue
            if key != target_key:
                self._host.clear_unsupported_target(key)

        surveyed_sites = []
        seismic = self.sonar_tier() == "seismic"
        for s in sites:
            if seismic and self._needs_deep_oil_survey(s):
                surveyed_sites.append(self._survey_deep_oil(s))
            elif not getattr(s, "surveyed", False):
                log.print(f"[{self._host.name}] Surveying site {s.id} ({s.kind()})...")
                s_res = self._host.vehicle.sonar.survey(s.id)
                log.debug(f"[{self._host.name}] sonar.survey({s.id!r}) -> status={s_res.status!r}")
                if s_res.status == "ok":
                    self._host.clear_unsupported_target(f"site_{s.id}")
                    surveyed_sites.append(s_res.site)
                elif s_res.status in ["too_hard", "tier_too_low", "research_required", "wrong_scanner"]:
                    log.level("warn").print(f"[{self._host.name}] Site {s.id} survey limitation: {s_res.status} - {s_res.message}")
                    self._host.blacklist_target(f"site_{s.id}", s_res.status, s_res.message, scanner_type="sonar")
                    surveyed_sites.append(s)
                else:
                    surveyed_sites.append(s)
            else:
                surveyed_sites.append(s)
            flush_all()
            sleep(0.5)

        log.end(f"[{self._host.name}] Sonar sweep done: {len(sites)} site(s) in range, {len(surveyed_sites)} returned")
        log.trace(f"[{self._host.name}] scan_and_survey() exit: {len(sites)} candidate site(s) in range, {len(surveyed_sites)} returned.")
        return surveyed_sites

    def sonar_tier(self):
        """Mounted sonar's tier name ("basic" ... "seismic"), None without a readable sonar."""
        sonar = getattr(self._host.vehicle, "sonar", None)
        if not sonar:
            return None
        try:
            return sonar.tier()
        except Exception as error:
            swallowed("vehicle_survey.VehicleSurveyMixin.sonar_tier: sonar.tier", error)
            return None

    def _needs_deep_oil_survey(self, site):
        """
        True for an inert formation a Seismic survey still has to settle. The
        scan's site objects may carry the status from before the sweep, so
        anything not known dry is surveyed: a dry one costs nothing, a
        reservoir becomes an Oil Well (lib/deep_oil.py).
        """
        kind = getattr(site, "kind", None)
        if not callable(kind) or kind() != "inert":
            return False
        return getattr(site, "seismic_status", "unscanned") != "dry"

    def _survey_deep_oil(self, site):
        """Seismic survey of one inert formation; returns the resulting site (an OilWell on a reservoir)."""
        log = self._host.log
        res = self._host.vehicle.sonar.survey(site.id)
        log.debug(f"[{self._host.name}] deep-oil sonar.survey({site.id!r}) -> status={res.status!r}")
        if res.status != "ok":
            log.level("warn").print(f"[{self._host.name}] Deep-oil survey of {site.id} failed: {res.status} - {res.message}")
            return site
        result = getattr(res, "site", None) or site
        kind = getattr(result, "kind", None)
        if callable(kind) and kind() == "oil":
            log.print(f"[{self._host.name}] Deep oil reservoir confirmed at {site.id} ({site.x:.0f}, {site.y:.0f}): new Oil Well.")
        else:
            log.debug(f"[{self._host.name}] {site.id} is dry.")
        return result

    def deep_oil_targets(self):
        """
        Inert formations this vehicle should visit for deep oil: only with
        Seismic Sonar mounted (other tiers never learn a formation's status,
        so ordinary scouts never route here), nearest home first.
        """
        if self.sonar_tier() != "seismic":
            return []
        journal = get_component("journal")
        if not journal or not hasattr(journal, "discovered_sites"):
            return []
        try:
            state = deep_oil.prospect(journal.discovered_sites("nocturna"))
        except Exception as error:
            swallowed("vehicle_survey.VehicleSurveyMixin.deep_oil_targets: journal.discovered_sites", error)
            return []
        sites = deep_oil.targets(state)
        home = self._host.assigned_slot_coords
        sites.sort(key=lambda s: self._host.distance_between(home, (s.x, s.y)))
        self._host.log.debug(f"[{self._host.name}] deep_oil_targets(): {len(state['potential'])} potential, {len(state['unscanned'])} unscanned, {state['found']} found, {state['remaining']} unaccounted.")
        return sites

    def sonar_signature(self):
        """Returns the mounted sonar capability used for retry decisions."""
        sonar = getattr(self._host.vehicle, "sonar", None)
        if not sonar:
            return "none"
        try:
            return f"{sonar.tier()}:{sonar.range()}:{sonar.hardness_limit()}"
        except Exception as error:
            swallowed("vehicle_survey.VehicleSurveyMixin.sonar_signature: sonar.tier", error)
            return "unknown"

    def remember_sonar_retry(self, coords):
        """Remember a limited contact until sonar capability changes."""
        target_key = f"poi_{int(round(coords[0]))}_{int(round(coords[1]))}"
        status = getattr(self, "last_scan_status", "unknown")
        self._host.blacklist_target(target_key, status, f"Scan limited: {status}", scanner_type="sonar")

    def unscanned_pois(self):
        """Returns known map contacts that still need a vehicle sonar scan."""
        log = self._host.log
        log.start(f"[{self._host.name}] unscanned_pois", level="debug")
        log.trace("unscanned_pois() enter")
        planet = get_component("nocturna")
        if not planet or not hasattr(planet, "points_of_interest"):
            log.trace("unscanned_pois() exit: no 'nocturna' points_of_interest available.")
            log.end()
            return []
        try:
            unsupported_targets = self._host.get_unsupported_targets()
            existing_claims = self._host.get_claims()
            curr_tick = self._host.get_current_tick()
            points = []
            for point in planet.points_of_interest():
                if getattr(point, "scanned", False):
                    continue
                key = f"poi_{point.x}_{point.y}"

                # Check unsupported / blacklisted targets across fleet
                # (legacy 'X:Y' pioneer keys arrive renamed to 'poi_X_Y')
                target_entry = unsupported_targets.get(key)
                if target_entry:
                    can_attempt, attempt_reason = self._host.can_attempt_target(key, target_entry)
                    log.trace(f"{key}: unsupported entry found (reason={target_entry.get('reason', target_entry.get('status'))!r}) -> can_attempt={can_attempt} ({attempt_reason})")
                    if not can_attempt:
                        continue
                else:
                    log.trace(f"{key}: no unsupported entry on record.")

                # Check if claimed by another active vehicle (Rover, Pioneer, or peer)
                claim = existing_claims.get(key)
                if claim and (claim.get("vehicle") != self._host.name and claim.get("rover") != self._host.name):
                    claim_age = curr_tick - claim.get("tick", 0)
                    if is_fresh(claim, curr_tick, self._host.CLAIM_STALE_TICKS):
                        log.trace(f"{key}: skipped, actively claimed by {claim.get('vehicle', claim.get('rover'))} ({claim_age} ticks ago).")
                        continue

                points.append(point)
            home = self._host.assigned_slot_coords
            points.sort(key=lambda p: self._host.distance_between(home, (p.x, p.y)))
            log.trace(f"unscanned_pois() exit: {len(points)} candidate(s), nearest-first from {home}.")
            log.end()
            return points
        except Exception as error:
            swallowed("vehicle_survey.VehicleSurveyMixin.unscanned_pois: self._host.get_unsupported_targets", error)
            log.end()
            return []
        log.end()

    def unsurveyed_known_sites(self):
        """
        Known Sites already classified by sonar (kind revealed) but never fully
        surveyed -- typically because a previous sonar.survey() call failed with
        too_hard/tier_too_low. These sites are invisible to unscanned_pois()
        because PointOfInterest.scanned flips True the moment scan() classifies
        the contact, independent of whether survey() itself ever succeeds --
        without this, a capability-blocked site would never be revisited again,
        even after a sonar upgrade or a new scan research unlock. Only returns
        sites can_attempt_target() says are actually worth another try (compares
        the mounted sonar's current tier/hardness/range and unlocked scan
        researches against what was recorded at blacklist time), so the vehicle
        doesn't repeatedly drive back to a site nothing has changed for.
        """
        log = self._host.log
        log.start(f"[{self._host.name}] unsurveyed_known_sites", level="debug")
        journal = get_component("journal")
        if not journal or not hasattr(journal, "discovered_sites"):
            log.end()
            return []
        try:
            unsupported_targets = self._host.get_unsupported_targets()
            existing_claims = self._host.get_claims()
            curr_tick = self._host.get_current_tick()
            sites = []
            for site in journal.discovered_sites("nocturna"):
                if getattr(site, "surveyed", False):
                    continue
                key = f"site_{site.id}"

                target_entry = unsupported_targets.get(key)
                if target_entry:
                    can_attempt, attempt_reason = self._host.can_attempt_target(key, target_entry)
                    log.trace(f"{key}: unsupported entry found (reason={target_entry.get('reason', target_entry.get('status'))!r}) -> can_attempt={can_attempt} ({attempt_reason})")
                    if not can_attempt:
                        continue
                else:
                    log.trace(f"{key}: no unsupported entry on record.")

                claim = existing_claims.get(key)
                if claim and (claim.get("vehicle") != self._host.name and claim.get("rover") != self._host.name):
                    claim_age = curr_tick - claim.get("tick", 0)
                    if is_fresh(claim, curr_tick, self._host.CLAIM_STALE_TICKS):
                        log.trace(f"{key}: skipped, actively claimed by {claim.get('vehicle', claim.get('rover'))} ({claim_age} ticks ago).")
                        continue

                sites.append(site)
            home = self._host.assigned_slot_coords
            sites.sort(key=lambda s: self._host.distance_between(home, (s.x, s.y)))
            log.end()
            return sites
        except Exception as error:
            swallowed("vehicle_survey.VehicleSurveyMixin.unsurveyed_known_sites: self._host.get_unsupported_targets", error)
            log.end()
            return []
        log.end()

    def survey_spiral_points(self, step=None, start_index=0, max_points=160):
        """Yields indexed outward square-spiral waypoints spaced for the mounted sonar."""
        sonar = getattr(self._host.vehicle, "sonar", None)
        if not sonar:
            return

        if step is None:
            step = max(20.0, sonar_range(self._host.vehicle, "vehicle_survey.VehicleSurveyMixin.survey_spiral_points: sonar.range") * 0.75)

        x, y = self._host.assigned_slot_coords
        directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        direction_index = 0
        leg_length = 1
        point_index = 0
        yielded = 0

        while yielded < max_points:
            for _ in range(2):
                dx, dy = directions[direction_index % len(directions)]
                for _ in range(leg_length):
                    x += dx * step
                    y += dy * step
                    if point_index >= start_index:
                        yield (point_index, x, y)
                        yielded += 1
                        if yielded >= max_points:
                            return
                    point_index += 1
                direction_index += 1
            leg_length += 1

    def save_survey_waypoint(self, point_index, coords, sites):
        """Publishes completed spiral progress to the shared Data Archive notebook."""
        site_summaries = []
        for site in sites or []:
            try:
                kind = site.kind() if hasattr(site, "kind") else getattr(site, "kind", "unknown")
            except Exception as error:
                swallowed("vehicle_survey.VehicleSurveyMixin.save_survey_waypoint: site.kind", error)
                kind = "unknown"
            site_summaries.append(
                {
                    "id": getattr(site, "id", None),
                    "kind": kind,
                    "x": getattr(site, "x", None),
                    "y": getattr(site, "y", None),
                    "surveyed": getattr(site, "surveyed", False),
                    "item_id": getattr(site, "item_id", None),
                }
            )

        def update_progress(current):
            progress = dict(current) if isinstance(current, dict) else {}
            waypoints = list(progress.get("waypoints", []))
            entry = {
                "index": point_index,
                "coords": [coords[0], coords[1]],
                "sites": site_summaries,
            }
            if not any(item.get("index") == point_index for item in waypoints):
                waypoints.append(entry)
            progress["waypoints"] = waypoints
            progress["next_index"] = max(point_index + 1, progress.get("next_index", 0))
            progress["last_completed"] = entry
            progress["updated_by"] = self._host.name
            return progress

        archive.transaction(SURVEY_SPIRAL_KEY, {}, update_progress)

    def survey_known_pois(self, max_points=20):
        """Scans multiple known contacts in one battery-safe outward route."""
        completed = 0
        visited = set()

        # A target restored from a saved mission (see vehicle_claims.py) after
        # a script reload takes priority over discovery, so we continue toward
        # the same destination instead of restarting the search from scratch.
        resumed = None
        mission = self._host.mission
        if mission is not None and mission.target_key and mission.target.get("coords"):
            resumed = (mission.target_key, tuple(mission.target["coords"]))
            self._host.log.print(f"[{self._host.name}] Resuming previously claimed POI '{resumed[0]}' at {resumed[1]} after reload.")

        while completed < max_points:
            current_pos = self._host.get_position()

            if resumed:
                target_key, target = resumed
                resumed = None
                target_label = "resumed target"
                extra_keys = []
            else:
                # Three pools: fresh "?" contacts to scan, already-classified
                # sites that may now succeed after sonar/research upgrades
                # (see unsurveyed_known_sites()), and, with Seismic Sonar,
                # inert formations that may hide deep oil (deep_oil_targets()).
                # Merged into one distance-sorted route so the vehicle doesn't
                # need a separate pass for each.
                candidates = (
                    [{"key": f"poi_{p.x}_{p.y}", "coords": (p.x, p.y), "label": "unscanned POI"} for p in self.unscanned_pois() if (p.x, p.y) not in visited]
                    + [{"key": f"site_{s.id}", "coords": (s.x, s.y), "label": f"unsurveyed site {s.id}"} for s in self.unsurveyed_known_sites() if (s.x, s.y) not in visited]
                    + [{"key": f"site_{s.id}", "coords": (s.x, s.y), "label": f"inert formation {s.id} (deep oil, {getattr(s, 'seismic_status', '?')})"} for s in self.deep_oil_targets() if (s.x, s.y) not in visited]
                )
                requests = read_requests()
                requested = [c for c in candidates if request_at(c["coords"][0], c["coords"][1], requests) is not None]
                rest = [c for c in candidates if request_at(c["coords"][0], c["coords"][1], requests) is None]
                weights = self.outpost_weights(candidates)
                stops = self.scan_stops(requested, current_pos, weights) + self.scan_stops(rest, current_pos, weights)
                self._host.log.debug(f"[{self._host.name}] survey_known_pois(): {len(candidates)} candidate(s) in {len(stops)} scan stop(s) from {current_pos}, {len(requested)} in {len(requests)} survey request area(s) first.")

                chosen = None
                for stop in stops:
                    budget = self._host.calculate_trip_energy(stop["coords"], planned_scans=4)
                    if budget["is_achievable"]:
                        self._host.log.debug(f"[{self._host.name}] survey_known_pois(): chose stop {stop['coords']} for {stop['keys']}, budget={budget['total_required_wh']:.1f} Wh.")
                        chosen = stop
                        visited.update(stop["members"])
                        break
                    else:
                        self._host.log.debug(f"[{self._host.name}] survey_known_pois(): rejected stop {stop['coords']} for {stop['keys']}, unreachable within budget ({budget['total_required_wh']:.1f} Wh required).")
                if chosen is None:
                    if candidates:
                        self._host.log.print(f"[{self._host.name}] Remaining known POIs/sites exceed the current route budget; returning home.")
                    break

                target = chosen["coords"]
                target_key = chosen["keys"][0]
                target_label = chosen["label"]
                extra_keys = chosen["keys"][1:]

            self._host.log.start(f"[{self._host.name}] Surveying known {target_label} at {target} ({self._host.distance_between(current_pos, target):.1f} m leg)")
            scanned, stop = self._survey_poi_leg(target_key, target, completed, extra_keys)
            self._host.log.end(f"[{self._host.name}] {'POI scan complete' if scanned else 'POI leg aborted'}")
            if scanned:
                completed += 1
            if stop:
                break
        if completed:
            self._host.log.print(f"[{self._host.name}] Completed {completed} POI scans on one outward route; returning home.")
        return completed

    def scan_reach(self):
        """Radius one scan stop may cover: the mounted sonar's range (vehicle_claims.sonar_range()) times
        scan_groups.COVER_MARGIN; 0.0 (stand on the target) without a sonar."""
        if not getattr(self._host.vehicle, "sonar", None):
            return 0.0
        return sonar_range(self._host.vehicle, "vehicle_survey.VehicleSurveyMixin.scan_reach: sonar.range") * COVER_MARGIN

    def outpost_weights(self, candidates):
        """
        {key: OUTPOST_WEIGHT} for candidates within
        outpost_mining.resource_assignment_range_m() of any outpost: a site
        there is minable without a long haul, so scan_stops() values it
        like a small cluster.
        """
        outposts = outpost_mining.outpost_positions()
        if not outposts:
            return {}
        range2 = outpost_mining.resource_assignment_range_m() ** 2
        weights = {}
        for c in candidates:
            x, y = c["coords"]
            for _, ox, oy in outposts:
                if (x - ox) * (x - ox) + (y - oy) * (y - oy) <= range2:
                    weights[c["key"]] = OUTPOST_WEIGHT
                    break
        return weights

    def scan_stops(self, candidates, current_pos, weights=None):
        """
        Scan stops over survey candidates (lib/scan_groups.py): one sweep per
        stop covers every member. weights: {key: weight} from
        outpost_weights(), 1 when absent. Returns [{"keys", "members"
        (coords), "coords" (where to stand), "label"}], most weighted
        contacts per metre first.
        """
        if not candidates:
            return []
        stops = []
        home = self._host.assigned_slot_coords
        tick = self._host.get_current_tick()
        weights = weights or {}
        planned = plan_stops_atomic([c["coords"] for c in candidates], self.scan_reach(), current_pos, home, [weights.get(c["key"], 1) for c in candidates])
        self._host.log.debug(f"[{self._host.name}] scan_stops(): {len(candidates)} candidate(s), {len(planned)} stop(s) in {self._host.get_current_tick() - tick} tick(s).")
        for stop in planned:
            members = [candidates[i] for i in stop["members"]]
            label = members[0]["label"] if len(members) == 1 else f"group of {len(members)} contacts"
            if any(m["key"] in weights for m in members):
                label += " near outpost"
            stops.append(
                {
                    "keys": [m["key"] for m in members],
                    "members": [m["coords"] for m in members],
                    "coords": stop["stand"],
                    "label": label,
                }
            )
        return stops

    def _survey_poi_leg(self, target_key, target, completed, extra_keys=()):
        """
        Drives to one scan stop and sweeps it; returns (scanned, stop_pass).
        target_key is the stop's first member, extra_keys the others it
        covers: each is claimed so peers skip it, and released after. A peer
        that planned at the same time may win some claims; the stop goes
        ahead on the ones won here and is skipped when none were won.
        """
        won = [key for key in [target_key] + list(extra_keys) if self._host.claim_target(key, {"coords": target, "name": key, "type": "poi"})]
        if not won:
            self._host.log.print(f"[{self._host.name}] Every contact at stop {target} is claimed by a peer; picking another stop.")
            return False, False
        target_key = won[0]
        extra_keys = won[1:]
        mission = Mission(kind="poi_survey", target_key=target_key, target={"coords": target, "name": target_key, "type": "poi"}, source="poi")
        self._host.begin_mission(mission, claimed=True)
        self._host.set_intent(f"surveying POI_{target[0]:.0f}_{target[1]:.0f}")
        self._host.publish_telemetry("SURVEY_POI", f"POI_{target[0]:.0f}_{target[1]:.0f}")
        if not self._host.drive_to(target[0], target[1]):
            self._host.log.level("warn").print(f"[{self._host.name}] Could not safely reach POI at {target}; ending survey pass.")
            self._release_extra_claims(extra_keys)
            self._host.release_target_claim(target_key)
            return False, True
        self._host.vehicle.nav.brake()
        scan_reserve = self._host.SONAR_WH_BUDGET * 4 * self._host.SAFETY_MARGIN_MULTIPLIER
        # Comfortable reserve, not the bare floor -- keeps the return leg fast.
        if self._host.get_battery()[0] <= self._host.energy_needed_to_return_comfortably() + scan_reserve:
            self._host.log.level("warn").print(f"[{self._host.name}] Insufficient energy to scan POI at {target}; returning home.")
            self._release_extra_claims(extra_keys)
            self._host.release_target_claim(target_key)
            return False, True
        sites = self.scan_and_survey(mission)
        self._release_extra_claims(extra_keys)
        self._host.release_target_claim(target_key)
        self.save_survey_waypoint(completed, target, sites)
        return True, self._host.get_battery()[0] < self._host.energy_needed_to_return_comfortably()

    def _release_extra_claims(self, keys):
        for key in keys:
            self._host.release_target_claim(key)
