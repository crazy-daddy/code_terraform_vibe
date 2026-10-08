# Data Types: Built In Types

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`Counter`](#counter) (BUILT-IN TYPES)
- [`defaultdict`](#defaultdict) (BUILT-IN TYPES)
- [`deque`](#deque) (BUILT-IN TYPES)
- [`dict`](#dict) (BUILT-IN TYPES)
- [`float`](#float) (BUILT-IN TYPES)
- [`generator`](#generator) (BUILT-IN TYPES)
- [`int`](#int) (BUILT-IN TYPES)
- [`list`](#list) (BUILT-IN TYPES)
- [`OrderedDict`](#ordereddict) (BUILT-IN TYPES)
- [`set`](#set) (BUILT-IN TYPES)
- [`slice`](#slice) (BUILT-IN TYPES)
- [`str`](#str) (BUILT-IN TYPES)
- [`tuple`](#tuple) (BUILT-IN TYPES)
- [`CacheInfo`](#cacheinfo) (BUILT-IN MODULES)
- [`Field`](#field) (BUILT-IN MODULES)
- [`Match`](#match) (BUILT-IN MODULES)
- [`Pattern`](#pattern) (BUILT-IN MODULES)

---

## Counter

**Returned by:** `Counter(iterable)` from `collections`

### Methods

##### `.most_common(n: int | None = None, /) → list[tuple[K, int]]`

The counts from highest to lowest as `(item, count)` pairs; with `n`, only the top `n`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int \| None` | How many of the largest counts (default all) |

- **Returns** `list[tuple[K, int]]`

##### `.elements() → Iterator[K]`

Each item repeated as many times as its count, skipping counts below one.

- **Returns** `Iterator[K]`

##### `.total() → int`

The sum of all counts.

- **Returns** `int`

##### `.update(iterable: object = None, /, **kwargs: int) → None`

Add counts from an iterable of items, a mapping of counts, or keywords.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `object` | Items to count, or a mapping of counts to add |
| `**kwargs` | `int` | Counts to add by name |

- **Returns** `None`

##### `.subtract(iterable: object = None, /, **kwargs: int) → None`

Take counts away, the opposite of `update`; a count may go to zero or below.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `object` | Items to uncount, or a mapping of counts to take away |
| `**kwargs` | `int` | Counts to take away by name |

- **Returns** `None`

##### `.copy() → Counter[K]`

A new `Counter` with the same counts.

- **Returns** `Counter[K]`

*Types / Built-in Types*

## defaultdict

**Returned by:** `defaultdict(factory)` from `collections`

### Properties

##### `.default_factory: Callable | None`

The function called to make a missing key's value, or `None`.

- **Returns** `Callable | None`

### Methods

##### `.copy() → defaultdict[K, V]`

A new `defaultdict` with the same items and factory.

- **Returns** `defaultdict[K, V]`

*Types / Built-in Types*

## deque

**Returned by:** `deque(iterable)` from `collections`

### Properties

##### `.maxlen: int | None`

The size limit given when the `deque` was made, or `None`.

- **Returns** `int | None`

### Methods

##### `.append(x: T, /) → None`

Add an item to the right end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `T` | Item to add |

- **Returns** `None`

##### `.appendleft(x: T, /) → None`

Add an item to the left end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `T` | Item to add |

- **Returns** `None`

##### `.pop() → T`

Remove and return the rightmost item.

- **Returns** `T`

##### `.popleft() → T`

Remove and return the leftmost item.

- **Returns** `T`

##### `.extend(iterable: Iterable[T], /) → None`

Add every item of an iterable to the right end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to add |

- **Returns** `None`

##### `.extendleft(iterable: Iterable[T], /) → None`

Add every item of an iterable to the left end, one at a time, so they end up reversed.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Items to add |

- **Returns** `None`

##### `.rotate(n: int = 1, /) → None`

Move items from the right end to the left `n` times, or the other way when `n` is negative.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `n` | `int` | Steps to rotate |

- **Returns** `None`

##### `.clear() → None`

Remove every item.

- **Returns** `None`

##### `.copy() → deque[T]`

A new `deque` with the same items and `maxlen`.

- **Returns** `deque[T]`

##### `.count(x: object, /) → int`

How many items equal `x`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `object` | Value to count |

- **Returns** `int`

##### `.index(x: object, start: int = 0, stop: int | None = None, /) → int`

Position of the first item equal to `x`, searching from `start` up to `stop`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `object` | Value to find |
| `start` | `int` | First position to search |
| `stop` | `int \| None` | Position to stop before |

- **Returns** `int`

##### `.insert(i: int, x: T, /) → None`

Insert `x` before position `i`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `i` | `int` | Position to insert before |
| `x` | `T` | Item to insert |

- **Returns** `None`

##### `.remove(value: object, /) → None`

Remove the first item equal to `value`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value to remove |

- **Returns** `None`

##### `.reverse() → None`

Reverse the items in place.

- **Returns** `None`

*Types / Built-in Types*

## dict

**Returned by:** `dict` literals `{k: v}` · `dict()` · methods returning a `dict`

### Properties

##### `.length: int`

Number of key-value pairs. Same as `len(d)`. Property: no parens.

- **Returns** `int`

### Methods

##### `.keys() → list[K]`

Return a list of all keys, in insertion order.

- **Returns** `list[K]`

##### `.values() → list[V]`

Return a list of all values, in insertion order.

- **Returns** `list[V]`

##### `.items() → list[tuple[K, V]]`

Return a list of `(key, value)` tuples, in insertion order. Common pattern: `for k, v in d.items(): ...`.

- **Returns** `list[tuple[K, V]]`

##### `.has(key: K, /) → bool`

`True` if `key` is in the dictionary. Equivalent to Python's `key in d`. Use this for safe membership tests before subscript.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `K` | Key to check |

- **Returns** `bool`

##### `.get(key: K, default: V | None = None, /) → V`

Return the value for `key`, or `default` (`None` if omitted) if the key is missing. Never raises for a missing hashable key; an unhashable key still raises `TypeError`, matching Python.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `K` | Key to look up |
| `default` | `V \| None` | Value to return if missing |

- **Returns** `V`

##### `.pop(key: K, default?: V, /) → V`

Remove `key` and return its value. Raises if the key isn't present unless a `default` is provided: in that case the missing-key path returns `default` and the dict is unchanged. Matches Python's `dict.pop(k, default)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `K` | Key to remove |
| `default` | `V` | Value to return if the key is missing |

- **Returns** `V`

##### `.popitem() → tuple[K, V]`

Remove and return the last inserted `(key, value)` pair. Raises if the dictionary is empty. Insertion order is deterministic, but use this only when consuming a `dict` as a stack is what you intend.

- **Returns** `tuple[K, V]`

##### `.setdefault(key: K, default: V | None = None, /) → V`

Return `d[key]` if it exists; otherwise set `d[key] = default` and return `default`. Useful for building grouped collections.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `K` | Key |
| `default` | `V \| None` | Value to set if missing |

- **Returns** `V`

##### `.update(other?: dict[K, V] | Iterable[tuple[K, V]], /, **kwargs: V) → None`

Merge entries into this `dict`, overwriting matching keys. Accepts another `dict`, an iterable of `(key, value)` pairs, keyword args, OR a combination: `d.update(other, a=1, b=2)`. Mutates in place.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `dict[K, V] \| Iterable[tuple[K, V]]` | A `dict`, or an iterable of `(key, value)` pairs |
| `kwargs` | `V` | More entries, by keyword (`speed=2`) |

- **Returns** `None`

##### `.fromkeys(iterable: Iterable[object], value: object = None, /) → dict`

A new `dict` with every item of `iterable` as a key, each set to `value`: `dict.fromkeys(["iron", "copper"], 0)` → `{"iron": 0, "copper": 0}`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[object]` | Keys for the new `dict` |
| `value` | `object` | Value for every key (default `None`) |

- **Returns** `dict`

##### `.copy() → dict[K, V]`

Return a shallow copy of the dictionary. Top-level keys/values are duplicated to a fresh `dict`; nested mutable values (`list` and `dict` values) are shared with the original.

- **Returns** `dict[K, V]`

##### `.clear() → None`

Remove all entries.

- **Returns** `None`

*Types / Built-in Types*

## float

**Returned by:** decimal literals · `float(value)` · division with `/`

### Properties

##### `.real: float`

The number itself, so any number can be read as `x.real`.

- **Returns** `float`

##### `.imag: float`

Always `0`: a real number has no imaginary part.

- **Returns** `float`

### Methods

##### `.conjugate() → float`

The number itself.

- **Returns** `float`

##### `.as_integer_ratio() → tuple[int, int]`

The exact fraction the number holds, in lowest terms: `(0.75).as_integer_ratio()` → `(3, 4)`.

- **Returns** `tuple[int, int]`

##### `.is_integer() → bool`

`True` when the number has no fractional part: `(2.0).is_integer()` → `True`.

- **Returns** `bool`

*Types / Built-in Types*

## generator

**Returned by:** calling a function containing `yield` · generator expressions

### Properties

##### `.__name__: str`

Name of the generator function that created this generator.

- **Returns** `str`

##### `.__qualname__: str`

Qualified name of the generator function that created this generator.

- **Returns** `str`

### Methods

##### `.send(value: object) → T`

Resume the generator and make `value` the result of its paused `yield`. Returns the next yielded value. Sending a non-`None` value before the first `yield` raises `TypeError`; completion raises `StopIteration`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value delivered to the paused `yield` |

- **Returns** `T`

##### `.throw(exception: BaseException | type) → T`

Raise an exception at the generator's paused `yield`. Returns the next value if the generator catches it and yields again; otherwise the exception propagates.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `exception` | `BaseException \| type` | Exception instance or exception class |

- **Returns** `T`

##### `.close() → None`

Stop the generator by raising `GeneratorExit` at its paused `yield`. `finally` cleanup runs before this returns. A generator that yields while closing raises `RuntimeError`.

- **Returns** `None`

##### `.__iter__() → generator`

Return this generator. Generators are one-shot iterators.

- **Returns** `generator`

##### `.__next__() → T`

Resume the generator with `None` and return its next yielded value. Completion raises `StopIteration`.

- **Returns** `T`

*Types / Built-in Types*

## int

**Returned by:** whole-number literals · `int(value)` · `len()` and other counts

### Properties

##### `.real: int`

The number itself, so any number can be read as `x.real`.

- **Returns** `int`

##### `.imag: int`

Always `0`: a real number has no imaginary part.

- **Returns** `int`

##### `.numerator: int`

The number itself, as the top of a fraction over 1.

- **Returns** `int`

##### `.denominator: int`

Always `1`.

- **Returns** `int`

### Methods

##### `.conjugate() → int`

The number itself.

- **Returns** `int`

##### `.bit_length() → int`

How many binary digits the number needs, ignoring its sign: `(10).bit_length()` → `4`.

- **Returns** `int`

##### `.bit_count() → int`

How many 1 bits the number has, ignoring its sign: `(7).bit_count()` → `3`.

- **Returns** `int`

##### `.as_integer_ratio() → tuple[int, int]`

The number as a fraction: `(6).as_integer_ratio()` → `(6, 1)`.

- **Returns** `tuple[int, int]`

##### `.is_integer() → bool`

Always `True` for a whole number.

- **Returns** `bool`

*Types / Built-in Types*

## list

**Returned by:** list literals `[1, 2, 3]` · `list(iterable)` · methods returning lists

### Properties

##### `.length: int`

Number of items in the list. Same as `len(lst)`. Property: no parens.

- **Returns** `int`

### Methods

##### `.append(item: T, /) → None`

Add `item` to the end of the list. Returns `None`. Mutates in place. Raises if the list would exceed the interpreter's max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to append |

- **Returns** `None`

##### `.pop(index: int = -1, /) → T`

Remove and return one element. Default removes the last (`pop()`). Pass an integer index to remove a specific item: `lst.pop(0)` removes the first, `lst.pop(-1)` removes the last. Negative indices count from the end. Empty list or out-of-range index raises an error. Non-integer index raises.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Position to remove (default: -1, the last item) |

- **Returns** `T`

##### `.remove(item: T, /) → None`

Remove the first occurrence of `item` by value. Raises if not found. Use `item in lst` first if you need to check.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to remove |

- **Returns** `None`

##### `.insert(index: int, item: T, /) → None`

Insert `item` at position `index`, shifting later items right. `insert(0, x)` puts `x` at the front. Out-of-range indices clamp to the ends (no error). Raises if the list would exceed the max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Position |
| `item` | `T` | Value |

- **Returns** `None`

##### `.index(item: T, start: int = 0, end?: int, /) → int`

Return the index of the first occurrence of `item`. Optional `start` and `end` restrict the search to a slice (Python-style: negative indices count from the end, clamped to bounds). Raises if not found within the range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to find |
| `start` | `int` | Start index (default 0) |
| `end` | `int` | End index, exclusive (default length) |

- **Returns** `int`

##### `.count(item: T, /) → int`

Count occurrences of `item` in the list. Equality is by value (numbers, strings, booleans compared deeply).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to count |

- **Returns** `int`

##### `.sort(*, key: Callable | None = None, reverse: bool = False) → None`

Sort the list **in place** using `<` between mutually comparable keys. With `key=None` (the default), each value is its own key. Numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may define the exact rich-comparison slots needed by `<`; unsupported pairs raise. `key=` is called once per item and must be **pure**: it cannot suspend the script or mutate game state. `reverse` is truth-tested, and the finite input is handled eagerly within the interpreter's collection limit.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `Callable \| None` | Function returning the value to compare for each item |
| `reverse` | `bool` | `True` to sort from largest to smallest |

- **Returns** `None`

##### `.reverse() → None`

Reverse the list in place. Returns `None`.

- **Returns** `None`

##### `.copy() → list[T]`

Return a shallow copy of the list. Modifying the copy does not affect the original; nested mutable items are shared.

- **Returns** `list[T]`

##### `.extend(iterable: Iterable[T], /) → None`

Append every item from another finite iterable to the end of this list. Mutates in place. Raises if the result would exceed the max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[T]` | Finite iterable of items to append |

- **Returns** `None`

##### `.clear() → None`

Remove all items. Returns `None`. Equivalent to `lst[:] = []`.

- **Returns** `None`

*Types / Built-in Types*

## OrderedDict

**Returned by:** `OrderedDict(...)` from `collections`

### Methods

##### `.move_to_end(key: K, last: bool = True) → None`

Move an existing key to the end, or to the front with `last=False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `K` | Key to move |
| `last` | `bool` | `True` for the end, `False` for the front |

- **Returns** `None`

##### `.popitem(last: bool = True) → tuple[K, V]`

Remove and return the last `(key, value)` pair, or the first with `last=False`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `last` | `bool` | `True` for the last pair, `False` for the first |

- **Returns** `tuple[K, V]`

##### `.copy() → OrderedDict[K, V]`

A new `OrderedDict` with the same items.

- **Returns** `OrderedDict[K, V]`

*Types / Built-in Types*

## set

**Returned by:** set literals `{1, 2}` · `set(iterable)` · set algebra operators

### Properties

##### `.length: int`

Number of unique members. Same as `len(s)`. Property: no parens.

- **Returns** `int`

### Methods

##### `.add(item: T, /) → None`

Add `item` to the set. No effect if already present. The item may be any hashable value, including tuples of hashables and properly hashable user-class instances.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to add |

- **Returns** `None`

##### `.remove(item: T, /) → None`

Remove `item`. Raises if not present. Use `.discard()` for the safe form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to remove |

- **Returns** `None`

##### `.discard(item: T, /) → None`

Remove `item` if present. No error if absent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to remove |

- **Returns** `None`

##### `.pop() → T`

Remove and return an arbitrary element. Order is deterministic (insertion order) but scripts shouldn't rely on it. Raises if the set is empty.

- **Returns** `T`

##### `.clear() → None`

Remove all members.

- **Returns** `None`

##### `.copy() → set[T]`

Return a shallow copy.

- **Returns** `set[T]`

##### `.has(item: T, /) → bool`

`True` if `item` is in the set. Equivalent to Python's `item in s`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to check |

- **Returns** `bool`

##### `.union(*others: Iterable[T]) → set[T]`

Return a new set with members from this set and every finite iterable in `others`. With no arguments, returns a copy.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `set[T]`

##### `.intersection(*others: Iterable[T]) → set[T]`

Return a new set containing members shared with every finite iterable in `others`. With no arguments, returns a copy.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `set[T]`

##### `.difference(*others: Iterable[T]) → set[T]`

Return a new set without members found in any finite iterable in `others`. With no arguments, returns a copy.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `set[T]`

##### `.symmetric_difference(other: Iterable[T], /) → set[T]`

Return a new set with members in exactly one of this set and the finite iterable `other`. Same as `a ^ b`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Iterable[T]` | Finite iterable |

- **Returns** `set[T]`

##### `.update(*others: Iterable[T]) → None`

Add every member from each finite iterable in `others`. Mutates in place; with no arguments, does nothing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `None`

##### `.intersection_update(*others: Iterable[T]) → None`

Keep only members shared with every finite iterable in `others`. Mutates in place; with no arguments, does nothing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `None`

##### `.difference_update(*others: Iterable[T]) → None`

Remove members found in any finite iterable in `others`. Mutates in place; with no arguments, does nothing.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `others` | `Iterable[T]` | Other collections |

- **Returns** `None`

##### `.symmetric_difference_update(other: Iterable[T], /) → None`

Replace this set with members in exactly one of this set and the finite iterable `other`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Iterable[T]` | Finite iterable |

- **Returns** `None`

##### `.issubset(other: Iterable[T], /) → bool`

`True` if every member of this set is also in the finite iterable `other`. Same as `a <= b` for sets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Iterable[T]` | Finite iterable |

- **Returns** `bool`

##### `.issuperset(other: Iterable[T], /) → bool`

`True` if this set contains every member of the finite iterable `other`. Same as `a >= b` for sets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Iterable[T]` | Finite iterable |

- **Returns** `bool`

##### `.isdisjoint(other: Iterable[T], /) → bool`

`True` if this set and the finite iterable `other` share no members.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `Iterable[T]` | Finite iterable |

- **Returns** `bool`

*Types / Built-in Types*

## slice

**Returned by:** `slice(stop)` · `slice(start, stop, step)`

### Properties

##### `.start: float | None`

Start bound, or `None` when omitted. For `slice(stop)`, `.start` is `None` and `.stop` is the argument.

- **Returns** `float | None`

##### `.stop: float | None`

Stop bound, or `None` when omitted.

- **Returns** `float | None`

##### `.step: float | None`

Step bound, or `None` when omitted. Sequence indexing rejects a step of `0`.

- **Returns** `float | None`

*Types / Built-in Types*

## str

**Returned by:** string literals · `str(value)` · methods returning strings

### Properties

##### `.length: int`

Number of characters in the string. Same as `len(s)`. Property: no parens.

- **Returns** `int`

### Methods

##### `.upper() → str`

Return a copy with all characters in uppercase.

- **Returns** `str`

##### `.lower() → str`

Return a copy with all characters in lowercase.

- **Returns** `str`

##### `.strip(chars: str | None = None, /) → str`

Return a copy with whitespace (or `chars` if given) trimmed from both ends. Passing `None` explicitly is the same as omitting `chars`. `chars` is treated as a SET of characters to strip, not a substring: `"...hello...".strip(".")` → `"hello"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `str \| None` | Characters to strip, or `None` for whitespace |

- **Returns** `str`

##### `.lstrip(chars: str | None = None, /) → str`

Like `strip()` but only trims from the left end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `str \| None` | Characters to strip, or `None` for whitespace |

- **Returns** `str`

##### `.rstrip(chars: str | None = None, /) → str`

Like `strip()` but only trims from the right end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `str \| None` | Characters to strip, or `None` for whitespace |

- **Returns** `str`

##### `.split(sep: str | None = None, maxsplit: int = -1) → list[str]`

Split into substrings. With `sep=None`, every Python whitespace character separates words, runs collapse, and leading/trailing whitespace is ignored unless a finite `maxsplit` leaves it in the unsplit remainder. With a non-empty string separator, matches are literal and empty fields are preserved. Both parameters accept keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `str \| None` | Non-empty string separator or `None` for whitespace |
| `maxsplit` | `int` | Maximum splits (default `-1`) |

- **Returns** `list[str]`

##### `.rsplit(sep: str | None = None, maxsplit: int = -1) → list[str]`

Like `split()`, but a `maxsplit` counts from the right, so the unsplit rest is the first item: `"a/b/c".rsplit("/", 1)` → `["a/b", "c"]`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `str \| None` | Non-empty string separator or `None` for whitespace |
| `maxsplit` | `int` | Maximum splits (default `-1`) |

- **Returns** `list[str]`

##### `.splitlines(keepends: bool = False) → list[str]`

Split on Python line boundaries, including `\n`, `\r\n`, `\r`, vertical tab, form feed, Unicode NEL, and Unicode line/paragraph separators. Trailing boundaries do not add an extra empty item. Pass `keepends=True` to retain each boundary.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `keepends` | `bool` | Keep line-boundary characters |

- **Returns** `list[str]`

##### `.join(iterable: Iterable[str], /) → str`

Concatenate every string in a finite `iterable`, inserting this string as the separator between them. `",".join(["a", "b", "c"])` → `"a,b,c"`. All items must be strings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `Iterable[str]` | Finite iterable of strings |

- **Returns** `str`

##### `.find(substring: str, start: int | None = 0, end: int | None = None, /) → int`

Return the lowest index where `substring` appears, or `-1` if not found. Optional `start` and `end` restrict the search to a slice. Negative indices count from the end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `str` | Substring to find |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `int`

##### `.index(substring: str, start: int | None = 0, end: int | None = None, /) → int`

Like `find()`, but raises an error if the substring isn't present. Use `find()` if you want `-1` instead of an error.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `str` | Substring to find |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `int`

##### `.replace(old: str, new: str, count: int = -1, /) → str`

Return a copy with every occurrence of `old` replaced by `new`. Optional `count` limits the number of replacements: `s.replace("a", "b", 1)` only replaces the first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `old` | `str` | Substring to find |
| `new` | `str` | Replacement string |
| `count` | `int` | Max replacements (default: all) |

- **Returns** `str`

##### `.startswith(prefix: str | tuple[str, ...], start: int | None = 0, end: int | None = None, /) → bool`

`True` if the string starts with `prefix`. `prefix` can be a single string OR a tuple containing only strings: `"abc".startswith(("ab", "xy"))` → `True`. Optional `start` / `end` restrict the check to a slice (negative indices count from the end).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `str \| tuple[str, ...]` | String or tuple of strings |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `bool`

##### `.endswith(suffix: str | tuple[str, ...], start: int | None = 0, end: int | None = None, /) → bool`

`True` if the string ends with `suffix`. Accepts a single string OR a tuple containing only strings. Optional `start` / `end` restrict the check to a slice: useful for checking suffixes inside a larger string without rebuilding.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `suffix` | `str \| tuple[str, ...]` | String or tuple of strings |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `bool`

##### `.count(substring: str, start: int | None = 0, end: int | None = None, /) → int`

Count non-overlapping occurrences of `substring`. Optional `start` and `end` restrict the search to a slice. Empty `substring` returns length + 1.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `str` | Substring to count |
| `start` | `int \| None` | Start index |
| `end` | `int \| None` | End index, exclusive |

- **Returns** `int`

##### `.zfill(width: int, /) → str`

Pad with leading zeros to at least `width` characters. A leading `+` or `-` sign is preserved.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `int` | Target width |

- **Returns** `str`

##### `.center(width: int, fill: str = " ", /) → str`

Center the string within `width` characters, padding both sides with `fill` (default space). `fill` must be a single character.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `int` | Target width |
| `fill` | `str` | Fill character (default space) |

- **Returns** `str`

##### `.ljust(width: int, fill: str = " ", /) → str`

Left-justify within `width` characters, padding the right with `fill`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `int` | Target width |
| `fill` | `str` | Fill character (default space) |

- **Returns** `str`

##### `.rjust(width: int, fill: str = " ", /) → str`

Right-justify within `width` characters, padding the left with `fill`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `int` | Target width |
| `fill` | `str` | Fill character (default space) |

- **Returns** `str`

##### `.title() → str`

Return a titlecased copy: each run of cased characters starts with its Unicode titlecase mapping and continues in lowercase.

- **Returns** `str`

##### `.capitalize() → str`

Return a copy with the first character titlecased and the rest lowercased.

- **Returns** `str`

##### `.casefold() → str`

Apply Python-compatible Unicode case folding for caseless comparison. Functionally `.lower()` for ASCII and stronger for many Unicode characters.

- **Returns** `str`

##### `.swapcase() → str`

Swap the case of every character (lowercase ↔ uppercase).

- **Returns** `str`

##### `.isdigit() → bool`

`True` if the string is non-empty and contains only Unicode digit characters, including decimal and compatibility digits.

- **Returns** `bool`

##### `.isalpha() → bool`

`True` if the string is non-empty and contains only Unicode letters.

- **Returns** `bool`

##### `.isalnum() → bool`

`True` if the string is non-empty and contains only Unicode letters or numbers.

- **Returns** `bool`

##### `.isspace() → bool`

`True` if the string is non-empty and contains only whitespace characters.

- **Returns** `bool`

##### `.islower() → bool`

`True` if the string has at least one cased character and every cased character is lowercase.

- **Returns** `bool`

##### `.isupper() → bool`

`True` if the string has at least one cased character and every cased character is uppercase.

- **Returns** `bool`

##### `.istitle() → bool`

`True` when the string contains at least one cased character and each run of cased characters begins with an uppercase or Unicode titlecase character, followed only by lowercase characters. Characters without case separate the runs.

- **Returns** `bool`

##### `.isdecimal() → bool`

`True` when the string is not empty and every character is a decimal digit, `0` to `9` in any writing system. Stricter than `isdigit()`, which also accepts `²`.

- **Returns** `bool`

##### `.isnumeric() → bool`

`True` when the string is not empty and every character is numeric: digits, fractions such as `½` and numerals such as `Ⅷ`.

- **Returns** `bool`

##### `.isascii() → bool`

`True` when every character is ASCII, code point below 128. An empty string is `True`.

- **Returns** `bool`

##### `.isidentifier() → bool`

`True` when the string is spelled like a Python name, such as a variable name. Keywords such as `class` count too.

- **Returns** `bool`

##### `.isprintable() → bool`

`True` when every character prints visibly or is a space, and `False` for a line break, a tab or another control character. An empty string is `True`.

- **Returns** `bool`

##### `.rfind(substring: str, start: int | None = 0, end: int | None = None, /) → int`

Return the highest index where `substring` appears, or `-1` if not found. Mirror of `find()` from the right: useful for parsing the last separator of a string.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `str` | Substring to find |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `int`

##### `.rindex(substring: str, start: int | None = 0, end: int | None = None, /) → int`

Like `rfind()`, but raises if the substring isn't present.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `str` | Substring to find |
| `start` | `int \| None` | Start index (default 0) |
| `end` | `int \| None` | End index, exclusive (default length) |

- **Returns** `int`

##### `.format(*args: object, **kwargs: object) → str`

Replace placeholders with arguments. `{}` takes the next positional argument, `{0}` a numbered one and `{name}` a keyword one, and a field can add a conversion and a format spec exactly like an f-string: `"{:>8.2f}|{name!r}".format(3.14159, name="ore")` → `"    3.14|'ore'"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Values for the numbered `{}` fields |
| `kwargs` | `object` | Values for the named fields, by keyword (`name="world"`) |

- **Returns** `str`

##### `.format_map(mapping: dict[str, object], /) → str`

Like `.format()` with every `{name}` field read from one `dict`: `"{name} is done".format_map(job)`. A numbered or `{}` field is a `ValueError`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `mapping` | `dict[str, object]` | The `dict` the named fields read their values from |

- **Returns** `str`

##### `.expandtabs(tabsize: int = 8) → str`

Replace each tab with spaces up to the next multiple of `tabsize` columns, counted from the last line break: `"a\tb".expandtabs(4)` → `"a   b"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `tabsize` | `int` | Columns between tab stops (default 8) |

- **Returns** `str`

##### `.maketrans(x: str | dict[str | int, str | int | None], y: str | None = None, z: str | None = None, /) → dict[float, object]`

Build a table for `translate()`. `str.maketrans("abc", "xyz")` maps each character of the first string to the one at the same place in the second, a third string lists characters to delete, and one `dict` maps characters to their replacements.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `x` | `str \| dict[str \| int, str \| int \| None]` | Characters to replace, or a `dict` of replacements |
| `y` | `str \| None` | Replacement characters, as many as in `x` |
| `z` | `str \| None` | Characters to delete |

- **Returns** `dict[float, object]`

##### `.translate(table: dict[int, str | int | None], /) → str`

Replace characters through a table from `str.maketrans()`, or any `dict` from code points to a string, a code point, or `None` to delete: `"cab".translate(str.maketrans("abc", "xyz"))` → `"zxy"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `table` | `dict[int, str \| int \| None]` | Table from `str.maketrans()` |

- **Returns** `str`

##### `.partition(sep: str, /) → tuple[str, str, str]`

Split into three parts at the first occurrence of non-empty `sep`: `(before, sep, after)`. If `sep` isn't found, returns `(original, "", "")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `str` | Non-empty separator |

- **Returns** `tuple[str, str, str]`

##### `.rpartition(sep: str, /) → tuple[str, str, str]`

Like `partition()` but splits at the LAST occurrence of non-empty `sep`. If not found, returns `("", "", original)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `str` | Non-empty separator |

- **Returns** `tuple[str, str, str]`

##### `.removeprefix(prefix: str, /) → str`

Return a copy with `prefix` stripped from the start (only if present). Safer than slicing when you're not sure if the prefix is there.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `str` | Prefix to remove |

- **Returns** `str`

##### `.removesuffix(suffix: str, /) → str`

Return a copy with `suffix` stripped from the end (only if present).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `suffix` | `str` | Suffix to remove |

- **Returns** `str`

*Types / Built-in Types*

## tuple

**Returned by:** tuple literals `(1, 2)` · `enumerate()` · methods returning tuples

### Properties

##### `.length: int`

Number of items in the tuple. Same as `len(t)`. Property: no parens.

- **Returns** `int`

### Methods

##### `.index(item: T, start: int = 0, end?: int, /) → int`

Return the index of the first occurrence of `item`. Optional `start` and `end` restrict the search to a slice. Raises if not found within the range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to find |
| `start` | `int` | Start index (default 0) |
| `end` | `int` | End index, exclusive (default length) |

- **Returns** `int`

##### `.count(item: T, /) → int`

Count occurrences of `item` in the tuple.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `T` | Value to count |

- **Returns** `int`

*Types / Biosphere*

## CacheInfo

**Returned by:** `functools.lru_cache(fn).cache_info()` · `functools.cache(fn).cache_info()`

Get `CacheInfo` from the APIs listed here. It has no script constructor.

### Properties

##### `.hits: int`

Calls answered from the cache

- **Returns** `int`

##### `.misses: int`

Calls that had to run the function

- **Returns** `int`

##### `.maxsize: int`

How many results this cache keeps before dropping the least recently used one

- **Returns** `int`

##### `.currsize: int`

How many results are stored right now

- **Returns** `int`

*Types / Built-in Modules*

## Field

**Returned by:** `dataclasses.fields()`

Get `Field` from the APIs listed here. It has no script constructor.

### Properties

##### `.name: str`

Field name as declared

- **Returns** `str`

##### `.default: object`

The field's default value, or `MISSING` when it has none

- **Returns** `object`

##### `.default_factory: Callable`

The zero-argument function that builds this field's default, or `MISSING` when there is none

- **Returns** `Callable`

##### `.init: bool`

`True` when the field is a parameter of the generated constructor

- **Returns** `bool`

##### `.repr: bool`

`True` when the field appears in the generated text form

- **Returns** `bool`

##### `.compare: bool`

`True` when the field takes part in equality and ordering

- **Returns** `bool`

##### `.kw_only: bool`

`True` when the field must be passed by name

- **Returns** `bool`

*Types / Built-in Modules*

## Match

**Returned by:** `re.search()` · `re.match()` · `re.fullmatch()`

Get `Match` from the APIs listed here. It has no script constructor.

### Properties

##### `.pattern: str`

The regular expression pattern string that produced this match.

- **Returns** `str`

##### `.string: str`

The string that was searched.

- **Returns** `str`

##### `.lastindex: int | None`

Number of the last group that matched, or `None` if no group did.

- **Returns** `int | None`

##### `.lastgroup: str | None`

Name of the last group that matched, or `None` if it has no name or no group matched.

- **Returns** `str | None`

##### `.pos: int`

Where the search started in the string.

- **Returns** `int`

##### `.endpos: int`

Where the search stopped in the string.

- **Returns** `int`

##### `.re: Pattern`

The compiled `Pattern` that produced this match.

- **Returns** `Pattern`

### Methods

##### `.group(group: int | str = 0, /, *groups: int | str) → str | None`

Return the matched text for a group, by number or by `(?P<name>...)` name. Group `0` is the whole match, and several groups return a `tuple`: `m.group(1, "unit")`. Optional groups that did not match return `None`; an unknown group raises. `m[1]` is the same as `m.group(1)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `group` | `int \| str` | Capture group number or name; default 0 |
| `groups` | `int \| str` | More groups, which make the result a `tuple` |

- **Returns** `str | None`

##### `.groups(default: object = None) → tuple[str | None, ...]`

Return a `tuple` of captured groups, excluding group `0`. Groups that did not match use `default`, which is `None` if omitted.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `object` | Value for unmatched optional groups |

- **Returns** `tuple[str | None, ...]`

##### `.start(index: int | str = 0) → int`

Start character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int \| str` | Capture group index; default 0 |

- **Returns** `int`

##### `.end(index: int | str = 0) → int`

End character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int \| str` | Capture group index; default 0 |

- **Returns** `int`

##### `.span(index: int | str = 0) → tuple[int, ...]`

Return `(start, end)` for the group. Unmatched optional groups return `(-1, -1)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int \| str` | Capture group index; default 0 |

- **Returns** `tuple[int, ...]`

##### `.__getitem__(group: int | str, /) → str | None`

`m[1]` gives the same text as `m.group(1)`, and `m["name"]` as `m.group("name")`; a group that took no part in the match gives `None`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `group` | `int \| str` | Capture group number or name; default 0 |

- **Returns** `str | None`

##### `.groupdict(default: object = None) → dict[str, str | None]`

Return a `dict` of every named group's text, by name. Named groups that did not match use `default`, which is `None` if omitted.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `object` | Value for unmatched optional groups |

- **Returns** `dict[str, str | None]`

##### `.expand(template: str, /) → str`

Fill in a replacement template the way `re.sub()` does, from this match: `m.expand(r"\2-\1")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `template` | `str` | Template with backreferences |

- **Returns** `str`

*Types / Built-in Modules*

## Pattern

**Returned by:** `re.compile()`

Get `Pattern` from the APIs listed here. It has no script constructor.

### Properties

##### `.pattern: str`

The pattern text this was compiled from.

- **Returns** `str`

##### `.flags: int`

The flags this was compiled with.

- **Returns** `int`

##### `.groups: int`

How many capture groups the pattern has.

- **Returns** `int`

##### `.groupindex: dict[str, float]`

A `dict` from each `(?P<name>...)` group name to its number.

- **Returns** `dict[str, float]`

### Methods

##### `.search(string: str, pos: int = 0, endpos: int | None = None) → Match | None`

Like `re.search()` with this pattern, looking only between `pos` and `endpos`: a `Match`, or `None` if nothing there matches.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `pos` | `int` | Index to start at (default 0) |
| `endpos` | `int \| None` | Index to stop before (default the end) |

- **Returns** `Match | None`

##### `.match(string: str, pos: int = 0, endpos: int | None = None) → Match | None`

Like `re.match()` with this pattern, anchored at `pos`: a `Match`, or `None` if the text at `pos` does not match.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `pos` | `int` | Index to start at (default 0) |
| `endpos` | `int \| None` | Index to stop before (default the end) |

- **Returns** `Match | None`

##### `.fullmatch(string: str, pos: int = 0, endpos: int | None = None) → Match | None`

Like `re.fullmatch()` with this pattern, over the text from `pos` to `endpos`: a `Match`, or `None` if any part is left unmatched.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `pos` | `int` | Index to start at (default 0) |
| `endpos` | `int \| None` | Index to stop before (default the end) |

- **Returns** `Match | None`

##### `.findall(string: str, pos: int = 0, endpos: int | None = None) → list`

Like `re.findall()` with this pattern, between `pos` and `endpos`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `pos` | `int` | Index to start at (default 0) |
| `endpos` | `int \| None` | Index to stop before (default the end) |

- **Returns** `list`

##### `.finditer(string: str, pos: int = 0, endpos: int | None = None) → Iterator[Match]`

Like `re.finditer()` with this pattern, between `pos` and `endpos`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `pos` | `int` | Index to start at (default 0) |
| `endpos` | `int \| None` | Index to stop before (default the end) |

- **Returns** `Iterator[Match]`

##### `.sub(repl: str | Callable, string: str, count: int = 0) → str`

Like `re.sub()` with this pattern.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `repl` | `str \| Callable` | Replacement text, or a function from `Match` to text |
| `string` | `str` | Text to search |
| `count` | `int` | Maximum replacements; 0 means all |

- **Returns** `str`

##### `.subn(repl: str | Callable, string: str, count: int = 0) → tuple[str, int]`

Like `re.subn()` with this pattern.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `repl` | `str \| Callable` | Replacement text, or a function from `Match` to text |
| `string` | `str` | Text to search |
| `count` | `int` | Maximum replacements; 0 means all |

- **Returns** `tuple[str, int]`

##### `.split(string: str, maxsplit: int = 0) → list`

Like `re.split()` with this pattern.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `string` | `str` | Text to search |
| `maxsplit` | `int` | Maximum splits; 0 means all |

- **Returns** `list`

*Types / Exploration*
