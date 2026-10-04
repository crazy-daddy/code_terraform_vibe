import fluid_routing
from archive import archive
from tree_console import TreeConsole
from swallow import swallowed
from retired_machines import retire, release, retired_ids

# Biomass pillar retirement. The Biomass pillar owns a fixed 100,000 TP of
# the Terraform Index and adds nothing once biomass reaches its final phase
# ("Full Biomass", BIOMASS_COMPLETE_T; nocturna.md: "a completed pillar
# contributes no additional Index"). No research is gated above 130,000 t.
# Essences feed only the Biomass Mixer and the Mixer makes only biomass, so
# from then on the Liquifier -> Mixer chain only draws power and eats the
# life forms the Seed Maker needs.
#
# Stage 1, automatic (every consumer checks biomass_complete()):
#   - Essence Liquifiers stop feeding and eject their input bin to local
#     storage (lib/essence_liquifier.py retire_step()).
#   - Biomass Mixer scripts stop routing; control_room_automation.py stops the Mixer gate.
#   - BiomassRetirement.step() (control_room_automation.py) switches every Mixer's breaker off
#     and each Liquifier's once its input bin is empty, and publishes
#     RETIRE_KEY for status_panel.py.
#   - Miner drones visit biosites holding a requested life form first, then
#     ones that refill an outpost's buffer of LIFEFORM_BUFFER_SLOTS Warehouse
#     slots per form, kept for creature feed (lib/drone_mining.py,
#     lib/drone_depot.py). Stored stock is never destroyed; a full Drone
#     Depot flushes surplus only as a last resort (flush_surplus()).
# Stage 2, manual (status_panel.py button, drawn only once every machine is
# ready): sell_retired_machines() undeploys each machine and sells what
# undeploy() returns to Inventory -- the kit plus every applied tier pack --
# at full Shop price (decompiled shop sell: deployable equipment and upgrade
# packs resell at cost).
#
# Ready to undeploy (decompiled undeploy cargo check): no items in any bin.
# Fluid buffers don't block, so a Mixer is always ready and a Liquifier once
# its life-form input is empty. Essence left in buffers is lost.

# Final Biomass phase threshold, tons ("terraform.biomass.full_biosphere" in
# the decompiled sensor phase table).
BIOMASS_COMPLETE_T = 250000

LIQUIFIER_TYPE_ID = "essence_liquifier"
MIXER_TYPE_ID = "biomass_mixer"
RETIRED_TYPE_IDS = (LIQUIFIER_TYPE_ID, MIXER_TYPE_ID)
# Tier packs undeploy() returns with a Mixer of that tier or higher.
MIXER_TIER_PACKS = ((2, "biomass_mixer_upgrade_pack_mk2"),)

# One dict: {"complete", "tons", "machines": {id: {...}}, "ready", "status", "last_sale"}.
RETIRE_KEY = "biomass.retire"
# retired_machines registry name of this retirement.
RETIRED_BY = "biomass"
# Other scripts' per-machine telemetry, pruned for sold machines.
LIQUIFIER_STATUS_KEY = "essence_liquifier.status"
MIXER_STATUS_KEY = "biomass_mixer.status"
MIXER_GATE_KEY_PREFIX = "biomass_mixer.gate."
MIXER_GATE_KNOWN_LIQUIFIERS_KEY = "biomass_mixer.gate_known_liquifiers"

# undeploy() answers that only mean "not right now".
TRANSIENT_UNDEPLOY_STATUSES = ("inventory_full", "cargo_present", "docked_drone")

log = TreeConsole(module="biomass_retire")


def biomass_tons():
    """Planet biomass in tons (biomass_sensor), 0.0 when unreadable."""
    try:
        sensor = get_component("biomass_sensor")
        return float(sensor.get_value()) if sensor else 0.0
    except Exception as error:
        swallowed("biomass_retire.biomass_tons: biomass_sensor.get_value", error)
        return 0.0


def biomass_complete():
    """True once biomass reached BIOMASS_COMPLETE_T. Biomass never falls, so this never flips back."""
    return biomass_tons() >= BIOMASS_COMPLETE_T


def retire_state():
    raw = archive.get(RETIRE_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _call(obj, method, default):
    try:
        return getattr(obj, method)()
    except Exception as error:
        swallowed("biomass_retire._call: getattr(obj, method)", error)
        return default


def _input_count(liquifier):
    port = getattr(liquifier, "input", None)
    return _call(port, "count", 0) if port is not None else 0


class BiomassRetirement:
    """Stage 1 bookkeeping for control_room_automation.py: breakers off, readiness per machine, RETIRE_KEY status."""

    def __init__(self, power: "PowerControl | None" = None):
        self.power = power or get_component("power_control")
        self._announced = False
        self._unswitchable_warned = set()

    def _switch_off(self, machine_id):
        """Breaker off once; True when the machine is (now) unpowered."""
        power = self.power
        if power is None:
            return False
        try:
            if not power.is_powered(machine_id):
                return True
            if not power.can_power_off(machine_id):
                if machine_id not in self._unswitchable_warned:
                    self._unswitchable_warned.add(machine_id)
                    log.level("warn").print(f"[{machine_id}] has no breaker toggle; leaving it powered.")
                return False
            power.set_powered(machine_id, False)
            log.print(f"[{machine_id}] Biomass complete: breaker off.")
            return True
        except Exception as error:
            swallowed("biomass_retire.BiomassRetirement._switch_off: power.set_powered", error)
            return False

    def _machines(self):
        """{id: entry} for every deployed Liquifier and Mixer, with readiness."""
        machines = {}
        for type_id in RETIRED_TYPE_IDS:
            for building, outpost_id in fluid_routing.discover_network_buildings(type_id, resolve=True):
                machine_id = getattr(building, "id", None)
                if not machine_id:
                    continue
                entry = {"type": type_id, "outpost": outpost_id, "tier": 1, "ready": True, "why": "ready"}
                if type_id == MIXER_TYPE_ID:
                    entry["tier"] = _call(building, "tier", 1) or 1
                else:
                    held = _input_count(building)
                    if held > 0:
                        entry.update({"ready": False, "why": f"{held} life form(s) in input"})
                machines[machine_id] = entry
        return machines

    def step(self, current_tick=0):
        """One pass. Returns the published status line."""
        tons = biomass_tons()
        state = retire_state()
        if tons < BIOMASS_COMPLETE_T:
            if state.get("complete", True):
                archive.set(RETIRE_KEY, {"complete": False})
            return f"biomass {tons:.0f} / {BIOMASS_COMPLETE_T} t"
        if not self._announced:
            self._announced = True
            log.print(f"Biomass {tons:.0f} t >= {BIOMASS_COMPLETE_T} t: pillar complete, retiring Liquifiers and Mixers.")

        machines = self._machines()
        # A Mixer can go dark at once; a Liquifier's own script must keep
        # running until it has ejected its input bin.
        dark = [m for m, e in machines.items() if e["type"] == MIXER_TYPE_ID or e["ready"]]
        # Registered before the breakers go off, so script parking never sees them as stray dark.
        unregistered = set(dark) - retired_ids(RETIRED_BY)
        if unregistered:
            retire(sorted(unregistered), RETIRED_BY)
        for machine_id in dark:
            machines[machine_id]["powered_off"] = self._switch_off(machine_id)
        waiting = sorted(i for i, e in machines.items() if not e["ready"])
        ready = bool(machines) and not waiting
        if not machines:
            status = "biomass complete: chain retired"
        elif ready:
            status = f"biomass complete: {len(machines)} machine(s) ready to sell"
        else:
            status = f"biomass complete: {len(machines) - len(waiting)}/{len(machines)} ready, draining {', '.join(waiting)}"
        log.debug(f"step: tons={tons:.0f}, machines={machines}.")
        archive.set(RETIRE_KEY, {
            "complete": True,
            "tons": tons,
            "machines": machines,
            "ready": ready,
            "status": status,
            "last_sale": state.get("last_sale", ""),
            "tick": current_tick,
        })
        return status


def _sell_one(shop: "Shop", item_id):
    """Sells one item_id from Inventory; credits earned, 0 on failure."""
    try:
        res = shop.sell(item_id, 1)
    except Exception as error:
        swallowed("biomass_retire._sell_one: shop.sell", error)
        return 0
    if getattr(res, "status", "") != "ok":
        log.level("warn").print(f"sell('{item_id}') -> {getattr(res, 'status', '?')}: {getattr(res, 'message', '')}. Left in Inventory.")
        return 0
    return getattr(res, "credits", 0) or 0


def _prune_telemetry(machine_id):
    release([machine_id])
    archive.pop_entry(LIQUIFIER_STATUS_KEY, machine_id)
    archive.pop_entry(MIXER_STATUS_KEY, machine_id)
    archive.delete(f"{MIXER_GATE_KEY_PREFIX}{machine_id}")


def sell_retired_machines():
    """
    Stage 2 (operator button): undeploys every ready machine in RETIRE_KEY and
    sells the kit plus any tier pack it returns. Machines still draining or
    refused for a transient reason are left for the next press. Returns a
    one-line summary (also stored as RETIRE_KEY["last_sale"]).
    """
    state = retire_state()
    if not state.get("complete"):
        return "biomass not complete; nothing to sell"
    computer = get_component("computer")
    shop = get_component("shop")
    if not computer or not shop:
        return "computer or shop unavailable"

    log.start("Selling retired biomass machines")
    sold = []
    credits = 0
    skipped = []
    machines = state.get("machines") or {}
    for machine_id, entry in sorted(machines.items()):
        if not isinstance(entry, dict) or not entry.get("ready"):
            skipped.append(f"{machine_id} (draining)")
            continue
        try:
            res = computer.undeploy(machine_id)
        except Exception as error:
            swallowed("biomass_retire.sell_retired_machines: computer.undeploy", error)
            skipped.append(f"{machine_id} (error)")
            continue
        status = getattr(res, "status", "")
        if status == "not_found":
            _prune_telemetry(machine_id)
            continue
        if status != "ok":
            level = "debug" if status in TRANSIENT_UNDEPLOY_STATUSES else "warn"
            log.level(level).print(f"[{machine_id}] undeploy -> {status}: {getattr(res, 'message', '')}")
            skipped.append(f"{machine_id} ({status})")
            continue
        items = [entry.get("type")]
        for tier, pack_id in MIXER_TIER_PACKS:
            if entry.get("type") == MIXER_TYPE_ID and (entry.get("tier") or 1) >= tier:
                items.append(pack_id)
        earned = sum(_sell_one(shop, item_id) for item_id in items if item_id)
        credits += earned
        sold.append(machine_id)
        _prune_telemetry(machine_id)
        log.print(f"[{machine_id}] Undeployed and sold {items} for {earned} cr.")

    if sold:
        archive.delete(MIXER_GATE_KNOWN_LIQUIFIERS_KEY)
    summary = f"sold {len(sold)} machine(s) for {credits} cr"
    if skipped:
        summary += f"; skipped {', '.join(skipped)}"
    state["last_sale"] = summary
    archive.set(RETIRE_KEY, state)
    log.end(f"Biomass chain sale: {summary}.")
    return summary
