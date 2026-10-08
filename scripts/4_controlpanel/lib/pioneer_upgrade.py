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
# Sport Nav is deliberately NOT part of the automatic tier ladder below -- the
# user asked for it to stay a manual, operator-triggered action (Fleet panel
# button) instead of something that fires on its own every cycle. Basic Nav is
# exclusive (mount() returns capability_already_mounted next to it), so the
# first Sport Nav swaps 1:1 into the Basic Nav's slot; further Sport Navs stack
# only with each other, into a free slot.

from archive import archive
import cash
import deep_oil
from item_tiers import SONAR_TIERS, DRILL_TIERS, BATTERY_HOLDER_TIERS, CARGO_RACK_TIERS, PORTABLE_BATTERY_TIERS, PORTABLE_BIN_TIERS, best_mounted
import outpost_mining
from pioneer_split import best_holder_count, split_cost
from swallow import swallowed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vehicle import VehicleController

# Ladders come from lib/item_tiers.py, worst -> best. best_unlocked_tier()
# only ever steps to the immediate next entry, never straight to the top, so
# a single swap is always one affordable purchase rather than needing the
# full ladder's combined cost banked at once.
# The default sonar ladder stops at Deep: Seismic Sonar only adds deep-oil
# prospecting under inert formations (lib/deep_oil.py). _sonar_ladder() adds
# the Deep -> Seismic step for one scout while that work is open. A Pioneer
# with Seismic mounted keeps it (no swap back), so newly found formations
# never make it flip.
SONAR_UPGRADE_TIERS = SONAR_TIERS[:SONAR_TIERS.index("sonar_module_deep") + 1]
SEISMIC_SONAR_ID = "sonar_module_seismic"
BASIC_NAV_MODULE_ID = "nav_module"
SPORT_NAV_MODULE_ID = "nav_module_sport"

# Capacity per portable: Wh per battery, units per bin (equipment_modules.md).
PORTABLE_CAPACITY = {"portable_battery": 50, "heavy_portable_battery": 100, "portable_bin": 25, "heavy_portable_bin": 50}

# Holder/Rack split (vehicles_drones.md §2b-2): a mining Pioneer re-splits its
# container slots only when the current split pays at least this factor more
# drive Wh per delivered unit than the best one (or reaches fewer sites), so a
# shifting site list does not make it flip slots back and forth.
SPLIT_MIN_GAIN = 1.15

# One shared dict {vehicle_name: True}, same rationale and shape as
# vehicle_claims.py's RECALL_KEY: the Data Archive has a fixed shared
# key-count cap, so a per-vehicle top-level key doesn't scale with fleet size.
SPORT_NAV_REQUEST_KEY = "vehicle.sport_nav_request"


def is_sport_nav_requested(vehicle_name):
    """Module-level so vehicles_panel.py's Fleet card can read the pending flag without instantiating a controller."""
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


class PioneerUpgradeMixin:
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
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._catalogue: shop.get_catalogue", error)
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

    def _sonar_ladder(self):
        """
        Sonar ladder for this cycle: SONAR_TIERS (Deep -> Seismic allowed) for
        a Deep-sonar Pioneer while _seismic_wanted(), else SONAR_UPGRADE_TIERS.
        """
        try:
            mounted = best_mounted(self._host.vehicle.modules(), SONAR_TIERS)
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._sonar_ladder: vehicle.modules", error)
            return SONAR_UPGRADE_TIERS
        if mounted == SONAR_UPGRADE_TIERS[-1] and self._seismic_wanted():
            return SONAR_TIERS
        return SONAR_UPGRADE_TIERS

    def _seismic_wanted(self):
        """
        True when this Pioneer should take the Seismic step: both seismic
        researches unlocked, deep-oil work open (deep_oil.open_work()) and no
        other Pioneer has Seismic Sonar mounted. Two scouts idling at base in
        the same cycle could both pass; the second Seismic then just shares
        the work.
        """
        research = get_component("research")
        try:
            if not research or not all(research.is_unlocked(r) for r in deep_oil.SEISMIC_RESEARCH_IDS):
                return False
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._seismic_wanted: research.is_unlocked", error)
            return False
        journal = get_component("journal")
        try:
            state = deep_oil.prospect(journal.discovered_sites("nocturna") if journal else [])
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._seismic_wanted: journal.discovered_sites", error)
            return False
        if not deep_oil.open_work(state):
            return False
        holder = self._other_seismic_pioneer()
        if holder:
            self._host.log.debug(f"[{self._host.name}] Seismic step skipped: {holder} already carries Seismic Sonar.")
            return False
        return True

    def _other_seismic_pioneer(self):
        """Id of another Pioneer with Seismic Sonar mounted, else None (reads each live vehicle's modules())."""
        fleet = get_component("fleet")
        own_id = getattr(self._host.vehicle, "id", self._host.name)
        try:
            refs = fleet.vehicles() if fleet else []
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._other_seismic_pioneer: fleet.vehicles", error)
            return None
        for ref in refs:
            ref_id = getattr(ref, "id", "")
            if getattr(ref, "kind", "") != "pioneer" or not ref_id or ref_id == own_id:
                continue
            try:
                vehicle = get_component(ref_id)
                if vehicle and best_mounted(vehicle.modules(), SONAR_TIERS) == SEISMIC_SONAR_ID:
                    return ref_id
            except Exception as error:
                swallowed("pioneer_upgrade.PioneerUpgradeMixin._other_seismic_pioneer: vehicle.modules", error)
        return None

    def _shop(self):
        """Guarded Shop component accessor -- buy()/sell() call sites below all check this for None first."""
        return get_component("shop")

    def _cash_id(self):
        """lib/cash.py consumer id: one pioneer_upgrade ask per Pioneer."""
        return f"pioneer_upgrade:{self._host.name}"

    def _credits(self):
        commander = get_component("commander")
        if not commander or not hasattr(commander, "get_credits"):
            return 0
        try:
            return commander.get_credits()
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._credits: commander.get_credits", error)
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

        self._upgrade_function_module(self._sonar_ladder())
        self._upgrade_function_module(DRILL_TIERS)
        self._rebalance_container_split()
        self._upgrade_containers(BATTERY_HOLDER_TIERS, PORTABLE_BATTERY_TIERS, needs_full_charge=True)
        self._upgrade_containers(CARGO_RACK_TIERS, PORTABLE_BIN_TIERS, needs_full_charge=False)
        self._top_up_container_density(BATTERY_HOLDER_TIERS, PORTABLE_BATTERY_TIERS, needs_full_charge=True)
        self._top_up_container_density(CARGO_RACK_TIERS, PORTABLE_BIN_TIERS, needs_full_charge=False)

    def _top_tier(self, tiers, catalogue, mounted_ids):
        """Best tier the Shop sells, else the best one already mounted, else None."""
        for item_id in reversed(tiers):
            if item_id in catalogue or item_id in mounted_ids:
                return item_id
        return None

    def _split_sites(self):
        """
        [(fixed_wh, wh_per_unit), ...] for every surveyed mineral site this
        Pioneer's drill can cut that belongs to its home outpost: the site's
        resource marker names home, or (unassigned) home is its nearest
        outpost. Read live from the journal each call, so new sites count.
        fixed_wh is the empty round trip from the home station at cruise
        throttle; wh_per_unit is the dig plus the extra return-drive Wh of
        one carried unit.
        """
        journal = get_component("journal")
        home_id = getattr(self._host.home_outpost, "id", None)
        if not journal or not hasattr(journal, "surveyed_sites") or not home_id:
            return []
        try:
            hardness_limit = self._host.vehicle.drill.hardness_limit()
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._split_sites: drill.hardness_limit", error)
            return []
        home = self._host.get_home_slot_coords()
        throttle = self._host.cruise_throttle
        empty_rate = self._host.wh_per_meter_at_throttle(throttle, cargo_units=0)
        unit_rate = self._host.wh_per_meter_at_throttle(throttle, cargo_units=1) - empty_rate
        sites = []
        try:
            for site in journal.surveyed_sites("nocturna"):
                if site.kind() != "mineral" or (getattr(site, "hardness", None) or 99) > hardness_limit:
                    continue
                owner = outpost_mining.site_assigned_outpost(site.x, site.y) or outpost_mining.nearest_outpost_id(site.x, site.y)
                if owner != home_id:
                    continue
                distance = self._host.distance_between(home, (site.x, site.y))
                dig_wh = self._host.mine_wh_per_unit(getattr(site, "item_id", None), getattr(site, "purity", None))
                sites.append((2 * distance * empty_rate, dig_wh + distance * unit_rate))
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._split_sites: journal.surveyed_sites", error)
        return sites

    def _rebalance_container_split(self):
        """
        Mining Pioneers only: re-split the container slots between Battery
        Holders and Cargo Racks so a trip to this outpost's sites is neither
        battery- nor cargo-bound: least drive Wh per delivered unit
        (pioneer_split.best_holder_count(), rated at the best tier of each). Converts the surplus kind one slot at a time
        through _swap_container(), buying the best unlocked tier directly;
        _upgrade_containers()/_top_up_container_density() then handle tiers.
        """
        if not self._has_drill():
            return
        slots = self._host.vehicle.modules()
        holders = [s for s in slots if getattr(s, "module_id", None) in BATTERY_HOLDER_TIERS]
        racks = [s for s in slots if getattr(s, "module_id", None) in CARGO_RACK_TIERS]
        if not holders or not racks:
            return
        container_slots = len(holders) + len(racks)

        catalogue = self._catalogue()
        mounted = set()
        for slot in holders + racks:
            mounted.add(slot.module_id)
            mounted.update(i for i in slot.internal_items if i)
        holder_id = self._top_tier(BATTERY_HOLDER_TIERS, catalogue, mounted)
        rack_id = self._top_tier(CARGO_RACK_TIERS, catalogue, mounted)
        battery_id = self._top_tier(PORTABLE_BATTERY_TIERS, catalogue, mounted)
        bin_id = self._top_tier(PORTABLE_BIN_TIERS, catalogue, mounted)
        if not (holder_id and rack_id and battery_id and bin_id):
            return
        wh_per_holder = _BAY_COUNTS[holder_id] * PORTABLE_CAPACITY[battery_id]
        units_per_rack = _BAY_COUNTS[rack_id] * PORTABLE_CAPACITY[bin_id]

        sites = self._split_sites()
        safety, reserve = self._host.SAFETY_MARGIN_MULTIPLIER, self._host.MIN_EMERGENCY_RESERVE_WH
        target = best_holder_count(container_slots, wh_per_holder, units_per_rack, sites, safety, reserve)
        if target is None or target == len(holders):
            self._host.log.debug(f"[{self._host.name}] container split: keep {len(holders)} holders / {len(racks)} racks ({len(sites)} site(s), best {target}).")
            return
        current = split_cost(len(holders), container_slots, wh_per_holder, units_per_rack, sites, safety, reserve)
        best = split_cost(target, container_slots, wh_per_holder, units_per_rack, sites, safety, reserve)
        if current[0] <= best[0] and current[1] < best[1] * SPLIT_MIN_GAIN:
            self._host.log.debug(f"[{self._host.name}] container split: {target} holders costs {best[1]:.2f} vs {current[1]:.2f} drive Wh/unit, gain below x{SPLIT_MIN_GAIN}; keeping {len(holders)}.")
            return

        shop = self._shop()
        if shop is None:
            return
        if target > len(holders):
            old_slots, old_tiers, new_id, fill_item = racks, CARGO_RACK_TIERS, holder_id, battery_id
        else:
            old_slots, old_tiers, new_id, fill_item = holders, BATTERY_HOLDER_TIERS, rack_id, bin_id
            self._ensure_full_charge_for_sale()
        count = int(abs(target - len(holders)))
        # Lowest-tier containers go first: fewest bays lost per slot.
        old_slots = sorted(old_slots, key=lambda s: old_tiers.index(str(s.module_id)))[:count]
        cost = catalogue.get(new_id, 0) + _BAY_COUNTS[new_id] * catalogue.get(fill_item, 0)

        self._host.log.start(
            f"[{self._host.name}] Container split {len(holders)}/{len(racks)} -> {target}/{container_slots - target} holders/racks "
            f"(drive {current[1]:.2f} -> {best[1]:.2f} Wh/unit, unreachable {current[0]} -> {best[0]} of {len(sites)} site(s))"
        )
        done = 0
        for slot in old_slots:
            if not cash.can_spend(self._cash_id(), cost, label=f"{self._host.name}: {new_id}"):
                self._host.log.debug(f"[{self._host.name}] container split: '{new_id}' + bays costs {cost}cr, cash manager holds it back; retrying later.")
                break
            outcome = self._swap_container(shop, slot, slot.module_id, new_id, fill_item, cost)
            self._host.log.debug(f"[{self._host.name}] {outcome}")
            if not outcome.startswith("Auto-upgraded"):
                break
            done += 1
        self._host.log.end(f"[{self._host.name}] Container split: {done}/{count} slot(s) converted")

    def _has_drill(self):
        """True with a Drill Module mounted (vehicle.drill raises or is None without one)."""
        try:
            return getattr(self._host.vehicle, "drill", None) is not None
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin._has_drill: vehicle.drill", error)
            return False

    def run_module_upgrades_mid_job(self):
        """
        Sonar/Drill tier pass plus the holder/rack split for a recharge stop
        at base inside a running job (vehicle_mining.py's recharge-and-resume),
        which keeps its claim across several base visits. A battery-bound
        miner lives in that loop and never reaches the idle gate, so the
        split must run here too. Neither swap touches the claim; both need an
        empty hold. Container tier steps stay in run_auto_upgrade_cycle().
        """
        if not self._host.is_at_base() or self._host.vehicle.cargo.count() > 0:
            return
        if not hasattr(self._host.vehicle, "modules"):
            return
        self._upgrade_function_module(self._sonar_ladder())
        self._upgrade_function_module(DRILL_TIERS)
        self._rebalance_container_split()

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
        if not cash.can_spend(self._cash_id(), cost, label=f"{self._host.name}: {best}"):
            self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{best}' costs {cost}cr, cash manager holds it back; retrying later.")
            return

        shop = self._shop()
        if shop is None:
            return

        self._host.log.start(f"[{self._host.name}] Auto-upgrade slot {slot.index}: '{old_id}' -> '{best}' ({cost}cr)")
        outcome = self._swap_function_module(shop, slot.index, old_id, best, cost)
        self._host.log.end(f"[{self._host.name}] {outcome}")

    def _swap_function_module(self, shop: "Shop", slot_index, old_id, best, cost):
        """Unmounts old_id, buys and mounts best, sells old_id; returns the outcome text."""
        unmount_res = self._host.vehicle.unmount(slot_index)
        if unmount_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: unmount({slot_index}) for '{old_id}' failed: {unmount_res.status} - {unmount_res.message}")
            return "Upgrade aborted: unmount failed"

        buy_res = shop.buy(best, 1)
        if buy_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: buy('{best}') failed ({buy_res.status}); remounting '{old_id}'.")
            self._host.vehicle.mount(slot_index, old_id)
            cash.release(self._cash_id())
            return "Upgrade aborted: buy failed, old module remounted"
        cash.spent(self._cash_id(), cost)

        mount_res = self._host.vehicle.mount(slot_index, best)
        if mount_res.status != "ok":
            self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: mount('{best}') failed ({mount_res.status}) after buying it -- left in Inventory for manual handling.")
            return "Upgrade failed: mount failed"

        sell_res = shop.sell(old_id, 1)
        return f"Auto-upgraded slot {slot_index}: '{old_id}' -> '{best}' (sold old for {getattr(sell_res, 'credits', 0)}cr)"

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
            if not cash.can_spend(self._cash_id(), total_cost, label=f"{self._host.name}: {best}"):
                self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{best}' + {new_bay_count}x '{fill_item}' costs {total_cost}cr total, cash manager holds it back; retrying later.")
                continue

            if needs_full_charge:
                self._ensure_full_charge_for_sale()

            self._host.log.start(f"[{self._host.name}] Auto-upgrade slot {slot.index}: '{old_id}' -> '{best}' ({total_cost}cr)")
            outcome = self._swap_container(shop, slot, old_id, best, fill_item, total_cost)
            self._host.log.end(f"[{self._host.name}] {outcome}")

    def _swap_container(self, shop: "Shop", slot, old_id, best, fill_item, total_cost):
        """Empties, unmounts and sells old_id, buys and mounts best, refills its bays; returns the outcome text."""
        slot_index = slot.index
        for internal_index, item_id in enumerate(slot.internal_items):
            if item_id is None:
                continue
            uninstall_res = self._host.vehicle.uninstall(slot_index, internal_index)
            if uninstall_res.status != "ok":
                self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: uninstall(slot {slot_index}, bay {internal_index}) failed: {uninstall_res.status}; aborting this slot's upgrade for now.")
                return "Upgrade aborted: uninstall failed"
            shop.sell(item_id, 1)

        unmount_res = self._host.vehicle.unmount(slot_index)
        if unmount_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: unmount({slot_index}) for '{old_id}' failed: {unmount_res.status} - {unmount_res.message}")
            return "Upgrade aborted: unmount failed"
        shop.sell(old_id, 1)

        buy_res = shop.buy(best, 1)
        if buy_res.status != "ok":
            self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: buy('{best}') failed ({buy_res.status}) after selling '{old_id}' -- slot {slot_index} left empty until next cycle.")
            return "Upgrade failed: buy failed, slot left empty"
        mount_res = self._host.vehicle.mount(slot_index, best)
        if mount_res.status != "ok":
            self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: mount('{best}') failed ({mount_res.status}) after buying it -- left in Inventory for manual handling.")
            return "Upgrade failed: mount failed"

        self._fill_container_bays(slot_index, fill_item)
        cash.spent(self._cash_id(), total_cost)
        return f"Auto-upgraded slot {slot_index}: '{old_id}' -> '{best}', bays filled with '{fill_item}'"

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
                if not cash.can_spend(self._cash_id(), heavy_cost, label=f"{self._host.name}: {heavy_portable}"):
                    self._host.log.debug(f"[{self._host.name}] auto-upgrade: '{heavy_portable}' costs {heavy_cost}cr, cash manager holds it back; retrying later.")
                    break
                self._host.log.start(f"[{self._host.name}] Upgrading slot {slot.index} bay {internal_index}: '{base_portable}' -> '{heavy_portable}' ({heavy_cost}cr)")
                outcome = self._swap_portable(shop, slot.index, internal_index, base_portable, heavy_portable, heavy_cost)
                self._host.log.end(f"[{self._host.name}] {outcome}")

    def _swap_portable(self, shop: "Shop", slot_index, internal_index, base_portable, heavy_portable, heavy_cost):
        """Replaces one installed base portable with the Heavy variant; returns the outcome text."""
        uninstall_res = self._host.vehicle.uninstall(slot_index, internal_index)
        if uninstall_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: density uninstall(slot {slot_index}, bay {internal_index}) failed: {uninstall_res.status}.")
            return "Bay upgrade aborted: uninstall failed"
        shop.sell(base_portable, 1)
        buy_res = shop.buy(heavy_portable, 1)
        cash.spent(self._cash_id(), heavy_cost if buy_res.status == "ok" else 0)
        if buy_res.status != "ok":
            self._host.log.level("error").print(f"[{self._host.name}] auto-upgrade: density buy('{heavy_portable}') failed ({buy_res.status}) after selling '{base_portable}' -- bay {internal_index} left empty.")
            return "Bay upgrade failed: buy failed, bay left empty"
        install_res = self._host.vehicle.install(slot_index, internal_index, heavy_portable)
        if install_res.status != "ok":
            self._host.log.level("warn").print(f"[{self._host.name}] auto-upgrade: density install('{heavy_portable}', slot {slot_index}, bay {internal_index}) failed: {install_res.status} -- left in Inventory.")
            return "Bay upgrade failed: install failed"
        return f"Auto-upgraded slot {slot_index} bay {internal_index}: '{base_portable}' -> '{heavy_portable}'"

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
        except Exception as error:
            swallowed("pioneer_upgrade.PioneerUpgradeMixin.handle_sport_nav_request_if_active: self._host.vehicle.modules", error)
            slots = []
        basic_nav_slot = next((s for s in slots if getattr(s, "module_id", None) == BASIC_NAV_MODULE_ID), None)
        free_slot = next((s for s in slots if getattr(s, "module_id", None) is None), None)
        target_slot = basic_nav_slot or free_slot
        if target_slot is None:
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
        if basic_nav_slot is not None:
            self._host.log.start(f"[{self._host.name}] Swapping Basic Nav for Sport Nav in slot {target_slot.index} (manual request)")
            outcome = self._swap_function_module(shop, target_slot.index, BASIC_NAV_MODULE_ID, SPORT_NAV_MODULE_ID, catalogue.get(SPORT_NAV_MODULE_ID, 0))
            self._host.log.end(f"[{self._host.name}] {outcome}")
            clear_sport_nav_request(self._host.name)
            return
        self._host.log.start(f"[{self._host.name}] Installing Sport Nav in slot {target_slot.index} (manual request)")
        buy_res = shop.buy(SPORT_NAV_MODULE_ID, 1)
        if buy_res.status == "ok":
            mount_res = self._host.vehicle.mount(target_slot.index, SPORT_NAV_MODULE_ID)
            if mount_res.status == "ok":
                self._host.log.print(f"[{self._host.name}] Sport Nav mounted in slot {target_slot.index} (manual request).")
            else:
                self._host.log.level("error").print(f"[{self._host.name}] Sport Nav bought but mount failed ({mount_res.status}) -- left in Inventory for manual handling.")
        else:
            self._host.log.level("warn").print(f"[{self._host.name}] Sport Nav purchase failed: {buy_res.status}.")
        self._host.log.end(f"[{self._host.name}] Sport Nav request handled")
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
