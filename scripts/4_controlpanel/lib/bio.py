# Shared Library for Biology Pipeline Automation
# Event-driven and Signal Bus aware coordination for the pipeline stages that are the
# same regardless of biome: Bio Collector, Bio Lab, and Bio Exchange. Outpost-aware
# throughout: these buildings started out home-only (hardcoded to "inventory"), but
# the pipeline can now be deployed at a remote outpost that has Warehouses only, no
# Inventory -- see docs/AI_CHEATSHEET.md and TODO.md Phase 4.
#
# The one biome-specific step -- Coastal glow-tinting, Volcanic forge-casting, Deep
# QC conditioning, Geothermal gene-splicing, or nothing at all for Frozen -- lives in
# its own bio_coastal.py/bio_volcanic.py/bio_deep.py/bio_geothermal.py module, each
# subclassing bio_processor.py's BioProcessorController and importing the shared
# helpers from bio_orders.py. This module never imports any of them (see
# bio_orders.local_biome_processor()'s docstring for why that would be circular); only each
# biome's thin entrypoint script imports its own controller directly.
import cash
import outpost_reagents
from archive import archive
from bio_orders import MAX_LOCAL_BIO_ARTIFACTS, bio_demand_totals, find_matching_stack, focus_local_order, get_my_biome, is_local_order, is_order_incomplete, item_category, local_biome_processor, local_sibling, local_sources, local_stock, local_stock_snapshot, processor_fragment_preference, processor_is_idle, snapshot_stock, total_demanded_artifacts  # fmt: skip
from bio_retire import retire_pass
from storage import outpost_is_home
from storage_unload import best_unload_target, drain_port_to_storage, eject_unneeded, send_stack
from storage_take import take_item
from swallow import swallowed
from tree_console import TreeConsole, flush_all, reset_all
from version_guard import validate_game_version


class BioExchangeController:
    """
    Manages Bio Orders, aggressive inventory sweeps, and sample deliveries.
    Receiving channel: 'sample_ready'
    """

    def __init__(self, machine: "BioExchange", sweep_delay=10.0):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_exchange")
        self.comms = get_component("comms")
        self.sweep_delay = sweep_delay
        self.log = TreeConsole(module="bio")

    def drain_output(self):
        drain_port_to_storage(self.machine.output, self.machine.outpost)

    def clear_input(self):
        if self.machine.input.count() > 0:
            eject_unneeded(self.machine.input, (), outpost=self.machine.outpost)

    def _required_fragment_ids(self, all_orders):
        """Every fragment item id genuinely still needed (remaining > 0, net of
        delivered + in-transit) by any incomplete order anywhere -- local or
        foreign. sweep_and_deliver()'s own delivery loop above already ships a
        matching sample to ANY such order regardless of locality, so "needed by
        nothing" for _cleanup_orphaned_artifacts() has to mean nothing here, not
        just nothing local."""
        required = set()
        for order in all_orders:
            if not is_order_incomplete(order):
                continue
            requires = getattr(order, "requires", {}) or {}
            delivered = getattr(order, "delivered", {}) or {}
            in_transit = getattr(order, "in_transit", {}) or {}
            for item_id, needed in requires.items():
                remaining = needed - delivered.get(item_id, 0) - in_transit.get(item_id, 0)
                if remaining > 0:
                    required.add(item_id)
        return required

    def _is_bio_sample(self, item_id, properties, all_orders):
        """True if item_catalog classifies item_id as "biology_sample" -- the only
        reliable test, since Deep samples carry no properties at all and would
        otherwise be indistinguishable from iron_ore or a reagent. Cached per id
        (static metadata). Falls back to "has properties, or some Bio Order has
        ever required this id" only if the catalog is unavailable/doesn't know it."""
        category = None
        try:
            category = item_category(item_id)
        except Exception as error:
            swallowed("bio.BioExchangeController._is_bio_sample: item_category", error)
        if category is not None:
            return category == "biology_sample"
        self.log.debug(f"[EXCHANGE] item_catalog has no category for {item_id} -- falling back to properties/order-requires heuristic.")
        if properties:
            return True
        return any(item_id in (getattr(order, "requires", {}) or {}) for order in all_orders)

    def _cleanup_orphaned_artifacts(self, all_orders):
        """
        Destroys locally-staged property-tagged bio samples (raw or already
        processed) of a fragment type that no order anywhere still needs any of. The
        delivery loop above only ever ships a matching sample toward an order that
        still wants it, so a fragment type nothing wants any more -- its one
        requesting order already completed, or it was only ever picked up via
        BioCollectorController's "uncataloged discovery" harvesting -- has no path
        back out of local storage; it just sits there forever. Left alone, that dead
        stock counts against MAX_LOCAL_BIO_ARTIFACTS (lib/bio_orders.py) exactly like live
        in-flight stock, so a handful of orphaned samples permanently wedges the
        Collector into refusing to harvest ANYTHING further, needed or not (see
        BioLabController.step()'s demand-gated extract() for the other half:
        stopping this from building up going forward).

        Matches on item id only, not exact properties -- a raw, not-yet-processed
        sample never matches any order's exact requirement (that's the whole point
        of the biome processor), so gating on exact properties would misclassify
        perfectly good raw stock waiting to be processed as orphaned and destroy it.

        A stack counts as a bio sample by item_catalog category (_is_bio_sample()),
        not by carrying properties -- Deep samples are propertyless, and gating on
        properties alone let finished orders' leftovers pile up one-per-Warehouse-slot
        until the outpost jammed.
        """
        self.log.start("[EXCHANGE] _cleanup_orphaned_artifacts", level="debug")
        outpost = self.machine.outpost
        required = self._required_fragment_ids(all_orders)
        self.log.trace(f"entry, {len(required)} fragment id(s) still required across {len(all_orders)} orders")
        cleaned = 0
        for source_id, component in local_sources(outpost):
            if not component or not hasattr(component, "stacks"):
                continue
            try:
                stacks = component.stacks()
            except Exception as error:
                swallowed("bio.BioExchangeController._cleanup_orphaned_artifacts: component.stacks", error)
                continue
            for stack in stacks:
                item_id = getattr(stack, "id", None)
                count = getattr(stack, "count", 0)
                properties = getattr(stack, "properties", None) or None
                if not item_id or count <= 0:
                    continue
                if item_id in required:
                    continue
                if not self._is_bio_sample(item_id, properties, all_orders):
                    continue
                if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                    self.machine.input.connect(source_id)
                # None + "exact" selects propertyless items only (docs/components/bio_conditioner.md load()).
                take_res = self.machine.input.take(item_id, count, properties, "exact")
                if getattr(take_res, "moved", 0) <= 0:
                    self.log.debug(f"[EXCHANGE] Could not take orphaned {item_id} from '{source_id}': {getattr(take_res, 'status', '?')} - {getattr(take_res, 'message', '')}")
                if getattr(take_res, "moved", 0) > 0:
                    flush_res = self.machine.input.flush()
                    cleaned += getattr(flush_res, "moved", count)
                    self.log.debug(f"[EXCHANGE] Flushed {getattr(flush_res, 'moved', count)}x orphaned {item_id} (properties {properties}) from '{source_id}' -- no order needs this fragment.")
        self.log.trace(f"exit, flushed {cleaned} orphaned unit(s) total.")
        self.log.end()

    def sweep_and_deliver(self):
        """
        Aggressive Sweep: Iterates local storage (home Inventory, or this outpost's
        Warehouses if remote) and delivers ANY sample matching ANY incomplete order
        (local OR foreign) to declutter it. Only takes a stack whose exact properties
        satisfy matches_order() -- required for biomes like Coastal, where a sample
        only counts if its glow matches the order's target_glow exactly, not just the
        right fragment id.
        """
        self.drain_output()
        self.clear_input()

        outpost = self.machine.outpost
        all_orders = self.machine.orders()
        delivered_count = 0

        self.log.debug(f"[EXCHANGE] Starting sweep across {len(all_orders)} orders. Checking local storage...")

        for ord_info in all_orders:
            if not is_order_incomplete(ord_info):
                continue

            for item_id, count_needed in ord_info.requires.items():
                deliv = ord_info.delivered.get(item_id, 0)
                in_tr = ord_info.in_transit.get(item_id, 0)
                remaining_needed = count_needed - (deliv + in_tr)

                if remaining_needed <= 0:
                    self.log.debug(f"[EXCHANGE] {ord_info.id} already satisfied for {item_id} (needed={count_needed} delivered={deliv} in_transit={in_tr}) -- skipping.")
                    continue

                available = local_stock(item_id, outpost)
                if available <= 0:
                    self.log.debug(f"[EXCHANGE] {ord_info.id} still needs {remaining_needed}x {item_id} but 0 available locally -- skipping.")
                    continue

                to_deliver = min(remaining_needed, available)
                self.log.debug(f"[EXCHANGE] {ord_info.id}: remaining_needed={remaining_needed} available={available} -> will attempt to_deliver={to_deliver}x {item_id}.")

                # Switch active order to deliver matching items
                active = self.machine.active_order()
                if active is None or active.id != ord_info.id:
                    set_res = self.machine.set_order(ord_info.id)
                    if set_res.status != "ok":
                        self.log.level("warn").print(f"[EXCHANGE] Failed to set order {ord_info.id}: {set_res.status} - {set_res.message}")
                        continue
                    biome_tag = getattr(ord_info, "biome", "order")
                    self.log.print(f"[EXCHANGE] Switched to {ord_info.id} ({ord_info.name} - {biome_tag}) to deliver {to_deliver}x {item_id}")

                self.log.start(f"[EXCHANGE] Delivering up to {to_deliver}x {item_id} -> {ord_info.id}")
                delivered = self._deliver_units(ord_info, item_id, to_deliver, outpost)
                delivered_count += delivered
                self.log.end(f"[EXCHANGE] {ord_info.id}: delivered {delivered}x {item_id}")

        self.drain_output()
        self.clear_input()
        self._cleanup_orphaned_artifacts(all_orders)

        if delivered_count > 0:
            self.log.print(f"[EXCHANGE] Sweep finished: delivered {delivered_count} sample(s).")

        self._select_default_order(all_orders)

    def _deliver_units(self, ord_info, item_id, to_deliver, outpost):
        """Delivers up to to_deliver matching samples to the active order one at a time; returns how many went in."""
        delivered = 0
        for _ in range(to_deliver):
            self.drain_output()

            match = find_matching_stack(self.machine, item_id, outpost)
            if not match:
                self.log.debug(f"[EXCHANGE] No locally-staged {item_id} variant currently satisfies this order.")
                break
            source_id, properties = match

            if hasattr(self.machine.input, "connected_id") and self.machine.input.connected_id() != source_id:
                self.machine.input.connect(source_id)

            take_res = self.machine.input.take(item_id, 1, properties, "exact")
            if take_res.status != "ok":
                self.log.level("warn").print(f"[EXCHANGE] Take {item_id} status: {take_res.status} - {take_res.message}")
                if take_res.status == "target_wrong_material":
                    self.clear_input()
                break

            deliv_res = self.machine.deliver()
            while deliv_res.status == "busy":
                flush_all()
                sleep(0.2)
                deliv_res = self.machine.deliver()

            if deliv_res.status not in ["ok", "complete"]:
                self.log.level("error").print(f"[EXCHANGE] Deliver error: {deliv_res.status} - {deliv_res.message}")
                break
            delivered += 1
            self.log.print(f"[EXCHANGE] Delivered 1x {item_id} -> {ord_info.id} ({ord_info.name}) (Status: {deliv_res.status})")
            if deliv_res.status == "complete":
                self._on_order_complete(ord_info)
        return delivered

    def _on_order_complete(self, ord_info):
        """Announces a completed order and records its id in the archive."""
        reward_str = f" (+{ord_info.reward} credits)" if getattr(ord_info, "reward", 0) else ""
        try:
            notify(f"[Bio Order Complete] {ord_info.name}{reward_str}!", level="info", duration_seconds=10.0)
        except Exception as error:
            swallowed("bio.BioExchangeController.sweep_and_deliver: notify", error)
        order_id = ord_info.id
        try:
            archive.transaction("bio.completed_orders", [], lambda lst: lst if order_id in lst else lst + [order_id])
        except Exception as error:
            swallowed("bio.BioExchangeController.sweep_and_deliver: archive.transaction", error)

    def _select_default_order(self, all_orders):
        """Selects a local incomplete order for ongoing collection unless the active one already is."""
        my_biome = get_my_biome(self.machine)
        active = self.machine.active_order()
        if active is None or not is_order_incomplete(active) or not is_local_order(active, my_biome):
            for ord_info in all_orders:
                if is_order_incomplete(ord_info):
                    if is_local_order(ord_info, my_biome):
                        self.machine.set_order(ord_info.id)
                        self.log.print(f"[EXCHANGE] Set default local order: {ord_info.id} ({ord_info.name})")
                        break

    def run(self):
        self.log.print(f"Bio Exchange ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            reset_all()
            if retire_pass(self.machine, "bio_exchange"):
                continue
            self.sweep_and_deliver()

            # Wait for either the next sweep interval OR an instant 'sample_ready' signal from the lab
            if self.comms:
                try:
                    # Non-blocking check for instant delivery trigger
                    msg = self.comms.receive("sample_ready")
                    if msg.status == "ok" and msg.packet:
                        value = msg.packet.value
                        sample_id = value.get("sample_id") if isinstance(value, dict) else None  # type: ignore[union-attr]  # game isinstance stub does not narrow
                        self.log.print(f"[EXCHANGE] Received sample_ready event ({sample_id}), triggering immediate sweep!")
                        continue
                except Exception as error:
                    swallowed("bio.BioExchangeController.run: self.comms.receive", error)

            flush_all()
            sleep(self.sweep_delay)


class BioLabController:
    """
    Automates Analyze and Extract for the Bio Lab.
    Cleans latched inputs/outputs, auto-purchases missing reagents (home only --
    a remote Lab has no direct Shop delivery, so it publishes its reagent targets as
    pull requests, lib/outpost_reagents.py, for the Pioneer pull hauler homed there), and notifies
    the Signal Bus ('sample_ready') upon completing an extraction.
    """

    def __init__(self, machine: "BioLab"):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_lab")
        self.shop = get_component("shop")
        self.comms = get_component("comms")
        self.inventory_full_notified = False
        self.log = TreeConsole(module="bio")

    def drain_output(self):
        outpost = self.machine.outpost
        if self.machine.output.count() > 0:
            for stack in self.machine.output.stacks():
                target = best_unload_target(stack.id, stack.count, outpost=outpost)
                if target is None:
                    self.log.debug(f"[{self.name}] No local storage has room for {stack.count}x {stack.id} -- leaving staged, retrying next cycle.")
                    return False  # no local storage has room -- leave staged, retry next cycle
                moved, status, message = send_stack(self.machine.output, stack.id, stack.count, target)
                if status == "ok":
                    self.log.print(f"[{self.name}] Sent {moved}x {stack.id} to '{target}'.")
                    self.inventory_full_notified = False
                elif status == "busy":
                    flush_all()
                    sleep(0.2)
                    return False
                elif status in ["target_full", "slots_full", "inventory_full"]:
                    self.handle_storage_full()
                    return False
                else:
                    self.log.level("warn").print(f"[{self.name}] Output notice: {status} - {message}")
                    flush_all()
                    sleep(0.5)
                    return False
        return True

    def handle_storage_full(self):
        """Pause extraction while preserving the sample in the lab output."""
        if not self.inventory_full_notified:
            self.log.level("warn").print(f"[{self.name}] WARNING: local storage is full. Free space to resume sample extraction.")
            try:
                notify(f"[{self.name}] Storage Full! Free space to resume extraction.", level="warn", duration_seconds=8.0)
            except Exception as error:
                swallowed("bio.BioLabController.handle_storage_full: notify", error)
            self.inventory_full_notified = True
        flush_all()
        sleep(2.0)

    def _wait_for_processor(self):
        """
        Blocks until the local biome processor's next heartbeat broadcast, instead
        of busy-polling with sleep() while this Lab holds off pulling its next
        specimen from the Collector or draining its own extracted output -- see
        processor_is_idle()'s docstring for why that gate exists. The heartbeat
        fires once every processor step() cycle regardless of what that cycle did
        (see each processor controller's own _notify_heartbeat()-equivalent
        docstring for why it's not just "fired on a successful load" -- that version
        could leave a Lab waiting forever if the processor went idle with nothing
        left to load), so this always wakes up again within one processor cycle to
        re-check processor_is_idle() from scratch. Falls back to a short sleep if
        comms is unavailable or the wait itself errors.
        """
        self.log.start(f"[{self.name}] _wait_for_processor", level="debug")
        self.log.trace("entry, waiting on 'biome_processor_heartbeat'")
        if self.comms:
            try:
                flush_all()
                self.comms.wait_broadcast("biome_processor_heartbeat")
                self.log.trace("exit, heartbeat received")
                self.log.end()
                return
            except Exception:
                self.log.trace("wait_broadcast errored -- falling back to sleep(0.5)")
        flush_all()
        sleep(0.5)
        self.log.end()

    def step(self):
        outpost = self.machine.outpost
        is_home = outpost_is_home(outpost)
        processor, processor_type = local_biome_processor(outpost)
        processor_idle = processor_is_idle(processor, processor_type)
        self.log.trace(f"[{self.name}] step: entry, is_home={is_home} processor_type={processor_type} processor_idle={processor_idle} specimen_present={self.machine.specimen is not None}")

        if not is_home:
            # Remote Lab: keep its reagent targets published as buyable pull
            # requests for the Pioneer hauler homed here (throttled inside).
            try:
                outpost_reagents.publish_reagent_requests(outpost)
            except Exception as error:
                swallowed("bio.BioLabController.step: publish_reagent_requests", error)

        if processor_idle:
            if not self.drain_output():
                return
        # else: leave whatever's in Lab output staged -- the local biome processor
        # isn't ready for it yet -- and fall through to analyze/extract below, which
        # keep working on whatever's already in the chamber.

        specimen = self.machine.specimen
        if specimen is None:
            self._fill_empty_chamber(outpost, processor_idle)
        elif specimen.stage == "collected":
            self._analyze()
        elif specimen.stage == "analyzed":
            self._prepare_and_extract(specimen, outpost, is_home, processor_idle)

    def _pause(self, sec):
        flush_all()
        sleep(sec)

    def _fill_empty_chamber(self, outpost, processor_idle):
        """Empty chamber: clears stray input reagents, then pulls the next specimen from the Collector once the processor is idle."""
        # Clear unwanted input reagents
        if self.machine.input.count() > 0:
            eject_unneeded(self.machine.input, (), outpost=outpost)

        if not processor_idle:
            self._wait_for_processor()
            return

        # Pull specimen from collector cargo -- must be this Lab's own
        # outpost's Collector (take_from() requires same-outpost source).
        collector = local_sibling(outpost, "bio_collector")
        if collector and collector.cargo is not None:
            t_res = self.machine.take_from(collector)
            if t_res.status == "ok":
                self.log.print(f"[{self.name}] Transferred specimen from collector to lab chamber.")
            else:
                self.log.debug(f"[{self.name}] take_from(collector) -> {t_res.status}: {getattr(t_res, 'message', '')}")
        else:
            self.log.debug(f"[{self.name}] No specimen to pull -- collector={'none' if not collector else 'found'} cargo={'empty' if not collector or collector.cargo is None else 'present'}.")
        self._pause(0.5)

    def _analyze(self):
        """Stage 1: analyzes the collected specimen and records its fragment recipe in the archive."""
        self.log.start(f"[{self.name}] Analyzing specimen...")
        a_res = self.machine.analyze()
        if a_res.status == "ok":
            info = a_res.info
            assert info is not None
            try:

                def update_recipes(curr):
                    d = dict(curr or {})
                    d[info.fragment_id] = {"name": info.name, "recipe": info.required_recipe, "rarity": getattr(info, "rarity", "unknown")}
                    return d

                archive.transaction("bio.fragment_recipes", {}, update_recipes)
            except Exception as error:
                swallowed("bio.BioLabController.step: archive.transaction", error)
            self.log.end(f"[{self.name}] Analyzed: {info.name} ({info.fragment_id}). Recipe: {info.required_recipe}")
        else:
            self.log.end(f"[{self.name}] analyze() -> {a_res.status}")
        self._pause(0.5)

    def _prepare_and_extract(self, specimen, outpost, is_home, processor_idle):
        """Stage 2: discards an unneeded specimen, else fixes the loaded reagents one step per tick and extracts once the recipe is loaded."""
        fragment_id = specimen.fragment_id
        assert fragment_id is not None  # set once analyze() succeeds
        loaded = self.machine.loaded_reagents or {}

        if not loaded and self._discard_if_unneeded(fragment_id, outpost):
            return

        recipe = specimen.recipe or {}

        # Unload wrong reagents
        mismatched = any(r not in recipe or q > recipe.get(r, 0) for r, q in loaded.items())
        if mismatched:
            self.log.debug(f"[{self.name}] Reagent mismatch vs recipe {recipe} -- loaded={loaded}. Unloading mismatched reagents...")
            self.machine.unload_reagents()
            self._pause(0.5)
            return

        # Check and load input buffer reagents
        if self.machine.input.count() > 0:
            self._load_input_buffer(recipe, loaded, outpost)
            return

        # Load missing reagents: from local stock, buying the shortfall only when
        # this Lab is at home (a remote Lab can't have the Shop deliver to it;
        # its pull requests bring reagents in, see publish_reagent_requests()).
        # One reagent per tick.
        for reagent_id, req_qty in recipe.items():
            curr_qty = loaded.get(reagent_id, 0)
            if req_qty - curr_qty > 0:
                self._load_missing_reagent(reagent_id, req_qty, curr_qty, outpost, is_home)
                return

        self.log.start(f"[{self.name}] Extracting sample for {specimen.fragment_id}...")
        outcome = self._extract_specimen(specimen, processor_idle)
        self.log.end(f"[{self.name}] Extract {outcome}")

    def _discard_if_unneeded(self, fragment_id, outpost):
        """
        Discards the chamber specimen instead of extracting it when no local
        order still needs more of this fragment; returns True if it did.

        See bio_demand_totals()'s docstring for why the Lab (not just the
        Collector) needs this check: the Collector's own "uncataloged
        discovery" harvesting picks up specimens purely to identify a new
        location/fragment, with no demand behind them at all. analyze()
        already cataloged the fragment either way, so discarding here loses
        nothing but the reagent/output cost of an extraction nothing would
        ever collect. Unreadable orders (no Exchange, or orders() raised)
        skip the gate rather than discard on missing data.
        """
        orders = None
        exchange = local_sibling(outpost, "bio_exchange")
        if exchange:
            try:
                orders = exchange.orders()
            except Exception as error:
                swallowed("bio.BioLabController.step: exchange.orders", error)
        if orders is None:
            return False
        demand_totals = bio_demand_totals(orders, get_my_biome(self.machine))
        if demand_totals.get(fragment_id, 0) > local_stock(fragment_id, outpost):
            return False
        self.log.debug(f"[{self.name}] {fragment_id} not needed by any order -- discarding instead of extracting.")
        self.machine.discard()
        self._pause(0.5)
        return True

    def _load_input_buffer(self, recipe, loaded, outpost):
        """Loads what the recipe still needs from the input buffer and ejects the rest."""
        keep = []
        for stack in self.machine.input.stacks():
            needed = recipe.get(stack.id, 0) - loaded.get(stack.id, 0)
            if needed > 0:
                load_qty = min(stack.count, needed)
                self.machine.load(stack.id, load_qty)
                keep.append(stack.id)
        eject_unneeded(self.machine.input, keep, outpost=outpost)
        self._pause(0.5)

    def _load_missing_reagent(self, reagent_id, req_qty, curr_qty, outpost, is_home):
        """Takes one missing reagent from local stock into the chamber, first covering a local shortfall."""
        missing = req_qty - curr_qty
        local_have = local_stock(reagent_id, outpost)
        self.log.debug(f"[{self.name}] Reagent {reagent_id}: required={req_qty} loaded={curr_qty} missing={missing} local_have={local_have}.")
        if local_have < missing and not self._cover_shortfall(reagent_id, missing, local_have, is_home):
            return

        moved = take_item(self.machine.input, reagent_id, missing, outpost=outpost)
        if moved > 0:
            self.machine.load(reagent_id, moved)
        self._pause(0.5)

    def _cover_shortfall(self, reagent_id, missing, local_have, is_home):
        """Buys the local shortfall at home; returns False (after pausing) when it can't be covered this tick."""
        if not (is_home and self.shop):
            self.log.level("warn").print(f"[{self.name}] Waiting on {reagent_id} resupply ({local_have}/{missing} on hand locally).")
            self._pause(2.0)
            return False
        buy_qty = missing - local_have
        cost = buy_qty * cash.shop_price(reagent_id)
        cash_id = f"bio_reagents:{self.name}"
        if not cash.can_spend(cash_id, cost, label=f"{buy_qty}x {reagent_id}"):
            self.log.debug(f"[{self.name}] {buy_qty}x {reagent_id} ({cost} cr): cash manager holds it back.")
            self._pause(1.0)
            return False
        buy_res = self.shop.buy(reagent_id, buy_qty)
        if buy_res.status != "ok":
            cash.release(cash_id)
            self._pause(1.0)
            return False
        cash.spent(cash_id, cost)
        self.log.print(f"[{self.name}] Purchased {buy_qty}x {reagent_id} from shop.")
        return True

    def _extract_specimen(self, specimen, processor_idle):
        """Runs extract() on the chamber specimen and hands the sample over; returns an outcome string for the enclosing log block."""
        ext_res = self.machine.extract()
        if ext_res.status != "ok":
            self.log.debug(f"[{self.name}] extract() -> {ext_res.status}: {getattr(ext_res, 'message', '')}")
            return f"failed ({ext_res.status})"
        sample_id = specimen.fragment_id
        self.log.print(f"[{self.name}] Extracted sample: {sample_id}!")
        if not processor_idle:
            self._wait_for_processor()
            return f"done: {sample_id} (waiting on processor)"
        if not self.drain_output():
            return f"done: {sample_id} (output not drained)"

        # Notify Exchange over Signal Bus for immediate delivery
        if self.comms:
            try:
                self.comms.send("sample_ready", {"sample_id": sample_id})
            except Exception as error:
                swallowed("bio.BioLabController.step: self.comms.send", error)
        return f"done: {sample_id}"

    def run(self):
        self.log.print(f"Bio Lab ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            reset_all()
            if retire_pass(self.machine, "bio_lab"):
                continue
            self.step()
            flush_all()
            sleep(0.5)


class BioCollectorController:
    """
    Gathers specimens matching the local orders of this outpost's own Bio
    Exchange (bio_demand_totals()).
    Prevents over-harvesting:
    - Never harvests fragments already sufficient in local storage/deliveries.
    - Caps uncataloged harvests if local storage already holds ample samples.
    """

    def __init__(self, machine: "BioCollector"):
        self.machine = machine
        self.name = getattr(machine, "id", "bio_collector")
        self.pending_analysis = set()
        self.log = TreeConsole(module="bio")

    def coord_key(self, c):
        return (round(c[0], 2), round(c[1], 2))

    def step(self):
        if self.machine.cargo is not None:
            self.log.trace(f"[{self.name}] step: cargo already occupied -- skipping this cycle.")
            flush_all()
            sleep(0.5)
            return

        outpost = self.machine.outpost
        my_biome = get_my_biome(self.machine)
        exchange = local_sibling(outpost, "bio_exchange")
        self.log.trace(f"[{self.name}] step: entry, my_biome={my_biome} exchange_found={exchange is not None}")

        # Fetch exchange.orders() and walk local storage exactly ONCE per
        # step(), not once per fragment -- see focus_local_order()'s and
        # local_stock_snapshot()'s docstrings: re-fetching/re-walking per
        # fragment (~20-30 of them) measured at ~20s, then still ~8s/cycle
        # even after caching orders() alone, from the storage walk.
        snapshot = local_stock_snapshot(outpost)
        orders, current_order = self._focus_order(exchange, snapshot, my_biome)
        preferred_fragments = set((current_order.requires or {}).keys()) if current_order else set()
        self.log.debug(f"[{self.name}] Focus order: {getattr(current_order, 'id', None)}, preferred_fragments={preferred_fragments}")

        # 1. Determine demand -- shared with BioLabController's own extract-vs-
        # discard() gate, see bio_demand_totals()'s docstring.
        demand_totals = bio_demand_totals(orders, my_biome)
        needed_fragments = {frag_id for frag_id, count_needed in demand_totals.items() if snapshot_stock(snapshot, frag_id) < count_needed}
        self.log.debug(f"[{self.name}] demand_totals={demand_totals} -> needed_fragments={needed_fragments} (local stock already covers the rest)")

        # Coarse safety net, NOT the primary flow control (that's each processor
        # controller's structural idle-gate, see processor_is_idle()): in a
        # healthy pipeline this should basically never trip, since the Lab won't
        # hand off/drain faster than the processor can keep up. Biome-agnostic --
        # reads the already-built snapshot's totals rather than re-scanning
        # anything, and doesn't care which (if any) marker property applies.
        total_demanded_local = total_demanded_artifacts(snapshot, demand_totals.keys())
        if total_demanded_local >= MAX_LOCAL_BIO_ARTIFACTS:
            self.log.debug(f"[{self.name}] Safety net tripped: {total_demanded_local} demanded artifact(s) already sitting locally >= MAX_LOCAL_BIO_ARTIFACTS={MAX_LOCAL_BIO_ARTIFACTS} -- pausing harvest this cycle.")
            flush_all()
            sleep(1.0)
            return

        # 2. Scan local biome
        locations = self.machine.scan()
        if not locations:
            self.log.trace(f"[{self.name}] scan() returned no locations this cycle.")
            flush_all()
            sleep(2.0)
            return

        for loc in locations:
            if loc.cataloged:
                self.pending_analysis.discard(self.coord_key(loc.coords))

        target_coords, harvest_label = self._needed_target(locations, needed_fragments, preferred_fragments, outpost)

        if needed_fragments and target_coords is None:
            self.log.debug(f"[{self.name}] needed_fragments={needed_fragments} but none of the {len(locations)} scanned location(s) are cataloged as a matching fragment yet.")

        if target_coords is None:
            target_coords, harvest_label = self._discovery_target(locations, outpost)

        if target_coords:
            self.log.start(f"[{self.name}] {harvest_label}")
            res = self.machine.collect(target_coords)
            if res.status != "ok":
                self.log.debug(f"[{self.name}] collect({target_coords}) -> {res.status}: {getattr(res, 'message', '')} -- releasing pending_analysis claim.")
                self.pending_analysis.discard(self.coord_key(target_coords))
                self.log.end(f"[{self.name}] Harvest failed ({res.status})")
                flush_all()
                sleep(1.0)
            else:
                self.log.end(f"[{self.name}] Harvest started")
        else:
            # Idle cleanly
            self.log.trace(f"[{self.name}] No harvest target this cycle ({len(locations)} location(s) scanned) -- idling.")
            flush_all()
            sleep(2.0)

    def _focus_order(self, exchange, snapshot, my_biome):
        """(orders, focus order) of the outpost's own Bio Exchange, read once
        per step(); ([], None) without an Exchange. When orders() raises,
        the focus is picked from no orders."""
        if not exchange:
            return [], None
        try:
            orders = exchange.orders()
        except Exception as error:
            swallowed("bio.BioCollectorController.step: exchange.orders", error)
            orders = []
        return orders, focus_local_order(orders, snapshot, my_biome)

    def _needed_target(self, locations, needed_fragments, preferred_fragments, outpost):
        """
        Priority 1 of step(): (coords, harvest label) of a cataloged location
        whose fragment local orders need, else (None, ""). Prefers the
        current/focus order's own fragments, falling back to any other
        incomplete order's fragment if none of those are discoverable nearby
        right now. Within each tier, ranks fragments by the local processor's
        setup preference (processor_fragment_preference()).
        """
        if not needed_fragments:
            return None, ""
        location_by_fragment = {}
        for loc in locations:
            if loc.cataloged and loc.fragment_id in needed_fragments and loc.fragment_id not in location_by_fragment:
                location_by_fragment[loc.fragment_id] = loc
        processor, processor_type = local_biome_processor(outpost)
        ranked = processor_fragment_preference(processor, processor_type, location_by_fragment.keys())
        for tier_label, in_tier in (("current order", True), ("other order", False)):
            for fragment_id in ranked:
                if (fragment_id in preferred_fragments) == in_tier:
                    loc = location_by_fragment[fragment_id]
                    return loc.coords, f"Harvesting needed specimen ({tier_label}): {fragment_id} at {loc.coords}"
        return None, ""

    def _discovery_target(self, locations, outpost):
        """
        Priority 2 of step(), strictly throttled: (coords, harvest label) of
        the first uncataloged location not already pending analysis, claimed
        in pending_analysis; (None, "") while the lab holds a collected
        specimen or nothing qualifies.
        """
        lab = local_sibling(outpost, "bio_lab")
        if lab and lab.specimen is not None and lab.specimen.stage == "collected":
            self.log.debug(f"[{self.name}] Skipping uncataloged discovery -- lab already holds a collected specimen awaiting analysis.")
            return None, ""
        for loc in locations:
            if not loc.cataloged and self.coord_key(loc.coords) not in self.pending_analysis:
                self.pending_analysis.add(self.coord_key(loc.coords))
                return loc.coords, f"Harvesting uncataloged fragment at {loc.coords} (discovery)"
        return None, ""

    def run(self):
        self.log.print(f"Bio Collector ({self.name}) online via Shared Library & Signal Bus.")
        validate_game_version()
        while True:
            reset_all()
            if retire_pass(self.machine, "bio_collector"):
                continue
            self.step()
