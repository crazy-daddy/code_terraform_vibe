# Atomic Power Rush (future runs)

Evaluation (2026-10-02) of reaching Nuclear Program and a first Reactor as early as possible on a new save. Power buildings each need a running script, and above 50 running scripts every script shrinks every other script's step allowance (`docs/cheatsheet/dev_workflow.md` §1d-1). Fewer, larger generators are the lever.

## Verdict

Worth it as an ordering rule, not as a diversion. Nuclear Program needs Terraform Index 650,000 (`docs/database/research_catalog.md`). Without Wildlife the Index can reach 900,000 (atmosphere 700k + biomass 100k + plants 100k), so 650,000 needs most of the atmosphere progress either way. Take the cheap pillar TP early (full Biomass at 250,000 t, the Plants phases, the first Wildlife phase). Run the nuclear prep in parallel, so the Reactor is bought the moment the gate opens.

## Power per running script

| Source | Output | Running scripts per 5 kW | Shop price |
|---|---|---|---|
| Solar tracker | 50 W in daylight, 0 at night | ~100 by day (stopped at night, §1d-2) | |
| Steam Turbine | 108 W (90 t/h steam) | ~46, plus the Thermal Caps feeding them | 7,500 cr |
| Oil Generator | 700 W (8 t/h oil) | ~7 | 2,000 cr |
| Reactor | 5,000 W, day and night | 1 | 750,000 cr |

Example: 20 turbines + 19 solar trackers (≤ ~3.1 kW, ~39 scripts) replaced by one Reactor moves N from ~165 to ~127 running scripts: allowance 303 → ~394 steps per tick, ~30% for every script. The chain adds little: the Fuel Assembler parks when idle (§1d-2), only the leader Weather Station script runs (`production_logistics.md` §1m), and the aftermath drone is a fleet drone. Turbines need not be sold: turbine commitment (`lib/turbine_commit.py`) parks the ones the Reactor's output replaces, and parked turbines cost no steps, so they stay as backup for a Reactor trip or a rod shortage.

## Before the gate: Oil Generators

Per script an Oil Generator gives ~6.5× a Steam Turbine and ~14× a solar tracker at peak, so power added before 650,000 should be Oil Generators fed by Oil Pumps, not more turbines or solar. Oil is finite and shared with Tar and Plastics; some players report being oil-gated. The surplus base-load mode (`power_fluids.md` §1c-1) burns only the wells' inflow no other consumer takes, so the generator count is sized to that surplus. Unknown: oil yield per well, to be measured early in a run.

## Nuclear prep, in unlock order

| Prep | Opens at |
|---|---|
| Weather Station in every biome (dust messages need all 5, `production_logistics.md` §1m; 60,000 cr each beyond the one Weather Program installs), uranium stockpiled in Lead Casks | Weather Program, TI 330,000 |
| Plated drone (Shield Plating) for uranium collection | Shielded Logistics, O2 3,000 |
| Fuel Assembler + Lead Ore (H2) mining; one rod = 4 Raw Uranium + 2 Lead Plates | Fuel Assembler, Temp 10,000 |
| Order **Vestibule, Hot Freight Proof** (Raw Uranium), which unlocks `craft_fuel_rod` | needs uranium |
| 750,000 cr saved through the cash manager | before TI 650,000 |

Uranium is not the limit: a dust storm every 48 game h leaves 14-28 Raw Uranium, ~10.5 U/day if all are collected; one Reactor at heat 1.0 burns 1/3 rod/day (1.3 U/day), so supply covers ~7 Reactors (~35 kW) (`production_logistics.md` §1n).

## First Wildlife phase

The Wildlife pillar counts individuals in established colonies, not species (`docs/components/wildlife_sensor.md`). A colony is founded with 4; at full support `wildlife_model.breeding_rate` puts a Common colony at 10 individuals ~65 game h after establishment (Uncommon ~86 h, Rare ~128 h; model estimates). The phase threshold and its TP are not in the repo docs (only in the local decompiled dump). Fragments and feed recipes are not the bottleneck: the Collector + Bio Lab catalog creatures fast, and the planner revives whatever is ready (`wildlife.md` §1l-2).

## Caveats

- Mk IV heater/O2/pressure packs draw ~100× Mk I power and burn rods, so the nuclear era raises demand; plan for several Reactors.
- One Reactor is a single point of failure (overheat trip, no rods, no cooling water): keep parked turbines and the battery tier as backup.
- Fuel use follows commanded heat, not output: without load following a full battery wastes rods (TODO.md Phase 10).
