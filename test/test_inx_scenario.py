# coding=utf-8
"""INX export of a full scenario against a reference file, and the export's robustness.

test/data/inx_scenario_golden.INX was written before the export was reworked for speed
and robustness; the rework must not change the result.
"""

import os
import re
import shutil
import tempfile
import unittest

from . import inx_scenario
from .inx_helpers import read_inx
from .plugin_env import DATA_DIR, start_qgis

GOLDEN = os.path.join(DATA_DIR, 'inx_scenario_golden.INX')

# Matrices compared with a tolerance. The terrain heights are whole metres, cut off from
# the DEM interpolated by GDAL; GDAL versions differ by millimetres, which moves a cell
# lying just above a whole metre (5.002 m here) by one metre.
TOLERANT = {'terrainheight': 1}


def matrices(text):
    """Every matrix of an INX file, by tag (also when its closing tag is missing)."""
    found = {}
    for match in re.finditer(r'<([A-Za-z0-9_]+) type="matrix-data"[^>]*>([^<]*)<', text):
        found[match.group(1)] = [line.strip().rstrip(',') for line in match.group(2).strip().splitlines()]
    return found


def comparable(text):
    """The INX without the free-text remark."""
    return re.sub(r'<remark>.*?</remark>', '', text)


class InxScenarioTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        cls.tmp = tempfile.mkdtemp(prefix='g2e_scenario_')
        cls.path = inx_scenario.export(cls.tmp, 'scenario')
        with open(cls.path, encoding='utf-8') as f:
            cls.text = f.read()
        with open(GOLDEN, encoding='utf-8') as f:
            cls.golden = f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_matrices_match_the_reference(self):
        new, old = matrices(self.text), matrices(self.golden)
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
        for tag in ('modelRotation', 'realworldLowerLeft_X', 'realworldLowerLeft_Y', 'UTMZone', 'grids-I', 'grids-J'):
            with self.subTest(tag=tag):
                pattern = r'<%s>\s*(.*?)\s*</%s>' % (tag, tag)
                self.assertAlmostEqual(float(re.search(pattern, self.text).group(1)),
                                       float(re.search(pattern, self.golden).group(1)), places=6)

    def test_a_far_away_feature_does_not_move_the_layer(self):
        """H7: each layer was projected to the UTM zone of its own extent's corner."""
        path = inx_scenario.export(self.tmp, 'far', far_feature=True)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertEqual(matrices(text)['zTop'], matrices(self.golden)['zTop'])


if __name__ == '__main__':
    unittest.main()
