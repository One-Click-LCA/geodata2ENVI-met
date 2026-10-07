# coding=utf-8
"""INX export of synthetic layers: positions of buildings, receptors and 3D plants."""

import os
import shutil
import tempfile
import unittest

from .inx_helpers import (make_layer, new_worker, read_inx, rectangle_wkt, set_buildings,
                          set_plants3d, set_receptors)
from .plugin_env import import_plugin_module, start_qgis

CRS = 'EPSG:32632'
X0, Y0 = 500000.0, 5400000.0
DX = 2.0
II, JJ = 20, 16


def cell_centre(i, j):
    """Centre of the 1-based ENVI-met cell (i, j); j counts from the south."""
    return X0 + (i - 0.5) * DX, Y0 + (j - 0.5) * DX


class InxExportTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        consts = import_plugin_module('Const_defines')
        cls.INT, cls.STR = consts.FIELD_TYPE_INT, consts.FIELD_TYPE_STRING
        cls.tmp = tempfile.mkdtemp(prefix='g2e_inx_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def export(self, name, configure):
        sub_area = make_layer('Polygon', CRS, [(rectangle_wkt(X0, Y0, X0 + II * DX, Y0 + JJ * DX), [])])
        path = os.path.join(self.tmp, name + '.INX')
        worker = new_worker(sub_area, dx=DX, dy=DX, filename=path)
        configure(worker)
        worker.saveINX()
        return read_inx(path)

    def test_positions_relative_to_buildings(self):
        # building on the 1-based cells i = 5..7, j = 3..5
        building = make_layer('Polygon', CRS,
                              [(rectangle_wkt(X0 + 4 * DX, Y0 + 2 * DX, X0 + 7 * DX, Y0 + 5 * DX), [10])],
                              fields=[('h', self.INT)])
        receptors = make_layer('Point', CRS, [
            ('POINT(%f %f)' % cell_centre(11, 8), ['R1']),
            ('POINT(%f %f)' % cell_centre(II, JJ), ['RNE']),   # north-east corner cell
            ('POINT(%f %f)' % cell_centre(1, 1), ['RSW']),     # south-west corner cell
        ], fields=[('rid', self.STR)])
        trees = make_layer('Point', CRS, [('POINT(%f %f)' % cell_centre(16, 13), ['0000C2'])],
                           fields=[('pid', self.STR)])

        def configure(worker):
            set_buildings(worker, building, 'h')
            set_receptors(worker, receptors, 'rid')
            set_plants3d(worker, trees, 'pid')

        inx = self.export('positions', configure)
        self.assertEqual((inx['II'], inx['JJ']), (II, JJ))

        # buildings: matrix line 0 is the northernmost row (j = JJ)
        ztop = inx['zTop']
        built = {(col + 1, JJ - row) for row, line in enumerate(ztop) for col, v in enumerate(line) if int(v) > 0}
        self.assertEqual(built, {(i, j) for i in range(5, 8) for j in range(3, 6)})

        # receptors are 0-based in the INX (SPACES writes i-1/j-1, envicore adds 1)
        self.assertEqual(inx['receptors']['R1'], (11 - 1, 8 - 1))
        self.assertEqual(inx['receptors']['RNE'], (II - 1, JJ - 1))
        self.assertEqual(inx['receptors']['RSW'], (0, 0))

        # 3D plants are 1-based
        self.assertEqual(inx['plants3d'], [(16, 13, '0000C2')])

    def test_custom_ids_without_layers(self):
        """'Custom ID' ticked but no layer chosen must not crash the export (M2)."""

        def configure(worker):
            worker.plant1dID_UseCustom = True
            worker.plant1dID_custom = '0000XX'
            worker.srcPID_UseCustom = True
            worker.srcPID_custom = '0000SP'
            worker.srcLID_UseCustom = True
            worker.srcLID_custom = '0000SL'
            worker.srcAID_UseCustom = True
            worker.srcAID_custom = '0000SA'

        inx = self.export('custom_ids', configure)
        self.assertEqual((inx['II'], inx['JJ']), (II, JJ))
        self.assertNotIn('0000XX', inx['text'])
        self.assertNotIn('0000SP', inx['text'])


if __name__ == '__main__':
    unittest.main()
