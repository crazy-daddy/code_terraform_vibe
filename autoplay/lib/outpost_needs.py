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
#    "range_m": mining range of an outpost (outpost_mining)}
#
# A need is {"role", "biome", "urgency", "why", "found", "locked"} (+ "ores"
# for mining). Urgency:
#   now   live demand nothing covers: open Bio Orders of a biome without its
#         bio_<biome> chain; Biomass phase minimum above the biomes making
#         essence (the deficit, missing biomes with an outpost first).
#   soon  the next Biomass phase's essence; a wanted ore whose surveyed sites
#         are all out of every outpost's mining range; every Smelter /
#         Fabricator host full; a refined exotic a designated role takes,
#         with no refinery_<fluid> anywhere.
#   later end-state checklist: weather_<biome> and liquifier_<biome> in every
#         biome, bio_<biome> where the biome has a processor. A locked role
#         (autoplay_roles.unlocked() False) is always "later".
# Only now/soon needs make a proposal. A role is covered by an outpost that
# designates it, or whose buildings make it up (observed; family sub-roles
# only when biome-locked, since a tank or Refiner does not tell its fluid).
# Earth orders for life forms are no need: drones catch them anywhere.
#
# plan_hosts() merges needs onto existing outposts first (biome lock, slots
# under the cap when the bundle has a penalized machine, a Drone Depot added
# for item roles, the role's site within reach); home takes no penalized
# role (its slots are reserved). Leftover found needs group into founding
# bundles: one per biome lock, one for mining, one for the rest.
# refinery_<fluid> never founds (found False): it goes onto an outpost with
# a raw deposit of its fluid within supply_tiers.NEAR_TILES.

from swallow import swallowed
from grid_geom import outpost_box
from supply_tiers import NEAR_TILES, gap, fluid_sites
from extractor_plan import mining_sites, smelter_outposts
from infra_topology import surveyed_sites
from outpost_mining import resource_assignment_range_m
import autoplay_roles
from autoplay_roles import BIOMES, BIO_PROCESSORS, role_flag, biome_ok, unlocked, bundle_slots, observed, observed_roles

URGENCIES = ("now", "soon", "later")
PROPOSE_URGENCIES = ("now", "soon")
FACTORY_ROLES = ("smelter", "factory")   # hosts full everywhere -> another host "soon"
EXTRA_HOST_ROLES = FACTORY_ROLES + ("mining",)   # a need for one more host, not for a first one
REFINED_EXOTICS = ("sulfur_gas", "chlorine", "cryofluid", "quicksilver")


def _rank(urgency):
    return URGENCIES.index(urgency) if urgency in URGENCIES else len(URGENCIES)


def _need(role, urgency, why, **extra):
    need = {"role": role, "biome": role_flag(role, "biome"), "urgency": urgency, "why": why,
            "found": not role.startswith("refinery_"), "locked": False}
    need.update(extra)
    return need


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


def _dist(ax, ay, bx, by):
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def unreached_ores(wanted, ore_sites, outposts, range_m):
    """Wanted ores with surveyed sites, none of them within range_m of an outpost; sorted."""
    out = []
    for ore in sorted(set(wanted)):
        sites = [row for row in ore_sites if row["item"] == ore]
        if sites and not any(_dist(row["x"], row["y"], entry["x"], entry["y"]) <= range_m
                             for row in sites for entry in outposts):
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
    settled = set([entry.get("biome") for entry in outposts])
    missing = sorted([biome for biome in BIOMES if biome not in makers],
                     key=lambda biome: (biome not in settled, BIOMES.index(biome)))
    deficit = max(0, required - len(makers))
    needs = []
    for index, biome in enumerate(missing):
        if index < deficit:
            needs.append(_need("liquifier_" + biome, "now",
                               f"biomass phase needs {required} essences, {len(makers)} made"))
        elif index == deficit and required < len(BIOMES):
            needs.append(_need("liquifier_" + biome, "soon", f"next biomass phase needs {required + 1} essences"))
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
    for role in FACTORY_ROLES:
        found = hosts(role, outposts)
        if found and all(entry["used"] >= entry["capacity"] for entry in found):
            needs.append(_need(role, "soon", f"every {role} outpost is full"))
    taken = set(snap.get("fluids_in", []))
    raws = set([row["fluid"] for row in snap.get("fluid_sites", [])])
    for fluid in REFINED_EXOTICS:
        role = "refinery_" + fluid
        if fluid in taken and "raw_" + fluid in raws and not hosts(role, outposts) and not hosts("refinery", outposts):
            needs.append(_need(role, "soon", f"{fluid} is taken, nothing refines it"))
    return needs


def needs(snap):
    """
    Every open need, most urgent first (then role name): now_signals() and
    later_checklist() merged per role (most urgent kept, mining ores joined),
    covered roles dropped, locked roles moved to "later".
    """
    outposts = snap["outposts"]
    kits = snap.get("kits", set())
    merged = {}
    for need in now_signals(snap) + later_checklist():
        role = need["role"]
        if role not in EXTRA_HOST_ROLES and hosts(role, outposts):
            continue
        old = merged.get(role)
        if old is None or _rank(need["urgency"]) < _rank(old["urgency"]):
            merged[role] = need
    out = []
    for role, need in merged.items():
        if not unlocked(role, kits):
            need = dict(need)
            need["locked"] = True
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
    if any(role_flag(name, "items") for name in roles) and "drone_depot" not in roles \
            and (entry is None or not covers(entry, "drone_depot")):
        return roles + ["drone_depot"]
    return roles


def _site_ok(need, entry, snap):
    role = need["role"]
    if role.startswith("refinery_"):
        raw = "raw_" + role[len("refinery_"):]
        box = outpost_box(entry["x"], entry["y"])
        return gap(box, [row["box"] for row in snap.get("fluid_sites", []) if row["fluid"] == raw]) <= NEAR_TILES
    if need.get("ores"):
        range_m = snap.get("range_m", 0)
        return all(any(_dist(row["x"], row["y"], entry["x"], entry["y"]) <= range_m
                       for row in snap.get("ore_sites", []) if row["item"] == ore) for ore in need["ores"])
    return True


def host_check(need, entry, snap):
    """(roles to add, None) when `entry` can take the need, else (None, reason)."""
    role = need["role"]
    if covers(entry, role):
        return (None, "has it")
    if not biome_ok(role, entry.get("biome")):
        return (None, "biome " + str(entry.get("biome")))
    current = _current_roles(entry)
    added = _with_depot([role], entry)
    after, penalized = bundle_slots(current + added)
    if entry.get("home") and bundle_slots(added)[1] > 0:
        return (None, "home slots reserved")
    extra = after - bundle_slots(current)[0]
    used = max(entry.get("used", 0), bundle_slots(current)[0])
    if penalized and used + extra > entry.get("capacity", 0):
        return (None, f"over cap ({used}+{extra}/{entry.get('capacity', 0)})")
    if not _site_ok(need, entry, snap):
        return (None, "site out of reach")
    return (added, None)


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
            added, reason = host_check(need, entry, snap)
            if added is None:
                rejected.append((need["role"], entry["id"], reason))
                continue
            entry["roles"].extend([name for name in added if name not in entry["roles"]])
            entry["used"] = entry.get("used", 0) + bundle_slots(added)[0]
            item = designate.setdefault(entry["id"], {"outpost": entry["id"], "roles": [], "needs": [],
                                                      "urgency": need["urgency"], "why": []})
            item["roles"].extend([name for name in added if name not in item["roles"]])
            item["needs"].append(need["role"])
            item["why"].append(need["why"])
            if _rank(need["urgency"]) < _rank(item["urgency"]):
                item["urgency"] = need["urgency"]
            taken = True
            break
        if not taken and need["found"]:
            leftovers.append(need)
    return {"designate": [designate[key] for key in sorted(designate)], "found": found_bundles(leftovers),
            "rejected": rejected}


def found_bundles(leftovers):
    """Founding bundles of leftover needs: one per biome lock, one for mining, one for the other roles."""
    groups = {}
    for need in leftovers:
        key = need["biome"] or ("mining" if need["role"] == "mining" else "")
        groups.setdefault(key, []).append(need)
    bundles = []
    for key in sorted(groups):
        members = groups[key]
        roles = _with_depot([need["role"] for need in members])
        ores = sorted(set([ore for need in members for ore in need.get("ores", [])]))
        bundles.append({"biome": members[0]["biome"], "roles": roles, "needs": [need["role"] for need in members],
                        "urgency": URGENCIES[min([_rank(need["urgency"]) for need in members])],
                        "why": [need["why"] for need in members], "ores": ores})
    return sorted(bundles, key=lambda bundle: (_rank(bundle["urgency"]), bundle["roles"]))


def log_plan(log, open_needs, plan):
    """Debug trail of one need pass (AGENTS.md rule 7): needs, rejected hosts, proposals."""
    for need in open_needs:
        log.debug(f"Need {need['role']} ({need['urgency']}{', locked' if need['locked'] else ''}): {need['why']}.")
    for role, outpost_id, reason in plan["rejected"]:
        log.trace(f"Need {role}: {outpost_id} rejected ({reason}).")
    for item in plan["designate"]:
        log.debug(f"Designate {item['outpost']} +{item['roles']} ({item['urgency']}): {'; '.join(item['why'])}.")
    for bundle in plan["found"]:
        log.debug(f"Found {bundle['biome'] or 'any biome'} {bundle['roles']} ({bundle['urgency']}): {'; '.join(bundle['why'])}.")


# --- game readers (thin; each returns a safe default when unreadable) ---

def _call(obj, name, default):
    try:
        return getattr(obj, name)()
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
            out.append({"id": ref.id, "x": float(ref.x), "y": float(ref.y), "biome": ref.biome,
                        "home": bool(ref.is_home), "roles": autoplay_roles.role_list(roles_map.get(ref.id)),
                        "types": types, "used": int(ref.buildings_used), "capacity": int(ref.buildings_capacity)})
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


def read_kits():
    """Kit ids the network can get: Shop catalogue, a Fabricator's recipe outputs, Inventory stacks."""
    kits = set()
    shop = get_component("shop")
    if shop is not None:
        kits.update([item.id for item in _call(shop, "get_catalogue", []) or []])
    for fabricator in _machines("fabricator")[:1]:
        kits.update([recipe.output_item for recipe in _call(fabricator, "list_recipes", []) or []])
    inventory = get_component("inventory")
    if inventory is not None:
        kits.update([stack.item_id for stack in _call(inventory, "stacks", []) or []])
    return kits


def read_bio_orders():
    """{biome: open Bio Orders} from the first Bio Exchange (orders are shared by every Exchange)."""
    out = {}
    for exchange in _machines("bio_exchange")[:1]:
        for order in _call(exchange, "orders", []) or []:
            if getattr(order, "status", "") != "complete" and getattr(order, "percent", 0) < 100:
                out[order.biome] = out.get(order.biome, 0) + 1
    return out


def read_essences_required():
    """Biomass phase minimum essences from the first Biomass Mixer; None without one."""
    for mixer in _machines("biomass_mixer")[:1]:
        value = _call(mixer, "required_essences", 0)
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
    return {"outposts": outposts, "kits": read_kits(), "bio_orders": read_bio_orders(),
            "essences_required": read_essences_required(), "ore_wanted": sorted(smelter_outposts()[1]),
            "ore_sites": mining_sites(sites), "fluid_sites": fluid_sites(sites), "fluids_in": taken,
            "range_m": resource_assignment_range_m()}
