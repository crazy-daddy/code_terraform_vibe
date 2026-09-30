# Pure per-cell computations of the Harvester's publish step (lib/field_keeper.py).
# Every function here touches no game object, archive, console or clock: the
# caller reads the cells first and passes plain tuples/dicts, so each call is
# safe to run through lib/atomic.py's run_atomic() (docs/cheatsheet/dev_workflow.md §1d-1).
# A call handles one chunk (the *_CHUNK constants below); the worst chunk of each
# function is measured in tests/test_harvester_pure.py against ATOMIC_STEP_BUDGET.

ROW_CHUNK = 32               # planted-cell rows per care/stats scan call (worst row ~120 operations)
SOON_CHUNK = 96              # planted-cell rows per soon_sectors() call (worst row ~30 operations)
CARE_CHUNK = 48              # care entries per due_targets() call (worst entry ~45 operations)
ITEM_CHUNK = 96              # layout entries per demand-count / rotation / seeded call (worst entry ~30 operations)
ATOMIC_STEP_BUDGET = 4000    # worst-case interpreter operations allowed for one atomic call here

# Cell attributes behind a row (harvester_planting.planted_rows()), in row order.
ROW_ATTRS = ("status", "plant", "growth", "manual_light_remaining", "manual_water_remaining",
             "manual_salt_remaining", "lit", "watered", "salted")
# Per treatment kind: (kind, row index of its manual hours left, row index of its coverage flag).
KIND_SLOTS = {"light": ("light", 3, 6), "water": ("water", 4, 7), "salt": ("salt", 5, 8)}
HAND_STATUSES = ("growing", "stalled")
KEPT_STATUSES = ("growing", "stalled", "mature")


def care_slots(table, salt_ok):
    """{species: [(kind, hours index, flag index)]} from {species: kinds}; salt only while `salt_ok`. Runs outside atomic calls."""
    return {species: [KIND_SLOTS[kind] for kind in kinds if kind != "salt" or salt_ok] for species, kinds in table.items()}


def scan_rows(rows, slots, kept):
    """
    One pass over planted-cell rows [(sector, (status, plant, growth, light_h, water_h, salt_h, lit, watered, salted))].
    Returns (care, mature, stalled, productive):
      care        {sector: [(kind, manual hours left)]} of the treatments the Harvester keeps up
                  (harvester_care.hand_care(): no provider covers it), from care_slots()
      mature      rows with status "mature"
      stalled     rows with status "stalled"
      productive  species of the rows that are not stalled
    `kept` = sectors whose mature crops also count for care.
    """
    care = {}
    mature = stalled = 0
    productive = set()
    for sector, v in rows:
        status = v[0]
        if status == "stalled":
            stalled += 1
        else:
            productive.add(v[1])
            if status == "mature":
                mature += 1
        kinds = slots.get(v[1])
        if kinds and (status in HAND_STATUSES or (status in KEPT_STATUSES and sector in kept)):
            out = [(kind, v[hi] or 0) for kind, hi, fi in kinds if not (v[fi] and (v[hi] or 0) <= 0)]
            if out:
                care[sector] = out
    productive.discard(None)
    productive.discard("")
    return care, mature, stalled, productive


def due_targets(items, refresh_h):
    """{sector: [kinds]} of the care `items` [(sector, [(kind, hours left)])] with a treatment below `refresh_h`."""
    out = {}
    for sector, treatments in items:
        due = [kind for kind, remaining in treatments if remaining < refresh_h]
        if due:
            out[sector] = due
    return out


def soon_sectors(rows, active, kept, prefetch_growth):
    """Sectors of planted rows in `active` (not kept) with their layout species, mature or grown to `prefetch_growth`."""
    return [sector for sector, (status, plant, growth, *_rest) in rows
            if sector in active and sector not in kept and plant == active[sector]
            and (status == "mature" or (growth or 0) >= prefetch_growth)]


def needed_seeds(items, statuses, open_statuses, soon, seed_ids):
    """{seed_id: cells} for the layout `items` [(sector, species)] that are open (by `statuses`) or in `soon`, in first-seen order."""
    now = {}
    for sector, species in items:
        if statuses.get(sector, "unknown") in open_statuses or sector in soon:
            seed_id = seed_ids[species]
            now[seed_id] = now.get(seed_id, 0) + 1
    return now


def rotation_counts(items, kept, seed_ids):
    """{seed_id: cells} of the layout `items` [(sector, species)] outside `kept`, in first-seen order."""
    rotation = {}
    for sector, species in items:
        if sector not in kept:
            seed_id = seed_ids[species]
            rotation[seed_id] = rotation.get(seed_id, 0) + 1
    return rotation


def seeded_items(items, mine, automated):
    """[(sector, species)] of `items` whose sector is in `mine` or `automated`."""
    return [(sector, species) for sector, species in items if sector in mine or sector in automated]


def merge_counts(parts):
    """Sums count dicts, keeping first-seen key order. Runs outside atomic calls (few keys)."""
    total = {}
    for part in parts:
        for key, n in part.items():
            total[key] = total.get(key, 0) + n
    return total
