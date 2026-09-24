# Guide: Built-in Functions, Modules & Commands

Built-in runtime functions, modules, and system commands.

---

## System

##### `get_game_version() → str`

Read the current game's build identifier, matching the version at the bottom right of Settings and in feedback reports. Available before boot and from shared Libraries on every platform. Use it to identify an exact build when sharing scripts; build hashes cannot be compared as newer or older versions.

- **Returns** String containing the seven-character commit hash, or `"dev"` in an unstamped development or test environment.

```python
print(get_game_version())
```

##### `boot() → ActionResult`

Initialize the system and run diagnostics.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"booting"` | success | The boot sequence has started. |
| `"already_booted"` | success | The system is already booted. |

```python
boot()
```

##### `activate_power() → ActionResult`

Turn on the power grid after the station has finished booting.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"activating"` | success | Activation has started. |
| `"already_online"` | success | The system is already online. |
| `"boot_required"` | rejection | The station must finish booting before this operation is available. |

```python
activate_power()
```

##### `activate_sensors() → ActionResult`

Bring the sensor array online. Requires power.

- **Returns** `ActionResult`
- **Result fields** `.status`, `.message`
- **Success payload** None

*Outcomes*

| Status | Kind | Meaning |
| --- | --- | --- |
| `"initializing"` | success | Initialization has started. |
| `"already_online"` | success | The system is already online. |
| `"power_required"` | rejection | The operation requires an online power system. |

```python
activate_sensors()
```

##### `get_component(name: str) → Component | None`

Access a player-owned entity by its **immutable id** (e.g. `"solar_3"`, `"outpost_home"`). The id is auto-generated on creation and never changes: use this in scripts that need to outlive renames. To look up by display name (mutable), use `get_component_by_name(name)`. Returns `None` if no entity has the given id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Entity id (machine or outpost) |

- **Returns** Component object

```python
clock = get_component("clock")
time = clock.get_time()
print(time)
```

##### `get_component_by_name(name: str) → Component | None`

Look up any addressable player-owned component (machine or outpost) by its display name. Names default to the entity's id but can be freely renamed from the Computer System tab; uniqueness is enforced across the shared rename namespace. Custom Panels share that namespace but are not components, so they are not returned here. Mutable: `get_component(id)` is the stable form for long-running scripts. Returns `None` if no component has the given name.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | The entity's display name |

- **Returns** Component (machine or outpost), or None if no component by that name exists

```python
ore_bin = get_component_by_name("Iron Stockpile")
print(ore_bin.count("iron_ore"))
```

*Commands*

## Infrastructure

##### `get_pipe(pipe_id: str) → Pipe | None`

Look up an infrastructure pipe by id. Returns a live read-only `Pipe` handle, or `None` if no pipe by that id exists.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pipe_id` | `str` | Pipe id (from `list_pipes()`) |

- **Returns** Live read-only `Pipe` handle or `None`

```python
pipe = get_pipe("pipe_1")
if pipe != None:
    print(pipe.state())
```

##### `list_pipes() → list[Pipe]`

List every infrastructure pipe currently laid (complete or in-progress) as live read-only `Pipe` handles.

- **Returns** List of live read-only `Pipe` handles

```python
for pipe in list_pipes():
    print(pipe.id, pipe.state())
```

*Built-in Functions*

## Built-in Functions

### Output

##### `print(*values: object, sep: str = " ", end: str = "\n") → None`

Output text to the console. Multiple values are joined by `sep` (default a single space). `end` is appended after the last value (default a newline). Console output is a character stream and the newlines in it are what break lines, so `end=""` leaves the line open and the next `print()` continues it: use that to build a row from several calls, then close it with a bare `print()`. Every call updates an unfinished line immediately. Within that row, `\r` returns the write position to the start and `\b` moves it back one visible character. Neither control erases text by itself; following text overwrites existing text. Neither control can enter an earlier row, and ANSI escape sequences are not interpreted.

- **Returns** `None`

##### `warn(*values: object, sep: str = " ", end: str = "\n") → None`

Output an amber warning line to the persistent console. Same argument behavior as `print()`, but routed to the WARNINGS filter. Use it for background monitors that need attention without showing a toast. Use `notify(text, "warn")` when the player should be interrupted.

- **Returns** `None`

##### `debug(*values: object, sep: str = " ", end: str = "\n") → None`

Output low-priority telemetry to the persistent console. Same argument behavior as `print()`, but hidden from the ALL view unless debug output is enabled in console options. Use it for noisy tuning data that should not crowd normal logs.

- **Returns** `None`

##### `notify(text: str, /, level: str = "info", duration_seconds?: float, dismissible: bool = True) → None`

Show a toast to the player and add it to the **Computer → Notifications** archive. Use sparingly: for events that genuinely need the operator's attention (battery critical, contract solved, drone stranded); prefer `print()` for ongoing telemetry. `level` is `"info"` (default), `"warn"`, or `"error"` and drives the toast's color + the history entry's color dot. `duration_seconds` sets how long the toast stays before auto-dismissing: clamped to **0.5-30s**; omitted uses the default (**5s** info/warn, **6s** error). Pass **0** as the duration to make the toast **sticky**: it never auto-dismisses and stays until the player clicks it. Use this for fatal errors that must be acknowledged. `dismissible` defaults to `True`; pass `False` as the fourth argument for a forced-read toast with no early close. A sticky toast is always dismissible, so it can never pin the screen. Identical consecutive notifications from the same script collapse inside a 1-second window, and a sticky already on screen is never duplicated, so a tight loop can't spam the screen.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `text` | `str` | Notification text |
| `level` | `str` | Notification severity |
| `duration_seconds` | `float` | Visible duration in real seconds; 0 is sticky |
| `dismissible` | `bool` | Whether the player may close the toast early |

- **Returns** `None`

### Control

##### `sleep(seconds: float, /) → None`

Wait before continuing. **The argument is in real seconds**, not world-clock hours. The day cycle compresses **24** world-clock hours into a shorter real-time window, so `sleep(25)` is about 1 world-clock hour at the default 10-min-per-day pacing. For planet-aware delays, query the conversion: `sleep(get_component("clock").real_seconds_per_hour() * 2)` waits exactly two world-clock hours regardless of pacing. Loops are paced automatically; `sleep()` is for deliberate delays.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `seconds` | `float` | How long to wait, in seconds; zero or more |

- **Returns** `None`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `sleep(seconds)` requires one numeric duration. |
| `ValueError` | `sleep(seconds)` requires a finite duration greater than or equal to zero. |
| `OverflowError` | `sleep(seconds)` cannot represent the requested duration within the simulation tick range. |

### Utility

##### `len(value: Sized, /) → int`

Length of a list, tuple, string, dict, or set.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `Sized` | String, list, tuple, dict, set, range, or object to measure |

- **Returns** `int`

##### `range(stop: int, /) / range(start: int, stop: int, /) / range(start: int, stop: int, step: int, /) → list[int]`

Materialize the bounded integer range from `start` to `stop` (exclusive), stepping by `step`. `range(5)` → `[0,1,2,3,4]`. Endpoints and steps retain arbitrary-size exact integers, while the produced list must fit the interpreter's collection limit. All arguments must be integers; `step=0` and fractional values are rejected. Negative `step` counts down: `range(5, 0, -1)` → `[5,4,3,2,1]`.

- **Returns** `list[int]`

##### `slice(stop: int | None, /) / slice(start: int | None, stop: int | None, step: int | None = None, /) → slice`

Build a reusable slice object for list, tuple, and string subscripts. `slice(None, None, -1)` is the reusable form of `[::-1]`; `seq[s]` follows the same bounds and step rules as `seq[start:stop:step]`.

- **Returns** `slice`

##### `type(value: object, /) → str`

Returns the player's value-based type category as a string: a user class instance returns its class name, `"int"` covers whole numbers (including exact huge integers), `"float"` covers fractional / non-finite numbers, and built-ins report `"str"`, `"bool"`, `"NoneType"`, `"list"`, `"tuple"`, `"dict"`, `"set"`, or `"slice"`. Game API values retain the established `"object"` category so existing scripts remain unchanged; use `object_type(value)` for a concrete registered data-object name. Numeric categories are based on the current value, not literal spelling, so `type(4.0)` returns `"int"` because the value is whole. Parameter types follow Python instead: a `float` parameter takes any number, an `int` parameter only a whole one.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value whose type name you want |

- **Returns** `str`

##### `object_type(value: object, /) → str`

Return a concrete registered name such as `"MiningSite"`, `"CatalogedFragment"`, or `"Position"` for a game data object without changing the established result of `type(value)`. Component references return `"Component"`; other values use the same public category as `type(value)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value whose concrete game data-object name is needed |

- **Returns** `str`

##### `vars(object: object, /) → dict[str, object]`

Return a detached, shallow dictionary of an object's public data fields. Structured results, positions, journal entries, and other game data values include their documented attribute fields but not methods; class instances include their own stored attributes. Changing the returned dictionary does not change the object, although nested lists and dictionaries are shared. Use `object_type(object)` separately when the concrete registered name is needed. Pass exactly one object; the no-argument local-scope form is not supported.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `object` | `object` | Game API value or class instance to snapshot |

- **Returns** `dict[str, object]`

##### `object() → object`

Construct a new identity-only base object. It takes no arguments and has no writable game-script attributes. User classes inherit from `object` implicitly.

- **Returns** `object`

##### `TypedDict(name: str, fields: dict[str, object], /) → type`

Declare a fixed-key dict shape for the editor. Use the functional form (`State = TypedDict("State", {"mode": str})`) and annotate records with that name (`state: State = {...}`). Runtime treats this as an inert type marker; the editor uses it for key autocomplete, field type flow, and typo lint. The field dictionary is ordinary code, so a game type used as a field type needs its import first (`from __builtins__ import Site`, then `"site": Site`) or the name in quotes (`"site": "Site"`); both give the same editor type flow.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Declared type name |
| `fields` | `dict[str, object]` | Dictionary mapping field names to type expressions. Every value is evaluated, so a game type name must be imported or quoted. |

- **Returns** `type`

##### `hasattr(value: object, name: str, /) → bool`

Return `True` if `value.name` is readable, otherwise `False`. The attribute name must be a string. Useful in duck-typed helpers that accept several documented object shapes, e.g. `hasattr(value, "required_recipe")`. Gameplay result objects keep their fixed fields, so branch on `.status` before reading a documented payload such as `analysis.info`. Missing mounted sub-objects such as `self.sonar` return `False` when the module is not installed.

- **Returns** `bool`

##### `getattr(value: object, name: str, default?: object, /) → object`

Read an attribute by string name, exactly like `value.name`. Without `default`, a missing attribute raises `AttributeError`; with `default`, missing attributes return that fallback. Works for game object properties/methods and built-in methods such as `getattr([1], "append")`. Use with `hasattr()` for duck-typed helpers, not as a replacement for a gameplay result's documented `.status`, `.message`, and payload fields.

- **Returns** `object`

##### `sorted(sequence: Iterable[T], /, *, key: Callable | None = None, reverse: bool = False) → list[T]`

Return a new list sorted using `<` between mutually comparable keys. With `key=None` (the default), each value is its own key. Numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may define the exact rich-comparison slots needed by `<`; unsupported pairs raise. `key=` is called once per item and must be pure: it cannot suspend or mutate game state. `reverse` is truth-tested, and the finite input is handled eagerly within the interpreter's collection limit.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sequence` | `Iterable[T]` | Values to sort |
| `key` | `Callable \| None` | Function returning the value to compare for each item |
| `reverse` | `bool` | `True` to sort from largest to smallest |

- **Returns** `list[T]`

##### `reversed(iterable: Iterable[T], /) → list[T]`

Return a reversed list copy of any finite iterable. This consumes the input fully, so an infinite generator exceeds the collection limit; dictionaries (their keys), sets (deterministic insertion order), generators, and custom iterator-protocol classes are accepted.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Sequence to reverse |

- **Returns** `list[T]`

##### `enumerate(iterable: Iterable[T], /, start: int = 0) → list[tuple[int, T]]`

List of (index, value) pairs. Optional integer `start=N` shifts the index: `enumerate(items, start=1)` for 1-based indexing. Arbitrarily large integer starts remain exact. `start` may be positional or keyword, but not both.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to number |
| `start` | `int` | Number given to the first item |

- **Returns** `list[tuple[int, T]]`

##### `zip(*iterables: Iterable, strict: bool = False) → list[tuple]`

Combine iterables into tuples. With no args, returns empty list. With one arg, returns a list of 1-tuples. Stops at the shortest input unless `strict=True`, which raises if input lengths differ.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable` | Sequences to pair up |
| `strict` | `bool` | `True` to raise when the lengths differ |

- **Returns** `list[tuple]`

##### `isinstance(value: object, type_or_tuple: type | tuple, /) → bool`

Check if a value is of the given type. Accepts a builtin type callable (`object`, `int`, `float`, `str`, `list`, `dict`, `set`, `tuple`, `slice`, `bool`), a string type name, a tuple of types, or a type union like `int | float` (matches any). `int` matches whole numbers and booleans, `float` matches fractional / non-finite numbers, and string `"number"` remains the broad numeric family for scripts that intentionally accept either.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to test |
| `type_or_tuple` | `type \| tuple` | A type, or a tuple of types |

- **Returns** `bool`

##### `callable(value: object, /) → bool`

`True` when a value has a call surface: user-defined `def` / `lambda`, built-in functions, classes, bound methods, and class instances whose type defines `__call__`. Like Python, this checks the type-level call slot without executing its descriptor; an actual call can still raise if that slot resolves to a non-callable value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to test |

- **Returns** `bool`

##### `dir(value: object, /) → list[str]`

Lists the method and attribute names available on `value`, sorted: runtime introspection for discovering what you can do with something. On a component or game object (`dir(self)`, `dir(get_component("smelter_1"))`) it returns that object's callable methods and properties, straight from the console. On a built-in container it returns the type's methods: `dir([1, 2])` → `"append"`, `"pop"`, …; `dir("hi")` → `"upper"`, `"split"`, …. Values with no members (numbers, booleans, `None`) return an empty list. Pass exactly one value: the no-argument `dir()` that lists current-scope names is not supported.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value whose attribute names you want |

- **Returns** `list[str]`

##### `hash(value: object, /) → int`

Hash any hashable value to an integer: strings, numbers, booleans, `None`, tuples of hashable values, functions, classes, and hashable user instances. Instances are identity-hashable by default; defining `__eq__` without `__hash__` makes them unhashable, and a custom `__hash__` controls `hash(obj)`, dict keys, and set membership.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Hashable value |

- **Returns** `int`

##### `super() / super(type: type, object: object, /) → object`

Return a proxy that searches the receiver's MRO after a chosen class. Inside a method, use `super()` for cooperative parent calls such as `super().__init__(...)`. The explicit `super(type, object)` form accepts an instance or subclass of `type`; the one-argument form is not supported.

- **Returns** `object`

##### `issubclass(cls: type, class_or_tuple: type | tuple, /) → bool`

`True` if `cls` is the given class or a subclass of it (or of any class in the tuple), per the MRO. `issubclass(Dog, Animal)` is `True`; every class is a subclass of `object`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `type` | Class to test |
| `class_or_tuple` | `type \| tuple` | A class, or a tuple of classes |

- **Returns** `bool`

##### `property(fget: Callable | None = None, fset: Callable | None = None, fdel: Callable | None = None, doc: str | None = None) → property`

Build a property descriptor. Use `@property` for the common getter form, or call `property(fget, fset, fdel, doc)` directly; every argument is optional and may also be named. Instance reads call `fget`, writes call `fset`, and deletion calls `fdel`; an already-bound hook stays bound and receives the property instance as an additional argument. `.getter(fn)`, `.setter(fn)`, and `.deleter(fn)` return cloned descriptors. An omitted/`None` `doc` follows `fget.__doc__` through normal attribute lookup; an explicit non-`None` doc is preserved by clones.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fget` | `Callable \| None` | Optional instance getter |
| `fset` | `Callable \| None` | Optional instance setter |
| `fdel` | `Callable \| None` | Optional instance deleter |
| `doc` | `str \| None` | Optional explicit descriptor doc value |

- **Returns** `property`

##### `classmethod(func: Callable, /) → Callable`

Wrap a function as a class method. Usually written `@classmethod`; the decorated method receives the class (conventionally `cls`) as its first argument and can be called on the class or an instance.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `Callable` | Function to bind to the class |

- **Returns** `Callable`

##### `staticmethod(func: Callable, /) → Callable`

Wrap a function as a static method. Usually written `@staticmethod`; the decorated method receives neither an instance nor the class and behaves as a plain function namespaced under the class.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `Callable` | Function to store without receiver binding |

- **Returns** `Callable`

##### `NotImplemented: NotImplemented`

The immutable singleton returned by an operator method to ask Python to try reflected dispatch or the normal fallback.

- **Returns** `NotImplemented`

##### `Ellipsis: object`

The immutable singleton also written `...`. As a statement it stands in for a body you have not written yet, and inside a type annotation it means "any number of": `tuple[float, ...]` is a tuple of any length and `Callable[..., Site]` takes any arguments.

- **Returns** `object`

##### `__debug__: bool`

Immutable boolean constant, always `True` in game scripts. It may be read but cannot be assigned or deleted directly.

- **Returns** `bool`

##### `__name__: str`

The name of the module the code runs in: `"__main__"` in the script you run, and the library's name when the code runs because another script imported it. `if __name__ == "__main__":` runs a block only when the file itself is run.

- **Returns** `str`

### Conversion

##### `str(value: object = '', /) → str`

Convert a value to its string form. With no arguments, returns the empty string `''`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to turn into text |

- **Returns** `str`

##### `int(value: str | float = 0, /, base?: int) → int`

Convert to integer. With no args returns `0`. Numbers truncate toward zero. String conversion consumes the whole trimmed value and accepts Python underscore separators and Unicode decimal digits. The optional `base` is 2-36 or `0`; `base=0` detects `0x` / `0b` / `0o` prefixes. Prefix and `base` forms retain arbitrary-size exact integers within the interpreter's integer budget.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `str \| float` | Number, `True`/`False`, or numeric text to convert |
| `base` | `int` | Number base for text, from 2 to 36 |

- **Returns** `int`

##### `float(value: str | float = 0.0, /) → float`

Convert to float. With no arguments, returns `0.0`. String conversion consumes the whole trimmed value and accepts Python decimal/exponent syntax, underscore separators, Unicode decimal digits, and case-insensitive `inf` / `nan`. Trailing garbage raises; booleans coerce to `0.0` / `1.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `str \| float` | Number, `True`/`False`, or numeric text to convert |

- **Returns** `float`

##### `chr(code: int, /) → str`

Character from Unicode code point (e.g. chr(65) → 'A').

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `code` | `int` | Unicode code point |

- **Returns** `str`

##### `ord(char: str, /) → int`

Unicode code point from character (e.g. ord('A') → 65).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `char` | `str` | A single character |

- **Returns** `int`

##### `bool(value?: object, /) → bool`

Convert to boolean (True/False). With no args returns False.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to test for truth |

- **Returns** `bool`

##### `list(iterable?: Iterable[T], /) → list[T]`

Convert any iterable to a list, or create an empty list with `list()`. Methods: `.append(x)`, `.pop([i])`, `.insert(i, x)`, `.remove(x)`, `.index(x [, start [, end]])`, `.count(x)`, `.sort()`, `.reverse()`, `.copy()`, `.extend(iter)`, `.clear()`, `.length` (property). Subscript with `lst[i]` and slice with `lst[start:end:step]`. See individual entries below for full Python-compliant semantics.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to copy into a new list |

- **Returns** `list[T]`

##### `dict(**kwargs: V) / dict(source: dict[K, V] | Iterable[tuple[K, V]], /, **kwargs: V) → dict[K, V]`

Build a dictionary. Empty form `dict()`. From pairs: `dict([("a", 1), ("b", 2)])`. Shallow-copy another dict: `dict(d)`. Keyword form: `dict(name="Mars", temp=-63)`. Keys may be any hashable value, including tuples of hashables and properly hashable user instances. Methods: `.keys()`, `.values()`, `.items()`, `.has(k)`, `.get(k, default?)`, `.pop(k, default?)`, `.popitem()`, `.setdefault(k, default?)`, `.update(other)`, `.copy()`, `.clear()`, `.length` (property). Operators: `a | b` returns a merged copy with right-hand values winning; `a |= b` updates `a` in place. Subscript with `d[k]`; missing key raises. Use `.get(k)` or `.has(k)` for safe lookup.

- **Returns** `dict[K, V]`

##### `set(iterable?: Iterable[T], /) → set[T]`

Build a set of unique members from any iterable, or `set()` for empty. Members may be any hashable values, including tuples of hashables and properly hashable user instances. Use `{1, 2, 3}` for a literal: empty `{}` is a dict, not a set, so empty set is always `set()`. Methods: `.add(x)`, `.remove(x)`, `.discard(x)`, `.pop()`, `.clear()`, `.copy()`, `.union(s)`, `.intersection(s)`, `.difference(s)`, `.symmetric_difference(s)`, `.update(s)`, `.issubset(s)`, `.issuperset(s)`, `.isdisjoint(s)`. Operators: `in`, `|` (union), `&` (intersection), `-` (difference), `^` (symmetric difference), `<` `<=` `>=` `>` (subset/superset), `==`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to copy into a new set |

- **Returns** `set[T]`

##### `tuple(iterable?: Iterable[T], /) → tuple[T, ...]`

Build a tuple from any iterable, or `tuple()` for empty. Tuples are like lists but immutable (no `append` / `pop` / `sort`): useful for fixed records and as hashable keys. Methods: `.index(x)`, `.count(x)`, `.length` (property). Subscript and slice with `t[i]` / `t[a:b]` just like lists.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to copy into a new tuple |

- **Returns** `tuple[T, ...]`

##### `hex(integer: int, /) → str`

Render an integer as a Python-style hex string with `0x` prefix. `hex(255)` → `'0xff'`, `hex(-16)` → `'-0x10'`. Floats reject.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `integer` | `int` | Whole number to convert |

- **Returns** `str`

##### `bin(integer: int, /) → str`

Render an integer as a binary string with `0b` prefix. `bin(10)` → `'0b1010'`. Floats reject.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `integer` | `int` | Whole number to convert |

- **Returns** `str`

##### `oct(integer: int, /) → str`

Render an integer as an octal string with `0o` prefix. `oct(8)` → `'0o10'`. Floats reject.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `integer` | `int` | Whole number to convert |

- **Returns** `str`

##### `repr(value: object, /) → str`

Developer-readable string for a value, with quotes around strings and nested-repr for containers. `repr([1, "a"])` → `"[1, 'a']"` (note the quotes around `'a'`). Use when you want to see the value's structure, not its display form. Also reached via f-string `!r` conversion: `f"{name!r}"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to describe |

- **Returns** `str`

### Functional

##### `total_ordering(cls: type, /) → type`

Class decorator that preserves the class object and fills missing ordering methods from `__eq__` plus one of `__lt__`, `__le__`, `__gt__`, or `__ge__`. Explicit methods are never replaced. Applying it mutates the local class namespace.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `type` | Class to complete |

- **Returns** `type`

##### `wraps(wrapped: Callable, /) → Callable`

Return a decorator that preserves the wrapped callable's supported name, qualified name, docstring, custom attributes, and `__wrapped__` link while keeping the wrapper's call behavior. Applying the returned decorator mutates only that local wrapper function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `wrapped` | `Callable` | Callable whose metadata should be copied |

- **Returns** `Callable`

### Math

##### `abs(number: float, /) → float`

Absolute value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number whose distance from zero you want |

- **Returns** `float`

##### `isclose(a: float, b: float, rel_tol: float = 0.000000001, abs_tol: float = 0.0) → bool`

Return `True` when two numbers are close enough to treat as equal. `rel_tol` scales with the compared values; `abs_tol` sets a fixed accepted difference in the same unit, useful for values near zero and physical readings such as coordinates. Tolerances must be non-negative. This is the directly available equivalent of Python's `math.isclose()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `float` | First number |
| `b` | `float` | Second number |
| `rel_tol` | `float` | Maximum relative difference |
| `abs_tol` | `float` | Maximum absolute difference in the values' unit |

- **Returns** `bool`

##### `min(iterable: Iterable[T], /, *, key: Callable | None = None, default?: object) / min(a: T, b: T, /, *args: T, key: Callable | None = None) → T`

Return the selected original value whose key is smallest under `<`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `<`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.

- **Returns** `T`

##### `max(iterable: Iterable[T], /, *, key: Callable | None = None, default?: object) / max(a: T, b: T, /, *args: T, key: Callable | None = None) → T`

Return the selected original value whose key is largest under `>`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `>`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.

- **Returns** `T`

##### `round(number: float, ndigits: int | None = None) → float`

Round with ties to even. Without `ndigits` (or with `None`), returns the nearest whole value and rejects NaN/infinity. Integer and boolean inputs remain exact; negative `ndigits` rounds exact integers in decimal. Both arguments accept keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value to round |
| `ndigits` | `int \| None` | Decimal digits or None |

- **Returns** `float`

##### `pow(base: float, exp: float, mod: int | None = None) → float`

`base` raised to `exp`. Optional `mod` performs exact modular exponentiation and accepts negative exponents when the base has a modular inverse. `base`, `exp`, and `mod` accept positional or keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `base` | `float` | Base value |
| `exp` | `float` | Exponent |
| `mod` | `int \| None` | Optional integer modulus |

- **Returns** `float`

##### `random() → float`

Random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.random()` after `import random`.

- **Returns** `float`

##### `rand() → float`

Short alias for `random()`: a random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.rand()` after `import random`.

- **Returns** `float`

##### `randint(min: int, max: int, /) → int`

Random integer `N` where `min <= N <= max`. Bounds are inclusive and must be whole numbers. Each successful run begins a new automatic sequence. Useful with `planet.get_bounds()` for random valid coordinates. Also available as `random.randint(min, max)` after `import random`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `min` | `int` | Smallest possible result |
| `max` | `int` | Largest possible result |

- **Returns** `int`

##### `sqrt(number: float, /) → float`

Square root. Errors on negative input.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number zero or greater |

- **Returns** `float`

##### `floor(number: float, /) → int`

Round down to the nearest integer.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to round down |

- **Returns** `int`

##### `ceil(number: float, /) → int`

Round up to the nearest integer.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to round up |

- **Returns** `int`

##### `trunc(number: float, /) → int`

Drop the fractional part (round toward zero).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to cut toward zero |

- **Returns** `int`

##### `divmod(a: float, b: float, /) → tuple[float, ...]`

Divides `a` by `b` and returns two values: the quotient rounded down, and the remainder left over. For example, `divmod(19, 2)` returns `(9, 1)` because 2 fits into 19 nine times with 1 left over.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `float` | Number to divide |
| `b` | `float` | Number to divide by |

- **Returns** `tuple[float, ...]`

##### `sign(number: float, /) → int`

Returns `-1`, `0`, or `1` for negative, zero, or positive input.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to test |

- **Returns** `int`

##### `exp(number: float, /) → float`

`e` raised to the power of the argument.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Power of e to compute |

- **Returns** `float`

##### `log(number: float, base?: float, /) → float`

Natural log, or log with the given base.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |
| `base` | `float` | Logarithm base; the natural logarithm when omitted |

- **Returns** `float`

##### `log2(number: float, /) → float`

Base-2 logarithm.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |

- **Returns** `float`

##### `log10(number: float, /) → float`

Base-10 logarithm.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |

- **Returns** `float`

##### `sin(radians: float, /) → float`

Sine of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `cos(radians: float, /) → float`

Cosine of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `tan(radians: float, /) → float`

Tangent of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `asin(number: float, /) → float`

Arc sine. Input must be in `-1 to 1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value from -1 to 1 |

- **Returns** `float`

##### `acos(number: float, /) → float`

Arc cosine. Input must be in `-1 to 1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value from -1 to 1 |

- **Returns** `float`

##### `atan(number: float, /) → float`

Arc tangent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Tangent value |

- **Returns** `float`

##### `atan2(y: float, x: float, /) → float`

Arc tangent of `y/x`, correctly choosing the quadrant.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `y` | `float` | Vertical component |
| `x` | `float` | Horizontal component |

- **Returns** `float`

##### `degrees(radians: float, /) → float`

Convert radians to degrees.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `radians(degrees: float, /) → float`

Convert degrees to radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `degrees` | `float` | Angle in degrees |

- **Returns** `float`

##### `sum(iterable: Iterable[float] | Iterable[list], /, start: float | list = 0) → float | list`

Sum of every numeric item in an iterable. Optional `start` (number or list): `sum(list_of_lists, [])` flattens. `start` may be positional or keyword, but not both.

- **Returns** `float | list`

##### `prod(iterable: Iterable[float], /, start: float = 1) → float`

Product of every numeric item in an iterable. Empty iterables return `start`. `start` may be positional or keyword, but not both.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Numbers to multiply |
| `start` | `float` | Value the product starts from |

- **Returns** `float`

##### `inf: float`

Positive infinity, larger than every finite number. Use `-inf` for negative infinity, including as an initial best or worst value in search and pathfinding algorithms.

- **Returns** `float`

##### `pi: float`

Mathematical constant `π ≈ 3.14159`.

- **Returns** `float`

##### `tau: float`

Mathematical constant `τ = 2π`.

- **Returns** `float`

### Logic

##### `all(iterable: Iterable, /) → bool`

True if every item in the iterable is truthy. Stops at the first falsy item, so generators are consumed only as far as needed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable` | Values to test |

- **Returns** `bool`

##### `any(iterable: Iterable, /) → bool`

True if any item in the iterable is truthy. Stops at the first truthy item, so generators are consumed only as far as needed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable` | Values to test |

- **Returns** `bool`

### Iteration

##### `iter(iterable: Iterable[T], /) → list | generator`

Return an iterator. Built-in iterables use a compatibility list-shaped iterator; protocol iterators and generators keep their identity, so `iter(iterator) is iterator`. `for` advances generators and custom iterators one item at a time, so it can break out of an infinite iterator. Consumers that must finish, such as `list(...)`, remain bounded.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to iterate |

- **Returns** `list | generator`

##### `next(iterator: Iterator[T], default?: object, /) → T`

Advance an iterator by one item. Iterators returned by `iter()` and custom `__next__` iterators retain their cursor across calls. Ordinary lists keep the compatibility behavior of popping the front; other non-iterator iterables return their first materialized item. Exhaustion raises `StopIteration` unless `default` is given.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterator` | `Iterator[T]` | Iterator to advance |
| `default` | `object` | Returned instead of raising `StopIteration` once the iterator is exhausted |

- **Returns** `T`

##### `pairwise(iterable: Iterable[T], /) → list[tuple[T, T]]`

Return neighboring pairs from an iterable. `pairwise([1,2,3])` → `[(1,2), (2,3)]`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Sequence to walk in neighbouring pairs |

- **Returns** `list[tuple[T, T]]`

##### `batched(iterable: Iterable[T], size: int, /) → list[tuple[T, ...]]`

Split an iterable into tuple batches of `size`. The final batch may be shorter. `batched([1,2,3,4,5], 2)` → `[(1,2), (3,4), (5,)]`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to group |
| `size` | `int` | Items per batch; 1 or more |

- **Returns** `list[tuple[T, ...]]`

##### `starmap(fn: Callable, iterable: Iterable, /) → list`

Call pure `fn` with each tuple/list item unpacked as arguments. The callback cannot suspend the script or mutate game state. `starmap(pow, [(2,3), (3,2)])` → `[8,9]`. An empty input never inspects or calls `fn`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable` | Function called with each item unpacked as its arguments |
| `iterable` | `Iterable` | Tuples or lists of arguments |

- **Returns** `list`

##### `flatten(iterable: Iterable, /) → list`

Flatten one level of nested iterables into a list. `flatten([[1,2], (3,4)])` → `[1,2,3,4]`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable` | Sequence of sequences to flatten one level |

- **Returns** `list`

##### `count_by(iterable: Iterable, key_fn?: Callable, /) → dict[object, int]`

Count items into a dict. Without `key_fn` (or with `None`), counts each item. With a pure `key_fn`, counts the computed key; callbacks cannot suspend the script or mutate game state: `count_by(items, lambda x: x.kind)`. An empty input never inspects or calls the key function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable` | Values to count |
| `key_fn` | `Callable` | Optional function that maps each item to the key to count |

- **Returns** `dict[object, int]`

##### `chain(*iterables: Iterable[T]) → list[T]`

Flattens any number of iterables into one list, in order. `chain([1,2], [3,4])` → `[1,2,3,4]`. Accepts lists, tuples, strings, sets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable[T]` | Sequences to join end to end |

- **Returns** `list[T]`

##### `accumulate(iterable: Iterable[float], /) → list[float]`

Running prefix sum over any finite iterable. `accumulate([1,2,3,4])` → `[1,3,6,10]`. Numeric items only; booleans participate as integers and arbitrarily large integers remain exact.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Numbers to total as you go |

- **Returns** `list[float]`

##### `combinations(iterable: Iterable[T], k: int, /) → list[tuple[T, ...]]`

All `k`-element combinations from an iterable, in input order, no repeats. Returns a list of tuples. `combinations([1,2,3], 2)` → `[(1,2), (1,3), (2,3)]`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to choose from |
| `k` | `int` | How many to choose |

- **Returns** `list[tuple[T, ...]]`

##### `permutations(iterable: Iterable[T], k?: int, /) → list[tuple[T, ...]]`

All `k`-length ordered arrangements from an iterable. `k` defaults to the full length. `permutations([1,2,3])` → all 6 orderings as tuples.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to arrange |
| `k` | `int` | How many to arrange; all of them when omitted |

- **Returns** `list[tuple[T, ...]]`

##### `product(*iterables: Iterable, repeat: int = 1) → list[tuple]`

Cartesian product. `product([0,1], [0,1])` → `[(0,0), (0,1), (1,0), (1,1)]`. Each input must be iterable; result is a list of tuples. Optional keyword `repeat=N` repeats the input pools, matching `itertools.product([0,1], repeat=2)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable` | Sequences to combine |
| `repeat` | `int` | How many times to repeat the sequences |

- **Returns** `list[tuple]`

##### `map(fn: Callable, iter1: Iterable, iter2?: Iterable, ..., /, strict: bool = False) → list`

Apply pure `fn` to corresponding items of each iterable. Callbacks cannot suspend the script or mutate game state. Single-iter form calls `fn(x)`; multi-iter form calls `fn(x, y, ...)` and stops at the shortest input unless `strict=True`, which raises if input lengths differ. If no row is produced, `fn` is never inspected or called.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable` | Function called with one item from each sequence |
| `iter1` | `Iterable` | First sequence |
| `iter2` | `Iterable` | Second sequence, and any further ones |
| `strict` | `bool` | `True` to raise when the lengths differ |

- **Returns** `list`

##### `filter(fn: Callable | None, iterable: Iterable[T], /) → list[T]`

Keep items for which pure `fn(item)` is truthy; callbacks cannot suspend the script or mutate game state. `filter(None, iter)` keeps every truthy item without a callback. An empty input never inspects or calls `fn`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable \| None` | Function returning `True` for items to keep, or `None` to keep truthy items |
| `iterable` | `Iterable[T]` | Values to filter |

- **Returns** `list[T]`

##### `reduce(fn: Callable, iterable: Iterable[T], initializer?: object, /) → object`

Combine an iterable into one value by repeatedly calling pure `fn(total, item)`; callbacks cannot suspend the script or mutate game state. With no initializer, the first item becomes the initial total; empty iterables then raise. Empty-with-initializer and singleton-without-initializer perform no callback call. Also available as `from functools import reduce`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable` | Function combining the running value with the next item |
| `iterable` | `Iterable[T]` | Values to combine |
| `initializer` | `object` | Starting value |

- **Returns** `object`

### Exceptions

##### `BaseException(*args: object) → BaseException`

Root of the supported exception hierarchy.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `BaseException`

##### `BaseException.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `BaseException.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `BaseException.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `BaseException.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `Exception(*args: object) → Exception`

Base class matched by ordinary `except Exception:` handlers.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `Exception`

##### `Exception.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `Exception.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `Exception.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `Exception.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ArithmeticError(*args: object) → ArithmeticError`

Base class for numeric calculation failures.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ArithmeticError`

##### `ArithmeticError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ArithmeticError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ArithmeticError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ArithmeticError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ValueError(*args: object) → ValueError`

A value has the right type but an invalid value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ValueError`

##### `ValueError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ValueError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ValueError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ValueError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `TypeError(*args: object) → TypeError`

An operation received a value of an inappropriate type.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `TypeError`

##### `TypeError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `TypeError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `TypeError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `TypeError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `PermissionError(*args: object) → PermissionError`

An operation is prohibited by the caller's ownership or access contract.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `PermissionError`

##### `PermissionError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `PermissionError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `PermissionError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `PermissionError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ReferenceError(*args: object) → ReferenceError`

A captured component or module handle is no longer valid.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ReferenceError`

##### `ReferenceError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ReferenceError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ReferenceError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ReferenceError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `LookupError(*args: object) → LookupError`

Base class for invalid mapping keys and sequence indexes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `LookupError`

##### `LookupError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `LookupError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `LookupError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `LookupError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `KeyError(*args: object) → KeyError`

A dictionary key is not present.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `KeyError`

##### `KeyError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `KeyError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `KeyError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `KeyError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `IndexError(*args: object) → IndexError`

A sequence index is out of range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `IndexError`

##### `IndexError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `IndexError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `IndexError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `IndexError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `AttributeError(*args: object) → AttributeError`

An attribute reference failed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `AttributeError`

##### `AttributeError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `AttributeError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `AttributeError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `AttributeError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `RuntimeError(*args: object) → RuntimeError`

A runtime failure does not fit a more specific category.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `RuntimeError`

##### `RuntimeError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `RuntimeError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `RuntimeError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `RuntimeError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `NotImplementedError(*args: object) → NotImplementedError`

A required operation or override is not implemented.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `NotImplementedError`

##### `NotImplementedError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `NotImplementedError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `NotImplementedError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `NotImplementedError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `RecursionError(*args: object) → RecursionError`

The interpreter's call-depth limit was exceeded.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `RecursionError`

##### `RecursionError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `RecursionError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `RecursionError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `RecursionError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `NameError(*args: object) → NameError`

A local, free, or global name could not be resolved.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `NameError`

##### `NameError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `NameError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `NameError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `NameError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `UnboundLocalError(*args: object) → UnboundLocalError`

A statically local name was read before it was bound; this is a `NameError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `UnboundLocalError`

##### `UnboundLocalError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `UnboundLocalError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `UnboundLocalError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `UnboundLocalError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ImportError(*args: object) → ImportError`

An import could not provide the requested binding.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ImportError`

##### `ImportError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ImportError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ImportError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ImportError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ModuleNotFoundError(*args: object) → ModuleNotFoundError`

An imported module could not be found; this is an `ImportError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ModuleNotFoundError`

##### `ModuleNotFoundError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ModuleNotFoundError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ModuleNotFoundError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ModuleNotFoundError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `OverflowError(*args: object) → OverflowError`

A numeric conversion or bounded allocation exceeded its supported range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `OverflowError`

##### `OverflowError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `OverflowError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `OverflowError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `OverflowError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `ZeroDivisionError(*args: object) → ZeroDivisionError`

Division or modulo used a zero divisor.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `ZeroDivisionError`

##### `ZeroDivisionError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `ZeroDivisionError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `ZeroDivisionError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `ZeroDivisionError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `StopIteration(*args: object) → StopIteration`

An iterator was exhausted. Its `.value` contains a generator's return value, or `None`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `StopIteration`

##### `StopIteration.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `StopIteration.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `StopIteration.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `StopIteration.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `StopIteration.value: object`

The return value carried by a completed generator, or `None`.

- **Returns** `object`

##### `GeneratorExit(*args: object) → GeneratorExit`

Raised inside a generator when `close()` asks it to stop. It derives directly from `BaseException`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `GeneratorExit`

##### `GeneratorExit.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `GeneratorExit.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `GeneratorExit.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `GeneratorExit.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `AssertionError(*args: object) → AssertionError`

An `assert` statement failed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `AssertionError`

##### `AssertionError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `AssertionError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `AssertionError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `AssertionError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `SyntaxError(*args: object) → SyntaxError`

Source could not be compiled.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `SyntaxError`

##### `SyntaxError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `SyntaxError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `SyntaxError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `SyntaxError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

##### `IndentationError(*args: object) → IndentationError`

Source indentation is inconsistent; this is a `SyntaxError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Exception arguments, usually one message. They are stored on `.args`; keyword arguments are rejected. |

- **Returns** `IndentationError`

##### `IndentationError.args: tuple`

The tuple of arguments the exception was created with. One message argument makes `str(error)` that message.

- **Returns** `tuple`

##### `IndentationError.__cause__: BaseException | None`

The exception named by `raise ... from cause`, or `None`.

- **Returns** `BaseException | None`

##### `IndentationError.__context__: BaseException | None`

The exception that was being handled when this one was raised, or `None`.

- **Returns** `BaseException | None`

##### `IndentationError.__suppress_context__: bool`

`True` after `raise ... from ...` (including `from None`), which marks the implicit context as deliberately replaced.

- **Returns** `bool`

*Built-in Functions*

## Argument Types

The types parameters and results are written in. Most are ordinary Python types (`str`, `int`, `float`, `bool`, `list[str]`, `dict[str, int]`) and game types such as `Site`. The names below cover the rest: shapes several calls accept, and the Python words for 'any value' and 'anything a loop can walk'.

##### `JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]`

Any value the Signal Bus, the Data Archive and `json` can carry: text, a number, `True` or `False`, `None`, or a list or dict of those, with string keys.

##### `ItemProperties = dict[str, JsonValue]`

The properties of one item, as `ItemStack.properties` returns them: a dict from property name to a `JsonValue`.

##### `IdRecord`

A dict or an object with a string `id`, such as a `Site`, a record saved with `vars()`, or an instance of your own class. Only `id` is read; other fields are ignored.

##### `TransmissionRecord`

A `SignalTransmission`, or a dict or object with the same fields: string `event_id`, `channel` and `data`, and whole-number `number` and `total`.

##### `SiteRef = str | Site | IdRecord`

A site to act on: its id, a `Site` from `scan()`, or an `IdRecord` carrying the site's id.

##### `RecipeRef = str | Recipe | IdRecord`

A recipe to select: its id, a `Recipe`, or an `IdRecord` carrying the recipe's id.

##### `object`

Any value at all.

##### `Callable`

Something you can call: a function, a lambda, a method, or a class.

##### `Iterable`

Anything a `for` loop can walk: a list, tuple, set, dict, string, range, or generator. `Iterable[str]` means one whose items are strings.

##### `Iterator`

An iterable that hands out one item per `next()` call, such as the result of `iter()` or a generator.

##### `Sized`

Anything `len()` accepts: a string, list, tuple, dict, set, range, or a class with `__len__`.

##### `T`

The item type of the container on this page: in `list[T]`, `T` is whatever the list holds. `K` and `V` are a dict's key and value types. Hover shows the real type when the editor knows it.

*Built-in Modules*

## random

Built-in random-number helpers. Each successful run gets a new automatic sequence; use random.seed(value) when you want a reproducible sequence. Works without Shared Library research.

##### `random.random() → float`

Random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.random()` after `import random`.

- **Returns** `float`

##### `random.rand() → float`

Short alias for `random()`: a random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.rand()` after `import random`.

- **Returns** `float`

##### `random.randint(min: int, max: int, /) → int`

Random integer `N` where `min <= N <= max`. Bounds are inclusive and must be whole numbers. Each successful run begins a new automatic sequence. Useful with `planet.get_bounds()` for random valid coordinates. Also available as `random.randint(min, max)` after `import random`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `min` | `int` | Smallest possible result |
| `max` | `int` | Largest possible result |

- **Returns** `int`

##### `random.seed(a: int | float | str | bool | None = None) → None`

Initialize random-number generation. Omit `a` or pass `None` to select another automatic sequence. Pass a number, boolean, or string to make later draws reproducible; the same value produces the same sequence.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `int \| float \| str \| bool \| None` | Optional number, boolean, string, or None seed |

- **Returns** `None`

*Built-in Modules*

## functools

Built-in functional helpers. Works without Shared Library research.

##### `functools.reduce(fn: Callable, iterable: Iterable[T], initializer?: object, /) → object`

Combine an iterable into one value by repeatedly calling pure `fn(total, item)`; callbacks cannot suspend the script or mutate game state. With no initializer, the first item becomes the initial total; empty iterables then raise. Empty-with-initializer and singleton-without-initializer perform no callback call. Also available as `from functools import reduce`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable` | Function combining the running value with the next item |
| `iterable` | `Iterable[T]` | Values to combine |
| `initializer` | `object` | Starting value |

- **Returns** `object`

##### `functools.total_ordering(cls: type, /) → type`

Class decorator that preserves the class object and fills missing ordering methods from `__eq__` plus one of `__lt__`, `__le__`, `__gt__`, or `__ge__`. Explicit methods are never replaced. Applying it mutates the local class namespace.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `type` | Class to complete |

- **Returns** `type`

##### `functools.wraps(wrapped: Callable, /) → Callable`

Return a decorator that preserves the wrapped callable's supported name, qualified name, docstring, custom attributes, and `__wrapped__` link while keeping the wrapper's call behavior. Applying the returned decorator mutates only that local wrapper function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `wrapped` | `Callable` | Callable whose metadata should be copied |

- **Returns** `Callable`

##### `functools.partial(func: Callable, /, *args: object, **keywords: object) → Callable`

Return a new callable that calls `func` with some arguments already filled in. `partial(move, rover)` is a one-argument function; later positional arguments follow the bound ones and later keywords replace bound keywords of the same name. The result carries `.func`, `.args` and `.keywords`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `Callable` | Function to bind arguments to |
| `*args` | `object` | Positional arguments to bind now; arguments passed later follow them |
| `**keywords` | `object` | Keyword arguments to bind now; a keyword passed later replaces the bound one |

- **Returns** `Callable`

##### `functools.lru_cache(maxsize: int | Callable | None = 128, typed: bool = False) → Callable`

Decorator that remembers what the function returned for each set of arguments, so a repeat call returns the stored value instead of running the body. Use it on pure calculations that a loop repeats, never on a function that reads the world. A cached reading is frozen at the first call and will not follow the machine. The wrapped function gains `.cache_clear()` and `.cache_info()`. Arguments must be hashable, exactly as dict keys are.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `maxsize` | `int \| Callable \| None` | How many results to keep, **128** by default. Past that the least recently used one is dropped. `None` asks for no limit, which this game caps anyway so a script that runs all session cannot grow a cache forever. A function here, `lru_cache(f)`, wraps it with the default size |
| `typed` | `bool` | Treat arguments of different types as different keys, so `f(1)` and `f(1.5)` never share a result |

- **Returns** `Callable`

##### `functools.cache(user_function: Callable, /) → Callable`

Decorator that remembers every result, the same as `lru_cache(maxsize=None)`. The same warning applies: cache calculations, never world readings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `user_function` | `Callable` | Function to memoize |

- **Returns** `Callable`

*Built-in Modules*

## re

Built-in regular-expression helpers. Works without Shared Library research. Patterns use a linear-time safe regular expression subset.

##### `re.IGNORECASE: int`

Case-insensitive matching flag. Short alias: `re.I`.

- **Returns** `int`

##### `re.MULTILINE: int`

`^` and `$` also match line boundaries. Short alias: `re.M`.

- **Returns** `int`

##### `re.DOTALL: int`

`.` also matches newline characters. Short alias: `re.S`.

- **Returns** `int`

##### `re.I: int`

Short alias for `re.IGNORECASE`.

- **Returns** `int`

##### `re.M: int`

Short alias for `re.MULTILINE`.

- **Returns** `int`

##### `re.S: int`

Short alias for `re.DOTALL`.

- **Returns** `int`

##### `re.search(pattern: str, string: str, flags: int = 0) → Match | None`

Search anywhere in `string` for `pattern`. Returns a `Match` object, or `None` if there is no match. Patterns use the documented safe regular expression subset.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `string` | `str` | String to search |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.match(pattern: str, string: str, flags: int = 0) → Match | None`

Match `pattern` at the start of `string`. Returns a `Match` object, or `None` if the start does not match.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `string` | `str` | String to check |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.fullmatch(pattern: str, string: str, flags: int = 0) → Match | None`

Match the whole `string` against `pattern`. Returns a `Match` object, or `None` if any part is left unmatched.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `string` | `str` | String to check |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.findall(pattern: str, string: str, flags: int = 0) → list`

Return all non-overlapping matches. With no capture groups, the result is a list of matched strings. With one capture group, the result is that group. With multiple capture groups, the result is tuples.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `string` | `str` | String to search |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

##### `re.sub(pattern: str, repl: str, string: str, count: int = 0, flags: int = 0) → str`

Replace matches of `pattern` in `string` with `repl`. `count=0` replaces all matches; a positive count limits replacements. Replacement text supports numeric backreferences like `\1` and `\g<1>`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `repl` | `str` | Replacement text |
| `string` | `str` | String to transform |
| `count` | `int` | Maximum replacements; 0 means all |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `str`

##### `re.split(pattern: str, string: str, maxsplit: int = 0, flags: int = 0) → list`

Split `string` wherever `pattern` matches. `maxsplit=0` means no limit. Capturing groups are included in the output, matching Python's `re.split` behavior.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Regular expression pattern |
| `string` | `str` | String to split |
| `maxsplit` | `int` | Maximum splits; 0 means all |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

*Built-in Modules*

## dataclasses

Built-in record-class helpers. Works without Shared Library research. Generates concise user-class value objects; use TypedDict for JSON-shaped records.

##### `dataclasses.MISSING: object`

Sentinel telling a field with no default apart from one that defaults to `None`. Test it with `field.default is MISSING`.

- **Returns** `object`

##### `dataclasses.dataclass(cls?: type | None, /, *, init: bool = True, repr: bool = True, eq: bool = True, order: bool = False, kw_only: bool = False, unsafe_hash: bool = False, frozen: bool = False, slots: bool = False, weakref_slot: bool = False) → type`

Decorate a class to generate declaration-ordered construction, representation, value equality, and optional ordering. Supports both `@dataclass` and `@dataclass(...)`, inherited fields, `__post_init__`, and explicit-method preservation. Generated behavior is controlled by `init`, `repr`, `eq`, `order`, and `kw_only`. Compatibility flags `unsafe_hash`, `frozen`, `slots`, and `weakref_slot` may be passed only as `False`; their `True` behavior and every unlisted standard-library option are rejected rather than ignored. Dataclass instances remain ordinary user objects and cannot cross JSON-shaped game API boundaries.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `type \| None` | Optional class for functional or bare-decorator use |
| `init` | `bool` | Generate __init__ (default True) |
| `repr` | `bool` | Generate __repr__ (default True) |
| `eq` | `bool` | Generate exact-class __eq__ (default True) |
| `order` | `bool` | Generate ordering methods (default False) |
| `kw_only` | `bool` | Make generated constructor fields keyword-only (default False) |
| `unsafe_hash` | `bool` | Compatibility flag; only False is supported |
| `frozen` | `bool` | Compatibility flag; only False is supported |
| `slots` | `bool` | Compatibility flag; only False is supported |
| `weakref_slot` | `bool` | Compatibility flag; only False is supported |

- **Returns** `type`

##### `dataclasses.field(*, default?: object, default_factory?: Callable, init: bool = True, repr: bool = True, compare: bool = True, kw_only?: bool) → object`

Configure one annotated dataclass field. Use `default` for an immutable or hashable shared value, or `default_factory` for a zero-argument factory that creates an independent value per instance; supplying both is an error. Mutable or otherwise unhashable direct defaults are rejected and must use `default_factory`. `init` controls constructor inclusion, `repr` controls generated display, `compare` controls equality and ordering, and `kw_only` controls that field's constructor position. Field metadata/introspection, `hash`, and every unlisted standard-library option are not supported.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `object` | Optional immutable or hashable shared value; mutable or unhashable values must use default_factory |
| `default_factory` | `Callable` | Optional zero-argument factory |
| `init` | `bool` | Include this field in the generated constructor (default True) |
| `repr` | `bool` | Include this field in generated representation (default True) |
| `compare` | `bool` | Include this field in generated equality and ordering (default True) |
| `kw_only` | `bool` | Make this constructor field keyword-only |

- **Returns** `object`

##### `dataclasses.asdict(obj: object, /) → dict[str, JsonValue]`

Return a record-class instance as a dict, recursing into nested record classes, lists, tuples, dicts and sets. Dict keys are converted too, so a record class used as a key raises `TypeError` here rather than surviving into a result that cannot be sent. This is the bridge out of a class: the result is accepted by `json.dumps()`, `comms.send()` and the Data Archive, which all refuse a class instance. Values that are not containers are placed in the result as they are, not copied, so a shared list stays shared.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `object` | Record-class instance to convert |

- **Returns** `dict[str, JsonValue]`

##### `dataclasses.astuple(obj: object, /) → tuple`

Return a record-class instance as a tuple of its field values, recursing the same way `asdict()` does. Useful as a sort key or a dict key when every field is hashable.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `object` | Record-class instance to convert |

- **Returns** `tuple`

##### `dataclasses.fields(obj: object, /) → tuple[Field, ...]`

Return one `Field` per declared field, in declaration order. Accepts a record class or one of its instances.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `object` | Record class or instance to inspect |

- **Returns** `tuple[Field, ...]`

##### `dataclasses.replace(obj: object, /, **changes: object) → object`

Return a new instance with the named fields changed and every other field copied from `obj`. The class is constructed normally, so `__init__` runs again. A field declared `init=False` cannot be replaced.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `object` | Record-class instance to copy |
| `**changes` | `object` | Fields to set by name; every other field is copied from `obj` |

- **Returns** `object`

##### `dataclasses.is_dataclass(obj: object, /) → bool`

True when the value is a record class or an instance of one.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `object` | Value to test |

- **Returns** `bool`

*Built-in Modules*

## enum

Built-in enumerations: named constants, flags, and int or str members. Works without Shared Library research.

##### `class Enum`

Base class for enumerations: a fixed set of named members. Each assignment in the class body makes a member with `.name` and `.value`, in definition order. `Color(value)` finds a member by value, `Color[name]` by name, and iterating the class, `len(Color)` and `value in Color` cover every member. Members are singletons compared by identity and cannot be reassigned.

##### `class ReprEnum(Enum)`

An `Enum` whose `str()` and `format()` are those of its mixed-in data type, while `repr()` stays `<Color.RED: 1>`. `IntEnum`, `StrEnum` and `IntFlag` are built on it.

##### `class IntEnum(int, ReprEnum)`

An enumeration whose members are ints: they work in arithmetic, comparisons, indexing, `json.dumps` and any game function that takes a number. `str()` of a member is its number.

##### `class StrEnum(str, ReprEnum)`

An enumeration whose members are strings: they work with every string method, as dict keys equal to the plain string, in `json.dumps` and in any game function that takes a string. `auto()` gives the member name in lower case.

##### `class Flag(Enum)`

An enumeration of bit flags. Combine members with `|`, `&`, `^` and `~`; `in` tests whether one flag is set in another, iterating a combination yields its single flags, and `len` counts them. `auto()` gives successive powers of two.

##### `class IntFlag(int, ReprEnum, Flag)`

A flag enumeration whose members are ints, so a combination is also a plain number. Bits the class does not name are kept rather than refused.

##### `class EnumType(type)`

The type of every enumeration class, for `isinstance(cls, EnumType)`. Enumeration classes are built with a class statement or the functional form `Enum("Name", names)`, never by calling `EnumType` directly.

##### `EnumMeta = EnumType`

Another name for `EnumType`.

##### `class FlagBoundary(StrEnum)`

How a flag enumeration treats bits it does not name, given as `boundary=` in the class statement: `STRICT` raises, `CONFORM` drops them, `EJECT` returns a plain int, and `KEEP` keeps them. `Flag` defaults to `STRICT` and `IntFlag` to `KEEP`.

##### `class EnumCheck(StrEnum)`

The checks `verify` accepts: `UNIQUE`, `CONTINUOUS` and `NAMED_FLAGS`.

##### `enum.STRICT: str`

Flag boundary: a value with bits the class does not name raises `ValueError`.

- **Returns** `str`

##### `enum.CONFORM: str`

Flag boundary: bits the class does not name are dropped.

- **Returns** `str`

##### `enum.EJECT: str`

Flag boundary: a value with bits the class does not name comes back as a plain int.

- **Returns** `str`

##### `enum.KEEP: str`

Flag boundary: bits the class does not name are kept in the flag value.

- **Returns** `str`

##### `enum.CONTINUOUS: str`

`verify` check: no integer (or, for a flag, no bit) is missing between the smallest and largest member value.

- **Returns** `str`

##### `enum.NAMED_FLAGS: str`

`verify` check: every bit of a multi-bit flag alias belongs to a named member.

- **Returns** `str`

##### `enum.UNIQUE: str`

`verify` check: no two members share a value.

- **Returns** `str`

##### `enum.auto(value: object = _auto_null) → object`

A placeholder for a member's value. The enumeration's `_generate_next_value_` fills it in at the assignment: `Enum` and `IntEnum` count up from 1 after the largest earlier value, `StrEnum` uses the member name in lower case, and `Flag` and `IntFlag` use the next power of two. Pass a value to set it yourself.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | The member's value. Omit it to have the enumeration generate one. |

- **Returns** `object`

##### `enum.member(value: object) → object`

Makes a class-body value a member even when it would not be one, such as a function: `@member` above a `def`, or `x = member(f)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | The value that becomes a member. |

- **Returns** `object`

##### `enum.nonmember(value: object) → object`

Keeps a class-body value out of the members: `SIZE = nonmember(3)` stays an ordinary class attribute.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | The value to keep as an ordinary class attribute. |

- **Returns** `object`

##### `enum.property(fget: Callable | None = None, fset: Callable | None = None, fdel: Callable | None = None, doc: str | None = None) → Callable`

A property for enumerations. On a member it reads like `property`; read through the class, it looks up the member of the same name. Use it for a member attribute whose name is also a member name.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fget` | `Callable \| None` | Function that returns the attribute's value for a member. |
| `fset` | `Callable \| None` | Function that stores a new value, or None to make the attribute read-only. |
| `fdel` | `Callable \| None` | Function that deletes the attribute, or None. |
| `doc` | `str \| None` | Documentation text for the attribute. |

- **Returns** `Callable`

##### `enum.unique(enumeration: type, /) → type`

Class decorator that raises `ValueError` naming every alias when two members share a value, and returns the enumeration unchanged when every value is different.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `enumeration` | `type` | The enumeration class to check. |

- **Returns** `type`

##### `enum.verify(*checks: EnumCheck) → Callable`

Class decorator that checks an enumeration against `UNIQUE` (no aliases), `CONTINUOUS` (no missing integers, or no missing bits for a flag) and `NAMED_FLAGS` (every bit of a multi-bit flag alias is a member), and raises `ValueError` describing the first check that fails.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `checks` | `EnumCheck` | The checks to apply: any of `UNIQUE`, `CONTINUOUS` and `NAMED_FLAGS`. |

- **Returns** `Callable`

##### `enum.global_enum(cls: type, update_str: bool = False) → type`

Class decorator that copies every member into the global names of the module that defines the enumeration, and makes `repr()` show module-style names such as `__main__.RED`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `type` | The enumeration class. |
| `update_str` | `bool` | Also change `str()` of an `IntEnum` or `StrEnum` member to the bare name. |

- **Returns** `type`

##### `enum.global_enum_repr(self: Enum) → str`

The `repr()` that `global_enum` installs on an enumeration: the module name and the member name, such as `__main__.RED`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `self` | `Enum` | An enumeration member. |

- **Returns** `str`

##### `enum.global_flag_repr(self: Enum) → str`

The `repr()` that `global_enum` installs on a flag enumeration, joining module-style names with `|`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `self` | `Enum` | An enumeration member. |

- **Returns** `str`

##### `enum.global_str(self: Enum) → str`

The `str()` that `global_enum` installs: the bare member name.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `self` | `Enum` | An enumeration member. |

- **Returns** `str`

##### `enum.show_flag_values(value: int) → list[int]`

The single-bit values set in a positive integer or flag member, lowest first, as a list. Raises `ValueError` for a negative number.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `int` | A non-negative integer or a flag member. |

- **Returns** `list[int]`

##### `enum.pickle_by_global_name(self: Enum, proto: int) → str`

Returns the member's name. Provided so code written for CPython runs unchanged; the game has no pickle, so nothing calls it for you.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `self` | `Enum` | An enumeration member. |
| `proto` | `int` | The pickle protocol number, which the function ignores. |

- **Returns** `str`

##### `enum.pickle_by_enum_name(self: Enum, proto: int) → tuple`

Returns `(getattr, (cls, name))` for the member. Provided so code written for CPython runs unchanged; the game has no pickle, so nothing calls it for you.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `self` | `Enum` | An enumeration member. |
| `proto` | `int` | The pickle protocol number, which the function ignores. |

- **Returns** `tuple`

*Built-in Modules*

## json

Built-in JSON text helpers. Turns records into text and back, using the same value shapes the Signal Bus and Data Archive accept. Works without Shared Library research.

##### `json.dumps(obj: JsonValue, /, *, indent: int | str | None = None, sort_keys: bool = False, ensure_ascii: bool = True, separators: tuple[str, str] | None = None, allow_nan: bool = True, skipkeys: bool = False) → str`

Return `obj` as JSON text. Accepts `None`, booleans, numbers, strings, lists, tuples and dicts whose keys are strings, numbers, booleans or `None`, the same shapes the Signal Bus and Data Archive store. A set, a class instance or a function raises `TypeError`; convert it first, for example with `dataclasses.asdict()`. A container that contains itself raises `ValueError`, and one nested deeper than **256** levels raises `RecursionError`, which is the same depth `loads()` reads back.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `JsonValue` | Value to write as JSON text |
| `indent` | `int \| str \| None` | `None` for one compact line, a number of spaces, or the literal text to indent each level with |
| `sort_keys` | `bool` | Write object keys in sorted order, so two equal dicts built in a different order produce identical text. Use this whenever the text is a cache key. The keys themselves are sorted, so numeric keys order numerically (**1, 2, 10**) and a dict mixing key types Python cannot compare raises `TypeError` |
| `ensure_ascii` | `bool` | Escape every non-ASCII character as `\uXXXX`. Pass `False` to write the characters directly |
| `separators` | `tuple[str, str] \| None` | A two-item `(item, key)` tuple of strings replacing the defaults `(", ", ": ")` |
| `allow_nan` | `bool` | Write `nan` and infinities as `NaN`, `Infinity` and `-Infinity`. Pass `False` to raise `ValueError` instead. Note that those three spellings are not standard JSON, and a value that round-trips here can still be refused by `comms.send()` and the Data Archive |
| `skipkeys` | `bool` | Silently drop dict entries whose key has no JSON spelling instead of raising `TypeError` |

- **Returns** `str`

##### `json.loads(s: str, /) → JsonValue`

Read JSON text and return the value: `None`, a boolean, a number, a string, a list, or a dict with string keys. Malformed text raises `ValueError` naming the line, column and character position. Note that a whole number always comes back as an int, because in this language a whole float IS an int.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `s` | `str` | JSON text to read |

- **Returns** `JsonValue`

*Built-in Modules*

## heapq

Built-in priority-queue helpers. Keeps an ordinary list arranged so the smallest item is always first. Works without Shared Library research.

##### `heapq.heappush(heap: list, item: object, /) → None`

Add `item` to `heap`, keeping the smallest item at `heap[0]`. The heap is an ordinary list, so `len()` and `heap[0]` work as usual, and only the ordering of the rest is the heap's business.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `None`

##### `heapq.heappop(heap: list, /) → T`

Remove and return the smallest item, keeping the heap arranged. Raises `IndexError` on an empty heap, so check `len(heap)` first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |

- **Returns** `T`

##### `heapq.heappushpop(heap: list, item: object, /) → T`

Add `item` and return the smallest item, in one pass. Faster than a push followed by a pop, and never grows the heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `T`

##### `heapq.heapreplace(heap: list, item: object, /) → T`

Return the smallest item and add `item`, in one pass. The heap keeps its size. Raises `IndexError` on an empty heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `T`

##### `heapq.heapify(x: list, /) → None`

Rearrange an existing list into a heap, in place. Cheaper than pushing the items one at a time.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `list` | List to rearrange in place |

- **Returns** `None`

##### `heapq.nsmallest(n: int, iterable: Iterable, /, key: Callable | None = None) → list[T]`

Return the `n` smallest items as a sorted list. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items to return |
| `iterable` | `Iterable` | Values to choose from |
| `key` | `Callable \| None` | Optional function called once per item; the returned values are compared instead of the items |

- **Returns** `list[T]`

##### `heapq.nlargest(n: int, iterable: Iterable, /, key: Callable | None = None) → list[T]`

Return the `n` largest items as a list, largest first. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items to return |
| `iterable` | `Iterable` | Values to choose from |
| `key` | `Callable \| None` | Optional function called once per item; the returned values are compared instead of the items |

- **Returns** `list[T]`

*Built-in Modules*

## traceback

Built-in traceback helpers. Report where a caught exception came from, frame by frame. Works without Shared Library research.

##### `traceback.format_exc() → str`

Return the traceback of the exception currently being handled, as a string: the chain of calls that led to it, innermost last, each with its file, line and function. Call it inside an `except` block. Outside one it returns `NoneType: None`.

- **Returns** `str`

##### `traceback.print_exc() → None`

Write the traceback of the exception currently being handled to the console's error output. Same text as `format_exc()`, printed instead of returned. This is the answer to "the message says what broke, but where?" for an exception your own code caught.

- **Returns** `None`

*Language / Basics*
