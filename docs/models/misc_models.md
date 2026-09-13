# Models: Miscellaneous Game Objects & Sub-structures

Granular data models and return types extracted from `__builtins__.pyi`.

## `AlienTerminal`

```python
class AlienTerminal:
 """.terminal"""
 def guess(self, digits: _list[_int]) -> GuessResult:
 """Test a list of exactly 15 whole-number digits in the **1-5** range and return `GuessResult`. Exact-position matches are removed first; `.misplaced` then counts shared remaining occurrences without over-counting duplicates. Wrong argument or element types raise `TypeError`; wrong length, fractional values, or out-of-range digits raise `ValueError`."""
 ...
 length: _int
```

## `AnalyzeInfo`

```python
class AnalyzeInfo:
 """bio_lab.analyze().info after status == \"ok\""""
 fragment_id: Literal["gw_cranial_plate", "gw_caudal_fin", "gw_cardiac_node", "gw_jaw_fang", "gw_spinal_vertebra", "vc_dorsal_carapace", "vc_mandible_claw", "vc_antenna_cluster", "vc_walking_leg", "vc_eye_stalk", "oc_cranium", "oc_tentacle_arm", "oc_chitin_beak", "oc_ink_sac", "oc_lens_eye", "bw_skull", "bw_foreclaw", "bw_ribcage", "bw_hindlimb", "bw_tail_spike", "vd_bell", "vd_nematocyst", "vd_neural_mesh", "vd_photophore", "vd_tendril", "mh_fruiting_body", "mh_spore_pod", "mh_mycelium_root", "mh_chitin_node", "mh_stigmatic_disc", "hs_mandible", "hs_wing_membrane", "hs_thorax_plate", "hs_abdomen_segment", "hs_compound_eye", "ms_chelicera", "ms_leg_tarsus", "ms_pedipalp", "ms_abdomen_sclerite", "ms_eye_cluster", "hc_aperture_lip", "hc_shell_whorl", "hc_septum_plate", "hc_beak", "hc_tentacle_crown", "ma_cranial_papilla", "ma_cuticle_molt", "ma_ganglion_node", "ma_chitinous_seta", "ma_luminous_ring", "gm_compound_eye", "gm_folded_wing", "gm_raptorial_claw", "gm_abdominal_sheath", "gm_antennal_whip", "fs_calyx_plate", "fs_arm_segment", "fs_stalk_columnal", "fs_oral_tegmen", "fs_holdfast_rootlet", "sd_cranial_crest", "sd_wing_membrane", "sd_obsidian_scale", "sd_tail_barb", "sd_talon", "ce_stalked_eye", "ce_swimmeret_lobe", "ce_mouth_disc", "ce_great_appendage", "ce_cephalic_photophore", "st_scute_plate", "st_plastron_shard", "st_limb_claw", "st_beak", "st_carapace_neural", "vm_cephalic_horn", "vm_wing_sheet", "vm_gill_filament", "vm_tail_barb", "vm_ventral_photophore"]
 name: _str
 rarity: Literal["common", "uncommon", "rare", "legendary"]
 required_recipe: _dict[_str, Any]
 coords: _tuple[_float, _float]
 distance: _float
```

## `Analyzer`

```python
class Analyzer:
 """.analyzer"""
 def read(self, group: _list[Any]) -> _str:
 """Read a list of exactly five string tokens and return the single token they were expanded from. A non-list argument or non-string element raises `TypeError`; the wrong length or an unrecognized group raises `ValueError`."""
 ...
```

## `Arbiter`

```python
class Arbiter:
 """.arbiter"""
 def new_game(self) -> ActionResult[Literal["ok", "in_progress"]]:
 """Start a fresh 3×3 game on an empty board; you move first. After a finished game this call pauses about half a second before the next board is ready. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def restart(self) -> ActionResult[Literal["ok"]]:
 """Abandon any game in progress and start fresh; you move first. Abandoning a game mid-play counts as a non-win and resets your current-run streak to 0. Like new_game(), it pauses about half a second between games. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def play(self, cell: _int) -> ActionResult[Literal["ongoing", "win", "loss", "draw", "occupied", "no_game"]]:
 """Place your mark in a whole-number cell in the **0-8** range (row-major), then the Arbiter responds. Three marks in a row, column, or diagonal wins. A non-number cell raises `TypeError`; a non-finite, fractional, or out-of-range cell raises `ValueError` before game state is considered. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def board(self) -> _list[_str]:
 """The 9 board cells as a list, index 0-8 row-major. Each cell is \"\" (empty), \"you\", or \"arbiter\"."""
 ...
 def result(self) -> Literal["ongoing", "win", "loss", "draw", "no_game"]:
 """Current game outcome: \"ongoing\", \"win\", \"loss\", \"draw\", or \"no_game\" (no game started yet)."""
 ...
 def streak(self) -> _int:
 """Consecutive wins in the current script run. Resets to 0 on a loss, draw, abandonment, or fresh script run."""
 ...
 def target(self) -> _int:
 """The consecutive-win count needed to complete the contract."""
 ...
 def token(self) -> _str:
 """The passcode to transmit: a non-empty string once streak() reaches target(), otherwise an empty string."""
 ...
```

## `Battery`

```python
class Battery:
 """self.battery (vehicles)"""
 def level(self) -> _float:
 """Charge level as a fraction, **0-1**."""
 ...
 def wh(self) -> _float:
 """Current charge in Wh (across all batteries)."""
 ...
 def capacity(self) -> _float:
 """Maximum capacity in Wh."""
 ...
 def holders(self) -> _list[Holder]:
 """List of every Battery Holder currently mounted on the vehicle. Empty for the Rover (sealed battery)."""
 ...
```

## `BatteryComponent`

```python
class BatteryComponent(Component):
 """Battery: Base-station energy storage. It fills on its own when generation runs a surplus and drains when the grid falls short. If it empties, machines shut off and their scripts pause."""
 name: _str
 outpost: OutpostRef
 def get_level(self) -> _float:
 """Current stored energy in watt-hours (**Wh**). Drops when consumption exceeds generation, rises when generation exceeds consumption, and stays level when they are equal. Approaching **0** is a red flag, the grid is about to brown out."""
 ...
 def get_capacity(self) -> _float:
 """Total battery capacity in watt-hours (**Wh**). Queryable rather than hardcoded so future upgrades don't break scripts. Use with `get_level()` for charge percent."""
 ...
```

## `Bounds`

```python
class Bounds:
 """planet.get_bounds()"""
 min_x: _float
 max_x: _float
 min_y: _float
 max_y: _float
```

## `BroadcastInfo`

```python
class BroadcastInfo:
 """comms.latest_info(channel); comms.wait_broadcast(channel).broadcast after status == \"ok\""""
 value: Any
 sender: _str | None
 age_seconds: _float | None
```

## `BulkLiquidReservoir`

```python
class BulkLiquidReservoir(Component):
 """Large Liquid Tank: A big passive tank holding 1,000 t of one liquid. Like a Liquid Tank it sticks to the first fluid piped in, and only lets go once it has drained completely."""
 name: _str
 outpost: OutpostRef
 def fluid(self) -> Literal["", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"]:
 """The latched liquid id (e.g. `\"water\"`, `\"oil\"`, `\"frozen_essence\"`), or `\"\"` while empty. The tank commits to the first liquid it receives and holds only that until it drains to **0**, then re-latches."""
 ...
 def level(self) -> _float:
 """Current liquid stored in tons, from **0** to `capacity()`. At **0** the tank unlatches and can accept a different liquid next."""
 ...
 def capacity(self) -> _float:
 """Maximum tons this tank holds. Queryable rather than hardcoded. Use with `level()` or `fill_pct()` for threshold checks."""
 ...
 def fill_pct(self) -> _float:
 """Fill fraction (**0.0-1.0**), shortcut for `level() / capacity()`. Common threshold in supply-control scripts."""
 ...
 def inflow_rate(self) -> _float:
 """Liquid arriving in t/h. **0** = no upstream flow."""
 ...
 def outflow_rate(self) -> _float:
 """Liquid leaving in t/h. **0** = no downstream consumer drawing."""
 ...
 def is_full(self) -> _bool:
 """`True` when `level() == capacity()`; upstream source is backpressured."""
 ...
 def is_empty(self) -> _bool:
 """`True` when `level() == 0`; the tank is unlatched and downstream consumers are starved."""
 ...
 liquid_in: FluidPort
 liquid_out: FluidPort
 water_in: FluidPort
 water_out: FluidPort
 oil_in: FluidPort
 oil_out: FluidPort
 frozen_essence_in: FluidPort
 frozen_essence_out: FluidPort
 coastal_essence_in: FluidPort
 coastal_essence_out: FluidPort
 geothermal_essence_in: FluidPort
 geothermal_essence_out: FluidPort
 volcanic_essence_in: FluidPort
 volcanic_essence_out: FluidPort
 deep_essence_in: FluidPort
 deep_essence_out: FluidPort
 brine_in: FluidPort
 brine_out: FluidPort
 raw_cryofluid_in: FluidPort
 raw_cryofluid_out: FluidPort
 cryofluid_in: FluidPort
 cryofluid_out: FluidPort
 raw_quicksilver_in: FluidPort
 raw_quicksilver_out: FluidPort
 quicksilver_in: FluidPort
 quicksilver_out: FluidPort
```

## `ChamberSample`

```python
class ChamberSample:
 """bio_luminizer.chamber"""
 fragment_id: Literal["gw_caudal_fin", "vc_mandible_claw", "oc_tentacle_arm", "bw_foreclaw", "vd_nematocyst", "mh_spore_pod", "hs_wing_membrane", "ms_leg_tarsus", "hc_shell_whorl", "ma_cuticle_molt", "gm_folded_wing", "fs_arm_segment", "sd_wing_membrane", "ce_swimmeret_lobe", "st_plastron_shard", "vm_wing_sheet"]
 name: _str
 glow: _tuple[_float, _float, _float]
```

## `ChargingStation`

```python
class ChargingStation(Component):
 """Vehicle Charging Station: Grid-powered fleet charging: Mk I provides **1 bay / 30 W**, Mk II **2 bays / 120 W**, and Mk III **4 bays / 240 W**. Idle bays pool onto one vehicle; several vehicles share the budget. A script queues charging or dispatches rescue."""
 name: _str
 outpost: OutpostRef
 def get_docked(self) -> _list[_str]:
 """List of vehicle instance ids parked inside the station's local service pad plus its **~2 m** margin, or inside the owning Outpost's common service area. Returns ids, not vehicles; dereference each via `get_component(id)` to read battery state, cargo, or anything else. Empty list means no vehicles docked. Call each iteration; the list can change between ticks as vehicles drive in or out."""
 ...
 def charge(self, vehicle_id: _str, target_level: _float = ...) -> ActionResult[Literal["charging", "queued", "target_reached", "not_docked", "station_offline", "invalid"]]:
 """Queue a docked rover or Pioneer to charge until its battery reaches `target_level` (greater than **0** and at most **1**, defaults to **1.0**). The station decides whether it starts immediately or waits behind another vehicle: Mk I charges one vehicle at a time, Mk II two, Mk III four. The fewer vehicles active, the faster each charges (idle bays pool). Example: `self.charge(\"pioneer_1\", 0.8)` means 'charge this vehicle until it reaches 80%'. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def stop(self, vehicle_id: _str) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
 """Remove a vehicle from this station's charge queue. It does not move the vehicle or change its current battery. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
 """Clear every queued charge job on this station. Rescue-drone missions are separate and are not cancelled by this. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
 def get_active(self) -> _list[_str]:
 """List of vehicle ids currently occupying active charging bays. Mk I returns at most one id, Mk II two, Mk III four. These are the vehicles sharing the station's pooled budget this tick."""
 ...
 def get_queue(self) -> _list[_str]:
 """List of vehicle ids in charge-queue order. The first `get_bay_count()` entries are the ones that can be active right now, assuming they are still docked and below their target."""
 ...
 def status(self, vehicle_id: _str) -> _dict[_str, Any]:
 """Detailed status for one vehicle: a dict with `state` (`\"charging\"`, `\"queued\"`, `\"docked\"`, `\"target_reached\"`, `\"not_docked\"`, `\"station_offline\"`, or `\"missing\"`), `target_level`, `battery_wh`, `capacity_wh`, `rate_w` (the pooled watts this vehicle is actually receiving, rises as fewer vehicles share the bays), `bay_index`, and `queue_index`. Use this for dashboards or queue managers."""
 ...
 def tier(self) -> _int:
 """Permanently installed Charging Station tier as an integer (**1-3**). Mk II raises bay count and bay rate; Mk III raises bay count again."""
 ...
 def get_bay_count(self) -> _int:
 """Number of simultaneous vehicle charging bays. Mk I is **1**, Mk II **2**, Mk III **4**."""
 ...
 def get_bay_rate(self) -> _float:
 """Watts pushed by a single bay (**30 W** Mk I, **60 W** Mk II/III). With bay pooling a lone vehicle draws every idle bay, so its actual rate is up to `get_bay_count() × get_bay_rate()`, read `get_charge_rate(id)` for what a specific vehicle is really getting. The station's total grid draw is `get_bay_count() × get_bay_rate()` whenever any vehicle is charging, plus rescue-drone draw if a rescue is out."""
 ...
 def get_charge_rate(self, vehicle_id: _str) -> _float:
 """Actual watts being pushed into the specified vehicle right now, the station's total budget (`get_bay_count() × get_bay_rate()`) split evenly across every active vehicle. A lone vehicle gets the whole budget (Mk III: **240 W**); the more vehicles charging, the lower each one's share. Returns **0** if the vehicle is not occupying an active bay."""
 ...
 def dispatch_rescue(self, vehicle_name: _str, target_level: _float = ...) -> ActionResult[Literal["ok", "already_dispatched", "station_offline", "not_found", "invalid"]]:
 """Send a field-service drone to a Rover or Pioneer by display name or id. `target_level` is a battery fraction greater than **0** and at most **1** and defaults to **1.0**. Dispatch stops the target vehicle so the drone can reach it. The station must be powered at launch, but the drone can finish its mission through a later outage. If the target reaches a powered Charging Station first, the remaining request joins that station's queue. Only one rescue can run at a time; call `cancel_rescue()` to recall it. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def cancel_rescue(self) -> ActionResult[Literal["ok", "not_found"]]:
 """Recall this station's active field-service drone. If the drone was outbound or trickle-charging, the target vehicle is released immediately and keeps any charge already delivered while the drone returns to the station. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_rescuing(self) -> _bool:
 """`True` while a rescue drone is deployed (out, at the target, or returning). A recalled drone still counts as rescuing until it reaches the station, but the target vehicle is released as soon as `cancel_rescue()` succeeds. Use before `dispatch_rescue()` to avoid the `\"already_dispatched\"` rejection: `if not self.is_rescuing(): self.dispatch_rescue(name)`. Exactly one drone at a time, queue rescues manually if you need more."""
 ...
 def get_rescue_target(self) -> _str:
 """Display name of the vehicle currently being rescued, or empty string if the drone is idle. Use for dashboards (\"rescuing Rover 1\") or to decide whether to wait vs send a different vehicle to pick up slack."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `Clock`

```python
class Clock(Component):
 """Clock: The ship's clock. It tracks the time of day, the day count, and the sun's position, everything a script needs for day-night timing and solar tracking."""
 name: _str
 def get_time(self) -> _tuple[_int, _int, _int]:
 """Current time as a **3-element list** `[hours, minutes, seconds]` in 24-hour format. Index with `t[0]`, `t[1]`, `t[2]`. Use for time-of-day branches or to wait for specific hours."""
 ...
 def get_day(self) -> _int:
 """Current day number, starts at **1** and increments when the in-world clock rolls past midnight. Use for daily-budget logic (e.g. reset counters at the start of each day) or to detect day transitions for machines like the Heat Generator whose state changes per day."""
 ...
 def get_time_of_day(self) -> Literal["dawn", "day", "dusk", "night"]:
 """Current daylight phase as a string: `\"dawn\"`, `\"day\"`, `\"dusk\"`, or `\"night\"`. This is the simulation phase used by solar/day-night logic; the header may further label `\"day\"` as Morning/Afternoon/Evening for flavor."""
 ...
 def get_elevation(self) -> _float:
 """Sun's elevation above the horizon (**0-90** degrees). **0** at night, rises to **90** at solar noon (equator), back to **0** at dusk. Solar panels peak when their tilt complements the current elevation."""
 ...
 def tick(self) -> _int:
 """Deterministic simulation tick since save start. At normal speed the simulation grants a fresh script step budget every tick (**10 ticks/sec**, so one tick is **0.1** simulation seconds). Use tick deltas for profiling script timing instead of wall-clock milliseconds."""
 ...
 def elapsed_seconds(self) -> _float:
 """Elapsed simulation seconds since save start. This is the same time base that `sleep(seconds)` waits against, not browser wall-clock time."""
 ...
 def elapsed_game_hours(self) -> _float:
 """Elapsed world-clock hours since save start. Useful for rate calculations and logs that should follow the compressed day/night cycle instead of real seconds."""
 ...
 def real_seconds_per_hour(self) -> _float:
 """Number of real seconds in one world-clock hour. The day cycle compresses **24** world-clock hours into a fixed real-time window, so `sleep(clock.real_seconds_per_hour())` waits exactly one world-clock hour and multiplying by **24** waits a full day. Lets scripts express world-time delays without hardcoding the conversion."""
 ...
```

## `Commander`

```python
class Commander(Component):
 """Commander: Read the player's name and current credits with `get_component(\"me\")` or `get_component(\"commander\")`. Scripts cannot change either value."""
 name: _str
 def get_name(self) -> _str:
 """Your commander name as a string. Set during initial character creation (or default). Use for personalized dashboard messages."""
 ...
 def get_credits(self) -> _float:
 """Current credit balance. Changes when `shop.buy()` / `shop.sell()` run, Bio Exchanges pay out, contract transmissions succeed, and Orders complete. Use as a gate before expensive `shop.buy()` calls."""
 ...
```

## `Comms`

```python
class Comms(Component):
 """Signal Bus: Coordinates scripts through shared JSON-safe values. Access the Signal Bus with `get_component(\"comms\")` after its research unlocks. Use `send()` and `receive()` for work that should be handled once; use `broadcast()` and `latest()` for the newest shared value."""
 name: _str
 def send(self, channel: _str, value: Any) -> SendResult[Literal["ok", "invalid_channel", "channel_limit", "queue_full", "id_exhausted", "invalid_value"]]:
 """Add a JSON-safe value to a named channel queue. Keep the send receipt to identify or cancel that exact request later, even when several requests contain identical values. Channel ids may contain letters, numbers, `_`, `.`, `:`, and `-`. Use queues for work items that should be handled once. Fixed result contract: `SendResult`; branch on `.status` and read `.message`. Payload fields: `.message_id`."""
 ...
 def receive(self, channel: _str, message_id: _int | None = ...) -> ReceiveResult[Literal["ok", "empty", "not_found", "invalid_channel"]]:
 """Take one queued message. Omit `message_id` or pass `None` to take the oldest, or supply a message id to take exactly that job. Selection and removal happen together, so only one competing receiver can take it. Other queued messages keep their order, and broadcasts are preserved. Use `pending()` to choose work by priority, location, or capability before receiving it. Fixed result contract: `ReceiveResult`; branch on `.status` and read `.message`. Payload fields: `.packet`."""
 ...
 def wait(self, channel: _str) -> ReceiveResult[Literal["ok", "invalid_channel"]]:
 """Wait for and take the oldest queued message. If the queue is empty, only this script pauses until work is available; the game and other scripts keep running. Messages already queued are taken immediately. Broadcasts do not satisfy the wait. Pausing preserves the wait, and stopping the script abandons it without consuming a message. Fixed result contract: `ReceiveResult`; branch on `.status` and read `.message`. Payload fields: `.packet`."""
 ...
 def wait_any(self, channels: _list[Any]) -> WaitAnyResult[Literal["ok", "invalid_channel"]]:
 """Wait for and take one queued message from any listed channel. Channels listed first have priority whenever work is selected; each channel keeps its oldest-first order. If every queue is empty, only this script waits. Broadcasts do not satisfy the wait. The channel list is copied when called, and repeated names are considered once at their first position. Pausing preserves the wait; stopping abandons it without taking work. Fixed result contract: `WaitAnyResult`; branch on `.status` and read `.message`. Payload fields: `.channel` and `.packet`."""
 ...
 def wait_broadcast(self, channel: _str) -> WaitBroadcastResult[Literal["ok", "invalid_channel"]]:
 """Wait for the next broadcast on a channel. Every script already waiting captures that publication, including a repeated value or None. Existing broadcasts do not satisfy a new wait. Only this script pauses; queued messages remain untouched. The first publication is retained even if another broadcast follows or the channel is cleared. Pausing retains that signal for resume; stopping abandons the wait. Fixed result contract: `WaitBroadcastResult`; branch on `.status` and read `.message`. Payload fields: `.broadcast`."""
 ...
 def pending(self, channel: _str) -> _list[CommsMessage]:
 """Inspect all waiting messages on a channel in receive order without consuming them. Use the snapshot to display pending work in a Control Room card or total outstanding requests. Each message and its nested value are copied; editing the returned list or messages does not change the Signal Bus. Broadcasts and messages already received are excluded. Read again to refresh the snapshot."""
 ...
 def cancel(self, channel: _str, message_id: _int) -> ActionResult[Literal["ok", "not_found", "invalid_channel"]]:
 """Cancel one waiting message using its send receipt's `.message_id` or its `.id` from `pending(channel)`. Use it to remove an obsolete request or add a Cancel button to a Control Room job board. Other messages keep their ids, values, and receive order, including messages sent after the snapshot. The latest broadcast is preserved. Cancellation only removes queued work; it cannot stop a worker that has already received the message. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def update(self, channel: _str, message_id: _int, value: Any) -> ActionResult[Literal["ok", "not_found", "invalid_channel", "invalid_value"]]:
 """Replace the complete value of one waiting message. Use its send receipt or an id from `pending()` to edit a delivery, priority, or destination from a script or Control Room card. The id, queue position, original sender, and send time stay unchanged. Replacement happens in one operation and works even when the queue is full. Messages already received cannot be edited. Read `pending()` again to refresh an earlier snapshot. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def broadcast(self, channel: _str, value: Any) -> ActionResult[Literal["ok", "invalid_channel", "channel_limit", "invalid_value"]]:
 """Store a channel's latest JSON-safe value without consuming queue slots. Use broadcasts for shared telemetry like fleet mode, target sector, or current priority. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def latest(self, channel: _str) -> Any:
 """Return the most recent value broadcast on a channel, or `None` if the channel has no latest value. Reading latest does not consume it."""
 ...
 def latest_info(self, channel: _str) -> BroadcastInfo | None:
 """Inspect the latest broadcast, who published it, and how long ago it was updated. Use the snapshot to detect outdated worker reports or show freshness in a Control Room card. Reading does not consume messages or change the channel. Read again to refresh the value and age."""
 ...
 def queue_size(self, channel: _str) -> _float:
 """Number of queued messages waiting on the channel."""
 ...
 def channels(self) -> _list[_str]:
 """All channel ids that currently have queued messages or a latest broadcast value."""
 ...
 def clear(self, channel: _str) -> CountResult[Literal["ok", "no_op", "invalid_channel"]]:
 """Remove a channel's queued messages and latest broadcast. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `CommsMessage`

```python
class CommsMessage:
 """comms.pending(channel) list entries; comms.receive(channel).packet, comms.wait(channel).packet, or comms.wait_any(channels).packet after status == \"ok\""""
 id: _int
 sender: _str
 tick: _int
 value: Any
```

## `Component`

```python
class Component:
 """get_component / self"""
 id: _str
```

## `Console`

```python
class Console(Component):
 """Console: Writes structured script output to the same Console used by `print()`. Access it with `get_component(\"console\")`; no research is required. Messages can have a severity, named channel, color, and timestamp."""
 name: _str
 def print(self, message: Any, level: _str = ..., channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
 """Print a line with full control. `level` is `info` / `warn` / `error` / `debug` (which feed the WARNINGS / ERRORS filters), or any other non-empty string for a custom level shown as a colored badge. An empty level behaves like `info`. `channel` routes the line to a named tab (empty = the main stream). `color` is a theme token (`\"warning\"`, `\"success\"`, `\"accent\"`), which recolors with the theme, or any CSS color: hex (`\"#aabbcc\"`), `\"rgb(255,100,0)\"`, `\"hsl(30,100%,50%)\"`, or a name like `\"orange\"`. A true `timestamp` value prepends the game time-of-day. Example: `get_component(\"console\").print(\"Overheat\", \"alert\", \"alarms\", \"warning\", True)`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def info(self, message: Any, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
 """Print an info line (the default level). Its optional channel, color, and timestamp parameters behave like those on `print`. Equivalent to `print(message)`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def warn(self, message: Any, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
 """Print a warning line, appears in the console's WARNINGS filter. Its optional channel, color, and timestamp parameters control routing and presentation. For an interruptive popup instead, use the global `notify(text, \"warn\")`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def error(self, message: Any, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
 """Print an error line, appears in the console's ERRORS filter. Its optional channel, color, and timestamp parameters control routing and presentation. This is your own message at error severity, not an uncaught exception. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def debug(self, message: Any, channel: _str = ..., color: _str = ..., timestamp: _bool = ...) -> ActionResult[Literal["ok"]]:
 """Print a low-priority debug line, hidden from the ALL view unless the player enables debug output. Its optional channel, color, and timestamp parameters control routing and presentation. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def now(self) -> _str:
 """Return the current game time-of-day as a `\"HH:MM:SS\"` string, for building your own line prefixes when you want full control over formatting."""
 ...
 def clear(self, channel: _str = ...) -> ActionResult[Literal["ok"]]:
 """Clear output produced by this script. With a `channel` argument, clears only this script's lines in that channel; with no argument, clears all output from this script. Other scripts and system messages are preserved. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
```

## `Construction`

```python
class Construction:
 """.pending_constructions() / .active_constructions() / .paused_constructions()"""
 id: _str
 kind: Literal["pipe", "power_line", "gas_bridge", "liquid_bridge", "power_bridge", "deconstruct", "outpost", "thermal_cap", "water_pump", "oil_pump", "exotic_gas_cap", "exotic_spring_tap", "mining_drill", "mining_drill_industrial", "mining_drill_heavy"]
 medium: Literal["gas", "liquid", "power"] | None
 position: Position
 progress: _float
 required_item: _str | None
 required_count: _int
```

## `ConstructionBlueprint`

```python
class ConstructionBlueprint(Component):
 """Construction Blueprint: Manages planned construction and removal work. Plan Mode and scripts share the same queue. Scripts can place structures, pipes, power lines, and bridges, or mark existing structures for removal. Planning creates the map marker immediately without needing a vehicle at the site. A Pioneer with a Constructor Module must still travel to each job and call `self.constructor.execute(construction.id)` to perform the work."""
 name: _str
 def plan_structure(self, kind: _str, x: _float, y: _float, rotation: _int = ...) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_kind", "invalid_rotation", "out_of_bounds", "wrong_target", "unsurveyed_target", "too_hard", "target_claimed", "occupied", "clearance", "blocked"]]:
 """Create one point-structure construction ghost from script coordinates. Supported kinds are `\"outpost\"`, `\"thermal_cap\"`, `\"water_pump\"`, `\"oil_pump\"`, `\"exotic_gas_cap\"`, `\"exotic_spring_tap\"`, `\"mining_drill\"`, `\"mining_drill_industrial\"`, and `\"mining_drill_heavy\"`. Drill kinds require their matching Earth Order kit recipe. Coordinates snap to the map grid. Extraction structures snap to the exact matching surveyed feature, while Outposts use the snapped footprint anchor. The optional clockwise rotation is `0`, `90`, `180`, or `270`. The ghost enters the shared queue immediately; a Pioneer still constructs it later. Fixed result contract: `BlueprintPlanResult`; branch on `.status` and read `.message`. Payload fields: `.blueprint_ids`."""
 ...
 def plan_pipe(self, medium: _str, x1: _float, y1: _float, x2: _float, y2: _float) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_medium", "out_of_bounds", "invalid_route", "blocked", "already_exists"]]:
 """Create pipe construction jobs from script coordinates. Requires Constructor Module research. `medium` is `\"gas\"`, `\"liquid\"`, or a registered fluid id such as `\"steam\"`, `\"water\"`, or `\"oil\"`. Coordinates snap to tile-center lanes. A field structure uses its site coordinates. An internal outpost machine uses its owning outpost as the utility anchor, so route to a point in `building.outpost`'s footprint, such as `[building.outpost.x, building.outpost.y]`, not to the vehicle docking point in `building.position`. Existing matching pieces are reused automatically. Fixed result contract: `BlueprintPlanResult`; branch on `.status` and read `.message`. Payload fields: `.blueprint_ids`."""
 ...
 def plan_power_line(self, x1: _float, y1: _float, x2: _float, y2: _float) -> BlueprintPlanResult[Literal["ok", "locked", "out_of_bounds", "invalid_route", "blocked", "already_exists"]]:
 """Create power-line construction jobs from script coordinates. Requires Constructor Module research. Coordinates snap to tile-center lanes; off-axis paths choose the valid L-shaped elbow with the least new construction. A field structure uses its site coordinates. An internal outpost machine uses its owning outpost as the utility anchor, so route to a point in `building.outpost`'s footprint, such as `[building.outpost.x, building.outpost.y]`, not to the vehicle docking point in `building.position`. Existing matching pieces are reused automatically. Fixed result contract: `BlueprintPlanResult`; branch on `.status` and read `.message`. Payload fields: `.blueprint_ids`."""
 ...
 def plan_bridge(self, medium: _str, x: _float, y: _float, axis: _str) -> BlueprintPlanResult[Literal["ok", "locked", "invalid_medium", "invalid_axis", "out_of_bounds", "blocked", "already_exists"]]:
 """Create one utility bridge job from script coordinates. Requires Constructor Module research. `medium` is `\"gas\"`, `\"liquid\"`, `\"power\"`, or a registered fluid id. `x`/`y` are the bridge center tile and `axis` is `\"horizontal\"` or `\"vertical\"`. Fixed result contract: `BlueprintPlanResult`; branch on `.status` and read `.message`. Payload fields: `.blueprint_ids`."""
 ...
 def mark_deconstruct(self, x: _float, y: _float, layer: _str = ..., target_id: _str = ...) -> BlueprintPlanResult[Literal["ok", "locked", "nothing_here", "already_queued", "ambiguous_target", "out_of_bounds", "invalid_layer", "blocked"]]:
 """Mark built infrastructure or a normal map building at the coordinate for deconstruction. Requires Constructor Module research. Base and Outposts are protected. When several independent map layers overlap, choose the `\"building\"`, `\"gas\"`, `\"liquid\"`, or `\"power\"` layer; the default `\"auto\"` requires an unambiguous target. At a same-layer junction, provide the optional exact target id. A Pioneer still executes the job with `self.constructor.execute(id)` at the job's reported `position`. Fixed result contract: `BlueprintPlanResult`; branch on `.status` and read `.message`. Payload fields: `.blueprint_ids`."""
 ...
 def cancel(self, blueprint_id: _str) -> ActionResult[Literal["ok", "not_found", "worker_not_present", "no_cargo_space", "construction_dependency"]]:
 """Cancel a queued, active, or paused construction blueprint by id. Unpaid jobs cancel immediately. A paid job keeps its material at the build site: park a Pioneer there to recover it into cargo. A failed recovery leaves the job and material intact. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def pending_constructions(self) -> _list[Construction]:
 """Returns blueprints awaiting a worker as `list<Construction>`. Drawn pipe/power paths and marked deconstruction targets are split into independent jobs, usually in placement order. Pass each `c.id` to `self.constructor.execute(c.id)` to build or deconstruct it. Read `c.required_item` and `c.required_count` to load the exact cargo before executing; never infer material from `c.kind`. Filter by `c.kind` to specialize a Pioneer's role, then use `c.medium` to distinguish `\"gas\"`, `\"liquid\"`, and `\"power\"` utility jobs. Point structures have `c.medium == None`; see `Construction.kind` for the full kind list."""
 ...
 def active_constructions(self) -> _list[Construction]:
 """Returns blueprints currently being built (a Pioneer is working). Useful for monitor scripts, read `c.progress` to see how far along."""
 ...
 def paused_constructions(self) -> _list[Construction]:
 """Returns blueprints started then abandoned (worker died, ran out of fuel, or script stopped). Any Pioneer can resume by navigating to `c.position` and calling `self.constructor.execute(c.id)`."""
 ...
```

## `CoreDevice`

```python
class CoreDevice:
 """.device"""
 def submit(self, index: _int, bytes: _list[_int]) -> ActionResult[Literal["locked", "rejected"]]:
 """Submit a rebuilt core for whole-number slot `index` (0-9). Wrong container or element types raise `TypeError`; a fractional or out-of-range index, wrong list length, or numeric value outside the **0-255** range raises `ValueError`. A rejected submission does not lock the slot. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def recovered(self) -> _int:
 """How many of the 10 cores are locked in the current script run. A fresh run starts at 0."""
 ...
 def target(self) -> _int:
 """The number of cores you must recover to complete the contract: 10."""
 ...
 def token(self) -> _str:
 """The passcode to transmit: a non-empty string once recovered() reaches target(), otherwise an empty string."""
 ...
```

## `CropAutomator`

```python
class CropAutomator(Component):
 """Crop Automator: Queues harvest, plant, and treatment jobs across up to 24 other cells in a centered 5 by 5 service area, then executes one job at a time with a short pause between them."""
 name: _str
 def harvest(self, sector: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range"]]:
 """Submit one harvest job for a covered sector. Submission is immediate; valid field work later takes **0.1 hours**. Missing output space pauses this FIFO head without bypassing it. A target mismatch is terminal, takes no work time, and advances the queue. Fixed result contract: `JobReceipt`; branch on `.status` and read `.message`. Payload fields: `.job_id` and `.queue_position`."""
 ...
 def plant(self, sector: _str, seed_id: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range", "invalid_seed"]]:
 """Submit one planting job with a specific species seed. Submission is immediate and does not require the seed to be loaded yet. The serial executor pauses at this FIFO head until the seed is present, then spends **0.1 hours** and rechecks the target before committing. Fixed result contract: `JobReceipt`; branch on `.status` and read `.message`. Payload fields: `.job_id` and `.queue_position`."""
 ...
 def apply(self, sector: _str, item_id: _str) -> JobReceipt[Literal["queued", "queue_full", "not_placed", "out_of_range", "invalid_material"]]:
 """Submit one Fertilizer Mk I/II/III or Growth Accelerant job. Submission is immediate and does not require the material to be loaded yet. The serial executor pauses at this FIFO head until the material is present, then spends **0.1 hours** and rechecks the target before committing. Fixed result contract: `JobReceipt`; branch on `.status` and read `.message`. Payload fields: `.job_id` and `.queue_position`."""
 ...
 def position(self) -> _str:
 """Grid sector occupied by this automator. Jobs can target up to 24 other cells in its centered 5 by 5 service area."""
 ...
 def cell(self, sector: _str) -> Cell | None:
 """Read one sector inside this automator's service area as a `Cell` snapshot, covering plant, status, growth, conditions, and remaining treatment hours. The addressable set is exactly the set `harvest()`, `plant()`, and `apply()` accept, so a sector this returns `None` for is one no job can target either."""
 ...
 def cells(self) -> _list[Cell]:
 """Read every sector this automator serves as a list of `Cell` snapshots, for sweeping the whole service area in one pass. Unscanned natural ground reports status `\"unknown\"`."""
 ...
 def status(self) -> Literal["not_placed", "no_power", "working", "no_seed", "no_material", "output_full", "results_full", "idle"]:
 """Exact executor state: `\"not_placed\"`, `\"no_power\"`, `\"working\"`, `\"no_seed\"`, `\"no_material\"`, `\"output_full\"`, `\"results_full\"`, or `\"idle\"`."""
 ...
 def current_job(self) -> CropJob | None:
 """Active FIFO head as a `CropJob`, including action, target, progress, and blocker. Returns `None` while idle."""
 ...
 def get_queue(self) -> _list[CropJob]:
 """Snapshot of pending `CropJob` values in exact FIFO order (first in, first out). The active job is reported separately by `current_job()`."""
 ...
 def queue_count(self) -> _int:
 """Total unfinished jobs, counting the active job and every pending job. Maximum **50**."""
 ...
 def result_count(self) -> _int:
 """Completed terminal results waiting in the result inbox. At **50**, execution pauses until results are consumed."""
 ...
 def next_result(self) -> CropJobResult[Literal["ok", "partial", "empty", "out_of_range", "no_plant", "not_mature", "no_forage", "not_empty", "base_sector", "already_mature", "tier_conflict", "invalid_seed", "invalid_material"]]:
 """Consume the oldest terminal result. An empty inbox is reported without changing machine state. Fixed result contract: `CropJobResult`; branch on `.status` and read `.message`. Payload fields: `.job_id`, `.action`, `.sector`, `.item_id`, `.collected`, and `.discarded`."""
 ...
 def cancel_job(self, job_id: _int) -> ActionResult[Literal["ok", "not_found"]]:
 """Cancel one active or pending job by id. Canceling active work discards only its progress; inputs and field state remain unchanged. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def move_job(self, job_id: _int, position: _int) -> ActionResult[Literal["ok", "not_found", "invalid"]]:
 """Move one unfinished job to a one-based execution position, counting the active job first and then pending jobs. Reordering only pending work preserves active progress. While a job is active, changing which job is first preempts the arm: the displaced job keeps its id and request, loses its progress, and creates no terminal result. Position **1** is first; `queue_count()` is the last position. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_queue(self) -> CountResult[Literal["ok", "no_op"]]:
 """Cancel the active job and every pending job. Completed results remain available through `next_result()`. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `CropJob`

```python
class CropJob:
 """Crop Automator current_job() and get_queue()"""
 id: _int
 action: Literal["harvest", "plant", "apply"]
 sector: _str
 item_id: _str | None
 state: Literal["working", "blocked", "queued"]
 progress: _float
 blocker: Literal["not_placed", "no_power", "no_seed", "no_material", "output_full", "results_full"] | None
```

## `Dispenser`

```python
class Dispenser(Component):
 """Dispenser: Salts the four orthogonally adjacent field cells (directly above, below, left, and right) while powered, supplied, and enabled."""
 name: _str
 def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
 """Command salting on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_enabled(self) -> _bool:
 """`True` when the running script has commanded salting on."""
 ...
 def is_active(self) -> _bool:
 """`True` when commanded on with power and salt available."""
 ...
 def is_supplied(self) -> _bool:
 """`True` when the dispenser is commanded on, powered, and has salt in its input buffer. If disabled, unpowered, or empty, covered cells lose `salted`."""
 ...
 def status(self) -> Literal["not_placed", "disabled", "no_power", "no_salt", "active"]:
 """Exact operating state: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"`, `\"no_salt\"`, or `\"active\"`."""
 ...
 def buffer(self) -> _float:
 """Fraction of the onboard salt buffer currently filled (**0-1**). It drops while dosing cells and refills through `self.input`."""
 ...
 def tier(self) -> _int:
 """Always **1**. The Dispenser ships at Mk I and has no upgrade pack; salt providers don't tier, so every deployed Dispenser reads **1**."""
 ...
 def position(self) -> _str:
 """Grid sector occupied by this dispenser, such as `\"E14\"`."""
 ...
 input: InputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `EssenceLiquifier`

```python
class EssenceLiquifier(Component):
 """Essence Liquifier: Renders native life-form samples down into their biome's essence fluid. It only accepts life forms from its own outpost's biome, and produces that biome's essence."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 def essence_rate(self) -> _float:
 """Current biome essence output, in **t/h**. At 100% outpost efficiency, the Essence Liquifier has a base **1 t/h** life-form intake. This readout applies both outpost efficiency and the loaded life form's rarity yield (common **×5**, uncommon **×10**, rare **×25**), and reads **0** when the machine cannot run or buffer its next whole output."""
 ...
 def yield_multiplier(self) -> _float:
 """Unscaled essence tons produced per ton of the life form currently in the input bin: **5** for a common life form, **10** uncommon, **25** rare. Returns **0** when the input is empty. At 100% outpost efficiency, `essence_rate()` equals this multiplier while the machine is powered, fed, and able to buffer its next whole output; overcrowding can reduce the actual output rate."""
 ...
 def is_stalled(self) -> _bool:
 """`True` whenever `stall_reason()` is not `\"ok\"`: no valid host biome, no input, or insufficient output room for the next whole rarity-scaled yield. Use `stall_reason()` for the specific cause."""
 ...
 def stall_reason(self) -> Literal["ok", "no_biome", "no_input", "output_full", "unconnected"]:
 """Why the Liquifier is idle, as a string you can branch on: `\"no_biome\"` (the machine has no valid host outpost), `\"no_input\"` (input bin empty, feed it native-biome life forms), `\"output_full\"` (the next whole rarity-scaled yield cannot fit and a configured output cannot drain right now), `\"unconnected\"` (the next whole yield cannot fit and the essence output has no effective peer relationship), or `\"ok\"` (running, ready, or able to buffer the next whole yield). More specific than `is_stalled()`."""
 ...
 def biome(self) -> Literal["frozen", "coastal", "geothermal", "volcanic", "deep"] | None:
 """Returns the biome the host outpost sits in: `\"frozen\"`, `\"coastal\"`, `\"geothermal\"`, `\"volcanic\"`, or `\"deep\"`. Returns `None` when the machine has no valid outpost. This determines which life-form items the Essence Liquifier will accept; wrong-biome items are rejected by the input port."""
 ...
 frozen_essence_out: FluidPort
 coastal_essence_out: FluidPort
 geothermal_essence_out: FluidPort
 volcanic_essence_out: FluidPort
 deep_essence_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `ExoticDeposit`

```python
class ExoticDeposit(Site):
 """any Site-returning API where `kind() == \"exotic\"` (e.g. `exotic_gas_cap.deposit()`, `exotic_spring_tap.deposit()`, sonar / journal queries)"""
 def fluid(self) -> Literal["ammonia", "swamp_gas", "raw_sulfur_gas", "raw_chlorine", "brine", "raw_cryofluid", "raw_quicksilver"] | None:
 """Fluid id this deposit emits, e.g. `\"ammonia\"` (common, usable direct) or `\"raw_chlorine\"` (rare, needs the Refiner). `None` until `surveyed`."""
 ...
 def medium(self) -> Literal["gas", "liquid"] | None:
 """`\"gas\"` (tap with an **Exotic Gas Cap**) or `\"liquid\"` (tap with an **Exotic Spring Tap**). `None` until `surveyed`."""
 ...
 def rarity(self) -> Literal["common", "uncommon", "rare"] | None:
 """`\"common\"` emits the usable fluid with no refining; `\"uncommon\"` and `\"rare\"` emit a raw feedstock the Refiner converts with tar. Rarer deposits are sparser and stay dormant longer. `None` until `surveyed`."""
 ...
 def survey_level(self) -> Literal["basic", "wide", "deep"] | None:
 """Highest survey tier achieved on this deposit: `\"basic\"` / `\"wide\"` / `\"deep\"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def current_phase(self) -> Literal["active", "dormant"] | None:
 """The deposit's phase right now: `\"active\"` (emitting) or `\"dormant\"` (idle). Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the deposit is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def cycle_active_minutes(self) -> _float | None:
 """Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise."""
 ...
 def cycle_dormant_minutes(self) -> _float | None:
 """Duration of the dormant phase in minutes (rare deposits stay dormant longest). Requires **deep** survey: returns `None` otherwise."""
 ...
 def next_phase_in(self) -> _float | None:
 """Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def base_rate(self) -> _float | None:
 """Peak output rate during the active phase (t/h). Requires **wide** survey: returns `None` at basic."""
 ...
 def current_rate(self) -> _float | None:
 """Output rate right now (t/h: **0** during dormant). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def has_cap(self) -> _bool:
 """Boolean: `True` if an Exotic Gas Cap or Exotic Spring Tap is currently deployed on this deposit. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def cap_id(self) -> _str:
 """Machine id of the currently deployed cap/tap, or empty string when none is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
```

## `ExoticGasCap`

```python
class ExoticGasCap(Component):
 """Exotic Gas Cap: Captures gas from a cyclic exotic deposit during its active phase. Connect `self.gas_out` to a consumer, build a completed Gas Pipe route from the field Cap to that destination, then set a **0-1** release rate with `self.set_throttle(value)`. A full buffer pauses collection without losing gas."""
 name: _str
 def deposit(self) -> ExoticDeposit | None:
 """The `ExoticDeposit` this cap is bolted to, `.id`, `position()`, `fluid()`, `current_phase()`, cycle timing. Field availability is gated by the sonar tier that last surveyed the deposit: basic reveals phase only, wide adds rates, deep adds cycle timing. `None` if the cap isn't on a deposit. Use `deposit.current_phase()` to check whether the source is active. See `ExoticDeposit`."""
 ...
 def capture_rate(self) -> _float:
 """Exotic gas captured from the deposit on the last flow tick in t/h. **0** during the deposit's dormant phase, or when the buffer is full and holding (see `is_venting()`). Already factors in current phase and buffer headroom, read it instead of computing from the deposit's rate. Updates once per flow tick."""
 ...
 def is_venting(self) -> _bool:
 """`True` if active gas production exceeded the capture buffer's available space on the last flow tick. The excess is held upstream without losing gas. Dormancy returns `False` even with a full buffer, as does loss of power. This is a capture-space limit, unlike `is_stalled()`, which reports a blocked release. Open `self.set_throttle(...)` toward a tank with room."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if, on the last flow tick, the powered cap had an open throttle and buffered gas available for release but could transfer none across its connected routes. An empty buffer, closed throttle, or lack of power does not report a stall."""
 ...
 def throttle(self) -> _float:
 """Current release-valve setting, `0.0` (holding) to `1.0` (wide open). Read it back after `set_throttle(...)`."""
 ...
 def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
 """Open the cap's release valve in the `0.0 to 1.0` range (clamped). `0` holds the buffer; `1.0` releases gas across reachable connected destinations as fast as buffer supply, headroom, and throughput allow. This script-owned setpoint resets to `0` when the script stops, ends, or errors. `[self only]` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 gas_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `ExoticSpringTap`

```python
class ExoticSpringTap(Component):
 """Exotic Spring Tap: Captures liquid from a cyclic exotic spring during its active phase. Connect `self.liquid_out` to a consumer, build a completed Liquid Pipe route from the field Tap to that destination, then set a **0-1** release rate with `self.set_throttle(value)`. A full buffer pauses collection without losing liquid."""
 name: _str
 def deposit(self) -> ExoticDeposit | None:
 """The `ExoticDeposit` this tap is bolted to, `.id`, `position()`, `fluid()`, `current_phase()`, cycle timing. Field availability is gated by the sonar tier that last surveyed the deposit (basic / wide / deep). `None` if the tap isn't on a deposit. Use `deposit.current_phase()` to check whether the source is active. See `ExoticDeposit`."""
 ...
 def capture_rate(self) -> _float:
 """Exotic liquid captured from the spring on the last flow tick in t/h. **0** during the deposit's dormant phase, or when the buffer is full and holding (see `is_venting()`). Already factors in current phase and buffer headroom. Updates once per flow tick."""
 ...
 def is_venting(self) -> _bool:
 """`True` if active liquid production exceeded the capture buffer's available space on the last flow tick. The excess is held upstream without losing liquid. Dormancy returns `False` even with a full buffer, as does loss of power. This is a capture-space limit, unlike `is_stalled()`, which reports a blocked release. Open `self.set_throttle(...)` toward a tank with room."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if, on the last flow tick, the powered tap had an open throttle and buffered liquid available for release but could transfer none across its connected routes. An empty buffer, closed throttle, or lack of power does not report a stall."""
 ...
 def throttle(self) -> _float:
 """Current release-valve setting, `0.0` (holding) to `1.0` (wide open). Read it back after `set_throttle(...)`."""
 ...
 def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
 """Open the tap's release valve in the `0.0 to 1.0` range (clamped). `0` holds the buffer; `1.0` releases liquid across reachable connected destinations as fast as buffer supply, headroom, and throughput allow. This script-owned setpoint resets to `0` when the script stops, ends, or errors. `[self only]` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 liquid_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `Fabricator`

```python
class Fabricator(Component):
 """Fabricator: Assembles finished parts from several refined materials at once. A script picks a recipe, gathers each ingredient into its shared stockpile, and drains the finished items out."""
 name: _str
 outpost: OutpostRef
 def list_recipes(self) -> _list[Recipe]:
 """Every recipe this fabricator has been given a blueprint for. Returns Recipe objects with `.tier`, `.id`, `.name`, `.inputs`, `.output_item`, `.output_count`, `.duration_game_hours`, `.power_draw`, `.fluid_inputs` (tons consumed per run), and optional byproduct fields. Locked recipes (no blueprint yet) do not appear, the list reflects what the player can actually craft today. `sorted(self.list_recipes(), key=lambda recipe: recipe.tier)` orders the available queue from foundations upward."""
 ...
 def find_recipe(self, recipe_id: _str) -> Recipe | None:
 """Find one unlocked recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine."""
 ...
 def set_recipe(self, recipe_or_id: Any) -> ActionResult[Literal["ok", "unknown_recipe", "offline", "recipe_locked", "busy", "material_mismatch"]]:
 """Select which recipe to assemble: `self.set_recipe(\"craft_gas_pipe_segment\")`, or pass a Recipe from `list_recipes()`. Setting a recipe doesn't clear the stockpile, so leftovers from a previous recipe stay until consumed or `self.input.flush()` discards them. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
 """Unset the selected recipe and leave the Fabricator idle. The input stockpile is preserved because it is general staged material, not the selected recipe. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_recipe(self) -> Literal["", "craft_gas_pipe_segment", "craft_liquid_pipe_segment", "craft_power_line_segment", "craft_gas_pipe_bridge", "craft_liquid_pipe_bridge", "craft_power_line_bridge", "craft_pressure_valve", "craft_machine_frame", "craft_circuit_panel", "craft_control_unit", "craft_battery_cell", "craft_thermal_cap_kit", "craft_turbine_rotor", "craft_tank_lining", "craft_water_pump", "craft_oil_pump", "craft_lubricant", "craft_plastic", "craft_rubber", "craft_tar", "craft_reinforced_biopolymer", "craft_enrichment_compound", "craft_drone_station_kit", "craft_drone_station_kit_medium", "craft_drone_station_kit_large", "craft_drone_service_station_kit", "craft_mining_drill_kit", "craft_mining_drill_industrial_kit", "craft_mining_drill_heavy_kit", "craft_drone_small", "craft_drone_medium", "craft_drone_large", "craft_electric_thruster", "craft_heli_thruster", "craft_cargo_pod_small", "craft_cargo_pod_medium", "craft_cargo_pod_large", "craft_battery_pack", "craft_oil_tank_small", "craft_oil_tank_medium", "craft_oil_tank_large", "craft_coolant_loop", "craft_neutron_capacitor", "craft_seed_maker_kit", "craft_plant_terraformer_kit", "craft_grow_lamp_kit", "craft_sprinkler_kit", "craft_dispenser_kit", "craft_garbage_disposal_kit", "craft_exotic_gas_cap_kit", "craft_exotic_spring_tap_kit", "craft_fertilizer", "craft_fertilizer_mk2", "craft_fertilizer_mk3", "craft_growth_accelerant", "craft_yield_amplifier", "craft_plant_terraformer_pack_mk2", "craft_grow_lamp_pack_mk2", "craft_grow_lamp_pack_mk3", "craft_sprinkler_pack_mk2", "craft_sprinkler_pack_mk3", "craft_habitat_pack_mk2", "craft_lead_plate", "craft_oxygen_upgrade_pack_mk4", "craft_heat_upgrade_pack_mk4", "craft_pressure_upgrade_pack_mk4", "craft_lead_cask", "craft_shield_plating", "craft_lightning_rod_kit"]:
 """Current recipe id as a string, or the empty string if no recipe is set. Use to gate other logic or confirm after `set_recipe()`."""
 ...
 def get_recipe_inputs(self) -> _dict[_str, _float]:
 """Input requirements for the current recipe as a dict `{item_id: count_per_craft}`. Empty dict if no recipe is set. Use with `.keys()` / `.values()` / `.items()` to drive a loop: `for mat, need in self.get_recipe_inputs().items(): self.input.connect(bin_for(mat)); self.input.take(mat, need)`."""
 ...
 def get_stockpile(self) -> _dict[_str, _float]:
 """Current stockpile contents as a dict `{item_id: count_currently_stored}`. Iterate with `.items()` to see every material; index directly with `self.get_stockpile()[\"iron_ingot\"]` to read one. Essential for deciding what else needs pulling in."""
 ...
 def get_stockpile_used(self) -> _int:
 """Total units across every material in the stockpile. Compare to `get_stockpile_capacity()` to detect when the pile is full. When it is full, further input is blocked until the running craft consumes some material."""
 ...
 def get_stockpile_capacity(self) -> _int:
 """Combined unit cap across all materials (fixed for this fabricator). Queryable rather than hardcoded, the cap tunes separately from your script. Use `used / capacity` for a fill-percent gauge."""
 ...
 def is_running(self) -> _bool:
 """`True` while a craft is in progress. Use before `set_recipe()` to avoid `\"busy\"`, or to show status. Stays `True` across ticks until the craft completes."""
 ...
 def get_progress(self) -> _float:
 """Progress toward the current craft's completion (**0-1**). Resets to **0** when a craft finishes. Use for progress bars and to detect completions by watching the value drop."""
 ...
 def get_output_count(self) -> _int:
 """Completed units waiting in the output buffer. Drain them via `self.output.send(...)` before the buffer fills, processing stalls when the output is full."""
 ...
 input: InputSlot
 output: OutputSlot
 byproduct: OutputSlot
 steam_in: FluidPort
 water_in: FluidPort
 oil_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `FluidConnection`

```python
class FluidConnection:
 """FluidPort.connections()"""
 machine_id: _str
 machine_name: _str
 fluid: Literal["steam", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"] | None
 declared_by: Literal["self", "peer", "both"]
 state: Literal["local", "ready", "unreachable", "conflict", "neutral", "incompatible"]
```

## `FluidPort`

```python
class FluidPort:
 """any `<fluid>_in` / `<fluid>_out` property on a flow-network machine"""
 def connect(self, target: _str) -> ActionResult[Literal["ok", "not_found", "incompatible"]]:
 """Record or replace this port's one declared target, using a stable machine id or display name. The target must expose a compatible opposite-direction port. Either the provider or consumer may declare the relationship; one declaration is enough. Local machines transfer directly, while remote intent waits for any completed conflict-free same-medium component reaching both anchors. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def disconnect(self) -> ActionResult[Literal["ok"]]:
 """Clear only this port's declared target. Buffered fluid remains. If the peer independently declared the same relationship, that reverse declaration remains active. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def connected_to(self) -> _str:
 """Display name of the target declared by this port, or empty string. It does not list compatible reverse declarations owned by peer ports."""
 ...
 def connected_id(self) -> _str:
 """Stable id of the target declared by this port, or empty string. `connect()` accepts an id or a display name, so compare against this when you need the identity to match what you passed: `connected_to()` answers with the renameable name. For every effective peer, including declarations owned by the other side, use `connections()`."""
 ...
 def connections(self) -> _list[FluidConnection]:
 """Read-only snapshots of every effective peer relationship on this port, including declarations authored by peer ports. Each `FluidConnection` reports the peer, exact fluid when known, declaration ownership, and structural state. Pipe ids are deliberately not exposed or selected."""
 ...
 def level(self) -> _float:
 """Current tons of fluid buffered at this port. Pass-through source ports such as Pump outputs store nothing and therefore read **0**."""
 ...
 def capacity(self) -> _float:
 """Max tons this port's buffer can hold."""
 ...
 def flow_rate(self) -> _float:
 """Current total live flow in **t/h**. **0** may mean idle, starved, full, unreachable, conflicted, or waiting across a simulation timing boundary; it does not erase the connection or pipe identity."""
 ...
```

## `FuelAssembler`

```python
class FuelAssembler(Component):
 """Fuel Assembler: Presses Raw Uranium and lead plates into Fuel Rods or Nuclear Batteries, working like the Fabricator. It draws heavy recipe power while running, so it is best run in bursts when your lightning banks are full."""
 name: _str
 outpost: OutpostRef
 def list_recipes(self) -> _list[Recipe]:
 """Unlocked recipes this machine can run, including each recipe's derived `.tier`. The Fuel Rod recipe arrives through Vestibule's queue; the Nuclear Battery recipe arrives through Helios's queue."""
 ...
 def find_recipe(self, recipe_id: _str) -> Recipe | None:
 """Find one unlocked fuel recipe by id without looping through `list_recipes()`. Returns its `Recipe` object, or `None` when the id is unknown, locked, or belongs to another machine."""
 ...
 def set_recipe(self, recipe_or_id: Any) -> ActionResult[Literal["ok", "unknown_recipe", "recipe_locked", "offline", "busy", "material_mismatch"]]:
 """Select a Fuel Rod or Nuclear Battery recipe by id or by passing a Recipe from `list_recipes()`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_recipe(self) -> ActionResult[Literal["ok", "busy", "material_present"]]:
 """Release the recipe once the current craft is idle and the output buffer is drained. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_recipe(self) -> Literal["", "craft_fuel_rod", "craft_nuclear_battery"]:
 """The committed recipe id, empty when none."""
 ...
 def get_recipe_inputs(self) -> _dict[_str, _int]:
 """Input requirements for the committed recipe as a dict `{item_id: count_per_craft}`. Returns an empty dict when no recipe is committed."""
 ...
 def is_running(self) -> _bool:
 """`True` while a craft is actually advancing, power, inputs, and output space all present."""
 ...
 def get_progress(self) -> _float:
 """Current craft progress **0-1**. Progress survives power cuts and resumes."""
 ...
 def get_stockpile(self) -> _dict[_str, Any]:
 """Staged inputs by item id, `{\"raw_uranium\": 12, \"lead_plate\": 4}`-shaped dict."""
 ...
 def get_output_count(self) -> _int:
 """Finished products for the selected recipe waiting in the small output buffer."""
 ...
 input: InputSlot
 output: OutputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `GarbageDisposal`

```python
class GarbageDisposal(Component):
 """Waste Processor: Permanently destroys one script-selected waste stream: items, liquids, or gases. Use the item input for unwanted stock, `liquid_in` for surplus water or other liquids, and `gas_in` for gases. It has no output and recovers no value."""
 name: _str
 outpost: OutpostRef
 def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
 """Arm or pause destruction in the selected mode. Stopping the owning script resets this setpoint to off. Staged items and fluids remain intact. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_enabled(self) -> _bool:
 """Read whether the owning script has armed the processor."""
 ...
 def set_mode(self, mode: _str) -> ActionResult[Literal["ok"]]:
 """Select exactly one destruction stream: `\"items\"`, `\"liquid\"`, or `\"gas\"`. Changing modes pauses the other buffers without deleting them. The selected fluid port accepts flow only while enabled. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def mode(self) -> Literal["items", "liquid", "gas"]:
 """Read the selected waste stream."""
 ...
 def status(self) -> Literal["disabled", "no_power", "idle", "processing"]:
 """Read the exact live state: `\"disabled\"`, `\"no_power\"`, `\"idle\"`, or `\"processing\"`."""
 ...
 def throughput(self) -> _float:
 """Read the selected mode's last destruction rate. Item mode reports units/h; liquid and gas modes report t/h."""
 ...
 def item_throughput(self) -> _float:
 """Read the last item destruction rate in units/h."""
 ...
 def liquid_throughput(self) -> _float:
 """Read the last liquid destruction rate in t/h. At 100% outpost efficiency, the maximum is **120 t/h**."""
 ...
 def gas_throughput(self) -> _float:
 """Read the last gas destruction rate in t/h. At 100% outpost efficiency, the maximum is **120 t/h**."""
 ...
 def is_running(self) -> _bool:
 """Read whether the selected mode destroyed material on the last processing tick."""
 ...
 input: InputSlot
 liquid_in: FluidPort
 gas_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `GeologicalAnomaly`

```python
class GeologicalAnomaly(Site):
 """any Site-returning API where `kind() == \"inert\"`"""
 ...
```

## `Gps`

```python
class Gps(Component):
 """GPS: A ship sensor that reports which outpost you're viewing, its name and coordinates, and how many buildings are deployed there. Switching outposts on the dashboard retargets it."""
 name: _str
 def planet(self) -> Nocturna:
 """Returns the current planet component. Use `gps.planet().id` for stable ids such as `\"nocturna\"` when calling Journal APIs, and `gps.planet().get_name()` for the display name `\"Nocturna\"`."""
 ...
 def site_name(self) -> _str:
 """Returns the current outpost's display name. `\"Nocturna Base\"` for the home outpost (default, players can rename); `\"Outpost 1\"`, `\"Outpost 2\"`, ... for player-founded outposts."""
 ...
 def coords(self) -> _tuple[_int, _int]:
 """Returns the current outpost's world coordinates as a **2-element list** `[x, y]`. The home outpost sits at `[0, 0]`; founded outposts carry the position the player chose in Plan mode."""
 ...
 def buildings_used(self) -> _int:
 """Returns the number of buildings deployed at the **current** outpost. Sensors, mobile units, structural hubs, and POI extraction machines don't count, only shop-purchased deployable buildings."""
 ...
 def buildings_capacity(self) -> _int:
 """Returns the soft building threshold at the current outpost. Each counted building above it reduces productive and service throughput. Nocturna Base has a few extra starter slots; founded outposts use the standard threshold."""
 ...
 def is_full(self) -> _bool:
 """Returns `True` when the current outpost has reached or exceeded its soft building threshold. The threshold itself does not block ordinary deployment."""
 ...
 def is_home(self) -> _bool:
 """Returns `True` when the current outpost is the home outpost (the one the player started at, default name `\"Nocturna Base\"`). Useful for branching on whether you're managing the spawn site versus a remote outpost."""
 ...
```

## `GrowLamp`

```python
class GrowLamp(Component):
 """Grow Lamp: Lights the four orthogonally adjacent field cells (directly above, below, left, and right) while powered and enabled."""
 name: _str
 def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
 """Command the lamp on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_enabled(self) -> _bool:
 """`True` when the running script has commanded this lamp on."""
 ...
 def is_active(self) -> _bool:
 """`True` when the lamp is commanded on and has power."""
 ...
 def is_supplied(self) -> _bool:
 """`True` when the lamp is commanded on, powered, and actively lighting its covered cells. If disabled or unpowered, covered cells lose `lit` and their plants pause."""
 ...
 def status(self) -> Literal["not_placed", "disabled", "no_power", "active"]:
 """Exact operating state: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"`, or `\"active\"`."""
 ...
 def tier(self) -> _int:
 """Deployed tier (**1-4**). Mk I/II/III/IV provide **1×/2×/4×/8×** supported plant output and draw **5/25/100/500 W** while active."""
 ...
 def position(self) -> _str:
 """Grid sector occupied by this lamp, such as `\"E14\"`."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `Habitat`

```python
class Habitat(Component):
 """Habitat: Revives one species from Biology reagents staged in this Habitat's dedicated local input, then breeds it into a colony. One living colony is allowed per species. Established colonies keep their progress when moved between Habitats."""
 name: _str
 outpost: OutpostRef
 def set_revival_target(self, creature_id: _str) -> ActionResult[Literal["ok", "occupied", "species_exists", "unknown_creature", "not_cataloged"]]:
 """Select which cataloged creature this Habitat is preparing with `self.set_revival_target(\"salt_tortoise\")`. The validated target persists when the script stops and after a failed setup check or rearing attempt, so the Habitat card can show the creature and its live preparation requirements before a colony exists. Selecting another valid creature replaces the target without consuming materials. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def revive(self) -> ActionResult[Literal["ok", "occupied", "no_target", "species_exists", "not_cataloged", "wrong_feed", "insufficient_feed", "insufficient_reagents"]]:
 """Bring this Habitat's selected revival target to life with `self.revive()`. Stock at least **2** of its feed first: revival spends one and one must remain for rearing. Stage the exact rarity-scaled Bio Lab reagents shown by the Habitat or `journal.cataloged_creatures(...)`. Creature bonuses do not change this one-time recipe. Failed checks spend nothing and keep the selected target. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def rehouse(self, creature_id: _str) -> ActionResult[Literal["ok", "occupied", "no_colony", "not_established", "insufficient_capacity", "unknown_creature"]]:
 """Attach an established species colony to this Habitat with `self.rehouse(\"salt_tortoise\")`. The destination must be empty and its current capacity must fit the entire colony. The same call moves a colony directly from another Habitat or restores one after its former Habitat was undeployed. Population, life stage, brood progress, Insight history, and purchased bonuses are preserved. Growth and active Wildlife contribution pause while a colony is unhoused. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_gas_intake(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set the gas inflow rate in **t/h**, pulled from the connected Gas Tank (wire it with `self.gas_in.connect(\"gas_tank_1\")`) into the enclosure's gas reserve. This is the regulator actuator: read `gas_level()`, compare it with `gas_band()`, and raise intake below the band or lower it above the band. Idle at **0**. Clamps to `>= 0`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def purge_intake(self, port: _str | None = ...) -> ActionResult[Literal["ok", "empty"]]:
 """Vents a feedstock inlet so it can accept a different fluid. Pass `\"gas_in\"` or `\"liquid_in\"` to vent one, or omit to vent both, venting only what is actually blocked leaves a healthy buffer alone. The inlets take the first fluid that reaches them and then refuse any other, so an enclosure supplied the wrong gas ends up holding one it cannot use with no way to take the right one. Purge, rewire, and the next correct delivery replaces the enclosure air: `self.purge_intake()` then `self.gas_in.connect(\"Sulfur Refiner\")`. The vented fluid is destroyed; feed and colony progress are untouched. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def purge_reserve(self, medium: _str) -> ActionResult[Literal["ok", "empty"]]:
 """Empties the selected enclosure reserve immediately: `self.purge_reserve(\"gas\")` or `self.purge_reserve(\"liquid\")`. The fluid is destroyed. The other reserve, inlet buffers, connections, intake settings, feed, and colony progress stay intact. The reserve can refill on later ticks if intake remains open. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_liquid_intake(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set the liquid inflow rate in **t/h**, pulled from the connected Liquid Tank (`self.liquid_in.connect(\"liquid_tank_1\")`) into the enclosure's liquid reserve. Meter it to hold `liquid_band()`. Idle at **0**. Clamps to `>= 0`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def unlock_bonus(self, node_id: _str) -> ActionResult[Literal["ok", "unknown_node", "already_purchased", "population_locked", "insufficient_insight"]]:
 """Permanently purchase one node from this creature's tree. Pass a node id from `get_bonus_tree().nodes`. The **1 Insight** Adaptation affects this species only. The **4 Insight** Breakthrough affects every species and also requires this source colony to reach **10,000** population. A rejected purchase spends nothing. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def tier(self) -> _int:
 """Permanently installed Habitat tier as an integer (**1-2**). Mk II doubles carrying capacity only; breeding speed and biological costs come from adaptations."""
 ...
 def population(self) -> _int:
 """Current colony head count (individuals). Reads **0** for an empty Habitat OR one still in the Founded rearing window, a colony only counts (here and on the Wildlife sensor) once it's established. Breeds up toward `carrying_capacity()` and never falls."""
 ...
 def species(self) -> Literal["", "salt_tortoise", "magmatic_annelid", "mycelial_husk", "mantle_strider", "glasswing_mantis", "veil_mantle", "vault_crab", "tidal_cephalopod", "bone_walker", "vent_drifter", "hive_sentinel", "hollow_choir", "ferric_sea_lily", "crustal_echo", "glacial_wyrm", "spire_drake"]:
 """The housed creature id (e.g. `\"glacial_wyrm\"`), or `\"\"` when the Habitat is empty. Use to look the creature up or branch your regulator per species."""
 ...
 def revival_target(self) -> Literal["", "salt_tortoise", "magmatic_annelid", "mycelial_husk", "mantle_strider", "glasswing_mantis", "veil_mantle", "vault_crab", "tidal_cephalopod", "bone_walker", "vent_drifter", "hive_sentinel", "hollow_choir", "ferric_sea_lily", "crustal_echo", "glacial_wyrm", "spire_drake"]:
 """The creature id explicitly selected with `set_revival_target(...)`, or `\"\"` before selection and after establishment. Failed setup checks and rearing attempts retain this value, while `species()` remains empty until revival actually starts."""
 ...
 def life_stage(self) -> Literal["empty", "founded", "first_breeding", "self_sustaining", "thriving", "abundant"]:
 """The colony's stage as a string: `\"empty\"`, `\"founded\"`, `\"first_breeding\"`, `\"self_sustaining\"`, `\"thriving\"`, or `\"abundant\"`. The colony climbs as its own population crosses each stage threshold; each climb opens a harder requirement and raises the ceiling. Branch on it to scale up your supply: `if self.life_stage() == \"thriving\": self.set_liquid_intake(...)`."""
 ...
 def is_established(self) -> _bool:
 """`True` once the colony cleared the Founded rearing window and is counting on the sensor; `False` during rearing or when empty. Gate breeding logic on it: `if self.is_established(): regulate()`."""
 ...
 def rearing_progress(self) -> _float:
 """Fraction **0-1** of the Founded rearing window held in-band. Climbs only while every active band is satisfied; reaches **1.0** to establish. Reads **0** when empty/established, and resets to 0 if a band is lost (rearing fails). Watch it during a fresh revive to confirm your regulator is holding."""
 ...
 def rearing_failed(self) -> _bool:
 """`True` after a rearing attempt lost its bands and reverted the Habitat to preparation. The genome and selected target are kept, fix your regulator and call `revive()` again. Clears when a target is selected or revival restarts."""
 ...
 def brood_size(self) -> _int:
 """Whole individuals produced by the next completed breeding cycle. Normally **1**; brood bonuses build toward a guaranteed extra individual and periodically make it **2**. Reads **0** without an established colony or carrying-capacity space."""
 ...
 def breeding_rate(self) -> _float:
 """Expected individuals/h at the current population, remaining capacity (headroom), life support, rarity, adaptation effects, and available local inputs. Population adds less and less extra speed above 10 individuals, while brood yield and purchased speed effects stay within their overall limits. This is the rate readout; `breeding_efficiency()` is only the life-support factor."""
 ...
 def feed_level(self) -> _float:
 """Usable feed units remaining after partial consumption. Feed is consumed automatically only when individuals are born. Top it up with `self.input.take(...)`; over-stocking is harmless."""
 ...
 def gas_level(self) -> _float:
 """Current gas held in the enclosure, in **tons**. Compare it with `gas_band()` and meter `set_gas_intake(...)` to hold it inside the window. It drops as the colony consumes gas while breeding and rises with intake."""
 ...
 def liquid_level(self) -> _float:
 """Current liquid held in the enclosure, in **tons**. Compare it with `liquid_band()` and meter `set_liquid_intake(...)` to hold the window."""
 ...
 def get_insight(self) -> HabitatInsight:
 """Read the shared Wildlife Insight balance and this colony's current and lifetime contribution. Insight accrues directly from positive population change. Static population and elapsed time alone produce nothing."""
 ...
 def get_bonus_tree(self) -> HabitatBonusTree:
 """Read this creature's species-only Adaptation and all-species Breakthrough, including each node's `.scope`, `.source_species`, permanent purchase state, current effect activity, Insight cost, and unmet requirements. The tree appears after selecting a revival target and its nodes remain visible while locked."""
 ...
 def get_active_bonuses(self) -> _list[HabitatBonusNode]:
 """Read every purchased node currently affecting this Habitat, including global Breakthroughs earned from other species. Each result exposes `.scope` and `.source_species`. A conditional node disappears while its local condition is unmet; use its source Habitat's `get_bonus_tree()` to inspect permanent ownership."""
 ...
 def gas_band(self) -> _list[_float]:
 """Safe gas-inventory range `[low, high]` in **tons** for the colony's current stage. Breeding receives full gas support inside the range; too little starves the colony and too much is toxic. Returns an empty list before gas is required. Read it each loop because the range tightens as the colony grows."""
 ...
 def liquid_band(self) -> _list[_float]:
 """Safe liquid-inventory range `[low, high]` in **tons** for the colony's current stage. Returns an empty list before liquid is required. Read it each loop because the range tightens as the colony grows."""
 ...
 def feed_ok(self) -> _bool:
 """`True` when the feed named by `required_feed()` is stocked. Feed is consumed automatically as individuals are born. `False` means the bin is empty or contains the wrong feed. Missing feed stalls breeding but does not reduce the established population."""
 ...
 def gas_ok(self) -> _bool:
 """`True` when gas requirements are met or gas is not required yet. `False` means the level is outside `gas_band()` or the enclosure holds the wrong gas. If the level is inside the range, compare `gas_fluid()` with `required_gas()`."""
 ...
 def liquid_ok(self) -> _bool:
 """`True` when liquid requirements are met or liquid is not required yet. `False` means the level is outside `liquid_band()` or the enclosure holds the wrong liquid. Compare `liquid_fluid()` with `required_liquid()` to tell which."""
 ...
 def breeding_efficiency(self) -> _float:
 """Current life-support multiplier from **0-100%**, not the population growth rate. The weakest active input sets it; **100%** means every input is ready. Growth also scales with population momentum, rarity, and bonuses. Capacity stops growth only when full and never slows breeding beforehand. Poor conditions never reduce population."""
 ...
 def gas_fluid(self) -> Literal["", "steam", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine"]:
 """The exotic gas currently held in the enclosure, such as `\"chlorine\"`, or `\"\"` when empty. It must equal `required_gas()` for the gas range to count. If `gas_level()` is in range but `gas_ok()` is `False`, the enclosure holds the wrong gas."""
 ...
 def liquid_fluid(self) -> Literal["", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"]:
 """The exotic liquid currently held in the enclosure, or `\"\"` when empty. It must equal `required_liquid()` for the liquid range to count."""
 ...
 def required_feed(self) -> Literal["", "feed_salt_tortoise", "feed_magmatic_annelid", "feed_mycelial_husk", "feed_mantle_strider", "feed_glasswing_mantis", "feed_veil_mantle", "feed_vault_crab", "feed_tidal_cephalopod", "feed_bone_walker", "feed_vent_drifter", "feed_hive_sentinel", "feed_hollow_choir", "feed_ferric_sea_lily", "feed_crustal_echo", "feed_glacial_wyrm", "feed_spire_drake"]:
 """The exact feed item id required by the selected revival target or housed creature, or `\"\"` when neither exists. Compare it with `self.input.stacks()` while staging or diagnosing feed."""
 ...
 def required_gas(self) -> Literal["", "swamp_gas", "ammonia", "sulfur_gas", "chlorine"]:
 """The exotic gas required at the colony's current stage, such as `\"swamp_gas\"`, or `\"\"` before gas is needed. The requirement becomes more demanding at later stages, so check it again as the colony grows. Other gases do not satisfy the required range."""
 ...
 def required_liquid(self) -> Literal["", "brine", "cryofluid", "quicksilver"]:
 """The exotic liquid this creature needs at its current stage, e.g. `\"brine\"`; escalates at later stages (`\"brine\"` → `\"cryofluid\"` → `\"quicksilver\"`). `liquid_fluid()` must match it. `\"\"` when liquid isn't required yet."""
 ...
 def next_required_gas(self) -> Literal["", "swamp_gas", "ammonia", "sulfur_gas", "chlorine"]:
 """The gas required after the next life-stage transition, or `\"\"` if the next stage needs no gas or there is no next stage. Read it with `next_gas_band()` before the population reaches the threshold."""
 ...
 def next_required_liquid(self) -> Literal["", "brine", "cryofluid", "quicksilver"]:
 """The liquid required after the next life-stage transition, or `\"\"` if the next stage needs no liquid or there is no next stage. Read it with `next_liquid_band()` before the population reaches the threshold."""
 ...
 def next_gas_band(self) -> _list[_float]:
 """The next life stage's exact gas window as `[low, high]` in **tons**. Returns `[]` if that stage needs no gas or the colony is already Abundant. Pair with `next_required_gas()` to prepare the correct supply and regulator in advance."""
 ...
 def next_liquid_band(self) -> _list[_float]:
 """The next life stage's exact liquid window as `[low, high]` in **tons**. Returns `[]` if that stage needs no liquid or the colony is already Abundant. Pair with `next_required_liquid()`."""
 ...
 def carrying_capacity(self) -> _int:
 """The colony's ceiling at its current life stage. Population breeds toward it and plateaus there; a maxed colony consumes nothing. Life-stage advancement raises the base ceiling, and Habitat Mk II doubles it. Adaptations never change capacity. Reads **0** when empty."""
 ...
 def headroom(self) -> _int:
 """Individuals still breedable before the current ceiling (`carrying_capacity() - population()`, floored at **0**). **0** means this colony is capped and idling. Before Abundant, reach the next stage; at Abundant Mk I, apply the sole Habitat Mk II pack or grow another species."""
 ...
 def next_stage_population(self) -> _int:
 """Exact population that opens the next life stage: **250**, **2,500**, **25,000**, or **175,001**. Returns **0** when the Habitat is empty or already Abundant. Mk I stops at **175,000**, so entering Abundant requires Mk II. Compare the result with `population()` so your script can prepare the next supply before the transition."""
 ...
 def next_requirement(self) -> Literal["capacity", "gas", "liquid", "switch_gas", "switch_liquid", "tighter_bands", "none"]:
 """What changes at the colony's next stage: `\"capacity\"`, `\"gas\"`, `\"liquid\"`, `\"switch_gas\"`, `\"switch_liquid\"`, `\"tighter_bands\"`, or `\"none\"` at Abundant. Pair it with `next_stage_population()` to learn when the transition happens and what to prepare."""
 ...
 gas_in: FluidPort
 liquid_in: FluidPort
 input: InputSlot
 reagents: InputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `HabitatBonusNode`

```python
class HabitatBonusNode:
 """Habitat.get_bonus_tree().nodes and Habitat.get_active_bonuses()"""
 id: _str
 source_species: _str
 slot: Literal["adaptation", "breakthrough"]
 scope: Literal["species", "global"]
 depth: _int
 name: _str
 description: _str
 state: Literal["purchased", "available", "unaffordable", "population_locked"]
 purchased: _bool
 active: _bool
 insight_cost: _int
 local_population: _int
 unmet: _list[_str]
```

## `HabitatBonusTree`

```python
class HabitatBonusTree:
 """Habitat.get_bonus_tree()"""
 species: _str
 shared_insight: _float
 purchased_count: _int
 nodes: _list[HabitatBonusNode]
```

## `HabitatInsight`

```python
class HabitatInsight:
 """Habitat.get_insight()"""
 shared: _float
 shared_exact: _float
 rate_per_hour: _float
 lifetime_produced: _float
 producing: _bool
```

## `HarvestingMachineRef`

```python
class HarvestingMachineRef:
 """outpost.harvesting_machines() / outpost_network.home().harvesting_machines()"""
 id: _str
 name: _str
 type_id: Literal["grow_lamp", "sprinkler", "dispenser", "crop_automator"]
 powered: _bool
 position: _str
```

## `Holder`

```python
class Holder:
 """self.battery.holders()"""
 id: _str
 size: Literal["small", "medium", "large"]
 capacity: _float
 wh: _float
 batteries: _list[PortableBattery | None]
```

## `JobReceipt`

```python
class JobReceipt(Generic[_StatusT]):
 """Crop Automator job submission"""
 status: _StatusT
 message: _str
 job_id: _int | None
 queue_position: _int | None
```

## `Journal`

```python
class Journal(Component):
 """Journal: Stores sites found or surveyed by sonar and fragments cataloged by Bio Labs. Access it with `get_component(\"journal\")` to plan trips and Bio Orders without scanning again. Records are separated by planet and survive script restarts, vehicle changes, and save/load."""
 name: _str
 def discovered_sites(self, planet_id: _str) -> _list[Site]:
 """Lists every site classified by sonar on `planet_id`. Call `journal.discovered_sites(\"nocturna\")` for Nocturna. Each entry is a `MiningSite`, `ThermalVent`, `WaterWell`, `OilWell`, `ExoticDeposit`, or `GeologicalAnomaly`, according to `kind()`. Unsurveyed productive sites leave their detailed fields as `None`; inert formations are resolved by scanning. Duplicate scans do not add duplicate entries. Returns an empty list before any sites are found. See `Site`."""
 ...
 def surveyed_sites(self, planet_id: _str) -> _list[Site]:
 """Every fully-resolved site on `planet_id` as `list<Site>`, same shape as `discovered_sites()`, filtered to `surveyed == True`. This includes inert `GeologicalAnomaly` contacts because sonar resolves them without a second survey. Branch on `kind()` to access fields: `MiningSite` exposes `.item_id`, `.hardness`, `.purity`; `ThermalVent` exposes phase / rate / cycle timing (gated by sonar tier); `WaterWell` / `OilWell` expose `.yield_tier`, `.flow_rate`. See `Site`."""
 ...
 def cataloged_fragments(self, planet_id: _str) -> _list[CatalogedFragment]:
 """Lists fragments analyzed at a Bio Lab on `planet_id`, newest first. Each `CatalogedFragment` includes its stable fragment id, display name, biome, coordinates, and rarity. Match `entry.fragment_id` against `BioOrder.requires`, and pass `entry.coords` to `bio_collector.collect(...)`. Unanalyzed fragments and creature identity remain hidden. After all five fragments are cataloged, the completed creature appears in `journal.cataloged_creatures(planet_id)`. Returns an empty list for a different planet."""
 ...
 def cataloged_creatures(self, planet_id: _str) -> _list[CatalogedCreature]:
 """Lists creatures whose five fragments have all been analyzed on `planet_id`, most recently completed first. Each `CatalogedCreature` provides the stable creature id, its five fragment ids, required feed item and Feed Maker recipe, minimum startup feed, and exact rarity-scaled revival reagents. Use `.creature_id` with `habitat.set_revival_target(...)`. Use `.feed_recipe_id` to find the matching unlocked `Recipe` in `feed_maker.list_recipes()`; recipe ingredients remain owned by that Recipe. Returns an empty list for a different planet."""
 ...
 def coord_info(self, x: _float, y: _float) -> LifeFormScanResult | None:
 """Read the saved `LifeFormScanResult` for a discovered permanent biosite coordinate. Returns `None` for untouched biosites and scanned coordinates that are not sites. The query returns immediately."""
 ...
 def biomass_coords(self) -> _list[LifeFormScanResult]:
 """Lists every discovered permanent biosite as a `LifeFormScanResult`. This is the restart-safe route source for harvester drones: inspect `.coord`, each sample's `.remaining_tons`, and `is_ready(x, y)` before dispatching."""
 ...
 def has_scanned(self, x: _float, y: _float) -> _bool:
 """`True` after the whole-number coordinate `(x, y)` has been scanned. Use it to skip biosites already visited by a route that resumes across script restarts."""
 ...
 def is_empty(self, x: _float, y: _float) -> _bool:
 """`True` only when this whole-number tile has been scanned and contained no life forms. Returns `False` for both occupied and untouched tiles, so pair it with `has_scanned()`."""
 ...
 def is_ready(self, x: _float, y: _float) -> _bool:
 """`True` when a discovered biosite can be extracted now. Returns `False` while another drone is extracting there, after depletion, or during its rarity-based cooldown. The query uses current site state and returns immediately."""
 ...
 def next_ready_at(self, x: _float, y: _float) -> _float | None:
 """When the extraction cooldown ends, as an absolute hour. A depleted site's timestamp remains even after that hour passes, until extraction replenishes it. Returns `None` if the biosite is not recorded, still has material, or has never been extracted. Use `is_ready(x, y)` to check whether extraction can begin now."""
 ...
```

## `LightningRod`

```python
class LightningRod(Component):
 """Lightning Rod: A **4,000 Wh** emergency reserve that catches lightning within **600 m** and discharges behind batteries. Condition falls **0.05 per day**, reducing capture to zero unless a running script repairs it with **1 Storm Glass**."""
 name: _str
 outpost: OutpostRef
 def bank(self) -> _float:
 """Wh currently banked, **0** up to `capacity()`. Rises only when a strike lands within catch range of this rod; falls automatically when its grid is short and the batteries are empty. It never charges from grid surplus."""
 ...
 def capacity(self) -> _float:
 """Bank capacity in Wh, several times a base battery. Query this instead of hardcoding the number."""
 ...
 def last_strike(self) -> _float:
 """Hour timestamp of the last strike from which this rod accepted energy, or **-1** if none. A strike that adds no energy, for example when the bank is full or integrity is zero, does not update this record. Compare with the clock's current time to see how long it has been since energy was last captured."""
 ...
 input: InputSlot
 def integrity(self) -> _float:
 """This rod's condition from **0** to **1**, which is also its capture efficiency. Continuous corrosion lowers it by **0.05 per day**; strikes do not cause separate damage. A rod at **0.5** banks half of every strike it catches, and one at **0** banks nothing while still standing and still repairable."""
 ...
 def repair(self) -> ActionResult[Literal["ok", "no_op", "no_material"]]:
 """Restore this rod to full condition. If it is worn, one call consumes **1 Storm Glass** from its input and sets condition to **1**. At full condition, no material is consumed. Without Storm Glass in the input, condition does not change. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...

# Game lookup helpers
@overload
def get_component(name: Literal["me"]) -> Commander | None: ...
@overload
def get_component(name: Literal["commander"]) -> Commander | None: ...
@overload
def get_component(name: Literal["shop"]) -> Shop | None: ...
@overload
def get_component(name: Literal["fleet"]) -> FleetComponent | None: ...
@overload
def get_component(name: Literal["outpost_network"]) -> OutpostNetworkComponent | None: ...
@overload
def get_component(name: Literal["power_control"]) -> PowerControl | None: ...
@overload
def get_component(name: Literal["run_control"]) -> RunControl | None: ...
@overload
def get_component(name: Literal["research"]) -> Research | None: ...
@overload
def get_component(name: Literal["item_catalog"]) -> ItemCatalog | None: ...
@overload
def get_component(name: Literal["transmitter"]) -> Transmitter | None: ...
@overload
def get_component(name: Literal["atmosphere"]) -> Atmosphere | None: ...
@overload
def get_component(name: Literal["nocturna"]) -> Nocturna | None: ...
@overload
def get_component(name: Literal["orders"]) -> Orders | None: ...
@overload
def get_component(name: Literal["comms"]) -> Comms | None: ...
@overload
def get_component(name: Literal["console"]) -> Console | None: ...
@overload
def get_component(name: Literal["notebook"]) -> Notebook | None: ...
@overload
def get_component(name: Literal["markers"]) -> Markers | None: ...
@overload
def get_component(name: Literal["journal"]) -> Journal | None: ...
@overload
def get_component(name: Literal["construction_blueprint"]) -> ConstructionBlueprint | None: ...
@overload
def get_component(name: Literal["scanner_1"]) -> Scanner | None: ...
@overload
def get_component(name: Literal["harvester_1"]) -> Harvester | None: ...
@overload
def get_component(name: Literal["clock"]) -> Clock | None: ...
@overload
def get_component(name: Literal["gps"]) -> Gps | None: ...
@overload
def get_component(name: Literal["inventory"]) -> Inventory | None: ...
@overload
def get_component(name: Literal["thermometer"]) -> Thermometer | None: ...
@overload
def get_component(name: Literal["oxygen_sensor"]) -> OxygenSensor | None: ...
@overload
def get_component(name: Literal["pressure_sensor"]) -> PressureSensor | None: ...
@overload
def get_component(name: Literal["biomass_sensor"]) -> BiomassSensor | None: ...
@overload
def get_component(name: Literal["plants_sensor"]) -> PlantsSensor | None: ...
@overload
def get_component(name: Literal["wildlife_sensor"]) -> WildlifeSensor | None: ...
@overload
def get_component(name: Literal["outpost_home"]) -> OutpostComponent | None: ...
@overload
def get_component(name: Literal["bio_collector_1"]) -> BioCollector | None: ...
@overload
def get_component(name: Literal["bio_lab_1"]) -> BioLab | None: ...
@overload
def get_component(name: Literal["bio_exchange_1"]) -> BioExchange | None: ...
@overload
def get_component(name: _str) -> Component | None: ...
def get_component_by_name(name: _str) -> Component | None: ...

# Game API functions
def boot() -> ActionResult[Literal["booting", "already_booted"]]:
 """Initialize the system and run diagnostics. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
def activate_power() -> ActionResult[Literal["activating", "already_online", "boot_required"]]:
 """Turn on the power grid after the station has finished booting. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
def activate_sensors() -> ActionResult[Literal["initializing", "already_online", "power_required"]]:
 """Bring the sensor array online. Requires power. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
def get_pipe(pipe_id: _str) -> Pipe | None:
 """Look up an infrastructure pipe by id. Returns a live read-only `Pipe` handle, or `None` if no pipe by that id exists."""
 ...
def list_pipes() -> _list[Pipe]:
 """List every infrastructure pipe currently laid (complete or in-progress) as live read-only `Pipe` handles."""
 ...
# Output text to the console. Multiple values are joined by `sep` (default a single space). `end` is appended after the last value (default a newline). Console output is a character stream and the newlines in it are what break lines, so `end=""` leaves the line open and the next `print()` continues it: use that to build a row from several calls, then close it with a bare `print()`. Every call updates an unfinished line immediately. Within that row, `\r` returns the write position to the start and `\b` moves it back one visible character. Neither control erases text by itself; following text overwrites existing text. Neither control can enter an earlier row, and ANSI escape sequences are not interpreted.
def print(*values: Any, sep: _str = ..., end: _str = ...) -> None: ...
# Output an amber warning line to the persistent console. Same argument behavior as `print()`, but routed to the WARNINGS filter. Use it for background monitors that need attention without showing a toast. Use `notify(text, "warn")` when the player should be interrupted.
def warn(*values: Any, sep: _str = ..., end: _str = ...) -> None: ...
# Output low-priority telemetry to the persistent console. Same argument behavior as `print()`, but hidden from the ALL view unless debug output is enabled in console options. Use it for noisy tuning data that should not crowd normal logs.
def debug(*values: Any, sep: _str = ..., end: _str = ...) -> None: ...
def notify(text: _str, /, level: _str = ..., duration_seconds: _float = ..., dismissible: _bool = ...) -> None:
 """Show a toast to the player and add it to the **Computer → Notifications** archive. Use sparingly: for events that genuinely need the operator's attention (battery critical, contract solved, drone stranded); prefer `print()` for ongoing telemetry. `level` is `\"info\"` (default), `\"warn\"`, or `\"error\"` and drives the toast's color + the history badge. `duration_seconds` sets how long the toast stays before auto-dismissing: clamped to **0.5-30s**; omitted uses the default (**5s** info/warn, **6s** error). Pass **0** as the duration to make the toast **sticky**: it never auto-dismisses and stays until the player clicks it: use this for fatal errors that must be acknowledged. `dismissible` defaults to `True`; pass `False` as the fourth argument for a forced-read toast with no early close. A sticky toast is always dismissible, so it can never pin the screen. Identical consecutive notifications from the same script collapse inside a 1-second window, and a sticky already on screen is never duplicated, so a tight loop can't spam the screen."""
 ...
def sleep(seconds: _float, /) -> None:
 """Wait before continuing. **The argument is in real seconds**, not world-clock hours. The day cycle compresses **24** world-clock hours into a shorter real-time window, so `sleep(25)` is about 1 world-clock hour at the default 10-min-per-day pacing. For planet-aware delays, query the conversion: `sleep(get_component(\"clock\").real_seconds_per_hour() * 2)` waits exactly two world-clock hours regardless of pacing. Loops are paced automatically; `sleep()` is for deliberate delays."""
 ...
def len(value: Any, /) -> _int:
 """Length of a list, tuple, string, dict, or set."""
 ...
```

## `Loom`

```python
class Loom:
 """.loom"""
 def weave(self, a: _str, b: _str) -> _str:
 """Braid two strings into one and return it. Each character is one token. Deterministic: the same inputs always weave the same way, so probe it freely. A non-string argument raises `TypeError`; either input longer than 30 characters raises `ValueError`. The loom only weaves forward; build the reverse yourself."""
 ...
```

## `Marker`

```python
class Marker:
 """markers.get() / markers.list()"""
 id: _str
 x: _float
 y: _float
 label: _str
 note: _str
 icon: Literal["pin", "x", "check", "circle", "flag", "crosshair", "warning", "hammer", "resource", "power", "fluid", "star"]
 color: Literal["neutral", "accent", "success", "warning", "error", "violet"]
```

## `Markers`

```python
class Markers(Component):
 """Map Markers: Annotates the Planet Map from your scripts. Get it with `get_component(\"markers\")` after Cartography unlocks, then `markers.place(\"survey.rover_1.empty:120:-40\", 120, -40, \"No contact\", \"x\")` to drop a marker anywhere in the world, instantly, with no vehicle and no materials. Markers are notes, not blueprints: to actually build somewhere, pass the coordinates to `construction_blueprint.plan_structure(...)`. Store structured data in the Data Archive under the same id."""
 name: _str
 def place(self, id: _str, x: _float, y: _float, label: _str = ..., icon: _str = ..., color: _str = ..., note: _str = ...) -> ActionResult[Literal["ok", "invalid_key", "invalid_coords", "out_of_bounds", "invalid_icon", "invalid_color", "invalid_text", "limit_reached"]]:
 """Create or rewrite one marker. Reusing an id moves and restyles that marker instead of adding a second one, so a script that restarts after a save does not fill the map with duplicates. Coordinates are world meters and keep their fractions. Organize families of markers by id prefix, and include the controlling machine in the prefix, as in `\"survey.rover_1.\"`, so two scripts cannot overwrite each other. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get(self, id: _str) -> Marker | None:
 """Read one marker by id."""
 ...
 def list(self, prefix: _str = ...) -> _list[Marker]:
 """Read markers as a list sorted by id. Pass a prefix such as `\"build.\"` to read one family. Loop the result to route a vehicle: `for m in markers.list(\"build.\"): self.nav.set_target(m.x, m.y)`."""
 ...
 def remove(self, id: _str) -> ActionResult[Literal["ok", "not_found", "invalid_key"]]:
 """Delete one marker by id. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear(self, prefix: _str) -> CountResult[Literal["ok", "no_op", "invalid_key"]]:
 """Delete a whole family of markers by id prefix, then place the current ones again to keep a family in step with what your script now believes. The prefix is required: `markers.clear(\"\")` deletes every marker on the planet, including the ones you placed by hand, and nothing records who placed what. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `MiningSite`

```python
class MiningSite(Site):
 """any Site-returning API where `kind() == \"mineral\"`"""
 item_id: Literal["iron_ore", "silicon", "titanium", "cobalt", "rare_earth", "neutronium", "lead_ore"] | None
 hardness: _float | None
 purity: Literal["standard", "rich", "pure"] | None
```

## `MobileUnitRef`

```python
class MobileUnitRef:
 """fleet.mobile_units()"""
 category: Literal["vehicle", "drone"]
 id: _str
 name: _str
 kind: Literal["rover", "pioneer", "drone_small", "drone_medium", "drone_large"]
 status: Literal["idle", "moving", "stranded", "scanning", "surveying", "drilling", "discarding", "constructing", "transferring", "charging", "queued", "being_rescued", "traveling", "refueling", "waiting_service", "waiting_oil", "waiting_bay", "holding_weather", "scrambled", "stalled_no_battery", "stalled_no_oil", "stalled_no_route"]
 x: _float
 y: _float
 def position(self) -> Position:
 """Position snapshot from when this ref was returned."""
 ...
 is_docked: _bool
 is_being_rescued: _bool
 rescue_status: Literal["none", "outbound", "charging", "carrying", "returning"]
```

## `Notebook`

```python
class Notebook(Component):
 """Data Archive: Stores JSON-safe data that survives script restarts and save/load. Access the Data Archive with `get_component(\"notebook\")` after its research unlocks. Use Libraries to share code and the Signal Bus to share temporary live state."""
 name: _str
 def set(self, key: _str, value: Any) -> ActionResult[Literal["ok", "invalid_key", "entry_limit", "invalid_value"]]:
 """Store a JSON-safe value under a named key. The archive holds up to 512 entries; each value supports 8 nested levels, 16,384 total nodes counting values and containers, and 4,096 characters per string or dictionary key. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def transaction(self, key: _str, default: Any, updater: Any) -> ActionResult[Literal["ok", "invalid_key", "entry_limit", "invalid_value", "busy"]]:
 """Atomically transform one stored value within the same archive value limits. The updater may be any pure callable; it receives the latest value or supplied default and cannot sleep, yield, or mutate the world. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get(self, key: _str, default: Any = ...) -> Any:
 """Read a stored value by key. If the key is missing, returns the optional default argument; if no default is provided, returns `None`. Reading does not consume or modify the entry."""
 ...
 def has(self, key: _str) -> _bool:
 """Return `True` when the archive contains the key, otherwise `False`."""
 ...
 def delete(self, key: _str) -> ActionResult[Literal["ok", "not_found", "invalid_key"]]:
 """Remove one key. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def keys(self, prefix: _str = ...) -> _list[_str]:
 """Return archive keys as a sorted list. Pass a prefix such as `\"rover.\"` to list only matching keys."""
 ...
 def clear(self, prefix: _str = ...) -> CountResult[Literal["ok", "no_op", "invalid_key"]]:
 """Remove archived entries. With no prefix it clears the whole archive; with a prefix it clears matching keys. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `OilPump`

```python
class OilPump(Component):
 """Oil Pump: Extracts oil from a surveyed well at a throttle your script sets. Oil wells run in active and dormant phases, so buffer the output through a Liquid Tank to ride out the dry spells."""
 name: _str
 def well(self) -> OilWell:
 """The `OilWell` this pump is bolted to. Same shape as `WaterWell`, yield tier (1×/2×/3×) and base flow rate."""
 ...
 def pump_rate(self) -> _float:
 """Total oil delivered across every reachable connected destination this tick, in t/h. **0** when throttle is **0**, the well is dormant, or no destination can accept flow. See `is_stalled()` to tell a routing block from a dormant well."""
 ...
 def well_active(self) -> _bool:
 """Reads the well's pulse. `True`, the well below is in its active phase and delivers at full rate. `False`, dormant: no oil at any throttle, typically for several hours. Bank oil in a downstream Liquid Tank and throttle down during the gap to save watts."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if, on the last flow tick, the powered pump had an open throttle and oil available from its active well but could transfer none across its connected routes. Dormancy, a closed throttle, or lack of power does not report a stall. Declare a destination with `self.oil_out.connect(...)`, or let consumers connect their own `oil_in` ports to this Pump."""
 ...
 def throttle(self) -> _float:
 """Current throttle setting (**0-1**). **0** by default."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set the pump's total output rate (**0-1**) across reachable connected destinations. `0` idles the pump; `1` allows full active-well output subject to headroom and throughput. This script-owned setpoint resets to `0` when the script stops, ends, or errors, so keep the control loop running while the Pump should operate. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 oil_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `OilWell`

```python
class OilWell(Site):
 """any Site-returning API where `kind() == \"oil\"` (e.g. `oil_pump.well()`, sonar / journal queries)"""
 def yield_tier(self) -> Literal["standard", "rich", "pure"] | None:
 """One of `\"standard\"` (**1×**) / `\"rich\"` (**2×**) / `\"pure\"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying."""
 ...
 def flow_rate(self) -> _float | None:
 """Peak tons of oil per hour. **8 / 16 / 24** for standard / rich / pure. Oil wells pulse through active and dormant phases: a dormant well delivers nothing at any throttle (read the pump's `well_active()`). `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying."""
 ...
 def has_pump(self) -> _bool:
 """Boolean: `True` if an Oil Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings."""
 ...
 def pump_id(self) -> _str:
 """Current machine id of the Oil Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings."""
 ...
```

## `Panel`

```python
class Panel:
 """panel (panel scripts only). Create one on the **Control Room** page; see `custom_panels`"""
 def card(self, x: _float, y: _float, w: _float, h: _float, title: _str = ...) -> ActionResult[Literal["ok"]]:
 """Bordered subsection with optional title bar. Use to group related content visually, mirrors the dashboard's card aesthetic.

 `preview
 card(8, 8, 264, 64, \"Section\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def divider(self, x1: _float, y1: _float, x2: _float, y2: _float) -> ActionResult[Literal["ok"]]:
 """Horizontal or vertical separator line in the muted border color. Use to break a panel into visual zones.

 `preview
 divider(10, 40, 270, 40)
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def label(self, x: _float, y: _float, text: _str, style: _str = ...) -> ActionResult[Literal["ok"]]:
 """Semantically styled text. `style` accepts `\"title\"` (bright, bold), `\"caption\"` (muted, uppercase), `\"muted\"` (secondary), `\"value\"` (numeric readout). Defaults to `\"title\"`. Use instead of `draw_text` when you want the dashboard's text hierarchy applied automatically.

 `preview
 label(10, 30, \"OXYGEN\", \"caption\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def status_dot(self, x: _float, y: _float, r: _float, status: _str) -> ActionResult[Literal["ok"]]:
 """Colored disc resolved from a status string. Recognized values: `\"running\"` (green), `\"paused\"` (warning), `\"error\"` (error red), `\"idle\"` (muted). Renders with a subtle outer glow ring. Useful for per-row indicators in machine lists.

 `preview
 status_dot(0, 0, 5, \"running\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def toggle(self, x: _float, y: _float, on: _bool, label: _str = ...) -> ActionResult[Literal["ok"]]:
 """Green/grey power-toggle pill matching the dashboard's machine on/off control. This widget only displays the `on` value you pass in; use `panel.switch(...)` for a clickable control.

 `preview
 toggle(10, 12, true, \"powered\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def pill(self, x: _float, y: _float, text: _str, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Rounded badge with text, achievement-style. Color accepts theme tokens (`\"accent\"`, `\"success\"`, `\"warning\"`, `\"error\"`, `\"text-muted\"`) or hex. Use for status labels or category tags.

 `preview
 pill(10, 22, \"earned\", \"success\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def counter(self, x: _float, y: _float, value: Any, label: _str = ..., size: _float = ...) -> ActionResult[Literal["ok"]]:
 """Big-number stat block, large value on top, small uppercase label below. Use for headline numbers (credits, day count, ingot inventory). `size` defaults to **24**.

 `preview
 counter(16, 38, 87, \"shipped\", 26)
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def progress_bar(self, x: _float, y: _float, w: _float, h: _float, fraction: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Horizontal fill bar with track + filled accent. `fraction` clamps to **0-1**. Color defaults to `\"accent\"`; use `\"success\"`, `\"warning\"`, `\"error\"` for traffic-light cues.

 `preview
 progress_bar(0.72, \"success\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def vertical_bar(self, x: _float, y: _float, w: _float, h: _float, fraction: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Vertical fill bar, fills from the bottom up. Same `fraction` and color rules as `progress_bar`. Use when the panel layout favors verticality (multi-tank stacks, atmospheric stacks).

 `preview
 vertical_bar(110, 10, 30, 60, 0.6)
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def bar_chart(self, x: _float, y: _float, w: _float, h: _float, values: Any, max: _float = ..., labels: Any = ...) -> ActionResult[Literal["ok"]]:
 """Multi-bar comparison chart, themed alternating colors, optional labels under each bar. `max` is optional, omit to auto-scale to the largest value.

 `preview
 bar_chart(0, 0, 0, 0, [42, 80, 26, 61, 95], 100)
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def gauge(self, x: _float, y: _float, radius: _float, fraction: _float, label: _str = ...) -> ActionResult[Literal["ok"]]:
 """Three-quarter-circle dial with arc fill. `fraction` clamps to **0-1**, sweeping **270°** from bottom-left around to bottom-right. Optional center label sits in the middle (typically the value as text).

 `preview
 gauge(140, 50, 32, 0.62, \"62%\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def spark_line(self, x: _float, y: _float, w: _float, h: _float, values: Any) -> ActionResult[Literal["ok"]]:
 """Compact trend line drawn from a numeric series. Player accumulates values into a list and pushes the most recent on each tick, the widget normalizes to the series' min/max range and fills a subtle area below the line. Empty / single-value series no-op.

 `preview
 spark_line(0, 0, 0, 0)
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def button(self, key: _str, x: _float, y: _float, w: _float = ..., h: _float = ..., label: _str = ...) -> _bool:
 """A clickable button. Pass a unique `key` so the click routes back to it. Returns `True` the single tick it's pressed (momentary), branch on it: `if panel.button(\"shed\", 10, 12): power.set_powered(...)`. `w`/`h` default to **90×26**. The first input widget that lets a card *act* on the player's click, not just paint.

 `preview
 button(10, 12, 90, 26, \"shed now\")
 `
 """
 ...
 def switch(self, key: _str, x: _float, y: _float, default_on: _bool = ..., label: _str = ...) -> _bool:
 """An interactive on/off switch, the player clicks it to flip. Pass a unique `key`; `default_on` sets the starting state the first time the card runs. Returns the current boolean every tick, and the flip persists in the card's state across reloads. Unlike the display `toggle` (which only shows a state you pass in), this one is clickable: `auto = panel.switch(\"auto_recover\", 165, 128, True)`.

 `preview
 switch(10, 12, true, \"auto-recover\")
 `
 """
 ...
 def slider(self, key: _str, x: _float, y: _float, w: _float, default: _float = ..., label: _str = ...) -> _float:
 """A horizontal slider the player clicks to set a value. Pass a unique `key`; `default` (**0-1**) sets the starting value. Returns the current value as a **0-1** number every tick, persisted in the card's state. Use it for thresholds the player tunes live, a buy-trigger level, a throttle target.

 `preview
 slider(10, 14, 120, 0.5, \"rate\")
 `
 """
 ...
 def draw_text(self, x: _float, y: _float, text: _str, size: _float = ..., color: _str = ..., wrap: _float = ...) -> ActionResult[Literal["ok"]]:
 """Text rendered in monospace at the given size. Optional `wrap` (pixel width) enables greedy word-wrapping into a multi-line block, useful for log feeds and order briefings. Color accepts theme tokens or hex.

 `preview
 draw_text(10, 24, \"Hello, panel.\", 14, \"text-bright\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def icon_ids(self) -> _list[_str]:
 """List of every id `draw_icon` can render, sorted. Covers more than the items you can hold: fluids, creatures, essences, and machine art all have icons. Use it to build a picker, validate an id before drawing, or just print the catalog once while you are writing a card.

 `
 for icon in panel.icon_ids():
 print(icon)
 `
 """
 ...
 def draw_icon(self, x: _float, y: _float, item_id: _str, size: _float = ...) -> ActionResult[Literal["ok"]]:
 """Render any icon from the game's item catalog at the requested size (default **32** pixels). Item id is the same string you'd pass to `inventory` / `storage_bin` APIs (`\"iron_ore\"`, `\"iron_ingot\"`, `\"water\"`, etc.), plus things you never hold such as fluids and creatures. `panel.icon_ids()` returns the full list, and every item's own page lives under **Database** in this panel. Unknown ids no-op silently.

 `preview
 draw_icon()
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def draw_rect(self, x: _float, y: _float, w: _float, h: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Outlined rectangle in the given color (defaults to `\"border\"`). Use for custom subsection borders or visual frames.

 `preview
 draw_rect(10, 10, 260, 60, \"accent\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def fill_rect(self, x: _float, y: _float, w: _float, h: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Filled rectangle in the given color (defaults to `\"accent\"`). Use for backgrounds, progress fills, color blocks.

 `preview
 fill_rect(10, 10, 260, 60, \"success\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def draw_circle(self, x: _float, y: _float, r: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Outlined circle in the given color.

 `preview
 draw_circle(140, 40, 24, \"accent\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def fill_circle(self, x: _float, y: _float, r: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Filled disc in the given color.

 `preview
 fill_circle(140, 40, 24, \"warning\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def draw_line(self, x1: _float, y1: _float, x2: _float, y2: _float, color: _str = ...) -> ActionResult[Literal["ok"]]:
 """Single straight line.

 `preview
 draw_line(10, 40, 270, 40, \"accent\")
 ` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`.
 """
 ...
 def clear(self) -> ActionResult[Literal["ok"]]:
 """Wipe the panel canvas. Call at the top of every `while True:` loop iteration so old paint doesn't ghost behind new paint. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def width(self) -> _float:
 """Current logical canvas width in pixels: **500** for a one-column card or **1000** for a two-column card. Use for ratio-based positioning."""
 ...
 def height(self) -> _float:
 """Current logical canvas height in pixels: **200** for a one-row card or **400** for a two-row card. Use for ratio-based positioning."""
 ...
```

## `Pipe`

```python
class Pipe:
 """list_pipes() / get_pipe(pipe_id)"""
 id: _str
 def start(self) -> Position | None:
 """Geometric start coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry."""
 ...
 def end(self) -> Position | None:
 """Geometric end coordinate of this pipe piece as a `Position`. This is construction geometry, not flow direction. Returns `None` only if malformed state contains no segment geometry."""
 ...
 def type(self) -> Literal["gas", "liquid"]:
 """Pipe hardware medium: `\"gas\"` or `\"liquid\"`. Use `contents()` for the exact substance established by complete provider-consumer connections."""
 ...
 def contents(self) -> Literal["steam", "water", "oil", "frozen_essence", "coastal_essence", "geothermal_essence", "volcanic_essence", "deep_essence", "ammonia", "swamp_gas", "raw_sulfur_gas", "sulfur_gas", "raw_chlorine", "chlorine", "brine", "raw_cryofluid", "cryofluid", "raw_quicksilver", "quicksilver"] | None:
 """The one exact fluid established by complete player connections whose locations this physical component reaches, such as `\"steam\"`, `\"water\"`, or `\"oil\"`. Returns `None` when there is no complete connection or multiple exact substances conflict. Activity, power, throttle, flow, and headroom do not change this identity."""
 ...
 def conflicting_contents(self) -> _list[_str]:
 """Sorted exact substances established by complete provider-consumer connections when more than one uses this physical component, or an empty list. A non-empty result means flow is halted."""
 ...
 def connections(self) -> _list[_dict[_str, _str]]:
 """Diagnostic machine-port claims established on this physical component. Each dictionary contains `machine_id`, `port`, `direction`, `fluid`, and a representative `pipe_id` from the component; players never connect to that pipe id directly."""
 ...
 def incompatible_sinks(self) -> _list[_str]:
 """Ids of directly connected consumers that cannot accept `contents()`. Those consumers receive nothing, while compatible branches continue flowing. Live read."""
 ...
 def is_complete(self) -> _bool:
 """Boolean: `True` once the Constructor has finished laying the pipe and flow can run. Live read."""
 ...
 def length(self) -> _float:
 """Total length of the pipe in meters, summed over every H/V segment."""
 ...
 def laying_head(self) -> _tuple[_float, _float] | None:
 """`[x, y]` coordinates of the current laying head while incomplete, or `None` once complete. Live read."""
 ...
 def flow_rate(self) -> _float:
 """Tons per world hour (`t/h`) currently moving through the pipe. **0** while incomplete, stalled, source-empty, or conflicted. Live read."""
 ...
 def state(self) -> Literal["flowing", "stalled", "incomplete", "no_source", "conflict"]:
 """Current pipe state: one of `\"flowing\"` / `\"stalled\"` / `\"incomplete\"` / `\"no_source\"` / `\"conflict\"`. Live read."""
 ...
```

## `Planet`

```python
class Planet:
 """transmitter.list_planets()"""
 id: _str
 name: _str
 description: _str
```

## `PointOfInterest`

```python
class PointOfInterest:
 """nocturna.points_of_interest()"""
 x: _float
 y: _float
 scanned: _bool
 kind: Literal["unknown", "mineral", "biomass", "thermal", "water", "oil", "exotic", "inert"]
```

## `PortableBattery`

```python
class PortableBattery:
 """self.battery.holders()[...].batteries[...]"""
 id: Literal["portable_battery", "heavy_portable_battery"]
 def level(self) -> _float:
 """Charge level as a fraction, **0-1**."""
 ...
 def wh(self) -> _float:
 """Current charge in Wh."""
 ...
 def capacity(self) -> _float:
 """Rated capacity in Wh."""
 ...
```

## `Rack`

```python
class Rack:
 """self.cargo.racks()"""
 id: _str
 size: Literal["small", "medium", "large"]
 bins: _list[Bin | None]
```

## `Reactor`

```python
class Reactor(Component):
 """Reactor: Generates up to **5,000 W** from Fuel Rods and cooling water. One rod lasts **72 hours** at heat **1.0**; fuel use follows commanded heat even while the core is warming or outside its efficient band."""
 name: _str
 outpost: OutpostRef
 def set_heat(self, value: _float) -> ActionResult[Literal["ok"]]:
 """Set reactor heat from **0-1**. Values outside the range are clamped. The setting returns to **0** when the owning script stops. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def heat(self) -> _float:
 """Current heat setting from **0-1**."""
 ...
 def temperature(self) -> _float:
 """Current temperature in °C. Output begins at **300**, peaks at **900**, then falls back to zero across the **900-950** red band. **950** triggers an automatic overheat shutdown."""
 ...
 def fuel_level(self) -> _float:
 """Active Fuel Rod life from **0-1**. One full rod lasts **72 hours** at heat **1.0**; lower heat extends it proportionally. The next rod is taken automatically from `input`."""
 ...
 def power_output(self) -> _float:
 """Watts on the grid this tick."""
 ...
 def status(self) -> Literal["running", "overheated", "no_fuel", "no_coolant"]:
 """Current operating state: `running`, `overheated`, `no_fuel`, or `no_coolant`. Shutdowns recover automatically after cooling or supplies return."""
 ...
 water_in: FluidPort
 input: InputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `Research`

```python
class Research(Component):
 """Research: Checks global research progress through `get_component(\"research\")`. Use the public ids shown on the Research page, such as `\"research_auto_feeders\"`. Available from the beginning and read-only."""
 name: _str
 def is_unlocked(self, research_id: _str) -> _bool:
 """Return `True` only when `research_id` is known and unlocked. Known but locked research returns `False`. An unknown id also returns `False` without printing, so scripts can handle every lookup result themselves."""
 ...
 def unlocked(self) -> _list[_str]:
 """Return a fresh list of public research ids that are unlocked and available in the current build. The list follows stable Research-page registry order, contains no internal capability ids, and can be modified without changing game state."""
 ...
```

## `RunControl`

```python
class RunControl(Component):
 """Run Control: Shared start/stop controller for machine scripts, the remote equivalent of a machine card's Run / Stop buttons. Use it to build a supervisor: one script that watches the base and shuts down another machine when it detects a fault, without parking that machine in a permanent `sleep` loop. This is the **run/stop axis**, separate from `power_control` (the breaker): `stop` ends a script and latches it off, while a power toggle only pauses and auto-resumes."""
 name: _str
 def is_running(self, machine_id: _str) -> _bool:
 """Returns `True` when the named machine has a script actively scheduled, including while it sits mid-`sleep` or mid-action. A paused, stopped, completed, or errored script reads `False`, as does an unknown machine id. Call it before `start`/`stop` to avoid redundant commands."""
 ...
 def stop(self, machine_id: _str) -> ActionResult[Literal["ok", "not_found", "no_script"]]:
 """Stops the named machine's script the same way the card's Stop button does: `run.stop(\"o2gen_1\")` ends the script, resets its setpoints to idle, and zeroes its live readouts. Structural state (recipes, in-flight progress, loaded materials) is preserved. The stop is **latched**, unlike a power-off, the script does not auto-resume; restart it with `start`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def start(self, machine_id: _str) -> ActionResult[Literal["ok", "not_found", "no_script", "already_running", "not_powered", "under_construction"]]:
 """Runs the named machine's script from the top, the same way the card's Run button does: `run.start(\"o2gen_1\")`. A fresh run restarts from the first line; it does not resume mid-script. The machine must be powered and fully built. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
```

## `Scanner`

```python
class Scanner(Component):
 """Scanner: Reveals the sectors of the harvester grid around base so the Harvester knows where to collect. It maps the home grid only; exploring the wider planet is a job for a vehicle's sonar."""
 name: _str
 def scan(self, sector: _str) -> ScanResult[Literal["ok", "empty"]]:
 """Scan one local sector with `self.scan(\"E14\")`. The scan takes a few ticks and pauses the script. Malformed or out-of-bounds sector ids raise `ValueError`. This local-grid scanner finds surface items, not planetary `Site` contacts. Fixed result contract: `ScanResult`; branch on `.status` and read `.message`. Payload fields: `.id`, `.name`, and `.value`."""
 ...
 def get_scanned(self) -> _dict[_str, ScanResult]:
 """Every previously scanned sector as a fresh dict `{sector_id: ScanResult}`. Iterate with `.keys()` / `.values()` / `.items()`, or index by sector id: `self.get_scanned()[\"E14\"]`. A sector only needs to be physically scanned once, and that history persists across script runs. Each `get_scanned()` call reflects the current contents of those sectors, including items collected or dropped since the last call. A dict or `ScanResult` already saved in your script does not update itself, so call `get_scanned()` again before choosing another target. Returns an empty dict if nothing has been scanned yet."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `ScriptCommand`

```python
class ScriptCommand:
 """self.peek_command() / self.next_command().command after status == \"ok\""""
 id: _str
 name: _str
 args: _dict[_str, Any]
 source: Literal["editor", "script", "signal", "system"]
 created_at: _float
 tick: _float | None
```

## `Shop`

```python
class Shop(Component):
 """Shop: Buys from and sells to Earth. Use `get_component(\"shop\")` to automate surplus sales or purchases when a threshold is reached. The same catalogue and prices are used by the Shop UI."""
 name: _str
 def sell(self, item_id: _str, quantity: _int = ...) -> SaleResult[Literal["ok", "not_sellable", "no_stock"]]:
 """Sell a positive whole-number `quantity` of `item_id`, defaulting to **1**. The complete quantity is removed from the lowest-indexed matching Inventory slots in one transaction; if Inventory contains fewer units, nothing is sold. Battery products refund their charge percentage, with a **50% minimum**; fully charged batteries refund their full normal value. Use the Inventory page when you need to choose one exact battery instance. Fixed result contract: `SaleResult`; branch on `.status` and read `.message`. Payload fields: `.item_id`, `.units`, and `.credits`."""
 ...
 def sell_all(self, item_id: _str) -> SaleResult[Literal["ok", "not_sellable", "no_stock"]]:
 """Sell every unit of `item_id` currently in Inventory in one transaction. There is no per-unit cooldown. Each battery product is valued from its own retained charge, with a **50% minimum** and full normal value at full charge. Fixed result contract: `SaleResult`; branch on `.status` and read `.message`. Payload fields: `.item_id`, `.units`, and `.credits`."""
 ...
 def buy(self, item_id: _str, quantity: _int = ...) -> ActionResult[Literal["ok", "not_found", "locked", "insufficient_credits", "inventory_full"]]:
 """Buy a positive whole-number `quantity` of `item_id`, defaulting to **1**. The complete quantity must be affordable and fit in base Inventory; otherwise nothing is charged or delivered. Purchases are placed in base Inventory, not delivered directly to a machine or remote outpost. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_catalogue(self) -> _list[ShopItem]:
 """Every available catalogue entry as a list of `{id, name, cost}` objects. Use to pick a target dynamically or to show a filtered picker in a script. The Earth shop never runs out of catalogue items; entries hidden by tech gates don't appear."""
 ...
```

## `SignalReceiver`

```python
class SignalReceiver:
 """weather_station.signal_receiver"""
 def transmissions(self) -> _list[SignalTransmission]:
 """Raw transmissions audible to this powered station right now. More than one event may be present. Ordering is stable, but copies sharing a packet number are not ordered by validity. The receiver stores no history."""
 ...
```

## `SignalTransmission`

```python
class SignalTransmission:
 """SignalReceiver.transmissions()"""
 event_id: _str
 number: _int
 total: _int
 channel: Literal["broadcast", "frozen", "coastal", "geothermal", "volcanic", "deep"]
 data: _str
 checksum: _int
 emitted_at_gh: _float
 expires_at_gh: _float
 source_station_id: _str
```

## `Site`

```python
class Site:
 """SonarModule.scan().sites / SonarModule.survey().site / journal and site-bound machine queries"""
 id: _str
 name: _str
 x: _float
 y: _float
 def kind(self) -> Literal["mineral", "thermal", "water", "oil", "exotic", "inert"]:
 """One of `\"mineral\"` / `\"thermal\"` / `\"water\"` / `\"oil\"` / `\"exotic\"` / `\"inert\"`. Use it to narrow to the concrete subtype: after `if site.kind() == \"mineral\":` the editor surfaces `MiningSite`-specific fields on `site`. `\"inert\"` means sonar resolved a physical formation with no extractable signal."""
 ...
 def position(self) -> Position:
 """`Position` snapshot with `.x` / `.y` world coordinates."""
 ...
 surveyed: _bool
```

## `Sprinkler`

```python
class Sprinkler(Component):
 """Sprinkler: Waters the four orthogonally adjacent field cells (directly above, below, left, and right) while powered, supplied, and enabled."""
 name: _str
 def set_enabled(self, enabled: _bool) -> ActionResult[Literal["ok"]]:
 """Command watering on or off. Power loss pauses the script but preserves this setpoint; stopping the machine script resets it to `False`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_enabled(self) -> _bool:
 """`True` when the running script has commanded watering on."""
 ...
 def is_active(self) -> _bool:
 """`True` when commanded on with power and water available."""
 ...
 def is_supplied(self) -> _bool:
 """`True` when the sprinkler is commanded on, powered, and has water in its `water_in` buffer. If disabled, unpowered, or dry, covered cells lose `watered`."""
 ...
 def status(self) -> Literal["not_placed", "disabled", "no_power", "no_water", "active"]:
 """Exact operating state: `\"not_placed\"`, `\"disabled\"`, `\"no_power\"`, `\"no_water\"`, or `\"active\"`."""
 ...
 def buffer(self) -> _float:
 """Fraction of the onboard water buffer currently filled (**0-1**). It drops while watering and refills from the connected `water_in` source."""
 ...
 def tier(self) -> _int:
 """Deployed tier (**1-4**). Mk I/II/III/IV provide **1×/2×/4×/8×** supported plant output, draw **5/25/100/500 W**, and consume **2/10/200/1,000 t/h Water** while active."""
 ...
 def position(self) -> _str:
 """Grid sector occupied by this sprinkler, such as `\"E14\"`."""
 ...
 water_in: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `SteamCondenser`

```python
class SteamCondenser(Component):
 """Steam Condenser: Converts incoming steam into clean water at a 1:1 mass ratio. Scripted throttle controls its 250 t/h peak and 150 W draw."""
 name: _str
 outpost: OutpostRef
 def condensation_rate(self) -> _float:
 """Clean water produced on the last simulation tick in t/h. Full throttle reaches **250 t/h** when the steam input has supply, the water output has room, and the host outpost is not overcrowded."""
 ...
 def efficiency(self) -> _float:
 """Fraction of the throttle's requested condensation completed on the last tick (**0.0-1.0**). Low values mean the steam input ran short or the water output filled before the tick completed."""
 ...
 def is_stalled(self) -> _bool:
 """`True` when throttle is above zero and the current fluid state blocks condensation because `steam_in` is empty or `water_out` is full. This is derived immediately from both ports; use `status()` to distinguish the blockers."""
 ...
 def status(self) -> Literal["idle", "no_power", "no_steam", "output_full", "running"]:
 """Current actionable state: `\"idle\"`, `\"no_power\"`, `\"no_steam\"`, `\"output_full\"`, or `\"running\"`. This is derived live from throttle, power, and both fluid buffers. Once throttle is **0**, it reports `\"idle\"`; inspect port levels to decide when to reopen it."""
 ...
 def throttle(self) -> _float:
 """Current condensation setpoint (**0.0-1.0**). It scales steam use, water output, and power draw linearly."""
 ...
 def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
 """Set condensation from **0.0-1.0** (clamped). **0** idles with no conversion or variable draw. **1.0** requests **250 t/h** and **150 W**. Draw follows the throttle even when steam is empty or the output is full, so set **0** to save power while blocked. This script-owned setpoint resets to **0** when the script stops, ends, or errors. Call from this Condenser's own script. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 steam_in: FluidPort
 water_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `SupplyDock`

```python
class SupplyDock(Component):
 """Supply Dock: Ships finished goods to Earth at **25 units/h** before throughput research. A script assigns a contractor or Weekly Earth Order, loads what it needs, and enables dispatch; completion or expiry stops the dock until reassigned."""
 name: _str
 outpost: OutpostRef
 def capacity(self) -> _int:
 """Total units still owed across every item of the active Order (the dock's remaining demand). Returns **0** when no Order is assigned. Use as the upper bound for how much you still need to load + ship."""
 ...
 def total(self) -> _int:
 """Sum of units currently loaded across every slot. Compare to `capacity()` to see how much more the dock still needs to ingest; `total() == 0` means every slot is empty."""
 ...
 def count(self, item_id: _str) -> _int:
 """Units of `item_id` currently held across the dock's slots. Returns **0** if the dock holds none of that item. Use before loading more to avoid redundant `take()` calls: `if self.count(\"iron_ore\") < 20: self.input.take(\"iron_ore\", 20)`."""
 ...
 def slots(self) -> _list[DockSlot]:
 """The dock's physical slots as a list of `DockSlot` objects (`.index`, `.item_id`, `.count`). Always **5** entries, indexed **0-4**; slots not opened by the current Order have `.item_id == None` and `.count == 0`. See `DockSlot`."""
 ...
 def current_order(self) -> Order | None:
 """Returns this dock's active Earth `Order`, or `None` if no Earth Order is assigned. Flips to `None` automatically when the Earth Order completes. Use it to read `.requires` and `.shipped` before deciding what to load."""
 ...
 def set_order(self, order_id: _str) -> ActionResult[Literal["ok", "unknown_order", "completed", "cargo_present"]]:
 """Assign an Earth Order to this dock. Discover ids with `orders.list_orders()` or `orders.list_weekly_orders()`, then pass one to `self.set_order(id)`. Several docks may serve the **same** order and share shipped progress. Cargo is physical: drain this dock through a local machine or vehicle before switching orders. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def clear_order(self) -> ActionResult[Literal["ok"]]:
 """Release this dock's assignment and stop dispatch. Loaded cargo stays inside the dock. Recover it directly with `self.input.eject(destination, item_id, count)`, or by connecting a local machine or vehicle input to this Supply Dock. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def set_enabled(self, on: _bool) -> ActionResult[Literal["ok"]]:
 """Toggle the continuous dispatcher. `True` resumes shipping; `False` pauses it. Loading is unaffected either way, the input port still accepts material. **Auto-flips off** when the assigned order completes; the script must re-enable after the next `set_order` call. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def is_enabled(self) -> _bool:
 """`True` while the dispatcher is active. It becomes `False` after `set_enabled(False)` or when the assigned Order completes. A new dock starts enabled, so assigning an Order while cargo is loaded begins shipping immediately."""
 ...
 def dispatch_rate(self) -> _float:
 """The dispatcher's current effective throughput in **units/h**, already including throughput research and any outpost overcrowding penalty. The base rate is **25** (one unit every **2.4** minutes); **Bulk Logistics II** multiplies it by **4**, and **Bulk Logistics III** by **16**. Multiply this returned value by hours elapsed to predict how much the dock will ship."""
 ...
 def current_dispatch(self) -> _str | None:
 """The `item_id` the dispatcher is currently emitting, or `None` when idle (no power, no Order, dispatcher paused via `set_enabled(False)`, or no shippable unit loaded). Useful for scripts that want to know which material is flowing right now."""
 ...
 def dispatch_progress(self) -> _float:
 """Fraction **0-1** of the current unit's accumulator toward emission. Holds at **0** while the dock has nothing shippable loaded, the charge starts when a shippable unit lands. Drives the perimeter-clock animation on the dock card; scripts can use it to estimate \"next launch in X hours.\""""
 ...
 input: InputSlot
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `TempHeater`

```python
class TempHeater(Component):
 """Heat Generator: Warms the planet surface by producing heat. The best power setting shifts with the day's weather, so a script reads the conditions and holds the heater at the right level."""
 name: _str
 outpost: OutpostRef
 input: InputSlot
 steam_in: FluidPort
 def set_power(self, watts: _float) -> ActionResult[Literal["ok"]]:
 """Set base heater power from **0-10**; values outside that range are clamped. `0` turns heating off. The best positive setting depends on the current `thermal_state()`, so update it with `self.set_power(value)` as conditions change. Higher Mk tiers multiply grid draw without changing the best base setting. A poor setting wastes energy and reduces heat output. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def thermal_state(self) -> Literal["clear", "dust_storm", "heat_bleed", "dust_veil"]:
 """Current daily heater thermal state, one of `\"clear\"`, `\"dust_storm\"`, `\"heat_bleed\"`, `\"dust_veil\"`. Each state has its own optimal positive `set_power()` value. The state is stable throughout the current day and changes only on a new day, so read it at the start of each iteration and branch when the string changes: `if state == \"clear\": self.set_power(5)` etc. Your job is figuring out the four optimal values."""
 ...
 def efficiency(self) -> _float:
 """Current heating efficiency (**0-100%**). Hits **100%** only when `set_power()` exactly matches the current `thermal_state()`'s optimal, and falls off *steeply* around it (not linearly): about **31%** one step away, then a **10%** floor for any setting two or more steps off. Reads **0%** only when power is `0`. Scan positive power values and take the setting that reads **100%** as each state's optimal."""
 ...
 def output(self) -> _float:
 """Current heat-unit production rate per hour at the current settings. Heat accumulates to raise surface temperature over many days; the sensor rate display projects per-day totals. Reflects `efficiency() × tier multiplier`. Reads `0` if unpowered or no script running. Recomputed live on every read, a fresh `set_power(...)` is reflected immediately."""
 ...
 def tier(self) -> _int:
 """Permanently installed Mk tier as an integer (**1-4**). Upgrade packs raise this value; temporary Mk III steam starvation does not. Compare with `effective_tier()` when diagnosing a supplied or degraded heater."""
 ...
 def is_degraded(self) -> _bool:
 """`True` when a Mk III pack is starved of its required fluid input and the machine has fallen back to the previous tier multiplier for this tick. Check after applying a Mk III pack, if `True`, your tier-3 heater is temporarily running as Mk II; look at `self.steam_in.level()` and the upstream thermal cap."""
 ...
 def effective_tier(self) -> _int:
 """The tier actually in effect this tick: `tier()` normally, previous tier while `is_degraded()` is `True`. Scripts that rebalance steam flow between heaters should compare `effective_tier()` with `tier()`."""
 ...
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `ThermalCap`

```python
class ThermalCap(Component):
 """Thermal Cap: Captures Steam from a thermal vent. If its chamber reaches 100%, every stored ton blows into the atmosphere; a script must release, route, or relieve pressure."""
 name: _str
 def vent(self) -> ThermalVent:
 """The `ThermalVent` this cap sits on. Field availability follows the sonar tier that last surveyed the vent: basic reveals phase, wide adds steam rates, deep adds cycle timing. Use `self.vent().current_phase()` (or the cap's own `phase()`) to know when steam is coming. See `ThermalVent`."""
 ...
 def phase(self) -> Literal["active", "dormant"] | None:
 """`\"active\"` while the vent produces steam (your chamber fills) or `\"dormant\"` while it rests (the chamber only drains). `None` until the vent is surveyed. Drive your release loop off this: open the throttle when active, ease it when dormant so you do not run downstream dry."""
 ...
 def next_phase_in(self) -> _float | None:
 """Game-minutes until the vent flips between active and dormant, so you can open up before a surge or ease off before a dry spell. Returns `None` unless the vent was **Deep**-surveyed, so a predictive loop is the payoff for deep sonar."""
 ...
 def pressure(self) -> _float:
 """Chamber fill in the `0.0 to 1.0` range. It climbs while the cap captures steam from the vent and drops as you release through `steam_out`. Hit `1.0` and the cap **overpressurizes**: the whole chamber blows off to atmosphere and rebuilds from empty. The job is keeping this off the ceiling, so poll it every tick and open the throttle as it rises."""
 ...
 def capture_rate(self) -> _float:
 """Steam captured from the vent on the last tick, in t/h. **0** during the dormant phase, up to the vent's current output while active. Already factors in the vent's phase, so read it instead of computing from the vent rate. Updates once per flow tick."""
 ...
 def is_overpressured(self) -> _bool:
 """`True` the tick the chamber tops out and blows its whole contents to atmosphere. After that the chamber is empty and must refill from the vent before you get steam again, so everything you had banked is gone. If you see this, you released too slowly, open the throttle sooner."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if, on the last flow tick, the powered cap had an open throttle and chamber steam available for release but could transfer none across its connected routes. An empty chamber, closed throttle, or lack of power does not report a stall. Declare a destination with `self.steam_out.connect(...)`, or let consumers connect their own `steam_in` ports to this Cap."""
 ...
 def throttle(self) -> _float:
 """The current release-valve setting, `0.0` (sealed) to `1.0` (wide open). Read it back after `set_throttle(...)`."""
 ...
 def set_throttle(self, t: _float) -> ActionResult[Literal["ok"]]:
 """Open the cap's release valve in the `0.0 to 1.0` range (clamped). `0` seals the chamber so it fills; `1.0` releases steam across all reachable connected destinations as fast as chamber supply, destination headroom, and throughput allow. Your primary knob against overpressure, so call it every tick against `pressure()`. This script-owned setpoint resets to `0` when the script stops, ends, or errors. If no destination can accept enough and `pressure()` still climbs, use `set_relief(...)` to shed the surplus. `[self only]` Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def relief(self) -> _float:
 """The current relief-valve setting, `0.0` (shut) to `1.0` (wide open). Read it back after `set_relief(...)`."""
 ...
 def relief_rate(self) -> _float:
 """Steam wasted to atmosphere through the relief valve this tick, in t/h. `0` when the relief valve is shut. Watch it to see how much surplus you're dumping."""
 ...
 def set_relief(self, t: _float) -> ActionResult[Literal["ok"]]:
 """Open the relief valve from **0-1** to dump excess chamber steam into the atmosphere. Use it when connected consumers cannot keep up and `pressure()` is still climbing. `0` keeps all steam available for consumers. Values outside the range are clamped. Call this only from the Thermal Cap's own script. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 steam_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `ThermalVent`

```python
class ThermalVent(Site):
 """any Site-returning API where `kind() == \"thermal\"` (e.g. `thermal_cap.vent()`, sonar / journal queries)"""
 def survey_level(self) -> Literal["basic", "wide", "deep"] | None:
 """Highest survey tier achieved on this vent: `\"basic\"` / `\"wide\"` / `\"deep\"`, or `None` if not yet surveyed. Reads live: a deeper re-survey upgrades held Site objects too. Higher tiers unlock more fields below. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def cycle_active_minutes(self) -> _float | None:
 """Duration of the active phase in minutes. Requires **deep** survey: returns `None` otherwise."""
 ...
 def cycle_dormant_minutes(self) -> _float | None:
 """Duration of the dormant phase in minutes. Requires **deep** survey: returns `None` otherwise."""
 ...
 def current_phase(self) -> Literal["active", "dormant"] | None:
 """The vent's phase right now: `\"active\"` or `\"dormant\"`. Reads live: poll it from a held Site object and it follows the cycle. Returns `None` before the vent is surveyed. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def next_phase_in(self) -> _float | None:
 """Game-minutes until the next phase flip. Reads live: poll it in a control loop to act before dormancy hits. Requires **deep** survey: returns `None` otherwise. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def base_steam_rate(self) -> _float | None:
 """Peak steam rate during active phase (t/h). Requires **wide** survey: returns `None` at basic."""
 ...
 def current_steam_rate(self) -> _float | None:
 """Steam rate right now (t/h: **0** during dormant phase). Reads live. Requires **wide** survey: returns `None` at basic. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def has_cap(self) -> _bool:
 """Boolean: `True` if a Thermal Cap is currently deployed on this vent. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
 def cap_id(self) -> _str:
 """Machine id of the currently deployed Thermal Cap, or empty string when no cap is present. Reads live. A pre-survey sonar result stays unrevealed; obtain a new object after surveying."""
 ...
```

## `Transmitter`

```python
class Transmitter(Component):
 """Transmitter: Sends data to other planets. Use it to report sensor readings to Earth or submit contract answers. Call `connect()` to choose a planet, then `transmit(key, value)` to send data; `disconnect()` clears the connection. A connection lasts only for the current script run, so each transmitting script must connect first. Save `get_component(\"transmitter\")` to a variable and reuse it for both calls."""
 name: _str
 def list_planets(self) -> _list[Planet]:
 """Every available transmission destination as a list of `Planet` objects (each with `.id`, `.name`, etc.). Call once at script start to see what is available; pass a returned `.id` to `connect(id)`."""
 ...
 def connect(self, planet: _str) -> ActionResult[Literal["ok", "not_found"]]:
 """Open a channel to the planet with the given id: `result = transmitter.connect(\"earth\")`. The id must be lowercase (from `list_planets()`). Read `transmitter.get_info().target` after success. Connection lasts only for the current script run, if your script restarts, `connect()` again before `transmit()`. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def disconnect(self) -> ActionResult[Literal["ok"]]:
 """Close the current script-run channel. This does not affect contracts or any other script; it only clears this Transmitter object's active target so later `transmit()` calls must `connect()` again. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 def get_info(self) -> TransmitterInfo:
 """Current connection status. Returns an object with `.connected` (boolean) and `.target` (connected planet id, or `\"none\"`). Use as a guard before `transmit()`: `if transmitter.get_info().connected: transmitter.transmit(...)`."""
 ...
 def transmit(self, key: _str, value: Any) -> ActionResult[Literal["correct", "incorrect", "already_completed_correct", "already_completed_incorrect", "accepted", "rejected", "not_connected", "wrong_planet", "wrong_contract", "locked", "unknown_contract", "key_is_planet", "unknown_key"]]:
 """Send a named value to the connected planet with `transmitter.transmit(key, value)`. Opening sensor telemetry is unavailable until the power and sensor onboarding steps are complete and the uplink step is active. For sensor readings, use the name requested by Earth, such as `\"current_temperature\"`. For contract answers, use `self.contract.id`. The data arrives in the same tick. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
```

## `TransmitterInfo`

```python
class TransmitterInfo:
 """transmitter.get_info()"""
 connected: _bool
 target: Literal["none"]
```

## `WaterPump`

```python
class WaterPump(Component):
 """Water Pump: Extracts water from a surveyed well at a throttle your script sets. Its Planet Map blueprint can be placed in Plan Mode or by script; a Pioneer must still build it on the well."""
 name: _str
 def well(self) -> WaterWell:
 """The `WaterWell` this pump is bolted to. Read `.yield_tier()` to see whether the well is `\"standard\"` / `\"rich\"` / `\"pure\"` (1×/2×/3× multiplier) and `.flow_rate()` for the well's per-hour output. Useful for prioritization scripts that compare yields across the fleet."""
 ...
 def pump_rate(self) -> _float:
 """Total water delivered to connected destinations this tick, in t/h. Reads **0** when throttle is **0** or no destination can accept flow. If a productive well still reports 0, check the connections, completed pipe routes, conflicts, power, and destination capacity."""
 ...
 def is_stalled(self) -> _bool:
 """`True` if, on the last flow tick, the powered pump had an open throttle and water available from its well but could transfer none across its connected routes. No available water, a closed throttle, or lack of power does not report a stall. Declare a destination with `self.water_out.connect(...)`, or let consumers connect their own `water_in` ports to this Pump."""
 ...
 def throttle(self) -> _float:
 """Current throttle setting (**0-1**). **0** by default, the pump idles until a script calls `set_throttle()`."""
 ...
 def set_throttle(self, rate: _float) -> ActionResult[Literal["ok"]]:
 """Set the pump's total output rate (**0-1**) across reachable connected destinations. **0** idles the pump (no extraction, no draw); **1** allows full well output subject to headroom and throughput. This script-owned setpoint resets to **0** when the script stops, ends, or errors, so keep the control loop running while the Pump should operate. Fixed result contract: `ActionResult`; branch on `.status` and read `.message`."""
 ...
 output: PickupOutputSlot
 water_out: FluidPort
 def peek_command(self) -> ScriptCommand | None:
 """Read the next queued command without consuming it. Use this when you want to inspect a command before deciding whether to handle it."""
 ...
 def next_command(self) -> CommandResult[Literal["ok", "empty"]]:
 """Consume the oldest queued command from this script's mailbox. Fixed result contract: `CommandResult`; branch on `.status` and read `.message`. Payload fields: `.command`."""
 ...
 def command_count(self) -> _int:
 """Return how many commands are waiting in this script's mailbox."""
 ...
 def clear_commands(self) -> CountResult[Literal["ok", "no_op"]]:
 """Remove every queued command for this script. Fixed result contract: `CountResult`; branch on `.status` and read `.message`. Payload fields: `.count`."""
 ...
```

## `WaterWell`

```python
class WaterWell(Site):
 """any Site-returning API where `kind() == \"water\"` (e.g. `water_pump.well()`, sonar / journal queries)"""
 def yield_tier(self) -> Literal["standard", "rich", "pure"] | None:
 """One of `\"standard\"` (**1×**) / `\"rich\"` (**2×**) / `\"pure\"` (**3×**). `None` until surveyed. Checks current survey progress, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying. Wells reveal fully on basic survey."""
 ...
 def flow_rate(self) -> _float | None:
 """Tons of water per hour this well produces. **10 / 20 / 30** for standard / rich / pure. `None` until surveyed. Reads live, except on a pre-survey sonar result, which keeps returning `None`; obtain a new object after surveying."""
 ...
 def has_pump(self) -> _bool:
 """Boolean: `True` if a Water Pump is currently deployed on this well. A pre-survey sonar result always returns `False`; obtain a new object after surveying for live readings."""
 ...
 def pump_id(self) -> _str:
 """Current machine id of the Water Pump deployed on this well, or empty string when no pump is present. A pre-survey sonar result always returns empty string; obtain a new object after surveying for live readings."""
 ...
```

## `Zone`

```python
class Zone:
 """WeatherReport.coverage() and WeatherEventForecast.corridor()"""
 def intersect(self, other: Any) -> Zone:
 """Keep only the geometry shared by both zones."""
 ...
 def union(self, other: Any) -> Zone:
 """Keep everything covered by either zone."""
 ...
 def subtract(self, other: Any) -> Zone:
 """Remove the other zone's geometry from this zone."""
 ...
 def diff(self, other: Any) -> Zone:
 """Keep geometry present in only one of the two zones."""
 ...
 def center(self) -> _tuple[_float, _float] | None:
 """Centroid as `[x, y]` in m, or `None` for an empty zone. This describes visible storm geometry, not its hidden aftermath."""
 ...
 def area(self) -> _float:
 """Covered area in m²."""
 ...
 def contains(self, x: _float, y: _float) -> _bool:
 """`True` when the point is inside the zone."""
 ...
 def is_empty(self) -> _bool:
 """`True` when the zone covers nothing."""
 ...
```
