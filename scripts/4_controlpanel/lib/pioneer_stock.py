# Pioneer mixin: stocking construction material at home. Loads a job's
# material (batched across the upcoming same-material jobs, capped by free
# cargo and the active peers' fair share) and tops the remaining bins up with
# the materials of other open jobs. Layer 4 of the vehicle mixins
# (docs/plans/mixin_refactor/README.md): it calls cargo (unload_cargo) and
# fleet_unit (publish_telemetry); lot and deferral bookkeeping stays with the
# caller, BuildJob (lib/job_build.py). Composed into PioneerController only
# (lib/pioneer.py); batching math lives in lib/construction_plan.py.

from typing import TYPE_CHECKING

import construction_plan
import fleet_status
import logistics_requests
from machine_controller import port_counts
from storage import take_item, takeable_stock
from swallow import swallowed

if TYPE_CHECKING:
    from pioneer import PioneerController


class ConstructionStockMixin:
    """
    Construction material stocking mixed into PioneerController. Depends on
    VehicleCargoMixin (unload_cargo) and FleetUnitMixin (publish_telemetry,
    get_current_tick).
    """

    @property
    def _host(self) -> "PioneerController":
        return self  # type: ignore[return-value]

    def cargo_count(self, item_id):
        """Units of item_id currently sitting in the Pioneer's cargo, across all stacks."""
        return self._host.cargo_counts().get(item_id, 0)

    def cargo_counts(self):
        """{item_id: units} aboard, from one cargo.stacks() read ({} if unreadable)."""
        return port_counts(getattr(self._host.vehicle, "cargo", None), "pioneer_stock.ConstructionStockMixin.cargo_counts: self._host.vehicle.cargo.stacks")

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
                swallowed("pioneer_stock.ConstructionStockMixin.load_construction_materials: self._host.vehicle.cargo.capacity", error)

        if have >= goal and have >= required_count:
            return True

        if not hasattr(self._host.vehicle, "input"):
            self._host.log.level("warn").print(f"[{self._host.name}] Cannot load {required_item}: no input port / Auto Feeders.")
            return False

        missing = max(0, goal - have)
        if missing <= 0:
            return have >= required_count

        # BuildJob returns to self._host.home_outpost before stocking.
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
            parts.append(f"requested by {request.get('by')} (target {logistics_requests.request_target(request)})")
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

    def _free_cargo_space(self):
        """Free cargo units; 50 when the cargo can't be read."""
        if not hasattr(self._host.vehicle, "cargo"):
            return 50
        try:
            return max(0, self._host.vehicle.cargo.capacity() - self._host.vehicle.cargo.count())
        except Exception as error:
            swallowed("pioneer_stock.ConstructionStockMixin._free_cargo_space: self._host.vehicle.cargo.capacity", error)
            return 50

    def _cargo_space_for(self, item_id):
        """Units of item_id the cargo still takes (construction_plan.bin_space()); free cargo when the racks can't be read, 0 without cargo."""
        cargo = getattr(self._host.vehicle, "cargo", None)
        if cargo is None:
            return 0
        try:
            return construction_plan.bin_space(cargo.racks(), item_id)
        except Exception as error:
            swallowed("pioneer_stock.ConstructionStockMixin._cargo_space_for: cargo.racks", error)
            return self._host._free_cargo_space()

    def _top_up_materials(self, job, targets):
        """
        Fills the cargo room left after job's material with the materials of
        the other jobs in targets, the material with the job nearest to job
        first, so one trip home stocks for several materials. A material is
        loaded only when its nearest job's whole need fits and is takeable;
        the load is capped by bin room and the peers' fair share. Skipped
        while a deconstruction is open (it needs room for reclaimed parts).
        Returns [(nearest job row, units aboard)] per material loaded.
        """
        if not hasattr(self._host.vehicle, "cargo") or not hasattr(self._host.vehicle, "input"):
            return []
        if any([row["kind"] == construction_plan.DECONSTRUCT_KIND for row in targets]):
            return []
        name = self._host.name
        loaded = []
        for item, rows in construction_plan.other_materials(targets, job):
            if self._host.vehicle.cargo.full():
                break
            need = rows[0]["count"]
            space = self._host._cargo_space_for(item)
            stock = takeable_stock(item, outpost=self._host.home_outpost)
            if space < need or stock < need:
                self._host.log.debug(f"[{name}] Top-up skips {item}: room {space}, home stock {stock}, next job needs {need}.")
                continue
            batch = min(stock, self._host.fair_share_batch(item, construction_plan.batch_count(rows, item, max_limit=space)))
            if batch < need:
                continue
            moved = take_item(self._host.vehicle.input, item, batch, outpost=self._host.home_outpost)
            aboard = self._host.cargo_count(item)
            if aboard < need:
                self._host.log.debug(f"[{name}] Top-up of {item} moved {moved}/{batch}; {aboard} aboard, short of {need}.")
                continue
            self._host.log.print(f"[{name}] Topped up {moved}x {item} ({len(rows)} open job(s) need it).")
            loaded.append((rows[0], aboard))
        return loaded

    def stock_materials(self, job, targets):
        """
        Loads job's material at home, batched across the upcoming same-material
        jobs in targets and capped by free cargo and the peers' fair share,
        then tops up with other jobs' materials. Returns (status, extra):
        "aboard" when job's material was already loaded, "loaded" after a
        load that covers job, "short" when it doesn't; extra is
        _top_up_materials()'s list after a load, else [].
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
            self._host.log.debug(f"[{self._host.name}] BuildJob: {item} already loaded for job {job['id']}; waiting a beat before retry.")
            return "aboard", []
        self._host.log.start(f"[{self._host.name}] Stocking up to {batch}x {item} for chained construction.")
        loaded = self._host.load_construction_materials(job["job"], target_count=batch)
        extra = self._host._top_up_materials(job, targets) if loaded else []
        self._host.log.end(f"[{self._host.name}] Stocking {'done' if loaded else 'failed'}.")
        return ("loaded" if loaded else "short"), extra
