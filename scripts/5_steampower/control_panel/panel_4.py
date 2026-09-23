# Tier-5 copy of 4_controlpanel's panel_4.py. Only difference: also drives
# lib/biomass_mixer_gate.py's MixerGate (Biomass Mixer duty-cycling via the
# breaker -- a paused Mixer can't wake itself, so an always-on script must).
#
# Control Room automation CALCULATOR -- headless, draws nothing. See
# panel_1.py for the actual STATUS/AUTOMATION card UI, which reads this
# script's results back out of `archive`.
#
# Split out because this game has no true background/daemon script type -- a
# Custom Panel is the only slot that can host an "always-on, not tied to one
# building" process, which is why Supply Dock planning (below) ended up here
# instead of on any one dock. But mixing that with UI rendering turned out to
# be fragile: found live that a single iteration running long (e.g.
# supply_dock.plan_dock_assignments() churning through several orders, ~2-10s
# even after lib/production.py's SourceCache fix cut its cost down) wedges
# that Custom Panel's rendering permanently -- confirmed via temporary debug
# prints that the script kept looping and completing fine underneath
# (~100ms/iteration) the entire time the card stayed visually blank. There's
# no known threshold under which an occasional multi-second stall is safe for
# a script that also renders every tick, so the fix is structural: keep this
# process entirely headless (no panel.* calls at all) and publish its results
# to `archive` for panel_1.py to display instead of drawing them directly --
# same Archive-as-decoupling-channel pattern CLAUDE.md calls for when a
# result can't be produced by the component that has to display it.
#
# NOTE ON THE FILE NUMBER: this script started life as panel_1.py (the first
# Custom Panel on any save, hence the natural original home for a
# "guaranteed to keep running" process). In the LIVE SAVE it's panel_7.py
# instead -- Custom Panel ids only ever increment (deleting one never frees
# its number) and cards can't be drag-reordered in the Control Room UI, so
# getting the UI card into the visually-first slot meant recreating it at
# panel_1 and moving this (position-agnostic, since it draws nothing)
# calculator to whatever number was free.
#
# In this SOURCE TREE it's named panel_4.py instead (cosmetic renumbering to
# panel_1..4 across the four real Control Room scripts, done when scripts/
# was split into tiers -- see docs/AI_CHEATSHEET.md §9). That's deliberately
# decoupled from the live-save slot number above; devtools/scripts_sync.py
# does NOT currently bridge the two (see TODO.md's "Panel dev-side numbering
# vs. save-side slot numbers"), so this file only re-deploys correctly today
# because the save's panel_7.py already has code and is never re-synced.
#
# See docs/AI_CHEATSHEET.md §7's panel-numbering-quirk note for the current
# full mapping -- it WILL drift again if panels are added/removed in-game,
# so verify against the operator before trusting it.
#
# Responsibilities (see docs/AI_CHEATSHEET.md):
#   - Power Grid supervision (brownout load-shedding, day/night calibration)
#     for every grid, one PowerGridManager instance per grid, reused across
#     cycles so its day/night state persists.
#   - The Smelter Inventory->Warehouse rebalance sweep, once per cycle.
#   - Cross-warehouse stock consolidation, every outpost, once per cycle.
#   - Outpost-founding -> resource marker auto-reassignment
#     (lib/outpost_mining.py's reevaluate_unassigned_near_outpost()).
#   - Biomass Mixer duty-cycle gate (lib/biomass_mixer_gate.py), every
#     MIXER_GATE_TICK_INTERVAL.
#   - Supply Dock order-assignment planning across every discovered dock
#     (lib/supply_dock.py's plan_dock_assignments() -- the central "decider"
#     so multiple docks share/split Earth Orders instead of each redundantly
#     scanning the order board and independently guessing; see
#     docs/AI_CHEATSHEET.md #2a-0-5).
# lib/solar.py's SolarController and lib/smelter.py's SmelterController no
# longer do any of this themselves -- it's a hard dependency on this script
# running (see legacy/README.md for pre-Control-Room saves). The manual
# "Clean Archive"/"Sync Unsupported"/"Confirm New Version" buttons live on
# panel_1.py instead -- they're rare, user-triggered one-offs, not the
# chronic per-cycle cost that forced this script headless.

from archive import archive
from power import PowerGridManager
from biomass_mixer_gate import MixerGate
from storage import rebalance_inventory_to_warehouses, consolidate_cross_warehouse_stock, reclaim_inventory_only_items_from_warehouses
from version_guard import version_mismatch
import outpost_mining
import supply_dock

OUTPOST_KNOWN_IDS_KEY = "outposts.known_ids"

# Published each time the storage-tick automation runs; panel_1.py reads this
# to display the "ALWAYS-ON" line instead of computing it itself. Left
# untouched (not overwritten) while version_mismatch() halts automation below,
# same as the old combined script did -- panel_1.py shows its own fixed
# "halted" message in that case rather than trusting a stale summary.
AUTOMATION_SUMMARY_KEY = "control_room.automation_summary"

# ~1s and 10s at 10 ticks/sec (see lib/archive_cleaner.py's documented tick rate).
SOLAR_TICK_INTERVAL = 10
STORAGE_TICK_INTERVAL = 100
MIXER_GATE_TICK_INTERVAL = 10

grid_managers = {}          # {anchor_id: PowerGridManager}, reused so day/night state persists
last_solar_tick = 0
last_storage_tick = 0
last_mixer_gate_tick = 0
mixer_gate = None           # MixerGate, created lazily once power_control is available
mixer_gate_summary = "no Mixers"
grid_count = 0              # last solar-sync grid census; carries over on ticks solar_due is False

while True:
    clock = get_component("clock")
    power = get_component("power_control")

    if not version_mismatch():
        current_tick = clock.tick() if clock and hasattr(clock, "tick") else 0
        solar_due = (last_solar_tick == 0) or (current_tick - last_solar_tick >= SOLAR_TICK_INTERVAL)
        storage_due = (last_storage_tick == 0) or (current_tick - last_storage_tick >= STORAGE_TICK_INTERVAL)
        mixer_gate_due = (last_mixer_gate_tick == 0) or (current_tick - last_mixer_gate_tick >= MIXER_GATE_TICK_INTERVAL)

        if solar_due:
            last_solar_tick = current_tick
            grid_count = 0
            try:
                elevation = clock.get_elevation() if clock else 0.0
                live_grids = power.grids() if power and hasattr(power, "grids") else []
                current_anchors = set()
                for grid in live_grids:
                    anchor = getattr(grid, "anchor_id", None)
                    current_anchors.add(anchor)
                    manager = grid_managers.get(anchor)
                    if manager is None:
                        manager = PowerGridManager(grid, clock=clock, power=power)
                        grid_managers[anchor] = manager
                    manager.supervise_grid(grid, elevation)
                    grid_count += 1

                # Grids that stopped being reported (merged into another via a new
                # power line) -- release anything they still had shed rather than
                # stranding it forever (see PowerGridManager.release_all()).
                for stale_anchor in list(grid_managers.keys()):
                    if stale_anchor not in current_anchors:
                        grid_managers[stale_anchor].release_all()
                        del grid_managers[stale_anchor]
            except Exception as e:
                print(f"[AUTOMATION] Grid supervision error: {e}")

        if mixer_gate_due:
            last_mixer_gate_tick = current_tick
            try:
                if mixer_gate is None and power:
                    mixer_gate = MixerGate(power=power, clock=clock)
                if mixer_gate is not None:
                    gate_states = mixer_gate.step(current_tick)
                    if gate_states:
                        paused = sum(1 for st in gate_states.values() if st.get("state") == "pause")
                        mixer_gate_summary = f"{len(gate_states)} Mixer(s), {paused} paused"
            except Exception as e:
                print(f"[AUTOMATION] Mixer gate error: {e}")

        if storage_due:
            last_storage_tick = current_tick
            try:
                rebalance_inventory_to_warehouses()
            except Exception as e:
                print(f"[AUTOMATION] Rebalance sweep error: {e}")

            try:
                reclaim_inventory_only_items_from_warehouses()
            except Exception as e:
                print(f"[AUTOMATION] Reclaim sweep error: {e}")

            outpost_new_count = 0
            try:
                network = get_component("outpost_network")
                if network and hasattr(network, "outposts"):
                    outposts = network.outposts()
                    current_ids = {getattr(o, "id", None) for o in outposts}
                    current_ids.discard(None)
                    known_ids = set(archive.get(OUTPOST_KNOWN_IDS_KEY, []) or [])
                    new_ids = current_ids - known_ids
                    for new_id in new_ids:
                        assigned = outpost_mining.reevaluate_unassigned_near_outpost(new_id)
                        print(f"[AUTOMATION] New outpost '{new_id}' detected -- assigned {assigned} nearby resource marker(s).")
                        outpost_new_count += 1
                    if current_ids != known_ids:
                        archive.set(OUTPOST_KNOWN_IDS_KEY, sorted(current_ids))

                    # Cross-warehouse consolidation sweep (storage.py's
                    # consolidate_cross_warehouse_stock(), which calls
                    # .compact()) -- every outpost, not just home, since a
                    # remote outpost's Warehouses (e.g. a Bio Lab reagent drop)
                    # can end up with the same item split across multiple
                    # Warehouse buildings the same way repeat hauler deliveries
                    # can at home.
                    for o in outposts:
                        o_id = getattr(o, "id", "?")
                        try:
                            consolidate_cross_warehouse_stock(o)
                        except Exception as e:
                            print(f"[AUTOMATION] Cross-warehouse consolidation error at '{o_id}': {e}")
            except Exception as e:
                print(f"[AUTOMATION] Outpost sync error: {e}")

            dock_plan_count = 0
            try:
                plan = supply_dock.plan_dock_assignments(clock=clock)
                dock_plan_count = sum(1 for v in plan.values() if v)
            except Exception as e:
                print(f"[AUTOMATION] Supply Dock planning error: {e}")

            archive.set(AUTOMATION_SUMMARY_KEY, f"{grid_count} grid(s) supervised, rebalance swept, {outpost_new_count} new outpost(s), {dock_plan_count} dock(s) assigned, {mixer_gate_summary}")

    sleep(1.0)
