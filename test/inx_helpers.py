# coding=utf-8
"""Build small synthetic GIS layers, export them with the Worker and read the INX back."""

import re

from .plugin_env import import_plugin_module, start_qgis


def make_layer(geometry_type, crs, features, fields=()):
    """Memory layer from (wkt, attributes) pairs; ``fields`` are (name, type) pairs."""
    start_qgis()
    from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsVectorLayer
    layer = QgsVectorLayer(f'{geometry_type}?crs={crs}', geometry_type.lower(), 'memory')
    provider = layer.dataProvider()
    provider.addAttributes([QgsField(name, field_type) for name, field_type in fields])
    layer.updateFields()
    new_features = []
    for wkt, attributes in features:
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromWkt(wkt))
        feature.setAttributes(list(attributes))
        new_features.append(feature)
    provider.addFeatures(new_features)
    layer.updateExtents()
    return layer


def rectangle_wkt(x0, y0, x1, y1):
    """Rectangle starting at the lower-left corner, the vertex the plugin uses as R0."""
    return f'POLYGON(({x0} {y0}, {x0} {y1}, {x1} {y1}, {x1} {y0}, {x0} {y0}))'


def new_worker(sub_area, dx=2.0, dy=2.0, filename=''):
    """A Worker set up like Geo2ENVImet.start_worker_inx does with an empty dialog."""
    worker_module = import_plugin_module('Worker')
    worker = worker_module.Worker()
    worker.subAreaLayer = sub_area
    worker.subAreaLayer_nonRot = sub_area
    worker.dx = dx
    worker.dy = dy
    worker.dz = 2.0
    worker.KK = 10
    worker.useSplitting = True
    worker.useTelescoping = False
    worker.teleStart = 0
    worker.teleStretch = 0
    worker.filename = filename
    worker.defaultRoof = '000000'
    worker.defaultWall = '000000'
    worker.removeBBorder = 0
    worker.startSurfID = '0200PP'
    # no network in tests
    worker.get_time_zone_geonames = lambda: '1'
    worker.get_elevation_geonames = lambda: 100
    return worker


def set_buildings(worker, layer, top_field):
    worker.bLayer = layer
    worker.bTop = top_field
    worker.bTop_UseCustom = False
    worker.bBot = ''
    worker.bBot_UseCustom = False
    for name in ('bName', 'bWall', 'bRoof', 'bGreenWall', 'bGreenRoof'):
        setattr(worker, name, '')
        setattr(worker, name + '_UseCustom', False)
    worker.bName_custom = ''
    worker.bWall_custom = '000000'
    worker.bRoof_custom = '000000'
    worker.bGreenWall_custom = ''
    worker.bGreenRoof_custom = ''
    worker.bBPS_disabled = True


def set_receptors(worker, layer, id_field):
    worker.recLayer = layer
    worker.recID = id_field
    worker.recID_UseCustom = False


def set_plants3d(worker, layer, id_field):
    worker.plant3dLayer = layer
    worker.plant3dID = id_field
    worker.plant3dID_UseCustom = False
    worker.plant3dAddOut_disabled = True


def read_inx(path):
    """The parts of an INX file the tests look at."""
    with open(path, encoding='utf-8') as f:
        text = f.read()

    def scalar(tag):
        m = re.search(r'<%s>\s*(.*?)\s*</%s>' % (tag, tag), text)
        return m.group(1) if m else None

    def matrix(tag):
        m = re.search(r'<%s type="matrix-data"[^>]*>(.*?)</%s>' % (tag, tag), text, re.S)
        if m is None:
            return None
        lines = [line.strip().rstrip(',') for line in m.group(1).strip().splitlines() if line.strip()]
        return [line.split(',') for line in lines]

    receptors = {name: (int(i), int(j)) for i, j, name in re.findall(
        r'<Receptors>\s*<cell_i>\s*(-?\d+)\s*</cell_i>\s*<cell_j>\s*(-?\d+)\s*</cell_j>\s*'
        r'<name>\s*(.*?)\s*</name>', text)}
    plants = [(int(i), int(j), plant_id) for i, j, plant_id in re.findall(
        r'<3Dplants>\s*<rootcell_i>\s*(-?\d+)\s*</rootcell_i>\s*<rootcell_j>\s*(-?\d+)\s*</rootcell_j>\s*'
        r'<rootcell_k>\s*-?\d+\s*</rootcell_k>\s*<plantID>\s*(.*?)\s*</plantID>', text)]
    return {
        'II': int(scalar('grids-I')),
        'JJ': int(scalar('grids-J')),
        'zTop': matrix('zTop'),
        'fixedheight': matrix('fixedheight'),
        'soil': matrix('ID_soilprofile'),
        'receptors': receptors,
        'plants3d': plants,
        'text': text,
    }
