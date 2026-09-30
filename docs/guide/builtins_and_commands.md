# Guide: Built-in Functions, Modules & Commands

Built-in runtime functions, modules, and system commands.

---

## System

##### `get_game_version() → str`

Read the current game's build identifier, matching the version at the bottom right of Settings and in feedback reports. Available before boot and from shared Libraries on every platform. Use it to identify an exact build when sharing scripts; build hashes cannot be compared as newer or older versions.

- **Returns** `str`. The seven-character commit hash, or `"dev"` in an unstamped development or test environment.

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

- **Returns** `Component | None`

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

- **Returns** `Component | None`. A machine or an outpost. `None` when no component has that name.

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

- **Returns** `Pipe | None`. A live, read-only handle.

```python
pipe = get_pipe("pipe_1")
if pipe != None:
    print(pipe.state())
```

##### `list_pipes() → list[Pipe]`

List every infrastructure pipe currently laid (complete or in-progress) as live read-only `Pipe` handles.

- **Returns** `list[Pipe]`. Live, read-only handles.

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

##### `setattr(value: object, name: str, new_value: object, /) → None`

Set the attribute called `name` on `value`, exactly as `value.name = new_value` does, when the name is only known while the script runs: `setattr(state, field, 0)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Object to change |
| `name` | `str` | Attribute name |
| `new_value` | `object` | Value to store |

- **Returns** `None`

##### `delattr(value: object, name: str, /) → None`

Remove the attribute called `name` from `value`, exactly as `del value.name` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Object to change |
| `name` | `str` | Attribute name |

- **Returns** `None`

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

List of (index, value) pairs. Optional integer `start=N` shifts the index: `enumerate(items, start=1)` for 1-based indexing. Arbitrarily large integer starts remain exact. `start` may be positional or keyword, but not both. Given a generator, it returns a lazy iterator instead of a list, taking each item only when the loop asks for it.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to number |
| `start` | `int` | Number given to the first item |

- **Returns** `list[tuple[int, T]]`

##### `zip(*iterables: Iterable, strict: bool = False) → list[tuple]`

Combine iterables into tuples. With no args, returns empty list. With one arg, returns a list of 1-tuples. Stops at the shortest input unless `strict=True`, which raises if input lengths differ. When an input is a generator, it returns a lazy iterator instead of a list.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable` | Sequences to pair up |
| `strict` | `bool` | `True` to raise when the lengths differ |

- **Returns** `list[tuple]`

##### `isinstance(value: object, type_or_tuple: type | tuple, /) → bool`

Check if a value is of the given type. Accepts a builtin type callable (`object`, `int`, `float`, `str`, `list`, `dict`, `set`, `tuple`, `slice`, `bool`), a class of your own, a game class imported from `__builtins__` (after `from __builtins__ import Smelter`, a smelter is an instance of `Smelter` and of `Component`), a string type name, a tuple of types, or a type union like `int | float` (matches any). `int` matches whole numbers and booleans, `float` matches fractional / non-finite numbers, and string `"number"` remains the broad numeric family for scripts that intentionally accept either.

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

`True` if `cls` is the given class or a subclass of it (or of any class in the tuple), per the MRO. `issubclass(Dog, Animal)` is `True`; every class is a subclass of `object`. Game classes imported from `__builtins__` work the same way: `issubclass(Smelter, Component)` and `issubclass(MiningSite, Site)` are `True`.

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
| `base` | `int` | Number base for text, from 2 to 36, or 0 to detect numeric prefixes |

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

##### `format(value: object, format_spec: str = '', /) → str`

Format one value by a format spec, the same text an f-string field produces: `format(3.14159, ".2f")` → `"3.14"`, `format(42, ">6")` → `"    42"`. With no spec it is `str(value)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to format |
| `format_spec` | `str` | Format spec, such as `".2f"` or `">10"` |

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

`base` raised to `exp`, exactly like `base ** exp`, so your own classes that define `__pow__` or `__rpow__` work too. Optional `mod` performs exact modular exponentiation and accepts negative exponents when the base has a modular inverse; a class base receives it as `__pow__(exp, mod)`. `base`, `exp`, and `mod` accept positional or keyword form.

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

Arc sine. Input must be from `-1` to `1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value from -1 to 1 |

- **Returns** `float`

##### `acos(number: float, /) → float`

Arc cosine. Input must be from `-1` to `1`.

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

##### `sum(iterable: Iterable[float] | Iterable[list] | Iterable[object], /, start: float | list | object = 0) → float | list`

Adds up the items of an iterable with `+`, starting from `start` (default `0`). Works for numbers, lists (`sum(list_of_lists, [])` flattens), tuples, and your own classes that define `__add__` or `__radd__`. Strings are refused: use `"".join(items)`. `start` may be positional or keyword, but not both.

- **Returns** `float | list`

##### `prod(iterable: Iterable[float], /, start: float = 1) → float`

Multiplies the items of an iterable with `*`, starting from `start` (default `1`). Works for numbers and for your own classes that define `__mul__` or `__rmul__`. Empty iterables return `start`. `start` may be positional or keyword, but not both.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Values to multiply |
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

##### `iter(iterable: Iterable[T] | Callable, sentinel?: object, /) → list | generator`

Return an iterator. Built-in iterables use a compatibility list-shaped iterator; protocol iterators and generators keep their identity, so `iter(iterator) is iterator`. `for` advances generators and custom iterators one item at a time, so it can break out of an infinite iterator. Consumers that must finish, such as `list(...)`, remain bounded. With a `sentinel`, `iter(read, None)` calls `read()` for each item and stops at the first result equal to `None`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T] \| Callable` | Values to iterate, or a function to call when `sentinel` is given |
| `sentinel` | `object` | Value that ends the iteration when the function returns it |

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

##### `count_by(iterable: Iterable[T], key_fn?: Callable, /) → dict[object, int]`

Count items into a dict. Without `key_fn` (or with `None`), counts each item. With a pure `key_fn`, counts the computed key; callbacks cannot suspend the script or mutate game state: `count_by(items, lambda x: x.kind)`. An empty input never inspects or calls the key function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to count |
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

Running totals over any finite iterable: the first item, then each total so far plus the next item with `+`. `accumulate([1,2,3,4])` → `[1,3,6,10]`. Works for anything `+` works on, including strings, lists and your own classes that define `__add__`. Arbitrarily large integers remain exact.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Values to total as you go |

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

Apply pure `fn` to corresponding items of each iterable. Callbacks cannot suspend the script or mutate game state. Single-iter form calls `fn(x)`; multi-iter form calls `fn(x, y, ...)` and stops at the shortest input unless `strict=True`, which raises if input lengths differ. If no row is produced, `fn` is never inspected or called. When an input is a generator, it returns a lazy iterator instead of a list.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fn` | `Callable` | Function called with one item from each sequence |
| `iter1` | `Iterable` | First sequence |
| `iter2` | `Iterable` | Second sequence, and any further ones |
| `strict` | `bool` | `True` to raise when the lengths differ |

- **Returns** `list`

##### `filter(fn: Callable | None, iterable: Iterable[T], /) → list[T]`

Keep items for which pure `fn(item)` is truthy; callbacks cannot suspend the script or mutate game state. `filter(None, iter)` keeps every truthy item without a callback. An empty input never inspects or calls `fn`. Given a generator, it returns a lazy iterator instead of a list.

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

##### `random.randrange(start: int, stop: int | None = None, step: int = 1, /) → int`

Random whole number from `range(start, stop, step)`: `randrange(10)` is 0 to 9, `randrange(5, 20, 5)` is 5, 10 or 15. The stop value is never picked.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `start` | `int` | First possible value, or the stop value when it is the only argument |
| `stop` | `int \| None` | End of the range, never picked |
| `step` | `int` | Distance between possible values (default 1) |

- **Returns** `int`

##### `random.choice(seq: list[T] | tuple[T, ...] | str, /) → T`

One random item of a list, tuple or string: `random.choice(["iron", "copper"])`. An empty one is an `IndexError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `seq` | `list[T] \| tuple[T, ...] \| str` | List, tuple or string to pick from |

- **Returns** `T`

##### `random.choices(population: list[T] | tuple[T, ...] | str, weights: Iterable[float] | None = None, *, cum_weights: Iterable[float] | None = None, k: int = 1) → list[T]`

`k` random items picked with repetition, as a list. `weights` makes some items likelier: `random.choices(["ore", "ice"], weights=[3, 1], k=5)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `population` | `list[T] \| tuple[T, ...] \| str` | List, tuple or string to pick from |
| `weights` | `Iterable[float] \| None` | How likely each item is, in the same order |
| `cum_weights` | `Iterable[float] \| None` | Running totals of the weights, instead of `weights` |
| `k` | `int` | How many items to pick (default 1) |

- **Returns** `list[T]`

##### `random.shuffle(x: list[object], /) → None`

Put a list's items in random order, in place. Returns `None`; the list itself changes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `list[object]` | List to reorder |

- **Returns** `None`

##### `random.sample(population: list[T] | tuple[T, ...] | str, k: int, *, counts: Iterable[int] | None = None) → list[T]`

`k` different random items, as a list, never picking one place twice: `random.sample(range(100), 3)`. `counts` repeats items: `counts=[3, 2]` puts the first item in the pool three times and the second twice.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `population` | `list[T] \| tuple[T, ...] \| str` | List, tuple or string to pick from |
| `k` | `int` | How many items to pick, at most the population size or the expanded pool size when `counts` is supplied |
| `counts` | `Iterable[int] \| None` | How many times each item is in the pool |

- **Returns** `list[T]`

##### `random.uniform(a: float, b: float, /) → float`

Random decimal number between `a` and `b`: `random.uniform(-1, 1)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `float` | One end of the range |
| `b` | `float` | The other end of the range |

- **Returns** `float`

##### `random.gauss(mu: float = 0.0, sigma: float = 1.0) → float`

Random number from a bell curve around `mu` with spread `sigma`: most results fall within `sigma` of `mu`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `mu` | `float` | Center of the bell curve (default 0) |
| `sigma` | `float` | Spread of the bell curve (default 1) |

- **Returns** `float`

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
| `typed` | `bool` | Also key results by argument type, so arguments that compare equal but have different types never share a result |

- **Returns** `Callable`

##### `functools.cache(user_function: Callable, /) → Callable`

Decorator that remembers every result, the same as `lru_cache(maxsize=None)`. The same warning applies: cache calculations, never world readings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `user_function` | `Callable` | Function to memoize |

- **Returns** `Callable`

##### `functools.cmp_to_key(mycmp: Callable, /) → Callable`

Turn a compare function into a `key=` function: `sorted(items, key=cmp_to_key(compare))`, where `compare(a, b)` returns a negative number when `a` comes first, zero when they tie and a positive number when `b` comes first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `mycmp` | `Callable` | Compare function taking two items |

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

##### `re.VERBOSE: int`

Whitespace and `#` comments in the pattern are layout, so a long pattern can span lines. Short alias: `re.X`.

- **Returns** `int`

##### `re.ASCII: int`

`\d`, `\w` and `\s` match only ASCII characters instead of all Unicode ones. Short alias: `re.A`.

- **Returns** `int`

##### `re.X: int`

Short alias for `re.VERBOSE`.

- **Returns** `int`

##### `re.A: int`

Short alias for `re.ASCII`.

- **Returns** `int`

##### `re.search(pattern: str | Pattern, string: str, flags: int = 0) → Match | None`

Search anywhere in `string` for `pattern`. Returns a `Match` object, or `None` if there is no match. Patterns use the documented safe regular expression subset.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to search |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.match(pattern: str | Pattern, string: str, flags: int = 0) → Match | None`

Match `pattern` at the start of `string`. Returns a `Match` object, or `None` if the start does not match.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to check |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.fullmatch(pattern: str | Pattern, string: str, flags: int = 0) → Match | None`

Match the whole `string` against `pattern`. Returns a `Match` object, or `None` if any part is left unmatched.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to check |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Match | None`

##### `re.findall(pattern: str | Pattern, string: str, flags: int = 0) → list`

Return all non-overlapping matches. With no capture groups, the result is a list of matched strings. With one capture group, the result is that group. With multiple capture groups, the result is tuples.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to search |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

##### `re.sub(pattern: str | Pattern, repl: str | Callable, string: str, count: int = 0, flags: int = 0) → str`

Replace matches of `pattern` in `string` with `repl`. `count=0` replaces all matches; a positive count limits replacements. Replacement text supports backreferences like `\1`, `\g<1>` and `\g<name>`, and `repl` may instead be a function that gets each `Match` and returns its replacement.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `repl` | `str \| Callable` | Replacement text, or a function from `Match` to text |
| `string` | `str` | String to transform |
| `count` | `int` | Maximum replacements; 0 means all |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `str`

##### `re.split(pattern: str | Pattern, string: str, maxsplit: int = 0, flags: int = 0) → list`

Split `string` wherever `pattern` matches. `maxsplit=0` means no limit. Capturing groups are included in the output, matching Python's `re.split` behavior.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to split |
| `maxsplit` | `int` | Maximum splits; 0 means all |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

##### `re.compile(pattern: str | Pattern, flags: int = 0) → Pattern`

Compile `pattern` once into a `Pattern` whose own `search`, `findall`, `sub` and other methods reuse it: `digits = re.compile(r"\d+")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Pattern`

##### `re.finditer(pattern: str | Pattern, string: str, flags: int = 0) → Iterator[Match]`

Every non-overlapping match of `pattern` in `string`, one `Match` at a time, for `for m in re.finditer(...)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `string` | `str` | String to search |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Iterator[Match]`

##### `re.subn(pattern: str | Pattern, repl: str | Callable, string: str, count: int = 0, flags: int = 0) → tuple[str, int]`

Like `re.sub()`, but returns `(new_string, number_of_replacements)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str \| Pattern` | Regular expression pattern |
| `repl` | `str \| Callable` | Replacement text, or a function from `Match` to text |
| `string` | `str` | String to transform |
| `count` | `int` | Maximum replacements; 0 means all |
| `flags` | `int` | Optional flags such as `re.IGNORECASE` |

- **Returns** `tuple[str, int]`

##### `re.escape(pattern: str, /) → str`

Put a backslash before every character that means something in a pattern, so `re.escape("1.5")` matches the text `1.5` exactly.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `str` | Text to match literally |

- **Returns** `str`

##### `re.purge() → None`

Clear the cache of compiled patterns. Patterns are compiled and cached automatically, so this is rarely needed.

- **Returns** `None`

*Built-in Modules*

## dataclasses

Built-in record-class helpers. Works without Shared Library research. Generates concise user-class value objects; use TypedDict for JSON-shaped records.

##### `dataclasses.MISSING: object`

Sentinel telling a field with no default apart from one that defaults to `None`. Test it with `field.default is MISSING`.

- **Returns** `object`

##### `dataclasses.dataclass(cls?: type | None, /, *, init: bool = True, repr: bool = True, eq: bool = True, order: bool = False, kw_only: bool = False, match_args: bool = True, unsafe_hash: bool = False, frozen: bool = False, slots: bool = False, weakref_slot: bool = False) → type`

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
| `match_args` | `bool` | Set `__match_args__` to the fields `__init__` takes positionally, so `case Point(x, y):` matches them in order (default True) |
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

Return a record-class instance as a dict, recursively converting nested record classes, lists, tuples and dicts. Sets are copied as sets with their members unchanged. Dict keys are converted too, so a record class used as a key raises `TypeError` when its converted dict cannot be used as a key. The result can be passed to `json.dumps()`, `comms.send()` or the Data Archive only when its values and keys meet that destination's rules. Lists, tuples and dicts are rebuilt; other leaf values are reused rather than deep-copied.

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

Built-in JSON text helpers. Turns supported values into text and back. Supported non-string dictionary keys become JSON key text; the Signal Bus and Data Archive instead require string keys and apply their own payload limits. Works without Shared Library research.

##### `json.dumps(obj: JsonValue, /, *, indent: int | str | None = None, sort_keys: bool = False, ensure_ascii: bool = True, separators: tuple[str, str] | None = None, allow_nan: bool = True, skipkeys: bool = False) → str`

Return `obj` as JSON text. Accepts `None`, booleans, numbers, strings, lists, tuples and dicts whose keys are strings, numbers, booleans or `None`. Those non-string keys are converted to text. The Signal Bus and Data Archive instead require string dictionary keys and apply their own payload limits. A set, a class instance or a function raises `TypeError`; convert it first, for example with `dataclasses.asdict()`. A container that contains itself raises `ValueError`, and one nested deeper than **256** levels raises `RecursionError`, which is the same depth `loads()` reads back.

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

##### `heapq.heappush(heap: list[T], item: object, /) → None`

Add `item` to `heap`, keeping the smallest item at `heap[0]`. The heap is an ordinary list, so `len()` and `heap[0]` work as usual, and only the ordering of the rest is the heap's business.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list[T]` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `None`

##### `heapq.heappop(heap: list[T], /) → T`

Remove and return the smallest item, keeping the heap arranged. Raises `IndexError` on an empty heap, so check `len(heap)` first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list[T]` | List arranged as a heap by the other heapq functions |

- **Returns** `T`

##### `heapq.heappushpop(heap: list[T], item: object, /) → T`

Add `item` and return the smallest item, in one pass. Faster than a push followed by a pop, and never grows the heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list[T]` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `T`

##### `heapq.heapreplace(heap: list[T], item: object, /) → T`

Return the smallest item and add `item`, in one pass. The heap keeps its size. Raises `IndexError` on an empty heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list[T]` | List arranged as a heap by the other heapq functions |
| `item` | `object` | Value to add |

- **Returns** `T`

##### `heapq.heapify(x: list, /) → None`

Rearrange an existing list into a heap, in place. Cheaper than pushing the items one at a time.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `list` | List to rearrange in place |

- **Returns** `None`

##### `heapq.nsmallest(n: int, iterable: Iterable[T], /, key: Callable | None = None) → list[T]`

Return the `n` smallest items as a sorted list. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items to return |
| `iterable` | `Iterable[T]` | Values to choose from |
| `key` | `Callable \| None` | Optional function called once per item; the returned values are compared instead of the items |

- **Returns** `list[T]`

##### `heapq.nlargest(n: int, iterable: Iterable[T], /, key: Callable | None = None) → list[T]`

Return the `n` largest items as a list, largest first. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items to return |
| `iterable` | `Iterable[T]` | Values to choose from |
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

*Built-in Modules*

## math

Python's math functions and constants under `math.`, such as `math.sqrt`, `math.floor`, `math.gcd` and `math.pi`. The common ones also work without the prefix. Works without Shared Library research.

##### `math.pi: float`

Mathematical constant `π ≈ 3.14159`.

- **Returns** `float`

##### `math.tau: float`

Mathematical constant `τ = 2π`.

- **Returns** `float`

##### `math.e: float`

Euler's number, `2.718281828459045`.

- **Returns** `float`

##### `math.inf: float`

Positive infinity, larger than any number.

- **Returns** `float`

##### `math.nan: float`

Not a number: the result of an undefined calculation. Test for it with `math.isnan`, since `nan == nan` is `False`.

- **Returns** `float`

##### `math.acos(number: float, /) → float`

Arc cosine. Input must be from `-1` to `1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value from -1 to 1 |

- **Returns** `float`

##### `math.asin(number: float, /) → float`

Arc sine. Input must be from `-1` to `1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Value from -1 to 1 |

- **Returns** `float`

##### `math.atan(number: float, /) → float`

Arc tangent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Tangent value |

- **Returns** `float`

##### `math.atan2(y: float, x: float, /) → float`

Arc tangent of `y/x`, correctly choosing the quadrant.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `y` | `float` | Vertical component |
| `x` | `float` | Horizontal component |

- **Returns** `float`

##### `math.ceil(number: float, /) → int`

Round up to the nearest integer.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to round up |

- **Returns** `int`

##### `math.cos(radians: float, /) → float`

Cosine of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `math.degrees(radians: float, /) → float`

Convert radians to degrees.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `math.exp(number: float, /) → float`

`e` raised to the power of the argument.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Power of e to compute |

- **Returns** `float`

##### `math.floor(number: float, /) → int`

Round down to the nearest integer.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to round down |

- **Returns** `int`

##### `math.isclose(a: float, b: float, rel_tol: float = 0.000000001, abs_tol: float = 0.0) → bool`

Return `True` when two numbers are close enough to treat as equal. `rel_tol` scales with the compared values; `abs_tol` sets a fixed accepted difference in the same unit, useful for values near zero and physical readings such as coordinates. Tolerances must be non-negative. This is the directly available equivalent of Python's `math.isclose()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `float` | First number |
| `b` | `float` | Second number |
| `rel_tol` | `float` | Maximum relative difference |
| `abs_tol` | `float` | Maximum absolute difference in the values' unit |

- **Returns** `bool`

##### `math.log(number: float, base?: float, /) → float`

Natural log, or log with the given base.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |
| `base` | `float` | Logarithm base; the natural logarithm when omitted |

- **Returns** `float`

##### `math.log10(number: float, /) → float`

Base-10 logarithm.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |

- **Returns** `float`

##### `math.log2(number: float, /) → float`

Base-2 logarithm.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number greater than zero |

- **Returns** `float`

##### `math.prod(iterable: Iterable[float], /, start: float = 1) → float`

Multiplies the items of an iterable with `*`, starting from `start` (default `1`). Works for numbers and for your own classes that define `__mul__` or `__rmul__`. Empty iterables return `start`. `start` may be positional or keyword, but not both.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Values to multiply |
| `start` | `float` | Value the product starts from |

- **Returns** `float`

##### `math.radians(degrees: float, /) → float`

Convert degrees to radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `degrees` | `float` | Angle in degrees |

- **Returns** `float`

##### `math.sin(radians: float, /) → float`

Sine of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `math.sqrt(number: float, /) → float`

Square root. Errors on negative input.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number zero or greater |

- **Returns** `float`

##### `math.tan(radians: float, /) → float`

Tangent of an angle in radians.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `radians` | `float` | Angle in radians |

- **Returns** `float`

##### `math.trunc(number: float, /) → int`

Drop the fractional part (round toward zero).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `float` | Number to cut toward zero |

- **Returns** `int`

##### `math.fabs(x: float, /) → float`

Absolute value as a float: `math.fabs(-2)` → `2.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.cbrt(x: float, /) → float`

Cube root, negative numbers included: `math.cbrt(-8)` → `-2.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.exp2(x: float, /) → float`

`2` raised to `x`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Power of two |

- **Returns** `float`

##### `math.expm1(x: float, /) → float`

`e ** x - 1`, accurate even when `x` is tiny.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Exponent |

- **Returns** `float`

##### `math.log1p(x: float, /) → float`

Natural log of `1 + x`, accurate even when `x` is tiny.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number above -1 |

- **Returns** `float`

##### `math.sinh(x: float, /) → float`

Hyperbolic sine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.cosh(x: float, /) → float`

Hyperbolic cosine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.tanh(x: float, /) → float`

Hyperbolic tangent, always between `-1` and `1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.asinh(x: float, /) → float`

Inverse hyperbolic sine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `float`

##### `math.acosh(x: float, /) → float`

Inverse hyperbolic cosine.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number, at least 1 |

- **Returns** `float`

##### `math.atanh(x: float, /) → float`

Inverse hyperbolic tangent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number between -1 and 1 |

- **Returns** `float`

##### `math.isfinite(x: float, /) → bool`

`True` unless `x` is infinite or `nan`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `bool`

##### `math.isinf(x: float, /) → bool`

`True` when `x` is positive or negative infinity.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `bool`

##### `math.isnan(x: float, /) → bool`

`True` when `x` is `nan`, which is not even equal to itself.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `bool`

##### `math.copysign(x: float, y: float, /) → float`

`x`'s size with `y`'s sign: `math.copysign(3, -0.5)` → `-3.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Size of the result |
| `y` | `float` | Number whose sign the result takes |

- **Returns** `float`

##### `math.fmod(x: float, y: float, /) → float`

Remainder with the sign of `x`, unlike `%`, which takes the sign of `y`: `math.fmod(-7, 3)` → `-1.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Dividend |
| `y` | `float` | Divisor |

- **Returns** `float`

##### `math.remainder(x: float, y: float, /) → float`

Distance from `x` to the nearest multiple of `y`, which can be negative: `math.remainder(7, 4)` → `-1.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Dividend |
| `y` | `float` | Divisor |

- **Returns** `float`

##### `math.pow(x: float, y: float, /) → float`

`x` raised to `y` as a float. Unlike `**`, a negative base with a fractional exponent is a `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Base |
| `y` | `float` | Exponent |

- **Returns** `float`

##### `math.modf(x: float, /) → tuple[float, float]`

The fractional and whole parts of `x`, both with its sign: `math.modf(-3.25)` → `(-0.25, -3.0)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `float` | Number |

- **Returns** `tuple[float, float]`

##### `math.hypot(*coordinates: float) → float`

Length of the vector from the origin: `math.hypot(3, 4)` → `5.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `coordinates` | `float` | Coordinates |

- **Returns** `float`

##### `math.dist(p: Iterable[float], q: Iterable[float], /) → float`

Straight-line distance between two points: `math.dist((0, 0), (3, 4))` → `5.0`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `p` | `Iterable[float]` | First point |
| `q` | `Iterable[float]` | Second point, same number of coordinates |

- **Returns** `float`

##### `math.fsum(iterable: Iterable[float], /) → float`

Sum of floats without rounding error building up: `math.fsum([0.1] * 10)` → `1.0`, where `sum` gives `0.9999999999999999`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[float]` | Numbers to add |

- **Returns** `float`

##### `math.gcd(*integers: int) → int`

Greatest common divisor: `math.gcd(12, 18)` → `6`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `integers` | `int` | Whole numbers |

- **Returns** `int`

##### `math.lcm(*integers: int) → int`

Least common multiple: `math.lcm(4, 6)` → `12`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `integers` | `int` | Whole numbers |

- **Returns** `int`

##### `math.isqrt(n: int, /) → int`

Whole-number square root, rounded down: `math.isqrt(10)` → `3`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | Whole number, at least 0 |

- **Returns** `int`

##### `math.factorial(n: int, /) → int`

`n!`, the product of `1` to `n`: `math.factorial(5)` → `120`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | Whole number, at least 0 |

- **Returns** `int`

##### `math.perm(n: int, k: int | None = None, /) → int`

Ways to pick `k` of `n` items in order: `math.perm(5, 2)` → `20`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items |
| `k` | `int \| None` | How many to arrange (default all) |

- **Returns** `int`

##### `math.comb(n: int, k: int, /) → int`

Ways to choose `k` of `n` items, order ignored: `math.comb(5, 2)` → `10`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | How many items |
| `k` | `int` | How many to choose |

- **Returns** `int`

*Built-in Modules*

## itertools

Python's iterator building blocks under `itertools.`, such as `itertools.count`, `itertools.islice` and `itertools.groupby`. Each returns a lazy iterator, so an endless one is fine in a loop with a `break`. Works without Shared Library research.

##### `itertools.count(start: int | float = 0, step: int | float = 1) → Iterator[int | float]`

Count up forever from `start` by `step`: `for i in count(1):` numbers loop passes from 1. It never ends on its own, so stop with `break` or take a few with `islice`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `start` | `int \| float` | First number |
| `step` | `int \| float` | Added each time |

- **Returns** `Iterator[int | float]`

##### `itertools.cycle(iterable: Iterable[T], /) → Iterator[T]`

Repeat the items of `iterable` forever, in order: `cycle(["north", "east", "south"])` for a patrol route. An empty input gives nothing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to repeat |

- **Returns** `Iterator[T]`

##### `itertools.repeat(object: T, times: int | None = None) → Iterator[T]`

Give the same value `times` times, or forever when `times` is `None`: `repeat(0, 5)` yields five zeros.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `object` | `T` | Value to give |
| `times` | `int \| None` | How many times, or `None` for forever |

- **Returns** `Iterator[T]`

##### `itertools.accumulate(iterable: Iterable[T], func: Callable | None = None, *, initial: T | None = None) → Iterator[T]`

Running totals: `accumulate([1, 2, 3])` yields `1, 3, 6`. Pass `func` to combine with something other than `+`, such as `max` for a running best, and `initial=` to start from a value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Values to combine |
| `func` | `Callable \| None` | Pure function combining the total so far with the next value; `+` when omitted |
| `initial` | `T \| None` | Value to start from, given first |

- **Returns** `Iterator[T]`

##### `itertools.batched(iterable: Iterable[T], n: int, *, strict: bool = False) → Iterator[tuple[T, ...]]`

Group items into tuples of `n`: `batched("abcdefg", 3)` yields `("a", "b", "c")`, `("d", "e", "f")`, `("g",)`. With `strict=True`, a short last group raises `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to group |
| `n` | `int` | Items per group, at least 1 |
| `strict` | `bool` | Raise instead of giving a short last group |

- **Returns** `Iterator[tuple[T, ...]]`

##### `itertools.chain(*iterables: Iterable[T]) → Iterator[T]`

Go through several iterables one after another: `chain(ore_sites, ice_sites)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable[T]` | Iterables to go through in order |

- **Returns** `Iterator[T]`

##### `itertools.chain.from_iterable(iterable: Iterable[Iterable[T]], /) → Iterator[T]`

Like `chain`, reading the iterables from one iterable: `chain.from_iterable(rows)` flattens rows lazily.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[Iterable[T]]` | Iterable of iterables |

- **Returns** `Iterator[T]`

##### `itertools.compress(data: Iterable[T], selectors: Iterable) → Iterator[T]`

Keep the items of `data` whose matching selector is truthy: `compress("abcd", [1, 0, 1, 0])` yields `"a"`, `"c"`. Stops at the shorter input.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `data` | `Iterable[T]` | Items to pick from |
| `selectors` | `Iterable` | Truth values, one per item |

- **Returns** `Iterator[T]`

##### `itertools.dropwhile(predicate: Callable, iterable: Iterable[T], /) → Iterator[T]`

Skip items while pure `predicate(item)` is truthy, then give every remaining item.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `predicate` | `Callable` | Pure test deciding what to skip at the start |
| `iterable` | `Iterable[T]` | Items to read |

- **Returns** `Iterator[T]`

##### `itertools.filterfalse(predicate: Callable | None, iterable: Iterable[T], /) → Iterator[T]`

Keep the items for which pure `predicate(item)` is falsy, the opposite of `filter`. With `None`, keeps the falsy items.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `predicate` | `Callable \| None` | Pure test, or `None` to test the items themselves |
| `iterable` | `Iterable[T]` | Items to read |

- **Returns** `Iterator[T]`

##### `itertools.groupby(iterable: Iterable[T], key: Callable | None = None) → Iterator[tuple[object, Iterator[T]]]`

Group consecutive items that share a key, as `(key, group)` pairs; each group is an iterator over its items. Sort by the same key first to group all equal items together. Reading the next pair ends the previous group.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to group |
| `key` | `Callable \| None` | Pure function giving each item's key; the item itself when omitted |

- **Returns** `Iterator[tuple[object, Iterator[T]]]`

##### `itertools.islice(iterable: Iterable[T], start: int | None, stop: int | None = None, step: int | None = 1, /) → Iterator[T]`

Take part of an iterator without building a list: `islice(it, 3)` gives the first three items, `islice(it, 2, 10, 2)` every second item from index 2 up to 10. Skipped items are consumed; if `start` is greater than `stop`, it can still consume the first `start` items.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to read |
| `start` | `int \| None` | With one number, where to stop; otherwise the first index to give |
| `stop` | `int \| None` | Index to stop before, or `None` for no end |
| `step` | `int \| None` | Distance between given indexes, at least 1 |

- **Returns** `Iterator[T]`

##### `itertools.pairwise(iterable: Iterable[T], /) → Iterator[tuple[T, T]]`

Neighboring pairs, lazily: `pairwise(route)` yields each `(a, b)` leg of a route.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to pair |

- **Returns** `Iterator[tuple[T, T]]`

##### `itertools.starmap(function: Callable, iterable: Iterable, /) → Iterator[object]`

Call `function` with each item unpacked as its arguments: `starmap(pow, [(2, 3), (3, 2)])` yields `8, 9`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `function` | `Callable` | Pure function to call |
| `iterable` | `Iterable` | Rows of arguments |

- **Returns** `Iterator[object]`

##### `itertools.takewhile(predicate: Callable, iterable: Iterable[T], /) → Iterator[T]`

Give items while pure `predicate(item)` is truthy, and stop at the first one that is not.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `predicate` | `Callable` | Pure test deciding when to stop |
| `iterable` | `Iterable[T]` | Items to read |

- **Returns** `Iterator[T]`

##### `itertools.tee(iterable: Iterable[T], n: int = 2, /) → tuple[Iterator[T], ...]`

Split one iterator into `n` independent iterators that each give every item. Use the copies, not the original, afterwards.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Iterator to split |
| `n` | `int` | How many copies |

- **Returns** `tuple[Iterator[T], ...]`

##### `itertools.zip_longest(*iterables: Iterable, fillvalue: object = None) → Iterator[tuple]`

Like `zip`, but runs to the longest input and fills the missing places with `fillvalue`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable` | Iterables to combine |
| `fillvalue` | `object` | Value for an input that has run out |

- **Returns** `Iterator[tuple]`

##### `itertools.product(*iterables: Iterable, repeat: int = 1) → Iterator[tuple]`

Every combination taking one item from each input, as tuples: `product("ab", [1, 2])` yields `("a", 1)`, `("a", 2)`, `("b", 1)`, `("b", 2)`. `repeat=n` uses the inputs `n` times.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterables` | `Iterable` | Inputs to combine |
| `repeat` | `int` | How many times to use the inputs |

- **Returns** `Iterator[tuple]`

##### `itertools.permutations(iterable: Iterable[T], r: int | None = None) → Iterator[tuple[T, ...]]`

Every ordering of `r` items, as tuples; all items when `r` is omitted. Items are told apart by position, not value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to order |
| `r` | `int \| None` | Items per ordering |

- **Returns** `Iterator[tuple[T, ...]]`

##### `itertools.combinations(iterable: Iterable[T], r: int) → Iterator[tuple[T, ...]]`

Every choice of `r` items, in input order and without repeats: `combinations("abc", 2)` yields `("a", "b")`, `("a", "c")`, `("b", "c")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to choose from |
| `r` | `int` | Items per choice |

- **Returns** `Iterator[tuple[T, ...]]`

##### `itertools.combinations_with_replacement(iterable: Iterable[T], r: int) → Iterator[tuple[T, ...]]`

Every choice of `r` items where an item may be chosen more than once: `combinations_with_replacement("ab", 2)` yields `("a", "a")`, `("a", "b")`, `("b", "b")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to choose from |
| `r` | `int` | Items per choice |

- **Returns** `Iterator[tuple[T, ...]]`

*Built-in Modules*

## operator

Python's operators as functions under `operator.`, such as `operator.add` to pass to `reduce` and `operator.itemgetter` to pass as a `key=`. Works without Shared Library research.

##### `operator.abs(a: object, /) → object`

The built-in `abs(a)`: a number without its sign, or what a class's `__abs__` returns.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Operand |

- **Returns** `object`

##### `operator.lt(a: object, b: object, /) → object`

`a < b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.le(a: object, b: object, /) → object`

`a <= b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.eq(a: object, b: object, /) → object`

`a == b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.ne(a: object, b: object, /) → object`

`a != b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.ge(a: object, b: object, /) → object`

`a >= b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.gt(a: object, b: object, /) → object`

`a > b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.not_(a: object, /) → bool`

`not a` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Value to test |

- **Returns** `bool`

##### `operator.truth(a: object, /) → bool`

`True` when `a` is truthy, the same test `if a:` makes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Value to test |

- **Returns** `bool`

##### `operator.is_(a: object, b: object, /) → bool`

`a is b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `bool`

##### `operator.is_not(a: object, b: object, /) → bool`

`a is not b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `bool`

##### `operator.is_none(a: object, /) → bool`

`a is None` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Value to test |

- **Returns** `bool`

##### `operator.is_not_none(a: object, /) → bool`

`a is not None` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Value to test |

- **Returns** `bool`

##### `operator.add(a: object, b: object, /) → object`

`a + b` as a function: `reduce(operator.add, [1, 2, 3])` → `6`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.sub(a: object, b: object, /) → object`

`a - b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.mul(a: object, b: object, /) → object`

`a * b` as a function: `reduce(operator.mul, [2, 3, 4])` → `24`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.truediv(a: object, b: object, /) → object`

`a / b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.floordiv(a: object, b: object, /) → object`

`a // b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.mod(a: object, b: object, /) → object`

`a % b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.pow(a: object, b: object, /) → object`

`a ** b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.lshift(a: object, b: object, /) → object`

`a << b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.rshift(a: object, b: object, /) → object`

`a >> b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.and_(a: object, b: object, /) → object`

`a & b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.or_(a: object, b: object, /) → object`

`a | b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.xor(a: object, b: object, /) → object`

`a ^ b` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Left operand |
| `b` | `object` | Right operand |

- **Returns** `object`

##### `operator.neg(a: object, /) → object`

`-a` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Operand |

- **Returns** `object`

##### `operator.pos(a: object, /) → object`

`+a` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Operand |

- **Returns** `object`

##### `operator.invert(a: object, /) → object`

`~a` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Operand |

- **Returns** `object`

##### `operator.inv(a: object, /) → object`

`~a` as a function, the same as `invert`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Operand |

- **Returns** `object`

##### `operator.index(a: object, /) → int`

`a` as a whole number, the conversion a list index makes: `operator.index(True)` → `1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Value to convert |

- **Returns** `int`

##### `operator.concat(a: object, b: object, /) → object`

`a + b` for two sequences, such as lists or text.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | First sequence |
| `b` | `object` | Sequence to add |

- **Returns** `object`

##### `operator.contains(a: object, b: object, /) → bool`

`b in a` as a function. The container comes first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Container to search |
| `b` | `object` | Value to look for |

- **Returns** `bool`

##### `operator.countOf(a: Iterable, b: object, /) → int`

How many items of `a` equal `b`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `Iterable` | Items to count in |
| `b` | `object` | Value to count |

- **Returns** `int`

##### `operator.indexOf(a: Iterable, b: object, /) → int`

Position of the first item of `a` that equals `b`. Raises `ValueError` when none does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `Iterable` | Items to search |
| `b` | `object` | Value to find |

- **Returns** `int`

##### `operator.getitem(a: object, b: object, /) → object`

`a[b]` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Container |
| `b` | `object` | Index or key |

- **Returns** `object`

##### `operator.setitem(a: object, b: object, c: object, /) → None`

`a[b] = c` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Container |
| `b` | `object` | Index or key |
| `c` | `object` | Value to store |

- **Returns** `None`

##### `operator.delitem(a: object, b: object, /) → None`

`del a[b]` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `object` | Container |
| `b` | `object` | Index or key |

- **Returns** `None`

##### `operator.attrgetter(attr: str, /, *attrs: str) → Callable`

A function that reads the named attribute, for `key=`: `sorted(points, key=attrgetter("x"))`. Several names give a tuple.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `attr` | `str` | Attribute name; a dotted name reads through, such as `"pos.x"` |
| `*attrs` | `str` | More attribute names |

- **Returns** `Callable`

##### `operator.itemgetter(item: object, /, *items: object) → Callable`

A function that reads the given index or key, for `key=`: `sorted(pairs, key=itemgetter(1))` sorts by each pair's second item. Several keys give a tuple.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `object` | Index or key |
| `*items` | `object` | More indexes or keys |

- **Returns** `Callable`

##### `operator.methodcaller(name: str, /, *args: object, **kwargs: object) → Callable`

A function that calls the named method on its argument: `map(methodcaller("strip"), lines)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `str` | Method name |
| `*args` | `object` | Arguments for the method |
| `**kwargs` | `object` | Keyword arguments for the method |

- **Returns** `Callable`

##### `operator.call(obj: Callable, /, *args: object, **kwargs: object) → object`

`obj(*args, **kwargs)` as a function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `Callable` | Function to call |
| `*args` | `object` | Arguments |
| `**kwargs` | `object` | Keyword arguments |

- **Returns** `object`

*Built-in Modules*

## string

Python's text constants under `string.`, such as `string.ascii_uppercase` and `string.digits`, plus `string.capwords`. Works without Shared Library research.

##### `string.ascii_letters: str`

`ascii_lowercase` followed by `ascii_uppercase`.

- **Returns** `str`

##### `string.ascii_lowercase: str`

The letters `abcdefghijklmnopqrstuvwxyz`.

- **Returns** `str`

##### `string.ascii_uppercase: str`

The letters `ABCDEFGHIJKLMNOPQRSTUVWXYZ`.

- **Returns** `str`

##### `string.digits: str`

The text `0123456789`.

- **Returns** `str`

##### `string.hexdigits: str`

The text `0123456789abcdefABCDEF`.

- **Returns** `str`

##### `string.octdigits: str`

The text `01234567`.

- **Returns** `str`

##### `string.punctuation: str`

Every ASCII punctuation character, `!` through `~`.

- **Returns** `str`

##### `string.printable: str`

`digits`, `ascii_letters`, `punctuation` and `whitespace` together.

- **Returns** `str`

##### `string.whitespace: str`

Space, tab, newline, carriage return, vertical tab and form feed.

- **Returns** `str`

##### `string.capwords(s: str, sep: str | None = None) → str`

Capitalize every word: `capwords("hello  world")` → `"Hello World"`. Without `sep`, words split on any whitespace and rejoin with one space; with `sep`, they split and rejoin on it.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `s` | `str` | Text to capitalize |
| `sep` | `str \| None` | Word separator (default any whitespace) |

- **Returns** `str`

*Built-in Modules*

## collections

Python's container types under `collections.`: `defaultdict`, `Counter`, `OrderedDict`, `deque` and `namedtuple`. `collections.abc` still names the abstract types for annotations. Works without Shared Library research.

##### `collections.Counter(iterable: object = None, /, **kwargs: int) → Counter`

A dict that counts things: `Counter("banana")` counts each letter, and a missing key reads as `0`. `most_common(n)` lists the biggest counts.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `object` | Items to count, or a mapping of counts |
| `**kwargs` | `int` | Counts by name |

- **Returns** `Counter`

##### `collections.defaultdict(default_factory: Callable | None = None, /, *args: object, **kwargs: object) → defaultdict`

A dict that makes a value for a missing key: with `defaultdict(list)` every new key starts as `[]`, so `groups[key].append(x)` just works.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default_factory` | `Callable \| None` | Function that makes a missing key's value |
| `*args` | `object` | A mapping or iterable of pairs to start from |
| `**kwargs` | `object` | Items by name |

- **Returns** `defaultdict`

##### `collections.OrderedDict(iterable: object = (), /, **kwargs: object) → OrderedDict`

A dict with order-aware extras: `move_to_end(key)` and `popitem(last=False)`, and `==` between two of them also compares their order.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `object` | A mapping or iterable of pairs to start from |
| `**kwargs` | `object` | Items by name |

- **Returns** `OrderedDict`

##### `collections.deque(iterable: Iterable[T] = (), maxlen: int | None = None) → deque`

A list-like queue with fast adds and removes at both ends: `append`, `appendleft`, `pop`, `popleft`. With `maxlen`, adding past the limit drops from the other end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to start with |
| `maxlen` | `int \| None` | Size limit (default none) |

- **Returns** `deque`

##### `collections.namedtuple(typename: str, field_names: str | Iterable[str], *, rename: bool = False, defaults: Iterable | None = None, module: str | None = None) → type`

Make a tuple class with named fields: `Point = namedtuple("Point", "x y")`, then `Point(1, 2).x`. It still indexes and unpacks like a tuple.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `typename` | `str` | Class name |
| `field_names` | `str \| Iterable[str]` | Field names, as a list or one string such as `"x y"` |
| `rename` | `bool` | Replace invalid field names with `_0`, `_1` and so on |
| `defaults` | `Iterable \| None` | Defaults for the last fields |
| `module` | `str \| None` | Accepted and ignored |

- **Returns** `type`

*Language / Basics*
