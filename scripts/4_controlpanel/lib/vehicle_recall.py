# Vehicle mixin: recall and retirement. While the recall flag is set
# (FleetUnitMixin.is_recalled, flag helpers in vehicle_claims.py) the vehicle
# abandons its target and heads home; at base with a pending decommission
# request it unloads, charges, strips and sells every part
# (lib/fleet_decommission.py). Layer 4 of the vehicle mixins
# (docs/plans/mixin_refactor/README.md): it calls claims (release_target_claim),
# charging (return_to_base, recharge_at_station), cargo (unload_cargo) and
# navigation/energy; nothing below calls back into it.
# Shared by Rover and Pioneer via VehicleController (lib/vehicle.py).

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController


class VehicleRecallMixin:
    """
    Recall handling mixed into VehicleController. Depends on
    FleetUnitMixin (is_recalled, publish_telemetry),
    VehicleClaimsMixin (release_target_claim),
    VehicleChargingMixin (return_to_base, recharge_at_station),
    VehicleCargoMixin (unload_cargo), VehicleEnergyMixin (get_battery) and
    VehicleNavigationMixin (is_at_base, get_position).
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def handle_recall_if_active(self):
        """
        If recalled, abandons any current target and heads to base (or just
        idles there if already home). Returns True when recall is active, so
        callers should skip their normal cycle this pass:
            if self.handle_recall_if_active():
                sleep(5.0)
                continue
        """
        if not self._host.is_recalled():
            return False

        if self._host.is_at_base():
            self._host.log.debug(f"[{self._host.name}] Recall active and already at base ({self._host.get_position()}); idling in RECALLED state.")
            self._host.publish_telemetry("RECALLED")
            self._host._prepare_decommission()
        else:
            self._host.log.start(f"[{self._host.name}] Recall active; returning to base.")
            self._host.log.debug(f"[{self._host.name}] Recall active while away from base (current position {self._host.get_position()}, base slot {self._host.assigned_slot_coords}); abandoning mission={self._host.mission.target_key if self._host.mission else None!r} and heading home.")
            self._host.publish_telemetry("RECALLED")
            self._host.release_target_claim()
            reached = self._host.return_to_base()
            self._host.log.end(f"[{self._host.name}] Recall return {'complete' if reached else 'incomplete'}.")
        return True

    def _prepare_decommission(self):
        """
        At base while recalled for retirement (lib/fleet_decommission.py):
        unloads cargo at HOME_BASE, charges to DECOMMISSION_MIN_SOC (Portable
        Batteries sell for their charge; a Rover's integrated battery
        doesn't, so it skips this), strips and sells every part
        (_strip_and_sell_parts()), then marks the entry ready for the
        coordinator to undeploy the bare chassis. No-op unless a request is
        pending.
        """
        from fleet_decommission import decommission_entry, mark_decommission_ready, DECOMMISSION_MIN_SOC
        name = self._host.name
        entry = decommission_entry(name)
        if not entry or entry.get("state") != "requested":
            return
        self._host.log.start(f"[{name}] Preparing for decommission")
        cargo = getattr(self._host.vehicle, "cargo", None)
        if cargo is not None and cargo.count() > 0:
            self._host.unload_cargo()
            if cargo.count() > 0:
                self._host.log.level("warn").print(f"[{name}] {cargo.count()} unit(s) still aboard (storage full?); retrying.")
                self._host.log.end("cargo aboard")
                return
        _, _, level = self._host.get_battery()
        if entry.get("kind") != "rover" and level < DECOMMISSION_MIN_SOC:
            self._host.log.debug(f"[{name}] Charging to {DECOMMISSION_MIN_SOC*100:.0f}% before decommission ({level*100:.0f}%).")
            self._host.recharge_at_station(target_level=1.0)
            self._host.log.end("charging")
            return
        stripped, credits, failure = self._host._strip_and_sell_parts()
        if failure:
            self._host.log.level("warn").print(f"[{name}] Stripping parts stopped: {failure}; retrying.")
            self._host.log.end(f"sold {stripped} part(s) for {credits} cr so far")
            return
        mark_decommission_ready(name)
        self._host.publish_telemetry("DECOMMISSION_READY")
        self._host.log.end(f"[{name}] Empty; sold {stripped} part(s) for {credits} cr; ready for undeploy.")

    def _strip_and_sell_parts(self):
        """
        Uninstalls every portable and unmounts every module, selling each one
        right after it lands in Inventory, so the retirement needs one free
        Inventory slot instead of one per part (undeploy() refuses with
        inventory_full otherwise). Portables come out before their holder
        (unmount() refuses a non-empty one). shop.sell() takes the
        lowest-indexed matching Inventory slot, so a spare of the same item
        may be the unit sold. The Nav Module stays mounted (get_position()
        and is_at_base() need it); the coordinator sells it with the chassis
        kit after the undeploy. Returns (parts sold, credits, failure or None).
        """
        vehicle = self._host.vehicle
        shop = get_component("shop")
        if not hasattr(vehicle, "unmount") or not shop:
            return 0, 0, None
        sold = [0, 0]

        def sell(item_id):
            res = shop.sell(item_id, 1)
            if res.status == "ok":
                sold[0] += 1
                sold[1] += int(getattr(res, "credits", 0) or 0)
            self._host.log.trace(f"[{self._host.name}] sell('{item_id}') -> {res.status}")

        for slot in vehicle.modules():
            module_id = getattr(slot, "module_id", None)
            if not module_id or module_id.startswith("nav_module"):
                continue
            for internal_index, item_id in enumerate(getattr(slot, "internal_items", None) or []):
                if item_id is None:
                    continue
                res = vehicle.uninstall(slot.index, internal_index)
                if res.status != "ok":
                    return sold[0], sold[1], f"uninstall(slot {slot.index}, bay {internal_index}) {res.status}: {res.message}"
                sell(item_id)
            res = vehicle.unmount(slot.index)
            if res.status != "ok":
                return sold[0], sold[1], f"unmount({slot.index}) {res.status}: {res.message}"
            sell(module_id)
        return sold[0], sold[1], None
