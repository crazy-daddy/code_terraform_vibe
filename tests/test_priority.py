"""priority: the 0-999 priority scale and the ladder helpers (pure functions)."""

import unittest

import harness  # noqa: F401  (puts the lib dirs on sys.path)
import priority as pr


class ScaleTests(unittest.TestCase):
    def test_band_fine_name_clamp(self):
        self.assertEqual(pr.band(437), 400)
        self.assertEqual(pr.fine(437), 37)
        self.assertEqual(pr.band(0), 0)
        self.assertEqual(pr.band_name(650), "order")
        self.assertEqual(pr.band_name(100), "stock")
        self.assertEqual(pr.band_name(50), "none")
        self.assertEqual(pr.clamp(-5), 0)
        self.assertEqual(pr.clamp(1500), 999)
        self.assertEqual(pr.clamp(42.9), 42)

    def test_order_prio(self):
        self.assertEqual(pr.order_prio(0, score_max=10), 600)
        self.assertEqual(pr.order_prio(10, score_max=10), 699)
        self.assertEqual(pr.order_prio(5, score_max=10), 649)
        self.assertEqual(pr.order_prio(50, score_max=10), 699)
        self.assertEqual(pr.order_prio(-3, score_max=10), 600)
        self.assertEqual(pr.order_prio(5, score_max=0), 699)

    def test_order_prio_override_wins(self):
        self.assertEqual(pr.order_prio(0, override=640, score_max=10), 640)
        self.assertEqual(pr.order_prio(10, override=850, score_max=10), 850)
        self.assertEqual(pr.order_prio(10, override=50, score_max=10), 50)
        self.assertEqual(pr.order_prio(10, override=5000, score_max=10), 999)

    def test_blueprint_prio(self):
        self.assertEqual(pr.blueprint_prio(False, 0), 899)
        self.assertEqual(pr.blueprint_prio(True, 0), 799)
        self.assertEqual(pr.blueprint_prio(True, None), 799)
        self.assertEqual(pr.blueprint_prio(True, 1), 399)
        self.assertEqual(pr.blueprint_prio(True, 2), 389)
        self.assertEqual(pr.blueprint_prio(True, 3), 379)
        self.assertEqual(pr.blueprint_prio(True, 50), 300)

    def test_ceil_units(self):
        self.assertEqual(pr.ceil_units(2.0), 2)
        self.assertEqual(pr.ceil_units(2.01), 3)
        self.assertEqual(pr.ceil_units(0), 0)


class LadderBuildTests(unittest.TestCase):
    def test_ladder_cleans_input(self):
        self.assertEqual(pr.ladder([[100, 100], [400, 30]]), [[400, 30], [100, 100]])
        self.assertEqual(pr.ladder([[400, 30], "junk", [1], [1, 2, 3], ["a", 5], [200, 0], [300, -4]]), [[400, 30]])
        self.assertEqual(pr.ladder([[400, 30], [400, 50]]), [[400, 50]])
        self.assertEqual(pr.ladder([[400, 30], [100, 20]]), [[400, 30]])
        self.assertEqual(pr.ladder([(400, 30), (100, 100)]), [[400, 30], [100, 100]])
        self.assertEqual(pr.ladder(None), [])
        self.assertEqual(pr.ladder({"a": 1}), [])

    def test_level_and_total(self):
        lv = [[400, 30], [100, 100]]
        self.assertEqual(pr.ladder_level(lv, 400), 30)
        self.assertEqual(pr.ladder_level(lv, 300), 30)
        self.assertEqual(pr.ladder_level(lv, 100), 100)
        self.assertEqual(pr.ladder_level(lv, 500), 0)
        self.assertEqual(pr.ladder_total(lv), 100)
        self.assertEqual(pr.ladder_level([], 100), 0)
        self.assertEqual(pr.ladder_total([]), 0)

    def test_raise(self):
        lv = [[400, 30], [100, 100]]
        self.assertEqual(pr.ladder_raise(lv, 400, 20), [[400, 30], [100, 100]])
        self.assertEqual(pr.ladder_raise(lv, 400, 50), [[400, 50], [100, 100]])
        self.assertEqual(lv, [[400, 50], [100, 100]])
        lv = [[400, 30], [100, 100]]
        self.assertEqual(pr.ladder_raise(lv, 600, 50), [[600, 50], [100, 100]])
        lv = [[400, 30], [100, 100]]
        self.assertEqual(pr.ladder_raise(lv, 200, 60), [[400, 30], [200, 60], [100, 100]])
        self.assertEqual(pr.ladder_raise([], 300, 7), [[300, 7]])

    def test_raise_noop_and_in_place(self):
        lv = [[400, 30]]
        self.assertIs(pr.ladder_raise(lv, 600, 0), lv)
        self.assertIs(pr.ladder_raise(lv, 600, -3), lv)
        self.assertEqual(lv, [[400, 30]])
        self.assertIs(pr.ladder_raise(lv, 500, 40), lv)
        self.assertEqual(lv, [[500, 40]])

    def test_add(self):
        lv = [[400, 30], [100, 100]]
        self.assertIs(pr.ladder_add(lv, 400, 5), lv)
        self.assertEqual(lv, [[400, 35], [100, 105]])
        self.assertEqual(pr.ladder_add([[600, 10], [100, 100]], 400, 5), [[600, 10], [400, 15], [100, 105]])
        self.assertEqual(pr.ladder_add([[400, 30], [100, 100]], 600, 5), [[600, 5], [400, 35], [100, 105]])
        self.assertEqual(pr.ladder_add([[600, 10]], 100, 5), [[600, 10], [100, 15]])
        self.assertEqual(pr.ladder_add([], 300, 4), [[300, 4]])
        lv = [[400, 30]]
        pr.ladder_add(lv, 400, 0)
        self.assertEqual(lv, [[400, 30]])

    def test_max_leaves_inputs(self):
        a = [[600, 10], [100, 50]]
        b = [[400, 30], [100, 40]]
        self.assertEqual(pr.ladder_max(a, b), [[600, 10], [400, 30], [100, 50]])
        self.assertEqual(a, [[600, 10], [100, 50]])
        self.assertEqual(b, [[400, 30], [100, 40]])
        self.assertEqual(pr.ladder_max([], b), b)

    def test_scale(self):
        lv = [[600, 3], [100, 10]]
        self.assertEqual(pr.ladder_scale(lv, 2.5), [[600, 8], [100, 25]])
        self.assertEqual(lv, [[600, 3], [100, 10]])
        self.assertEqual(pr.ladder_scale(lv, 0), [])
        self.assertEqual(pr.ladder_scale(lv, 1), lv)

    def test_from_levels(self):
        self.assertEqual(pr.from_levels(100, 30), [[400, 30], [100, 100]])
        self.assertEqual(pr.from_levels(100, None), [[400, 100]])
        self.assertEqual(pr.from_levels(100, 100), [[400, 100]])
        self.assertEqual(pr.from_levels(100, 0), [[100, 100]])
        self.assertEqual(pr.from_levels(0, 5), [])
        self.assertEqual(pr.from_levels(100, 30, need_prio=650, target_prio=320), [[650, 30], [320, 100]])


class DeficitTests(unittest.TestCase):
    LV = [[600, 10], [400, 30], [100, 100]]

    def test_ladder_deficits(self):
        self.assertEqual(pr.ladder_deficits(self.LV, 12), [(400, 18), (100, 70)])
        self.assertEqual(pr.ladder_deficits(self.LV, 0), [(600, 10), (400, 20), (100, 70)])
        self.assertEqual(pr.ladder_deficits(self.LV, 100), [])
        self.assertEqual(pr.ladder_deficits([], 0), [])

    def test_band_deficits(self):
        self.assertEqual(pr.band_deficits([[650, 10], [620, 20]], 0), {600: 20})
        self.assertEqual(pr.band_deficits(self.LV, 12), {400: 18, 100: 70})
        self.assertEqual(pr.band_deficits(self.LV, 100), {})

    def test_top_deficit(self):
        self.assertEqual(pr.top_deficit(self.LV, 0), (600, 10))
        self.assertEqual(pr.top_deficit(self.LV, 12), (400, 18))
        self.assertEqual(pr.top_deficit(self.LV, 100), (0, 0))
        self.assertEqual(pr.top_deficit([], 0), (0, 0))

    def test_deficits_text(self):
        self.assertEqual(pr.deficits_text([]), "none")
        self.assertEqual(pr.deficits_text([(400, 18), (100, 70)]), "need(400) 18, stock(100) 70")


if __name__ == "__main__":
    unittest.main()
