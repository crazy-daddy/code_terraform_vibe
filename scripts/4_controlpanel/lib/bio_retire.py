import fluid_routing
import logistics_requests
import outpost_reagents
from archive import archive
from building_ops import undeploy
from game_clock import now_tick
from retired_machines import sell_kits
from storage_unload import best_unload_target, drain_port_to_storage
from swallow import swallowed
from tree_console import TreeConsole, flush_all

# Bio chain retirement, one biome at a time. Once every Bio Order of a biome
# reads complete, that biome's Collectors, Labs, processors and Exchanges have
# nothing left to do: the orders were their only consumer, and their
# completion already cataloged every fragment and unlocked every feed recipe
# Wildlife needs (docs/guide/wildlife_overview.md).
#
# BioRetirement.step() (orchestrator_automation.py, storage cadence):
#   - reads orders() from any Bio Exchange and latches every biome whose
#     orders are all complete in RETIRE_KEY["done"] (never removed, so the
#     list survives the sale of the last Exchange);
#   - tries to undeploy every chain machine at an outpost of a done biome and
#     sells the kit it returns (bio machines take no tier packs). Refused
#     undeploys (cargo still inside, an action running, Inventory full) and
#     refused sales (RETIRE_KEY["unsold"]) are retried next pass. A sold Lab
#     or Caster withdraws its outpost's pull requests; the Caster's Fabricator
#     order lapses on its own heartbeat.
# Emptying is self-only, so each chain machine's own script calls
# retire_pass() every loop, which runs drain() instead of its work: chamber or
# cargo discarded/ejected, input ejected and output sent to local storage
# (decompiled undeploy cargo check: bins, Collector cargo, Lab specimen and
# loaded reagents, processor chamber, any running action).

# Seconds a retired machine's script waits between drain() passes.
RETIRED_POLL_SECONDS = 5.0
# Clock ticks a chain script reuses its copy of the done list (10 ticks/s -> 60 s).
RETIRE_CHECK_TICKS = 600

# Every machine type of the chain; the processors are bio_orders.BIOME_PROCESSOR_TYPE_IDS.
CHAIN_TYPE_IDS = ("bio_collector", "bio_lab", "bio_luminizer", "bio_caster", "bio_conditioner", "dna_sequencer", "bio_exchange")
EXCHANGE_TYPE_ID = "bio_exchange"
LAB_TYPE_ID = "bio_lab"
CASTER_TYPE_ID = "bio_caster"
# logistics.requests requester ids withdrawn when their machine is sold:
# outpost_reagents.REQUESTER_ID (Lab) and bio_volcanic.REQUESTER_ID (Caster;
# bio_volcanic imports bio, which imports this module).
CASTER_REQUESTER_ID = "bio_caster"

# One dict: {"done": [biome], "unsold": [item id], "status", "last_sale", "tick"}.
RETIRE_KEY = "bio.retire"

log = TreeConsole(module="bio_retire")


def same_biome(a, b):
    """Equal, or one name contains the other (bio_orders.is_local_order()'s rule), but never a match
    for an empty biome, so a machine without one never retires."""
    return bool(a and b) and (a == b or a in b or b in a)


def done_biomes():
    """Biomes whose Bio Orders are all complete ([] when unreadable)."""
    try:
        state = archive.get(RETIRE_KEY, {}) or {}
    except Exception as error:
        swallowed("bio_retire.done_biomes: archive.get", error)
        return []
    done = state.get("done") if isinstance(state, dict) else None
    return done if isinstance(done, list) else []


def biome_retired(biome):
    """True once every Bio Order of `biome` is complete. False without a biome."""
    return any(same_biome(biome, done) for done in done_biomes())


# This script's copy of done_biomes() and the tick it was read; a chain script
# loops every 0.5-5 s, the list changes a few times per save.
_done_cache = {"tick": None, "done": []}


def _cached_done_biomes():
    tick = now_tick()
    last = _done_cache["tick"]
    if last is None or not 0 <= tick - last < RETIRE_CHECK_TICKS:
        _done_cache["tick"] = tick
        _done_cache["done"] = done_biomes()
    return _done_cache["done"]


def _eject_input(machine, outpost):
    port = getattr(machine, "input", None)
    if port is None or port.count() <= 0:
        return
    for stack in port.stacks():
        destination = best_unload_target(stack.id, stack.count, outpost=outpost)
        if destination is None:
            continue
        port.eject(destination, stack.id, stack.count, getattr(stack, "properties", None) or None, "exact")


def drain(machine, type_id):
    """
    One emptying pass, from the machine's own script: clears its chamber,
    cargo or order, ejects its input and sends its output to local storage.
    Discarded specimens and samples are worthless once their biome is done.
    """
    outpost = machine.outpost
    try:
        if type_id == "bio_collector":
            if machine.cargo is not None:
                machine.discard()
            return
        if type_id == LAB_TYPE_ID:
            if machine.specimen is not None:
                machine.discard()
            elif machine.loaded_reagents:
                machine.unload_reagents()
        elif type_id == EXCHANGE_TYPE_ID:
            if machine.active_order() is not None:
                machine.clear_order()
        elif type_id in ("bio_luminizer", "dna_sequencer"):
            if machine.chamber is not None:
                machine.discard()
        elif type_id == "bio_caster":
            if machine.fragment() or machine.materials():
                machine.eject()
        elif type_id == "bio_conditioner":
            if machine.fragment():
                machine.eject()
        _eject_input(machine, outpost)
        if machine.output.count() > 0:
            drain_port_to_storage(machine.output, outpost)
    except Exception as error:
        swallowed(f"bio_retire.drain: {type_id}", error)


def retire_pass(machine, type_id):
    """For a chain script's run loop: True (after one drain() and a RETIRED_POLL_SECONDS wait)
    when the machine's biome is retired (done list re-read every RETIRE_CHECK_TICKS), else False."""
    biome = getattr(machine.outpost, "biome", None)
    if not any(same_biome(biome, done) for done in _cached_done_biomes()):
        return False
    drain(machine, type_id)
    flush_all()
    sleep(RETIRED_POLL_SECONDS)
    return True


def _status_line(done, waiting, unsold):
    """BioRetirement's published status line."""
    if not done:
        return "no biome complete"
    parts = [f"done {', '.join(done)}"]
    if waiting:
        parts.append(f"draining {', '.join(sorted(waiting))}")
    if unsold:
        parts.append(f"unsold {', '.join(unsold)}")
    if not waiting and not unsold:
        parts.append("chains retired")
    return "; ".join(parts)


class BioRetirement:
    """Retirement pass for orchestrator_automation.py: latches done biomes, undeploys and sells their chain machines."""

    def __init__(self):
        self.warned = {}

    @staticmethod
    def _machines(type_ids):
        """[(building, type_id, outpost_id, biome)] for every deployed machine of type_ids."""
        machines = []
        for type_id in type_ids:
            for building, outpost_id in fluid_routing.discover_network_buildings(type_id, resolve=True):
                if not getattr(building, "id", None):
                    continue
                outpost = getattr(building, "outpost", None)
                machines.append((building, type_id, outpost_id, getattr(outpost, "biome", None)))
        return machines

    @staticmethod
    def _complete_biomes(exchange: "BioExchange"):
        """Biomes with at least one Bio Order and no incomplete one."""
        try:
            orders = exchange.orders()
        except Exception as error:
            swallowed("bio_retire.BioRetirement._complete_biomes: exchange.orders", error)
            return set()
        biomes = {}
        for order in orders:
            biome = getattr(order, "biome", None)
            if biome:
                biomes[biome] = biomes.get(biome, True) and getattr(order, "status", "") == "complete"
        return {b for b, complete in biomes.items() if complete}

    def _undeploy(self, building, type_id, outpost_id, computer):
        """Undeploys one machine: "ok" (kit in Inventory), "gone" or "refused"."""
        machine_id = building.id
        status = undeploy(machine_id, log, self.warned, computer=computer, tag="[bio] ")
        if status == "not_found":
            return "gone"
        if status != "ok":
            return "refused"
        if type_id == LAB_TYPE_ID:
            logistics_requests.clear_requests(outpost_reagents.REQUESTER_ID, outpost_id)
        elif type_id == CASTER_TYPE_ID:
            logistics_requests.clear_requests(CASTER_REQUESTER_ID, outpost_id)
        log.print(f"[{machine_id}] Biome orders complete: undeployed.")
        return "ok"

    def step(self, current_tick=0):
        """One pass. Returns the published status line."""
        state = archive.get_dict(RETIRE_KEY)
        done = list(state.get("done") or [])
        unsold = list(state.get("unsold") or [])
        exchanges = self._machines((EXCHANGE_TYPE_ID,))
        if exchanges:
            for biome in sorted(self._complete_biomes(exchanges[0][0]) - set(done)):
                done.append(biome)
                log.print(f"Every {biome} Bio Order complete: retiring that biome's bio chain.")

        # Only Exchanges are discovered until a biome is done.
        machines = self._machines(CHAIN_TYPE_IDS) if done else []
        retiring = [m for m in machines if any(same_biome(m[3], b) for b in done)]
        waiting = []
        last_sale = state.get("last_sale", "")
        if retiring or unsold:
            computer = get_component("computer")
            shop = get_component("shop")
            if computer and shop:
                to_sell = []
                for building, type_id, outpost_id, _ in retiring:
                    result = self._undeploy(building, type_id, outpost_id, computer)
                    if result == "ok":
                        to_sell.append(type_id)
                    elif result == "refused":
                        waiting.append(building.id)
                credits, refused = sell_kits(shop, unsold, log, warn=False) if unsold else (0, [])
                earned, fresh_refused = sell_kits(shop, to_sell, log)
                sold = len(unsold) - len(refused) + len(to_sell) - len(fresh_refused)
                unsold = refused + fresh_refused
                if sold:
                    last_sale = f"sold {sold} kit(s) for {credits + earned} cr"
                    log.print(f"Bio chain sale: {last_sale}.")

        status = _status_line(done, waiting, unsold)
        new_state = {"done": done, "unsold": unsold, "status": status, "last_sale": last_sale}
        if done and any(state.get(k) != v for k, v in new_state.items()):
            new_state["tick"] = current_tick
            archive.set(RETIRE_KEY, new_state)
        return status
