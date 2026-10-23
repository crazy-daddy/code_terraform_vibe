# Building pass of planner_loop.run_planner() (docs/plans/building_planner.md):
# compares what each outpost's designation wants with the buildings standing
# there and turns the difference into proposals. Nothing is built until the
# operator approves a proposal on the BUILD card (autoplay/build_panel.py);
# an approved proposal becomes building_ops jobs.
#
# Providers (pure, over the outpost_needs snapshot):
#   roles      one building per group a designated role lacks
#              (autoplay_roles.role_gaps()); the first alternative whose kit
#              can be had (snapshot "kits"); the Warehouse group is left to
#              the storage provider.
#   storage    once the Warehouse kit can be had: Warehouse slots the designation stocks (stock_slots()) beyond
#              the slots standing there; ceil(deficit / per_warehouse) of
#              the kind the snapshot builds (Large Warehouse once its kit is
#              available, building_planner.md "Storage replaces the fixed 2:1
#              swap"); at least one where a designated role needs a Warehouse.
#   retire     a Refiner that published retire "ready" (refiner.status).
#   focus      the atmosphere focus (focus_plan.py): one "swap" proposal
#              current -> focus pillar when a pillar swap is worth it; the
#              focus itself goes to autoplay.focus every full pass, together
#              with the game_phase history sample (game_phase.record()).
#   atmosphere, power, factory, kits, retire, fleet
#              build_providers.py over build_context() (grids, generators,
#              machines, fleet counts, prices): deploys, in-place upgrade
#              packs, retires and fleet changes.
# Gates: the building cap and, for deploys with a known draw, the grid's power
# headroom (build_providers.power_block()). A deploy that takes an outpost over its capacity
# while it holds a penalized machine (storage.PENALIZED_TYPES) is shown
# blocked and can't be approved (founding plan §capacity).
#
# Archive autoplay.build_proposals {proposal_id: entry}, rewritten only on change:
#   kind      "deploy" | "upgrade" | "retire" | "swap" | "fleet"
#   outpost, type_id, kit, count (deploy) / machine_id, item_id (upgrade) /
#   machine_id (retire) / from, to (swap: pillar_swap keys) /
#   fleet_kind, role, delta (fleet: +1 commission, -1 retire)
#   provider, why, kit_source ("inventory" | "available" | None), blocked
#   status    proposed | approved | queued | rejected
#   jobs      building_ops job ids once queued
#   tick      proposed / rejected / queued at
# Ids: "deploy:<outpost>:<type_id>", "upgrade:<machine_id>:<item_id>",
# "retire:<machine_id>", "focus:<from>:<to>", "fleet:<kind>:<role>:<+|->"
# (":<outpost>" appended for a per-outpost fleet row, e.g. a Pioneer miner).
# An approved fleet row calls fleet_commission.queue_pioneer() (HOME_BASE =
# the row's outpost, home without one) / queue_drone() or
# fleet_decommission.request_decommission() (an idle unit of the role, at
# the row's outpost when set) and is done at once.
# A rejected entry holds its id out for REJECT_HOLD_TICKS. A queued entry
# goes once all its jobs are done; a blocked job puts the entry back to
# proposed with the job's status in `blocked`. An approved swap calls
# pillar_swap.request_swap() (a refusal puts it back to proposed, blocked
# "swap running"); a queued swap that stopped running goes, and one the
# operator stopped (pillar.swap "stopped") is held like a rejected entry.
# An approved swap row that no longer matches the focus goes back to
# proposed, so a stale from/to never starts.

from typing import TYPE_CHECKING

import autoplay_roles
import build_providers
import building_ops
import components
import focus_plan
import game_phase
import outpost_needs
import pillar_swap
from archive import archive
from autoplay_roles import WAREHOUSE_SLOTS, WAREHOUSES, kit_id, role_gaps, stock_slots, warehouse_slots
from components import component, machine_tier
from game_clock import is_fresh
from logistics_requests import PICKUP_STALE_TICKS, drone_yield_enabled
from priority import BUILD
from storage import PENALIZED_TYPES, inventory_count
from swallow import swallowed

ROLE_DEMAND_KEY = "fleet.role_demand"  # = role_demand.ROLE_DEMAND_KEY
ROLE_DEMAND_STALE_TICKS = 3000  # = role_demand.ROLE_DEMAND_STALE_TICKS
MISSIONS_KEY = "fleet.missions"  # = mission_pool.MISSIONS_KEY
MISSIONS_STALE_TICKS = 3000  # = mission_pool.MISSIONS_STALE_TICKS

if TYPE_CHECKING:
    from tree_console import TreeConsole

PROPOSALS_KEY = "autoplay.build_proposals"
REQUESTER = "building_plan"
REFINER_STATUS_KEY = "refiner.status"
RETIRE_READY = "ready"
PASS_TICKS = 6000  # full pass at most this often (10 sim min)
REJECT_HOLD_TICKS = 864000  # 24 sim hours a rejected proposal stays out
OPEN = ("proposed", "approved", "queued")
MINER_LATCH_KEY = "autoplay.miner_latch"  # {"seen": {vehicle: tick}, "idle": {vehicle: tick}, "need": {"outpost:ore": tick}}: since when a Pioneer miner is in fleet.status, is idle, a raw ore is at NEED there
FLEET_PREFIXES = (("pioneer_", "pioneer"), ("rover_", "rover"), ("drone_", "drone"))
TIERED_TYPES = build_providers.GENERATOR_TYPES + build_providers.FACTORY_TYPES  # machines with a tier() to read (packs apply there)


def _tick():
    try:
        clock = get_component("clock")
        return clock.tick() if clock else 0
    except Exception as error:
        swallowed("building_plan._tick: clock.tick", error)
        return 0


# ---------- providers (pure) ----------


def _pick(group, kits):
    """First alternative of a building group whose kit can be had; None when all are locked."""
    for type_id in group:
        if kit_id(type_id) in kits:
            return type_id
    return None


def role_wants(entry, kits):
    """[(type_id, 1, why)] for every building group a designated role lacks at this outpost (Warehouses left out)."""
    types = entry.get("types") or {}
    out = []
    seen = []
    for role in role_gaps(entry.get("roles"), types)["missing"]:
        for group in autoplay_roles.building_groups(role):
            if group == WAREHOUSES or group in seen or any(types.get(t, 0) > 0 for t in group):
                continue
            seen.append(group)
            type_id = _pick(group, kits)
            if type_id is not None:
                out.append((type_id, 1, f"role {role} lacks {type_id}"))
    return out


def storage_wants(entry, snap):
    """[(warehouse type, count, why)] for the Warehouse slots the designation stocks beyond what stands there."""
    roles = entry.get("roles") or []
    types = entry.get("types") or {}
    per = snap.get("per_warehouse") or WAREHOUSE_SLOTS["warehouse"]
    type_id = "large_warehouse" if per == WAREHOUSE_SLOTS["large_warehouse"] else "warehouse"
    if kit_id(type_id) not in (snap.get("kits") or ()):
        return []  # before Warehouse research: Storage Bins, sized by the machine scripts
    want = stock_slots(roles, snap.get("stock") or {})
    have, buildings = warehouse_slots(types)
    count = (max(0, want - have) + per - 1) // per
    if count:
        return [(type_id, count, f"stock needs {want} slots, {have} standing")]
    needs_one = any(WAREHOUSES in autoplay_roles.building_groups(role) for role in autoplay_roles.role_list(roles))
    if needs_one and not buildings:
        return [(type_id, 1, "designated role needs a Warehouse")]
    return []


def cap_block(entry, type_id, count):
    """Reason the deploy would break the cap gate, else None."""
    used, cap = entry.get("used", 0), entry.get("capacity", 0)
    if not cap or used + count <= cap:
        return None
    types = entry.get("types") or {}
    if type_id in PENALIZED_TYPES or any(types.get(t, 0) > 0 for t in PENALIZED_TYPES):
        return f"over cap ({used}+{count} > {cap}) with a penalized machine"
    return None


def reserve_open(snap, proposals, jobs):
    """
    Snapshot copy whose outposts hold the slots of the open deploys (approved,
    or queued with jobs not done): used += n, "reserved" = {type_id: n}.
    """
    held = {}
    for entry in proposals.values():
        if not isinstance(entry, dict) or entry.get("kind") != "deploy" or not entry.get("outpost"):
            continue
        if entry.get("status") == "approved":
            n = int(entry.get("count", 1))
        elif entry.get("status") == "queued":
            n = len([j for j in entry.get("jobs") or [] if (jobs.get(j) or {}).get("state") != "done"])
        else:
            continue
        if n > 0:
            row = held.setdefault(entry["outpost"], {})
            row[entry["type_id"]] = row.get(entry["type_id"], 0) + n
    if not held:
        return snap
    rows = []
    for entry in snap.get("outposts") or []:
        row = held.get(entry["id"])
        rows.append(dict(entry, used=entry.get("used", 0) + sum(row.values()), reserved=row) if row else entry)
    return dict(snap, outposts=rows)


def want_id(entry):
    """Proposal id of a build_providers want."""
    kind = entry["kind"]
    if kind == "deploy":
        return f"deploy:{entry['outpost']}:{entry['type_id']}"
    if kind == "upgrade":
        return f"upgrade:{entry['machine_id']}:{entry['item_id']}"
    if kind == "retire":
        return f"retire:{entry['machine_id']}"
    pid = f"fleet:{entry['fleet_kind']}:{entry['role']}:{'+' if entry.get('delta', 0) > 0 else '-'}"
    return f"{pid}:{entry['outpost']}" if entry.get("outpost") else pid


def provider_proposals(ctx, inventory):
    """{proposal_id: entry} of build_providers.all_wants(ctx) with the shared gates applied."""
    snap = ctx.get("snap") or {}
    kits = snap.get("kits") or set()
    by_id = {entry["id"]: entry for entry in snap.get("outposts") or []}
    out = {}
    for item in build_providers.all_wants(ctx):
        pid = want_id(item)
        if pid in out:
            continue
        entry = {
            "kind": item["kind"],
            "outpost": item.get("outpost"),
            "type_id": item.get("type_id"),
            "count": int(item.get("count") or 1),
            "machine_id": item.get("machine_id"),
            "item_id": item.get("item_id"),
            "fleet_kind": item.get("fleet_kind"),
            "role": item.get("role"),
            "delta": int(item.get("delta") or 0),
            "provider": item["provider"],
            "why": item["why"],
            "kit_source": None,
            "blocked": item.get("blocked"),
        }
        if item["kind"] == "deploy":
            kit = kit_id(item["type_id"])
            entry["kit"] = kit
            entry["kit_source"] = "inventory" if inventory.get(kit, 0) >= entry["count"] else ("available" if kit in kits else None)
            host = by_id.get(item.get("outpost"))
            if host is not None and not entry["blocked"]:
                entry["blocked"] = cap_block(host, item["type_id"], entry["count"])
        elif item["kind"] == "upgrade":
            entry["kit"] = item["item_id"]
            entry["kit_source"] = "inventory" if inventory.get(item["item_id"], 0) > 0 else "available"
        out[pid] = entry
    return out


def fresh_proposals(snap, inventory, refiners, focus=None, ctx=None):
    """
    {proposal_id: entry} the providers want now. inventory = {kit_id: units};
    refiners = refiner.status {machine_id: entry}; focus = focus_plan.decide()
    output (its swap, when decided, becomes the "focus:<from>:<to>" entry);
    ctx = build_context() for the build_providers (None: roles, storage,
    Refiner retire and the swap only).
    """
    kits = snap.get("kits") or set()
    out = {}
    for entry in snap.get("outposts") or []:
        oid = entry["id"]
        for provider, wants in (("roles", role_wants(entry, kits)), ("storage", storage_wants(entry, snap))):
            for type_id, count, why in wants:
                kit = kit_id(type_id)
                source = "inventory" if inventory.get(kit, 0) >= count else ("available" if kit in kits else None)
                out[f"deploy:{oid}:{type_id}"] = {"kind": "deploy", "outpost": oid, "type_id": type_id, "kit": kit, "count": count, "provider": provider, "why": why, "kit_source": source, "blocked": cap_block(entry, type_id, count)}
    for machine_id, status in sorted((refiners or {}).items()):
        if isinstance(status, dict) and status.get("retire") == RETIRE_READY:
            out[f"retire:{machine_id}"] = {"kind": "retire", "machine_id": machine_id, "outpost": status.get("outpost"), "type_id": "refiner", "provider": "retire", "why": "wildlife complete, Refiner emptied", "kit_source": None, "blocked": None}
    swap = focus_plan.swap_entry(focus or {})
    if swap is not None:
        out[focus_plan.proposal_id(focus or {})] = swap
    if ctx is not None:
        for pid, entry in provider_proposals(ctx, inventory).items():
            out.setdefault(pid, entry)
    return out


def _drop_stale_swaps(proposals, fresh):
    """Approved swap rows the fresh pass no longer wants go back to proposed (and then away)."""
    for pid, entry in proposals.items():
        if entry.get("kind") == "swap" and entry.get("status") == "approved" and pid not in fresh:
            entry["status"] = "proposed"


def merge(old, fresh, tick):
    """New proposals dict: open entries keep their status, rejected ones hold their id, dropped proposals go."""
    out = {}
    for pid, entry in old.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "rejected" and tick - (entry.get("tick") or 0) < REJECT_HOLD_TICKS:
            out[pid] = entry
        elif status in ("approved", "queued"):
            out[pid] = dict(entry, **{k: v for k, v in (fresh.get(pid) or {}).items() if k not in ("count", "blocked")})
    for pid, entry in fresh.items():
        if pid in out:
            continue
        prev = old.get(pid) if isinstance(old.get(pid), dict) else {}
        out[pid] = dict(entry, status="proposed", tick=prev.get("tick", tick) if prev.get("status") == "proposed" else tick)
    return out


def advance(entry, jobs):
    """Status of a queued entry from its jobs: "done" (all done), "blocked: <status>" or "queued"."""
    states = [(jobs.get(j) or {}) for j in entry.get("jobs") or []]
    for job in states:
        if job.get("state") == "blocked":
            return "blocked: " + str(job.get("status"))
    if states and all(job.get("state") == "done" for job in states):
        return "done"
    if not states:
        return "done"
    return "queued"


# ---------- operator answers (BUILD card) ----------


def load():
    return archive.get_dict(PROPOSALS_KEY)


def answer(proposal_id, approve):
    """Operator approve / reject of an open proposal; False when it is not open, blocked or the write failed."""
    tick = _tick()
    done = [False]

    def updater(cur):
        cur = cur if isinstance(cur, dict) else {}
        entry = cur.get(proposal_id)
        if not isinstance(entry, dict) or entry.get("status") != "proposed":
            return cur
        if approve and entry.get("blocked"):
            return cur
        entry["status"] = "approved" if approve else "rejected"
        entry["tick"] = tick
        done[0] = True
        return cur

    return archive.transaction(PROPOSALS_KEY, {}, updater) and done[0]


# ---------- pass ----------


def _read_inventory(kits):
    out = {}
    for kit in kits:
        out[kit] = inventory_count(kit)
    return out


# ---------- context readers (build_providers) ----------


def read_grids():
    """build_providers grid rows from power_control.grids()."""
    import power  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")

    control = component("power_control")
    out = []
    if control is None:
        return out
    try:
        grids = list(control.grids() or [])
    except Exception as error:
        swallowed("building_plan.read_grids: power_control.grids", error)
        return out
    for grid in grids:
        try:
            types = {}
            for member in getattr(grid, "members", None) or []:
                type_id = str(getattr(member, "type_id", "") or "")
                types[type_id] = types.get(type_id, 0) + 1
            out.append(
                {
                    "anchor": str(getattr(grid, "anchor_id", "")),
                    "outposts": [str(o) for o in (getattr(grid, "outpost_ids", None) or [])],
                    "generated": float(getattr(grid, "generated", 0.0) or 0.0),
                    "consumed": float(getattr(grid, "consumed", 0.0) or 0.0),
                    "stored": float(getattr(grid, "stored", 0.0) or 0.0),
                    "capacity": float(getattr(grid, "capacity", 0.0) or 0.0),
                    "reserve": power.reserve_fraction(power.measure_grid(grid)),
                    "phase": power.grid_phase(grid),
                    "types": types,
                }
            )
        except Exception as error:
            swallowed("building_plan.read_grids: grid fields", error)
    return out


def read_machines(type_ids):
    """({type_id: [(machine_id, outpost_id, tier)]}, {(outpost_id, type_id): [machine_id]}) over outpost_network."""
    rows = {}
    ids = {}
    for ref in components.outposts():
        for type_id in type_ids:
            try:
                for building in ref.buildings(type_id) or []:
                    rows.setdefault(type_id, []).append((building.id, ref.id, machine_tier(building.id) if type_id in TIERED_TYPES else 1))
                    ids.setdefault((ref.id, type_id), []).append(building.id)
            except Exception as error:
                swallowed("building_plan.read_machines: buildings", error)
    return rows, ids


def unit_kind(name):
    return next((kind for prefix, kind in FLEET_PREFIXES if str(name).startswith(prefix)), None)


def fleet_counts(status, commission=None, decommission=None):
    """
    {kind: {role: n}} of fleet.status entries by name prefix (FLEET_PREFIXES) and
    published role, plus "queued": {kind: {role: n}} commission jobs not done
    and "retiring": {kind: {role: n}} units with a decommission entry.
    """
    import fleet_commission  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")

    out = {}
    roles = {}
    for name, entry in (status or {}).items():
        if not isinstance(entry, dict):
            continue
        kind = unit_kind(name)
        role = entry.get("role")
        if kind and role:
            out.setdefault(kind, {})[role] = out.get(kind, {}).get(role, 0) + 1
            roles[str(name)] = (kind, role)
    queued = {}
    for job in (commission or {}).get("jobs") or []:
        if isinstance(job, dict) and job.get("state") not in ("done", "cancelled") and job.get("role"):
            kind = fleet_commission.job_kind(job)
            queued.setdefault(kind, {})[job["role"]] = queued.get(kind, {}).get(job["role"], 0) + 1
    retiring = {}
    for name in decommission or {}:
        if name in roles:
            kind, role = roles[name]
            retiring.setdefault(kind, {})[role] = retiring.get(kind, {}).get(role, 0) + 1
    out["queued"] = queued
    out["retiring"] = retiring
    return out


def idle_unit(status, kind, role, decommission=None, home=None):
    """Name of an idle fleet.status unit of kind / role not already retiring (with base `home` when given: HOME_BASE until a refit moves it; not for a hauler: haulers float); None without one.
    A Pioneer with Seismic Sonar mounted goes last: it alone surveys deep oil."""
    import fleet_status  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")
    from outpost_mining import HOME_OUTPOST_ID

    names = []
    for name, entry in (status or {}).items():
        if not isinstance(entry, dict) or entry.get("role") != role or unit_kind(name) != kind or name in (decommission or {}):
            continue
        if home is not None and role != "hauler" and (entry.get("base") or entry.get("home") or HOME_OUTPOST_ID) != home:
            continue
        if fleet_status.is_idle(entry.get("state")):
            names.append(str(name))
    return min(names, key=lambda name: (kind == "pioneer" and seismic_mounted(name), name)) if names else None


def seismic_mounted(vehicle_id):
    """True when vehicle_id has Seismic Sonar mounted."""
    import pioneer_upgrade  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")

    vehicle = component(vehicle_id)
    try:
        return bool(vehicle) and any(slot.module_id == pioneer_upgrade.SEISMIC_SONAR_ID for slot in vehicle.modules())
    except Exception as error:
        swallowed("building_plan.seismic_mounted: vehicle.modules", error)
        return False


def pickup_backlog(pickups, tick, stale=PICKUP_STALE_TICKS):
    """Age in ticks of the oldest pickup still not aboard and younger than `stale` (abandoned plans leave older ones); 0 without one."""
    ages = [tick - int(entry.get("tick") or tick) for entry in (pickups or {}).values() if isinstance(entry, dict) and not entry.get("aboard")]
    live = [age for age in ages if age < stale]
    return max(live) if live else 0


def drills_missing(snap):
    """Smelter ores without a surveyed site that has a drill."""
    rows = snap.get("ore_sites") or []
    return sorted(ore for ore in snap.get("ore_wanted") or [] if not any(row.get("item") == ore and row.get("drill") for row in rows))


def latch_since(part, live, tick):
    """{name: tick} since which each name in `live` is continuously present (MINER_LATCH_KEY[part]); names gone drop out. Writes only on change."""
    latch = archive.get(MINER_LATCH_KEY, {}) or {}
    if not isinstance(latch, dict):
        latch = {}
    state = latch.get(part)
    if not isinstance(state, dict):
        state = {}
    out = {name: int(state[name]) if isinstance(state.get(name), (int, float)) else int(tick) for name in live}
    if out != state:
        archive.set(MINER_LATCH_KEY, dict(latch, **{part: out}))
    return out


class _OutpostId:
    """The id-only outpost a live=False outpost_tier_deficits() read needs."""

    def __init__(self, outpost_id):
        self.id = outpost_id


def ore_need(tick):
    """{outpost_id: [ore, ...]} raw ores at NEED or above per outpost (published requests, net of in-flight and mining yield)."""
    import logistics_requests  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")
    from game_rules import RAW_ORE_ITEM_IDS

    out = {}
    for outpost_id in logistics_requests.active_requests(tick):
        need, _stock = logistics_requests.split_need_stock(logistics_requests.outpost_tier_deficits(_OutpostId(outpost_id), tick, live=False))  # type: ignore[arg-type]  # live=False reads only .id
        ores = sorted(item for item, units in need.items() if item in RAW_ORE_ITEM_IDS and units > 0)
        if ores:
            out[outpost_id] = ores
    return out


def ore_need_since(need, tick):
    """{outpost_id: {ore: tick}} since which each NEED ore is open there (MINER_LATCH_KEY "need")."""
    since = latch_since("need", [f"{outpost_id}:{ore}" for outpost_id, ores in need.items() for ore in ores], tick)
    out = {}
    for name, start in since.items():
        outpost_id, ore = name.rsplit(":", 1)
        out.setdefault(outpost_id, {})[ore] = start
    return out


def miner_homes(status, commission, tick):
    """
    {outpost_id: {"count", "queued", "newest", "idle_since"}} of Pioneer miners
    by base (HOME_BASE until a refit stations the miner elsewhere): count = fleet.status units with role "miner" plus queued
    miner jobs (queued). newest: the latest tick a miner there showed up
    (MINER_LATCH_KEY "seen"). idle_since: the oldest tick an idle miner there
    has been idle since ("idle"), None without an idle one. A job whose
    Pioneer already reports in fleet.status (attach, fitting) counts once.
    """
    import fleet_commission  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")
    import fleet_status
    from outpost_mining import HOME_OUTPOST_ID

    out = {}
    idle = []
    homes = {}
    for name, entry in (status or {}).items():
        if not isinstance(entry, dict) or entry.get("role") != "miner" or unit_kind(name) != "pioneer":
            continue
        home = entry.get("base") or entry.get("home") or HOME_OUTPOST_ID
        homes[str(name)] = home
        out.setdefault(home, {"count": 0, "queued": 0, "newest": None, "idle_since": None})["count"] += 1
        if fleet_status.is_idle(entry.get("state")):
            idle.append(str(name))
    for job in (commission or {}).get("jobs") or []:
        if isinstance(job, dict) and job.get("state") not in ("done", "cancelled") and job.get("role") == "miner" and fleet_commission.job_kind(job) == "pioneer" and job.get("new_id") not in homes:
            home = fleet_commission.job_home_base(job) or HOME_OUTPOST_ID
            slot = out.setdefault(home, {"count": 0, "queued": 0, "newest": None, "idle_since": None})
            slot["count"] += 1
            slot["queued"] += 1
    for name, start in latch_since("seen", list(homes), tick).items():
        slot = out[homes[name]]
        slot["newest"] = start if slot["newest"] is None else max(slot["newest"], start)
    for name, start in latch_since("idle", idle, tick).items():
        slot = out[homes[name]]
        slot["idle_since"] = start if slot["idle_since"] is None else min(slot["idle_since"], start)
    return out


def pioneer_role_demand(tick):
    """{role: {"wanted", "keep", "slots"?}} of a fresh fleet.role_demand (lib/role_demand.py; read here without its import chain), else {}."""
    value = archive.get(ROLE_DEMAND_KEY, {})
    if not is_fresh(value, tick, ROLE_DEMAND_STALE_TICKS) or not isinstance(value.get("roles"), list):
        return {}
    out = {}
    for e in value["roles"]:
        if isinstance(e, dict) and isinstance(e.get("role"), str):
            out[e["role"]] = {"wanted": int(e.get("wanted") or 0), "keep": int(e.get("keep") or 0)}
            if isinstance(e.get("slots"), dict):
                out[e["role"]]["slots"] = e["slots"]  # the miner entry: per outpost
    return out


def pioneer_missions(tick):
    """Entries of a fresh fleet.missions (lib/mission_pool.py; read here without its import chain), else []."""
    value = archive.get(MISSIONS_KEY, {})
    if not is_fresh(value, tick, MISSIONS_STALE_TICKS) or not isinstance(value.get("entries"), list):
        return []
    return [e for e in value["entries"] if isinstance(e, dict) and isinstance(e.get("id"), str)]


def _safe(name, read, default):
    """read(), or default when it raises (one failing reader must not drop every provider)."""
    try:
        return read()
    except Exception as error:
        swallowed("building_plan.build_context: " + name, error)
        return default


def read_prices():
    shop = component("shop")
    if shop is None:
        return {}
    try:
        return {item.id: int(item.cost) for item in shop.get_catalogue() or []}
    except Exception as error:
        swallowed("building_plan.read_prices: shop.get_catalogue", error)
        return {}


def build_context(snap, phase, focus, tick):
    """The build_providers context (its module header) from the in-game reads."""
    import fleet_commission
    import fleet_decommission
    import fleet_status
    import outpost_mining
    from logistics_requests import pickups_snapshot

    machines, machine_ids = read_machines(build_providers.GENERATOR_TYPES + build_providers.FACTORY_TYPES + ("storage_bin", "weather_station", "battery", "charging_station"))
    status = _safe("fleet_status", fleet_status.get_all, None)
    commission = _safe("fleet_commission", fleet_commission.commission_state, {})
    decommission = _safe("fleet_decommission", fleet_decommission.decommission_state, {})
    pickups = _safe("pickups", pickups_snapshot, {})
    need = _safe("ore_need", lambda: ore_need(tick), None)  # None, not {}: a failed read must not reset the latches
    reach = _safe("mining_reach", lambda: outpost_mining.mineable_ores_by_outpost(tick), {})
    prices = read_prices()
    packs = [build_providers.pack_id(t, tier) for t in build_providers.GENERATOR_TYPES for tier in (2, 3)] + [build_providers.MACHINE_PACKS[t] + str(tier) for t in build_providers.FACTORY_TYPES for tier in (2, 3)]
    return {
        "snap": snap,
        "phase": phase,
        "focus": focus or {},
        "generators": {t: machines.get(t, []) for t in build_providers.GENERATOR_TYPES},
        "machines": {t: machines.get(t, []) for t in build_providers.FACTORY_TYPES},
        "machine_ids": machine_ids,
        "grids": read_grids(),
        "prices": prices,
        "inventory": _read_inventory(packs),
        "fleet": fleet_counts(status or {}, commission, decommission),
        "fleet_status": status,  # None: unreadable, not "no builders" (charging_pass() and charging_retire_wants() then do nothing)
        "pickup_backlog": pickup_backlog(pickups, tick),
        "pioneer_roles": _safe("role_demand", lambda: pioneer_role_demand(tick), {}),
        "missions": _safe("missions", lambda: pioneer_missions(tick), []),
        "drone_yield": _safe("drone_yield", drone_yield_enabled, False),
        "drills_missing": drills_missing(snap),
        "miners": _safe("miner_homes", lambda: miner_homes(status, commission, tick), {}) if status is not None else {},
        "mining_reach": {outpost_id: sorted(ores) for outpost_id, ores in reach.items()},
        "ore_need": _safe("ore_need_since", lambda: ore_need_since(need, tick), {}) if need is not None else {},
        "tick": tick,
    }


def takeover_pass(ctx, log):
    """
    Turns the drone yield switch on once build_providers.drone_takeover(ctx)
    holds and it is off (autoplay plays without the operator's FLEET switch);
    never turns it off. True when it flipped.
    """
    import logistics_requests  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")

    if ctx.get("drone_yield") or not build_providers.drone_takeover(ctx):
        return False
    logistics_requests.set_drone_yield_enabled(True)
    ctx["drone_yield"] = True
    log.start("Drone takeover")
    log.print(f"Depots stand and {build_providers.TAKEOVER_HAULERS} hauler drones fly: drone yield switched on.")
    log.end("drone yield on")
    return True


def charging_pass(ctx, log):
    """Once the Pioneer haulers are replaced (charging_retire_ready()), moves the "charging" role to build_providers.charging_keepers() (the stations go through build_providers.kit_wants())."""
    if not build_providers.charging_retire_ready(ctx):
        return
    keepers = build_providers.charging_keepers(ctx)
    # A miner base only keeps what it has: without the role it is left out (not added, nothing to remove).
    only_miners = build_providers.miner_keepers(ctx) - autoplay_roles.station_keepers(build_providers.outposts(ctx), ctx.get("fleet_status"))
    entries = autoplay_roles.outpost_roles()
    keepers -= {outpost_id for outpost_id in only_miners if "charging" not in autoplay_roles.role_list(entries.get(outpost_id))}
    added, removed = autoplay_roles.sync_charging_roles(keepers)
    if added or removed:
        log.start("Charging roles")
        log.print(f"charging role: added {added}, removed {removed}.")
        log.end(f"{len(added) + len(removed)} change(s)")


class BuildingPlanner:
    """
    The building pass. run_pass(snap) returns "idle" (nothing proposed or
    queued), "waiting" (proposals wait for the operator) or "working" (jobs
    run). snap: the founding pass's outpost_needs snapshot when fresh, else
    None (read here).
    """

    def __init__(self, log: "TreeConsole"):
        self.log = log
        self.ops = building_ops.BuildingOps(log)
        self.full_tick = None
        self.phase = None  # last game_phase snapshot (its research set survives a failed read)
        self.focus = None

    def due(self):
        return self.full_tick is None or _tick() - self.full_tick >= PASS_TICKS

    def run_pass(self, snap=None):
        tick = _tick()
        stored = load()
        proposals = {pid: dict(e) for pid, e in stored.items() if isinstance(e, dict)}
        if self.due():
            snap = snap if snap is not None else outpost_needs.snapshot()
            refiners = archive.get(REFINER_STATUS_KEY, {}) or {}
            self.focus = self._focus(snap, tick)
            snap = reserve_open(snap, proposals, building_ops.jobs())
            ctx = self._context(snap, tick)
            if ctx is not None:
                takeover_pass(ctx, self.log)
                charging_pass(ctx, self.log)
            kits = sorted({e["kit"] for e in fresh_proposals(snap, {}, refiners, None, ctx).values() if e.get("kit")})
            wanted = fresh_proposals(snap, _read_inventory(kits), refiners, self.focus, ctx)
            _drop_stale_swaps(proposals, wanted)
            proposals = merge(proposals, wanted, tick)
            self.full_tick = tick
        lines = self._queue(proposals, tick)
        notes = self.ops.step_jobs()
        lines += self._settle(proposals)
        if proposals != stored:
            archive.transaction(PROPOSALS_KEY, {}, lambda _old: proposals)
        opened = [pid for pid, e in proposals.items() if e.get("status") == "proposed" and stored.get(pid, {}).get("status") != "proposed"]
        if lines or opened:
            self.log.start("Building proposals")
            for pid in opened:
                e = proposals[pid]
                if e["kind"] == "swap":
                    self.log.print(f"Proposed swap {e['from']} -> {e['to']}: {e['why']}")
                    continue
                if e["kind"] == "fleet":
                    self.log.print(f"Proposed fleet {e['fleet_kind']} {e['role']} {e['delta']:+d}: {e['why']}" + (f" (blocked: {e['blocked']})" if e.get("blocked") else ""))
                    continue
                what = f"{e.get('count', 1)}x {e['type_id']}" if e["kind"] == "deploy" else (f"{e['machine_id']} {e['item_id']}" if e["kind"] == "upgrade" else e["machine_id"])
                self.log.print(f"Proposed {e['kind']} {what} at {e.get('outpost') or 'home'}: {e['why']}" + (f" (blocked: {e['blocked']})" if e.get("blocked") else ""))
            for line in lines:
                self.log.print(line)
            self.log.end(f"{len([e for e in proposals.values() if e.get('status') in OPEN])} open")
        if notes:
            self.log.debug("Build jobs: " + "; ".join(notes))
        if any(e.get("status") == "queued" for e in proposals.values()):
            return "working"
        return "waiting" if any(e.get("status") == "proposed" for e in proposals.values()) else "idle"

    def _context(self, snap, tick):
        try:
            return build_context(snap, self.phase or {}, self.focus, tick)
        except Exception as error:
            swallowed("building_plan.BuildingPlanner._context", error)
            self.log.level("warn").print(f"Build context failed: {error}")
            return None

    def _focus(self, snap, tick):
        """The atmosphere focus of this pass: game_phase snapshot and history sample, focus_plan.run(), autoplay.focus."""
        try:
            self.phase = game_phase.snapshot(tick, self.phase)
            game_phase.record(self.phase, tick)
            focus = focus_plan.run(self.phase, focus_plan.wants_from_needs(outpost_needs.needs(snap)), tick)
        except Exception as error:
            swallowed("building_plan.BuildingPlanner._focus", error)
            self.log.level("warn").print(f"Focus pass failed: {error}")
            return self.focus
        stored = archive.get(focus_plan.FOCUS_KEY, {}) or {}
        if {k: v for k, v in focus.items() if k != "tick"} != {k: v for k, v in stored.items() if k != "tick"}:
            archive.set(focus_plan.FOCUS_KEY, focus)
            self.log.debug(f"Focus: {focus.get('pillar')} ({focus.get('mode')}), current {focus.get('current')}, swap {focus.get('swap')}: {'; '.join(focus.get('why') or [])}")
        return focus

    def _queue(self, proposals, tick):
        """Approved proposals become executor jobs (a swap: a pillar_swap request)."""
        lines = []
        for pid, entry in sorted(proposals.items()):
            if entry.get("status") != "approved":
                continue
            jobs = []
            if entry["kind"] == "swap":
                if pillar_swap.request_swap(entry["from"], entry["to"]):
                    entry.update({"status": "queued", "jobs": [], "tick": tick, "blocked": None})
                    lines.append(f"{pid} approved: pillar swap {entry['from']} -> {entry['to']} requested.")
                else:
                    entry.update({"status": "proposed", "blocked": "swap running", "tick": tick})
                    lines.append(f"{pid}: pillar swap refused (one running); back to proposed.")
                continue
            if entry["kind"] == "fleet":
                done = self._fleet_action(entry)
                if done:
                    del proposals[pid]
                    lines.append(f"{pid} approved: {done}.")
                else:
                    entry.update({"status": "proposed", "blocked": "no idle unit of that role", "tick": tick})
                    lines.append(f"{pid}: no idle unit to retire; back to proposed.")
                continue
            if entry["kind"] == "deploy":
                for n in range(int(entry.get("count", 1))):
                    jobs.append(building_ops.request_deploy(entry["type_id"], entry["outpost"], REQUESTER, entry["why"], ref=f"{pid}#{n}", kit_id=entry.get("kit")))
            elif entry["kind"] == "upgrade":
                jobs.append(building_ops.request_upgrade(entry["machine_id"], entry["item_id"], REQUESTER, entry["why"]))
            else:
                # The Refiner emptied itself already (its retire flag); the retire provider's types (bins,
                # batteries, Weather Stations) hold nothing a script must empty: no handshake either.
                jobs.append(building_ops.request_retire(entry["machine_id"], REQUESTER, entry["why"], handshake=False))
            if None in jobs:
                lines.append(f"{pid}: job write rejected; retried next pass.")
                continue
            entry.update({"status": "queued", "jobs": jobs, "tick": tick})
            lines.append(f"{pid} approved: {len(jobs)} job(s) queued.")
        return lines

    def _fleet_action(self, entry):
        """Runs an approved fleet row: a commission job or a decommission request. Returns a line, or None when no unit fits."""
        import fleet_commission  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")
        import fleet_decommission
        import fleet_status

        kind, role = entry.get("fleet_kind"), entry.get("role")
        if int(entry.get("delta") or 0) > 0:
            if kind == "drone":
                job = fleet_commission.queue_drone(role, None, prio=BUILD)
            else:
                job = fleet_commission.queue_pioneer(role, entry.get("outpost"), prio=BUILD)
            return f"commission job {job} ({kind} {role})"
        name = idle_unit(fleet_status.get_all(), kind, role, fleet_decommission.decommission_state(), entry.get("outpost"))
        if name is None:
            return None
        fleet_decommission.request_decommission(name, kind)
        return f"decommission {name}"

    def _settle(self, proposals):
        """Queued entries whose jobs finished go; a blocked job sends its entry back to proposed."""
        jobs = building_ops.jobs()
        lines = []
        for pid in sorted(proposals):
            entry = proposals[pid]
            if entry.get("status") != "queued":
                continue
            if entry.get("kind") == "swap":
                if not pillar_swap.is_running():
                    state = (pillar_swap.swap_state() or {}).get("state")
                    if state == "stopped":
                        entry.update({"status": "rejected", "tick": _tick()})
                        lines.append(f"{pid}: swap stopped by the operator; held.")
                    else:
                        del proposals[pid]
                        lines.append(f"{pid}: swap ended ({state}).")
                continue
            state = advance(entry, jobs)
            if state == "done":
                del proposals[pid]
                lines.append(f"{pid}: done.")
            elif state.startswith("blocked"):
                entry.update({"status": "proposed", "blocked": state[len("blocked: ") :], "jobs": []})
                lines.append(f"{pid}: job {state}; back to proposed.")
        return lines
