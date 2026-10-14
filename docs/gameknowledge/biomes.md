# Biomes on Nocturna: which biome a position is in

Source: `internals/terraform_decompiled/simworker/deobfuscated.js`. Search `Generated Nocturna biome lattice` for the lookup, `biome_at` for the scripting call, `wrong_biome_for_machine` for the machine lock, and `generateThermalVents` / `generateFluidWells` for world generation. Data: [biomes.json](biomes.json). Code: `BIOMES` in `lib/game_rules.py`, `BIO_PROCESSORS` in `autoplay/lib/autoplay_roles.py`, `BIOME_KINDS` in `lib/contact_inference.py`.

## The five biomes

There are exactly five: `frozen`, `coastal`, `geothermal`, `volcanic`, `deep`. There is no "green" biome. The UI paints coastal teal-green (primary `#6fb9a4`), so a player reading the map can call coastal "green".

| Biome | Bio processor (step 3 machine) | Fluid sites spawned there | Map share |
| :--- | :--- | :--- | ---: |
| frozen | none | water wells | 9 % |
| coastal | Bio Luminizer (`bio_luminizer`) | water wells | 24 % |
| geothermal | DNA Sequencer (`dna_sequencer`) | thermal vents | 16 % |
| volcanic | Bio Caster (`bio_caster`) | oil wells | 23 % |
| deep | Bio Conditioner (`bio_conditioner`) | exotic deposits | 28 % |

Each biome also carries a `difficulty` field (frozen 1.0, then +0.1 per row down to deep 1.4). Its use is not traced here.

## Position to biome

`nocturna.biome_at(x, y)` and every internal biome check call one function. It reads a fixed lattice that ships inside the game code:
- 451 x 451 cells, 4 m apart, covering x and y from -900 to +900 (the Nocturna map bounds).
- Column `i = round((x + 900) / 4)`, row `r = round((900 - y) / 4)`, after clamping both offsets to 0..1800. Row 0 is the north edge (y = +900). Rounding is JS `Math.round` (halves round up).
- Each cell holds a biome index 0..4 in the order frozen, coastal, geothermal, volcanic, deep. An unknown value falls back to frozen.
- Positions off the map clamp to the nearest edge cell.

So boundaries are a raster at 4 m resolution, not polygons or Voronoi centres. The function takes only x and y. The seed is not an input, so the map is the same in every save and every seed. The API text says the same: "Pure geography, same answer for the same coordinate forever." What the seed does change is where wells, vents and deposits land inside their biome.

The `{biome: [[x, y] x 16]}` point table next to the lattice is not a boundary source. It holds wildlife spawn anchors (16 per biome, picked by creature index).

Regions (4-connected patches; areas from the lattice):
- frozen: 3 patches. The main one covers the home base (x about -200..160 at y = 0), plus patches near (477, 421) and (-805, 556).
- coastal: 1 large ring around the frozen centre (71 % of all coastal), plus one patch near (703, -624).
- geothermal: 7 patches. The largest are near (390, -612), (-439, -681), (-674, 302) and (779, 776).
- volcanic: 9 patches. The largest are near (127, 666), (-68, -738) and (-504, 628).
- deep: 12 patches. The largest is the west edge (around (-688, -177)), then (580, 660) and (735, 52).

[biomes.json](biomes.json) holds the whole lattice, one run-length coded string per row, with the lookup rule. A coarse view (north up) puts frozen in the centre, a coastal ring around it, deep along the west and east edges, volcanic and geothermal in the north and south bands.

## Which position the game checks

- **Machines are locked by the outpost's biome, not their own tile.** Placing a step 3 machine (the four processors above) checks the biome at the outpost record's `x, y`, its anchor (top-left corner of the placement square). A mismatch fails with `wrong_biome_for_machine`. A machine with no step 3 biome is never locked. A machine's own biome is likewise its outpost's biome, and its position only when it has no outpost.
- The Essence Liquifier uses the outpost anchor's biome too. It accepts only life forms native to that biome (else `no_input`).
- World generation places a fluid site only where the biome holds at the spot and 20 m north, south, east and west. Its fallback search uses the same test. Water spawns in frozen or coastal, oil in volcanic, thermal vents in geothermal, exotics in deep.

## Run 20261008_7e5e168: outposts

Biome at each outpost anchor, with the distance to the nearest other biome:

| Outpost | Anchor | Biome | Nearest other biome |
| :--- | :--- | :--- | :--- |
| home | 0, 0 | frozen | coastal, 157 m |
| outpost_1 | 170, 80 | coastal | frozen, 24 m (to the south-west) |
| outpost_2 | 200, -440 | geothermal | coastal, 58 m |
| outpost_3 | -460, 280 | deep | geothermal, 30 m |
| outpost_5 | 30, 420 | volcanic | coastal, 30 m |
| outpost_6 | 200, 0 | coastal | frozen, 31 m |
| smelter idea | -450, 120 | deep | coastal, 31 m |

outpost_1 and outpost_6 are coastal. The owner's "green" is the coastal map colour. The Luminizer at outpost_1 also proves it, because the game refuses a Luminizer outside coastal. The final save fits as well: DNA Sequencer at outpost_2 (geothermal), Bio Caster at outpost_5 (volcanic), Bio Conditioner at outpost_3 (deep).
