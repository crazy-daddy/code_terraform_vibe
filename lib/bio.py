# Shared Library for Biology Pipeline Automation
# Event-driven and Signal Bus aware coordination for Bio Collector, Bio Lab, and Bio Exchange.
from archive import archive

def get_my_biome(machine):
    if hasattr(machine, "outpost") and machine.outpost:
        return getattr(machine.outpost, "biome", None)
    return None

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


class BioExchangeController:
    """
    Manages Bio Orders, aggressive inventory sweeps, and sample deliveries.
    Broadcasting channel: 'bio_orders'
    Receiving channel: 'sample_ready'
    """
    def __init__(self, machine, sweep_delay=10.0):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_exchange")
        self.inv = get_component("inventory")
        self.comms = get_component("comms")
        self.sweep_delay = sweep_delay

        try:
            self.machine.input.connect("inventory")
            self.machine.output.connect("inventory")
        except Exception:
            pass

    def drain_output(self):
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                try:
                    self.machine.output.send(stack.id, stack.count)
                except Exception:
                    pass

    def clear_input(self):
        if self.machine.input.count() > 0:
            for stack in self.machine.input.stacks():
                try:
                    self.machine.input.eject("inventory", stack.id, stack.count)
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
        Aggressive Sweep: Iterates through inventory and delivers ANY sample
        matching ANY incomplete order (local OR foreign) to declutter inventory.
        """
        self.drain_output()
        self.clear_input()

        all_orders = self.machine.orders()
        delivered_count = 0

        print(f"[EXCHANGE] Starting sweep across {len(all_orders)} orders. Checking inventory...")

        # Diagnostic: print what biological samples we actually have in inventory
        inv_stacks = self.inv.stacks() if self.inv else []
        bio_stacks = [s for s in inv_stacks if "sample" in getattr(s, "category", "") or s.id.startswith(("st_", "ma_", "vc_", "bw_", "gw_", "oc_", "vd_", "mh_", "hs_", "ms_", "hc_", "gm_", "fs_", "sd_", "ce_", "vm_"))]
        if bio_stacks:
            stack_desc = ", ".join(f"{s.count}x {s.id}" for s in bio_stacks)
            print(f"[EXCHANGE] Inventory biological samples found: {stack_desc}")
        else:
            print("[EXCHANGE] No biological sample item stacks detected in inventory.")

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, count_needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                remaining_needed = count_needed - (deliv + in_tr)

                if remaining_needed <= 0:
                    continue

                available_in_inv = self.inv.count(item_id) if self.inv else 0
                if available_in_inv <= 0:
                    continue

                to_deliver = min(remaining_needed, available_in_inv)

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
                    take_res = self.machine.input.take(item_id, 1)
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
    Cleans latched inputs/outputs, auto-purchases missing reagents, and notifies
    the Signal Bus ('sample_ready') upon completing an extraction.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_lab")
        self.collector = get_component("bio_collector_1")
        self.shop = get_component("shop")
        self.inv = get_component("inventory")
        self.comms = get_component("comms")
        self.inventory_full_notified = False

        try:
            self.machine.input.connect("inventory")
            self.machine.output.connect("inventory")
        except Exception:
            pass

    def drain_output(self):
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                res_send = self.machine.output.send(stack.id, stack.count)
                if res_send.status == "ok":
                    print(f"[{self.name}] Sent {res_send.moved}x {stack.id} to inventory.")
                    self.inventory_full_notified = False
                elif res_send.status == "busy":
                    sleep(0.2)
                    return False
                elif res_send.status in ["target_full", "slots_full", "inventory_full"]:
                    self.handle_inventory_full()
                    return False
                else:
                    print(f"[{self.name}] Output notice: {res_send.status} - {res_send.message}")
                    sleep(0.5)
                    return False
        return True

    def handle_inventory_full(self):
        """Pause extraction while preserving the sample in the lab output."""
        if not self.inventory_full_notified:
            print(f"[{self.name}] WARNING: Base inventory is full. Free space to resume sample extraction.")
            try:
                notify(f"[{self.name}] Base Inventory Full! Free space to resume extraction.", level="warn", duration_seconds=8.0)
            except Exception:
                pass
            self.inventory_full_notified = True
        sleep(2.0)

    def step(self):
        if not self.drain_output():
            return

        specimen = self.machine.specimen

        if specimen is None:
            # Clear unwanted input reagents
            if self.machine.input.count() > 0:
                for stack in self.machine.input.stacks():
                    try:
                        self.machine.input.eject("inventory", stack.id, stack.count)
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
                            self.machine.input.eject("inventory", stack.id, stack.count)
                        except Exception:
                            pass
                sleep(0.5)
                return

            # Load missing reagents from inventory or shop
            needs_loading = False
            for reagent_id, req_qty in recipe.items():
                curr_qty = loaded.get(reagent_id, 0)
                missing = req_qty - curr_qty
                if missing > 0:
                    needs_loading = True
                    inv_stock = self.inv.count(reagent_id) if self.inv else 0
                    if inv_stock < missing:
                        buy_qty = missing - inv_stock
                        buy_res = self.shop.buy(reagent_id, buy_qty)
                        if buy_res.status == "ok":
                            print(f"[{self.name}] Purchased {buy_qty}x {reagent_id} from shop.")
                        else:
                            sleep(1.0)
                            break

                    take_res = self.machine.input.take(reagent_id, missing)
                    if take_res.status in ["ok", "partial"] and take_res.moved > 0:
                        self.machine.load(reagent_id, take_res.moved)
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
    - Never harvests fragments already sufficient in inventory/deliveries.
    - Caps uncataloged harvests if inventory already holds ample samples.
    """
    def __init__(self, machine):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_collector")
        self.exchange = get_component("bio_exchange_1")
        self.lab = get_component("bio_lab_1")
        self.inv = get_component("inventory")
        self.comms = get_component("comms")
        self.pending_analysis = set()

    def coord_key(self, c):
        return (round(c[0], 2), round(c[1], 2))

    def step(self):
        if self.machine.cargo is not None:
            sleep(0.5)
            return

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
                in_inv = self.inv.count(frag_id) if self.inv else 0
                if in_inv < count_needed:
                    needed_fragments.add(frag_id)
        elif self.exchange:
            active = self.exchange.active_order()
            if active and is_local_order(active, my_biome) and is_order_incomplete(active):
                for frag_id, count_needed in active.requires.items():
                    deliv = active.delivered.get(frag_id, 0)
                    in_tr = active.in_transit.get(frag_id, 0)
                    in_inv = self.inv.count(frag_id) if self.inv else 0
                    if deliv + in_tr + in_inv < count_needed:
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
