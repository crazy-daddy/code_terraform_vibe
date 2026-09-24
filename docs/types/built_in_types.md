# Data Types: Built In Types

Complete property specifications, descriptions, units, and return types from the official documentation.

## Index

- [`dict`](#dict) (BUILT-IN TYPES)
- [`generator`](#generator) (BUILT-IN TYPES)
- [`list`](#list) (BUILT-IN TYPES)
- [`set`](#set) (BUILT-IN TYPES)
- [`slice`](#slice) (BUILT-IN TYPES)
- [`str`](#str) (BUILT-IN TYPES)
- [`tuple`](#tuple) (BUILT-IN TYPES)
- [`CacheInfo`](#cacheinfo) (BUILT-IN MODULES)
- [`Field`](#field) (BUILT-IN MODULES)
- [`Match`](#match) (BUILT-IN MODULES)

---

## dict

**Returned by:** dict literals `{k: v}` · `dict()` · methods returning dicts

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

Remove and return the last inserted `(key, value)` pair. Raises if the dictionary is empty. Insertion order is deterministic, but use this only when consuming a dict as a stack is what you intend.

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

Merge entries into this dict, overwriting matching keys. Accepts another dict, an iterable of `(key, value)` pairs, keyword args, OR a combination: `d.update(other, a=1, b=2)`. Mutates in place.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `dict[K, V] \| Iterable[tuple[K, V]]` | A dict, or an iterable of (key, value) pairs |
| `kwargs` | `V` | More entries, by keyword (`speed=2`) |

- **Returns** `None`

##### `.copy() → dict[K, V]`

Return a shallow copy of the dictionary. Top-level keys/values are duplicated to a fresh dict; nested mutable values (lists, dicts) are shared with the original.

- **Returns** `dict[K, V]`

##### `.clear() → None`

Remove all entries.

- **Returns** `None`

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

Resume the generator and make `value` the result of its paused `yield`. Returns the next yielded value. Sending a non-`None` value before the first yield raises `TypeError`; completion raises `StopIteration`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `object` | Value delivered to the paused yield |

- **Returns** `T`

##### `.throw(exception: BaseException | type) → T`

Raise an exception at the generator's paused `yield`. Returns the next value if the generator catches it and yields again; otherwise the exception propagates.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `exception` | `BaseException \| type` | Exception instance or exception class |

- **Returns** `T`

##### `.close() → None`

Stop the generator by raising `GeneratorExit` at its paused yield. `finally` cleanup runs before this returns. A generator that yields while closing raises `RuntimeError`.

- **Returns** `None`

##### `.__iter__() → generator`

Return this generator. Generators are one-shot iterators.

- **Returns** `generator`

##### `.__next__() → T`

Resume the generator with `None` and return its next yielded value. Completion raises `StopIteration`.

- **Returns** `T`

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

Remove the first occurrence of `item` by value. Raises if not found. Use `.index(item)` first if you need to check.

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
| `chars` | `str \| None` | Characters to strip, or None for whitespace |

- **Returns** `str`

##### `.lstrip(chars: str | None = None, /) → str`

Like `strip()` but only trims from the left end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `str \| None` | Characters to strip, or None for whitespace |

- **Returns** `str`

##### `.rstrip(chars: str | None = None, /) → str`

Like `strip()` but only trims from the right end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `str \| None` | Characters to strip, or None for whitespace |

- **Returns** `str`

##### `.split(sep: str | None = None, maxsplit: int = -1) → list[str]`

Split into substrings. With `sep=None`, every Python whitespace character separates words, runs collapse, and leading/trailing whitespace is ignored unless a finite `maxsplit` leaves it in the unsplit remainder. With a non-empty string separator, matches are literal and empty fields are preserved. Both parameters accept keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `str \| None` | Non-empty string separator or None for whitespace |
| `maxsplit` | `int` | Maximum splits (default -1) |

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

Replace placeholders with arguments. Auto-numbered `{}` consumes the next positional arg, explicit `{0}`/`{1}` reference specific positionals, and `{name}` looks up a keyword arg: `"hi {name}".format(name="world")` → `"hi world"`. For format specs / conversions (`{x:>10}`, `{x!r}`), prefer f-strings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `args` | `object` | Values for the numbered `{}` fields |
| `kwargs` | `object` | Values for the named fields, by keyword (`name="world"`) |

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

True when the field is a parameter of the generated constructor

- **Returns** `bool`

##### `.repr: bool`

True when the field appears in the generated text form

- **Returns** `bool`

##### `.compare: bool`

True when the field takes part in equality and ordering

- **Returns** `bool`

##### `.kw_only: bool`

True when the field must be passed by name

- **Returns** `bool`

*Types / Built-in Modules*

## Match

**Returned by:** `re.search()` · `re.match()` · `re.fullmatch()`

### Properties

##### `.pattern: str`

The regular expression pattern string that produced this match.

- **Returns** `str`

##### `.string: str`

The string that was searched.

- **Returns** `str`

### Methods

##### `.group(index: int = 0) → str | None`

Return the matched text for group `index`. Group `0` is the whole match. Optional groups that did not match return `None`; an out-of-range group raises.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Capture group index; default 0 |

- **Returns** `str | None`

##### `.groups(default: object = None) → tuple[str | None, ...]`

Return a tuple of captured groups, excluding group `0`. Groups that did not match use `default`, which is `None` if omitted.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `object` | Value for unmatched optional groups |

- **Returns** `tuple[str | None, ...]`

##### `.start(index: int = 0) → int`

Start character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Capture group index; default 0 |

- **Returns** `int`

##### `.end(index: int = 0) → int`

End character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Capture group index; default 0 |

- **Returns** `int`

##### `.span(index: int = 0) → tuple[int, ...]`

Return `(start, end)` for the group. Unmatched optional groups return `(-1, -1)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `int` | Capture group index; default 0 |

- **Returns** `tuple[int, ...]`

*Types / Exploration*
