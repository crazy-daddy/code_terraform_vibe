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
- [`Match`](#match) (BUILT-IN MODULES)

---

## dict

**Returned by:** dict literals `{k: v}` · `dict()` · methods returning dicts

### Properties

##### `.length`

Number of key-value pairs. Same as `len(d)`. Property: no parens.

- **Returns** `number`

### Methods

##### `.keys()`

Return a list of all keys, in insertion order.

- **Returns** `list`

##### `.values()`

Return a list of all values, in insertion order.

- **Returns** `list`

##### `.items()`

Return a list of `(key, value)` tuples, in insertion order. Common pattern: `for k, v in d.items(): ...`.

- **Returns** `list`

##### `.has(key, /)`

`True` if `key` is in the dictionary. Equivalent to Python's `key in d`. Use this for safe membership tests before subscript.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `any` | Key to check |

- **Returns** `boolean`

##### `.get(key, default=None, /)`

Return the value for `key`, or `default` (`None` if omitted) if the key is missing. Never raises for a missing hashable key; an unhashable key still raises `TypeError`, matching Python.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `any` | Key to look up |
| `default` | `any` | Value to return if missing |

- **Returns** `any`

##### `.pop(key, default?, /)`

Remove `key` and return its value. Raises if the key isn't present unless a `default` is provided: in that case the missing-key path returns `default` and the dict is unchanged. Matches Python's `dict.pop(k, default)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `any` | Key to remove |
| `default` | `any` | Value to return if the key is missing |

- **Returns** `any`

##### `.popitem()`

Remove and return the last inserted `(key, value)` pair. Raises if the dictionary is empty. Insertion order is deterministic, but use this only when consuming a dict as a stack is what you intend.

- **Returns** `tuple`

##### `.setdefault(key, default=None, /)`

Return `d[key]` if it exists; otherwise set `d[key] = default` and return `default`. Useful for building grouped collections.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `key` | `any` | Key |
| `default` | `any` | Value to set if missing |

- **Returns** `any`

##### `.update(other?, /, **kwargs)`

Merge entries into this dict, overwriting matching keys. Accepts another dict, an iterable of `(key, value)` pairs, keyword args, OR a combination: `d.update(other, a=1, b=2)`. Mutates in place.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Dict or iterable of (key, value) pairs |

- **Returns** `None`

##### `.copy()`

Return a shallow copy of the dictionary. Top-level keys/values are duplicated to a fresh dict; nested mutable values (lists, dicts) are shared with the original.

- **Returns** `dict`

##### `.clear()`

Remove all entries.

- **Returns** `None`

*Types / Built-in Types*

---

## generator

**Returned by:** calling a function containing `yield` · generator expressions

### Properties

##### `.__name__`

Name of the generator function that created this generator.

- **Returns** `string`

##### `.__qualname__`

Qualified name of the generator function that created this generator.

- **Returns** `string`

### Methods

##### `.send(value)`

Resume the generator and make `value` the result of its paused `yield`. Returns the next yielded value. Sending a non-`None` value before the first yield raises `TypeError`; completion raises `StopIteration`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `value` | `any` | Value delivered to the paused yield |

- **Returns** `any`

##### `.throw(exception)`

Raise an exception at the generator's paused `yield`. Returns the next value if the generator catches it and yields again; otherwise the exception propagates.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `exception` | `any` | Exception instance or exception class |

- **Returns** `any`

##### `.close()`

Stop the generator by raising `GeneratorExit` at its paused yield. `finally` cleanup runs before this returns. A generator that yields while closing raises `RuntimeError`.

- **Returns** `None`

##### `.__iter__()`

Return this generator. Generators are one-shot iterators.

- **Returns** `generator`

##### `.__next__()`

Resume the generator with `None` and return its next yielded value. Completion raises `StopIteration`.

- **Returns** `any`

*Types / Built-in Types*

---

## list

**Returned by:** list literals `[1, 2, 3]` · `list(iterable)` · methods returning lists

### Properties

##### `.length`

Number of items in the list. Same as `len(lst)`. Property: no parens.

- **Returns** `number`

### Methods

##### `.append(item, /)`

Add `item` to the end of the list. Returns `None`. Mutates in place. Raises if the list would exceed the interpreter's max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to append |

- **Returns** `None`

##### `.pop(index=-1, /)`

Remove and return one element. Default removes the last (`pop()`). Pass an integer index to remove a specific item: `lst.pop(0)` removes the first, `lst.pop(-1)` removes the last. Negative indices count from the end. Empty list or out-of-range index raises an error. Non-integer index raises.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Position to remove (default: -1, the last item) |

- **Returns** `any`

##### `.remove(item, /)`

Remove the first occurrence of `item` by value. Raises if not found. Use `.index(item)` first if you need to check.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to remove |

- **Returns** `None`

##### `.insert(index, item, /)`

Insert `item` at position `index`, shifting later items right. `insert(0, x)` puts `x` at the front. Out-of-range indices clamp to the ends (no error). Raises if the list would exceed the max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Position |
| `item` | `any` | Value |

- **Returns** `None`

##### `.index(item, start=0, end=None, /)`

Return the index of the first occurrence of `item`. Optional `start` and `end` restrict the search to a slice (Python-style: negative indices count from the end, clamped to bounds). Raises if not found within the range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.count(item, /)`

Count occurrences of `item` in the list. Equality is by value (numbers, strings, booleans compared deeply).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to count |

- **Returns** `number`

##### `.sort(*, key=None, reverse=False)`

Sort the list **in place** using `<` between mutually comparable keys. With `key=None` (the default), each value is its own key. Numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may define the exact rich-comparison slots needed by `<`; unsupported pairs raise. `key=` is called once per item and must be **pure**: it cannot suspend the script or mutate game state. `reverse` is truth-tested, and the finite input is handled eagerly within the interpreter's collection limit.

- **Returns** `None`

##### `.reverse()`

Reverse the list in place. Returns `None`.

- **Returns** `None`

##### `.copy()`

Return a shallow copy of the list. Modifying the copy does not affect the original; nested mutable items are shared.

- **Returns** `list`

##### `.extend(iterable, /)`

Append every item from another finite iterable to the end of this list. Mutates in place. Raises if the result would exceed the max-length cap.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `any` | Finite iterable of items to append |

- **Returns** `None`

##### `.clear()`

Remove all items. Returns `None`. Equivalent to `lst[:] = []`.

- **Returns** `None`

*Types / Built-in Types*

---

## set

**Returned by:** set literals `{1, 2}` · `set(iterable)` · set algebra operators

### Properties

##### `.length`

Number of unique members. Same as `len(s)`. Property: no parens.

- **Returns** `number`

### Methods

##### `.add(item, /)`

Add `item` to the set. No effect if already present. The item may be any hashable value, including tuples of hashables and properly hashable user-class instances.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to add |

- **Returns** `None`

##### `.remove(item, /)`

Remove `item`. Raises if not present. Use `.discard()` for the safe form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to remove |

- **Returns** `None`

##### `.discard(item, /)`

Remove `item` if present. No error if absent.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to remove |

- **Returns** `None`

##### `.pop()`

Remove and return an arbitrary element. Order is deterministic (insertion order) but scripts shouldn't rely on it. Raises if the set is empty.

- **Returns** `any`

##### `.clear()`

Remove all members.

- **Returns** `None`

##### `.copy()`

Return a shallow copy.

- **Returns** `set`

##### `.has(item, /)`

`True` if `item` is in the set. Equivalent to Python's `item in s`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to check |

- **Returns** `boolean`

##### `.union(*others)`

Return a new set with members from this set and every finite iterable in `others`. With no arguments, returns a copy.

- **Returns** `set`

##### `.intersection(*others)`

Return a new set containing members shared with every finite iterable in `others`. With no arguments, returns a copy.

- **Returns** `set`

##### `.difference(*others)`

Return a new set without members found in any finite iterable in `others`. With no arguments, returns a copy.

- **Returns** `set`

##### `.symmetric_difference(other, /)`

Return a new set with members in exactly one of this set and the finite iterable `other`. Same as `a ^ b`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Finite iterable |

- **Returns** `set`

##### `.update(*others)`

Add every member from each finite iterable in `others`. Mutates in place; with no arguments, does nothing.

- **Returns** `None`

##### `.intersection_update(*others)`

Keep only members shared with every finite iterable in `others`. Mutates in place; with no arguments, does nothing.

- **Returns** `None`

##### `.difference_update(*others)`

Remove members found in any finite iterable in `others`. Mutates in place; with no arguments, does nothing.

- **Returns** `None`

##### `.symmetric_difference_update(other, /)`

Replace this set with members in exactly one of this set and the finite iterable `other`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Finite iterable |

- **Returns** `None`

##### `.issubset(other, /)`

`True` if every member of this set is also in the finite iterable `other`. Same as `a <= b` for sets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Finite iterable |

- **Returns** `boolean`

##### `.issuperset(other, /)`

`True` if this set contains every member of the finite iterable `other`. Same as `a >= b` for sets.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Finite iterable |

- **Returns** `boolean`

##### `.isdisjoint(other, /)`

`True` if this set and the finite iterable `other` share no members.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `other` | `any` | Finite iterable |

- **Returns** `boolean`

*Types / Built-in Types*

---

## slice

**Returned by:** `slice(stop)` · `slice(start, stop, step)`

### Properties

##### `.start`

Start bound, or `None` when omitted. For `slice(stop)`, `.start` is `None` and `.stop` is the argument.

- **Returns** `any`

##### `.stop`

Stop bound, or `None` when omitted.

- **Returns** `any`

##### `.step`

Step bound, or `None` when omitted. Sequence indexing rejects a step of `0`.

- **Returns** `any`

*Types / Built-in Types*

---

## str

**Returned by:** string literals · `str(value)` · methods returning strings

### Properties

##### `.length`

Number of characters in the string. Same as `len(s)`. Property: no parens.

- **Returns** `number`

### Methods

##### `.upper()`

Return a copy with all characters in uppercase.

- **Returns** `string`

##### `.lower()`

Return a copy with all characters in lowercase.

- **Returns** `string`

##### `.strip(chars=None, /)`

Return a copy with whitespace (or `chars` if given) trimmed from both ends. Passing `None` explicitly is the same as omitting `chars`. `chars` is treated as a SET of characters to strip, not a substring: `"...hello...".strip(".")` → `"hello"`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `string` | Characters to strip, or None for whitespace |

- **Returns** `string`

##### `.lstrip(chars=None, /)`

Like `strip()` but only trims from the left end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `string` | Characters to strip, or None for whitespace |

- **Returns** `string`

##### `.rstrip(chars=None, /)`

Like `strip()` but only trims from the right end. Passing `None` explicitly selects whitespace trimming.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `chars` | `string` | Characters to strip, or None for whitespace |

- **Returns** `string`

##### `.split(sep=None, maxsplit=-1)`

Split into substrings. With `sep=None`, every Python whitespace character separates words, runs collapse, and leading/trailing whitespace is ignored unless a finite `maxsplit` leaves it in the unsplit remainder. With a non-empty string separator, matches are literal and empty fields are preserved. Both parameters accept keyword form.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `any` | Non-empty string separator or None for whitespace |
| `maxsplit` | `number` | Maximum splits (default -1) |

- **Returns** `list<string>`

##### `.splitlines(keepends=False)`

Split on Python line boundaries, including `\n`, `\r\n`, `\r`, vertical tab, form feed, Unicode NEL, and Unicode line/paragraph separators. Trailing boundaries do not add an extra empty item. Pass `keepends=True` to retain each boundary.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `keepends` | `boolean` | Keep line-boundary characters |

- **Returns** `list<string>`

##### `.join(iterable, /)`

Concatenate every string in a finite `iterable`, inserting this string as the separator between them. `",".join(["a", "b", "c"])` → `"a,b,c"`. All items must be strings.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `iterable` | `any` | Finite iterable of strings |

- **Returns** `string`

##### `.find(substring, start=0, end=None, /)`

Return the lowest index where `substring` appears, or `-1` if not found. Optional `start` and `end` restrict the search to a slice. Negative indices count from the end.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `string` | Substring to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.index(substring, start=0, end=None, /)`

Like `find()`, but raises an error if the substring isn't present. Use `find()` if you want `-1` instead of an error.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `string` | Substring to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.replace(old, new, count=-1, /)`

Return a copy with every occurrence of `old` replaced by `new`. Optional `count` limits the number of replacements: `s.replace("a", "b", 1)` only replaces the first.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `old` | `string` | Substring to find |
| `new` | `string` | Replacement string |
| `count` | `number` | Max replacements (default: all) |

- **Returns** `string`

##### `.startswith(prefix, start=0, end=None, /)`

`True` if the string starts with `prefix`. `prefix` can be a single string OR a tuple containing only strings: `"abc".startswith(("ab", "xy"))` → `True`. Optional `start` / `end` restrict the check to a slice (negative indices count from the end).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `string` | String or tuple of strings |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `boolean`

##### `.endswith(suffix, start=0, end=None, /)`

`True` if the string ends with `suffix`. Accepts a single string OR a tuple containing only strings. Optional `start` / `end` restrict the check to a slice: useful for checking suffixes inside a larger string without rebuilding.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `suffix` | `string` | String or tuple of strings |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `boolean`

##### `.count(substring, start=0, end=None, /)`

Count non-overlapping occurrences of `substring`. Optional `start` and `end` restrict the search to a slice. Empty `substring` returns length + 1.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `string` | Substring to count |
| `start` | `number` | Start index |
| `end` | `number` | End index, exclusive |

- **Returns** `number`

##### `.zfill(width, /)`

Pad with leading zeros to at least `width` characters. A leading `+` or `-` sign is preserved.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `number` | Target width |

- **Returns** `string`

##### `.center(width, fill=" ", /)`

Center the string within `width` characters, padding both sides with `fill` (default space). `fill` must be a single character.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `number` | Target width |
| `fill` | `string` | Fill character (default space) |

- **Returns** `string`

##### `.ljust(width, fill=" ", /)`

Left-justify within `width` characters, padding the right with `fill`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `number` | Target width |
| `fill` | `string` | Fill character (default space) |

- **Returns** `string`

##### `.rjust(width, fill=" ", /)`

Right-justify within `width` characters, padding the left with `fill`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `width` | `number` | Target width |
| `fill` | `string` | Fill character (default space) |

- **Returns** `string`

##### `.title()`

Return a titlecased copy: each run of cased characters starts with its Unicode titlecase mapping and continues in lowercase.

- **Returns** `string`

##### `.capitalize()`

Return a copy with the first character titlecased and the rest lowercased.

- **Returns** `string`

##### `.casefold()`

Apply Python-compatible Unicode case folding for caseless comparison. Functionally `.lower()` for ASCII and stronger for many Unicode characters.

- **Returns** `string`

##### `.swapcase()`

Swap the case of every character (lowercase ↔ uppercase).

- **Returns** `string`

##### `.isdigit()`

`True` if the string is non-empty and contains only Unicode digit characters, including decimal and compatibility digits.

- **Returns** `boolean`

##### `.isalpha()`

`True` if the string is non-empty and contains only Unicode letters.

- **Returns** `boolean`

##### `.isalnum()`

`True` if the string is non-empty and contains only Unicode letters or numbers.

- **Returns** `boolean`

##### `.isspace()`

`True` if the string is non-empty and contains only whitespace characters.

- **Returns** `boolean`

##### `.islower()`

`True` if the string has at least one cased character and every cased character is lowercase.

- **Returns** `boolean`

##### `.isupper()`

`True` if the string has at least one cased character and every cased character is uppercase.

- **Returns** `boolean`

##### `.istitle()`

`True` when the string contains at least one cased character and each run of cased characters begins with an uppercase or Unicode titlecase character, followed only by lowercase characters. Characters without case separate the runs.

- **Returns** `boolean`

##### `.rfind(substring, start=0, end=None, /)`

Return the highest index where `substring` appears, or `-1` if not found. Mirror of `find()` from the right: useful for parsing the last separator of a string.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `string` | Substring to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.rindex(substring, start=0, end=None, /)`

Like `rfind()`, but raises if the substring isn't present.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `substring` | `string` | Substring to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.format(*args, **kwargs)`

Replace placeholders with arguments. Auto-numbered `{}` consumes the next positional arg, explicit `{0}`/`{1}` reference specific positionals, and `{name}` looks up a keyword arg: `"hi {name}".format(name="world")` → `"hi world"`. For format specs / conversions (`{x:>10}`, `{x!r}`), prefer f-strings.

- **Returns** `string`

##### `.partition(sep, /)`

Split into three parts at the first occurrence of non-empty `sep`: `(before, sep, after)`. If `sep` isn't found, returns `(original, "", "")`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `string` | Non-empty separator |

- **Returns** `[string, string, string]`

##### `.rpartition(sep, /)`

Like `partition()` but splits at the LAST occurrence of non-empty `sep`. If not found, returns `("", "", original)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `sep` | `string` | Non-empty separator |

- **Returns** `[string, string, string]`

##### `.removeprefix(prefix, /)`

Return a copy with `prefix` stripped from the start (only if present). Safer than slicing when you're not sure if the prefix is there.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `prefix` | `string` | Prefix to remove |

- **Returns** `string`

##### `.removesuffix(suffix, /)`

Return a copy with `suffix` stripped from the end (only if present).

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `suffix` | `string` | Suffix to remove |

- **Returns** `string`

*Types / Built-in Types*

---

## tuple

**Returned by:** tuple literals `(1, 2)` · `enumerate()` · methods returning tuples

### Properties

##### `.length`

Number of items in the tuple. Same as `len(t)`. Property: no parens.

- **Returns** `number`

### Methods

##### `.index(item, start=0, end=None, /)`

Return the index of the first occurrence of `item`. Optional `start` and `end` restrict the search to a slice. Raises if not found within the range.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to find |
| `start` | `number` | Start index (default 0) |
| `end` | `number` | End index, exclusive (default length) |

- **Returns** `number`

##### `.count(item, /)`

Count occurrences of `item` in the tuple.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `item` | `any` | Value to count |

- **Returns** `number`

*Types / Biosphere*

---

## Match

**Returned by:** `re.search()` · `re.match()` · `re.fullmatch()`

### Properties

##### `.pattern`

The regular expression pattern string that produced this match.

- **Returns** `string`

##### `.string`

The string that was searched.

- **Returns** `string`

### Methods

##### `.group(index=0)`

Return the matched text for group `index`. Group `0` is the whole match. Optional groups that did not match return `None`; an out-of-range group raises.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Capture group index; default 0 |

- **Returns** `Optional[string]`

##### `.groups(default=None)`

Return a tuple of captured groups, excluding group `0`. Groups that did not match use `default`, which is `None` if omitted.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `default` | `any` | Value for unmatched optional groups |

- **Returns** `tuple`

##### `.start(index=0)`

Start character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Capture group index; default 0 |

- **Returns** `number`

##### `.end(index=0)`

End character index for the group. Unmatched optional groups return `-1`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Capture group index; default 0 |

- **Returns** `number`

##### `.span(index=0)`

Return `(start, end)` for the group. Unmatched optional groups return `(-1, -1)`.

*Parameters*

| Name | Type | Description |
| --- | --- | --- |
| `index` | `number` | Capture group index; default 0 |

- **Returns** `tuple<number>`

*Types / Exploration*

---
