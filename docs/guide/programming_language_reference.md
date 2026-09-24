# Guide: Programming & Language Reference

Complete syntax, standard library, and language reference for Code: Terraform Python scripting.

---

## Variables

Variables store values that you can use later.

```
x = 10
name = "oxygen"
active = True
```

You can use variables in expressions:

```
a = 5
b = 3
result = a + b
print(result)
```

Output: 8

*Guide / Programming*

## Operators

Operators combine values, compare values, and build conditions.

### Assignment vs equality

Use `=` to store a value. Use `==` to compare two values. Scripts do not use `===`.

```
target = 10
if value == target:
  print("match")
```

`=` changes a variable. `==` asks a question and returns `True` or `False`.

### Comparisons

```
a == b  # equal
a != b  # not equal
a < b  # less than
a <= b  # less than or equal
a > b  # greater than
a >= b  # greater than or equal
```

### Boolean logic

Use `and`, `or`, and `not` to combine conditions:

```
if powered and battery > 100:
  print("ready")
if not blocked:
  print("clear")
```

### Math and division

```
a + b  # add
a - b  # subtract
a * b  # multiply
a / b  # divide
a // b  # floor division
a % b  # remainder, also called modulo
a ** b  # power
```

Use `/` when you want normal division. Use `//` when you want the whole-number quotient. Use `%` when you want the remainder after division.

Modulo is useful for repeating patterns and even/odd checks:

```
value % 2 == 0 # even
value % 2 == 1 # odd
```

### Membership and None

Use `in` to check whether a value is inside a list, tuple, set, string, or dict keys. Use `is None` for the special empty value.

```
if target in scanned:
  print("known")
if result is None:
  print("nothing found")
```

*Guide / Programming*

## Numbers

### Overview

Numbers are one family, there is no separate stored `int` and `float` type. `int`, `float`, and `number` are three **views of the same value**, decided by the value itself.

### int, float, number

- `int`, a **whole** numeric value (no decimal part)
- `float`, a value **with a decimal part**
- `number`, **either** of the above

The label follows the current value, not how you wrote it:

```
type(5)    # int
type(0.6)   # float
type(4.0)   # int  (whole value)
type(10 / 2) # int  (10 / 2 is 5.0)
type(10 / 3) # float
```

> This is **not** Python's model. In Python `type(4.0)` is `float` because the literal was written as a float. Here it is `int` because the value is whole, the number itself is identical, only the label differs.

### Checking a number

```
isinstance(x, int)     # True if x is whole
isinstance(x, float)    # True if x has a decimal part
isinstance(x, int | float) # True for either numeric category
isinstance(x, "number")   # True for any number
x % 1 == 0         # True if x is whole
```

Use `isinstance(x, "number")` when you only care that a value is numeric at all, and `int(x)` to chop a value to a whole number (`int(3.7)` is `3`).

### Numbers in parameter types

DOCS, hover and signature help write each parameter's type the way Python does, and there `int` and `float` say what a parameter accepts rather than which view a value has:

- `count: int` takes a whole value however you wrote it (`2.0` is fine) and refuses one with a decimal part (`2.5` raises)
- `x: float` takes any number, whole or not

This is Python's own convention: wherever a `float` is expected, an `int` is accepted too.

### Precision

Decimal numbers use standard floating-point arithmetic, so tiny rounding can show up:

```
0.1 + 0.2  # 0.30000000000000004, not exactly 0.3
```

This is normal for calculated decimal values. Use `isclose()` when you mean close enough rather than bit-for-bit equality:

```
if isclose(0.1 + 0.2, 0.3):
  print("equal for this calculation")
```

The default `rel_tol` handles ordinary rounding relative to the size of the values. Use `abs_tol` when your accepted difference has a real gameplay meaning. For example, this treats a Rover within half a meter on both axes as being at the target:

```
target_x = 100
target_y = 40
pos = self.nav.get_position()

if isclose(pos.x, target_x, abs_tol=0.5) and isclose(pos.y, target_y, abs_tol=0.5):
  print("at target")
```

Choose the tolerance from what the value represents, such as meters, Wh, or a **0-1** level. Knowing only that a value is floating-point does not determine the right gameplay tolerance.

*Guide / Programming*

## Print

Use print() to output normal text to the console.

```
print("Hello")
print(42)
```

You can print multiple values separated by spaces:

```
temp = -63
print("Temperature:", temp, "°C")
```

Use warn() for monitor messages you want to stand out in the persistent console without showing a toast:

```
if self.efficiency() < 100:
  warn("oxygen generator below 100% efficiency")
```

Use debug() for noisy telemetry you only want while tuning a script. Debug lines are hidden from ALL unless you enable debug output from the console options menu:

```
debug("target", target_sector, "heat", self.get_heat())
```

The console can show THIS SCRIPT, ALL output, WARNINGS, or ERRORS.

*Guide / Programming*

## Self & Components

Most scripts in Code: Terraform run **inside a machine**. A Scanner script runs inside the Scanner; a Bio Lab script runs inside the Lab. Inside that script, `self` means **this machine**.

```
# Scanner script
scan = self.scan("E14")
```

```
# Bio Lab script
analysis = self.analyze()
if analysis.status == "ok":
  info = analysis.info
```

### Hardware actions are local

Actions that change physical state or spend game time are usually **self only**. Store their result, branch on `.status`, and read `.message`; specialized results add payload fields.

```
move = self.move("E14")
if move.status == "ok":
  pickup = self.collect()
```

### Reading another component

Use `get_component(id)` for read-only coordination:

```
scanner = get_component("scanner_1")
scanned = scanner.get_scanned()
```

Sometimes a local action accepts another component reference:

```
collector = get_component("bio_collector_1")
taken = self.take_from(collector)
if taken.status != "ok":
  print(taken.message)
```

The action still belongs to the Bio Lab's `self`; it is not remote control of the Collector. Use shared state or Signal Bus messages to coordinate separate machine scripts.

Stable ids such as `"bio_collector_1"` are safest for long-running scripts. Display names are convenient but can change.

*Guide / Programming*

## If / Elif / Else

Branching is how a script reacts to what it reads. A chain starts with `if`, adds any number of `elif` branches, and may end with `else`.

```
temp = get_component("thermometer").get_value()

if temp > 20:
  print("Warm")
elif temp > 0:
  print("Above freezing")
elif temp > -40:
  print("Cold")
else:
  print("Dangerously cold")
```

The first branch whose condition is true runs, and every branch after it is skipped. That is why the order matters: write the most specific condition first. Reversing the chain above would print `Cold` for every temperature below 20, because `temp > -40` is already true by then.

`elif` is not the same as a second `if`. A chain picks exactly one branch; separate `if` statements each get tested, so more than one can run.

```
# One of these runs.
if level > 80:
  self.set_throttle(0)
elif level < 20:
  self.set_throttle(1)

# Both of these can run.
if level > 80:
  print("high")
if level > 50:
  print("over half")
```

`else` is optional. Leave it off when there is nothing to do in the remaining case.

### What counts as true

A condition is any expression. Comparisons and `and` / `or` / `not` are covered on the **Operators** page. A bare value works too, and these are the ones that count as false:

- `False` and `None`
- the number `0`
- an empty string, list, tuple, dict, or set

Everything else is true, so `if result.sites:` reads as "if the scan found any sites".

```
result = self.sonar.scan()
if result.sites:
  print("found", len(result.sites))
else:
  print("nothing in range")
```

Use `is None` rather than `== None`, and be careful with a value that can legitimately be `0`: `if count:` treats a real count of zero as false, while `if count is not None:` does not.

### Branching on a result

Commands return a result object with a `.status` field. Do not test the result itself, because the object is true even when its status reports a rejection. Compare the status instead, and let the chain name each outcome:

```
result = self.input.take("iron_ore", 10)

if result.status == "ok":
  print("took", result.moved)
elif result.status == "partial":
  print("only got", result.moved)
else:
  print("failed:", result.message)
```

Every status a command can return is listed in its DOCS entry, so the chain can be written before the script is ever run.

### Choosing a value inline

When both branches only pick a value, the inline form is shorter than four lines:

```
mode = "day" if sun > 0 else "night"
```

### When to use Match / Case instead

A long chain that tests the same value over and over is what `match` is for. Reach for it when branching on the shape of a value or on many fixed alternatives, and see the **Match / Case** page. Keep `if` / `elif` / `else` for ranges, combined conditions, and anything testing more than one value.

*Guide / Programming*

## Loops & Scripts

Scripts run once by default. To keep a script running continuously, use a while loop:

```
while True:
  # this runs every game tick
  print("running")
```

The interpreter automatically gives time back to the game while loops run. World systems and other scripts keep moving, so you do not need `sleep()` to make a loop safe.

Use `sleep()` only when you intentionally want game time to pass before the script continues:

```
while True:
  print("every 5 seconds")
  sleep(5)
```

For loops iterate over a list:

```
for i in range(5):
  print(i)
```

See **Long-Running Scripts** for designing loops that re-read machine state and remain safe when a running script starts again after a game load.

*Guide / Programming*

## Match / Case

`match` lets a script branch on the shape of a value instead of writing a long chain of `if` checks.

```
packet = ["ore", 12]

match packet:
  case ["ore", amount] if amount > 0:
    print("ore", amount)
  case ["ice", amount]:
    print("ice", amount)
  case _:
    print("unknown packet")
```

### Patterns

- Literal patterns: `case "ok":`, `case 0:`, `case True:`, `case None:`
- Wildcard: `case _:`
- Captures: `case amount:`
- Alternatives: `case "busy" | "cooling":`
- Guards: `case [kind, amount] if amount > 0:`
- List/tuple patterns: `case [x, y]:`, `case [head, *rest]:`
- Dict patterns: `case {"status": "ok", "value": value}:`

Dict-style patterns also match result objects by field name:

```
result = self.input.take("iron_ore", 10)
match result:
  case {"status": "ok", "moved": moved}:
    print("moved", moved)
  case {"status": reason, "message": message}:
    warn(reason, message)
```

Class patterns such as `case Thing(x):` are not part of the interpreter. Use list, tuple, dict, literal, and field-name patterns instead.

*Guide / Programming*

## Conversion Functions

Convert between types using built-in functions.

```
str(42)    # "42"
int("7")    # 7
float("3.14") # 3.14
```

Character conversion, useful for building sector IDs (A1, B2, etc.):

```
chr(65)  # "A"
chr(66)  # "B"
ord("A")  # 65
```

Example, generate sector names:

```
row = 0
while row < 8:
  letter = chr(65 + row)
  sector = letter + str(1)
  print(sector) # A1, B1, C1...
  row = row + 1
```

*Guide / Programming*

## Strings & F-strings

F-strings let you embed expressions directly in strings:

```
heat = 45
print(f"Heat: {heat}/100")
name = "Crystal Shard"
print(f"Found {name} worth {300} credits")
```

Slicing extracts part of a string or list:

```
pos = "E13"
letter = pos[0]    # "E"
column = pos[1:]   # "13"
first3 = pos[:3]   # "E13"
```

Use 'in' to check membership:

```
if "A1" in scanned_list:
  print("already scanned")

if sector not in visited:
  print("new sector")
```

'in' works with lists, dicts (checks keys), and strings (checks substring).

### String methods

- `.upper()` / `.lower()`, case conversion
- `.strip()` / `.lstrip()` / `.rstrip()`, remove whitespace
- `.split(sep)`, split into list
- `.join(list)`, join list into string: `", ".join(["a", "b"])` → `"a, b"`
- `.find(sub)`, index of substring, -1 if not found
- `.index(sub)`, like find but raises error if not found
- `.replace(old, new)`, replace all occurrences
- `.startswith(s)` / `.endswith(s)`, check prefix/suffix
- `.count(sub)`, count occurrences
- `.title()` / `.capitalize()`, title case / capitalize first
- `.isdigit()` / `.isalpha()` / `.isalnum()` / `.isspace()`, character checks
- `.zfill(width)`, pad with zeros
- `.center(w)` / `.ljust(w)` / `.rjust(w)`, alignment
- `.format(args)`, `"Hello {}".format("world")`

*Guide / Programming*

## Regular Expressions

Use the built-in `re` module when plain string methods are not enough: matching a pattern, extracting groups, replacing variable-shaped text, or splitting on several separators.

`re` is a built-in module. It works without Shared Library research, but you import it so your script clearly signals that it is using regular expressions:

```
import re

text = "ore_42 at E13"
match = re.search("ore_(\d+)", text)
if match:
  print(match.group(1))  # 42
```

### Match helpers

- `re.search(pattern, string, flags=0)`, find the first match anywhere
- `re.match(pattern, string, flags=0)`, match only at the start
- `re.fullmatch(pattern, string, flags=0)`, match the whole string

These return a `Match` object, or `None` when there is no match.

```
import re

m = re.fullmatch("([A-Z])(\d+)", "E13")
if m is not None:
  print(m.group(0))  # E13
  print(m.group(1))  # E
  print(m.group(2))  # 13
  print(m.span())   # (0, 3)
```

`Match.group(0)` is the whole match. Capturing groups start at `1`. `Match.groups()` returns all captured groups as a tuple.

### Lists and replacements

```
import re

print(re.findall("\d+", "A12 B7"))
print(re.split("[,;]\s*", "iron, ice; quartz"))
print(re.sub("ore_(\d+)", "ore-\\1", "ore_42"))
```

`re.findall()` returns strings when the pattern has no groups, one captured value when it has one group, or tuples when it has multiple groups. `re.sub()` replacement text supports numeric backreferences such as `\\1` and `\\g<1>`.

### Flags

Flags are module constants. Combine them with `|`:

```
import re

flags = re.IGNORECASE | re.MULTILINE
print(re.findall("^ore", "Ore\nice", flags))
```

Available flags:

- `re.IGNORECASE` / `re.I`
- `re.MULTILINE` / `re.M`
- `re.DOTALL` / `re.S`

### Syntax note

Code: Terraform exposes a Python-shaped `re` API backed by a linear-time pattern engine. Common patterns like `\d+`, `[A-Z]+`, `.*`, `^`, `$`, groups `(...)`, and alternation `a|b` are supported. Backtracking-only features such as lookaround and pattern backreferences are not supported. Replacement backreferences in `re.sub()` remain supported.

Patterns are capped at **512** characters. Quantified groups such as `(a+)+` are safe to use because matching does not backtrack.

*Guide / Programming*

## Lists & Tuples

Lists are ordered collections. Create with brackets. Tuples are fixed ordered collections; create them with parentheses when you want a stable pair, coordinate, or small record:

```
items = [1, 2, 3]
empty = []
mixed = ["hello", 42, True]
point = (12, 8)
single = (42,)
```

Access by index (0-based, negative from end):

```
first = items[0]  # 1
last = items[-1]  # 3
x = point[0]    # 12
```

Slicing with step:

```
items[1:3]   # [2, 3]
items[::2]   # [1, 3], every other
items[::-1]  # [3, 2, 1], reversed
point[:]    # (12, 8)
```

List comprehension, build lists concisely:

```
squares = [x * x for x in range(10)]
evens = [x for x in range(20) if x % 2 == 0]
```

Tuple unpacking and multiple assignment:

```
a, b, c = [1, 2, 3]
first, second = ("hello", "world")


def choose_route():
  return "E14", ["E13", "E14"]

target, route = choose_route()

routes = [(0, "nav_module"), (1, "cargo_rack")]
for slot, item in routes:
  print(slot, item)
```

### List methods

- `.append(value)`, add to end
- `.pop()`, remove and return last item
- `.insert(index, value)`, insert at position
- `.remove(value)`, remove first occurrence
- `.index(value)`, find position of value
- `.count(value)`, count occurrences
- `.sort()`, sort in place
- `.reverse()`, reverse in place
- `.copy()`, shallow copy
- `.extend(list_or_tuple)`, add all items from another sequence
- `.clear()`, remove all items
- `.length`, number of items

Tuples are immutable. They support indexing, slicing, `.index(value)`, `.count(value)`, `.length`, `len()`, and `for` loops.

*Guide / Programming*

## Dictionaries

Dictionaries store key-value pairs. Keys can be any hashable value: strings, numbers, booleans, `None`, or tuples made only of hashable values. String keys are the most common for game data:

```
data = {"name": "Crystal", "value": 300}
empty = dict()
```

Access and modify:

```
print(data["name"])    # Crystal
data["quality"] = "high"
coords = {}
coords[(0, 0)] = "base"
```

Check if a key exists:

```
if "name" in data:
  print(data["name"])
```

Iterate:

```
for key in data.keys():
  print(key, data[key])

for pair in data.items():
  key = pair[0]
  val = pair[1]
  print(f"{key}: {val}")
```

### Merge

Use `left | right` to make a new merged dictionary. Use `left |= right` to update the existing dictionary in place. When the same key appears in both, the right-hand value wins.

```
thing = {"a": 1, "b": 2}
other = {"a": 3, "c": 4}
print(thing | other) # {"a": 3, "b": 2, "c": 4}
```

### Methods

- `.keys()`, list of all keys
- `.values()`, list of all values
- `.items()`, list of [key, value] pairs
- `.get(key, default)`, get value or default if missing
- `.has(key)`, check if key exists
- `.pop(key, default)`, remove key and return value
- `.popitem()`, remove and return the last inserted [key, value] pair
- `.update(dict)`, merge another dict in
- `.setdefault(key, default)`, get or set default
- `.clear()`, remove all entries

*Guide / Programming*

## Built-in Functions Overview

These functions are always available.

### Output

- `print(values...)`, print normal text to console
- `warn(values...)`, print an amber warning line to the console's WARNINGS view
- `debug(values...)`, print low-priority telemetry, hidden from ALL unless debug output is enabled
- `notify(text, level?, duration?)`, show a toast and archive it in Notifications

### Types

- `type(value)`, returns value-based categories such as `int` for whole numbers, `float` for fractional numbers, `str`, and `bool`. Numeric categories use the current value, so `type(4.0)` is `int`.
- `isinstance(value, type)`, check type/category: `isinstance(name, str)`, `isinstance(n, int)`, `isinstance(n, int | float)`, `isinstance(x, (int, str))`, or broad `isinstance(n, "number")`
- `callable(value)`, `True` if value is a function, method, class, or object with a callable `__call__`
- `len(value)`, length of string, list, tuple, dict, or set
- `bool(value)`, convert to `True`/`False`

### Conversion

- `str(value)`, `int(value, base?)`, `float(value)`
- `list(value)`, `tuple(value)`, `set(value)`, `dict(...)`, type constructors
- `chr(code)`, `ord(char)`
- `hex(n)`, `bin(n)`, `oct(n)`, integer to base-prefixed string
- `repr(value)`, debug-friendly string representation

### Math

- `abs(n)`, `round(n, digits?)`, `pow(base, exp)`
- `isclose(a, b, rel_tol=0.000000001, abs_tol=0.0)`, compare floating-point results with an accepted difference
- `min(values...)` / `max(values...)`, args, a list, or a tuple
- `sum(sequence, start=0)` / `prod(sequence, start=1)`, add or multiply numeric items
- `random()` / `rand()`, random float from 0 up to but not including 1
- `randint(min, max)`, random integer with inclusive bounds
- `import random`, module form with `random.random()`, `random.rand()`, and `random.randint(min, max)`
- `floor(n)`, `ceil(n)`, `trunc(n)`, `sign(n)`, `divmod(a, b)`
- `sqrt(n)`, `exp(n)`, `log(n)`, `log2(n)`, `log10(n)`
- `sin(n)`, `cos(n)`, `tan(n)`, `asin`, `acos`, `atan`, `atan2(y, x)`
- `degrees(rad)`, `radians(deg)`
- `inf`, positive infinity; use `-inf` for negative infinity
- `pi`, `tau`, constants

### Sequences

- `range(stop)` / `range(start, stop, step)`
- `sorted(sequence, key=fn, reverse=False)`, new sorted list. Pass `key=lambda x: x.value` to sort by a computed field; `reverse=True` for descending.
- `reversed(sequence)`, new reversed list
- `enumerate(sequence, start=0)`, list of `(index, value)` pairs
- `zip(sequence1, sequence2, ..., strict=False)`, combine sequences into pairs; `strict=True` raises if lengths differ
- `map(fn, sequence)` / `filter(fn, sequence)` / `reduce(fn, sequence, initializer?)`, transform, select, or fold items
- `pairwise(sequence)`, neighboring `(a, b)` pairs
- `batched(sequence, size)`, fixed-size tuple batches
- `starmap(fn, sequence)`, call `fn` with tuple/list items unpacked as arguments
- `flatten(sequence)`, flatten one nested level
- `count_by(sequence, key_fn?)`, count values or computed keys into a dict
- `iter(sequence)` / `next(iterator)`, manual iteration
- `chain(seq1, seq2, ...)`, concatenate sequences
- `accumulate(sequence)`, running totals
- `combinations(sequence, r)` / `permutations(sequence, r)`, combinatorics
- `product(seq1, seq2, ...)`, cartesian product

### Logic

- `all(sequence)`, `True` if every item is truthy
- `any(sequence)`, `True` if any item is truthy

### Modules

- `import random`, random-number helpers
- `from functools import reduce`, reducer helper as a module import, plus `partial` for pre-bound callables and `lru_cache` / `cache` for memoization
- `import re`, regular expressions: `search`, `match`, `fullmatch`, `findall`, `sub`, and `split`
- `from dataclasses import dataclass, field`, generated record-class construction and field configuration, plus `asdict`, `astuple`, `fields`, `replace`, `is_dataclass`, and the `MISSING` sentinel
- `import json`, JSON text: `dumps` and `loads`
- `import heapq`, priority queues: `heappush`, `heappop`, `heappushpop`, `heapreplace`, `heapify`, `nsmallest`, and `nlargest`
- `import traceback`, where a caught exception came from: `print_exc` and `format_exc`
- `from enum import Enum, auto`, named sets of constants: `Enum`, `IntEnum`, `StrEnum`, `Flag`, `IntFlag`, `auto`, and the `unique` and `verify` checks

### Timing

- `sleep(seconds)`, intentionally wait before continuing. Loops are paced automatically; use this only when you want game time to pass.

### Other

- `hash(value)`, hash a string, number, bool, `None`, tuple-of-hashables, or class instance (identity by default, `__hash__` when defined)

*Guide / Programming*

## Exceptions

Exceptions let a helper function stop with a named error when the caller gives it impossible input or an assumption has broken. Use them for bugs and malformed calls. Expected gameplay outcomes such as cargo full, nothing scanned, or queue empty belong in command result objects: branch on `.status` and read `.message`. These objects are normal return values, not exceptions.

### Raise an error

Call an exception class with a clear message, then `raise` it:

```
def normalize_sector(sector):
  if not isinstance(sector, str):
    raise TypeError(f"normalize_sector: expected str, got {type(sector)}")
  if len(sector) < 2:
    raise ValueError("normalize_sector: expected a sector like A1")
  return sector
```

`type("A1")` returns `str`, not `string`. Prefer `isinstance(value, str)` when you want a true/false type check.

### API boundary

Gameplay APIs follow the same distinction. Wrong argument kinds raise `TypeError`; correctly typed but invalid values raise `ValueError` or another documented exception. Ordinary world states do not raise: a command returns its result object so your script can handle `"busy"`, `"no_cargo_space"`, `"not_found"`, and similar outcomes without guessing.

### Catch and keep running

Use `try` / `except` when a script can recover and continue. The variable after `as` is the exception object: printing it shows its message, `error.args` holds the arguments it was created with, and `type(error)`, `isinstance(error, ValueError)`, identity checks, and `raise error` retain its exception class and identity.

```
target = None
try:
  target = normalize_sector(command.args["sector"])
except KeyError as error:
  warn("command missing sector", error)
except (TypeError, ValueError) as error:
  warn(error)

if target is not None:
  print("target", target)
```

Catch the narrowest error that makes sense. `except Exception as error:` catches ordinary game-script exceptions derived from `Exception`, which is useful at a boundary but can hide mistakes if used everywhere. It does not catch control-flow exceptions derived directly from `BaseException`, such as `GeneratorExit`. A handler can name one supported exception, a dotted alias such as `errors.ValueError`, or a tuple such as `except (KeyError, TypeError):`. Computed handler expressions are not part of the game-script surface. Handler names resolve when an error is caught, so aliases and shadowing behave normally. An `as error` target exists only inside that handler and is cleared on every exit; copy any detail you need later into another variable.

### Cleanup and re-raising

A `try` block may have `else`, which runs only when the `try` body finishes without an exception, and `finally`, which always runs before control leaves through success, error, `return`, `break`, or `continue`. A new error or control-flow exit from `finally` replaces the pending one, so keep cleanup small and predictable. Bare `raise` inside an active handler or its `finally` block re-raises the same exception identity.

`raise RuntimeError("message") from cause` stores the cause on the new exception's `__cause__` (and `from None` marks the chain as deliberately cut). An exception raised while another is being handled records that one on `__context__`. The game console shows only the raised exception; your handler can walk `__cause__` and `__context__` when the earlier failure matters.

### Built-in names

Common choices are `ValueError` for a value with the right type but wrong contents, `TypeError` for the wrong kind of value, `KeyError` for a missing dictionary key, `IndexError` for a bad list index, `AttributeError` for a missing field or method, and `RuntimeError` for a failed assumption while running.

Other supported names include `NameError`, `UnboundLocalError`, `ImportError`, `ModuleNotFoundError`, `ZeroDivisionError`, `StopIteration`, `GeneratorExit`, `AssertionError`, `NotImplementedError`, `RecursionError`, `IndentationError`, `OverflowError`, and `SyntaxError`. A completed generator raises `StopIteration`; its `.value` is the generator's `return` value. `GeneratorExit` is used by `generator.close()` and normally belongs inside generator cleanup.

### Your own exception classes

Derive a class from `Exception` (or from any built-in exception) when a failure deserves its own name, for example so a library can signal one condition and every caller can catch exactly that:

```
class LowBattery(Exception):
  def __init__(self, level):
    super().__init__(f"battery at {level}%")
    self.level = level

def check(rover):
  level = round(rover.battery.level() * 100)
  if level < 20:
    raise LowBattery(level)

try:
  check(get_component("rover_1"))
except LowBattery as err:
  print(err, err.level)
```

`class Empty(Exception): pass` is enough for a class with no extra data: `Empty("no cargo")` stores the message on `.args` and `str(err)` returns it. A bare `raise Empty` creates the object with no arguments. `except Exception as err:` catches every class derived from `Exception`, including yours, and `isinstance(err, LowBattery)` and `issubclass(LowBattery, Exception)` walk the hierarchy. Override `__str__` when the console text should differ from the message argument. Pick the closest built-in base so generic handlers keep working, and keep the message specific enough that the console tells you where the problem came from.

*Guide / Programming*

## Utility Helpers

Small helper functions are always available in every script. Use this page when you need quick random numbers, bounds-safe coordinates, math, collection transforms, or console output without hunting through the full Built-in Functions reference.

### Random numbers

Use the Python-shaped module form when you want code to read like normal Python:

```
import random as rng

roll = rng.randint(1, 6)
jitter = rng.random()
print("roll", roll, "jitter", jitter)
```

`random.random()` returns a float from **0** up to but not including **1**. `random.rand()` is the same helper with a shorter name. `random.randint(min, max)` returns a whole number between `min` and `max`, including both ends.

You can also call the same helpers globally:

```
roll = randint(1, 6)
jitter = rand()
```

If you import the module as plain `import random`, the name `random` refers to the module in that script. That is fine; call `random.random()` for the float helper.

### Random valid coordinates

Planet bounds are a good partner for `randint`:

```
planet = get_component("nocturna")
b = planet.get_bounds()

x = randint(b.min_x, b.max_x)
y = randint(b.min_y, b.max_y)

if planet.contains(x, y):
  print("valid target", x, y)
```

### Numeric helpers

Common math helpers are built in:

- `min(...)` / `max(...)`, choose the smallest or largest value
- `sum(items, start=0)` / `prod(items, start=1)`, add or multiply numeric values
- `round(n, digits?)`, `floor(n)`, `ceil(n)`, `trunc(n)`, shape numbers
- `abs(n)`, `sign(n)`, `divmod(a, b)`, distance, direction, and quotient/remainder
- `sqrt(n)`, `sin(n)`, `cos(n)`, `atan2(y, x)`, geometry and steering helpers
- `degrees(rad)` / `radians(deg)`, convert angle units

Example:

```
distance = 42.8
whole = ceil(distance)
hours, minutes = divmod(135, 60)
print(whole, hours, minutes)
```

### Collection helpers

These help with lists, tuples, strings, dicts, and sets:

- `len(value)`, length
- `range(...)`, integer sequences for loops
- `sorted(sequence, key=fn, reverse=False)`, sorted copy
- `reversed(sequence)`, reversed copy
- `enumerate(sequence)`, `(index, value)` pairs
- `zip(a, b, ..., strict=False)`, combine sequences; `strict=True` raises if lengths differ
- `map(fn, sequence)` / `filter(fn, sequence)` / `reduce(fn, sequence, initializer?)`, transform, select, or fold values
- `pairwise(sequence)`, neighboring pairs, useful for route segments
- `batched(sequence, size)`, chunks for page-sized work or repeated commands
- `starmap(fn, sequence)`, unpack tuple/list rows into a function call
- `flatten(sequence)`, one-level flattening for nested route or cargo lists
- `count_by(sequence, key_fn?)`, counts into a dict, optionally by a computed key
- `all(sequence)` / `any(sequence)`, boolean checks

Example:

```
items = ["iron_ore", "ice", "quartz"]
for index, item in enumerate(sorted(items)):
  print(index, item)

print(count_by(["ice", "ore", "ice"]))
```

### Console helpers

Use `print()` for normal output, `warn()` for persistent warnings, `debug()` for low-priority telemetry, and `notify(text, level?)` for on-screen alerts. Use the Console component when a script intentionally owns a noisy display.

```
warn("storage nearly full")
debug("loop heartbeat")
notify("Rover battery low", "warn")

console = get_component("console")
console.clear("alarms")
```

For the exhaustive list and exact signatures, open **Built-in Functions**.

*Guide / Programming*

## Imports & Libraries

Imports have several precise kinds: executable built-in modules, typing-only support modules, compiler directives, the explicit shared root, and your own Library scripts. Library scripts unlock with **Shared Library** research; the built-in and support namespaces do not require that research.

### Executable built-in modules

Use `import random`, then `random.randint(1, 10)`, `import re` for regular expressions, `import json` to turn records into text and back, `import heapq` for priority queues, `import traceback` to find out where an exception you caught came from, `from enum import Enum, IntEnum, StrEnum, Flag, auto` for named sets of constants, `from functools import reduce, partial, lru_cache, cache` for reducer-style algorithms, pre-bound callables and memoization, or `from dataclasses import dataclass, field` for generated record classes, with `asdict`, `astuple`, `fields`, `replace`, `is_dataclass` and the `MISSING` sentinel alongside them. You can also call `random()`, `rand()`, `randint(min, max)`, and `reduce(fn, iterable, initializer?)` directly as global helpers. Everything else stays on its own module so the code says where it came from: regex helpers on `re`, and `dataclass` and `field` likewise require their standard module import.

### Typing and editor support

`typing`, `types`, `collections.abc`, and `user_stubs` provide names for annotations and editor analysis. Their type names are erased while a script runs; they are not a place for executable helpers. `typing.TYPE_CHECKING` is always `False` in the game. `collections` is the package used to reach `collections.abc`. Put executable shared code in a Library instead of `user_stubs.py`.

`from __future__ import annotations` is a compiler directive, not a normal binding. Put future directives at the beginning of a module, after an optional module docstring and before ordinary statements. The directive itself creates no `annotations` name.

`__builtins__` is the explicit import view of the shared interpreter and game root, for example `from __builtins__ import len, get_component`. Script-owner locals such as `self` and `panel` are not part of that shared module. Game type names such as `Smelter`, `Battery`, and `Component` are part of it too, as annotation-only names: `from __builtins__ import Smelter` binds `Smelter` wherever a type is named. An annotation needs no import, because annotations never run; a place that does run, such as a `TypedDict` field dictionary or a type alias, does need it. In an external editor those names are already in scope and need no import at all. Every machine is a `Component` at runtime, so branch on `type_id` when you need to tell one kind from another; there is no per-machine class to pass to `isinstance`. The generated `builtins` and `code_terraform` stubs exist only for external-editor type checking and cannot be imported by a running game script.

### Player Libraries

After **Ship Computer** and **Shared Library** are researched, open **Ship → Computer → Library** in the left sidebar and click `+ New`. A Library script is shared code: write a helper once, then import it from any machine script.

Create a Library script called `sensors`:

```
def temp():
  """Read the current thermometer value."""
  return get_component("thermometer").get_value()

def o2():
  """Read the current oxygen sensor value."""
  return get_component("oxygen_sensor").get_value()
```

Import specific functions:

```
from sensors import temp

print(temp())
```

Import all public names from a library:

```
from sensors import *

print(temp())
print(o2())
```

Names starting with `_` stay private and are not imported by `*`. Or import the whole module:

```
import sensors

print(sensors.o2())
```

Library scripts run in their own shared scope. Built-ins and top-level game functions are available, but caller-local names are not. `self` and `panel` are not defined inside a library, so pass a component, component id, or other context into a helper when it needs to act for the importing script.

Function docstrings from imported libraries show in hover and autocomplete, so shared helpers can document their own parameters, return values, exceptions, and fixed result contracts.

*Guide / Programming*

## Docstrings

Docstrings are string literals placed at the top of a function body. They do not change how the function runs; they document what the function is for.

When you hover a user-defined function or see it in autocomplete, the editor shows its signature, its docstring, and its return annotation if it has one. Imported library functions show their docstrings too. Add a return annotation such as `-> str | None` when you want the tooltip's separate return line.

```
def next_needed(order) -> str | None:
  """Pick the next missing item for an order.

  [[helper]]

  ## Returns

  - a fragment id when one is still required
  - `None` when the order already has everything it needs
  """
  for item in order.requires.keys():
    if order.delivered.get(item, 0) < order.requires[item]:
      return item
  return None
```

### Formatting

Docstrings use the same markdown-lite formatting as DOCS descriptions:

- Inline code: `status`, `"ok"`, `self.deliver()`
- Bold text: **important**
- Badges: **helper** or **self only**
- Headings: `## Returns`
- Callouts: lines starting with `>`
- Bullets: `- item` or `• item`
- Numbered lists: `1. item`
- Tables: a header row, a `|---|---|` separator row, then one row per line
- Fenced code blocks with triple backticks

The list above is rendered, so the markers are invisible. This is what you type, one example per line:

```text
Inline code: `status`, `"ok"`, `self.deliver()`
Bold text: **important**
Badges: [[helper]] or [[self only]]
Heading: ## Returns
Callout: > check the status first
Bullet: - item
Numbered: 1. item
```

A table needs the separator row or it renders as plain text:

```text
| Sector | Row | Col |
|---|---|---|
| C4 | 3 | 4 |
| C14 | 3 | 14 |
```

Use blank lines between sections when you want the hover to render them as separate blocks.

### Variants

A triple-quoted string at the very top of a script is a script description, not a function docstring. The Variants tab uses the first non-empty line of that top-of-file docstring as the variant description. If there is no top-of-file docstring, the first `#` comment is used instead.

```
"""Night route: charge first, then collect ice."""

while True:
  print("working")
```

For function-level help, put the docstring immediately under `def`. For variant summaries, put it at the top of the file before any code.

*Guide / Programming*

## Writing Classes

Classes bundle **data** (attributes) with **behavior** (methods) into one reusable shape. An instance is one filled-in copy.

```
class Counter:
  def __init__(self, start):
    self.n = start   # an instance attribute
  def inc(self):
    self.n += 1

c = Counter(10)
c.inc()
print(c.n)       # 11
```

### self, __init__, and attributes

`__init__(self, ...)` runs once when you write `Counter(10)`, it sets up the new instance. Every method takes `self` (the instance) as its first parameter, and `self.x = ...` creates an instance attribute. A value assigned in the class body (`limit = 5`) is a **class attribute**, shared by all instances and readable as `Counter.limit` or `c.limit`.

### self inside a machine script

In a machine's own script the top-level `self` is the machine (`self.mine()`). Inside a class method, `self` is the **object**, they never collide, because a method's `self` is simply its first parameter.

> If a method needs to drive the machine, pass it in: `Planner(self)` at the top level (where `self` is the machine), store it (`self.bot = bot`), then call `self.bot.mine()` inside the method.

### Inheritance and super()

`class Dog(Animal):` inherits `Animal`'s methods and attributes. Override any of them, and reach the base version with `super()`:

```
class Animal:
  def __init__(self, name):
    self.name = name
  def speak(self):
    return "..."

class Dog(Animal):
  def __init__(self, name, breed):
    super().__init__(name)  # run Animal's setup first
    self.breed = breed
  def speak(self):
    return self.name + " says woof"

d = Dog("Rex", "husky")
print(d.speak())        # Rex says woof
print(isinstance(d, Animal), issubclass(Dog, Animal)) # True True
```

Multiple inheritance resolves by Python's C3 method-resolution order, so cooperative `super()` works across a diamond, every `__init__` in the chain runs once.

### Operators are dunder methods

Operators and builtins are sugar for `__dunder__` method calls. Define them to make your objects act like built-in types:

```
class Vec:
  def __init__(self, x):
    self.x = x
  def __add__(self, o):
    return Vec(self.x + o.x)    # powers a + b
  def __eq__(self, o):
    return self.x == o.x      # powers a == b
  def __repr__(self):
    return "Vec(" + str(self.x) + ")"  # how print() shows it
```

`__lt__` powers `<`, `__len__` powers `len()` and truthiness, `__getitem__` powers `x[k]`, `__contains__` powers `in`, `__iter__` powers `for`, and `__call__` makes an instance callable.

> Operator overloads must be **pure**, they cannot `sleep()` or change game state. Regular methods, `__init__`, and `__call__` can.

### @property and method decorators

`@property` turns a method into an attribute read **without parens**; add `@name.setter` to allow assignment:

```
class Tank:
  def __init__(self):
    self._level = 0
  @property
  def level(self):
    return self._level
  @level.setter
  def level(self, v):
    self._level = max(0, v)

t = Tank()
t.level = 42      # runs the setter
print(t.level)     # runs the getter
```

`@staticmethod` defines a method with no `self`; `@classmethod` receives the class as `cls`. Any function can be a decorator (`@deco` rewrites to `name = deco(name)`). `from functools import total_ordering` fills in the rest of the comparisons from `__eq__` plus one of `__lt__` / `__le__` / `__gt__` / `__ge__`.

### Dataclasses

Use the built-in `dataclasses` module when a class is mainly a declaration of named fields but still needs class behavior. The decorator generates declaration-ordered construction, readable representation, value equality, and optional ordering; `__post_init__` is the place for validation after generated assignment.

```
from dataclasses import dataclass, field

@dataclass(order=True)
class Job:
  priority: int
  label: str = ""
  tags: list[str] = field(default_factory=list, compare=False)

  def __post_init__(self):
    if self.priority < 0:
      raise ValueError("priority must be non-negative")

a = Job(2, "ice run")
b = Job(1, "ore run")
a.tags.append("cold")
print(b < a, a)
```

`default_factory` creates an independent mutable value for every instance. Mutable or otherwise unhashable direct defaults such as lists, dictionaries, and sets are rejected; use `default_factory` for them. `dataclass` supports `init`, `repr`, `eq`, `order`, and `kw_only`. `field` supports `default`, `default_factory`, `init`, `repr`, `compare`, and `kw_only`. Inherited annotated fields and explicit field overrides participate in the generated constructor.

A dataclass remains an ordinary user-class instance. It does not become a dict and cannot cross JSON-shaped game boundaries such as the Signal Bus or notebook APIs. Use `TypedDict` for mapping-shaped payloads and cached rows; use a dataclass for methods, validation, generated construction, value equality, or ordering.

The compatibility spellings `frozen=False`, `unsafe_hash=False`, `slots=False`, and `weakref_slot=False` may be passed, but their `True` behavior is not supported. `match_args`, `ClassVar`, `InitVar`, `MISSING`, `KW_ONLY`, `Field`, `FrozenInstanceError`, `is_dataclass`, `asdict`, `astuple`, `replace`, `fields`, `make_dataclass`, and public `__dataclass_fields__` introspection are not supported. Annotation types otherwise stay erased and are not enforced. Canonical `ClassVar` and `InitVar` annotations are recognized only so the decorator can reject those unsupported field forms clearly; all other fields come from executed annotated names.

### Controlling construction with __new__

Building an instance has two steps. `__new__` decides **which object exists**, then `__init__` fills it in. Most classes only need `__init__`; reach for `__new__` when `Cls(...)` should hand back an object it already has.

```
class Settings:
  _instance = None
  def __new__(cls):
    if cls._instance is None:
      cls._instance = super().__new__(cls)
    return cls._instance
  def __init__(self):
    self.rate = 5

print(Settings() is Settings())  # True, always the same object
```

`__new__` takes the class as its first parameter (`cls`, not `self`) and must **return** the object. `super().__new__(cls)` makes a fresh one. Return an object of another type and `__init__` is skipped entirely, which is how a constructor can hand back a subclass.

> `__new__` must answer immediately: it cannot `sleep()` or take world actions. Allocation only picks the object; put the work in `__init__`, which can still do both.

### Answering unknown attributes with __getattr__

`__getattr__(self, name)` runs only when a name was **not** found the normal way, so it never slows down or shadows a real attribute:

```
class Readings:
  def __init__(self, values):
    self.values = values
  def __getattr__(self, name):
    if name in self.values:
      return self.values[name]
    raise AttributeError(name)

r = Readings({"pressure": 91})
print(r.pressure)   # 91
```

Raising `AttributeError` is how you say a name really is missing, and it is what `hasattr()` and `getattr(obj, name, default)` look for. Like operator dunders, `__getattr__` must be pure.

### Registering subclasses with __init_subclass__

`__init_subclass__` runs on a **base** each time a subclass is defined, which is the plain way to keep a registry:

```
class Job:
  registry = []
  def __init_subclass__(cls):
    Job.registry.append(cls)

class Haul(Job): pass
class Scan(Job): pass
print(len(Job.registry))  # 2
```

It receives the new class as `cls` and never fires for the class that defines it.

### When to use a class

- **Class**, custom initialization, inheritance, or operator overloading.
- **dataclass**, named fields plus generated construction, display, equality, or ordering.
- **`TypedDict`**, a mapping-shaped record or JSON payload (the editor autocompletes its keys).
- **dict**, dynamic, data-driven keys.

### What's not supported

Reasonably-full Python classes, with these deliberate exclusions. Defining any of them is reported as an error naming the method, so nothing you write is silently ignored:

- Metaclasses, `__slots__`, `abc` / `@abstractmethod`.
- The general descriptor protocol (`__get__`, `__set__`, `__delete__`, `__set_name__`), only `@property` is exposed.
- `__del__`. Scripts have no reference counting and their memory is released all at once when the script stops, so a finalizer could never run at a meaningful moment. Release things in a method you call yourself.
- `__setattr__`, `__delattr__`, `__getattribute__`. Attribute assignment always stores directly; use a `@property` setter to run code when a value changes, and `__getattr__` for names the class does not already have.
- `for` advances `__iter__` / `__next__` and generators lazily, so `break` works with an endless iterator. Operations that need the entire result, such as `list(...)`, remain bounded by the collection limit.
- A class that defines `__eq__` without defining `__hash__` is unhashable, matching Python. Define an integer-returning `__hash__` to use equality-aware instances as dict/set keys. Classes that define neither use identity hashing and also work as keys.

*Guide / Editor & Tools*
