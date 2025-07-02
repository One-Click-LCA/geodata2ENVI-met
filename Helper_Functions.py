import datetime as dt
from .NetCDF import *
from qgis.core import QgsColorRampShader
from .Const_defines import *
from os import path


def calculate_datetime_netcdf(date_str: str, time_str: str, delimiter: str, time_stp: int, nc: NetCDF,
                              exclude_year: bool):
    # get separate values
    day, month, year = date_str.split(delimiter)
    hour, minute, second = time_str.split(delimiter)
    # convert values to integer
    year = int(year)
    month = int(month)
    day = int(day)
    hour = int(hour)
    minute = int(minute)
    # build a datetime-obj
    dt_var = dt.datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=0)
    # calculate timestep-time
    changed = dt.timedelta(hours=float(nc.time[time_stp]))
    new_dt = dt_var + changed
    # reconvert to a string
    date, time = new_dt.strftime('%Y-%m-%d %H:%M:%S').split(' ')
    # split to separate values
    year, month, day = date.split('-')
    hour, minute, second = time.split(':')
    # set together in the correct format
    if exclude_year:
        date = f'{day}.{month}'
    else:
        date = f'{day}.{month}.{year}'
    time = f'{hour}.{minute}.{second}'
    return date, time


def get_color_scale_interpolation():
    interpolation = 1
    if C_COLOR_SCALE_INTERPOLATION == 0:
        # Discrete
        interpolation = QgsColorRampShader.Discrete
    elif C_COLOR_SCALE_INTERPOLATION == 1:
        # Interpolated
        interpolation = QgsColorRampShader.Interpolated
    elif C_COLOR_SCALE_INTERPOLATION == 2:
        # Exact
        interpolation = QgsColorRampShader.Exact
    return interpolation


def get_color_scale_mode():
    mode = 0
    if C_COLOR_SCALE_MODE == 0:
        # Equal Interval
        mode = QgsColorRampShader.EqualInterval
    elif C_COLOR_SCALE_MODE == 1:
        # Continuous
        mode = QgsColorRampShader.Continous
    elif C_COLOR_SCALE_MODE == 2:
        # Quantile
        mode = QgsColorRampShader.Quantile
    return mode


def merge_filepath(folder: str, file: str):
    return path.normpath(path.join(folder, file))
