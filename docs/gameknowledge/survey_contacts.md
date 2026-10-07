# Unresolved sonar contacts: what the blocked reason tells

Source: the sonar scan in `internals/terraform_decompiled/simworker/deobfuscated.js` (search `geological_survey_unlock`, the blocked-contact builder next to `findSitesInRange(`). Code: `lib/contact_inference.py`.

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

Soft prior on top (owner, 2026-10-07): a `research_required` contact in the geothermal biome is most likely thermal (`BIOME_KIND_PRIOR`). The rule table only removes kinds the game rules out; the prior reweights what is left.
