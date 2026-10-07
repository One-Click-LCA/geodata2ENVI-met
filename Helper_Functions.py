from qgis.core import QgsColorRampShader
from .Const_defines import C_COLOR_SCALE_INTERPOLATION, C_COLOR_SCALE_MODE


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
        mode = QgsColorRampShader.Continuous
    elif C_COLOR_SCALE_MODE == 2:
        # Quantile
        mode = QgsColorRampShader.Quantile
    return mode
