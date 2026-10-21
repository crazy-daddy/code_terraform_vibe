# Design History: Control Room Panels & Autoplay

Why behind Control Room panels, headless workers and autoplay planners (cheatsheet §7, §11). Hub: [`../DESIGN_HISTORY.md`](../DESIGN_HISTORY.md).

## §7 — Control Room Panels: The Headless Split & Overlap Bugs

**Why the automation calculator had to become headless.** A single combined script (originally
`panel_1.py`) used to both draw the STATUS/AUTOMATION card *and* run all the automation itself
(grid supervision, rebalance sweep, outpost sync, `supply_dock.plan_dock_assignments()`). Found
live: `plan_dock_assignments()` running inside that same per-tick loop (even after §2a-1b's
`SourceCache` fix cut its cost to ~2s) wedged the card's own rendering outright — confirmed via
temporary debug prints that the script kept looping and completing fine underneath
(~100ms/iteration) the entire time the card stayed visually blank, with no exception anywhere.
There's no known threshold under which an occasional multi-second stall is safe for a script that
also renders every tick, and this game has no true background/daemon script type — a Custom Panel
is the only slot that can host an "always-on, not tied to one building" process — so the fix was
structural, not a further speedup: the calculator became headless
(`sleep(1.0)`-paced like every other controller's `run()`), publishing its result summary to
`archive` instead of drawing it directly. Everything the UI script draws (STATUS's clock/power/
storage/alerts, the version gate, the manual buttons) is a cheap single-call component read or a
rare user-triggered one-off, not the chronic per-cycle cost that forced the calculator headless, so
it stays inline in that UI script.

**Why the panel-numbering table exists at all.** Custom Panel ids are assigned by the game on
creation and only ever increment — deleting a panel doesn't free its number, and cards can't be
drag-reordered once placed (confirmed live; a ticket was filed with the dev about both). The
calculator started out as `panel_1.py` (the first panel that exists on any save) but was later
recreated at a new number to get the UI card into the visual slot the operator wanted — hence the
"currently" qualifier on every cross-reference to a specific `panel_N.py` filename.

**Two real overlap bugs, screenshot-driven** (text was visibly stacked on top of other text
in-game):
1. `card(x, y, w, h, title)` already renders its own title bar text. All three cards additionally
   called `panel.label(24, 34, TITLE, "caption")` right after — a second, independently-positioned
   render of the exact same title, landing almost on top of the card's own title bar. Removed the
   redundant `label()` call in all three.
2. `slider(key, x, y, w, default, label)` draws its own `label` text at a position the script
   doesn't control — pairing it with a separately-positioned `panel.draw_text()` right after it
   (to show the slider's live numeric value) visibly collided with the widget's own label. Fixed
   by folding the live value INTO the label string itself instead of a second draw call. The
   scroll slider does the same, but the "X-Y of N" range text can only be computed *after*
   `slider()` returns a value for this tick, so it's built from the return of the *previous* tick's
   call (a plain script-level variable persisting across the `while True:` loop, the same way
   `self.wh_per_progress` persists across a controller's own loop) — a one-tick lag, invisible
   since the panel repaints every tick regardless.
3. `panel_2.py`'s narrow-mode per-vehicle row placed the location text almost directly under the
   role pill — the pill renders taller than the assumed 16px gap allows, so the two visibly
   overlapped. Fixed by moving the location text down and widening narrow-mode `row_height` from
   `54` to `64`.

These three produced the general layout rules now listed in the cheatsheet's §7 (never duplicate a
`card()`'s own title, fold a widget's live value into its own label instead of a second text
element, give a `pill()` more vertical clearance than plain text, anchor fixed-footprint elements
from the edge rather than a width fraction).

---

## §7a — Suspended Generators Froze Panel Cards (2026-09-29, fixed in game v0.1.29)

A generator left suspended in a Control Room card (`any(<genexpr>)` stopping at its first match,
or `next(<genexpr>)`) froze the card on its last frame while the script kept looping. Cause: the
simworker commits a panel frame only at a top-level loop boundary with `loopDepth === 1`, and a
suspended generator's `for` loop left `loopDepth` raised. We worked around it with list
comprehensions in panel code (repro was `devtools/panel_generator_repro.py`, removed after the fix; in git since `ca27473`). Game v0.1.29
saves and restores `loopDepth` in `enterGeneratorFrame`/`exitGeneratorFrame`, and the repro keeps
updating live, so the panel rule was dropped.

## §7b — Headless Workers Moved to Automations (2026-09-30, game v0.1.29)

Before v0.1.29 a Custom Panel was the only slot for an always-on script tied to no building, so the
Control Room calculator (`automation_panel.py`) and the Warehouse upgrade worker
(`warehouse_upgrade_panel.py`) ran as panels that drew nothing (see §7). The v0.1.29 Automations
tab (Computer > Automations) gives such scripts their own slot type: no machine, no power supply
(a brownout never pauses grid supervision), no card. Both moved there as
`control_room_automation.py` and `warehouse_upgrade_automation.py`; `scripts_sync.py` role-matches
`automation_N` slots the same way as `panel_N`. The move does not change the running-script count.
`run_control` still only targets machines (`f4()` looks up `state.machines`), so an automation
cannot be started or stopped from another script.

## §11f — One Refinery Role, No Per-Fluid Sub-Roles (2026-10-03)

- The `refinery_<fluid>` sub-roles (one raw fluid in, one refined fluid out) were dropped. Only `refinery` is
  left, and it always pipes all four raw exotics in and all four refined exotics out.
- Reason: the Refiner controller (`lib/refiner.py`) picks its recipe from the network-wide tank fill. It
  takes the emptiest refined fluid whose raw fluid has stock anywhere. A Refiner with only one fluid pair
  piped in would switch to a recipe whose raw input it cannot reach, or whose output has no pipe.
- Port budget: the refinery needs 4 gas fluids and 4 liquid fluids. A 4×4 footprint has 12 perimeter
  tiles per layer, so it also fits next to `factory` or `wildlife`.
- No migration: no save used the sub-roles yet.

## §7c — Control Room Cards Sleep Between Frames (2026-10-14)

A CPU profile of the live game put the seven cards at ~16 % of all script time; stopping them raised the sim speed from 1.7x to 2.4x. The game re-runs a card loop every tick unless it sleeps, and almost all of a card's cost is its Python (reads and formatting), not the widgets: all widget calls plus canvas work stayed under 1 % of the sim worker. The game also skips rasterizing a frame whose draw ops equal the last one. Cards now end each loop with `panel_pace.pace()` ([panels.md](../cheatsheet/panels.md)).

- **Why sleeping is safe**: `sleep()` commits the frame before waiting, so the card keeps showing it; a button press stays queued until the next frame's `button()` answers it.
- **Cursor over the card keeps one-tick pacing**: hover, slider drag and wheel scrolling would otherwise move in 1 s steps. `mouse()` hands out `pressed`/`released` once, so a card that reads it passes its reading to `pace()`.

## §11e — Fluid Pass Looks Ahead (2026-10-13)

The fluid pass connected only extractors that already stood, in a fixed water, oil, steam order, and essences reached the Biomass Mixer only when someone designated its outpost.

- **Pipes before pumps.** Untapped discovered sites and sonar contacts whose kind the biome settles (contact_inference) are planned producer terminals, routed only as plan-ahead chunks. Placing an extractor checks machines on its tiles, not pipes (simworker placement check), so a pipe on the future footprint does not block it. Their footprints are walls for other fluids, so no foreign network touches the extractor later.
- **Priority from need, not a fixed list.** Need versus supply per fluid, with designated-but-unbuilt consumers at a discount and a weight per phase, decides which fluid gets stock first. Machine draw rates stay out: the planner does not know machine counts per outpost, and counts of consumers and producers already move the order the way the operator expects.
- **Mixer by observation.** The Mixer is placed by hand and no founding need designates it. The fluid pass treats a standing Mixer as the `biomass_mixer` role in a local copy of the roles; only the founding pass writes `autoplay.outpost_roles`.

## §11l — Pioneer Miners Proposed per Outpost (2026-10-19)

On the 2026-10-18 run nothing proposed a mining Pioneer; the operator commissioned one by hand on day 20. The fleet provider only retired miners once drills covered every Smelter ore.

- **Per outpost, not per ore.** The operator chose to station a miner at the outpost that needs the ore, even when a miner elsewhere reaches it: trips stay short. The row carries the outpost, and the commission uses it as `HOME_BASE`.
- **No second miner for an ore the first can't reach.** Every commission gets the same best drill and battery preset, so a new miner reaches what the old one reaches. More miners come only from throughput: a `NEED` ore its miners reach stays open with none idle. The clock restarts with each new miner, so one approve can't chain into the cap.
- **Caps: 4 per outpost, 12 in all; idle retire keeps 2 per outpost.** The band between floor and cap stops churn. Drills end it all: once every Smelter ore has a drilled site, no miner is proposed and the existing rule retires them one by one.

## §11m — Charging Stations Wait for the Pioneers' Replacement (2026-10-21)

Operator decision: a Charging Station goes per outpost, once the Pioneers it serves are replaced: Pioneer miners by mining drills (an outpost keeps its station while a Pioneer miner is based there; `miner_surplus_wants()` sells them once drills cover it) and Pioneer haulers by drone haulers (nothing retires until a hauler drone flies and Pioneer haulers are down to the pump-salt ones). One gate, `charging_retire_ready()`, serves both the retire rows and the `charging` role move, so the role no longer leaves a station early.
