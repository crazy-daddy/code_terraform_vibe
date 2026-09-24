# Guide: language_reference

## Variables

Store values for later use. No type declarations needed.

```python
x = 10
name = "oxygen"
active = True
```

*Language / Basics*

## Print

Output text to the console.

```python
print("Hello")
print(42)
print("Temp:", temp, "°C")
```

*Language / Basics*

## Type Annotations

Optional type hints on assignments and function signatures, in the standard Python (PEP 526) form. `thermometer: Thermometer = get_component("thermometer")` documents the variable's type inline; the editor uses the annotation for hover, autocomplete, and Cmd+click navigation. Function params accept the same form (`def f(x: int):`) along with a return annotation (`-> Site:`). Generic shapes work: `xs: list[Site] = []`, `m: dict[str, int] = {}`, `b: Optional[Battery] = None`. Annotations help the editor understand your code. Annotation types are not evaluated and do not check or convert values at runtime. The structural exception is `@dataclass`: annotated class-attribute names become fields used to generate its constructor and other methods.

```python
thermometer: Thermometer = get_component("thermometer")
xs: list[int] = []

def pick(sites: list[Site]) -> Site:
    return sites[0]
```

*Language / Basics*

## Ellipsis

`...` is a value. It is written as three dots or by its name `Ellipsis`, and there is exactly one of it, so `x is Ellipsis` is how you test for it. It does two jobs. As a statement it stands in for a body you have not written yet: `def plan(): ...` runs and returns `None`, the same as `pass`. Inside a type annotation it means "any number of": `tuple[float, ...]` is a tuple of any length, and `Callable[..., Site]` is a function that takes any arguments and returns a `Site`. It is truthy, it prints as `Ellipsis`, and it works as a dict key or a set member. Annotations are erased when a script runs, so the annotation forms cost nothing at runtime; the editor reads them for hover and autocomplete.

```python
def plan_route(sites):
    ...          # a body you have not written yet

readings: tuple[float, ...] = (1.0, 2.5, 4.0)   # a tuple of any length
pick: Callable[..., Site]                       # any arguments, returns a Site

print(...)                # Ellipsis
print(... is Ellipsis)    # True
```

*Language / Basics*

## Tracebacks

When you catch an exception, the message tells you what went wrong and nothing about where. Import the built-in `traceback` module and call `traceback.print_exc()` inside an `except` block to print the whole chain of calls that led to it, innermost last, each line naming the script or Library, the line number and the function. `traceback.format_exc()` returns the same text as a string instead of printing it, so you can put it in a `notify()`, write it to a Signal Bus channel, or keep it for later. Outside an `except` block both report `NoneType: None`, because there is no exception to describe. An uncaught error already prints its file and line by itself; this is for the ones your own code handles, which is most of them once a script grows a Library.

```python
import traceback

try:
    site = self.sonar.best_site()
    self.nav.move_to(site.id)
except Exception:
    traceback.print_exc()          # where it broke, frame by frame

try:
    risky()
except Exception:
    notify(traceback.format_exc(), "error")
```

*Language / Basics*

## Regular Expressions

Import the built-in `re` module for pattern matching, captures, replacements, and regex-based splitting. It works without Shared Library research and returns `Match` objects from `search`, `match`, and `fullmatch`. Pair it with raw strings (`r"..."`) so you don't have to double every backslash in a pattern.

```python
import re

m = re.search(r"ore_(\d+)", "ore_42")
if m:
    print(m.group(1))
```

*Language / Basics*

## Raw Strings

Prefix a string with `r` to keep backslashes literal instead of treating them as escapes, handy for `re` patterns so you don't have to double every backslash. `r"\d+"` is the three characters backslash, `d`, `+`. Combine with `f` for raw f-strings (`rf"..."`), where `{...}` interpolation still works but backslashes stay literal. A backslash still escapes the closing quote, so a raw string can't end in an odd number of backslashes.

```python
import re

# r"..." keeps backslashes literal: no need to double them
m = re.search(r"ore_(\d+)", "ore_42")
print(m.group(1))

label = "iron"
print(rf"\d items of {label}")
```

*Language / Basics*

## Bitwise & Set Operators

The `|`, `&`, `^` operators are polymorphic. On two **sets**: union, intersection, symmetric difference (`{1,2} | {2,3}` → `{1,2,3}`). On two **numbers**: bitwise OR / AND / XOR (`0xF0 & 0x33` → `0x30`). Mixed-type operands raise. Shifts `<<` / `>>` and unary `~` are integer-only. Bitwise math uses Python-style arbitrary-size integers with a safety cap for runaway values, `1 << 61` prints `2305843009213693952`, not a rounded JavaScript number. Augmented forms (`x |= 1`, `x <<= 8`) work on both shapes.

```python
flags = (1 << 8) | 0xFF
masked = flags & 0xF0
toggled = flags ^ 0b1010

a = {1, 2, 3}
b = {2, 3, 4}
print(a | b)  # {1, 2, 3, 4}
print(a & b)  # {2, 3}
```

*Language / Control Flow*

## If / Else

Branch on a condition. A chain is `if`, then any number of `elif` branches, then an optional `else` that catches everything left. The first branch whose condition is true runs, and the rest are skipped, so order the branches from most specific to least. A condition is any expression: a comparison, `and` / `or` / `not`, or a value tested for truth, where `0`, `""`, an empty list or dict, and `None` are all false. Use `x if condition else y` to choose one value inline. Reach for `match` instead when many branches test the same value against fixed shapes.

```python
if temp > 20:
    print("Warm")
elif temp > 0:
    print("Above freezing")
elif temp > -40:
    print("Cold")
else:
    print("Dangerously cold")

status = "warm" if temp > 0 else "cold"
```

*Language / Control Flow*

## While Loop

Repeat a block for as long as its condition is true. The condition is checked before every pass, so something inside the block has to move it toward false or the loop never ends. `break` stops the loop immediately and carries on below it. `continue` skips the rest of this pass and starts the next one. An optional `else:` block runs when the loop ends without a `break`. Loop control belongs to the current function/class-free loop body; a nested helper or class cannot break or continue its caller's loop.

```python
i = 0
while i < 5:
    print(i)
    i = i + 1
```

*Language / Control Flow*

## For Loop

Walk a list, tuple, or range, running the block once per item with the current item bound to a name you choose. `break` stops the loop immediately and carries on below it. `continue` skips the rest of this pass and starts the next one. Tuple targets unpack (`for k, v in d.items():`), and an optional `else:` block runs when the loop ends without a `break`. Loop control belongs to the current function/class-free loop body; a nested helper or class cannot break or continue its caller's loop.

```python
for i in range(5):
    print(i)
```

*Language / Control Flow*

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

## Lists & Tuples

Ordered collections and fixed pairs of values.

```python
readings = [10, 20, 30]
point = (12, 8)
print(point[0])
readings.append(40)
```

*Language / Data Structures*

## Dictionaries

Key-value pairs for named data.

```python
planet = {"name": "Mars", "temp": -63}
print(planet["name"])
```

*Language / Data Structures*

## TypedDict (record shapes)

Use `TypedDict("Name", {...})` for small record-shaped structures: controller state, route records, cached scan rows, or the simple data objects you might otherwise reach for a class/decorator to model. Annotate a variable with it (`state: Name`) and the editor autocompletes keys, flows each field's type through both `state["key"]` and `state.key`, and flags a typo'd key **before you run**. At runtime, `state.mode` and `state["mode"]` are equivalent for a dict containing the ordinary string key `"mode"`; built-in dict method names still resolve as methods. `TypedDict` adds a stable declared shape so the editor can autocomplete and type-check those fields even when the value flows through other code.

The field dictionary is ordinary code that runs, unlike an annotation, so a game type named there has to exist as a value. Import it first (`from __builtins__ import Site`, then `"site": Site`) or write the name in quotes (`"site": "Site"`). Both give identical editor type flow; built-in types such as `str`, `int` and `tuple[float, float]` need neither.

```python
State = TypedDict("State", {
    "mode": str,
    "scans": int,
})

s: State = {"mode": "sonar", "scans": 0}
s.mode           # or s["mode"]: autocompletes; typos flagged
s["scans"] += 1
```

*Language / Data Structures*

## JSON

Import the built-in `json` module to turn a record into text and back. `json.dumps(value)` writes `None`, booleans, numbers, strings, lists, tuples, and dicts with scalar keys, which is exactly the value shape the Signal Bus and the Data Archive accept, so anything that serializes is also something you can send or store. `json.dumps(value, sort_keys=True)` produces the same text for two equal dicts built in a different order, which is what makes it usable as a cache key. `json.loads(text)` reads it back and raises `ValueError` naming the line, column, and character when the text is malformed. A set, a class instance, or a function is refused; convert it first with `dataclasses.asdict()`. Note that a whole number always comes back as an int, because in this language a whole float IS an int.

```python
import json

plan = {"site": "b4", "tons": 12}
text = json.dumps(plan, sort_keys=True)
print(text)
print(json.loads(text)["site"])
```

*Language / Data Structures*

## Priority Queues

Import the built-in `heapq` module to keep an ordinary list arranged so the smallest item is always `heap[0]`. Push with `heapq.heappush(heap, item)` and take the smallest with `heapq.heappop(heap)`, both far cheaper than re-sorting the whole list every tick. Push `(priority, payload)` tuples when you want an explicit priority, since tuples compare by their first element. `heapq.heapify(existing_list)` arranges a list you already have, and `heapq.nsmallest(n, items, key=...)` / `heapq.nlargest(n, items, key=...)` pick the best few without sorting everything. Your own classes work too, as long as they define `__lt__`. Popping an empty heap raises `IndexError`, so check `len(heap)` first.

```python
import heapq

queue = []
heapq.heappush(queue, (2, "refuel"))
heapq.heappush(queue, (1, "rescue"))

while len(queue) > 0:
    priority, job = heapq.heappop(queue)
    print(priority, job)
```

*Language / Functions*

## Functions

Define reusable blocks of code. Parameters can have default values (`def f(x, n=10): ...`), and callers can use either positional args (`f(5, 20)`) or keyword args (`f(5, n=20)`), same as Python. All positional args must come before any keyword args at the call site. Optional type annotations document intent: `def scan(site: MiningSite) -> Site:`. They help the editor with hover and autocomplete, but they do not change how the script runs.

```python
def double(x):
    return x * 2

print(double(5))
```

*Language / Functions*

## Generators (yield)

A `def` that contains `yield` is a generator: calling it returns a lazy iterator that produces one value each time it is asked, instead of building the whole list up front. Loop over it with `for x in gen():`, pull one value with `next(it)` (raises `StopIteration` when spent, or returns a default with `next(it, fallback)`), or materialize it with `list(gen())`. `yield from other()` re-emits every value from another iterable/generator and evaluates to that generator's `return` value. Advanced control: `gen.send(v)` resumes the paused `yield` with `v`, `gen.throw(error)` raises an exception at that yield, and `gen.close()` stops it (running any `finally`). A generator is one-shot: once exhausted it stays empty. Note: a bare generator expression `(x for x in xs)` is now lazy too, so wrap it in `list(...)` if you need a reusable list. Generators live only in the running script and cannot be sent over the Signal Bus or stored in the Data Archive: `list(...)` them first.

```python
def route(points):
    for point in points:
        yield point[0], point[1]

# Values are produced one at a time, on demand:
waypoints = [(10, 4), (14, 9), (20, 12)]
for x, y in route(waypoints):
    print("next", x, y)

# yield from re-emits another iterable's values:
def full_route(near, far):
    yield from route(near)
    yield from route(far)
```

*Language / Functions*

## Caching Results

Decorate a function with `@lru_cache(maxsize=...)` or `@cache` from `functools` and it remembers what it returned for each set of arguments, so a repeat call skips the body. Each script gets a limited number of steps per tick, so this matters when a loop recomputes the same score or distance for the same inputs. Only cache **pure calculations**. Put it on a function that reads a machine and the first reading is frozen forever, which is a bug that looks like the machine stopped changing. Arguments must be hashable, exactly as dict keys are. The wrapped function gains `.cache_info()` and `.cache_clear()`. `maxsize` bounds how many results are kept, dropping the least recently used one first; `@cache` asks for no bound, which the game caps anyway so a script that runs all session cannot grow a cache forever.

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def travel_cost(from_x, from_y, to_x, to_y):
    return sqrt((to_x - from_x) ** 2 + (to_y - from_y) ** 2)

print(travel_cost(0, 0, 3, 4))
print(travel_cost(0, 0, 3, 4))
print(travel_cost.cache_info().hits)
```

*Language / Classes*

## Classes

Bundle data and behavior together. `__init__(self, ...)` sets up each instance (`self.count = 0`), and methods take `self` first. **In a machine script the top-level `self` is the machine; inside a method `self` is the object**, pass the machine in if a method needs to drive it. `__new__(cls, ...)` decides which object a constructor hands back, for singletons and cached instances; `__getattr__(self, name)` answers names the class does not already have; `__init_subclass__(cls)` runs on a base each time a subclass is defined. The editor autocompletes `instance.` members and flows method return types through chains.

```python
class Counter:
    def __init__(self, start):
        self.n = start
    def inc(self):
        self.n += 1

c = Counter(10)
c.inc()
print(c.n)
```

*Language / Classes*

## @dataclass

Import `dataclass` and `field` from `dataclasses` to turn annotated class attributes into declaration-ordered constructor fields. `dataclass` supports `init`, `repr`, `eq`, `order`, and `kw_only`; `field` supports `default`, `default_factory`, `init`, `repr`, `compare`, and `kw_only`. Mutable or otherwise unhashable direct defaults are rejected; use `default_factory` to create a separate value for each instance. Generated behavior includes inherited fields, `__init__`, `__repr__`, exact-class equality, optional ordering, and `__post_init__`. The compatibility spellings `frozen=False`, `unsafe_hash=False`, `slots=False`, and `weakref_slot=False` are accepted, but their `True` behavior is not supported. `match_args` and `ClassVar` / `InitVar` field semantics are unsupported; canonical uses receive a clear error. `asdict`, `astuple`, `fields`, `replace`, `is_dataclass`, the `MISSING` sentinel, and the `Field` records `fields()` returns are all available; `asdict()` is the supported bridge from an instance to a JSON-shaped value. `KW_ONLY`, `FrozenInstanceError`, `make_dataclass`, and public `__dataclass_fields__` introspection are unavailable; annotation types stay erased. A dataclass is still an ordinary user-class instance: use it when a record needs methods, validation, value equality, or ordering. Use `TypedDict` when the value is fundamentally a mapping or must cross a JSON-shaped boundary such as the Signal Bus or notebook APIs.

```python
from dataclasses import dataclass, field

@dataclass(order=True)
class Job:
    priority: int
    label: str = ""
    tags: list[str] = field(default_factory=list, compare=False)

job = Job(2, "ice run")
print(job)
```

*Language / Classes*

## Enumerations (enum)

Import from `enum` to give a fixed set of named constants one type: `class Mode(Enum):` with members such as `IDLE = auto()` and `MINING = auto()`. Each member is a single object with `.name` and `.value`. Compare members with `is` or `==`, look one up by value with `Mode(1)` or by name with `Mode["IDLE"]`, and loop over the class to visit every member in definition order. A plain `Enum` member is not a string, so `mode == "IDLE"` is always `False`: compare with `Mode.IDLE`, or with `mode.name`. In `match`, write `case Mode.IDLE:`, because a bare `case IDLE:` captures every value instead of checking for the member. `IntEnum` and `StrEnum` members are real numbers and strings, so they compare equal to plain values and travel on the Signal Bus and through `json.dumps` as those values; send a plain member's `.name` or `.value` instead. `Flag` and `IntFlag` members combine with `|`, `&`, `^` and `~` into sets of options you test with `in` and loop over. `@unique` refuses aliases and `@verify(...)` checks the values; `_missing_`, `_generate_next_value_`, `_ignore_`, `member()`, `nonmember()`, `@property`, `@global_enum` and the functional form `Enum("Mode", "IDLE MINING")` behave as in Python. Hooks the class calls for you (`_missing_`, `_generate_next_value_`, `__new__`) finish at once, so they cannot `sleep()` or run machine actions. Only `int`, `str` and `float` can be mixed in as a member data type. The editor completes members, knows each member's `name` and `value`, and warns on both mistakes above.

```python
from enum import Enum, IntFlag, auto

class Mode(Enum):
    IDLE = auto()
    MINING = auto()

class Need(IntFlag):
    POWER = auto()
    WATER = auto()

mode = Mode.MINING
match mode:
    case Mode.IDLE:
        print("waiting")
    case Mode.MINING:
        print("digging", mode.name)

needs = Need.POWER | Need.WATER
print(Need.WATER in needs)
```

*Language / Classes*

## Inheritance & super()

`class Dog(Animal):` inherits `Animal`'s methods and attributes. Override any of them, and call the base version with `super().method(...)`. Multiple inheritance resolves by Python's C3 MRO, so cooperative `super()` works across a diamond. `isinstance(x, Animal)` and `issubclass(Dog, Animal)` walk the chain.

```python
class Animal:
    def __init__(self, name):
        self.name = name
    def speak(self):
        return "..."

class Dog(Animal):
    def speak(self):
        return "woof"

print(Dog("Rex").speak())
```

*Language / Classes*

## Custom exceptions

Derive your own exception classes from `Exception` (or any built-in exception) with `class LowBattery(Exception):`. Raise them with `raise LowBattery(level)`, catch them by class with `except LowBattery as err:`, and `except Exception:` still catches them through the hierarchy. An exception object keeps its constructor arguments on `.args` (one message argument makes `str(err)` that message), any extra attributes your `__init__` sets, `.__cause__` from `raise ... from`, and `.__context__` for the exception that was being handled. Override `__str__` to control the console text. The editor autocompletes your exception's members after `except ... as err:` and flags a `raise` or `except` target that is not an exception class.

```python
class LowBattery(Exception):
    def __init__(self, level):
        super().__init__(f"battery at {level}%")
        self.level = level

def check(rover):
    level = rover.battery.percent()
    if level < 20:
        raise LowBattery(level)

try:
    check(get_component("rover_1"))
except LowBattery as err:
    print(err, err.level, err.args)
except Exception as err:
    print("other failure:", err)
```

*Language / Classes*

## Operators & dunder methods

Define what operators and builtins do on your objects. `__eq__` / `__lt__` power `==` and `<`; `__add__` (and reflected `__radd__`) power `+`; `__len__`, `__bool__`, `__getitem__`, `__contains__`, `__iter__`, `__call__`, and `__str__` / `__repr__` dispatch from `len()`, truthiness, `x[k]`, `in`, `for`, calling, and `print`. Operator overloads must be **pure**, they cannot `sleep()` or change game state.

```python
class Vec:
    def __init__(self, x):
        self.x = x
    def __add__(self, o):
        return Vec(self.x + o.x)
    def __eq__(self, o):
        return self.x == o.x
    def __repr__(self):
        return "Vec(" + str(self.x) + ")"

print(Vec(1) + Vec(2))
print(Vec(3) == Vec(3))
```

*Language / Classes*

## Decorators

`@deco` above a `def` or `class` wraps it: `name = deco(name)`. Stack them, and pass arguments (`@deco(arg)`). Built-in method decorators: `@staticmethod` (no `self`), `@classmethod` (receives the class as `cls`), and `@property`. The standard `dataclasses` module provides `@dataclass` for generated record-class behavior.

```python
def trace(fn):
    def wrapper(*args):
        print("calling", fn)
        return fn(*args)
    return wrapper

@trace
def step(n):
    return n * 2

print(step(5))
```

*Language / Classes*

## @property

`@property` turns a method into a computed attribute read **without parens** (`tank.level`, not `tank.level()`). Add `@name.setter` so `tank.level = 42` runs validation. Use it to expose derived or guarded state while keeping plain attribute syntax.

```python
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
t.level = 42
print(t.level)
```

*Components / Core Systems*
