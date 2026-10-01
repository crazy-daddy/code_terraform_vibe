# Occupancy of the map's utility layers for the infrastructure planner: which
# tile carries which network, per layer ("gas", "liquid", "power").
#
# Sources, read once per planner pass:
#   - list_pipes(): completed and partly built pipe pieces (one TILE_M piece
#     each), with the exact fluid of their physical component (contents()).
#   - construction_blueprint pending/active/paused jobs: ghosts of pipes,
#     power lines and bridges.
#   - autoplay.networks (archive): the routes the planner laid per fluid, so a
#     ghost or a not-yet-connected piece of ours is known before contents()
#     latches.
# Power-line pieces have no list API: completed lines are only visible as
# subnets through power_control.grids(); power-line ghosts come from the jobs.
#
# Labels: a fluid id, POWER for power pieces, or FOREIGN ("?") for a piece of
# unknown identity (no contents, not ours) or a tile two identities claim.
# The router treats every other label on the same layer as a wall.
#
# The pipe read is the planner's heaviest step (every piece is several game
# calls), so it runs in PIPE_CHUNK slices through lib/atomic.py run_batched().

from archive import archive
from atomic import run_batched
from swallow import swallowed
from grid_geom import piece_tiles, job_tiles, tile_at, run_tiles

NETWORKS_KEY = "autoplay.networks"

FOREIGN = "?"
POWER = "power"
LAYERS = ("gas", "liquid", "power")

# Gas fluids (docs/database/fluids.md "Type: Gas"); every other fluid is a liquid.
GAS_FLUIDS = ("steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine")

PIPE_CHUNK = 16   # pipes per atomic read slice (worst ~190 operations each, see tests)
JOB_CHUNK = 20    # construction jobs per atomic read slice (worst ~165 operations each)

_JOB_GETTERS = ("pending_constructions", "active_constructions", "paused_constructions")


def fluid_medium(fluid):
    """Pipe medium ("gas" / "liquid") that carries `fluid`."""
    return "gas" if fluid in GAS_FLUIDS else "liquid"


def _xy(pos):
    if pos is None:
        return None
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    if x is None or y is None:
        return None
    return (float(x), float(y))


def read_pipe_slice(pipes):
    """Plain rows {medium, tiles, contents, complete, conflict, id} for a slice of Pipe objects (atomic-safe: reads only)."""
    rows = []
    for pipe in pipes:
        start = _xy(pipe.start())
        end = _xy(pipe.end())
        if start is None or end is None:
            continue
        rows.append({
            "id": pipe.id,
            "medium": pipe.type(),
            "tiles": piece_tiles(start[0], start[1], end[0], end[1]),
            "contents": pipe.contents(),
            "complete": pipe.is_complete(),
            "conflict": bool(pipe.conflicting_contents()),
        })
    return rows


def _job_medium(job):
    medium = getattr(job, "medium", None)
    if medium in LAYERS:
        return medium
    kind = str(getattr(job, "kind", "") or "")
    if kind.startswith("power"):
        return "power"
    if kind.startswith("gas"):
        return "gas"
    if kind.startswith("liquid"):
        return "liquid"
    return None


def read_job_slice(jobs):
    """Plain rows {id, kind, medium, tiles} for the utility jobs (pipes, lines, bridges) of a slice of Construction objects."""
    rows = []
    for job in jobs:
        medium = _job_medium(job)
        pos = _xy(getattr(job, "position", None))
        if medium is None or pos is None:
            continue
        kind = str(getattr(job, "kind", "") or "")
        rows.append({"id": job.id, "kind": kind, "medium": medium, "tiles": job_tiles(pos[0], pos[1])})
    return rows


def planned_labels(networks):
    """{medium: {tile: fluid}} from autoplay.networks {fluid: [[x1, y1, x2, y2], ...]} (straight runs, tile centres)."""
    labels = {"gas": {}, "liquid": {}}
    for fluid, runs in (networks or {}).items():
        layer = labels[fluid_medium(fluid)]
        for run in runs or []:
            if not isinstance(run, (list, tuple)) or len(run) != 4:
                continue
            for tile in run_tiles(tile_at(run[0], run[1]), tile_at(run[2], run[3])):
                layer[tile] = fluid
    return labels


def _claim(layer, tile, label):
    held = layer.get(tile)
    if held is None or held == label:
        layer[tile] = label
    else:
        layer[tile] = FOREIGN


def build_occupancy(pipe_rows, job_rows, labels):
    """
    {layer: {tile: label}} from read_pipe_slice()/read_job_slice() rows and
    planned_labels(). A piece's label: its contents(); else the planner's own
    fluid for that tile; else FOREIGN. Conflicted pieces are FOREIGN.
    """
    occ = {layer: {} for layer in LAYERS}
    for row in pipe_rows:
        medium = row["medium"]
        layer = occ.get(medium)
        if layer is None:
            continue
        own = labels.get(medium, {})
        for tile in row["tiles"]:
            if row["conflict"]:
                label = FOREIGN
            else:
                label = row["contents"] or own.get(tile) or FOREIGN
            _claim(layer, tile, label)
    for row in job_rows:
        medium = row["medium"]
        layer = occ[medium]
        if medium == "power":
            for tile in row["tiles"]:
                layer[tile] = POWER
            continue
        # A ghost bridge has no axis on its job, so only its centre tile is claimed.
        own = labels.get(medium, {})
        for tile in row["tiles"]:
            _claim(layer, tile, own.get(tile) or FOREIGN)
    return occ


def walls(layer_occ, fluid):
    """Tiles a route for `fluid` may not enter on this layer: every tile held by another label."""
    return {tile for tile, label in layer_occ.items() if label != fluid}


def held(layer_occ, fluid):
    """Tiles already carrying `fluid` on this layer (free for the router to reuse)."""
    return {tile for tile, label in layer_occ.items() if label == fluid}


def footprint_ports(footprint, layer_occ, fluid):
    """
    How a footprint's tiles stand for a `fluid` network on its medium layer:
      held:   tiles already carrying `fluid` (the network already reaches the site),
      free:   empty tiles a new route may end on without touching another network,
      others: {label: [tiles]} held by other networks.
    The footprint is full for this medium when `held` and `free` are both empty.
    """
    out = {"held": [], "free": [], "others": {}}
    for tile in footprint:
        label = layer_occ.get(tile)
        if label is None:
            out["free"].append(tile)
        elif label == fluid:
            out["held"].append(tile)
        else:
            out["others"].setdefault(label, []).append(tile)
    return out


def summary(occ):
    """{layer: {label: tile count}} for one summary log line."""
    out = {}
    for layer, tiles in occ.items():
        counts = {}
        for label in tiles.values():
            counts[label] = counts.get(label, 0) + 1
        out[layer] = counts
    return out


class Topology:
    """One pass's occupancy read from the game (pipes, jobs, autoplay.networks)."""

    def __init__(self):
        self.pipe_rows = []
        self.job_rows = []
        self.occ = {layer: {} for layer in LAYERS}

    def read(self):
        """Reads the game state; returns self. Missing APIs leave the matching rows empty."""
        try:
            pipes = list_pipes() or []  # type: ignore[name-defined]  # game builtin
        except Exception as error:
            swallowed("infra_topology.Topology.read: list_pipes", error)
            pipes = []
        self.pipe_rows = run_batched(read_pipe_slice, pipes, PIPE_CHUNK)
        jobs = []
        blueprints = get_component("construction_blueprint")
        if blueprints is not None:
            for getter in _JOB_GETTERS:
                try:
                    jobs.extend(getattr(blueprints, getter)() or [])
                except Exception as error:
                    swallowed(f"infra_topology.Topology.read: {getter}", error)
        self.job_rows = run_batched(read_job_slice, jobs, JOB_CHUNK)
        networks = archive.get(NETWORKS_KEY, {})
        labels = planned_labels(networks if isinstance(networks, dict) else {})
        self.occ = build_occupancy(self.pipe_rows, self.job_rows, labels)
        return self
