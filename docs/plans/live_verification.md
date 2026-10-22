# Live verification run from a new seed

Written 2026-10-22. One manual run that checks the plans whose code is merged and that only wait for a live run:

| Plan | Code state | Checked in |
|---|---|---|
| [outpost_founding_planner.md](outpost_founding_planner.md), revision 3 phases 1 and 2 ([impl](founding_rev3_phase2_impl.md)) | Merged `b06144a` | [§3](#3-early-game-founding-planner-revision-3), [§4](#4-mid-game-constructor-base-and-roles), [§5](#5-late-game-drone-takeover) |
| [resource_markers_removal.md](resource_markers_removal.md) | Sessions 0-2 done | [§2](#2-early-game-before-cartography-markers-removal) |
| [dynamic_roles/](dynamic_roles/README.md), stages 1-3 and mission pool A/B | Merged, headless only | [§4](#4-mid-game-constructor-base-and-roles), [§5](#5-late-game-drone-takeover) |

Markers used below:

- 🛑 **Pause and call Claude**: stop playing at this point and start a live debug session (the `code-terraform` MCP `debug_*` tools). The game keeps running; Claude attaches with log breakpoints.
- 📝 **Record**: note it in the decision recorder (see [Recording deviations](#recording-deviations)).

## 0. Setup

- [ ] Deploy with `--include-autoplay`. Without it, the planner does not run and none of the planner checks below apply.
- [ ] Start the new game **first**, then restart the MCP (`/mcp` reconnect or a new Claude session). `run-mcp.mjs` binds to the newest save workspace at launch; without a restart, a debug session attaches to the old save.
- [ ] Delete the deployed `harvesting/sync_resource_markers.py` from the save by hand. Its source is gone, but the save keeps the deployed copy.
- [ ] Start the decision recorder (`python devtools/play/decision_recorder.py`). Consider `--copy-every 10` for this run (default 30 minutes).
- [ ] Note the commit hash and the seed. The run is compared with the recorded runs in [planner_rev2_results.md](planner_rev2_results.md).

## 1. Any time: script errors

- [ ] A script stops with `ImportError: cannot import name ...` (the test save showed it in `drone_8.py`).
  - 🛑 Call Claude **before** restarting anything. Likely cause: an importer was applied before the library it imports from ([live_debugging.md](../cheatsheet/live_debugging.md), apply order). A later apply does not revive the stopped script. Claude compares `libs_awaiting_apply()` and the deployed source with the saved source.

## 2. Early game, before Cartography: markers removal

- [ ] A stationed Pioneer mines iron on the first NEED.
- [ ] `mining.active_ores` grows in the order iron, silicon, titanium.
- [ ] An ore that is not latched yet gets no STOCK floor. Full slots get no buffer.
- [ ] No `resource.` archive markers appear.
- [ ] Dock raw-ore orders are still covered by a mining outpost's dock.

## 3. Early game: founding planner revision 3

- [ ] The first outpost gets the `charging` role and a Charging Station while drone yield is off.
- [ ] **Geothermal scouting** (least tested part, never run live): `geo-<n>` survey requests appear while the Thermal Cap is still locked. Expect 2, nearest home, at least 600 m apart.
- [ ] A discovered but unsurveyed vent creates a `power` need that asks for the survey first (`survey: True`).
- [ ] **Second factory outpost proposal**: it leaves the first outpost's cluster, but only once outpost_1's Charging Station stands. In the replay, without the station it stayed west at every weight tried.
  - 🛑 Call Claude **before approving** the proposal. Claude sets a breakpoint in the planner's ranking and reads the `reach_gain` and `future` terms against `ctx["starts"]`. The replay result came from a scratch probe, not from `planner_replay.py`, so this is the first real check of `WEIGHTS_EARLY["reach_gain"]` = 9.
  - 📝 Record the score breakdown and the site with `/w`, even when they look right.

## 4. Mid game: constructor base and roles

- [ ] Commission a builder from the card with `HOME_BASE` set to another outpost. On start, `_restore_constructor_base` moves its base to home; the FLEET card `base` reads home.
- [ ] A miner refits to builder: it drives home and takes its stock from home.
  - 🛑 Call Claude when the **first refit starts** (watch the Roles tab). Claude attaches to that Pioneer's script without stopping it (`debug_start` without `runIfIdle`) and logs the refit and base change. Nothing needs to be stopped.
- [ ] With 2 or more builders, both draw their stock at home.
- [ ] Roles tab, Queue view: entries show ages and holders. A refit takes the oldest entry within a band.
- [ ] When a miner leaves an outpost, check whether a probe miner comes back about once per `REFIT_COOLDOWN_TICKS` (known bound from stale reach).
  - 📝 Record the outpost.

## 5. Late game: drone takeover

First live run of the drones-haul mode.

- [ ] Every outpost with the `drone_depot` role has a depot and 3 hauler drones **fly** (queued ones don't count). Autoplay then turns drone yield on itself, logs it once and never turns it off.
  - 🛑 Call Claude just **before the third hauler drone launches**. Claude watches `drone_takeover()` and `charging_retire_ready()` flip.
- [ ] Pioneer haulers are sold down to `SALT_PIONEER_HAULERS`. Only after that does the BUILD card show station removal rows.
- [ ] These Charging Stations stay:
  - home, while builders live there;
  - the salt keeper within 300 m of home;
  - any outpost that still has Pioneer miners and already holds a station.
- [ ] Once drills have replaced an outpost's Pioneer miners, its removal row appears.
- [ ] The obsolete scout is sold once both salt haulers exist and the survey is complete. Blocked POIs and POIs out of reach count as surveyed.

## Recording deviations

The decision recorder already keeps the console lines (`console.jsonl.gz`, error text included) and stamps every note with wall time, game time and commit.

| Command | Use for | Save copy |
|---|---|---|
| `/n <text>` | A plain observation or deviation | None; the newest copy can be up to `--copy-every` minutes old |
| `/w <text>` | A deviation whose exact state Claude needs, e.g. a planner proposal to replay | Yes, when the newest change entry is minor (major entries already have one). Check `/l` first: `/w` attaches to the newest change entry, which may be unrelated |

For every deviation, write: outpost id, the card and row involved, and whether the script was already in `error`. Claude replays the planner against a save, not against a description.

## When to call Claude

- **Wrong decisions while scripts keep running**: call Claude for a live debug session. Claude attaches with log breakpoints and the game keeps going.
- **Crashes and errors**: don't wait. Record the error with `/w` and go on. Attaching to a script in `error` gains nothing.
