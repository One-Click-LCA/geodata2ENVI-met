import numpy as np
import time


class EDX:
    def __init__(self, filepath: str):
        """
        :param filepath: filepath to the edx-file
        :param visual_mode: if visual-mode is true, only the first 3 arrays in the corresponding EDT-file are loaded
        These are relevant to display the model area in Blender. This safes computing-time
        """
        self.edx_file = filepath

        # init definitions from Info-Website
        self.data_type_dict = {0: "ftUnknown", 1: "ft2DRaster", 2: "ft3DRaster", 3: "ft3DFacade"}
        self.data_content_dict = {0: "fcUnknown", 1: "fcAtmosphere", 2: "fcSurface", 3: "fcSoil",
                                  4: "fcPollutants", 5: "fcBiomet", 6: "fcVegetation", 7: "fcFacade",
                                  8: "fcSolarAccess", 9: "fcFacadeStatic", 10: "fcFacadeSolarAccess",
                                  11: "fcRadiation", 12: "fcViewScape", 13: "fcPhotocat"}
        self.data_health_status_dict = {0: "fsNormal", 1: "fsCheck", 2: "fsInitialisation", 3: "fsPanicDump"}

        # init edx-variables
        self.data_type = -1
        self.data_content = -1
        self.data_zorientation = -1
        self.data_health_status = -1
        self.data_spatial_dim = -1
        self.nr_xdata = -1
        self.nr_ydata = -1
        self.nr_zdata = -1
        self.spacing_x = []
        self.spacing_y = []
        self.spacing_z = []
        self.data_per_variable = -1
        self.nr_variables = -1
        self.name_variables = []
        self.title = ""
        self.simulation_basename = ""
        self.simulation_date = ""
        self.simulation_time = ""
        self.projectname = ""
        self.locationname = ""
        self.model_rotation = 0.0
        self.location_georef_lat = 0.0
        self.location_georef_lon = 0.0
        self.location_georef_xy_utmzone = 0
        self.location_georef_x = 0.0
        self.location_georef_y = 0.0
        self.enviMet_version = ""
        self.enviMet__GUID = ""
        self.licenseholder = ""
        self.sunposition = 0.0
        self.windinflow = 0.0

        # load data from edx-file
        self.load_metadata()

    def load_metadata(self):
        file = open(self.edx_file, 'br')
        for row in file:
            row = row.decode('cp1252')
            if "<data_type>" in row:
                self.data_type = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<data_content>" in row:
                self.data_content = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<data_zorientation>" in row:
                self.data_zorientation = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<data_health_status>" in row:
                self.data_health_status = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<data_spatial_dim>" in row:
                self.data_spatial_dim = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<nr_xdata>" in row:
                self.nr_xdata = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<nr_ydata>" in row:
                self.nr_ydata = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<nr_zdata>" in row:
                self.nr_zdata = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<spacing_x>" in row:
                self.spacing_x = [float(i) for i in row.split(">", 1)[1].split("<", 1)[0].strip().split(",")]
            if "<spacing_y>" in row:
                self.spacing_y = [float(i) for i in row.split(">", 1)[1].split("<", 1)[0].strip().split(",")]
            if "<spacing_z>" in row:
                self.spacing_z = [float(i) for i in row.split(">", 1)[1].split("<", 1)[0].strip().split(",")]
            if "<Data_per_variable>" in row:
                self.data_per_variable = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<nr_variables>" in row:
                self.nr_variables = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<name_variables>" in row:
                self.name_variables = row.split(">", 1)[1].split("<", 1)[0].split(",")
            if "<title>" in row:
                self.title = row.split(">", 1)[1].split("<", 1)[0]
            if "<simulation_basename>" in row:
                self.simulation_basename = row.split(">", 1)[1].split("<", 1)[0]
            if "<simulation_date>" in row:
                self.simulation_date = row.split(">", 1)[1].split("<", 1)[0]
            if "<simulation_time>" in row:
                self.simulation_time = row.split(">", 1)[1].split("<", 1)[0]
            if "<projectname>" in row:
                self.projectname = row.split(">", 1)[1].split("<", 1)[0]
            if "<locationname>" in row:
                self.locationname = row.split(">", 1)[1].split("<", 1)[0]
            if "<model_rotation>" in row:
                self.model_rotation = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<location_georef_lat>" in row:
                self.location_georef_lat = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<location_georef_lon>" in row:
                self.location_georef_lon = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<location_georef_xy_utmzone>" in row:
                self.location_georef_xy_utmzone = int(row.split(">", 1)[1].split("<", 1)[0])
            if "<location_georef_x>" in row:
                self.location_georef_x = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<location_georef_y>" in row:
                self.location_georef_y = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<envi-met_version>" in row:
                self.enviMet_version = row.split(">", 1)[1].split("<", 1)[0]
            if "<envi-met_GUID>" in row:
                self.enviMet__GUID = row.split(">", 1)[1].split("<", 1)[0]
            if "<licenseholder>" in row:
                self.licenseholder = row.split(">", 1)[1].split("<", 1)[0]
            if "<sunposition>" in row:
                self.sunposition = float(row.split(">", 1)[1].split("<", 1)[0])
            if "<windinflow>" in row:
                self.windinflow = float(row.split(">", 1)[1].split("<", 1)[0])
        file.close()


class EDT:
    """
    Description: parses the EDT-file. Structure of binary EDT-file is known from here:
    https://envi-met.info/doku.php?id=filereference:edx_edi
    """
    def __init__(self, filepath: str, edx: EDX, var_name: str = '', z: int = -1):
        self.associated_edx = edx
        self.demID = 2
        # default settings -> load whole EDT-file
        if (var_name == '') and (z == -1):
            self.edt_file = np.fromfile(filepath, dtype=np.float32)
            self.data_dict = {}
            self.init_data_dict()
        else:
            # load specific layer from specific variable -> much faster
            self.var_name = var_name
            self.z = z
            self.terrain_follow = self.check_for_terrain(filepath)
            if self.terrain_follow:
                offset = self.calc_offset(' Objects ( )',0)
                count = self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.nr_zdata
                self.dem_offset = np.empty([self.associated_edx.nr_xdata, self.associated_edx.nr_ydata], dtype=int)

                self.edt_file = np.fromfile(filepath, dtype=np.float32, offset=offset, count=count)
                self.load_terrain_data() # we now have the dem_offset -> so the k-level of the first atmosphere cell

                offset = self.calc_offset(self.var_name, 0) # z_level = 0 because we need to load the full 3 model
                count = self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.nr_zdata
                self.specified_data = np.empty([self.associated_edx.nr_xdata, self.associated_edx.nr_ydata,
                                                self.associated_edx.data_per_variable], dtype=np.float32)
                self.edt_file = np.fromfile(filepath, dtype=np.float32, offset=offset, count=count)
                self.load_defined_data_dem()

            else:
                offset = self.calc_offset(self.var_name, self.z)
                count = self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.data_per_variable
                self.specified_data = np.empty([self.associated_edx.nr_xdata, self.associated_edx.nr_ydata,
                                                self.associated_edx.data_per_variable], dtype=np.float32)
                self.edt_file = np.fromfile(filepath, dtype=np.float32, offset=offset, count=count)
                self.load_defined_data()

    def check_for_terrain(self, filepath):
        offset = self.calc_offset(' Objects ( )', self.z)
        if offset >= 0:
            count = self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.data_per_variable
            #print(offset)
            #print(count)
            has_terrain = False
            #print(filepath)
            edt_file_tmp = np.fromfile(filepath, dtype=np.float32, offset=offset, count=count)
            for y in range(self.associated_edx.nr_ydata):
                for x in range(self.associated_edx.nr_xdata):
                    for n in range(self.associated_edx.data_per_variable):
                        idx = (y * self.associated_edx.data_per_variable * self.associated_edx.nr_xdata) + (x * self.associated_edx.data_per_variable) + n
                        #print(edt_file_tmp)
                        #print(idx)
                        #print(edt_file_tmp[idx])
                        if (round(edt_file_tmp[idx]) == self.demID):
                            has_terrain = True
            return has_terrain
        else:
            return False

    def calc_offset(self, var_name, z_level):
        found = False
        i = 0
        for var in self.associated_edx.name_variables:
            if var_name == " Objects ( )":                               # Objects are special -> older versions of ENVI-met / BIO-met were not using the same exact string for "Objects"...
                if "Objects" in var:
                    found = True
                    break
                else:
                    i += 1
            else:
                if var == var_name:
                    found = True
                    break
                else:
                    i += 1
        #print(i)
        offset = i * (self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.nr_zdata
                      * self.associated_edx.data_per_variable)
        offset += z_level * (self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.data_per_variable)
        offset *= 4  # size of float32
        if found:
            return offset
        else:
            return -1

    def load_defined_data(self):
        for y in range(self.associated_edx.nr_ydata):
            for x in range(self.associated_edx.nr_xdata):
                for n in range(self.associated_edx.data_per_variable):
                    idx = (y * self.associated_edx.data_per_variable * self.associated_edx.nr_xdata) + (x * self.associated_edx.data_per_variable) + n
                    self.specified_data[x, y, n] = self.edt_file[idx]
                    #print(self.edt_file[idx])

    def load_defined_data_dem(self):
        defined_data_3d = np.empty(
            [self.associated_edx.nr_xdata, self.associated_edx.nr_ydata, self.associated_edx.nr_zdata], dtype=np.float32)
        idx = 0
        for z in range(self.associated_edx.nr_zdata):
            for y in range(self.associated_edx.nr_ydata):
                for x in range(self.associated_edx.nr_xdata):
                    defined_data_3d[x, y, z] = self.edt_file[idx]
                    idx += 1
                    #print(self.edt_file[idx])

        for x in range(self.associated_edx.nr_xdata):
            for y in range(self.associated_edx.nr_ydata):
                for n in range(self.associated_edx.data_per_variable):
                    if (self.dem_offset[x, y] + self.z) < self.associated_edx.nr_zdata:
                        self.specified_data[x, y, n] = defined_data_3d[x, y, self.dem_offset[x,y] + self.z]
                    else:
                        self.specified_data[x, y, n] = defined_data_3d[x, y, self.associated_edx.nr_zdata - 1]

    def load_terrain_data(self):
        terrain_data_3d = np.empty(
            [self.associated_edx.nr_xdata, self.associated_edx.nr_ydata, self.associated_edx.nr_zdata], dtype=np.float32)
        idx = 0
        for z in range(self.associated_edx.nr_zdata):
            for y in range(self.associated_edx.nr_ydata):
                for x in range(self.associated_edx.nr_xdata):
                    terrain_data_3d[x, y, z] = self.edt_file[idx]
                    idx += 1
                    #print(self.edt_file[idx])

        for x in range(self.associated_edx.nr_xdata):
            for y in range(self.associated_edx.nr_ydata):
                foundK = 0
                for z in range(self.associated_edx.nr_zdata):
                    if round(terrain_data_3d[x, y, z]) == self.demID:
                        foundK = z + 1
                    self.dem_offset[x,y] = foundK

    def init_data_dict(self):
        for arr in range(len(self.associated_edx.name_variables)):
            var = self.associated_edx.name_variables[arr]
            data_array = np.empty(
                [self.associated_edx.nr_xdata, self.associated_edx.nr_ydata, self.associated_edx.nr_zdata,
                 self.associated_edx.data_per_variable], dtype=np.float32)
            for z in range(self.associated_edx.nr_zdata):
                for y in range(self.associated_edx.nr_ydata):
                    for x in range(self.associated_edx.nr_xdata):
                        for n in range(self.associated_edx.data_per_variable):
                            idx = (
                                    arr * self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.nr_zdata * self.associated_edx.data_per_variable) \
                                  + (
                                              z * self.associated_edx.nr_xdata * self.associated_edx.nr_ydata * self.associated_edx.data_per_variable) \
                                  + (y * self.associated_edx.nr_xdata * self.associated_edx.data_per_variable) + (
                                              x * self.associated_edx.data_per_variable) + n
                            data_array[x, y, z, n] = self.edt_file[idx]
            self.data_dict[var] = data_array



