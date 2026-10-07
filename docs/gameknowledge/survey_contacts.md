# Unresolved sonar contacts: what the blocked reason tells

Source: the sonar scan in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `geological_survey_unlock`, the blocked-contact builder next to `findSitesInRange(`) and world generation (`generateThermalVents`, `generateExoticDeposits`, `generateFluidWells`). Code: `lib/contact_inference.py`.

A sweep returns the contacts it could not identify in `SonarScanResult.blocked`, each with a `.reason`. The game picks the reason from the contact's real kind:

| Reason | Contact kind | When |
| :--- | :--- | :--- |
| `wrong_scanner` | biomass | always for a vehicle sonar (needs a drone bio-scan) |
| `too_hard` | mineral | hardness above the sonar's limit (basic 1, Wide 3, Deep 4) |
| `research_required` | thermal | Geological Survey locked |
| `research_required` | water | Hydrology Survey locked |
| `research_required` | exotic | Exotic Husbandry (common) or Deep Exotics (rare) locked |
| `research_required` | oil | Petroleum Survey locked |
| `tier_too_low` | oil | Petroleum Survey unlocked, sonar below Deep |

So the reason plus the scan researches unlocked at the time (stored on each `survey.unsupported_targets` entry) narrows the kind:
- `research_required` with Hydrology, Petroleum and both exotic researches unlocked is a **thermal vent** for certain.
- With only Geological Survey locked among the classifying researches, it is thermal; with several locked, it is one of those kinds.
- `tier_too_low` is always oil.
- `too_hard` with a Wide Sonar (limit 3) is Neutronium, the only H4 mineral.

## Biome decides the fluid kind

World generation places each fluid kind in one biome only; the placement test (and its fallback) checks the biome at the spot and 20 m around it (`BIOME_KINDS`):

| Biome | Kind |
| :--- | :--- |
| geothermal | thermal vent |
| frozen, coastal | water well |
| volcanic | oil well |
| deep | exotic deposit |

Minerals and biomass spawn in every biome. So `nocturna.biome_at(x, y)` at a `research_required` contact names its kind outright, even for entries written before `unlocked_scan_researches` was recorded (2026-10-04). If biome and research record disagree, the research record wins (`possible_kinds()`).

Map markers name the kind and the locked research that classifies it, e.g. "Thermal vent: needs Geological Survey" (2 kPa). A thermal vent's note adds that tapping it also needs Thermal Cap (2.5 kPa).
