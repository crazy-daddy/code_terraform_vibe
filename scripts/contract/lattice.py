# Lattice Contract Solver
# Minesweeper-style deduction: probes only proven-clear cells, then transmits the node map.

UNKNOWN = 0
CLEAR = 1
NODE = 2
MAX_COMPONENT = 60
SEARCH_BUDGET = 20000

c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

if c.status == "completed":
    print("Contract already marked completed.")

grid = c.grid
W = grid.width()
H = grid.height()
CELLS = W * H

nbrs = []
for idx in range(CELLS):
    cx = idx % W
    cy = idx // W
    around = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            nx = cx + dx
            ny = cy + dy
            if (dx != 0 or dy != 0) and 0 <= nx < W and 0 <= ny < H:
                around.append(ny * W + nx)
    nbrs.append(around)

state = [UNKNOWN] * CELLS
reading = [-1] * CELLS
unk_cnt = [len(nbrs[i]) for i in range(CELLS)]
flag_cnt = [0] * CELLS
read_cells = []
pending = []
work = []
failed = False


def set_state(i, new):
    """Record a proven cell and queue the read cells whose counters it changes."""
    state[i] = new
    for j in nbrs[i]:
        unk_cnt[j] -= 1
        if new == NODE:
            flag_cnt[j] += 1
        if reading[j] >= 0:
            work.append(j)
    if new == CLEAR:
        pending.append(i)


def mark_clear(i):
    set_state(i, CLEAR)


def mark_node(i):
    set_state(i, NODE)


def probe_one():
    global failed
    i = pending.pop()
    res = grid.probe(i % W, i // W)
    if res.status != "ok" or res.reading is None:
        print(f"Probe ({i % W},{i // W}) failed: {res.status} - {res.message}")
        failed = True
        return
    reading[i] = res.reading
    read_cells.append(i)
    work.append(i)


def propagate():
    """Single-cell rule, driven by a work list of read cells whose neighborhood changed."""
    while work:
        i = work.pop()
        unk = unk_cnt[i]
        if unk == 0:
            continue
        need = reading[i] - flag_cnt[i]
        if need == 0:
            for j in nbrs[i]:
                if state[j] == UNKNOWN:
                    mark_clear(j)
        elif need == unk:
            for j in nbrs[i]:
                if state[j] == UNKNOWN:
                    mark_node(j)


def constraints():
    """(unknown cells, nodes still to place) for each read cell with unknown neighbors."""
    out = []
    for i in read_cells:
        if unk_cnt[i] > 0:
            unk = [j for j in nbrs[i] if state[j] == UNKNOWN]
            out.append((unk, reading[i] - flag_cnt[i]))
    return out


def apply(unk, need):
    """Resolve a set that is all-clear or all-node; True if it changed anything."""
    changed = False
    if need == 0:
        for j in unk:
            if state[j] == UNKNOWN:
                mark_clear(j)
                changed = True
    elif need == len(unk):
        for j in unk:
            if state[j] == UNKNOWN:
                mark_node(j)
                changed = True
    return changed


def subset_rules():
    """If one constraint's cells sit inside another's, the difference is resolved by the counts."""
    cons = constraints()
    by_cell = {}
    for k, (unk, need) in enumerate(cons):
        for j in unk:
            by_cell.setdefault(j, []).append(k)
    changed = False
    for ka, (ua, na) in enumerate(cons):
        for kb in by_cell[ua[0]]:
            ub, nb = cons[kb]
            if kb == ka or len(ub) <= len(ua):
                continue
            inside = True
            for j in ua:
                if j not in ub:
                    inside = False
                    break
            if inside:
                diff = [j for j in ub if j not in ua]
                if apply(diff, nb - na):
                    changed = True
    return changed


def enumerate_frontier():
    """Cells that are node/clear in every valid assignment of a constraint component."""
    cons = constraints()
    by_cell = {}
    for k, (unk, need) in enumerate(cons):
        for j in unk:
            by_cell.setdefault(j, []).append(k)
    seen = {}
    comps = []
    for start in by_cell:
        if start in seen:
            continue
        cells = [start]
        seen[start] = True
        comp_cons = {}
        head = 0
        while head < len(cells):
            cell = cells[head]
            head += 1
            for k in by_cell[cell]:
                if k in comp_cons:
                    continue
                comp_cons[k] = True
                for j in cons[k][0]:
                    if j not in seen:
                        seen[j] = True
                        cells.append(j)
        comps.append((cells, list(comp_cons)))
    comps.sort(key=lambda comp: len(comp[0]))
    changed = False
    for cells, klist in comps:
        if len(cells) > MAX_COMPONENT:
            continue
        pos = {}
        for p, cell in enumerate(cells):
            pos[cell] = p
        member_of = [[] for _ in cells]
        for k in klist:
            for j in cons[k][0]:
                member_of[pos[j]].append(k)
        placed = {k: 0 for k in klist}
        left = {k: len(cons[k][0]) for k in klist}
        assign = [0] * len(cells)
        node_hits = [0] * len(cells)
        total = [0]
        steps = [0]

        def search(p):
            if steps[0] > SEARCH_BUDGET:
                return
            steps[0] += 1
            if p == len(cells):
                total[0] += 1
                for q in range(len(cells)):
                    node_hits[q] += assign[q]
                return
            for v in (0, 1):
                for k in member_of[p]:
                    placed[k] += v
                    left[k] -= 1
                ok = True
                for k in member_of[p]:
                    if placed[k] > cons[k][1] or placed[k] + left[k] < cons[k][1]:
                        ok = False
                        break
                if ok:
                    assign[p] = v
                    search(p + 1)
                for k in member_of[p]:
                    placed[k] -= v
                    left[k] += 1

        search(0)
        if steps[0] > SEARCH_BUDGET:
            print(f"  debug: component of {len(cells)} cells exceeded search budget")
            continue
        if total[0] == 0:
            continue
        for p, cell in enumerate(cells):
            if state[cell] != UNKNOWN:
                continue
            if node_hits[p] == total[0]:
                mark_node(cell)
                changed = True
            elif node_hits[p] == 0:
                mark_clear(cell)
                changed = True
        if changed:
            return True
    return changed


start = grid.start()
mark_clear(start[1] * W + start[0])
print(f"Start cell: ({start[0]},{start[1]}), grid {W}x{H}")

stalls = 0
while not failed:
    propagate()
    if pending:
        probe_one()
        continue
    stalls += 1
    if subset_rules():
        continue
    if enumerate_frontier():
        continue
    break

nodes = state.count(NODE)
clears = state.count(CLEAR)
unresolved = state.count(UNKNOWN)
print(f"Solved with {stalls} stalls: {nodes} nodes, {clears} clear, {unresolved} unresolved")

if failed:
    print("Lattice faulted; resetting and aborting without transmitting.")
    grid.reset()
elif unresolved:
    print("Unresolved cells remain; refusing to guess, not transmitting.")
else:
    node_map = [1 if state[i] == NODE else 0 for i in range(CELLS)]
    transmitter = get_component("transmitter")
    if not transmitter:
        print("[LATTICE] No Transmitter found!")
    else:
        link = transmitter.connect("earth")
        if link.status != "ok":
            print(f"Transmitter connection failed: {link.status} - {link.message}")
        else:
            tx_res = transmitter.transmit(c.id, node_map)
            print("Transmission status:", tx_res.status, "-", tx_res.message)
