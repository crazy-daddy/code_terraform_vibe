# Early-game build-order optimization (0 → 150k TP)

Results of the headless build-order search (2026-10-05). Tools: `devtools/headless/policy.mjs` (plays the Shop and Inventory from a JSON plan), `devtools/buildorder_search.py` (runs plans in parallel, one Node process per core), `devtools/buildorder_model.py` (TP curve). Runner usage: [dev_workflow.md §10b](../cheatsheet/dev_workflow.md).

**Bottom line:** fill the base with one pillar's generators at a time, each up to its phase-1 cap. Heat goes to 12 HU, because the Pioneer's Battery Holder needs it. Use the order heat → O2 → pressure, and keep the Bio-Loop. Result: 150k TP with a scout Pioneer ready in **4.08 game hours**, against **7.71 h** for the current order (O2 9 → pressure 0.2 → heat 12).

## Objective

- **Hard constraint:** at 150k TP, a scout Pioneer is deployed, with Nav, Sonar and a Battery Holder mounted, and `pioneer.py` is running. Its gates are Pioneer (100k TP), Nav (0.12 kPa), Sonar (0.15 kPa), Battery Holder (heat 12) and the Charging Station as its home (O2 9 ppt).
- **Pareto values:**
  1. Game hours to 150k TP with the Pioneer ready (primary).
  2. POIs discovered (`journal.planets.nocturna.mining.discoveredSites`).
  3. Net worth: credits plus the shop value of deployed machines, mounted modules and Inventory. Sales refund the full shop price.
- **Bio-Loop:** counts only through its credits. Its blueprint unlocks come too late to matter here.

## How TP works (simworker)

TP is a pure function of the current pillar values; it does not accumulate.
- Each pillar adds a piecewise-linear curve over its phase thresholds.
- Heat, O2 and pressure each get 136k/3 = **45,333 TP for phase 1**, then 46,000, 46,667, 47,333 and 48,000.
- The biosphere pillars (biomass, plants, wildlife) get 20,000 per phase.
- The total is capped at 1,000,000.

Checked against a save: O2 6.94 ppt gives 31,440 TP (the formula gives 31,465). Constants and code: `devtools/buildorder_model.py`.

| Pillar | Phase-1 cap | Phase-2 end | TP per unit, phase 1 | TP per unit, phase 2 |
| :--- | ---: | ---: | ---: | ---: |
| O2 | 10 ppt | 150 ppt | 4,533 / ppt | 329 / ppt |
| Pressure | 0.3 kPa | 7 kPa | 151,111 / kPa | 6,866 / kPa |
| Heat | 11 HU | 140 HU | 4,121 / HU | 357 / HU |

- All three phase-1 caps together give 136k TP. The last 14k to 150k must come from phase 2, which is 13–22× slower per generator.
- 9 ppt, 0.11 kPa and 12 HU are unlock gates, not TP breakpoints.

## Generator calibration (headless, Mk I, from checkpoint h2)

| Generator | Rate at 100 % | Measured efficiency | Power | Price |
| :--- | ---: | :--- | ---: | ---: |
| Oxygen Generator | 0.0004 ppt/s | 100 % | 8 W | 1,000 cr |
| Pressure Generator | 0.00002 kPa/s | 100 % after a ramp of about 0.2 h per new generator (resonance sync) | 7 W | 900 cr |
| Heat Generator (`temp_heater`) | 0.00042 HU/s | about 93 % on average (weather dips) | 5 W | 800 cr |

- At 100 %, TP per generator in phase 1 is: pressure 3.0, O2 1.8, heat 1.7 TP/s.
- In phase 2 all three are about 0.13–0.14 TP/s. Heat is a little lower because of weather.
- Time units are game seconds; a game day is 600 s.

Phase-1 gains are linear and slots are the binding resource. So the time to fill all three caps depends mostly on generator-seconds, not on the order. Order only shifts unlock timing (Charger, rovers, Pioneer) and the efficiency of the tail.

## Macro-plan results (checkpoint h2: tick 1193, after onboarding, 550 cr)

Each plan fills the free base slots with the active pillar's generators (`keep` = fill) and sells the previous pillar's generators (full refund). Its last pillar keeps the slots for the phase-2 tail. In every plan, the Charging Station comes first in the keep list and 2 rovers come with it.
- `pw S/B`: solar panels / batteries.
- `-bio`: Bio-Loop sold, so 3 more generator slots.
- `+ind`: Smelter + Supply Dock.

| Plan (order, targets) | Hours | POIs | Net worth |
| :--- | ---: | ---: | ---: |
| pressure>heat>o2 0.3/12/10 pw7/4 -bio | 3.62 | 3 | 36,925 |
| heat>pressure>o2 12/0.3/10 pw7/4 -bio | 3.64 | 3 | 36,925 |
| heat>o2>pressure 12/10/0.3 pw7/4 -bio | 3.73 | 9 | 36,925 |
| o2>heat>pressure 10/12/0.3 pw7/4 -bio | 3.76 | 9 | 36,925 |
| pressure>o2>heat 0.3/10/11 pw7/4 -bio | 3.89 | 3 | 36,925 |
| o2>pressure>heat 10/0.3/11 pw7/4 -bio | 3.94 | 9 | 36,925 |
| **heat>o2>pressure 12/10/0.3 pw6/3** | **4.08** | **9** | **217,874** |
| pressure>heat>o2 0.3/12/10 pw6/3 | 4.15 | 3 | 259,509 |
| heat>pressure>o2 12/0.3/10 pw6/3 | 4.17 | 3 | 246,481 |
| o2>heat>pressure 10/12/0.3 pw6/3 | 4.17 | 9 | 247,081 |
| pressure>o2>heat 0.3/10/11 pw6/3 | 4.43 | 9 | 214,506 |
| o2>pressure>heat 10/0.3/11 pw6/3 | 4.44 | 9 | 217,815 |
| heat>o2>pressure 12/10/0.3 pw6/3 +ind | 4.65 | 9 | 262,623 |
| pressure>heat>o2 0.3/12/10 pw6/3 +ind | 4.69 | 3 | 259,486 |
| heat>pressure>o2 12/0.3/10 pw6/3 +ind | 4.71 | 3 | 259,506 |
| o2>heat>pressure 10/12/0.3 pw6/3 +ind | 4.77 | 9 | 275,102 |
| pressure>o2>heat 0.3/10/11 pw6/3 +ind | 5.08 | 9 | 248,396 |
| o2>pressure>heat 10/0.3/11 pw6/3 +ind | 5.20 | 9 | 262,587 |
| **current: o2>pressure>heat 9/0.2/12 pw6/3** | **7.71** | **9** | **218,029** |

What the table shows:
- **Caps beat gates.** The current targets stop O2 at 9.02 and pressure at 0.2. That leaves about 19.6k phase-1 TP unused, and then heat crawls through phase 2 for about 5 h.
- **Order matters little (±0.1 h), but heat should not be last.** A heat tail runs at about 93 % efficiency (weather), so plans that end in heat are about 0.3 h slower.
- **Bio-Loop:** selling it saves about 0.45 h but cuts net worth from about 220k to 37k. It is the main credit source of this phase.
- **Industry (Smelter + Supply Dock):** costs about 0.6 h, because it takes 2 generator slots. It adds only 30–45k net worth, since the Supply Dock unlocks late (110k TP).
- **POIs:** plans that reach O2 9 (Charging Station) late, i.e. pressure first, discover only 3 POIs instead of 9.

### Timeline of the best plan (heat>o2>pressure 12/10/0.3 pw6/3)

| Game h | TP | O2 / P / Heat | Credits | Event |
| ---: | ---: | :--- | ---: | :--- |
| 0 | 231 | 0.05 / 0 / 0 | 550 | stage 0: heaters |
| 0.75 | 45,770 | 0.05 / 0 / 11.5 | 7,300 | |
| 1.0 | 65,032 | 4.27 / 0 / 12.0 | 32,714 | stage 1: O2 generators |
| 1.25 | 85,944 | 8.88 / 0 / 12.0 | 80,533 | Charging Station at about 1.26 h |
| 1.5 | 100,811 | 10.02 / 0.06 / 12.0 | 118,386 | stage 2: pressure; Pioneer at about 1.5 h |
| 1.75 | 132,909 | 10.02 / 0.28 / 12.0 | 156,038 | Pioneer ready |
| 2.0 | 137,692 | 10.02 / 0.49 / 12.0 | 160,229 | phase-2 tail starts |
| 4.08 | 150,000 | 10.02 / 2.29 / 12.0 | 171,174 | done |

The phase-2 tail (136k → 150k) takes about 2.1 h, half of the run. From about 2.75 h, the credits stop growing and sit unused.

## Opening order (checkpoint h1: tick 582, 2 unpowered O2 generators, no power, 3,275 cr)

Every opening continues with heat>o2>pressure 12/10/0.3. The `opening` list is bought in order before the stages start.

| Opening | pw6/3 | pw5/2 | pw4/2 |
| :--- | ---: | ---: | ---: |
| power first (batteries, solar, then heaters) | 4.11 | 4.39 | 5.23 |
| just-in-time (S H H H H S B H H H H S B) | 4.09 | 4.39 | 5.23 |
| solar first (S S S H×6 B B) | 4.09 | 4.39 | 5.23 |
| heater rush (S H×6 B) | 4.09 | 4.39 | 5.23 |

- **The opening order does not matter:** all four finish within 0.02 h of each other. Credits limit only the first few minutes, and every order reaches a full base at about the same time.
- **The amount of power does matter.** 5 solar + 2 batteries loses 0.3 h to brownouts (about 80 s of empty battery). 4 + 2 loses 1.1 h. 6 + 3 shows about 4 s of brownout. The `-bio` plans used 7 + 4; that power level was not tested with the Bio-Loop kept.

## Auto Feeders first (checkpoint h2, 2026-10-06)

Variant: an O2 stage up to 1 ppt (Auto Feeders, so the Bio-Loop powers on), 2.2 ppt (10k TP from O2 alone: Ship Computer, so `solar.py` can take over the buying) or 3 ppt (Earth Clearance Contracts) runs before the best plan. Its O2 Generators are sold when the heat stage starts and bought again in the O2 stage. All runs start from the same checkpoint, so they share its world seed (the sim is deterministic).

| Plan (pw6/3) | 10k TP | Hours | Net worth | Credits at 0.5 h | Credits at 1 h | Final credits | Buys / sells before 10k TP |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| heat>o2>pressure (baseline) | 0.175 h | 3.98 | 217,892 | 5,625 | 52,752 | 171,192 | 16 / 4 |
| feeders1 + baseline | 0.183 h | 4.00 | 232,883 | 54,094 | 125,836 | 186,183 | 24 / 12 |
| **feeders2.2 + baseline** | 0.183 h | 4.00 | 232,821 | 50,144 | 125,722 | 186,121 | **12 / 0** |
| feeders3 + baseline | 0.183 h | 3.99 | 232,805 | 50,144 | 125,722 | 186,105 | 12 / 0 |

- **An O2 stage first is almost free and earns more.** It costs at most 0.02 h and gives +15k net worth (+7 %). The Bio-Loop pays its Bio Order credits about 0.6 h earlier, so about 50k credits are available at 0.5 h instead of 6k.
- **The O2 targets 1, 2.2 and 3 ppt give the same result** (within 0.01 h and 100 cr). Until about 10k TP the base is credit-bound, and O2 and heat give about the same TP per slot in phase 1.
- **O2 to 2.2 ppt needs the fewest manual actions before 10k TP:** 12 buys, no sales, versus 24 buys and 12 sales for O2 to 1 ppt (sell the O2 Generators, buy heaters). In this variant the switch to heaters comes at 10k TP, where `solar.py` can do it.
- **Earth Clearance contracts (O2 3 ppt):** with `"contracts": true` the policy credits the 3 contracts (Data Tablet 6,700, Sealed Vault 10,000, Terminal Breach 8,000 cr) 30 s after the unlock. In game, `scripts/contract/` solves them after one Accept click. Every plan gains exactly 24,700 cr of net worth and finishes at the same time. In feeders3 they pay at 0.23 h. In the other plans O2 reaches 3 ppt only in the O2 stage, so they pay at about 0.85 h, when credits are no longer short. The 3 intro contracts (4,150 cr) are solved before checkpoint h1. The next batch (Verified Contractor) needs O2 300 ppt.
- O2 1 ppt alone gives about 4.5k TP.
- The early credits sit unused in this plan. Experiments 2 and 3 below (Pressure Mk II, more power) could use them.
- Runs from before the heater-parking fix (below), so slower by about 0.3 h: pw7/4 was about 0.7 h slower than pw6/3 in every plan.

### Sim artifact: parked heaters (fixed 2026-10-06)

The first runs on 2026-10-06 gave 4.29 h for the baseline. The cause was not the reworked `heater.py`: old and new heater give the same time (3.97 h without `--park`). The cause was `--park`. Since commit d0f3148, parked heaters woke only on a day change or the 1-minute refresh. Each step of a new heater's power scan (`sleep(0.2)` between `set_power()` calls) then waited up to 1 minute, so heat lagged (1.4 HU instead of 3.9 HU at 0.25 h). The day-change A/B ran on a late save, where the heaters had already finished their scans, so it did not show this. `passive.mjs` now keeps a heater awake while its power changed recently or is 0. Parked runs now match unparked runs (3.98 h against 3.97 h) and still save about 25 % wall time.

## Pressure Mk II in the tail (checkpoint h2, 2026-10-06)

Variant: the feeders2.2 plan (Bio-Loop kept), plus a tail stage from 1.2 kPa (Mk II unlock, `research_pressure_mk2_pack`) that raises solar and batteries and applies Pressure Mk II packs (12,000 cr, 5x output, 5x power draw). The policy applies a pack only once the stage's solar and battery counts are met. Suite: `--suite mk2`.

| Packs | pw6/3 | pw8/4 | pw10/5 | pw12/6 |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 4.01 | | | |
| 4 | 3.74 | 3.53 | 3.44 | 3.76 |
| 8 | 3.72 | 3.43 | **3.36** | 3.76 |
| 25 (all) | 3.71 | 3.42 | **3.36** | 3.76 |

- **Result:** 3.36 h against 4.01 h, so the tail is 0.65 h shorter. Net worth is unchanged at about 246k: undeploying an upgraded machine returns its pack to Inventory, and it sells at the full price (`undeploy` refunds packs).
- **Power is what makes it work.** At the old pw6/3 level, 8 or more packs give 3.71 h and 49 s of brownout. The base starves (12 Mk II generators draw 35 W each). 10 solar + 5 batteries is the best level. 12/6 is worse, because the extra buildings take generator slots.
- **Packs beyond about 8 add nothing:** the credits run out, and the plan has fewer than 25 generators.
- **Sim artifact fixed:** a full Inventory (rover ore) made the solar swap fail (`undeploy ... inventory_full`). The policy now frees a stack and retries.
- **Not automated in game:** no script call applies an upgrade pack. Only the UI command `inventory.applyUpgradePack` does. `solar.py` could buy the packs and raise its power targets, but the player applies the packs. This is not built yet.

### Charging Station sold while the Pioneer is away (not adopted)

Plan option `stationAway` (radius in m, `--suite away`): the station is sold while the Pioneer is farther than the radius from home and bought back when it returns, so its slot holds a generator. On the best plan above it saves 0.07 h (3.36 h to 3.29 h at 5 m; 3.35 h at 20 m). Not adopted: the gain is about 2 %, and vehicle scripts look up the station only at start (`no charging station at home`), so a restart while it is sold leaves them without a home.

## Script bug found: Inventory fills up and blocks Pioneer gear

Rovers fill the base Inventory with iron ore and ingots. After that, Shop buys of the Pioneer gear (Battery Holder, Portable Battery) fail with `inventory_full`, and the Pioneer never gets ready. Ore and ingots can't be sold (`invalid_request`). The policy now frees one stack when a buy fails this way: it sells the stack, or drops it when the item can't be sold. Then it retries. `lib/early_buyer.py` (`top_up_rover_gear`, `free_material_stack`, §2m) does the same for Rover gear: it clears the largest ore (else ingot) item, sold or dropped, and retries. Pioneer parts go through the commission queue.

`solar.py`'s `STAGES` play the feeders2.2 plan (pw6/3) once Ship Computer is researched; `lib/early_buyer.py` continues it from 70k TP.

## Search method and termination

- **Plain enumeration is enough.** A run goes at 100–200× real time and starts in about 1 s. A full plan to 150k takes 1–2 minutes of wall time on one core.
- **Runs:** each run starts at below-normal priority, so the desktop stays responsive.
- **Beam search** pays off only for finer decision spaces, such as per-purchase timing or mixed allocations. Its node evaluation would fork the sim state (`Sim.serialize()`/`load()`).
- **Termination per run:**
  - Goal: TP ≥ 150k and the Pioneer ready.
  - Time cap: `--hours`; a plan that doesn't finish counts as failed.
  - The crash list and brownout seconds are reported with each run.
- **Termination for openings:** every opening is followed by the same plan, so openings can be compared at a fixed horizon (for example 1 h: TP and credits) instead of run to 150k.
- **Next-level pruning, not built:** branch and bound with an admissible bound (all free slots filled with the best current-slope generator, unlimited power); drop branches more than 15 % behind the leader at fixed checkpoints.

## Open questions and next experiments

1. **Sell the Bio-Loop when the tail starts.** Its income stops at about 2.75 h, so its 3 slots could hold generators in the tail. Estimate: −0.4 h with no net-worth loss.
2. **Pressure Mk II packs in the tail.** In the best plan, pressure passes 1.2 kPa (Mk II unlock) at about 2.8 h, with about 7k TP still to go, and about 170k credits sit unused. A pack costs 12,000 cr and gives 5× output in the same slot, at 5× power. Test it with more solar.
3. **Power 7/4 with the Bio-Loop kept.**
4. **Robustness:** rerun the top plans from other checkpoints and seeds (weather). The Harvester field is done: over 10 fields the feeders2.2 plan reaches 150k TP in 3.98–4.05 h ([scoring_map_seeds.md](../plans/scoring_map_seeds.md)).

## Reproduce

```
python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h2.json            # macro suite
python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h1.json --suite opening
python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h2.json --suite feeders
python devtools/buildorder_search.py --save devtools/headless/.cache/checkpoints/early_h2.json --suite mk2
```

The checkpoints are copies of a throwaway save's history snapshots (`save_<id>.hN.json`). They hold private save data, so they stay in the gitignored `.cache/` and are not in this repo. Each run writes `plan.json`, `metrics.jsonl`, `console.log` and `summary.json` under `--out`.
