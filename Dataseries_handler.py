from .EDX_EDT import *
from .NetCDF import *
from datetime import datetime
from .Helper_Functions import *
import numpy as np
import os


class timestep:
    # Class attributes - treat like constants
    EDX_EDT = 'EDX_EDT'
    NC = 'nc'

    def __init__(self):
        self.filename = ''
        self.filetype = ''
        self.date = ''
        self.time = ''
        self.datetime = datetime(1, 1, 1, 1, 1, 1)
        self.QGSLayer = None
        self.nc_timestep_idx = 0
        # Further data which is essential for the add to map function
        self.location_georef_x = 0.0
        self.location_georef_y = 0.0
        self.location_georef_lat = 0.0
        self.spacing_x = []
        self.spacing_y = []
        self.location_georef_xy_utmzone = 0
        self.model_rotation = 0.0

    def setDatetime(self):
        if (self.date != '') and (self.time != ''):
            split_date = self.date.split('.')
            split_time = self.time.split('.')
            d = int(split_date[0])
            m = int(split_date[1])
            y = 2018  # int(split_date[2])
            h = int(split_time[0])
            mi = int(split_time[1])
            s = int(split_time[2])
            self.datetime = datetime(y, m, d, h, mi, s)


class merged_timestep:
    def __init__(self):
        self.timestepA = timestep()
        self.timestepB = timestep()
        self.delta_checked = False
        self.checkedA = False
        self.checkedB = False
        self.placeholderA = False
        self.placeholderB = False
        self.datetime = datetime(1, 1, 1, 1, 1, 1)
        self.strDatetime = ''

    def setDatetime(self):
        if self.placeholderA:
            self.datetime = self.timestepB.datetime
        else:
            self.datetime = self.timestepA.datetime


class dataseries_handler:
    def __init__(self):
        self.SeriesA = []
        self.SeriesB = []
        self.Series_dict = {}
        self.mergedList = []
        self.FolderA = ''
        self.FolderB = ''
        self.SelectedHeight = 0.0
        self.HeightRange = ''
        self.SelectedVariable = ''
        self.SelectedVariableState = ''
        self.SelectedVariableUnit = ''
        self.SelectedSubArea = None
        self.variables = {}
        self.variable_units = {}
        self.CheckCount = 0
        self.cached_nc_file = None

    def setSelectedVariable(self, var: str):
        # e.g. Potential Air Temperature (comparable) -> Potential Air Temperature
        self.SelectedVariable = var.split('(', 1)[0].strip()
        self.SelectedVariableUnit = self.variable_units.get(self.SelectedVariable, 'units')

    def setSelectedVariableState(self, state: str):
        # e.g. Potential Air Temperature (comparable) -> comparable
        self.SelectedVariableState = state.split('(', 1)[-1].split(')', 1)[0]

    # insertion sort
    def insertInSeriesA(self, tstp: timestep):
        if len(self.SeriesA) == 0:
            self.SeriesA.append(tstp)
        else:
            item_inserted = False
            for i in range(len(self.SeriesA)):
                if self.SeriesA[i].datetime > tstp.datetime:
                    self.SeriesA.insert(i, tstp)
                    item_inserted = True
                    break
            # catch edge case - if the tstp.datetime is larger than any datetime in the list, the if-clause above
            # is never True and the item is not inserted during the loop
            if not item_inserted:
                self.SeriesA.append(tstp)

    # insertion sort
    def insertInSeriesB(self, tstp: timestep):
        if len(self.SeriesB) == 0:
            self.SeriesB.append(tstp)
        else:
            item_inserted = False
            for i in range(len(self.SeriesB)):
                if self.SeriesB[i].datetime > tstp.datetime:
                    self.SeriesB.insert(i, tstp)
                    item_inserted = True
                    break
            # catch edge case - if the tstp.datetime is larger than any datetime in the list, the if-clause above
            # is never True and the item is not inserted during the loop
            if not item_inserted:
                self.SeriesB.append(tstp)

    def loadEDXVars(self, edx: EDX, listID: str):
        for var in edx.name_variables:
            # trim units from variable name e.g. 'Wind Speed (m/s)' -> 'Wind Speed'
            trimmed = var.split('(', 1)[0].strip()
            unit = var.split('(', 1)[-1].split(')', 1)[0].strip()
            self.variable_units[trimmed] = unit
            value = self.variables.get(trimmed, -1)
            if listID == 'A':
                if value != -1:
                    self.variables[trimmed] = (1, value[1])
                else:
                    self.variables[trimmed] = (1, 0)
            else:
                if value != -1:
                    self.variables[trimmed] = (value[0], 1)
                else:
                    self.variables[trimmed] = (0, 1)

    def loadNCVars(self, nc: NetCDF, listID: str):
        for var in nc.var_metadata.keys():
            value = self.variables.get(var, -1)
            unit = nc.var_metadata[var].unit
            self.variable_units[var] = unit
            if listID == 'A':
                if value != -1:
                    self.variables[var] = (1, value[1])
                else:
                    self.variables[var] = (1, 0)
            else:
                if value != -1:
                    self.variables[var] = (value[0], 1)
                else:
                    self.variables[var] = (0, 1)

    def fillList(self, folder: str, listID: str):
        vars_loaded_nc = False
        vars_loaded_edx = False
        self.CheckCount = 0
        self.variables.clear()
        self.variable_units.clear()

        if listID == 'A':
            self.FolderA = folder
        else:
            self.FolderB = folder

        if folder != '':
            if listID == 'A':
                self.SeriesA.clear()
            else:
                self.SeriesB.clear()
            # fill with timesteps
            # distinguish between EDX/EDT and NetCDF
            files = [file for file in os.listdir(folder) if os.path.isfile(merge_filepath(folder=folder, file=file))]
            for file in files:
                file_format = file.split('.')[-1]
                if file_format == 'nc':
                    nc = NetCDF(merge_filepath(folder=folder, file=file))
                    for i in range(len(nc.time)):
                        tstp = timestep()
                        tstp.filename = file
                        tstp.filetype = tstp.NC
                        tstp.nc_timestep_idx = i
                        tstp.date, tstp.time = calculate_datetime_netcdf(date_str=nc.sim_date, time_str=nc.sim_time,
                                                                         delimiter='.', time_stp=i, nc=nc,
                                                                         exclude_year=True)
                        tstp.date = tstp.date.strip() + '.'
                        tstp.time = tstp.time.strip()
                        tstp.setDatetime()
                        if listID == 'A':
                            self.insertInSeriesA(tstp)
                        else:
                            self.insertInSeriesB(tstp)
                    if not vars_loaded_nc:
                        self.loadNCVars(nc, listID)
                        vars_loaded_nc = True
                elif file_format == 'EDX':
                    edt_file = file.replace('.EDX', '.EDT')
                    if edt_file in files:
                        # both EDX and EDT file exist for that timestep
                        edx = EDX(merge_filepath(folder=folder, file=file))
                        tstp = timestep()
                        tstp.filename = file
                        tstp.filetype = tstp.EDX_EDT
                        tstp.date = edx.simulation_date
                        tstp.date = tstp.date.strip()
                        split_date = tstp.date.split('.')
                        tstp.date = split_date[0] + '.' + split_date[1] + '.'
                        split_time = edx.simulation_time.split('.')
                        tstp.time = split_time[0] + '.' + split_time[1] + '.00'
                        tstp.time = tstp.time.strip()
                        tstp.setDatetime()
                        if listID == 'A':
                            self.insertInSeriesA(tstp)
                        else:
                            self.insertInSeriesB(tstp)
                        if not vars_loaded_edx:
                            self.loadEDXVars(edx, listID)
                            vars_loaded_edx = True

        # Fallback if different filetypes in Series A / B
        vars_loaded_edx = False
        vars_loaded_nc = False
        if listID == 'A':
            if self.FolderB != '':
                files = [file for file in os.listdir(self.FolderB) if os.path.isfile(merge_filepath(folder=self.FolderB, file=file))]
                for file in files:
                    file_format = file.split('.')[-1]
                    if (file_format == 'nc') and not vars_loaded_nc:
                        nc = NetCDF(merge_filepath(folder=self.FolderB, file=file))
                        self.loadNCVars(nc, 'B')
                        vars_loaded_nc = True
                    elif (file_format == 'EDX') and not vars_loaded_edx:
                        edx = EDX(merge_filepath(folder=self.FolderB, file=file))
                        self.loadEDXVars(edx, 'B')
                        vars_loaded_edx = True

                    if vars_loaded_nc and vars_loaded_edx:
                        break
        else:
            if self.FolderA != '':
                files = [file for file in os.listdir(self.FolderA) if os.path.isfile(merge_filepath(folder=self.FolderA, file=file))]
                for file in files:
                    file_format = file.split('.')[-1]
                    if (file_format == 'nc') and not vars_loaded_nc:
                        nc = NetCDF(merge_filepath(folder=self.FolderA, file=file))
                        self.loadNCVars(nc, 'A')
                        vars_loaded_nc = True
                    elif (file_format == 'EDX') and not vars_loaded_edx:
                        edx = EDX(merge_filepath(folder=self.FolderA, file=file))
                        self.loadEDXVars(edx, 'A')
                        vars_loaded_edx = True

                    if vars_loaded_nc and vars_loaded_edx:
                        break

        self.fillSeriesDict()
        self.fillMergedList()

    def fillSeriesDict(self):
        self.Series_dict.clear()

        for i in range(len(self.SeriesA)):
            self.Series_dict[self.SeriesA[i].datetime] = (i, -1)

        for i in range(len(self.SeriesB)):
            dt = self.SeriesB[i].datetime
            value = self.Series_dict.get(dt, -1)
            if value != -1:
                # the value exists already in the dictionary. Add to it.
                a = value[0]
                self.Series_dict[dt] = (a, i)
            else:
                # key does not yet exist in the dictionary
                self.Series_dict[dt] = (-1, i)

    def fillMergedList(self):
        self.mergedList.clear()
        for key in self.Series_dict.keys():
            value = self.Series_dict[key]
            tstp_merged = None
            if (value[0] == -1) or (value[1] == -1):
                if value[0] == -1:
                    # TimestepA does not exist and is a placeholder
                    tstp_merged = self.initMergedTimestep(None, self.SeriesB[value[1]])
                elif value[1] == -1:
                    # TimestepB does not exist and is a placeholder
                    tstp_merged = self.initMergedTimestep(self.SeriesA[value[0]], None)
            else:
                # Both timesteps exist
                tstp_merged = self.initMergedTimestep(self.SeriesA[value[0]], self.SeriesB[value[1]])

            # insertion sort
            if len(self.mergedList) == 0:
                self.mergedList.append(tstp_merged)
            else:
                item_inserted = False
                for i in range(len(self.mergedList)):
                    if self.mergedList[i].datetime > tstp_merged.datetime:
                        self.mergedList.insert(i, tstp_merged)
                        item_inserted = True
                        break
                # catch edge case - if the tstp.datetime is larger than any datetime in the list, the if-clause above
                # is never True and the item is not inserted during the loop
                if not item_inserted:
                    self.mergedList.append(tstp_merged)

    def loadDataForTimestep(self, idx: int):
        dataA = None
        dataB = None
        if idx <= len(self.mergedList):
            merged = self.mergedList[idx]
            # Check timestep A
            if (not merged.placeholderA) and (merged.checkedA or merged.delta_checked):
                tstp = merged.timestepA
                if tstp.filetype == tstp.EDX_EDT:
                    edx = EDX(merge_filepath(folder=self.FolderA, file=tstp.filename))
                    edt_file = merge_filepath(folder=self.FolderA, file=tstp.filename.replace('.EDX', '.EDT'))
                    z_lvl = self.calcHeightlvl(spacing_z=edx.spacing_z)
                    edt = EDT(filepath=edt_file, edx=edx, var_name=self.SelectedVariable, z=z_lvl)
                    dataA = edt.specified_data
                    dataA = dataA.reshape((dataA.shape[0], dataA.shape[1]))
                    tstp.location_georef_x = edx.location_georef_x
                    tstp.location_georef_y = edx.location_georef_y
                    tstp.location_georef_lat = edx.location_georef_lat
                    tstp.spacing_x = edx.spacing_x
                    tstp.spacing_y = edx.spacing_y
                    tstp.location_georef_xy_utmzone = edx.location_georef_xy_utmzone
                    tstp.model_rotation = edx.model_rotation
                elif tstp.filetype == tstp.NC:
                    filepath = merge_filepath(folder=self.FolderA, file=tstp.filename)
                    if self.cached_nc_file is None:
                        # there if no nc-file cached yet
                        self.cached_nc_file = NetCDF(filepath=filepath)
                    elif filepath != self.cached_nc_file.filepath:
                        # we found a second nc-file in the folder
                        # self.cached_nc_file.file.close()
                        self.cached_nc_file = NetCDF(filepath=filepath)
                    spacing_z = self.cached_nc_file.file.getncattr("SizeDZ")
                    z_lvl = self.calcHeightlvl(spacing_z=spacing_z)
                    var_metadata = self.cached_nc_file.get_var_metadata(self.SelectedVariable)
                    dataA = self.cached_nc_file.get_data(varName=var_metadata.name, z_lvl=z_lvl,
                                                         time_stp=tstp.nc_timestep_idx)
                    tstp.location_georef_x = self.cached_nc_file.georef_x
                    tstp.location_georef_y = self.cached_nc_file.georef_y
                    tstp.location_georef_lat = self.cached_nc_file.georef_lat
                    tstp.spacing_x = [float(i) for i in self.cached_nc_file.size_x]
                    tstp.spacing_y = [float(i) for i in self.cached_nc_file.size_y]
                    tstp.location_georef_xy_utmzone = self.cached_nc_file.UTM_zone
                    tstp.model_rotation = float(self.cached_nc_file.model_rotation)

            # Check timestep B
            if (not merged.placeholderB) and (merged.checkedB or merged.delta_checked):
                tstp = merged.timestepB
                if tstp.filetype == tstp.EDX_EDT:
                    edx = EDX(merge_filepath(folder=self.FolderB, file=tstp.filename))
                    edt_file = merge_filepath(folder=self.FolderB, file=tstp.filename.replace('.EDX', '.EDT'))
                    z_lvl = self.calcHeightlvl(spacing_z=edx.spacing_z)
                    edt = EDT(filepath=edt_file, edx=edx, var_name=self.SelectedVariable, z=z_lvl)
                    dataB = edt.specified_data
                    dataB = dataB.reshape((dataB.shape[0], dataB.shape[1]))
                    tstp.location_georef_x = edx.location_georef_x
                    tstp.location_georef_y = edx.location_georef_y
                    tstp.location_georef_lat = edx.location_georef_lat
                    tstp.spacing_x = edx.spacing_x
                    tstp.spacing_y = edx.spacing_y
                    tstp.location_georef_xy_utmzone = edx.location_georef_xy_utmzone
                    tstp.model_rotation = edx.model_rotation
                elif tstp.filetype == tstp.NC:
                    filepath = merge_filepath(folder=self.FolderB, file=tstp.filename)
                    if self.cached_nc_file is None:
                        # there if no nc-file cached yet
                        self.cached_nc_file = NetCDF(filepath=filepath)
                    elif filepath != self.cached_nc_file.filepath:
                        # we found a second nc-file in the folder
                        # cached_nc_file.file.close()
                        self.cached_nc_file = NetCDF(filepath=filepath)
                    spacing_z = self.cached_nc_file.file.getncattr("SizeDZ")
                    z_lvl = self.calcHeightlvl(spacing_z=spacing_z)
                    var_metadata = self.cached_nc_file.get_var_metadata(self.SelectedVariable)
                    dataB = self.cached_nc_file.get_data(varName=var_metadata.name, z_lvl=z_lvl,
                                                         time_stp=tstp.nc_timestep_idx)
                    tstp.location_georef_x = self.cached_nc_file.georef_x
                    tstp.location_georef_y = self.cached_nc_file.georef_y
                    tstp.location_georef_lat = self.cached_nc_file.georef_lat
                    tstp.spacing_x = [float(i) for i in self.cached_nc_file.size_x]
                    tstp.spacing_y = [float(i) for i in self.cached_nc_file.size_y]
                    tstp.location_georef_xy_utmzone = self.cached_nc_file.UTM_zone
                    tstp.model_rotation = float(self.cached_nc_file.model_rotation)

        # dataA/B is None if the if-branches were not executed
        return dataA, dataB

    def calcHeightlvl(self, spacing_z):
        z_lvl = 0
        currentHeightInterval = (0.0, spacing_z[0])
        for j in range(len(spacing_z) - 1):
            if (self.SelectedHeight >= currentHeightInterval[0]) \
                    and (self.SelectedHeight <= currentHeightInterval[1]):
                break
            currentHeightInterval = (currentHeightInterval[0] + spacing_z[j], currentHeightInterval[1] + spacing_z[j + 1])
            z_lvl += 1
        self.HeightRange = f'{round(currentHeightInterval[0], 3)}m-{round(currentHeightInterval[1], 3)}m'
        return z_lvl

    def getVariablesAsList(self, bOnlyComparable: bool):
        if bOnlyComparable:
            var_list = [var for var in self.variables.keys() if self.variables[var] == (1, 1)]
        else:
            var_list = [var for var in self.variables.keys()]

        for i in range(len(var_list)):
            var = var_list[i]
            value = self.variables[var]
            if (value[0] == 1) and (value[1] == 1):
                # the variable exists in both Series A and B
                var_list[i] = f'{var} (Comparable)'
            elif value[0] == 1:
                # the variable only exists in Series A
                var_list[i] = f'{var} (Only Series A)'
            elif value[1] == 1:
                # the variable only exists in Series B
                var_list[i] = f'{var} (Only Series B)'
        var_list = sorted(var_list, key=str.lower)
        return var_list

    @staticmethod
    def initMergedTimestep(tstpA: timestep, tstpB: timestep):
        tstp_merged = merged_timestep()
        if tstpA is None:
            tstp_merged.placeholderA = True
            tstp_merged.timestepB = tstpB
            tstp_merged.strDatetime = f'{tstpB.date} {tstpB.time}'
        elif tstpB is None:
            tstp_merged.placeholderB = True
            tstp_merged.timestepA = tstpA
            tstp_merged.strDatetime = f'{tstpA.date} {tstpA.time}'
        else:
            tstp_merged.timestepA = tstpA
            tstp_merged.timestepB = tstpB
            tstp_merged.strDatetime = f'{tstpA.date} {tstpA.time}'
        tstp_merged.setDatetime()
        return tstp_merged

    def reset(self):
        self.SelectedHeight = 0.0
        self.HeightRange = ''
        self.SelectedVariable = ''
        self.SelectedVariableState = ''
        self.SelectedVariableUnit = ''
        self.SelectedSubArea = None
        # all other class-fields get overwritten or cleared during the process of add-to-map


# init global dataseries handler
dataseries = dataseries_handler()
