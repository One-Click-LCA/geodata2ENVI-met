"""ENVI-met simulation files (.SIMX): read JSON or XML, write JSON or XML.

A simulation is a dict of sections, each a dict of key -> value, as in ENVI-met's
JSON format: ``{'mainData': {'simName': ..., ...}, 'SimpleForcing': {'TAir': [...]}, ...}``.
Sections and keys the plugin does not know are kept as they were read, so loading
and saving a file does not lose settings the plugin does not show.

ENVI-met reads JSON SIMX files since 5.9 and writes them since 5.9.5; older
versions read the XML format only. JSON values must have the types ENVI-met's
writer uses (booleans as true/false), because its reader converts by type.

No QGIS imports.
"""

import json
import re
from collections import OrderedDict

JSON_SINCE = (5, 9, 0)

BOOL = 'bool'
INT = 'int'
FLOAT = 'float'
STR = 'str'
FLOATS = 'floats'

# Value types of the keys ENVI-met reads and writes (from its SIMX reader and writer).
TYPES = {
    'mainData': {'simName': STR, 'INXFile': STR, 'filebaseName': STR, 'outDir': STR, 'startDate': STR,
                 'startTime': STR, 'simDuration': INT, 'windSpeed': FLOAT, 'windDir': FLOAT, 'z0': FLOAT,
                 'T_H': FLOAT, 'Q_H': FLOAT, 'Q_2m': FLOAT, 'windLimit': FLOAT, 'useCoriolis': INT,
                 'fetchSurfaceMode': INT, 'SurroundingAreaRadiation': BOOL, 'windAccuracy': INT},
    'FailSafes': {'useFailSafes': BOOL, 'TaLimit_diff': FLOAT, 'TsurfLimit_diff': FLOAT,
                  'CO2LimitLower_diff': FLOAT, 'CO2LimitUpper_diff': FLOAT},
    'TThread': {'UseTThread_CallMain': BOOL, 'TThreadPRIO': INT},
    'ModelTiming': {'surfaceSteps': INT, 'flowSteps': INT, 'radiationSteps': INT, 'plantSteps': INT,
                    'sourcesSteps': INT},
    'Soil': {'waterUpperlayer': FLOAT, 'waterMiddlelayer': FLOAT, 'waterDeeplayer': FLOAT,
             'waterBedrockLayer': FLOAT, 'tempUpperlayer': FLOAT, 'tempMiddlelayer': FLOAT,
             'tempDeeplayer': FLOAT, 'tempBedrockLayer': FLOAT},
    'indoorSettings': {'naturalVentilation': INT, 'defaultBuildingUse': INT, 'indoorMode': INT,
                       'indoorLowerC': FLOAT, 'indoorUpperC': FLOAT},
    'Building': {'surfaceTemp': FLOAT, 'indoorTemp': FLOAT, 'indoorConst': BOOL, 'airConHeat': BOOL},
    'Sources': {'userPolluName': STR, 'userPolluType': INT, 'userPartDiameter': FLOAT, 'userPartDensity': FLOAT,
                'multipleSources': BOOL, 'activeChem': BOOL, 'isoprene': BOOL},
    'LBC': {'LBC_TQ': INT, 'LBC_TKE': INT},
    'SimpleForcing': {'TAir': FLOATS, 'Qrel': FLOATS},
    'FullForcing': {'fileName': STR, 'forceT': BOOL, 'forceQ': BOOL, 'forceWind': BOOL, 'forcePrecip': BOOL,
                    'forceRadClouds': BOOL, 'forceBackgrConc': BOOL, 'interpolationMethod': INT, 'nudging': BOOL,
                    'nudgingFactor': FLOAT, 'minFlowsteps': INT, 'limitWind2500': BOOL, 'maxWind2500': FLOAT,
                    'z_0': FLOAT},
    'TimeSteps': {'sunheight_step01': FLOAT, 'sunheight_step02': FLOAT, 'dt_step00': FLOAT, 'dt_step01': FLOAT,
                  'dt_step02': FLOAT},
    'OutputSettings': {'mainFiles': INT, 'textFiles': INT, 'netCDF': BOOL, 'emailNotification': BOOL,
                       'inclNestingGrids': BOOL, 'writeAgents': BOOL, 'writeAtmosphere': BOOL,
                       'writeBuildings': BOOL, 'writeObjects': BOOL, 'writeGreenpass': BOOL, 'writeNesting': BOOL,
                       'writePollutants': BOOL, 'writeRadiation': BOOL, 'writeSoil': BOOL,
                       'writeSolarAccess': BOOL, 'writeSurface': BOOL, 'writeVegetation': BOOL,
                       'writeWindSectors': BOOL, 'netCDFAllDataInOneFile': BOOL, 'netCDFWriteOnlySmallFile': BOOL},
    'Clouds': {'lowClouds': FLOAT, 'middleClouds': FLOAT, 'highClouds': FLOAT},
    'Background': {'userSpec': FLOAT, 'NO': FLOAT, 'NO2': FLOAT, 'O3': FLOAT, 'PM_10': FLOAT, 'PM_2_5': FLOAT},
    'SolarAdjust': {'SWFactor': FLOAT},
    'spinUp': {'warmStart': BOOL},
    'PhotoCat': {'usePhotocat': BOOL, 'photocatMaterial': INT},
    'RadScheme': {'IVSHeightAngle_HiRes': INT, 'IVSAziAngle_HiRes': INT, 'IVSHeightAngle_LoRes': INT,
                  'IVSAziAngle_LoRes': INT, 'AdvCanopyRadTransfer': BOOL, 'ViewFacUpdateInterval': INT,
                  'RayTraceStepWidthHighRes': FLOAT, 'RayTraceStepWidthLowRes': FLOAT,
                  'RadiationHeightBoundary': FLOAT, 'MRTCalcMethod': INT, 'MRTProjFac': INT},
    'Parallel': {'CPUDemand': STR},
    'GreenCityTree': {'fileName': STR},
    'CoolingDevice': {'fileName': STR},
    'PlantModel': {'CO2BackgroundPPM': FLOAT, 'LeafTransmittance': BOOL, 'TreeCalendar': BOOL},
    'Turbulence': {'turbulenceModel': INT, 'TKELimit': BOOL},
    'SOR': {'SORMode': INT},
    'InflowAvg': {'inflowAvg': BOOL},
    'Facades': {'FacadeMode': INT},
}

# Section order of ENVI-met's JSON writer; other sections follow in the order they were read.
JSON_ORDER = ['mainData', 'SimModule', 'FailSafes', 'TThread', 'ModelTiming', 'Soil', 'indoorSettings', 'Sources',
              'LBC', 'SimpleForcing', 'FullForcing', 'TimeSteps', 'OutputSettings', 'Clouds', 'Background',
              'SolarAdjust', 'spinUp', 'PhotoCat', 'RadScheme', 'Parallel', 'GreenCityTree', 'CoolingDevice',
              'PlantModel']

# Sections and keys ENVI-met 6 no longer reads (the plugin's pages do not set them any more).
RETIRED_V6 = {
    'sections': {'Building', 'Turbulence', 'SOR', 'Facades', 'InflowAvg', 'Nesting'},
    'keys': {'mainData': {'Q_H'}, 'Soil': {'tempUpperlayer', 'tempMiddlelayer', 'tempDeeplayer', 'tempBedrockLayer'},
             'FullForcing': {'nudging', 'nudgingFactor'},
             'OutputSettings': {'netCDFAllDataInOneFile', 'netCDFWriteOnlySmallFile'}},
}


class SimxError(Exception):
    pass


def uses_json(version):
    """True if the ENVI-met version (major, minor, patch) reads JSON SIMX files; unknown versions do."""
    return version is None or tuple(version) >= JSON_SINCE


def _canonical_key(section, key):
    """The key's spelling in TYPES (ENVI-guide writes CPUDemand, older plugins CPUdemand)."""
    for known in TYPES.get(section, {}):
        if known.lower() == key.lower():
            return known
    return key


def _convert(value, kind):
    if kind is None:
        return value
    if kind == FLOATS:
        if isinstance(value, (list, tuple)):
            return [float(v) for v in value]
        return [float(v) for v in str(value).split(',') if v.strip()]
    if kind == BOOL:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value).strip().lower() in ('1', 'true', 'yes')
    if kind == INT:
        return int(round(float(value))) if not isinstance(value, bool) else int(value)
    if kind == FLOAT:
        return float(value)
    return str(value).strip() if not isinstance(value, str) else value.strip()


def _typed(section, key, value):
    key = _canonical_key(section, key)
    try:
        return key, _convert(value, TYPES.get(section, {}).get(key))
    except (TypeError, ValueError):
        return key, value


def read(path):
    """Read a SIMX file in either format. Returns (simulation dict, 'json' or 'xml')."""
    with open(path, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8-sig', errors='replace') if raw[:3] == b'\xef\xbb\xbf' else raw.decode('utf-8', errors='replace')
    stripped = text.lstrip()
    if stripped.startswith('{'):
        try:
            data = json.loads(stripped, object_pairs_hook=OrderedDict)
        except ValueError as error:
            raise SimxError(f'Not a valid JSON SIMX file: {error}')
        simulation = OrderedDict()
        for section, values in data.items():
            if isinstance(values, dict) and section in TYPES:
                simulation[section] = OrderedDict(_typed(section, k, v) for k, v in values.items())
            else:
                simulation[section] = values
        return simulation, 'json'
    if '<ENVI-MET_Datafile>' in stripped[:200]:
        return _read_xml(text), 'xml'
    raise SimxError('Not an ENVI-met SIMX file.')


def _read_xml(text):
    body = text.split('<ENVI-MET_Datafile>', 1)[1].rsplit('</ENVI-MET_Datafile>', 1)[0]
    simulation = OrderedDict()
    for match in re.finditer(r'<([A-Za-z_][\w]*)>(.*?)</\1>', body, re.DOTALL):
        section, content = match.group(1), match.group(2)
        values = OrderedDict()
        for item in re.finditer(r'<([A-Za-z_][\w]*)>([^<]*)</\1>', content):
            key, value = _typed(section, item.group(1), item.group(2).strip())
            values[key] = value
        if values or section in TYPES:
            simulation[section] = values
    return simulation


def _json_value(section, key, value):
    kind = TYPES.get(section, {}).get(key)
    if kind == BOOL:
        return bool(value)
    if kind == INT:
        return int(value)
    if kind == FLOAT:
        return float(value)
    if kind == FLOATS:
        return [float(v) for v in value]
    return value


def ordered_sections(simulation):
    names = [s for s in JSON_ORDER if s in simulation]
    names += [s for s in simulation if s not in names and s != 'Header']
    return names


def write_json(path, simulation, remark=''):
    header = OrderedDict(simulation.get('Header', {}))
    header.update(filetype='simConfJSON', version=1)
    header.setdefault('remark', remark)
    header.setdefault('fileInfo', '')
    data = OrderedDict([('Header', header)])
    for section in ordered_sections(simulation):
        values = simulation[section]
        if isinstance(values, dict):
            data[section] = OrderedDict((k, _json_value(section, k, v)) for k, v in values.items())
        else:
            data[section] = values
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def _xml_value(section, key, value):
    kind = TYPES.get(section, {}).get(key)
    if kind == BOOL or isinstance(value, bool):
        return '1' if value else '0'
    if kind == FLOATS or isinstance(value, (list, tuple)):
        return ','.join(f'{float(v):.5f}' for v in value)
    return str(value)


def write_xml(path, simulation, revision_date=''):
    """The XML format of ENVI-met up to 5.8 (sections the JSON format nests are left out)."""
    lines = ['<ENVI-MET_Datafile>', '<Header>', '<filetype>SIMX</filetype>', '<version>2</version>',
             f'<revisiondate>{revision_date}</revisiondate>', '<remark></remark>', '<checksum>0</checksum>',
             '<encryptionlevel>0</encryptionlevel>', '</Header>']
    for section in ordered_sections(simulation):
        values = simulation[section]
        if not isinstance(values, dict) or any(isinstance(v, dict) for v in values.values()):
            continue
        lines.append(f'  <{section}>')
        for key, value in values.items():
            lines.append(f'     <{key}> {_xml_value(section, key, value)} </{key}>')
        lines.append(f'  </{section}>')
    lines.append('</ENVI-MET_Datafile>')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path
