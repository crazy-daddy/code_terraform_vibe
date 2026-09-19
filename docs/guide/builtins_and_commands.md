# Guide: Built-in Functions, Modules & Commands

Built-in runtime functions, modules, and system commands.

---

## Built-in Functions

### Output

##### `print(*values, sep=" ", end="\n")`

Output text to the console. Multiple values are joined by `sep` (default a single space). `end` is appended after the last value (default a newline). Console output is a character stream and the newlines in it are what break lines, so `end=""` leaves the line open and the next `print()` continues it: use that to build a row from several calls, then close it with a bare `print()`. Every call updates an unfinished line immediately. Within that row, `\r` returns the write position to the start and `\b` moves it back one visible character. Neither control erases text by itself; following text overwrites existing text. Neither control can enter an earlier row, and ANSI escape sequences are not interpreted.

- **Returns** `None`

##### `warn(*values, sep=" ", end="\n")`

Output an amber warning line to the persistent console. Same argument behavior as `print()`, but routed to the WARNINGS filter. Use it for background monitors that need attention without showing a toast. Use `notify(text, "warn")` when the player should be interrupted.

- **Returns** `None`

##### `debug(*values, sep=" ", end="\n")`

Output low-priority telemetry to the persistent console. Same argument behavior as `print()`, but hidden from the ALL view unless debug output is enabled in console options. Use it for noisy tuning data that should not crowd normal logs.

- **Returns** `None`

##### `notify(text, /, level="info", duration_seconds?, dismissible=True)`

Show a toast to the player and add it to the **Computer → Notifications** archive. Use sparingly: for events that genuinely need the operator's attention (battery critical, contract solved, drone stranded); prefer `print()` for ongoing telemetry. `level` is `"info"` (default), `"warn"`, or `"error"` and drives the toast's color + the history entry's color dot. `duration_seconds` sets how long the toast stays before auto-dismissing: clamped to **0.5-30s**; omitted uses the default (**5s** info/warn, **6s** error). Pass **0** as the duration to make the toast **sticky**: it never auto-dismisses and stays until the player clicks it. Use this for fatal errors that must be acknowledged. `dismissible` defaults to `True`; pass `False` as the fourth argument for a forced-read toast with no early close. A sticky toast is always dismissible, so it can never pin the screen. Identical consecutive notifications from the same script collapse inside a 1-second window, and a sticky already on screen is never duplicated, so a tight loop can't spam the screen.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `text` | `string` | Notification text |
| `level` | `string` | Notification severity |
| `duration_seconds` | `number` | Visible duration in real seconds; 0 is sticky |
| `dismissible` | `boolean` | Whether the player may close the toast early |

- **Returns** `None`

### Control

##### `sleep(seconds, /)`

Wait before continuing. **The argument is in real seconds**, not world-clock hours. The day cycle compresses **24** world-clock hours into a shorter real-time window, so `sleep(25)` is about 1 world-clock hour at the default 10-min-per-day pacing. For planet-aware delays, query the conversion: `sleep(get_component("clock").real_seconds_per_hour() * 2)` waits exactly two world-clock hours regardless of pacing. Loops are paced automatically; `sleep()` is for deliberate delays.

- **Returns** `None`

*Raises*

| Exception | Condition |
| --- | --- |
| `TypeError` | `sleep(seconds)` requires one numeric duration. |
| `ValueError` | `sleep(seconds)` requires a finite duration greater than or equal to zero. |
| `OverflowError` | `sleep(seconds)` cannot represent the requested duration within the simulation tick range. |

### Utility

##### `len(value, /)`

Length of a list, tuple, string, dict, or set.

- **Returns** `number`

##### `range(stop, /) / range(start, stop, /) / range(start, stop, step, /)`

Materialize the bounded integer range from `start` to `stop` (exclusive), stepping by `step`. `range(5)` → `[0,1,2,3,4]`. Endpoints and steps retain arbitrary-size exact integers, while the produced list must fit the interpreter's collection limit. All arguments must be integers; `step=0` and fractional values are rejected. Negative `step` counts down: `range(5, 0, -1)` → `[5,4,3,2,1]`.

- **Returns** `list<number>`

##### `slice(stop, /) / slice(start, stop, step=None, /)`

Build a reusable slice object for list, tuple, and string subscripts. `slice(None, None, -1)` is the reusable form of `[::-1]`; `seq[s]` follows the same bounds and step rules as `seq[start:stop:step]`.

- **Returns** `slice`

##### `type(value, /)`

Returns the player's value-based type category as a string: a user class instance returns its class name, `"int"` covers whole numbers (including exact huge integers), `"float"` covers fractional / non-finite numbers, and built-ins report `"str"`, `"bool"`, `"NoneType"`, `"list"`, `"tuple"`, `"dict"`, `"set"`, or `"slice"`. Game API values retain the established `"object"` category so existing scripts remain unchanged; use `object_type(value)` for a concrete registered data-object name. Numeric categories are based on the current value, not literal spelling, so `type(4.0)` returns `"int"` because the value is whole. Game APIs still document broad numeric parameters as `number` when they accept either ints or floats.

- **Returns** `string`

##### `object_type(value, /)`

Return a concrete registered name such as `"MiningSite"`, `"CatalogedFragment"`, or `"Position"` for a game data object without changing the established result of `type(value)`. Component references return `"Component"`; other values use the same public category as `type(value)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `any` | Value whose concrete game data-object name is needed |

- **Returns** `string`

##### `vars(object, /)`

Return a detached, shallow dictionary of an object's public data fields. Structured results, positions, journal entries, and other game data values include their documented attribute fields but not methods; class instances include their own stored attributes. Changing the returned dictionary does not change the object, although nested lists and dictionaries are shared. Use `object_type(object)` separately when the concrete registered name is needed. Pass exactly one object; the no-argument local-scope form is not supported.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `object` | `any` | Game API value or class instance to snapshot |

- **Returns** `dict`

##### `object()`

Construct a new identity-only base object. It takes no arguments and has no writable game-script attributes. User classes inherit from `object` implicitly.

- **Returns** `object`

##### `TypedDict(name, fields, /)`

Declare a fixed-key dict shape for the editor. Use the functional form (`State = TypedDict("State", {"mode": str})`) and annotate records with that name (`state: State = {...}`). Runtime treats this as an inert type marker; the editor uses it for key autocomplete, field type flow, and typo lint.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `string` | Declared type name |
| `fields` | `any` | Dictionary mapping field names to type expressions |

- **Returns** `any`

##### `hasattr(value, name, /)`

Return `True` if `value.name` is readable, otherwise `False`. The attribute name must be a string. Useful in duck-typed helpers that accept several documented object shapes, e.g. `hasattr(value, "required_recipe")`. Gameplay result objects keep their fixed fields, so branch on `.status` before reading a documented payload such as `analysis.info`. Missing mounted sub-objects such as `self.sonar` return `False` when the module is not installed.

- **Returns** `boolean`

##### `getattr(value, name, default?, /)`

Read an attribute by string name, exactly like `value.name`. Without `default`, a missing attribute raises `AttributeError`; with `default`, missing attributes return that fallback. Works for game object properties/methods and built-in methods such as `getattr([1], "append")`. Use with `hasattr()` for duck-typed helpers, not as a replacement for a gameplay result's documented `.status`, `.message`, and payload fields.

- **Returns** `any`

##### `sorted(sequence, /, *, key=None, reverse=False)`

Return a new list sorted using `<` between mutually comparable keys. With `key=None` (the default), each value is its own key. Numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may define the exact rich-comparison slots needed by `<`; unsupported pairs raise. `key=` is called once per item and must be pure: it cannot suspend or mutate game state. `reverse` is truth-tested, and the finite input is handled eagerly within the interpreter's collection limit.

- **Returns** `list`

##### `reversed(iterable, /)`

Return a reversed list copy of any finite iterable. This consumes the input fully, so an infinite generator exceeds the collection limit; dictionaries (their keys), sets (deterministic insertion order), generators, and custom iterator-protocol classes are accepted.

- **Returns** `list`

##### `enumerate(iterable, /, start=0)`

List of (index, value) pairs. Optional integer `start=N` shifts the index: `enumerate(items, start=1)` for 1-based indexing. Arbitrarily large integer starts remain exact. `start` may be positional or keyword, but not both.

- **Returns** `list<tuple>`

##### `zip(*iterables, strict=False)`

Combine iterables into tuples. With no args, returns empty list. With one arg, returns a list of 1-tuples. Stops at the shortest input unless `strict=True`, which raises if input lengths differ.

- **Returns** `list<tuple>`

##### `isinstance(value, type_or_tuple, /)`

Check if a value is of the given type. Accepts a builtin type callable (`object`, `int`, `float`, `str`, `list`, `dict`, `set`, `tuple`, `slice`, `bool`), a string type name, a tuple of types, or a type union like `int | float` (matches any). `int` matches whole numbers and booleans, `float` matches fractional / non-finite numbers, and string `"number"` remains the broad numeric family for scripts that intentionally accept either.

- **Returns** `boolean`

##### `callable(value, /)`

`True` when a value has a call surface: user-defined `def` / `lambda`, built-in functions, classes, bound methods, and class instances whose type defines `__call__`. Like Python, this checks the type-level call slot without executing its descriptor; an actual call can still raise if that slot resolves to a non-callable value.

- **Returns** `boolean`

##### `dir(value, /)`

Lists the method and attribute names available on `value`, sorted: runtime introspection for discovering what you can do with something. On a component or game object (`dir(self)`, `dir(get_component("smelter_1"))`) it returns that object's callable methods and properties, straight from the console. On a built-in container it returns the type's methods: `dir([1, 2])` → `"append"`, `"pop"`, …; `dir("hi")` → `"upper"`, `"split"`, …. Values with no members (numbers, booleans, `None`) return an empty list. Pass exactly one value: the no-argument `dir()` that lists current-scope names is not supported.

- **Returns** `list`

##### `hash(value, /)`

Hash any hashable value to an integer: strings, numbers, booleans, `None`, tuples of hashable values, functions, classes, and hashable user instances. Instances are identity-hashable by default; defining `__eq__` without `__hash__` makes them unhashable, and a custom `__hash__` controls `hash(obj)`, dict keys, and set membership.

- **Returns** `number`

##### `super() / super(type, object, /)`

Return a proxy that searches the receiver's MRO after a chosen class. Inside a method, use `super()` for cooperative parent calls such as `super().__init__(...)`. The explicit `super(type, object)` form accepts an instance or subclass of `type`; the one-argument form is not supported.

- **Returns** `any`

##### `issubclass(cls, class_or_tuple, /)`

`True` if `cls` is the given class or a subclass of it (or of any class in the tuple), per the MRO. `issubclass(Dog, Animal)` is `True`; every class is a subclass of `object`.

- **Returns** `boolean`

##### `property(fget=None, fset=None, fdel=None, doc=None)`

Build a property descriptor. Use `@property` for the common getter form, or call `property(fget, fset, fdel, doc)` directly; every argument is optional and may also be named. Instance reads call `fget`, writes call `fset`, and deletion calls `fdel`; an already-bound hook stays bound and receives the property instance as an additional argument. `.getter(fn)`, `.setter(fn)`, and `.deleter(fn)` return cloned descriptors. An omitted/`None` `doc` follows `fget.__doc__` through normal attribute lookup; an explicit non-`None` doc is preserved by clones.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `fget` | `any` | Optional instance getter |
| `fset` | `any` | Optional instance setter |
| `fdel` | `any` | Optional instance deleter |
| `doc` | `any` | Optional explicit descriptor doc value |

- **Returns** `property`

##### `classmethod(func, /)`

Wrap a function as a class method. Usually written `@classmethod`; the decorated method receives the class (conventionally `cls`) as its first argument and can be called on the class or an instance.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `any` | Function to bind to the class |

- **Returns** `any`

##### `staticmethod(func, /)`

Wrap a function as a static method. Usually written `@staticmethod`; the decorated method receives neither an instance nor the class and behaves as a plain function namespaced under the class.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `any` | Function to store without receiver binding |

- **Returns** `any`

##### `NotImplemented: NotImplemented`

The immutable singleton returned by an operator method to ask Python to try reflected dispatch or the normal fallback.

- **Returns** `NotImplemented`

##### `__debug__: boolean`

Immutable boolean constant, always `True` in game scripts. It may be read but cannot be assigned or deleted directly.

- **Returns** `boolean`

### Conversion

##### `str(value='', /)`

Convert a value to its string form. With no arguments, returns the empty string `''`.

- **Returns** `string`

##### `int(value=0, /, base?)`

Convert to integer. With no args returns `0`. Numbers truncate toward zero. String conversion consumes the whole trimmed value and accepts Python underscore separators and Unicode decimal digits. The optional `base` is 2-36 or `0`; `base=0` detects `0x` / `0b` / `0o` prefixes. Prefix and `base` forms retain arbitrary-size exact integers within the interpreter's integer budget.

- **Returns** `number`

##### `float(value=0.0, /)`

Convert to float. With no arguments, returns `0.0`. String conversion consumes the whole trimmed value and accepts Python decimal/exponent syntax, underscore separators, Unicode decimal digits, and case-insensitive `inf` / `nan`. Trailing garbage raises; booleans coerce to `0.0` / `1.0`.

- **Returns** `number`

##### `chr(code, /)`

Character from Unicode code point (e.g. chr(65) → 'A').

- **Returns** `string`

##### `ord(char, /)`

Unicode code point from character (e.g. ord('A') → 65).

- **Returns** `number`

##### `bool(value?, /)`

Convert to boolean (True/False). With no args returns False.

- **Returns** `boolean`

##### `list(iterable?, /)`

Convert any iterable to a list, or create an empty list with `list()`. Methods: `.append(x)`, `.pop([i])`, `.insert(i, x)`, `.remove(x)`, `.index(x [, start [, end]])`, `.count(x)`, `.sort()`, `.reverse()`, `.copy()`, `.extend(iter)`, `.clear()`, `.length` (property). Subscript with `lst[i]` and slice with `lst[start:end:step]`. See individual entries below for full Python-compliant semantics.

- **Returns** `list`

##### `dict(**kwargs) / dict(source, /, **kwargs)`

Build a dictionary. Empty form `dict()`. From pairs: `dict([("a", 1), ("b", 2)])`. Shallow-copy another dict: `dict(d)`. Keyword form: `dict(name="Mars", temp=-63)`. Keys may be any hashable value, including tuples of hashables and properly hashable user instances. Methods: `.keys()`, `.values()`, `.items()`, `.has(k)`, `.get(k, default?)`, `.pop(k, default?)`, `.popitem()`, `.setdefault(k, default?)`, `.update(other)`, `.copy()`, `.clear()`, `.length` (property). Operators: `a | b` returns a merged copy with right-hand values winning; `a |= b` updates `a` in place. Subscript with `d[k]`; missing key raises. Use `.get(k)` or `.has(k)` for safe lookup.

- **Returns** `dict`

##### `set(iterable?, /)`

Build a set of unique members from any iterable, or `set()` for empty. Members may be any hashable values, including tuples of hashables and properly hashable user instances. Use `{1, 2, 3}` for a literal: empty `{}` is a dict, not a set, so empty set is always `set()`. Methods: `.add(x)`, `.remove(x)`, `.discard(x)`, `.pop()`, `.clear()`, `.copy()`, `.union(s)`, `.intersection(s)`, `.difference(s)`, `.symmetric_difference(s)`, `.update(s)`, `.issubset(s)`, `.issuperset(s)`, `.isdisjoint(s)`. Operators: `in`, `|` (union), `&` (intersection), `-` (difference), `^` (symmetric difference), `<` `<=` `>=` `>` (subset/superset), `==`.

- **Returns** `set`

##### `tuple(iterable?, /)`

Build a tuple from any iterable, or `tuple()` for empty. Tuples are like lists but immutable (no `append` / `pop` / `sort`): useful for fixed records and as hashable keys. Methods: `.index(x)`, `.count(x)`, `.length` (property). Subscript and slice with `t[i]` / `t[a:b]` just like lists.

- **Returns** `tuple`

##### `hex(integer, /)`

Render an integer as a Python-style hex string with `0x` prefix. `hex(255)` → `'0xff'`, `hex(-16)` → `'-0x10'`. Floats reject.

- **Returns** `string`

##### `bin(integer, /)`

Render an integer as a binary string with `0b` prefix. `bin(10)` → `'0b1010'`. Floats reject.

- **Returns** `string`

##### `oct(integer, /)`

Render an integer as an octal string with `0o` prefix. `oct(8)` → `'0o10'`. Floats reject.

- **Returns** `string`

##### `repr(value, /)`

Developer-readable string for a value, with quotes around strings and nested-repr for containers. `repr([1, "a"])` → `"[1, 'a']"` (note the quotes around `'a'`). Use when you want to see the value's structure, not its display form. Also reached via f-string `!r` conversion: `f"{name!r}"`.

- **Returns** `string`

### Functional

##### `total_ordering(cls, /)`

Class decorator that preserves the class object and fills missing ordering methods from `__eq__` plus one of `__lt__`, `__le__`, `__gt__`, or `__ge__`. Explicit methods are never replaced. Applying it mutates the local class namespace.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `any` | Class to complete |

- **Returns** `any`

##### `wraps(wrapped, /)`

Return a decorator that preserves the wrapped callable's supported name, qualified name, docstring, custom attributes, and `__wrapped__` link while keeping the wrapper's call behavior. Applying the returned decorator mutates only that local wrapper function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `wrapped` | `any` | Callable whose metadata should be copied |

- **Returns** `any`

### Math

##### `abs(number, /)`

Absolute value.

- **Returns** `number`

##### `isclose(a, b, rel_tol=0.000000001, abs_tol=0.0)`

Return `True` when two numbers are close enough to treat as equal. `rel_tol` scales with the compared values; `abs_tol` sets a fixed accepted difference in the same unit, useful for values near zero and physical readings such as coordinates. Tolerances must be non-negative. This is the directly available equivalent of Python's `math.isclose()`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `number` | First number |
| `b` | `number` | Second number |
| `rel_tol` | `number` | Maximum relative difference |
| `abs_tol` | `number` | Maximum absolute difference in the values' unit |

- **Returns** `boolean`

##### `min(a, b, ...) / min(sequence, key=fn, default=v)`

Return the selected original value whose key is smallest under `<`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `<`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.

- **Returns** `any`

##### `max(a, b, ...) / max(sequence, key=fn, default=v)`

Return the selected original value whose key is largest under `>`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `>`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.

- **Returns** `any`

##### `round(number, ndigits=None)`

Round with ties to even. Without `ndigits` (or with `None`), returns the nearest whole value and rejects NaN/infinity. Integer and boolean inputs remain exact; negative `ndigits` rounds exact integers in decimal. Both arguments accept keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `number` | `number` | Value to round |
| `ndigits` | `any` | Decimal digits or None |

- **Returns** `number`

##### `pow(base, exp, mod=None)`

`base` raised to `exp`. Optional `mod` performs exact modular exponentiation and accepts negative exponents when the base has a modular inverse. `base`, `exp`, and `mod` accept positional or keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `base` | `number` | Base value |
| `exp` | `number` | Exponent |
| `mod` | `any` | Optional integer modulus |

- **Returns** `number`

##### `random()`

Random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.random()` after `import random`.

- **Returns** `number`

##### `rand()`

Short alias for `random()`: a random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.rand()` after `import random`.

- **Returns** `number`

##### `randint(min, max, /)`

Random integer `N` where `min <= N <= max`. Bounds are inclusive and must be whole numbers. Each successful run begins a new automatic sequence. Useful with `planet.get_bounds()` for random valid coordinates. Also available as `random.randint(min, max)` after `import random`.

- **Returns** `number`

##### `sqrt(number, /)`

Square root. Errors on negative input.

- **Returns** `number`

##### `floor(number, /)`

Round down to the nearest integer.

- **Returns** `number`

##### `ceil(number, /)`

Round up to the nearest integer.

- **Returns** `number`

##### `trunc(number, /)`

Drop the fractional part (round toward zero).

- **Returns** `number`

##### `divmod(a, b, /)`

Divides `a` by `b` and returns two values: the quotient rounded down, and the remainder left over. For example, `divmod(19, 2)` returns `(9, 1)` because 2 fits into 19 nine times with 1 left over.

- **Returns** `tuple<number>`

##### `sign(number, /)`

Returns `-1`, `0`, or `1` for negative, zero, or positive input.

- **Returns** `number`

##### `exp(number, /)`

`e` raised to the power of the argument.

- **Returns** `number`

##### `log(number, base?, /)`

Natural log, or log with the given base.

- **Returns** `number`

##### `log2(number, /)`

Base-2 logarithm.

- **Returns** `number`

##### `log10(number, /)`

Base-10 logarithm.

- **Returns** `number`

##### `sin(radians, /)`

Sine of an angle in radians.

- **Returns** `number`

##### `cos(radians, /)`

Cosine of an angle in radians.

- **Returns** `number`

##### `tan(radians, /)`

Tangent of an angle in radians.

- **Returns** `number`

##### `asin(number, /)`

Arc sine. Input must be in `-1 to 1`.

- **Returns** `number`

##### `acos(number, /)`

Arc cosine. Input must be in `-1 to 1`.

- **Returns** `number`

##### `atan(number, /)`

Arc tangent.

- **Returns** `number`

##### `atan2(y, x, /)`

Arc tangent of `y/x`, correctly choosing the quadrant.

- **Returns** `number`

##### `degrees(radians, /)`

Convert radians to degrees.

- **Returns** `number`

##### `radians(degrees, /)`

Convert degrees to radians.

- **Returns** `number`

##### `sum(iterable, /, start=0)`

Sum of every numeric item in an iterable. Optional `start` (number or list): `sum(list_of_lists, [])` flattens. `start` may be positional or keyword, but not both.

- **Returns** `number | list`

##### `prod(iterable, /, start=1)`

Product of every numeric item in an iterable. Empty iterables return `start`. `start` may be positional or keyword, but not both.

- **Returns** `number`

##### `inf: number`

Positive infinity, larger than every finite number. Use `-inf` for negative infinity, including as an initial best or worst value in search and pathfinding algorithms.

- **Returns** `number`

##### `pi: number`

Mathematical constant `π ≈ 3.14159`.

- **Returns** `number`

##### `tau: number`

Mathematical constant `τ = 2π`.

- **Returns** `number`

### Logic

##### `all(iterable, /)`

True if every item in the iterable is truthy. Stops at the first falsy item, so generators are consumed only as far as needed.

- **Returns** `boolean`

##### `any(iterable, /)`

True if any item in the iterable is truthy. Stops at the first truthy item, so generators are consumed only as far as needed.

- **Returns** `boolean`

### Iteration

##### `iter(iterable, /)`

Return an iterator. Built-in iterables use a compatibility list-shaped iterator; protocol iterators and generators keep their identity, so `iter(iterator) is iterator`. `for` advances generators and custom iterators one item at a time, so it can break out of an infinite iterator. Consumers that must finish, such as `list(...)`, remain bounded.

- **Returns** `list | generator`

##### `next(iterator, default?, /)`

Advance an iterator by one item. Iterators returned by `iter()` and custom `__next__` iterators retain their cursor across calls. Ordinary lists keep the compatibility behavior of popping the front; other non-iterator iterables return their first materialized item. Exhaustion raises `StopIteration` unless `default` is given.

- **Returns** `any`

##### `pairwise(iterable, /)`

Return neighboring pairs from an iterable. `pairwise([1,2,3])` → `[(1,2), (2,3)]`.

- **Returns** `list<tuple>`

##### `batched(iterable, size, /)`

Split an iterable into tuple batches of `size`. The final batch may be shorter. `batched([1,2,3,4,5], 2)` → `[(1,2), (3,4), (5,)]`.

- **Returns** `list<tuple>`

##### `starmap(fn, iterable, /)`

Call pure `fn` with each tuple/list item unpacked as arguments. The callback cannot suspend the script or mutate game state. `starmap(pow, [(2,3), (3,2)])` → `[8,9]`. An empty input never inspects or calls `fn`.

- **Returns** `list`

##### `flatten(iterable, /)`

Flatten one level of nested iterables into a list. `flatten([[1,2], (3,4)])` → `[1,2,3,4]`.

- **Returns** `list`

##### `count_by(iterable, key_fn?, /)`

Count items into a dict. Without `key_fn` (or with `None`), counts each item. With a pure `key_fn`, counts the computed key; callbacks cannot suspend the script or mutate game state: `count_by(items, lambda x: x.kind)`. An empty input never inspects or calls the key function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `any` | Values to count |
| `key_fn` | `any` | Optional function that maps each item to the key to count |

- **Returns** `dict<any, number>`

##### `chain(*iterables)`

Flattens any number of iterables into one list, in order. `chain([1,2], [3,4])` → `[1,2,3,4]`. Accepts lists, tuples, strings, sets.

- **Returns** `list`

##### `accumulate(iterable, /)`

Running prefix sum over any finite iterable. `accumulate([1,2,3,4])` → `[1,3,6,10]`. Numeric items only; booleans participate as integers and arbitrarily large integers remain exact.

- **Returns** `list<number>`

##### `combinations(iterable, k, /)`

All `k`-element combinations from an iterable, in input order, no repeats. Returns a list of tuples. `combinations([1,2,3], 2)` → `[(1,2), (1,3), (2,3)]`.

- **Returns** `list<tuple>`

##### `permutations(iterable, k?, /)`

All `k`-length ordered arrangements from an iterable. `k` defaults to the full length. `permutations([1,2,3])` → all 6 orderings as tuples.

- **Returns** `list<tuple>`

##### `product(*iterables, repeat=1)`

Cartesian product. `product([0,1], [0,1])` → `[(0,0), (0,1), (1,0), (1,1)]`. Each input must be iterable; result is a list of tuples. Optional keyword `repeat=N` repeats the input pools, matching `itertools.product([0,1], repeat=2)`.

- **Returns** `list<tuple>`

##### `map(fn, iter1, iter2?, ..., /, strict=False)`

Apply pure `fn` to corresponding items of each iterable. Callbacks cannot suspend the script or mutate game state. Single-iter form calls `fn(x)`; multi-iter form calls `fn(x, y, ...)` and stops at the shortest input unless `strict=True`, which raises if input lengths differ. If no row is produced, `fn` is never inspected or called.

- **Returns** `list`

##### `filter(fn, iterable, /)`

Keep items for which pure `fn(item)` is truthy; callbacks cannot suspend the script or mutate game state. `filter(None, iter)` keeps every truthy item without a callback. An empty input never inspects or calls `fn`.

- **Returns** `list`

##### `reduce(fn, iterable, initializer?, /)`

Combine an iterable into one value by repeatedly calling pure `fn(total, item)`; callbacks cannot suspend the script or mutate game state. With no initializer, the first item becomes the initial total; empty iterables then raise. Empty-with-initializer and singleton-without-initializer perform no callback call. Also available as `from functools import reduce`.

- **Returns** `any`

### Exceptions

##### `BaseException(message?, /)`

Root of the supported exception hierarchy.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `BaseException`

##### `Exception(message?, /)`

Base class matched by ordinary `except Exception:` handlers.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `Exception`

##### `ArithmeticError(message?, /)`

Base class for numeric calculation failures.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ArithmeticError`

##### `ValueError(message?, /)`

A value has the right type but an invalid value.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ValueError`

##### `TypeError(message?, /)`

An operation received a value of an inappropriate type.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `TypeError`

##### `PermissionError(message?, /)`

An operation is prohibited by the caller's ownership or access contract.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `PermissionError`

##### `ReferenceError(message?, /)`

A captured component or module handle is no longer valid.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ReferenceError`

##### `LookupError(message?, /)`

Base class for invalid mapping keys and sequence indexes.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `LookupError`

##### `KeyError(message?, /)`

A dictionary key is not present.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `KeyError`

##### `IndexError(message?, /)`

A sequence index is out of range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `IndexError`

##### `AttributeError(message?, /)`

An attribute reference failed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `AttributeError`

##### `RuntimeError(message?, /)`

A runtime failure does not fit a more specific category.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `RuntimeError`

##### `NotImplementedError(message?, /)`

A required operation or override is not implemented.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `NotImplementedError`

##### `RecursionError(message?, /)`

The interpreter's call-depth limit was exceeded.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `RecursionError`

##### `NameError(message?, /)`

A local, free, or global name could not be resolved.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `NameError`

##### `UnboundLocalError(message?, /)`

A statically local name was read before it was bound; this is a `NameError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `UnboundLocalError`

##### `ImportError(message?, /)`

An import could not provide the requested binding.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ImportError`

##### `ModuleNotFoundError(message?, /)`

An imported module could not be found; this is an `ImportError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ModuleNotFoundError`

##### `OverflowError(message?, /)`

A numeric conversion or bounded allocation exceeded its supported range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `OverflowError`

##### `ZeroDivisionError(message?, /)`

Division or modulo used a zero divisor.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `ZeroDivisionError`

##### `StopIteration(message?, /)`

An iterator was exhausted. Its `.value` contains a generator's return value, or `None`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `StopIteration`

##### `StopIteration.value`

The return value carried by a completed generator, or `None`.

- **Returns** `any`

##### `GeneratorExit(message?, /)`

Raised inside a generator when `close()` asks it to stop. It derives directly from `BaseException`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `GeneratorExit`

##### `AssertionError(message?, /)`

An `assert` statement failed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `AssertionError`

##### `SyntaxError(message?, /)`

Source could not be compiled.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `SyntaxError`

##### `IndentationError(message?, /)`

Source indentation is inconsistent; this is a `SyntaxError` subclass.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `message` | `any` | Optional positional exception message |

- **Returns** `IndentationError`

*Built-in Modules*

---

## random

Built-in random-number helpers. Each successful run gets a new automatic sequence; use random.seed(value) when you want a reproducible sequence. Works without Shared Library research.

##### `random.random()`

Random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.random()` after `import random`.

- **Returns** `number`

##### `random.rand()`

Short alias for `random()`: a random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.rand()` after `import random`.

- **Returns** `number`

##### `random.randint(min, max, /)`

Random integer `N` where `min <= N <= max`. Bounds are inclusive and must be whole numbers. Each successful run begins a new automatic sequence. Useful with `planet.get_bounds()` for random valid coordinates. Also available as `random.randint(min, max)` after `import random`.

- **Returns** `number`

##### `random.seed(a=None)`

Initialize random-number generation. Omit `a` or pass `None` to select another automatic sequence. Pass a number, boolean, or string to make later draws reproducible; the same value produces the same sequence.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `a` | `any` | Optional number, boolean, string, or None seed |

- **Returns** `None`

*Built-in Modules*

---

## functools

Built-in functional helpers. Works without Shared Library research.

##### `functools.reduce(fn, iterable, initializer?, /)`

Combine an iterable into one value by repeatedly calling pure `fn(total, item)`; callbacks cannot suspend the script or mutate game state. With no initializer, the first item becomes the initial total; empty iterables then raise. Empty-with-initializer and singleton-without-initializer perform no callback call. Also available as `from functools import reduce`.

- **Returns** `any`

##### `functools.total_ordering(cls, /)`

Class decorator that preserves the class object and fills missing ordering methods from `__eq__` plus one of `__lt__`, `__le__`, `__gt__`, or `__ge__`. Explicit methods are never replaced. Applying it mutates the local class namespace.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `any` | Class to complete |

- **Returns** `any`

##### `functools.wraps(wrapped, /)`

Return a decorator that preserves the wrapped callable's supported name, qualified name, docstring, custom attributes, and `__wrapped__` link while keeping the wrapper's call behavior. Applying the returned decorator mutates only that local wrapper function.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `wrapped` | `any` | Callable whose metadata should be copied |

- **Returns** `any`

##### `functools.partial(func, /, *args, **keywords)`

Return a new callable that calls `func` with some arguments already filled in. `partial(move, rover)` is a one-argument function; later positional arguments follow the bound ones and later keywords replace bound keywords of the same name. The result carries `.func`, `.args` and `.keywords`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `func` | `any` | Function to bind arguments to |
| `*args` | `any` | Positional arguments to bind now; arguments passed later follow them |
| `**keywords` | `any` | Keyword arguments to bind now; a keyword passed later replaces the bound one |

- **Returns** `any`

##### `functools.lru_cache(maxsize=128, typed=False)`

Decorator that remembers what the function returned for each set of arguments, so a repeat call returns the stored value instead of running the body. Use it on pure calculations that a loop repeats, never on a function that reads the world. A cached reading is frozen at the first call and will not follow the machine. The wrapped function gains `.cache_clear()` and `.cache_info()`. Arguments must be hashable, exactly as dict keys are.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `maxsize` | `any` | How many results to keep, **128** by default. Past that the least recently used one is dropped. `None` asks for no limit, which this game caps anyway so a script that runs all session cannot grow a cache forever |
| `typed` | `boolean` | Treat arguments of different types as different keys, so `f(1)` and `f(1.5)` never share a result |

- **Returns** `any`

##### `functools.cache(user_function, /)`

Decorator that remembers every result, the same as `lru_cache(maxsize=None)`. The same warning applies: cache calculations, never world readings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `user_function` | `any` | Function to memoize |

- **Returns** `any`

*Built-in Modules*

---

## re

Built-in regular-expression helpers. Works without Shared Library research. Patterns use a linear-time safe regular expression subset.

##### `re.IGNORECASE: number`

Case-insensitive matching flag. Short alias: `re.I`.

- **Returns** `number`

##### `re.MULTILINE: number`

`^` and `$` also match line boundaries. Short alias: `re.M`.

- **Returns** `number`

##### `re.DOTALL: number`

`.` also matches newline characters. Short alias: `re.S`.

- **Returns** `number`

##### `re.I: number`

Short alias for `re.IGNORECASE`.

- **Returns** `number`

##### `re.M: number`

Short alias for `re.MULTILINE`.

- **Returns** `number`

##### `re.S: number`

Short alias for `re.DOTALL`.

- **Returns** `number`

##### `re.search(pattern, string, flags=0)`

Search anywhere in `string` for `pattern`. Returns a `Match` object, or `None` if there is no match. Patterns use the documented safe regular expression subset.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `string` | `string` | String to search |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Optional[Match]`

##### `re.match(pattern, string, flags=0)`

Match `pattern` at the start of `string`. Returns a `Match` object, or `None` if the start does not match.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `string` | `string` | String to check |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Optional[Match]`

##### `re.fullmatch(pattern, string, flags=0)`

Match the whole `string` against `pattern`. Returns a `Match` object, or `None` if any part is left unmatched.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `string` | `string` | String to check |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `Optional[Match]`

##### `re.findall(pattern, string, flags=0)`

Return all non-overlapping matches. With no capture groups, the result is a list of matched strings. With one capture group, the result is that group. With multiple capture groups, the result is tuples.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `string` | `string` | String to search |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

##### `re.sub(pattern, repl, string, count=0, flags=0)`

Replace matches of `pattern` in `string` with `repl`. `count=0` replaces all matches; a positive count limits replacements. Replacement text supports numeric backreferences like `\1` and `\g<1>`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `repl` | `string` | Replacement text |
| `string` | `string` | String to transform |
| `count` | `number` | Maximum replacements; 0 means all |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `string`

##### `re.split(pattern, string, maxsplit=0, flags=0)`

Split `string` wherever `pattern` matches. `maxsplit=0` means no limit. Capturing groups are included in the output, matching Python's `re.split` behavior.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pattern` | `string` | Regular expression pattern |
| `string` | `string` | String to split |
| `maxsplit` | `number` | Maximum splits; 0 means all |
| `flags` | `number` | Optional flags such as `re.IGNORECASE` |

- **Returns** `list`

*Built-in Modules*

---

## dataclasses

Built-in record-class helpers. Works without Shared Library research. Generates concise user-class value objects; use TypedDict for JSON-shaped records.

##### `dataclasses.MISSING: any`

Sentinel telling a field with no default apart from one that defaults to `None`. Test it with `field.default is MISSING`.

- **Returns** `any`

##### `dataclasses.dataclass(cls?, /, *, init=True, repr=True, eq=True, order=False, kw_only=False, unsafe_hash=False, frozen=False, slots=False, weakref_slot=False)`

Decorate a class to generate declaration-ordered construction, representation, value equality, and optional ordering. Supports both `@dataclass` and `@dataclass(...)`, inherited fields, `__post_init__`, and explicit-method preservation. Generated behavior is controlled by `init`, `repr`, `eq`, `order`, and `kw_only`. Compatibility flags `unsafe_hash`, `frozen`, `slots`, and `weakref_slot` may be passed only as `False`; their `True` behavior and every unlisted standard-library option are rejected rather than ignored. Dataclass instances remain ordinary user objects and cannot cross JSON-shaped game API boundaries.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `cls` | `any` | Optional class for functional or bare-decorator use |
| `init` | `boolean` | Generate __init__ (default True) |
| `repr` | `boolean` | Generate __repr__ (default True) |
| `eq` | `boolean` | Generate exact-class __eq__ (default True) |
| `order` | `boolean` | Generate ordering methods (default False) |
| `kw_only` | `boolean` | Make generated constructor fields keyword-only (default False) |
| `unsafe_hash` | `boolean` | Compatibility flag; only False is supported |
| `frozen` | `boolean` | Compatibility flag; only False is supported |
| `slots` | `boolean` | Compatibility flag; only False is supported |
| `weakref_slot` | `boolean` | Compatibility flag; only False is supported |

- **Returns** `any`

##### `dataclasses.field(*, default?, default_factory?, init=True, repr=True, compare=True, kw_only?)`

Configure one annotated dataclass field. Use `default` for an immutable or hashable shared value, or `default_factory` for a zero-argument factory that creates an independent value per instance; supplying both is an error. Mutable or otherwise unhashable direct defaults are rejected and must use `default_factory`. `init` controls constructor inclusion, `repr` controls generated display, `compare` controls equality and ordering, and `kw_only` controls that field's constructor position. Field metadata/introspection, `hash`, and every unlisted standard-library option are not supported.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `any` | Optional immutable or hashable shared value; mutable or unhashable values must use default_factory |
| `default_factory` | `any` | Optional zero-argument factory |
| `init` | `boolean` | Include this field in the generated constructor (default True) |
| `repr` | `boolean` | Include this field in generated representation (default True) |
| `compare` | `boolean` | Include this field in generated equality and ordering (default True) |
| `kw_only` | `boolean` | Make this constructor field keyword-only |

- **Returns** `any`

##### `dataclasses.asdict(obj, /)`

Return a record-class instance as a dict, recursing into nested record classes, lists, tuples, dicts and sets. Dict keys are converted too, so a record class used as a key raises `TypeError` here rather than surviving into a result that cannot be sent. This is the bridge out of a class: the result is accepted by `json.dumps()`, `comms.send()` and the Data Archive, which all refuse a class instance. Values that are not containers are placed in the result as they are, not copied, so a shared list stays shared.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Record-class instance to convert |

- **Returns** `dict`

##### `dataclasses.astuple(obj, /)`

Return a record-class instance as a tuple of its field values, recursing the same way `asdict()` does. Useful as a sort key or a dict key when every field is hashable.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Record-class instance to convert |

- **Returns** `tuple`

##### `dataclasses.fields(obj, /)`

Return one `Field` per declared field, in declaration order. Accepts a record class or one of its instances.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Record class or instance to inspect |

- **Returns** `tuple<Field>`

##### `dataclasses.replace(obj, /, **changes)`

Return a new instance with the named fields changed and every other field copied from `obj`. The class is constructed normally, so `__init__` runs again. A field declared `init=False` cannot be replaced.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Record-class instance to copy |
| `**changes` | `any` | Fields to set by name; every other field is copied from `obj` |

- **Returns** `any`

##### `dataclasses.is_dataclass(obj, /)`

True when the value is a record class or an instance of one.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Value to test |

- **Returns** `boolean`

*Built-in Modules*

---

## json

Built-in JSON text helpers. Turns records into text and back, using the same value shapes the Signal Bus and Data Archive accept. Works without Shared Library research.

##### `json.dumps(obj, /, *, indent=None, sort_keys=False, ensure_ascii=True, separators=None, allow_nan=True, skipkeys=False)`

Return `obj` as JSON text. Accepts `None`, booleans, numbers, strings, lists, tuples and dicts whose keys are strings, numbers, booleans or `None`, the same shapes the Signal Bus and Data Archive store. A set, a class instance or a function raises `TypeError`; convert it first, for example with `dataclasses.asdict()`. A container that contains itself raises `ValueError`, and one nested deeper than **256** levels raises `RecursionError`, which is the same depth `loads()` reads back.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `obj` | `any` | Value to write as JSON text |
| `indent` | `any` | `None` for one compact line, a number of spaces, or the literal text to indent each level with |
| `sort_keys` | `boolean` | Write object keys in sorted order, so two equal dicts built in a different order produce identical text. Use this whenever the text is a cache key. The keys themselves are sorted, so numeric keys order numerically (**1, 2, 10**) and a dict mixing key types Python cannot compare raises `TypeError` |
| `ensure_ascii` | `boolean` | Escape every non-ASCII character as `\uXXXX`. Pass `False` to write the characters directly |
| `separators` | `any` | A two-item `(item, key)` tuple of strings replacing the defaults `(", ", ": ")` |
| `allow_nan` | `boolean` | Write `nan` and infinities as `NaN`, `Infinity` and `-Infinity`. Pass `False` to raise `ValueError` instead. Note that those three spellings are not standard JSON, and a value that round-trips here can still be refused by `comms.send()` and the Data Archive |
| `skipkeys` | `boolean` | Silently drop dict entries whose key has no JSON spelling instead of raising `TypeError` |

- **Returns** `string`

##### `json.loads(s, /)`

Read JSON text and return the value: `None`, a boolean, a number, a string, a list, or a dict with string keys. Malformed text raises `ValueError` naming the line, column and character position. Note that a whole number always comes back as an int, because in this language a whole float IS an int.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `s` | `string` | JSON text to read |

- **Returns** `any`

*Built-in Modules*

---

## heapq

Built-in priority-queue helpers. Keeps an ordinary list arranged so the smallest item is always first. Works without Shared Library research.

##### `heapq.heappush(heap, item, /)`

Add `item` to `heap`, keeping the smallest item at `heap[0]`. The heap is an ordinary list, so `len()` and `heap[0]` work as usual, and only the ordering of the rest is the heap's business.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `any` | Value to add |

- **Returns** `None`

##### `heapq.heappop(heap, /)`

Remove and return the smallest item, keeping the heap arranged. Raises `IndexError` on an empty heap, so check `len(heap)` first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |

- **Returns** `any`

##### `heapq.heappushpop(heap, item, /)`

Add `item` and return the smallest item, in one pass. Faster than a push followed by a pop, and never grows the heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `any` | Value to add |

- **Returns** `any`

##### `heapq.heapreplace(heap, item, /)`

Return the smallest item and add `item`, in one pass. The heap keeps its size. Raises `IndexError` on an empty heap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `heap` | `list` | List arranged as a heap by the other heapq functions |
| `item` | `any` | Value to add |

- **Returns** `any`

##### `heapq.heapify(x, /)`

Rearrange an existing list into a heap, in place. Cheaper than pushing the items one at a time.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `list` | List to rearrange in place |

- **Returns** `None`

##### `heapq.nsmallest(n, iterable, /, key=None)`

Return the `n` smallest items as a sorted list. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `number` | How many items to return |
| `iterable` | `any` | Values to choose from |
| `key` | `any` | Optional function called once per item; the returned values are compared instead of the items |

- **Returns** `list`

##### `heapq.nlargest(n, iterable, /, key=None)`

Return the `n` largest items as a list, largest first. Pass `key=` to compare something derived from each item, exactly as `sorted()` does.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `number` | How many items to return |
| `iterable` | `any` | Values to choose from |
| `key` | `any` | Optional function called once per item; the returned values are compared instead of the items |

- **Returns** `list`

*Built-in Modules*

---

## traceback

Built-in traceback helpers. Report where a caught exception came from, frame by frame. Works without Shared Library research.

##### `traceback.format_exc()`

Return the traceback of the exception currently being handled, as a string: the chain of calls that led to it, innermost last, each with its file, line and function. Call it inside an `except` block. Outside one it returns `NoneType: None`.

- **Returns** `string`

##### `traceback.print_exc()`

Write the traceback of the exception currently being handled to the console's error output. Same text as `format_exc()`, printed instead of returned. This is the answer to "the message says what broke, but where?" for an exception your own code caught.

- **Returns** `None`

*Built-in Modules*

---

## System

##### `get_game_version()`

Read the current game's build identifier, matching the version at the bottom right of Settings and in feedback reports. Available before boot and from shared Libraries on every platform. Use it to identify an exact build when sharing scripts; build hashes cannot be compared as newer or older versions.

- **Returns** String containing the seven-character commit hash, or `"dev"` in an unstamped development or test environment.

```python
print(get_game_version())
```

##### `boot()`

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

##### `activate_power()`

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

##### `activate_sensors()`

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

##### `get_component(name)`

Access a player-owned entity by its **immutable id** (e.g. `"solar_3"`, `"outpost_home"`). The id is auto-generated on creation and never changes: use this in scripts that need to outlive renames. To look up by display name (mutable), use `get_component_by_name(name)`. Returns `None` if no entity has the given id.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `string` | Entity id (machine or outpost) |

- **Returns** Component object

```python
clock = get_component("clock")
time = clock.get_time()
print(time)
```

##### `get_component_by_name(name)`

Look up any addressable player-owned component (machine or outpost) by its display name. Names default to the entity's id but can be freely renamed from the Computer System tab; uniqueness is enforced across the shared rename namespace. Custom Panels share that namespace but are not components, so they are not returned here. Mutable: `get_component(id)` is the stable form for long-running scripts. Returns `None` if no component has the given name.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `name` | `string` | The entity's display name |

- **Returns** Component (machine or outpost), or None if no component by that name exists

```python
ore_bin = get_component_by_name("Iron Stockpile")
print(ore_bin.count("iron_ore"))
```

*Commands*

---

## Infrastructure

##### `get_pipe(pipe_id)`

Look up an infrastructure pipe by id. Returns a live read-only `Pipe` handle, or `None` if no pipe by that id exists.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `pipe_id` | `string` | Pipe id (from `list_pipes()`) |

- **Returns** Live read-only `Pipe` handle or `None`

```python
pipe = get_pipe("pipe_1")
if pipe != None:
    print(pipe.state())
```

##### `list_pipes()`

List every infrastructure pipe currently laid (complete or in-progress) as live read-only `Pipe` handles.

- **Returns** List of live read-only `Pipe` handles

```python
for pipe in list_pipes():
    print(pipe.id, pipe.state())
```

*Built-in Functions*

---
