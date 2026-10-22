# Drone ability: biosite mining (harvesting). Builds candidates from
# journal.biomass_coords(), filters to this drone's home outpost's biome
# (drone_cargo.py's is_home_biome_sample() -- only native-biome samples
# process at the Essence Liquifier), exclusive-claims a ready site
# (journal.is_ready() cooldown gate + drone_claims.py's claim_biosite(), NOT
# mining_reservations.py's shared yield-debit pattern -- biosite extraction
# is exclusive-with-cooldown, not shared, see docs/AI_CHEATSHEET.md) and
# extract()s in a loop until the site depletes or cargo fills. The role loop
# (fly out, extract, return to the home Drone Depot and unload, stall
# fallback) is BiositeJob (lib/job_biosite.py); the unload trip is
# drone_cargo.return_and_unload().
#
# Open question flagged in the plan: whether bio_extractor.extract() can
# target a specific species at a mixed-biome tile, or always pulls whatever
# is present. docs/types/biosphere.md's PortableBioExtractor.extract() takes
# NO arguments at all (no species/item_id parameter) -- so it cannot target a
# specific species; it always pulls whatever occupies that site's chamber.
# This confirms the plan's v1 default is the only safe option:
# biosite_candidates() below skips any biosite where a non-home-biome
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

from typing import TYPE_CHECKING

import logistics_requests
from biomass_retire import biomass_complete
from drone_depot import lifeform_buffer_cap
from mission import Mission
from storage import warehouse_stocks
from swallow import swallowed
from tree_console import flush_all, method_block

if TYPE_CHECKING:
    from drone import DroneController
    from tree_console import TreeConsole


# Extra pull on a biosite per requested (logistics_requests) or
# below-buffer life form it still holds, by rarity -- rare forms (the fungi:
# one site per biome, 36 h regrowth) sit on few sites with long cooldowns, so
# a site holding one is worth a detour first.
RARITY_REQUEST_WEIGHT = {"common": 1, "uncommon": 2, "rare": 4}


def _tons(lf, field="remaining_tons"):
    """A life form's tonnage field (remaining_tons or tons) as float, 0.0 when unset."""
    return float(getattr(lf, field, 0.0) or 0.0)


class _SiteDemand:
    """What biosite_candidates() scores sites against: requested forms by
    band (logistics_requests) and, after biomass completion, the forms any
    outpost requests and those short of the home outpost's buffer."""

    def __init__(self, bands, requested, retired, wanted_types, short_forms):
        self.bands = bands
        self.requested = requested
        self.retired = retired
        self.wanted_types = wanted_types
        self.short_forms = short_forms


def _score_site(coords, life_forms, home_forms, demand):
    """
    biosite_candidates() entry for a ready site, or None when after biomass
    completion it holds no requested or below-buffer form and is not a
    partly drained site holding a requested form.
    """
    retired = demand.retired
    sample = home_forms[0]
    remaining = _tons(sample)
    peak = _tons(sample, "tons")
    # A site's cooldown/regrowth only starts once it is fully empty
    # (biosphere.md: "Partial depletion persists and cooldown starts
    # only when the site is empty"), so a half-drained site left
    # sitting is dead time on its regen clock.
    partial = 0.0 < remaining < peak
    if retired:
        amounts = [(_tons(lf), _tons(lf, "tons")) for lf in life_forms]
        partial = any(r < p for r, p in amounts) and any(r > 0 for r, _p in amounts)
    request_score = 0
    top_band = 0
    for lf in life_forms if retired else home_forms:
        lf_type = getattr(lf, "type", None)
        if demand.requested.get(lf_type, 0) > 0 and _tons(lf) > 0:
            request_score += RARITY_REQUEST_WEIGHT.get(getattr(lf, "rarity", "common"), 1)
            top_band = max([top_band] + [band for band, items in demand.bands.items() if items.get(lf_type, 0) > 0])
    buffer_need = 0
    if retired:
        buffer_need = sum(RARITY_REQUEST_WEIGHT.get(getattr(lf, "rarity", "common"), 1) for lf in life_forms if demand.short_forms.get(getattr(lf, "type", None), 0) > 0 and _tons(lf) > 0)
    if retired and request_score == 0 and buffer_need == 0 and not (partial and any(getattr(lf, "type", None) in demand.wanted_types for lf in life_forms)):
        return None
    x, y = coords
    return {
        "coords": (x, y),
        "target_key": f"bio_{x}_{y}",
        "sample_type": getattr(sample, "type", None),
        "remaining_tons": remaining,
        "partial": partial,
        "request_score": request_score,
        "band": top_band,
        "buffer_need": buffer_need,
    }


class DroneMiningMixin:
    @property
    def _host(self) -> "DroneController":
        return self  # type: ignore[return-value]

    @method_block(lambda self, *_, **__: f"[{self._host.name}] biosite_candidates()")
    def biosite_candidates(self):
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
        self._host.log.trace("biosite_candidates() entry.")
        journal = get_component("journal")
        if not journal or not self._host.home_biome:
            self._host.log.debug("missing journal or unknown home_biome; returning no candidates.")
            return []

        try:
            sites = journal.biomass_coords()
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin.biosite_candidates: journal.biomass_coords", error)
            sites = []

        pos = self._host.position()
        demand = self._site_demand(sites)
        candidates = []
        skipped = {"no_home_forms": 0, "mixed_biome": 0, "cooling": 0, "unneeded": 0}
        for site in sites:
            coord = getattr(site, "coord", None)
            life_forms = getattr(site, "life_forms", []) or []
            if not coord or not life_forms:
                continue
            x, y = int(coord[0]), int(coord[1])

            home_forms = [lf for lf in life_forms if self._host.is_home_biome_sample(getattr(lf, "type", None))]
            if not home_forms:
                skipped["no_home_forms"] += 1
                continue
            if len(home_forms) != len(life_forms) and not demand.retired:
                # Mixed-biome tile: extract() takes no species argument (see
                # module docstring), so v1 skips this site entirely rather
                # than risk pulling the wrong species.
                skipped["mixed_biome"] += 1
                self._host.log.trace(f"Biosite ({x}, {y}) skipped: mixed-biome tile ({len(home_forms)}/{len(life_forms)} home-biome samples).")
                continue
            if not journal.is_ready(x, y):
                skipped["cooling"] += 1
                continue

            candidate = _score_site((x, y), life_forms, home_forms, demand)
            if candidate is None:
                skipped["unneeded"] += 1
                continue
            candidates.append(candidate)

        # Sites holding forms requested in the highest band first (score =
        # rarity weight of the requested forms), then partially-drained sites (finish them so their cooldown
        # can start), then nearest. select_biosite_target() still skips any
        # candidate the drone can't afford, so a far partial site only wins
        # when it's reachable.
        candidates.sort(key=lambda c: (-c["band"], -c["request_score"], not c["partial"], -c["buffer_need"], self._host.distance_between(pos, c["coords"])))
        self._log_candidates(sites, candidates, demand, skipped)
        self._host.log.trace(f"biosite_candidates() exit: {len(candidates)} candidate(s).")
        return candidates

    def _site_demand(self, sites):
        """The requests and buffer shortfalls biosite_candidates() scores sites against."""
        try:
            bands = logistics_requests.network_band_deficits()
        except Exception as error:
            swallowed("drone_mining.DroneMiningMixin.biosite_candidates: logistics_requests.network_band_deficits", error)
            bands = {}
        requested = logistics_requests.sum_tiers(bands)
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
        return _SiteDemand(bands, requested, retired, wanted_types, short_forms)

    def _log_candidates(self, sites, candidates, demand, skipped):
        """biosite_candidates()'s decision trail: which sites go first and why, and what was skipped."""
        requested = demand.requested
        requested_sites = [c for c in candidates if c["request_score"] > 0]
        if requested_sites:
            self._host.log.debug(f"[{self._host.name}] biosite_candidates(): {len(requested_sites)} site(s) hold requested life forms (deficits {requested}); visiting first: " + ", ".join(f"{c['target_key']}(score {c['request_score']})" for c in requested_sites))
        elif requested:
            self._host.log.debug(f"requests {requested} but no ready home-biome site holds them; normal order.")
        buffer_sites = [c for c in candidates if c["request_score"] == 0 and c["buffer_need"] > 0]
        if buffer_sites:
            self._host.log.debug(f"[{self._host.name}] biosite_candidates(): {len(buffer_sites)} site(s) refill the life-form buffer (short {demand.short_forms}).")
        partial_count = sum(1 for c in candidates if c["partial"])
        if partial_count:
            self._host.log.debug(f"[{self._host.name}] biosite_candidates(): prioritizing {partial_count} partially-drained site(s): " + ", ".join(f"{c['target_key']}={c['remaining_tons']:.1f}t" for c in candidates if c["partial"]))
        self._host.log.debug(
            f"[{self._host.name}] biosite_candidates(): {len(sites)} known site(s), {len(candidates)} ready home-biome candidate(s) "
            f"(skipped {skipped['no_home_forms']} non-home, {skipped['mixed_biome']} mixed-biome, {skipped['cooling']} cooling-down, "
            f"{skipped['unneeded']} neither requested nor short of buffer after biomass completion)."
        )

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

    def adopt_interrupted_extraction(self, log: "TreeConsole"):
        """
        Restart-during-extraction check, run once when the miner job starts.
        extract() keeps the drone occupied across a script restart, so every
        go_to()/go_to_station() is rejected "busy" until it finishes. If no
        mission was resumed (load_mission() found none, or the claim was
        lost), the job would otherwise pick a new target or try to unload,
        and fail on "busy" every cycle.

        detect_role()'s extract() probe already tells us: "busy" (old job
        still running) or "ok" (probe just harvested here) means the drone
        is hovering over a biosite mid-harvest. Adopt that site as the
        current mission, so the job's resume path keeps extracting until
        the site depletes or cargo fills, then unloads as normal.
        """
        log.start(f"[{self._host.name}] adopt_interrupted_extraction", level="debug")
        probe = self._host.role_probe_status.get("bio_extractor")
        if probe not in ("busy", "ok"):
            log.end()
            return
        pos = self._host.position()
        coords = (int(round(pos[0])), int(round(pos[1])))
        key = f"bio_{coords[0]}_{coords[1]}"
        if self._host.current_target_key == key:
            log.debug(f"Extract probe '{probe}' at {coords}; resumed mission already covers this site.")
            log.end()
            return
        if self._host.current_target_key:
            log.debug(f"Extract probe '{probe}' at {coords} differs from resumed mission '{self._host.current_target_key}'; adopting the site the drone is actually on.")
            self._host.release_biosite_claim(self._host.current_target_key)
        if not self._host.claim_biosite(key, {"coords": coords, "name": key}):
            # Still finish here: the drone can't leave until the running
            # extract() ends anyway.
            log.level("warn").print(f"[{self._host.name}] Restarted mid-extraction at {coords}, but a peer holds the claim; finishing the running job anyway.")
        self._host.begin_mission(Mission(kind="mine", target_key=key, target={"coords": coords, "name": key, "sample_type": None}), claimed=True)
        log.print(f"[{self._host.name}] Restarted mid-extraction at {coords} (probe: {probe}); resuming harvest there.")
        log.end()

    def extract_until_done(self, coords):
        """
        Repeatedly bio_extractor.extract()s at coords until the site depletes
        (status "cooling") or cargo fills. extract() "stays occupied...
        including across a script stop and restart" per its own docs, so
        this loop needs no extra resumability handling itself -- only the
        flight leg to get here needed re-issuing (see job_biosite.py).
        """
        self._host.log.trace(f"[{self._host.name}] extract_until_done({coords}) entry.")
        settle_retries = 5
        extracted_total = 0.0
        self._host.log.start(f"[{self._host.name}] Extracting at {coords}")
        while True:
            if self._host.current_target_key:
                self._host.refresh_biosite_claim(self._host.current_target_key)
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
        self._host.log.trace(f"[{self._host.name}] extract_until_done({coords}) exit.")
