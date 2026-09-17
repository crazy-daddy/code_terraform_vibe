# Shared Library for Biology Pipeline Automation
# Event-driven and Signal Bus aware coordination for Bio Collector, Bio Lab, Bio
# Exchange, and Bio Luminizer. Outpost-aware throughout: these buildings started out
# home-only (hardcoded to "inventory"), but the pipeline can now be deployed at a
# remote outpost that has Warehouses only, no Inventory -- see
# docs/AI_CHEATSHEET.md and TODO.md Phase 4.
from archive import archive
from storage import take_item, warehouse_stock, total_stock, drain_port_to_storage, discover_storage_buildings, best_unload_target

def get_my_biome(machine):
    if hasattr(machine, "outpost") and machine.outpost:
        return getattr(machine.outpost, "biome", None)
    return None

def local_sibling(outpost, type_id):
    """
    First same-outpost sibling component of type_id (e.g. a Bio Lab's own Bio
    Collector, or a Bio Collector's own Bio Exchange/Bio Lab), discovered via
    outpost.buildings(type_id) rather than a hardcoded instance id like
    "bio_collector_1" -- a save with more than one Bio pipeline (e.g. a second
    one at a remote outpost, see docs/AI_CHEATSHEET.md Phase 4) needs each
    controller to find its OWN outpost's sibling, not always the same
    hardcoded home-outpost instance. Returns None if this outpost has none
    (or outpost is None/unavailable).
    """
    if not outpost or not hasattr(outpost, "buildings"):
        return None
    try:
        found = outpost.buildings(type_id)
    except Exception:
        return None
    if not found:
        return None
    b_id = getattr(found[0], "id", None)
    return get_component(b_id) if b_id else None

def is_home_outpost(outpost):
    # outpost is an OutpostRef (see storage.discover_storage_buildings() /
    # outpost_mining.outpost_by_id() callers) -- .is_home is a plain bool
    # property there, not a method (docs/types/world_and_sites.md's
    # OutpostRef vs. Outpost component distinction), so this must NOT call it.
    return getattr(outpost, "is_home", True) if outpost else True

def local_stock(item_id, outpost):
    """
    How much of item_id this machine can actually reach locally: home Inventory (plus
    any Warehouse) at the home outpost, or Warehouse-only at a remote outpost.
    total_stock() always adds home Inventory regardless of `outpost` -- correct when
    `outpost` IS home, wrong for a remote outpost (would over-report by whatever's
    sitting untouched back at home). See storage.warehouse_stock()'s docstring.
    """
    if is_home_outpost(outpost):
        return total_stock(item_id)
    return warehouse_stock(item_id, outpost)

def is_local_order(ord_info, my_biome):
    if not my_biome:
        return True
    ord_biome = getattr(ord_info, "biome", None)
    if not ord_biome:
        return True
    return ord_biome == my_biome or ord_biome in my_biome or my_biome in ord_biome

def is_order_incomplete(ord_info):
    """
    Checks if an order is incomplete.
    Note: percent in BioOrder is an integer (0..100) or float (0.0..1.0).
    We check both ord_info.status and percent (< 100).
    """
    if getattr(ord_info, "status", "") == "complete":
        return False
    pct = getattr(ord_info, "percent", 0.0)
    # If percent is formatted as 0..100 (e.g. 13% or 4%), compare against 100
    if pct >= 100:
        return False
    # If percent is formatted as 0.0..1.0, compare against 1.0 (unless it's an integer >= 1)
    if isinstance(pct, float) and pct >= 1.0:
        return False
    return True


def _luminizer_is_idle(luminizer):
    """
    True if the local Bio Luminizer's chamber, input, and output are all
    empty -- i.e. genuinely ready for a new sample, not still holding/working
    the previous one. Used by BioLabController to gate pulling the next
    specimen from the Collector and draining its own extracted output into
    the Warehouse: since Collector/Lab/Luminizer are each single-slot
    hardware, refusing both of those two actions until the Luminizer is
    fully idle bounds the pipeline to at most one raw specimen in flight
    ahead of it at a time -- no Warehouse pileup is structurally possible
    regardless of how broadly the Collector searches for "needed" fragments,
    which is what RAW_BACKLOG_CAP_PER_FRAGMENT/FOCUS_ORDER_COUNT used to
    exist to prevent numerically (see docs/AI_CHEATSHEET.md Sec 1f).

    True when there's no local Luminizer at all (a non-coastal biome
    pipeline has none), so this gate never blocks a Lab that isn't feeding
    one.
    """
    if not luminizer:
        return True
    try:
        if luminizer.chamber is not None:
            return False
        if luminizer.input.count() > 0:
            return False
        if luminizer.output.count() > 0:
            return False
    except Exception:
        return True
    return True


def _local_sources(outpost):
    """[(source_id, component), ...] for every storage location this outpost can pull
    from: "inventory" first if home, then every discovered Warehouse at `outpost`."""
    sources = []
    if is_home_outpost(outpost):
        inv = get_component("inventory")
        if inv:
            sources.append(("inventory", inv))
    for building in discover_storage_buildings(outpost):
        sources.append((building["id"], building["component"]))
    return sources


def _local_stock_snapshot(outpost):
    """
    One full walk of local storage (see _local_sources()), returning
    (totals, by_glow):
      totals: {item_id: total_count} -- every _local_stock()-equivalent
        answer for this outpost, from a SINGLE storage walk instead of one
        walk per item_id.
      by_glow: {(item_id, glow_tuple): count} -- every
        _glow_matching_count()-equivalent answer, same single-walk sharing.

    Caching exchange.orders() alone (see _focus_coastal_order()'s docstring)
    only got BioCollectorController.step() from ~20s to ~8s/cycle -- the
    remaining cost was THIS: local_stock()/_glow_matching_count() were each
    independently re-walking every Warehouse's stacks() from scratch, once
    per fragment (sometimes several times per fragment, inside
    _raw_backlog_count()'s per-order loop). Building one snapshot per step()
    and having every stock/glow lookup read from it instead is the same fix
    applied one layer deeper.
    """
    totals = {}
    by_glow = {}
    for source_id, component in _local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception:
            continue
        for stack in stacks:
            item_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not item_id or count <= 0:
                continue
            totals[item_id] = totals.get(item_id, 0) + count
            properties = getattr(stack, "properties", None) or {}
            glow = properties.get("glow")
            if glow:
                key = (item_id, tuple(glow))
                by_glow[key] = by_glow.get(key, 0) + count
    return totals, by_glow


def _snapshot_stock(snapshot, item_id):
    """Total local stock of item_id from a _local_stock_snapshot() -- the
    snapshot-based equivalent of local_stock(item_id, outpost)."""
    totals, _ = snapshot
    return totals.get(item_id, 0)


def _snapshot_glow_count(snapshot, item_id, target_glow):
    """Local stock of item_id whose glow exactly equals target_glow, from a
    _local_stock_snapshot() -- the snapshot-based equivalent of
    _glow_matching_count(item_id, outpost, target_glow). Direct property
    comparison, NOT exchange.matches_order() -- matches_order() only
    reflects whatever the Exchange's OWN active_order currently is, and
    self.set_order()/self.clear_order()/self.deliver() are all documented
    *(self only)* hardware calls: a script can only ever drive the machine
    it's physically attached to, never a sibling fetched via
    get_component()/local_sibling() (confirmed live: calling
    exchange.set_order() from the Luminizer's own script raised
    "PermissionError: Cannot call set_order() on bio_exchange_4 remotely").
    So any OTHER script (Luminizer, Collector) that needs to know "does this
    stack match THIS SPECIFIC order" has no way to force the Exchange's
    active order to check against -- it has to compare the glow property
    directly instead, which needs no hardware call at all."""
    if not target_glow:
        return 0
    _, by_glow = snapshot
    return by_glow.get((item_id, tuple(target_glow)), 0)


def _total_glow_artifacts(snapshot):
    """Total units of any glow-tagged item sitting in local storage right
    now (raw and already-tinted, across every fragment type) -- a coarse
    aggregate reading straight off an already-built _local_stock_snapshot(),
    no extra scanning. See MAX_LOCAL_GLOW_ARTIFACTS for what this backstops."""
    _, by_glow = snapshot
    return sum(by_glow.values())


# Coarse safety-net cap on total glow-tagged artifacts (raw + tinted, any
# fragment type) allowed to sit in local storage before BioCollectorController
# pauses harvesting entirely. NOT the primary flow-control mechanism -- that's
# BioLabController's Luminizer-idle gate (_luminizer_is_idle()), which bounds
# in-flight specimens to the pipeline's own single-slot hardware (Collector
# cargo, Lab specimen/output, Luminizer chamber/input/output) and should keep
# this number at 0-2 in a healthy pipeline: the Lab holds at most 1 before the
# Luminizer picks it up, and the Luminizer holds at most 1-2 before the
# Exchange sweeps them up. This cap exists purely as insurance against that
# structural bound somehow not holding (e.g. a sibling script not running) --
# see docs/AI_CHEATSHEET.md Sec 1f for the numeric per-fragment throttle this
# replaces.
MAX_LOCAL_GLOW_ARTIFACTS = 4


def _find_matching_stack(exchange_machine, item_id, outpost):
    """
    Scans every local storage source for a stack of item_id whose exact properties
    satisfy exchange_machine.matches_order() (glow/genes/plain-sample, whatever the
    active order actually requires) -- the documented pattern
    (docs/components/bio_exchange.md: matches_order() before an exact take()) for
    picking the RIGHT variant instead of blindly grabbing whatever's staged first.
    Returns (source_id, properties) or None.
    """
    for source_id, component in _local_sources(outpost):
        if not component or not hasattr(component, "stacks"):
            continue
        try:
            stacks = component.stacks()
        except Exception:
            continue
        for stack in stacks:
            if getattr(stack, "id", None) != item_id:
                continue
            properties = getattr(stack, "properties", None)
            try:
                if exchange_machine.matches_order(item_id, properties):
                    return source_id, properties
            except Exception:
                continue
    return None


def _order_fragment_remaining(order, fragment_id, snapshot):
    """
    Units of fragment_id this order still genuinely needs, net of what's
    already delivered, in transit, or sitting locally already correctly
    tinted for it (see _snapshot_glow_count()). Module-level (not just
    BioLuminizerController._fragment_remaining(), which delegates here) so
    _focus_coastal_order() can use the same check when picking which order
    to concentrate on.

    Found live: without this, an order that merely lists fragment_id in
    `.requires` -- even with its deficit for that specific fragment already
    fully covered -- looked identical to one still genuinely wanting more of
    it. `_focus_coastal_order()` could lock onto that already-satisfied
    order while a DIFFERENT incomplete local order genuinely still needed
    more of the same fragment; every subsequent per-fragment remaining-check
    on the locked order came back 0, so the Luminizer found nothing to load
    and just repeated the same no-op every tick, even with matching raw
    stock sitting right there and real aggregate demand for it elsewhere.
    """
    needed = (order.requires or {}).get(fragment_id, 0)
    if needed <= 0:
        return 0
    delivered = (order.delivered or {}).get(fragment_id, 0)
    in_transit = (order.in_transit or {}).get(fragment_id, 0)
    remaining = needed - delivered - in_transit
    if remaining <= 0:
        return 0
    target_glow = getattr(order, "target_glow", None)
    already_matching = _snapshot_glow_count(snapshot, fragment_id, target_glow)
    return max(0, remaining - already_matching)


def _focus_coastal_order(orders, snapshot, my_biome, fragment_id=None):
    """
    The ONE local, incomplete, glow-requiring order to concentrate on right
    now -- optionally the one that specifically still needs more of
    fragment_id (not just any order that lists it in `.requires` -- see
    _order_fragment_remaining()'s docstring for the live bug that
    distinction fixes). Deliberately NOT exchange.active_order() (see
    BioLuminizerController's docstring for that whole story). When
    fragment_id is omitted, prefers a candidate that already has local stock
    of one of its genuinely-still-needed required fragments over one needing
    fresh collection.

    Takes an already-fetched `orders` list (exchange.orders()) rather than
    `exchange` itself -- found live: exchange.orders() returns ~80 orders
    and isn't free to call, so callers fetch it once per step() and thread
    it through every helper that needs it instead of each fetching its own
    copy (see docs/AI_CHEATSHEET.md Sec 1f for the ~20s/cycle this caused
    before that fix).

    Shared by BioCollectorController (used to prefer harvesting this order's
    fragments over other incomplete orders') and BioLuminizerController
    (_find_coastal_order() delegates here) so both agree on the SAME "order
    we're concentrating on right now" -- e.g. the Luminizer's tint target and
    the Collector's harvest preference stay in sync. Actual overproduction
    prevention is now structural (see _luminizer_is_idle()), not enforced by
    this selection.
    """
    candidates = []
    for order in orders:
        if not is_order_incomplete(order):
            continue
        if not is_local_order(order, my_biome):
            continue
        if not getattr(order, "target_glow", None):
            continue
        if fragment_id is not None and fragment_id not in (order.requires or {}):
            continue
        candidates.append(order)

    if not candidates:
        return None

    if fragment_id is not None:
        for order in candidates:
            if _order_fragment_remaining(order, fragment_id, snapshot) > 0:
                return order
        return None

    for order in candidates:
        if any(
            _order_fragment_remaining(order, frag_id, snapshot) > 0 and _snapshot_stock(snapshot, frag_id) > 0
            for frag_id in (order.requires or {}).keys()
        ):
            return order
    return candidates[0]


class BioExchangeController:
    """
    Manages Bio Orders, aggressive inventory sweeps, and sample deliveries.
    Broadcasting channel: 'bio_orders'
    Receiving channel: 'sample_ready'
    """
    def __init__(self, machine, sweep_delay=10.0):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_exchange")
        self.comms = get_component("comms")
        self.sweep_delay = sweep_delay

    def drain_output(self):
        drain_port_to_storage(self.machine.output, self.machine.outpost)

    def clear_input(self):
        if self.machine.input.count() > 0:
            for stack in self.machine.input.stacks():
                try:
                    destination = best_unload_target(stack.id, stack.count, outpost=self.machine.outpost)
                    self.machine.input.eject(destination, stack.id, stack.count)
                except Exception:
                    pass

    def broadcast_demands(self):
        """Broadcasts all pending order demands across the Signal Bus."""
        if not self.comms:
            return

        all_orders = self.machine.orders()
        my_biome = get_my_biome(self.machine)
        local_demands = {}
        all_demands = {}

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                rem = needed - (deliv + in_tr)
                if rem > 0:
                    all_demands[item_id] = all_demands.get(item_id, 0) + rem
                    if is_local_order(ord_info, my_biome):
                        local_demands[item_id] = local_demands.get(item_id, 0) + rem

        payload = {
            "local_demands": local_demands,
            "all_demands": all_demands,
            "active_order": getattr(self.machine.active_order(), "id", None),
        }
        try:
            self.comms.broadcast("bio_orders", payload)
        except Exception:
            pass

    def sweep_and_deliver(self):
        """
        Aggressive Sweep: Iterates local storage (home Inventory, or this outpost's
        Warehouses if remote) and delivers ANY sample matching ANY incomplete order
        (local OR foreign) to declutter it. Only takes a stack whose exact properties
        satisfy matches_order() -- required for biomes like coastal, where a sample
        only counts if its glow matches the order's target_glow exactly, not just the
        right fragment id.
        """
        self.drain_output()
        self.clear_input()

        outpost = self.machine.outpost
        all_orders = self.machine.orders()
        delivered_count = 0

        print(f"[EXCHANGE] Starting sweep across {len(all_orders)} orders. Checking local storage...")

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, count_needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                remaining_needed = count_needed - (deliv + in_tr)

                if remaining_needed <= 0:
                    continue

                available = local_stock(item_id, outpost)
                if available <= 0:
                    continue

                to_deliver = min(remaining_needed, available)

                # Switch active order to deliver matching items
                active = self.machine.active_order()
                if active is None or active.id != ord_info.id:
                    set_res = self.machine.set_order(ord_info.id)
                    if set_res.status != "ok":
                        print(f"[EXCHANGE] Failed to set order {ord_info.id}: {set_res.status} - {set_res.message}")
                        continue
                    biome_tag = getattr(ord_info, "biome", "order")
                    print(f"[EXCHANGE] Switched to {ord_info.id} ({ord_info.name} - {biome_tag}) to deliver {to_deliver}x {item_id}")

                for _ in range(to_deliver):
                    self.drain_output()

                    match = _find_matching_stack(self.machine, item_id, outpost)
                    if not match:
                        print(f"[EXCHANGE] No locally-staged {item_id} variant currently satisfies this order.")
                        break
                    source_id, properties = match

                    if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                        self.machine.input.connect(source_id)

                    take_res = self.machine.input.take(item_id, 1, properties, "exact")
                    if take_res.status != "ok":
                        print(f"[EXCHANGE] Take {item_id} status: {take_res.status} - {take_res.message}")
                        if take_res.status == "target_wrong_material":
                            self.clear_input()
                        break

                    deliv_res = self.machine.deliver()
                    while deliv_res.status == "busy":
                        sleep(0.2)
                        deliv_res = self.machine.deliver()

                    if deliv_res.status in ["ok", "complete"]:
                        delivered_count += 1
                        print(f"[EXCHANGE] Delivered 1x {item_id} -> {ord_info.id} ({ord_info.name}) (Status: {deliv_res.status})")
                        if deliv_res.status == "complete":
                            reward_str = f" (+{ord_info.reward} credits)" if getattr(ord_info, "reward", 0) else ""
                            try:
                                notify(f"[Bio Order Complete] {ord_info.name}{reward_str}!", level="info", duration_seconds=10.0)
                            except Exception:
                                pass
                            try:
                                archive.transaction(
                                    "bio.completed_orders",
                                    [],
                                    lambda lst: lst if ord_info.id in lst else lst + [ord_info.id]
                                )
                            except Exception:
                                pass
                    else:
                        print(f"[EXCHANGE] Deliver error: {deliv_res.status} - {deliv_res.message}")
                        break

        self.drain_output()
        self.clear_input()

        if delivered_count > 0:
            print(f"[EXCHANGE] Sweep finished: delivered {delivered_count} sample(s).")

        # Select a local incomplete order for ongoing collection
        my_biome = get_my_biome(self.machine)
        active = self.machine.active_order()
        if active is None or not is_order_incomplete(active) or not is_local_order(active, my_biome):
            for ord_info in all_orders:
                if is_order_incomplete(ord_info):
                    if is_local_order(ord_info, my_biome):
                        self.machine.set_order(ord_info.id)
                        print(f"[EXCHANGE] Set default local order: {ord_info.id} ({ord_info.name})")
                        break

        self.broadcast_demands()

    def run(self):
        print(f"Bio Exchange ({self.name}) online via Shared Library & Signal Bus.")
        while True:
            self.sweep_and_deliver()

            # Wait for either the next sweep interval OR an instant 'sample_ready' signal from the lab
            if self.comms:
                try:
                    # Non-blocking check for instant delivery trigger
                    msg = self.comms.receive("sample_ready")
                    if msg.status == "ok":
                        print(f"[EXCHANGE] Received sample_ready event ({msg.packet.get('sample_id')}), triggering immediate sweep!")
                        continue
                except Exception:
                    pass

            sleep(self.sweep_delay)


class BioLabController:
    """
    Automates Analyze and Extract for the Bio Lab.
    Cleans latched inputs/outputs, auto-purchases missing reagents (home only --
    a remote Lab has no direct Shop delivery, so it waits on the reagent transporter
    instead, see lib/vehicle_cargo.py's run_haul_loop()), and notifies
    the Signal Bus ('sample_ready') upon completing an extraction.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_lab")
        self.shop = get_component("shop")
        self.comms = get_component("comms")
        self.inventory_full_notified = False

    def drain_output(self):
        outpost = self.machine.outpost
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                target = best_unload_target(stack.id, stack.count, outpost=outpost)
                if target is None:
                    return False  # no local storage has room -- leave staged, retry next cycle
                if hasattr(self.machine.output, "connected_id") and self.machine.output.connected_id() != target:
                    self.machine.output.connect(target)
                res_send = self.machine.output.send(stack.id, stack.count)
                if res_send.status == "ok":
                    print(f"[{self.name}] Sent {res_send.moved}x {stack.id} to '{target}'.")
                    self.inventory_full_notified = False
                elif res_send.status == "busy":
                    sleep(0.2)
                    return False
                elif res_send.status in ["target_full", "slots_full", "inventory_full"]:
                    self.handle_storage_full()
                    return False
                else:
                    print(f"[{self.name}] Output notice: {res_send.status} - {res_send.message}")
                    sleep(0.5)
                    return False
        return True

    def handle_storage_full(self):
        """Pause extraction while preserving the sample in the lab output."""
        if not self.inventory_full_notified:
            print(f"[{self.name}] WARNING: local storage is full. Free space to resume sample extraction.")
            try:
                notify(f"[{self.name}] Storage Full! Free space to resume extraction.", level="warn", duration_seconds=8.0)
            except Exception:
                pass
            self.inventory_full_notified = True
        sleep(2.0)

    def _wait_for_luminizer(self):
        """
        Blocks until the local Luminizer's next heartbeat broadcast, instead
        of busy-polling with sleep() while this Lab holds off pulling its
        next specimen from the Collector or draining its own extracted
        output -- see _luminizer_is_idle()'s docstring for why that gate
        exists. The heartbeat fires once every Luminizer step() cycle
        regardless of what that cycle did (see
        BioLuminizerController._notify_heartbeat()'s docstring for why it's
        not just "fired on a successful load" -- that version could leave a
        Lab waiting forever if the Luminizer went idle with nothing left to
        load), so this always wakes up again within one Luminizer cycle to
        re-check _luminizer_is_idle() from scratch. Falls back to a short
        sleep if comms is unavailable or the wait itself errors.
        """
        if self.comms:
            try:
                self.comms.wait_broadcast("luminizer_heartbeat")
                return
            except Exception:
                pass
        sleep(0.5)

    def step(self):
        outpost = self.machine.outpost
        is_home = is_home_outpost(outpost)
        luminizer = local_sibling(outpost, "bio_luminizer")
        luminizer_idle = _luminizer_is_idle(luminizer)

        if luminizer_idle:
            if not self.drain_output():
                return
        # else: leave whatever's in Lab output staged -- the Luminizer isn't
        # ready for it yet -- and fall through to analyze/extract below,
        # which keep working on whatever's already in the chamber.

        specimen = self.machine.specimen

        if specimen is None:
            # Clear unwanted input reagents
            if self.machine.input.count() > 0:
                for stack in self.machine.input.stacks():
                    try:
                        destination = best_unload_target(stack.id, stack.count, outpost=outpost)
                        self.machine.input.eject(destination, stack.id, stack.count)
                    except Exception:
                        pass

            if not luminizer_idle:
                self._wait_for_luminizer()
                return

            # Pull specimen from collector cargo -- must be this Lab's own
            # outpost's Collector (take_from() requires same-outpost source).
            collector = local_sibling(outpost, "bio_collector")
            if collector and collector.cargo is not None:
                t_res = self.machine.take_from(collector)
                if t_res.status == "ok":
                    print(f"[{self.name}] Transferred specimen from collector to lab chamber.")
            sleep(0.5)
            return

        # Stage 1: Analyze
        if specimen.stage == "collected":
            print(f"[{self.name}] Analyzing specimen...")
            a_res = self.machine.analyze()
            if a_res.status == "ok":
                print(f"[{self.name}] Analyzed: {a_res.info.name} ({a_res.info.fragment_id}). Recipe: {a_res.info.required_recipe}")
                try:
                    def update_recipes(curr):
                        d = dict(curr or {})
                        d[a_res.info.fragment_id] = {
                            "name": a_res.info.name,
                            "recipe": a_res.info.required_recipe,
                            "rarity": getattr(a_res.info, "rarity", "unknown")
                        }
                        return d
                    archive.transaction("bio.fragment_recipes", {}, update_recipes)
                except Exception:
                    pass
            sleep(0.5)
            return

        # Stage 2: Extract
        if specimen.stage == "analyzed":
            recipe = specimen.recipe or {}
            loaded = self.machine.loaded_reagents or {}

            # Unload wrong reagents
            mismatched = any(r not in recipe or q > recipe.get(r, 0) for r, q in loaded.items())
            if mismatched:
                print(f"[{self.name}] Unloading mismatched reagents...")
                self.machine.unload_reagents()
                sleep(0.5)
                return

            # Check and load input buffer reagents
            if self.machine.input.count() > 0:
                for stack in self.machine.input.stacks():
                    needed = recipe.get(stack.id, 0) - loaded.get(stack.id, 0)
                    if needed > 0:
                        load_qty = min(stack.count, needed)
                        self.machine.load(stack.id, load_qty)
                    else:
                        try:
                            destination = best_unload_target(stack.id, stack.count, outpost=outpost)
                            self.machine.input.eject(destination, stack.id, stack.count)
                        except Exception:
                            pass
                sleep(0.5)
                return

            # Load missing reagents: from local stock, buying the shortfall only when
            # this Lab is at home (a remote Lab can't have the Shop deliver to it --
            # see run_haul_loop() for how a remote Lab gets restocked).
            needs_loading = False
            for reagent_id, req_qty in recipe.items():
                curr_qty = loaded.get(reagent_id, 0)
                missing = req_qty - curr_qty
                if missing > 0:
                    needs_loading = True
                    local_have = local_stock(reagent_id, outpost)
                    if local_have < missing:
                        if is_home and self.shop:
                            buy_qty = missing - local_have
                            buy_res = self.shop.buy(reagent_id, buy_qty)
                            if buy_res.status == "ok":
                                print(f"[{self.name}] Purchased {buy_qty}x {reagent_id} from shop.")
                            else:
                                sleep(1.0)
                                break
                        else:
                            print(f"[{self.name}] Waiting on {reagent_id} resupply ({local_have}/{missing} on hand locally).")
                            sleep(2.0)
                            break

                    moved = take_item(self.machine.input, reagent_id, missing, outpost=outpost)
                    if moved > 0:
                        self.machine.load(reagent_id, moved)
                    sleep(0.5)
                    break

            if not needs_loading:
                print(f"[{self.name}] Extracting sample for {specimen.fragment_id}...")
                ext_res = self.machine.extract()
                if ext_res.status == "ok":
                    sample_id = specimen.fragment_id
                    print(f"[{self.name}] Extracted sample: {sample_id}!")
                    if not luminizer_idle:
                        self._wait_for_luminizer()
                        return
                    if not self.drain_output():
                        return

                    # Notify Exchange over Signal Bus for immediate delivery
                    if self.comms:
                        try:
                            self.comms.send("sample_ready", {"sample_id": sample_id})
                        except Exception:
                            pass

    def run(self):
        print(f"Bio Lab ({self.name}) online via Shared Library & Signal Bus.")
        while True:
            self.step()
            sleep(0.5)


class BioCollectorController:
    """
    Gathers specimens matching active demands broadcast over Signal Bus.
    Prevents over-harvesting:
    - Never harvests fragments already sufficient in local storage/deliveries.
    - Caps uncataloged harvests if local storage already holds ample samples.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_collector")
        self.comms = get_component("comms")
        self.pending_analysis = set()

    def coord_key(self, c):
        return (round(c[0], 2), round(c[1], 2))

    def step(self):
        if self.machine.cargo is not None:
            sleep(0.5)
            return

        outpost = self.machine.outpost
        my_biome = get_my_biome(self.machine)
        exchange = local_sibling(outpost, "bio_exchange")

        # Fetch exchange.orders() and walk local storage exactly ONCE per
        # step(), not once per fragment -- see _focus_coastal_order()'s and
        # _local_stock_snapshot()'s docstrings: re-fetching/re-walking per
        # fragment (~20-30 of them) measured at ~20s, then still ~8s/cycle
        # even after caching orders() alone, from the storage walk.
        orders = []
        current_order = None
        snapshot = _local_stock_snapshot(outpost)
        if exchange:
            try:
                orders = exchange.orders()
            except Exception:
                orders = []
            current_order = _focus_coastal_order(orders, snapshot, my_biome)
        preferred_fragments = set((current_order.requires or {}).keys()) if current_order else set()

        # Coarse safety net, NOT the primary flow control (that's
        # BioLabController's Luminizer-idle gate, see _luminizer_is_idle()):
        # in a healthy pipeline this should basically never trip, since the
        # Lab won't hand off/drain faster than the Luminizer can keep up.
        # Kept cheap on purpose -- reads the already-built snapshot's glow
        # totals rather than re-scanning anything.
        if _total_glow_artifacts(snapshot) >= MAX_LOCAL_GLOW_ARTIFACTS:
            sleep(1.0)
            return

        # 1. Determine demand from Signal Bus broadcast or local query
        needed_fragments = set()
        demands = None
        if self.comms:
            try:
                # latest(channel) -> Any: returns the raw broadcast() payload
                # directly (or None), NOT a status-wrapped ActionResult --
                # there's no .status/.broadcast to check here (confirmed live:
                # that always raised AttributeError, silently swallowed below,
                # so this branch never actually ran; the Collector was always
                # falling back to the single active_order() branch instead,
                # which is unstable).
                broadcast = self.comms.latest("bio_orders")
                if isinstance(broadcast, dict):
                    demands = broadcast.get("local_demands", {})
            except Exception:
                pass

        if demands is not None:
            for frag_id, count_needed in demands.items():
                if _snapshot_stock(snapshot, frag_id) < count_needed:
                    needed_fragments.add(frag_id)
        elif exchange:
            active = exchange.active_order()
            if active and is_local_order(active, my_biome) and is_order_incomplete(active):
                for frag_id, count_needed in active.requires.items():
                    deliv = active.delivered.get(frag_id, 0)
                    in_tr = active.in_transit.get(frag_id, 0)
                    stock = _snapshot_stock(snapshot, frag_id)
                    if deliv + in_tr + stock < count_needed:
                        needed_fragments.add(frag_id)

        # 2. Scan local biome
        locations = self.machine.scan()
        if not locations:
            sleep(2.0)
            return

        for loc in locations:
            if loc.cataloged:
                self.pending_analysis.discard(self.coord_key(loc.coords))

        target_coords = None

        # Priority 1: Collect what is actively needed by local orders --
        # prefer the current/focus order's own fragments first, falling back
        # to any other incomplete order's fragment if none of those are
        # discoverable nearby right now.
        if needed_fragments:
            for loc in locations:
                if loc.cataloged and loc.fragment_id in needed_fragments and loc.fragment_id in preferred_fragments:
                    target_coords = loc.coords
                    print(f"[{self.name}] Harvesting needed specimen (current order): {loc.fragment_id} at {loc.coords}")
                    break
            if target_coords is None:
                for loc in locations:
                    if loc.cataloged and loc.fragment_id in needed_fragments:
                        target_coords = loc.coords
                        print(f"[{self.name}] Harvesting needed specimen (other order): {loc.fragment_id} at {loc.coords}")
                        break

        # Priority 2: Uncataloged discovery (strictly throttled)
        if target_coords is None:
            lab = local_sibling(outpost, "bio_lab")
            lab_busy = (lab and lab.specimen is not None and lab.specimen.stage == "collected")
            if not lab_busy:
                for loc in locations:
                    if not loc.cataloged and self.coord_key(loc.coords) not in self.pending_analysis:
                        target_coords = loc.coords
                        self.pending_analysis.add(self.coord_key(loc.coords))
                        print(f"[{self.name}] Harvesting uncataloged fragment at {loc.coords} (discovery)")
                        break

        if target_coords:
            res = self.machine.collect(target_coords)
            if res.status != "ok":
                self.pending_analysis.discard(self.coord_key(target_coords))
                sleep(1.0)
        else:
            # Idle cleanly
            sleep(2.0)

    def run(self):
        print(f"Bio Collector ({self.name}) online via Shared Library & Signal Bus.")
        while True:
            self.step()


class BioLuminizerController:
    """
    Tints a raw coastal sample's glow to match the local Bio Exchange's active order
    (BioOrder.target_glow) via a 3x3 lamp-mix solve (docs/components/bio_luminizer.md),
    then infuses it for delivery. A sample whose fragment doesn't need tinting (no
    active coastal order requiring it) is passed through unchanged via discard().
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_luminizer")
        self.comms = get_component("comms")
        self._lamp_matrix = None  # (red_sig, green_sig, blue_sig) -- fixed hardware, read once

    def _lamp_matrix_cols(self):
        if self._lamp_matrix is None:
            red = self.machine.lamp_signature("red")
            green = self.machine.lamp_signature("green")
            blue = self.machine.lamp_signature("blue")
            if red and green and blue:
                self._lamp_matrix = (red, green, blue)
        return self._lamp_matrix

    def _find_coastal_order(self, orders, snapshot, fragment_id=None):
        """
        Finds an incomplete, local, glow-requiring order -- optionally one that
        specifically requires fragment_id. Deliberately NOT
        exchange.active_order(): that's a single shared, mutable pointer
        BioExchangeController.sweep_and_deliver() freely reassigns to whatever
        order it's currently delivering ANY matching sample to (coastal or
        not) as part of its own aggressive multi-order sweep. Reading it here
        would make the Luminizer's tint target flap to whatever unrelated
        order the Exchange's sweep last happened to select, not the coastal
        order that actually needs this fragment.

        Takes an already-fetched `orders` list -- step() fetches
        exchange.orders() exactly once per cycle and threads it through every
        helper below, instead of each one fetching its own fresh ~80-order
        copy (measured live: that pattern cost ~20s/cycle in
        BioCollectorController before the same fix was applied there -- see
        module-level _focus_coastal_order()'s docstring).

        Delegates to the module-level _focus_coastal_order() -- shared with
        BioCollectorController's own harvest preference so both controllers
        concentrate on the SAME order at the same time, rather than the
        Collector gathering for orders the Luminizer isn't even working on
        yet. See _focus_coastal_order()'s docstring for the full "prefer
        stock we already have" reasoning and the live deadlock this also
        incidentally used to cause (an untouched fragment stuck staged in
        the Luminizer's own latched input while a different order was
        selected -- self.input holds one item id at a time until
        load()/flush() clears it).
        """
        my_biome = get_my_biome(self.machine)
        return _focus_coastal_order(orders, snapshot, my_biome, fragment_id)

    def _fragment_remaining(self, order, fragment_id, snapshot):
        """Units of fragment_id this order still needs, net of what's already
        correctly tinted for it. Delegates to the module-level
        _order_fragment_remaining() -- shared with _focus_coastal_order()'s
        own "does this order still genuinely need this fragment" check."""
        return _order_fragment_remaining(order, fragment_id, snapshot)

    def _active_target_for(self, orders, snapshot, fragment_id):
        order = self._find_coastal_order(orders, snapshot, fragment_id)
        if not order:
            return None
        return getattr(order, "target_glow", None)

    def _order_matching_glow(self, orders, fragment_id, glow):
        """Incomplete local order requiring fragment_id whose target_glow exactly
        equals `glow`, or None. Used to tell "already correctly tinted, just
        needs delivering" apart from "still raw, needs (re-)tinting". Takes an
        already-fetched `orders` list -- see _find_coastal_order()'s docstring."""
        if not glow:
            return None
        my_biome = get_my_biome(self.machine)
        for order in orders:
            if not is_order_incomplete(order):
                continue
            if not is_local_order(order, my_biome):
                continue
            if fragment_id not in (order.requires or {}):
                continue
            target = getattr(order, "target_glow", None)
            if target and list(target) == list(glow):
                return order
        return None

    def _find_raw_stack(self, orders, fragment_id, outpost):
        """
        (source_id, properties, count) for the first locally-staged
        fragment_id stack that is NOT already correctly tinted for some
        current local order -- i.e. genuinely raw and safe to pull in for
        tinting. Never returns an already-finished stack (one whose glow
        exactly matches a live order's target_glow): that one just needs
        delivering, not re-tinting, and storage.take_item()'s property-blind
        take() could otherwise grab it by chance instead of raw material.
        Takes an already-fetched `orders` list -- see _find_coastal_order()'s
        docstring.
        """
        for source_id, component in _local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception:
                continue
            for stack in stacks:
                if getattr(stack, "id", None) != fragment_id:
                    continue
                count = getattr(stack, "count", 0)
                if count <= 0:
                    continue
                properties = getattr(stack, "properties", None) or {}
                glow = properties.get("glow")
                if glow and self._order_matching_glow(orders, fragment_id, glow):
                    continue  # already correctly tinted -- leave it for delivery
                return source_id, properties, count
        return None

    def _notify_heartbeat(self):
        """
        Broadcasts once every step() cycle, regardless of what that cycle
        did. BioLabController waits on this (via comms.wait_broadcast())
        instead of busy-polling with sleep() while it holds off pulling its
        next specimen from the Collector / draining its own output -- see
        BioLabController._wait_for_luminizer()'s docstring.

        Deliberately unconditional, not just "fired after a successful
        load()": wait_broadcast() only satisfies on a broadcast published
        AFTER the call, so a signal that only fired on a successful load
        would never fire again once the Luminizer drained its last item with
        nothing staged behind it to load next -- including right at startup,
        before this Luminizer has ever loaded anything at all -- leaving a
        waiting Lab stuck forever even though the Luminizer had, in fact,
        gone idle. Firing every cycle instead means the Lab always wakes up
        again within one Luminizer step(), whatever state it's actually in.
        """
        if not self.comms:
            return
        try:
            self.comms.broadcast("luminizer_heartbeat", {"chamber_empty": self.machine.chamber is None})
        except Exception:
            pass

    def _load_next_sample(self, orders, snapshot):
        outpost = self.machine.outpost

        # self.input latches to whatever's already staged (e.g. left over
        # from an earlier interrupted cycle) until load()/flush() clears it.
        # Each staged stack is either already correctly tinted (a previous
        # infuse() succeeded, but it never got drained out before something
        # else got staged alongside it) -- in which case it doesn't belong in
        # the chamber again, it just needs ejecting to storage so the
        # Exchange can find and deliver it -- or genuinely raw, in which case
        # it's the next thing to load. Found live: loading an
        # already-correctly-glowing staged sample back into the chamber
        # leaves the Luminizer unable to do anything useful with it (it's
        # already at target, there's nothing left to solve for).
        staged_stacks = []
        if hasattr(self.machine.input, "stacks"):
            try:
                staged_stacks = self.machine.input.stacks()
            except Exception:
                staged_stacks = []

        raw_candidate = None
        for stack in staged_stacks:
            staged_id = getattr(stack, "id", None)
            count = getattr(stack, "count", 0)
            if not staged_id or count <= 0:
                continue
            properties = getattr(stack, "properties", None) or {}
            glow = properties.get("glow")

            if glow and self._order_matching_glow(orders, staged_id, glow):
                try:
                    destination = best_unload_target(staged_id, count, outpost=outpost)
                    self.machine.input.eject(destination, staged_id, count, properties, "exact")
                    print(f"[{self.name}] Ejected already-tinted {staged_id} (glow {glow}) to '{destination}' for delivery.")
                except Exception:
                    pass
                continue

            if raw_candidate is None:
                raw_candidate = (staged_id, properties)

        if raw_candidate:
            staged_id, properties = raw_candidate
            order = self._find_coastal_order(orders, snapshot, staged_id)
            if order and self._fragment_remaining(order, staged_id, snapshot) > 0:
                load_res = self.machine.load(staged_id, properties, "exact")
                if load_res.status == "ok":
                    print(f"[{self.name}] Loaded already-staged {staged_id} into chamber.")
                return
            # No current local order needs it any more -- recover it to
            # storage instead of leaving input stuck on dead material forever.
            try:
                count = self.machine.input.count()
                destination = best_unload_target(staged_id, count, outpost=outpost)
                self.machine.input.eject(destination, staged_id, count, properties, "exact")
                print(f"[{self.name}] Recovered stale staged {staged_id} to '{destination}' (no longer needed).")
            except Exception:
                pass
            return

        if staged_stacks:
            return  # everything staged this cycle was already-tinted and just got ejected above

        order = self._find_coastal_order(orders, snapshot)
        if not order:
            return

        for fragment_id in (order.requires or {}).keys():
            if self._fragment_remaining(order, fragment_id, snapshot) <= 0:
                continue
            found = self._find_raw_stack(orders, fragment_id, outpost)
            if not found:
                continue
            source_id, properties, _ = found
            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)
            take_res = self.machine.input.take(fragment_id, 1, properties, "exact")
            if take_res.status != "ok":
                continue
            load_res = self.machine.load(fragment_id, properties, "exact")
            if load_res.status == "ok":
                print(f"[{self.name}] Loaded {fragment_id} into chamber.")
            return

    def _try_lamps(self, r, g, b, target):
        if not (0 <= r <= 40 and 0 <= g <= 40 and 0 <= b <= 40):
            return False
        self.machine.set_lamps(r, g, b)
        current = self.machine.glow()
        if current is None or list(current) != list(target):
            return False
        self._commit_infuse(target)
        return True

    def _commit_infuse(self, target):
        res = self.machine.infuse()
        if res.status == "ok":
            print(f"[{self.name}] Infused sample at glow {target}.")
        elif res.status == "busy":
            sleep(0.2)

    def _solve_and_apply(self, target):
        matrix = self._lamp_matrix_cols()
        if not matrix:
            print(f"[{self.name}] Lamp signature unavailable this cycle.")
            return

        zero_res = self.machine.set_lamps(0, 0, 0)
        if zero_res.status != "ok":
            return
        base = self.machine.glow()
        if base is None:
            return

        delta = [target[i] - base[i] for i in range(3)]
        solved = _solve_3x3(matrix, delta)
        if solved is None:
            print(f"[{self.name}] Could not solve lamp mix for target {target} (singular lamp matrix).")
            return

        r, g, b = (max(0, min(40, round(v))) for v in solved)
        if self._try_lamps(r, g, b, target):
            return

        # Bounded local search over the +/-1-per-channel neighborhood for rounding
        # error -- cheap (<=27 combinations) and avoids trusting the rounded solve
        # blindly, without brute-forcing the full 41^3 space against the live game.
        for dr in (-1, 0, 1):
            for dg in (-1, 0, 1):
                for db in (-1, 0, 1):
                    if dr == 0 and dg == 0 and db == 0:
                        continue
                    if self._try_lamps(r + dr, g + dg, b + db, target):
                        return

        print(f"[{self.name}] WARNING: no exact lamp match found near ({r},{g},{b}) for target {target}.")

    def step(self):
        self._notify_heartbeat()
        drain_port_to_storage(self.machine.output, self.machine.outpost)

        outpost = self.machine.outpost
        exchange = local_sibling(outpost, "bio_exchange")

        # Fetch exchange.orders() and walk local storage exactly ONCE per
        # step(), not once per fragment -- see BioCollectorController.step()
        # for the perf history (~20s/cycle re-fetching orders(), then ~8s
        # re-walking storage per fragment even after caching orders() alone).
        orders = []
        if exchange:
            try:
                orders = exchange.orders()
            except Exception:
                orders = []
        snapshot = _local_stock_snapshot(outpost)

        chamber = self.machine.chamber
        if chamber is None:
            self._load_next_sample(orders, snapshot)
            sleep(0.5)
            return

        target = self._active_target_for(orders, snapshot, chamber.fragment_id)
        if not target:
            # No glow requirement for this fragment right now -- pass through unchanged.
            self.machine.discard()
            sleep(0.5)
            return

        self._solve_and_apply(target)

    def run(self):
        print(f"Bio Luminizer ({self.name}) online via Shared Library.")
        while True:
            self.step()
            sleep(0.5)


def _solve_3x3(matrix, b):
    """
    Solve M @ x = b for a 3x3 matrix `matrix` (columns = [red_sig, green_sig, blue_sig]
    triples, each a lamp's fixed per-unit RGB contribution) via Cramer's rule, pure
    Python (no numpy in this sandboxed environment). Returns [x0, x1, x2], or None if
    the matrix is singular (shouldn't happen -- lamp_signature() is documented fixed
    hardware with independent channels).
    """
    m = [[matrix[0][i], matrix[1][i], matrix[2][i]] for i in range(3)]  # rows

    def det3(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))

    d = det3(m)
    if d == 0:
        return None

    result = []
    for col in range(3):
        m_col = [row[:] for row in m]
        for row in range(3):
            m_col[row][col] = b[row]
        result.append(det3(m_col) / d)
    return result
