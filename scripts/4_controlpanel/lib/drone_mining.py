# Drone role: biosite miner (harvester). Builds candidates from
# journal.biomass_coords(), filters to this drone's home outpost's biome
# (drone_cargo.py's is_home_biome_sample() -- only native-biome samples
# process at the Essence Liquifier), exclusive-claims a ready site
# (journal.is_ready() cooldown gate + drone_claims.py's claim_biosite(), NOT
# mining_reservations.py's shared yield-debit pattern -- biosite extraction
# is exclusive-with-cooldown, not shared, see docs/AI_CHEATSHEET.md), flies
# out, extract()s in a loop until the site depletes or cargo fills, returns
# to its home Drone Depot (get_home_depot()), unloads, releases the claim.
#
# Open question flagged in the plan: whether bio_extractor.extract() can
# target a specific species at a mixed-biome tile, or always pulls whatever
# is present. docs/types/biosphere.md's PortableBioExtractor.extract() takes
# NO arguments at all (no species/item_id parameter) -- so it cannot target a
# specific species; it always pulls whatever occupies that site's chamber.
# This confirms the plan's v1 default is the only safe option:
# _biosite_candidates() below skips any biosite where a non-home-biome
# sample is ALSO present at the same tile, rather than risking extract()
# pulling the wrong species into a chamber that can't be processed locally.

from tree_console import TreeConsole
import logistics_requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController


# Extra pull on a biosite per requested (logistics_requests) life form it
# still holds, by rarity -- rare forms sit on few sites with long cooldowns,
# so a site holding one is worth a detour first.
RARITY_REQUEST_WEIGHT = {"common": 1, "uncommon": 2, "rare": 4}


class DroneMiningMixin:

    # Wait before retrying an unload at a full Drone Depot (10 ticks/s,
    # so ~30 s). The drone charges at its drone_service meanwhile.
    DEPOT_FULL_RETRY_TICKS = 300

    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    def _biosite_candidates(self):
        """
        [{"coords", "target_key", "sample_type", "remaining_tons"}, ...] for
        every discovered permanent biosite that is entirely native to this
        drone's home biome and currently journal.is_ready() (cooldown gate,
        checked before even attempting a claim -- see module docstring).
        Sorted by request score first (sites holding life forms another
        outpost currently requests via lib/logistics_requests.py, weighted by
        RARITY_REQUEST_WEIGHT; 0 everywhere when nothing is requested), then
        partially-drained sites, then by distance.
        """
        self._host.log.trace(f"[{self._host.name}] _biosite_candidates() entry.")
        journal = get_component("journal")
        if not journal or not self._host.home_biome:
            self._host.log.debug(f"[{self._host.name}] _biosite_candidates(): missing journal or unknown home_biome; returning no candidates.")
            return []

        try:
            sites = journal.biomass_coords()
        except Exception:
            sites = []

        pos = self._host.position()
        try:
            requested = logistics_requests.network_deficits()
        except Exception:
            requested = {}
        candidates = []
        skipped_no_home_forms = 0
        skipped_mixed_biome = 0
        skipped_cooling = 0
        for site in sites:
            coord = getattr(site, "coord", None)
            life_forms = getattr(site, "life_forms", []) or []
            if not coord or not life_forms:
                continue
            x, y = int(coord[0]), int(coord[1])

            home_forms = [lf for lf in life_forms if self._host.is_home_biome_sample(getattr(lf, "type", None))]
            if not home_forms:
                skipped_no_home_forms += 1
                continue
            if len(home_forms) != len(life_forms):
                # Mixed-biome tile: extract() takes no species argument (see
                # module docstring), so v1 skips this site entirely rather
                # than risk pulling the wrong species.
                skipped_mixed_biome += 1
                self._host.log.trace(f"[{self._host.name}] Biosite ({x}, {y}) skipped: mixed-biome tile ({len(home_forms)}/{len(life_forms)} home-biome samples).")
                continue
            if not journal.is_ready(x, y):
                skipped_cooling += 1
                continue

            sample = home_forms[0]
            remaining = float(getattr(sample, "remaining_tons", 0.0) or 0.0)
            peak = float(getattr(sample, "tons", 0.0) or 0.0)
            # A site's cooldown/regrowth only starts once it is fully empty
            # (biosphere.md: "Partial depletion persists and cooldown starts
            # only when the site is empty"), so a half-drained site left
            # sitting is dead time on its regen clock.
            partial = 0.0 < remaining < peak
            request_score = 0
            for lf in home_forms:
                lf_type = getattr(lf, "type", None)
                if requested.get(lf_type, 0) > 0 and float(getattr(lf, "remaining_tons", 0.0) or 0.0) > 0:
                    request_score += RARITY_REQUEST_WEIGHT.get(getattr(lf, "rarity", "common"), 1)
            candidates.append({
                "coords": (x, y),
                "target_key": f"bio_{x}_{y}",
                "sample_type": getattr(sample, "type", None),
                "remaining_tons": remaining,
                "partial": partial,
                "request_score": request_score,
            })

        # Partially-drained sites first (finish them so their cooldown can
        # start), then nearest. select_biosite_target() still skips any
        # candidate the drone can't afford, so a far partial site only wins
        # when it's reachable.
        candidates.sort(key=lambda c: (-c["request_score"], not c["partial"], self._host.distance_between(pos, c["coords"])))
        requested_sites = [c for c in candidates if c["request_score"] > 0]
        if requested_sites:
            self._host.log.debug(
                f"[{self._host.name}] _biosite_candidates(): {len(requested_sites)} site(s) hold requested life forms (deficits {requested}); visiting first: "
                + ", ".join(f"{c['target_key']}(score {c['request_score']})" for c in requested_sites)
            )
        elif requested:
            self._host.log.debug(f"[{self._host.name}] _biosite_candidates(): requests {requested} but no ready home-biome site holds them; normal order.")
        partial_count = sum(1 for c in candidates if c["partial"])
        if partial_count:
            self._host.log.debug(
                f"[{self._host.name}] _biosite_candidates(): prioritizing {partial_count} partially-drained site(s): "
                + ", ".join(f"{c['target_key']}={c['remaining_tons']:.1f}t" for c in candidates if c["partial"])
            )
        self._host.log.debug(
            f"[{self._host.name}] _biosite_candidates(): {len(sites)} known site(s), {len(candidates)} ready home-biome candidate(s) "
            f"(skipped {skipped_no_home_forms} non-home, {skipped_mixed_biome} mixed-biome, {skipped_cooling} cooling-down)."
        )
        self._host.log.trace(f"[{self._host.name}] _biosite_candidates() exit: {len(candidates)} candidate(s).")
        return candidates

    def select_biosite_target(self, candidates):
        """
        First candidate this drone can both afford (calculate_trip_energy())
        and win the exclusive claim for -- mirrors vehicle_claims.py's
        claim-after-filter race pattern (a peer miner drone may win the
        claim between this drone's filter pass and its own claim attempt,
        so this tries the next candidate rather than giving up for the
        cycle).
        """
        self._host.log.trace(f"[{self._host.name}] select_biosite_target() entry: {len(candidates)} candidate(s).")
        for candidate in candidates:
            budget = self._host.calculate_trip_energy(candidate["coords"])
            if not budget["is_achievable"]:
                self._host.log.trace(f"[{self._host.name}] Biosite {candidate['target_key']}: {budget['total_required_wh']:.1f} Wh required, not achievable on current battery; skipping.")
                continue
            if self._host.claim_biosite(candidate["target_key"], {"coords": candidate["coords"], "name": candidate["target_key"]}):
                self._host.log.trace(f"[{self._host.name}] select_biosite_target() exit: claimed {candidate['target_key']}.")
                return candidate, budget
            self._host.log.debug(f"[{self._host.name}] Lost claim race on biosite {candidate['target_key']} to a peer drone; trying next candidate.")
        self._host.log.trace(f"[{self._host.name}] select_biosite_target() exit: no claimable candidate.")
        return None, None

    def run_miner_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_mining")
        log.print(f"Drone Miner Controller ({self._host.name}) online. Home biome: {self._host.home_biome or 'unknown'}.")
        self._adopt_interrupted_extraction(log)
        while True:
            try:
                if self._host.is_stranded():
                    log.level("warn").print(f"[{self._host.name}] {self._host.status()}; awaiting drone_service rescue.")
                    self._host.publish_telemetry("STRANDED")
                    sleep(poll_interval)
                    continue

                if self._host.handle_recall_if_active():
                    sleep(poll_interval)
                    continue

                self._host.cleanup_stale_biosite_claims()

                # Resume an in-progress mission after a script reload. A
                # drone's go_to() is CANCELLED by a script restart
                # (drone.md), unlike a rover's persistent drive command, so
                # re-validate the claim and physical position, then
                # re-issue the flight leg -- extract() itself resumes
                # transparently once physically there again (its own docs:
                # "stays occupied... including across a script stop and
                # restart").
                if self.current_target_key and self.current_target:
                    coords = tuple(self.current_target.get("coords", (0, 0)))
                    log.debug(f"[{self._host.name}] Resuming claimed target '{self.current_target_key}' after reload; re-validating position.")
                    if not self._host.is_at(coords, precision=1.0):
                        if not self._host.fly_to(coords[0], coords[1], precision=1.0):
                            log.level("warn").print(f"[{self._host.name}] Could not re-reach resumed target {coords}; will retry.")
                            sleep(poll_interval)
                            continue
                    self._extract_until_done(coords)
                    if not self._return_and_unload():
                        sleep(poll_interval)
                    continue

                curr_wh, _, _ = self._host.get_battery()
                if curr_wh <= self._host.energy_needed_to_return_comfortably():
                    self._host.return_to_service_for_charge(log, f"Battery low ({curr_wh:.1f} Wh)")
                    sleep(poll_interval)
                    continue

                if self._host.cargo_count() > 0:
                    now_tick = self._host.get_current_tick()
                    retry_tick = getattr(self, "_depot_full_retry_tick", 0)
                    if now_tick < retry_tick:
                        # Depot was full last try: stay docked at the
                        # drone_service (charging) until the backoff expires.
                        log.debug(f"[{self._host.name}] Depot full backoff: {retry_tick - now_tick} ticks left; charging at drone_service.")
                        self._host.return_to_service_for_charge(log, "Waiting for Drone Depot space")
                        self._host.publish_telemetry("WAITING_DEPOT_SPACE")
                        sleep(poll_interval)
                        continue
                    # Without the sleep a failed return (e.g. go_to "busy")
                    # retried in a tight loop and flooded the console.
                    if not self._return_and_unload():
                        sleep(poll_interval)
                    continue

                candidates = self._biosite_candidates()
                if not candidates:
                    log.debug(f"[{self._host.name}] No ready home-biome biosite candidates this cycle.")
                    self._host.publish_telemetry("IDLE_NO_TARGETS")
                    sleep(30.0)
                    continue

                target, budget = self.select_biosite_target(candidates)
                if not target or not budget:
                    log.debug(f"[{self._host.name}] {len(candidates)} candidate(s) found but none both reachable and claimable.")
                    self._host.publish_telemetry("IDLE_OUT_OF_RANGE")
                    _, _, lvl = self._host.get_battery()
                    if lvl < 0.98:
                        # See drone_scout.py's run_scout_loop() for why this is
                        # needed: without it, a drone too low on charge for any
                        # trip (but not low enough to trip the proactive-return
                        # check above) idles here forever instead of topping up.
                        self._host.return_to_service_for_charge(log, f"No candidate reachable at {lvl*100:.0f}% charge")
                    sleep(15.0)
                    continue

                self.current_target_key = target["target_key"]
                self.current_target = {"coords": target["coords"], "name": target["target_key"], "sample_type": target["sample_type"]}
                self._host.save_mission("mine", self.current_target)

                log.print(f"[{self._host.name}] Reserved biosite {target['target_key']} ({target['sample_type']}) at {target['coords']} (Est. trip cost: {budget['total_required_wh']:.1f} Wh).")
                self._host.publish_telemetry("OUTBOUND", target["target_key"])

                if not self._host.fly_to(target["coords"][0], target["coords"][1], precision=1.0):
                    log.level("warn").print(f"[{self._host.name}] Could not reach biosite {target['coords']}; releasing claim and retrying later.")
                    self._host.release_biosite_claim(target["target_key"])
                    sleep(poll_interval)
                    continue

                self._extract_until_done(target["coords"])
                if not self._return_and_unload():
                    sleep(poll_interval)
            except Exception as e:
                log.level("error").print(f"[{self._host.name}] Miner loop exception: {e}")
                try:
                    self._host.release_biosite_claim()
                except Exception:
                    pass
                sleep(5.0)

    def _adopt_interrupted_extraction(self, log):
        """
        Restart-during-extraction check, run once when the miner loop starts.
        extract() keeps the drone occupied across a script restart, so every
        go_to()/go_to_station() is rejected "busy" until it finishes. If no
        mission was resumed (load_mission() found none, or the claim was
        lost), the loop would otherwise pick a new target or try to unload,
        and fail on "busy" every cycle.

        detect_role()'s extract() probe already tells us: "busy" (old job
        still running) or "ok" (probe just harvested here) means the drone
        is hovering over a biosite mid-harvest. Adopt that site as the
        current mission, so the loop's resume branch keeps extracting until
        the site depletes or cargo fills, then unloads as normal.
        """
        probe = self._host.role_probe_status.get("bio_extractor")
        if probe not in ("busy", "ok"):
            return
        pos = self._host.position()
        coords = (int(round(pos[0])), int(round(pos[1])))
        key = f"bio_{coords[0]}_{coords[1]}"
        if self.current_target_key == key:
            log.debug(f"[{self._host.name}] Extract probe '{probe}' at {coords}; resumed mission already covers this site.")
            return
        if self.current_target_key:
            log.debug(f"[{self._host.name}] Extract probe '{probe}' at {coords} differs from resumed mission '{self.current_target_key}'; adopting the site the drone is actually on.")
            self._host.release_biosite_claim(self.current_target_key)
        if not self._host.claim_biosite(key, {"coords": coords, "name": key}):
            # Still finish here: the drone can't leave until the running
            # extract() ends anyway.
            log.level("warn").print(f"[{self._host.name}] Restarted mid-extraction at {coords}, but a peer holds the claim; finishing the running job anyway.")
        self.current_target_key = key
        self.current_target = {"coords": coords, "name": key, "sample_type": None}
        self._host.save_mission("mine", self.current_target)
        log.print(f"[{self._host.name}] Restarted mid-extraction at {coords} (probe: {probe}); resuming harvest there.")

    def _extract_until_done(self, coords):
        """
        Repeatedly bio_extractor.extract()s at coords until the site depletes
        (status "cooling") or cargo fills. extract() "stays occupied...
        including across a script stop and restart" per its own docs, so
        this loop needs no extra resumability handling itself -- only the
        flight leg to get here needed re-issuing (see run_miner_loop()).
        """
        self._host.log.trace(f"[{self._host.name}] _extract_until_done({coords}) entry.")
        settle_retries = 5
        while True:
            if self.current_target_key:
                self._host.refresh_biosite_claim(self.current_target_key)
            try:
                res = self._host.drone.bio_extractor.extract()
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Extraction call failed at {coords}: {e}")
                break

            if res.status == "ok":
                self._host.log.print(f"[{self._host.name}] Extracted {res.extracted:.1f}t at {coords}.")
                if self._host.cargo_full():
                    break
                continue
            elif res.status == "busy":
                sleep(1.0)
                continue
            elif res.status == "cooling":
                self._host.log.print(f"[{self._host.name}] Biosite {coords} depleted and cooling down; heading back.")
                break
            elif res.status == "not_at_location" and settle_retries > 0:
                # Route may still be settling into a hover; give it a few
                # seconds before giving up and flying home empty.
                settle_retries -= 1
                self._host.log.debug(f"[{self._host.name}] extract() not_at_location at {coords} (status={self._host.status()}, pos={self._host.position()}); retrying, {settle_retries} left.")
                sleep(1.0)
                continue
            else:
                self._host.log.level("warn").print(f"[{self._host.name}] Extraction notice at {coords}: {res.status} - {res.message}")
                break
        self._host.log.trace(f"[{self._host.name}] _extract_until_done({coords}) exit.")

    def _return_and_unload(self):
        """Flies to the home Depot and unloads. Returns True on success, False when the caller should back off before retrying."""
        self._host.log.trace(f"[{self._host.name}] _return_and_unload() entry.")
        depot_coords, depot_info = self._host.get_home_depot()
        depot_id = depot_info.get("id")
        self._host.publish_telemetry("RETURNING_TO_DEPOT")

        reached = bool(depot_id) and self._host.fly_to_station(depot_id, target_coords=depot_coords)
        if not reached and self._host.status() == "waiting_bay":
            # Arrived, but the bay got taken. With a pool home a sibling
            # depot may be free now: re-pick once and transfer (same coords,
            # no flight cost).
            alt_coords, alt_info = self._host.get_home_depot(prefer_id=depot_id)
            alt_id = alt_info.get("id")
            if alt_id and alt_id != depot_id:
                self._host.log.debug(f"[{self._host.name}] Depot '{depot_id}' bay taken; switching to free sibling '{alt_id}'.")
                depot_coords, depot_id = alt_coords, alt_id
                reached = self._host.fly_to_station(depot_id, target_coords=depot_coords)
        if not reached and self._host.status() == "waiting_bay":
            # Every home depot's bay is occupied. Falling back to fly_to()
            # would "arrive" instantly (same coords) and then unload into
            # nothing, since cargo.unload() needs a docked berth. Stay
            # queued and retry. Warn once per wait, not on every retry.
            already_waiting = self._host.state == "WAITING_DEPOT_BAY"
            msg = f"[{self._host.name}] Drone Depot '{depot_id}' has no free bay (waiting_bay); a docked drone is holding it. Retrying."
            if already_waiting:
                self._host.log.debug(msg)
            else:
                self._host.log.level("warn").print(msg)
            self._host.publish_telemetry("WAITING_DEPOT_BAY")
            return False
        if not reached:
            self._host.log.debug(f"[{self._host.name}] fly_to_station({depot_id}) unavailable or failed; falling back to direct fly_to({depot_coords}).")
            reached = self._host.fly_to(depot_coords[0], depot_coords[1], precision=1.5)
        if not reached:
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach Drone Depot to unload; will retry.")
            return False

        unloaded = self._host.unload_cargo_at_depot()
        if unloaded < 0:
            self._host.log.level("warn").print(f"[{self._host.name}] Drone Depot has no free slot for this cargo; leaving aboard until space opens.")
            self._host.publish_telemetry("WAITING_DEPOT_SPACE")
        elif unloaded > 0:
            self._host.log.print(f"[{self._host.name}] Unloaded {unloaded} units at Drone Depot.")

        if unloaded < 0:
            self._depot_full_retry_tick = self._host.get_current_tick() + self.DEPOT_FULL_RETRY_TICKS
            self._host.log.debug(f"[{self._host.name}] Depot full; parking at drone_service to charge, next unload attempt in {self.DEPOT_FULL_RETRY_TICKS} ticks.")

        self._host.release_biosite_claim()
        # Leave the berth now, even with no next mining target picked yet --
        # a miner otherwise sits docked here between trips, occupying a bay
        # a peer drone (or this one, on a later retry) may be waiting in
        # line for. Also releases the bay when the Depot is full (unloaded
        # < 0): staying docked wouldn't make its stuck cargo unloadable any
        # sooner, but it would keep the bay from a drone unloading a
        # different item that DOES have space.
        self._host.leave_station()
        if unloaded < 0:
            # Re-docking at a full depot every few seconds burns time and
            # battery for nothing. Charge at the drone_service instead; the
            # miner loop holds the drone there until the retry tick passes.
            self._host.return_to_service_for_charge(self._host.log, "Drone Depot full")
            self._host.publish_telemetry("WAITING_DEPOT_SPACE")
        else:
            self._host.publish_telemetry("READY_AT_DEPOT")
        self._host.log.trace(f"[{self._host.name}] _return_and_unload() exit: unloaded={unloaded}.")
        # Depot full counts as failure: cargo is still aboard, so the caller
        # should back off before retrying.
        return unloaded >= 0
