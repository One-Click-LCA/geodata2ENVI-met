"""Display units for the CF/UDUNITS unit strings in ENVI-met's NetCDF output."""

_DISPLAY = {
    'degree_celsius': '°C',
    'degree celsius': '°C',
    'degc': '°C',
    'k': 'K',
    'k h-1': 'K/h',
    'k/h': 'K/h',
    'm s-1': 'm/s',
    'm/s': 'm/s',
    'm2 s-1': 'm²/s',
    'm2 s-2': 'm²/s²',
    'm2 s-3': 'm²/s³',
    'm2 m-3': 'm²/m³',
    'w m-2': 'W/m²',
    'g kg-1': 'g/kg',
    'g m-2': 'g/m²',
    'mg m-3': 'mg/m³',
    'ug m-3': 'µg/m³',
    'mg m-2 s-1': 'mg/(m²·s)',
    's m-1': 's/m',
    'percent': '%',
    '%': '%',
    'degree': '°',
    'degrees': '°',
    'pa': 'Pa',
    'ppm': 'ppm',
    '1': '',
}


def display_unit(unit):
    """'degree_Celsius' -> '°C', 'W m-2' -> 'W/m²'; unknown strings are returned unchanged."""
    if not unit:
        return ''
    return _DISPLAY.get(unit.strip().lower(), unit.strip())
