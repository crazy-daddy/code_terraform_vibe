# Power phases, power sizing and the reactor site (rough plan)

Status: rough plan, 2026-10-21. Not started. One code session per step group (A, B, C, D), each with a handoff.

Absorbs the atomic power evaluation of 2026-10-02 (`atomic_rush.md`, deleted). Two contradictions between the two plans are resolved here (operator, 2026-10-21):

- Backup after nuclear: Oil Generators, not parked turbines. Turbines are retired and sold; Thermal Caps and Steam Condensers stay.
- "Rush": removed. Nuclear Program unlocks on its own at Terraform Index 650,000. What the old plan called rushing is an ordering rule (push newly unlocked pillars first) plus a prep track so the Reactor is bought the moment the gate opens.

Three problems share the same code (`autoplay_roles` catalog, `outpost_needs.host_check()`, `build_providers.kit_wants()` and `power_wants()`):

1. The planner has no notion of which power source is current, so it can't retire steam or move a reactor onto the old steam outpost.
2. The reactor role models only the Reactor. The Lead Casks and the Fuel Assembler deploy at home, so uranium and fuel rods have to be hauled, which would need a dedicated nuclear hauler.
3. Power is sized to the fluid supply, not to demand: a run ends up with 20 turbines and 19 gas tanks for ~500 W of load.

## Why nuclear

Power buildings each need a running script, and above 50 running scripts every script shrinks every other script's step allowance (`docs/cheatsheet/dev_workflow.md` §1d-1). Fewer, larger generators are the lever.

| Source | Output | Running scripts per 5 kW | Shop price |
|---|---|---|---|
| Solar tracker | 50 W in daylight, 0 at night | ~100 by day (stopped at night, §1d-2) | |
| Steam Turbine | 108 W (90 t/h steam) | ~46, plus the Thermal Caps feeding them | 7,500 cr |
| Oil Generator | 700 W (8 t/h oil) | ~7 | 2,000 cr |
| Reactor | 5,000 W, day and night | 1 | 750,000 cr |

Example: 20 turbines + 19 solar trackers (≤ ~3.1 kW, ~39 scripts) replaced by one Reactor moves N from ~165 to ~127 running scripts: allowance 303 → ~394 steps per tick, ~30% for every script. The chain adds little: the Fuel Assembler parks when idle (§1d-2), only the leader Weather Station script runs (`production_logistics.md` §1m), and the aftermath drone is a fleet drone.

## Ordering, not rush

Nuclear Program needs Terraform Index 650,000 (`docs/database/research_catalog.md`). Without Wildlife the Index can reach 900,000 (atmosphere 700k + biomass 100k + plants 100k), so the gate opens late in the atmosphere work either way. The rule: when a pillar unlocks, push it first (full Biomass at 250,000 t, the Plants phases, Wildlife), because cheap TP there moves the Index faster than more atmosphere generators.

No new code (operator): atmosphere focus is `focus_plan.py`; the biomass, plants and wildlife planners pick their roles up through role gaps as soon as they unlock and retire via `autoplay_roles.RETIRED_WITH`. This section is a design note.

**Wildlife.** TP is credited per individual and accrues continuously between phase boundaries (`docs/guide/terraform_index.md`); the sensor counts individuals in established colonies (`docs/components/wildlife_sensor.md`). Phases at 10 / 1,000 / 50,000 / 500,000 / 5,000,000 individuals (decompiled dump). Species count earns Insight and Mk II capacity, not TP. Per-colony growth flattens to ~150 individuals/h past 5,000, and undeploying a Habitat pauses its growth. So: never cycle species through Habitats to "found them all"; found as many colonies as slots and feed allow and keep every one growing. A colony is founded with 4; at full support a Common colony reaches 10 individuals ~65 game h after establishment (Uncommon ~86 h, Rare ~128 h; model estimates). Fragments and feed recipes are not the bottleneck (`wildlife.md` §1l-2).

## Power phases

`game_phase.power_phase(snap)`, a pure function over the phase snapshot like the other predicates. Inputs are research and the generators that stand.

| Phase | Sources | Rule |
| ---: | :--- | :--- |
| 1 | solar | only source; no outpost role |
| 2 | steam (+ solar) | solar still allowed, fading out (no new trackers, old ones not replaced) |
| 3 | steam + oil | both coexist; power added in this phase is Oil Generators, never more turbines or solar |
| 4 | nuclear (+ oil) | oil stays as the fallback; steam turbines retired, caps and condensers stay |

**Triggers** (operator): a phase *opens* on its research unlock (Thermal Cap, Oil Generator, Nuclear Program); from then on new power uses the new source. The old source *retires* only once the new one carries the grid, and gradually. For 3→4: Nuclear Program unlocked = reactor site designated, prep and cash spent, no more turbines; turbines are sold only after a Reactor runs with rods in stock and `power.reactor_carried(grid)` holds, in batches of the ones turbine commitment (`lib/turbine_commit.py`) has already parked. Same shape for 1→2 (no new solar once a turbine stands; old trackers sold later) and 2→3. `power_phase` is the predicate; the retire pacing belongs to the power planner.

Oil is finite and shared with Tar and Plastics; some players report being oil-gated. The surplus base-load mode (`power_fluids.md` §1c-1) burns only the wells' inflow no other consumer takes.

## Size power to demand

Today `build_providers.power_wants()` adds one generator whenever grid headroom is negative and the reserve is low, with no upper bound, and `vent_cycles.plan_steam()` (`steam.plan`, STATUS card) sizes turbines and tanks to what the vents can carry. Neither looks at demand. The result is turbines and tanks that terraforming could have used as slots and scripts.

Rule: generator count = measured demand, capped by the fluid supply.

- **Demand**: 7-day peak of consumed W from `power.daily_hist:<anchor>` (§1a-0, already recorded), plus the draw of designated-but-unbuilt roles (`autoplay_roles.demand()`, `build_providers.generator_draw()`), plus a margin.
- **Steam supply**: `steam.plan` turbines carried (exists).
- **Oil supply**: new `oil.plan` mirroring `plan_steam()`: wells' rate × active share from `journal.surveyed_sites()` and the deep-survey cycle; until surveyed, the §1c-1 inflow EMA, persisted to the archive (today it lives only in `oil_generator.py` memory).
- Gas tanks sized to the turbines actually wanted, not to the vents.
- `power_wants()` gets the upper bound; `retire_wants()` sells surplus turbines and gas tanks.
- Demand and supply figures on the STATUS card beside `steam.plan`.

## Nuclear prep track, in unlock order

| Prep | Opens at |
|---|---|
| Weather Station in every biome (dust messages need all 5, `production_logistics.md` §1m; 60,000 cr each beyond the one Weather Program installs), uranium stockpiled in Lead Casks | Weather Program, TI 330,000 |
| Plated drone (Shield Plating) for uranium collection | Shielded Logistics, O2 3,000 |
| Fuel Assembler + Lead Ore (H2) mining; one rod = 4 Raw Uranium + 2 Lead Plates | Fuel Assembler, Temp 10,000 |
| Order **Vestibule, Hot Freight Proof** (Raw Uranium), which unlocks `craft_fuel_rod` | needs uranium |
| 750,000 cr saved through the cash manager | before TI 650,000 |

The prep runs during phases 2 and 3, so the Reactor is bought when the gate opens and phase 4 starts without a power gap. Uranium is not the limit: a dust storm every 48 game h leaves 14-28 Raw Uranium, ~10.5 U/day (~2.6 rods/day) if all are collected; one Reactor at heat 1.0 burns 1/3 rod/day, a Mk IV generator 0.1 rod/day, so supply covers ~7 Reactors (~35 kW) (`production_logistics.md` §1n).

## Steps

### A. Split the power role

- `power` covers both turbines and oil generators (preset: steam and oil in), so "drop steam, keep oil" can't be expressed. Split it into `power_steam` (`steam_turbine`, in: steam) and `power_oil` (`oil_generator`, in: oil).
- Migrate existing `autoplay.outpost_roles` entries: `power` becomes whichever of the two the outpost's buildings make up (both if both stand). Readers to update: `power_plan`, `extractor_plan`, `fluid_plan`, the `power` `site_fluid` need in `outpost_needs.lookahead()`, the Steam Condenser host pick in `kit_wants()` (`"power" in role_list(...)`), `DEFAULT_ROLE_PRESETS`, cheatsheet §11f.
- `condenser` (Steam Condenser) goes with `power_steam`.

### B. Reactor site as one role

Current: `ROLE_CATALOG["reactor"] = {"buildings": ["reactor"], "exclusive": True}`; Lead Casks (`LEAD_CASKS`) and the Fuel Assembler deploy at home (`build_providers.kit_wants()`, `outpost=base["id"]`).

Site needs (operator):

| Building | Count | Strictly needed |
| :--- | ---: | :--- |
| Reactor | ≥ 1 | yes |
| Lead Cask | ≥ 2 (uranium, fuel rods) | ≥ 1 (fuel rods) |
| Fuel Assembler | ≥ 1 | no, but it removes the uranium/fuel rod hauling |
| Warehouse | ≥ 1 (lead plates) | no |
| Liquid Tank (water) | ≥ 1 | no |
| Mk IV terraform generators | any | no (`terraform`, already in `EXCLUSIVE_SHARE_ROLES`) |

Nothing else lives at the reactor host: Smelter, Fabricator and Weather Stations stand at other outposts, water pumps in the field.

- `reactor` role: buildings `reactor`, `lead_cask`, `fuel_assembler`; `items: True` (Warehouse and Drone Depot through the normal stock path; `lead_plate` on its stock list). Catalog groups are all-or-nothing, so the building planner builds the Fuel Assembler there. Water tank via `storage_water` when wanted.
- The role's own machines never trip the exclusive check: `host_check()` looks only at the host's *other* roles.
- `kit_wants()`: casks and Fuel Assembler at the reactor host once one is designated, else home (as now).
- Moving an existing home Fuel Assembler and casks to the reactor site: undeploy and redeploy, or leave them at home. Decide in the session; the casks hold uranium, so drain first.

### C. Phase transitions in the outpost planner

- **Exclusive rule.** `host_check()` uses `_penalized_role()` (`storage.PENALIZED_TYPES`, the overcrowding list) as a stand-in for "production role". The real reason for `exclusive` is the slot budget (run 2: "too few slots", [planner_rev2_results.md](planner_rev2_results.md)). Replace the proxy with an explicit rule: an exclusive host takes `EXCLUSIVE_SHARE_ROLES`, non-penalized roles, and, during the 3→4 transition, roles that retire in phase 4 (`power_steam`).
- **Water site.** `reactor` is a `site_fluid` water need (`NEAR_TILES`). In phase 3+ with a water network built, accept piped water: the steam outpost is geothermal and has no water wells. Pipes are cheap by then (operator).
- **Retire steam turbines.** Gated on `power.reactor_carried(grid)` with rods in stock, not on the unlock. Phase 4 adds `power_steam` to `autoplay_roles.retired()` (same path as the bio, biomass, plants and wildlife roles: dropped from the designation, never re-proposed). The turbines still need an undeploy-and-sell step: a `retire_wants()` entry in `build_providers` or the power planner's steam leg, selling in batches the turbines turbine commitment has parked. Thermal Caps, Gas Tanks that condensers or fabricators draw from, and the Steam Condensers stay: fabricators and condensers consume steam. No parked-turbine backup; the Oil Generators are the fallback.
- **Repurpose.** With the turbines gone, the geothermal power outpost is the natural reactor host (outpost costs scale, so no new outpost). Its `liquifier_geothermal` must not block: biomass is usually complete before nuclear, so `retired()` has dropped it already. Check that order holds; if not, let `liquifier_*` share with the reactor.
- **Solar fade (phase 2+).** No new trackers; selling old ones is the TODO "retire solar trackers early" in Phase 10.

### D. Size power to demand

The rule from "Size power to demand" above: demand from `power.daily_hist` plus designated draw, `oil.plan` beside `steam.plan` with the inflow EMA persisted, an upper bound in `power_wants()`, a surplus retire path in `retire_wants()`, STATUS card figures.

## Caveats

- Mk IV heater/O2/pressure packs draw ~100× Mk I power and burn rods, so the nuclear era raises demand; plan for several Reactors.
- One Reactor is a single point of failure (no rods, no cooling water): the oil fallback and the battery tier cover it.
- Fuel use follows commanded heat, not output: without load following a full battery wastes rods (TODO.md Phase 10).

## Decisions (operator, 2026-10-21)

- Phase triggers: open on unlock, retire the old source only once the new one carries the grid. `power_phase` lives in `game_phase`.
- Reactor host roles: `terraform` Mk IV generators plus the reactor role's own buildings (Reactor, Lead Casks, Fuel Assembler, Warehouse, water tank via `storage_water`). Nothing else.
- Oil fallback size in phase 4: sized to the loads that keep the Reactor rolling, grid-wide wherever they stand: Drone Stations, Weather Stations (uranium), water pumps (cooling), Smelter (lead), Fabricator (lead plates), Fuel Assembler. Measured from those members' draw on the grid, not a fixed count.
- Pillar-first rule: design note, no code.

## Open

- Oil surplus vs more Reactors. Burning the surplus keeps more running scripts; an extra Reactor costs ~1/3 rod/day, the rods of ~3 Mk IV generators. Decide once oil inflow and the Mk IV count are measured on a save; record both numbers here.
