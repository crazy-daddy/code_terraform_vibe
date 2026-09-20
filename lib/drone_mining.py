# Drone role: biosite miner (harvester). Builds candidates from
# journal.biomass_coords(), filters to this drone's home outpost's biome
# (drone_cargo.py's is_home_biome_sample() -- only native-biome samples
# process at the Essence Liquifier), exclusive-claims a ready site
# (journal.is_ready() cooldown gate + drone_claims.py's claim_biosite(), NOT
# mining_reservations.py's shared yield-debit pattern -- biosite extraction
# is exclusive-with-cooldown, not shared, see docs/AI_CHEATSHEET.md), flies
# out, extract()s in a loop until the site depletes or cargo fills, returns
# to the nearest Drone Depot, unloads, releases the claim.
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


class DroneMiningMixin:
    def _biosite_candidates(self):
        """
        [{"coords", "target_key", "sample_type", "remaining_tons"}, ...] for
        every discovered permanent biosite that is entirely native to this
        drone's home biome and currently journal.is_ready() (cooldown gate,
        checked before even attempting a claim -- see module docstring).
        """
        journal = get_component("journal")
        if not journal or not self.home_biome:
            return []

        try:
            sites = journal.biomass_coords()
        except Exception:
            sites = []

        pos = self.position()
        candidates = []
        for site in sites:
            coord = getattr(site, "coord", None)
            life_forms = getattr(site, "life_forms", []) or []
            if not coord or not life_forms:
                continue
            x, y = int(coord[0]), int(coord[1])

            home_forms = [lf for lf in life_forms if self.is_home_biome_sample(getattr(lf, "type", None))]
            if not home_forms:
                continue
            if len(home_forms) != len(life_forms):
                # Mixed-biome tile: extract() takes no species argument (see
                # module docstring), so v1 skips this site entirely rather
                # than risk pulling the wrong species.
                continue
            if not journal.is_ready(x, y):
                continue

            sample = home_forms[0]
            candidates.append({
                "coords": (x, y),
                "target_key": f"bio_{x}_{y}",
                "sample_type": getattr(sample, "type", None),
                "remaining_tons": getattr(sample, "remaining_tons", 0.0),
            })

        candidates.sort(key=lambda c: self.distance_between(pos, c["coords"]))
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
        for candidate in candidates:
            budget = self.calculate_trip_energy(candidate["coords"])
            if not budget["is_achievable"]:
                continue
            if self.claim_biosite(candidate["target_key"], {"coords": candidate["coords"], "name": candidate["target_key"]}):
                return candidate, budget
        return None, None

    def run_miner_loop(self, poll_interval=5.0):
        log = TreeConsole(module="drone_mining")
        log.print(f"Drone Miner Controller ({self.name}) online. Home biome: {self.home_biome or 'unknown'}.")
        while True:
            try:
                if self.is_stranded():
                    log.level("warn").print(f"[{self.name}] {self.status()}; awaiting drone_service rescue.")
                    self.publish_telemetry("STRANDED")
                    sleep(poll_interval)
                    continue

                self.cleanup_stale_biosite_claims()

                # Resume an in-progress mission after a script reload. A
                # drone's go_to() is CANCELLED by a script restart
                # (drone.md), unlike a rover's persistent drive command, so
                # re-validate the claim and physical position, then
                # re-issue the flight leg -- extract() itself resumes
                # transparently once physically there again (its own docs:
                # "stays occupied... including across a script stop and
                # restart").
                has_resumable_target = bool(self.current_target_key and self.current_target)
                if has_resumable_target:
                    coords = tuple(self.current_target.get("coords"))
                    log.debug(f"[{self.name}] Resuming claimed target '{self.current_target_key}' after reload; re-validating position.")
                    if not self.is_at(coords, precision=1.0):
                        if not self.fly_to(coords[0], coords[1], precision=1.0):
                            log.level("warn").print(f"[{self.name}] Could not re-reach resumed target {coords}; will retry.")
                            sleep(poll_interval)
                            continue
                    self._extract_until_done(coords)
                    self._return_and_unload()
                    continue

                curr_wh, _, _ = self.get_battery()
                if curr_wh <= self.energy_needed_to_return_comfortably():
                    service_coords, service_info = self.get_nearest_drone_service()
                    if not self.is_at(service_coords, precision=3.0):
                        log.debug(f"[{self.name}] Battery low ({curr_wh:.1f} Wh); returning to drone_service.")
                        self.publish_telemetry("RETURNING_TO_SERVICE")
                        service_id = service_info.get("id")
                        if not (service_id and self.fly_to_station(service_id)):
                            self.fly_to(service_coords[0], service_coords[1], precision=3.0)
                    sleep(poll_interval)
                    continue

                if self.cargo_count() > 0:
                    self._return_and_unload()
                    continue

                candidates = self._biosite_candidates()
                if not candidates:
                    log.debug(f"[{self.name}] No ready home-biome biosite candidates this cycle.")
                    self.publish_telemetry("IDLE_NO_TARGETS")
                    sleep(30.0)
                    continue

                target, budget = self.select_biosite_target(candidates)
                if not target:
                    log.debug(f"[{self.name}] {len(candidates)} candidate(s) found but none both reachable and claimable.")
                    self.publish_telemetry("IDLE_OUT_OF_RANGE")
                    sleep(15.0)
                    continue

                self.current_target_key = target["target_key"]
                self.current_target = {"coords": target["coords"], "name": target["target_key"], "sample_type": target["sample_type"]}
                self.save_mission("mine", self.current_target)

                log.print(f"[{self.name}] Reserved biosite {target['target_key']} ({target['sample_type']}) at {target['coords']} (Est. trip cost: {budget['total_required_wh']:.1f} Wh).")
                self.publish_telemetry("OUTBOUND", target["target_key"])

                if not self.fly_to(target["coords"][0], target["coords"][1], precision=1.0):
                    log.level("warn").print(f"[{self.name}] Could not reach biosite {target['coords']}; releasing claim and retrying later.")
                    self.release_biosite_claim(target["target_key"])
                    sleep(poll_interval)
                    continue

                self._extract_until_done(target["coords"])
                self._return_and_unload()
            except Exception as e:
                log.level("error").print(f"[{self.name}] Miner loop exception: {e}")
                try:
                    self.release_biosite_claim()
                except Exception:
                    pass
                sleep(5.0)

    def _extract_until_done(self, coords):
        """
        Repeatedly bio_extractor.extract()s at coords until the site depletes
        (status "cooling") or cargo fills. extract() "stays occupied...
        including across a script stop and restart" per its own docs, so
        this loop needs no extra resumability handling itself -- only the
        flight leg to get here needed re-issuing (see run_miner_loop()).
        """
        while True:
            if self.current_target_key:
                self.refresh_biosite_claim(self.current_target_key)
            try:
                res = self.drone.bio_extractor.extract()
            except Exception as e:
                self.log.level("error").print(f"[{self.name}] Extraction call failed at {coords}: {e}")
                break

            if res.status == "ok":
                self.log.print(f"[{self.name}] Extracted {res.extracted:.1f}t at {coords}.")
                if self.cargo_full():
                    break
                continue
            elif res.status == "busy":
                sleep(1.0)
                continue
            elif res.status == "cooling":
                self.log.print(f"[{self.name}] Biosite {coords} depleted and cooling down; heading back.")
                break
            else:
                self.log.level("warn").print(f"[{self.name}] Extraction notice at {coords}: {res.status} - {res.message}")
                break

    def _return_and_unload(self):
        depot_coords, depot_info = self.get_nearest_drone_depot()
        depot_id = depot_info.get("id")
        self.publish_telemetry("RETURNING_TO_DEPOT")

        reached = bool(depot_id) and self.fly_to_station(depot_id)
        if not reached:
            reached = self.fly_to(depot_coords[0], depot_coords[1], precision=1.5)
        if not reached:
            self.log.level("warn").print(f"[{self.name}] Could not reach Drone Depot to unload; will retry.")
            return

        unloaded = self.unload_cargo_at_depot()
        if unloaded < 0:
            self.log.level("warn").print(f"[{self.name}] Drone Depot has no free slot for this cargo; leaving aboard until space opens.")
            self.publish_telemetry("WAITING_DEPOT_SPACE")
        elif unloaded > 0:
            self.log.print(f"[{self.name}] Unloaded {unloaded} units at Drone Depot.")

        self.release_biosite_claim()
        self.publish_telemetry("READY_AT_DEPOT")
