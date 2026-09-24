# Data Types: Orders And Comms

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`BroadcastInfo`](#broadcastinfo) (ORDERS & COMMS)
- [`CommsMessage`](#commsmessage) (ORDERS & COMMS)
- [`DockSlot`](#dockslot) (ORDERS & COMMS)
- [`Order`](#order) (ORDERS & COMMS)
- [`ReceiveResult`](#receiveresult) (ORDERS & COMMS)
- [`SendResult`](#sendresult) (ORDERS & COMMS)
- [`TransmitterInfo`](#transmitterinfo) (ORDERS & COMMS)
- [`WaitAnyResult`](#waitanyresult) (ORDERS & COMMS)
- [`WaitBroadcastResult`](#waitbroadcastresult) (ORDERS & COMMS)

---

## BroadcastInfo

**Returned by:** comms.latest_info(channel); comms.wait_broadcast(channel).broadcast after status == "ok"

### Properties

##### `.value: JsonValue`

A copy of this broadcast's value, including `None` if that was the value published. From `latest_info()` it is the latest value; from `wait_broadcast()` it is the first publication captured by that wait.

- **Returns** `JsonValue`

##### `.sender: str | None`

Who published this broadcast, or `None` if the saved broadcast has no sender information.

- **Returns** `str | None`

##### `.age_seconds: float | None`

Simulation seconds since this broadcast, sampled when `latest_info()` is read or `wait_broadcast()` resumes. Uses the same time base as `sleep()` and `clock.elapsed_seconds()`; pausing the simulation freezes the age. `None` means the timestamp is missing or invalid. The returned age is a snapshot.

- **Returns** `float | None`

*Types / Orders & Comms*

## CommsMessage

**Returned by:** comms.pending(channel) list entries; comms.receive(channel).packet, comms.wait(channel).packet, or comms.wait_any(channels).packet after status == "ok"

### Properties

##### `.id: int`

Monotonic message id assigned by the Signal Bus.

- **Returns** `int`

##### `.sender: str`

Script owner id that sent the message.

- **Returns** `str`

##### `.tick: int`

Game tick when the message was sent.

- **Returns** `int`

##### `.value: JsonValue`

JSON-safe message value: `None`, boolean, number, string, list, or dict with string keys.

- **Returns** `JsonValue`

*Types / Orders & Comms*

## DockSlot

**Returned by:** supply_dock.slots()

### Properties

##### `.index: int`

Zero-based slot index (**0-4**): stable across calls.

- **Returns** `int`

##### `.item_id: str | None`

Item id currently occupying this slot, or `None` if the slot is empty.

- **Returns** `str | None`

##### `.count: int`

Units currently stored in this slot.

- **Returns** `int`

*Types / Orders & Comms*

## Order

**Returned by:** orders.list_orders() / orders.list_upcoming_orders() / orders.list_weekly_orders() / orders.get_order() / orders.completed_orders() (Earth Orders)

### Properties

##### `.id: str`

Immutable Earth Order id. Useful for logs and dashboards; Supply Dock scripts use it to identify the order currently assigned to their dock.

- **Returns** `str`

##### `.name: str`

Pre-translated display name of the Earth Order.

- **Returns** `str`

##### `.requires: dict[str, int]`

A dict `{item_id: count}` of what Earth is demanding. Use `.keys()`, `.values()`, `.items()`, or index directly: `order.requires["iron_ore"]`.

- **Returns** `dict[str, int]`

##### `.shipped: dict[str, int]`

A dict `{item_id: count}` of how many units of each item have already landed. Empty for upcoming orders. Use `.get(item_id, 0)` to read safely.

- **Returns** `dict[str, int]`

##### `.reward_credits: int`

Credit payout. Upcoming and active campaign orders quote the payout at your current contractor reputation; the final payout may change as reputation grows. Completed campaign orders report the recorded payout. Weekly rewards are fixed.

- **Returns** `int`

##### `.reward_kind: str | None`

Variable-reward kind: `"recipe"` / `"tech"`, or `None` for credits-only.

- **Returns** `str | None`
- **Possible values** `"recipe"`, `"tech"`

##### `.reward_label: str | None`

Pre-translated description of the variable reward, or `None` for credits-only Earth Orders.

- **Returns** `str | None`

##### `.status: str`

`"upcoming"` for a future campaign order available for planning, `"active"` for a current order available for fulfillment, or `"completed"` once delivered. Weekly Earth Orders are never `"upcoming"`.

- **Returns** `str`
- **Possible values** `"upcoming"`, `"active"`, `"completed"`

##### `.kind: str`

Order source: `"campaign"` or `"weekly"`.

- **Returns** `str`
- **Possible values** `"campaign"`, `"weekly"`

##### `.expires_day: int | None`

Day when a Weekly Earth Order expires, or `None` for contractor campaign orders.

- **Returns** `int | None`

##### `.contractor_id: str | None`

Id of the issuing contractor, or `None` for Weekly Earth Orders. Stable across saves and useful for branching on specific campaign partners.

- **Returns** `str | None`
- **Possible values** `"helios_orbital"`, `"spire_research"`, `"vestibule_logistics"`

##### `.contractor_name: str | None`

Pre-translated issuing contractor name, or `None` for Weekly Earth Orders.

- **Returns** `str | None`

*Types / Orders & Comms*

## ReceiveResult

**Returned by:** comms.receive(); comms.wait()

### Properties

##### `.status: str`

`"ok"` when a queued message was consumed; `"empty"` when no id was requested and the queue was empty; `"not_found"` when the requested id was absent; or `"invalid_channel"` for an invalid channel id.

- **Returns** `str`
- **Possible values** `"ok"`, `"empty"`, `"not_found"`, `"invalid_channel"`

##### `.message: str`

Player-readable explanation of the receive outcome.

- **Returns** `str`

##### `.packet: CommsMessage | None`

The consumed `CommsMessage` when `status == "ok"`, otherwise `None`. When a message id was requested, this packet has that exact id.

- **Returns** `CommsMessage | None`

*Types / Orders & Comms*

## SendResult

**Returned by:** comms.send()

### Properties

##### `.status: str`

Send outcome. `"ok"` means a message was queued; every other outcome means no message was sent.

- **Returns** `str`
- **Possible values** `"ok"`, `"invalid_channel"`, `"channel_limit"`, `"queue_full"`, `"id_exhausted"`, `"invalid_value"`

##### `.message: str`

Player-readable explanation of the send outcome.

- **Returns** `str`

##### `.message_id: int | None`

The queued message's positive integer id when `status == "ok"`, or `None` when no message was sent. Matches `.id` in `pending()` and `receive().packet`. Use it with `receive()`, `cancel()`, or `update()` to target that exact request.

- **Returns** `int | None`

*Types / Orders & Comms*

## TransmitterInfo

**Returned by:** transmitter.get_info()

### Properties

##### `.connected: bool`

True if connected to a target.

- **Returns** `bool`

##### `.target: str`

Connected planet id, or `"none"` when disconnected.

- **Returns** `str`
- **Possible values** `"none"`

*Types / Orders & Comms*

## WaitAnyResult

**Returned by:** comms.wait_any()

### Properties

##### `.status: str`

`"ok"` when one queued message was consumed, or `"invalid_channel"` when any listed channel id is invalid. Valid empty queues keep waiting.

- **Returns** `str`
- **Possible values** `"ok"`, `"invalid_channel"`

##### `.message: str`

Player-readable explanation of the wait outcome.

- **Returns** `str`

##### `.channel: str | None`

The channel the consumed message came from when `status == "ok"`; otherwise `None`.

- **Returns** `str | None`

##### `.packet: CommsMessage | None`

The consumed `CommsMessage` when `status == "ok"`; otherwise `None`. Its id, sender, tick, and copied value belong to the selected channel.

- **Returns** `CommsMessage | None`

*Types / Orders & Comms*

## WaitBroadcastResult

**Returned by:** comms.wait_broadcast()

### Properties

##### `.status: str`

`"ok"` when a new broadcast was captured, or `"invalid_channel"` for an invalid channel id. A valid channel keeps waiting until a new broadcast arrives.

- **Returns** `str`
- **Possible values** `"ok"`, `"invalid_channel"`

##### `.message: str`

Player-readable explanation of the broadcast wait outcome.

- **Returns** `str`

##### `.broadcast: BroadcastInfo | None`

The captured `BroadcastInfo` when `status == "ok"`; otherwise `None`. It contains the publication's copied value, sender, and age when the script resumes.

- **Returns** `BroadcastInfo | None`

*Types / Panels*
