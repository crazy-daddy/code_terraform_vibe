# Unify duplicated handlers (requests, fluids, item I/O, clone pairs)

## Context
After the bio_* load merge (`ee0fe49`, `b9f01d5`) the user wants other "similar method" families found and migrated to generalized handlers, especially relics from early development. Survey method: AST inventory + normalized-AST near-duplicate scan over `scripts/**` (1194 pairs >= 0.85 similarity; script inlined under Verification), then manual reading of the clusters. Tiers `0_cold_boot`/`1_early` cannot import `lib/` (unlock at tier 2), so their clones (pioneer_scout vs rover, bio_collector vs bio_lab) stay.

Each cluster below = one commit (caveman-commit), sync hold (`devtools/.sync-backups/hold`) around multi-file edits, cheatsheet module map/§ updated in the same change.

## Cluster R — logistics request publishing (7 hand-rolled publishers)
Every requester already calls `logistics_requests.set_requests()/clear_requests()`, but each re-implements throttle + set-or-clear + foreign-owner skip + "short" debug line with its own module state:
- `lib/outpost_reagents.py:99` publish_reagent_requests (`_last_publish_tick` dict)
- `6_seeds/lib/seed_maker.py:307`, `6_seeds/lib/seed_supply.py:137` (`_last_request_tick`)
- `8_planting/lib/plant_terraformer_demand.py:124` (`_published_targets/_tick`, foreign-owner skip)
- `9_wildlife/lib/wildlife_planner.py:671` (`state["requests"]`, foreign-owner skip)
- `lib/pump_salt.py:160` (`_published`)
- `lib/bio_volcanic.py` `_publish_material_demand` (interval throttle)
- `5_steampower/lib/site_supply.py:476` `_publish` + `_unchanged` — the best version: stateless, compares wants with the archive entries already published.

Plan: move `_unchanged`/`_publish` from site_supply into `lib/logistics_requests.py` as
`publish_requests(outpost_id, requester, wants, tick, requests=None, buyable=False, skip_foreign=True) -> bool` (writes only when wants differ from the published entries or `REPUBLISH_TICKS` elapsed; empty wants clears; `skip_foreign` drops items another requester owns there, logged once via debug). Callers keep computing `wants`, drop their own throttle state (keep outer compute throttles where computing wants is expensive, e.g. seed_maker `_open_combo_counts`). Normalize inconsistencies found: seed_maker never clears on empty wants; seed_supply clears all outposts (`clear_requests(REQUESTER_ID)` without outpost). site_supply imports it back. Note: logistics_requests is tier 4, site_supply tier 5 → move `REPUBLISH_TICKS` constant to logistics_requests.

Fabricator orders (`production.set_upgrade_order/set_backlog_order`) are already one generalized handler — no change.

## Cluster F — fluid input wrappers around FluidInputRouter/FluidOutputRouter
Routers are adopted everywhere, but the glue around them is cloned:
1. **Viable-source discovery** (outposts × `FLUID_SOURCE_TYPE_IDS[key]` × `fluid_building_is_viable` → `rank_own_outpost_first`), ~12 copies: `fabricator.py:224`, `bio_volcanic.py:339`, `10_nuclear/lib/reactor.py:274`, `8_planting/lib/field_provider.py:135`, `8_planting/lib/plant_terraformer_water.py:42`, tiered variants in `terraforming.py:118/135`, `steam_turbine.py:116`, `oil_generator.py:155`, `steam_condenser.py:131`, `habitat.py:291`, `refiner.py:290`, `biomass_mixer.py:115`.
   Add to `lib/production_fluids.py` (owns FLUID_SOURCE_TYPE_IDS + viability): `viable_fluid_source_pairs(fluid_key, type_ids=None)` → `[(building_id, outpost_id)]` and `discover_fluid_sources(fluid_key, own_outpost_id, type_ids=None)` → ranked ids. Tiered callers compose pairs per tier. Fixes two rule violations on the way: field_provider/plant_terraformer_water `except Exception: log.debug(...)` without `swallowed()`.
2. **`_port_starved(port)`**, 5 identical copies (`terraforming.py:66`, `fabricator.py:270`, `bio_volcanic.py:361`, `field_provider.py:161`, `plant_terraformer_water.py:65`) → `fluid_routing.port_starved(port)`.
3. **Event logging/callbacks**: every `ensure_*` builds the same `on_dropped`/`on_connect_notice`/`on_blacklisted` closures and the same `event.kind` if-chain (`oil_generator.py:172`, `steam_condenser.py:135/153`, `fluid_pump.py:110`, `thermal_cap.py:140`, `field_provider.py:172`, `plant_terraformer_water.py:76`, fabricator, bio_volcanic, terraforming, refiner, habitat, essence_liquifier, exotic_cap). Add `fluid_routing.ensure_input_logged(router, port, tick, starved, log, name, port_label, fluid_label)` and `ensure_output_logged(...)` emitting the standard lines; callers pass only the per-fluid "not found" hint. `field_provider.ensure_water` and `plant_terraformer_water.ensure_water` (0.98 clone) collapse into one call each.
4. Optional, low value: hysteresis gate (`terraforming._update_guard`, `steam_condenser.update_steam_gate/update_water_gate`) → small `HysteresisGate` helper. Skip unless cheap.
Not migrated: `water_sink.py` direct `port.connect(tank_id)` (deliberate one-shot drain of one chosen tank), `tank_upgrade` connect (swap migration), steam-guard `disconnect()`.

## Cluster I — item load / drain
Most loaders already use `storage.take_item` and most drains `storage.drain_port_inventory_first/drain_port_to_storage` (fabricator, smelter, bio_volcanic, fuel_assembler load, feed_maker load, habitat, pioneer_construction, essence_liquifier.feed_from_warehouse: keep). Relics/clones:
1. **Exact clones**: `5_steampower/lib/essence_liquifier.py:131 _local_depots` + `:154 _depot_stock` == `logistics_requests.local_depots/depot_stock` → delete, call shared.
2. **`_inventory_count` ×8** (`drone_upgrade`, `fleet_commission`, `fleet_decommission`, `fleet_upgrade`, `pioneer_commission`, `tank_upgrade`, `warehouse_upgrade`, `wildlife_planner`) → `storage.inventory_count(item_id)` next to `total_stock` (`storage.py:163`).
3. **Hand-rolled drains**:
   - `6_seeds/lib/seed_maker.py:225 _drain_output` = inventory-first-then-warehouse by hand → `drain_port_inventory_first`.
   - `6_seeds/lib/seed_supply.py:111` and `9_wildlife/lib/feed_maker.py:211` = warehouse-first-then-default by hand → new `storage.drain_port_storage_first(port, outpost)`.
   - `lib/bio.py:907 drain_output` (status-aware: busy/full/other) and fuel_assembler rod branch (`10_nuclear/lib/fuel_assembler.py:333`, cask target) hand-roll connect+send → extract `storage.send_stack(port, item_id, count, target) -> (moved, status, message)` used by both and inside the existing drain helpers; bio uses a result-list variant of `drain_port_to_storage`.
   - Optional: `storage.drain_and_report(port, outpost, log, name, at_home, on_moved=None)` for the identical result-reporting loops in fabricator/smelter/fuel_assembler (`on_moved` = `consume_manual_order` hook).
4. **Depot take loop**: `8_planting/lib/plant_terraformer.py:352 _take_from_depots` == depot loop in `seed_maker._load_one:195` → `logistics_requests.take_from_depots(port, item_id, amount, outpost) -> moved`. (`essence_liquifier.feed_from_depot` stays: retain/biome rules.)
5. **`_call(method, default, *args)` ×4** (`fuel_assembler:99`, `feed_maker:65`, `habitat:108`, `refiner:172`) → `swallow.call_or(obj, method, default, *args, where=...)` in tier-4 lib (other `_call` variants with different signatures stay).

## Cluster C — other clone pairs (validated by diff)
- **tank_upgrade ↔ warehouse_upgrade**: `_advance_once` (60 lines, only label/text/drain-method differ), `_advance`, `_sell_kits`, `_shape`, `_inventory_count` → shared `lib/building_swap_upgrade.py` base class; subclasses supply type ids, labels, `_drain`.
- **drone_claims ↔ vehicle_claims**: `_read_mission`, `save_mission`, `load_mission`, `set_*_recalled`, claim `updater`/refresh differ only by key/noun → shared `MissionStore(key, legacy_prefix, noun)` + recall-dict helpers in a new `lib/fleet_claims_common.py` (or in vehicle_claims, imported by drone_claims).
- **fabricator ↔ smelter**: `claim_recipe`, `release_recipe`, `is_shedded`, `run`, recipe-claim `updater` (separate keys `fabricator.recipe_claims` / `smelter.recipe_claims`) → `RecipeClaimMixin(claims_key, stale_ticks)` in a new `lib/recipe_claims.py`.
- **charging ↔ drone_service**: `__init__`, `assess_stations`, `is_nearest_station_to`, `step`, `run` → shared station-controller base (drone version adds "not among candidates → False").
- Small: `drone_energy.get_nearest_drone_service/get_nearest_drone_depot` (identical) → one `_nearest(type_ids)`; `mining_drill.publish_telemetry/updater` == `plant_terraformer.publish_telemetry/updater` → shared telemetry helper; `script_parking._set_powered` == `turbine_commit._set_powered`; `fleet_commission._start_script` == `fleet_upgrade._start_script`; `drones_panel.wrap_text` == `vehicles_panel.wrap_text`; `construction_plan.coords_of` == `vehicle.extract_coords`.
- Review-only (structural similarity, different intent; leave): `drone_navigation.fly_to_station/fly_to_drill`, `flight_timeout_ticks/drive_timeout_ticks`, `vehicle_survey.unscanned_pois/unsurveyed_known_sites`, the many `run()` loops.

## Order / scope
All four clusters are in scope, one session each: R → F(1,2,3) → I(1–5) → C (upgrade base, claims, recipe claims, stations, smalls). TODO.md tracks one item per cluster under "Handler Unification".
- Each session: one cluster, re-read the named files first (line numbers drift), one commit per sub-item where it helps, tick its TODO.md item.
- Deferred bits (F4 hysteresis gate, I3 `drain_and_report`, anything riskier than expected) stay as TODO.md sub-items.
- After the last cluster: move the plan to `docs/plans/done/` and the TODO items to TODO_done.md.

## Verification
- `python -m pytest tests -q` after each cluster (incl. `test_game_imports.py`, `test_log_blocks_balanced.py`, `test_reset_in_run_loops.py`, `test_game_builtins.py`); add focused tests for `publish_requests` (unchanged → no write, foreign owner skipped, empty → clear), `discover_fluid_sources` ranking, `port_starved`, shared upgrade base via existing fakes.
- `pyright` clean (pyrightconfig.json).
- AST check: rerun the near-duplicate scan below; migrated pairs must drop out.

```python
# Normalized-AST near-duplicate scan (run from repo root).
import ast, glob, difflib, itertools, copy
class N(ast.NodeTransformer):
    def visit_Name(s, n): return ast.copy_location(ast.Name(id='_', ctx=n.ctx), n)
    def visit_arg(s, n): n.arg = '_'; n.annotation = None; return n
    def visit_Constant(s, n): return ast.copy_location(ast.Constant(value=type(n.value).__name__), n)
fns = []
for f in sorted(glob.glob('scripts/**/*.py', recursive=True)):
    if '__pycache__' in f: continue
    for n in ast.walk(ast.parse(open(f, encoding='utf-8').read())):
        if isinstance(n, ast.FunctionDef) and n.end_lineno - n.lineno >= 5:
            s = ast.dump(N().visit(copy.deepcopy(ast.Module(body=n.body, type_ignores=[]))))
            fns.append((f, n.lineno, n.name, n.end_lineno - n.lineno + 1, s.replace('(', ' ').replace(')', ' ').replace(',', ' ').split()))
out = []
for a, b in itertools.combinations(fns, 2):
    if min(a[3], b[3]) / max(a[3], b[3]) < 0.6: continue
    sm = difflib.SequenceMatcher(None, a[4], b[4], autojunk=False)
    if sm.real_quick_ratio() >= 0.85 and sm.quick_ratio() >= 0.85 and sm.ratio() >= 0.85:
        out.append((sm.ratio(), a, b))
for r, a, b in sorted(out, key=lambda x: -x[0] * min(x[1][3], x[2][3]))[:150]:
    print(f"{r:.2f} {a[0]}:{a[1]} {a[2]}({a[3]}L) ~ {b[0]}:{b[1]} {b[2]}({b[3]}L)")
```
- Live deploy only via `devtools/scripts_sync.py` after asking the user.
