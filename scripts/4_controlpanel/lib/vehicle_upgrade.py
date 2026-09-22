# Pioneer mixin: automatic hardware tier upgrades. Once a better Sonar/Drill
# tier or bigger Battery Holder/Cargo Rack unlocks (present in the Shop
# catalogue), a Pioneer idling at home sells its obsolete part and equips the
# better one -- one tier step per cycle, never skipping straight to the top,
# so each swap stays a single affordable purchase.
#
# Pioneer-only: docs/database/equipment_modules.md documents Sport Nav, Wide/
# Deep Sonar, and Industrial/Heavy Drill as Pioneer-universal-slot items --
# the Rover's 3 fixed slots only ever accept the basic nav/sonar/drill module
# (see docs/components/rover.md), so there is never a better tier for it to
# equip. This mixin is composed into PioneerController only (lib/pioneer.py),
# never into the shared VehicleController base RoverController also uses.
#
# Sport Nav is deliberately NOT part of the automatic tier ladder below --
# unlike Sonar/Drill/Holder/Rack, it stacks additively on top of whatever Nav
# is already mounted rather than replacing it, and the user asked for it to
# stay a manual, operator-triggered action (Fleet panel button) instead of
# something that fires on its own every cycle.

from archive import archive
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController

# Worst -> best. best_unlocked_tier() only ever steps to the immediate next
# entry, never straight to the top, so a single swap is always one affordable
# purchase rather than needing the full ladder's combined cost banked at once.
SONAR_TIERS = ["sonar_module", "sonar_module_wide", "sonar_module_deep"]
DRILL_TIERS = ["drill_module", "drill_module_industrial", "drill_module_heavy"]
BATTERY_HOLDER_TIERS = ["battery_holder_small", "battery_holder_medium", "battery_holder_large"]
CARGO_RACK_TIERS = ["cargo_rack_small", "cargo_rack_medium", "cargo_rack_large"]
PORTABLE_BATTERY_TIERS = ["portable_battery", "heavy_portable_battery"]
PORTABLE_BIN_TIERS = ["portable_bin", "heavy_portable_bin"]
SPORT_NAV_MODULE_ID = "nav_module_sport"

# One shared dict {vehicle_name: True}, same rationale and shape as
# vehicle_claims.py's RECALL_KEY: the Data Archive has a fixed shared
# key-count cap, so a per-vehicle top-level key doesn't scale with fleet size.
SPORT_NAV_REQUEST_KEY = "vehicle.sport_nav_request"


def is_sport_nav_requested(vehicle_name):
    """Module-level so panel_2.py's Fleet card can read the pending flag without instantiating a controller."""
    requests = archive.get(SPORT_NAV_REQUEST_KEY, {}) or {}
    if not isinstance(requests, dict):
        return False
    return bool(requests.get(vehicle_name, False))


def request_sport_nav(vehicle_name):
    """Sets vehicle_name's pending Sport Nav request, consumed once by that Pioneer's own script next time it's idle at base."""
    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        requests[vehicle_name] = True
        return requests

    archive.transaction(SPORT_NAV_REQUEST_KEY, {}, updater)


def clear_sport_nav_request(vehicle_name):
    def updater(requests):
        if not isinstance(requests, dict):
            requests = {}
        requests.pop(vehicle_name, None)
        return requests

    archive.transaction(SPORT_NAV_REQUEST_KEY, {}, updater)


class VehicleUpgradeMixin:
    """
    Automatic Pioneer hardware upgrades, mixed into PioneerController only.
    Depends on VehicleNavigationMixin (is_at_base()), VehicleEnergyMixin
    (get_battery()/recharge_at_station()), and VehicleClaimsMixin
    (current_target_key) for its idle/safety gating.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def _catalogue(self):
        """Fresh {item_id: cost} from the Shop catalogue -- infrequent code path (once per idle-at-base cycle), no need for the tick-level caching other mixins use. A locked item is simply absent (docs/components/shop.md: "entries hidden by tech gates don't appear")."""
        shop = get_component("shop")
        if not shop or not hasattr(shop, "get_catalogue"):
            return {}
        try:
            return {entry.id: entry.cost for entry in shop.get_catalogue()}
        except Exception:
            return {}

    def _best_unlocked_tier(self, tiers, current_id, catalogue):
        """First tier strictly above current_id's index that's present in catalogue, else None. current_id not found in tiers (e.g. nothing mounted yet) -> None, nothing to upgrade automatically."""
        if current_id not in tiers:
            return None
        idx = tiers.index(current_id)
        if idx + 1 >= len(tiers):
            return None
        candidate = tiers[idx + 1]
        return candidate if candidate in catalogue else None

    def _shop(self):
        """Guarded Shop component accessor -- buy()/sell() call sites below all check this for None first."""
        return get_component("shop")

    def _credits(self):
        commander = get_component("commander")
        if not commander or not hasattr(commander, "get_credits"):
            return 0
        try:
            return commander.get_credits()
        except Exception:
            return 0

    def run_auto_upgrade_cycle(self):
        """
        Called once per idle-at-base cycle (see handle_upgrade_cycle_if_idle()).
        Requires the vehicle to be parked at base with an empty hold and no
        live mission claim -- every swap below unmounts/uninstalls hardware,
        which needs a stable, uncommitted vehicle to do safely.
        """
        if not self._host.is_at_base() or self._host.vehicle.cargo.count() > 0 or self._host.current_target_key:
            return
        if not hasattr(self._host.vehicle, "modules"):
            return

        self._upgrade_function_module(SONAR_TIERS)
        self._upgrade_function_module(DRILL_TIERS)
        self._upgrade_containers(BATTERY_HOLDER_TIERS, PORTABLE_BATTERY_TIERS, needs_full_charge=True)
        self._upgrade_containers(CARGO_RACK_TIERS, PORTABLE_BIN_TIERS, needs_full_charge=False)
        self._top_up_container_density(BATTERY_HOLDER_TIERS, PORTABLE_BATTERY_TIERS, needs_full_charge=True)
        self._top_up_container_density(CARGO_RACK_TIERS, PORTABLE_BIN_TIERS, needs_full_charge=False)

    def _upgrade_function_module(self, tiers):
        """Single-capability slot swap (Sonar / Drill): no internal items, exactly one mounted at a time."""
        slots = self._host.vehicle.modules()
        slot = next((s for s in slots if getattr(s, "module_id", None) in tiers), None)
        if slot is None:
            return  # nothing of this kind mounted -- e.g. a hauler-role Pioneer with no Sonar

        catalogue = self._catalogue()
        old_id = slot.module_id
        best = self._best_unlocked_tier(tiers, old_id, catalogue)
        if best is None:
            return

        cost = catalogue.get(best, 0)
        if self._credits() < cost:
            self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{best}' costs {cost}cr, can't afford yet; retrying later.")
            return

        shop = self._shop()
        if shop is None:
            return

        slot_index = slot.index
        unmount_res = self._host.vehicle.unmount(slot_index)
        if unmount_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: unmount({slot_index}) for '{old_id}' failed: {unmount_res.status} - {unmount_res.message}")
            return

        buy_res = shop.buy(best, 1)
        if buy_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: buy('{best}') failed ({buy_res.status}); remounting '{old_id}'.")
            self._host.vehicle.mount(slot_index, old_id)
            return

        mount_res = self._host.vehicle.mount(slot_index, best)
        if mount_res.status != "ok":
            self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: mount('{best}') failed ({mount_res.status}) after buying it -- left in Inventory for manual handling.")
            return

        sell_res = shop.sell(old_id, 1)
        self._host.log.print(f"[{self._host.name}] Auto-upgraded slot {slot_index}: '{old_id}' -> '{best}' (sold old for {getattr(sell_res, 'credits', 0)}cr).")

    def _fill_container_bays(self, slot_index, fill_item):
        """Buys and installs fill_item into every currently-empty bay of the container mounted at slot_index."""
        shop = self._shop()
        if shop is None:
            return
        slots = self._host.vehicle.modules()
        slot = next((s for s in slots if s.index == slot_index), None)
        if slot is None:
            return
        for internal_index, item_id in enumerate(slot.internal_items):
            if item_id is not None:
                continue
            buy_res = shop.buy(fill_item, 1)
            if buy_res.status != "ok":
                self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: buy('{fill_item}') for slot {slot_index} bay {internal_index} failed: {buy_res.status}.")
                continue
            install_res = self._host.vehicle.install(slot_index, internal_index, fill_item)
            if install_res.status != "ok":
                self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: install('{fill_item}', slot {slot_index}, bay {internal_index}) failed: {install_res.status} -- left in Inventory.")

    def _ensure_full_charge_for_sale(self):
        """
        Portable Batteries refund their retained charge% (50% minimum) on
        sale (docs/components/shop.md) -- top off before pulling any off a
        Battery Holder so the sale recovers full value instead of the floor.
        Already at base, so this is cheap.
        """
        _, _, level = self._host.get_battery()
        if level < 0.99:
            self._host.recharge_at_station(target_level=1.0)

    def _upgrade_containers(self, tiers, portable_tiers, needs_full_charge):
        """Battery Holder / Cargo Rack bay-count swap. Several may be mounted at once (aggregated pool) -- each matching slot is upgraded independently, no consolidation."""
        shop = self._shop()
        if shop is None:
            return
        catalogue = self._catalogue()
        base_portable, heavy_portable = portable_tiers[0], portable_tiers[-1]
        fill_item = heavy_portable if heavy_portable in catalogue else base_portable

        # Snapshot slot indices before mutating anything -- unmount/mount
        # calls below change what modules() returns, but slot INDEX identity
        # is stable across a swap at the same position.
        slots = self._host.vehicle.modules()
        candidates = [s for s in slots if getattr(s, "module_id", None) in tiers]

        for slot in candidates:
            old_id = slot.module_id
            best = self._best_unlocked_tier(tiers, old_id, catalogue)
            if best is None:
                continue

            # Bay count is a property of the TARGET tier, not the current one.
            new_bay_count = _BAY_COUNTS.get(best, len(slot.internal_items))

            total_cost = catalogue.get(best, 0) + new_bay_count * catalogue.get(fill_item, 0)
            if self._credits() < total_cost:
                self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{best}' + {new_bay_count}x '{fill_item}' costs {total_cost}cr total, can't afford yet; retrying later.")
                continue

            if needs_full_charge:
                self._ensure_full_charge_for_sale()

            slot_index = slot.index
            aborted = False
            for internal_index, item_id in enumerate(slot.internal_items):
                if item_id is None:
                    continue
                uninstall_res = self._host.vehicle.uninstall(slot_index, internal_index)
                if uninstall_res.status != "ok":
                    self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: uninstall(slot {slot_index}, bay {internal_index}) failed: {uninstall_res.status}; aborting this slot's upgrade for now.")
                    aborted = True
                    break
                shop.sell(item_id, 1)
            if aborted:
                continue

            unmount_res = self._host.vehicle.unmount(slot_index)
            if unmount_res.status != "ok":
                self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: unmount({slot_index}) for '{old_id}' failed: {unmount_res.status} - {unmount_res.message}")
                continue
            shop.sell(old_id, 1)

            buy_res = shop.buy(best, 1)
            if buy_res.status != "ok":
                self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: buy('{best}') failed ({buy_res.status}) after selling '{old_id}' -- slot {slot_index} left empty until next cycle.")
                continue
            mount_res = self._host.vehicle.mount(slot_index, best)
            if mount_res.status != "ok":
                self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: mount('{best}') failed ({mount_res.status}) after buying it -- left in Inventory for manual handling.")
                continue

            self._fill_container_bays(slot_index, fill_item)
            self._host.log.print(f"[{self._host.name}] Auto-upgraded slot {slot_index}: '{old_id}' -> '{best}', bays filled with '{fill_item}'.")

    def _top_up_container_density(self, tiers, portable_tiers, needs_full_charge):
        """
        Upgrades already-installed base-tier portables (Portable Battery /
        Portable Bin) to the Heavy variant, independent of any holder/rack
        resize this cycle -- the user asked for Heavy to always be installed
        once unlocked, not just in newly-added bays.
        """
        shop = self._shop()
        if shop is None:
            return
        catalogue = self._catalogue()
        base_portable, heavy_portable = portable_tiers[0], portable_tiers[-1]
        if heavy_portable not in catalogue:
            return
        heavy_cost = catalogue.get(heavy_portable, 0)

        slots = self._host.vehicle.modules()
        for slot in slots:
            if getattr(slot, "module_id", None) not in tiers:
                continue
            stale_bays = [i for i, item_id in enumerate(slot.internal_items) if item_id == base_portable]
            if not stale_bays:
                continue
            if needs_full_charge:
                self._ensure_full_charge_for_sale()
            for internal_index in stale_bays:
                if self._credits() < heavy_cost:
                    self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{heavy_portable}' costs {heavy_cost}cr, can't afford yet; retrying later.")
                    break
                uninstall_res = self._host.vehicle.uninstall(slot.index, internal_index)
                if uninstall_res.status != "ok":
                    self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: density uninstall(slot {slot.index}, bay {internal_index}) failed: {uninstall_res.status}.")
                    continue
                shop.sell(base_portable, 1)
                buy_res = shop.buy(heavy_portable, 1)
                if buy_res.status != "ok":
                    self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: density buy('{heavy_portable}') failed ({buy_res.status}) after selling '{base_portable}' -- bay {internal_index} left empty.")
                    continue
                install_res = self._host.vehicle.install(slot.index, internal_index, heavy_portable)
                if install_res.status != "ok":
                    self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: density install('{heavy_portable}', slot {slot.index}, bay {internal_index}) failed: {install_res.status} -- left in Inventory.")
                else:
                    self._host.log.print(f"[{self._host.name}] Auto-upgraded slot {slot.index} bay {internal_index}: '{base_portable}' -> '{heavy_portable}'.")

    def handle_sport_nav_request_if_active(self):
        """
        Manual-only Sport Nav install, consumed from the operator's Fleet
        panel request (see request_sport_nav()). One-shot: the request flag
        clears whether this succeeds or not, so a stuck request (no free
        slot, locked research, insufficient credits) doesn't retry forever --
        the operator can just click the button again once ready.
        """
        if not is_sport_nav_requested(self._host.name):
            return
        if not self._host.is_at_base() or self._host.vehicle.cargo.count() > 0 or self._host.current_target_key:
            return  # not safely idle yet -- leave the request pending for a later cycle

        try:
            slots = self._host.vehicle.modules()
        except Exception:
            slots = []
        free_slot = next((s for s in slots if getattr(s, "module_id", None) is None), None)
        if free_slot is None:
            self._host.log.level("warn").print(f"[{self._host.name}] Sport Nav requested but no free slot available; free one up and re-request.")
            clear_sport_nav_request(self._host.name)
            return

        catalogue = self._catalogue()
        if SPORT_NAV_MODULE_ID not in catalogue:
            self._host.log.level("warn").print(f"[{self._host.name}] Sport Nav requested but not yet unlocked in the Shop.")
            clear_sport_nav_request(self._host.name)
            return
        if self._credits() < catalogue.get(SPORT_NAV_MODULE_ID, 0):
            self._host.log.level("warn").print(f"[{self._host.name}] Sport Nav requested but insufficient credits; re-request once affordable.")
            clear_sport_nav_request(self._host.name)
            return

        shop = self._shop()
        if shop is None:
            clear_sport_nav_request(self._host.name)
            return
        buy_res = shop.buy(SPORT_NAV_MODULE_ID, 1)
        if buy_res.status == "ok":
            mount_res = self._host.vehicle.mount(free_slot.index, SPORT_NAV_MODULE_ID)
            if mount_res.status == "ok":
                self._host.log.print(f"[{self._host.name}] Sport Nav mounted in slot {free_slot.index} (manual request).")
            else:
                self._host.log.level("error").print(f"[{self._host.name}] Sport Nav bought but mount failed ({mount_res.status}) -- left in Inventory for manual handling.")
        else:
            self._host.log.level("warn").print(f"[{self._host.name}] Sport Nav purchase failed: {buy_res.status}.")
        clear_sport_nav_request(self._host.name)

    def handle_upgrade_cycle_if_idle(self):
        """
        One call for the Pioneer's main loop to make at its existing "parked
        at base, checking readiness" checkpoint: consumes any pending Sport
        Nav request first, then -- only once genuinely idle (at base, empty
        cargo, no live mission) -- runs the automatic tier-upgrade pass.
        """
        self.handle_sport_nav_request_if_active()
        self.run_auto_upgrade_cycle()


# Bay counts per equipment_modules.md -- small/medium/large hold 1/2/3 bays
# for both Battery Holder and Cargo Rack. Kept module-level (not per-instance)
# since it's a static equipment fact, not vehicle state.
_BAY_COUNTS = {
    "battery_holder_small": 1,
    "battery_holder_medium": 2,
    "battery_holder_large": 3,
    "cargo_rack_small": 1,
    "cargo_rack_medium": 2,
    "cargo_rack_large": 3,
}
