# Fluid pass of the infrastructure planner (autoplay/infra_planner_automation.py): one
# pipe network per fluid, joining that fluid's producers to the outposts whose
# role needs it (autoplay_roles).
#
# Pipes carry no fluid of their own: plan_pipe() keeps only the medium, and a
# network's contents come from the connect() relationships routed through it.
# Between two locations the game splits the fluids over the components that
# reach both; one more fluid than components there is a conflict. So a
# network may touch only the footprints of its own fluid's terminals:
#   - other networks of the same medium (any other label, FOREIGN included)
#     are walls, crossed only by a bridge,
#   - the footprints of every other outpost and field structure are walls.
# Gas and liquid ignore each other; power is not involved.
#
# Terminals of a fluid: field structures producing it (water/oil pumps,
# thermal caps, exotic caps/taps by their deposit's fluid()), outposts whose
# roles make it ("out": condenser water, Refiner outputs) and outposts whose
# roles take it ("in"). A fluid nobody makes is skipped. A terminal is connected when a footprint tile already
# carries the fluid. Each pass routes at most MAX_ROUTES_PER_PASS routes, A*
# from every tile carrying the fluid (reused for free) to the free footprint
# tiles of the unconnected terminals; a route ends on the first footprint tile
# it reaches, so it takes one port. With no network yet, the first producer
# with a free port is the source and only consumer outposts are goals.
# An outpost keeps its last free ports for the earlier fluids of its role
# preset order that still need one (reserved); a footprint with no free tile
# left is full for that medium (autoplay.port_status).
#
# Storage buffer: a storage outpost (designated
# autoplay_roles.STORAGE_BUFFER_ROLES) takes many fluids, and every one needs
# its own lane in. The tiles within STORAGE_BUFFER_TILES of its footprint (storage_buffer_tiles(), minus every
# structure footprint) are walls for a fluid that outpost does not take, and
# soft tiles (SOFT_TILE_COST) for one it takes, so a through-route of its own
# fluid stays short. When a wall buffer leaves no route (a producer standing
# inside it), the route is searched again without the buffer.
#
# Urgency (supply_tiers): a field producer whose connection is plan-ahead
# (far from every consumer of its fluid while a nearer one supplies it) is
# left out of the normal routes. Only when no normal route is open, the power
# pass is idle and no plan-ahead pipe job of ours is open, the pass routes one
# plan-ahead producer at supply_tiers.PLAN_AHEAD_PRIO, cut to
# PLAN_AHEAD_MAX_PIECES pieces per pass (the next pass continues from the
# stub), with the segments and bridges in stock plus a reserve.

from archive import archive
from atomic import run_atomic, run_batched, run_chunked
from swallow import swallowed
from grid_geom import outpost_tiles, outpost_box, buffer_box, tile_key, extractor_tiles, route_init, route_seed, route_step, route_path, path_plan, run_pieces, truncate_steps, SEED_CHUNK
from infra_topology import fluid_medium, footprint_ports, outpost_positions, home_outpost_id, surveyed_sites
from blueprint_queue import stock, queue_pipe_route, open_planned
from construction_plan import DEFAULT_PRIORITY
from drill_sites import known_positions
import autoplay_roles
import supply_tiers
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

PORT_STATUS_KEY = "autoplay.port_status"
MAX_ROUTES_PER_PASS = 1   # fluid routes queued per pass
LABEL_CHUNK = 200         # occupancy tiles per atomic label_slice() (~3,400 operations worst, tests/test_autoplay_fluid.py)
FLUID_ORDER = ("water", "oil", "steam")   # routing order; other fluids follow by name
PLAN_AHEAD_BRIDGE_RESERVE = 2   # bridges left in stock after a plan-ahead route

# Site kind -> fluid its extractor produces ("exotic" reads the deposit's fluid()).
_SITE_FLUIDS = {"water": "water", "oil": "oil", "thermal": "steam"}
_SITE_MACHINE_GETTERS = {"water": "pump_id", "oil": "pump_id", "thermal": "cap_id", "exotic": "cap_id"}


def site_rows(sites):
    """[{"name": machine id, "fluid": fluid | None, "tiles": footprint}] of every extractor standing on a surveyed site."""
    rows = []
    for site in sites:
        try:
            kind = site.kind()
            getter = _SITE_MACHINE_GETTERS.get(kind)
            if getter is None:
                continue
            machine_id = getattr(site, getter)()
            if not machine_id:
                continue
            fluid = site.fluid() if kind == "exotic" else _SITE_FLUIDS.get(kind)
            rows.append({"name": machine_id, "fluid": fluid, "tiles": extractor_tiles(float(site.x), float(site.y))})
        except Exception as error:
            swallowed("fluid_plan.site_rows: site read", error)
    return rows


def fluid_order(fluids):
    """Routing order: FLUID_ORDER first, then the rest by name."""
    return sorted(set(fluids), key=lambda f: (FLUID_ORDER.index(f) if f in FLUID_ORDER else len(FLUID_ORDER), f))


def terminals(fluid, producers, outpost_xy, demand):
    """
    [{"name", "producer": bool, "tiles"}] of one fluid: field producers by
    name, then producing outposts, then consuming outposts, each by id. An
    outpost that makes and takes the fluid is listed once, as a producer.
    """
    out = [{"name": row["name"], "producer": True, "tiles": row["tiles"]}
           for row in sorted(producers, key=lambda r: r["name"]) if row["fluid"] == fluid]
    placed = [outpost_id for outpost_id in sorted(demand) if outpost_id in outpost_xy]
    makers = [outpost_id for outpost_id in placed if fluid in demand[outpost_id]["out"]]
    takers = [outpost_id for outpost_id in placed if fluid in demand[outpost_id]["in"] and outpost_id not in makers]
    out.extend([{"name": outpost_id, "producer": True, "tiles": outpost_tiles(*outpost_xy[outpost_id])} for outpost_id in makers])
    out.extend([{"name": outpost_id, "producer": False, "tiles": outpost_tiles(*outpost_xy[outpost_id])} for outpost_id in takers])
    return out


def label_slice(items, fluid):
    """(walls, held) tile lists of a slice of (tile, label) occupancy items for `fluid` (atomic-safe)."""
    return [([tile for tile, label in items if label != fluid], [tile for tile, label in items if label == fluid])]


def split_labels(layer_occ, fluid):
    """(walls, held) tile sets of a whole layer, in atomic LABEL_CHUNK slices."""
    walls = set()
    held = set()
    for part_walls, part_held in run_batched(label_slice, list(layer_occ.items()), LABEL_CHUNK, fluid):
        walls.update(part_walls)
        held.update(part_held)
    return (walls, held)


def reserved_for(outpost_fluids, fluid, free_count, layer_occ, tiles, routable):
    """Earlier same-medium fluids of the outpost's list that still need a port; True when they claim every free tile left."""
    medium = fluid_medium(fluid)
    waiting = 0
    for other in outpost_fluids:
        if other == fluid:
            break
        if other in routable and fluid_medium(other) == medium and not any(layer_occ.get(t) == other for t in tiles):
            waiting += 1
    return waiting > 0 and free_count <= waiting


def route_request(fluid, terms, layer_occ, held, demand, routable, failed, deferred=()):
    """
    What one route for `fluid` should connect: {"sources", "goals" {tile: terminal name},
    "start" (terminal used as source when no network exists, else None),
    "connected", "full", "reserved", "failed", "deferred"} (lists of terminal names).
    deferred = names of terminals left out of this route (plan-ahead producers).
    No goals: nothing to route for this fluid now.
    """
    out = {"sources": [], "goals": {}, "start": None, "connected": [], "full": [], "reserved": [], "failed": [], "deferred": []}
    open_terms = []
    for term in terms:
        ports = footprint_ports(term["tiles"], layer_occ, fluid)
        if ports["held"]:
            out["connected"].append(term["name"])
        elif term["name"] in deferred:
            out["deferred"].append(term["name"])
        elif (fluid, term["name"]) in failed:
            out["failed"].append(term["name"])
        elif not ports["free"]:
            out["full"].append(term["name"])
        elif term["name"] in demand and reserved_for(demand[term["name"]]["order"], fluid, len(ports["free"]), layer_occ, term["tiles"], routable):
            out["reserved"].append(term["name"])
        else:
            open_terms.append((term, ports["free"]))
    if not open_terms:
        return out
    if out["connected"]:
        out["sources"] = sorted(held)
        goal_terms = open_terms
    else:
        starts = [(term, free) for term, free in open_terms if term["producer"]]
        if not starts:
            return out
        out["start"] = starts[0][0]["name"]
        out["sources"] = starts[0][1]
        goal_terms = [(term, free) for term, free in open_terms if not term["producer"]]
    for term, free in goal_terms:
        for tile in free:
            out["goals"].setdefault(tile, term["name"])
    return out


def foreign_footprints(structures, terms):
    """Tiles of every structure footprint ({name: tiles}) that is not one of the fluid's terminals."""
    own = {term["name"] for term in terms}
    own_tiles = {tile for term in terms for tile in term["tiles"]}
    return {tile for name, tiles in structures.items() if name not in own for tile in tiles if tile not in own_tiles}


def storage_buffer_tiles(x, y, width=autoplay_roles.STORAGE_BUFFER_TILES):
    """Tiles within `width` tiles of the outpost footprint anchored at (x, y), the footprint left out."""
    box = outpost_box(x, y)
    tx0, ty0, tx1, ty1 = buffer_box(box, width)
    return {tile_key(tx, ty) for tx in range(tx0, tx1 + 1) for ty in range(ty0, ty1 + 1)
            if not (box[0] <= tx <= box[2] and box[1] <= ty <= box[3])}


def storage_buffers(outpost_xy, roles_map):
    """{outpost_id: buffer tiles} of the live outposts whose designation keeps a buffer (autoplay_roles.keeps_buffer())."""
    out = {}
    for outpost_id, roles in roles_map.items():
        if outpost_id in outpost_xy and autoplay_roles.keeps_buffer(roles):
            out[outpost_id] = storage_buffer_tiles(*outpost_xy[outpost_id])
    return out


def buffer_split(buffers, terms, structures):
    """(wall tiles, soft tiles) of the storage buffers for one fluid: soft around a terminal of it, wall elsewhere; footprints left out."""
    own = {term["name"] for term in terms}
    footprints = {tile for tiles in structures.values() for tile in tiles}
    wall, soft = set(), set()
    for outpost_id, tiles in buffers.items():
        (soft if outpost_id in own else wall).update(tiles)
    return (wall - soft - footprints, soft - footprints)


def find_route(request, walls, foreign, soft=None):
    """route_path() for a route_request(): atomic seed slices and router steps."""
    state = run_atomic(route_init, (), list(request["goals"]), walls | foreign, walls, soft)
    run_batched(route_seed, request["sources"], SEED_CHUNK, state)
    run_chunked(route_step, state)
    return route_path(state)


def port_status(demand, outpost_xy, occ):
    """{outpost_id: {"gas": [labels], "liquid": [labels], "full": [media]}} of the consumer outposts' footprints."""
    out = {}
    for outpost_id in sorted(demand):
        if outpost_id not in outpost_xy:
            continue
        tiles = outpost_tiles(*outpost_xy[outpost_id])
        entry = {"gas": [], "liquid": [], "full": []}
        for medium in ("gas", "liquid"):
            layer = occ.get(medium, {})
            labels = sorted({layer[t] for t in tiles if t in layer})
            entry[medium] = labels
            if all(t in layer for t in tiles):
                entry["full"].append(medium)
        out[outpost_id] = entry
    return out


def route_cost(steps):
    """(pipe pieces, bridges) a route's build steps need at most (existing pieces are reused, so fewer jobs may result)."""
    pieces = sum([run_pieces(step[1], step[2]) for step in steps if step[0] == "run"])
    bridges = len([1 for step in steps if step[0] == "bridge"])
    return (pieces, bridges)


def _structures(outpost_xy, producers, ghosts=()):
    """{name: footprint tiles} of every outpost, extractor on a site, known drill and extractor ghost (structure rows)."""
    out = {outpost_id: outpost_tiles(x, y) for outpost_id, (x, y) in outpost_xy.items()}
    for row in ghosts:
        out["ghost:" + row["id"]] = extractor_tiles(row["x"], row["y"])
    for row in producers:
        out[row["name"]] = row["tiles"]
    for drill_id, entry in known_positions().items():
        pos = entry.get("pos") if isinstance(entry, dict) else None
        if pos is not None and isinstance(pos, (list, tuple)) and len(pos) == 2:
            out[drill_id] = extractor_tiles(float(pos[0]), float(pos[1]))
    return out


class FluidPlanner:
    """One fluid pass per planner tick; see the module header."""

    def __init__(self, log: "TreeConsole"):
        self.log = log
        self.failed = set()   # (fluid, terminal name) the game rejected or no route reached this run; retried after restart
        self.buffers = {}     # storage_buffers() of the current pass

    def run_pass(self, topo, power_idle=True):
        """
        "queued" (a route was planned), "ahead" (a plan-ahead route chunk was
        planned), "waiting" (blocked by stock, or a plan-ahead pipe job of ours
        still open), "done" (nothing to route) or "error" (outposts unreadable).
        power_idle: the power pass has nothing urgent left (plan-ahead allowed).
        """
        outpost_xy = outpost_positions()
        if outpost_xy is None:
            self.log.debug("Fluid: outpost_network unreadable; pass skipped.")
            return "error"
        dropped = autoplay_roles.prune_roles(set(outpost_xy))
        demand = autoplay_roles.demand(sorted(outpost_xy), autoplay_roles.outpost_roles(), autoplay_roles.presets(), home_outpost_id())
        if dropped:
            self.log.debug(f"Fluid: {dropped} role entr(ies) of gone outposts pruned.")
        if not demand:
            self.log.debug(f"Fluid: no outpost has a fluid role ({autoplay_roles.ROLES_KEY}); nothing to route.")
            return "done"
        self._write_port_status(port_status(demand, outpost_xy, topo.occ))
        sites = surveyed_sites()
        producers = site_rows(sites)
        urgent = supply_tiers.urgent_producers(supply_tiers.fluid_sites(sites), demand, outpost_xy)
        deferred = {row["name"] for row in producers if row["name"] not in urgent}
        routable = {row["fluid"] for row in producers if row["fluid"]} | {f for entry in demand.values() for f in entry["out"]}
        structures = _structures(outpost_xy, producers, topo.structure_rows)
        self.buffers = storage_buffers(outpost_xy, autoplay_roles.outpost_roles())
        fluids = []
        for fluid in fluid_order([f for entry in demand.values() for f in entry["in"]]):
            if fluid in routable:
                fluids.append(fluid)
            else:
                self.log.debug(f"Fluid {fluid}: no producer (field structure or outpost role \"out\"); skipped.")
        queued = 0
        waiting = False
        ahead_open = False
        for fluid in fluids:
            if queued >= MAX_ROUTES_PER_PASS:
                break
            outcome = self._fluid(fluid, topo, demand, routable, producers, outpost_xy, structures, deferred)
            if outcome == "queued":
                queued += 1
            elif outcome == "waiting":
                waiting = True
            elif outcome == "deferred":
                ahead_open = True
        if queued:
            return "queued"
        if waiting:
            return "waiting"
        if not ahead_open:
            return "done"
        return self._plan_ahead(fluids, topo, demand, routable, producers, outpost_xy, structures, power_idle)

    def _plan_ahead(self, fluids, topo, demand, routable, producers, outpost_xy, structures, power_idle):
        """One plan-ahead route chunk when nothing urgent is open; returns "ahead", "waiting" or "done"."""
        if open_planned(("pipe", "bridge"), supply_tiers.PLAN_AHEAD_PRIO):
            self.log.debug("Fluid: a plan-ahead pipe job of ours is still open; the next chunk waits.")
            return "waiting"
        if not power_idle:
            self.log.debug("Fluid: plan-ahead routes wait for the power pass.")
            return "done"
        for fluid in fluids:
            if self._fluid(fluid, topo, demand, routable, producers, outpost_xy, structures, (), True) == "queued":
                return "ahead"
        return "done"

    def _fluid(self, fluid, topo, demand, routable, producers, outpost_xy, structures, deferred, ahead=False):
        """
        Routes one fluid's next connection; returns "queued", "waiting",
        "deferred" (only plan-ahead producers left) or "done". ahead: also
        route the producers the normal pass leaves out (deferred is then empty).
        """
        medium = fluid_medium(fluid)
        layer_occ = topo.occ.get(medium, {})
        terms = terminals(fluid, producers, outpost_xy, demand)
        walls, held = split_labels(layer_occ, fluid)
        request = route_request(fluid, terms, layer_occ, held, demand, routable, self.failed, deferred)
        notes = [f"{key} {', '.join(request[key])}" for key in ("full", "reserved", "failed", "deferred") if request[key]]
        mode = " (plan-ahead)" if ahead else ""
        self.log.debug(f"Fluid {fluid}{mode}: {len(request['connected'])}/{len(terms)} terminal(s) connected, "
                       f"{len(set(request['goals'].values()))} to route{'; ' + '; '.join(notes) if notes else ''}.")
        if not request["goals"]:
            return "deferred" if request["deferred"] and request["connected"] else "done"
        self.log.start(f"Fluid {fluid}: routing to {len(set(request['goals'].values()))} terminal(s){mode}")
        outcome = self._route(fluid, medium, request, walls, held, structures, terms, ahead)
        self.log.end(outcome)
        if outcome.startswith("queued"):
            return "queued"
        return "waiting" if outcome.startswith("waiting") else "done"

    def _route(self, fluid, medium, request, walls, held, structures, terms, ahead=False):
        """Searches and queues one route (a plan-ahead one cut to PLAN_AHEAD_MAX_PIECES); returns the block's outcome line."""
        foreign = foreign_footprints(structures, terms)
        buffer_wall, buffer_soft = buffer_split(self.buffers, terms, structures)
        path = find_route(request, walls, foreign | buffer_wall, buffer_soft)
        if not path and buffer_wall:
            self.log.debug(f"Fluid {fluid}: no route around the storage buffer; searching through it.")
            path = find_route(request, walls, foreign, buffer_soft)
        if not path:
            names = sorted(set(request["goals"].values()))
            for name in names:
                self.failed.add((fluid, name))
            self.log.level("warn").print(f"Fluid {fluid}: no route to {', '.join(names)} (walls: other networks and footprints).")
            return "no route"
        target = request["goals"][path[-1][0]]
        origin = request["start"] or "network"
        steps = path_plan(path)
        truncated = False
        prio = DEFAULT_PRIORITY
        if ahead:
            steps, truncated = truncate_steps(steps, supply_tiers.PLAN_AHEAD_MAX_PIECES)
            prio = supply_tiers.PLAN_AHEAD_PRIO
        pieces, bridges = route_cost(steps)
        segment_item = f"{medium}_pipe_segment"
        bridge_item = f"{medium}_pipe_bridge"
        have_segments = stock(segment_item)
        have_bridges = stock(bridge_item) if bridges else 0
        need_segments = pieces + (supply_tiers.PLAN_AHEAD_RESERVE if ahead else 0)
        need_bridges = bridges + (PLAN_AHEAD_BRIDGE_RESERVE if ahead and bridges else 0)
        self.log.debug(f"{origin} -> {target}: {len(path) - 1} tiles, {len(steps)} step(s){' (chunk)' if truncated else ''}, "
                       f"{pieces} piece(s), {bridges} bridge(s).")
        if need_segments > have_segments or need_bridges > have_bridges:
            return f"waiting for {segment_item} {have_segments}/{need_segments}, {bridge_item} {have_bridges}/{need_bridges}"
        status, ids, message = queue_pipe_route(fluid, steps, prio, held)
        if status != "ok":
            self.failed.add((fluid, target))
            self.log.level("warn").print(f"Fluid {fluid} route {origin} -> {target} rejected: {status} {message}")
            return f"rejected ({status})"
        chunk = f" (plan-ahead{' chunk' if truncated else ''}, prio {prio})" if ahead else ""
        self.log.print(f"Fluid {fluid}: {origin} -> {target}{chunk}, {pieces} piece(s), {bridges} bridge(s), {len(ids)} job(s) queued.")
        return f"queued {origin} -> {target}"

    def _write_port_status(self, status):
        """Stores autoplay.port_status when it changed."""
        if archive.get(PORT_STATUS_KEY, None) == status:
            return
        try:
            archive.set(PORT_STATUS_KEY, status)
        except Exception as error:
            swallowed("fluid_plan.FluidPlanner._write_port_status: archive.set", error)
