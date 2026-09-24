# Guide: weather_system

## Weather System

Weather is a timed resource system operated through Weather Stations and drones. Active storms are visible on Weather and the Planet Map, but an aftermath coordinate must be recovered from live transmissions.

### Storm lifecycle

Dust storms and thunderstorms move across the planet and may overlap. Heat and Pressure increase intensity, reward yield, and lightning energy; they do not make storms occur more often.

A storm's transmissions become audible when it starts and remain available until **4 world-clock hours after it ends**. Its aftermath appears only when the storm ends:

- A dust storm leaves **14-28 Raw Uranium** for **48 world-clock hours**.
- An eligible thunderstorm leaves **2-4 Storm Glass** for **96 world-clock hours**. A thunderstorm without an aftermath transmits no Storm Glass message.

The reward remains hidden until a drone reaches its exact coordinate. A nearby or expired location returns `nothing_here` and gives no directional hint.

### Build reception coverage

Weather Program installs one completed Weather Station at Nocturna Base. Each powered station draws **50 W**, monitors a **300 m** local radius, and receives broadcast traffic plus the dust channel for its own biome. Additional stations are deployed at outposts.

Dust movement records are divided among all five biome channels, so a complete dust message requires powered reception in every biome. Thunder movement records are broadcast, so one powered station can hear a complete Storm Glass message.

### Recover the coordinate

`signal_receiver.transmissions()` returns only records audible to that station now. It stores no history, several events may be present at once, and corrupted copies may declare the same packet number as a valid record. Player code must retain what it needs before reception closes.

Records with the same `event_id` belong to one event. Each record declares its `number`, expected `total`, encoded `data`, and `checksum`. The data format is `event_id|number|total|dx|dy`. A valid checksum equals the full sum of the ASCII code of every character in `data`, with no modulo reduction.

A complete valid numbered set describes movement from `(0, 0)`. Apply its `dx` and `dy` records in number order; the endpoint is the exact aftermath coordinate. DOCS entries for **SignalTransmission** define every field. Player code decides how to retain records, share them between stations, and track incomplete events.

### Collect the aftermath

After the storm ends, send a drone with cargo space to the recovered coordinate and call `collect()`. One successful collection transfers at most **5 units**, so a larger aftermath may need repeated collections or more than one trip. Raw Uranium adds exposure unless the drone has Shield Plating; Storm Glass is not radioactive. A discovered live aftermath then appears on the maps until it is exhausted or expires.

### What each surface does

- **Incoming** automatically summarizes storms expected to enter powered-station coverage. It does not require `observe()` and never reveals an aftermath.
- `observe()` measures local active storms and forecasts. `last_report()` reads that station's latest report.
- `signal_receiver` supplies the raw records used for aftermath recovery.
- `signal_board` is an optional per-station display. It presents only records and labelled values published by player code; it does not validate, merge, store, or decode them.
- `strikes()` provides bounded local lightning history. Lightning Rod capture works independently of Weather Station scripts.

The required process is reception, retention, validation, assembly, coordinate recovery, and collection. The storage, coordination, presentation, and dispatch program remain yours to design.

*Guide / World & Infrastructure*
