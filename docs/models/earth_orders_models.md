# Models: Earth Orders & Logistics Demands Models

Granular data models and return types extracted from `__builtins__.pyi`.

## `Order`

```python
class Order:
    """orders.list_orders() / orders.list_upcoming_orders() / orders.list_weekly_orders() / orders.get_order() / orders.completed_orders() (Aufträge der Erde)"""
    id: _str
    name: _str
    requires: _dict[_str, _int]
    shipped: _dict[_str, _int]
    reward_credits: _int
    reward_kind: Literal["recipe", "tech"] | None
    reward_label: _str | None
    status: Literal["upcoming", "active", "completed"]
    kind: Literal["campaign", "weekly"]
    expires_day: _int | None
    contractor_id: Literal["helios_orbital", "spire_research", "vestibule_logistics"] | None
    contractor_name: _str | None
```

## `Orders`

```python
class Orders(Component):
    """Aufträge der Erde: Lies die aktuellen Aufträge der Erde, künftige Anforderungen und Belohnungen der Kampagne sowie den Verlauf abgeschlossener Kampagnenaufträge über `get_component(\"orders\")`. Skripte von Versorgungsdocks können anhand von Kampagnenaufträgen und wöchentlichen Aufträgen entscheiden, was sie versenden; Übersichten können den Fortschritt anzeigen. Skripte können Aufträge der Erde weder erstellen noch stornieren. Bioaufträge stammen stattdessen von einer Biobörse."""
    name: _str
    def list_orders(self) -> _list[Order]:
        """Aktuelle Kampagnenaufträge der Auftraggeber als Liste von `Order`-Objekten in fester Reihenfolge. Diese Aufträge verfallen nie und verschwinden aus der Liste, sobald alles versendet wurde. Eine leere Liste bedeutet, dass derzeit keine Lieferung für einen Auftraggeber möglich ist. Siehe `Order`."""
        ...
    def list_upcoming_orders(self) -> _list[Order]:
        """Plane künftige Produktion und Belohnungen anhand der anstehenden Kampagnenaufträge der Auftraggeber. Die Aufträge stehen in der Reihenfolge der Kampagne; die Abfolge jedes Auftraggebers bleibt erhalten. Aktuelle und abgeschlossene Aufträge sowie wöchentliche Aufträge der Erde sind ausgeschlossen. Anstehende Aufträge können Versorgungsdocks erst zugewiesen werden, wenn sie aktuell sind. Siehe `Order`."""
        ...
    def list_weekly_orders(self) -> _list[Order]:
        """Die fünf aktuellen wöchentlichen Aufträge der Erde, einschließlich der in diesem Zyklus bereits erfüllten Angebote. Gibt eine leere Liste zurück, bis eine geeignete Produktionskette verfügbar ist. Wöchentliche Objekte haben `.kind == \"weekly\"` und `.expires_day`, aber keinen Auftraggeber; sie bieten ausschließlich Credits als Belohnung und ihr `.status` lautet `\"active\"` oder `\"completed\"`. Die gesamte Liste wird alle sieben Tage ersetzt."""
        ...
    def get_order(self, order_id: _str) -> Order | None:
        """Suche einen bestimmten Auftrag der Erde anhand seiner ID, auch einen anstehenden Kampagnenauftrag zur Planung. Anstehende Aufträge können Versorgungsdocks erst zugewiesen werden, wenn sie aktuell sind. Unbekannte oder abgelaufene IDs wöchentlicher Aufträge liefern `None`; abgeschlossene wöchentliche Aufträge bleiben nur bis zur Aktualisierung ihrer Auftragstafel sichtbar. Siehe `Order`."""
        ...
    def completed_orders(self) -> _list[Order]:
        """Dauerhafter Verlauf der Kampagnenaufträge der Auftraggeber, nach Abschlusszeit sortiert (älteste zuerst). Abgeschlossene wöchentliche Aufträge bleiben auf der aktuellen wöchentlichen Auftragstafel und sind in diesem Verlauf bewusst nicht enthalten."""
        ...
```
