# Core Sample Contract Solver
# Reconstructs damaged data cores (None = destroyed byte) from the format rules, submits each, then transmits the token.

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from user_stubs import core_sample as self

MARK = 42


def solve_core(core):
    """Return the unique valid reconstruction of a damaged core, or (None, reason)."""
    total = len(core)
    if total < 12 or (total - 4) % 4 != 0:
        return None, f"length {total} is not 4+4*N"
    n = (total - 4) // 4
    if n < 2 or n % 2:
        return None, f"N={n} must be even and >= 2"

    header = [MARK, n, total]
    for i, want in enumerate(header):
        if core[i] is not None and core[i] != want:
            return None, f"header byte {i} is {core[i]}, expected {want}"

    cells = [core[3 + 4 * i : 7 + 4 * i] for i in range(n)]
    lock_known = core[-1]

    def kinds_of(i):
        k = cells[i][0]
        return [k] if k is not None else [1, 2, 3, 4]

    def fits(i, kind, pair):
        """Survivors of cell i allow this kind/pair and, where checkable, the SUM rule."""
        k, load, p, s = cells[i]
        if k is not None and k != kind:
            return False
        if p is not None and p != pair:
            return False
        if load is not None and s is not None and s != (kind + load + pair) % 256:
            return False
        return True

    solutions = []

    def match(kind, pair, unassigned):
        if not unassigned:
            solutions.append((list(kind), list(pair)))
            return
        i = unassigned[0]
        rest = unassigned[1:]
        for j in rest:
            for ki in kinds_of(i):
                kj = 5 - ki
                if not (1 <= kj <= 4):
                    continue
                if not (fits(i, ki, j) and fits(j, kj, i)):
                    continue
                kind[i] = ki
                kind[j] = kj
                pair[i] = j
                pair[j] = i
                match(kind, pair, [r for r in rest if r != j])

    match([0] * n, [0] * n, list(range(n)))

    results = []
    for kind, pair in solutions:
        loads, sums, free = [], [], []
        for i in range(n):
            _, load, _, s = cells[i]
            if load is not None:
                s = (kind[i] + load + pair[i]) % 256
            elif s is not None:
                load = (s - kind[i] - pair[i]) % 256
            else:
                free.append(i)
            loads.append(load)
            sums.append(s)
        if len(free) > 1:
            continue
        known_xor = 0
        for i in range(n):
            if i not in free:
                known_xor ^= sums[i]
        if free:
            if lock_known is None:
                continue
            i = free[0]
            sums[i] = known_xor ^ lock_known
            loads[i] = (sums[i] - kind[i] - pair[i]) % 256
            lock = lock_known
        else:
            lock = known_xor
            if lock_known is not None and lock_known != lock:
                continue
        out = list(header)
        for i in range(n):
            out += [kind[i], loads[i], pair[i], sums[i]]
        out.append(lock)
        results.append(out)

    if len(results) != 1:
        return None, f"{len(results)} candidate reconstructions"
    return results[0], "ok"


c = self.contract
print(f"Contract: {c.name} ({c.id}), Reward: {c.reward} credits")

if c.status == "completed":
    print("Contract already marked completed.")

device = c.device
cores = c.cores
print(f"Reconstructing {len(cores)} cores")

for index, core in enumerate(cores):
    fixed, why = solve_core(core)
    if fixed is None:
        print(f"Core {index}: cannot reconstruct ({why})")
        continue
    try:
        result = device.submit(index, fixed)
    except (TypeError, ValueError) as err:
        print(f"Core {index}: submit error: {err}")
        continue
    print(f"Core {index}: {result.status} - {result.message}")

print(f"Recovered {device.recovered()}/{device.target()}")

if device.recovered() >= device.target():
    transmitter = get_component("transmitter")
    if not transmitter:
        print("[CORE_SAMPLE] No Transmitter found!")
    else:
        link = transmitter.connect("earth")
        if link.status != "ok":
            print(f"Transmitter connection failed: {link.status} - {link.message}")
        else:
            tx_res = transmitter.transmit(c.id, device.token())
            print("Transmission status:", tx_res.status, "-", tx_res.message)
else:
    print("Not all cores recovered; token not transmitted.")
