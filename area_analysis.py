"""Area analysis, QGIS side: analysis areas from a polygon layer, outputs, cell previews.

The computation itself is in core.zones and core.stats.
"""

import math
import os
import re

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsField, QgsFields,
                       QgsGeometry, QgsPointXY)

from .Const_defines import FIELD_TYPE_DOUBLE, FIELD_TYPE_INT, FIELD_TYPE_STRING
from .core import readers, stats as core_stats, zones as core_zones

ALL_AREAS = 'all'


class AnalysisError(Exception):
    pass


def open_source(path, source_name=''):
    """A readers.Source for a result file, or for a source (by name) of an output folder."""
    if os.path.isfile(path):
        if path.lower().endswith('.nc'):
            return readers.Source(os.path.splitext(os.path.basename(path))[0], [path])
        folder = os.path.dirname(path)
        for source in readers.find_sources(folder):
            if os.path.normcase(path) in (os.path.normcase(p) for p in source.paths):
                return source
        raise AnalysisError(f'{path} is not an ENVI-met result file.')
    sources = readers.find_sources(path)
    if not sources:
        raise AnalysisError(f'No ENVI-met results (NetCDF or EDX/EDT files) in {path}.')
    if not source_name:
        return sources[0]
    for source in sources:
        if source.name.lower() == source_name.strip().lower():
            return source
    raise AnalysisError(f'{path} has no results called "{source_name}". '
                        f'Available: {", ".join(s.name for s in sources)}.')


def _value(feature, field):
    value = feature[field]
    if value is None or (hasattr(value, 'isNull') and value.isNull()):
        return None
    text = str(value).strip()
    return text if text and text != 'NULL' else None


def zones_from_features(features, layer_crs, id_field, name_field, epsg, transform_context):
    """Zones from polygon features, dissolved per ID (all features form one zone without an ID field).

    Returns (zones, number of features without an ID that were skipped).
    """
    transform = QgsCoordinateTransform(layer_crs, QgsCoordinateReferenceSystem(f'EPSG:{epsg}'), transform_context)
    geometries, names, skipped = {}, {}, 0
    for feature in features:
        if not feature.hasGeometry():
            continue
        zone_id = _zone_id(feature, id_field) if id_field else ALL_AREAS
        if zone_id is None:
            skipped += 1
            continue
        geometry = QgsGeometry(feature.geometry())
        geometry.convertToStraightSegment()      # curved polygons
        geometry.transform(transform)
        geometries.setdefault(zone_id, []).append(geometry)
        if zone_id not in names and name_field:
            names[zone_id] = _value(feature, name_field)
    zones = []
    for zone_id, parts in geometries.items():
        union = QgsGeometry.unaryUnion(parts)
        polygons = []
        for part in union.asGeometryCollection():
            rings = part.asPolygon()
            if not rings:
                continue
            outer = np.array([(p.x(), p.y()) for p in rings[0]])
            holes = [np.array([(p.x(), p.y()) for p in ring]) for ring in rings[1:]]
            polygons.append((outer, holes))
        if polygons:
            zones.append(core_zones.Zone(zone_id, names.get(zone_id) or str(zone_id), polygons))
    zones.sort(key=lambda z: (str(type(z.zone_id)), z.zone_id))
    return zones, skipped


def _zone_id(feature, field):
    """The area ID of a feature, or None.

    IDs stay numbers where they are numbers, so they sort and join naturally in spreadsheets: numeric
    fields, and text that is written as a plain number ("1", "2.5"). Other text stays text, so two
    different IDs never become the same one ("01" stays "01" next to "1").
    """
    value = feature[field]
    if value is None or (hasattr(value, 'isNull') and value.isNull()):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(value) if float(value).is_integer() else value
    text = str(value).strip()
    if not text or text == 'NULL':
        return None
    try:
        number = float(text)
        number = int(number) if number.is_integer() else number
    except ValueError:
        return text
    return number if str(number) == text else text


def latlon_function(epsg):
    """(east, north) arrays -> (lat, lon) arrays for EPSG ``epsg``."""
    import pyproj
    transformer = pyproj.Transformer.from_crs(int(epsg), 4326, always_xy=True)

    def convert(east, north):
        lon, lat = transformer.transform(np.asarray(east), np.asarray(north))
        return np.asarray(lat), np.asarray(lon)
    return convert


def resolve_variables(result_file, text, mode):
    """VariableRequests for a comma-separated list of names (short or long); default: UTCI.

    Returns (variables, problems).
    """
    available = result_file.variables
    problems = []
    if not text or not text.strip():
        chosen = None
        if mode == core_zones.MODE_PEDESTRIAN:
            chosen = next((k for k, v in available.items() if v.kind == readers.KIND_2D
                           and 'UTCI' in k.upper() and 'BIOMET' in k.upper().replace(' ', '')), None)
        if chosen is None:
            chosen = next((k for k, v in available.items() if v.kind == readers.KIND_3D and 'UTCI' in k.upper()), None)
        if chosen is None:
            return [], ['These results have no UTCI; choose the variables to evaluate.']
        tokens = [chosen]
    else:
        tokens = [t.strip() for t in re.split(r'[;,]', text) if t.strip()]
    variables = []
    for token in tokens:
        key = token if token in available else next(
            (k for k, v in available.items() if token.lower() in (k.lower(), v.long_name.lower())), None)
        if key is None:
            problems.append(f'"{token}" is not in these results.')
            continue
        request, problem = _request(available, key, token, mode)
        if problem:
            problems.append(problem)
        else:
            variables.append(request)
    return variables, problems


def _request(available, key, token, mode, name=None):
    """(VariableRequest, None) for a variable that can be evaluated in ``mode``, else (None, problem)."""
    v = available[key]
    if v.kind == readers.KIND_SOIL:
        return None, f'"{token}" is a soil variable; area statistics use atmosphere cells.'
    if mode == core_zones.MODE_RANGE and v.kind != readers.KIND_3D:
        return None, f'"{token}" is a 2D field; height ranges need 3D variables.'
    return core_stats.VariableRequest(key, v.long_name, v.display_units, v.kind, name=name), None


def _plain(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def pair_variables(variables_a, result_file_b, text_b, mode):
    """B's variables for A's, for a comparison: each carries A's key as its name, so the rows pair up.

    ``text_b`` names them in A's order. Empty: B's variable with A's key, else the one with A's long
    name (NetCDF "T" is "Air Temperature", the EDX key), else the one whose name matches without
    spaces and punctuation (NetCDF "UTCIBiomet" and EDX "UTCI Biomet"). Returns (variables, problems).
    """
    available = result_file_b.variables
    problems = []
    if text_b and text_b.strip():
        tokens = [t.strip() for t in re.split(r'[;,]', text_b) if t.strip()]
        if len(tokens) != len(variables_a):
            return [], [f'Variables B: name one for each variable of A ({len(variables_a)}), in the same order.']
        candidates = []
        for token in tokens:
            matches = [k for k, v in available.items() if token.lower() in (k.lower(), v.long_name.lower())]
            candidates.append((token, token if token in available else (matches[0] if matches else None)))
    else:
        candidates = []
        for a in variables_a:
            key = a.key if a.key in available else _unique(
                k for k, v in available.items() if v.long_name.lower() == a.long_name.lower())
            if key is None:
                plain = {_plain(a.key), _plain(a.long_name)}
                key = _unique(k for k, v in available.items() if _plain(k) in plain or _plain(v.long_name) in plain)
            candidates.append((a.key, key))
    variables = []
    for a, (token, key) in zip(variables_a, candidates):
        if key is None:
            problems.append(f'"{token}" is not in results B; name the variables of B (same order as A).')
            continue
        request, problem = _request(available, key, token, mode, name=a.name)
        if problem:
            problems.append(problem)
        else:
            variables.append(request)
    return variables, problems


def _unique(keys):
    keys = list(keys)
    return keys[0] if len(keys) == 1 else None


def same_vertical(static_a, static_b):
    """True if a cell index (j, i, k) is the same place in both runs: same levels and same terrain.

    Different buildings do not matter (their cells are simply invalid in one run); a different
    terrain or vertical grid puts the same k at another height.
    """
    return (static_a.dz.shape == static_b.dz.shape and np.allclose(static_a.dz, static_b.dz)
            and static_a.dem.shape == static_b.dem.shape and np.array_equal(static_a.dem, static_b.dem))


def level_text(mode, z_min, z_max):
    if mode == core_zones.MODE_PEDESTRIAN:
        return f'pedestrian level (terrain + {core_zones.PEDESTRIAN_HEIGHT:g} m)'
    return f'{z_min:g}-{z_max:g} m above ground'


def write_masks(folder, prefix, grid, static, masks, info, delimiter=','):
    """<prefix>_cells.csv, <prefix>_zones.csv and <prefix>_grid.json; returns their paths."""
    os.makedirs(folder, exist_ok=True)
    try:
        latlon = latlon_function(grid.epsg)
    except Exception:          # pyproj missing or failing: leave lat/lon empty
        latlon = None
    rows = []
    for mask in masks:
        rows.extend(core_zones.cell_rows(grid, static, mask, latlon))
    paths = {
        'cells': core_stats.write_csv(os.path.join(folder, f'{prefix}_cells.csv'), rows,
                                      core_zones.CELL_COLUMNS, delimiter),
        'zones': core_stats.write_csv(os.path.join(folder, f'{prefix}_zones.csv'),
                                      [core_zones.zone_row(grid, m) for m in masks],
                                      core_zones.ZONE_COLUMNS, delimiter),
    }
    paths['grid'] = os.path.join(folder, f'{prefix}_grid.json')
    core_zones.write_grid_json(paths['grid'], grid, info)
    return paths


def preview_fields():
    fields = QgsFields()
    fields.append(QgsField('zone_id', FIELD_TYPE_STRING))
    fields.append(QgsField('zone_name', FIELD_TYPE_STRING))
    for name in ('i', 'j', 'k'):
        fields.append(QgsField(name, FIELD_TYPE_INT))
    for name in ('fraction', 'vertical_fraction', 'weight'):
        fields.append(QgsField(name, FIELD_TYPE_DOUBLE))
    return fields


def preview_features(grid, masks, fields):
    """One polygon per listed cell (its footprint), with the zone and the cell's weights."""
    dx, dy = float(grid.dx[0]), float(grid.dy[0])
    r = np.radians(grid.rotation)
    c, s = np.cos(r), np.sin(r)

    def utm(x, y):
        return QgsPointXY(grid.x0 + x * c + y * s, grid.y0 - x * s + y * c)

    for mask in masks:
        for n in range(len(mask)):
            i, j = int(mask.i[n]), int(mask.j[n])
            x0, y0 = i * dx, j * dy
            ring = [utm(x0, y0), utm(x0 + dx, y0), utm(x0 + dx, y0 + dy), utm(x0, y0 + dy), utm(x0, y0)]
            feature = QgsFeature(fields)
            feature.setGeometry(QgsGeometry.fromPolygonXY([ring]))
            feature.setAttributes([str(mask.zone.zone_id), mask.zone.name, i, j, int(mask.k[n]),
                                   float(mask.fraction[n]), float(mask.vertical_fraction[n]), float(mask.weight[n])])
            yield feature
