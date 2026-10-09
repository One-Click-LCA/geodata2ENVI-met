# coding=utf-8
"""The area-analysis Processing algorithms, run through processing.run on synthetic results."""

import csv
import math
import os
import shutil
import tempfile
import unittest

from . import fixtures as fx
from .inx_helpers import make_layer
from .plugin_env import import_plugin_module, make_plugin, start_qgis


def model_polygon(x0, y0, x1, y1):
    """WKT of a rectangle given in model coordinates of the fixtures' grid."""
    r = math.radians(fx.ROTATION)

    def utm(x, y):
        return fx.X0 + x * math.cos(r) + y * math.sin(r), fx.Y0 - x * math.sin(r) + y * math.cos(r)
    corners = [utm(x0, y0), utm(x1, y0), utm(x1, y1), utm(x0, y1), utm(x0, y0)]
    return 'POLYGON((' + ', '.join(f'{x} {y}' for x, y in corners) + '))'


def read_csv(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


class AreaAlgorithmsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        from qgis.core import QgsApplication
        registry = QgsApplication.processingRegistry()
        if registry.providerById('envimet') is None:
            provider = import_plugin_module('processing_provider.provider').EnvimetProvider()
            registry.addProvider(provider)
            cls.provider = provider
        cls.tmp = tempfile.mkdtemp(prefix='g2e_areas_')
        cls.root = fx.write_output_folder(os.path.join(cls.tmp, 'sim_output'))
        cls.shifted = os.path.join(cls.tmp, 'shifted_output')
        fx.write_netcdf(os.path.join(cls.shifted, 'NetCDF', 'sim_001.nc'), x0=fx.X0 + 1.0)
        cls.levels = os.path.join(cls.tmp, 'levels_output')        # same grid, other vertical levels
        fx.write_netcdf(os.path.join(cls.levels, 'NetCDF', 'sim_001.nc'), dz=[0.5] * 5 + [2.0, 2.0, 2.0])
        string = import_plugin_module('Const_defines').FIELD_TYPE_STRING
        cls.areas = make_layer('Polygon', f'EPSG:326{fx.ZONE}', [
            (model_polygon(0, 0, 5, 2), ['1', 'Courtyard']),       # cells i 0..1 and half of 2, row 0
            (model_polygon(2, 0, 4, 2), ['1', 'Courtyard']),       # overlaps the first: dissolved, not double
            (model_polygon(6, 6, 10, 10), ['2', 'Square']),        # 2 x 2 cells around the building (3, 4)
            (model_polygon(0, 6, 2, 8), [None, 'no id']),          # no ID: left out
        ], fields=[('zone', string), ('label', string)])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_algorithm(self, name, **parameters):
        import processing
        defaults = {'AREAS': self.areas, 'ID_FIELD': 'zone', 'NAME_FIELD': 'label', 'RESULTS': self.root,
                    'OUTPUT_FOLDER': tempfile.mkdtemp(dir=self.tmp), 'PREFIX': 'test'}
        defaults.update(parameters)
        return processing.run(f'envimet:{name}', defaults)

    def test_masks_and_preview(self):
        result = self.run_algorithm('areamasks', CELLS='TEMPORARY_OUTPUT')
        zones = {row['zone_id']: row for row in read_csv(result['ZONES_CSV'])}
        self.assertEqual(set(zones), {'1', '2'})
        self.assertEqual(zones['1']['zone_name'], 'Courtyard')
        self.assertAlmostEqual(float(zones['1']['polygon_area_m2']), 10.0, places=3)    # union, not 10 + 4
        self.assertAlmostEqual(float(zones['1']['air_area_m2']), 10.0, places=3)
        self.assertAlmostEqual(float(zones['2']['polygon_area_m2']), 16.0, places=3)
        self.assertAlmostEqual(float(zones['2']['air_area_m2']), 12.0, places=3)        # minus the building
        cells = read_csv(result['CELLS_CSV'])
        courtyard = [c for c in cells if c['zone_id'] == '1']
        self.assertEqual(sorted((int(c['i']), float(c['fraction'])) for c in courtyard),
                         [(0, 1.0), (1, 1.0), (2, 0.5)])
        self.assertTrue(all(c['k'] == '3' and c['k_em'] == '4' for c in courtyard))
        self.assertTrue(all(c['lat'] and c['lon'] for c in courtyard))
        self.assertEqual(result['CELLS'].featureCount(), len(cells))

    def test_statistics(self):
        result = self.run_algorithm('areastatistics', VARIABLES='T, UTCIBiomet', THRESHOLDS='30')
        rows = read_csv(result['STATISTICS'])
        t = [r for r in rows if r['variable'] == 'T' and r['zone_id'] == '1' and r['datetime'] == '2024-07-06 05:00']
        self.assertEqual(len(t), 1)
        self.assertAlmostEqual(float(t[0]['mean']), 1300.8, places=3)
        self.assertEqual(t[0]['level'], 'pedestrian level (terrain + 1.5 m)')
        utci = [r for r in rows if r['variable'] == 'UTCIBiomet' and r['zone_id'] == '2']
        self.assertTrue(all(r['n_valid'] == '3' for r in utci))            # the building cell is not listed
        self.assertIn('share_above_30', rows[0])
        self.assertIn('share_26_to_32', utci[0])
        self.assertEqual(len(read_csv(result['DIURNAL'])), 2 * 2 * 2)       # 2 areas x 2 variables x 2 hours
        self.assertTrue(os.path.exists(result['DAILY']))

    def test_default_variable_is_utci(self):
        result = self.run_algorithm('areastatistics')
        self.assertEqual({r['variable'] for r in read_csv(result['STATISTICS'])}, {'UTCIBiomet'})

    def test_comparison_on_the_same_grid(self):
        result = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS_B=self.root)
        rows = read_csv(result['STATISTICS'])
        self.assertEqual({r['scenario'] for r in rows}, {'A', 'B', 'A-B'})
        self.assertTrue(all(float(r['mean']) == 0.0 for r in rows if r['scenario'] == 'A-B'))

    def test_comparison_on_different_grids(self):
        result = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS_B=self.shifted)
        differences = [r for r in read_csv(result['STATISTICS']) if r['scenario'] == 'A-B']
        self.assertTrue(differences)
        self.assertTrue(all(r['source'] == 'A-B (difference of means)' for r in differences))

    def test_comparison_with_other_vertical_levels(self):
        """The same k is another height when the levels differ: no cell-by-cell pairing then."""
        result = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS_B=self.levels)
        differences = [r for r in read_csv(result['STATISTICS']) if r['scenario'] == 'A-B']
        self.assertTrue(differences)
        self.assertTrue(all(r['source'] == 'A-B (difference of means)' for r in differences))

    def test_comparison_across_formats(self):
        """NetCDF "T" and EDX "Air Temperature" are the same quantity: found by its long name."""
        for extra in ({}, {'VARIABLES_B': 'Air Temperature'}):
            with self.subTest(**extra):
                result = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS_B=self.root,
                                            SOURCE_B='atmosphere (EDX)', **extra)
                rows = read_csv(result['STATISTICS'])
                self.assertEqual({r['variable'] for r in rows}, {'T'})
                differences = [r for r in rows if r['scenario'] == 'A-B']
                self.assertEqual(len(differences), 2 * 2)       # 2 areas x 2 time steps, cell by cell
                self.assertTrue(all(r['source'] == 'A-B' and float(r['mean']) == 0.0 for r in differences))

    def test_variables_b_must_match_a(self):
        from qgis.core import QgsProcessingException
        with self.assertRaises(QgsProcessingException):
            self.run_algorithm('areastatistics', VARIABLES='T, UTCIBiomet', RESULTS_B=self.root,
                               SOURCE_B='atmosphere (EDX)', VARIABLES_B='Air Temperature')

    def test_a_result_file_instead_of_a_folder(self):
        result = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS=None,
                                    RESULTS_FILE=os.path.join(self.root, 'NetCDF', 'sim_001.nc'))
        self.assertEqual({r['scenario'] for r in read_csv(result['STATISTICS'])}, {'A'})

    def test_3d_results_without_objects(self):
        """Without an Objects field every cell counts as air; building cells drop out by their missing values."""
        path = fx.write_netcdf(os.path.join(self.tmp, 'no_objects', 'Report.nc'), with_objects=False)

        def means(rows):
            return {(r['zone_id'], r['datetime']): (r['n_valid'], round(float(r['mean']), 6)) for r in rows
                    if r['scenario'] == 'A'}
        for vertical in ({}, {'VERTICAL': 1, 'Z_MIN': 0.0, 'Z_MAX': 3.0}):
            with self.subTest(**vertical):
                usual = self.run_algorithm('areastatistics', VARIABLES='T', **vertical)
                bare = self.run_algorithm('areastatistics', VARIABLES='T', RESULTS=None, RESULTS_FILE=path,
                                          **vertical)
                self.assertEqual(means(read_csv(bare['STATISTICS'])), means(read_csv(usual['STATISTICS'])))
                self.assertTrue(all(c['k'] != '' for c in read_csv(bare['CELLS_CSV'])))

    def test_text_ids_stay_distinct(self):
        """"01" and "1" are two areas; "1" becomes a number, "01" stays text."""
        string = import_plugin_module('Const_defines').FIELD_TYPE_STRING
        areas = make_layer('Polygon', f'EPSG:326{fx.ZONE}', [
            (model_polygon(0, 0, 4, 2), ['01', 'first']),
            (model_polygon(0, 4, 4, 6), ['1', 'second']),
        ], fields=[('zone', string), ('label', string)])
        result = self.run_algorithm('areamasks', AREAS=areas)
        zones = {row['zone_id']: row['zone_name'] for row in read_csv(result['ZONES_CSV'])}
        self.assertEqual(zones, {'01': 'first', '1': 'second'})

    def test_height_range(self):
        result = self.run_algorithm('areastatistics', VARIABLES='T', VERTICAL=1, Z_MIN=0.0, Z_MAX=3.0)
        rows = read_csv(result['STATISTICS'])
        square = [r for r in rows if r['zone_id'] == '2']
        self.assertTrue(all('volume_m3' in r and float(r['volume_m3']) > 0 for r in square))
        cells = read_csv(result['CELLS_CSV'])
        above_roof = [c for c in cells if c['zone_id'] == '2' and (c['j'], c['i']) == ('3', '4')]
        self.assertEqual(sorted(int(c['k']) for c in above_roof), [4, 5])

    def test_dialog_hands_over_the_series(self):
        plugin = make_plugin()
        plugin.load_series_folder(self.root, 'A')
        parameters = plugin.area_statistics_parameters()
        self.assertEqual(parameters['RESULTS'], self.root)
        self.assertEqual(parameters['SOURCE'], 'NetCDF')
        self.assertNotIn('RESULTS_B', parameters)


if __name__ == '__main__':
    unittest.main()
