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
#
# Once biomass is complete (lib/biomass_retire.py) there is no Liquifier left
# to feed, and mixed-biome tiles are fair game. Sites holding a life form some
# outpost requests (the Seed Maker, lib/logistics_requests.py) go first. Next
# come sites holding a form whose stock at the drone's home outpost is below
# the Warehouse buffer (lib/drone_depot.py lifeform_buffer_cap()), so every
# form is on hand for creature feed. Sites holding neither are skipped unless
# partly drained with a requested form. Each visited site is drained fully so
# its cooldown starts; forms that come along past their buffer wait in the
# Drone Depot, which flushes them only as a last resort (flush_surplus()).

from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed
import logistics_requests
import fleet_intent
from biomass_retire import biomass_complete
from drone_depot import lifeform_buffer_cap
from storage import warehouse_stocks
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from drone import DroneController


# Extra pull on a biosite per requested (logistics_requests) or
# below-buffer life form it still holds, by rarity -- rare forms (the fungi:
# one site per biome, 36 h regrowth) sit on few sites with long cooldowns, so
# a site holding one is worth a detour first.
RARITY_REQUEST_WEIGHT = {"common": 1, "uncommon": 2, "rare": 4}


class DroneMiningMixin:

    # Wait before retrying an unload at a full Drone Depot (10 ticks/s,
    # so ~30 s). The drone hovers at the Depot meanwhile (hover_wait()),
    # flying to a drone_service only below LAUNCH_MIN_SOC.
    DEPOT_FULL_RETRY_TICKS = 300
    # After this many full-Depot unload failures in a row, cargo another
    # Depot outpost requests is delivered there instead (_deliver_elsewhere()).
    DEPOT_FULL_STALL_ATTEMPTS = 3

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
        partially-drained sites, then (after biomass completion) buffer need
        (forms below lifeform_buffer_cap() at the home outpost, weighted by
        RARITY_REQUEST_WEIGHT), then by distance.
        """
        self._host.log.start(f"[{self._host.name}] _biosite_candidates()", level="debug")
        self._host.log.trace("_biosite_candidates() entry.")
        journal = get_component("journal")
        if not journal or not self._host.home_biome:
            self._host.log.debug("missing journal or unknown home_biome; returning no candidates.")
            self._host.log.end()
            return []

        try:
            sites = journal.biomass_coords()
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin._biosite_candidates: journal.biomass_coords", error)
            sites = []

        pos = self._host.position()
        try:
            requested = logistics_requests.network_deficits()
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin._biosite_candidates: logistics_requests.network_deficits", error)
            requested = {}
        retired = biomass_complete()
        # Every life form any outpost requests, satisfied or not: a partly
        # drained site holding one is finished even with the request met,
        # or it never cools down and regrows.
        wanted_types = set()
        short_forms = {}
        if retired:
            for items in logistics_requests.active_requests().values():
                wanted_types.update(items.keys())
            short_forms = self._buffer_shortfalls(sites)
        candidates = []
        skipped_no_home_forms = 0
        skipped_mixed_biome = 0
        skipped_cooling = 0
        skipped_unneeded = 0
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
            if len(home_forms) != len(life_forms) and not retired:
                # Mixed-biome tile: extract() takes no species argument (see
                # module docstring), so v1 skips this site entirely rather
                # than risk pulling the wrong species.
                skipped_mixed_biome += 1
                self._host.log.trace(f"Biosite ({x}, {y}) skipped: mixed-biome tile ({len(home_forms)}/{len(life_forms)} home-biome samples).")
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
            if retired:
                amounts = [(float(getattr(lf, "remaining_tons", 0.0) or 0.0), float(getattr(lf, "tons", 0.0) or 0.0)) for lf in life_forms]
                partial = any(r < p for r, p in amounts) and any(r > 0 for r, _p in amounts)
            request_score = 0
            for lf in (life_forms if retired else home_forms):
                lf_type = getattr(lf, "type", None)
                if requested.get(lf_type, 0) > 0 and float(getattr(lf, "remaining_tons", 0.0) or 0.0) > 0:
                    request_score += RARITY_REQUEST_WEIGHT.get(getattr(lf, "rarity", "common"), 1)
            buffer_need = 0
            if retired:
                buffer_need = sum(RARITY_REQUEST_WEIGHT.get(getattr(lf, "rarity", "common"), 1) for lf in life_forms if short_forms.get(getattr(lf, "type", None), 0) > 0 and float(getattr(lf, "remaining_tons", 0.0) or 0.0) > 0)
            if retired and request_score == 0 and buffer_need == 0 and not (partial and any(getattr(lf, "type", None) in wanted_types for lf in life_forms)):
                skipped_unneeded += 1
                continue
            candidates.append({
                "coords": (x, y),
                "target_key": f"bio_{x}_{y}",
                "sample_type": getattr(sample, "type", None),
                "remaining_tons": remaining,
                "partial": partial,
                "request_score": request_score,
                "buffer_need": buffer_need,
            })

        # Partially-drained sites first (finish them so their cooldown can
        # start), then nearest. select_biosite_target() still skips any
        # candidate the drone can't afford, so a far partial site only wins
        # when it's reachable.
        candidates.sort(key=lambda c: (-c["request_score"], not c["partial"], -c["buffer_need"], self._host.distance_between(pos, c["coords"])))
        requested_sites = [c for c in candidates if c["request_score"] > 0]
        if requested_sites:
            self._host.log.debug(
                f"[{self._host.name}] _biosite_candidates(): {len(requested_sites)} site(s) hold requested life forms (deficits {requested}); visiting first: "
                + ", ".join(f"{c['target_key']}(score {c['request_score']})" for c in requested_sites)
            )
        elif requested:
            self._host.log.debug(f"requests {requested} but no ready home-biome site holds them; normal order.")
        buffer_sites = [c for c in candidates if c["request_score"] == 0 and c["buffer_need"] > 0]
        if buffer_sites:
            self._host.log.debug(
                f"[{self._host.name}] _biosite_candidates(): {len(buffer_sites)} site(s) refill the life-form buffer (short {short_forms})."
            )
        partial_count = sum(1 for c in candidates if c["partial"])
        if partial_count:
            self._host.log.debug(
                f"[{self._host.name}] _biosite_candidates(): prioritizing {partial_count} partially-drained site(s): "
                + ", ".join(f"{c['target_key']}={c['remaining_tons']:.1f}t" for c in candidates if c["partial"])
            )
        self._host.log.debug(
            f"[{self._host.name}] _biosite_candidates(): {len(sites)} known site(s), {len(candidates)} ready home-biome candidate(s) "
            f"(skipped {skipped_no_home_forms} non-home, {skipped_mixed_biome} mixed-biome, {skipped_cooling} cooling-down, "
            f"{skipped_unneeded} neither requested nor short of buffer after biomass completion)."
        )
        self._host.log.trace(f"_biosite_candidates() exit: {len(candidates)} candidate(s).")
        self._host.log.end()
        return candidates

    def _buffer_shortfalls(self, sites):
        """
        {life_form: units below lifeform_buffer_cap()} at this drone's home
        outpost, for every form on the known biosites. Stock counts the
        outpost's Warehouses plus its Drone Depot stockpiles (not yet staged).
        Only sites holding a home-biome form count; the drone skips the rest.
        """
        outpost = getattr(self._host, "home_outpost", None)
        if outpost is None:
            return {}
        cap = lifeform_buffer_cap(outpost)
        in_depots = {}
        for depot in logistics_requests.local_depots(outpost):
            for item_id, units in logistics_requests.depot_stock(depot).items():
                in_depots[item_id] = in_depots.get(item_id, 0) + units
        forms = set()
        for site in sites:
            types = [getattr(lf, "type", None) for lf in (getattr(site, "life_forms", []) or [])]
            if any(self._host.is_home_biome_sample(t) for t in types):
                forms.update(types)
        forms.discard(None)
        stashes = warehouse_stocks(list(forms), outpost)
        short = {}
        for form in forms:
            missing = cap - stashes[form] - in_depots.get(form, 0)
            if missing > 0:
                short[form] = missing
        self._host.log.trace(f"buffer shortfalls at '{getattr(outpost, 'id', '?')}' (cap {cap}): {short}.")
        return short

    def select_biosite_target(self, candidates):
        """
        First candidate this drone can both afford (calculate_trip_energy())
        and win the exclusive claim for -- mirrors vehicle_claims.py's
        claim-after-filter race pattern (a peer miner drone may win the
        claim between this drone's filter pass and its own claim attempt,
        so this tries the next candidate rather than giving up for the
        cycle).
        """
        self._host.log.start(f"[{self._host.name}] select_biosite_target", level="debug")
        self._host.log.trace(f"select_biosite_target() entry: {len(candidates)} candidate(s).")
        for candidate in candidates:
            budget = self._host.calculate_trip_energy(candidate["coords"])
            if not budget["is_achievable"]:
                self._host.log.trace(f"Biosite {candidate['target_key']}: {budget['total_required_wh']:.1f} {self._host.energy_unit()} required, not achievable on current battery; skipping.")
                continue
            if self._host.claim_biosite(candidate["target_key"], {"coords": candidate["coords"], "name": candidate["target_key"]}):
                self._host.log.trace(f"select_biosite_target() exit: claimed {candidate['target_key']}.")
                self._host.log.end()
                return candidate, budget
            self._host.log.debug(f"Lost claim race on biosite {candidate['target_key']} to a peer drone; trying next candidate.")
        self._host.log.trace("select_biosite_target() exit: no claimable candidate.")
        self._host.log.end()
        return None, None

    def run_miner_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_mining")
        log.print(f"Drone Miner Controller ({self._host.name}) online. Home biome: {self._host.home_biome or 'unknown'}.")
        self._adopt_interrupted_extraction(log)
        while True:
            reset_all()
            try:
                if self._host.is_stranded():
                    log.level("warn").print(f"[{self._host.name}] {self._host.status()}; awaiting drone_service rescue.")
                    self._host.publish_telemetry("STRANDED")
                    flush_all()
                    sleep(poll_interval)
                    continue

                if self._host.handle_recall_if_active():
                    flush_all()
                    sleep(poll_interval)
                    continue

                if self._host.handle_upgrade_request_if_active():
                    flush_all()
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
                            flush_all()
                            sleep(poll_interval)
                            continue
                    self._extract_until_done(coords)
                    if not self._return_and_unload():
                        flush_all()
                        sleep(poll_interval)
                    continue

                curr_wh, _, _ = self._host.get_battery()
                if curr_wh <= self._host.energy_needed_to_return_comfortably():
                    self._host.return_to_service_for_charge(log, f"Battery low ({curr_wh:.1f} {self._host.energy_unit()})")
                    flush_all()
                    sleep(poll_interval)
                    continue

                if self._host.cargo_count() > 0:
                    now_tick = self._host.get_current_tick()
                    retry_tick = getattr(self, "_depot_full_retry_tick", 0)
                    full_depot = getattr(self, "_depot_full_id", None)
                    if now_tick < retry_tick:
                        self._wait_for_depot_space(log, full_depot, retry_tick - now_tick)
                        flush_all()
                        sleep(poll_interval)
                        continue
                    if getattr(self, "_depot_full_count", 0) >= self.DEPOT_FULL_STALL_ATTEMPTS and self._deliver_elsewhere(log):
                        continue
                    # Without the sleep a failed return (e.g. go_to "busy")
                    # retried in a tight loop and flooded the console.
                    if not self._return_and_unload():
                        flush_all()
                        sleep(poll_interval)
                    continue

                candidates = self._biosite_candidates()
                if not candidates:
                    log.debug(f"[{self._host.name}] No ready home-biome biosite candidates this cycle.")
                    self._host.publish_telemetry("IDLE_NO_TARGETS")
                    flush_all()
                    sleep(30.0)
                    continue

                if self._host.hold_for_launch_charge(log):
                    flush_all()
                    sleep(poll_interval)
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
                    flush_all()
                    sleep(15.0)
                    continue

                self.current_target_key = target["target_key"]
                self.current_target = {"coords": target["coords"], "name": target["target_key"], "sample_type": target["sample_type"]}
                self._host.save_mission("mine", self.current_target)

                log.start(f"[{self._host.name}] Reserved biosite {target['target_key']} ({target['sample_type']}) at {target['coords']} (Est. trip cost: {budget['total_required_wh']:.1f} {self._host.energy_unit()}).")
                needs_backoff, outcome = self._run_mission(log, target)
                log.end(outcome)
                if needs_backoff:
                    flush_all()
                    sleep(poll_interval)
            except Exception as e:
                log.level("error").print(f"[{self._host.name}] Miner loop exception: {e}")
                try:
                    self._host.release_biosite_claim()
                except Exception as error:
                    swallowed("drone_mining.DroneMiningMixin.run_miner_loop: self._host.release_biosite_claim", error)
                flush_all()
                sleep(5.0)

    def _run_mission(self, log: "TreeConsole", target):
        """Flies to the reserved biosite, extracts and unloads; returns (caller should back off, outcome text)."""
        self._host.set_intent(fleet_intent.describe("sampling", [target["sample_type"]], at=target["target_key"], root=fleet_intent.haul_root([target["sample_type"]])))
        self._host.publish_telemetry("OUTBOUND", target["target_key"])

        if not self._host.fly_to(target["coords"][0], target["coords"][1], precision=1.0):
            log.level("warn").print(f"[{self._host.name}] Could not reach biosite {target['coords']}; releasing claim and retrying later.")
            self._host.release_biosite_claim(target["target_key"])
            return True, "unreachable, claim released"

        self._extract_until_done(target["coords"])
        if not self._return_and_unload():
            return True, "extracted, unload deferred"
        return False, "extracted and unloaded"

    def _adopt_interrupted_extraction(self, log: "TreeConsole"):
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
        log.start(f"[{self._host.name}] _adopt_interrupted_extraction", level="debug")
        probe = self._host.role_probe_status.get("bio_extractor")
        if probe not in ("busy", "ok"):
            log.end()
            return
        pos = self._host.position()
        coords = (int(round(pos[0])), int(round(pos[1])))
        key = f"bio_{coords[0]}_{coords[1]}"
        if self.current_target_key == key:
            log.debug(f"Extract probe '{probe}' at {coords}; resumed mission already covers this site.")
            log.end()
            return
        if self.current_target_key:
            log.debug(f"Extract probe '{probe}' at {coords} differs from resumed mission '{self.current_target_key}'; adopting the site the drone is actually on.")
            self._host.release_biosite_claim(self.current_target_key)
        if not self._host.claim_biosite(key, {"coords": coords, "name": key}):
            # Still finish here: the drone can't leave until the running
            # extract() ends anyway.
            log.level("warn").print(f"[{self._host.name}] Restarted mid-extraction at {coords}, but a peer holds the claim; finishing the running job anyway.")
        self.current_target_key = key
        self.current_target = {"coords": coords, "name": key, "sample_type": None}
        self._host.save_mission("mine", self.current_target)
        log.print(f"[{self._host.name}] Restarted mid-extraction at {coords} (probe: {probe}); resuming harvest there.")
        log.end()

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
        extracted_total = 0.0
        self._host.log.start(f"[{self._host.name}] Extracting at {coords}")
        while True:
            if self.current_target_key:
                self._host.refresh_biosite_claim(self.current_target_key)
            try:
                res = self._host.drone.bio_extractor.extract()
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Extraction call failed at {coords}: {e}")
                break

            if res.status == "ok":
                extracted_total += res.extracted
                self._host.log.print(f"[{self._host.name}] Extracted {res.extracted:.1f}t at {coords}.")
                if self._host.cargo_full():
                    break
                continue
            elif res.status == "busy":
                flush_all()
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
                flush_all()
                sleep(1.0)
                continue
            else:
                self._host.log.level("warn").print(f"[{self._host.name}] Extraction notice at {coords}: {res.status} - {res.message}")
                break
        self._host.log.end(f"{extracted_total:.1f}t extracted")
        self._host.log.trace(f"[{self._host.name}] _extract_until_done({coords}) exit.")

    def _wait_for_depot_space(self, log: "TreeConsole", depot_id, ticks_left):
        """
        Depot-full backoff: hover in place off the berth (free) and report
        WAITING_DEPOT_SPACE for depot_id, which lets that Depot flush surplus
        (lib/drone_depot.py flush_surplus()). Charges at a drone_service
        only when below LAUNCH_MIN_SOC.
        """
        log.start(f"[{self._host.name}] _wait_for_depot_space", level="debug")
        _, _, lvl = self._host.get_battery()
        if lvl < self._host.LAUNCH_MIN_SOC:
            log.debug(f"Depot full backoff: {ticks_left} ticks left, {lvl*100:.0f}% charge; charging at drone_service meanwhile.")
            self._host.return_to_service_for_charge(log, "Waiting for Drone Depot space")
            self._host.publish_telemetry("WAITING_DEPOT_SPACE", depot_id)
            log.end()
            return
        log.debug(f"Depot full backoff: {ticks_left} ticks left; hovering off the berth.")
        self._host.hover_wait("WAITING_DEPOT_SPACE", depot_id)
        log.end()

    def _deliver_elsewhere(self, log: "TreeConsole"):
        """
        Stalled at a full home Depot: delivers cargo that another Depot
        outpost requests (logistics_requests.outpost_deficits()) there, once,
        if the trip is affordable (calculate_trip_energy()). Picks the outpost
        taking the most units. True when anything was unloaded (the stall
        counter resets); False leaves the drone waiting at home.
        """
        try:
            contents = {i: int(n) for i, n in dict(self._host.drone.cargo.contents()).items() if n > 0}
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin._deliver_elsewhere: self._host.drone.cargo.contents", error)
            return False
        home_ids = {d["id"] for d in self._host._home_depot_candidates()}
        by_outpost = {}
        for depot in self._host.get_all_drone_depots():
            if depot["id"] not in home_ids and depot.get("outpost_id"):
                by_outpost.setdefault(depot["outpost_id"], []).append(depot)
        network = get_component("outpost_network")
        try:
            outposts = {o.id: o for o in network.outposts()} if network else {}
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin._deliver_elsewhere: network.outposts", error)
            outposts = {}
        best, best_units = None, 0
        for outpost_id, depots in by_outpost.items():
            deficits = logistics_requests.outpost_deficits(outposts.get(outpost_id), live=False) if outpost_id in outposts else {}
            units = sum(min(n, deficits.get(i, 0)) for i, n in contents.items())
            if units <= 0:
                continue
            budget = self._host.calculate_trip_energy(depots[0]["coords"])
            if not budget["is_achievable"]:
                log.debug(f"[{self._host.name}] Stalled cargo: '{outpost_id}' wants {units} unit(s) but is out of range.")
                continue
            if units > best_units:
                best, best_units = (outpost_id, depots), units
        if best is None:
            log.debug(f"[{self._host.name}] Stalled cargo {contents}: no other Depot outpost requests it in range; waiting at home.")
            return False
        outpost_id, depots = best
        depot = self._host._pick_free_depot(depots)
        log.start(f"[{self._host.name}] Home Depot full {self._depot_full_count}x; delivering {contents} to '{depot['id']}' ({outpost_id}), which requests {best_units} unit(s).")
        delivered = self._deliver_to_depot(log, depot)
        log.end("delivered" if delivered else "not delivered")
        return delivered

    def _deliver_to_depot(self, log: "TreeConsole", depot):
        """Docks at the other outpost's Depot and unloads the stalled cargo; True when anything was unloaded."""
        self._host.publish_telemetry("DELIVERING", depot["id"])
        if not self._host.fly_to_station(depot["id"], target_coords=depot["coords"]):
            log.level("warn").print(f"[{self._host.name}] Could not dock at '{depot['id']}' for the stalled cargo; back to waiting at home.")
            return False
        unloaded = self._host.unload_cargo_at_depot()
        self._host.leave_station()
        if unloaded <= 0:
            log.debug(f"[{self._host.name}] '{depot['id']}' took nothing ({unloaded}); back to waiting at home.")
            return False
        log.print(f"[{self._host.name}] Unloaded {unloaded} stalled unit(s) at '{depot['id']}'.")
        self._depot_full_count = 0
        self._depot_full_retry_tick = 0
        return True

    def _unload_and_leave(self, depot_id):
        """Unloads at the docked Depot, maintains modules, leaves the berth; returns the unloaded count (negative when the Depot is full)."""
        unloaded = self._host.unload_cargo_at_depot()
        if unloaded < 0:
            self._host.log.level("warn").print(f"[{self._host.name}] Drone Depot has no free slot for this cargo; leaving aboard until space opens.")
            self._host.publish_telemetry("WAITING_DEPOT_SPACE")
        elif unloaded > 0:
            self._host.log.print(f"[{self._host.name}] Unloaded {unloaded} units at Drone Depot.")

        if unloaded < 0:
            self._depot_full_retry_tick = self._host.get_current_tick() + self.DEPOT_FULL_RETRY_TICKS
            self._depot_full_count = getattr(self, "_depot_full_count", 0) + 1
            self._depot_full_id = depot_id
            self._host.log.debug(f"[{self._host.name}] Depot '{depot_id}' full ({self._depot_full_count}x in a row); next unload attempt in {self.DEPOT_FULL_RETRY_TICKS} ticks.")
        elif self._host.cargo_count() == 0:
            self._depot_full_count = 0
            self._depot_full_id = None

        self._host.release_biosite_claim()
        if unloaded >= 0 and self._host.cargo_count() == 0:
            # Docked and empty: the one moment couple()/uncouple() can run.
            self._host.maintain_modules_at_depot()
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
            # battery for nothing; the miner loop hovers here until the retry
            # tick passes (_wait_for_depot_space()).
            self._wait_for_depot_space(self._host.log, depot_id, self.DEPOT_FULL_RETRY_TICKS)
        else:
            self._host.publish_telemetry("READY_AT_DEPOT")
        return unloaded

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

        self._host.log.start(f"[{self._host.name}] Unloading at Drone Depot '{depot_id}'")
        unloaded = self._unload_and_leave(depot_id)
        self._host.log.end("depot full, cargo kept aboard" if unloaded < 0 else f"unloaded {unloaded} unit(s)")
        self._host.log.trace(f"[{self._host.name}] _return_and_unload() exit: unloaded={unloaded}.")
        # Depot full counts as failure: cargo is still aboard, so the caller
        # should back off before retrying.
        return unloaded >= 0
