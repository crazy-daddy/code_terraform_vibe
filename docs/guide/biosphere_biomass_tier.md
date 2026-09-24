# Guide: biosphere_biomass_tier

## Biosphere, Biomass Tier

The **Biosphere** is the second major terraforming track. Its first tier is **Biomass**: drone crews discover and harvest native life, then outpost machines convert it into planetary biomass.

### Unlock

**Basic Drone Operations** opens at 180k Terraform Index, before Biosphere. It exposes drone deployment and control, but every chassis, thruster, station, battery, and Cargo Pod still needs a blueprint earned from Earth Orders and must be fabricated. **Biosphere** opens at 210k and adds the Portable Bio Scanner, Portable Bio Extractor, Essence Liquifier, and Biomass Mixer.

### Permanent biosites

The Planet Map contains **35 permanent biological sites**: **7 total per biome type across the entire map**, shared among all disconnected patches of that biome. They begin as the same question-mark contacts used for other physical sites and block construction. Each contains **1-3** native life forms; every biome's six life forms are guaranteed somewhere among its seven sites. Locations and contents are identical in every game.

Biological field tools mount only on drones. You don't hunt for the question marks by eye: `get_component("nocturna").points_of_interest()` returns every "?" contact on the map (each with `.x` / `.y` / `.scanned`), so a scanning drone routes straight to the unscanned ones instead of wandering. Fly to a contact with `go_to(x, y)`, then call `self.bio_scanner.scan()`. The question mark becomes a biological marker and the result persists in the Journal. A contact's `.kind` stays `"unknown"` until scanned, so bio-scan each unknown to find the biosites (minerals, vents, and wells share the same map and scan empty for a bio scanner). A harvester drone returns to a biosite coordinate and calls `self.bio_extractor.extract()`.

A Small electric drone uses its Thruster slot for an Electric Thruster and one of its two Module slots for a Battery Pack. That leaves one specialist slot: fit a Scanner or an Extractor for the trip, swap roles while docked, or field two drones. Medium and Large chassis add room later.

The extractor includes a **25 t sealed chamber** that holds one life-form type at a time. Each Cargo Pod holds ONE material: Small 100, Medium 250, Large 500 units, so a drone carries as many materials as it has pods. Use `self.cargo.space_for(item_id)` to check room for a specific material before a trip. `get_component("journal").biomass_coords()` is the restart-safe list of discovered routes; each sample exposes peak `.tons` and current `.remaining_tons`.

### Depletion and cooldown

A harvest removes only what the drone can carry. Remaining stock stays at the site for another trip. Cooldown starts only after every life form there is depleted. Common, uncommon, and rare sites use progressively longer cooldowns, then replenish at the same permanent coordinate. Use `journal = get_component("journal")`, then `journal.is_ready(x, y)` and `journal.next_ready_at(x, y)` to schedule rotations.

### Local processing

A Drone Depot stockpile belongs to one outpost. Dock there to unload, then route the sample into an **Essence Liquifier at that same outpost**. The specimen must be native to the outpost's biome. The Liquifier produces only that biome's essence.

Nothing is shared between outposts. Move life forms with drones, and move essence through a physical liquid network of ports, pipes, and tanks. A **Biomass Mixer** consumes the required biome essences and produces biomass tons. Later phases require more distinct essences, so progression expands the local station and Liquifier chain into more biomes and brings those liquid lines together at a Mixer.

> The extractor chamber makes a basic harvester functional. Cargo Pods reduce trips but do not replace the local outpost chain.

Plants and Wildlife are the next Biosphere pillars.

*Guide / World & Infrastructure*
