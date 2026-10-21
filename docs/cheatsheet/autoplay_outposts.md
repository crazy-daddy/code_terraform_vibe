# Autoplay: outpost roles, extractors, needs, sites, proposals (§11f-§11j)

Part of [`AI_CHEATSHEET.md`](../AI_CHEATSHEET.md). Autoplay outpost roles, extractor pass and urgency tiers, outpost needs, site scoring and proposals. Rest of the autoplay planner: [`autoplay.md`](autoplay.md).

## §11f Outpost roles (`autoplay/lib/autoplay_roles.py`)

| Key | Shape | Writer |
| :--- | :--- | :--- |
| `autoplay.role_presets` | `{role: {"in": [fluid, ...], "out": [fluid, ...]}}` (a plain list = `"in"` only) | seeded with `DEFAULT_ROLE_PRESETS` when missing; default roles the stored dict lacks are added, operator edits of existing roles kept |
| `autoplay.outpost_roles` | `{outpost_id: role \| [role, ...]}` | operator, and an approved designate proposal (§11j); entries of gone outposts pruned each pass; retired roles dropped (below) |

Default presets (in → out): `factory` water, oil, steam · `terraform` water, steam · `power` steam, oil · `farm` water · `condenser` steam → water · `reactor` water · `drone_service` oil · `bio_caster` steam, water · `biomass_mixer` the five essences · `refinery` the four raw exotics → sulfur_gas, chlorine, cryofluid, quicksilver · `wildlife` ammonia, swamp_gas, sulfur_gas, chlorine, brine, cryofluid, quicksilver. `refinery` always takes all four raw exotics and makes all four refined ones: the Refiner controller picks its recipe from the network-wide tank fill, so it needs every pipe. One-fluid sub-role `wildlife_<fluid>` spreads Habitat fluids over outposts; `liquifier_<biome>` → `<biome>_essence` (an Essence Liquifier makes its outpost biome's essence); `storage_<fluid>` = that fluid in and out (tanks; the outpost becomes a producer terminal on that network). `fluids_for()` also returns `"supply"`: the `"out"` fluids of source roles; `condenser` (`BACKUP_ROLES`) and `storage_<fluid>` are no source (§11g). Waste Processors have no role (generic sink, wire locally). The home outpost always has `HOME_ROLES` (`farm`: the Harvester field is there) after its own roles. An outpost's fluid order (roles in order, each role's in before its out, duplicates dropped) is its port service order. Example: `{"home": ["wildlife_ammonia"], "outpost_3": ["factory", "refinery"]}`.

**Designation vs buildings.** `autoplay.outpost_roles` is the designation (intent) every autoplay pass goes by, also for roles whose buildings are not deployed or not unlocked yet. Machine scripts go by the buildings actually there. `bio_<biome>` presets: none, except `bio_volcanic` = the `bio_caster` fluids.

**Retired roles** (`retired(name, phase)`, `RETIRED_WITH`): a role whose chain is done for good, read from the retire modules' latches in the `game_phase` snapshot. `bio_<biome>` once `bio_retire` latched the biome (`bio_retired`; `bio_caster` = volcanic). `biomass_mixer`, `liquifier_*` once biomass is complete. `plants` once Plants is complete. `wildlife`, `wildlife_*`, `feed` once Wildlife is complete. Each full outpost planner pass drops them from `autoplay.outpost_roles` (`drop_retired_roles()`, logged under "Outpost roles"); an entry may end up `[]`, and its outpost then gets the undesignated fallback (§11j). `outpost_needs.snapshot()` leaves them out of every outpost's `roles` as well, `needs()` asks for none of them, and `undesignated_item()` adopts no retired role from buildings still standing. Kept, `role_gaps()` would make the building planner redeploy the sold machines. `refinery` stays: the Refiner has its own retire (§1l-2, §11l).

**Role catalog** (`ROLE_CATALOG`, code-side; fluids stay in the presets). Per role: `buildings` (groups; a group is a type_id or a list of alternatives), `biome` lock, `unique` (max-one-per-outpost machine), `items` (item logistics, needs a Drone Depot), `ore`, `biosites`.

| Role | Buildings | Flags |
| :--- | :--- | :--- |
| `factory` / `smelter` | fabricator / smelter | items |
| `mining` | warehouse or large_warehouse | items, ore |
| `storage` | warehouse or large_warehouse | items (exempt only: may go over the cap) |
| `drone_depot` | drone_station (any size) | |
| `drone_service`, `power`, `condenser`, `reactor`, `terraform`, `biomass_mixer`, `refinery` | their machine (power: turbine or oil generator; terraform: O2, pressure or heat) | |
| `charging` | charging_station (every outpost founded before drones carry the freight, §11h `with_charging()`; deployed by `build_providers.kit_wants()` at every outpost without one while the FLEET card's drone yield switch is off; once `charging_retire_ready()` holds (drone yield on, a hauler drone flies, Pioneer haulers down to `SALT_PIONEER_HAULERS`), `kit_wants()` retires the stations outside `charging_keepers()` (`station_keepers()` plus `miner_keepers()`: outposts with a Pioneer miner based there, ctx `miners`, that already hold a station; never a new station or role) and `building_plan.charging_pass()` moves the role to the keepers, see `TAKEOVER_HAULERS` in the autoplay.md constants) | |
| `wildlife[_<fluid>]` | habitat | items |
| `bio_<biome>` | bio_collector, bio_lab, bio_exchange + the biome's processor (`BIO_PROCESSORS`; frozen has none) | biome, unique, items, biosites |
| `weather_<biome>` | weather_station | biome, unique |
| `liquifier_<biome>` | essence_liquifier | biome, items, biosites |
| `storage_<fluid>` | liquid_tank, gas_tank or bulk_liquid_reservoir | |

Not in the catalog (`farm`, operator roles): fluids only, never observed or missing.

| Function | Answer |
| :--- | :--- |
| `observed(name, type_counts)` / `observed_roles()` | every group has a deployed alternative; `observed_roles()` leaves out `FAMILY_PREFIXES` sub-roles (a tank does not tell which fluid) |
| `role_gaps(designated, type_counts)` | `missing` = designated catalog roles not observed (building planner backlog); `extra` = observed, not designated, and not covered by a designated role's buildings |
| `unlocked(name, available_kits)` | every group has an alternative whose kit (`kit_id()`, `KIT_IDS` where it differs from the type_id) is available; non-catalog roles always |
| `biome_ok()` / `biome_locks()` | biome lock check; more than one lock in a designation = no outpost can host it |
| `bundle_slots(roles, warehouses=True)` | `(counted, penalized)`: one slot per distinct group; penalized = groups with a `PENALIZED_TYPES` machine (`storage.PENALIZED_TYPES`, shared with the machine scripts' storage outpost check); `warehouses=False` leaves the Warehouse group out |
| `stock_slots(roles, stock)` | Warehouse slots the roles stock: distinct items of their lists in `stock` (`{role: [item, ...]}`; shared items once), fallback slots for item roles without a list, `FACTORY_BUFFER_SLOTS` for `factory`; `storage` 0 (sized by what it holds) |
| `site_slots(roles, stock, have_slots, per_warehouse)` | `(counted, penalized, warehouses)`: machine groups + Warehouses for the stock beyond `have_slots`; home too (Inventory: 60 slots × 20 at most, no bulk store) |
| `warehouse_slots(type_counts)` | `(slots, buildings)` of the Warehouses standing at an outpost |

**Warehouse stock** (every outpost, home included; one 2000-unit slot per item). Lists come from in-game data (`outpost_needs.read_stock_items()`): `smelter` = ores, outputs and byproducts of the Smelter recipes and `factory` = those outputs (`smelter_stock()`), in two stages. Before the Large Warehouse kit is available: the recipes unlocked now, small Warehouses (a later ore adds one; the Large swap frees slots again). From then on: the end state, so the list counts only once the recipes cover every `RAW_ORE_ITEM_IDS` ore, else `SMELTER_FALLBACK_SLOTS`. Warehouse size `per_warehouse` = 5, 15 once the Large Warehouse kit is available; wildlife roles unlock after it (Plants 2,250,000 vs Biomass 30,000), so they are always sized with 15. `feed` = inputs of the Feed Maker recipes in `wildlife.feed`, once they hold every species' recipe (`feed_stock()`, `wildlife_common.recipe_of()` over `wildlife_data.SPECIES`); `mining` = the need's ores. Otherwise, and for every other role, the fallbacks below.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `WAREHOUSE_SLOTS` | warehouse 5, large_warehouse 15 | slots per building; Large once its kit is available |
| `FACTORY_BUFFER_SLOTS` | 10 | factory slots on top of its ingots (intermediates, finished goods) |
| `STOCK_FALLBACK_SLOTS` | smelter 14 (`SMELTER_FALLBACK_SLOTS`), factory 7, mining 1, feed 30 (`FEED_FALLBACK_SLOTS`), wildlife 16 (`WILDLIFE_FALLBACK_SLOTS`), bio_volcanic `BIO_STOCK_SLOTS` + `CASTER_STOCK_SLOTS` | a role without a complete list |
| `BIO_STOCK_SLOTS` | 9 | `bio.MAX_LOCAL_BIO_ARTIFACTS` 4 + 5 `outpost_reagents` reagents (a test checks both) |
| `CASTER_STOCK_SLOTS` | 7 | Bio Caster forge materials: the 16 recipes share 7 fabricated materials; added for `bio_volcanic` |
| `STOCK_PREFIX_SLOTS` | `bio_` `BIO_STOCK_SLOTS`, `liquifier_` 6 (`LIQUIFIER_STOCK_SLOTS`), `wildlife_` 1 | liquifier: one slot per life form of its biome |
| `HOME_RESERVED_ROLES` | farm, plants, feed, wildlife | home keeps its slots for these once wildlife is unlocked (§11h) |

Catalog roles for the home end state: `feed` (feed_maker, items), `plants` (plant_terraformer).

**Overcrowding** (simworker machine table): counted buildings over the outpost cap (`buildings_capacity`) cost 10% each (floor 20%), but only `PENALIZED_TYPES` (production machines, bio chain, generators, Supply Dock, charging station, drone service station, lightning rod) slow down. Warehouses, tanks, batteries, Drone Depots, Lead Cask and Weather Station count but are exempt. Field structures, sensors and vehicles do not count.

## §11g Extractor pass and urgency tiers (`autoplay/lib/extractor_plan.py`, `autoplay/lib/supply_tiers.py`)

**Urgency tiers** (`supply_tiers`, shared by the extractor, fluid and power passes). Consumers of fluid F = outposts whose roles take F (`"in"`) and do not make it. Outposts *supplying* F = those whose role is a source of F (`autoplay_roles.fluids_for()` `"supply"`): a `condenser` (`BACKUP_ROLES`, a backup for water pumps) and `storage_<fluid>` tanks are not, so neither stops a water well from being tapped.

| Tier | Untapped site of fluid F | Prio |
| :--- | :--- | :--- |
| `TIER_NOW` (0) | F has consumers and no supply (no built or planned extractor on an F site, no outpost supplying F): the nearest F site only | 0 |
| `TIER_SOON` (1) | F has consumers and the site is at most `NEAR_TILES` from one of them; also a drill for a Smelter ore without one | 0 |
| `TIER_AHEAD` (2) | F has consumers, site farther away | `PLAN_AHEAD_PRIO` |
| `TIER_SPARE` (3) | no outpost takes F (distance = to the nearest outpost) | `PLAN_AHEAD_PRIO` |

Order: tier, distance (footprint gap in tiles), output (`flow_rate()`, `base_steam_rate()`, `base_rate()`; 0 when the survey level hides it), site id. **Built producers** (`urgent_producers()`): those at most `NEAR_TILES` from a consumer of their fluid are urgent; with none near and no outpost supplying F, the nearest one is. Every other built producer is plan-ahead: the fluid and power passes connect it only in plan-ahead chunks.

**Plan-ahead pacing.** Plan-ahead jobs get `PLAN_AHEAD_PRIO` (Pioneers build them only when no normal job is open), one chunk at a time per pass, at most `pieces` per pipe route or power link, and only with the items in stock plus `reserve` (`supply_tiers.plan_ahead_limits()` → `(pieces, reserve)`: `PLAN_AHEAD_EARLY` before the mining-drill phase, `drone_upgrade.upgrade_phase_reached()`, else `PLAN_AHEAD_LATE`; the construction stock scales at the same point). So a plan-ahead blueprint never makes the Fabricator craft for it (the blueprint demand cascade finds its items in stock) and never takes the stock urgent work needs. Stock = `storage.takeable_stock()` at the Constructor's home (`production.construction_site_id()`), what a Pioneer can load there (`blueprint_queue.stock()`). The stock itself comes from the construction stock in `site_supply` ([production_logistics.md](pull_logistics.md) §2i-1): segments, gas/liquid bridges and one kit per untapped site, built in Fabricator idle time.

**Extractor pass** (`ExtractorPlanner.run_pass(topo, idle)`). Candidates = untapped fluid sites without an extractor ghost (`supply_tiers.fluid_candidates()`; structure kinds `water_pump`, `oil_pump`, `thermal_cap`, `exotic_gas_cap` on a gas deposit, `exotic_spring_tap` on a liquid one) plus drills. **Drills** need no pipes, and one drill per ore is enough: ores = every raw ore some outpost's Smelter has an unlocked recipe for (`production.smelter_ores()`). For each such ore with no drill on any of its sites (a site's `drill_id()`, or a drill ghost), the site nearest a Smelter outpost (then purest) is a `TIER_SOON` candidate. Drill kind = the lightest that cuts the hardness with its kit in stock, else the lightest that cuts it (`DRILL_KINDS`: `mining_drill` hardness ≤ 1, `mining_drill_industrial` ≤ 3, `mining_drill_heavy` ≤ 4; kit = `<kind>_kit`).

Per pass at most one extractor. Urgent ones go while fewer than `MAX_OPEN_URGENT` urgent extractor jobs of ours are open; an urgent job whose kit is not in stock is still queued (the blueprint demand makes the Fabricator build the kit). A plan-ahead one only when `idle` (power `joined`, fluid `done`), no extractor job of ours is open and its kit is in stock. Kit per kind: `construction_plan.EXTRACTOR_KITS` (pumps deploy from the `water_pump` / `oil_pump` item itself, caps, tap and drills from a `*_kit`); a plan-ahead job whose `required_item` turns out short is cancelled again. `plan_structure()` rejections: `locked` drops the kind for the run; site rejections (`target_claimed`, `occupied`, `clearance`, `too_hard`, ...) drop the site for the run; up to `MAX_TRIES_PER_PASS` sites per pass. Outcomes: `queued`, `waiting` (extractor jobs of ours open, or urgent ones at the cap), `done`, `error`. Pipes and power lines for a new extractor follow in the fluid and power passes once it is built.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `NEAR_TILES` (`supply_tiers`) | 25 | max footprint gap (tiles) from a consumer outpost for an urgent site or producer |
| `PLAN_AHEAD_PRIO` (`supply_tiers`) | 1 | `construction.priority` of plan-ahead jobs |
| `PLAN_AHEAD_EARLY` (`supply_tiers`) | (15, 5) | (pieces per plan-ahead pipe route or power link chunk, segments left in stock after it) before the mining-drill phase |
| `PLAN_AHEAD_LATE` (`supply_tiers`) | (30, 20) | same, from the mining-drill phase on |
| `MAX_OPEN_URGENT` | 2 | urgent extractor jobs of ours open at once |
| `MAX_TRIES_PER_PASS` | 5 | sites tried per pass when the game rejects one |
| `MATCH_TILES` | 1 | a drill or ghost this many tiles or fewer from a site stands on it |

## §11h Outpost needs (`autoplay/lib/outpost_needs.py`)

Need model of the outpost founding planner (`docs/plans/outpost_founding_planner.md`). Pure core over one snapshot (`snapshot()` reads it in game: outposts with designated roles, building type counts, used/capacity and biome; available kits; open Bio Orders per biome from the first Bio Exchange; `required_essences()` of the first Biomass Mixer; Smelter ores; surveyed mineral and fluid sites; fluids the designated roles take; `outpost_mining.resource_assignment_range_m()`).

A role is **covered** by an outpost that designates it or whose buildings make it up (`observed()`) in a biome the role allows. Family sub-roles without a biome lock (`storage_`, `wildlife_`) are covered only by designation.

| Urgency | Need |
| :--- | :--- |
| `now` | `bio_<biome>`: open Bio Orders of a biome no outpost has the chain for · `liquifier_<biome>`: Biomass phase minimum above the biomes making essence (deficit only; missing biomes with an outpost first, then `BIOMES` order) · `smelter` + `factory` off home (`off_home`): the first factory outpost once `research_outpost_hub` is unlocked and no outpost off home covers a factory role (`now` with the Fabricator unlocked, else by its ETA; `ores` = the Smelter ores, `EARLY_ORES` before any recipe is readable) |
| `soon` | `liquifier_<biome>`: the next missing biome (next phase) · `mining` (+ `ores`): wanted ores whose surveyed sites are all out of range of every outpost and none of them drilled (drones fetch from a drill anywhere; an ore with no surveyed site is survey work, no need) · `smelter`/`factory` (`factory_needs()`): every host of the role at or over `HOST_FULL_SHARE` of its cap **and** the role's machine group busy (`activity` share ≥ `BUSY_SHARE`; ≥ `BUSY_SHARE_EXTRA` once `MAX_FACTORY_HOSTS` factory outposts stand off home; an unknown share never asks) · `terraform`: no outpost keeps `TERRA_MIN_FREE` free slots while the atmosphere front is open · `storage`: a penalized outpost under `TERRA_MIN_FREE` free slots holds `STORAGE_TANKS_MIN` tanks or more and no outpost covers `storage` · `refinery`: a designated role takes a refined exotic whose raw deposit is surveyed, and nothing refines |
| by ETA (`lookahead()`, only once `research_outpost_hub` is unlocked) | second `smelter` + `factory` (`off_home`, `soon`): one factory outpost stands off home and fewer than `MAX_FACTORY_HOSTS` do, Fabricator unlocked (operator 2026-10-21: two factory outposts are the target; the proposal's cash verdict sets the timing; the need carries no biome, site scoring spreads them: `biome_new`, later `reach_gain`) · `power` (`site_fluid` steam): a thermal vent is surveyed, or only discovered (`snap["thermal_sites"]`, `discovered_thermal()`; then the need carries `survey_first`, the found proposal gets `survey` whatever its confidence, and its look-ahead fluid `steam` drops once the need is `now`/`soon`), and no outpost has one within `NEAR_TILES` (a discovered vent counts by its `extractor_box`), by the ETA of `research_thermal_cap` · `liquifier_frozen` (`off_home`): home holds a Mixer or Liquifier and biomass is not complete, by the ETA of `research_wildlife` · `reactor` (`site_fluid` water, exclusive): by the ETA of `research_nuclear_program`, only when `now`/`soon` and `game_phase.nuclear_ahead()` (Wildlife research unlocked: the program sits at the end of the TP ladder, the earlier TP rate would put it hours away). `urgency_for(eta, LEAD_TICKS["found"])`: `now` within the lead, `soon` within twice it, else `later`; no rate = `later`. These needs carry `blocked_by` (the research id; `focus_plan` scores it) and keep their urgency while the role's kit is still locked (`locked: True`) |
| `later` | end state: `weather_<biome>` and `liquifier_<biome>` in every biome, `bio_<biome>` where the biome has a processor (not frozen) · any other locked role (`unlocked()` False, `locked: True`) |

Earth orders for life forms are no need (drones catch them anywhere). Only `now`/`soon` needs (`PROPOSE_URGENCIES`) reach `plan_hosts()`, except for an undesignated outpost (below). A role in the snapshot's `refused_roles` (rejected `REFUSE_ROLE_TIMES` times within the hold, §11j) makes no need. An `off_home` need ignores home's cover.

**Look-ahead fluids** (`future_fluids(snap, needs)`, `plan_hosts()` `"future"`, feeds the §11i `future` term): `steam` while no outpost hosts `power` and no `power` need is `now`/`soon`; `water` once `game_phase.nuclear_ahead()` while no outpost hosts `reactor` and no `reactor` need is `now`/`soon`; `[]` before `research_outpost_hub`. `outpost_plan._rank()` re-ranks when they change (ranking signature, with the `drones` flag).

**Merge before founding** (`plan_hosts()`, `host_check()`): each need tries existing outposts by free slots (most first), then id. A host must allow the role's biome, not cover it yet, and keep its counted buildings within `buildings_capacity` when the combined bundle has a penalized machine (`site_slots()`, new Warehouses for the added stock included; exempt-only bundles may go over). Item roles add `drone_depot` when the host has none. Home counts Warehouses like any outpost. It hosts other roles only until wildlife is unlocked (`home_reserved()`: Habitat kit available, a Habitat at home, or a wildlife/feed role designated there); from then on only `HOME_RESERVED_ROLES` and `wildlife_<fluid>` (wildlife lives at home: Forage comes from the home field). Home refuses `off_home` needs, and a factory role once a factory outpost stands off home (until wildlife is complete; operator, run 2). An `exclusive` role (`reactor`) goes only onto a host without other penalized roles, and such a host takes no further penalized role except `EXCLUSIVE_SHARE_ROLES` (`terraform`: Mk IV generators beside the reactor). `mining` needs a site of each of its ores within range; a `site_fluid` need (`power`, `reactor`) a surveyed site of that fluid within `supply_tiers.NEAR_TILES`; `refinery` needs a raw exotic deposit within `NEAR_TILES` and never founds (`found: False`). A host that takes a need counts its new roles for the next need. Leftover needs form **founding bundles** (`found_bundles()`): one per biome lock, one for `mining` (ores joined), one per exclusive role, one for the other roles, each with `drone_depot` when an item role is in it and `charging` while Pioneers do the logistics (`with_charging()`, snapshot `drones` = `logistics_requests.drone_yield_enabled()`), `slots` (`site_slots()` on an empty outpost), `over_cap` (a penalized bundle above `FOUNDED_CAPACITY` = 20 buildings) and `blocked_by` (the research ids its needs wait for). The planner never releases a factory designation: moving one orphans the ores and ingots in its Warehouses. **Undesignated outposts** (`undesignated_item()`): a non-home outpost without an `autoplay.outpost_roles` entry that took no `now`/`soon` need (founded by hand, or off an approved found proposal) still gets a designate proposal: the first unlocked open need of any urgency it can host (roles another outpost took this pass skipped), else `mining` of the wanted ores in its reach, plus the roles its buildings make up; only those built roles when nothing fits (operator, run 2026-10-18).

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `LEAD_TICKS` | found 12 h, designate 6 h (sim) | ETA within which a look-ahead need is `now` (`soon` within twice it) |
| `HOST_FULL_SHARE` | 0.7 | used / capacity from which a factory host counts as full |
| `BUSY_SHARE` / `BUSY_SHARE_EXTRA` | 0.7 / 0.9 | group utilisation (`1 - spare_mean / n` of `machine_activity`) before full hosts ask for another; the higher bar past `MAX_FACTORY_HOSTS` |
| `MAX_FACTORY_HOSTS` | 2 | factory outposts off home before the higher busy bar applies |
| `TERRA_MIN_FREE` | 2 | free slots an outpost keeps for generators |
| `STORAGE_TANKS_MIN` | 4 | tanks at a crowded penalized outpost that ask for a storage outpost |
| `EARLY_ORES` | iron_ore, silicon | ores the first factory host wants before a Smelter recipe is readable |

## §11i Outpost site scoring (`autoplay/lib/outpost_sites.py`)

Where a founding bundle (§11h `found_bundles()`) should go. Decides from in-game data only: `nocturna.points_of_interest()`, `journal.discovered_sites()`, `nocturna.biome_at()`, `get_bounds()`, outposts and outpost ghosts (`read_world()`).

**Placement checks** (`check()`, mirrors `plan_structure("outpost")`): the anchor is the placement square's NW corner, world y grows north; square `PLACE_M` = 20 m (x .. x+20, y-20 .. y), centre (x+10, y-10). Clearance is measured from a point to the `CLEAR_SIDE_M` = 26 m square around the centre: other outposts' centres and outpost ghosts `OUTPOST_CLEARANCE_M` = 40 m, every POI (unknown, scanned, biomass) `POI_CLEARANCE_M` = 20 m. The outpost's biome is the biome at the anchor. A bundle that keeps a pipe buffer (`wants()["clear"]`: a `storage` role) also needs its footprint and the `STORAGE_BUFFER_TILES` around it (`grid_geom.outpost_box()`/`buffer_box()`) free of pipes and pipe jobs (`pipe_near()`; tiles bucketed in `PIPE_BLOCK_TILES` = 4 blocks by `pipe_blocks()`). `outpost_plan` reads those tiles with an `infra_topology.Topology` read only when such a bundle is ranked (`pipe_tiles()`), and rechecks its proposals the same way. Rejections: `out_of_bounds`, `outpost_clearance`, `poi_clearance`, `biome <id>`, `pipe_buffer`.

**Knowledge levels**: 1 = POI of kind `unknown`; 2 = kind known (discovered site, a scanned POI kind such as `biomass`, or an unknown POI whose `poi_X_Y` entry in `survey.unsupported_targets` has reason `wrong_scanner`: vehicle sonar cannot classify biomass, `survey_requests.known_biomass()`), details `None`; 3 = surveyed site (ore, purity, hardness, exotic fluid). A water/oil/thermal contact's fluid is known from its kind. Level 1–2 contacts count by expected value; the prior (`priors()`) comes from this save's own scans: kind shares over every contact of known kind, ore and exotic shares over surveyed sites, mean purity factor; flat when nothing is known.

**Score terms** (higher better; `WEIGHTS`):

| Term | Weight | Value |
| :--- | :--- | :--- |
| `ore` | 10 | per bundle ore (the need's ores): surveyed sites within `range_m` (outpost mining range) by purity factor, `HARD_FACTOR` when no available drill kit cuts the hardness, capped at `ORE_CAP` per ore; less-known contacts add P(mineral) × P(ore) × mean purity on top, up to `ORE_CAP` × ores |
| `fluid` | 6 | per wanted field fluid (the bundle roles' `"in"` fluids with a field site: water, oil, steam, raw exotics, not made by the bundle itself): best contact whose extractor footprint is at most `NEAR_TILES` tiles (Manhattan gap between footprints = pipe pieces, same measure as `supply_tiers`) from the outpost footprint, closeness `1 − gap / NEAR_TILES`; unknown contacts by chance, up to 1 per fluid |
| `exotic` | 1 | `EXOTIC_VALUE` per raw exotic deposit in fluid reach the bundle does not want (a later `refinery` role), capped at 1 |
| `biosite` | 2 | biomass contacts within `BIOSITE_RANGE_M` in the bundle's biome (bio-scanned = known, unknown POIs by P(biomass)), share of `BIOSITE_CAP`; only bundles with a `biosites` role |
| `margin` | 4 | biome-locked bundles: share of the `MARGIN_PROBES_M` rings (8 directions) around the anchor holding only its biome |
| `room` | 2 | share of 8 probe points at `ROOM_M` on the map and clear of other outposts |
| `home` | −2 (early −4) | per km from the home centre |
| `near` | −3 | home centre closer than `HOME_NEAR_M` (300 m): share of the shortfall (the base spreads outward); with `home` the best home distance is `HOME_NEAR_M` |
| `grid` | −6 | per km of Manhattan distance to the nearest outpost or ghost (links run on tiles: a diagonal gap costs its full L of power line and pipe) |
| `travel` | −2 (early −3) | per km to the nearest reach point (`reach_points()`: home or a Charging Station host; constructors drive there on battery) |
| `crowd` | −3 | free tiles between this footprint and the nearest outpost's or ghost's (Chebyshev) under `SPACING_TILES`: share of the shortfall (each fluid needs its own pipe in, a free tile between pipes for bridges, room at the outposts); with `grid` the best gap is `SPACING_TILES` |
| `biome_new` | 1 (early 3) | the anchor's biome holds no outpost yet (`settled`: the outposts' biomes) |
| `reach_gain` | 3 (early 9; 0 while drones haul) | share of out-of-reach contacts (any kind, not stuck) the candidate's Charging Station would bring within `CONSTRUCTOR_REACH_M`. `ctx["remote"]` = `(x, y, n)` clusters per `CELL_M` cell of contacts farther than `CONSTRUCTOR_REACH_M` from every `starts` point, `ctx["remote_n"]` their count; 0 without starts or remote contacts. Outside `RESOURCE_TERMS` (no `confidence` effect). Costs `REACH_UNITS` per cluster in `score_step()`; a finish too big for the slice runs in a slice of its own |
| `future` | 3 | closeness (1 − d/`FUTURE_RANGE_M`) to the best contact of each look-ahead fluid: known fluid 1, unknown by biome prior, else a geothermal scout area at 0.5. Mean over `want["future"]` (§11h `future_fluids()`, via `plan["future"]` and `wants(..., future)`) of the best spot value × closeness, d from the candidate centre, clamped at 0; 0 without look-ahead fluids. Spots (`prepare_want()` `future_spots`, `future_rows()` in `VALUE_CHUNK` slices, non-stuck contacts only): a contact known to yield the fluid (any level) 1; an unknown one (level 1) its inferred `kinds` weight of the fluid's kind, else the save's kind prior renormalised over the kinds that can spawn in its biome (`biome_share()`, `contact_inference.BIOME_KINDS`; 0 when the biome rules the kind out); the `FUTURE_TOP` best per fluid, ties nearest home. No steam spot: the geothermal scout areas (`read_world(geothermal=)`, `outpost_plan` `geo_areas`, ≤ `GEOTHERMAL_SCOUTS` nearest home) at `FUTURE_CELL_VALUE`. Only those scout areas count, not every probed geothermal cell. Outside `RESOURCE_TERMS`. Costs `REACH_UNITS` per spot in `score_step()`, charged with the finish |

**Phase** (`phase_inputs(outposts, early, drones)`, early = no mining drill yet, `game_phase.drills()`; `drones` = `snap["drones"]` zeroes `reach_gain`): `WEIGHTS_EARLY` and a **reach gate**: `check()` rejects an anchor (`out_of_reach`) whose centre is farther than `CONSTRUCTOR_REACH_M` from every reach point (home and every outpost with a Charging Station, `reach_points()`); late: `WEIGHTS`, no gate. The ore term weighs each wanted ore by its **demand share** (`demand_factors()`: shares normalised to mean 1 over the wanted ores, an ore without a share gets the smallest listed one; no data = 1 each). `outpost_plan.read_demand()` reads the shares from `production_demand.get_smelter_demands()` (outputs mapped to ores) and falls back to `DEMAND_FALLBACK`.

`confidence` = share of the resource terms (ore, fluid, exotic, biosite) from known contacts; below `MIN_CONFIDENCE` a row carries `survey: True` (survey trip first). A **stuck** contact adds no guess to score or confidence: an unsurveyed contact whose `poi_X_Y` or `site_<id>` entry in `survey.unsupported_targets` still blocks (`survey_requests.blocked_targets()`: every reason but `wrong_scanner`; a `research_required` entry only while no scan research from `vehicle_claims.SCAN_RESEARCH_IDS` was unlocked after it was recorded). So an area with only contacts the scouts cannot resolve stops asking for a survey; a new scan research makes its `research_required` contacts count as guesses again and the area asks again. `too_hard`/`tier_too_low` entries stay stuck until a scout with a better sonar retries them (`can_attempt_target()`) and clears or rewrites the entry. A bundle with ores keeps only anchors with ore in reach.

**Search** (`rank_sites()`): `CANDIDATE_STEP_M` grid over the map, `check()`ed and scored without margin and room; the best `REFINE_TOP` are re-searched on a `REFINE_STEP_M` grid within `REFINE_RADIUS_M`, the best of those get margin and room (`add_detail()`). Contact values per bundle are computed once (`prepare_want()`, `value_rows()`: one value per term per contact) and bucketed in `CELL_M` cells. Scoring runs in `score_step()` chunks (`run_chunked`) of `STEP_UNITS` work units, resumable mid-anchor and mid-cell, so contact density never overruns a slice. Biome reads are cached per tile for the run.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `CANDIDATE_STEP_M` | 80 | coarse candidate grid |
| `REFINE_STEP_M` / `REFINE_RADIUS_M` / `REFINE_TOP` | 20 / 40 / 5 | refine grid, window half-width, coarse candidates refined |
| `CELL_M` | 150 | contact bucket size |
| `BIOSITE_RANGE_M` | 300 | biomass contacts a bio / liquifier outpost counts |
| `ORE_CAP` / `BIOSITE_CAP` | 2 / 6 | saturation per ore / of biosites |
| `PURITY_FACTOR` | standard 1, rich 1.5, pure 2 | surveyed ore value |
| `HARD_FACTOR` | 0.2 | ore site no available drill cuts (`hardness_limit()` over `extractor_plan.DRILL_KINDS` kits) |
| `EXOTIC_VALUE` | 0.25 | per unwanted raw exotic deposit |
| `MARGIN_PROBES_M` | 20, 40, 80, 160 | biome margin rings |
| `ROOM_M` | 100 | room probe distance |
| `SPACING_TILES` | 4 | free tiles between outpost footprints below which the `crowd` term costs (operator: 3–5 do) |
| `MIN_CONFIDENCE` | 0.5 | below: survey first |
| `CONSTRUCTOR_REACH_M` | 600 | early reach gate: distance from home or a Charging Station host |
| `REMOTE_TOP` | 40 | remote contact clusters (largest `n` first) kept in `ctx["remote"]` for `reach_gain`; bounds the per-anchor finish cost. `remote_n` stays the full count, so the term is a share of the full total |
| `FUTURE_RANGE_M` | 500 | `future` term: closeness falls to 0 at this distance from a spot |
| `FUTURE_TOP` | 8 | best spots kept per look-ahead fluid |
| `FUTURE_CELL_VALUE` | 0.5 | value of a geothermal scout area when no steam contact is known |
| `DEMAND_FALLBACK` | iron_ore 0.6, silicon 0.3 | ore demand shares before a Smelter demand is readable (run 2: 20k iron, 12k silicon mined) |
| `FILTER_CHUNK` | 4 | anchors per atomic `check()` slice |
| `VALUE_CHUNK` | 15 | contacts per atomic `value_rows()` slice |
| `DETAIL_CHUNK` | 1 | rows per atomic `add_detail()` slice |
| `STEP_UNITS` | 50 | work units (~45 operations) per `score_step()`: row 4, cell 1, anchor start 4, finish 22 (~1,000 operations with 9 outposts) plus `REACH_UNITS` = 1 per remote cluster and future spot |

Slice costs are measured in `tests/test_autoplay_outpost_sites.py` against `ATOMIC_STEP_BUDGET` on a map several times denser in contacts than a real one.

## §11j Outpost proposals (`autoplay/lib/outpost_plan.py`)

The founding pass, first in the run loop: `outpost_needs` needs and hosts (§11h) and `outpost_sites` sites (§11i) become at most `MAX_PROPOSALS` = 5 proposals, each a map marker the operator answers. Nothing is bought or queued: an approved `found` proposal stays `approved`.

| Key | Shape | Writer |
| :--- | :--- | :--- |
| `autoplay.outpost_proposals` | `{proposal_id: {"id", "kind": "found" \| "designate", "outpost", "x", "y", "biome", "lock", "roles", "needs", "ores", "urgency", "why": [...], "score", "confidence", "survey", "over_cap", "price", "status": "proposed" \| "approved" \| "built" \| "rejected", "ok", "moved", "blocked", "placed", "tick"}}` | founding pass, rewritten only on change |
| `autoplay.survey_requests` | `{proposal_id \| "geo-<n>": {"x", "y", "radius", "why"}}` | founding pass (`survey_areas()`, `geo_requests()`), rewritten only on change; read by the ground scout (`vehicle_survey.survey_known_pois()`) and the drone scout (`drone_scout.scan_candidates()`) |

**Survey requests** (`lib/survey_requests.py`): every open found proposal with `survey` (confidence under `MIN_CONFIDENCE`) asks for its area: centre of its placement square, radius = its bundle's widest scoring range (`prepare_want()` `radius`; `BIOSITE_RANGE_M` before the want is prepared). Both scouts put candidates inside any request area first (`requested_first()`), keeping their own nearest-first order within each part, and log the count in their candidate debug line. A request goes when its proposal stops wanting a survey (re-rank after the scans raise confidence), is built, rejected or dropped. Contacts the scouts cannot resolve stay skipped by them and count as stuck in scoring (§11i), so such an area raises confidence and its request goes.

**Geothermal scouting** (`geo-<n>` requests): while Outpost Hub is unlocked, Thermal Cap is not and no thermal contact is known (`thermal_known()`: a discovered site or POI of kind `thermal`), a full pass probes the `CANDIDATE_STEP_M` grid for geothermal tiles once per planner (`_probe_geothermal()`, `GEO_PROBE_CHUNK` biome reads per atomic slice) and asks for `GEOTHERMAL_SCOUTS` areas of radius `GEOTHERMAL_SCOUT_RADIUS_M`: the geothermal cell nearest home first, each next one beyond twice the radius of every earlier pick (`geothermal_areas()`; the base spirals outward). Thermal vents lie only in the geothermal biome (`contact_inference.BIOME_KINDS`). The requests go on the next full pass after a thermal contact is known (`thermal_seen`, latched per planner) or Thermal Cap is unlocked; an unreadable planet leaves the probe for the next full pass.

Proposal ids: `d-<outpost>` (designate, on the outpost's anchor, price 0) and `f-<biome lock | mining | x-<role> | general>` (one per founding bundle, at its best ranked site; price = the Shop catalogue `cost` of `outpost_kit`, which already counts every kit owned; `cash` = `ok` when the price leaves `cash.MIN_FLOOR` of the balance, else `wait`, shown in the note; `blocked_by` = the bundle's research ids). Order: operator OK first, then urgency, designate before found, score. A rejected entry stays under `<id>~<tick>` for `REJECT_HOLD_TICKS` (newest `MAX_REJECTED` = 10): a rejected designation's (role, outpost) pairs go to the need snapshot as `"refused"` (`host_check()` skips them, so the need tries the next host or a founding); a rejected site holds anchors within `REJECT_RADIUS_M` for the same bundle; a role rejected `REFUSE_ROLE_TIMES` times among the held entries (any host or site) goes to the snapshot as `refused_roles` and makes no need at all until the hold ends.

**Markers** (id `autoplay.outpost.<proposal_id>`, drawn at the **centre** of the placement square (`outpost_centre()`), label `Outpost Suggestion`, icon `flag` found / `star` designate, color `accent` / `violet`, `warning` when blocked, `success` when approved; note = roles, urgency and reasons, price, score and confidence, then what blocks it or how to approve, at most 240 characters):
- **Approve:** add the word `OK` to the label (any case). Approval needs no blocker: placement failure (`check()`), pending re-check, `survey` (confidence under `MIN_CONFIDENCE`), `over_cap`. The OK label is re-read each pass, so a blocker cleared later approves then. An approved designate writes its roles into `autoplay.outpost_roles` at once (status `built`, marker removed).
- **Move:** a found marker dragged more than `MOVE_EPS_M` gives the new anchor (`anchor_of_marker()`: the marker position is the centre, the anchor its NW corner), kept from then on; it is re-checked and re-scored (`recheck()`), a failure goes into the note. A dragged designate marker is put back.
- **Reject:** delete the marker (only markers the planner placed count; a failed `markers.list()` skips the pass).
- The planner places a marker only when its fields differ from what it reads back, keeps an operator label holding OK, and removes markers of proposals no longer open.

Full pass (needs, hosts, merge) every pass while the other passes work, else every `REPLAN_TICKS`; sites are re-ranked only when the founding bundles change or after `RERANK_TICKS`. Every open found proposal gets `check()` on a full pass, a dragged one also in watch mode. Outcomes: `locked` (no Map Markers), `idle`, `waiting`, `changed`.

| Constant | Value | Meaning |
| :--- | :--- | :--- |
| `MAX_PROPOSALS` / `MAX_REJECTED` | 5 / 10 | open proposals / rejected entries on hold |
| `REFUSE_ROLE_TIMES` | 2 | rejections of one role within the hold that silence the role everywhere |
| `REJECT_HOLD_TICKS` | 864,000 (24 sim h) | hold of a rejected proposal |
| `REJECT_RADIUS_M` | 100 | anchors a rejected site holds |
| `REPLAN_TICKS` / `RERANK_TICKS` | 6,000 / 36,000 | full pass in watch mode / site re-rank with unchanged bundles |
| `MOVE_EPS_M` | 0.5 | marker offset that counts as a drag |
| `GEOTHERMAL_SCOUTS` / `GEOTHERMAL_SCOUT_RADIUS_M` | 2 / 300 | geothermal scout requests and their radius |
| `GEO_PROBE_CHUNK` | 4 | `biome_at` reads per atomic slice of the geothermal probe |
