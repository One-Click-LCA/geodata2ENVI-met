"""Stateless helper functions extracted from Worker.

These functions do not depend on any Worker instance state, so they live here to
keep Worker.py smaller and to make them reusable and independently testable.
"""
from math import floor, trunc

import pyproj
from qgis.core import QgsCoordinateReferenceSystem


def get_UTM_zone(lon, lat):
    zoneNum = trunc((floor(lon + 180) / 6) + 1)
    zoneHemi = "N"
    if lat >= 0:
        zoneHemi = "N"
    else:
        zoneHemi = "S"
    res = str(zoneNum) + ' ' + zoneHemi
    return res


def getQGIS_crs(tstp):
    if tstp.location_georef_lat >= 0:
        crs = pyproj.CRS.from_string(f'+proj=utm +zone={tstp.location_georef_xy_utmzone} +north')
    else:
        crs = pyproj.CRS.from_string(f'+proj=utm +zone={tstp.location_georef_xy_utmzone} +south')
    qgs_crs = QgsCoordinateReferenceSystem(f'EPSG:{crs.to_authority()[1]}')
    return crs, qgs_crs
