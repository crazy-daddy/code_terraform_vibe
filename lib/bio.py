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

def is_home_outpost(outpost):
    return getattr(outpost, "is_home", lambda: True)() if outpost else True

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
        self.collector = get_component("bio_collector_1")
        self.shop = get_component("shop")
        self.comms = get_component("comms")
        self.inventory_full_notified = False

    def drain_output(self):
        outpost = self.machine.outpost
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                target = best_unload_target(stack.id, stack.count, outpost=outpost)
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

    def step(self):
        if not self.drain_output():
            return

        outpost = self.machine.outpost
        is_home = is_home_outpost(outpost)
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

            # Pull specimen from collector cargo
            if self.collector and self.collector.cargo is not None:
                t_res = self.machine.take_from(self.collector)
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
        self.exchange = get_component("bio_exchange_1")
        self.lab = get_component("bio_lab_1")
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

        # 1. Determine demand from Signal Bus broadcast or local query
        needed_fragments = set()
        demands = None
        if self.comms:
            try:
                b_res = self.comms.latest("bio_orders")
                if b_res.status == "ok" and b_res.broadcast:
                    demands = b_res.broadcast.get("local_demands", {})
            except Exception:
                pass

        if demands is not None:
            for frag_id, count_needed in demands.items():
                if local_stock(frag_id, outpost) < count_needed:
                    needed_fragments.add(frag_id)
        elif self.exchange:
            active = self.exchange.active_order()
            if active and is_local_order(active, my_biome) and is_order_incomplete(active):
                for frag_id, count_needed in active.requires.items():
                    deliv = active.delivered.get(frag_id, 0)
                    in_tr = active.in_transit.get(frag_id, 0)
                    if deliv + in_tr + local_stock(frag_id, outpost) < count_needed:
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

        # Priority 1: Collect what is actively needed by local orders
        if needed_fragments:
            for loc in locations:
                if loc.cataloged and loc.fragment_id in needed_fragments:
                    target_coords = loc.coords
                    print(f"[{self.name}] Harvesting needed specimen: {loc.fragment_id} at {loc.coords}")
                    break

        # Priority 2: Uncataloged discovery (strictly throttled)
        if target_coords is None:
            lab_busy = (self.lab and self.lab.specimen is not None and self.lab.specimen.stage == "collected")
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
        self.exchange = get_component("bio_exchange_1")
        self._lamp_matrix = None  # (red_sig, green_sig, blue_sig) -- fixed hardware, read once

    def _lamp_matrix_cols(self):
        if self._lamp_matrix is None:
            red = self.machine.lamp_signature("red")
            green = self.machine.lamp_signature("green")
            blue = self.machine.lamp_signature("blue")
            if red and green and blue:
                self._lamp_matrix = (red, green, blue)
        return self._lamp_matrix

    def _active_target_for(self, fragment_id):
        if not self.exchange:
            return None
        order = self.exchange.active_order()
        if not order or not is_order_incomplete(order):
            return None
        if fragment_id not in (order.requires or {}):
            return None
        return getattr(order, "target_glow", None)

    def _load_next_sample(self):
        if not self.exchange:
            return
        order = self.exchange.active_order()
        if not order or not is_order_incomplete(order) or not getattr(order, "target_glow", None):
            return
        for fragment_id in (order.requires or {}).keys():
            moved = take_item(self.machine.input, fragment_id, 1, outpost=self.machine.outpost)
            if moved > 0:
                load_res = self.machine.load(fragment_id)
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
        drain_port_to_storage(self.machine.output, self.machine.outpost)

        chamber = self.machine.chamber
        if chamber is None:
            self._load_next_sample()
            sleep(0.5)
            return

        target = self._active_target_for(chamber.fragment_id)
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
