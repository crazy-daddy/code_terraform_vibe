# Guide: errors_and_console

## Reading Errors and Console Output

The console is part of the interface. It shows output your script explicitly prints, uncaught exceptions, and dedicated transcripts such as sensor calibration tests.

### Opening it

Click **Console** in the bottom window bar to open or focus it. In dock mode, the console sits in the lower-right pane beside the editor. Use the console filter to switch between THIS SCRIPT, ALL output, WARNINGS, and ERRORS.

### Results are the program interface

Gameplay commands return fixed result objects without printing ordinary success or rejection messages automatically. `result.status` is the stable code to branch on, and `result.message` explains the exact outcome. Payload-bearing results add named fields such as `.moved`, `.sites`, or `.info`.

```
result = self.extract()
if result.status != "ok":
  print(result.message)
```

Your script decides which command outcomes belong in the console. Never compare `.message` in program logic because it is localized display text. Malformed calls raise typed exceptions such as `TypeError` or `ValueError`; ordinary game states such as `"busy"` or `"no_cargo_space"` remain result statuses so the script can decide what to do.

### Busy is not failure

A `"busy"` status means the machine is finishing another timed action, not that something broke. For the retry pattern, see **Command Results**.

### Debugging rhythm

Store the result of an important command, inspect `.status` and `.message`, then read any payload fields only for statuses that provide them. Use **Trace** when you want to see where the script is parked, and **Debug** when you need to inspect variables directly.

*Guide / Tutorials*

---
