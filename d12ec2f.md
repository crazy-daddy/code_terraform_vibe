# Version Change TODO: Experimental v0.1.31 (manual build d12ec2f)

Temporary checklist for adopting the v0.1.31 changes (changelog in
[VERSIONCHANGE_TODO.md](VERSIONCHANGE_TODO.md), docs diff, and the simworker diff
`b102c2b_working.md`, from e1986ce). Fold open items into [TODO.md](TODO.md) or finish them, then
delete this file.

## 0. Devtools after the update (dev_workflow.md §10c)

- [x] Docs split: one section was renamed (`Vehicle Proximity & Service` -> `... Service Areas`);
      the `##` heading in `docs/guide/vehicle_service_areas.md` was updated and the split re-run.
      No new or dropped files.
- [x] `extract_game_spec.py`: `unresolved 0`, `coverage ok`. The `tests/game_spec.json` diff only
      adds `inventory.compact` and `run_control.pause` / `resume`.
- [x] Seed generators: `seed_quality.py recipes --check` and `field.mjs --check` report
      `port matches` for seeds 1, 7 and 42. The game's world-generation code did not change, so
      the `swap_seed.py` round trip was not re-run.
- [x] `game_speed.py`: the `=setInterval(` clock pattern still matches the raw bundle (one match).
- [x] `headless/simhost.mjs`: the game removed its per-system wrapper `g9(name, fn)`. Each system
      now runs in its own inline `try { ... } catch (e) { he.error(`TICK`, `<Name> failed`, e); }`.
      `SYSTEM_WRAPPER` was replaced by `SYSTEM_TRY`, which wraps each try body in
      `__ctTimedSystem(`<Name>`, ...)` and keeps the catch. It wraps 28 of 28 blocks in 7 ms.
      Per-system timing and `--skip-systems` work again under the same names.
      `SensorSystem` is gone: its tick was a no-op.
- [x] Headless runs: a fresh save prints no `[headless]` line. A recorder save (t713551) and the
      midlate sample save run with latest scripts: `errored` 0, no `Game version changed`.
- [x] `python -m unittest discover -s tests`: 1686 tests OK.

## 1. Smelter/Fabricator recipe times now include the Mk tier (top priority)

Changelog: "Mk II and Mk III Smelters and Fabricators now report their own recipe times and power
to scripts". In the simworker, `list_recipes()` and `find_recipe()` on a Smelter, Fabricator,
Fuel Assembler or Refiner now build each `Recipe` for the machine that was asked
(`s4(recipe, machine)`):

- `duration_game_hours` is divided by that machine's speed.
- `power_draw` is multiplied by that machine's power factor.

The Smelter/Fabricator speed table is 1 / 2 / 4 for Mk I / II / III, the same values as our
`MACHINE_TIER_SPEED`. Until now only the Feed Maker's `Recipe` included its tier.

Our code still assumes Mk I times:
[production_core.py:20-23](scripts/4_controlpanel/lib/production_core.py#L20-L23) and
`craft_seconds(recipe, speed)` divide by `machine_speed()` again. So on a Mk II machine the craft
time is underestimated 4x, and on a Mk III machine 16x:

- `smelter.py` (`switch_min_demand`, ore prefill cap) and `fabricator.py` `load_inputs()` pass
  their own machine's speed. Their recipe comes from their own machine, so it is already scaled.
  Result: the prefill window stages more crafts than intended. The hardware and chunk caps
  limit the effect.
- `production_sites.local_make_seconds()` reads recipes from `SourceCache` (the default
  Smelter/Fabricator, scaled by that machine's tier) and then divides by the speed of the site's
  fastest machine. Result: the time is wrong whenever the default machine is not Mk I.

- [x] Normalized: `craft_seconds(recipe, speed, source_speed)`; own-machine callers pass
      neither, `local_make_seconds()` passes `SourceCache.recipe_source_speed(kind)`.
      Was: choose a fix. Either normalize to base time (multiply each `Recipe` by the speed of the
      machine it came from, then divide by the target machine's speed), or pass `speed=1` where
      the recipe comes from the machine that runs it and handle `SourceCache` separately.
- [x] Update production_logistics.md (the `craft_seconds()` paragraph says the Mk I time is
      reported on every tier) and the `Recipe` fakes in `tests/game_stubs.py` if they model tiers.

## 2. `run_control.pause(machine_id)` / `resume(machine_id)` (opportunity for script parking)

`pause` holds a machine's running script at its current line and keeps its setpoints. `resume`
continues it from that line. Outcomes, kinds and the full contract:
[docs/components/run_control.md](docs/components/run_control.md). Details from the decompiled
code:

- It works on any scripted machine, including machines without a breaker (solar, Harvester,
  vehicles). Today breaker parking (dev_workflow.md §1d-2, `lib/script_parking.py`) covers only
  machines with `can_power_off()`.
- A paused script has status `paused`, so like a breaker pause it should drop out of the
  running-script count N (§1d). Not measured yet.
- Calling `pause` on a script that a power cut already paused removes it from
  `powerPausedScriptIds`. It then stays paused when power returns. This interacts with
  `PowerGridManager` load shedding.
- After a save loads, a paused script stays paused, and `resume` restarts it from the first line.

- [x] Measured headless (midlate sample save, drone_7, drone_8, pioneer_1 paused for 3000 ticks
      from an Automation): N drops by 1 per pause, `is_running()` reads False, `resume` -> `ok`,
      and the controllers carry on. A drone paused in flight finishes the flight and docks at its
      depot. While paused and docked it does not charge (battery flat for 1500 ticks), because
      charging needs the vehicle's own script. Solar is not needed: night stop already covers it.
      In the sample save's `fleet.status`, about 8 of 22 vehicles are idle (2 Pioneers
      `IDLE_AT_BASE`, 1 scout `SURVEY_COMPLETE`, 5 haulers `IDLE*`).
- [ ] Decide whether `script_parking.py` should use `pause`/`resume` for machines without a
      breaker. Keep breakers where load shedding needs them.

## 3. "Goal already met" outcomes are now successes

The status codes did not change, only their documented kind (`rejection` -> `success`):
`target_reached` (Vehicle Charging Station and Drone Service Station `charge`/`refuel`),
`already_here` (Harvester `move`), `already_full` (Harvester refill), `no_op` (Lightning Rod
repair), `already_purchased` (Habitat node). The game no longer prints a console warning for
them.

- [x] Checked: our scripts branch on `.status` (charging.py, drone_service.py, habitat.py,
      harvester_care.py, harvester_heat.py, 0_cold_boot harvester.py), not on the kind. No
      action.

## 4. Renamed display names

Ids are unchanged. Only labels changed:

| Old | New |
| --- | --- |
| Exotic Husbandry (`research_exotic_husbandry`) | Exotic Fluids |
| Deep Exotics (`research_deep_exotics`) | Rare Exotics |
| Deep-Sea Conditioning (`research_bio_conditioner`) | Deep Fragment Conditioning |
| Wide Sonar (`sonar_module_wide`) | Extended Sonar |
| Enrichment Compound | Bio Enrichment Compound |
| mobile unit role Hazard | Hazmat |
| "hot cargo" | "radioactive cargo" (outcome codes `hot_cargo_requires_cask`, `cask_accepts_hot_only` unchanged) |

Some Earth Order titles also changed, for example "Helios, Heavy Drill Build" became "Helios,
Mining Drill Kit Build".

- [ ] Optional: `RESEARCH_NAMES` in
      [contact_inference.py:37-38](scripts/4_controlpanel/lib/contact_inference.py#L37-L38)
      (marker labels) and its comment on line 24 still use the old research names. Cosmetic.
- [x] No script compares order titles, item names or `nocturna.name()` with fixed text. The
      planet name is now localized; the docs say never to compare it.

## 5. Other API additions

- `inventory.compact() -> TransferResult` (`ok` / `already_compact`, `.moved` = units moved).
  No current use in our scripts.
- Panel `progress_bar` / `vertical_bar` take the gradient presets `"good-high"`, `"good-low"` and
  `"neutral"`, the same meters as the machine cards.
  - [ ] Optional: use them in the Control Room cards (battery charge, waste, progress bars).

## 6. Changes found only in the simworker diff

- Performance work, no script-visible effect: script writes are tracked with revision stamps
  (`QS`/`$S`/`eC`), and snapshot deltas skip unchanged infrastructure and scripts. The power
  topology cache now compares inputs instead of rebuilding a signature string. The power grid
  snapshot reads (`p3`) build `outpost_ids` / `machine_ids` / `members` lazily (`LSe.defer`).
  `power_control` values are unchanged.
- The game's internal logger now folds repeated lines into `(the previous line repeated N more
  times)` after 10 s. This applies to the browser console only, not to script `console` output.
- Wrong-material rejections (`target_wrong_material`) have per-machine messages for the Habitat,
  Seed Maker, Crop Automator, Plant Terraformer and Essence Liquifier. Supply Dock
  `order_slots_full` uses a new message key. The status codes are unchanged, and no script
  parses these messages.
- Biology Lab machines report `research_required` with a workbench-specific message.
- Outpost cameras show real storms. This changes the camera event registry (8 events, +WX-14
  "sunbreak") and the climate schedules in `planet.cameraObservations`. Cosmetic; the headless
  sim runs it like any other system.
- Only one number changed: the camera climate event count (`count: 12` -> `14`). Cosmetic.

## 7. Docs-only clarifications worth knowing

- Pipe throughput: each matched source-side and sink-side attachment link carries 2,000 t/h
  (6,000 t/h after High-Pressure Fluid Transport). Separate pipe networks that touch one outpost
  stay separate. Same model as before, worded as "pipe network" instead of "component".
- The Reactor uses 0.5-1 t/h of water whenever its heat setting is above 0, not only while
  heating.
- Vehicle Charging Station: when no `dock()` is chosen, a vehicle docks at the station closest
  to it. Distance is measured to the station or to its outpost's center, whichever is closer.
  The station charges docked vehicles in the order they were queued.
- `Recipe.duration_game_hours` doc: "including the querying machine's Mk tier" (see §1).
- Script logs under `<save>_scripts/logs/` are written only while external editing is on, and
  logs of deleted scripts are removed. Our setup has external editing on.
