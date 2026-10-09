# coding=utf-8
"""Build small synthetic GIS layers, export them with the Worker and read the INX back."""

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


def grid_text(values):
    """A grid of the model area as rows of text, north first, as the XML matrices print it."""
    return [['1' if v is True else '0' if v is False else str(v) for v in row] for row in values.tolist()]


def read_inx(path):
    """The parts of an INX file (either format, core.inx) the tests look at."""
    inx = import_plugin_module('core.inx')
    model = inx.read(path)
    with open(path, encoding='utf-8-sig') as f:
        text = f.read()
    return {
        'model': model,
        'II': model['geometry']['i'],
        'JJ': model['geometry']['j'],
        'zTop': grid_text(model['grids']['top']),
        'fixedheight': grid_text(model['grids']['fixedHeight']),
        'soil': grid_text(model['grids']['soilProfiles']),
        'receptors': {r['name']: (r['i'], r['j']) for r in model['receptors']},
        'plants3d': [(p['i'], p['j'], p['id']) for p in model['plants3d']],
        'text': text,
    }
