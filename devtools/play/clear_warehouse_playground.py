# Playground script: empties one Warehouse into the best other stores.
# Paste into the in-game Playground, set WAREHOUSE below, run.
# Every stack goes to storage.best_unload_target() (same routing the machines use),
# with the cleared Warehouse excluded. At home, Inventory is the last fallback.
# Automation may refill the Warehouse afterwards: nothing marks it as retiring.

WAREHOUSE = 1  # number from the building id, e.g. 7 for warehouse_7
LARGE = False  # True for large_warehouse_N
DRY_RUN = False  # True: print the plan, move nothing
BUSY_RETRIES = 5  # tries per stack while a store answers "busy"

from components import component  # noqa: E402
from storage import best_unload_target, discover_storage_buildings, forget_storage_discovery  # noqa: E402


def find_source(source_id):
    """(component, outpost) for source_id, else (None, None)."""
    network = component("outpost_network")
    for outpost in network.outposts() if network else []:
        for building in discover_storage_buildings(outpost):
            if building["id"] == source_id:
                return building["component"], outpost
    return None, None


def room_at(target, item_id, properties):
    store = component(target)
    if not store or not hasattr(store, "space_for"):
        return 0
    return store.space_for(item_id, properties) if properties else store.space_for(item_id)


def move_stack(source, source_id, outpost, stack):
    """Moves one stack, target by target. Returns units moved."""
    item_id, properties = stack.id, getattr(stack, "properties", None)
    left, moved_total, busy = stack.count, 0, []
    while left > 0:
        target = best_unload_target(item_id, 1, outpost=outpost, exclude=[source_id] + busy)
        if target is None:
            print(f"  {item_id}: no store has room, {left} left")
            break
        units = min(left, room_at(target, item_id, properties))
        if units <= 0:
            busy.append(target)  # no room for this property variant
            continue
        if DRY_RUN:
            print(f"  {item_id}: would move {units} -> {target}")
            return units
        result = (
            source.transfer_to(target, item_id, units, properties)
            if properties
            else source.transfer_to(target, item_id, units)
        )
        status, moved = getattr(result, "status", None), getattr(result, "moved", 0) or 0
        if status == "busy" and len(busy) < BUSY_RETRIES:
            busy.append(target)
            sleep(0.5)  # noqa: F821 -- game builtin
            continue
        if moved <= 0:
            print(f"  {item_id}: {target} took nothing ({status}: {getattr(result, 'message', '')})")
            break
        print(f"  {item_id}: moved {moved} -> {target}")
        moved_total += moved
        left -= moved
        busy = []
        forget_storage_discovery()
    return moved_total


def run():
    source_id = f"{'large_warehouse' if LARGE else 'warehouse'}_{WAREHOUSE}"
    source, outpost = find_source(source_id)
    if source is None:
        print(f"{source_id} not found")
        return
    stacks = [stack for stack in source.stacks() if stack.count > 0]
    print(
        f"Clearing {source_id} at {getattr(outpost, 'name', '?')}: {len(stacks)} stacks{' (dry run)' if DRY_RUN else ''}"
    )
    moved = sum([move_stack(source, source_id, outpost, stack) for stack in stacks])
    left = sum([stack.count for stack in source.stacks()])
    print(f"Done: moved {moved}, {left} units left in {source_id}")


run()
