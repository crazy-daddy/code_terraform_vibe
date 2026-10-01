# Lead Cask roles and hot-cargo moves (docs/components/lead_cask.md).
#
# A cask holds one hot item (Raw Uranium or Fuel Rods) and unlatches when empty.
# A Drone Depot unloading hot cargo picks the first cask at its outpost that is
# empty or already holds that item with room (simworker drone `unload`), so a
# script cannot choose the cask. Roles therefore work by planning and repair:
#   - `lead_cask.roles` = {cask_id: "fuel_rod" | "raw_uranium"}, one shared dict
#     like `fluid_routing.tank_assignments`. Operator-editable; ensure_rod_cask()
#     adds one "fuel_rod" entry per outpost that makes or burns rods. Casks
#     without an entry take either item.
#   - Room for an item (room_for(), drones' uranium collection) leaves out casks
#     whose role is the other item.
#   - repair() moves Raw Uranium out of a "fuel_rod" cask into other casks
#     (transfer_to), and take_from_casks() drains such a cask first, so the
#     cask unlatches and the next Fuel Rod latches it.

from archive import archive
from swallow import swallowed

LEAD_CASK_TYPE_ID = "lead_cask"
URANIUM_ITEM = "raw_uranium"
ROD_ITEM = "fuel_rod"
HOT_ITEMS = (URANIUM_ITEM, ROD_ITEM)
ROLES_KEY = "lead_cask.roles"


def home_outpost():
    network = get_component("outpost_network")
    if network is None or not hasattr(network, "outposts"):
        return None
    try:
        for outpost in network.outposts():
            if getattr(outpost, "is_home", False):
                return outpost
    except Exception as error:
        swallowed("lead_cask.home_outpost: network.outposts", error)
    return None


def _all_outposts():
    network = get_component("outpost_network")
    if network is None or not hasattr(network, "outposts"):
        return []
    try:
        return list(network.outposts())
    except Exception as error:
        swallowed("lead_cask._all_outposts: network.outposts", error)
        return []


def roles():
    stored = archive.get(ROLES_KEY, {})
    return stored if isinstance(stored, dict) else {}


def casks_at(outpost):
    """[{"id", "component", "material", "count", "capacity", "role"}] for the Lead Casks at
    outpost (None = home). `material` is "" for an empty cask."""
    if outpost is None:
        outpost = home_outpost()
    if outpost is None or not hasattr(outpost, "buildings"):
        return []
    try:
        refs = outpost.buildings(LEAD_CASK_TYPE_ID)
    except Exception as error:
        swallowed("lead_cask.casks_at: outpost.buildings", error)
        return []
    assigned = roles()
    out = []
    for ref in refs or []:
        cask = get_component(getattr(ref, "id", ""))
        if cask is None:
            continue
        try:
            material = cask.material() or ""
            count = int(cask.count(material)) if material else 0
            out.append({"id": cask.id, "component": cask, "material": material, "count": count,
                        "capacity": int(cask.capacity()), "role": assigned.get(cask.id, "")})
        except Exception as error:
            swallowed("lead_cask.casks_at: lead_cask read", error)
    return out


def cask_stock(item_id, outpost=None, casks=None):
    """Units of item_id in the Lead Casks at outpost (None = home)."""
    casks = casks_at(outpost) if casks is None else casks
    return sum(c["count"] for c in casks if c["material"] == item_id)


def network_cask_stock(item_id):
    """Units of item_id in every Lead Cask on the network."""
    return sum(cask_stock(item_id, outpost) for outpost in _all_outposts())


def room_for(item_id, outpost=None, casks=None):
    """Free units for item_id: casks latched to it or empty, minus casks reserved for the other item."""
    casks = casks_at(outpost) if casks is None else casks
    room = 0
    for c in casks:
        if c["role"] and c["role"] != item_id:
            continue
        if c["material"] in ("", item_id):
            room += max(0, c["capacity"] - c["count"])
    return room


def unload_target(item_id, outpost=None, casks=None):
    """Id of a cask that can take item_id (its role allows it, latched to it or empty, with room), else None."""
    casks = casks_at(outpost) if casks is None else casks
    fits = [c for c in casks if c["role"] in ("", item_id) and c["material"] in ("", item_id) and c["count"] < c["capacity"]]
    fits.sort(key=lambda c: (0 if c["material"] == item_id else 1, 0 if c["role"] == item_id else 1))
    return fits[0]["id"] if fits else None


def take_from_casks(port, item_id, amount, outpost=None, casks=None):
    """Pulls up to amount of item_id into an input port (connect + take, one source at a time).
    Misfiled casks (role is the other item) first, then fullest first. Returns units moved."""
    casks = casks_at(outpost) if casks is None else casks
    holders = [c for c in casks if c["material"] == item_id and c["count"] > 0]
    holders.sort(key=lambda c: (0 if c["role"] and c["role"] != item_id else 1, -c["count"]))
    moved = 0
    for c in holders:
        if moved >= amount:
            break
        try:
            if not hasattr(port, "connected_id") or port.connected_id() != c["id"]:
                result = port.connect(c["id"])
                if getattr(result, "status", "") != "ok":
                    continue
            result = port.take(item_id, amount - moved)
        except Exception as error:
            swallowed("lead_cask.take_from_casks: port.take", error)
            continue
        got = getattr(result, "moved", 0) or 0
        c["count"] -= got
        moved += got
    return moved


def _set_role(cask_id, role, existing_ids):
    """Writes cask_id's role and drops entries of casks that no longer exist (existing_ids: every live cask id)."""
    def updater(stored):
        stored = dict(stored) if isinstance(stored, dict) else {}
        for other in list(stored.keys()):
            if other not in existing_ids:
                del stored[other]
        stored[cask_id] = role
        return stored

    archive.transaction(ROLES_KEY, {}, updater)


def _live_cask_ids():
    ids = set()
    for outpost in _all_outposts():
        try:
            for ref in outpost.buildings(LEAD_CASK_TYPE_ID) or []:
                ids.add(getattr(ref, "id", ""))
        except Exception as error:
            swallowed("lead_cask._live_cask_ids: outpost.buildings", error)
    return ids


def ensure_rod_cask(outpost, casks=None):
    """(cask_id, note): the outpost's "fuel_rod" cask, assigning one when none is set.
    Picks a cask holding rods, else an empty unassigned cask, else the least-full
    unassigned uranium cask (repair() then empties it). Needs two casks: one for
    uranium stays. Returns (None, reason) when no cask can be given the role."""
    casks = casks_at(outpost) if casks is None else casks
    for c in casks:
        if c["role"] == ROD_ITEM:
            return c["id"], None
    free = [c for c in casks if not c["role"]]
    if len(casks) < 2:
        return None, f"{len(casks)} Lead Cask(s) here; rods need their own cask besides the uranium one"
    pick = None
    for wanted in (ROD_ITEM, ""):
        pick = next((c for c in free if c["material"] == wanted), None)
        if pick:
            break
    if pick is None:
        uranium = sorted((c for c in free if c["material"] == URANIUM_ITEM), key=lambda c: c["count"])
        if uranium and len([c for c in casks if c["role"] != ROD_ITEM]) >= 2:
            pick = uranium[0]
    if pick is None:
        return None, "every Lead Cask here is reserved for uranium"
    try:
        _set_role(pick["id"], ROD_ITEM, _live_cask_ids())
    except Exception as error:
        swallowed("lead_cask.ensure_rod_cask: _set_role", error)
        return None, "archive write failed"
    pick["role"] = ROD_ITEM
    return pick["id"], f"assigned '{pick['id']}' to Fuel Rods"


def repair(outpost, casks=None):
    """Moves Raw Uranium out of "fuel_rod" casks into other casks with room. Returns units moved."""
    casks = casks_at(outpost) if casks is None else casks
    moved = 0
    for source in casks:
        if source["role"] != ROD_ITEM or source["material"] != URANIUM_ITEM or source["count"] <= 0:
            continue
        for target in casks:
            if source["count"] <= 0:
                break
            if target is source or target["role"] == ROD_ITEM or target["material"] not in ("", URANIUM_ITEM):
                continue
            room = target["capacity"] - target["count"]
            if room <= 0:
                continue
            try:
                result = source["component"].transfer_to(target["id"], URANIUM_ITEM, min(room, source["count"]))
            except Exception as error:
                swallowed("lead_cask.repair: transfer_to", error)
                continue
            got = getattr(result, "moved", 0) or 0
            source["count"] -= got
            target["count"] += got
            target["material"] = URANIUM_ITEM if target["count"] > 0 else target["material"]
            moved += got
        if source["count"] <= 0:
            source["material"] = ""
    return moved
