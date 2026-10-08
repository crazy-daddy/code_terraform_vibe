# Guide: sonar_scanning

## Sonar: scanning and surveying

Sonar helps a Rover or Pioneer find resources on the Planet Map. **Scan** to identify nearby contacts, then **survey** a site to learn its extraction details. Driving past a contact does not scan it automatically.

### Choose a sonar

| Sonar | Range | Mineral hardness limit | Energy per scan or paid survey |
|---|---|---|---|
| Basic (Sonar Module) | 50 m | 1 | 0.5 Wh |
| Wide Sonar | 180 m | 3 | 1 Wh |
| Deep Sonar | 280 m | 4 | 2 Wh |
| Seismic Sonar | 280 m | 4 | 3 Wh |

The hardness limit includes every softer mineral. Basic detects Iron and Silicon. Wide adds Titanium, Cobalt, Lead and Rare Earth. Deep and Seismic also detect Neutronium. **Detecting a mineral does not mean your drill can mine it**: the drill has its own hardness limit.

Basic fits the Rover's Sonar slot or a Pioneer universal slot. Wide, Deep and Seismic require a **Pioneer universal slot**. Replace the previous sonar when upgrading. Research **Sonar Module**, **Wide Sonar** or **Deep Sonar** to buy the corresponding module; **Advanced Oil Extraction** unlocks Seismic Sonar.

### What each survey reveals

For **thermal vents and exotic deposits**, Basic reveals the active or dormant phase; an exotic survey also identifies the fluid, medium and rarity. Wide adds the base and current flow rates. Deep adds active and dormant durations and the time until the next phase. Seismic provides the same details as Deep, plus deep oil prospecting beneath inert formations.

A mineral survey reveals the mineral, hardness and purity. A water or oil well survey reveals its yield and flow rate. These sites do not use the gradual thermal/exotic detail levels.

**Research and sonar capability both matter.** A stronger sonar does not bypass research:

| Contact | Required research | Sonar needed |
|---|---|---|
| Thermal vents | Geological Survey | Any |
| Water wells | Hydrology Survey | Any |
| Ordinary oil wells | Petroleum Survey | Deep or Seismic |
| Common and uncommon exotic deposits | Exotic Husbandry | Any |
| Rare exotic deposits | Deep Exotics | Any |
| Deep oil beneath inert formations | Petroleum Survey and Advanced Oil Extraction | Seismic |

### Scan, then survey

Use the Planet Map's question-mark contacts to choose where to explore. Scripts can read them with `get_component("nocturna").points_of_interest()`. Travel within the mounted sonar's range, stop, and call `self.sonar.scan()`. The sweep checks around the vehicle's current position and records classified sites in the **Journal**.

Read the scan's `.sites` for usable contacts and `.blocked` for contacts it could not classify. **A sweep can find usable sites and blocked contacts together**, so inspect both even when some contacts need better equipment or research. Repeating the same scan cannot overcome those requirements. Biological contacts need a Portable Bio Scanner instead of vehicle sonar.

Call `self.sonar.survey(site)` on a discovered site while it remains in range. A scan takes **0.15 h**; an ordinary paid survey takes **0.25 h**. For ordinary sites, repeating a survey at the same or a lower sonar tier is free and instant. After upgrading sonar, survey known thermal vents and exotic deposits again to unlock the deeper details.

Run this from a stopped vehicle with sonar and enough battery charge. It surveys productive contacts; inert formations use the deep-oil workflow below:

```
sweep = self.sonar.scan()
print(sweep.message)
for site in sweep.sites:
  if site.kind() != "inert":
    result = self.sonar.survey(site)
    if result.status == "ok":
      print(result.site.id, result.site.kind())
    else:
      print(result.message)
```

Query `get_component("journal").discovered_sites("nocturna")` for previously classified sites. The Journal remembers discoveries, so you can plan return trips without scanning the whole map again.

### Revisit inert formations for deep oil

**Inert formations are the targets for Seismic Sonar.** Any sonar can identify them as `GeologicalAnomaly` sites with `site.kind() == "inert"`. Ordinary scanning marks them surveyed, but that does not rule out oil deeper underground. **Revisit them even if the Journal already marks them surveyed.**

After Petroleum Survey and Advanced Oil Extraction, mount Seismic Sonar and scan within **280 m**. Read `site.seismic_status`: `"potential"` means a possible deep reservoir; `"dry"` means no deep oil. Survey a potential contact with `self.sonar.survey(site)` to confirm an Oil Well at the same coordinates. A new deep-oil survey takes **0.5 h** and costs **3 Wh**; re-surveying a known dry formation is free. Three inert formations on each map conceal these additional reservoirs.

See `industrial_upgrades` for the full deep-oil example and Oil Pump upgrades. For individual commands and returned fields, see `SonarModule`.

For turning surveyed mineral sites into delivered ore, continue with `mining_guide`.

*Guide / Tutorials*
