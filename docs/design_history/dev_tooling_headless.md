# Design History: Dev Tooling, Profiling & Headless

Why behind tick-cost profiling, logging, live debug, tiered scripts and headless stand-ins (cheatsheet §0, §0a, §1d, §8-§10, §12). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

## §1d — Per-Script Tick-Cost Profiling: Thermal Cap Case Study

Two profiling passes each found a real, *sustained* per-step cost with no periodic spike at the
discovery-cache/rescan intervals, which correctly pointed at genuine bugs — see §1b above for what
they were and how they were fixed (both verified via stub tests confirming the call counts dropped
to zero/near-zero). A third pass still showed Thermal Cap reading ~2-3 against Turbine's ~0 with
nothing left in either script's own code to explain the gap — at that point the signal had reached
the profiler's own noise floor (ambient cooperative-scheduling jitter, or a fixed engine-side cost
of that specific component's own methods, neither fixable from script code) and further chasing it
stopped being productive.

That's the profiler's actual working mode and its limit: it can't measure a single call's cost
directly (see the cheatsheet's granularity-limit note on why a `0` doesn't mean "cheap"), and a
*sustained per-step* delta with no periodicity matching a known cache/interval constant is a
reliable signal worth grep-ing for once or twice — not an oracle to keep re-running against the
same script once every explanation in its own code has been exhausted.

Instrumentation was added to `lib/thermal_cap.py` and `lib/steam_turbine.py` for this
investigation, then deliberately removed again from both once it stopped yielding actionable
findings — `lib/profiling.py` itself is kept for any future script suspected of doing real bulk
per-call work.

---

## §8 — Live-Debug Bridge: How the Command Channel and Library Caching Were Established

The general external-command channel was found (2026-09-22) from a real stale request left in `command.json` by earlier tool use, not reverse-engineered blind. Sending `"action":"run"` for `rover_1.py` force-restarted the running script (fresh startup, tick counter reset). The same session showed that restarting `rover_1.py` after syncing a new `lib/vehicle_mining.py` still ran the stale cached module. Every relevant VS Code command was then tried against the changed library file (Run Script in Game → `context`, Create Library in Game → `file_exists`, Import File as Game Library → `duplicate_name`, Rename Library and Update Imports → `no_change`); each failed for a semantically correct reason, never "not found", ruling out a hidden apply command. `scripts_sync.py --auto`'s launch retry exists because a freshly re-filled `drone_2.py` failed an immediate launch and succeeded after a short wait. Library registration via `create-library` was confirmed 2026-09-24 (`drone_upgrade`, `fleet_upgrade` → `{"ok": true}`).

---

## §9 — Tiered `scripts/` Migration

pre-restructure codebase written/tested against save with 60 techs unlocked (incl. `data_archive_unlock`, `custom_panels_unlock`) → moved wholesale into `4_controlpanel/` as honest home tier (one-off `devtools/_migrate_from_root.py`, removed; in git since `dc37c01`), not guessed apart per file. `0_cold_boot`/`1_early` seeded separately from former `early_game_runner/` submodule's ([code-terraform-earlygame-automation](https://github.com/crazy-daddy/code-terraform-earlygame-automation)) `early_game_runner/templates/` (flat) and `early_game_runner/templates/early/` (richer) boilerplate. That submodule = this project's own earlier `code-terraform-earlygame-automation` prototype, not `inspirations/vakermit`. Flat `early_game_runner/templates/*.py` = thin `from <lib_module> import ...` wrappers around project's own `lib/` controllers (`terraforming.py`, `solar.py`, `smelter.py`, ...), need `research_shared_library` → wrongly copied into `0_cold_boot` in initial seeding. Only `early_game_runner/templates/early/` genuinely self-contained (no `lib/`/game-module imports), belongs at `0_cold_boot`/`1_early`. `0_cold_boot/power/solar.py` = hand-trimmed exception: `early_game_runner/templates/early/solar.py` bundles full Ship-Computer building-buyer speedrunner around tracking loop, so cold-boot gets few-line sun-tracking-only script extracted from it. `fabricator`, unified `pioneer` (destination-routing, distinct from `pioneer_scout`), `steam_turbine`, `thermal_cap`, `water_pump` have no self-contained early equivalent yet → removed from `0_cold_boot` rather than left broken. They resolve once save reaches tier defining them (currently `4_controlpanel`). Splitting rest of `4_controlpanel` into earlier-tier-capable content = manual follow-up (see TODO.md), not automatic.


**Collapsed to two tiers (2026-10-04).** An audit of `scripts/` found that only 16 files were ever replaced by a higher tier, and 14 of those swaps happened at or before `4_controlpanel`. Tiers 5–10 held almost only new files. Those were already deployed early (`lib_chain()`), or they matched a slot only once their machine existed, so their `.criteria` gates added nothing. `2_libunlock`/`3_archiveunlock` were empty markers. `1_early` needed no gate of its own either: its Solar buyer guards `computer` behind `research_computer` itself, and `shop`/`research` exist from the start. Result:
- `0_cold_boot` (self-contained, no `lib/`) + `4_controlpanel` (full stack). `LIB_UNLOCK_TIER_NUMBER = 4`.
- The tier-1 Solar buyer replaced the tracking-only cold-boot Solar. The Pioneer Scout became `0_cold_boot/pioneer/pioneer.py`, so pioneer slots match before tier 4. The `mount_vehicle.py` step moved inline into the early Rover/Pioneer scripts, because scripts_sync has no separate mount pass.
- The planting Harvester (`field_keeper.py`) became the only tier-4 Harvester: before Seed Makers it degrades to the loose-item sweep.
- The two Power Guards (tier-4 night forecast, tier-5 combined reserve) were the one real fork. They merged into one `lib/power.py` that picks its strategy per grid from the generator mix (`grid_phase()`: solar / steam / oil / reactor; cheatsheet §1a). The deciding point: what a grid needs depends on its generators, not on how far the save has progressed, and a save can have a solar-only grid next to a steam grid. The reactor phase only stops oil *surplus* burning. Idle Oil Generators already park themselves through `script_parking`, so no extra park mode was needed.

---

## §12 — Script Cost Scales With Running-Script Count (2026-09-30)

Machines felt "behind" (Harvester, Smelter, Fabricator; Supply Docks joining completed orders). A
performance pass cut per-poll work: building discovery memoized for 2 s (`production`, `storage`,
`drone_energy`, `vehicle_energy`), one `SourceCache` per Fabricator step, Harvester geometry/per-step
caches and a route search that stops at the first reached target, Pressure Generators sleeping until
their sync window, slower polls for solar/pumps/turbines/thermal caps/oil generators/Crop Automators,
nearest-station-first arbitration for Drone Service and Charging Stations, and the dock plan published
on its own 5 s timer (Docks also re-check a planned order is still active).

The measurements behind it (docs/BENCHMARK.md) first looked like one interpreter budget shared by the
awake scripts, which argued for slower polls everywhere. Further runs disproved that: stopping all 8
Control Room cards (always awake) changed nothing beyond their count, and stopping 19 solar trackers that
sleep 10 s at a time helped exactly as much as their count predicts. The decompiled scheduler confirmed the rule: each script gets
`min(1000, floor(50000 / N))` steps per tick, N counting running and sleeping scripts, so up to 50 scripts
run at full speed and beyond that a fixed 50,000 steps per tick are split evenly. The Smelter/Fabricator active poll therefore went back to 1 s: a faster poll costs
only the script itself.

A rewrite with centralized control was considered and rejected: the slowness was pacing and
recomputation, not structure, and *self only* setpoints (`set_tilt`, `set_throttle`, ...) reset to idle
whenever a script ends or is stopped (measured on a solar panel), so machine scripts cannot be replaced by
one central script. The remaining levers are fewer running scripts (retire machines that don't earn their
share, merge Control Room cards, start scripts only while their machine has work) and computing shared
results once centrally; both are in TODO.md.

## §0 — Mixin Self-Typing: `_host` Over Fake Base or Protocol (2026-09-22)

Mixins (vehicle, drone, pioneer, harvester, ...) need `self` typed as the composed controller for Pyright.

- **Fake base, rejected**: `_Base = VehicleController if TYPE_CHECKING else object`, then `class VehicleSurveyMixin(_Base)`. Checking one mixin file alone showed only a harmless "dead code" hint, so it was rolled out to all 11 mixins. A full-repo `npx pyright` then reported "Class cannot derive from itself" on every base of `class VehicleController(...)` in `lib/vehicle.py` (same for `lib/drone.py`): each mixin's type-only base is the composed class itself, a real cycle that only shows at the composition site. Fully reverted.
- **Protocol, not built**: a `VehicleControllerLike(Protocol)` with the whole cross-mixin surface, used as a per-method `self:` annotation. It worked in a scratchpad test, but needed the full attribute surface of all mixins and an annotation on every method.
- **Chosen**: one `_host` property per mixin returning `self` typed as the controller (one `# type: ignore[return-value]`), with methods going through `self._host`. A full Pyright pass at `lib/vehicle.py` showed 0 errors, 0 warnings.
- **Lesson**: a single-file diagnostics check is not evidence that a typing pattern is safe for a multi-file composition. Verify at the composition site before rolling a pattern out.

## §0a — TreeConsole Wrapped Blocks: Decorator, Opt-In (2026-10-05)

Adapted from zroski's newer `RConsole.block` / `run` (`inspirations/discord-ideas/zroski.txt`), the same
author's console that TreeConsole grew from.

- **Why**: 249 `log.start()` calls need 612 `log.end()` calls, mostly an `end()` before every early `return`.
  A wrapper closes the block on every exit. An exception escaping a manual block also left the header with no
  END line until `reset_all()`; the wrapper writes `END <name> !! <Type>: <message>` instead, so the log
  shows the path the error took.
- **Opt-in, no mass migration**: most info blocks end with an outcome message (`end("3 orders placed")`)
  that a wrapper cannot know. The wrapper fits debug decision-trail blocks around a whole function.
- **`method_block` reads `self.log` at call time**: a class-level decorator cannot see the instance's
  `log`, so `@self.log.block` (RConsole's shape) is impossible for methods.
- **Not taken**: per-indent colors (one `log.color()` call in the codebase) and `pretty_format` dumps
  (CODE_GUIDES prefers aggregates; dumps fight the buffer cap).
- **Unverified in game at the time of writing**: no `lib/` used a custom decorator, `functools.wraps` or
  `__name__` live before. `drone_depot.flush_surplus` was the pilot: it ran every tick on all 7 Drone Depots of the main save without errors, so the
  same day it was rolled out to the 21 methods whose debug block had 5+ bare `end()` exits (208 lines removed).

## §9 — Lib Tier at the Data Archive (70k TP), Not the Control Room (2026-10-07)

The `4_controlpanel` tier used to wait for Custom Panels (150k TP). Everything the full `lib/` stack needs is unlocked by 70k: Shared Library (20k), Signal Bus (35k), Automations (50k), Data Archive (70k). Only the cards need the Control Room.

- **One version per machine**: the Charging Station, Rovers, scout Pioneer and Supply Dock all deploy after 70k under the `STAGES` build order (vehicles need pressure, which comes last; the Pioneer and Supply Dock need 100k/110k TP). With the switch at 70k they start on the tier-4 scripts, so their tier-0 stand-ins (rover, pioneer, charging station, supply dock) were deleted instead of kept in step with the libs.
- **Buyer in `control_room_automation.py`, not a second Automation**: the Automation already exists from the lib tier on, and grid supervision (PowerGridManager) is wanted from the start. An extra Automation would cost a running script for good. The buyer goes idle for good once the Control Room is researched.
- **Pioneer through the commission queue**: a tier-4 Pioneer only fits itself as a commissioned one (`LoadoutFittingMixin`), so the buyer queues a `scout` job instead of buying a bare chassis. It queues only a buildable spec: a blocked job can only be cancelled on the COMMISSION card, which comes at 150k.
- **Rovers fit themselves**: same mixin, fixed `ROVER_LOADOUT`; a kind counts as mounted at any tier.
- **Headless keeps up**: `run.mjs --lib-tier` makes the same switch in a fresh game (`library.create`, `automation.create`), so the build-order search still reaches 150k with a scouting Pioneer on the real scripts.

## §10b-1 — Fluid Network Rebuild Trap and `--sticky-fluids` (2026-10-05 to 2026-10-08)

**Up to build 3b1b03e** the fluid network analysis (`Ex()`, cached in `ux` under one signature string `gx()`) had a single key that held both the pipe geometry and every machine's fluid types and content flags. A tank running dry every tick therefore rebuilt everything, topology included, twice per tick. Measured on the owner's late save (887k TP, 274 machines), where `bulk_liquid_reservoir_9` (oil, outpost_4, 48 t/h in, ~48 t/h out, ~0.2 of 1,000 stored) ran dry every tick:
- 121 of 132 analysis calls missed the cache over 60 ticks (buffered: 13 of 131).
- FlowTransport 142 ms per tick against 13 ms buffered: 43 % of all simulation CPU, twice the cost of all 146 running scripts.
- Filled to 500 or 900 t by hand, the reservoir was empty again within minutes. A per-machine signature diff over 10 game minutes put 9,263 of 9,378 changes on that reservoir (drain: 6 Fabricators on `craft_tar` plus 5 Oil Generators against 5 Oil Pumps) and ~300 on item port rewiring.

Workarounds from that time: `run.mjs --sticky-fluids` patched the signature so headless runs stayed usable (every late-save run used it), the fluid-only recipe hysteresis in `lib/fabricator.py`, and the "keep tanks buffered" advice. The developer announced a fix on 2026-10-05.

**Build e1986ce** splits the key (fluids.md "Rebuild cost"): the topology is cached under `geometry`, without content flags. A forced flip now costs about 1 ms per tick (the 887k save state was no longer available, so the flip was forced on the mid-late sample save), and a natural late-save run differs by about 1 ms per tick with and without the flag. So runs no longer pass `--sticky-fluids`.

- **Kept, not removed**: the patch is small, feature-detected (it switches off with a warning when the pattern no longer matches), and still useful to reproduce older A/B numbers that were taken with it (event_driven_automation.md, headless_sim.md "Passive machines"), or on a future build that regresses.
- **Cost of keeping**: one signature pattern in `simhost.mjs` to maintain per game update. Remove it when that pattern breaks and nothing needs the old numbers.
- **Fluid-only recipe hysteresis kept, new reason**: the CPU reason is gone, but the pause still keeps a reserve for the consumers that never pause (Oil Generators on last resort, recipes with fluid plus items). Without it they share an empty tank with `craft_tar`. Throughput is unchanged, set by the supply.

## §1d-2v — Idle Vehicles Paused, Not Stopped (2026-10-11, game build v0.1.31)

v0.1.31 added `run_control.pause()` / `resume()`, which work on machines without a breaker. About 8 of 22 vehicles in the midlate sample save sat idle, each costing the scheduler like a busy script (§1d-1).

- **Pause, not stop.** A stopped vehicle script loses its in-memory job state (role, haul memory, construction lot) and restarts from the top. A paused one keeps its place, and a vehicle already in flight finishes that flight (measured headless: a drone paused mid-route docked at its Depot). Only a save load turns a resume into a restart.
- **Where a vehicle may wait.** A Pioneer waits only at its base, because the Charging Station there charges docked vehicles on its own. A drone waits hovering or at a drone_service, never in a Depot bay: drones leave bays between trips on purpose so peers can unload, and a paused drone in a bay would keep it. No charge gate, because hovering burns nothing and a woken drone refuels as usual.
- **Commands wake from the panel, not at their writers.** Recall, retirement, chassis upgrade and Sport Nav are written by several card and panel paths. Checking those five keys each pass in `ScriptParking` keeps every writer unchanged and also covers keys written by hand.
- **Work wakes compare keys, not amounts.** A paused hauler wakes for a new (outpost, item) request and a Constructor for a new job id. Growing amounts of an existing request do not wake it, so a request that is republished every pass cannot keep vehicles awake. The 3000-tick re-check catches the rest.

## §1d-1 — Logging Inside Atomic Calls (2026-10-11)

Wrapping a function in `run_atomic()` kept failing on logging: `console.print()` is a world change in the game's callback check (decompiled `validateNativeCall`, effect `mutation: world`), so any log line that reached the console inside the callback raised `RuntimeError`. Debug lines only buffer, but the shared buffer flushes on a level or channel change, the size cap or the end of an info block, so whether a call failed depended on what else had been logged. Pure planners worked around it by returning notes for the caller to log.

- **One choke point, not a second log object.** The pass-along log already exists: each controller builds one `TreeConsole` and hands it down, and every instance shares one module buffer. What was missing was a switch on the final write. `atomic.console_print()` is that switch: `TreeConsole` and `swallowed()` write through it, and it queues while a `run_atomic()` call is active. The queue is written right after the outermost call, also when it raises, so order across levels and modules holds.
- **Lives in `lib/atomic.py`.** It imports nothing, so `swallow` (which must not import `archive` or `tree_console`) can use it. `ATOMIC_ENABLED = False` turns queuing off with the runners.
- **Time of logging kept.** Queued info lines get the `console.now()` stamp (a plain read, allowed in callbacks) at queue time instead of `timestamp=True` at write time.
- **Not covered:** raw `map()`/`sorted(key=)`/`lru_cache` callbacks and `archive.transaction()` updaters do not set the flag. Existing pure planners that return notes (`pull_plan.pull_candidate()`, `drone_haul_plan`, `construction_plan`, `wildlife_planner`) keep that shape: it is testable, and nothing forces a change.

## §10b-2 — Headless Stand-In `scale`: One Record for N Terraformers (2026-10-14)

Phase 2 of the headless stand-ins ([docs/headless/standins.md](../headless/standins.md)). A focused run keeps one subsystem real; the terraformers of a mid or late save are dozens of identical Mk III machines whose scripts and per-machine system work cost ticks without telling the test anything.

- **Scale per record, not a global multiplier.** Each survivor carries `data.scale = N` and the simworker multiplies that machine's atmosphere output, fluid drain and power draw by it. A global factor would also scale the machines a scenario keeps real; a per-record field keeps mixed groups (members beyond `max`, refused undeploys, idle machines) exact.
- **Undeploy, never splice** (superseded by §10b-5: members are stopped now). The extra members leave through the game's own `machine.undeploy` (fluid network, power grid, retired-machine list and script slots are cleaned up by the game), with the refunded kits removed from the Inventory by a slot diff, so the scaled run keeps the real run's Inventory and net worth.
- **No gate patch.** The survivor keeps one running script (the Level-1 stand-in), so the game's `scriptSlots.some(running)` gate passes as it does for a real machine; the virtual script count takes the removed scripts as ghosts.
- **Stable-string anchors, all or none.** Five worker lines are patched by `SCALE_PATTERNS` (`anchors.mjs`), anchored on property names only (`.co2`, `.planet.temperature.heatUnits`, `.pressure`, `` `${…portType}_level` ``, `.data.tier ?? 1`), minified locals captured from the matched line. A pattern that does not match exactly once switches the whole feature off and the mode falls back to `standin`: a half-scaled worker (output ×N, drain ×1) would pass a test with the wrong fluid balance.
- **`perRecord` against port starvation.** A port has one declared target and its own buffer and flow cap, so one record draining N machines' worth can run its port dry while N real machines would not. Groups split into records of at most `perRecord` (10); `minLevel` and a 6,000-tick stall warning in the summary show whether the split held.

## §10b-3 — Headless Stand-In `mover`: Pickups Emulation, Not a Fleet Model (2026-10-14)

Phase 3 of the headless stand-ins ([docs/headless/standins.md](../headless/standins.md)). With the hauler fleet stopped, something has to serve `logistics.requests`, or every requester (seed maker, reagents, salt, site supply) starves and the run tells nothing about its target.

- **Serve the key the requesters already write, in their own units.** The mover reads the request ladders, computes the deficit from the live store count and takes from the nearest outpost's surplus over its own level at that band. It never reads an entry's `have`: requesters republish on a ladder change or after `REPUBLISH_TICKS`, not on stock changes, so `have` lags up to 3,000 ticks.
- **One world through `logistics.pickups`.** Each trip is a pickup entry in the exact `reserve_pickup()` shape under the vehicle name `standin_mover`, deleted on arrival. `in_flight()` then caps the requesters' over-asking and the real orchestrator (demand record, commission, site supply) sees the same bookkeeping as with Pioneers. The reverse, a private queue, would double-serve: the requester keeps asking until the items land. Other vehicles' entries are read (in flight, reserved from a source) and never touched.
- **No fleet heartbeat.** `drone_haulers_present()` looks for a fresh hauler drone in `fleet.status`; stopped drones stop publishing, so requesters fall back to the ground-hauler source rules by themselves within `HAULER_FRESH_TICKS`. `drone.mission`, `drone.heli_free` and `depot.stage` have drone and Depot readers only, which are stopped too.
- **Upper bound, never a fleet model.** Items leave at once and land after load time plus straight-line travel; no cargo capacity, charge, weather or queueing at a dock. A test that needs the fleet's real throughput keeps logistics real; never size a fleet from a `mover` run.

## §10b-4 — Headless Stand-In `produce` / `cash` and `off` Stubs: Stated Rates, Fresh Keys (2026-10-14)

Phase 4 of the headless stand-ins ([docs/headless/standins.md](../headless/standins.md)): the plants group as a producer, and the keys an `off` orchestrator, wildlife or biomass group leaves behind.

- **Rates are stated, not learned.** The plan had `produce` default to the save's harvest telemetry; the lib publishes `harvest_yield` (Forage per harvest, `plant.automators`) and nothing about cadence, so any per-hour figure would be a guess dressed as a measurement. The scenario states `forage_h` / `rates` and the start line prints them, so a run's input is visible in its log.
- **`cash` writes the field the lib reads.** `commander.get_credits()` returns `player.credits` in the worker's component table, the same field `run.mjs` reports, so a credits stand-in needs no archive key and no shop command. Whole credits per pass, fraction carried, like a `rate_h` flow.
- **A stub says "nothing", a stale record lies.** An `off` group's scripts stop publishing, and some readers keep acting on the last record: a shed list keeps machines paused, a wildlife plan keeps a forage reserve, a `cash.budget` older than `MANAGER_STALE_TICKS` makes every capital `can_spend()` keep `LEGACY_RESERVE` (100,000 cr). Each stub is the value the readers treat as "no manager here" (verified reader by reader before it was written), and `cash.budget` is refreshed every pass because its freshness is the signal. Consumers' asks and holds in it are kept until they age out as `_prune()` does: wiping them every pass would let two consumers spend the same credits.
- **A seed wins over a stub.** A key named in the scenario's `archive` section is the operator's fixed input; the stub never touches it, so a test can pin a shed list or a budget and still have the group off.

## §10b-5 — Headless `scale` Stops Members Instead of Undeploying (2026-10-15)

The headless tool is meant for any player's script set ([docs/headless/standins.md](../headless/standins.md)), so a stand-in must not lean on how this repo plays. §10b-2 undeployed the extra members of a `scale` group. That freed their building slots, and the worker counts buildings live from `state.machines`: `buildings_used()`, `is_full()`, the OutpostRef fields and the overcrowding factor all changed. On a full outpost, a script that fills free slots saw room and built. On an overcrowded outpost (the cap is soft: −10 % per building over it, floor 20 %), every `throughput` machine there ran better than in a full run, the heaters' heat output included. This repo never overcrowds and its slot fillers (`early_buyer`, `solar.py`) only run at home before the Control Room, so the 1631 A/B rows were not affected. Another player's runs would have been.

- **Stop, don't undeploy.** The worker gates a terraformer's output, fluid drain (`z7` runs after the gate) and power draw on a running script in its slots, so a member with a stopped script does nothing. It stays deployed: same building slot, same id in `outpost.buildings()`, same component, same overcrowding count. The survivor's `data.scale = N` still does the N machines' work. The CPU saving barely changes: the stopped scripts were the cost, and a stopped member's system loops end at the gate.
- **Not a counter patch.** A first fix (2ec8f8f) kept the undeploy and patched the worker's two building counters to add `data.scale`. That fixed the counts but not `outpost.buildings()` or per-id reads: a script that keeps N machines by listing them saw fewer and rebuilt them. Stopping fixes every read at once and needs no extra anchors.
- **No lie about running.** Answering `run_control.is_running()` with true for a stopped member was considered and rejected. `stop`/`start`/`pause` would have to lie too, and the machine's own reads (power draw 0, frozen port levels, the missing heartbeat the sweep removes) would still contradict it. A supervisor that cross-checks would act on the contradiction. A member looks exactly like an `off` machine instead: honest, and a script set that restarts it shows up in `revived`.
- **What stays different is measured, not hidden.** Faking what a stopped machine's script writes (archive records, requests, signals) would mean rewriting that script with all its interactions, which is about as costly as running it. The engine-side view stays honest at no cost. The script-side differences show in the A/B rows, `revived`, `leftovers` and `sweepLive`.
- **Revival guard always on for members.** A revived member adds its output on top of the record that already counts it, so the guard stops it again even under `sweep: false`.
