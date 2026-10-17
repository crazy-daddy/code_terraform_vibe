# Need model of the outpost founding planner (docs/plans/outpost_founding_planner.md):
# which roles the outpost network lacks now and later, and which of them an
# existing outpost can take (designate) before a new one is founded.
#
# Input is one plain snapshot (snapshot() reads it in game; tests build it):
#   {"outposts": [{"id", "x", "y", "biome", "home", "roles": [designated],
#                  "types": {type_id: n}, "used", "capacity"}],
#    "kits": set of available kit ids (autoplay_roles.unlocked()),
#    "bio_orders": {biome: open Bio Orders},
#    "essences_required": Biomass phase minimum (None without a Mixer),
#    "ore_wanted": [ore, ...] the Smelters have a recipe for,
#    "ore_sites": extractor_plan.mining_sites() rows,
#    "fluid_sites": supply_tiers.fluid_sites() rows,
#    "fluids_in": [fluid, ...] the designated roles take,
#    "range_m": mining range of an outpost (outpost_mining),
#    "stock": {role: [item_id, ...]} Warehouse stock lists (read_stock_items()),
#    "per_warehouse": slots of the Warehouse kind to build: 5, 15 once the
#                     Large Warehouse kit is available. Wildlife roles unlock
#                     after it (Plants 2,250,000 vs Biomass 30,000), so they
#                     are always sized with 15,
#    "refused": [[role, outpost_id], ...] designations the operator rejected
#               (outpost_plan); host_check() skips them,
#    "refused_roles": [role, ...] roles the operator rejected twice within the
#               hold (outpost_plan): no need for them at all,
#    "activity": {"smelter": busy share 0..1, "fabricator": ...} from
#               machine_activity (None when unknown),
#    "phase": game_phase.snapshot() (research, pillars, history; {} offline)}
#
# A need is {"role", "biome", "urgency", "why", "found", "locked"} (+ "ores"
# for mining, "blocked_by" the research a look-ahead need waits for,
# "off_home" when home may not host it). Urgency:
#   now   live demand nothing covers: open Bio Orders of a biome without its
#         bio_<biome> chain; Biomass phase minimum above the biomes making
#         essence (the deficit, missing biomes with an outpost first); the
#         first factory host off home once outposts and the Fabricator are
#         unlocked.
#   soon  the next Biomass phase's essence; a wanted ore whose surveyed sites
#         are all out of every outpost's mining range; another Smelter /
#         Fabricator host while every host is full AND busy (lookahead(),
#         at most MAX_FACTORY_HOSTS off home unless busier still); a refined
#         exotic a designated role takes, with its raw deposit surveyed and
#         no refinery anywhere; a terraform host when no outpost has
#         TERRA_MIN_FREE slots for generators; a storage outpost when tanks
#         crowd a penalized outpost.
#   look-ahead by ETA (lookahead(), once outposts are unlocked): a research milestone the coming phase
#         needs an outpost for (power near a thermal vent before Thermal
#         Caps, the frozen essence chain off home before Wildlife, the
#         reactor bundle before the Nuclear Program, once Wildlife is unlocked:
#         the Nuclear Program sits at the end of the TP ladder and the early TP
#         rate would put it hours away) is "now" when its ETA
#         (game_phase, pillar history) is within LEAD_TICKS, "soon" within
#         twice that, else "later". These needs carry blocked_by and keep
#         their urgency while the role's kit is still locked.
#   later end-state checklist: weather_<biome> and liquifier_<biome> in every
#         biome, bio_<biome> where the biome has a processor. Any other
#         locked role (autoplay_roles.unlocked() False) is "later".
# Only now/soon needs make a proposal. A role is covered by an outpost that
# designates it, or whose buildings make it up (observed; family sub-roles
# only when biome-locked, since a tank or Refiner does not tell its fluid);
# an off_home need ignores home's cover. Earth orders for life forms are no
# need: drones catch them anywhere.
#
# plan_hosts() merges needs onto existing outposts first (biome lock, slots
# under the cap when the bundle has a penalized machine, a Drone Depot added
# for item roles, new Warehouses for the added stock counted against the cap
# (autoplay_roles.site_slots(), home included), the role's site within
# reach, an exclusive host (reactor) only with EXCLUSIVE_SHARE_ROLES). Home
# hosts other roles only until wildlife is unlocked (Habitat kit available, a
# Habitat at home, or wildlife designated there); from then on its slots are
# reserved for HOME_RESERVED_ROLES (farm, Plant Terraformers, Feed Makers,
# Habitats: Forage comes from the home field). Home takes no Smelter or
# Fabricator once a factory outpost exists, until wildlife is complete
# (operator, run 2). Factory designations are never released by the planner:
# moving one orphans the ores and ingots in its Warehouses. Leftover found
# needs group into founding bundles: one per biome lock, one for mining, one
# per exclusive role, one for the rest. refinery never founds (found False):
# it goes onto an outpost with a raw exotic deposit within
# supply_tiers.NEAR_TILES. It takes every raw exotic and makes every refined
# one (the Refiner picks its recipe network-wide).

from typing import TYPE_CHECKING

import autoplay_roles
import game_phase
from archive import archive
from atomic import run_batched
from autoplay_roles import BIO_PROCESSORS, EXCLUSIVE_SHARE_ROLES, HOME_RESERVED_ROLES, TANKS, WAREHOUSE_SLOTS, biome_ok, observed, observed_roles, role_flag, site_slots, unlocked, warehouse_slots
from extractor_plan import mining_sites, smelter_outposts
from game_clock import now_tick
from game_rules import BIOMES, RAW_ORE_ITEM_IDS
from grid_geom import outpost_box
from infra_topology import surveyed_sites
from outpost_mining import resource_assignment_range_m
from storage import PENALIZED_TYPES
from supply_tiers import NEAR_TILES, fluid_sites, gap
from swallow import swallowed
from wildlife_common import FEED_KEY, recipe_of
from wildlife_data import SPECIES

if TYPE_CHECKING:
    from typing import Callable, TypeVar

    from tree_console import TreeConsole

    _T = TypeVar("_T")

URGENCIES = ("now", "soon", "later")
PROPOSE_URGENCIES = ("now", "soon")
FACTORY_ROLES = ("smelter", "factory")  # hosts full and busy everywhere -> another host "soon"
FOUNDED_CAPACITY = 20  # building cap of a founded outpost before Weather / Outpost Expansion bonuses
EXTRA_HOST_ROLES = FACTORY_ROLES + ("mining", "terraform")  # a need for one more host, not for a first one
REFINED_EXOTICS = ("sulfur_gas", "chlorine", "cryofluid", "quicksilver")
HOUR_TICKS = 36000
LEAD_TICKS = {"found": 12 * HOUR_TICKS, "designate": 6 * HOUR_TICKS}  # how far ahead a look-ahead need turns "now"
ACTIVITY_GROUPS = {"smelter": "smelter", "factory": "fabricator"}  # role -> machine_activity group
BUSY_SHARE = 0.7  # utilisation of a Smelter / Fabricator group before its full hosts ask for another
BUSY_SHARE_EXTRA = 0.9  # the same past MAX_FACTORY_HOSTS factory outposts
HOST_FULL_SHARE = 0.7  # used / capacity from which a factory host counts as full
MAX_FACTORY_HOSTS = 2  # factory outposts off home before the higher busy bar applies (operator: a 3rd adds logistics)
TERRA_MIN_FREE = 2  # free slots an outpost must keep for generators, else a terraform host is wanted
STORAGE_TANKS_MIN = 4  # tanks at a penalized outpost near its cap that ask for a storage outpost
EARLY_ORES = ("iron_ore", "silicon")  # ores the first factory host wants before any Smelter recipe is readable
OUTPOSTS_RESEARCH = "research_outpost_hub"
FABRICATOR_RESEARCH = "research_fabricator"
THERMAL_CAP_RESEARCH = "research_thermal_cap"
NUCLEAR_RESEARCH = "research_nuclear_program"
ESSENCE_TYPES = ("biomass_mixer", "essence_liquifier")
SITE_CHUNK = 8  # surveyed sites read per atomic slice in snapshot() (60 sites in one go pass the 10,000-step cap)


def _rank(urgency):
    return URGENCIES.index(urgency) if urgency in URGENCIES else len(URGENCIES)


def _need(role, urgency, why, **extra):
    need = {"role": role, "biome": role_flag(role, "biome"), "urgency": urgency, "why": why, "found": role != "refinery", "locked": False}
    need.update(extra)
    return need


def urgency_for(eta, lead):
    """now within `lead` ticks (0 = reached), soon within twice that, later beyond or without an ETA."""
    if eta is None:
        return "later"
    if eta <= lead:
        return "now"
    return "soon" if eta <= 2 * lead else "later"


def eta_text(eta):
    return "reached" if eta == 0 else ("no rate yet" if eta is None else f"~{eta / float(HOUR_TICKS):.0f} h")


def covers(entry, role):
    """True when the outpost designates `role` or its buildings make it up in the right biome."""
    if role in entry.get("roles", []):
        return True
    if role.startswith(autoplay_roles.FAMILY_PREFIXES) and role_flag(role, "biome") is None:
        return False
    return observed(role, entry.get("types", {})) and biome_ok(role, entry.get("biome"))


def hosts(role, outposts):
    """Outposts covering `role`."""
    return [entry for entry in outposts if covers(entry, role)]


def factory_hosts(outposts):
    """Outposts off home covering a Smelter or Fabricator role."""
    return [entry for entry in outposts if not entry.get("home") and any(covers(entry, role) for role in FACTORY_ROLES)]


def busy_share(snap, role):
    """Utilisation 0..1 of the role's machine group (machine_activity), None when unknown."""
    value = (snap.get("activity") or {}).get(ACTIVITY_GROUPS.get(role, role))
    return float(value) if isinstance(value, (int, float)) else None


def near_fluid(entry, snap, fluid):
    """True when a surveyed site of `fluid` lies within NEAR_TILES of the outpost footprint."""
    boxes = [row["box"] for row in snap.get("fluid_sites", []) if row["fluid"] == fluid]
    if not boxes:
        return False
    box = outpost_box(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
    return gap(box, boxes) <= NEAR_TILES


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def unreached_ores(wanted, ore_sites, outposts, range_m):
    """Wanted ores with surveyed sites, none within range_m of an outpost and none drilled (drones fetch from a drill anywhere); sorted."""
    out = []
    for ore in sorted(set(wanted)):
        sites = [row for row in ore_sites if row["item"] == ore]
        if not sites or any(row.get("drill") for row in sites):
            continue
        if not any(_dist(row["x"], row["y"], entry["x"], entry["y"]) <= range_m for row in sites for entry in outposts):
            out.append(ore)
    return out


def later_checklist():
    """End-state needs: weather_ and liquifier_ per biome, bio_ where the biome has a processor."""
    needs = []
    for biome in BIOMES:
        needs.append(_need("weather_" + biome, "later", "end state: weather station in " + biome))
        needs.append(_need("liquifier_" + biome, "later", "end state: " + biome + " essence"))
        if biome in BIO_PROCESSORS:
            needs.append(_need("bio_" + biome, "later", "end state: " + biome + " bio chain"))
    return needs


def _essence_needs(snap):
    required = snap.get("essences_required")
    if not isinstance(required, int) or required <= 0:
        return []
    outposts = snap["outposts"]
    makers = [biome for biome in BIOMES if hosts("liquifier_" + biome, outposts)]
    settled = {entry.get("biome") for entry in outposts}
    missing = sorted([biome for biome in BIOMES if biome not in makers], key=lambda biome: (biome not in settled, BIOMES.index(biome)))
    deficit = max(0, required - len(makers))
    needs = []
    for index, biome in enumerate(missing):
        if index < deficit:
            needs.append(_need("liquifier_" + biome, "now", f"biomass phase needs {required} essences, {len(makers)} made"))
        elif index == deficit and required < len(BIOMES):
            needs.append(_need("liquifier_" + biome, "soon", f"next biomass phase needs {required + 1} essences"))
    return needs


def factory_needs(snap):
    """
    Another Smelter / Fabricator host: every host of the role at or over
    HOST_FULL_SHARE of its cap AND the role's group busy (BUSY_SHARE; past
    MAX_FACTORY_HOSTS off home BUSY_SHARE_EXTRA). An unknown busy share
    never asks (operator, run 2: full but idle hosts were no reason).
    """
    outposts = snap["outposts"]
    needs = []
    extra = len(factory_hosts(outposts)) >= MAX_FACTORY_HOSTS
    for role in FACTORY_ROLES:
        found = hosts(role, outposts)
        if not found or not all(entry["used"] >= HOST_FULL_SHARE * entry["capacity"] for entry in found):
            continue
        busy = busy_share(snap, role)
        bar = BUSY_SHARE_EXTRA if extra else BUSY_SHARE
        if busy is not None and busy >= bar:
            needs.append(_need(role, "soon", f"every {role} outpost is full and {int(busy * 100)} % busy"))
    return needs


def lookahead(snap):
    """
    Needs of the coming phases, before live demand blocks (module header):
    the first factory host off home, power near a thermal vent before Thermal
    Caps, a terraform host when slots run out, the frozen essence chain off
    home before Wildlife, a storage outpost when tanks crowd production, the
    reactor bundle before the Nuclear Program.
    """
    phase = snap.get("phase") or {}
    outposts = snap["outposts"]
    home = [entry for entry in outposts if entry.get("home")]
    needs = []
    if not game_phase.unlocked(phase, OUTPOSTS_RESEARCH):
        return needs  # no outpost can be founded yet; the early buyer owns the base until then
    if not factory_hosts(outposts):
        eta = game_phase.research_eta_ticks(phase, FABRICATOR_RESEARCH)
        urgency = "now" if eta == 0 else urgency_for(eta, LEAD_TICKS["found"])
        ores = list(snap.get("ore_wanted") or EARLY_ORES)
        why = "first factory outpost: near iron, off home" + ("" if eta == 0 else f", Fabricator {eta_text(eta)}")
        needs.append(_need("smelter", urgency, why, off_home=True, blocked_by=FABRICATOR_RESEARCH, ores=ores))
        needs.append(_need("factory", urgency, why, off_home=True, blocked_by=FABRICATOR_RESEARCH))
    if any(row["fluid"] == "steam" for row in snap.get("fluid_sites", [])) and not any(near_fluid(entry, snap, "steam") for entry in outposts):
        eta = game_phase.research_eta_ticks(phase, THERMAL_CAP_RESEARCH)
        urgency = urgency_for(eta, LEAD_TICKS["found"])
        needs.append(_need("power", urgency, f"steam power near a thermal vent, Thermal Cap {eta_text(eta)}", blocked_by=THERMAL_CAP_RESEARCH, site_fluid="steam"))
    if "atmosphere" in game_phase.fronts(phase) and outposts and all(entry.get("capacity", 0) - entry.get("used", 0) < TERRA_MIN_FREE for entry in outposts):
        needs.append(_need("terraform", "soon", f"no outpost has {TERRA_MIN_FREE} free slots for generators"))
    if home and any(home[0].get("types", {}).get(type_id, 0) > 0 for type_id in ESSENCE_TYPES) and not game_phase.complete(phase, "biomass"):
        eta = game_phase.research_eta_ticks(phase, game_phase.WILDLIFE_RESEARCH)
        urgency = urgency_for(eta, LEAD_TICKS["found"])
        needs.append(_need("liquifier_frozen", urgency, f"home slots go to wildlife, Wildlife research {eta_text(eta)}: move the essence chain", off_home=True, blocked_by=game_phase.WILDLIFE_RESEARCH))
    crowded = [entry for entry in outposts if sum(entry.get("types", {}).get(t, 0) for t in TANKS) >= STORAGE_TANKS_MIN and entry.get("capacity", 0) - entry.get("used", 0) < TERRA_MIN_FREE and any(entry.get("types", {}).get(t, 0) > 0 for t in PENALIZED_TYPES)]
    if crowded and not hosts("storage", outposts):
        needs.append(_need("storage", "soon", "tanks crowd " + ", ".join(sorted(entry["id"] for entry in crowded))))
    if not hosts("reactor", outposts) and game_phase.nuclear_ahead(phase):
        eta = game_phase.research_eta_ticks(phase, NUCLEAR_RESEARCH)
        urgency = urgency_for(eta, LEAD_TICKS["found"])
        if urgency in PROPOSE_URGENCIES:
            needs.append(_need("reactor", urgency, f"Nuclear Program {eta_text(eta)}: reactor outpost with water in reach", blocked_by=NUCLEAR_RESEARCH, site_fluid="water"))
    return needs


def now_signals(snap):
    """Live-demand needs (now / soon), before unlock gating."""
    outposts = snap["outposts"]
    needs = []
    for biome in BIOMES:
        count = (snap.get("bio_orders") or {}).get(biome, 0)
        if count > 0 and not hosts("bio_" + biome, outposts):
            needs.append(_need("bio_" + biome, "now", f"{count} open {biome} Bio Order(s)"))
    needs.extend(_essence_needs(snap))
    ores = unreached_ores(snap.get("ore_wanted", []), snap.get("ore_sites", []), outposts, snap.get("range_m", 0))
    if ores:
        needs.append(_need("mining", "soon", "no outpost in range of " + ", ".join(ores), ores=ores))
    needs.extend(factory_needs(snap))
    taken = set(snap.get("fluids_in", []))
    raws = {row["fluid"] for row in snap.get("fluid_sites", [])}
    wanted = [fluid for fluid in REFINED_EXOTICS if fluid in taken and "raw_" + fluid in raws]
    if wanted and not hosts("refinery", outposts):
        needs.append(_need("refinery", "soon", ", ".join(wanted) + " taken, nothing refines it"))
    return needs


def needs(snap):
    """
    Every open need, most urgent first (then role name): now_signals() and
    later_checklist() merged per role (most urgent kept, mining ores joined),
    covered roles dropped, locked roles moved to "later".
    """
    outposts = snap["outposts"]
    kits = snap.get("kits", set())
    refused = snap.get("refused_roles") or []
    merged = {}
    for need in lookahead(snap) + now_signals(snap) + later_checklist():
        role = need["role"]
        if role in refused and need["urgency"] != "now":
            continue  # a twice-rejected role waits out the hold unless live demand blocks on it
        covering = [entry for entry in outposts if not (need.get("off_home") and entry.get("home"))]
        if role not in EXTRA_HOST_ROLES and hosts(role, covering):
            continue
        old = merged.get(role)
        if old is None or _rank(need["urgency"]) < _rank(old["urgency"]):
            merged[role] = need
    out = []
    for role, need in merged.items():
        if not unlocked(role, kits):
            need = dict(need)
            need["locked"] = True
            if not need.get("blocked_by"):
                need["urgency"] = "later"
        out.append(need)
    return sorted(out, key=lambda need: (_rank(need["urgency"]), need["role"]))


def _current_roles(entry):
    roles = list(entry.get("roles", []))
    for name in observed_roles(entry.get("types", {})):
        if name not in roles:
            roles.append(name)
    return roles


def _with_depot(roles, entry=None):
    if any(role_flag(name, "items") for name in roles) and "drone_depot" not in roles and (entry is None or not covers(entry, "drone_depot")):
        return roles + ["drone_depot"]
    return roles


def _site_ok(need, entry, snap):
    role = need["role"]
    if role == "refinery":
        raws = ["raw_" + fluid for fluid in REFINED_EXOTICS]
        box = outpost_box(entry["x"], entry["y"])
        return gap(box, [row["box"] for row in snap.get("fluid_sites", []) if row["fluid"] in raws]) <= NEAR_TILES
    if need.get("site_fluid"):
        return near_fluid(entry, snap, need["site_fluid"])
    if need.get("ores"):
        range_m = snap.get("range_m", 0)
        return all(any(_dist(row["x"], row["y"], entry["x"], entry["y"]) <= range_m for row in snap.get("ore_sites", []) if row["item"] == ore) for ore in need["ores"])
    return True


def reserved_role(role):
    """True for roles home keeps its slots for (HOME_RESERVED_ROLES, wildlife_<fluid> included)."""
    return role in HOME_RESERVED_ROLES or role.startswith("wildlife_")


def home_reserved(entry, kits):
    """True once wildlife is unlocked, a Habitat stands at home or home designates wildlife."""
    return unlocked("wildlife", kits) or entry.get("types", {}).get("habitat", 0) > 0 or any(reserved_role(name) and name not in ("farm", "plants") for name in entry.get("roles", []))


def host_check(need, entry, snap):
    """
    (roles to add, None, counted buildings added) when `entry` can take the
    need, else (None, reason, 0). Buildings include the Warehouses the
    added stock needs beyond the slots standing there (site_slots()).
    """
    role = need["role"]
    if covers(entry, role):
        return (None, "has it", 0)
    if [role, entry["id"]] in snap.get("refused", []):
        return (None, "operator rejected", 0)
    if not biome_ok(role, entry.get("biome")):
        return (None, "biome " + str(entry.get("biome")), 0)
    if entry.get("home") and need.get("off_home"):
        return (None, "off home", 0)
    current = _current_roles(entry)
    added = _with_depot([role], entry)
    if entry.get("home") and home_reserved(entry, snap.get("kits", set())) and not reserved_role(role):
        return (None, "home reserved for farm and wildlife", 0)
    if entry.get("home") and role in FACTORY_ROLES and factory_hosts(snap["outposts"]) and not game_phase.complete(snap.get("phase") or {}, "wildlife"):
        return (None, "home takes no factory role beside a factory outpost", 0)
    if role_flag(role, "exclusive") and any(name not in EXCLUSIVE_SHARE_ROLES and _penalized_role(name) for name in current):
        return (None, "exclusive role: host has other production roles", 0)
    if any(role_flag(name, "exclusive") for name in current) and role not in EXCLUSIVE_SHARE_ROLES:
        return (None, "host is exclusive (" + ", ".join(name for name in current if role_flag(name, "exclusive")) + ")", 0)
    stock = _stock(snap, need)
    per = snap.get("per_warehouse", 5)
    have_slots, have_buildings = warehouse_slots(entry.get("types", {}))
    before = site_slots(current, stock, have_slots, per)
    after = site_slots(current + added, stock, have_slots, per)
    extra = after[0] - before[0]
    used = max(entry.get("used", 0), before[0] + have_buildings)
    if after[1] and used + extra > entry.get("capacity", 0):
        return (None, f"over cap ({used}+{extra}/{entry.get('capacity', 0)}, {after[2]} new Warehouse(s))", 0)
    if not _site_ok(need, entry, snap):
        return (None, "site out of reach", 0)
    return (added, None, extra)


def _penalized_role(role):
    """True when any building of the role is a penalized machine (storage.PENALIZED_TYPES)."""
    for group in autoplay_roles.building_groups(role):
        if any(type_id in PENALIZED_TYPES for type_id in group):
            return True
    return False


def plan_hosts(open_needs, snap):
    """
    {"designate": [{"outpost", "roles", "needs", "urgency", "why"}],
     "found": [{"biome", "roles", "needs", "urgency", "why", "ores"}],
     "rejected": [(role, outpost_id, reason)]} for the now/soon needs.
    Hosts are tried by free slots (most first), then id; a host that takes a
    need counts its new roles for the next need.
    """
    outposts = []
    for entry in snap["outposts"]:
        copy = dict(entry)
        copy["roles"] = list(entry.get("roles", []))
        outposts.append(copy)
    designate = {}
    leftovers = []
    rejected = []
    for need in open_needs:
        if need["urgency"] not in PROPOSE_URGENCIES:
            continue
        order = sorted(outposts, key=lambda entry: (entry.get("used", 0) - entry.get("capacity", 0), entry["id"]))
        taken = False
        for entry in order:
            added, reason, extra = host_check(need, entry, snap)
            if added is None:
                rejected.append((need["role"], entry["id"], reason))
                continue
            entry["roles"].extend([name for name in added if name not in entry["roles"]])
            entry["used"] = entry.get("used", 0) + extra
            item = designate.setdefault(entry["id"], {"outpost": entry["id"], "roles": [], "needs": [], "urgency": need["urgency"], "why": []})
            item["roles"].extend([name for name in added if name not in item["roles"]])
            item["needs"].append(need["role"])
            item["why"].append(need["why"])
            if _rank(need["urgency"]) < _rank(item["urgency"]):
                item["urgency"] = need["urgency"]
            taken = True
            break
        if not taken and need["found"]:
            leftovers.append(need)
    return {"designate": [designate[key] for key in sorted(designate)], "found": found_bundles(leftovers, snap), "rejected": rejected}


def _stock(snap, need=None):
    """snap["stock"] with a mining need's ores as the mining list."""
    stock = dict(snap.get("stock") or {})
    if need is not None and need.get("ores"):
        stock["mining"] = list(need["ores"])
    return stock


def found_bundles(leftovers, snap=None):
    """
    Founding bundles of leftover needs: one per biome lock, one for mining,
    one for the other roles. "slots" = site_slots() of the bundle on an
    empty outpost; over_cap when a bundle with a penalized machine needs
    more than FOUNDED_CAPACITY buildings.
    """
    snap = snap or {}
    groups = {}
    for need in leftovers:
        key = need["biome"] or ("mining" if need["role"] == "mining" else ("x-" + need["role"] if role_flag(need["role"], "exclusive") else ""))
        groups.setdefault(key, []).append(need)
    bundles = []
    for key in sorted(groups):
        members = groups[key]
        roles = _with_depot([need["role"] for need in members])
        ores = sorted({ore for need in members for ore in need.get("ores", [])})
        stock = _stock(snap, {"ores": ores})
        counted, penalized, warehouses = site_slots(roles, stock, 0, snap.get("per_warehouse", 5))
        bundles.append(
            {
                "biome": members[0]["biome"],
                "roles": roles,
                "needs": [need["role"] for need in members],
                "urgency": URGENCIES[min([_rank(need["urgency"]) for need in members])],
                "why": [need["why"] for need in members],
                "ores": ores,
                "slots": {"counted": counted, "penalized": penalized, "warehouses": warehouses},
                "over_cap": bool(penalized) and counted > FOUNDED_CAPACITY,
                "blocked_by": sorted({need["blocked_by"] for need in members if need.get("blocked_by")}),
            }
        )
    return sorted(bundles, key=lambda bundle: (_rank(bundle["urgency"]), bundle["roles"]))


def log_plan(log: "TreeConsole", open_needs, plan):
    """Debug trail of one need pass (CODE_GUIDES.md#logging): needs, rejected hosts, proposals."""
    for need in open_needs:
        log.debug(f"Need {need['role']} ({need['urgency']}{', locked' if need['locked'] else ''}): {need['why']}.")
    for role, outpost_id, reason in plan["rejected"]:
        log.trace(f"Need {role}: {outpost_id} rejected ({reason}).")
    for item in plan["designate"]:
        log.debug(f"Designate {item['outpost']} +{item['roles']} ({item['urgency']}): {'; '.join(item['why'])}.")
    for bundle in plan["found"]:
        slots = bundle["slots"]
        log.debug(f"Found {bundle['biome'] or 'any biome'} {bundle['roles']} ({bundle['urgency']}, {slots['counted']} buildings incl. {slots['warehouses']} Warehouse(s){', over cap' if bundle['over_cap'] else ''}): {'; '.join(bundle['why'])}.")


# --- game readers (thin; each returns a safe default when unreadable) ---


def _call(name: str, read: "Callable[[], _T]", default: "_T") -> "_T":
    """read(), or default when it raises. A lambda, not a method name, so Pyright sees the call and its type."""
    try:
        return read()
    except Exception as error:
        swallowed("outpost_needs._call: " + name, error)
        return default


def read_outposts(roles_map):
    """Snapshot outpost entries over outpost_network; [] when unreadable."""
    network = get_component("outpost_network")
    if network is None:
        return []
    try:
        refs = list(network.outposts() or [])
    except Exception as error:
        swallowed("outpost_needs.read_outposts: outpost_network.outposts", error)
        return []
    out = []
    for ref in refs:
        try:
            types = {}
            for building in ref.buildings() or []:
                types[building.type_id] = types.get(building.type_id, 0) + 1
            out.append({"id": ref.id, "x": float(ref.x), "y": float(ref.y), "biome": ref.biome, "home": bool(ref.is_home), "roles": autoplay_roles.role_list(roles_map.get(ref.id)), "types": types, "used": int(ref.buildings_used), "capacity": int(ref.buildings_capacity)})
        except Exception as error:
            swallowed("outpost_needs.read_outposts: outpost read", error)
    return out


def _machines(type_id):
    """Components of every building of type_id over outpost_network."""
    network = get_component("outpost_network")
    out = []
    if network is None:
        return out
    try:
        for ref in network.outposts() or []:
            for building in ref.buildings(type_id) or []:
                component = get_component(building.id)
                if component is not None:
                    out.append(component)
    except Exception as error:
        swallowed("outpost_needs._machines: " + type_id, error)
    return out


def _recipes(type_id):
    """list_recipes() of the first machine of type_id (identical per machine, tech-gated); [] without one."""
    for machine in _machines(type_id)[:1]:
        return list(_call("list_recipes", lambda: machine.list_recipes(), []) or [])  # noqa: B023 (called within the iteration)
    return []


def read_stock_items(smelter_recipes, large):
    """
    Stock lists from in-game data: smelter_stock() (staged by the Large
    Warehouse, `large`) and feed_stock() (complete lists only).
    """
    out = smelter_stock(smelter_recipes, large)
    out.update(feed_stock(archive.get(FEED_KEY, {})))
    return out


def smelter_stock(recipes, large=True):
    """
    {"smelter": ores + outputs + byproducts, "factory": the outputs (every
    ingot a Fabricator may take)}. Two stages: before the Large Warehouse
    (large False) the recipes unlocked now, sized for small Warehouses (a
    later ore adds a Warehouse, and the Large swap frees slots again); from
    then on the end state, so the list counts only once it covers every ore
    in RAW_ORE_ITEM_IDS ({} before that: SMELTER_FALLBACK_SLOTS applies).
    """
    items = []
    outputs = []
    ores = set()
    for recipe in recipes:
        inputs = list((getattr(recipe, "inputs", None) or {}).keys())
        ores.update([item_id for item_id in inputs if item_id in RAW_ORE_ITEM_IDS])
        for item_id in inputs + [recipe.output_item, getattr(recipe, "byproduct_item", None)]:
            if item_id and item_id not in items:
                items.append(item_id)
        if recipe.output_item not in outputs:
            outputs.append(recipe.output_item)
    if not items or (large and not all(ore in ores for ore in RAW_ORE_ITEM_IDS)):
        return {}
    return {"smelter": items, "factory": sorted(outputs)}


def feed_stock(feed):
    """
    {"feed": inputs of the Feed Maker recipes (wildlife.feed)} once the
    recipes read there cover every species (wildlife_common.recipe_of());
    {} before that.
    """
    recipes = {}
    for entry in feed.values() if isinstance(feed, dict) else []:
        found = entry.get("recipes", {}) if isinstance(entry, dict) else {}
        if isinstance(found, dict):
            recipes.update(found)
    if not all(recipe_of(species) in recipes for species in SPECIES):
        return {}
    inputs = set()
    for needs in recipes.values():
        if isinstance(needs, dict):
            inputs.update(needs.keys())
    return {"feed": sorted(inputs)}


def read_kits(fabricator_recipes):
    """Kit ids the network can get: Shop catalogue, the Fabricator recipe outputs, Inventory stacks."""
    kits = set()
    shop = get_component("shop")
    if shop is not None:
        kits.update([item.id for item in _call("get_catalogue", lambda: shop.get_catalogue(), []) or []])
    kits.update([recipe.output_item for recipe in fabricator_recipes])
    inventory = get_component("inventory")
    if inventory is not None:
        kits.update([stack.id for stack in _call("stacks", lambda: inventory.stacks(), []) or []])
    return kits


def read_bio_orders(done=None):
    """{biome: open Bio Orders} from the first Bio Exchange (orders are shared by every Exchange); `done` collects {biome: complete orders}."""
    out = {}
    for exchange in _machines("bio_exchange")[:1]:
        for order in _call("orders", lambda: exchange.orders(), []) or []:  # noqa: B023 (called within the iteration)
            if getattr(order, "status", "") != "complete" and getattr(order, "percent", 0) < 100:
                out[order.biome] = out.get(order.biome, 0) + 1
            elif done is not None:
                done[order.biome] = done.get(order.biome, 0) + 1
    return out


def read_activity():
    """{group: busy share 0..1} of the machine_activity groups the factory rule reads; {} before the first sample."""
    import machine_activity  # imported here, not at module level: the lib import chain of the planner runs as one capped execution (dev_workflow §1d-1 "Import-time code")

    out = {}
    try:
        groups = (machine_activity.get() or {}).get("groups") or {}
    except Exception as error:
        swallowed("outpost_needs.read_activity", error)
        return out
    for name in ACTIVITY_GROUPS.values():
        entry = groups.get(name)
        if isinstance(entry, dict) and isinstance(entry.get("spare_mean"), (int, float)) and isinstance(entry.get("n"), (int, float)) and entry["n"] > 0:
            out[name] = max(0.0, min(1.0, 1.0 - float(entry["spare_mean"]) / float(entry["n"])))  # spare_mean = spare machines per sample
    return out


def read_essences_required():
    """Biomass phase minimum essences from the first Biomass Mixer; None without one."""
    for mixer in _machines("biomass_mixer")[:1]:
        value = _call("required_essences", lambda: mixer.required_essences(), 0)  # noqa: B023 (called within the iteration)
        return int(value) if isinstance(value, (int, float)) and value > 0 else None
    return None


def snapshot():
    """The need model's input, read in game (see the module header)."""
    roles_map = autoplay_roles.outpost_roles()
    outposts = read_outposts(roles_map)
    sites = surveyed_sites()
    role_presets = autoplay_roles.presets()
    taken = []
    for entry in outposts:
        for fluid in autoplay_roles.fluids_for(entry["roles"], role_presets)["in"]:
            if fluid not in taken:
                taken.append(fluid)
    fabricator_recipes = _recipes("fabricator")
    kits = read_kits(fabricator_recipes)
    large = "large_warehouse" in kits
    bio_done = {}
    bio_orders = read_bio_orders(bio_done)
    return {
        "outposts": outposts,
        "kits": kits,
        "activity": read_activity(),
        "phase": game_phase.snapshot(now_tick("outpost_needs.snapshot")),
        "bio_orders": bio_orders,
        "bio_done": bio_done,
        "stock": read_stock_items(_recipes("smelter"), large),
        "per_warehouse": WAREHOUSE_SLOTS["large_warehouse" if large else "warehouse"],
        "essences_required": read_essences_required(),
        "ore_wanted": sorted(smelter_outposts()[1]),
        "ore_sites": run_batched(mining_sites, sites, SITE_CHUNK),
        "fluid_sites": run_batched(fluid_sites, sites, SITE_CHUNK),
        "fluids_in": taken,
        "range_m": resource_assignment_range_m(),
    }
