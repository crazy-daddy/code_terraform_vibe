# Resource Supply Markers
# Syncs a "resource.poi_X_Y" map marker (lib/outpost_mining.py) for every
# already-surveyed mineral site, and sweeps any still-unassigned marker within
# range of each owned outpost, handing it over if nothing has claimed it yet.
#
# Run this manually:
#  - once, to backfill markers for sites surveyed before this system existed;
#  - after surveying a batch of new POIs (auto_assign_new_site() already runs
#    per-site during a live survey pass -- this is just for catching up);
#  - after founding a new outpost (CLAUDE.md: outposts are never founded
#    automatically, so there's no automatic hook for "a new outpost just
#    appeared" -- re-running this script is the intended trigger).

import outpost_mining


def sync_all_mineral_sites():
    journal = get_component("journal")
    if not journal or not hasattr(journal, "surveyed_sites"):
        print("[ERROR] Journal component unavailable.")
        return 0
    if not get_component("markers"):
        print("[ERROR] Map Markers component ('markers') is unavailable. Unlocked by Cartography research.")
        return 0

    synced = 0
    for site in journal.surveyed_sites("nocturna"):
        if site.kind() != "mineral" or not getattr(site, "item_id", None):
            continue
        outpost_mining.auto_assign_new_site(site)
        synced += 1
    print(f"[DONE] Synced {synced} mineral site marker(s).")
    return synced


def reevaluate_all_outposts():
    network = get_component("outpost_network")
    if not network or not hasattr(network, "outposts"):
        print("[ERROR] Outpost Network component unavailable.")
        return

    for outpost in network.outposts():
        newly_assigned = outpost_mining.reevaluate_unassigned_near_outpost(outpost.id)
        if newly_assigned:
            print(f"[INFO] Assigned {newly_assigned} previously-unclaimed resource marker(s) to '{outpost.id}'.")


# Execute when run directly as a script
sync_all_mineral_sites()
reevaluate_all_outposts()
