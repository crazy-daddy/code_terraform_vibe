# Pioneer mixin: Constructor Module field work. Picks a construction
# blueprint (pending/paused, by construction.priority and reachability),
# claims it exclusively, stocks its material at home and builds it
# (pipes, power lines, outposts, pumps, caps, deconstruction).
# Composed into PioneerController only (lib/pioneer.py); job scanning,
# priorities, holds and batching math live in lib/construction_plan.py.

from archive import archive
from vehicle_claims import SURVEY_CLAIMS_KEY, LEGACY_ROVER_CLAIMS_KEY
from storage import take_item, takeable_stock
import fleet_status
from version_guard import validate_game_version
import drill_sites
import fleet_intent
from swallow import swallowed
import construction_plan
import logistics_requests
from atomic import run_batched
from tree_console import flush_all, method_block, reset_all
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pioneer import PioneerController


class ConstructionWork:
    """Jobs one pass of the constructor loop may work on, cut to the top open priority."""

    def __init__(self, paused, pending, matching, priority, held_back, position):
        self.paused = paused  # paused job rows (resuming already-paid work)
        self.pending = pending  # pending job rows
        self.matching = matching  # (priority, ..., row) entries the cargo aboard can serve
        self.priority = priority  # priority being worked on
        self.held_back = held_back  # open jobs at lower priorities
        self.position = position  # Pioneer position at scan time


class PioneerConstructionMixin:
    """
    Constructor role of PioneerController: run_construction_loop() and the
    build/stock/claim steps it uses. Depends on VehicleController's energy,
    navigation, claims and cargo mixins.
    """
    # Minimum construction progress a trip should budget for so a job finishes
    # in roughly 4 round trips rather than dozens of drive-there-do-almost-
    # nothing-drive-back cycles. Capped at whatever progress remains.
    TARGET_CONSTRUCTION_PROGRESS_PER_TRIP = 0.25

    @property
    def _host(self) -> "PioneerController":
        return self  # type: ignore[return-value]

    def construction_claim_key(self, job_id):
        """
        Shared claims dict key for a construction job -- distinct prefix from
        mining's "site_"/POI's "poi_" so the three never collide in the same
        archive dict. Unlike mining sites (several Pioneers can now dig the
        same POI), a construction job is NOT shareable: two Constructor
        Pioneers both loading/building the same blueprint would double-load
        materials and waste a trip, so this reuses vehicle_claims.py's
        existing EXCLUSIVE claim mechanism as-is (see construction_plan.claim_free())
        rather than mining_reservations.py's non-exclusive yield-debit pattern.
        """
        return construction_plan.claim_key(job_id)

    def get_construction_progress(self, blueprint_id):
        """
        Current 0-1 progress for a blueprint id, checking pending/active/paused lists.

        A blueprint that is in NONE of those lists (while at least one of them
        could actually be read) is finished (or was removed), so it counts as
        1.0: the game drops a completed blueprint from every list. Without this,
        run_construction_loop()'s "release the claim once progress >= 1.0"
        check never fires (stale build_* claims block other builders for up to
        CLAIM_STALE_TICKS), and the completing execute() step reads as negative
        progress, so calibrate_wh_per_progress() ignores it. Stays 0.0 when the
        component or every list is unreadable.
        """
        bp = get_component("construction_blueprint")
        if not bp:
            return 0.0
        any_list_read = False
        for getter_name in ("pending_constructions", "active_constructions", "paused_constructions"):
            getter = getattr(bp, getter_name, None)
            if not getter:
                continue
            try:
                jobs = getter() or []
            except Exception as error:
                swallowed("pioneer_construction.PioneerConstructionMixin.get_construction_progress: getter", error)
                continue
            any_list_read = True
            progress = construction_plan.job_progress(jobs, blueprint_id)
            if progress is not None:
                return progress
        if any_list_read:
            self._host.log.debug(f"[{self._host.name}] get_construction_progress({blueprint_id}): not in any blueprint list -- treating as complete (1.0)")
            return 1.0
        return 0.0

    def release_finished_construction_claims(self, live_job_ids, existing_claims):
        """
        Drops every build_* claim THIS Pioneer holds whose blueprint is no
        longer live (not in pending/active/paused) -- finished or removed
        while this script wasn't the one to observe it (restart mid-build, or
        claims leaked before get_construction_progress() learned that "gone"
        means done). One transaction per claims key, and only when something
        actually needs releasing (checked first against existing_claims, which
        the caller already fetched).
        """
        mine = [
            key for key, claim in (existing_claims or {}).items()
            if key.startswith("build_") and isinstance(claim, dict)
            and (claim.get("vehicle") == self._host.name or claim.get("rover") == self._host.name)
            and key[len("build_"):] not in live_job_ids
        ]
        if not mine:
            return 0
        dead = set(mine)

        def updater(claims):
            if not isinstance(claims, dict):
                return {}
            return {k: v for k, v in claims.items() if k not in dead}

        archive.transaction(SURVEY_CLAIMS_KEY, {}, updater)
        archive.transaction(LEGACY_ROVER_CLAIMS_KEY, {}, updater)
        self._host.log.print(f"[{self._host.name}] Released {len(dead)} build claim(s) on finished/removed blueprints.")
        return len(dead)

    def read_construction_priorities(self):
        """{blueprint_id: int} from the construction.priority archive dict ({} when absent or unreadable)."""
        try:
            return construction_plan.clean_priorities(archive.get(construction_plan.PRIORITY_KEY, {}))
        except Exception as error:
            swallowed("pioneer_construction.PioneerConstructionMixin.read_construction_priorities: archive.get", error)
            return {}

    def read_construction_hold(self, tick):
        """Job kinds held by a fresh construction.hold (lib/construction_plan.py held_kinds()); empty when absent or unreadable."""
        try:
            return construction_plan.held_kinds(archive.get(construction_plan.HOLD_KEY, None), tick)
        except Exception as error:
            swallowed("pioneer_construction.PioneerConstructionMixin.read_construction_hold: archive.get", error)
            return set()

    def note_finished_power_job(self, kind, coords):
        """Records a finished power-line, power-bridge or deconstruction job in construction.power_tiles."""
        if kind not in (construction_plan.POWER_LINE_KIND, construction_plan.POWER_BRIDGE_KIND, construction_plan.DECONSTRUCT_KIND):
            return
        if not coords:
            return

        def updater(current):
            return construction_plan.note_power_job(current, kind, coords[0], coords[1])

        archive.transaction(construction_plan.POWER_TILES_KEY, construction_plan.empty_power_ledger(), updater)
        self._host.log.debug(f"[{self._host.name}] Power ledger: noted {kind} at ({coords[0]:.0f}, {coords[1]:.0f}).")

    def prune_construction_priorities(self, priorities, live_job_ids):
        """
        Drops construction.priority entries whose blueprint is not live.
        priorities must be read before the job lists, so an entry written
        after its blueprint was queued is never mistaken for a dead one.
        """
        stale = construction_plan.stale_priorities(priorities, live_job_ids)
        if not stale:
            return 0
        dead = set(stale)

        def updater(current):
            if not isinstance(current, dict):
                return {}
            return {k: v for k, v in current.items() if k not in dead}

        archive.transaction(construction_plan.PRIORITY_KEY, {}, updater)
        self._host.log.debug(f"[{self._host.name}] Pruned {len(dead)} construction.priority entr(ies) of finished/removed blueprints.")
        return len(dead)

    def planned_progress_for_job(self, job):
        """Remaining progress capped at TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, for trip budgeting."""
        remaining = max(0.0, 1.0 - (getattr(job, "progress", 0.0) or 0.0))
        return min(remaining, self._host.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP)

    def execute_construction(self, blueprint_id, coords=None, kind=None):
        """
        Drives within interaction range of a construction blueprint and executes it,
        recharging on-site and resuming for as long as real progress keeps being made.
        The energy budget check before departing only commits to
        TARGET_CONSTRUCTION_PROGRESS_PER_TRIP of the job, so running low on battery
        mid-build here is normal and expected, not a failure -- returning early
        would waste the trip and abandon a perfectly workable job. Blueprints can
        build outposts, pumps, well caps, power lines, and pipe networks.
        Caller must ensure required cargo is loaded first; see load_construction_materials().
        `kind` (the Construction's .kind): a finished mining_drill* blueprint
        records the new drill's position (drill_sites.record_built_drill()),
        since no game API exposes drill coordinates.

        Returns False only for a genuine rejection (blocked, insufficient materials,
        etc.) or an inability to physically reach the site/station -- never merely
        because the job is still incomplete and needs another recharge round later.
        """
        self._host.log.start(f"[{self._host.name}] Build '{blueprint_id}' ({kind or 'blueprint'}) at {coords}")
        # Doubles as the heartbeat peers read in construction_plan.peer_builders().
        self._host.publish_telemetry("BUILDING", blueprint_id)
        self._host.last_build_progress = 0.0
        ok = self._host._execute_construction(blueprint_id, coords, kind)
        outcome = ("finished" if self._host.last_build_progress >= 1.0 else "paused for later") if ok else "failed"
        self._host.log.end(f"[{self._host.name}] Build '{blueprint_id}' {outcome}")
        return ok

    @method_block(lambda self, *_, **__: f"[{self._host.name}] _execute_construction")
    def _execute_construction(self, blueprint_id, coords, kind):
        """Body of execute_construction()."""
        self._host.log.trace(f"execute_construction() enter: blueprint_id={blueprint_id!r}, coords={coords}")
        if not hasattr(self._host.vehicle, "constructor"):
            self._host.log.level("error").print(f"[{self._host.name}] Error: No ConstructorModule mounted on this Pioneer!")
            return False

        self._host.set_intent(fleet_intent.describe("building", [kind or "blueprint"], at=f"{coords[0]:.0f},{coords[1]:.0f}" if coords else None))
        if coords:
            self._host.log.print(f"[{self._host.name}] Driving to construction site at {coords}...")
            if not self._host.drive_with_recharge(coords[0], coords[1], precision=2.0):
                self._host.log.level("warn").print(f"[{self._host.name}] Could not reach construction site at {coords} safely.")
                self._host.log.trace("execute_construction() exit: could not reach site")
                return False

        if hasattr(self._host.vehicle, "nav"):
            try:
                self._host.vehicle.nav.brake()
            except Exception as exc:
                swallowed("pioneer_construction.PioneerConstructionMixin.execute_construction: self._host.vehicle.nav.brake", exc)

        while True:
            # No-op if this Pioneer doesn't actually own the job's claim (the
            # caller is expected to claim_target() before calling this), so
            # safe to call unconditionally.
            self._host.refresh_claim(self._host.construction_claim_key(blueprint_id))
            self._host.log.print(f"[{self._host.name}] Executing blueprint '{blueprint_id}'...")
            self._host.publish_telemetry("CONSTRUCTING", blueprint_id)
            progress_before = self._host.get_construction_progress(blueprint_id)
            wh_before, _, _ = self._host.get_battery()
            res = self._host.vehicle.constructor.execute(blueprint_id)
            progress_after = self._host.get_construction_progress(blueprint_id)
            self._host.last_build_progress = progress_after
            self._host.calibrate_wh_per_progress(progress_after - progress_before, wh_before - self._host.get_battery()[0])
            self._host.log.print(f"[{self._host.name}] Constructor result: {res.status} - {res.message}")

            if res.status == "ok":
                if kind and str(kind).startswith("mining_drill") and coords and hasattr(self._host.vehicle, "input"):
                    try:
                        drill_sites.record_built_drill(self._host.vehicle.input, str(kind), coords)
                    except Exception as error:
                        self._host.log.level("warn").print(f"[{self._host.name}] Could not record new drill position: {error}")
                try:
                    self._host.note_finished_power_job(kind, coords)
                except Exception as error:
                    swallowed("pioneer_construction.PioneerConstructionMixin._execute_construction: note_finished_power_job", error)
                self._host.log.trace(f"execute_construction() exit: blueprint '{blueprint_id}' complete")
                return True
            if res.status not in ("paused_no_power", "paused"):
                self._host.log.trace(f"execute_construction() exit: genuine rejection ({res.status})")
                return False  # genuine rejection, not a power issue -- don't keep retrying

            if progress_after <= progress_before:
                self._host.log.level("warn").print(f"[{self._host.name}] No progress made this cycle ({res.status}); leaving paused for a later attempt.")
                self._host.log.trace("execute_construction() exit: no progress made, leaving paused")
                return True

            self._host.log.print(f"[{self._host.name}] Construction paused ({res.status}) at {progress_after*100:.0f}% progress. Recharging nearby and resuming.")
            nearest_cs, _ = self._host.get_nearest_charging_station()
            if not self._host.drive_to(nearest_cs[0], nearest_cs[1], precision=1.0):
                self._host.log.level("warn").print(f"[{self._host.name}] Could not reach charging station to resume construction; leaving paused for a later attempt.")
                self._host.log.trace("execute_construction() exit: could not reach charging station")
                return True
            self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
            if coords and not self._host.drive_with_recharge(coords[0], coords[1], precision=2.0):
                self._host.log.level("warn").print(f"[{self._host.name}] Could not return to construction site after recharge; leaving paused for a later attempt.")
                self._host.log.trace("execute_construction() exit: could not return to site after recharge")
                return True
            if hasattr(self._host.vehicle, "nav"):
                try:
                    self._host.vehicle.nav.brake()
                except Exception as exc:
                    swallowed("pioneer_construction.PioneerConstructionMixin.execute_construction: self._host.vehicle.nav.brake #2", exc)

    def cargo_count(self, item_id):
        """Units of item_id currently sitting in the Pioneer's cargo, across all stacks."""
        try:
            return sum(getattr(s, "count", 0) for s in self._host.vehicle.cargo.stacks() if getattr(s, "id", None) == item_id)
        except Exception as error:
            swallowed("pioneer_construction.PioneerConstructionMixin.cargo_count: self._host.vehicle.cargo.stacks", error)
            return 0

    def cargo_counts(self):
        """{item_id: units} aboard, from one cargo.stacks() read ({} if unreadable)."""
        counts = {}
        try:
            for stack in self._host.vehicle.cargo.stacks():
                item_id = getattr(stack, "id", None)
                counts[item_id] = counts.get(item_id, 0) + getattr(stack, "count", 0)
        except Exception as error:
            swallowed("pioneer_construction.PioneerConstructionMixin.cargo_counts: self._host.vehicle.cargo.stacks", error)
        return counts

    def load_construction_materials(self, job, target_count=None):
        """Loads required_item from storage at this Pioneer's home outpost
        (Inventory too when that is the home outpost) into cargo,
        aiming for target_count (e.g. a whole chain of upcoming same-material
        jobs) but succeeding once this job's own required_count is met, since
        storage may not have the full batch on hand. Clamps the load request
        to available cargo capacity to prevent 'target_full' transfer
        rejections."""
        required_item = getattr(job, "required_item", None)
        required_count = getattr(job, "required_count", 0)
        if not required_item or required_count <= 0:
            return True  # deconstruction jobs and already-started jobs need nothing

        have = self._host.cargo_count(required_item)
        goal = max(required_count, target_count or 0)

        # Clamp goal to fit within available cargo space
        if hasattr(self._host.vehicle, "cargo"):
            try:
                cap = self._host.vehicle.cargo.capacity()
                cnt = self._host.vehicle.cargo.count()
                free_space = max(0, cap - cnt)
                goal = min(goal, have + free_space)
            except Exception as error:
                swallowed("pioneer_construction.PioneerConstructionMixin.load_construction_materials: self._host.vehicle.cargo.capacity", error)

        if have >= goal and have >= required_count:
            return True

        if not hasattr(self._host.vehicle, "input"):
            self._host.log.level("warn").print(f"[{self._host.name}] Cannot load {required_item}: no input port / Auto Feeders.")
            return False

        missing = max(0, goal - have)
        if missing <= 0:
            return have >= required_count

        # run_construction_loop() returns to self._host.home_outpost before stocking.
        moved = take_item(self._host.vehicle.input, required_item, missing, outpost=self._host.home_outpost)
        if moved > 0:
            self._host.log.print(f"[{self._host.name}] Loaded {moved}x {required_item} for construction (stocking toward {goal} for chained jobs).")
        elif self._host.cargo_count(required_item) < required_count:
            self._host.log.debug(f"[{self._host.name}] Could not load {required_item}: none takeable at '{self._host.home_base}'.")
        return self._host.cargo_count(required_item) >= required_count

    def material_wait_reason(self, item_id):
        """
        Why item_id can't be loaded at home right now, for the log: takeable
        home stock, units haulers have reserved toward home
        (logistics_requests.in_flight()), and the open logistics request for
        it at home, if any. Two archive reads plus one stock scan.
        """
        tick = self._host.get_current_tick()
        parts = [f"home stock {takeable_stock(item_id, outpost=self._host.home_outpost)}"]
        flying = logistics_requests.in_flight(self._host.home_base, tick).get(item_id, 0)
        if flying:
            parts.append(f"{flying} en route")
        request = logistics_requests.active_requests(tick).get(self._host.home_base, {}).get(item_id)
        if isinstance(request, dict):
            parts.append(f"requested by {request.get('by')} (target {request.get('target')})")
        else:
            parts.append("no haul request open")
        return ", ".join(parts)

    def fair_share_batch(self, item_id, batch):
        """
        batch capped so active same-home Constructor peers
        (construction_plan.peer_builders()) keep their share of item_id's stock
        at home; unchanged for a lone builder, so a solo chain still loads
        everything its cargo holds.
        """
        self._host.publish_telemetry("RESTOCKING", item_id)
        peers = construction_plan.peer_builders(
            fleet_status.get_all(), self._host.name, self._host.home_base,
            self._host.get_current_tick(), construction_plan.PEER_BUILDER_ACTIVE_TICKS,
        )
        if not peers:
            self._host.log.debug(f"[{self._host.name}] fair_share_batch({item_id}): no active peer builders; batch {batch}.")
            return batch
        # Material already aboard counts toward this builder's share.
        stock = takeable_stock(item_id, outpost=self._host.home_outpost) + self._host.cargo_count(item_id)
        share = construction_plan.fair_share(batch, stock, len(peers) + 1)
        self._host.log.debug(f"[{self._host.name}] fair_share_batch({item_id}): peers {peers}, home stock {stock}; batch {batch} -> {share}.")
        return share

    def run_construction_loop(self):
        """Continuously polls pending and paused construction blueprints and executes available builds."""
        self._host.log.print(f"Pioneer Controller ({self._host.name}) online. Monitoring construction blueprints.")
        # Job ids skipped until no other option remains (unreachable, failed,
        # or waiting for material); cleared when the Pioneer idles.
        self.failed_jobs = set()
        # Items already announced at info level as awaited.
        self.material_waits = set()

        validate_game_version()
        while True:
            reset_all()
            try:
                delay = self._host.construction_pass()
            except Exception as e:
                self._host.log.level("error").print(f"[{self._host.name}] Pioneer loop exception: {e}")
                try:
                    self._host.vehicle.nav.brake()
                except Exception as error:
                    swallowed("pioneer_construction.PioneerConstructionMixin.run_construction_loop: self._host.vehicle.nav.brake", error)
                # Releases every claim this Pioneer holds: the constructor
                # loop doesn't use current_target_key, and a Constructor
                # Pioneer only ever runs this one loop.
                try:
                    self._host.release_target_claim()
                except Exception as error:
                    swallowed("pioneer_construction.PioneerConstructionMixin.run_construction_loop: self._host.release_target_claim", error)
                delay = 5.0
            if delay:
                flush_all()
                sleep(delay)

    def construction_pass(self):
        """
        One pass of run_construction_loop(), first applicable step wins:
        recall, battery reserve, resume a paused job, build a pending job the
        cargo aboard serves, else claim the next job and stock its material.
        Returns the seconds to sleep before the next pass (0 = at once).
        """
        if self._host.handle_recall_if_active():
            return 5.0
        self._host._ready_at_base()
        if self._host._return_if_reserve_reached():
            return 0

        # Priorities first: see prune_construction_priorities().
        priorities = self._host.read_construction_priorities()
        bp = get_component("construction_blueprint")
        paused, paused_ok = self._host._read_jobs(bp, "paused_constructions")
        pending, pending_ok = self._host._read_jobs(bp, "pending_constructions")
        # Only sweep leaked claims when every list read cleanly -- a failed
        # read would make live jobs look finished.
        lists_ok = bool(bp) and paused_ok and pending_ok
        if not paused and not pending:
            return self._host._idle_without_jobs(bp, lists_ok, priorities)

        work = self._host._select_work(bp, paused, pending, lists_ok, priorities)
        delay = self._host._resume_paused_job(work.paused)
        if delay is None and work.matching:
            delay = self._host._build_matching_job(work.matching, work.position)
        if delay is None:
            delay = self._host._restock_for_next_job(work)
        return delay

    def _ready_at_base(self):
        """Parked at home: charge before departing and run the idle upgrade cycle."""
        if not self._host.is_at_base():
            return
        _, _, lvl = self._host.get_battery()
        if lvl < 0.90:
            self._host.recharge_at_station(target_level=1.0)
        self._host.handle_upgrade_cycle_if_idle()

    def _return_if_reserve_reached(self):
        """
        Heads to the nearest station once the battery is down to the reserve
        for a normal-speed return, not just the bare survival floor (which
        would leave conserve mode nothing to spend but the slowest crawl
        home). True when it drove off to recharge.
        """
        curr_wh, _, _ = self._host.get_battery()
        if curr_wh > self._host.energy_needed_to_return_comfortably():
            return False
        self._host._recharge_at_nearest("Return reserve reached in field; returning to nearest station to recharge.", "Field recharge done.")
        return True

    def _recharge_at_nearest(self, reason, outcome, station=None):
        """Drives to station (default: the nearest charging station) and charges to full, as one log block."""
        name = self._host.name
        self._host.log.start(f"[{name}] {reason}")
        if station is None:
            station, _ = self._host.get_nearest_charging_station()
        self._host.drive_to(station[0], station[1], precision=1.0)
        self._host.recharge_at_station(target_level=1.0, station_coords=station)
        self._host.log.end(f"[{name}] {outcome}")

    def _read_jobs(self, bp, getter_name):
        """(jobs, ok) from one construction_blueprint list; ok is False only when the read raised."""
        if not bp or not hasattr(bp, getter_name):
            return [], True
        try:
            return getattr(bp, getter_name)() or [], True
        except Exception as error:
            swallowed(f"pioneer_construction.PioneerConstructionMixin._read_jobs: bp.{getter_name}", error)
            return [], False

    def _sweep_dead_jobs(self, live_ids, claims, priorities):
        """Drops this Pioneer's build claims and the construction.priority entries of blueprints no longer live."""
        self._host.release_finished_construction_claims(live_ids, claims)
        self._host.prune_construction_priorities(priorities, live_ids)

    def _idle_at_base(self):
        """Parks at home as IDLE_AT_BASE; returns the idle sleep."""
        if self._host.distance_to_home() > 3.0:
            self._host.return_to_base()
        self._host.publish_telemetry("IDLE_AT_BASE")
        return 10.0

    def _idle_without_jobs(self, bp, lists_ok, priorities):
        """No paused or pending job: sweep state of finished blueprints, then idle at home."""
        self._host.log.debug(f"[{self._host.name}] run_construction_loop(): no paused or pending construction jobs; idling.")
        if lists_ok:
            active, active_ok = self._host._read_jobs(bp, "active_constructions")
            if active_ok:
                live_ids = {getattr(j, "id", getattr(j, "blueprint_id", None)) for j in active}
                self._host._sweep_dead_jobs(live_ids, self._host.get_claims(), priorities)
        self.failed_jobs.clear()
        return self._host._idle_at_base()

    def _select_work(self, bp, paused, pending, lists_ok, priorities):
        """
        Scans the job lists into a ConstructionWork: drops jobs a peer owns,
        failed ones and held kinds, then keeps only the top open priority.
        Also sweeps dead claims/priorities when every list read cleanly.
        """
        name = self._host.name
        # Unlike mining POIs (several Pioneers can dig the same site), a
        # construction job is NOT shareable -- two Constructor Pioneers both
        # loading/building the same blueprint would double-load materials and
        # waste a trip. The scan skips anything a peer already owns
        # (self-owned claims pass through, per construction_plan.claim_free()).
        existing_claims = self._host.get_claims()
        curr_tick = self._host.get_current_tick()
        active, active_ok = self._host._read_jobs(bp, "active_constructions")
        lists_ok = lists_ok and active_ok
        current_pos = self._host.get_position()
        cargo = self._host.cargo_counts()
        scan_args = (current_pos, cargo, existing_claims, name, curr_tick, self._host.CLAIM_STALE_TICKS, self.failed_jobs, priorities)
        paused_ids, paused_rows, _ = construction_plan.scan_jobs(paused, *scan_args)
        pending_ids, pending_rows, matching = construction_plan.scan_jobs(pending, *scan_args)
        if lists_ok:
            active_ids, _, _ = construction_plan.scan_jobs(active, *scan_args)
            self._host._sweep_dead_jobs(set(paused_ids + pending_ids + active_ids), existing_claims, priorities)
        held = self._host.read_construction_hold(curr_tick)
        if held:
            # Held jobs still count as live above (claims, priorities); they are only not worked on.
            paused_rows = [row for row in paused_rows if row["kind"] not in held]
            pending_rows = [row for row in pending_rows if row["kind"] not in held]
            matching = [entry for entry in matching if entry[3]["kind"] not in held]
            self._host.log.debug(f"[{name}] Construction hold: skipping {', '.join(sorted(held))} jobs.")
        self._host.log.debug(f"[{name}] Job scan: {len(paused_rows)}/{len(paused_ids)} paused and {len(pending_rows)}/{len(pending_ids)} pending open, {len(matching)} matching cargo {cargo}.")

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
            self._host.log.debug(f"[{name}] Working priority {top_prio}: {len(paused_rows)} paused and {len(pending_rows)} pending job(s); {held_back} lower-priority job(s) held back.")
        return ConstructionWork(paused_rows, pending_rows, matching, top_prio, held_back, current_pos)

    def _job_trip_budget(self, row, at_floor=False):
        """
        calculate_trip_energy() for one job row, budgeting this trip's share
        of its progress. at_floor prices driving at the speedmode throttle
        floor (minimum_wh_per_meter()) instead of the calibrated rate.
        """
        return self._host.calculate_trip_energy(
            row["coords"], planned_drill_units=0, planned_scans=0,
            planned_construction_progress=self._host.planned_progress_for_job(row["job"]),
            wh_per_meter=self._host.minimum_wh_per_meter() if at_floor else None,
        )

    def _claim_and_build(self, row, verb):
        """
        Claims row's job and builds it. None when a peer won the claim
        between scan and claim (the caller falls through to its next step),
        else the seconds to sleep.
        """
        job_id = row["id"]
        coords = row["coords"]
        key = self._host.construction_claim_key(job_id)
        if not self._host.claim_target(key, {"type": "build", "coords": coords, "name": job_id}):
            return None
        self._host.log.debug(f"[{self._host.name}] {verb} construction job: {job_id} at {coords}.")
        if not self._host.execute_construction(job_id, coords, kind=row["kind"]):
            self.failed_jobs.add(job_id)
            self._host.release_target_claim(key)
            return 2.0
        if self._host.last_build_progress >= 1.0:
            self._host.release_target_claim(key)
        return 0

    def _resume_paused_job(self, rows):
        """Resumes the first paused job (already-paid work) within reach; None when none was started."""
        for row in rows:
            if not row["coords"]:
                continue
            if self._host._job_trip_budget(row)["is_achievable"]:
                return self._host._claim_and_build(row, "Resuming paused")
            if self._host.distance_to_home() > 3.0:
                # Cannot reach safely from current field position.
                self._host._recharge_at_nearest("Insufficient energy to reach paused job safely; recharging at nearest station.", "Recharge before paused job done.")
                return None
        return None

    def _build_matching_job(self, matching, position):
        """
        Builds the nearest pending job the cargo aboard serves (materials or
        deconstruction). Gated on the speedmode throttle floor, not the
        typical calibrated rate: drive_with_recharge()/select_cruise_throttle()
        pick whatever throttle the leg needs, so a job only reachable by
        conserving hard is still attempted. None to fall through to restocking.
        """
        for _, _, _, row in matching:
            if row["coords"] and self._host._job_trip_budget(row, at_floor=True)["is_achievable"]:
                return self._host._claim_and_build(row, "Executing chained")
        return self._host._charge_for_matching_jobs(matching, position)

    def _charge_for_matching_jobs(self, matching, position):
        """Cargo serves pending jobs none of which is reachable: recharge, or mark them failed when even a full battery can't."""
        name = self._host.name
        station, _ = self._host.get_nearest_charging_station()
        if self._host.distance_between(position, station) > 3.0:
            self._host._recharge_at_nearest("Insufficient energy to reach next construction site; recharging at nearest station.", "Recharge before next site done.", station)
            return 0
        _, cap_wh, lvl = self._host.get_battery()
        if lvl < 0.98:
            self._host.log.start(f"[{name}] At station with materials but need charge ({lvl*100:.0f}%); recharging to full.")
            self._host.recharge_at_station(target_level=1.0, station_coords=station)
            self._host.log.end(f"[{name}] Recharged with materials aboard.")
            return 0
        # Full at a station and the floor-rate budget still fails: out of
        # range even at the slowest possible throttle.
        req_details = []
        for _, _, _, row in matching:
            if row["coords"]:
                req_details.append(f"{row['id']} ({self._host._job_trip_budget(row, at_floor=True)['total_required_wh']:.1f} Wh)")
            else:
                req_details.append(f"{row['id']}")
            self.failed_jobs.add(row["id"])
        self._host.log.level("warn").print(f"[{name}] Advisory: Matching construction job(s) exceed maximum battery range even at minimum throttle ({cap_wh:.1f} Wh): {', '.join(req_details)}.")
        return 5.0

    def _reachable_pending_jobs(self, rows):
        """
        Pending rows a full battery can serve from the nearest charging
        station, at the speedmode throttle floor (the true bound, since
        conserve mode can always throttle down that far) and budgeting the
        minimum useful on-site progress (TARGET_CONSTRUCTION_PROGRESS_PER_TRIP).
        A job beyond that is permanently out of range and is marked failed.
        """
        _, cap_wh, _ = self._host.get_battery()
        stations = [st["coords"] for st in self._host.get_all_charging_stations()] or [self._host.home_coords]
        trips = run_batched(
            construction_plan.station_trip_wh, rows, construction_plan.TRIP_CHUNK,
            stations, self._host.minimum_wh_per_meter(), self._host.wh_per_progress,
            self._host.TARGET_CONSTRUCTION_PROGRESS_PER_TRIP, self._host.SAFETY_MARGIN_MULTIPLIER, self._host.MIN_EMERGENCY_RESERVE_WH,
        )
        reachable = []
        for row, required_wh in trips:
            if required_wh is not None and required_wh > cap_wh:
                if row["id"] not in self.failed_jobs:
                    self._host.log.level("warn").print(f"[{self._host.name}] Construction job '{row['id']}' at {row['coords']} permanently exceeds battery capacity from nearest station even at minimum throttle ({required_wh:.1f} Wh required, {cap_wh:.1f} Wh max capacity). Marking failed.")
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
        for row in rows:
            if self._host.claim_target(self._host.construction_claim_key(row["id"]), {"type": "build", "coords": row["coords"], "name": row["id"]}):
                return row
        return None

    def _restock_for_next_job(self, work):
        """No job is buildable with the cargo aboard: claim the next reachable pending job and stock for it at home."""
        name = self._host.name
        targets = self._host._reachable_pending_jobs(work.pending)
        if not targets and work.held_back and work.pending:
            # Every pending job at this priority was just marked failed;
            # rescan so the held-back lower-priority jobs get their turn.
            self._host.log.debug(f"[{name}] run_construction_loop(): no reachable job at priority {work.priority}; rescanning for lower-priority jobs.")
            return 0
        if not targets:
            self._host.log.debug(f"[{name}] run_construction_loop(): every pending job is unreachable this cycle; clearing failed_jobs and idling.")
            self.failed_jobs.clear()
            return self._host._idle_at_base()

        job = self._host._claim_first(targets)
        if job is None:
            return 2.0

        if self._host.distance_to_home() > 3.0:
            self._host.return_to_base()
        # Fully charged before embarking on a new batch.
        _, _, lvl = self._host.get_battery()
        if lvl < 0.98:
            self._host.recharge_at_station(target_level=1.0)

        if job["item"] and job["count"] > 0:
            return self._host._stock_materials(job, targets)
        # Deconstruction job: make room for the reclaimed materials.
        self._host.log.debug(f"[{name}] run_construction_loop(): deconstruction job {job['id']}, no materials required.")
        if hasattr(self._host.vehicle, "cargo") and self._host.vehicle.cargo.full():
            self._host.unload_cargo()
        return 0

    def _free_cargo_space(self):
        """Free cargo units; 50 when the cargo can't be read."""
        if not hasattr(self._host.vehicle, "cargo"):
            return 50
        try:
            return max(0, self._host.vehicle.cargo.capacity() - self._host.vehicle.cargo.count())
        except Exception as error:
            swallowed("pioneer_construction.PioneerConstructionMixin._free_cargo_space: self._host.vehicle.cargo.capacity", error)
            return 50

    def _stock_materials(self, job, targets):
        """
        Loads job's material at home, batched across the upcoming same-material
        jobs in targets and capped by free cargo and the peers' fair share.
        """
        item = job["item"]
        count = job["count"]
        # Cargo holding other materials is offloaded first to free the bins.
        if hasattr(self._host.vehicle, "cargo") and self._host.vehicle.cargo.count() > 0 and self._host.cargo_count(item) == 0:
            self._host.unload_cargo()

        batch = construction_plan.batch_count(targets, item, max_limit=self._host._free_cargo_space())
        batch = max(count, self._host.fair_share_batch(item, batch))

        if self._host.cargo_count(item) >= count:
            # Already loaded; avoid rapid cycling.
            self._host.log.debug(f"[{self._host.name}] run_construction_loop(): {item} already loaded for job {job['id']}; waiting a beat before retry.")
            return 2.0
        self._host.log.start(f"[{self._host.name}] Stocking up to {batch}x {item} for chained construction.")
        loaded = self._host.load_construction_materials(job["job"], target_count=batch)
        self._host.log.end(f"[{self._host.name}] Stocking {'done' if loaded else 'failed'}.")
        if loaded:
            self.material_waits.discard(item)
            return 0
        return self._host._defer_jobs_needing(item, job, targets)

    def _defer_jobs_needing(self, item, job, targets):
        """
        item isn't obtainable right now (home storage empty, or a peer holds
        the whole stock): defers every job needing it, not just this one, so
        jobs whose materials are on hand get a turn this cycle. Material still
        being fabricated or hauled home is normal, so info once per wait,
        debug while it repeats.
        """
        deferred = construction_plan.ids_needing(targets, item)
        line = f"[{self._host.name}] Waiting for {item} ({self._host.material_wait_reason(item)}); deferring {len(deferred)} job(s) needing it."
        if item in self.material_waits:
            self._host.log.debug(line)
        else:
            self._host.log.print(line)
            self.material_waits.add(item)
        self.failed_jobs.update(deferred)
        self.failed_jobs.add(job["id"])
        self._host.release_target_claim(self._host.construction_claim_key(job["id"]))
        return 2.0
