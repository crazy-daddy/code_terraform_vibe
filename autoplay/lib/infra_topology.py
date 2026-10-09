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
from components import home_outpost_id
from grid_geom import piece_tiles, job_tiles, tile_at, run_tiles
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_console import TreeConsole

NETWORKS_KEY = "autoplay.networks"

FOREIGN = "?"
POWER = "power"
LAYERS = ("gas", "liquid", "power")

# Gas fluids (docs/database/fluids.md "Type: Gas"); every other fluid is a liquid.
GAS_FLUIDS = ("steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine")

PIPE_CHUNK = 16   # pipes per atomic read slice (worst ~190 operations each, see tests)
PIPE_PROGRESS_EVERY = 500   # pipes between progress lines (debug) while reading
ID_CHUNK = 200              # pipes per atomic id-check slice (new_pipe_slice())
FULL_REFRESH_PASSES = 30    # passes between full pipe re-reads (catches contents() changes of existing pipes)
JOB_CHUNK = 20    # construction jobs per atomic read slice (worst ~165 operations each)

_JOB_GETTERS = ("pending_constructions", "active_constructions", "paused_constructions")

# Construction kinds of field extractors (point structures on a surveyed site).
EXTRACTOR_KINDS = ("thermal_cap", "water_pump", "oil_pump", "exotic_gas_cap", "exotic_spring_tap",
                   "mining_drill", "mining_drill_industrial", "mining_drill_heavy")


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


def read_structure_slice(jobs):
    """Plain rows {id, kind, x, y} for the extractor jobs of a slice of Construction objects (position = the site)."""
    rows = []
    for job in jobs:
        kind = str(getattr(job, "kind", "") or "")
        if kind not in EXTRACTOR_KINDS:
            continue
        pos = _xy(getattr(job, "position", None))
        if pos is not None:
            rows.append({"id": job.id, "kind": kind, "x": pos[0], "y": pos[1]})
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


def pipe_occupancy(pipe_rows, labels):
    """
    {layer: {tile: label}} from read_pipe_slice() rows and planned_labels().
    A piece's label: its contents(); else the planner's own fluid for that
    tile; else FOREIGN. Conflicted pieces are FOREIGN.
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
    return occ


def overlay_jobs(pipe_occ, job_rows, labels):
    """A copy of pipe_occupancy() with the job ghosts (read_job_slice() rows) claimed on top."""
    occ = {layer: dict(tiles) for layer, tiles in pipe_occ.items()}
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


def build_occupancy(pipe_rows, job_rows, labels):
    """{layer: {tile: label}} from pipe rows, job rows and planned_labels() (pipe_occupancy() + overlay_jobs())."""
    return overlay_jobs(pipe_occupancy(pipe_rows, labels), job_rows, labels)


def new_pipe_slice(pipes, known):
    """Pipes of a slice whose id is not in `known` (atomic-safe: reads only)."""
    return [pipe for pipe in pipes if pipe.id not in known]


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


def outpost_positions():
    """{outpost_id: (x, y)} top-left anchors from outpost_network; None when unreadable (unlike {} = no outposts)."""
    network = get_component("outpost_network")
    if network is None:
        return None
    try:
        return {ref.id: (float(ref.x), float(ref.y)) for ref in network.outposts() or []}
    except Exception as error:
        swallowed("infra_topology.outpost_positions: outpost_network.outposts", error)
        return None


def surveyed_sites():
    """journal.surveyed_sites("nocturna"); [] when unreadable."""
    journal = get_component("journal")
    if journal is None:
        return []
    try:
        return journal.surveyed_sites("nocturna") or []
    except Exception as error:
        swallowed("infra_topology.surveyed_sites: journal.surveyed_sites", error)
        return []


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
    """
    The map's utility occupancy (pipes, jobs, autoplay.networks), kept across
    passes: read() re-reads only pipes with a new id and drops vanished ones;
    every FULL_REFRESH_PASSES passes (and on the first) it re-reads every pipe,
    since an existing pipe's contents() can change without a new id. The pipe
    occupancy is rebuilt only when pipes or autoplay.networks changed; job
    ghosts are overlaid on every read.
    """

    def __init__(self):
        self.cache = {}        # pipe id -> read_pipe_slice() row
        self.pipe_rows = []
        self.job_rows = []
        self.structure_rows = []   # read_structure_slice() rows: extractor ghosts
        self.job_ids = set()   # every pending/active/paused job id, utility or not
        self.jobs_ok = False   # False when a job list could not be read: job_ids is then incomplete
        self.occ = {layer: {} for layer in LAYERS}
        self.pipe_occ = {layer: {} for layer in LAYERS}
        self.networks = None   # autoplay.networks value pipe_occ was built with
        self.passes = 0        # reads since the last full pipe read
        self.last = ""         # what the latest read did, for the pass log

    def _read_rows(self, pipes, log: "TreeConsole | None"):
        rows = []
        for start in range(0, len(pipes), PIPE_PROGRESS_EVERY):
            rows.extend(run_batched(read_pipe_slice, pipes[start:start + PIPE_PROGRESS_EVERY], PIPE_CHUNK))
            if log is not None and len(pipes) > PIPE_PROGRESS_EVERY:
                log.debug(f"Map read: {min(start + PIPE_PROGRESS_EVERY, len(pipes))}/{len(pipes)} pipes.")
                log.flush()
        return rows

    def _read_pipes(self, log: "TreeConsole | None"):
        """Updates the pipe cache; returns True when it changed."""
        try:
            pipes = list_pipes() or []  # type: ignore[name-defined]  # game builtin
        except Exception as error:
            swallowed("infra_topology.Topology.read: list_pipes", error)
            self.last = "pipes unreadable, cache kept"
            return False
        if not self.cache or self.passes >= FULL_REFRESH_PASSES:
            self.cache = {row["id"]: row for row in self._read_rows(pipes, log)}
            self.passes = 0
            self.last = f"full read of {len(pipes)} pipes"
            return True
        self.passes += 1
        fresh = run_batched(new_pipe_slice, pipes, ID_CHUNK, self.cache)
        removed = len(self.cache) - (len(pipes) - len(fresh))
        if removed > 0:
            live = {pipe.id for pipe in pipes}
            for pipe_id in [pipe_id for pipe_id in self.cache if pipe_id not in live]:
                del self.cache[pipe_id]
        for row in self._read_rows(fresh, log):
            self.cache[row["id"]] = row
        self.last = f"{len(fresh)} new, {max(removed, 0)} removed of {len(pipes)} pipes"
        return bool(fresh) or removed > 0

    def read(self, log: "TreeConsole | None" = None):
        """Updates the occupancy from the game; returns self. Missing APIs leave the matching rows empty.
        log: TreeConsole for a debug progress line every PIPE_PROGRESS_EVERY pipes read."""
        pipes_changed = self._read_pipes(log)
        jobs = []
        self.jobs_ok = False
        blueprints = get_component("construction_blueprint")
        if blueprints is not None:
            self.jobs_ok = True
            for getter in _JOB_GETTERS:
                try:
                    jobs.extend(getattr(blueprints, getter)() or [])
                except Exception as error:
                    swallowed(f"infra_topology.Topology.read: {getter}", error)
                    self.jobs_ok = False
        self.job_ids = {job.id for job in jobs}
        self.job_rows = run_batched(read_job_slice, jobs, JOB_CHUNK)
        self.structure_rows = run_batched(read_structure_slice, jobs, JOB_CHUNK)
        networks = archive.get(NETWORKS_KEY, {})
        networks = networks if isinstance(networks, dict) else {}
        labels = planned_labels(networks)
        if pipes_changed or networks != self.networks:
            self.pipe_rows = list(self.cache.values())
            self.pipe_occ = pipe_occupancy(self.pipe_rows, labels)
            self.networks = networks
        self.occ = overlay_jobs(self.pipe_occ, self.job_rows, labels)
        return self
