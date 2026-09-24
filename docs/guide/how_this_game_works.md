# Guide: how_this_game_works

## How This Game Works

Code: Terraform is a systems game where progress comes from understanding machines, then writing small scripts that make those machines useful.

### The basic loop

1. Pick one machine or problem.
2. Read that machine's **Info** tab.
3. Check DOCS for the methods and return values it exposes.
4. Write a small script that does one clear thing.
5. Run it, inspect returned results, watch the console, then improve it.

The game is not asking you to memorize everything. It is asking you to learn where information lives. Info tabs explain intent. DOCS explain APIs. A command result explains the exact programmatic outcome. The console shows output your script chooses to print, uncaught errors, and dedicated test transcripts, while the dashboard shows whether the world changed.

### Commands and game time

Gameplay commands consistently return a result object: branch on `result.status`, read `result.message`, and then use any command-specific payload fields. Commands do not print their ordinary outcomes automatically. Some commands pause the script while their attempted work finishes; others start or queue background work and return its current state immediately. The planet keeps running in either case. See **Command Results** for the complete model.

### Good habits

Start with one machine. Store every important command result. Check `.status`; print `.message` while learning. Once a tiny script behaves, make it loop. Once one loop behaves, connect it to another system.

*Guide / Tutorials*
