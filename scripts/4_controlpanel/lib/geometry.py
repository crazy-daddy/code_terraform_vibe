"""Plane geometry on world coordinates (metres)."""


def distance(a, b):
    """Straight-line metres between two (x, y) points."""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def ceil_int(value):
    """Smallest int >= value. The game interpreter has no math module."""
    whole = int(value)
    return whole + 1 if value > whole else whole


def dist(ax, ay, bx, by):
    """Straight-line metres between (ax, ay) and (bx, by), for callers holding bare coordinates."""
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5
