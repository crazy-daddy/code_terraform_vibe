# Guide: signal_bus_guide

## Signal Bus

Coordinates scripts through shared JSON-safe values. Access the Signal Bus with `get_component("comms")` after its research unlocks. Use `send()` and `receive()` for work that should be handled once; use `broadcast()` and `latest()` for the newest shared value.

**Returned by:** `get_component("comms")`

**Every component has a stable `.id`. For a deployed machine, open the ⓘ on its card to find the exact ID, then pass that value to `get_component(id)`. IDs are case-sensitive.**

### Properties

##### `.id`

Stable programmatic identifier for this component. Use it with `get_component(id)` and APIs that ask for component, planet, vehicle, station, or order ids.

- **Returns** String

##### `.name`

Human-readable display name. Prefer `.id` for scripts that need to survive renames.

- **Returns** String

### Methods

##### `.send(channel, value)`

Add a JSON-safe value to a named channel queue. Keep the send receipt to identify or cancel that exact request later, even when several requests contain identical values. Channel ids may contain letters, numbers, `_`, `.`, `:`, and `-`. Use queues for work items that should be handled once.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `value` | `any` | JSON-safe value, up to 8 nested levels, 1,024 total values, and 4,096 characters per string |

- **Returns** `SendResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.message_id`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | One message was appended to the channel's queue, and its id is available in `message_id`. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. No message was queued. |
| `"channel_limit"` | rejection | The channel does not exist and the Signal Bus has no capacity for another channel. No message was queued. |
| `"queue_full"` | rejection | The channel's queue has reached its message limit. No message was queued. |
| `"id_exhausted"` | rejection | No additional stable message ids are available. No message was queued. |
| `"invalid_value"` | rejection | The supplied value violates the Signal Bus value rules. No message was queued. |

##### `.receive(channel, message_id=None)`

Take one queued message. Omit `message_id` or pass `None` to take the oldest, or supply a message id to take exactly that job. Selection and removal happen together, so only one competing receiver can take it. Other queued messages keep their order, and broadcasts are preserved. Use `pending()` to choose work by priority, location, or capability before receiving it.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `message_id` | `number` | Positive whole-number message id from `pending()` or a successful `send()` receipt. Omit or pass `None` to receive the oldest message. An id selects that exact message, never its position in the queue. |

- **Returns** `ReceiveResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.packet`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | One message was removed from the queue and returned. Without a message id it was the oldest; with an id it was exactly the requested message. |
| `"empty"` | success | No message id was requested and the channel has no queued messages. Nothing was consumed. |
| `"not_found"` | rejection | The supplied message id is not waiting on this channel. No other message was consumed. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `message_id` must be a finite whole number within the supported integer range. |
| `ValueError` | `message_id` must be greater than zero. |
| `OverflowError` | `message_id` must fit within the supported integer range. |

##### `.wait(channel)`

Wait for and take the oldest queued message. If the queue is empty, only this script pauses until work is available; the game and other scripts keep running. Messages already queued are taken immediately. Broadcasts do not satisfy the wait. Pausing preserves the wait, and stopping the script abandons it without consuming a message.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`. A valid missing channel waits for its first queued message. |

- **Returns** `ReceiveResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.packet`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | One message was removed from the queue and returned. Without a message id it was the oldest; with an id it was exactly the requested message. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |

##### `.wait_any(channels)`

Wait for and take one queued message from any listed channel. Channels listed first have priority whenever work is selected; each channel keeps its oldest-first order. If every queue is empty, only this script waits. Broadcasts do not satisfy the wait. The channel list is copied when called, and repeated names are considered once at their first position. Pausing preserves the wait; stopping abandons it without taking work.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channels` | `list` | List of 1-128 channel-id strings, in priority order. Each id has 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`. Missing channels may receive work later. Repeated names keep their first position. |

- **Returns** `WaitAnyResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.channel`, `.packet`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | One queued message was consumed from the first listed channel with waiting work. The result includes that channel and its copied message. |
| `"invalid_channel"` | rejection | At least one listed channel id is invalid. No message was consumed; channel and packet are None. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | channels must be a list containing only channel-id strings. |
| `ValueError` | channels must contain 1-128 entries. |

##### `.wait_broadcast(channel)`

Wait for the next broadcast on a channel. Every script already waiting captures that publication, including a repeated value or None. Existing broadcasts do not satisfy a new wait. Only this script pauses; queued messages remain untouched. The first publication is retained even if another broadcast follows or the channel is cleared. Pausing retains that signal for resume; stopping abandons the wait.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`. A valid missing channel can be watched without creating it. Only successful broadcasts on this channel satisfy the wait. |

- **Returns** `WaitBroadcastResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.broadcast`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The first successful broadcast published after this call was captured without consuming shared state. Every script already waiting receives its own copy. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |

##### `.pending(channel)`

Inspect all waiting messages on a channel in receive order without consuming them. Use the snapshot to display pending work in a Control Room card or total outstanding requests. Each message and its nested value are copied; editing the returned list or messages does not change the Signal Bus. Broadcasts and messages already received are excluded. Read again to refresh the snapshot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** List of copied CommsMessage entries in receive order, oldest first. Empty when no messages are waiting, including a missing channel or one with only a broadcast.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The channel id must be 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.cancel(channel, message_id)`

Cancel one waiting message using its send receipt's `.message_id` or its `.id` from `pending(channel)`. Use it to remove an obsolete request or add a Cancel button to a Control Room job board. Other messages keep their ids, values, and receive order, including messages sent after the snapshot. The latest broadcast is preserved. Cancellation only removes queued work; it cannot stop a worker that has already received the message.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `message_id` | `number` | Positive whole-number message id from a successful `send()` receipt or `pending(channel)`, not a position in the queue. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The specified message was removed from this channel's queue. Other messages and the latest broadcast were preserved. |
| `"not_found"` | rejection | No queued message on this channel has the supplied id. Nothing was removed. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `message_id` must be a finite whole number within the supported integer range. |
| `ValueError` | `message_id` must be greater than zero. |
| `OverflowError` | `message_id` must fit within the supported integer range. |

##### `.update(channel, message_id, value)`

Replace the complete value of one waiting message. Use its send receipt or an id from `pending()` to edit a delivery, priority, or destination from a script or Control Room card. The id, queue position, original sender, and send time stay unchanged. Replacement happens in one operation and works even when the queue is full. Messages already received cannot be edited. Read `pending()` again to refresh an earlier snapshot.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `message_id` | `number` | Positive whole-number id of a waiting message, from a successful `send()` receipt or `pending(channel)`. This identifies a message, not its position in the queue. |
| `value` | `any` | Complete replacement JSON-safe value, up to 8 nested levels, 1,024 total values, and 4,096 characters per string or dictionary key. Dictionary fields are replaced, not merged. |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The queued message now contains the replacement value. Its id, queue position, original sender, and send time were preserved. |
| `"not_found"` | rejection | No queued message on this channel has the supplied id. No value was changed. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |
| `"invalid_value"` | rejection | The replacement violates the Signal Bus value rules. The queued message was not changed. |

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `message_id` must be a finite whole number within the supported integer range. |
| `ValueError` | `message_id` must be greater than zero. |
| `OverflowError` | `message_id` must fit within the supported integer range. |

##### `.broadcast(channel, value)`

Store a channel's latest JSON-safe value without consuming queue slots. Use broadcasts for shared telemetry like fleet mode, target sector, or current priority.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |
| `value` | `any` | JSON-safe value, up to 8 nested levels, 1,024 total values, and 4,096 characters per string |

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The operation completed successfully. |
| `"invalid_channel"` | rejection | The supplied channel identifier is invalid. |
| `"channel_limit"` | rejection | The maximum number of communication channels has been reached. |
| `"invalid_value"` | rejection | The supplied value is invalid. |

##### `.latest(channel)`

Return the most recent value broadcast on a channel, or `None` if the channel has no latest value. Reading latest does not consume it.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** Latest broadcast value on the channel, or `None` if nothing has been broadcast.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The channel id must be 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.latest_info(channel)`

Inspect the latest broadcast, who published it, and how long ago it was updated. Use the snapshot to detect outdated worker reports or show freshness in a Control Room card. Reading does not consume messages or change the channel. Read again to refresh the value and age.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** A BroadcastInfo snapshot with value, sender, and age_seconds, or `None` when the channel has no broadcast. Missing saved sender or timestamp information is `None` in the corresponding field.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The channel id must be 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.queue_size(channel)`

Number of queued messages waiting on the channel.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** Number of queued messages on the channel.

*Raises*

| Exception | Condition |
| --- | --- |
| `ValueError` | The channel id must be 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-`, and cannot be a reserved object-field name. |

##### `.channels()`

All channel ids that currently have queued messages or a latest broadcast value.

- **Returns** List of channel ids with queued or broadcast state.

##### `.clear(channel)`

Remove a channel's queued messages and latest broadcast.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `channel` | `string` | Channel id, 1-64 characters using letters, numbers, `_`, `.`, `:`, or `-` |

- **Returns** `CountResult`
- **Result fields** `.status`, `.message`
- **Success payload** `.count`

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"ok"` | success | The command affected `.count` entries or units. |
| `"no_op"` | success | The command affected no entries or units. |
| `"invalid_channel"` | rejection | The supplied channel id is outside the Signal Bus naming rules. |

*Components / Logistics & Orders*

---
