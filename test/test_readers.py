# coding=utf-8
"""core.readers on synthetic ENVI-met files, and optionally on real outputs.

Set the environment variable G2E_TEST_OUTPUTS to a folder that contains ENVI-met
output folders to also check the readers against real files.
"""

import datetime as dt
import math
import os
import shutil
import tempfile
import unittest

import numpy as np

from . import fixtures as fx
from .plugin_env import import_plugin_module


class ReaderBasicsTest(unittest.TestCase):

    def setUp(self):
        self.r = import_plugin_module('core.readers')

    def test_round_to_minute(self):
        moment = self.r.round_to_minute(dt.datetime(2024, 7, 6, 4, 59, 59))
        self.assertEqual(moment, dt.datetime(2024, 7, 6, 5, 0))
        self.assertEqual(self.r.round_to_minute(dt.datetime(2024, 12, 31, 23, 59, 31)), dt.datetime(2025, 1, 1))
        self.assertEqual(self.r.round_to_minute(dt.datetime(2024, 7, 6, 5, 0, 29)), dt.datetime(2024, 7, 6, 5, 0))

    def test_level_for_height(self):
        dz = [0.4, 0.4, 0.4, 2.0]
        self.assertEqual(self.r.level_for_height(dz, 0.0), (0, (0.0, 0.4)))
        self.assertEqual(self.r.level_for_height(dz, 0.4)[0], 0)      # boundary -> lower cell
        self.assertEqual(self.r.level_for_height(dz, 1.0)[0], 2)
        self.assertEqual(self.r.level_for_height(dz, 50.0)[0], 3)

    def test_terrain_cells(self):
        objects = np.zeros((4, 1, 3))
        objects[0:2, 0, 1] = 2
        objects[:, 0, 2] = 2
        self.assertEqual(self.r.terrain_cells(objects).tolist(), [[0, 2, 4]])


class NetcdfReaderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.r = import_plugin_module('core.readers')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_nc_')
        cls.current = fx.write_netcdf(os.path.join(cls.tmp, 'current', 'sim_001.nc'))
        cls.old = fx.write_netcdf(os.path.join(cls.tmp, 'old', 'sim_001.nc'), layout='old')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def open(self, path):
        result = self.r.NetcdfFile(path)
        self.addCleanup(result.close)
        return result

    def test_grid_and_times(self):
        for path in (self.current, self.old):
            nc = self.open(path)
            self.assertEqual((nc.grid.nx, nc.grid.ny), (fx.NX, fx.NY))
            self.assertEqual(nc.grid.epsg, 32633)
            self.assertAlmostEqual(nc.grid.rotation, fx.ROTATION)
            # the old layout stores 0.9994 h: both read as 05:00
            self.assertEqual(nc.times, [dt.datetime(2024, 7, 6, 4, 0), dt.datetime(2024, 7, 6, 5, 0)])

    def test_southern_hemisphere_epsg(self):
        # the crs variable of the fixture says EPSG:32633, the latitude says south: the latitude wins
        path = fx.write_netcdf(os.path.join(self.tmp, 'south', 'sim_001.nc'), latitude=-33.9)
        self.assertEqual(self.open(path).grid.epsg, 32733)

    def test_variables_by_short_name(self):
        nc = self.open(self.current)
        # coordinates are not data; variables with a shared long name are both there
        self.assertNotIn('utm_easting', nc.variables)
        self.assertNotIn('Lat', nc.variables)
        self.assertIn('WallTempX', nc.variables)
        self.assertIn('WallTempY', nc.variables)
        self.assertEqual(nc.variables['PET'].label(), 'PET (Default Person) [PET]')
        self.assertEqual(nc.variables['T'].display_units, '°C')
        self.assertEqual(nc.variables['T'].kind, self.r.KIND_3D)
        self.assertEqual(nc.variables['UTCIBiomet'].kind, self.r.KIND_2D)
        self.assertEqual(nc.variables['SoilTemp'].kind, self.r.KIND_SOIL)

    def test_terrain_following_read(self):
        nc = self.open(self.current)
        data, description = nc.read('T', time_index=1, height=1.0)   # level 2 (0.8 m - 1.2 m)
        self.assertEqual(description, '0.8m-1.2m')
        self.assertEqual(data[0, 0], fx.t_value(1, 2, 0, 0))
        tj, ti = fx.TERRAIN_COLUMN
        self.assertEqual(data[tj, ti], fx.t_value(1, 2 + 2, tj, ti))     # two terrain cells below
        bj, bi = fx.BUILDING_COLUMN
        self.assertTrue(math.isnan(data[bj, bi]))                     # inside the building

    def test_2d_and_soil_reads(self):
        nc = self.open(self.current)
        data, description = nc.read('UTCIBiomet', time_index=0)
        self.assertEqual(description, '')
        self.assertAlmostEqual(data[2, 3], 30.0 + 2 + 0.3, places=5)
        self.assertTrue(math.isnan(data[fx.BUILDING_COLUMN]))
        data, description = nc.read('SoilTemp', time_index=0, height=0.06)
        self.assertEqual(description, '0.05m depth')
        self.assertEqual(data[0, 0], 19.0)

    def test_cell_centres_match_the_file(self):
        nc = self.open(self.current)
        self.assertTrue(nc.has_utm_fields())
        east, north = nc.utm_fields()
        grid_east, grid_north = nc.grid.cell_centres()
        self.assertLess(np.abs(grid_east - east).max(), 1e-6)
        self.assertLess(np.abs(grid_north - north).max(), 1e-6)
        self.assertLess(nc.placement_error(), 1e-6)
        self.assertIsNone(self.open(self.old).placement_error())
        # the geotransform maps pixel centres (north-up rows) to the same points
        gt = nc.grid.geotransform()
        for j, i in ((0, 0), (fx.NY - 1, fx.NX - 1), (2, 4)):
            row, col = fx.NY - 1 - j, i
            x = gt[0] + (col + 0.5) * gt[1] + (row + 0.5) * gt[2]
            y = gt[3] + (col + 0.5) * gt[4] + (row + 0.5) * gt[5]
            self.assertAlmostEqual(x, east[j, i], places=6)
            self.assertAlmostEqual(y, north[j, i], places=6)


class EdxReaderTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.r = import_plugin_module('core.readers')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_edx_')
        cls.edx = fx.write_edx(os.path.join(cls.tmp, 'atmosphere'), ring=2)
        cls.nc = fx.write_netcdf(os.path.join(cls.tmp, 'NetCDF', 'sim_001.nc'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_ring_is_cropped_and_time_rounded(self):
        edx = self.r.EdxFile(self.edx)
        self.assertEqual((edx.grid.nx, edx.grid.ny), (fx.NX, fx.NY))
        self.assertTrue(edx.grid.is_uniform())
        self.assertEqual(edx.times, [dt.datetime(2024, 7, 6, 5, 0)])
        self.assertIn('Objects', edx.variables)
        self.assertEqual(edx.variables['Air Temperature'].units, '°C')

    def test_header_encodings(self):
        for encoding in ('utf-8', 'cp1252'):
            path = fx.write_edx(os.path.join(self.tmp, encoding), encoding=encoding)
            self.assertEqual(self.r.EdxFile(path).variables['Air Temperature'].units, '°C')

    def test_same_values_as_netcdf(self):
        edx = self.r.EdxFile(self.edx)
        nc = self.r.NetcdfFile(self.nc)
        self.addCleanup(nc.close)
        self.assertTrue(edx.grid.matches(nc.grid))
        for height in (0.0, 1.0, 5.0):
            a, desc_a = edx.read('Air Temperature', height=height)
            b, desc_b = nc.read('T', time_index=1, height=height)
            self.assertEqual(desc_a, desc_b)
            np.testing.assert_array_equal(a, b)


class FindSourcesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.r = import_plugin_module('core.readers')
        cls.tmp = tempfile.mkdtemp(prefix='g2e_src_')
        cls.root = fx.write_output_folder(os.path.join(cls.tmp, 'sim_output'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_output_folder(self):
        sources = self.r.find_sources(self.root)
        self.addCleanup(lambda: [s.close() for s in sources])
        self.assertEqual([s.name for s in sources], ['NetCDF', 'Report_Slice', 'atmosphere (EDX)'])
        atmosphere = sources[2]
        # the 'First Flow Field' copy is not a time step
        self.assertEqual([t.datetime for t in atmosphere.timesteps],
                         [dt.datetime(2024, 7, 6, 4, 0), dt.datetime(2024, 7, 6, 5, 0)])
        self.assertEqual(len(sources[0].timesteps), 2)

    def test_subfolders_directly(self):
        names = [s.name for s in self.r.find_sources(os.path.join(self.root, 'NetCDF'))]
        self.assertEqual(names, ['NetCDF'])
        names = [s.name for s in self.r.find_sources(os.path.join(self.root, 'atmosphere'))]
        self.assertEqual(names, ['EDX (EDX)'])
        names = [s.name for s in self.r.find_sources(os.path.join(self.root, 'reportData'))]
        self.assertEqual(names, ['Report_Slice'])


@unittest.skipUnless(os.environ.get('G2E_TEST_OUTPUTS'), 'set G2E_TEST_OUTPUTS to check real ENVI-met outputs')
class RealOutputsTest(unittest.TestCase):
    """Placement and EDX/NetCDF agreement on real output folders below $G2E_TEST_OUTPUTS."""

    @classmethod
    def setUpClass(cls):
        cls.r = import_plugin_module('core.readers')
        root = os.environ['G2E_TEST_OUTPUTS']
        cls.outputs = []
        for current, dirs, _files in os.walk(root):
            if 'NetCDF' in dirs or 'atmosphere' in dirs:
                cls.outputs.append(current)
                dirs[:] = []
            elif current.count(os.sep) - root.count(os.sep) >= 3:
                dirs[:] = []

    def test_cell_centres_match_utm_fields(self):
        checked = 0
        for output in self.outputs:
            for source in self.r.find_sources(output):
                if source.name != 'NetCDF':
                    continue
                nc = source.first_file()
                if nc is not None and nc.has_utm_fields():
                    east, north = nc.utm_fields()
                    grid_east, grid_north = nc.grid.cell_centres()
                    error = max(np.abs(grid_east - east).max(), np.abs(grid_north - north).max())
                    with self.subTest(output=output):
                        self.assertLess(error, 0.01)
                    checked += 1
                source.close()
        print(f'\n  placement checked in {checked} NetCDF files')

    def test_pedestrian_rule_matches_znodebiomet(self):
        """From 5.9.5 on, ENVI-met's biomet level is the terrain-following rule in every column."""
        zones = import_plugin_module('core.zones')
        checked = 0
        for output in self.outputs:
            for source in self.r.find_sources(output):
                if source.name != 'NetCDF':
                    continue
                nc = source.first_file()
                if nc is None or (nc.model_version() or (0,)) < (5, 9, 5):
                    source.close()
                    continue
                static = nc.static_fields()
                if static.reported_biomet_k is not None:
                    rule = zones.pedestrian_levels(static.dem, static.dz)
                    with self.subTest(output=output):
                        np.testing.assert_array_equal(rule, static.reported_biomet_k)
                    checked += 1
                source.close()
        print(f'\n  pedestrian level checked in {checked} NetCDF files')

    def test_edx_matches_netcdf(self):
        checked = 0
        for output in self.outputs:
            sources = {s.name: s for s in self.r.find_sources(output)}
            nc_source, edx_source = sources.get('NetCDF'), sources.get('atmosphere (EDX)')
            if nc_source is None or edx_source is None:
                continue
            nc_steps = {t.datetime: t for t in nc_source.timesteps}
            for step in edx_source.timesteps:
                if step.datetime not in nc_steps or step.datetime == nc_source.timesteps[0].datetime:
                    continue
                nc_step = nc_steps[step.datetime]
                nc = nc_source.open(nc_step.path)
                edx = edx_source.open(step.path)
                if 'T' not in nc.variables or 'Air Temperature' not in edx.variables:
                    continue
                a, _ = edx.read('Air Temperature', height=1.5)
                b, _ = nc.read('T', time_index=nc_step.index, height=1.5)
                with self.subTest(output=output, time=step.datetime):
                    self.assertEqual(a.shape, b.shape)
                    both = ~np.isnan(a) & ~np.isnan(b)
                    self.assertGreater(both.sum(), 0)
                    self.assertLess(np.abs(a[both] - b[both]).max(), 1e-3)
                checked += 1
                break
            nc_source.close()
            edx_source.close()
        print(f'\n  EDX vs NetCDF checked in {checked} outputs')


if __name__ == '__main__':
    unittest.main()
