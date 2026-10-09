# coding=utf-8
"""Load results tab: GeoTIFF placement, sources, variables and the layer task."""

import math
import os
import shutil
import tempfile
import unittest

import numpy as np

from . import fixtures as fx
from .inx_helpers import make_layer
from .plugin_env import import_plugin_module, make_plugin, start_qgis


def sample(path, east, north):
    """Value of a north-up GeoTIFF at a point."""
    from osgeo import gdal
    dataset = gdal.Open(path)
    x0, dx, _, y0, _, dy = dataset.GetGeoTransform()
    col = int(math.floor((east - x0) / dx))
    row = int(math.floor((north - y0) / dy))
    value = dataset.GetRasterBand(1).ReadAsArray(col, row, 1, 1)[0, 0]
    nodata = dataset.GetRasterBand(1).GetNoDataValue()
    return np.nan if value == nodata else float(value)


class GeotiffPlacementTest(unittest.TestCase):

    def setUp(self):
        start_qgis()
        self.geotiff = import_plugin_module('core.geotiff')
        self.readers = import_plugin_module('core.readers')
        self.tmp = tempfile.mkdtemp(prefix='g2e_tif_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cell_values_land_on_their_midpoints(self):
        for rotation in (0.0, fx.ROTATION, -35.0):
            grid = self.readers.Grid(dx=[fx.DX] * fx.NX, dy=[fx.DX] * fx.NY, x0=fx.X0, y0=fx.Y0,
                                     rotation=rotation, utm_zone=fx.ZONE, latitude=fx.LATITUDE)
            values = np.arange(fx.NX * fx.NY, dtype=float).reshape(fx.NY, fx.NX)
            rotated = self.geotiff.write_rotated(os.path.join(self.tmp, f'r{rotation}.tif'), values, grid)
            north_up = self.geotiff.warp_north_up(rotated, os.path.join(self.tmp, f'n{rotation}.tif'), 0.25,
                                                  grid.epsg, resampling='nearest')
            east, north = grid.cell_centres()
            for j in range(fx.NY):
                for i in range(fx.NX):
                    with self.subTest(rotation=rotation, j=j, i=i):
                        self.assertEqual(sample(north_up, east[j, i], north[j, i]), values[j, i])


class ResultsTabTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plugin = make_plugin()
        cls.tmp = tempfile.mkdtemp(prefix='g2e_results_')
        cls.root = fx.write_output_folder(os.path.join(cls.tmp, 'sim_output'))
        # a second run whose model area sits 1 m further east: a different grid
        cls.shifted = os.path.join(cls.tmp, 'shifted_output')
        fx.write_netcdf(os.path.join(cls.shifted, 'NetCDF', 'sim_001.nc'), x0=fx.X0 + 1.0)

    @classmethod
    def tearDownClass(cls):
        from qgis.core import QgsProject
        QgsProject.instance().removeAllMapLayers()
        dataseries = import_plugin_module('Dataseries_handler').dataseries
        for series in ('A', 'B'):
            dataseries.set_folder('', series)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from qgis.core import QgsProject
        QgsProject.instance().removeAllMapLayers()
        self.plugin.iface.bar.messages.clear()
        self.plugin.dlg.cb_Output_SubArea.setLayer(None)
        self.plugin.select_cb_Output_SubArea()

    def load(self, folder_a, source_a='NetCDF', folder_b='', source_b=None):
        dlg = self.plugin.dlg
        self.plugin.load_series_folder(folder_a, 'A')
        dlg.cb_sourceA.setCurrentText(source_a)
        self.plugin.load_series_folder(folder_b, 'B')
        if source_b:
            dlg.cb_sourceB.setCurrentText(source_b)

    def choose_variable(self, text):
        box = self.plugin.dlg.cb_dataLayers
        texts = [box.itemText(n) for n in range(box.count())]
        self.assertIn(text, texts)
        box.setCurrentIndex(texts.index(text))

    def check(self, list_widget, rows):
        from qgis.PyQt.QtCore import Qt
        for row in rows:
            list_widget.item(row).setCheckState(Qt.CheckState.Checked)

    def run_task(self):
        requests = self.plugin.layer_requests()
        task = import_plugin_module('result_layers').ResultLayersTask(
            requests, cutline=self.plugin.sub_area_cutline(), on_finished=self.plugin.after_add_to_map)
        self.assertTrue(task.run())
        task.finished(True)
        self.assertEqual(task.errors, [])
        return task.layers

    def test_sources_and_variables(self):
        self.load(self.root)
        dlg = self.plugin.dlg
        self.assertEqual([dlg.cb_sourceA.itemText(n) for n in range(dlg.cb_sourceA.count())],
                         ['NetCDF', 'Report_Slice', 'atmosphere (EDX)'])
        texts = [dlg.cb_dataLayers.itemText(n) for n in range(dlg.cb_dataLayers.count())]
        self.assertIn('Air Temperature [T] (Only Series A)', texts)
        self.assertIn('Wall Temperature [WallTempX] (Only Series A)', texts)
        self.assertIn('Wall Temperature [WallTempY] (Only Series A)', texts)
        self.assertIn('PET (Default Person) [PET] (Only Series A)', texts)
        self.assertNotIn('UTM Easting of Cell Midpoint [utm_easting] (Only Series A)', texts)
        self.assertEqual(dlg.lw_SeriesA.count(), 2)
        self.assertEqual(dlg.lw_SeriesA.item(1).text(), '06.07.2024 05.00.00')

    def test_series_a_layer(self):
        self.load(self.root)
        self.choose_variable('Air Temperature [T] (Only Series A)')
        self.plugin.dlg.sb_height.setValue(1.0)
        self.check(self.plugin.dlg.lw_SeriesA, [1])
        layers = self.run_task()
        self.assertEqual([layer.name() for layer in layers], ['Air Temperature_06.07._05.00.00_0.8m-1.2m_SeriesA'])
        self.assertEqual(layers[0].crs().authid(), 'EPSG:32633')
        east, north = fx.cell_centres()
        path = layers[0].source()
        # bilinear 1 m pixels: their centres are up to 0.5 m from the cell midpoint (field: 5 K/m along j)
        self.assertAlmostEqual(sample(path, east[2, 2], north[2, 2]), fx.t_value(1, 2, 2, 2), delta=3.0)

    def test_cancelled_task_adds_no_layers(self):
        from qgis.core import QgsProject
        self.load(self.root)
        self.choose_variable('Air Temperature [T] (Only Series A)')
        self.check(self.plugin.dlg.lw_SeriesA, [0, 1])
        done = []
        task = import_plugin_module('result_layers').ResultLayersTask(
            self.plugin.layer_requests(), on_finished=lambda t: done.append(t))
        self.assertTrue(task.run())
        self.assertEqual(len(task.outputs), 2)
        task.finished(False)                    # what QGIS calls when the task was cancelled
        self.assertEqual((task.layers, done), ([], [task]))
        self.assertEqual(QgsProject.instance().count(), 0)

    def test_delta_on_the_same_grid_is_exact(self):
        # NetCDF (A) against the EDX files of the same run (B): matched by long name
        self.load(self.root, 'NetCDF', self.root, 'atmosphere (EDX)')
        self.choose_variable('Air Temperature [T] (Comparable)')
        self.check(self.plugin.dlg.lw_Delta, [1])
        layers = self.run_task()
        self.assertEqual([layer.name() for layer in layers], ['Air Temperature_06.07._05.00.00_0.0m-0.4m_Delta(A-B)'])
        east, north = fx.cell_centres()
        self.assertEqual(sample(layers[0].source(), east[2, 2], north[2, 2]), 0.0)

    def test_delta_on_different_grids(self):
        self.load(self.root, 'NetCDF', self.shifted, 'NetCDF')
        self.choose_variable('Air Temperature [T] (Comparable)')
        self.check(self.plugin.dlg.lw_Delta, [0])
        layers = self.run_task()
        self.assertEqual(len(layers), 1)
        east, north = fx.cell_centres()
        value = sample(layers[0].source(), east[2, 3], north[2, 3])
        # B is 1 m further east. The field rises 0.5 K/m along the model's x axis and 5 K/m along y;
        # 1 m east is cos(R) m along x and sin(R) m along y, and the field is linear, so bilinear is exact.
        r = math.radians(fx.ROTATION)
        self.assertAlmostEqual(value, 0.5 * math.cos(r) + 5.0 * math.sin(r), delta=0.01)

    def test_sub_area_clip(self):
        from qgis.core import QgsProject
        east, north = fx.cell_centres()
        half = 1.0
        polygon = (f'POLYGON(({east[1, 1] - half} {north[1, 1] - half}, {east[1, 1] + half} {north[1, 1] - half}, '
                   f'{east[1, 1] + half} {north[1, 1] + half}, {east[1, 1] - half} {north[1, 1] + half}, '
                   f'{east[1, 1] - half} {north[1, 1] - half}))')
        area = make_layer('Polygon', 'EPSG:32633', [(polygon, [])])
        QgsProject.instance().addMapLayer(area)
        self.load(self.root)
        self.plugin.dlg.cb_Output_SubArea.setLayer(area)
        self.plugin.select_cb_Output_SubArea()
        self.choose_variable('Universal Thermal Climate Index at Biometeorogical Height Level [UTCIBiomet] (Only Series A)')
        self.check(self.plugin.dlg.lw_SeriesA, [0])
        layers = [layer for layer in self.run_task()]
        extent = layers[0].extent()
        self.assertLessEqual(extent.width(), 2 * half + 1.0)
        self.assertAlmostEqual(sample(layers[0].source(), east[1, 1], north[1, 1]), 30.0 + 1 + 0.1, places=4)


if __name__ == '__main__':
    unittest.main()
