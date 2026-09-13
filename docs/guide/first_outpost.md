# Guide: first_outpost

## First Outpost

An Outpost expands your build area to a new part of the planet. Buying an **Outpost Kit** is only the material step; founding it also needs the Pioneer construction workflow.

### Requirements

- **Outpost Construction** research to buy the Outpost Kit.
- **Constructor Module** research to build Planet Map blueprints.
- A **Pioneer** with a **Nav Module** and a **Constructor Module** mounted.
- A **Battery Holder** with at least one charged **Portable Battery** installed. Without stored energy, the Pioneer cannot drive.
- A **Cargo Rack** with enough Portable Storage Bin space for one **Outpost Kit**.
- One Outpost Kit loaded into Pioneer cargo, not left in Base Inventory.
- An Outpost blueprint placed in Plan Mode or with `construction_blueprint.plan_structure("outpost", x, y)`.

### What to do

Place the outpost footprint first. Plan Mode gives visual placement feedback; the script API returns an exact planning status. Either path creates the same job marker. Then load the kit, move the Pioneer to the blueprint, brake, and build it from the Pioneer. If the Pioneer cannot leave, inspect its battery capacity and charge. If the kit is in inventory but nothing builds, check that the Constructor Module is mounted and the kit is physically in Pioneer cargo.

### Why this matters

A single home base becomes slow later. The outpost step is when terraforming becomes geographic: more build areas, more machines, more local power, and eventually networks that connect distant production.

*Guide / Tutorials*

---
