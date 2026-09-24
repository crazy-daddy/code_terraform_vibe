# Guide: command_results

## Command Results

### The basic pattern

Every command that changes the world returns a fixed result object. You may ignore the result when your script does not need to react:

```
self.set_power(5)
```

Store it when the outcome matters:

```
result = self.extract()
if result.status == "ok":
  print("sample ready")
else:
  print(result.message)
```

Every result has:

- `.status`, a stable machine-readable code used for program logic
- `.message`, a localized player-readable explanation used for display and debugging

Never branch on `.message`; its wording can change or be translated. A command with no payload returns `ActionResult`. A payload-bearing command returns a specialized result with the same two fields plus named payload fields. `AnalyzeResult` adds `.info`, `SonarScanResult` adds `.sites`, and `TransferResult` adds `.requested` and `.moved`.

### Results are not booleans

A result object is a structured value, not a success boolean. The object itself remains truthy even when its status describes a rejection. Do not write:

```
if self.analyze():
  print("success")
```

Store the result and compare its documented status instead. `"ok"` is common, but it is not the universal spelling of success. Depending on the command, successful or accepted outcomes can include `"started"`, `"queued"`, `"charging"`, `"complete"`, or another domain-specific code. The command's DOCS outcome table is authoritative.

### Payload fields

Read a payload only after a status that documents it:

```
analysis = self.analyze()
if analysis.status == "ok":
  recipe = analysis.info.required_recipe
else:
  print(analysis.message)
```

Rejected results keep the same result type. They do not turn into `False`, `None`, an empty dict, or a bare status string.

### Queries return natural values

Read-only queries do not perform gameplay commands, so they return their natural value directly. `self.is_running()` returns a boolean, `self.cargo.count()` returns a number, and `self.sonar.tier()` returns a string. An optional query can return `None` only for the one absence meaning stated in its DOCS entry.

### Waiting and background work

Some commands yield: the script pauses while that attempted operation finishes, then receives its result. `self.analyze()` is one example. Other commands start or queue persistent work and return immediately. A charging station's `charge(...)` result can report `"charging"` or `"queued"` while the station continues working in the background.

Do not assume that every timed system waits in the same way. The command description states whether it yields, starts work, or queues work.

### Busy and exceptions

`"busy"` is an ordinary transient outcome for commands that define it. Store that result, allow game time or the blocking state to change, then call the command again when your script wants a fresh result. Do not retry every non-success status as though all outcomes meant busy.

Wrong argument types and documented malformed values can raise precise exceptions such as `TypeError` or `ValueError`. Ordinary mutable world conditions use the result statuses listed for that command. Open the command's DOCS entry for its exact statuses, payload fields, timing, and exceptions. See **Long-Running Scripts** for using these results in automation that remains safe after a game load.

*Guide / Start Here*
