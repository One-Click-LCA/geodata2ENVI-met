import numpy as np
from .Const_defines import *

try:
    import netCDF4
except ImportError:
    # first we try to install netCDF4 from online source
    from qgis.PyQt.QtWidgets import QMessageBox
    QMessageBox.warning(None, 'Missing Library for Geodata2ENVI-met plugin',
                        "The Python library 'netCDF4' is required. It will now be installed. Please restart QGIS before using the plugin.", QMessageBox.Ok, QMessageBox.Ok) 
    import os
    if os.system("pip install netCDF4") == 0:
          
        #QMessageBox.information(None, 'netCDF library for Geodata2ENVI-met plugin installed', "Please restart QGIS before using the plugin.", QMessageBox.Ok, QMessageBox.Ok) 
        """        
        # if that failed, we try our best with a local whl file
        import sys
        this_dir = os.path.dirname(os.path.realpath(__file__, strict=True))
        path = ''
        if sys.platform == 'win32':
            # Windows
            path = os.path.normpath(this_dir + '/src/NetCDF4/netCDF4-1.7.2-cp313-cp313-win_amd64.whl')
        elif sys.platform == "darwin":
            # MacOS
            path = os.path.normpath(this_dir + '/src/NetCDF4/netCDF4-1.7.2-cp313-cp313-macosx_14_0_arm64.whl')
        elif sys.platform == "linux" or sys.platform == "linux2":
            # Linux
            path = os.path.normpath(this_dir + '/src/NetCDF4/netCDF4-1.7.2-cp313-cp313-manylinux_2_17_aarch64.manylinux2014_aarch64.whl')
                                                                                                                          
        if not (path in sys.path):
            sys.path.append(path)
        """
    else:
        QMessageBox.warning(None, 'Missing Library for Geodata2ENVI-met plugin',
                            "The Python library 'netCDF4' is required. It should be installed automatically when you install the plugin while being online.", QMessageBox.Ok, QMessageBox.Ok)
class NetCDF_Variable_Metadata:
    def __init__(self):
        self.name = ''
        self.dimensions = ()
        self.unit = ''
        self.shape = ()


class NetCDF:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.file = netCDF4.Dataset(filename=filepath, mode='r', format='NETCDF4')
        self.file.set_auto_mask(False)

        self.dem_offset_untransposed = self.get_DEM()
        self.dem_offset = np.transpose(self.dem_offset_untransposed)

        self.time = self.file.variables["Time"]
        self.time = np.array(self.time[:])
        self.time = np.around(self.time, 2)

        self.gridsK = self.file.variables["GridsK"]
        self.loc_z = np.array(self.gridsK)

        self.model_rotation = self.file.getncattr('ModelRotation')
        self.UTM_zone = self.file.getncattr('UTMZone')
        self.georef_x = self.file.getncattr('GeorefX')
        self.georef_y = self.file.getncattr('GeorefY')
        self.georef_lat = self.file.getncattr('LocationLatitude')
        self.sim_date = self.file.getncattr('SimulationDate')
        self.sim_time = self.file.getncattr('SimulationTime')
        self.size_x = self.file.getncattr("SizeDX")
        self.size_y = self.file.getncattr("SizeDY")

        self.var_metadata = {}
        self.load_all_var_metadata()

    def get_DEM(self):
        if 'DEMOffset' in self.file.variables.keys():
            dem_offset_untransposed = self.file.variables["DEMOffset"]
            dem_offset_untransposed = np.array(dem_offset_untransposed[0, :, :])
        elif 'Objects' in self.file.variables.keys():
            objects = self.file.variables['Objects']
            objects = np.array(objects[0, :, :, :])
            dem_offset_untransposed = np.zeros([objects.shape[1], objects.shape[2]], dtype=int)
            for i in range(objects.shape[2]):
                for j in range(objects.shape[1]):
                    for k in range(objects.shape[0]):
                        if objects[k, j, i] != C_TERRAIN_ID:
                            dem_offset_untransposed[j, i] = k
                            break

        elif ('GridsI' in self.file.dimensions) and ('GridsJ' in self.file.dimensions):
            gridsI = self.file.dimensions['GridsI'].size
            gridsJ = self.file.dimensions['GridsJ'].size
            dem_offset_untransposed = np.zeros([gridsJ, gridsI], dtype=int)
        else:
            dem_offset_untransposed = np.zeros([0, 0], dtype=int)
        return dem_offset_untransposed

    def get_var_metadata(self, key: str):
        return self.var_metadata.get(key)

    def get_var_info(self, varName: str):
        if varName in self.file.variables:
            return self.file.variables[varName]
        else:
            return None

    def load_all_var_metadata(self):
        for name in self.file.variables.keys():
            data = self.file.variables[name]
            meta = NetCDF_Variable_Metadata()

            meta.name = name

            if hasattr(data, 'units'):
                meta.unit = data.units
            if hasattr(data, 'shape'):
                meta.shape = data.shape
            if hasattr(data, 'dimensions'):
                meta.dimensions = data.dimensions

            if hasattr(data, 'long_name'):
                self.var_metadata[data.long_name] = meta
            elif hasattr(data, 'name'):
                self.var_metadata[data.name] = meta
            else:
                self.var_metadata[name] = meta

    def get_data(self, varName: str, z_lvl: int = 0, time_stp: int = 0):
        if varName in self.file.variables:
            data = self.get_var_info(varName)
            if data is not None:
                z = max(0, z_lvl)
                t = max(0, time_stp)

                if 'GridsK' in data.dimensions:
                    z_max = data.shape[data.dimensions.index('GridsK')] - 1
                elif 'SoilLevels' in data.dimensions:
                    z_max = data.shape[data.dimensions.index('SoilLevels')] - 1
                else:
                    z_max = 0

                if 'Time' in data.dimensions:
                    time_max = data.shape[data.dimensions.index('Time')] - 1
                else:
                    time_max = 0

                z = min(z, z_max)
                t = min(t, time_max)

                added_dem_array = self.dem_offset_untransposed + z
                added_dem_array[added_dem_array > z_max] = z_max

                if (len(data.shape) == 4) and ('Time' in data.dimensions) and ('GridsK' in data.dimensions):
                    data_array = data[t, :, :, :][:]
                    data_array = self.consider_dem(arr=data_array, dem=added_dem_array)
                    return np.transpose(data_array)
                    # return data[time, 2, :, :][:]
                elif (len(data.shape) == 4) and ('Time' in data.dimensions) and ('SoilLevels' in data.dimensions):
                    data_array = data[t, z, :, :][:]
                    return np.transpose(data_array)
                elif (len(data.shape) == 3) and ('GridsK' in data.dimensions):
                    data_array = data[:, :, :][:]
                    data_array = self.consider_dem(arr=data_array, dem=added_dem_array)
                    return np.transpose(data_array)
                elif (len(data.shape) == 3) and ('SoilLevels' in data.dimensions):
                    data_array = data[z, :, :][:]
                    return np.transpose(data_array)
                elif (len(data.shape) == 3) and ('Time' in data.dimensions):
                    data_array = data[t, :, :][:]
                    return np.transpose(data_array)
                elif len(data.shape) == 2:
                    return np.transpose(np.array(data))

        # fallback return None
        return None

    @staticmethod
    def consider_dem(arr, dem):
        # if the dem-array is not empty
        if not (dem.shape[0] == 0):
            # arr is a 3d-array, dem a 2d-array
            res_array = np.zeros((arr.shape[1], arr.shape[2]))
            for j in range(res_array.shape[0]):
                for i in range(res_array.shape[1]):
                    res_array[j, i] = arr[dem[j, i], j, i]
            return res_array[:]
        else:
            # this else-branch only executes if the variable DEMOffset is not present in the nc-file AND if the dimensions GridsI and GridsJ do not exist
            # in the nc-file. In that case, the DEM-array is initiated as np.zeros([0, 0])
            return arr[0, :, :][:]
