# Pioneer refit: turns a running Pioneer into another role in place, instead
# of selling it and commissioning a new one (docs/cheatsheet/vehicles_drones.md
# §2f-1). PioneerController.next_job() decides when (lib/role_demand.py);
# this mixin does the hardware part:
#   1. park in an outpost's service area (mount/unmount/install work only there),
#   2. sell the modules the new role's preset has no place for (bays first),
#   3. queue a coordinator job in state "fitting" with a lineage entry, so
#      lib/fleet_commission.py buys the missing parts exactly as for a new
#      Pioneer, and fit the rest (LoadoutFittingMixin.fit_loadout()),
#   4. rename it when its name is one the code gave.
# A script restart mid-refit resumes the fitting through
# fit_commissioned_loadout() (the lineage entry is still unfitted).

from typing import TYPE_CHECKING

from geometry import distance
from outpost_flow import founded_outposts, nearest_outpost
from pioneer_commission import PART_TIERS, PIONEER_PRESETS, build_spec, commission_name, rename_vehicle, update_commission
from swallow import swallowed
from vehicle_recall import sell_slot

if TYPE_CHECKING:
    from pioneer import PioneerController

REFIT_IDLE_TICKS = 3000  # idle this long before a Pioneer looks for another role
REFIT_COOLDOWN_TICKS = 12000  # between two refit attempts of one Pioneer, failed ones included
SERVICE_PAD_M = 2.0  # the service area reaches this far past the outpost footprint
FOOTPRINT_M = 20.0  # outpost placement footprint: 2 x 2 tiles of 10 m
SERVICE_PARK_TRIES = 3  # return_to_base() attempts to stop inside the service area

# Module item id -> its PART_TIERS category.
_CATEGORY = {item: category for category, items in PART_TIERS.items() for item in items}


def in_service_area(pos, origin):
    """
    True when pos lies in the service area of the outpost at origin
    (outpost.coords(), the footprint's top-left corner): the
    footprint padded SERVICE_PAD_M, x in [ox - pad, ox + 20 + pad), y in
    [oy - 20 - pad, oy + pad).
    """
    if pos is None or origin is None:
        return False
    x, y = pos[0], pos[1]
    ox, oy = origin[0], origin[1]
    return ox - SERVICE_PAD_M <= x < ox + FOOTPRINT_M + SERVICE_PAD_M and oy - FOOTPRINT_M - SERVICE_PAD_M <= y < oy + SERVICE_PAD_M


def _tier(item):
    category = _CATEGORY.get(item)
    return PART_TIERS[category].index(item) if category else -1


def plan_refit(slots, spec_modules):
    """
    Which mounted modules a refit keeps. slots = [(slot index, module id)]
    of the mounted slots; spec_modules = the preset's module ids. Per part
    category the spec counts, the mounted modules of that category stay,
    best tier first (a lower tier stays too: the upgrade cycle re-tiers it);
    the Nav Module always stays. Returns (keep, sell, modules): slot indices
    kept and sold, and spec_modules with each kept module in place of a
    spec entry of its category (what fit_loadout() then completes).
    """
    wanted = {}
    for item in spec_modules:
        category = _CATEGORY.get(item)
        wanted[category] = wanted.get(category, 0) + 1
    by_category = {}
    for index, module_id in slots:
        by_category.setdefault(_CATEGORY.get(module_id), []).append((index, module_id))
    keep, sell, kept_ids = [], [], {}
    for category, mounted in by_category.items():
        mounted.sort(key=lambda entry: (-_tier(entry[1]), entry[0]))
        room = len(mounted) if category == "nav" else (wanted.get(category, 0) if category else 0)
        for index, module_id in mounted[:room]:
            keep.append(index)
            kept_ids.setdefault(category, []).append(module_id)
        sell.extend(index for index, _ in mounted[room:])
    modules = []
    for item in spec_modules:
        pool = kept_ids.get(_CATEGORY.get(item)) or []
        modules.append(pool.pop(0) if pool else item)
    for pool in kept_ids.values():
        modules.extend(pool)  # a second Nav Module the spec has no place for stays listed
    return sorted(keep), sorted(sell), modules


def is_code_name(display_name, vehicle_id):
    """True when display_name is the game's default (the id) or a commission_name() of vehicle_id for any outpost and role."""
    if not display_name or display_name == vehicle_id:
        return True
    parts = str(display_name).split("_")
    if len(parts) != 3:
        return False
    tag, role, number = parts
    if role not in PIONEER_PRESETS or (tag != "H" and not tag.startswith("O")):
        return False
    return number == str(vehicle_id).rsplit("_", 1)[-1]


def refit_job(name, role, home_base, spec, tick):
    """(job, lineage) a refit adds to fleet.commission: the job starts in "fitting", the coordinator only buys and finishes it."""
    job_id = f"refit_{name}_{tick}"
    job = {"id": job_id, "kind": "pioneer", "role": role, "state": "fitting", "new_id": name, "home_base": home_base, "spec": spec}
    lineage = {"role": role, "job": job_id, "spec": spec, "home_base": home_base, "fitted": False, "missing": {}}
    return job, lineage


def enqueue_refit(state, job, lineage):
    """
    Adds job ahead of the first "queued" Pioneer job (the coordinator works
    one Pioneer job at a time, and a refit Pioneer waits parked on its
    parts) and its lineage entry, in place on a fleet.commission value.
    """
    jobs = [j for j in state.get("jobs") or [] if not (isinstance(j, dict) and j.get("new_id") == job["new_id"] and j.get("state") == "fitting")]
    at = next((i for i, j in enumerate(jobs) if isinstance(j, dict) and j.get("kind", "pioneer") == "pioneer" and j.get("state") == "queued"), len(jobs))
    jobs.insert(at, job)
    state["jobs"] = jobs
    state.setdefault("lineage", {})[job["new_id"]] = lineage


class PioneerRefitMixin:
    """
    Refits the Pioneer to another role, mixed into PioneerController after
    LoadoutFittingMixin. Uses LoadoutFittingMixin (fit_loadout,
    _report_missing, _slots), PioneerUpgradeMixin (_catalogue, _shop,
    _ensure_full_charge_for_sale) and the vehicle mixins (set_base,
    return_to_base, get_position).
    """

    refit_tick = -REFIT_COOLDOWN_TICKS

    @property
    def _host(self) -> "PioneerController":
        return self  # type: ignore[return-value]

    def refit(self, role):
        """Refits this Pioneer to role. True when done; False leaves the role unchanged (some surplus may be sold)."""
        host = self._host
        name = host.name
        old_role = host.role
        self.refit_tick = host.get_current_tick()
        spec, reason = build_spec(role, host._catalogue())
        if spec is None:
            host.log.level("warn").print(f"[{name}] Refit {old_role} -> {role}: no preset ({reason}).")
            return False
        host.log.start(f"[{name}] Refit {old_role} -> {role}")
        if not self._park_for_service():
            host.log.end(f"[{name}] Refit aborted: not parked in a service area.")
            return False
        host._ensure_full_charge_for_sale()
        keep, sell, modules = plan_refit([(s.index, s.module_id) for s in host._slots() if s.module_id], spec["modules"])
        spec = dict(spec, modules=modules)
        host.log.debug(f"[{name}] Refit plan: keep slots {keep}, sell slots {sell}, loadout {modules}.")
        failure = self._sell_slots(sell)
        if failure is not None:
            host.log.level("warn").print(f"[{name}] Refit {old_role} -> {role} aborted: {failure}.")
            host.log.end(f"[{name}] Refit aborted.")
            return False

        job, lineage = refit_job(name, role, host.home_base, spec, host.get_current_tick())
        update_commission(lambda s: enqueue_refit(s, job, lineage))
        host.fit_loadout(spec, f"Refit to {role}", lambda missing: host._report_missing(name, missing))
        update_commission(lambda s: s.get("lineage", {}).get(name, {}).update({"fitted": True, "missing": {}}))

        host.role = role
        if role != "hauler":
            host.set_base(host.home_base)  # the other roles work for HOME_BASE; a hauler floats
        self._rename_for(role)
        host.publish_telemetry("REFIT", target_desc=role)
        self.refit_tick = host.get_current_tick()
        host.log.end(f"[{name}] Refitted to {role}.")
        return True

    def _park_for_service(self):
        """Moves the base to the nearest founded outpost when away from the current one, then parks in its service area."""
        host = self._host
        pos = host.get_position()
        origin = self._base_origin()
        if origin is None or distance(pos, origin) > FOOTPRINT_M:
            nearest = nearest_outpost(pos, founded_outposts())
            if nearest is not None:
                host.set_base(nearest)
        for _ in range(SERVICE_PARK_TRIES):
            if in_service_area(host.get_position(), self._base_origin()):
                return True
            host.return_to_base()
        return in_service_area(host.get_position(), self._base_origin())

    def _base_origin(self):
        outpost = self._host.home_outpost
        try:
            return tuple(outpost.coords())[:2] if outpost is not None else None
        except Exception as error:
            swallowed("pioneer_refit.PioneerRefitMixin._base_origin: outpost.coords", error)
            return None

    def _sell_slots(self, indices):
        """Sells each slot in indices (vehicle_recall.sell_slot()); parks again once on not_at_service_point. None, else the failure."""
        host = self._host
        if not indices:
            return None
        shop = host._shop()
        if shop is None:
            return "no Shop"
        reparked = False
        for index in indices:
            failure = None
            for _ in range(2):
                slot = next((s for s in host._slots() if s.index == index), None)
                if slot is None or not slot.module_id:
                    break
                failure = sell_slot(host.vehicle, slot, shop, host.log, host.name)
                if failure is None or "not_at_service_point" not in failure or reparked:
                    break
                reparked = True
                if not self._park_for_service():
                    return "not parked in a service area"
            if failure is not None:
                return failure
        return None

    def _rename_for(self, role):
        """Renames to commission_name() for role at the current base, unless the operator named this Pioneer."""
        host = self._host
        display = getattr(host.vehicle, "name", None)
        if not is_code_name(display, host.name):
            host.log.debug(f"[{host.name}] Refit keeps the operator's name '{display}'.")
            return
        if display == commission_name(host.name, host.base_id, role):
            return
        rename_vehicle(host.name, host.base_id, role, host.log)
