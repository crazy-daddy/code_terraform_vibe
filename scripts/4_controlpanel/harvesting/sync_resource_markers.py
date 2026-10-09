# Resource Supply Markers
# Syncs a "resource.poi_X_Y" map marker (lib/outpost_mining.py) for every
# already-surveyed mineral site, then hands every still-unassigned marker to
# the closest mining-designated outpost in range.
#
# orchestrator_automation.py does both on its own (backfill once per run,
# sweep every storage pass); run this by hand only to force a pass now.

import outpost_mining

if not get_component("markers"):
    print("[ERROR] Map Markers component ('markers') is unavailable. Unlocked by Cartography research.")
else:
    synced = outpost_mining.sync_mineral_site_markers()
    assigned = outpost_mining.assign_unassigned_sites()
    print(f"[DONE] Synced {synced} mineral site marker(s), assigned {assigned} to mining outposts.")
