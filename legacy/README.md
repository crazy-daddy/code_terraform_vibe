# Legacy: pre-Control-Room self-electing power/smelter automation

`pre_control_room_leader_election.zip` is a point-in-time snapshot of this repo's `lib/` directory (plus
`solar_1.py` and `smelter_1.py`), taken right before Solar Grid supervision and the Smelter Inventory→
Warehouse rebalance sweep were centralized into `panel_1.py`'s Control Room automation.

## Why this exists

The live `lib/solar.py`/`lib/smelter.py` now hard-depend on `panel_1.py` running: `SolarController` only
tracks the sun (no grid supervision of its own any more), and `SmelterController` no longer runs the
rebalance sweep itself — both of those jobs are owned entirely by `panel_1.py`'s AUTOMATION section, which
requires the **Control Room** (`research_custom_panels` / `custom_panels_unlock`, Terraform Index 150,000 —
see `docs/database/research_catalog.md`) to be unlocked.

A **new save** hasn't unlocked Control Room yet, so it has no panel scripts and therefore no Solar Grid
brownout protection and no Smelter rebalance sweep at all until it does. This snapshot is the old
self-electing version (`SolarController.check_master()` / `SmelterController.check_leader()`, one Master/
Leader elected per grid/outpost among the running instances) that worked standalone, with no panel
dependency, for exactly that early-game window.

## How to use it

1. Unzip `pre_control_room_leader_election.zip` somewhere temporary.
2. Copy its `lib/` directory over your current `lib/` (overwrite), and copy `solar_1.py`/`smelter_1.py` back
   into the scripts root.
3. Run your solar/smelter entrypoint scripts as normal — no Control Room/panel needed.
4. Once `research_custom_panels` unlocks in that save, switch back: restore the live (non-legacy) `lib/`
   directory and make sure `panel_1.py` is running, since that's what now owns grid supervision and the
   rebalance sweep going forward.

Do not mix legacy `lib/solar.py`/`lib/smelter.py` with a live `panel_1.py` that also runs the centralized
automation — that would re-introduce the redundant-election problem this refactor removed (or worse, double
process the same shedding/rebalance logic from two independent code paths at once).
