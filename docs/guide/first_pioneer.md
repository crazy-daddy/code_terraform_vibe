# Guide: first_pioneer

## First Pioneer

A Pioneer is the first vehicle that turns remote plans into built infrastructure. The usual flow is: buy a Pioneer, mount the modules it needs, send it to the site, and let its local script do the work.

### What makes it different

The Rover is the introductory vehicle. A Pioneer does the same field work, mining included, and does it better and faster, and it is the only chassis that can build. The chassis is only the carrier; mounted modules decide what it can actually do.

For early expansion, look for four module families:

- **Nav Module** - moves the Pioneer across the full planet coordinate plane.
- **Battery Holder** - carries Portable Batteries. At least one charged Portable Battery must be installed or the Pioneer cannot move.
- **Cargo Rack** - hosts Portable Storage Bins that carry kits, pipe segments, power-line segments, and other build materials.
- **Constructor Module** - executes Planet Map blueprints once the right materials are on board.

### Good first goal

Before trying to found an outpost, practice with a small job: put a simple blueprint near home, install a charged Portable Battery, load the required kit or segments into Pioneer cargo, move it to the blueprint, brake, and execute it. The blueprint can come from Plan Mode or `get_component("construction_blueprint")`; either path creates the same persistent job. If the Pioneer cannot leave, check its Battery Holders and installed batteries. If construction is rejected, check the Constructor Module and cargo.

### Where to look

The Info tab explains the module APIs available through `self`. Plan Mode shows material requirements before placement. Query `get_component("construction_blueprint").pending_constructions()` for the queued `Construction` snapshots; every one exposes `required_item` and `required_count` to scripts.

*Guide / Tutorials*
