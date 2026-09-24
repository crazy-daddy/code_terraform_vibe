# Guide: signal_bus_guide

## Signal Bus

### Overview

Signal Bus is explicit shared state for scripts and the commander. Libraries share code; Signal Bus shares live values on named channels. For steering only one running script by hand, use its command mailbox (`self.next_command()`) instead.

Signal Bus unlocks with **Signal Bus** research. Before that, `get_component("comms")` returns `None`.

### Manual operator

Open **Ship Computer > Signal Bus** to send traffic without writing a scratch script. Choose **Queue** when one receiver should consume the message, or **Broadcast** when many readers should see the current value. Plain input is sent as text; valid JSON sends structured objects, arrays, strings, numbers, booleans, or `null`. Manual traffic shows your commander name as its sender.

Use **Inspect** on a channel to review its queued messages. Delete one message or clear the currently shown queue. Clearing targets the exact message ids you inspected, so a script message that arrives afterward is preserved. Queue deletion does not remove the channel's broadcast value.

### Queued messages

Use `send(channel, value)` and `receive(channel)` when each message should be handled once.

```
comms = get_component("comms")
sent = comms.send("jobs.mine", {
  "sector": "E14",
  "resource": "iron_ore",
  "priority": 2,
})
if sent.status != "ok":
  print(sent.message)
```

`send()` returns a `SendResult` with `.status`, `.message`, and `.message_id`. On `"ok"`, `.message_id` is the positive integer id of the message just queued. It is `None` for `"invalid_channel"`, `"invalid_value"`, `"queue_full"`, `"channel_limit"`, and `"id_exhausted"`, because those outcomes send nothing.

```
received = comms.receive("jobs.mine")
if received.status == "ok":
  msg = received.packet
  job = msg.value
  print("job from", msg.sender, job["sector"])
else:
  print(received.message)
```

`receive()` returns a `ReceiveResult`. `.packet` is a consumed `CommsMessage` only when `.status == "ok"`; it is `None` for `"empty"`, `"not_found"`, and `"invalid_channel"`. Omitting the id or passing `None` takes the oldest message. Supplying an id takes only that message. In short: `receive()` consumes; `latest()` does not.

### Wait for work

Use `wait(channel)` for a worker that should stay idle until it receives a request. It takes the oldest queued message immediately if one is available. Otherwise, only this script waits; the game and other scripts keep running. It does not need `async`, `await`, or a checking loop.

```
comms = get_component("comms")
while True:
    received = comms.wait("jobs.mine")
    if received.status != "ok":
        print(received.message)
        break
    job = received.packet
    print("Received", job.id, job.value)
    # Perform the requested work here before waiting again.
```

`wait()` returns a `ReceiveResult` with `.status`, `.message`, and `.packet`. A valid call waits for `"ok"` with a consumed `CommsMessage`. A malformed channel returns `"invalid_channel"` immediately with `.packet` set to `None`. Missing, empty, and broadcast-only channels keep the script waiting. There is no timeout. Broadcasts do not wake a worker with a job.

Messages stay queued until an active worker takes them. Each message can be taken by only one receiver. If another receiver or a Cancel button gets there first, the waiting worker stays waiting for the next message. Workers follow the normal script execution order; waiting does not reserve a message or grant priority over `receive()`.

Pausing the script preserves its wait without taking work. Stopping or restarting it abandons that wait without removing queued messages. Save/load preserves queued messages and follows normal script startup; it does not save the suspended call or local variables. Once a message has been received, the worker owns completing the job and reporting its outcome.

Use `receive()` when the same script must keep checking sensors, commands, or Control Room buttons while no job is available. A card using `wait()` pauses its own drawing and input handling too.

### Keep a send receipt

Keep the successful send's `.message_id` when your script may need to identify or cancel its own request later. This is the same id shown by `pending()` and `receive().packet`, and identical payloads still receive different ids.

```
sent = comms.send("jobs.water", {"outpost": "A"})
if sent.status == "ok":
    request_id = sent.message_id
    print("My delivery request", request_id)
else:
    print(sent.message)
```

After a successful send, when that request is no longer needed, pass the saved `request_id` to `comms.cancel("jobs.water", request_id)`. A receipt records which message was sent; it does not promise that the message is still waiting or that the work has been completed. Match the id against a fresh `pending()` list to check whether it is still queued. If a worker already received it, cancellation returns `"not_found"`.

### Inspect pending work

Use `pending(channel)` to inspect waiting messages without consuming them. It returns a list of `CommsMessage` entries, oldest first, with the same `.id`, `.sender`, `.tick`, and `.value` fields as a received message.

```
comms = get_component("comms")
for msg in comms.pending("jobs.mine"):
    print(msg.id, msg.sender, msg.value)
```

Use this list in a Control Room card to display the backlog while worker scripts continue receiving jobs. Reading `pending()` does not take or reserve any work. The list, each message, and nested values are copies; changing them does not change the queue.

The snapshot contains only messages waiting when you called it. It excludes broadcasts and jobs already taken by `receive()` or `wait()`, even if their workers are still busy. Read again to refresh after messages arrive or are received. An empty queue, a missing channel, or a channel with only a broadcast returns `[]`. A malformed channel id raises `ValueError`.

### Choose and take a job

Pass a message id to `receive(channel, message_id)` to take exactly the job you chose from `pending()`. Workers can choose by priority, location, or capability, and a Control Room card can offer a Run button for a specific job.

```
for candidate in comms.pending("jobs.mine"):
    if candidate.value["sector"] == "E14":
        received = comms.receive("jobs.mine", candidate.id)
        if received.status == "ok":
            job = received.packet
            print("Claimed", job.id, job.value)
            break
        elif received.status == "not_found":
            continue
        else:
            print(received.message)
            break
```

Checking for the selected id and removing its message happen in one operation. If two workers choose the same message, only one can receive it. The other gets `"not_found"` with `.packet` set to `None`, even if other jobs remain in the queue. It never takes a different job in place of the selected one. Start work only after `"ok"` and use the returned `.packet` for the job's data.

The id can also come from a successful send receipt. It must be a positive whole number within the supported integer range. A wrong channel or an id already received, canceled, or cleared produces `"not_found"`; a malformed channel produces `"invalid_channel"`. Invalid numeric ids raise the documented exceptions. Without an id, an empty queue produces `"empty"`.

Other queued messages, new arrivals, and broadcasts are preserved. Earlier `pending()` snapshots remain copies; read again to refresh. Receiving removes the job from the queue immediately. Your worker script still owns completing the work and reporting its outcome.

### Cancel pending work

Use `cancel(channel, message_id)` to remove one obsolete request. Pass the successful send's `.message_id` or the message's `.id` from `pending()`, not its position in the list. A Control Room card can give each waiting job its own Cancel button.

```
for msg in comms.pending("jobs.mine"):
    if msg.value["sector"] == "E14":
        result = comms.cancel("jobs.mine", msg.id)
        if result.status == "ok":
            print("Canceled", msg.id)
        elif result.status == "not_found":
            print("This job is no longer waiting")
        else:
            print(result.message)
```

`cancel()` returns an `ActionResult`. `"ok"` means that exact waiting message was removed. `"not_found"` means the id is not in this channel's queue, including when another script already received or canceled it. A malformed channel returns `"invalid_channel"`. The message id must be a positive whole number within the supported integer range; malformed numeric arguments raise the documented exceptions.

Other waiting messages keep their ids, payloads, and order. New arrivals and the latest broadcast are preserved. Cancellation does not stop a worker that already received the job. An earlier `pending()` snapshot stays unchanged; read again to update the panel.

### Wait on several channels

Use `wait_any(channels)` when one worker handles several kinds of requests:

```
comms = get_component("comms")
result = comms.wait_any(["urgent_deliveries", "deliveries"])
if result.status == "ok":
    print(result.channel, result.packet.value)
```

The first listed channel with queued work supplies exactly one message, oldest first within that channel. Priority is checked when the script can take work, including after waking or resuming from pause. If all listed queues are empty, only this script waits until one has work. Unrelated channels and broadcasts do not supply a message. There is no timeout, and missing channels do not need to be created in advance.

The result is a `WaitAnyResult` with `status`, `message`, `channel`, and `packet`. On `"ok"`, `channel` names the selected channel and `packet` is the consumed `CommsMessage`. If any channel id is invalid, `"invalid_channel"` returns immediately with `channel` and `packet` both `None`; no message is taken from any channel.

Pass a list containing 1-128 string entries. Other container types and non-string entries raise `TypeError`; an empty list or more than 128 entries raises `ValueError`. The whole list is validated before receiving. The list is copied when called; duplicate names are considered once at their first position.

Priority chooses the next request; it does not interrupt work already underway. A continuously busy earlier channel can keep later channels waiting. Competing receivers still take each message at most once. Pause, stop, save/load, and Control Room drawing follow the same rules as `wait(channel)`.

### Wait for a new broadcast

Use `wait_broadcast(channel)` to let several scripts react to the same new signal:

```
comms = get_component("comms")
result = comms.wait_broadcast("factory.phase")
if result.status == "ok":
    print(result.broadcast.value)
    print(result.broadcast.sender)
```

After the workers are waiting, another script or the Computer Signal Bus operator can broadcast `"start"` on `"factory.phase"`. Every script already waiting captures that publication and resumes at its next execution opportunity. It does not consume the shared broadcast or any queued messages. `send()`, queue edits, cancellation, and clearing a channel do not satisfy this wait.

A call waits for the first successful broadcast published after it starts. A value already available through `latest()` does not satisfy a new wait; use `latest_info()` when you want the current value immediately. Publishing the same value again still counts, including `None`. Failed publications and broadcasts on other channels do not wake it. There is no timeout, and waiting does not create a channel or use its queue capacity.

The fixed `WaitBroadcastResult` has `status`, `message`, and `broadcast`. On `"ok"`, `broadcast` is a `BroadcastInfo` with a copied `value`, `sender`, and `age_seconds` sampled when the script resumes. On `"invalid_channel"`, `broadcast` is `None`. Incorrect argument types or arity raise `TypeError`.

The first captured publication is retained if later broadcasts arrive before the script resumes, even in the same tick, or the channel is cleared. Each script receives an independent copy. Pausing a waiting script retains its first signal until resume; stopping or restarting discards it. Save/load preserves the bus's latest value, but not active waits or their captured signals; a restarted wait listens for a future publication. Signals published while a script is doing other work are not buffered for its next wait.

### Edit a waiting request

Use `update(channel, message_id, value)` to replace a request while it is still queued. A Control Room job board can let the player adjust an amount, destination, or priority without canceling and resending the job.

```
sent = comms.send("deliveries", {"item": "iron_ingot", "amount": 50})
if sent.status == "ok":
    updated = comms.update("deliveries", sent.message_id, {
        "item": "iron_ingot",
        "amount": 100,
    })
    print(updated.status, updated.message)
```

`update()` returns an `ActionResult` with `.status` and `.message`. `"ok"` means the complete replacement value was applied. `"not_found"` means that id is not waiting on the named channel, including after receipt, cancellation, or clearing. `"invalid_channel"` rejects a malformed channel; `"invalid_value"` rejects a replacement outside the payload rules below. Rejections leave the bus unchanged and never recreate a missing message. The id follows the same positive whole-number rules as `cancel()`.

The message keeps its id, queue position, original sender, and original send time. Other messages, new arrivals, and the latest broadcast stay unchanged. Updates require no new queue slot or message id, so a full queue can still be edited. A successful update is not a new send.

The entire value is replaced; dictionary fields are not merged. Earlier `pending()` snapshots remain unchanged. Read again to refresh your panel. If several scripts update the same waiting message, the last successful update wins.

Updating and receiving each happen in one operation. A worker receives either the complete original value or the complete replacement. If the worker receives first, an update returns `"not_found"` and cannot change the worker's copy or its work. Workers should use the packet returned by `receive()` or `wait()` for the actual job data, since an earlier snapshot may predate an edit.

### Broadcasts

Use `broadcast(channel, value)` and `latest(channel)` when many scripts should read the same current value. Broadcasts are not consumed; every reader sees the current value until a later broadcast replaces it or the channel is cleared.

```
published = comms.broadcast("fleet.mode", "return_home")
if published.status != "ok":
  print(published.message)

mode = comms.latest("fleet.mode")
if mode == "return_home":
  self.nav.set_target(0, 0)
```

`broadcast()` returns an `ActionResult`. `latest()` is a read-only query: it returns the current value directly, or `None` when there is no broadcast. `latest()` and `queue_size()` raise `ValueError` for a malformed channel id instead of disguising it as missing data.

### Check broadcast freshness

Use `latest_info(channel)` when a stored value is only useful while its publisher keeps reporting. It returns a `BroadcastInfo` snapshot with `.value`, `.sender`, and `.age_seconds`.

```
comms = get_component("comms")
info = comms.latest_info("worker.status")
if info is None:
    print("No report yet")
elif info.age_seconds is None:
    print("Report age is unknown")
elif info.age_seconds > 30:
    print("Worker report is outdated")
else:
    print(info.sender, info.value)
```

Age is measured in simulation seconds, the same time base as `sleep(seconds)` and `clock.elapsed_seconds()`. It advances as the simulation runs, freezes while paused, and does not count time spent with the save closed. Choose a threshold that matches how often your worker broadcasts.

No broadcast means `None`, including a missing channel or a channel with only queued messages. A broadcast of `None` still returns a snapshot whose `.value` is `None`. For older saved broadcasts without sender or valid timestamp information, the corresponding `.sender` or `.age_seconds` is `None`; publishing again supplies fresh information. Malformed channel ids raise `ValueError`.

The value and nested data are copies. The age is captured when you call the API, so read again to refresh your panel. Queued messages do not change the broadcast's sender or age, and reading does not consume anything. A new broadcast resets its age even when the value is unchanged. The API reports elapsed time; your script decides when a report is outdated.

### Monitoring and clearing

```
for channel in comms.channels():
  print(channel, comms.queue_size(channel))

cleared = comms.clear("jobs.mine")
print(cleared.status, cleared.count, cleared.message)
```

`clear()` returns a `CountResult`; `.count` is the number of queued/latest entries removed, and `"invalid_channel"` is distinct from a valid `"no_op"`. Unlike the Computer's queue-only deletion, script `clear()` removes both the queue and current broadcast. Use it only when your script intentionally owns that channel.

### Payload rules

Values must be JSON-safe: `None`, booleans, finite numbers, strings, lists/tuples, and dictionaries with string keys. Functions, components, sets, class instances, and dictionaries with non-string keys produce `"invalid_value"`. A payload supports up to **8** nested levels, **1,024** total values, and **4,096** characters in each string or dictionary key.

Channel ids contain **1-64** letters, numbers, `_`, `.`, `:`, or `-`. Reserved object-field names such as `"__proto__"` are rejected. A queue holds up to **64** messages and a save up to **128** channels. The Computer operator uses these same limits. Always branch on the returned `.status`; `.message` is the authoritative reason text.

*Guide / Automation Systems*
