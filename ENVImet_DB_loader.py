import numpy as np
import os

'''
Description: This file contains a class to load the ENVImet-Database as well as a class to automatically
load the default projects-folder with every containing project
'''


class EnviProjects:
    def __init__(self):
        self.workspace = ''
        self.selectedPython = ''
        self.installPath = ''
        self.userpathinfo = ''
        self.userpathmode = 0
        self.projects = []
        self.usersettings = os.getenv('APPDATA').replace('\\', '/') + '/ENVI-met/usersettings.setx'
        if os.path.exists(self.usersettings):
            self.usersettingsFound = True
            self.load_usersettings()
            self.sysDB_path = self.userpathinfo.rsplit('/', 1)[0] + '/sys.basedata/database.edb'
            self.userDB_path = self.userpathinfo + '/userdatabase.edb'
            self.sys_db = ENVImetDB(filepath=self.sysDB_path, use_project_db=False, filepath_user_db=self.userDB_path)
            self.load_projects(self.workspace)
        else:
            self.usersettingsFound = False

    def load_usersettings(self):
        settings = open(self.usersettings, 'br')
        for row in settings:
            row = row.decode('ansi')
            if '<absolute_path>' in row:
                self.workspace = row.split(">", 1)[1].split("<", 1)[0].replace(' ', '').replace('\\', '/')
            if '<selectedPython>' in row:
                self.selectedPython = row.split(">", 1)[1].split("<", 1)[0].replace(' ', '').replace('\\', '/')
            if ('<userpathinfo>' in row) and ('</userpathinfo>' in row):
                self.userpathinfo = row.split(">", 1)[1].split("<", 1)[0].replace(' ', '').replace('\\', '/')
            if '<userpathmode>' in row:
                self.userpathmode = int(row.split(">", 1)[1].split("<", 1)[0].replace(' ', ''))
        if not self.userpathinfo == '':
            self.installPath = self.userpathinfo.replace("sys.userdata", "")
        settings.close()

    def load_projects(self, path):
        subfolders = os.listdir(path)
        for folder in subfolders:
            p = self.workspace + '/' + folder
            if os.path.exists(p + '/project.infoX'):
                new_project = Project()
                new_project.projectPath = p
                info_file = open(p + '/project.infoX', 'br')
                for row in info_file:
                    row = row.decode('ansi')
                    if '<name>' in row:
                        new_project.name = row.split(">", 1)[1].split("<", 1)[0]
                    if '<description>' in row:
                        new_project.description = row.split(">", 1)[1].split("<", 1)[0]
                    if '<useProjectDB>' in row:
                        new_project.useProjectDB = bool(row.split(">", 1)[1].split("<", 1)[0].replace(' ', ''))
                #if new_project.useProjectDB and os.path.exists(new_project.projectPath + '/projectdatabase.edb'):
                #    new_project.DB = ENVImetDB(filepath=self.sysDB_path, use_project_db=True, filepath_project_db=new_project.projectPath + '/projectdatabase.edb')
                #else:
                #    new_project.DB = self.sys_db
                self.projects.append(new_project)
                info_file.close()
            #self.load_projects(p)


class Project:
    def __init__(self):
        self.name = ''
        self.description = ''
        self.useProjectDB = False
        self.projectPath = ''
        self.DB = None


class ENVImetDB:
    def __init__(self, filepath, use_project_db: bool = False, filepath_project_db: str = '', filepath_user_db: str = ''):
        #self.DB = open(filepath, 'br')
        #self.DB = self.get_np_array(self.DB)
        #if use_project_db:
        #    self.project_DB = open(filepath_project_db, 'br')
        #    self.project_DB = self.get_np_array(self.project_DB)
        #elif os.path.exists(filepath_user_db):
        #    self.user_DB = open(filepath_user_db, 'br')
        #    self.user_DB = self.get_np_array(self.user_DB)
        #print(filepath)
        self.use_project_db = use_project_db

        self.filetype = ''
        self.version = 0
        self.revisiondate = ''
        self.remark = ''
        self.checksum = 0
        self.encryptionlevel = 0

        self.soil_dict = {}
        self.profile_dict = {}
        self.material_dict = {}
        self.wall_dict = {}
        self.singlewall_dict = {}
        self.plant_dict = {}
        self.greening_dict = {}
        self.plant3d_dict = {}
        self.sources_dict = {}
        #print(filepath)
        self.load_data(filepath)
        if self.use_project_db:
            self.load_data(filepath_project_db)
        elif os.path.exists(filepath_user_db):
            self.load_data(filepath_user_db)

    @staticmethod
    def get_np_array(db):
        l = []
        for row in db:
            row = row.decode('ansi')
            l.append(row)
        return np.asarray(l, dtype=str)

    def load_data(self, database_path):
        databaseF = open(database_path, 'br')
        database = self.get_np_array(databaseF)
        count = 0
        for row in range(len(database)):
            if row + count == len(database)-1:
                # we reached last line of database and need to break the loop manually
                break

            if "<filetype>" in database[row + count]:
                self.filetype = database[row + count].split(">", 1)[1].split("<", 1)[0]
            elif "<version>" in database[row + count]:
                self.version = int(database[row + count].split(">", 1)[1].split("<", 1)[0])
            elif "<revisiondate>" in database[row + count]:
                self.revisiondate = database[row + count].split(">", 1)[1].split("<", 1)[0]
            elif "<remark>" in database[row + count]:
                self.remark = database[row + count].split(">", 1)[1].split("<", 1)[0]
            elif "<checksum>" in database[row + count]:
                self.checksum = int(database[row + count].split(">", 1)[1].split("<", 1)[0])
            elif "<encryptionlevel>" in database[row + count]:
                self.encryptionlevel = int(database[row + count].split(">", 1)[1].split("<", 1)[0])

            elif "<SOIL>" in database[row + count]:
                # found new soiltype
                soil = SOIL()
                count += 1
                while "</SOIL>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        soil.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        soil.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<versiegelung>" in database[row + count]:
                        soil.versiegelung = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<ns>" in database[row + count]:
                        soil.ns = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<nfc>" in database[row + count]:
                        soil.nfc = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<nwilt>" in database[row + count]:
                        soil.nwilt = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<matpot>" in database[row + count]:
                        soil.matpot = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<hydro_lf>" in database[row + count]:
                        soil.hydro_lf = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<volumenw>" in database[row + count]:
                        soil.volumenw = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<b>" in database[row + count]:
                        soil.b = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<waerme_lf>" in database[row + count]:
                        soil.waerme_lf = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        soil.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Color>" in database[row + count]:
                        soil.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AddValue1>" in database[row + count]:
                        soil.AddValue1 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AddValue2>" in database[row + count]:
                        soil.AddValue2 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1

                self.soil_dict[soil.ID] = soil

            elif "<PROFILE>" in database[row + count]:
                # found new profiletype
                profile = PROFILE()
                count += 1
                while "</PROFILE>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        profile.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        profile.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<z0_Length>" in database[row + count]:
                        profile.z0_length = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<soilprofil>" in database[row + count]:
                        profile.soilprofil = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")
                    elif "<Albedo>" in database[row + count]:
                        profile.Emissivitaet = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Emissivität>" in database[row + count]:
                        profile.Emissivitaet = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Irrigated>" in database[row + count]:
                        profile.Irrigated = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        profile.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        profile.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<AddValue1>" in database[row + count]:
                        profile.AddValue1 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AddValue2>" in database[row + count]:
                        profile.AddValue2 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1

                self.profile_dict[profile.ID] = profile

            elif "<MATERIAL>" in database[row + count]:
                # found new material
                material = MATERIAL()
                count += 1
                while "</MATERIAL>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        material.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        material.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<DefaultThickness>" in database[row + count]:
                        material.DefaultThickness = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Absorption>" in database[row + count]:
                        material.Absorption = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Transmission>" in database[row + count]:
                        material.Transmission = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Reflection>" in database[row + count]:
                        material.Reflection = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Emissivity>" in database[row + count]:
                        material.Emissivity = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SpecificHeat>" in database[row + count]:
                        material.SpecificHeat = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<ThermalConductivity>" in database[row + count]:
                        material.ThermalConductivity = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Density>" in database[row + count]:
                        material.Density = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<ExtraID>" in database[row + count]:
                        material.ExtraID = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        material.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        material.Group = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    count += 1

                self.material_dict[material.ID] = material

            elif "<WALL>" in database[row + count]:
                # found new wall
                wall = WALL()
                count += 1
                while "</WALL>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        wall.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        wall.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Materials>" in database[row + count]:
                        wall.Materials = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")
                    elif "<ThicknessLayers>" in database[row + count]:
                        wall.ThicknessLayers = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<TypeID>" in database[row + count]:
                        wall.TypeID = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<RoughnessLength>" in database[row + count]:
                        wall.RoughnessLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<CanBeGreened>" in database[row + count]:
                        wall.CanBeGreened = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        wall.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        wall.Group = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<AddValue1>" in database[row + count]:
                        wall.AddValue1 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AddValue2>" in database[row + count]:
                        wall.AddValue2 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1

                self.wall_dict[wall.ID] = wall

            elif "<PLANT>" in database[row + count]:
                # found new simple plant
                plant = PLANT()
                count += 1
                while "</PLANT>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        plant.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        plant.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<AlternativeName>" in database[row + count]:
                        plant.AlternativeName = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Planttype>" in database[row + count]:
                        plant.Planttype = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Leaftype>" in database[row + count]:
                        plant.Leaftype = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Albedo>" in database[row + count]:
                        plant.Albedo = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Transmittance>" in database[row + count]:
                        plant.Transmittance = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<rs_min>" in database[row + count]:
                        plant.rs_min = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Height>" in database[row + count]:
                        plant.Height = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Depth>" in database[row + count]:
                        plant.Depth = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LAD-Profile>" in database[row + count]:
                        plant.LAD_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<RAD-Profile>" in database[row + count]:
                        plant.RAD_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Season-Profile>" in database[row + count]:
                        plant.Season_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Group>" in database[row + count]:
                        plant.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Color>" in database[row + count]:
                        plant.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1

                self.plant_dict[plant.ID] = plant

            elif "<SINGLEWALL>" in database[row + count]:
                # found new single-wall
                wall = SINGLEWALL()
                count += 1
                while "</SINGLEWALL>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        wall.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Name>" in database[row + count]:
                        wall.Name = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Material>" in database[row + count]:
                        wall.Material = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<RoughnessLength>" in database[row + count]:
                        wall.RoughnessLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Thickness>" in database[row + count]:
                        wall.Thickness = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        wall.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        wall.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    count += 1
                self.singlewall_dict[wall.ID] = wall

            elif "<SOURCE>" in database[row + count]:
                # found new source
                source = SOURCE()
                count += 1
                while "</SOURCE>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        source.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        source.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Color>" in database[row + count]:
                        source.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        source.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<DefaultHeight>" in database[row + count]:
                        source.DefaultHeight = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Sourcetype>" in database[row + count]:
                        source.Sourcetype = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SpecialID>" in database[row + count]:
                        source.SpecialID = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Emissionprofile_User>" in database[row + count]:
                        source.Emissionprofile_User = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Emissionprofile_NO>" in database[row + count]:
                        source.Emissionprofile_NO = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Emissionprofile_NO2>" in database[row + count]:
                        source.Emissionprofile_NO2 = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Emissionprofile_O3>" in database[row + count]:
                        source.Emissionprofile_O3 = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Emissionprofile_PM10>" in database[row + count]:
                        source.Emissionprofile_PM10 = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Emissionprofile_PM25>" in database[row + count]:
                        source.Emissionprofile_PM25 = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    count += 1
                self.sources_dict[source.ID] = source

            elif "<GREENING>" in database[row + count]:
                # found new greening
                greening = GREENING()
                count += 1
                while "</GREENING>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        greening.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Name>" in database[row + count]:
                        greening.Name = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<HasSubstrate>" in database[row + count]:
                        greening.HasSubstrate = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SoilID>" in database[row + count]:
                        greening.SoilID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")
                    elif "<ThicknessLayers>" in database[row + count]:
                        greening.ThicknessLayers = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<subEmissivity>" in database[row + count]:
                        greening.subEmissivity = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<subAlbedo>" in database[row + count]:
                        greening.subAlbedo = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<subWaterCoeff>" in database[row + count]:
                        greening.subWaterCoeff = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SimplePlantID>" in database[row + count]:
                        greening.SimplePlantID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<LAI>" in database[row + count]:
                        greening.LAI = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SimplePlantThickness>" in database[row + count]:
                        greening.SimplePlantThickness = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafAngleDistribution>" in database[row + count]:
                        greening.LeafAngleDistribution = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AirGap>" in database[row + count]:
                        greening.AirGap = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        greening.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        greening.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<AddValue1>" in database[row + count]:
                        greening.AddValue1 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<AddValue2>" in database[row + count]:
                        greening.AddValue2 = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1

                self.greening_dict[greening.ID] = greening

            elif "<PLANT3D>" in database[row + count]:
                # found new 3D-Plant
                plant = PLANT3D()
                count += 1
                while "</PLANT3D>" not in database[row + count]:
                    if "<ID>" in database[row + count]:
                        plant.ID = database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "")
                    elif "<Description>" in database[row + count]:
                        plant.Description = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<AlternativeName>" in database[row + count]:
                        plant.AlternativeName = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Planttype>" in database[row + count]:
                        plant.Planttype = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Leaftype>" in database[row + count]:
                        plant.Leaftype = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Albedo>" in database[row + count]:
                        plant.Albedo = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Transmittance>" in database[row + count]:
                        plant.Transmittance = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<isoprene>" in database[row + count]:
                        plant.isoprene = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<leafweigth>" in database[row + count]:
                        plant.leafweigth = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<rs_min>" in database[row + count]:
                        plant.rs_min = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Height>" in database[row + count]:
                        plant.Height = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Width>" in database[row + count]:
                        plant.Width = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Depth>" in database[row + count]:
                        plant.Depth = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<RootDiameter>" in database[row + count]:
                        plant.RootDiameter = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<cellsize>" in database[row + count]:
                        plant.cellsize = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<xy_cells>" in database[row + count]:
                        plant.xy_cells = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<z_cells>" in database[row + count]:
                        plant.z_cells = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LAD-Profile" in database[row + count]:
                        count += 1
                        while "</LAD-Profile>" not in database[row + count]:
                            tmp = database[row + count].replace(" ", "").split(",")
                            plant.LAD_Profile.append((int(tmp[0]), int(tmp[1]), int(tmp[2]), float(tmp[3])))
                            count += 1

                        plant.convert_lad_profile_to_numpy()
                    elif "<RAD-Profile>" in database[row + count]:
                        plant.RAD_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Root-Range-Profile>" in database[row + count]:
                        plant.Root_Range_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<Season-Profile>" in database[row + count]:
                        plant.Season_Profile = [float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(",")]
                    elif "<DensityWood>" in database[row + count]:
                        plant.DensityWood = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<YoungsModulus>" in database[row + count]:
                        plant.YoungsModulus = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<YoungRatioRtoL>" in database[row + count]:
                        plant.YoungRatioRtoL = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<MORBranch>" in database[row + count]:
                        plant.MORBranch = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<MORConnection>" in database[row + count]:
                        plant.MORConnection = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<PlantGroup>" in database[row + count]:
                        plant.PlantGroup = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Color>" in database[row + count]:
                        plant.Color = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Group>" in database[row + count]:
                        plant.Group = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<ColorStem>" in database[row + count]:
                        plant.ColorStem = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<ColorBlossom>" in database[row + count]:
                        plant.ColorBlossom = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<L-SystemBased>" in database[row + count]:
                        plant.L_SystemBased = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Axiom>" in database[row + count]:
                        plant.Axiom = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<IterationDepth>" in database[row + count]:
                        plant.IterationDepth = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<hasUserEdits>" in database[row + count]:
                        plant.hasUserEdits = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LADMatrix_generated>" in database[row + count]:
                        plant.LADMatrix_generated = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<InitialSegmentLength>" in database[row + count]:
                        plant.InitialSegmentLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SmallSegmentLength>" in database[row + count]:
                        plant.SmallSegmentLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<ChangeSegmentLength>" in database[row + count]:
                        plant.ChangeSegmentLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SegmentResolution>" in database[row + count]:
                        plant.SegmentResolution = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<TurtleAngle>" in database[row + count]:
                        plant.TurtleAngle = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<RadiusOuterBranch>" in database[row + count]:
                        plant.RadiusOuterBranch = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<PipeFactor>" in database[row + count]:
                        plant.PipeFactor = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafPosition>" in database[row + count]:
                        plant.LeafPosition = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafsPerNode>" in database[row + count]:
                        plant.LeafsPerNode = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafInternodeLength>" in database[row + count]:
                        plant.LeafInternodeLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafMinSegmentOrder>" in database[row + count]:
                        plant.LeafMinSegmentOrder = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafWidth>" in database[row + count]:
                        plant.LeafWidth = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafLength>" in database[row + count]:
                        plant.LeafLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafSurface>" in database[row + count]:
                        plant.LeafSurface = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<PetioleAngle>" in database[row + count]:
                        plant.PetioleAngle = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<PetioleLength>" in database[row + count]:
                        plant.PetioleLength = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<LeafRotationalAngle>" in database[row + count]:
                        plant.LeafRotationalAngle = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<FactorHorizontal>" in database[row + count]:
                        plant.FactorHorizontal = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<TropismVector>" in database[row + count]:
                        plant.TropismVector = (float(i) for i in database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", "").split(","))
                    elif "<TropismElstaicity>" in database[row + count]:
                        plant.TropismElstaicity = float(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<SegmentRemovallist>" in database[row + count]:
                        plant.SegmentRemovallist = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<NrRules>" in database[row + count]:
                        plant.NrRules = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    elif "<Rules_Variable>" in database[row + count]:
                        plant.Rules_Variable = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Rules_Replacement>" in database[row + count]:
                        plant.Rules_Replacement = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Rules_isConditional>" in database[row + count]:
                        plant.Rules_isConditional = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Rules_Condition>" in database[row + count]:
                        plant.Rules_Condition = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<Rules_Remark>" in database[row + count]:
                        plant.Rules_Remark = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<TermLString>" in database[row + count]:
                        plant.TermLString = database[row + count].split(">", 1)[1].split("<", 1)[0]
                    elif "<ApplyTermLString>" in database[row + count]:
                        plant.ApplyTermLString = int(database[row + count].split(">", 1)[1].split("<", 1)[0].replace(" ", ""))
                    count += 1
                self.plant3d_dict[plant.ID] = plant
        databaseF.close()


class SOIL:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.versiegelung = 0
        self.ns = 0.0
        self.nfc = 0.0
        self.nwilt = 0.0
        self.matpot = 0.0
        self.hydro_lf = 0.0
        self.volumenw = 0.0
        self.b = 0.0
        self.waerme_lf = 0.0
        self.Group = ''
        self.Color = 0
        self.AddValue1 = 0.0
        self.AddValue2 = 0.0


class PROFILE:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.z0_length = 0.0
        self.soilprofil = np.empty(19, dtype=str)
        self.Albedo = 0.0
        self.Emissivitaet = 0.0
        self.ExtraID = 0
        self.Irrigated = 0
        self.Color = 0
        self.Group = ''
        self.AddValue1 = ''
        self.AddValue2 = ''


class MATERIAL:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.DefaultThickness = 0.0
        self.Absorption = 0.0
        self.Transmission = 0.0
        self.Reflection = 0.0
        self.Emissivity = 0.0
        self.SpecificHeat = 0.0
        self.ThermalConductivity = 0.0
        self.Density = 0.0
        self.ExtraID = 0
        self.Color = 0
        self.Group = ''


class WALL:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.Materials = np.empty(3, dtype=str)
        self.ThicknessLayers = np.empty(3, dtype=float)
        self.TypeID = 0
        self.RoughnessLength = 0.0
        self.CanBeGreened = 0
        self.Color = 0
        self.Group = ''
        self.AddValue1 = 0.0
        self.AddValue2 = 0.0


class SINGLEWALL:
    def __init__(self):
        self.ID = ''
        self.Name = ''
        self.Material = ''
        self.RoughnessLength = 0.0
        self.Thickness = 0.0
        self.Color = 0
        self.Group = ''

    # define an alias for Name -> Description
    @property
    def Description(self):
        return self.Name

    @Description.setter
    def Description(self, value):
        self.Name = value


class SOURCE:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.Color = 0
        self.Group = ''
        self.DefaultHeight = 0.0
        self.Sourcetype = 0
        self.SpecialID = 0
        self.Emissionprofile_User = []
        self.Emissionprofile_NO = []
        self.Emissionprofile_NO2 = []
        self.Emissionprofile_O3 = []
        self.Emissionprofile_PM10 = []
        self.Emissionprofile_PM25 = []
        self.Remark = ''

    def convert_emissionprofiles_to_numpy(self):
        self.Emissionprofile_User = np.asarray(self.Emissionprofile_User)
        self.Emissionprofile_NO = np.asarray(self.Emissionprofile_NO)
        self.Emissionprofile_NO2 = np.asarray(self.Emissionprofile_NO2)
        self.Emissionprofile_O3 = np.asarray(self.Emissionprofile_O3)
        self.Emissionprofile_PM10 = np.asarray(self.Emissionprofile_PM10)
        self.Emissionprofile_PM25 = np.asarray(self.Emissionprofile_PM25)


class PLANT:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.AlternativeName = ''
        self.Planttype = 0
        self.Leaftype = 0
        self.Albedo = 0.0
        self.Transmittance = 0.0
        self.rs_min = 0.0
        self.Height = 0.0
        self.Depth = 0.0
        self.LAD_Profile = np.empty(10, dtype=float)
        self.RAD_Profile = np.empty(10, dtype=float)
        self.Season_Profile = np.empty(12, dtype=float)
        self.Group = ''
        self.Color = 0


class GREENING:
    def __init__(self):
        self.ID = ''
        self.Name = ''
        self.HasSubstrate = 0
        self.SoilID = np.empty(3, dtype=str)
        self.ThicknessLayers = np.empty(3, dtype=float)
        self.subEmissivity = 0.0
        self.subAlbedo = 0.0
        self.subWaterCoeff = 0.0
        self.SimplepLantID = ''
        self.LAI = 0.0
        self.SimplePlantThickness = 0.0
        self.LeafAngleDistribution = 0.0
        self.AirGap = 0.0
        self.Color = 0
        self.Group = ''
        self.AddValue1 = 0.0
        self.AddValue2 = 0.0

    # define an alias for Name -> Description
    @property
    def Description(self):
        return self.Name

    @Description.setter
    def Description(self, value):
        self.Name = value


class PLANT3D:
    def __init__(self):
        self.ID = ''
        self.Description = ''
        self.AlternativeName = ''
        self.Planttype = 0
        self.Leaftype = 0
        self.Albedo = 0.0
        self.Transmittance = 0.0
        self.isoprene = 0.0
        self.leafweight = 0.0
        self.rs_min = 0.0
        self.Height = 0.0
        self.Width = 0.0
        self.Depth = 0.0
        self.RootDiameter = 0.0
        self.cellsize = 0.0
        self.xy_cells = 0
        self.z_cells = 0
        self.LAD_Profile = []
        self.RAD_Profile = np.empty(10, dtype=float)
        self.Root_Range_Profile = np.empty(10, dtype=float)
        self.Season_Profile = np.empty(10, dtype=float)
        self.DensityWood = 0.0
        self.YoungsMoulus = 0.0
        self.YoungRatioRtoL = 0.0
        self.MORBranch = 0.0
        self.MORConnection = 0.0
        self.PlantGroup = 0
        self.Color = 0
        self.Group = ''
        self.Group = ''
        self.ColorStem = 0
        self.ColorBlossom = 0
        self.L_SystemBased = 0
        self.hasUserEdits = 0
        self.Axiom = ''
        self.IterationDepth = 0
        self.LADMatrix_generated = 0
        self.InitialSegmentLength = 0.0
        self.SmallSegmentLength = 0.0
        self.ChangeSegmentLength = 0.0
        self.SegmentResolution = 0.0
        self.TurtleAngle = 0.0
        self.RadiusOuterBranch = 0.0
        self.PipeFactor = 0.0
        self.LeafPosition = 0
        self.LeafsPerNode = 0
        self.LeafInternodeLength = 0.0
        self.LeafMinSegmentOrder = 0
        self.LeafWidht = 0.0
        self.LeafLength = 0.0
        self.LeafSurface = 0.0
        self.PetioleAngle = 0.0
        self.PetioleLength = 0.0
        self.LeafRotationAngle = 0.0
        self.FactorHorizontal = 0.0
        self.TropismVector = (0.0, 0.0, 0.0)
        self.TropismElasticity = 0.0
        self.SegmentRemovallist = []
        self.NrRules = 0
        self.Rules_Variable = ''
        self.Rules_Replacement = ''
        self.Rules_Condition = ''
        self.Rules_isConditional = ''
        self.Rules_Remark = ''
        self.TermLString = ''
        self.ApplyTermLString = 0

    def convert_lad_profile_to_numpy(self):
        self.LAD_Profile = np.asarray(self.LAD_Profile)
