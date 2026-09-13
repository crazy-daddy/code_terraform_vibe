# Guide: Programming & Language Reference

Complete syntax, standard library, and language reference for Code: Terraform Python scripting.

---

## Variables

Store values for later use. No type declarations needed.

```python
x = 10
name = "oxygen"
active = True
```

*Language / Basics*

---

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

---

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

---

## Print

Output text to the console.

```python
print("Hello")
print(42)
print("Temp:", temp, "°C")
```

*Language / Basics*

---

## Self & Components

Most scripts in Code: Terraform run **inside a machine**. A Scanner script runs inside the Scanner; a Bio Lab script runs inside the Lab. Inside that script, `self` means **this machine**.

```
scan = self.scan("E14")
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

---

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

---

## Match / Case

Branch on the shape of a value. Supports literal cases, `_` wildcard, variable captures, `|` alternatives, `if` guards, list/tuple patterns with `*rest`, and dict-style patterns. An unguarded capture or `_` always matches and must be the final reachable case; a guard may still fall through. Mapping-pattern keys must be unique (`True` and `1` count as the same key). Dict-style patterns also work with fixed result objects, e.g. `result = self.input.take("iron_ore", 10)` followed by `case {"status": "ok", "moved": moved}:`.

```python
result = self.input.take("iron_ore", 10)
match result:
    case {"status": "ok", "moved": moved}:
        print("moved", moved)
    case {"status": status, "message": message}:
        print(status, message)
```

*Language / Data Structures*

---

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

---

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

---

## Regular Expressions

Import the built-in `re` module for pattern matching, captures, replacements, and regex-based splitting. It works without Shared Library research and returns `Match` objects from `search`, `match`, and `fullmatch`. Pair it with raw strings (`r"..."`) so you don't have to double every backslash in a pattern.

```python
import re

m = re.search(r"ore_(\d+)", "ore_42")
if m:
    print(m.group(1))
```

*Language / Basics*

---

## Lists & Tuples

Ordered collections and fixed pairs of values.

```python
readings = [10, 20, 30]
point = (12, 8)
print(point[0])
readings.append(40)
```

*Language / Data Structures*

---

## Dictionaries

Key-value pairs for named data.

```python
planet = {"name": "Mars", "temp": -63}
print(planet["name"])
```

*Language / Data Structures*

---

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
- `from functools import reduce`, reducer helper as a module import
- `import re`, regular expressions: `search`, `match`, `fullmatch`, `findall`, `sub`, and `split`
- `from dataclasses import dataclass, field`, generated record-class construction and field configuration

### Timing

- `sleep(seconds)`, intentionally wait before continuing. Loops are paced automatically; use this only when you want game time to pass.

### Other

- `hash(value)`, hash a string, number, bool, `None`, tuple-of-hashables, or class instance (identity by default, `__hash__` when defined)

*Guide / Programming*

---

## Exceptions

Exceptions let a helper function stop with a named error when the caller gives it impossible input or an assumption has broken. Use them for bugs and malformed calls. Expected gameplay outcomes such as cargo full, nothing scanned, or queue empty belong in command result objects: branch on `.status` and read `.message`. These objects are normal return values, not exceptions.

### Raise an error

Call an exception constructor with zero or one clear message, then `raise` it:

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

Use `try` / `except` when a script can recover and continue. The variable after `as` is the exception object: printing it shows its message, while `type(error)`, `isinstance(error, ValueError)`, identity checks, and `raise error` retain its exception class and identity.

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

`raise RuntimeError("message") from cause` evaluates and validates the cause, but the game console intentionally shows only the raised exception. Chained traceback metadata is not part of the displayed runtime surface.

### Built-in names

Common choices are `ValueError` for a value with the right type but wrong contents, `TypeError` for the wrong kind of value, `KeyError` for a missing dictionary key, `IndexError` for a bad list index, `AttributeError` for a missing field or method, and `RuntimeError` for a failed assumption while running.

Other supported names include `NameError`, `UnboundLocalError`, `ImportError`, `ModuleNotFoundError`, `ZeroDivisionError`, `StopIteration`, `GeneratorExit`, `AssertionError`, `NotImplementedError`, `RecursionError`, `IndentationError`, `OverflowError`, and `SyntaxError`. A completed generator raises `StopIteration`; its `.value` is the generator's `return` value. `GeneratorExit` is used by `generator.close()` and normally belongs inside generator cleanup.

You cannot define new exception classes in scripts. Pick the closest built-in name and make the message specific enough that the console tells you where the problem came from.

*Guide / Programming*

---

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

---

## Imports & Libraries

Imports have several precise kinds: executable built-in modules, typing-only support modules, compiler directives, the explicit shared root, and your own Library scripts. Library scripts unlock with **Shared Library** research; the built-in and support namespaces do not require that research.

### Executable built-in modules

Use `import random`, then `random.randint(1, 10)`, `from functools import reduce` for reducer-style algorithms, `import re` for regular expressions, or `from dataclasses import dataclass, field` for generated record classes. You can also call `random()`, `rand()`, `randint(min, max)`, and `reduce(fn, iterable, initializer?)` directly as global helpers. Regex helpers stay on the `re` module so pattern-matching code is explicit; `dataclass` and `field` likewise require their standard module import.

### Typing and editor support

`typing`, `types`, `collections.abc`, and `user_stubs` provide names for annotations and editor analysis. Their type names are erased while a script runs; they are not a place for executable helpers. `typing.TYPE_CHECKING` is always `False` in the game. `collections` is the package used to reach `collections.abc`. Put executable shared code in a Library instead of `user_stubs.py`.

`from __future__ import annotations` is a compiler directive, not a normal binding. Put future directives at the beginning of a module, after an optional module docstring and before ordinary statements. The directive itself creates no `annotations` name.

`__builtins__` is the explicit import view of the shared interpreter and game root, for example `from __builtins__ import len, get_component`. Script-owner locals such as `self` and `panel` are not part of that shared module. The generated `builtins` and `code_terraform` stubs exist only for external-editor type checking and cannot be imported by a running game script.

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

---

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

---

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

### When to use a class

- **Class**, custom initialization, inheritance, or operator overloading.
- **dataclass**, named fields plus generated construction, display, equality, or ordering.
- **`TypedDict`**, a mapping-shaped record or JSON payload (the editor autocompletes its keys).
- **dict**, dynamic, data-driven keys.

### What's not supported

Reasonably-full Python classes, with these deliberate exclusions:

- Metaclasses, `__slots__`, `abc` / `@abstractmethod`.
- The general descriptor protocol, only `@property` is exposed.
- `__new__`, `__del__`.
- Dynamic attribute hooks: `__getattr__`, `__setattr__`, `__delattr__`.
- `for` advances `__iter__` / `__next__` and generators lazily, so `break` works with an endless iterator. Operations that need the entire result, such as `list(...)`, remain bounded by the collection limit.
- A class that defines `__eq__` without defining `__hash__` is unhashable, matching Python. Define an integer-returning `__hash__` to use equality-aware instances as dict/set keys. Classes that define neither use identity hashing and also work as keys.

*Guide / Editor & Tools*

---
