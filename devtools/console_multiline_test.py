# In-game script: the game injects get_component()/sleep(), which devtools/ Pyright does not see.
# pyright: reportUndefinedVariable=false
# Console multi-line and limit probe: a few lines of output on channel "bench", no game side effects.
# Checks (1) how a "\n" inside one console.print renders, (2) what one multi-line print costs in simulation
# time, (3) the string and collection limits, read from the OverflowError messages, and (4) whether
# console.print accepts a string near the string limit. Every risky step is caught and reported.

import re

console = get_component("console")
clock = get_component("clock")
CH = "bench"
BRANCH = "┃   "


def timed(label, fn):
    t0 = clock.elapsed_seconds()
    fn()
    dt = clock.elapsed_seconds() - t0
    print(f"{label}: {dt:.2f}s")


def limit_from(message):
    digits = re.findall(r"[0-9][0-9,]*", message)
    return digits


def probe_string_limit():
    """Largest string this script can build, found by doubling; the error text names the limit."""
    n = 1000
    last_ok = 0
    while n <= 1000000:
        try:
            s = "x" * n
        except Exception as err:
            print(f"string of {n} chars failed: {type(err)}: {err}")
            print(f"  numbers in message: {limit_from(str(err))}")
            return last_ok
        last_ok = n
        n = n * 2
    print("no string limit hit up to 1,024,000 chars")
    return last_ok


def probe_collection_limit():
    n = 1000
    while n <= 1000000:
        try:
            lst = [0] * n
        except Exception as err:
            print(f"list of {n} items failed: {type(err)}: {err}")
            print(f"  numbers in message: {limit_from(str(err))}")
            return
        n = n * 2
    print("no collection limit hit up to 1,024,000 items")


print("== 1. multi-line rendering (check the 'bench' console tab) ==")
console.print("single line, info", level="info", channel=CH, timestamp=True)
console.print("multi A line 1\nmulti A line 2\nmulti A line 3", level="info", channel=CH, timestamp=True)
console.print(
    BRANCH + "tree line 1\n" + BRANCH + "tree line 2\n" + BRANCH + BRANCH + "tree line 3 (nested)",
    level="debug",
    channel=CH,
    timestamp=True,
)
console.print("trailing newline\n", level="info", channel=CH)
console.print("blank line between\n\nafter blank", level="info", channel=CH)

print("== 2. cost of one multi-line print vs many single prints ==")
lines = [f"line {i}" for i in range(20)]
block = "\n".join(lines)
timed("1 print with 20 lines", lambda: console.print(block, level="debug", channel=CH))
timed("5 single-line prints", lambda: [console.print(f"single {i}", level="debug", channel=CH) for i in range(5)])

print("== 3. limits ==")
biggest = probe_string_limit()
print(f"largest string built: {biggest} chars")
probe_collection_limit()

print("== 4. console.print near the string limit ==")
for size in (1000, 5000, 9000, 20000):
    if size > biggest and biggest > 0:
        print(f"skip {size}: above largest buildable string")
        continue
    try:
        res = console.print("y" * size, level="debug", channel=CH)
        print(f"print of {size} chars -> {res.status}")
    except Exception as err:
        print(f"print of {size} chars failed: {type(err)}: {err}")

print("Console test done")
