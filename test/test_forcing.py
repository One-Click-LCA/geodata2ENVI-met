# coding=utf-8
"""core.forcing.diurnal_profile (plain Python)."""

import unittest

from .plugin_env import import_plugin_module


class DiurnalProfileTest(unittest.TestCase):

    def setUp(self):
        self.profile = import_plugin_module('core.forcing').diurnal_profile

    def test_extremes_and_continuity(self):
        for low_hour, high_hour in ((5, 16), (16, 5), (0, 23), (23, 0)):
            values = self.profile(low_hour, high_hour, 10.0, 20.0)
            self.assertEqual(len(values), 24)
            self.assertAlmostEqual(values[low_hour], 10.0)
            self.assertAlmostEqual(values[high_hour], 20.0)
            self.assertAlmostEqual(min(values), 10.0)
            self.assertAlmostEqual(max(values), 20.0)
            # piecewise linear: steps never exceed the steeper of the two slopes
            rise = (high_hour - low_hour) % 24
            steepest = 10.0 / min(rise, 24 - rise)
            for hour in range(24):
                self.assertLessEqual(abs(values[hour] - values[hour - 1]), steepest + 1e-9)

    def test_same_hour_is_rejected(self):
        with self.assertRaises(ValueError):
            self.profile(7, 7, 10.0, 20.0)


if __name__ == '__main__':
    unittest.main()
