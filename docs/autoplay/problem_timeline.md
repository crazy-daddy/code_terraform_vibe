# Problem timeline of the first playthrough (from repo history)

Step 0 of [save_database.md](../plans/save_database.md). Sources: all 572 commits on `main` (2026-09-13 to
2026-10-06), [DESIGN_HISTORY.md](../DESIGN_HISTORY.md), `TODO_done.md`. Commit refs are short hashes.

How to read it:
- **Phase** follows [manual_walkthrough.md](manual_walkthrough.md). It is inferred from what a commit talks
  about, not from its date: the first run went slowly, with optimization rounds before each new phase (owner),
  and the repo only became the dev root on 2026-09-22. So the order is reliable, durations are not.
- **Kind**: **P** = a planner question (what to build, where, how many, when to retire); **S** = a machine
  script bug or tuning, listed only when it shaped a planner rule. Pure script fixes are left out.
- A fix taken in the first run is one candidate, not the answer (owner is a baseline, not an oracle).

## Phase 0-1: cold boot, H1 mining (0 to 100k TP)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Night brownouts; which loads shed first | P | Tiers: terraforming sheds first, production kept; battery shortfall advisor | ca4e7fe, TODO_done Phase 1 |
| Opening build order is slow | P | Headless search: heat 12 > O2 10 > pressure 0.3 reaches 150k TP in 4.1 h vs 7.7 h | f66e0ca |
| Vehicles lose their mission on reload, detour home to top off | S | Missions persisted, top-off only near home | d0f7158 |

## Phase 2: Pioneers, steam, H2/H3 (100k to 150k)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Pioneer stuck on blueprints it has no material for | P | Defer jobs lacking material; later: stock construction items at the builder's home before queuing | f77db18, cd1d4f3, b57f838 |
| Thermal Cap feeds a tank at another outpost with no pipe; overpressure | P | Same-outpost tank first, rebalance only at 0.98 full | 5caad58, 1348dbf, DH §1b |
| Inventory fills (60 slots) | P | Warehouses at home from the start | 5caad58 |
| Only one recipe demanded leaves extra Smelters/Fabs idle; one grabs all stock | S | Pile-on, prefill window | DH §2a-0-2 |

## Phase 3: water, first outposts (150k to 180k)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Water is the bottleneck | P | Steam Condensers on surplus steam | 5547ee7 |
| A full water tank stops the pump, and with it salt | P | Waste Processor drains water at 90 % to 60 % | 6f8ae6c, 0c2d29e |
| Up to 5 small tanks per fluid per outpost | P | Swap to one Large Liquid Tank (`bulk_liquid_reservoir`; `large_liquid_tank` is no type id) | 4d80c5c, 9eee6bb |
| Far outposts starve: pull hauler goes nearest-first | S | Score trips by units per metre | 19d8e0e |

## Phase 4: drones, biomass (180k to 330k)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Drones load only at drills/Depots: outpost stock never comes home, Seed Maker starves | P | Depot staging at every item outpost (now a founding rule) | 8f6837c, DH §10 |
| Production overshoots (dock loads, cargo aboard, peer Fabricators) and fills Inventory | S | Net all pipelines | 78d3b0e, 6c71c99 |
| Warehouse 2:1 swap drains block for tens of game minutes; the empty new one fills during the pause | P | Own Automation, greedy drain; owner now: build Large only once researched | d9e7fc7 |
| Bio chain floods Warehouse slots with raw specimens, deadlocks | S | Lab gated on processor idle (structural) | DH §1e/§1f |
| Biomass pillar done (250k t): Liquifiers and Mixer only burn power and life forms | P | Retire the essence chain, sell kits | 9eb3ee7 |
| Surplus life forms after that: destroyed by a Waste Processor, then reversed because they are wildlife feed | P | Keep them, refill buffers | 9eb3ee7, 98ad5d0 |

## Phase 5: oil, Plants Mk I (Plants 0 to 1.25M)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Banked steam can't cover a deficit (turbines rate-limited): brownout with 35 kt steam | P | Oil Generator starts on low battery | a55bdd3 |
| Oil tanks full, pumps stalled, grid in deficit; then base load drained tanks in hours | P | Burn measured oil inflow, steer to 80 % fill | 60af701, ea9b316 |
| One Harvester can't hand-care 15 species (~38 h/day) | P | Starter layout, then Crop Automators (Shop-only kits) | 9e0f85c, 5b64729 |
| Machine deploys queued behind care never ran | P | Deploy step ahead of care | 5b64729 |
| Forage clogs Crop Automators and their auto-loaders | S | Drain order: stored Forage, clogged automators, garden first | c74a805, 151387f, 497130c |
| Dispensers burn 48 salt/day vs 1 per hand-cared cell | P | No field machines in the garden | 774a834 |
| Plant Terraformer Mk II draws 900 W while blocked; partial batches burn Accelerant | P | Enable only with a full batch staged | 0faebf7, 1b04510 |
| Mk II Terraformers idle: nothing crafted Fertilizer | P | Standing orders on idle Fabricator time | 0fabc7b |
| Field short of Terraformer Forage demand | P | Yield Amplifier | 4da0bc2 |

## Phase 5-6: factory outposts and the script budget
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Home slots full: smelting and fabrication move to outposts | P | Remote Smelters/Fabs, per-site order trees, docks anywhere | a942900, 686d880, 76978f3 |
| Outpost crafted tar with 15k at home; valves stalled on glass no Smelter made | P | Ship spare stock before crafting | 3f012dc |
| Home kept pulling ore after its Smelters moved away | P | Home planned like any outpost; stranded ore evicted | e02665a, 12241b2, DH §2i-1 |
| Kits built at a remote Fabricator stay there, but deploy takes kits from home Inventory only | P | Haul kits home, count them in transit | e845bfd |
| Builder homed at an outpost never gets its blueprint material | P | Consume at the Constructor's home | 78505d8, 1ba3097 |
| Fabricators wait on just-in-time smelts | P | Ingot buffer per fab site (2000) | e987975 |
| Forage grows only at home: remote fab sites never get it | P | Raw-input stockpile requests | 708c5dd |
| Warehouses for stock use building slots at fab sites | P | Counted in the slot budget | b94a28d |
| A dock at a site without a Fabricator holds crafted orders forever | P | Docks pick orders by site role | db8092e |
| ~150-160 running scripts: everything feels behind | P | Script cost model; park idle machines, drills scriptless, solar off at night, turbine commitment | DH §12, d504308, a6e67b4, 4417aa0 |
| Control-room pass (~1600 ticks) outlasts the battery on a deficit | P | Grid supervision between storage sub-steps; Automations survive brownouts | ea9b316, 518f146 |
| Drones haul most freight: surplus Pioneers | P | Retire button | f3c91da |
| Machines built before their grid had power stay dark | P | Stray scan powers them | 693d264 |

## Phase 6: wildlife (Plants 2.25M, Wildlife 0 to 5M)
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| All Habitats at home within the 31-slot cap (Forage is home-only) | P | Home reserved for wildlife | f717904, b218fb8 |
| Exotic supply short: all Habitats pull, every buffer drops out of band | P | Ration slowest colonies first | 8f06ab9 |
| Exotic caps cycle in under a minute; parking lost active windows | S | Keep valve open, park only long dormancy | 5cdefd1 |
| Blocked colony reports 0 feed demand and is never fed | S | Model rate fallback | 2c2ae87 |
| Feed recipe switch ejects 100 Forage (~40 game min) | S | Switch with stockpile loaded | 7587322 |
| 4 Feed Makers chased a 49-feed shortfall | P | Max 2 makers per recipe | f174f45 |
| Tar ran dry, all Refiners stopped | P | Craft tar for Refiner outposts | c08b16a |
| Six tar Fabricators outdraw the oil wells: reservoir dry, fluid networks rebuilt every tick | P | Pause fluid-only recipes below 5 % fill | 62ed82d |
| Remote Refiner output stalls through the shared pipe pool | P | Own-outpost tanks first; storage needs split networks | 41d6152, 994c011 |
| Habitat done after its Breakthrough; pillar done at 5M | P | Release Habitats; retire Habitats, Feed Makers, Refiners, exotic tanks/caps; sell kits (Mk II packs not sellable) | 6c4cb57, 25ef978, 8429da0, 34d7a6b |

## Phase 7: nuclear and the atmosphere finish
| Problem | Kind | Fix taken | Ref |
|---|---|---|---|
| Raw Uranium comes only from dust-storm aftermaths | P | Weather Stations decode coordinates; plated drones collect (1.5x fuel, half cargo); Lead Cask room reserved | 42d5ef6, 7413628, b1ee3f8, 1e5433e |
| Lightning rods: 250-500 W for 4 rods, need batteries held at 0 | P | Rejected, went nuclear | 8a8f245, DH §1 |
| Reactor cooling water competes with other consumers | P | Water reserve per Reactor | e8afd09 |
| Rod shortage | P | Rod reserve at docks, alerts | 94c89a3 |
| Selling turbines dropped the save's tier and redeployed the night guard | P | Phase from the generator mix, not building counts | 5eed27b, DH §9 |
| Mk III pack applied under a running script leaves ports unbound | S | Restart the script after an upgrade | 1f1efe4 |
| O2 caps last (~555 game days); Mk III spam costs scripts; Mk IV needs rods | P | Open (atmosphere build-out tiers in TODO) | 1b465d2 |

## Decision points for the planner
Planner questions the first run met, in order. Each is a place a save should exist, so the planner's choice can be
compared with the one taken.
1. Opening order of atmosphere machines (P0-1).
2. Batteries vs night deficit; which loads shed (P0-1).
3. Home Warehouses before Inventory fills (P2).
4. Tank placement next to its producer, same outpost (P2-3).
5. Water source mix (pumps vs condensers) and a drain so pumps keep making salt (P3).
6. Depot at every item outpost (P4; now a rule).
7. Storage type: Large Warehouse once researched instead of swaps (P4; decided).
8. Retire the biomass chain at 250k t, but keep the life-form flow for wildlife (P4 to P6).
9. When hand care gives way to Crop Automators; no Dispensers in the garden (P5).
10. Generator mix: oil as last resort or base load, against oil supply (P5).
11. Deploy a machine together with its supply chain (Fertilizer, tar, Forage, kits at home) (P5-6).
12. Move Smelters/Fabs off home: move their stock, demand and buffers with them (P5-6).
13. Retire surplus Pioneers once drones haul (P5-6).
14. Running-script count: what earns a running script (P5-6 onward).
15. Feed Makers and Refiners sized to demand and to the oil/tar supply (P6).
16. Retire at pillar completion: biomass, plants, wildlife, exotics (P4, P6, P7).
17. Uranium chain before Reactors and Mk IV: Weather Stations, plated drones, Lead Casks (P7).
18. Mk III vs Mk IV atmosphere, scripts vs rods (P7).
19. Deploy only on a powered grid with pipes in place (all phases).

## What this means for the saves
- Commits cluster from 2026-09-29 to 2026-10-03 (about 330 of 572): factory outposts, the script budget, wildlife
  and nuclear prep. Most planner decisions (10 to 18) sit there, so that stretch needs the densest saves.
- Phases 0-3 changed the planner little and the headless early-game runs already cover them; one save at each
  phase start is enough.
- Missing in history, so watch for it in the playthrough: when to found each outpost (founding was done by hand
  and left no commits) and how many Smelters/Fabricators a phase needed.
