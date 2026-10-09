"""ENVI-met model area files (INX): read both formats, write the JSON format of ENVI-met 6.

ENVI-met up to version 5 stores a model area as tagged text ("<ENVI-MET_Datafile>",
called XML here); ENVI-met 6 (SPACES, envicore) writes JSON and still reads both.
The file extension is .INX either way: a file whose first character is "{" is JSON.

Both formats are read into the same model, a dict:

    header      fileInfo, remark, description
    geometry    i, j, k, dx, dy, dz, useSplitting, useTelescoping, verticalStretch,
                startStretch, modelType ('2.5D' or 'full3D')
    nesting     nestingGrids, soilProfileA, soilProfileB
    location    name, modelRot, epsgGeo, lon, lat, epsgProj, x, y, timezoneUTC, timezoneLon
    defaults    commonWall, commonRoof
    surrounding useSurroundingArea, borderLeft, borderRight, borderFront, borderRear
    refAlt      reference altitude of the terrain (m above sea level)
    grids       name -> north-up array (rows = j from north to south, columns = i), names
                top, bot, no, terrain (int), fixedHeight (bool), simplePlants,
                soilProfiles, sources (text; '' = none)
    buildings   [{no, name, wall, roof, wallGreen, roofGreen, bps, buildingUse, indoorMode,
                  indoorLowerC, indoorUpperC, internalGainWm2, suppressACHeatRelease}]
    plants3d    [{i, j, k, id, name, obs}]   root cells, 1-based
    receptors   [{i, j, name}]               cells, 0-based (as ENVI-met stores them)

The keys follow the JSON format (lib/BIOS/u_tModelAreaJSON.pas). In the JSON file the
grids are [i][j] with j from south to north; the north-up arrays here are what the
export works with and what the XML matrices print.

No QGIS imports.
"""

import json
import re
from collections import OrderedDict
from datetime import datetime, timezone

import numpy as np

FILE_TYPE = 'modelAreaJSON'
VERSION = 1
FULL_3D = 'full3D'
MODEL_2_5D = '2.5D'

INT_GRIDS = ('top', 'bot', 'no', 'terrain')
BOOL_GRIDS = ('fixedHeight',)
TEXT_GRIDS = ('simplePlants', 'soilProfiles', 'sources')
GRIDS = INT_GRIDS + BOOL_GRIDS + TEXT_GRIDS

BORDERS = ('borderLeft', 'borderRight', 'borderFront', 'borderRear')


def pad_id(value):
    """A database ID as ENVI-met expects it: 6 characters, '0'-filled on the left ('' and NULL become '')."""
    text = str(value).strip()
    if text in ('NULL', 'None', 'nan'):
        return ''
    return text.zfill(6) if text else ''


# --------------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------------

def read(path):
    """The model area of an INX file in either format."""
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252', errors='replace')     # files of older ENVI-met versions
    if text.lstrip().startswith('{'):
        return _from_json(text)
    return _from_xml(text)


def is_json(path):
    with open(path, 'rb') as f:
        head = f.read(64).lstrip(b'\xef\xbb\xbf \t\r\n')
    return head.startswith(b'{')


def _from_json(text):
    data = json.loads(text, strict=False)['envimetDatafile']    # SPACES may leave control characters in names
    header = data.get('header', {})
    if header.get('fileType') != FILE_TYPE:
        raise ValueError(f"not an ENVI-met model area (fileType {header.get('fileType')!r})")
    config = data.get('domainConfig', {})
    spatial = data.get('spatialData2D', {})
    geometry = config.get('modelGeometry', {})
    model = _empty_model(int(geometry.get('i', 0)), int(geometry.get('j', 0)))
    model['header'].update({k: header.get(k, '') for k in ('fileInfo', 'remark', 'description')})
    model['geometry'].update(geometry)
    model['nesting'].update(config.get('nestingArea', {}))
    model['location'].update(config.get('locationData', {}))
    model['defaults'].update(config.get('defaultSettings', {}))
    model['surrounding'].update(config.get('surroundingArea', {}))
    buildings = spatial.get('buildings', {})
    sources = {'top': buildings.get('top'), 'bot': buildings.get('bot'), 'no': buildings.get('no'),
               'fixedHeight': buildings.get('fixedHeight'),
               'terrain': spatial.get('terrain', {}).get('data'),
               'simplePlants': spatial.get('simplePlants', {}).get('data'),
               'soilProfiles': spatial.get('soilProfiles', {}).get('data'),
               'sources': spatial.get('sources', {}).get('data')}
    for name, values in sources.items():
        if values:
            # [i][j] with j from south -> north-up rows
            model['grids'][name] = _typed(np.array(values, dtype=object).T[::-1], name)
    model['refAlt'] = spatial.get('terrain', {}).get('refAlt', 0)
    model['buildings'] = [dict(b) for b in spatial.get('buildingInfo', [])]
    model['plants3d'] = [dict(p) for p in spatial.get('plants3D', [])]
    model['receptors'] = [dict(r) for r in spatial.get('receptors', [])]
    return model


def _typed(array, name):
    if name in INT_GRIDS:
        return array.astype(float).astype(int)
    if name in BOOL_GRIDS:
        if array.size and isinstance(array.flat[0], str):
            return array.astype(float) != 0          # XML text '0'/'1'; bool('0') would be True
        return array.astype(bool)
    return array.astype(str)


def _empty_model(ii, jj):
    return {
        'header': {'fileInfo': '', 'remark': '', 'description': ''},
        'geometry': {'i': ii, 'j': jj, 'k': 0, 'dx': 0.0, 'dy': 0.0, 'dz': 0.0, 'useSplitting': False,
                     'useTelescoping': False, 'verticalStretch': 0.0, 'startStretch': 0.0, 'modelType': MODEL_2_5D},
        'nesting': {'nestingGrids': 0, 'soilProfileA': '', 'soilProfileB': ''},
        'location': {'name': '', 'modelRot': 0.0, 'epsgGeo': 'EPSG:4326', 'lon': 0.0, 'lat': 0.0, 'epsgProj': '',
                     'x': 0.0, 'y': 0.0, 'timezoneUTC': 0.0, 'timezoneLon': 0.0},
        'defaults': {'commonWall': '', 'commonRoof': ''},
        'surrounding': {'useSurroundingArea': True, **{border: 1 for border in BORDERS}},
        'refAlt': 0,
        'grids': {name: _default_grid(name, ii, jj) for name in GRIDS},
        'buildings': [],
        'plants3d': [],
        'receptors': [],
    }


def _default_grid(name, ii, jj):
    if name in INT_GRIDS:
        return np.zeros((jj, ii), dtype=int)
    if name in BOOL_GRIDS:
        return np.zeros((jj, ii), dtype=bool)
    return np.full((jj, ii), '', dtype='<U6')


# XML tag -> (section, key, type) of the model
_XML_SCALARS = {
    'fileInfo': ('header', 'fileInfo', str), 'remark': ('header', 'remark', str),
    'grids-I': ('geometry', 'i', int), 'grids-J': ('geometry', 'j', int), 'grids-Z': ('geometry', 'k', int),
    'dx': ('geometry', 'dx', float), 'dy': ('geometry', 'dy', float), 'dz-base': ('geometry', 'dz', float),
    'useTelescoping_grid': ('geometry', 'useTelescoping', bool), 'useSplitting': ('geometry', 'useSplitting', bool),
    'verticalStretch': ('geometry', 'verticalStretch', float), 'startStretch': ('geometry', 'startStretch', float),
    'numberNestinggrids': ('nesting', 'nestingGrids', int), 'soilProfileA': ('nesting', 'soilProfileA', str),
    'soilProfileB': ('nesting', 'soilProfileB', str),
    'modelRotation': ('location', 'modelRot', float), 'projectionSystem': ('location', 'epsgProj', str),
    'realworldLowerLeft_X': ('location', 'x', float), 'realworldLowerLeft_Y': ('location', 'y', float),
    'locationName': ('location', 'name', str), 'location_Longitude': ('location', 'lon', float),
    'location_Latitude': ('location', 'lat', float),
    'locationTimeZone_Longitude': ('location', 'timezoneLon', float),
    'commonWallMaterial': ('defaults', 'commonWall', str), 'commonRoofMaterial': ('defaults', 'commonRoof', str),
    'useSurroundingArea': ('surrounding', 'useSurroundingArea', bool),
    'borderLeft': ('surrounding', 'borderLeft', int), 'borderRight': ('surrounding', 'borderRight', int),
    'borderFront': ('surrounding', 'borderFront', int), 'borderRear': ('surrounding', 'borderRear', int),
}
_XML_GRIDS = {'zTop': 'top', 'zBottom': 'bot', 'buildingNr': 'no', 'fixedheight': 'fixedHeight',
              'ID_plants1D': 'simplePlants', 'ID_soilprofile': 'soilProfiles', 'ID_sources': 'sources',
              'terrainheight': 'terrain'}
_XML_BUILDING = {'BuildingInternalNr': ('no', int), 'BuildingName': ('name', str),
                 'BuildingWallMaterial': ('wall', str), 'BuildingRoofMaterial': ('roof', str),
                 'BuildingFacadeGreening': ('wallGreen', str), 'BuildingRoofGreening': ('roofGreen', str),
                 'ObserveBPS': ('bps', bool), 'BuildingUse': ('buildingUse', int),
                 'BuildingIndoorMode': ('indoorMode', int), 'BuildingIndoorLower': ('indoorLowerC', float),
                 'BuildingIndoorUpper': ('indoorUpperC', float), 'BuildingInternalGain': ('internalGainWm2', float),
                 'BuildingSuppressACHeat': ('suppressACHeatRelease', bool)}
_TAG = re.compile(r'<([A-Za-z0-9_\-]+)>([^<]*)</\1>')


def _convert(text, kind):
    text = text.strip()
    if kind is bool:
        return text not in ('', '0', 'false', 'False')
    if kind is int:
        return int(float(text)) if text else 0
    if kind is float:
        return float(text) if text else 0.0
    return text


def _from_xml(text):
    if '<ENVI-MET_Datafile>' not in text[:500]:
        raise ValueError('neither an ENVI-met 6 (JSON) nor an older (XML) model area')
    tags = {}
    for match in _TAG.finditer(text):
        tags.setdefault(match.group(1), match.group(2))
    model = _empty_model(_convert(tags.get('grids-I', '0'), int), _convert(tags.get('grids-J', '0'), int))
    for tag, (section, key, kind) in _XML_SCALARS.items():
        if tag in tags:
            model[section][key] = _convert(tags[tag], kind)
    if 'SurroundingArea' not in text:
        model['surrounding']['useSurroundingArea'] = False       # older versions have none
    zone = re.search(r'([-+]?\d+(?:\.\d+)?)', tags.get('locationTimeZone_Name', ''))
    model['location']['timezoneUTC'] = float(zone.group(1)) if zone else 0.0
    if _convert(tags.get('isFull3DDesign', '0'), bool):
        model['geometry']['modelType'] = FULL_3D
    model['refAlt'] = _convert(tags.get('DEMReference', '0'), float)

    for tag, name in _XML_GRIDS.items():
        # up to the next tag: some files lack the closing tag of a matrix
        match = re.search(r'<%s type="matrix-data"[^>]*>([^<]*)<' % tag, text)
        if match is None:
            continue
        ii = model['geometry']['i']
        rows = []
        for line in match.group(1).strip('\r\n').splitlines():
            if not line.strip() and not rows:
                continue
            cells = [cell.strip() for cell in line.strip().split(',')]
            # empty text cells end a line with commas; some writers add a trailing comma
            rows.append((cells + [''] * ii)[:ii] if ii else cells)
        while rows and not any(rows[-1]) and len(rows) > model['geometry']['j']:
            rows.pop()
        values = np.array(rows, dtype=object)
        if name in INT_GRIDS or name in BOOL_GRIDS:
            values[values == ''] = '0'
        model['grids'][name] = _typed(values, name)

    for block in re.findall(r'<Buildinginfo>(.*?)</Buildinginfo>', text, re.S):
        values = dict(_TAG.findall(block))
        building = {key: _convert(values[tag], kind) for tag, (key, kind) in _XML_BUILDING.items() if tag in values}
        model['buildings'].append(building)
    for block in re.findall(r'<3Dplants>(.*?)</3Dplants>', text, re.S):
        values = dict(_TAG.findall(block))
        model['plants3d'].append({'i': _convert(values.get('rootcell_i', '1'), int),
                                  'j': _convert(values.get('rootcell_j', '1'), int),
                                  'k': _convert(values.get('rootcell_k', '0'), int),
                                  'id': values.get('plantID', '').strip(), 'name': values.get('name', '').strip(),
                                  'obs': _convert(values.get('observe', '0'), bool)})
    for block in re.findall(r'<Receptors>(.*?)</Receptors>', text, re.S):
        values = dict(_TAG.findall(block))
        model['receptors'].append({'i': _convert(values.get('cell_i', '0'), int),
                                   'j': _convert(values.get('cell_j', '0'), int),
                                   'name': values.get('name', '').strip()})
    return model


# --------------------------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------------------------

def new_model(ii, jj):
    """An empty model area of ii x jj cells, to be filled before writing."""
    return _empty_model(ii, jj)


def write(path, model):
    """Write the model area as ENVI-met 6 JSON (UTF-8 with BOM, as SPACES writes it)."""
    text = to_json(model)
    with open(path, 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write(text)
    return path


def to_json(model):
    geometry, location = model['geometry'], model['location']
    ii, jj = int(geometry['i']), int(geometry['j'])
    grids = {}
    placeholders = {}

    def grid(name):
        values = np.asarray(model['grids'][name])
        if values.shape != (jj, ii):
            raise ValueError(f'grid {name} has the shape {values.shape}, the model area {(jj, ii)}')
        values = values[::-1].T          # north-up rows -> [i][j] with j from south
        if name in INT_GRIDS:
            rows = values.astype(int).tolist()
        elif name in BOOL_GRIDS:
            rows = values.astype(bool).tolist()
        elif name == 'soilProfiles':
            rows = [[pad_id(v) or '000000' for v in row] for row in values.astype(str).tolist()]
        else:
            rows = [[pad_id(v) for v in row] for row in values.astype(str).tolist()]
        key = f'@@grid{len(placeholders)}@@'
        placeholders[key] = rows
        return key

    for name in GRIDS:
        grids[name] = grid(name)

    data = OrderedDict([
        ('header', OrderedDict([
            ('fileType', FILE_TYPE), ('version', VERSION),
            ('revisionDate', datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') +
             f'{datetime.now(timezone.utc).microsecond // 1000:03d}Z'),
            ('remark', str(model['header'].get('remark', ''))),
            ('description', str(model['header'].get('description', ''))),
            ('fileInfo', str(model['header'].get('fileInfo', ''))),
        ])),
        ('domainConfig', OrderedDict([
            ('modelAreaInfo', OrderedDict([('description', str(model['header'].get('description', ''))),
                                           ('author', ''), ('copyright', '')])),
            ('modelGeometry', OrderedDict([
                ('i', ii), ('j', jj), ('k', int(geometry['k'])), ('dx', _number(geometry['dx'])),
                ('dy', _number(geometry['dy'])), ('dz', _number(geometry['dz'])),
                ('useSplitting', bool(geometry['useSplitting'])), ('useTelescoping', bool(geometry['useTelescoping'])),
                ('verticalStretch', _number(geometry['verticalStretch'])),
                ('startStretch', _number(geometry['startStretch'])),
                ('modelType', FULL_3D if geometry.get('modelType') == FULL_3D else MODEL_2_5D),
            ])),
            ('nestingArea', OrderedDict([
                ('nestingGrids', int(model['nesting']['nestingGrids'])),
                ('soilProfileA', pad_id(model['nesting']['soilProfileA'])),
                ('soilProfileB', pad_id(model['nesting']['soilProfileB'])),
            ])),
            ('locationData', OrderedDict([
                ('name', str(location['name'])), ('modelRot', _number(location['modelRot'])),
                ('epsgGeo', str(location.get('epsgGeo') or 'EPSG:4326')),
                ('lon', _number(location['lon'])), ('lat', _number(location['lat'])),
                ('epsgProj', str(location.get('epsgProj', ''))),
                ('x', _number(location['x'])), ('y', _number(location['y'])),
                ('timezoneUTC', _number(location['timezoneUTC'])), ('timezoneLon', _number(location['timezoneLon'])),
            ])),
            ('defaultSettings', OrderedDict([('commonWall', pad_id(model['defaults']['commonWall'])),
                                             ('commonRoof', pad_id(model['defaults']['commonRoof']))])),
            ('surroundingArea', OrderedDict(
                [('useSurroundingArea', bool(model['surrounding']['useSurroundingArea']))] +
                [(border, int(model['surrounding'][border])) for border in BORDERS])),
        ])),
        ('spatialData2D', OrderedDict([
            ('buildings', OrderedDict([('top', grids['top']), ('bot', grids['bot']), ('no', grids['no']),
                                       ('fixedHeight', grids['fixedHeight'])])),
            ('simplePlants', {'data': grids['simplePlants']}),
            ('soilProfiles', {'data': grids['soilProfiles']}),
            ('sources', {'data': grids['sources']}),
            ('terrain', OrderedDict([('refAlt', int(round(float(model['refAlt'])))), ('data', grids['terrain'])])),
            ('plants3D', [OrderedDict([('i', int(p['i'])), ('j', int(p['j'])), ('k', int(p.get('k', 0))),
                                       ('id', pad_id(p['id'])), ('name', str(p.get('name', ''))),
                                       ('obs', bool(p.get('obs', False)))]) for p in model['plants3d']]),
            ('receptors', [OrderedDict([('i', int(r['i'])), ('j', int(r['j'])), ('name', str(r['name']))])
                           for r in model['receptors']]),
            ('routes', []),
            ('buildingInfo', [_building_json(b) for b in model['buildings']]),
        ])),
        ('spatialData3D', OrderedDict((name, {'data': []}) for name in
                                      ('buildingNos', 'buildingFaces', 'greeningFaces', 'singleFaces', 'terrain'))),
    ])
    text = json.dumps({'envimetDatafile': data}, indent=2, ensure_ascii=False)
    # grids one row per line: SPACES' one value per line makes large models needlessly long
    for key, rows in placeholders.items():
        match = re.search(r'^( *)(.*)"%s"' % re.escape(key), text, re.M)
        indent = match.group(1) + '  '
        body = ',\n'.join(indent + '  ' + json.dumps(row, ensure_ascii=False, separators=(',', ':')) for row in rows)
        text = text.replace(f'"{key}"', '[\n' + body + '\n' + indent + ']' if rows else '[]', 1)
    return text


def _number(value):
    """A JSON number: an int when the value is whole, so 2.0 is written as 2 as SPACES does."""
    value = float(value)
    return int(value) if value.is_integer() else value


def _building_json(building):
    return OrderedDict([
        ('no', int(building['no'])), ('name', str(building.get('name', ''))),
        ('wall', pad_id(building.get('wall', ''))), ('roof', pad_id(building.get('roof', ''))),
        ('wallGreen', pad_id(building.get('wallGreen', ''))), ('roofGreen', pad_id(building.get('roofGreen', ''))),
        ('bps', bool(building.get('bps', False))),
        ('indoorMode', int(building.get('indoorMode', -1))),
        ('suppressACHeatRelease', bool(building.get('suppressACHeatRelease', False))),
        ('indoorLowerC', float(building.get('indoorLowerC', -99.0))),
        ('indoorUpperC', float(building.get('indoorUpperC', -99.0))),
        ('buildingUse', int(building.get('buildingUse', 0))),
        ('internalGainWm2', float(building.get('internalGainWm2', 8.0))),
    ])
