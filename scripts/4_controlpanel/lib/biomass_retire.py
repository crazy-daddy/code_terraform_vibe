import fluid_routing
from archive import archive
from building_ops import undeploy
from components import sensor_value
from retired_machines import release, retire, retired_ids, sell_kits
from swallow import safe_call, swallowed
from tree_console import TreeConsole

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
#   - Biomass Mixer scripts stop routing; orchestrator_automation.py stops the Mixer gate.
#   - BiomassRetirement.step() (orchestrator_automation.py) switches every Mixer's breaker off
#     and each Liquifier's once its input bin is empty, and publishes
#     RETIRE_KEY.
#   - Miner drones visit biosites holding a requested life form first, then
#     ones that refill an outpost's buffer of LIFEFORM_BUFFER_SLOTS Warehouse
#     slots per form, kept for creature feed (lib/drone_mining.py,
#     lib/drone_depot.py). Stored stock is never destroyed; a full Drone
#     Depot flushes surplus only as a last resort (flush_surplus()).
# Stage 2, automatic (same BiomassRetirement.step()): each machine, once
# ready, is undeployed and what undeploy() returns to Inventory -- the kit
# plus every applied tier pack -- is sold at full Shop price (decompiled shop
# sell: deployable equipment and upgrade packs resell at cost). Refused
# undeploys (Inventory full, cargo arriving) are retried next pass.
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

# One dict: {"complete", "tons", "machines": {id: {...}}, "unsold": [item id], "status", "last_sale", "tick"}.
RETIRE_KEY = "biomass.retire"
# retired_machines registry name of this retirement.
RETIRED_BY = "biomass"
# Other scripts' per-machine telemetry, pruned for sold machines.
LIQUIFIER_STATUS_KEY = "essence_liquifier.status"
MIXER_STATUS_KEY = "biomass_mixer.status"
MIXER_GATE_KEY_PREFIX = "biomass_mixer.gate."
MIXER_GATE_KNOWN_LIQUIFIERS_KEY = "biomass_mixer.gate_known_liquifiers"

log = TreeConsole(module="biomass_retire")


def biomass_tons():
    """Planet biomass in tons (biomass_sensor), 0.0 when unreadable."""
    return sensor_value("biomass_sensor", "biomass_retire.biomass_tons: biomass_sensor.get_value") or 0.0


def biomass_complete():
    """True once biomass reached BIOMASS_COMPLETE_T. Biomass never falls, so this never flips back."""
    return biomass_tons() >= BIOMASS_COMPLETE_T


def retire_state():
    return archive.get_dict(RETIRE_KEY)


def _call(obj, method, default):
    return safe_call("biomass_retire._call: getattr(obj, method)", lambda: getattr(obj, method)(), default)


def _input_count(liquifier):
    port = getattr(liquifier, "input", None)
    return _call(port, "count", 0) if port is not None else 0


class BiomassRetirement:
    """Retirement pass for orchestrator_automation.py: breakers off, readiness per machine, sale of ready ones, RETIRE_KEY status."""

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
        summary, unsold = sell_ready_machines(machines, state.get("unsold") or [])
        last_sale = summary or state.get("last_sale", "")
        waiting = sorted(i for i, e in machines.items() if not e["ready"])
        refused = sorted(f"{i} ({e['why']})" for i, e in machines.items() if e["ready"] and e["why"] != "ready")
        if not machines and not unsold:
            status = "biomass complete: chain retired"
        else:
            parts = [f"{len(machines) - len(waiting)}/{len(machines)} ready"]
            if waiting:
                parts.append(f"draining {', '.join(waiting)}")
            if refused:
                parts.append(f"refused {', '.join(refused)}")
            if unsold:
                parts.append(f"unsold {', '.join(unsold)}")
            status = f"biomass complete: {'; '.join(parts)}"
        log.debug(f"step: tons={tons:.0f}, machines={machines}.")
        archive.set(
            RETIRE_KEY,
            {
                "complete": True,
                "tons": tons,
                "machines": machines,
                "unsold": unsold,
                "status": status,
                "last_sale": last_sale,
                "tick": current_tick,
            },
        )
        return status


def _prune_telemetry(machine_id):
    release([machine_id])
    archive.pop_entry(LIQUIFIER_STATUS_KEY, machine_id)
    archive.pop_entry(MIXER_STATUS_KEY, machine_id)
    archive.delete(f"{MIXER_GATE_KEY_PREFIX}{machine_id}")


def sell_ready_machines(machines, unsold=()):
    """
    Stage 2: retries selling `unsold` (kits left in Inventory by an earlier
    pass's refused sale), then undeploys every ready machine in `machines`
    ({id: entry}, as _machines() builds it) and sells the kit plus any tier
    pack it returns. Undeployed and vanished machines are removed from
    `machines`; a refused undeploy keeps its machine with the status in
    "why". Returns (one-line summary or "" when nothing was sold, ids still
    unsold).
    """
    computer = get_component("computer")
    shop = get_component("shop")
    if not computer or not shop:
        return "", list(unsold)
    credits, still_unsold = sell_kits(shop, unsold, log, warn=False) if unsold else (0, [])
    sold = len(unsold) - len(still_unsold)

    for machine_id in sorted(m for m, e in machines.items() if e.get("ready")):
        entry = machines[machine_id]
        status = undeploy(machine_id, log, computer=computer)
        if status == "not_found":
            _prune_telemetry(machine_id)
            machines.pop(machine_id, None)
            continue
        if status != "ok":
            entry["why"] = f"undeploy {status}"
            continue
        _prune_telemetry(machine_id)
        machines.pop(machine_id, None)
        items = [entry.get("type")]
        for tier, pack_id in MIXER_TIER_PACKS:
            if entry.get("type") == MIXER_TYPE_ID and (entry.get("tier") or 1) >= tier:
                items.append(pack_id)
        earned, refused = sell_kits(shop, [i for i in items if i], log)
        credits += earned
        sold += len(items) - len(refused)
        still_unsold += refused
        log.print(f"[{machine_id}] Biomass complete: undeployed, sold {len(items) - len(refused)}/{len(items)} of {items} for {earned} cr.")

    if not sold:
        return "", still_unsold
    archive.delete(MIXER_GATE_KNOWN_LIQUIFIERS_KEY)
    summary = f"sold {sold} item(s) for {credits} cr"
    log.print(f"Biomass chain sale: {summary}.")
    return summary, still_unsold
