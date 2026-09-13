# Models: Python Standard Builtin Emulations

Granular data models and return types extracted from `__builtins__.pyi`.

## `Match`

```python
class Match:
 """`re.search()` · `re.match()` · `re.fullmatch()`"""
 pattern: _str
 string: _str
 def group(self, index: _float = ...) -> _str | None:
 """Return the matched text for group `index`. Group `0` is the whole match. Optional groups that did not match return `None`; an out-of-range group raises."""
 ...
 def groups(self, default: Any = ...) -> _tuple[Any, ...]:
 """Return a tuple of captured groups, excluding group `0`. Groups that did not match use `default`, which is `None` if omitted."""
 ...
 def start(self, index: _float = ...) -> _int:
 """Start character index for the group. Unmatched optional groups return `-1`."""
 ...
 def end(self, index: _float = ...) -> _int:
 """End character index for the group. Unmatched optional groups return `-1`."""
 ...
 def span(self, index: _float = ...) -> _tuple[_float, ...]:
 """Return `(start, end)` for the group. Unmatched optional groups return `(-1, -1)`."""
 ...
```

## `enumerate`

```python
class enumerate(_list[_tuple[_int, _T]], Generic[_T]):
 """List of (index, value) pairs. Optional integer `start=N` shifts the index: `enumerate(items, start=1)` for 1-based indexing. Arbitrarily large integer starts remain exact. `start` may be positional or keyword, but not both."""
 def __init__(self, sequence: Iterable[_T], /, start: _int = ...) -> None: ...
# Sum of every numeric item in an iterable. Optional `start` (number or list): `sum(list_of_lists, [])` flattens. `start` may be positional or keyword, but not both.
@overload
def sum(iterable: Iterable[Any], /, start: _float = ...) -> _float: ...
@overload
def sum(iterable: Iterable[Any], /, start: _list[Any]) -> _list[Any]: ...
def prod(iterable: Any, /, start: _float = ...) -> _float:
 """Product of every numeric item in an iterable. Empty iterables return `start`. `start` may be positional or keyword, but not both."""
 ...
def all(iterable: Any, /) -> _bool:
 """True if every item in the iterable is truthy. Stops at the first falsy item, so generators are consumed only as far as needed."""
 ...
def any(iterable: Any, /) -> _bool:
 """True if any item in the iterable is truthy. Stops at the first truthy item, so generators are consumed only as far as needed."""
 ...
```

## `filter`

```python
class filter(_list[_T], Generic[_T]):
 """Keep items for which pure `fn(item)` is truthy; callbacks cannot suspend the script or mutate game state. `filter(None, iter)` keeps every truthy item without a callback. An empty input never inspects or calls `fn`."""
 def __init__(self, fn: Callable[[_T], object] | None, iterable: Iterable[_T], /) -> None: ...
def reduce(fn: Any, iterable: Any, initializer: Any = ..., /) -> Any:
 """Combine an iterable into one value by repeatedly calling pure `fn(total, item)`; callbacks cannot suspend the script or mutate game state. With no initializer, the first item becomes the initial total; empty iterables then raise. Empty-with-initializer and singleton-without-initializer perform no callback call. Also available as `from functools import reduce`."""
 ...

# Built-in values supplied by the interpreter
# Positive infinity, larger than every finite number. Use `-inf` for negative infinity, including as an initial best or worst value in search and pathfinding algorithms.
inf: _float
# Mathematical constant `π ≈ 3.14159`.
pi: _float
# Mathematical constant `τ = 2π`.
tau: _float

# Script-owner locals such as self and panel are intentionally omitted.
```

## `map`

```python
class map(_list[_R], Generic[_R]):
 """Apply pure `fn` to corresponding items of each iterable. Callbacks cannot suspend the script or mutate game state. Single-iter form calls `fn(x)`; multi-iter form calls `fn(x, y, ...)` and stops at the shortest input unless `strict=True`, which raises if input lengths differ. If no row is produced, `fn` is never inspected or called."""
 @overload
 def __init__(self, fn: Callable[[_T], _R], iter1: Iterable[_T], /, *, strict: _bool = ...) -> None: ...
 @overload
 def __init__(self, fn: Callable[[_T, _U], _R], iter1: Iterable[_T], iter2: Iterable[_U], /, *, strict: _bool = ...) -> None: ...
 @overload
 def __init__(self, fn: Callable[[_T, _U, _V], _R], iter1: Iterable[_T], iter2: Iterable[_U], iter3: Iterable[_V], /, *, strict: _bool = ...) -> None: ...
 @overload
 def __init__(self, fn: Callable[..., _R], iter1: Iterable[Any], *iterables: Iterable[Any], strict: _bool = ...) -> None: ...
```

## `range`

```python
class range(_list[_int]):
 """Materialize the bounded integer range from `start` to `stop` (exclusive), stepping by `step`. `range(5)` → `[0,1,2,3,4]`. Endpoints and steps retain arbitrary-size exact integers, while the produced list must fit the interpreter's collection limit. All arguments must be integers; `step=0` and fractional values are rejected. Negative `step` counts down: `range(5, 0, -1)` → `[5,4,3,2,1]`."""
 @overload
 def __init__(self, stop: _int, /) -> None: ...
 @overload
 def __init__(self, start: _int, stop: _int, step: _int = ..., /) -> None: ...
def chr(code: _float, /) -> _str:
 """Character from Unicode code point (e.g. chr(65) → 'A')."""
 ...
def ord(char: _str, /) -> _int:
 """Unicode code point from character (e.g. ord('A') → 65)."""
 ...
def object_type(value: Any, /) -> _str:
 """Return a concrete registered name such as `\"MiningSite\"`, `\"CatalogedFragment\"`, or `\"Position\"` for a game data object without changing the established result of `type(value)`. Component references return `\"Component\"`; other values use the same public category as `type(value)`."""
 ...
def vars(object: Any, /) -> _dict[_str, Any]:
 """Return a detached, shallow dictionary of an object's public data fields. Structured results, positions, journal entries, and other game data values include their documented attribute fields but not methods; class instances include their own stored attributes. Changing the returned dictionary does not change the object, although nested lists and dictionaries are shared. Use `object_type(object)` separately when the concrete registered name is needed. Pass exactly one object; the no-argument local-scope form is not supported."""
 ...
def total_ordering(cls: Any, /) -> Any:
 """Class decorator that preserves the class object and fills missing ordering methods from `__eq__` plus one of `__lt__`, `__le__`, `__gt__`, or `__ge__`. Explicit methods are never replaced. Applying it mutates the local class namespace."""
 ...
def wraps(wrapped: Any, /) -> Any:
 """Return a decorator that preserves the wrapped callable's supported name, qualified name, docstring, custom attributes, and `__wrapped__` link while keeping the wrapper's call behavior. Applying the returned decorator mutates only that local wrapper function."""
 ...
def TypedDict(name: _str, fields: Any, /) -> Any:
 """Declare a fixed-key dict shape for the editor. Use the functional form (`State = TypedDict(\"State\", {\"mode\": str})`) and annotate records with that name (`state: State = {...}`). Runtime treats this as an inert type marker; the editor uses it for key autocomplete, field type flow, and typo lint."""
 ...
# Return `True` if `value.name` is readable, otherwise `False`. The attribute name must be a string. Useful in duck-typed helpers that accept several documented object shapes, e.g. `hasattr(value, "required_recipe")`. Gameplay result objects keep their fixed fields, so branch on `.status` before reading a documented payload such as `analysis.info`. Missing mounted sub-objects such as `self.sonar` return `False` when the module is not installed.
def hasattr(value: Any, name: _str, /) -> _bool: ...
# Read an attribute by string name, exactly like `value.name`. Without `default`, a missing attribute raises `AttributeError`; with `default`, missing attributes return that fallback. Works for game object properties/methods and built-in methods such as `getattr([1], "append")`. Use with `hasattr()` for duck-typed helpers, not as a replacement for a gameplay result's documented `.status`, `.message`, and payload fields.
@overload
def getattr(value: Any, name: _str, /) -> Any: ...
@overload
def getattr(value: Any, name: _str, default: Any, /) -> Any: ...
def abs(number: Any, /) -> _float:
 """Absolute value."""
 ...
def isclose(a: _float, b: _float, rel_tol: _float = ..., abs_tol: _float = ...) -> _bool:
 """Return `True` when two numbers are close enough to treat as equal. `rel_tol` scales with the compared values; `abs_tol` sets a fixed accepted difference in the same unit, useful for values near zero and physical readings such as coordinates. Tolerances must be non-negative. This is the directly available equivalent of Python's `math.isclose()`."""
 ...
# Return the selected original value whose key is smallest under `<`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `<`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.
@overload
def min(a: _T, b: _T, /, *args: _T, key: Callable[[_T], Any] | None = ...) -> _T: ...
@overload
def min(iterable: Iterable[_T], /, *, key: Callable[[_T], Any] | None = ...) -> _T: ...
@overload
def min(iterable: Iterable[_T], /, *, key: Callable[[_T], Any] | None = ..., default: _U) -> _T | _U: ...
# Return the selected original value whose key is largest under `>`. Accepts multiple values or one finite iterable, handled eagerly within the collection limit. With `key=None` (the default), each value is its own key; otherwise the pure `key=` callback runs once per item and cannot suspend or mutate game state. Keys must be mutually comparable: numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may supply the rich-comparison slots required by `>`. In single-iterable form, `default=v` supplies the result for an empty input; without it, empty input raises.
@overload
def max(a: _T, b: _T, /, *args: _T, key: Callable[[_T], Any] | None = ...) -> _T: ...
@overload
def max(iterable: Iterable[_T], /, *, key: Callable[[_T], Any] | None = ...) -> _T: ...
@overload
def max(iterable: Iterable[_T], /, *, key: Callable[[_T], Any] | None = ..., default: _U) -> _T | _U: ...
def round(number: _float, ndigits: Any = ...) -> _float:
 """Round with ties to even. Without `ndigits` (or with `None`), returns the nearest whole value and rejects NaN/infinity. Integer and boolean inputs remain exact; negative `ndigits` rounds exact integers in decimal. Both arguments accept keyword form."""
 ...
def pow(base: _float, exp: _float, mod: Any = ...) -> _float:
 """`base` raised to `exp`. Optional `mod` performs exact modular exponentiation and accepts negative exponents when the base has a modular inverse. `base`, `exp`, and `mod` accept positional or keyword form."""
 ...
def random() -> _float:
 """Random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.random()` after `import random`."""
 ...
def rand() -> _float:
 """Short alias for `random()`: a random floating-point number `>= 0` and `< 1`. Each successful run begins a new automatic sequence. Also available as `random.rand()` after `import random`."""
 ...
def randint(min: _float, max: _float, /) -> _int:
 """Random integer `N` where `min <= N <= max`. Bounds are inclusive and must be whole numbers. Each successful run begins a new automatic sequence. Useful with `planet.get_bounds()` for random valid coordinates. Also available as `random.randint(min, max)` after `import random`."""
 ...
def sqrt(number: Any, /) -> _float:
 """Square root. Errors on negative input."""
 ...
def floor(number: Any, /) -> _int:
 """Round down to the nearest integer."""
 ...
def ceil(number: Any, /) -> _int:
 """Round up to the nearest integer."""
 ...
def trunc(number: Any, /) -> _int:
 """Drop the fractional part (round toward zero)."""
 ...
def divmod(a: Any, b: Any, /) -> _tuple[_float, ...]:
 """Divides `a` by `b` and returns two values: the quotient rounded down, and the remainder left over. For example, `divmod(19, 2)` returns `(9, 1)` because 2 fits into 19 nine times with 1 left over."""
 ...
def sign(number: Any, /) -> _int:
 """Returns `-1`, `0`, or `1` for negative, zero, or positive input."""
 ...
def exp(number: Any, /) -> _float:
 """`e` raised to the power of the argument."""
 ...
def log(number: Any, base: _float = ..., /) -> _float:
 """Natural log, or log with the given base."""
 ...
def log2(number: Any, /) -> _float:
 """Base-2 logarithm."""
 ...
def log10(number: Any, /) -> _float:
 """Base-10 logarithm."""
 ...
def sin(radians: Any, /) -> _float:
 """Sine of an angle in radians."""
 ...
def cos(radians: Any, /) -> _float:
 """Cosine of an angle in radians."""
 ...
def tan(radians: Any, /) -> _float:
 """Tangent of an angle in radians."""
 ...
def asin(number: Any, /) -> _float:
 """Arc sine. Input must be in `-1 to 1`."""
 ...
def acos(number: Any, /) -> _float:
 """Arc cosine. Input must be in `-1 to 1`."""
 ...
def atan(number: Any, /) -> _float:
 """Arc tangent."""
 ...
def atan2(y: _float, x: _float, /) -> _float:
 """Arc tangent of `y/x`, correctly choosing the quadrant."""
 ...
def degrees(radians: Any, /) -> _float:
 """Convert radians to degrees."""
 ...
def radians(degrees: _float, /) -> _float:
 """Convert degrees to radians."""
 ...
def sorted(sequence: Any, /, *, key: Any = ..., reverse: _bool = ...) -> _list[Any]:
 """Return a new list sorted using `<` between mutually comparable keys. With `key=None` (the default), each value is its own key. Numeric and boolean keys compare across that family, strings compare lexicographically, and user objects may define the exact rich-comparison slots needed by `<`; unsupported pairs raise. `key=` is called once per item and must be pure: it cannot suspend or mutate game state. `reverse` is truth-tested, and the finite input is handled eagerly within the interpreter's collection limit."""
 ...
```

## `reversed`

```python
class reversed(_list[_T], Generic[_T]):
 """Return a reversed list copy of any finite iterable. This consumes the input fully, so an infinite generator exceeds the collection limit; dictionaries (their keys), sets (deterministic insertion order), generators, and custom iterator-protocol classes are accepted."""
 def __init__(self, sequence: Iterable[_T], /) -> None: ...
```

## `zip`

```python
class zip(_list[_Z], Generic[_Z]):
 """Combine iterables into tuples. With no args, returns empty list. With one arg, returns a list of 1-tuples. Stops at the shortest input unless `strict=True`, which raises if input lengths differ."""
 @overload
 def __new__(cls, *, strict: _bool = ...) -> zip[_tuple[Any, ...]]: ...
 @overload
 def __new__(cls, iter1: Iterable[_T], /, *, strict: _bool = ...) -> zip[_tuple[_T]]: ...
 @overload
 def __new__(cls, iter1: Iterable[_T], iter2: Iterable[_U], /, *, strict: _bool = ...) -> zip[_tuple[_T, _U]]: ...
 @overload
 def __new__(cls, iter1: Iterable[_T], iter2: Iterable[_U], iter3: Iterable[_V], /, *, strict: _bool = ...) -> zip[_tuple[_T, _U, _V]]: ...
 @overload
 def __new__(cls, iter1: Iterable[Any], iter2: Iterable[Any], iter3: Iterable[Any], *iterables: Iterable[Any], strict: _bool = ...) -> zip[_tuple[Any, ...]]: ...
 def __init__(self, *iterables: Iterable[Any], strict: _bool = ...) -> None: ...
def isinstance(value: Any, type_or_tuple: Any, /) -> _bool:
 """Check if a value is of the given type. Accepts a builtin type callable (`object`, `int`, `float`, `str`, `list`, `dict`, `set`, `tuple`, `slice`, `bool`), a string type name, a tuple of types, or a type union like `int | float` (matches any). `int` matches whole numbers and booleans, `float` matches fractional / non-finite numbers, and string `\"number\"` remains the broad numeric family for scripts that intentionally accept either."""
 ...
def hex(integer: Any, /) -> _str:
 """Render an integer as a Python-style hex string with `0x` prefix. `hex(255)` → `'0xff'`, `hex(-16)` → `'-0x10'`. Floats reject."""
 ...
def bin(integer: Any, /) -> _str:
 """Render an integer as a binary string with `0b` prefix. `bin(10)` → `'0b1010'`. Floats reject."""
 ...
def oct(integer: Any, /) -> _str:
 """Render an integer as an octal string with `0o` prefix. `oct(8)` → `'0o10'`. Floats reject."""
 ...
def repr(value: Any, /) -> _str:
 """Developer-readable string for a value, with quotes around strings and nested-repr for containers. `repr([1, \"a\"])` → `\"[1, 'a']\"` (note the quotes around `'a'`). Use when you want to see the value's structure, not its display form. Also reached via f-string `!r` conversion: `f\"{name!r}\"`."""
 ...
def callable(value: Any, /) -> _bool:
 """`True` when a value has a call surface: user-defined `def` / `lambda`, built-in functions, classes, bound methods, and class instances whose type defines `__call__`. Like Python, this checks the type-level call slot without executing its descriptor; an actual call can still raise if that slot resolves to a non-callable value."""
 ...
def dir(value: Any, /) -> _list[Any]:
 """Lists the method and attribute names available on `value`, sorted: runtime introspection for discovering what you can do with something. On a component or game object (`dir(self)`, `dir(get_component(\"smelter_1\"))`) it returns that object's callable methods and properties, straight from the console. On a built-in container it returns the type's methods: `dir([1, 2])` → `\"append\"`, `\"pop\"`, …; `dir(\"hi\")` → `\"upper\"`, `\"split\"`, …. Values with no members (numbers, booleans, `None`) return an empty list. Pass exactly one value: the no-argument `dir()` that lists current-scope names is not supported."""
 ...
# Return an iterator. Built-in iterables use a compatibility list-shaped iterator; protocol iterators and generators keep their identity, so `iter(iterator) is iterator`. `for` advances generators and custom iterators one item at a time, so it can break out of an infinite iterator. Consumers that must finish, such as `list(...)`, remain bounded.
@overload
def iter(iterable: _IteratorT) -> _IteratorT: ...
@overload
def iter(iterable: Iterable[_T]) -> _list[_T]: ...
# Advance an iterator by one item. Iterators returned by `iter()` and custom `__next__` iterators retain their cursor across calls. Ordinary lists keep the compatibility behavior of popping the front; other non-iterator iterables return their first materialized item. Exhaustion raises `StopIteration` unless `default` is given.
@overload
def next(iterator: Iterator[_T]) -> _T: ...
@overload
def next(iterator: Iterator[_T], default: _U) -> _T | _U: ...
@overload
def next(iterator: Any, default: Any = ...) -> Any: ...
def hash(value: Any, /) -> _int:
 """Hash any hashable value to an integer: strings, numbers, booleans, `None`, tuples of hashable values, functions, classes, and hashable user instances. Instances are identity-hashable by default; defining `__eq__` without `__hash__` makes them unhashable, and a custom `__hash__` controls `hash(obj)`, dict keys, and set membership."""
 ...
def issubclass(cls: Any, class_or_tuple: Any, /) -> _bool:
 """`True` if `cls` is the given class or a subclass of it (or of any class in the tuple), per the MRO. `issubclass(Dog, Animal)` is `True`; every class is a subclass of `object`."""
 ...
def pairwise(iterable: Any, /) -> _list[_tuple[Any, ...]]:
 """Return neighboring pairs from an iterable. `pairwise([1,2,3])` → `[(1,2), (2,3)]`."""
 ...
def batched(iterable: Any, size: _float, /) -> _list[_tuple[Any, ...]]:
 """Split an iterable into tuple batches of `size`. The final batch may be shorter. `batched([1,2,3,4,5], 2)` → `[(1,2), (3,4), (5,)]`."""
 ...
def starmap(fn: Any, iterable: Any, /) -> _list[Any]:
 """Call pure `fn` with each tuple/list item unpacked as arguments. The callback cannot suspend the script or mutate game state. `starmap(pow, [(2,3), (3,2)])` → `[8,9]`. An empty input never inspects or calls `fn`."""
 ...
def flatten(iterable: Any, /) -> _list[Any]:
 """Flatten one level of nested iterables into a list. `flatten([[1,2], (3,4)])` → `[1,2,3,4]`."""
 ...
def count_by(iterable: Any, key_fn: Any = ..., /) -> _dict[Any, _float]:
 """Count items into a dict. Without `key_fn` (or with `None`), counts each item. With a pure `key_fn`, counts the computed key; callbacks cannot suspend the script or mutate game state: `count_by(items, lambda x: x.kind)`. An empty input never inspects or calls the key function."""
 ...
def chain(*iterables: Any) -> _list[Any]:
 """Flattens any number of iterables into one list, in order. `chain([1,2], [3,4])` → `[1,2,3,4]`. Accepts lists, tuples, strings, sets."""
 ...
def accumulate(iterable: Any, /) -> _list[_float]:
 """Running prefix sum over any finite iterable. `accumulate([1,2,3,4])` → `[1,3,6,10]`. Numeric items only; booleans participate as integers and arbitrarily large integers remain exact."""
 ...
def combinations(iterable: Any, k: Any, /) -> _list[_tuple[Any, ...]]:
 """All `k`-element combinations from an iterable, in input order, no repeats. Returns a list of tuples. `combinations([1,2,3], 2)` → `[(1,2), (1,3), (2,3)]`."""
 ...
def permutations(iterable: Any, k: Any = ..., /) -> _list[_tuple[Any, ...]]:
 """All `k`-length ordered arrangements from an iterable. `k` defaults to the full length. `permutations([1,2,3])` → all 6 orderings as tuples."""
 ...
def product(*iterables: Any, repeat: _float = ...) -> _list[_tuple[Any, ...]]:
 """Cartesian product. `product([0,1], [0,1])` → `[(0,0), (0,1), (1,0), (1,1)]`. Each input must be iterable; result is a list of tuples. Optional keyword `repeat=N` repeats the input pools, matching `itertools.product([0,1], repeat=2)`."""
 ...
```
