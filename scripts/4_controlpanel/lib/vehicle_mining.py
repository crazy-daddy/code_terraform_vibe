# Vehicle mixin: mineral-site candidate discovery, priority-sorted claiming
# and drill execution. Shared by Rover and Pioneer via VehicleController
# (lib/vehicle.py). No loop: the mining role is MineJob (lib/job_mine.py).
#
# Capability (which hardness a vehicle can mine) is always read live from
# self.vehicle.drill.hardness_limit() -- never assumed from vehicle type.
# Rovers only ever carry a basic Drill Module (hardness_limit 1, iron/silicon)
# in their fixed Drill slot; Industrial/Heavy Drills are Pioneer-universal-slot
# items for the higher-hardness sites a Rover can never reach. Job routing
# between the two is a soft priority-sort preference (see
# ROVER_PREFERRED_MAX_HARDNESS below), not a hard exclusivity rule, so a
# capable vehicle still picks up whatever's available rather than idling.

from typing import TYPE_CHECKING

import logistics_requests
import mining_reservations
import outpost_mining
from game_rules import RAW_ORE_ITEM_IDS
from item_tiers import can_cut
from logistics_requests import split_need_stock
from mission import Mission
from priority import NEED, STOCK, band_name
from production import get_raw_material_reason
from swallow import swallowed
from tree_console import flush_all

if TYPE_CHECKING:
    from vehicle import VehicleController

# Hardness a Rover's basic drill can handle. Pioneers pass this as
# deprioritize_hardness_at_or_below so they prefer sites only they can reach,
# while still falling back to easy ore if nothing harder is pending.
ROVER_PREFERRED_MAX_HARDNESS = 1.0

# Demand band a mine candidate serves ("band"): the highest band (lib/priority.py)
# in which the delivery outpost still misses the ore, STOCK when only stock
# headroom is left. A higher band beats a lower one, as haulers already rank it
# (haul_rank()). Sorted after priority, before the urgency-per-hour score
# (mining_score()).


def ore_bands(bands):
    """{band: {ore: units}}: the raw-ore entries of `bands` (outpost_tier_deficits()
    output, already net of in-flight mining yield). Positive entries only."""
    out = {}
    for band, items in bands.items():
        for item_id in sorted(items):
            if item_id in RAW_ORE_ITEM_IDS and items[item_id] > 0:
                out.setdefault(band, {})[item_id] = items[item_id]
    return out


def top_band(bands, item_id):
    """The highest band of `bands` ({band: {ore: units}}) with a deficit of item_id, STOCK when none."""
    found = [band for band, items in bands.items() if items.get(item_id, 0) > 0]
    return max(found) if found else STOCK


def sum_bands(bands):
    """{ore: units} over every band of `bands`."""
    total = {}
    for items in bands.values():
        for item_id, units in items.items():
            total[item_id] = total.get(item_id, 0) + units
    return total


class VehicleMiningMixin:
    """Mineral-site discovery, priority-sorted claiming, and drill execution."""

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def cargo_full_for_resume(self):
        """
        True when the cargo hold is full (Cargo.full()). A reload mid-return
        restores the mining claim, and resuming it with a full hold only
        drives back to the site and home again without mining, so callers
        unload first instead -- see MineJob.prepare_cargo() (lib/job_mine.py).
        """
        cargo = getattr(self._host.vehicle, "cargo", None)
        if cargo is None:
            return False
        try:
            return bool(cargo.full())
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.cargo_full_for_resume: cargo.full", error)
            return False

    def cargo_matches_target(self, target):
        """
        True when the vehicle's cargo is empty, or holds only the target's
        own harvest_item. Cargo isn't material-locked (docs/models/storage_and_items.md's
        Cargo.stacks() lists property-distinct stacks -- a Rover/Pioneer can
        physically carry a mix of ore types at once), so nothing stops a
        resumed mining job from mining a *different* ore straight into a hold
        that already carries something else -- wasteful (capacity meant for
        one clean load gets split across two materials) and confusing (an
        "interrupted, resume this job" trip budget assumed a roughly-empty
        hold, not one already partly full of an unrelated material). Callers
        use this to decide whether resuming a claimed target should first
        detour through an unload instead of mining straight into mismatched
        cargo -- see MineJob.prepare_cargo() (lib/job_mine.py).
        """
        if not hasattr(self._host.vehicle, "cargo") or self._host.vehicle.cargo.count() == 0:
            return True
        harvest_item = target.get("harvest_item") if target else None
        if not harvest_item:
            return True  # non-mining target (e.g. a POI survey) has no ore to mismatch against
        try:
            stacks = self._host.vehicle.cargo.stacks()
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.cargo_matches_target: self._host.vehicle.cargo.stacks", error)
            return True  # can't verify; don't block resumption over an unreadable stacks() call
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if item_id and count > 0 and item_id != harvest_item:
                return False
        return True

    def home_ore_bands(self):
        """
        {band: {ore: units}} this vehicle's home_base still requests
        (logistics_requests.outpost_tier_deficits(), net of stock, in-flight
        pickups and the yield in-flight mining trips to home already
        promised). Home is planned like any outpost: a smelting site's ore
        requests come from lib/site_supply.py.
        """
        tick = self._host.get_current_tick()
        return ore_bands(logistics_requests.outpost_tier_deficits(self._host.home_outpost, tick, live=True))

    def home_ore_demand(self):
        """{ore: units} of home_ore_bands(), every band summed."""
        return sum_bands(self.home_ore_bands())

    def build_mineral_site_candidates(self, deprioritize_hardness_at_or_below=None):
        """
        Candidate mineral-extraction sites matching home_ore_demand() and this
        vehicle's actual mounted drill capability. When
        deprioritize_hardness_at_or_below is set, sites at/below that hardness
        get priority=3 instead of priority=2, so select_best_mining_target()
        tries them last -- a soft preference, not exclusion.
        """
        self._host.log.start(f"[{self._host.name}] build_mineral_site_candidates()", level="debug")
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            self._host.log.end()
            return []

        bands = self.home_ore_bands()
        raw_demands = sum_bands(bands)
        if not raw_demands:
            self._host.log.debug("no ore requested at home; skipping candidate search.")
            self._host.log.end()
            return []

        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.build_mineral_site_candidates: self._host.vehicle.drill.hardness_limit", error)
                max_drill_hardness = 1.0
        self._host.log.debug(f"[{self._host.name}] build_mineral_site_candidates(): demand={raw_demands}, max_drill_hardness={max_drill_hardness}, deprioritize_hardness_at_or_below={deprioritize_hardness_at_or_below}")

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here: several vehicles can mine the same site,
        # so a peer already working a site is not disqualifying -- see
        # select_best_mining_target()'s yield reservation instead, which
        # debits home demand for ore already promised by an in-flight trip.
        home_id = getattr(self._host.home_outpost, "id", None)
        candidates = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                site_item = getattr(site, "item_id", None)
                if site.kind() != "mineral" or raw_demands.get(site_item, 0) <= 0:
                    continue
                hardness = getattr(site, "hardness", None)
                if not can_cut(hardness, max_drill_hardness):
                    self._host.log.debug(f"site_{site.id}: hardness {hardness} exceeds drill limit {max_drill_hardness}; skipped.")
                    continue

                key = f"site_{site.id}"
                if key in unsupported_targets:
                    can_attempt, reason = self._host.can_attempt_target(key, unsupported_targets[key])
                    if not can_attempt:
                        self._host.log.debug(f"{key}: blocked by unsupported-target record ({reason}); skipped.")
                        continue

                priority = 2
                if deprioritize_hardness_at_or_below is not None and hardness <= deprioritize_hardness_at_or_below:
                    priority = 3
                    self._host.log.debug(f"{key}: hardness {hardness} deprioritized (<= {deprioritize_hardness_at_or_below}); priority=3.")

                candidates.append(
                    {
                        "key": key,
                        "type": "mine",
                        "coords": (site.x, site.y),
                        "name": f"Site_{site.id}_{getattr(site, 'item_id', 'ore')}",
                        "harvest_item": site_item,
                        "reason": get_raw_material_reason(site_item),
                        "priority": priority,
                        "band": top_band(bands, site_item),
                        "purity": getattr(site, "purity", None),
                        "outpost_id": home_id,
                    }
                )
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.build_mineral_site_candidates: journal.surveyed_sites", error)

        self._host.log.debug(f"{len(candidates)} candidate(s) built.")
        self._host.log.end()
        return candidates

    def build_local_stockpile_candidates(self, outpost_id):
        """
        Candidate mineral-extraction sites for a vehicle STATIONED at
        outpost_id (MineJob with OutpostStockpile, lib/job_mine.py). Ores:
        those outpost_id (or another outpost this miner covers,
        remote_ore_need()) requests at NEED or above, plus a STOCK buffer up
        to the stock target of each active ore
        (outpost_mining.active_ores(), stockpile_headroom()), each only
        while in reach (reach_ores()). Sites: every surveyed site of those
        ores that the drill cuts (cuttable_sites());
        select_best_mining_target() ranks them by urgency per hour of mining
        and drops the ones the charge on board can't reach.

        Publishes the ores in reach (outpost_mining.publish_reach()), so
        planners know what this outpost can mine. When it returns no
        candidate, self.stockpile_empty_reason says why (for
        OutpostStockpile.idle()'s stand-by line).
        """
        self.stockpile_empty_reason = ""
        journal = get_component("journal")
        if not journal or not hasattr(journal, "surveyed_sites"):
            self.stockpile_empty_reason = "journal unavailable, no surveyed sites to read"
            return []

        sites, too_hard = self.cuttable_sites(journal)
        reach = self.reach_ores(sites, outpost_id)
        if reach is None:
            # Battery unreadable: publish nothing, let the trip budget sort the sites.
            reach = {site.item_id for site in sites}
        else:
            outpost_mining.publish_reach(self._host.name, outpost_id, reach, self._host.get_current_tick())
        if not reach:
            self.stockpile_empty_reason = "no surveyed site in reach on a full battery" + (f" ({too_hard} too hard for the drill)" if too_hard else "")
            return []

        # Ore requested at NEED band or above (a dock order, a local
        # Fabricator's ingots) goes ahead of stock-only ore, and may be mined
        # past the stock target up to that need.
        bands = self.stockpile_bands(outpost_id)
        need = split_need_stock(bands)[0]
        under_target = {}
        for item_id in sorted(reach):
            room = max(self.stockpile_headroom(outpost_id, item_id), need.get(item_id, 0))
            if room > 0:
                under_target[item_id] = room
        if not under_target:
            self.stockpile_empty_reason = f"no need and every buffered ore in reach ({', '.join(sorted(reach))}) is at its stock target, inactive or out of slots"
            return []

        unsupported_targets = self._host.get_unsupported_targets()

        # No peer-claim filter here either (see build_mineral_site_candidates()):
        # stockpile_headroom() already nets out peers' reserved trips, so a
        # second vehicle only joins while the stock target still has room.
        candidates = []
        blacklisted = 0
        for site in sites:
            site_item = site.item_id
            if site_item not in under_target:
                continue
            key = f"site_{site.id}"
            if key in unsupported_targets:
                can_attempt, _ = self._host.can_attempt_target(key, unsupported_targets[key])
                if not can_attempt:
                    blacklisted += 1
                    continue

            candidates.append(
                {
                    "key": key,
                    "type": "mine",
                    "coords": (site.x, site.y),
                    "name": f"Site_{site.id}_{site_item}",
                    "harvest_item": site_item,
                    "reason": f"stockpiling for outpost '{outpost_id}'",
                    "priority": 2,
                    "band": top_band(bands, site_item),
                    "purity": getattr(site, "purity", None),
                    "outpost_id": outpost_id,
                    "max_units": under_target[site_item],
                    "urgency": self.stock_urgency(site_item, under_target[site_item], top_band(bands, site_item)),
                }
            )

        if not candidates:
            self.stockpile_empty_reason = f"no usable surveyed site for {', '.join(sorted(under_target))}" + (f" (skipped: {blacklisted} blacklisted)" if blacklisted else "")
        self._host.log.debug(f"[{self._host.name}] build_local_stockpile_candidates('{outpost_id}'): {len(candidates)} candidate(s) built (reach={sorted(reach)}, under_target={under_target}, need={need}).")
        return candidates

    def cuttable_sites(self, journal):
        """(sites, too_hard): surveyed raw-ore sites this vehicle's drill cuts
        (item_tiers.can_cut()), and the count of those it can't."""
        max_drill_hardness = 1.0
        if hasattr(self._host.vehicle, "drill") and hasattr(self._host.vehicle.drill, "hardness_limit"):
            try:
                max_drill_hardness = self._host.vehicle.drill.hardness_limit()
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.cuttable_sites: self._host.vehicle.drill.hardness_limit", error)
                max_drill_hardness = 1.0
        try:
            surveyed = journal.surveyed_sites("nocturna")
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.cuttable_sites: journal.surveyed_sites", error)
            surveyed = []
        sites = []
        too_hard = 0
        for site in surveyed:
            try:
                if site.kind() != "mineral" or getattr(site, "item_id", None) not in RAW_ORE_ITEM_IDS:
                    continue
                if can_cut(getattr(site, "hardness", None), max_drill_hardness):
                    sites.append(site)
                else:
                    too_hard += 1
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.cuttable_sites: site check", error)
        return sites, too_hard

    def reach_ores(self, sites, outpost_id):
        """
        Ores of `sites` with at least one site whose round trip from
        outpost_id fits a full battery (full_battery_reaches()). Walks the
        sites nearest first: an ore stops being checked at its first site in
        reach, and the walk ends at the first site whose outbound leg alone
        exceeds the battery, since every site after it is farther. None when
        the battery or drive rate can't be read (get_battery() falls back to
        a made-up capacity), so the caller publishes no false empty reach.
        """
        outpost = outpost_mining.outpost_by_id(outpost_id)
        ox, oy = getattr(outpost, "x", None), getattr(outpost, "y", None)
        origin = (ox, oy) if ox is not None and oy is not None else self._host.get_position()
        try:
            capacity = float(self._host.vehicle.battery.capacity())
            out_rate = self._host.wh_per_meter_at_throttle(self._host.cruise_throttle, cargo_units=0)
        except Exception as error:
            swallowed("vehicle_mining.VehicleMiningMixin.reach_ores: battery capacity", error)
            return None
        by_distance = []
        for site in sites:
            try:
                by_distance.append((self._host.distance_between(origin, (site.x, site.y)), site))
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.reach_ores: site distance", error)
        reach = set()
        for dist, site in sorted(by_distance, key=lambda pair: pair[0]):
            if dist * out_rate * self._host.SAFETY_MARGIN_MULTIPLIER + self._host.MIN_EMERGENCY_RESERVE_WH > capacity:
                break
            if site.item_id in reach:
                continue
            try:
                if self.full_battery_reaches(origin, (site.x, site.y), site.item_id, getattr(site, "purity", None)):
                    reach.add(site.item_id)
            except Exception as error:
                swallowed("vehicle_mining.VehicleMiningMixin.reach_ores: full_battery_reaches", error)
        return reach

    def full_battery_reaches(self, origin, coords, item_id, purity=None):
        """
        True when a full battery covers origin -> coords, one unit dug there
        and the drive on to the charging station nearest coords, at cruise
        throttle with the trip budget's margin and reserve
        (calculate_trip_energy() terms, from origin instead of the vehicle's
        position and against capacity instead of charge).
        """
        capacity = float(self._host.vehicle.battery.capacity())
        station, _ = self._host.get_nearest_charging_station(from_coords=coords)
        throttle = self._host.cruise_throttle
        net = self._host.distance_between(origin, coords) * self._host.wh_per_meter_at_throttle(throttle, cargo_units=0) + self._host.distance_between(coords, station) * self._host.wh_per_meter_at_throttle(throttle, cargo_units=1) + self._host.mine_wh_per_unit(item_id, purity)
        return net * self._host.SAFETY_MARGIN_MULTIPLIER + self._host.MIN_EMERGENCY_RESERVE_WH <= capacity

    def stock_urgency(self, item_id, room, band):
        """
        How badly a stationed miner's outpost lacks item_id, 0..1: the missing
        share of its stock target (room / ore_stock_target()), so a nearly
        empty ore outranks a half-full one that is faster to dig. Ore missing
        in a band above STOCK is 1.0 (the band already puts it first; the
        band dict carries no fine prio to scale it by).
        """
        if band > STOCK:
            return 1.0
        target = outpost_mining.ore_stock_target(item_id)
        if target <= 0:
            return 1.0
        return max(0.0, min(1.0, room / target))

    def mining_hours_per_unit(self, cand, pos):
        """
        Game hours per delivered unit of a mine candidate: dig time per unit
        (mounted drill, site purity) plus the round trip from pos spread over
        the units one trip brings (max_mineable_units() on the battery on
        board, capped by the candidate's max_units). All live, so a battery
        or loadout change re-ranks from the next pick. None when no unit fits.
        """
        item_id = cand.get("harvest_item")
        units = self._host.max_mineable_units(cand["coords"], item_id, cand.get("purity"))
        if cand.get("max_units") is not None:
            units = min(units, cand["max_units"])
        if units <= 0:
            return None
        speed = self._host.leg_speed_m_per_hour(cand["coords"][0], cand["coords"][1])
        if speed <= 0:
            return None
        drive_hours = 2 * self._host.distance_between(pos, cand["coords"]) / speed
        return self._host.mine_hours_per_unit(item_id, cand.get("purity")) + drive_hours / units

    def mining_score(self, cand, pos):
        """Urgency per hour of a mine candidate: its "urgency" (default 1.0) / mining_hours_per_unit(). 0.0 for a POI or a site no unit fits."""
        if cand.get("type") != "mine":
            return 0.0
        hours = self.mining_hours_per_unit(cand, pos)
        if not hours:
            return 0.0
        return cand.get("urgency", 1.0) / hours

    def stockpile_headroom(self, outpost_id, item_id):
        """
        Units of item_id still missing from outpost_id's stock target, net of
        the yield peers' trips there already reserved (this vehicle's own
        reservation excluded) and of hauler pickups bound there. 0 for an ore
        not yet active (outpost_mining.active_ores()) or without store room
        for its buffer (outpost_mining.ore_buffer_fits()).
        """
        if item_id not in outpost_mining.active_ores():
            return 0
        outpost = outpost_mining.outpost_by_id(outpost_id)
        if outpost is not None and not outpost_mining.ore_buffer_fits(outpost, item_id):
            return 0
        return self.stockpile_room(outpost_id, item_id, outpost_mining.ore_stock_target(item_id))

    def stockpile_room(self, outpost_id, item_id, level):
        """Units of item_id missing at outpost_id up to `level`: level minus
        its held stock (logistics_requests.outpost_stock(): Warehouses, Drone
        Depots, Inventory only at home), the yield peers' trips there already
        reserved (this vehicle's own excluded) and hauler pickups bound there."""
        outpost = outpost_mining.outpost_by_id(outpost_id)
        tick = self._host.get_current_tick()
        reserved = mining_reservations.get_reserved_yield_totals(tick, outpost_id=outpost_id, exclude_vehicle=self._host.name).get(item_id, 0)
        hauled = logistics_requests.in_flight(outpost_id, tick).get(item_id, 0)
        held = logistics_requests.outpost_stock([item_id], outpost).get(item_id, 0)
        return level - held - reserved - hauled

    def stockpile_bands(self, outpost_id):
        """
        {band: {ore: units}} outpost_id requests
        (logistics_requests.outpost_tier_deficits()), net of the yield peers'
        trips there already reserved (this vehicle's own excluded). Dock ore
        arrives through the ore request ladder like any other request. Plus
        the ore need of other outposts that no miner there reaches but one
        here does (remote_ore_need()), added per band. Latches every ore at
        NEED or above active (outpost_mining.latch_active_ores()).
        """
        tick = self._host.get_current_tick()
        outpost = outpost_mining.outpost_by_id(outpost_id)
        bands = ore_bands(logistics_requests.outpost_tier_deficits(outpost, tick, live=True, exclude_vehicle=self._host.name))
        for band, items in self.remote_ore_need(outpost_id, outpost, tick).items():
            dest = bands.setdefault(band, {})
            for ore, units in items.items():
                dest[ore] = dest.get(ore, 0) + units
        outpost_mining.latch_active_ores(split_need_stock(bands)[0])
        return bands

    def remote_ore_need(self, outpost_id, outpost, tick):
        """
        {band: {ore: units}} other outposts request at NEED or above for ore
        no miner stationed there reaches but one at outpost_id does
        (outpost_mining.mineable_ores_by_outpost()): outpost_id mines it and
        the haulers carry it over. Netted, highest band first, by the ore
        outpost_id holds or peers' trips will bring there, since haulers take
        that ore too. Every outpost that reaches the ore sees the whole need.
        """
        by_outpost = outpost_mining.mineable_ores_by_outpost(tick)
        mine = by_outpost.get(outpost_id) or set()
        if not mine:
            return {}
        wanted = {}
        for other_id in sorted(logistics_requests.active_requests(tick)):
            if other_id == outpost_id:
                continue
            other_ores = by_outpost.get(other_id) or set()
            deficits = logistics_requests.outpost_tier_deficits(outpost_mining.outpost_by_id(other_id), tick, live=False)
            for band, items in ore_bands(deficits).items():
                if band < NEED:
                    continue
                for ore, units in items.items():
                    if ore in mine and ore not in other_ores:
                        wanted.setdefault(band, {})[ore] = wanted.get(band, {}).get(ore, 0) + units
        if not wanted:
            return {}
        ores = sorted({ore for items in wanted.values() for ore in items})
        held = logistics_requests.outpost_stock(ores, outpost)
        reserved = mining_reservations.get_reserved_yield_totals(tick, outpost_id=outpost_id, exclude_vehicle=self._host.name)
        cover = {ore: held.get(ore, 0) + reserved.get(ore, 0) for ore in ores}
        out = {}
        for band in sorted(wanted, reverse=True):
            for ore, units in wanted[band].items():
                used = min(units, cover[ore])
                cover[ore] -= used
                if units > used:
                    out.setdefault(band, {})[ore] = units - used
        if out:
            self._host.log.debug(f"[{self._host.name}] remote_ore_need('{outpost_id}'): {out} (cover {held} held, {reserved} reserved).")
        return out

    def stockpile_need(self, outpost_id):
        """{ore: units} outpost_id requests at the NEED band or above (stockpile_bands())."""
        return split_need_stock(self.stockpile_bands(outpost_id))[0]

    def select_best_mining_target(self, candidates):
        """
        Sorts candidates by (priority, -band, -mining_score(), distance) --
        lower priority number wins first, then ore missing in a higher demand
        band at the delivery outpost beats lower-band ore, then the highest urgency per hour of
        mining time (purity, distance, drill and battery all count, see
        mining_hours_per_unit()), distance only breaking ties -- then claims the
        first one that fits the round-trip energy budget. Returns (target,
        budget, diagnostics); target is None when nothing is currently
        achievable.

        A mine target's claim is per vehicle (VehicleClaimsMixin.claim_key()),
        so a peer mining the same site never blocks it. Instead this estimates
        the trip's yield -- energy on board (max_mineable_units()), capped by
        the candidate's "max_units" (stockpile headroom) -- and registers it
        via mining_reservations.reserve_yield(). A peer's next search sees
        that much of the deficit already promised (home_ore_demand(),
        stockpile_headroom()) and only joins the site while demand is left.
        The estimate is stashed on the candidate as "estimated_units" so
        callers size the actual mining call to it.

        Feasibility is first checked at a full 10-unit haul; if that doesn't
        fit the round-trip budget, retries at whatever max_mineable_units()
        says IS affordable instead of rejecting the site outright -- a
        vehicle whose battery can never fit a full 10-unit trip (e.g. a
        Rover with no bigger battery available, or a Pioneer eyeing
        expensive-per-unit ore like Neutronium) would otherwise stand by at
        base forever despite live demand and a perfectly reachable smaller
        load. Only 0 affordable units is a genuine rejection.
        """
        self._host.log.start(f"[{self._host.name}] select_best_mining_target", level="debug")
        pos = self._host.get_position()
        for cand in candidates:
            cand["score"] = self.mining_score(cand, pos)
        candidates = sorted(
            candidates,
            key=lambda c: (
                c.get("priority", 2),
                -c.get("band", STOCK),
                -c["score"],
                self._host.distance_between(pos, c["coords"]),
            ),
        )
        self._host.log.debug("ranked: " + ", ".join(f"{c.get('harvest_item') or c['key']}={c['score']:.2f}" for c in candidates))

        self._host.log.trace(f"select_best_mining_target() enter: {len(candidates)} candidate(s)")
        budget_candidates = 0
        claims_lost = 0
        cheapest_rejected = None
        for cand in candidates:
            planned_mine = 10 if cand["type"] == "mine" else 0
            planned_scan = 1 if cand["type"] == "poi" else 0
            budget = self._host.calculate_trip_energy(
                cand["coords"],
                planned_drill_units=planned_mine,
                planned_scans=planned_scan,
                mine_item_id=cand.get("harvest_item"),
                mine_purity=cand.get("purity"),
            )

            # A full 10-unit haul is only ever a planning assumption for the
            # feasibility check, not a hard requirement -- a vehicle whose
            # battery can never fit 10 units' worth of round trip (e.g. a
            # Rover with no bigger battery available) would otherwise reject
            # every site and sit at base forever despite live demand and a
            # perfectly reachable partial load. If the full haul doesn't fit,
            # fall back to whatever IS affordable (max_mineable_units() --
            # same estimator already used below to size the real mining call)
            # and retry the budget check with that instead. Only 0 affordable
            # units is a genuine rejection.
            partial_load = False
            if not budget["is_achievable"] and cand["type"] == "mine":
                affordable = self._host.max_mineable_units(cand["coords"], cand["harvest_item"], cand.get("purity"))
                if affordable > 0:
                    self._host.log.debug(f"{cand['key']}: full {planned_mine}-unit load needs {budget['total_required_wh']:.1f} Wh, not affordable; retrying at {affordable} units.")
                    planned_mine = affordable
                    budget = self._host.calculate_trip_energy(
                        cand["coords"],
                        planned_drill_units=planned_mine,
                        planned_scans=planned_scan,
                        mine_item_id=cand.get("harvest_item"),
                        mine_purity=cand.get("purity"),
                    )
                    partial_load = budget["is_achievable"]

            if budget["is_achievable"]:
                budget_candidates += 1
                estimated_units = 0
                if cand["type"] == "mine":
                    estimated_units = self._host.max_mineable_units(cand["coords"], cand["harvest_item"], cand.get("purity"))
                    if cand.get("max_units") is not None:
                        estimated_units = max(0, min(estimated_units, cand["max_units"]))
                    cand["estimated_units"] = estimated_units
                mission = Mission(kind=cand["type"], target_key=cand["key"], target=cand, prio=cand.get("priority", 0), budget=budget, reserved_yield=estimated_units > 0)
                if not self._host.begin_mission(mission):
                    claims_lost += 1
                    self._host.log.debug(f"{cand['key']}: within budget ({budget['total_required_wh']:.1f} Wh) but claim lost to a peer; trying next candidate.")
                    continue
                self._host.log.debug(f"[{self._host.name}] select_best_mining_target(): won {cand['key']} (priority={cand.get('priority')}, band={band_name(cand.get('band', STOCK))}, purity={cand.get('purity')}, score={cand['score']:.2f}) at {cand['coords']}, budget={budget['total_required_wh']:.1f} Wh.")
                if partial_load:
                    self._host.log.print(f"[{self._host.name}] {cand['key']}: battery can't afford a full load -- heading out for a partial ~{planned_mine}-unit load instead of standing by.")
                self._host.log.trace(f"select_best_mining_target() exit: chose {cand['key']}, estimated_units={cand.get('estimated_units')}")
                _ret = cand, budget, {"candidate_count": len(candidates), "budget_candidates": budget_candidates, "claims_lost": claims_lost, "cheapest_rejected": cheapest_rejected}
                self._host.log.end()
                return _ret
            else:
                if cheapest_rejected is None or budget["total_required_wh"] < cheapest_rejected["total_required_wh"]:
                    cheapest_rejected = budget
                self._host.log.debug(f"{cand['key']}: unreachable within budget ({budget['total_required_wh']:.1f} Wh required); rejected.")

        self._host.log.trace(f"select_best_mining_target() exit: no achievable candidate ({budget_candidates}/{len(candidates)} within budget).")
        _ret = None, None, {"candidate_count": len(candidates), "budget_candidates": budget_candidates, "claims_lost": claims_lost, "cheapest_rejected": cheapest_rejected}
        self._host.log.end()
        return _ret

    def restore_yield_reservation_flag(self):
        """
        Called once after VehicleController.__init__'s load_mission() resumes
        a mission post-reload: reservations live in the archive independently
        of the in-memory Mission.reserved_yield flag, so a
        resumed mine-type mission needs this to re-arm refresh_yield()/
        release_yield() instead of silently letting its reservation go stale.
        """
        mission = self._host.mission
        if mission is None:
            return
        mission.reserved_yield = False
        entry = mining_reservations.reservation_of(self._host.name)
        if entry is not None and entry["target_key"] == mission.target_key:
            mission.reserved_yield = True

    def mine_current_site(self, max_units=None):
        """Extracts minerals using the mounted Drill Module while enforcing battery & cargo limits."""
        if not hasattr(self._host.vehicle, "drill"):
            self._host.log.level("error").print(f"[{self._host.name}] Error: No DrillModule mounted!")
            return 0

        cargo_capacity = self._host.vehicle.cargo.capacity() if hasattr(self._host.vehicle, "cargo") else 10
        if max_units is None:
            max_units = cargo_capacity
        # Callers may pass a stockpile headroom far above what the hold can
        # take (e.g. 1999 left to a 2000-unit stock target); the cargo.full()
        # check stops us anyway, so cap here to keep progress logs honest.
        free_space = cargo_capacity - self._host.vehicle.cargo.count() if hasattr(self._host.vehicle, "cargo") else cargo_capacity
        max_units = max(0, min(max_units, free_space))

        self._host.publish_telemetry("MINING")
        mined_count = 0
        self.mining_interrupted_battery = False

        self._host.log.start(f"[{self._host.name}] Mining (up to {max_units} units, cargo {self._host.vehicle.cargo.count()}/{cargo_capacity})")
        while mined_count < max_units:
            if self._host.vehicle.cargo.full():
                self._host.log.print(f"[{self._host.name}] Cargo hold full ({cargo_capacity}/{cargo_capacity}). Finishing mining operation.")
                break

            if self._host.is_recalled():
                self._host.log.print(f"[{self._host.name}] Recall requested; ceasing extraction to return to base.")
                break

            curr_wh, _, _ = self._host.get_battery()
            # Comfortable (not bare-minimum) reserve: stopping here still leaves
            # enough charge for a normal-speed return, instead of grinding down
            # to the true floor and being forced to crawl home at minimum throttle.
            needed_to_return = self._host.energy_needed_to_return_comfortably()
            if curr_wh <= (needed_to_return + self._host.MINE_WH_PER_UNIT * 1.5):
                self._host.log.print(f"[{self._host.name}] Reached return energy threshold ({curr_wh:.1f} Wh left). Ceasing extraction for recharge.")
                self.mining_interrupted_battery = True
                break

            m_res = self._host.vehicle.drill.mine()
            if m_res.status == "ok":
                mined_count += 1
                if self._host.mission is not None:
                    self._host.clear_unsupported_target(self._host.mission.target_key)
                self._host.log.trace(f"[{self._host.name}] Mined unit {mined_count}/{max_units}. Cargo: {self._host.vehicle.cargo.count()}/{cargo_capacity}.")
            elif m_res.status == "busy":
                flush_all()
                sleep(0.5)
            else:
                self._host.log.print(f"[{self._host.name}] Drill finished or stopped: {m_res.status} - {m_res.message}")
                if m_res.status in ["tier_too_low", "too_hard", "research_required", "depleted", "not_found", "empty"]:
                    if self._host.mission is not None:
                        self._host.blacklist_target(self._host.mission.target_key, m_res.status, m_res.message, scanner_type="drill")
                break

            if self._host.mission is not None:
                self._host.refresh_claim(self._host.mission.target_key)
                if self._host.mission.reserved_yield:
                    mining_reservations.refresh_yield(self._host.name, self._host.get_current_tick())

        self._host.log.end(f"[{self._host.name}] Mined {mined_count}/{max_units} units")
        return mined_count

    def mine_until_full_or_exhausted(self, target_coords, max_units=None):
        """
        Mines the current site to cargo capacity (or max_units, if given --
        e.g. a stockpile target's remaining headroom, so a stationed miner
        doesn't overshoot a Warehouse stock target and waste a material slot
        on the overflow), recharging at the nearest station and driving back
        to resume as many times as needed when interrupted by low battery
        (mirrors the recharge-and-resume pattern used for construction jobs
        in pioneer.py's execute_construction()). max_units bounds the whole
        job, units unloaded at a base stop included, and an at-base unload
        ends the job so the next cycle picks its target from current demand.
        """
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() enter: target_coords={target_coords}, max_units={max_units}")
        total_mined = self.mine_current_site(max_units=max_units)

        while getattr(self, "mining_interrupted_battery", False) and not self._host.vehicle.cargo.full():
            if self._host.is_recalled():
                self._host.log.print(f"[{self._host.name}] Recall requested; not resuming mining after recharge.")
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: recalled, total_mined={total_mined}")
                return
            left = None if max_units is None else max_units - total_mined
            if left is not None and left <= 0:
                break
            self._host.log.start(f"[{self._host.name}] Mining job at {target_coords} interrupted by low battery; recharge and resume")
            mined, stop_reason = self._recharge_and_resume_mining(target_coords, left)
            self._host.log.end(f"[{self._host.name}] {'Resumed, mined ' + str(mined) + ' more' if stop_reason is None else 'Not resumed: ' + stop_reason}")
            total_mined += mined
            if stop_reason is not None:
                self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: {stop_reason}, total_mined={total_mined}")
                return
        self._host.log.trace(f"[{self._host.name}] mine_until_full_or_exhausted() exit: complete, total_mined={total_mined}")

    def _recharge_and_resume_mining(self, target_coords, max_units):
        """One recharge detour and resumed mining pass; returns (units mined, reason it stopped or None to keep going).

        max_units is what the job may still mine (None = up to cargo capacity).
        """
        if self._host.mission is not None:
            self._host.refresh_claim(self._host.mission.target_key)
            if self._host.mission.reserved_yield:
                mining_reservations.refresh_yield(self._host.name, self._host.get_current_tick())

        nearest_cs, _ = self._host.get_nearest_charging_station()
        reached_cs = self._host.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0)
        if not reached_cs:
            self._host.log.level("warn").print(f"[{self._host.name}] Failed to reach charging station during mining interruption.")
            return 0, "could not reach charging station"

        # A battery-interruption recharge stop can land at the home base
        # station itself (not just some remote field station) -- if so,
        # and cargo is already carrying ore, unload it *before* recharging:
        # recharge_at_station() can take several real minutes, and ore in
        # cargo the whole time is ore the Smelter can't touch. The load is
        # then delivered, so the job ends: resuming would keep mining this
        # ore with an empty hold and never re-check demand (a stationed
        # miner whose battery ran out before its hold filled stockpiled one
        # ore for hours while the others ran dry).
        delivered = self._host.is_at_base() and self._host.vehicle.cargo.count() > 0
        if delivered:
            self._host.log.print(f"[{self._host.name}] At base with cargo aboard; unloading before recharging.")
            self._host.unload_cargo()

        self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)

        # Pioneer-only Sonar/Drill upgrade at a base stop inside the job
        # (lib/pioneer_upgrade.py). hasattr-gated: RoverController shares
        # this mixin without PioneerUpgradeMixin.
        mid_job_upgrade = getattr(self._host, "run_module_upgrades_mid_job", None)
        if mid_job_upgrade is not None:
            mid_job_upgrade()
        if delivered:
            return 0, "load delivered at base"

        self._host.log.print(f"[{self._host.name}] Recharged to 100%. Returning to resume mining at {target_coords}...")
        if self._host.mission is not None:
            self._host.publish_telemetry("OUTBOUND", self._host.mission.target.get("name", "mining site"))
        reached_site = self._host.drive_with_recharge(target_coords[0], target_coords[1], precision=1.5)
        if not reached_site:
            self._host.log.level("warn").print(f"[{self._host.name}] Could not reach mining site after recharge.")
            return 0, "could not reach site after recharge"

        remaining_space = self._host.vehicle.cargo.capacity() - self._host.vehicle.cargo.count()
        if max_units is not None:
            remaining_space = min(remaining_space, max(0, max_units))
        if remaining_space > 0:
            return self.mine_current_site(max_units=remaining_space), None
        return 0, "no remaining space"
