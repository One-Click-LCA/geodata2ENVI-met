# coding=utf-8
"""INX export of a full scenario against a reference file, and the export's robustness.

test/data/inx_scenario_golden.INX was written (in the older XML format) before the export was
reworked for speed and robustness; the rework and the JSON format must not change the result.
Comparing the two also tests that core.inx reads both formats alike.
"""

import json
import os
import shutil
import tempfile
import unittest

from . import inx_scenario
from .inx_helpers import grid_text, read_inx
from .plugin_env import DATA_DIR, start_qgis

GOLDEN = os.path.join(DATA_DIR, 'inx_scenario_golden.INX')

# Matrices compared with a tolerance. The terrain heights are whole metres, cut off from
# the DEM interpolated by GDAL; GDAL versions differ by millimetres, which moves a cell
# lying just above a whole metre (5.002 m here) by one metre.
TOLERANT = {'terrain': 1}


def matrices(path):
    """Every grid of an INX file (either format) as rows of comma-separated text, north first."""
    return {name: [','.join(row) for row in grid_text(values)]
            for name, values in read_inx(path)['model']['grids'].items()}


class InxScenarioTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        cls.tmp = tempfile.mkdtemp(prefix='g2e_scenario_')
        cls.path = inx_scenario.export(cls.tmp, 'scenario')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_matrices_match_the_reference(self):
        new, old = matrices(self.path), matrices(GOLDEN)
        self.assertEqual(sorted(new), sorted(old))
        for tag in old:
            with self.subTest(matrix=tag):
                if tag in TOLERANT:
                    self.assertMatrixClose(new[tag], old[tag], TOLERANT[tag])
                else:
                    self.assertEqual(new[tag], old[tag])

    def assertMatrixClose(self, new, old, tolerance):
        self.assertEqual(len(new), len(old))
        for row, (a, b) in enumerate(zip(new, old)):
            a, b = [int(v) for v in a.split(',')], [int(v) for v in b.split(',')]
            self.assertEqual(len(a), len(b))
            worst = max(abs(x - y) for x, y in zip(a, b))
            self.assertLessEqual(worst, tolerance, f'row {row}: {a} != {b}')

    def test_lists_and_location_match_the_reference(self):
        new, old = read_inx(self.path), read_inx(GOLDEN)
        self.assertEqual(new['receptors'], old['receptors'])
        self.assertEqual(new['plants3d'], old['plants3d'])
        for section, key in (('location', 'modelRot'), ('location', 'x'), ('location', 'y'), ('geometry', 'i'),
                             ('geometry', 'j')):
            with self.subTest(key=key):
                self.assertAlmostEqual(float(new['model'][section][key]), float(old['model'][section][key]), places=6)
        self.assertEqual(new['model']['location']['epsgProj'], old['model']['location']['epsgProj'])

    def test_written_as_envi_met_6_json(self):
        with open(self.path, 'rb') as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf{'))          # UTF-8 with BOM, as SPACES writes it
        data = json.loads(raw.decode('utf-8-sig'))['envimetDatafile']
        self.assertEqual((data['header']['fileType'], data['header']['version']), ('modelAreaJSON', 1))
        geometry = data['domainConfig']['modelGeometry']
        self.assertEqual(geometry['modelType'], '2.5D')
        top = data['spatialData2D']['buildings']['top']
        # [i][j], j from south: as many columns as cells along x, each as long as the model is along y
        self.assertEqual((len(top), len(top[0])), (geometry['i'], geometry['j']))
        self.assertTrue(all(isinstance(v, int) for row in top for v in row))
        self.assertTrue(all(isinstance(v, bool) for row in data['spatialData2D']['buildings']['fixedHeight']
                            for v in row))
        self.assertTrue(all(len(v) == 6 for row in data['spatialData2D']['soilProfiles']['data'] for v in row))
        north_up = read_inx(self.path)['model']['grids']['top']
        self.assertEqual(top[0][0], north_up[-1, 0])              # south-west cell
        self.assertEqual(top[-1][-1], north_up[0, -1])            # north-east cell

    def test_a_far_away_feature_does_not_move_the_layer(self):
        """H7: each layer was projected to the UTM zone of its own extent's corner."""
        path = inx_scenario.export(self.tmp, 'far', far_feature=True)
        self.assertEqual(matrices(path)['top'], matrices(GOLDEN)['top'])


if __name__ == '__main__':
    unittest.main()
