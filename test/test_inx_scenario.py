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
                self.assertEqual(new[tag], old[tag])

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
