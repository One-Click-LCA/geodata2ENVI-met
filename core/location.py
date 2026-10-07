"""Time zone and elevation of a model location from GeoNames (no QGIS imports).

ENVI-met works in local *standard* time, so the time zone is GeoNames' rawOffset.
(gmtOffset is the offset on 1 January, which includes daylight saving time in the
southern hemisphere: Sydney is +11 there, +10 standard.)
"""

GEONAMES = 'https://secure.geonames.org'
USERNAME = 'envi_met'
TIMEOUT = 8

_cache = {}


def _get(service, lat, lon, requests_module=None):
    key = (service, round(lat, 4), round(lon, 4))
    if key in _cache:
        return _cache[key]
    if requests_module is None:
        import requests as requests_module
    response = requests_module.get(f'{GEONAMES}/{service}', params={'lat': lat, 'lng': lon, 'username': USERNAME},
                                   timeout=TIMEOUT)
    data = response.json() if response.status_code == 200 else None
    if data is not None and 'status' not in data:
        _cache[key] = data
    return data


def standard_time_offset(lat, lon, requests_module=None):
    """(hours east of UTC for standard time, None) or (estimate from the longitude, reason)."""
    try:
        data = _get('timezoneJSON', lat, lon, requests_module)
        if data is not None and 'status' not in data:
            if 'rawOffset' in data:
                return float(data['rawOffset']), None
            if 'gmtOffset' in data:
                return float(data['gmtOffset']), None
        reason = 'GeoNames gave no time zone'
    except Exception as error:      # offline, timeout, unexpected answer
        reason = f'GeoNames could not be reached ({type(error).__name__})'
    return float(round(lon / 15.0)), reason


def elevation(lat, lon, requests_module=None):
    """Ground elevation (m) from SRTM, or None (sea, no answer)."""
    try:
        data = _get('srtm1JSON', lat, lon, requests_module)
        if data is not None and 'srtm1' in data and int(data['srtm1']) >= 0:
            return int(data['srtm1'])
    except Exception:
        pass
    return None
