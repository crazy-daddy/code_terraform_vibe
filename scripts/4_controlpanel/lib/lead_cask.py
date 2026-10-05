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
#
# Inbound reservations: `lead_cask.inbound` = {carrier: {"outpost", "units",
# "tick"}}, Raw Uranium a drone has promised to unload at an outpost (claimed
# site's share, then the units aboard). reserve_inbound() grants room atomically
# against the other carriers' entries, so two drones never count on the same
# cask room. Entries older than INBOUND_STALE_TICKS are ignored and pruned.

from archive import archive
from swallow import swallowed

LEAD_CASK_TYPE_ID = "lead_cask"
URANIUM_ITEM = "raw_uranium"
ROD_ITEM = "fuel_rod"
HOT_ITEMS = (URANIUM_ITEM, ROD_ITEM)
ROLES_KEY = "lead_cask.roles"
INBOUND_KEY = "lead_cask.inbound"
# Same expiry as drone_claims.CLAIM_STALE_TICKS.
INBOUND_STALE_TICKS = 36000

# Local Fuel Rod consumers: Reactors and Mk IV terraformers (Mk IV pack burns
# rods from `input`). Their reserve is the Fuel Assembler's rod target before
# dock orders, and the floor Supply Docks leave in the casks (rods_for_orders()):
# a spare for a newly deployed Reactor, a buffer per Reactor (one rod lasts
# 72 game h at heat 1.0, one craft takes 6), one per Mk IV generator.
REACTOR_TYPE_ID = "reactor"
MK4_TYPE_IDS = ("temp_heater", "pressure_generator", "oxygen_generator")
MK4_TIER = 4
ROD_RESERVE = 1
RODS_PER_REACTOR = 2
RODS_PER_MK4 = 1

# Raw Uranium kept per outpost in its casks, on top of what Supply Dock orders
# there still owe (drone_weather.uranium_want()): 25 Fuel Rod crafts, about a
# week of rods for 3 Reactors at full heat. Drones collect no more past it.
URANIUM_STOCK_TARGET = 100

# Reactor fuel state (written by lib/reactor.py, read by the Status
# panel): {reactor_id: {"outpost", "status", "spare", "hours", "alert", "level",
# "tick"}}. `spare` = rods staged + in the outpost's casks, `hours` = game hours
# of fuel left at the current heat, `alert` = "" when fine.
REACTOR_FUEL_KEY = "reactor.fuel"
REACTOR_FUEL_FRESH_TICKS = 1800


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


def casks_at(outpost: "OutpostRef | None"):
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


def cask_stock(item_id, outpost: "OutpostRef | None" = None, casks=None):
    """Units of item_id in the Lead Casks at outpost (None = home)."""
    casks = casks_at(outpost) if casks is None else casks
    return sum(c["count"] for c in casks if c["material"] == item_id)


def _components_at(outpost: "OutpostRef | None", type_id):
    if outpost is None or not hasattr(outpost, "buildings"):
        return []
    try:
        refs = outpost.buildings(type_id)
    except Exception as error:
        swallowed("lead_cask._components_at: outpost.buildings", error)
        return []
    out = []
    for ref in refs or []:
        component = get_component(getattr(ref, "id", ""))
        if component is not None:
            out.append(component)
    return out


def rod_consumers(outpost: "OutpostRef | None"):
    """(reactors, mk4 generators) components at outpost."""
    mk4 = []
    for type_id in MK4_TYPE_IDS:
        for machine in _components_at(outpost, type_id):
            try:
                if int(machine.tier()) >= MK4_TIER:
                    mk4.append(machine)
            except Exception as error:
                swallowed("lead_cask.rod_consumers: tier", error)
    return _components_at(outpost, REACTOR_TYPE_ID), mk4


def staged_rods(machines):
    """Fuel Rods waiting in the machines' input slots."""
    total = 0
    for machine in machines:
        port = getattr(machine, "input", None)
        if port is None or not hasattr(port, "count"):
            continue
        try:
            total += int(port.count())
        except Exception as error:
            swallowed("lead_cask.staged_rods: input.count", error)
    return total


def consumer_rod_reserve(reactors, mk4):
    """Fuel Rods kept at an outpost for its own Reactors and Mk IV generators."""
    return ROD_RESERVE + RODS_PER_REACTOR * len(reactors) + RODS_PER_MK4 * len(mk4)


def rods_for_orders(outpost: "OutpostRef | None", casks=None):
    """(rods a Supply Dock may take from outpost's casks, rods held back): cask
    rods above the local consumers' reserve, less the rods already staged in them.
    None = home."""
    if outpost is None:
        outpost = home_outpost()
    casks = casks_at(outpost) if casks is None else casks
    held = _rods_to_hold(outpost)
    stock = cask_stock(ROD_ITEM, casks=casks)
    return max(0, stock - held), min(stock, held)


def _rods_to_hold(outpost: "OutpostRef | None"):
    """Rods the local consumers' reserve still wants beyond what they have staged."""
    reactors, mk4 = rod_consumers(outpost)
    return max(0, consumer_rod_reserve(reactors, mk4) - staged_rods(reactors + mk4))


def rods_free_to_ship(outpost: "OutpostRef | None", in_hand, casks=None):
    """Of `in_hand` fresh Fuel Rods (a Fuel Assembler's output), how many may go
    straight to a Supply Dock: cask rods + in_hand beyond the local consumers'
    reserve (the same floor rods_for_orders() leaves the docks). None = home."""
    if outpost is None:
        outpost = home_outpost()
    casks = casks_at(outpost) if casks is None else casks
    return max(0, min(in_hand, cask_stock(ROD_ITEM, casks=casks) + in_hand - _rods_to_hold(outpost)))


def reactor_fuel_alerts(tick, entries=None):
    """[(text, level)] from `reactor.fuel` (REACTOR_FUEL_KEY), "error" first; entries
    older than REACTOR_FUEL_FRESH_TICKS are left out (their Reactor script stopped)."""
    entries = archive.get(REACTOR_FUEL_KEY, {}) if entries is None else entries
    if not isinstance(entries, dict):
        return []
    out = []
    for reactor_id in sorted(entries):
        e = entries[reactor_id]
        if not isinstance(e, dict) or not e.get("alert") or not 0 <= tick - e.get("tick", 0) < REACTOR_FUEL_FRESH_TICKS:
            continue
        out.append((f"{reactor_id}: {e['alert']}", e.get("level", "warn")))
    out.sort(key=lambda a: 0 if a[1] == "error" else 1)
    return out


def network_cask_stock(item_id):
    """Units of item_id in every Lead Cask on the network."""
    return sum(cask_stock(item_id, outpost) for outpost in _all_outposts())


def room_for(item_id, outpost: "OutpostRef | None" = None, casks=None):
    """Free units for item_id: casks latched to it or empty, minus casks reserved for the other item."""
    casks = casks_at(outpost) if casks is None else casks
    room = 0
    for c in casks:
        if c["role"] and c["role"] != item_id:
            continue
        if c["material"] in ("", item_id):
            room += max(0, c["capacity"] - c["count"])
    return room


def _live_inbound(entries, tick):
    """{carrier: entry} of well-formed, non-stale inbound reservations."""
    if not isinstance(entries, dict):
        return {}
    return {carrier: e for carrier, e in entries.items()
            if isinstance(e, dict) and tick - e.get("tick", 0) < INBOUND_STALE_TICKS}


def inbound_units(outpost_id, tick, exclude=None):
    """Raw Uranium other carriers (all but exclude) have reserved at outpost_id."""
    live = _live_inbound(archive.get(INBOUND_KEY, {}), tick)
    return sum(int(e.get("units", 0)) for carrier, e in live.items() if carrier != exclude and e.get("outpost") == outpost_id)


def reserve_inbound(carrier, outpost_id, room, wanted, tick):
    """Reserves up to wanted units of room at outpost_id for carrier, net of the other carriers'
    reservations; prunes stale entries. Returns the units granted (0 = nothing reserved)."""
    granted = [0]

    def updater(entries):
        live = _live_inbound(entries, tick)
        others = sum(int(e.get("units", 0)) for c, e in live.items() if c != carrier and e.get("outpost") == outpost_id)
        granted[0] = max(0, min(wanted, room - others))
        if granted[0] > 0:
            live[carrier] = {"outpost": outpost_id, "units": granted[0], "tick": tick}
        else:
            live.pop(carrier, None)
        return live

    if not archive.transaction(INBOUND_KEY, {}, updater):
        return 0
    return granted[0]


def set_inbound(carrier, outpost_id, units, tick):
    """Sets carrier's reservation to units already aboard (no room check: they are committed)."""
    def updater(entries):
        live = _live_inbound(entries, tick)
        live[carrier] = {"outpost": outpost_id, "units": units, "tick": tick}
        return live

    archive.transaction(INBOUND_KEY, {}, updater)


def release_inbound(carrier):
    """Drops carrier's reservation. Plain read first: most calls find none."""
    entries = archive.get(INBOUND_KEY, {})
    if not isinstance(entries, dict) or carrier not in entries:
        return

    def updater(stored):
        stored = dict(stored) if isinstance(stored, dict) else {}
        stored.pop(carrier, None)
        return stored

    archive.transaction(INBOUND_KEY, {}, updater)


def unload_target(item_id, outpost: "OutpostRef | None" = None, casks=None):
    """Id of a cask that can take item_id (its role allows it, latched to it or empty, with room), else None."""
    casks = casks_at(outpost) if casks is None else casks
    fits = [c for c in casks if c["role"] in ("", item_id) and c["material"] in ("", item_id) and c["count"] < c["capacity"]]
    fits.sort(key=lambda c: (0 if c["material"] == item_id else 1, 0 if c["role"] == item_id else 1))
    return fits[0]["id"] if fits else None


def take_from_casks(port: "InputSlot | VehicleInputSlot", item_id, amount, outpost: "OutpostRef | None" = None, casks=None):
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


def ensure_rod_cask(outpost: "OutpostRef", casks=None):
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


def repair(outpost: "OutpostRef", casks=None):
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
