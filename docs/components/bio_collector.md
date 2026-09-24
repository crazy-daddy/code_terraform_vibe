# Component: bio_collector

> **Category:** Terraforming | **Component Name:** Bio Collector

Automates the Collect step of the biology loop, fetching a field specimen into its cargo slot on its own. It does nothing until a script tells it where to collect.

| Field | Value |
| --- | --- |
| Type | Atmosphere |
| Power in | -5 W (draws from grid) |

### How to obtain

1. Buy from the Shop for 3,000 cr.

**Returned by:** `self / get_component(id)`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

##### `.outpost: OutpostRef`

The outpost where this building is deployed. The returned `OutpostRef` includes its stable id, display name, biome, position, capacity, and `buildings()` query. Read the property again when you need current values.

- **Returns** `OutpostRef` for the outpost where this building is deployed.

##### `self.cargo: Specimen | None`

The collected `Specimen` waiting for transfer, or `None` if the slot is empty. Pre-analyze, `cargo.fragment_id` / `cargo.rarity` / `cargo.recipe` are `None`; `cargo.coords` and `cargo.distance` are always available.

- **Returns** The collected `Specimen`, or `None` if empty. Cleared when a Bio Lab takes it with `self.take_from(collector)`.

### Methods

##### `self.scan() → list[FragmentLocation]`

Lists fragment locations in this outpost's biome, nearest first. Each `FragmentLocation` includes `coords`, distance, and whether it has been cataloged. Cataloged locations also reveal their fragment id, name, and rarity; unknown locations leave those details as `None`. To identify an unknown location, collect it with `bio_collector.collect(location.coords)` and analyze it at a Bio Lab. Recipes and creature identity are not revealed here. Analyzed fragments also appear in `journal.cataloged_fragments(...)`.

- **Returns** List of `FragmentLocation`: every fragment in this outpost's biome with coords, straight-line distance, and `cataloged` (`True` after that fragment has been analyzed). Cataloged results expose `.fragment_id`, `.name`, and `.rarity`; unknown results keep them as `None`. Recipes and creature identity stay hidden. Sorted nearest-first.

##### `self.collect(coords: list[float]) → ActionResult` *(self only)*

Retrieve the fragment at `coords` from `scan()` and place it in the collector's cargo slot. The trip takes **~0.1-0.3 h** in every biome, depending on distance; the script pauses until collection finishes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `coords` | `list[float]` | World coordinates `[x, y]` from `scan()`. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"busy"` | transient | The component is already performing another operation. |
| `"cargo_occupied"` | rejection | The cargo area already contains an incompatible item or material. |
| `"invalid_coords"` | rejection | The supplied coordinates are invalid. |
| `"no_fragment"` | rejection | No fragment is available for the operation. |

##### `self.discard() → ActionResult` *(self only)*

Discard the specimen currently held in collector cargo. Use this when the collector picked up a specimen you do not want to send to a Bio Lab.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"empty"` | rejection | The relevant source or queue is empty. |
| `"busy"` | transient | The component is already performing another operation. |

##### `.peek_command() · .next_command() · .command_count() · .clear_commands()` *(self only)*

Read commands you send from the editor's **Commands** tab while this script runs. Identical on every scriptable machine, see the guide: Script Commands

*Components / Terraforming*
