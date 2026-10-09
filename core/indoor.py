"""Per-building indoor climate of ENVI-met 6 (the buildingInfo entries of the INX).

A building without a value takes the model-wide setting of the simulation (SIMX):
building use 0, indoor mode -1 and thresholds -99 mean "not stated". The internal
heat gain is only read for buildings of use 3 ("other").

Attribute values may be the user codes or common words ("office", "residential",
"AC", ...), as GIS layers often carry text. The user codes are the same for both
settings: -1 is "not stated", the options count from 1 (USER_CODES). They differ
from the INX codes (use 0..4, mode -1..3), which the parsers return. Each parser
returns (value, understood): ``understood`` is False for a value that was given
but could not be read, which then falls back to "not stated".

No QGIS imports.
"""

USE_NOT_STATED = 0
MODE_MODEL_DEFAULT = -1
THRESHOLD_NOT_STATED = -99.0
DEFAULT_INTERNAL_GAIN = 8.0

# Codes a user enters in an attribute field, in the order of the labels below
USER_CODES = (-1, 1, 2, 3, 4)
# user code -> INX code
_USE_INX = {-1: USE_NOT_STATED, 1: 1, 2: 2, 3: 3, 4: 4}
_MODE_INX = {-1: MODE_MODEL_DEFAULT, 1: 0, 2: 1, 3: 2, 4: 3}

# Combo box entries of the export page, in the order of USER_CODES
USE_LABELS = ['-1: Not stated (simulation setting)', '1: Residential (5 W/m2, 17:00-08:00)',
              '2: Office (15 W/m2, 08:00-17:00)', '3: Other (own internal heat gain)',
              '4: Hall / single storey (4 W/m2, one floor)']
MODE_LABELS = ['-1: Not stated (simulation setting)', '1: Free-running (no heating, no cooling)',
               '2: Heated, windows can be opened', '3: Mixed mode (windows first, cooling as backup)',
               '4: Fully conditioned (AC: sealed, heated and cooled)']

_USE_WORDS = {
    0: ('not stated', 'unknown', 'mixed', 'mixed use', 'default', 'none', 'unspecified'),
    1: ('residential', 'residence', 'dwelling', 'housing', 'house', 'home', 'apartment', 'apartments', 'flat',
        'flats', 'wohnen', 'wohngebaeude', 'wohngebäude'),
    2: ('office', 'offices', 'commercial', 'administration', 'workplace', 'school', 'buero', 'büro', 'verwaltung'),
    3: ('other', 'custom', 'own', 'own gain', 'internal gain'),
    4: ('hall', 'warehouse', 'industrial', 'industry', 'factory', 'church', 'sports hall', 'gym', 'storage',
        'single storey', 'single-storey', 'halle', 'lager'),
}
_MODE_WORDS = {
    -1: ('not stated', 'default', 'model default', 'simulation', 'unknown'),
    0: ('free', 'free-running', 'free running', 'free-floating', 'none', 'natural', 'unconditioned', 'off',
        'passive'),
    1: ('heated', 'heating', 'heat'),
    2: ('mixed', 'mixed mode', 'mixed-mode', 'hybrid'),
    3: ('ac', 'a/c', 'air conditioned', 'air-conditioned', 'conditioned', 'fully conditioned', 'cooled', 'cooling',
        'hvac', 'sealed', 'klima', 'klimatisiert'),
}


def _empty(value):
    return value is None or str(value).strip() in ('', 'NULL', 'None', 'nan')


def _word_lookup(value, words, inx_codes, default):
    if _empty(value):
        return default, True
    text = str(value).strip().lower()
    try:
        number = float(text)
    except ValueError:
        for code, names in words.items():
            if text in names:
                return code, True
        return default, False
    if number == int(number) and int(number) in inx_codes:
        return inx_codes[int(number)], True
    return default, False


def building_use(value):
    """INX building use code 0..4 from a user code (-1, 1..4) or a word."""
    return _word_lookup(value, _USE_WORDS, _USE_INX, USE_NOT_STATED)


def indoor_mode(value):
    """INX indoor mode code -1..3 from a user code (-1, 1..4) or a word."""
    return _word_lookup(value, _MODE_WORDS, _MODE_INX, MODE_MODEL_DEFAULT)


def _number(value, default, low, high, unset=None):
    if _empty(value):
        return default, True
    try:
        number = float(str(value).strip().replace(',', '.'))
    except ValueError:
        return default, False
    if unset is not None and number == unset:
        return default, True
    if not low <= number <= high:
        return default, False
    return number, True


def threshold(value):
    """An indoor temperature threshold in degrees Celsius; empty or -99 is "not stated"."""
    return _number(value, THRESHOLD_NOT_STATED, -50.0, 60.0, unset=THRESHOLD_NOT_STATED)


def internal_gain(value):
    """Internal heat gain in W per m2 of floor area (read by ENVI-met for use 3 only)."""
    return _number(value, DEFAULT_INTERNAL_GAIN, 0.0, 1000.0)


PARSERS = {'use': building_use, 'mode': indoor_mode, 'lower': threshold, 'upper': threshold, 'gain': internal_gain}

# setting -> key of a building in the model area (core.inx)
KEYS = (('use', 'buildingUse'), ('mode', 'indoorMode'), ('lower', 'indoorLowerC'), ('upper', 'indoorUpperC'),
        ('gain', 'internalGainWm2'))


def building_values(settings, suppress_ac_heat=False):
    """One building's indoor climate as INX values. ``settings`` maps use/mode/lower/upper/gain to values."""
    values = {}
    for key, name in KEYS:
        value = PARSERS[key](settings.get(key))[0]
        values[name] = int(value) if key in ('use', 'mode') else round(float(value), 2)
    values['suppressACHeatRelease'] = bool(suppress_ac_heat)
    return values
