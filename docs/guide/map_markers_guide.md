# Guide: map_markers_guide

## Map Markers

### Overview

Map markers are annotations you leave on the Planet Map: a glyph, a color, a label, and a short note pinned to a coordinate. You place them by hand in Plan Mode, and your scripts place them with `get_component("markers")`. Both paths write the same records.

A marker is a note, not construction. Placing one is instant and free: no materials, no Pioneer, no build time, no collision. Markers overlap buildings, sites, and each other freely.

Markers unlock with **Cartography** research. Before that, `get_component("markers")` returns `None`.

### Place from a script

```
markers = get_component("markers")

result = markers.place("survey.rover_1.empty:120:-40", 120, -40,
                       "No contact", "x", "neutral",
                       "Sonar sweep found nothing here.")
if result.status != "ok":
  print(result.message)
```

Reusing an id rewrites that marker, position included, so there is no separate move or rename call. That matters because a script restarts from its first line after a save and reload: a create-only API would fill the map with duplicates.

### Organize by id prefix

There are no tags. Ids carry the structure, the same way Data Archive keys and Signal Bus channels do.

```
for marker in markers.list("build."):
  print(marker.label, marker.x, marker.y)
```

**Include the controlling machine in the prefix**, as in `"survey.rover_1."` rather than `"survey."`. Two scripts that share a bare prefix will overwrite and clear each other's markers.

### Keeping a family current

```
prefix = "survey.rover_1."
markers.clear(prefix)
for site in get_component("journal").surveyed_sites("nocturna"):
  if site.kind() == "mineral":
    markers.place(prefix + site.id, site.x, site.y, site.item_id, "resource")
```

Clearing first makes the family a picture of what your script believes right now. The trade-off is that an error midway through leaves the map half-populated. Plain `place()` calls without the clear are safe against that, but markers for conclusions that are no longer true will pile up. Pick per script.

`markers.clear("")` deletes every marker on the planet, including the ones you placed by hand, and nothing records who placed what. The prefix argument is required so a full wipe has to be written out deliberately.

### Acting on a marker

Markers hold coordinates; they do not build anything. To turn one into real work, pass its position to the construction queue and let a Pioneer do the job.

```
for marker in markers.list("build.outpost"):
  plan = get_component("construction_blueprint").plan_structure("outpost", marker.x, marker.y)
  if plan.status != "ok":
    print(marker.id, plan.message)
```

### Limits

A planet holds up to **256** markers. Ids are 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`. Labels are up to **48** characters and notes up to **240**. Coordinates are world meters and keep their fractions; anything outside the planet is rejected.

Markers are for the map. Anything structured belongs in the Data Archive under the same id.

*Guide / Automation Systems*
