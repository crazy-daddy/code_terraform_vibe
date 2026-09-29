# Lattice Contract Solver
# Minesweeper-style deduction: probes only proven-clear cells, then transmits the node map.
# The board is padded with a wall ring so neighbours are plain index offsets, and neighbour
# counts use native slice/count calls: the game interpreter is slow, so op count matters.

UNKNOWN = 0
CLEAR = 1
NODE = 2
WALL = 3
MAX_COMPONENT = 60
SEARCH_BUDGET = 20000

c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

if c.status == "completed":
    print("Contract already marked completed.")

grid = c.grid
W = grid.width()
H = grid.height()
P = W + 2

state = [WALL] * P + ([WALL] + [UNKNOWN] * W + [WALL]) * H + [WALL] * P
reading = [-1] * len(state)
pending = []
frontier = []
failed = False


def unknowns(i):
    """Unknown cells around i, found row by row with a native membership test."""
    out = []
    for a in (i - P - 1, i - 1, i + P - 1):
        row = state[a : a + 3]
        if UNKNOWN in row:
            for t in (0, 1, 2):
                if row[t] == UNKNOWN:
                    out.append(a + t)
    return out


def mark_clear(j):
    state[j] = CLEAR
    pending.append(j)


def mark_node(j):
    state[j] = NODE


def check(i):
    """Single-cell rule. 0: nothing left to resolve, 1: resolved cells, 2: still undecided."""
    a = i - P - 1
    b = i - 1
    d = i + P - 1
    window = state[a : a + 3] + state[b : b + 3] + state[d : d + 3]
    unk = window.count(UNKNOWN)
    if unk == 0:
        return 0
    need = reading[i] - window.count(NODE)
    if need == 0:
        for j in unknowns(i):
            mark_clear(j)
        return 1
    if need == unk:
        for j in unknowns(i):
            mark_node(j)
        return 1
    return 2


def probe_pending():
    global failed
    while pending and not failed:
        i = pending.pop()
        res = grid.probe(i % P - 1, i // P - 1)
        if res.status != "ok" or res.reading is None:
            print(f"Probe ({i % P - 1},{i // P - 1}) failed: {res.status} - {res.message}")
            failed = True
            return
        reading[i] = res.reading
        if check(i) == 2:
            frontier.append(i)


def sweep():
    """Re-run the single-cell rule over the undecided frontier; True if anything resolved."""
    global frontier
    changed = False
    remaining = []
    for i in frontier:
        r = check(i)
        if r == 2:
            remaining.append(i)
        elif r == 1:
            changed = True
    frontier = remaining
    return changed


def constraints():
    """(unknown cells, nodes still to place) for each undecided frontier cell."""
    out = []
    for i in frontier:
        unk = unknowns(i)
        if unk:
            need = reading[i]
            for a in (i - P - 1, i - 1, i + P - 1):
                need -= state[a : a + 3].count(NODE)
            out.append((unk, need))
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
mark_clear((start[1] + 1) * P + start[0] + 1)
print(f"Start cell: ({start[0]},{start[1]}), grid {W}x{H}")

stalls = 0
while not failed:
    probe_pending()
    if failed:
        break
    if sweep() or pending:
        continue
    stalls += 1
    if subset_rules() or enumerate_frontier():
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
    node_map = []
    for y in range(H):
        row = state[(y + 1) * P + 1 : (y + 1) * P + 1 + W]
        node_map += [v >> 1 for v in row]
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
