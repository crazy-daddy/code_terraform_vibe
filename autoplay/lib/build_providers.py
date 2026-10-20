# Providers of the building pass (building_plan.py, docs/plans/building_planner.md
# phase 5): pure functions over one context dict, each returning wants.
#
# Context (building_plan.build_context() reads it in game; tests build it):
#   {"snap": outpost_needs snapshot (outposts with types / used / capacity /
#            roles / home / biome; used counts and "reserved" {type_id: n}
#            holds the open deploys, building_plan.reserve_open()), kits, activity, phase, bio_orders, bio_done,
#            ore_sites, fluid_sites, ore_wanted),
#    "phase": game_phase snapshot, "focus": focus_plan decision,
#    "generators": {type_id: [(machine_id, outpost_id, tier), ...]} atmosphere generators,
#    "machines": {type_id: [(machine_id, outpost_id, tier), ...]} Smelters / Fabricators,
#    "grids": [{"anchor", "outposts": [ids], "generated", "consumed", "stored",
#               "capacity", "reserve", "phase", "types": {type_id: n}}],
#    "prices": {item_id: cost} Shop catalogue, "inventory": {item_id: units},
#    "fleet": {"pioneer": {role: n}, "drone": {role: n}, "rover": {role: n}},
#    "pickup_backlog": oldest pickup age in ticks,
#    "drills_missing": [ore, ...] Smelter ores without a drill,
#    "pioneer_roles": {role: {"wanted", "keep"}} of a fresh fleet.role_demand ({} without one),
#    "drone_yield": the FLEET card's "leave to drones" switch (logistics.drone_yield),
#    "miners": {outpost: {"count", "queued", "newest", "idle_since"}} Pioneer miners
#    by base (queued jobs counted), "mining_reach": {outpost: [ore, ...]} its miners reach,
#    "ore_need": {outpost: {ore: since}} raw ores at NEED there, "tick": now}
#
# A want: {"kind": "deploy" | "upgrade" | "retire" | "fleet", "outpost", "type_id",
#          "count", "machine_id", "item_id", "fleet_kind", "role", "delta",
#          "why", "provider", "blocked"}. building_plan turns wants into
# proposals and applies the shared gates (cap, kit, power headroom).
#
# Rules (operator, the two recorded runs):
#   atmosphere  generators of the focus pillar where slots and power allow;
#               a Mk II / Mk III pack in place before another Mk I machine
#               (no slot, no script).
#   power       a generator by grid phase on a deficit with a low reserve;
#               the battery floor (Smelters / Fabricators must start while
#               turbines are parked); one tank per produced fluid at its
#               producer outpost.
#   factory     Smelter / Fabricator hosts full and busy: a pack first, else
#               one more machine at the host with room.
#   kits        phase build-outs by research: two Seed Makers at unlock, a
#               Depot and Service Station per item outpost, the Mixer at
#               Biosphere, Weather Stations, Lead Casks and the Fuel
#               Assembler ahead of the Nuclear Program, a Steam Condenser.
#   retire      spare Weather Stations while nuclear is locked, Storage Bins
#               beside a Warehouse, batteries above the floor on steam / oil
#               grids (the bio chain of a finished biome is retired by
#               lib/bio_retire.py on its own). Retire rows go straight to
#               undeploy: no machine script answers the build.retire handshake.
#   fleet       a scout drone before an extractor drone, two extractor drones
#               per essence biome, haulers against the pickup backlog, a
#               Pioneer miner for an outpost with a NEED ore and no miner,
#               another while a NEED ore its miners reach stays open and none
#               is idle, up to four per outpost and twelve in all, none once
#               every Smelter ore has a drill; all retire once every Smelter
#               ore has a drill (idle ones refit, lib/pioneer_refit.py); Pioneer
#               haulers above MAX_PIONEER_HAULERS (SALT_PIONEER_HAULERS for
#               pump salt once drones carry the freight) retire (idle scouts,
#               builders and miners refit, lib/pioneer_refit.py; hauler is the role they
#               fall back to); a plated drone before the Nuclear Program. Queued commission
#               jobs count as units ("queued" in the fleet counts) and a role
#               with a decommission in flight ("retiring") gets no second -1.

import game_phase
from autoplay_roles import TANKS, WAREHOUSES, kit_id, role_list
from focus_plan import KEY_PILLARS, PILLARS
from game_rules import BIOMES
from item_tiers import DEPOT_KIT_TIERS, DEPOT_TYPE_TIERS
from outpost_needs import BUSY_SHARE, BUSY_SHARE_EXTRA, LEAD_TICKS, MAX_FACTORY_HOSTS, NUCLEAR_RESEARCH, busy_share, factory_hosts, urgency_for
from pillar_swap import MAX_SWAP_TIER, pack_id

GENERATOR_DRAW_W = {"oxygen_generator": 8.0, "pressure_generator": 7.0, "temp_heater": 0.0}  # Mk I draw (spec powerDraw)
TIER_DRAW_FACTOR = {1: 1.0, 2: 5.0, 3: 20.0, 4: 100.0}  # pack multipliers (Mk II x5, Mk III x20, Mk IV x100 of Mk I; simworker jg())
MACHINE_PACKS = {"smelter": "smelter_upgrade_pack_mk", "fabricator": "fabricator_upgrade_pack_mk"}
MACHINE_MAX_TIER = 3
UPGRADES_PER_PASS = 3  # pack proposals of one type per pass
KEEP_FREE_SLOTS = 1  # slots a host keeps when generators fill it
POWER_MARGIN_W = 20.0  # headroom a deploy must leave on its grid
RESERVE_LOW = 0.5  # reserve fraction under which a deficit asks for a generator
BATTERY_FLOOR_WH = 1500.0  # bank a grid with Smelters / Fabricators keeps (their start load for ~15 min)
BATTERY_WH = {"battery": 500.0, "battery_large": 2000.0}
BATTERY_SURPLUS_WH = 2000.0  # bank above the floor on a steam / oil grid that retires a battery
FLUID_TANK = {"steam": "gas_tank", "water": "liquid_tank", "oil": "liquid_tank"}
PRODUCER_FLUIDS = {"power": ("steam",), "condenser": ("water",), "liquifier_": ()}
SEED_MAKERS = 2
LEAD_CASKS = 2
MINERS_PER_BIOME = 2
MAX_MINERS_PER_OUTPOST = 4  # Pioneer miners stationed at one outpost
MAX_PIONEER_MINERS = 12
MINER_BACKLOG_TICKS = 36000  # NEED ore open this long with no idle miner there: one more miner
MAX_PIONEER_HAULERS = 4  # fleet-wide: haulers float (set_base()); idle Pioneers of other roles refit to hauler
SALT_PIONEER_HAULERS = 2  # drone yield on and a hauler drone flying: drones carry the freight, these fetch pump salt (= role_demand.SALT_HAULERS)
HAUL_BACKLOG_TICKS = 36000
GENERATOR_TYPES = tuple(PILLARS.values())
FACTORY_TYPES = ("smelter", "fabricator")
STEAM_PHASES = ("steam", "oil")
POWER_TYPES = ("solar_generator", "steam_turbine", "oil_generator", "reactor")


def want(kind, provider, why, **fields):
    out = {"kind": kind, "provider": provider, "why": why, "outpost": None, "type_id": None, "count": 1, "machine_id": None, "item_id": None, "fleet_kind": None, "role": None, "delta": 0, "blocked": None}
    out.update(fields)
    return out


def outposts(ctx):
    return (ctx.get("snap") or {}).get("outposts") or []


def home(ctx):
    for entry in outposts(ctx):
        if entry.get("home"):
            return entry
    return None


def free_slots(entry):
    return int(entry.get("capacity", 0)) - int(entry.get("used", 0))


def pending(ctx, grid):
    """{type_id: n} of the open deploys (outpost "reserved", building_plan.reserve_open()) on the grid's outposts."""
    out = {}
    for entry in outposts(ctx):
        if entry["id"] in (grid.get("outposts") or []):
            for type_id, n in (entry.get("reserved") or {}).items():
                out[type_id] = out.get(type_id, 0) + n
    return out


def kits(ctx):
    return (ctx.get("snap") or {}).get("kits") or set()


def pack_ok(ctx, item_id):
    return item_id in (ctx.get("prices") or {}) or (ctx.get("inventory") or {}).get(item_id, 0) > 0


def grid_of(ctx, outpost_id):
    for grid in ctx.get("grids") or []:
        if outpost_id in (grid.get("outposts") or []):
            return grid
    return None


def headroom_w(grid):
    if grid is None:
        return None
    return float(grid.get("generated", 0.0)) - float(grid.get("consumed", 0.0))


def generator_draw(type_id, tier):
    """Draw in W of one atmosphere generator of `type_id` at `tier`."""
    return GENERATOR_DRAW_W.get(type_id, 0.0) * TIER_DRAW_FACTOR.get(tier, 1.0)


def power_block(ctx, outpost_id, draw_w):
    """Reason the grid cannot carry `draw_w` more, else None (an outpost without a grid is not blocked)."""
    grid = grid_of(ctx, outpost_id)
    if grid is None:
        return None
    room = headroom_w(grid) or 0.0
    if room - draw_w < POWER_MARGIN_W:
        return f"power: {room:.0f} W headroom on {grid.get('anchor')}, needs {draw_w:.0f} W"
    return None


# ---------- atmosphere ----------


def atmosphere_wants(ctx):
    focus = ctx.get("focus") or {}
    key = focus.get("pillar")
    if not key or key not in PILLARS or focus.get("swap"):
        return []
    type_id = PILLARS[key]
    out = []
    standing = (ctx.get("generators") or {}).get(type_id) or []
    for tier in range(1, MAX_SWAP_TIER):
        pack = pack_id(type_id, tier + 1)
        if not pack_ok(ctx, pack):
            continue
        candidates = [row for row in standing if row[2] == tier][:UPGRADES_PER_PASS]
        for machine_id, outpost_id, _tier in candidates:
            draw = generator_draw(type_id, tier + 1) - generator_draw(type_id, tier)
            out.append(want("upgrade", "atmosphere", f"focus {key}: Mk {tier + 1} pack in place (no slot, no script)", outpost=outpost_id, type_id=type_id, machine_id=machine_id, item_id=pack, blocked=power_block(ctx, outpost_id, draw)))
        if candidates:
            return out
    if kit_id(type_id) not in kits(ctx):
        return out
    hosts = [entry for entry in outposts(ctx) if free_slots(entry) > KEEP_FREE_SLOTS and (entry.get("home") or "terraform" in role_list(entry.get("roles")) or any(entry.get("types", {}).get(t, 0) > 0 for t in GENERATOR_TYPES))]
    hosts.sort(key=lambda entry: (not entry.get("home"), -free_slots(entry), entry["id"]))
    for entry in hosts[:1]:
        count = free_slots(entry) - KEEP_FREE_SLOTS
        room = headroom_w(grid_of(ctx, entry["id"]))
        draw = generator_draw(type_id, 1)
        if room is not None and draw > 0:
            count = min(count, int(max(0.0, room - POWER_MARGIN_W) // draw))
        if count <= 0:
            out.append(want("deploy", "atmosphere", f"focus {key}: generators wait for power on {entry['id']}", outpost=entry["id"], type_id=type_id, count=1, blocked=power_block(ctx, entry["id"], draw)))
        else:
            out.append(want("deploy", "atmosphere", f"focus {key}: {count} generator(s) fit {entry['id']} within slots and power", outpost=entry["id"], type_id=type_id, count=count))
    return out


# ---------- power ----------


def generator_for(ctx, grid):
    """Generator type for a deficit on `grid` by its phase and the unlocked kits."""
    available = kits(ctx)
    phase = grid.get("phase")
    if phase == "reactor" and "reactor" in available:
        return "reactor"
    if phase in STEAM_PHASES or grid.get("types", {}).get("steam_turbine", 0) > 0:
        if "oil_generator" in available and any(entry.get("types", {}).get("liquid_tank", 0) > 0 for entry in outposts(ctx) if entry["id"] in grid.get("outposts", [])):
            return "oil_generator"
        if "steam_turbine" in available:
            return "steam_turbine"
    if "steam_turbine" in available and grid.get("types", {}).get("gas_tank", 0) > 0:
        return "steam_turbine"
    return "solar_generator" if "solar_generator" in available else None


def host_on_grid(ctx, grid, type_id=None):
    """Grid outpost with the most free slots (one holding `type_id` first)."""
    rows = [entry for entry in outposts(ctx) if entry["id"] in (grid.get("outposts") or []) and free_slots(entry) > 0]
    rows.sort(key=lambda entry: (not (type_id and entry.get("types", {}).get(type_id, 0) > 0), -free_slots(entry), entry["id"]))
    return rows[0] if rows else None


def power_wants(ctx):
    out = []
    for grid in ctx.get("grids") or []:
        room = headroom_w(grid)
        reserve = grid.get("reserve")
        waiting = pending(ctx, grid)
        if room is not None and room < 0 and (reserve is None or reserve < RESERVE_LOW) and not any(waiting.get(t) for t in POWER_TYPES):
            type_id = generator_for(ctx, grid)
            host = host_on_grid(ctx, grid, type_id)
            if type_id and host:
                out.append(want("deploy", "power", f"{grid.get('anchor')}: {-room:.0f} W short, reserve {'unknown' if reserve is None else str(int(reserve * 100)) + ' %'}", outpost=host["id"], type_id=type_id))
        machines = sum(grid.get("types", {}).get(t, 0) for t in FACTORY_TYPES)
        bank = float(grid.get("capacity", 0.0)) + sum(waiting.get(t, 0) * wh for t, wh in BATTERY_WH.items())
        if machines and bank < BATTERY_FLOOR_WH:
            battery = "battery_large" if "battery_large" in kits(ctx) else "battery"
            host = host_on_grid(ctx, grid, battery)
            if battery in kits(ctx) and host:
                short = BATTERY_FLOOR_WH - bank
                count = max(1, int((short + BATTERY_WH[battery] - 1) // BATTERY_WH[battery]))
                out.append(want("deploy", "power", f"{grid.get('anchor')}: battery floor {BATTERY_FLOOR_WH:.0f} Wh for {machines} Smelter(s)/Fabricator(s), bank {float(grid.get('capacity', 0.0)):.0f} Wh", outpost=host["id"], type_id=battery, count=count))
    for entry in outposts(ctx):
        types = entry.get("types") or {}
        for role in role_list(entry.get("roles")):
            fluids = PRODUCER_FLUIDS.get(role, ())
            for fluid in fluids:
                tank = FLUID_TANK[fluid]
                if types.get(tank, 0) == 0 and types.get("bulk_liquid_reservoir", 0) == 0 and tank in kits(ctx):
                    out.append(want("deploy", "power", f"{role} at {entry['id']} buffers {fluid} in its own tank", outpost=entry["id"], type_id=tank))
    return out


# ---------- factory ----------


def factory_wants(ctx):
    out = []
    snap = ctx.get("snap") or {}
    bar = BUSY_SHARE_EXTRA if len(factory_hosts(outposts(ctx))) >= MAX_FACTORY_HOSTS else BUSY_SHARE
    for role, type_id in (("smelter", "smelter"), ("factory", "fabricator")):
        busy = busy_share(snap, role)
        if busy is None or busy < bar:
            continue
        standing = (ctx.get("machines") or {}).get(type_id) or []
        if not standing:
            continue
        for tier in range(1, MACHINE_MAX_TIER):
            pack = MACHINE_PACKS[type_id] + str(tier + 1)
            if not pack_ok(ctx, pack):
                continue
            candidates = [row for row in standing if row[2] == tier][:UPGRADES_PER_PASS]
            for machine_id, outpost_id, _tier in candidates:
                out.append(want("upgrade", "factory", f"{type_id}s {int(busy * 100)} % busy: Mk {tier + 1} pack before another machine", outpost=outpost_id, type_id=type_id, machine_id=machine_id, item_id=pack))
            if candidates:
                break
        else:
            hosts = [entry for entry in outposts(ctx) if entry.get("types", {}).get(type_id, 0) > 0 and free_slots(entry) > 0 and not entry.get("home")]
            hosts.sort(key=lambda entry: (-free_slots(entry), entry["id"]))
            if hosts and kit_id(type_id) in kits(ctx):
                out.append(want("deploy", "factory", f"{type_id}s {int(busy * 100)} % busy, every pack applied", outpost=hosts[0]["id"], type_id=type_id))
    return out


# ---------- phase kits ----------


def count_type(ctx, type_id):
    return sum(entry.get("types", {}).get(type_id, 0) for entry in outposts(ctx))


def kit_wants(ctx):
    out = []
    phase = ctx.get("phase") or {}
    available = kits(ctx)
    base = home(ctx)
    if base is None:
        return out
    if game_phase.unlocked(phase, "research_seed_maker") and "seed_maker" in available and count_type(ctx, "seed_maker") < SEED_MAKERS:
        out.append(want("deploy", "kits", "seed recipes take long: two Seed Makers from the unlock", outpost=base["id"], type_id="seed_maker", count=SEED_MAKERS - count_type(ctx, "seed_maker")))
    depot_kit = next((kit for kit in DEPOT_KIT_TIERS if kit in available), None)
    for entry in outposts(ctx):
        types = entry.get("types") or {}
        item_roles = any(role in ("smelter", "factory", "mining", "storage") or role.startswith(("bio_", "liquifier_")) for role in role_list(entry.get("roles")))
        if not item_roles and not any(types.get(t, 0) > 0 for t in FACTORY_TYPES + tuple(WAREHOUSES)):
            continue
        if depot_kit and not any(types.get(t, 0) > 0 for t in DEPOT_TYPE_TIERS):
            out.append(want("deploy", "kits", f"{entry['id']} moves items: a Drone Depot", outpost=entry["id"], type_id=DEPOT_TYPE_TIERS[DEPOT_KIT_TIERS.index(depot_kit)]))
    if "drone_service_station_kit" in available and count_type(ctx, "drone_service_station") == 0 and depot_kit:
        out.append(want("deploy", "kits", "first Drone Service Station at home", outpost=base["id"], type_id="drone_service_station"))
    if game_phase.biosphere_unlocked(phase) and "biomass_mixer" in available and count_type(ctx, "biomass_mixer") == 0:
        out.append(want("deploy", "kits", "Biosphere unlocked: the Biomass Mixer", outpost=base["id"], type_id="biomass_mixer"))
    eta = game_phase.research_eta_ticks(phase, NUCLEAR_RESEARCH)
    if game_phase.nuclear_ahead(phase) and (urgency_for(eta, LEAD_TICKS["found"]) in ("now", "soon") or game_phase.unlocked(phase, NUCLEAR_RESEARCH)):
        if "weather_station" in available:
            covered = {entry.get("biome") for entry in outposts(ctx) if entry.get("types", {}).get("weather_station", 0) > 0}
            for entry in outposts(ctx):
                if entry.get("biome") in BIOMES and entry.get("biome") not in covered and free_slots(entry) > 0:
                    out.append(want("deploy", "kits", f"Nuclear Program ahead: Weather Station in {entry.get('biome')} (uranium aftermaths)", outpost=entry["id"], type_id="weather_station"))
                    covered.add(entry.get("biome"))
        if "lead_cask" in available and count_type(ctx, "lead_cask") < LEAD_CASKS:
            out.append(want("deploy", "kits", "Nuclear Program ahead: Lead Casks for Raw Uranium", outpost=base["id"], type_id="lead_cask", count=LEAD_CASKS - count_type(ctx, "lead_cask")))
        if "fuel_assembler" in available and count_type(ctx, "fuel_assembler") == 0:
            out.append(want("deploy", "kits", "Nuclear Program ahead: the Fuel Assembler", outpost=base["id"], type_id="fuel_assembler"))
    if game_phase.unlocked(phase, "research_steam_condenser") and "steam_condenser" in available and count_type(ctx, "steam_condenser") == 0:
        hosts = [entry for entry in outposts(ctx) if "power" in role_list(entry.get("roles")) and free_slots(entry) > 0]
        if hosts:
            out.append(want("deploy", "kits", "Steam Condensation unlocked: water from surplus steam at the steam host", outpost=hosts[0]["id"], type_id="steam_condenser"))
    return out


# ---------- retire ----------


def retire_wants(ctx):
    out = []
    phase = ctx.get("phase") or {}
    for entry in outposts(ctx):
        types = entry.get("types") or {}
        if types.get("storage_bin", 0) > 0 and any(types.get(t, 0) > 0 for t in WAREHOUSES):
            for machine_id in (ctx.get("machine_ids") or {}).get((entry["id"], "storage_bin"), []):
                out.append(want("retire", "retire", f"{entry['id']} has a Warehouse: Storage Bins give the slot back", outpost=entry["id"], type_id="storage_bin", machine_id=machine_id))
    if not game_phase.unlocked(phase, NUCLEAR_RESEARCH) and urgency_for(game_phase.research_eta_ticks(phase, NUCLEAR_RESEARCH), LEAD_TICKS["found"]) == "later":
        stations = []
        for entry in outposts(ctx):
            if any(role.startswith("weather_") for role in role_list(entry.get("roles"))):
                continue
            stations.extend((entry["id"], machine_id) for machine_id in (ctx.get("machine_ids") or {}).get((entry["id"], "weather_station"), []))
        for outpost_id, machine_id in stations[1:]:
            out.append(want("retire", "retire", "Weather Stations wait for the Nuclear Program; one stays for storm glass", outpost=outpost_id, type_id="weather_station", machine_id=machine_id))
    for grid in ctx.get("grids") or []:
        if grid.get("phase") not in STEAM_PHASES or float(grid.get("stored", 0.0)) < BATTERY_FLOOR_WH + BATTERY_SURPLUS_WH:
            continue  # a bank that is large on paper but drained is no surplus
        surplus = float(grid.get("capacity", 0.0)) - BATTERY_FLOOR_WH - BATTERY_SURPLUS_WH
        for outpost_id in grid.get("outposts") or []:
            for machine_id in (ctx.get("machine_ids") or {}).get((outpost_id, "battery"), []):
                if surplus < BATTERY_WH["battery"]:
                    break
                surplus -= BATTERY_WH["battery"]
                out.append(want("retire", "retire", f"{grid.get('anchor')} on {grid.get('phase')}: bank above the floor by {surplus + BATTERY_WH['battery']:.0f} Wh", outpost=outpost_id, type_id="battery", machine_id=machine_id))
    return out


# ---------- fleet ----------


def fleet_count(ctx, kind, role):
    """Units of kind / role flying plus the commission jobs queued for them ("queued" counts)."""
    fleet = ctx.get("fleet") or {}
    return int((fleet.get(kind) or {}).get(role, 0)) + int(((fleet.get("queued") or {}).get(kind) or {}).get(role, 0))


def retiring(ctx, kind, role):
    """True while a decommission of that kind / role is in flight ("retiring" counts)."""
    return int((((ctx.get("fleet") or {}).get("retiring") or {}).get(kind) or {}).get(role, 0)) > 0


def fleet_wants(ctx):
    out = []
    phase = ctx.get("phase") or {}
    available = kits(ctx)
    drones = "drone_small" in available or "drone_medium" in available or "drone_large" in available
    essence_biomes = sorted({entry.get("biome") for entry in outposts(ctx) if any(role.startswith(("liquifier_", "bio_")) for role in role_list(entry.get("roles"))) and entry.get("biome")})
    if drones and essence_biomes:
        if fleet_count(ctx, "drone", "scout") == 0:
            out.append(want("fleet", "fleet", "a scout drone scans the biosites before any extractor drone can work", fleet_kind="drone", role="scout", delta=1))
        wanted = MINERS_PER_BIOME * len(essence_biomes)
        have = fleet_count(ctx, "drone", "miner")
        if have < wanted:
            out.append(want("fleet", "fleet", f"{MINERS_PER_BIOME} extractor drones per essence biome ({', '.join(essence_biomes)}), {have} flying", fleet_kind="drone", role="miner", delta=wanted - have, blocked=None if fleet_count(ctx, "drone", "scout") else "scout first"))
    if drones and (ctx.get("pickup_backlog") or 0) >= HAUL_BACKLOG_TICKS:
        out.append(want("fleet", "fleet", f"pickups wait {int(ctx['pickup_backlog'] / 36000)} h: one more hauler drone", fleet_kind="drone", role="hauler", delta=1))
    miners = fleet_count(ctx, "pioneer", "miner")
    if miners > 0 and game_phase.drills(phase) and not retiring(ctx, "pioneer", "miner"):
        missing = ctx.get("drills_missing") or []
        out.append(want("fleet", "fleet", "drills cover every Smelter ore: Pioneer miners are free" if not missing else "drills missing on " + ", ".join(missing), fleet_kind="pioneer", role="miner", delta=-1, blocked=None if not missing else "no drill on " + ", ".join(missing)))
    out.extend(miner_wants(ctx))
    out.extend(pioneer_surplus_wants(ctx))
    if game_phase.nuclear_ahead(phase) and urgency_for(game_phase.research_eta_ticks(phase, NUCLEAR_RESEARCH), LEAD_TICKS["found"]) in ("now", "soon") and fleet_count(ctx, "drone", "aftermath") == 0 and count_type(ctx, "weather_station") > 0 and drones:
        out.append(want("fleet", "fleet", "Nuclear Program ahead: a plated drone for uranium aftermaths", fleet_kind="drone", role="aftermath", delta=1))
    return out


def drones_haul(ctx):
    """Drones carry the freight: the FLEET card's drone yield switch is on and a hauler drone flies."""
    return bool(ctx.get("drone_yield")) and fleet_count(ctx, "drone", "hauler") > 0


def pioneer_surplus_wants(ctx):
    """
    -1 rows for Pioneers no work keeps. Haulers above max(MAX_PIONEER_HAULERS,
    hauler wanted); once drones carry the freight, above SALT_PIONEER_HAULERS
    (pump salt), builders and miners above max(keep, wanted) (miners: fleet
    totals of the per-outpost entries) and, with the salt haulers there,
    scouts above max(keep, wanted) (none once the survey is complete).
    Builders, miners and scouts need a fresh role demand. Idle Pioneers of other roles
    refit (lib/pioneer_refit.py) rather than wait for these.
    """
    out = []
    roles = ctx.get("pioneer_roles") or {}
    haulers = fleet_count(ctx, "pioneer", "hauler")
    if drones_haul(ctx):
        # Hauler demand counts drone-servable deficits too, so it doesn't raise this floor.
        keep_haulers, why = SALT_PIONEER_HAULERS, f"drone haulers carry the freight: keep {SALT_PIONEER_HAULERS} Pioneer haulers for pump salt"
    else:
        keep_haulers = max(MAX_PIONEER_HAULERS, int((roles.get("hauler") or {}).get("wanted") or 0))
        why = f"{haulers} Pioneer haulers: idle Pioneers refit to hauler, keep {keep_haulers}"
    if haulers > keep_haulers and not retiring(ctx, "pioneer", "hauler"):
        out.append(want("fleet", "fleet", why, fleet_kind="pioneer", role="hauler", delta=-1))
    if not drones_haul(ctx):
        return out
    for role in ("builder", "miner", "scout"):
        entry = roles.get(role)
        if entry is None or retiring(ctx, "pioneer", role):
            continue
        have, keep = fleet_count(ctx, "pioneer", role), max(int(entry.get("keep") or 0), int(entry.get("wanted") or 0))
        if role == "scout" and haulers < SALT_PIONEER_HAULERS:
            continue  # a spare scout refits to a free salt hauler slot first
        if have > keep:
            why = f"drone haulers carry the freight: keep {keep} {role}s, sell the rest" if keep else "survey complete: the scout is obsolete"
            out.append(want("fleet", "fleet", why, fleet_kind="pioneer", role=role, delta=-1))
    return out


def drilled_ores(ctx):
    """Ores with a surveyed site that has a drill: the drill feeds them, not a Pioneer."""
    return {row.get("item") for row in (ctx.get("snap") or {}).get("ore_sites") or [] if row.get("drill")}


def miner_wants(ctx):
    """
    Per-outpost Pioneer miners. +1 for an outpost with a NEED ore and no
    miner, or with a NEED ore its miners reach open MINER_BACKLOG_TICKS since
    the need or its newest miner, none idle and none queued (a new miner
    carries the same best drill and battery, so an ore the others can't
    reach is no reason). Ores a drill feeds don't count; none once drills cover every
    Smelter ore. No idle retire: an idle miner refits or re-stations
    (role_demand miner entry), pioneer_surplus_wants() sells the surplus.
    """
    out = []
    tick = ctx.get("tick", 0)
    drills_done = game_phase.drills(ctx.get("phase") or {}) and not ctx.get("drills_missing")
    miners = ctx.get("miners") or {}
    total = sum(int(slot.get("count") or 0) for slot in miners.values())
    drilled = drilled_ores(ctx)
    sited = {row.get("item") for row in (ctx.get("snap") or {}).get("ore_sites") or []}
    for outpost_id, ores in sorted((ctx.get("ore_need") or {}).items()):
        slot = miners.get(outpost_id) or {}
        have = int(slot.get("count") or 0)
        if drills_done or have >= MAX_MINERS_PER_OUTPOST or slot.get("queued"):
            continue
        reach = set((ctx.get("mining_reach") or {}).get(outpost_id) or ())
        open_ores = {ore: since for ore, since in ores.items() if ore not in drilled}
        uncovered = sorted(open_ores) if have == 0 else []
        newest = slot.get("newest") or 0
        backlog = sorted(ore for ore, since in open_ores.items() if have and ore in reach and slot.get("idle_since") is None and tick - max(since, newest) >= MINER_BACKLOG_TICKS)
        if uncovered:
            why = f"{outpost_id} needs {', '.join(uncovered)} and has no miner"
        elif backlog:
            why = f"{outpost_id} needs {', '.join(backlog)} for {MINER_BACKLOG_TICKS // 36000} h and its {have} miners are busy"
        else:
            continue
        missing = [ore for ore in uncovered or backlog if ore not in sited]
        blocked = f"fleet cap {MAX_PIONEER_MINERS}" if total >= MAX_PIONEER_MINERS else ("no surveyed " + ", ".join(missing) + " site" if len(missing) == len(uncovered or backlog) else None)
        out.append(want("fleet", "fleet", why, outpost=outpost_id, fleet_kind="pioneer", role="miner", delta=1, blocked=blocked))
    return out


PROVIDERS = (("atmosphere", atmosphere_wants), ("power", power_wants), ("factory", factory_wants), ("kits", kit_wants), ("retire", retire_wants), ("fleet", fleet_wants))


def all_wants(ctx):
    """Every provider's wants, in PROVIDERS order."""
    out = []
    for _name, provider in PROVIDERS:
        out.extend(provider(ctx))
    return out


def pillar_of(type_id):
    """Pillar id of a generator type (game_phase pillar ids), None otherwise."""
    for key, generator in PILLARS.items():
        if generator == type_id:
            return KEY_PILLARS[key]
    return None


def tank_types():
    return tuple(TANKS)
