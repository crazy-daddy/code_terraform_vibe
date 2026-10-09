"""Plane geometry on world coordinates (metres)."""


def distance(a, b):
    """Straight-line metres between two (x, y) points."""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5
