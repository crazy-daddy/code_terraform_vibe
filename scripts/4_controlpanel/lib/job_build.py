# BuildJob: the Constructor Pioneer's role (lib/job_base.py contract). Each
# step picks a construction blueprint (pending/paused, by construction.priority
# and reachability), claims it exclusively, stocks its material at home and
# builds it. run_job_loop(BuildJob(pioneer)) runs it (lib/pioneer.py).
# Archive I/O: lib/construction_lots.py; planning math: lib/construction_plan.py;
# stocking: lib/pioneer_stock.py; the build action itself:
# lib/pioneer_construction.py execute_construction().

from typing import TYPE_CHECKING

import construction_lots
import construction_plan
from atomic import run_atomic, run_batched
from job_base import Job

if TYPE_CHECKING:
    from pioneer import PioneerController


class ConstructionWork:
    """Jobs one BuildJob step may work on, cut to the top open priority."""

    def __init__(self, paused, pending, matching, priority, held_back, position, lot=None):
        self.paused = paused  # paused job rows (resuming already-paid work)
        self.pending = pending  # pending job rows
        self.matching = matching  # (priority, ..., row) entries the cargo aboard can serve
        self.priority = priority  # priority being worked on
        self.held_back = held_back  # open jobs at lower priorities
        self.position = position  # Pioneer position at scan time
        self.lot = lot or set()  # job ids in this Pioneer's construction.lots entry


class BuildJob(Job):
    """
    Constructor role. Overrides step() wholesale: battery reserve, resume a
    paused job, build a pending job the cargo aboard serves, else claim the
    next job and stock its material.
    """

    name = "build"
    recall_delay = 5.0
    idle_delay = 10.0
    # Narrows Job.host: a BuildJob only ever runs on a PioneerController.
    host: "PioneerController"  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, host):
        super().__init__(host)
        # Job ids skipped until no other option remains (unreachable, failed,
        # or waiting for material); cleared when the Pioneer idles.
        self.failed_jobs = set()
        # Items already announced at info level as awaited.
        self.material_waits = set()
        # The host's cruise_throttle before the first trip plan (_plan_trip_throttle()).
        self.base_cruise_throttle = None

    def announce(self):
        self.host.log.print(f"Pioneer Controller ({self.host.name}) online. Monitoring construction blueprints.")

    def on_error(self):
        """Releases every claim and the lot this Pioneer holds: a Constructor holds build_* claims outside self.host.mission."""
        self.host.release_target_claim()
        self._release_lot()

    def on_leave(self):
        self.on_error()

    def _release_lot(self):
        construction_lots.release_lot(self.host.name, self.host.get_current_tick(), self.host.log)

    def step(self):
        """
        One pass, first applicable step wins: battery reserve, resume a
        paused job, build a pending job the cargo aboard serves, else claim
        the next job and stock its material. Returns the seconds to sleep
        before the next pass (0 = at once).
        """
        self._ready_at_base()
        if self._return_if_reserve_reached():
            return 0

        # Priorities first: see construction_lots.prune_priorities().
        priorities = construction_lots.read_priorities()
        bp = get_component("construction_blueprint")
        paused, paused_ok = construction_lots.read_jobs(bp, "paused_constructions")
        pending, pending_ok = construction_lots.read_jobs(bp, "pending_constructions")
        # Only sweep leaked claims when every list read cleanly -- a failed
        # read would make live jobs look finished.
        lists_ok = bool(bp) and paused_ok and pending_ok
        if not paused and not pending:
            return self._idle_without_jobs(bp, lists_ok, priorities)

        work = self._select_work(bp, paused, pending, lists_ok, priorities)
        self._plan_trip_throttle(work.matching)
        delay = self._resume_paused_job(work.paused)
        if delay is None and work.matching:
            delay = self._build_matching_job(work.matching, work.position)
        if delay is None:
            delay = self._restock_for_next_job(work)
        return delay

    def _ready_at_base(self):
        """Parked at home: charge before departing and run the idle upgrade cycle."""
        host = self.host
        if not host.is_at_base():
            return
        _, _, lvl = host.get_battery()
        if lvl < 0.90:
            host.recharge_at_station(target_level=1.0)
        host.handle_upgrade_cycle_if_idle()

    def _return_if_reserve_reached(self):
        """
        Heads to the nearest station once the battery is down to the reserve
        for a normal-speed return, not just the bare survival floor (which
        would leave conserve mode nothing to spend but the slowest crawl
        home). True when it drove off to recharge.
        """
        curr_wh, _, _ = self.host.get_battery()
        if curr_wh > self.host.energy_needed_to_return_comfortably():
            return False
        self.host.recharge_at_nearest("Return reserve reached in field; returning to nearest station to recharge.", "Field recharge done.")
        return True

    def _idle_without_jobs(self, bp, lists_ok, priorities):
        """No paused or pending job: sweep state of finished blueprints, then idle at home."""
        host = self.host
        host.log.debug(f"[{host.name}] BuildJob: no paused or pending construction jobs; idling.")
        if lists_ok:
            active, active_ok = construction_lots.read_jobs(bp, "active_constructions")
            if active_ok:
                live_ids = {getattr(j, "id", getattr(j, "blueprint_id", None)) for j in active}
                construction_lots.sweep_dead_jobs(host.name, live_ids, host.get_claims(), priorities, host.log)
        self.failed_jobs.clear()
        self._release_lot()
        return self.idle()

    def _select_work(self, bp, paused, pending, lists_ok, priorities):
        """
        Scans the job lists into a ConstructionWork: drops jobs a peer owns
        (claim or lot), failed ones and held kinds, then keeps only the top
        open priority. Also sweeps dead claims/priorities when every list
        read cleanly.
        """
        host = self.host
        name = host.name
        # Unlike mining POIs (several Pioneers can dig the same site), a
        # construction job is NOT shareable -- two Constructor Pioneers both
        # loading/building the same blueprint would double-load materials and
        # waste a trip. The scan skips anything a peer already owns
        # (self-owned claims pass through, per construction_plan.claim_free()),
        # and every job in an active peer's lot; own-lot jobs sort first.
        existing_claims = host.get_claims()
        curr_tick = host.get_current_tick()
        taken, lot = construction_lots.read_lots(name, curr_tick)
        active, active_ok = construction_lots.read_jobs(bp, "active_constructions")
        lists_ok = lists_ok and active_ok
        current_pos = host.get_position()
        cargo = host.cargo_counts()
        scan_args = (current_pos, cargo, existing_claims, name, curr_tick, host.CLAIM_STALE_TICKS, self.failed_jobs, priorities, taken, lot)
        paused_ids, paused_rows, _ = construction_plan.scan_jobs(paused, *scan_args)
        pending_ids, pending_rows, matching = construction_plan.scan_jobs(pending, *scan_args)
        if lists_ok:
            active_ids, _, _ = construction_plan.scan_jobs(active, *scan_args)
            construction_lots.sweep_dead_jobs(name, set(paused_ids + pending_ids + active_ids), existing_claims, priorities, host.log)
        held = construction_lots.read_hold(curr_tick)
        if held:
            # Held jobs still count as live above (claims, priorities); they are only not worked on.
            paused_rows = [row for row in paused_rows if row["kind"] not in held]
            pending_rows = [row for row in pending_rows if row["kind"] not in held]
            matching = [entry for entry in matching if entry[-1]["kind"] not in held]
            host.log.debug(f"[{name}] Construction hold: skipping {', '.join(sorted(held))} jobs.")
        host.log.debug(f"[{name}] Job scan: {len(paused_rows)}/{len(paused_ids)} paused and {len(pending_rows)}/{len(pending_ids)} pending open, {len(matching)} matching cargo {cargo}, own lot {len(lot)}, {len(taken)} in peers' lots.")

        # Only the lowest open priority is worked on: a lower-priority job
        # is neither built nor stocked for while a higher one is open
        # (failed this pass or claimed by a peer counts as not open).
        top_prio = construction_plan.top_priority(paused_rows + pending_rows)
        held_back = len(paused_rows) + len(pending_rows)
        paused_rows = construction_plan.at_priority(paused_rows, top_prio)
        pending_rows = construction_plan.at_priority(pending_rows, top_prio)
        matching = [entry for entry in matching if entry[0] == top_prio]
        held_back -= len(paused_rows) + len(pending_rows)
        if held_back:
            host.log.debug(f"[{name}] Working priority {top_prio}: {len(paused_rows)} paused and {len(pending_rows)} pending job(s); {held_back} lower-priority job(s) held back.")
        return ConstructionWork(paused_rows, pending_rows, matching, top_prio, held_back, current_pos, lot)

    def _plan_trip_throttle(self, matching):
        """
        At a charging station, sets the host's cruise_throttle for the coming
        trip over the jobs the cargo serves (construction_plan.trip_throttle()):
        a far chain is driven slower so one charge builds more of it instead
        of one job per round trip. Back to the base throttle when no job is
        served or none fits. Away from a station it keeps the planned
        throttle, which the field reserve checks read too, until the next
        station.
        """
        host = self.host
        name = host.name
        base = self.base_cruise_throttle
        if base is None:
            base = self.base_cruise_throttle = host.cruise_throttle
        station, _ = host.get_nearest_charging_station()
        position = host.get_position()
        if host.distance_between(position, station) > 3.0:
            return
        plan = None
        if matching:
            stations = [st["coords"] for st in host.get_all_charging_stations()] or [station]
            route = run_atomic(construction_plan.trip_route, position, [entry[-1] for entry in matching], stations, construction_plan.TRIP_PLAN_JOBS)
            floor = host.MIN_SPEEDMODE_THROTTLE
            steps = int((base - floor) / construction_plan.TRIP_THROTTLE_STEP + 1e-6)
            throttles = [round(base - i * construction_plan.TRIP_THROTTLE_STEP, 3) for i in range(steps + 1)]
            if throttles[-1] > floor:
                throttles.append(floor)
            rates = [(t, host.wh_per_meter_at_throttle(t)) for t in throttles]
            # drive_with_recharge() adds the emergency reserve to both the leg out and the leg to the station.
            plan = run_atomic(
                construction_plan.trip_throttle, route, rates, host.wh_per_progress,
                host.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, host.SAFETY_MARGIN_MULTIPLIER,
                2 * host.MIN_EMERGENCY_RESERVE_WH, host.get_battery()[0],
            )
        throttle = plan[0] if plan else base
        if throttle != host.cruise_throttle:
            if plan and throttle < base:
                host.log.print(f"[{name}] Trip throttle {throttle*100:.0f}% (cruise {base*100:.0f}%): one charge covers {plan[1]} chained job(s).")
            else:
                host.log.debug(f"[{name}] Trip throttle back to cruise {base*100:.0f}%.")
            host.cruise_throttle = throttle
        elif plan:
            host.log.debug(f"[{name}] Trip throttle {throttle*100:.0f}% covers {plan[1]} chained job(s).")

    def _job_trip_budget(self, row, at_floor=False):
        """
        calculate_trip_energy() for one job row, budgeting this trip's share
        of its progress. at_floor prices driving at the speedmode throttle
        floor (minimum_wh_per_meter()) instead of the calibrated rate.
        """
        host = self.host
        return host.calculate_trip_energy(
            row["coords"], planned_drill_units=0, planned_scans=0,
            planned_construction_progress=construction_lots.planned_progress_for_job(row["job"], host.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP),
            wh_per_meter=host.minimum_wh_per_meter() if at_floor else None,
        )

    def _claim_and_build(self, row, verb):
        """
        Claims row's job and builds it. None when a peer won the claim
        between scan and claim (the caller falls through to its next step),
        else the seconds to sleep.
        """
        host = self.host
        job_id = row["id"]
        coords = row["coords"]
        key = host.construction_claim_key(job_id)
        if not host.claim_target(key, {"type": "build", "coords": coords, "name": job_id}):
            return None
        host.log.debug(f"[{host.name}] {verb} construction job: {job_id} at {coords}.")
        if not host.execute_construction(job_id, coords, kind=row["kind"]):
            self.failed_jobs.add(job_id)
            host.release_target_claim(key)
            return 2.0
        if host.last_build_progress >= 1.0:
            host.release_target_claim(key)
        return 0

    def _resume_paused_job(self, rows):
        """
        Resumes the first paused job (already-paid work) within reach; None
        when none was started. A job a peer claimed since the scan passes
        to the next one.
        """
        for row in rows:
            if not row["coords"]:
                continue
            if self._job_trip_budget(row)["is_achievable"]:
                delay = self._claim_and_build(row, "Resuming paused")
                if delay is not None:
                    return delay
                continue
            if self.host.distance_to_home() > 3.0:
                # Cannot reach safely from current field position.
                self.host.recharge_at_nearest("Insufficient energy to reach paused job safely; recharging at nearest station.", "Recharge before paused job done.")
                return None
        return None

    def _build_matching_job(self, matching, position):
        """
        Builds the nearest pending job the cargo aboard serves (materials or
        deconstruction). Gated on the speedmode throttle floor, not the
        typical calibrated rate: drive_with_recharge()/select_cruise_throttle()
        pick whatever throttle the leg needs, so a job only reachable by
        conserving hard is still attempted. A job a peer claimed since the
        scan passes to the next one; when peers took every reachable one,
        rescan rather than fall through to restocking, which would drive home
        with the cargo still aboard.
        """
        lost = False
        for entry in matching:
            row = entry[-1]
            if row["coords"] and self._job_trip_budget(row, at_floor=True)["is_achievable"]:
                delay = self._claim_and_build(row, "Executing chained")
                if delay is not None:
                    return delay
                lost = True
        if lost:
            return 2.0
        return self._charge_for_matching_jobs(matching, position)

    def _charge_for_matching_jobs(self, matching, position):
        """Cargo serves pending jobs none of which is reachable: recharge, or mark them failed when even a full battery can't."""
        host = self.host
        name = host.name
        station, _ = host.get_nearest_charging_station()
        if host.distance_between(position, station) > 3.0:
            host.recharge_at_nearest("Insufficient energy to reach next construction site; recharging at nearest station.", "Recharge before next site done.", station)
            return 0
        _, cap_wh, lvl = host.get_battery()
        if lvl < 0.98:
            host.log.start(f"[{name}] At station with materials but need charge ({lvl*100:.0f}%); recharging to full.")
            host.recharge_at_station(target_level=1.0, station_coords=station)
            host.log.end(f"[{name}] Recharged with materials aboard.")
            return 0
        # Full at a station and the floor-rate budget still fails: out of
        # range even at the slowest possible throttle.
        req_details = []
        for entry in matching:
            row = entry[-1]
            if row["coords"]:
                req_details.append(f"{row['id']} ({self._job_trip_budget(row, at_floor=True)['total_required_wh']:.1f} Wh)")
            else:
                req_details.append(f"{row['id']}")
            self.failed_jobs.add(row["id"])
        host.log.level("warn").print(f"[{name}] Advisory: Matching construction job(s) exceed maximum battery range even at minimum throttle ({cap_wh:.1f} Wh): {', '.join(req_details)}.")
        return 5.0

    def _reachable_pending_jobs(self, rows):
        """
        Pending rows a full battery can serve from the nearest charging
        station, at the speedmode throttle floor (the true bound, since
        conserve mode can always throttle down that far) and budgeting the
        minimum useful on-site progress (TARGET_CONSTRUCTION_PROGRESS_PER_TRIP).
        A job beyond that is permanently out of range and is marked failed.
        """
        host = self.host
        _, cap_wh, _ = host.get_battery()
        stations = [st["coords"] for st in host.get_all_charging_stations()] or [host.home_coords]
        trips = run_batched(
            construction_plan.station_trip_wh, rows, construction_plan.TRIP_CHUNK,
            stations, host.minimum_wh_per_meter(), host.wh_per_progress,
            host.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, host.SAFETY_MARGIN_MULTIPLIER, host.MIN_EMERGENCY_RESERVE_WH,
        )
        reachable = []
        for row, required_wh in trips:
            if required_wh is not None and required_wh > cap_wh:
                if row["id"] not in self.failed_jobs:
                    host.log.level("warn").print(f"[{host.name}] Construction job '{row['id']}' at {row['coords']} permanently exceeds battery capacity from nearest station even at minimum throttle ({required_wh:.1f} Wh required, {cap_wh:.1f} Wh max capacity). Marking failed.")
                    self.failed_jobs.add(row["id"])
                continue
            reachable.append(row)
        return reachable

    def _claim_first(self, rows):
        """
        Claims the first row this Pioneer can win, before the round trip home
        for materials, so a peer doesn't also fetch and build the same job.
        None when every row is already claimed.
        """
        host = self.host
        for row in rows:
            if host.claim_target(host.construction_claim_key(row["id"]), {"type": "build", "coords": row["coords"], "name": row["id"]}):
                return row
        return None

    def _restock_for_next_job(self, work):
        """No job is buildable with the cargo aboard: claim the next reachable pending job and stock for it at home."""
        host = self.host
        name = host.name
        targets = self._reachable_pending_jobs(work.pending)
        if not targets and work.held_back and work.pending:
            # Every pending job at this priority was just marked failed;
            # rescan so the held-back lower-priority jobs get their turn.
            host.log.debug(f"[{name}] BuildJob: no reachable job at priority {work.priority}; rescanning for lower-priority jobs.")
            return 0
        if not targets:
            host.log.debug(f"[{name}] BuildJob: every pending job is unreachable this cycle; clearing failed_jobs and idling.")
            self.failed_jobs.clear()
            return self.idle()

        # Unbuilt jobs of this Pioneer's own lot first: it continues its own
        # stretch rather than starting a new one next to it.
        if work.lot:
            targets = [row for row in targets if row["id"] in work.lot] + [row for row in targets if row["id"] not in work.lot]
        job = self._claim_first(targets)
        if job is None:
            return 2.0

        if host.distance_to_home() > 3.0:
            host.return_to_base()
        # Fully charged before embarking on a new batch.
        _, _, lvl = host.get_battery()
        if lvl < 0.98:
            host.recharge_at_station(target_level=1.0)

        if job["item"] and job["count"] > 0:
            return self._stock(job, targets)
        # Deconstruction job: make room for the reclaimed materials.
        host.log.debug(f"[{name}] BuildJob: deconstruction job {job['id']}, no materials required.")
        if hasattr(host.vehicle, "cargo") and host.vehicle.cargo.full():
            host.unload_cargo()
        self._reserve_lot(job, targets, construction_plan.DECONSTRUCT_LOT_JOBS)
        return 0

    def _stock(self, job, targets):
        """Stocks job's material at home (ConstructionStockMixin.stock_materials()) and reserves the lot it covers, else defers."""
        host = self.host
        item = job["item"]
        status, extra = host.stock_materials(job, targets)
        if status == "aboard":
            self._reserve_lot(job, targets, host.cargo_count(item))
            return 2.0
        if status == "loaded":
            self.material_waits.discard(item)
            self._reserve_lot(job, targets, host.cargo_count(item), extra)
            return 0
        return self._defer_jobs_needing(item, job, targets)

    def _reserve_lot(self, job, targets, units, extra=()):
        """
        Reserves job plus the nearest chain of same-material jobs in targets
        that units cover as this Pioneer's construction.lots entry, so peers
        work elsewhere (construction_plan "build lots"); each (seed row,
        units) in extra adds the chain of its material the same way.
        targets was scanned before the trip home, so jobs a peer claimed
        since are left out. When a peer's lot took job meanwhile, job's
        claim is released: the lot owner builds it, and its scan skips a
        job claimed by anyone else.
        """
        host = self.host
        name = host.name
        claims = host.get_claims()
        tick = host.get_current_tick()
        free = [
            row for row in targets
            if construction_plan.claim_free(claims.get(construction_plan.claim_key(row["id"])), name, tick, host.CLAIM_STALE_TICKS)
        ]
        lot = construction_plan.lot_prefix(construction_plan.grow_lot(job, free, units), units)
        free_ids = {row["id"] for row in free}
        for seed, seed_units in extra:
            if seed["id"] in free_ids:
                lot += construction_plan.lot_prefix(construction_plan.grow_lot(seed, free, seed_units), seed_units)
        kept = construction_lots.write_lot(name, tick, lot)
        host.log.print(f"[{name}] Reserved lot of {len(kept)} job(s) from {job['id']} for {units + sum([n for _, n in extra])} unit(s).")
        if job["id"] not in kept:
            host.log.print(f"[{name}] {job['id']} is in a peer's lot; releasing its claim.")
            host.release_target_claim(host.construction_claim_key(job["id"]))

    def _defer_jobs_needing(self, item, job, targets):
        """
        item isn't obtainable right now (home storage empty, or a peer holds
        the whole stock): defers every job needing it, not just this one, so
        jobs whose materials are on hand get a turn this cycle. Material still
        being fabricated or hauled home is normal, so info once per wait,
        debug while it repeats.
        """
        host = self.host
        deferred = construction_plan.ids_needing(targets, item)
        line = f"[{host.name}] Waiting for {item} ({host.material_wait_reason(item)}); deferring {len(deferred)} job(s) needing it."
        if item in self.material_waits:
            host.log.debug(line)
        else:
            host.log.print(line)
            self.material_waits.add(item)
        self.failed_jobs.update(deferred)
        self.failed_jobs.add(job["id"])
        host.release_target_claim(host.construction_claim_key(job["id"]))
        self._release_lot()
        return 2.0
