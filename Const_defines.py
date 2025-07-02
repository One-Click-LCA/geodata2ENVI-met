################################################################################
# This file defines constants which are used in other files of the project.    #
# Change the values here to update each relevant line of code to the new value #
################################################################################

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