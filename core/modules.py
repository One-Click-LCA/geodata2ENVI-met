"""ENVI-met 6 simulation modules: the SimModule section of a SIMX file.

A SIMX without SimModule (or with the name FULLCLIMATE) is a full holistic
simulation. A module run reads mainData and ``SimModule = {"name": ...,
"ModuleData": {...}}``; it ignores the forcing and the optional sections, so
the plugin leaves them out, as ENVI-guide does.

The plugin offers the five modules ENVI-guide 6 offers. The values written
for settings ENVI-guide does not show are the ones it writes for a new file;
ENVI-met's reader would use different defaults for missing keys, so every
key is always written.

ENVI-met opens a module's FOX file by the name in ``forcingFile``. ENVI-guide
copies the FOX next to the SIMX and writes the bare file name; the plugin does
the same.

No QGIS imports.
"""

import datetime
import os
import re

HOLISTIC = 'FULLCLIMATE'
SOLAR_ACCESS = 'SOLARACCESS'
WIND_FLOW = 'WINDFLOW'
WIND_COMFORT = 'WINDCOMFORT'
FAST_UTCI = 'FASTTHERMALCOMFORT'
FAST_UTCI_STATS = 'FASTTHERMALCOMFORTSTATS'

# The simulation types of the plugin, in the order of its combo box
CHOICES = [
    (HOLISTIC, 'Full holistic simulation'),
    (SOLAR_ACCESS, 'Module: solar access and shadows'),
    (WIND_FLOW, 'Module: wind flow, one inflow direction'),
    (WIND_COMFORT, 'Module: wind climate (wind comfort over a year)'),
    (FAST_UTCI, 'Module: fast thermal comfort (UTCI)'),
    (FAST_UTCI_STATS, 'Module: fast thermal comfort statistics'),
]
CODES = [code for code, _ in CHOICES]

MIN_VERSION = (6, 0, 0)

FOX_MODULES = (WIND_COMFORT, FAST_UTCI, FAST_UTCI_STATS)
_FOX_SUFFIX = {WIND_COMFORT: '_WindClimate.fox', FAST_UTCI: '_FastUTCI.fox', FAST_UTCI_STATS: '_UTCIStats.fox'}

# Settings ENVI-guide does not show, with the values it writes for a new file
HIDDEN_DEFAULTS = {
    WIND_FLOW: {'highPrecision': True},
    WIND_COMFORT: {'baseWindSpd': 10.0, 'sectorCnt': 16},
    FAST_UTCI: {'baseWindSpd': 10.0, 'sectorCnt': 8},
    FAST_UTCI_STATS: {'baseWindSpd': 10.0, 'sectorCnt': 8},
}

# Sections a module run does not read
UNUSED_SECTIONS = ('SimpleForcing', 'FullForcing', 'LBC', 'Clouds', 'Soil', 'indoorSettings', 'Building', 'Sources',
                   'Background', 'RadScheme', 'SolarAdjust', 'OutputSettings', 'TThread')

_DATE = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')


def module_name(simulation):
    """The simulation's module code; HOLISTIC when there is none."""
    section = simulation.get('SimModule')
    if not isinstance(section, dict):
        return HOLISTIC
    name = str(section.get('name', HOLISTIC) or HOLISTIC).strip().upper()
    return name


def module_data(simulation):
    section = simulation.get('SimModule')
    data = section.get('ModuleData') if isinstance(section, dict) else None
    return data if isinstance(data, dict) else {}


def build_section(code, values, loaded=None):
    """SimModule for ``code`` from the shown ``values``.

    ``loaded`` is the SimModule of a loaded file: for the same module, its settings the plugin
    does not show are kept.
    """
    data = {'outputFolder': ''}
    data.update(HIDDEN_DEFAULTS.get(code, {}))
    if isinstance(loaded, dict) and str(loaded.get('name', '')).upper() == code:
        kept = loaded.get('ModuleData')
        if isinstance(kept, dict):
            data.update(kept)
            # the wind-flow remark names where the wind values came from; it is wrong once they change
            if code == WIND_FLOW and (kept.get('windSpeed') != values.get('windSpeed')
                                      or kept.get('windDir') != values.get('windDir')):
                data.pop('inflowSource', None)
    data.update(values)
    return {'name': code, 'ModuleData': data}


# ------------------------------------------------------------------------------------------------ solar access

def solar_dates(text):
    """The dates of ``solarAccessDates`` ('dd.mm.yyyy,dd.mm.yyyy'), without empty entries."""
    return [d.strip() for d in str(text or '').split(',') if d.strip()]


def valid_date(text):
    if not _DATE.match(text):
        return False
    day, month, year = (int(p) for p in text.split('.'))
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def solstices_and_equinoxes(year):
    return [f'21.03.{year}', f'21.06.{year}', f'23.09.{year}', f'21.12.{year}']


# ------------------------------------------------------------------------------------------------ FOX files

def fox_file_name(simx_path, code):
    """Name of the module's FOX copy next to the SIMX, as ENVI-guide names it."""
    base = os.path.basename(simx_path).split('.', 1)[0]
    return base + _FOX_SUFFIX[code]


def problems(code, values):
    """What keeps a module from running, as sentences (empty when it can run)."""
    found = []
    if code == SOLAR_ACCESS:
        dates = solar_dates(values.get('solarAccessDates'))
        if not dates:
            found.append('Add at least one date for the solar access module.')
        found += [f'"{d}" is not a date (dd.mm.yyyy).' for d in dates if not valid_date(d)]
    if code in FOX_MODULES:
        fox = values.get('forcingFile', '')
        if not fox:
            found.append('Select the FOX file with the meteorological data for the module.')
        elif not os.path.isfile(fox):
            found.append(f'The FOX file {fox} does not exist.')
    if code == FAST_UTCI_STATS:
        # ENVI-met's statistics do not wrap around the end of the year or the day
        if values.get('startMonth', 1) > values.get('endMonth', 12):
            found.append('The start month must not be after the end month.')
        if values.get('startHour', 0) > values.get('endHour', 23):
            found.append('The start hour must not be after the end hour.')
    return found
