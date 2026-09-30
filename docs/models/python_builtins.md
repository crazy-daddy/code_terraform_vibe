# Models: Python Standard Builtin Emulations

Granular data models and return types extracted from `__builtins__.pyi`.

## `Match`

```python
class Match:
    """`re.search()` · `re.match()` · `re.fullmatch()`"""
    pattern: _str
    string: _str
    def group(self, group: _int | _str = ..., /, *groups: _int | _str) -> _str | None:
        """Gibt den übereinstimmenden Text einer Gruppe zurück, wahlweise über ihre Nummer oder über ihren Namen aus `(?P<name>...)`. Gruppe `0` umfasst die gesamte Übereinstimmung; mehrere Gruppen ergeben ein Tupel: `m.group(1, \"unit\")`. Optionale Gruppen ohne Übereinstimmung geben `None` zurück; eine unbekannte Gruppe löst einen Fehler aus. `m[1]` entspricht `m.group(1)`."""
        ...
    def groups(self, default: object = ...) -> _tuple[_str | None, ...]:
        """Gibt ein Tupel der erfassten Gruppen zurück, ohne Gruppe `0`. Gruppen ohne Übereinstimmung erhalten den Wert `default`, der bei Auslassung `None` ist."""
        ...
    def start(self, index: _int | _str = ...) -> _int:
        """Startindex der Zeichen für die Gruppe. Nicht übereinstimmende optionale Gruppen geben `-1` zurück."""
        ...
    def end(self, index: _int | _str = ...) -> _int:
        """Endindex der Zeichen für die Gruppe. Nicht übereinstimmende optionale Gruppen geben `-1` zurück."""
        ...
    def span(self, index: _int | _str = ...) -> _tuple[_int, ...]:
        """Gibt `(start, end)` für die Gruppe zurück. Nicht übereinstimmende optionale Gruppen geben `(-1, -1)` zurück."""
        ...
    def __getitem__(self, group: _int | _str, /) -> _str | None:
        """`m[1]` oder `m[\"name\"]`: derselbe Text wie `m.group(1)` oder `None` für eine Gruppe, die nicht an der Übereinstimmung beteiligt war."""
        ...
    def groupdict(self, default: object = ...) -> _dict[_str, _str | None]:
        """Gibt ein dict zurück, das jedem Gruppennamen den Text seiner benannten Gruppe zuordnet. Benannte Gruppen ohne Übereinstimmung erhalten `default`, das ohne Angabe `None` ist."""
        ...
    def expand(self, template: _str, /) -> _str:
        """Füllt eine Ersetzungsvorlage wie `re.sub()` mit den Werten dieser Übereinstimmung aus: `m.expand(r\"\\2-\\1\")`."""
        ...
    lastindex: _int | None
    lastgroup: _str | None
    pos: _int
    endpos: _int
    re: Pattern
```

## `Pattern`

```python
class Pattern:
    """`re.compile()`"""
    pattern: _str
    flags: _int
    groups: _int
    groupindex: _dict[_str, _float]
    def search(self, string: _str, pos: _int = ..., endpos: _int | None = ...) -> Match | None:
        """Wie `re.search()` mit diesem Muster, sucht aber nur zwischen `pos` und `endpos`: ein `Match` oder `None`, wenn dort nichts übereinstimmt."""
        ...
    def match(self, string: _str, pos: _int = ..., endpos: _int | None = ...) -> Match | None:
        """Wie `re.match()` mit diesem Muster, verankert an `pos`: ein `Match` oder `None`, wenn der Text an `pos` nicht übereinstimmt."""
        ...
    def fullmatch(self, string: _str, pos: _int = ..., endpos: _int | None = ...) -> Match | None:
        """Wie `re.fullmatch()` mit diesem Muster, angewendet auf den Text von `pos` bis `endpos`: ein `Match` oder `None`, wenn ein Teil davon ohne Übereinstimmung bleibt."""
        ...
    def findall(self, string: _str, pos: _int = ..., endpos: _int | None = ...) -> _list[Any]:
        """Wie `re.findall()` mit diesem Muster, zwischen `pos` und `endpos`."""
        ...
    def finditer(self, string: _str, pos: _int = ..., endpos: _int | None = ...) -> Iterator[Match]:
        """Wie `re.finditer()` mit diesem Muster, zwischen `pos` und `endpos`."""
        ...
    def sub(self, repl: _str | Callable[..., Any], string: _str, count: _int = ...) -> _str:
        """Wie `re.sub()` mit diesem Muster."""
        ...
    def subn(self, repl: _str | Callable[..., Any], string: _str, count: _int = ...) -> _tuple[_str, _int]:
        """Wie `re.subn()` mit diesem Muster."""
        ...
    def split(self, string: _str, maxsplit: _int = ...) -> _list[Any]:
        """Wie `re.split()` mit diesem Muster."""
        ...
```

## `enumerate`

```python
class enumerate(_list[_tuple[_int, _T]], Generic[_T]):
    """Liste von Paaren aus Index und Wert. Das optionale ganzzahlige `start=N` verschiebt den Index: `enumerate(items, start=1)` für eine Zählung ab 1. Auch beliebig große ganzzahlige Startwerte bleiben exakt. `start` kann als Positions- oder Schlüsselwortargument übergeben werden, aber nicht als beides zugleich. Bei einem Generator wird statt einer Liste ein Lazy-Iterator zurückgegeben, der jedes Element erst holt, wenn die Schleife es anfordert."""
    @overload
    def __new__(cls, sequence: Generator[_T, Any, Any], /, start: _int = ...) -> Iterator[_tuple[_int, _T]]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, sequence: Iterable[_T], /, start: _int = ...) -> enumerate[_T]: ...
    def __init__(self, sequence: Iterable[_T], /, start: _int = ...) -> None: ...
```

## `filter`

```python
class filter(_list[_T], Generic[_T]):
    """Behält Elemente, für die das Ergebnis der reinen Funktion `fn(item)` als wahr ausgewertet wird; Rückruffunktionen dürfen das Skript weder unterbrechen noch den Spielzustand verändern. `filter(None, iter)` behält ohne Rückruffunktion alle Elemente, die als wahr ausgewertet werden. Bei leerer Eingabe wird `fn` weder geprüft noch aufgerufen. Bei einem Generator wird statt einer Liste ein Lazy-Iterator zurückgegeben."""
    @overload
    def __new__(cls, fn: Callable[[_T], object] | None, iterable: Generator[_T, Any, Any], /) -> Iterator[_T]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, fn: Callable[[_T], object] | None, iterable: Iterable[_T], /) -> filter[_T]: ...
    def __init__(self, fn: Callable[[_T], object] | None, iterable: Iterable[_T], /) -> None: ...
```

## `map`

```python
class map(_list[_R], Generic[_R]):
    """Wendet die reine Funktion `fn` auf die jeweils entsprechenden Elemente aller iterierbaren Werte an. Rückruffunktionen dürfen das Skript weder unterbrechen noch den Spielzustand verändern. Bei einer Eingabe wird `fn(x)` aufgerufen, bei mehreren Eingaben `fn(x, y, ...)`. Die Verarbeitung endet mit der kürzesten Eingabe, außer wenn `strict=True` gesetzt ist; dann lösen unterschiedliche Längen einen Fehler aus. Wenn kein Ergebniselement entsteht, wird `fn` weder geprüft noch aufgerufen. Ist eine Eingabe ein Generator, wird statt einer Liste ein Lazy-Iterator zurückgegeben."""
    @overload
    def __new__(cls, fn: Callable[[_T], _R], iter1: Generator[_T, Any, Any], /, *, strict: _bool = ...) -> Iterator[_R]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, fn: Callable[[_T, _U], _R], iter1: Generator[_T, Any, Any], iter2: Iterable[_U], /, *, strict: _bool = ...) -> Iterator[_R]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, fn: Callable[[_T, _U], _R], iter1: Iterable[_T], iter2: Generator[_U, Any, Any], /, *, strict: _bool = ...) -> Iterator[_R]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, fn: Callable[..., _R], iter1: Iterable[Any], *iterables: Iterable[Any], strict: _bool = ...) -> map[_R]: ...
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
    """Erstellt eine Liste ganzer Zahlen von `start` bis ausschließlich `stop` in Schritten von `step`. `range(5)` → `[0,1,2,3,4]`. Grenzen und Schrittweite bleiben exakte Ganzzahlen beliebiger Größe; die erzeugte Liste muss jedoch innerhalb der Größenbeschränkung des Interpreters für Sammlungen liegen. Alle Argumente müssen Ganzzahlen sein; `step=0` und Bruchzahlen werden abgewiesen. Ein negatives `step` zählt abwärts: `range(5, 0, -1)` → `[5,4,3,2,1]`."""
    @overload
    def __init__(self, stop: _int, /) -> None: ...
    @overload
    def __init__(self, start: _int, stop: _int, step: _int = ..., /) -> None: ...
```

## `reversed`

```python
class reversed(_list[_T], Generic[_T]):
    """Gibt eine Listenkopie eines beliebigen endlichen iterierbaren Objekts mit umgekehrter Elementreihenfolge zurück. Die Eingabe wird vollständig durchlaufen; ein unendlicher Generator überschreitet daher die Größenbeschränkung für Sammlungen. Wörterbücher (über ihre Schlüssel), Sets (in deterministischer Einfügereihenfolge), Generatoren und eigene Klassen mit Iteratorprotokoll werden akzeptiert."""
    def __init__(self, sequence: Iterable[_T], /) -> None: ...
```

## `zip`

```python
class zip(_list[_Z], Generic[_Z]):
    """Kombiniert iterierbare Objekte zu Tupeln. Ohne Argumente wird eine leere Liste zurückgegeben. Mit einem Argument wird eine Liste aus 1-Tupeln zurückgegeben. Die Verarbeitung endet bei der kürzesten Eingabe, sofern nicht `strict=True` gesetzt ist; dann lösen unterschiedliche Eingabelängen einen Fehler aus. Ist eine Eingabe ein Generator, wird statt einer Liste ein Lazy-Iterator zurückgegeben."""
    @overload
    def __new__(cls, *, strict: _bool = ...) -> zip[_tuple[Any, ...]]: ...
    @overload
    def __new__(cls, iter1: Generator[_T, Any, Any], /, *, strict: _bool = ...) -> Iterator[_tuple[_T]]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, iter1: Iterable[_T], /, *, strict: _bool = ...) -> zip[_tuple[_T]]: ...
    @overload
    def __new__(cls, iter1: Generator[_T, Any, Any], iter2: Iterable[_U], /, *, strict: _bool = ...) -> Iterator[_tuple[_T, _U]]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, iter1: Iterable[_T], iter2: Generator[_U, Any, Any], /, *, strict: _bool = ...) -> Iterator[_tuple[_T, _U]]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __new__(cls, iter1: Iterable[_T], iter2: Iterable[_U], /, *, strict: _bool = ...) -> zip[_tuple[_T, _U]]: ...
    @overload
    def __new__(cls, iter1: Iterable[_T], iter2: Iterable[_U], iter3: Iterable[_V], /, *, strict: _bool = ...) -> zip[_tuple[_T, _U, _V]]: ...
    @overload
    def __new__(cls, iter1: Iterable[Any], iter2: Iterable[Any], iter3: Iterable[Any], *iterables: Iterable[Any], strict: _bool = ...) -> zip[_tuple[Any, ...]]: ...
    def __init__(self, *iterables: Iterable[Any], strict: _bool = ...) -> None: ...
```
