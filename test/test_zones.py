# coding=utf-8
"""core.zones and core.stats: exact cell fractions, vertical selection and weighted statistics."""

import datetime as dt
import math
import os
import random
import shutil
import tempfile
import unittest

import numpy as np

from . import fixtures as fx
from .plugin_env import import_plugin_module


def model_to_utm(grid, x, y):
    r = math.radians(grid.rotation)
    return grid.x0 + x * math.cos(r) + y * math.sin(r), grid.y0 - x * math.sin(r) + y * math.cos(r)


def zone_from_model(zones, grid, rings, zone_id=1, name='z'):
    """A Zone from rings given in model coordinates."""
    utm = []
    for ring in rings:
        e, n = model_to_utm(grid, np.array([p[0] for p in ring]), np.array([p[1] for p in ring]))
        utm.append(np.column_stack([e, n]))
    return zones.Zone(zone_id, name, [(utm[0], utm[1:])])


class CellFractionTest(unittest.TestCase):

    def setUp(self):
        self.readers = import_plugin_module('core.readers')
        self.zones = import_plugin_module('core.zones')
        self.grid = self.readers.Grid(dx=[2.0] * 20, dy=[2.0] * 15, x0=500000.0, y0=5400000.0, rotation=20.0,
                                      utm_zone=32, latitude=48.0)

    def fractions(self, rings):
        zone = zone_from_model(self.zones, self.grid, rings)
        j, i, f = self.zones.cell_fractions(self.grid, zone)
        return {(int(a), int(b)): float(c) for a, b, c in zip(j, i, f)}, zone

    def test_full_and_half_cells_on_a_rotated_grid(self):
        # cells i = 2..4 fully, i = 5 half; rows j = 3..4
        fractions, _ = self.fractions([[(4, 6), (11, 6), (11, 10), (4, 10)]])
        expected = {(j, i): 1.0 for j in (3, 4) for i in (2, 3, 4)}
        expected.update({(j, 5): 0.5 for j in (3, 4)})
        self.assertEqual(set(fractions), set(expected))
        for cell, value in expected.items():
            self.assertAlmostEqual(fractions[cell], value, places=6)

    def test_hole_and_total_area(self):
        outer = [(1.3, 1.1), (20.7, 1.1), (20.7, 17.9), (1.3, 17.9)]
        hole = [(5.5, 5.5), (9.1, 5.5), (9.1, 9.9), (5.5, 9.9)]
        fractions, zone = self.fractions([outer, hole])
        self.assertAlmostEqual(sum(fractions.values()) * 4.0, zone.area(), places=6)
        self.assertNotIn((3, 3), fractions)                     # the cell (6..8, 6..8) is inside the hole
        self.assertAlmostEqual(fractions[(2, 2)], 0.9375, places=6)   # (4..6, 4..6) minus 0.5 x 0.5 of the hole

    def test_thin_slit_through_a_cell(self):
        # a square with a 0.2 m wide slit from the top down to y = 7: it crosses row j = 5 (y 10..12)
        # in cells i = 4 and 5 without a vertex inside them
        ring = [(6, 6), (14, 6), (14, 14), (10.1, 14), (10.1, 7.0), (9.9, 7.0), (9.9, 14), (6, 14)]
        fractions, zone = self.fractions([ring])
        self.assertAlmostEqual(sum(fractions.values()) * 4.0, zone.area(), places=6)
        self.assertAlmostEqual(fractions[(5, 4)], 1.0 - 0.1 / 2.0, places=6)     # x 8..10, slit 9.9..10
        self.assertAlmostEqual(fractions[(5, 5)], 1.0 - 0.1 / 2.0, places=6)     # x 10..12, slit 10..10.1

    def test_random_polygons_conserve_area(self):
        rng = random.Random(7)
        for _ in range(20):
            # star-shaped around (cx, cy) with angle gaps below pi: always a simple polygon
            cx, cy = rng.uniform(10, 30), rng.uniform(8, 22)
            n = rng.randint(4, 12)
            angles = [2 * math.pi * (k + rng.uniform(0.0, 0.8)) / n for k in range(n)]
            radii = [rng.uniform(1, 8) for _ in angles]
            ring = [(cx + r * math.cos(a), cy + 0.75 * r * math.sin(a)) for a, r in zip(angles, radii)]
            fractions, zone = self.fractions([ring])
            self.assertAlmostEqual(sum(fractions.values()) * 4.0, zone.area(), places=5)
            self.assertTrue(all(0.0 < f <= 1.0 + 1e-9 for f in fractions.values()))


class MaskTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.readers = import_plugin_module('core.readers')
        cls.zones = import_plugin_module('core.zones')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_zones_')
        cls.nc_path = fx.write_netcdf(os.path.join(cls.tmp, 'NetCDF', 'sim_001.nc'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.nc = self.readers.NetcdfFile(self.nc_path)
        self.addCleanup(self.nc.close)
        self.static = self.nc.static_fields()

    def whole_area(self):
        g = self.nc.grid
        return zone_from_model(self.zones, g, [[(0, 0), (g.nx * fx.DX, 0), (g.nx * fx.DX, g.ny * fx.DX),
                                                (0, g.ny * fx.DX)]])

    def test_pedestrian_rule(self):
        levels = self.zones.pedestrian_levels(fx.dem_offset(), fx.DZ)
        self.assertEqual(levels[0, 0], 3)                       # centres 0.2 .. 1.8 m: 1.4 m is closest to 1.5
        tj, ti = fx.TERRAIN_COLUMN
        self.assertEqual(levels[tj, ti], 4)                     # ground at 0.8 m: 1.8 m is closest to 2.3 m
        self.assertIsNone(self.static.reported_biomet_k)         # the fixture has no ZNodeBiomet
        self.assertIsNone(self.static.biomet_level_mismatch())

    def test_pedestrian_mask_leaves_buildings_out(self):
        mask = self.zones.build_mask(self.nc.grid, self.whole_area(), self.static)
        cells = set(zip(mask.j.tolist(), mask.i.tolist()))
        self.assertNotIn(fx.BUILDING_COLUMN, cells)
        self.assertEqual(len(cells), fx.NX * fx.NY - 1)
        self.assertTrue(np.allclose(mask.weight, 4.0))

    def test_height_range_lists_air_above_the_roof(self):
        mask = self.zones.build_mask(self.nc.grid, self.whole_area(), self.static,
                                     mode=self.zones.MODE_RANGE, z_min=0.0, z_max=3.0)
        bj, bi = fx.BUILDING_COLUMN
        on_roof = mask.k[(mask.j == bj) & (mask.i == bi)].tolist()
        self.assertEqual(on_roof, [4, 5])                       # building in k = 0..3 (0 - 1.6 m)
        k5 = (mask.j == bj) & (mask.i == bi) & (mask.k == 5)
        self.assertAlmostEqual(float(mask.vertical_fraction[k5][0]), 0.5)   # 2.0 - 4.0 m cell, range to 3 m
        # volumes: per column the 3 m of the range (minus the building), times the cell area
        free = fx.NX * fx.NY - 1
        self.assertAlmostEqual(float(mask.weight.sum()), free * 4.0 * 3.0 + 4.0 * (3.0 - 1.6), places=6)

    def test_terrain_column_follows_the_ground(self):
        mask = self.zones.build_mask(self.nc.grid, self.whole_area(), self.static,
                                     mode=self.zones.MODE_RANGE, z_min=0.0, z_max=0.4)
        tj, ti = fx.TERRAIN_COLUMN
        self.assertEqual(mask.k[(mask.j == tj) & (mask.i == ti)].tolist(), [2])

    def test_height_range_needs_3d_results(self):
        """2D-only results have no levels: a height range (a volume) is refused, not made a 2D mask."""
        flat = self.zones.StaticFields(np.zeros((fx.NY, fx.NX), dtype=int), [1.0])
        with self.assertRaises(ValueError):
            self.zones.build_mask(self.nc.grid, self.whole_area(), flat, mode=self.zones.MODE_RANGE,
                                  z_min=0.0, z_max=3.0)
        self.assertEqual(len(self.zones.build_mask(self.nc.grid, self.whole_area(), flat)), fx.NX * fx.NY)

    def test_first_record_never_written(self):
        """Static fields come from the first written time step, not from a record left at the fill values."""
        path = fx.write_netcdf(os.path.join(self.tmp, 'unwritten', 'sim_001.nc'), first_unwritten=True)
        nc = self.readers.NetcdfFile(path)
        self.addCleanup(nc.close)
        self.assertEqual((nc.times[0], nc.first_index), (None, 1))
        static = nc.static_fields()
        np.testing.assert_array_equal(static.objects, self.static.objects)
        np.testing.assert_array_equal(static.dem, self.static.dem)
        mask = self.zones.build_mask(nc.grid, self.whole_area(), static)
        self.assertNotIn(fx.BUILDING_COLUMN, set(zip(mask.j.tolist(), mask.i.tolist())))


class StatsTest(unittest.TestCase):

    def setUp(self):
        self.stats = import_plugin_module('core.stats')

    def test_weighted_statistics(self):
        values = np.array([10.0, 20.0, 30.0, np.nan])
        weights = np.array([1.0, 1.0, 2.0, 5.0])
        result = self.stats.weighted_stats(values, weights, thresholds=(15.0,), class_limits=(15.0, 25.0))
        self.assertEqual((result['n_cells'], result['n_valid']), (4, 3))
        self.assertAlmostEqual(result['mean'], 22.5)
        self.assertAlmostEqual(result['std'], math.sqrt((12.5 ** 2 + 2.5 ** 2 + 2 * 7.5 ** 2) / 4))
        self.assertEqual((result['min'], result['max']), (10.0, 30.0))
        self.assertEqual(result['p25'], 10.0)       # cumulative shares 0.25, 0.5, 1.0
        self.assertEqual(result['p50'], 20.0)
        self.assertEqual(result['p95'], 30.0)
        self.assertAlmostEqual(result['share_above_15'], 0.75)
        self.assertAlmostEqual(result['share_below_15'], 0.25)
        self.assertAlmostEqual(result['share_15_to_25'], 0.25)
        self.assertAlmostEqual(result['share_above_25'], 0.5)

    def test_no_valid_cells(self):
        result = self.stats.weighted_stats(np.array([np.nan]), np.array([1.0]))
        self.assertEqual(result['n_valid'], 0)
        self.assertTrue(math.isnan(result['mean']))

    def test_class_limits(self):
        self.assertEqual(self.stats.class_limits_for('UTCIBiomet'), self.stats.UTCI_CLASS_LIMITS)
        self.assertEqual(self.stats.class_limits_for('PET', 'PET (Default Person)'), self.stats.PET_CLASS_LIMITS)
        self.assertIsNone(self.stats.class_limits_for('T', 'Air Temperature'))


class TimeSeriesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.readers = import_plugin_module('core.readers')
        cls.zones = import_plugin_module('core.zones')
        cls.stats = import_plugin_module('core.stats')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_series_')
        fx.write_output_folder(os.path.join(cls.tmp, 'out'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_area_means_per_time_step(self):
        source = self.readers.find_sources(os.path.join(self.tmp, 'out'))[0]
        self.addCleanup(source.close)
        first = source.first_file()
        grid, static = first.grid, first.static_fields()
        # zone: cells i = 0..1 (fully) and the left half of i = 2, row j = 0
        zone = zone_from_model(self.zones, grid, [[(0, 0), (5, 0), (5, 2), (0, 2)]])
        mask = self.zones.build_mask(grid, zone, static)
        variables = [self.stats.VariableRequest(key, v.long_name, v.display_units, v.kind)
                     for key, v in first.variables.items() if key in ('T', 'UTCIBiomet')]
        rows = self.stats.time_series(source, [mask], variables, self.zones.MODE_PEDESTRIAN, 'pedestrian')
        by = {(r['variable'], r['datetime']): r for r in rows}
        # T at the pedestrian level k = 3: 100*3 + 10*0 + i, weights 1, 1, 0.5 (times 4 m²)
        t = by[('T', '2024-07-06 05:00')]
        self.assertAlmostEqual(t['mean'], 1000 + 300 + (0 * 1 + 1 * 1 + 2 * 0.5) / 2.5, places=4)
        self.assertAlmostEqual(t['area_m2'], 10.0)
        u = by[('UTCIBiomet', '2024-07-06 04:00')]
        self.assertAlmostEqual(u['mean'], 30.0 + (0.0 * 1 + 0.1 * 1 + 0.2 * 0.5) / 2.5, places=4)
        self.assertIn('share_above_46', u)
        diurnal = self.stats.diurnal_cycle(rows)
        self.assertEqual(len(diurnal), 4)           # two variables x two hours


if __name__ == '__main__':
    unittest.main()
