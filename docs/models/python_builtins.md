# Models: Python Standard Builtin Emulations

Granular data models and return types extracted from `__builtins__.pyi`.

## `Match`

```python
class Match:
    """`re.search()` · `re.match()` · `re.fullmatch()`"""
    pattern: _str
    string: _str
    def group(self, index: _int = ...) -> _str | None:
        """Return the matched text for group `index`. Group `0` is the whole match. Optional groups that did not match return `None`; an out-of-range group raises."""
        ...
    def groups(self, default: object = ...) -> _tuple[_str | None, ...]:
        """Return a tuple of captured groups, excluding group `0`. Groups that did not match use `default`, which is `None` if omitted."""
        ...
    def start(self, index: _int = ...) -> _int:
        """Start character index for the group. Unmatched optional groups return `-1`."""
        ...
    def end(self, index: _int = ...) -> _int:
        """End character index for the group. Unmatched optional groups return `-1`."""
        ...
    def span(self, index: _int = ...) -> _tuple[_int, ...]:
        """Return `(start, end)` for the group. Unmatched optional groups return `(-1, -1)`."""
        ...
```

## `enumerate`

```python
class enumerate(_list[_tuple[_int, _T]], Generic[_T]):
    """List of (index, value) pairs. Optional integer `start=N` shifts the index: `enumerate(items, start=1)` for 1-based indexing. Arbitrarily large integer starts remain exact. `start` may be positional or keyword, but not both."""
    def __init__(self, sequence: Iterable[_T], /, start: _int = ...) -> None: ...
```

## `filter`

```python
class filter(_list[_T], Generic[_T]):
    """Keep items for which pure `fn(item)` is truthy; callbacks cannot suspend the script or mutate game state. `filter(None, iter)` keeps every truthy item without a callback. An empty input never inspects or calls `fn`."""
    def __init__(self, fn: Callable[[_T], object] | None, iterable: Iterable[_T], /) -> None: ...
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
```
