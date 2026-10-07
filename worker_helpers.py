"""Stateless helper functions extracted from Worker.

These functions do not depend on any Worker instance state, so they live here to
keep Worker.py smaller and to make them reusable and independently testable.
"""
from math import floor, trunc


def get_UTM_zone(lon, lat):
    zoneNum = trunc((floor(lon + 180) / 6) + 1)
    zoneHemi = "N"
    if lat >= 0:
        zoneHemi = "N"
    else:
        zoneHemi = "S"
    res = str(zoneNum) + ' ' + zoneHemi
    return res
