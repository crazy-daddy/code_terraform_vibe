# Pioneer mixin: the build action of the Constructor Module. Drives to a
# claimed blueprint and executes it, recharging nearby and resuming while it
# makes progress (pipes, power lines, outposts, pumps, caps, deconstruction),
# and calibrates Wh per progress from each step. Layer 4 of the vehicle
# mixins (docs/plans/mixin_refactor/README.md). Job choice, claims and lots
# live in BuildJob (lib/job_build.py), stocking in lib/pioneer_stock.py,
# archive I/O in lib/construction_lots.py, planning math in
# lib/construction_plan.py. Composed into PioneerController only (lib/pioneer.py).

from typing import TYPE_CHECKING

import construction_lots
import construction_plan
import fleet_intent
from swallow import swallowed
from tree_console import method_block

if TYPE_CHECKING:
    from pioneer import PioneerController


class PioneerConstructionMixin:
    """
    Build action of PioneerController: execute_construction() and the
    blueprint progress read it calibrates from. Depends on VehicleController's
    energy (get_battery, calibrate_wh_per_progress), charging
    (drive_with_recharge, recharge_at_station), navigation and claims
    (refresh_claim) mixins.
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
        BuildJob's "release the claim once progress >= 1.0" check never fires
        (stale build_* claims block other builders for up to
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

    def execute_construction(self, blueprint_id, coords=None, kind=None):
        """
        Drives within interaction range of a construction blueprint and executes it,
        recharging on-site and resuming for as long as real progress keeps being made.
        The energy budget check before departing only commits to
        TARGET_CONSTRUCTION_PROGRESS_PER_TRIP of the job, so running low on battery
        mid-build here is normal and expected, not a failure -- returning early
        would waste the trip and abandon a perfectly workable job. Blueprints can
        build outposts, pumps, well caps, power lines, and pipe networks.
        Caller must ensure required cargo is loaded first; see ConstructionStockMixin.load_construction_materials() (lib/pioneer_stock.py).

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

        self._host.brake_if_able("pioneer_construction.PioneerConstructionMixin.execute_construction: nav.brake")

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
                try:
                    construction_lots.note_finished_power_job(self._host.name, kind, coords, self._host.log)
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

            self._host.log.print(f"[{self._host.name}] Construction paused ({res.status}) at {progress_after * 100:.0f}% progress. Recharging nearby and resuming.")
            nearest_cs = self._host.drive_to_nearest_station()
            if nearest_cs is None:
                self._host.log.level("warn").print(f"[{self._host.name}] Could not reach charging station to resume construction; leaving paused for a later attempt.")
                self._host.log.trace("execute_construction() exit: could not reach charging station")
                return True
            self._host.recharge_at_station(target_level=1.0, station_coords=nearest_cs)
            if coords and not self._host.drive_with_recharge(coords[0], coords[1], precision=2.0):
                self._host.log.level("warn").print(f"[{self._host.name}] Could not return to construction site after recharge; leaving paused for a later attempt.")
                self._host.log.trace("execute_construction() exit: could not return to site after recharge")
                return True
            self._host.brake_if_able("pioneer_construction.PioneerConstructionMixin.execute_construction: nav.brake #2")
