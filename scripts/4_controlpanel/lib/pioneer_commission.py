# Pioneer commissioning, shared state + the Pioneer's own fitting side.
#
# The operator queues a new Pioneer on the COMMISSION card
# (control_panel/fleet_commission_panel.py); lib/fleet_commission.py, run by the
# headless control_room_automation.py, buys the chassis and every part of the role's
# preset, deploys the chassis at the home outpost (where the parts are) and
# waits for a script on it. A freshly deployed
# chassis is bare, and mount()/install() are self-only (docs/components/pioneer.md),
# so the Pioneer's own script fits the parts: LoadoutFittingMixin runs at the
# top of PioneerController.run(), before detect_role() -- a bare chassis would
# otherwise be detected as a hauler with no battery.
#
# One archive dict, fleet.commission (CODE_GUIDES.md#archive), shared with the
# drone jobs (lib/drone_commission.py):
#   {"jobs": [job, ...],               # queue; one pioneer and one drone job worked at a time
#    "lineage": {vehicle_id: {...}},   # commissioned Pioneers not fitted yet
#    "target_home": id | None,         # card's HOME_BASE picker for new Pioneers
#    "drone_outpost": id | None,       # card's outpost picker for new drones
#    "status": str}                    # coordinator's one-line status
# job     = {"id", "kind": "pioneer" | "drone", "role", "state", "spec", "known", "new_id", "reason",
#            "home_base" (pioneer: HOME_BASE, None = home), "outpost" (drone: deploy outpost, None = home)}
# lineage = {"role", "job", "spec", "home_base", "fitted", "missing": {item_id: n}}
# spec    = {"modules": [item_id, ...] (mount order), "battery_fill", "bin_fill"}
# A drone's lineage lives in fleet.upgrade instead (lib/drone_upgrade.py).

from archive import archive
from pioneer_upgrade import SONAR_TIERS, DRILL_TIERS, BATTERY_HOLDER_TIERS, CARGO_RACK_TIERS, PORTABLE_BATTERY_TIERS, PORTABLE_BIN_TIERS, _BAY_COUNTS
from swallow import swallowed
from typing import TYPE_CHECKING
from tree_console import flush_all, method_block
from storage import inventory_count

if TYPE_CHECKING:
    from vehicle import VehicleController

COMMISSION_KEY = "fleet.commission"
PIONEER_KIT_ID = "pioneer"

# Part category -> worst..best item ids. A preset slot takes the best one the
# Shop catalogue lists (locked items are absent from it).
PART_TIERS = {
    "nav": ["nav_module"],
    "sonar": SONAR_TIERS,
    "drill": DRILL_TIERS,
    "constructor": ["constructor_module"],
    "battery": BATTERY_HOLDER_TIERS,
    "cargo": CARGO_RACK_TIERS,
}
BATTERY_HOLDERS = set(BATTERY_HOLDER_TIERS)
CARGO_RACKS = set(CARGO_RACK_TIERS)

# Role -> one part category per chassis slot (8 universal slots), in mount
# order. The role module decides PioneerController.detect_role(); a hauler
# is the one with none of sonar/drill/constructor.
PIONEER_PRESETS = {
    "hauler": ["nav", "battery", "battery", "cargo", "cargo", "cargo", "cargo", "cargo"],
    "miner": ["nav", "drill", "battery", "battery", "cargo", "cargo", "cargo", "cargo"],
    "scout": ["nav", "sonar", "battery", "battery", "battery", "battery", "battery", "battery"],
    "constructor": ["nav", "constructor", "battery", "battery", "battery", "battery", "cargo", "cargo"],
}

# Fitting: wait between passes while a part is missing or the Pioneer is not
# parked in a service area; poll modules() after each mount/install.
FIT_RETRY_S = 10.0
FIT_POLL_TRIES = 10
FIT_POLL_S = 0.5


def commission_state():
    state = archive.get(COMMISSION_KEY, {})
    return state if isinstance(state, dict) else {}


def update_commission(mutate):
    """Atomically applies mutate(state) (in place) to fleet.commission."""
    def updater(state):
        if not isinstance(state, dict):
            state = {}
        mutate(state)
        return state
    archive.transaction(COMMISSION_KEY, {}, updater)


def lineage_entry(vehicle_id):
    entry = (commission_state().get("lineage") or {}).get(vehicle_id)
    return entry if isinstance(entry, dict) else None


def best_part(category, catalogue):
    """Best item of category the catalogue lists, else None."""
    unlocked = [i for i in PART_TIERS.get(category, []) if i in catalogue]
    return unlocked[-1] if unlocked else None


def best_fill(portable_tiers, catalogue):
    """Heavy portable once unlocked, else the base one (same policy as pioneer_upgrade.py)."""
    return portable_tiers[-1] if portable_tiers[-1] in catalogue else portable_tiers[0]


def build_spec(role, catalogue):
    """(spec, None) for role's preset at the best unlocked tiers, or (None, reason)."""
    preset = PIONEER_PRESETS.get(role)
    if not preset:
        return None, f"unknown role {role!r}"
    if PIONEER_KIT_ID not in catalogue:
        return None, "pioneer locked"
    modules = []
    for category in preset:
        item = best_part(category, catalogue)
        if item is None:
            return None, f"{category} locked"
        modules.append(item)
    return {
        "modules": modules,
        "battery_fill": best_fill(PORTABLE_BATTERY_TIERS, catalogue),
        "bin_fill": best_fill(PORTABLE_BIN_TIERS, catalogue),
    }, None


def spec_parts(spec):
    """{item_id: count} every part of spec, portables for every bay included (chassis excluded)."""
    parts = {}
    for item in spec.get("modules") or []:
        parts[item] = parts.get(item, 0) + 1
        bays = _BAY_COUNTS.get(item, 0)
        if item in BATTERY_HOLDERS:
            parts[spec["battery_fill"]] = parts.get(spec["battery_fill"], 0) + bays
        elif item in CARGO_RACKS:
            parts[spec["bin_fill"]] = parts.get(spec["bin_fill"], 0) + bays
    return parts


class LoadoutFittingMixin:
    """
    Fits a vehicle from Inventory, mixed into PioneerController and
    RoverController. Mounts spec["modules"] into free slots, then fills every
    Battery Holder / Cargo Rack bay. A commissioned Pioneer writes the parts
    still missing to lineage["missing"] for the coordinator to buy; done ->
    lineage["fitted"] = True, which the coordinator turns into a finished job.
    """

    @property
    def _host(self) -> "VehicleController":
        return self  # type: ignore[return-value]

    def fit_commissioned_loadout(self):
        """Blocks until this Pioneer's commissioned loadout is fitted. No-op without a lineage entry."""
        name = self._host.name
        entry = lineage_entry(name)
        if not entry or entry.get("fitted"):
            return
        self.fit_loadout(entry.get("spec") or {}, f"Commissioned as {entry.get('role')}", lambda missing: self._report_missing(name, missing))
        update_commission(lambda s: s.get("lineage", {}).get(name, {}).update({"fitted": True, "missing": {}}))

    def fit_loadout(self, spec, label, on_missing=None):
        """Blocks until spec is fitted. on_missing(missing) gets each pass's still-missing parts."""
        name = self._host.name
        self._host.log.start(f"[{name}] {label}: fitting {spec.get('modules')}")
        self._host.publish_telemetry("FITTING", target_desc="fitting")
        while True:
            result, missing = self._fit_pass(spec)
            if on_missing is not None:
                on_missing(missing)
            if result == "done":
                break
            self._host.publish_telemetry("FITTING", target_desc=result)
            self._host.log.debug(f"[{name}] Fitting pass: {result}; missing {missing}; retrying in {FIT_RETRY_S:.0f} s.")
            flush_all()
            sleep(FIT_RETRY_S)
        self._host.log.end(f"[{name}] Loadout fitted.")

    def _report_missing(self, name, missing):
        entry = lineage_entry(name) or {}
        if (entry.get("missing") or {}) != missing:
            update_commission(lambda s: s.get("lineage", {}).get(name, {}).update({"missing": missing}))

    def _slots(self):
        try:
            return list(self._host.vehicle.modules())
        except Exception as error:
            swallowed("pioneer_commission.LoadoutFittingMixin._slots: vehicle.modules", error)
            return []

    def _wait_for(self, check):
        """Polls check() until True (mount/install are service orders; completion timing unconfirmed)."""
        for _ in range(FIT_POLL_TRIES):
            if check():
                return True
            flush_all()
            sleep(FIT_POLL_S)
        return check()

    @method_block("_fit_pass")
    def _fit_pass(self, spec):
        """One pass over the loadout. Returns (result, missing): result "done" or a short reason."""
        name = self._host.name
        vehicle = self._host.vehicle
        missing = {}

        # 1. Modules: each spec entry not yet mounted goes into the first free slot.
        mounted = {}
        for slot in self._slots():
            if slot.module_id:
                mounted[slot.module_id] = mounted.get(slot.module_id, 0) + 1
        wanted = {}
        for item in spec.get("modules") or []:
            wanted[item] = wanted.get(item, 0) + 1
        for item in spec.get("modules") or []:
            if mounted.get(item, 0) >= wanted[item]:
                continue
            if inventory_count(item) <= 0:
                missing[item] = missing.get(item, 0) + 1
                mounted[item] = mounted.get(item, 0) + 1  # counted once per missing unit
                continue
            free = next((s.index for s in self._slots() if not s.module_id), None)
            if free is None:
                self._host.log.level("warn").print(f"[{name}] No free slot for '{item}'; loadout {spec.get('modules')} does not fit.")
                return "no free slot", missing
            res = vehicle.mount(free, item)
            self._host.log.debug(f"[{name}] mount({free}, '{item}') -> {res.status}")
            if res.status == "not_at_service_point":
                return "not at a service point", missing
            if res.status == "capability_already_mounted":
                mounted[item] = mounted.get(item, 0) + 1  # e.g. a nav already there
                continue
            if res.status != "ok":
                self._host.log.level("warn").print(f"[{name}] mount({free}, '{item}') refused: {res.status} - {res.message}")
                return f"mount {item}: {res.status}", missing
            self._wait_for(lambda: any(s.index == free and s.module_id == item for s in self._slots()))
            mounted[item] = mounted.get(item, 0) + 1

        # 2. Bays: every empty bay of a Battery Holder / Cargo Rack gets its portable.
        for slot in self._slots():
            if slot.module_id in BATTERY_HOLDERS:
                fill = spec.get("battery_fill")
            elif slot.module_id in CARGO_RACKS:
                fill = spec.get("bin_fill")
            else:
                continue
            for bay, installed in enumerate(slot.internal_items or []):
                if installed is not None or not fill:
                    continue
                if inventory_count(fill) <= 0:
                    missing[fill] = missing.get(fill, 0) + 1
                    continue
                index = slot.index
                res = vehicle.install(index, bay, fill)
                self._host.log.debug(f"[{name}] install({index}, {bay}, '{fill}') -> {res.status}")
                if res.status == "not_at_service_point":
                    return "not at a service point", missing
                if res.status != "ok":
                    self._host.log.level("warn").print(f"[{name}] install({index}, {bay}, '{fill}') refused: {res.status} - {res.message}")
                    return f"install {fill}: {res.status}", missing
                self._wait_for(lambda: any(s.index == index and len(s.internal_items or []) > bay and s.internal_items[bay] is not None for s in self._slots()))

        if missing:
            return "waiting for parts", missing
        return "done", missing
