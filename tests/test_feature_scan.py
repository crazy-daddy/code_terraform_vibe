"""devtools/code_scan/feature_scan.py: each pattern, ipc key resolution and stable hit ids."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devtools", "code_scan"))

import feature_scan as fs

SOURCE = """
STATUS_KEY = "drill.status"

class Slot:
    def __init__(self, a, b):
        self.a = a
        self.b = b

class Controller(Base):
    def __init__(self, a, b):
        self.a = a
        self.b = b

class Ranked:
    def __lt__(self, other): return True
    def __le__(self, other): return True

class Store:
    def get_level(self): return 1
    def set_level(self, v): pass
    def count(self): return self._bin.count()
    def stacks(self): return self._bin.stacks()
    def empty(self): return self._bin.empty()

def pick(kind):
    if kind == "a":
        return 1
    elif kind == "b":
        return 2
    elif kind == "c":
        return 3

def triple():
    return 1, 2, 3

def sort_key(x):
    return x, x, x

def read(row):
    return row[0] + row[1] + row[2]

def publish(archive, comms):
    archive.get(STATUS_KEY)
    archive.set("fleet.status", {"name": 1, "state": 2, "tick": 3})
    comms.broadcast("bio_orders", {})
"""


def scan(source=SOURCE):
    scanner = fs.Scanner()
    scanner.scan_source("lib/x.py", source)
    scanner.finish()
    return {h.id: h for h in scanner.hits}


class FeatureScanTest(unittest.TestCase):
    def test_patterns(self):
        ids = scan()
        expected = [
            "lib/x.py::value_class::Slot",
            "lib/x.py::ordering::Ranked",
            "lib/x.py::property_pair::Store.get_level",
            "lib/x.py::delegation::Store->_bin",
            "lib/x.py::elif_chain::pick:kind",
            "lib/x.py::tuple_return::triple",
            "lib/x.py::tuple_index::read:row",
            "*::ipc_key::archive:'drill.status'",
            "*::ipc_key::archive:'fleet.status'",
            "*::ipc_key::comms:'bio_orders'",
        ]
        for hit_id in expected:
            self.assertIn(hit_id, ids)

    def test_skips(self):
        ids = scan()
        self.assertNotIn("lib/x.py::value_class::Controller", ids)  # subclasses are controllers, not records
        self.assertNotIn("lib/x.py::tuple_return::sort_key", ids)
        self.assertFalse([i for i in ids if "dict_shape" in i])  # one 3-key site is below the threshold

    def test_dict_shape_groups_sites(self):
        source = 'a = {"x": 1, "y": 2, "z": 3}\nb = {"z": 0, "y": 0, "x": 0}\nc = a["x"]\n'
        hit = scan(source)["*::dict_shape::x,y,z"]
        self.assertEqual(len(hit.sites), 2)
        self.assertIn("key reads 1", hit.detail)

    def test_ids_ignore_line_numbers(self):
        moved = "\n\n\n" + SOURCE
        self.assertEqual(set(scan()), set(scan(moved)))


if __name__ == "__main__":
    unittest.main()
