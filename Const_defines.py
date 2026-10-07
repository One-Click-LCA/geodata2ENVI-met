################################################################################
# This file defines constants which are used in other files of the project.    #
# Change the values here to update each relevant line of code to the new value #
################################################################################

from qgis.core import Qgis

C_NODATA_VALUE = -999.0

C_COLOR_SCALE_STEPS = 20
C_COLOR_SCALE_NAME = 'Spectral'

# Interpolation: 0 = Discrete, 1 = Interpolated, 2 = Exact
C_COLOR_SCALE_INTERPOLATION = 1

# Mode: 0 = EqualInterval, 1 = Continous, 2 = Quantile
C_COLOR_SCALE_MODE = 0

C_COLOR_SCALE_INVERT = True
C_COLOR_SCALE_USE_CUSTOM = False
C_COLOR_SCALE_CUSTOM_PATH = ''

# Sampling: 1 (Bilinear (2x2 kernel)) and 3 (Cubic B-Spline (4x4 kernel)) work well
C_SAMPLING_METHOD = 1

C_TERRAIN_ID = 2

# Vector layer geometry types, matching QGIS' Qgis.GeometryType enum
# (Point = 0, Line = 1, Polygon = 2). Compared against QgsVectorLayer.geometryType().
C_VECTORLAYER_TYPE_POINT = 0
C_VECTORLAYER_TYPE_POLYGON = 2

# Aggregation method used by the data-series comparison plots.
C_METHOD_MEAN = 0
C_METHOD_MEDIAN = 1

# Plot appearance settings for the data-series comparison plots.
C_SERIES_A_COLOR = 'blue'
C_SERIES_B_COLOR = 'red'
C_DRAW_NEW_DAY_LINE = True
C_NEW_DAY_COLOR = 'grey'
C_PRINT_SOURCE = True
C_PRINT_SOURCE_FONTSIZE = 8

# Field-type constants for QgsField.
# QGIS >= 3.38 deprecated the QVariant.Type constructor of QgsField in favour of
# QMetaType.Type; earlier versions only accept QVariant.Type. Gate on the QGIS
# version so the non-deprecated form is used where available while staying
# compatible down to the minimum supported QGIS (see metadata.txt).
if Qgis.versionInt() >= 33800:
    from qgis.PyQt.QtCore import QMetaType as _QMetaType
    FIELD_TYPE_INT = _QMetaType.Type.Int
    FIELD_TYPE_STRING = _QMetaType.Type.QString
else:
    from qgis.PyQt.QtCore import QVariant as _QVariant
    FIELD_TYPE_INT = _QVariant.Type.Int
    FIELD_TYPE_STRING = _QVariant.Type.String
