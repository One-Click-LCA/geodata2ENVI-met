# coding=utf-8
"""The model area of an exported INX lands exactly on the digitised sub-area, in both hemispheres.

ENVI-met copies the INX's realworldLowerLeft_X/Y and modelRotation unchanged into
its outputs (GeorefX/Y, ModelRotation), so results are placed with the same
georeferencing. Results use core.readers.Grid; this checks that Grid, applied to
the values the plugin writes into the INX, reproduces the digitised rectangle.
"""

import math
import os
import re
import shutil
import tempfile
import unittest

from .inx_helpers import make_layer, new_worker
from .plugin_env import import_plugin_module, start_qgis

CASES = [
    # (EPSG, lower-left corner, latitude sign)
    (32633, (387500.0, 5820000.0), 1),      # Berlin, northern hemisphere
    (32756, (334000.0, 6250000.0), -1),     # Sydney, southern hemisphere
]
ROTATIONS = (0.0, 30.0, -25.0, 120.0)
WIDTH, HEIGHT = 40.0, 24.0     # multiples of the cell size
DX = 2.0


def rectangle(x0, y0, rotation):
    """Corners LL, UL, UR, LR of the model area turned clockwise by ``rotation`` about LL."""
    r = math.radians(rotation)
    ex = (math.cos(r), -math.sin(r))        # model x axis in UTM
    ey = (math.sin(r), math.cos(r))         # model y axis in UTM
    ll = (x0, y0)
    lr = (x0 + WIDTH * ex[0], y0 + WIDTH * ex[1])
    ul = (x0 + HEIGHT * ey[0], y0 + HEIGHT * ey[1])
    ur = (lr[0] + HEIGHT * ey[0], lr[1] + HEIGHT * ey[1])
    return ll, ul, ur, lr


class GeoreferenceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        cls.readers = import_plugin_module('core.readers')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_georef_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def export(self, epsg, corners, name):
        ll, ul, ur, lr = corners
        wkt = 'POLYGON((' + ', '.join(f'{x} {y}' for x, y in (ll, ul, ur, lr, ll)) + '))'
        sub_area = make_layer('Polygon', f'EPSG:{epsg}', [(wkt, [])])
        path = os.path.join(self.tmp, name + '.INX')
        worker = new_worker(sub_area, dx=DX, dy=DX, filename=path)
        worker.saveINX()
        with open(path, encoding='utf-8') as f:
            text = f.read()

        def value(tag):
            return re.search(r'<%s>\s*(.*?)\s*</%s>' % (tag, tag), text).group(1)
        return {tag: value(tag) for tag in ('grids-I', 'grids-J', 'modelRotation', 'realworldLowerLeft_X',
                                            'realworldLowerLeft_Y', 'location_Latitude', 'UTMZone',
                                            'projectionSystem')}

    def test_exported_area_matches_the_digitised_rectangle(self):
        for epsg, (x0, y0), sign in CASES:
            for rotation in ROTATIONS:
                with self.subTest(epsg=epsg, rotation=rotation):
                    corners = rectangle(x0, y0, rotation)
                    inx = self.export(epsg, corners, f'{epsg}_{rotation}')
                    self.assertEqual(inx['projectionSystem'], f'EPSG:{epsg}')
                    self.assertEqual(math.copysign(1, float(inx['location_Latitude'])), sign)
                    nx, ny = int(inx['grids-I']), int(inx['grids-J'])
                    self.assertEqual((nx, ny), (round(WIDTH / DX), round(HEIGHT / DX)))
                    grid = self.readers.Grid(
                        dx=[DX] * nx, dy=[DX] * ny, x0=float(inx['realworldLowerLeft_X']),
                        y0=float(inx['realworldLowerLeft_Y']), rotation=float(inx['modelRotation']),
                        utm_zone=int(inx['UTMZone']), latitude=float(inx['location_Latitude']))
                    self.assertEqual(grid.epsg, epsg)
                    # corners of the grid's outer cells, from the cell midpoints
                    east, north = grid.cell_centres()
                    r = math.radians(grid.rotation)
                    half_x = (DX / 2 * math.cos(r), -DX / 2 * math.sin(r))
                    half_y = (DX / 2 * math.sin(r), DX / 2 * math.cos(r))
                    grid_corners = [
                        (east[0, 0] - half_x[0] - half_y[0], north[0, 0] - half_x[1] - half_y[1]),      # LL
                        (east[-1, 0] - half_x[0] + half_y[0], north[-1, 0] - half_x[1] + half_y[1]),    # UL
                        (east[-1, -1] + half_x[0] + half_y[0], north[-1, -1] + half_x[1] + half_y[1]),  # UR
                        (east[0, -1] + half_x[0] - half_y[0], north[0, -1] + half_x[1] - half_y[1]),    # LR
                    ]
                    for (gx, gy), (cx, cy) in zip(grid_corners, corners):
                        self.assertAlmostEqual(gx, cx, delta=0.01)
                        self.assertAlmostEqual(gy, cy, delta=0.01)


if __name__ == '__main__':
    unittest.main()
