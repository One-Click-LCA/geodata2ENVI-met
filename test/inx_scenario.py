# coding=utf-8
"""A fuller INX export scenario: every kind of input, layers in lon/lat, a rotated sub-area and a DEM."""

import math
import os

import numpy as np

from .inx_helpers import (make_layer, new_worker, set_buildings, set_plants3d, set_receptors)
from .plugin_env import import_plugin_module, start_qgis

UTM = 'EPSG:32632'
X0, Y0 = 690000.0, 5340000.0      # zone 32, about 11.6 E 48.2 N
ROTATION = 25.0                   # the model area turns clockwise by this angle
DX = 2.0
WIDTH, HEIGHT = 30 * DX, 20 * DX


def utm(x, y):
    """Model coordinates (m from the lower-left corner along the model axes) -> UTM."""
    r = math.radians(ROTATION)
    return X0 + x * math.cos(r) + y * math.sin(r), Y0 - x * math.sin(r) + y * math.cos(r)


def model_rectangle(x0, y0, x1, y1, to_lonlat=None):
    corners = [utm(x0, y0), utm(x0, y1), utm(x1, y1), utm(x1, y0), utm(x0, y0)]
    if to_lonlat is not None:
        corners = [to_lonlat(x, y) for x, y in corners]
    return 'POLYGON((' + ', '.join(f'{x:.9f} {y:.9f}' for x, y in corners) + '))'


def model_point(x, y, to_lonlat=None):
    e, n = utm(x, y)
    if to_lonlat is not None:
        e, n = to_lonlat(e, n)
    return f'POINT({e:.9f} {n:.9f})'


def model_line(points, to_lonlat=None):
    coords = [utm(x, y) for x, y in points]
    if to_lonlat is not None:
        coords = [to_lonlat(e, n) for e, n in coords]
    return 'LINESTRING(' + ', '.join(f'{e:.9f} {n:.9f}' for e, n in coords) + ')'


def lonlat_transformer():
    import pyproj
    transformer = pyproj.Transformer.from_crs(32632, 4326, always_xy=True)
    return lambda e, n: transformer.transform(e, n)


def write_dem(path):
    """A DEM GeoTIFF in UTM covering the model with a slope rising 0.1 m per metre to the east."""
    from osgeo import gdal, osr
    xmin, xmax = X0 - 60, X0 + 120
    ymin, ymax = Y0 - 60, Y0 + 100
    res = 1.0
    cols, rows = int((xmax - xmin) / res), int((ymax - ymin) / res)
    x = xmin + (np.arange(cols) + 0.5) * res
    values = np.tile(200.0 + 0.1 * (x - xmin), (rows, 1)).astype(np.float32)
    dataset = gdal.GetDriverByName('GTiff').Create(path, cols, rows, 1, gdal.GDT_Float32)
    dataset.SetGeoTransform((xmin, res, 0, ymax, 0, -res))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32632)
    dataset.SetProjection(srs.ExportToWkt())
    dataset.GetRasterBand(1).WriteArray(values)
    dataset = None
    return path


def configure(worker, folder, far_feature=False):
    """Give ``worker`` every kind of input. ``far_feature`` adds a building near 5 E (UTM zone 31)."""
    start_qgis()
    consts = import_plugin_module('Const_defines')
    integer, string = consts.FIELD_TYPE_INT, consts.FIELD_TYPE_STRING
    lonlat = lonlat_transformer()
    buildings = [
        (model_rectangle(4, 4, 14, 10, lonlat), [12, 'Hall', '000000', '000000']),
        (model_rectangle(20, 22, 30, 30, lonlat), [21, 'Tower', '000000', '000000']),
    ]
    if far_feature:
        buildings.append(('POLYGON((5.0 48.0, 5.001 48.0, 5.001 48.001, 5.0 48.001, 5.0 48.0))', [9, 'Far', '', '']))
    set_buildings(worker, make_layer('Polygon', 'EPSG:4326', buildings,
                                     fields=[('top', integer), ('name', string), ('wall', string), ('roof', string)]),
                  'top')
    worker.bName, worker.bName_UseCustom = 'name', False
    surfaces = make_layer('Polygon', 'EPSG:4326', [(model_rectangle(0, 0, 30, 12, lonlat), ['0100ST'])],
                          fields=[('soil', string)])
    worker.surfLayer, worker.surfID, worker.surfID_UseCustom, worker.surfLayerfromVector = surfaces, 'soil', False, True
    plants = make_layer('Polygon', 'EPSG:4326', [(model_rectangle(36, 6, 44, 14, lonlat), ['0000H2'])],
                        fields=[('plant', string)])
    worker.plant1dLayer, worker.plant1dID, worker.plant1dID_UseCustom = plants, 'plant', False
    worker.plant1dLayerFromVector = True
    trees = make_layer('Point', 'EPSG:4326', [(model_point(49, 33, lonlat), ['0000C2'])], fields=[('pid', string)])
    set_plants3d(worker, trees, 'pid')
    receptors = make_layer('Point', 'EPSG:4326', [(model_point(17, 15, lonlat), ['R1']),
                                                    (model_point(59, 39, lonlat), ['NE'])], fields=[('rid', string)])
    set_receptors(worker, receptors, 'rid')
    points = make_layer('Point', 'EPSG:4326', [(model_point(27, 3, lonlat), ['0000PS'])], fields=[('src', string)])
    lines = make_layer('LineString', 'EPSG:4326', [(model_line([(1, 17), (59, 17)], lonlat), ['0000LS'])],
                       fields=[('src', string)])
    areas = make_layer('Polygon', 'EPSG:4326', [(model_rectangle(50, 2, 58, 8, lonlat), ['0000AS'])],
                       fields=[('src', string)])
    for kind, layer in (('P', points), ('L', lines), ('A', areas)):
        setattr(worker, f'src{kind}Layer', layer)
        setattr(worker, f'src{kind}ID', 'src')
        setattr(worker, f'src{kind}ID_UseCustom', False)
    from qgis.core import QgsRasterLayer
    worker.dEMLayer = QgsRasterLayer(write_dem(os.path.join(folder, 'dem.tif')), 'dem')
    worker.dEMBand = 1
    worker.dEMInterpol = 1
    worker.removeBBorder = 0
    return worker


def sub_area():
    return make_layer('Polygon', UTM, [(model_rectangle(0, 0, WIDTH, HEIGHT), [])])


def export(folder, name, far_feature=False):
    path = os.path.join(folder, name + '.INX')
    worker = new_worker(sub_area(), dx=DX, dy=DX, filename=path)
    configure(worker, folder, far_feature)
    worker.saveINX()
    return path
