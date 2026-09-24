# Guide: faq

## Frequently Asked Questions

Short answers to the questions commanders ask most. Each one points at the DOCS page that owns the full detail.

### Saves, files, and tools

**Where are my saves and scripts on disk?**
Each save stores its scripts as ordinary `.py` files in a `<save_id>_scripts/` folder under your platform's app-data directory, with that save's `.json` file beside it. Windows uses `%APPDATA%\io.codeterraform.game\`, macOS uses `~/Library/Application Support/io.codeterraform.game/`, and Linux uses `~/.local/share/io.codeterraform.game/`. To back a save up, copy both the `.json` file and its matching `_scripts` folder. **External Editor** lists every file in that folder and what it is for.

**Can I use VS Code or another editor instead of the in-game one?**
Yes, and edits sync live in both directions while the game runs. Settings > Editor > External Editor has **Set Up VS Code**, which installs the bundled extension and opens the scripts folder; completion, diagnostics, hover, and breakpoints then use the same analysis as the in-game editor. Other editors read the generated stubs sitting in the same folder. See **External Editor**.

**Can I read the DOCS without the clock running?**
Use **Export** in the DOCS toolbar. You choose which parts to include, and the manual saves as a PDF, a web page, or Markdown.

**I found a problem, or I have an idea. Where does it go?**
Use the **Feedback** button on the main menu or the pause menu. It sends the report with your build id attached, so it can be matched to the exact build it came from. The same screens link to Discord, which is where questions, follow-up, and opt-in test builds are discussed.

### Items and storage

**Do I have to carry items to an outpost, or can it use my Inventory?**
Inventory is a physical storeroom at Nocturna Base, not a planet-wide store. Machines and vehicles can use it as a freight endpoint only at home. Anywhere else, reagents, ore, and parts must already be in that outpost's own storage or aboard a vehicle parked there, so a Pioneer or a drone is how they arrive.

**How do I get rid of items I do not want?**
It depends where the item sits. `shop.sell(item_id, quantity)` turns Base Inventory stock into credits. `inventory.drop(slot)` deletes one unit from a Base Inventory slot by its zero-based index, and a vehicle uses `self.cargo.discard(rack_index)` against the racks that `self.cargo.racks()` reports. For a continuous overflow stream, research **Waste Processing** and fabricate a **Waste Processor**: it permanently destroys one selected stream, items through its feeder input, liquid through `liquid_in`, or gas through `gas_in`.

**A machine input is holding items I want back. Can I recover them?**
Yes. `input.eject(destination, item_id, count)` moves buffered items to another endpoint without changing the port's source connection, and it preserves item properties and respects destination capacity. `input.flush()` is the other tool, and it destroys the entire input buffer, so reach for it only when that is exactly what you want.

**How do I move items between a Warehouse, a Storage Bin, and Inventory?**
Stores never talk to each other on their own. A machine port connects to one endpoint at a time with `connect(name)`, then `take(item_id, count)` and `send(item_id, count)` move the goods, and a transfer takes time proportional to the units moved. At Nocturna Base `"inventory"` is a valid endpoint; elsewhere both ends must sit at the same outpost. See **Input & Output**.

**Why does `take()` or `send()` return `research_required`?**
Item flow through machine ports needs **Auto Feeders** research. Until then the ports exist but move nothing, which is why the Biology chain runs by hand first. **Fast Feeders**, much later, halves the duration of newly started transfers.

### Building and outposts

**How do I found an outpost?**
Buying the Outpost Kit is only the material step. You also need **Outpost Construction** and **Constructor Module** research, plus a Pioneer carrying a Nav Module, a Battery Holder with a charged Portable Battery, and a Cargo Rack holding the kit. Place an Outpost blueprint in Plan Mode or with `construction_blueprint.plan_structure("outpost", x, y)`, drive there, brake, and build it. **First Outpost** walks the whole sequence.

**How do I deploy a building at an outpost once it exists?**
Deploying is not freight, so there is usually nothing to drive out. Buy the shop kit and deploy it from **Inventory** straight into any founded outpost; upgrade packs are consumed into a finished machine the same way. Only constructor-built Planet Map machines, such as Thermal Caps, pumps, and field drills, need a Pioneer to carry the kit and build them in place.

**What is the building cap, and what happens when I pass it?**
It is a soft cap and it never blocks a deploy. Nocturna Base holds **25** buildings and a founded outpost holds **20**; **Outpost Expansion** research adds **5** to every current and future outpost. Past the cap each extra building costs **10%** efficiency at that outpost, down to a floor of **20%**. Each outpost counts on its own, so spreading out removes the penalty. `outpost_network.outposts()` reports `.buildings_used`, `.buildings_capacity`, and `.is_full`.

**How do I remove or move something I built?**
The route follows how it was placed. A shop kit deployed from Inventory is undeployed in **Ship Computer > System**. A fixed Harvesting-field machine is recovered with the local Harvester. A constructor-built Planet Map machine is deconstructed by a Pioneer, which reclaims the kit into its cargo. A founded outpost has its own Ship Computer > System decommission, which needs the outpost empty and returns one Outpost Kit. Undeploy is blocked only while real goods are still stored inside; stored charge and fluid buffers never block it.

### Exploration and mining

**What does "exceeds this sonar's detection limit" mean, and why does my vehicle keep rescanning the same spot?**
The sweep worked, but a contact nearby is harder than your sonar can identify. Minerals run from hardness **1** to **4**, and `sonar.hardness_limit()` and `drill.hardness_limit()` report what your current modules handle. Such a contact stays unscanned, so a loop filtering on `not point.scanned` reselects it forever. The sweep lists those contacts in `scan.blocked` with their coordinates and a reason: record them and skip them until you upgrade the sonar and scan again.

**What is the difference between a point of interest and a site?**
A point of interest is a permanent `?` on the Planet Map with whole-number coordinates and a `kind` that stays `"unknown"` until a scanner reaches it. `scan()` classifies contacts in range into sites, and `survey()` then reveals a productive site's details. `journal.surveyed_sites(planet_id)` lists everything fully resolved.

**Where is titanium?**
Titanium is hardness **2**, so a starter sonar cannot identify it and a starter drill cannot cut it even when it is right beside you. Contracts can ask for it well before you can reach it, which is normal. Upgrade the sonar first, rescan the contacts your Journal recorded as too hard, then upgrade the drill.

**What do I do when a vehicle runs out of power in the field?**
A **Vehicle Charging Station** can send a field-service drone. Call `self.dispatch_rescue(name)` from the station's own script, optionally with a target battery fraction. There is no distance limit, and the station only needs power at launch; the mission survives a later outage. Only one rescue runs at a time, so guard it with `if not self.is_rescuing():`, and the vehicle itself reports `self.is_being_rescued()` and `self.rescue_status()`.

**Rover or Pioneer, what is the difference?**
The Rover is the introductory vehicle. Its three fixed slots take a Nav Module plus the basic sonar and drill only; a Pioneer has eight universal slots, so it does the same field work, mining included, with the higher-tier modules the Rover cannot fit, and it is the only chassis that carries a Constructor Module and builds. The trade is outfitting: the Rover arrives with an integrated **100 Wh** battery and a **10-unit** hold, while a bare Pioneer has nothing built in, not even a battery. See **First Pioneer**.

**What is the Harvester for?**
It is the slow field vehicle for the surface grid: collecting what is scattered there, planting and tending crops, harvesting Forage, and deploying field automation. The items lying on the field at the start are a finite early credit source, so selling them is fine. The field's long-term job is the Plants pillar. See **First Harvesting Route**.

**Is the harvesting field part of the Planet Map?**
No. They are separate places and they do not interact. The harvesting field is a fixed local grid around Nocturna Base, 8 rows (A to H) by 24 columns (1 to 24), addressed `A1` through `H24`; it is generated once per save and there is only one, so founding an outpost does not add another. The Planet Map is the planet itself, where sonar contacts, sites, outposts, and constructor-built machines live. A Harvester works only its own grid, a Rover or Pioneer only the Planet Map, and neither reaches the other.

### Scripting

**How do I get every machine of one type?**
`get_component("outpost_network").outposts()` gives every outpost, and each one has `.buildings(type_id)` returning `BuildingRef` snapshots with `.id`, `.name`, `.type_id`, `.powered`, and `.position`. Loop the outposts to cover the whole planet, and pass `ref.id` to `get_component()` for live type-specific reads. Two families are deliberately not in that list: mobile units come from `get_component("fleet").vehicles()` and `.drones()`, and fixed Harvesting-field machines such as Crop Automators, Grow Lamps, Sprinklers, and Dispensers come from `outpost.harvesting_machines(type_id)` on the home outpost, because they occupy field cells rather than outpost building slots.

**Do I copy my script into every new machine of the same type?**
No. Save the code as a named variant in the editor's **Variants** tab, then use **Apply to all**, which copies it into every matching machine and restarts the running ones. It is a one-time copy rather than a live link, so later edits to the variant do not reach machines already holding a copy. See **Script Variants**.

**How do I turn a machine on or off, or start and stop its script, from code?**
Those controls live on shared components, not on the machine. `get_component("power_control").set_powered(machine_id, on)` is the breaker: switching it off pauses the script, which resumes when power returns. `get_component("run_control")` is the Run and Stop buttons: `start(id)`, `stop(id)` (stays off until started again), `is_running(id)`, and `apply_variant(id, variant_id)` to switch a stopped machine to a saved variant. See **Power Control** and **Run Control**.

**Why does only one machine get my Signal Bus message?**
`receive()` consumes a message, so the first reader takes it and everyone else sees `"empty"`. Send once per consumer, or publish a broadcast value and read it with `latest()`, which does not consume. See **Signal Bus** for queues, broadcasts, and `wait()`.

**Can a script wait on two things at once? Are there threads?**
There are no threads, and none are needed. Every machine's script runs independently, so the usual answer is to split the work across the machines that own it and coordinate over the Signal Bus. Inside one script, `comms.wait(channel)` idles only that script until a message arrives, while the planet and every other script keep running.

**Does the language support classes?**
Yes, including `__init__`, instance and class attributes, inheritance, `super()`, `isinstance`, and `issubclass`. Inside a method `self` is the object, which never collides with a machine script's top-level `self`; pass the machine in if a method needs to drive it. `import json`, `re`, `random`, `heapq`, `functools`, and `dataclasses` are available too. See **Writing Classes**.

**Why is `self` undefined inside my Library?**
Library scripts run in their own shared scope, so `self` and `panel` are never defined there. Pass the component, or its id, into the helper as a parameter and call it from the machine script that owns the hardware. See **Imports & Libraries**.

*Guide / Tutorials*
