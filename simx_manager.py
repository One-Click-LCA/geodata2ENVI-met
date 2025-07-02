import numpy as np
from datetime import datetime


class SIMX:
    def __init__(self):
        self.mainData = simx_mainData()
        self.TThread = simx_TThread()
        self.ModelTiming = simx_ModelTiming()
        self.Soil = simx_Soil()
        self.Sources = simx_Sources()
        self.Turbulence = simx_Turbulence()

        # if simple forcing is selected
        self.SimpleForcing = simx_SimpleForcing()
        # if open/cyclic is selected
        self.LBC = simx_LBC()
        # if full forcing is selected
        self.FullForcing = simx_FullForcing()

        self.TimeSteps = simx_TimeSteps()
        self.OutputSettings = simx_OutputSettings()
        self.Clouds = simx_Clouds()
        self.Background = simx_Background()
        self.SolarAdjust = simx_SolarAdjust()
        self.Building = simx_Building()
        self.RadScheme = simx_RadScheme()
        self.Parallel = simx_Parallel()
        self.SOR = simx_SOR()
        self.InflowAvg = simx_InflowAvg()
        self.PlantModel = simx_PlantModel()
        self.Facades = simx_Facades()

        # meteo-settings
        self.SiFoSelected = False
        self.FuFoSelected = False
        self.otherSelected = False
        # optional settings
        self.SoilSelected = False
        self.RadiationSelected = False
        self.BuildingSelected = False
        self.PollutantsSelected = False
        self.PlantsSelected = False
        self.TimingSelected = False
        self.OutputSelected = False
        self.ExpertSelected = False

    def load_simx(self, file_path: str):
        simx_file = open(file_path, 'r')
        section = ''
        for row in simx_file:
            # we check for the section we are currently iterating over to ignore duplicate namings of variables
            # in different sections and correctly assign the right value to each variable, even if variable names
            # repeat in different sections.
            if '<mainData>' in row:
                section = 'mainData'
            elif '<TThread>' in row:
                section = 'TThread'
            elif '<ModelTiming>' in row:
                section = 'ModelTiming'
            elif '<Soil>' in row:
                section = 'Soil'
            elif '<Sources>' in row:
                section = 'Sources'
            elif '<Turbulence>' in row:
                section = 'Turbulence'
            elif '<FullForcing>' in row:
                section = 'FullForcing'
            elif '<SimpleForcing>' in row:
                section = 'SimpleForcing'
            elif '<LBC>' in row:
                section = 'LBC'
            elif '<TimeSteps>' in row:
                section = 'TimeSteps'
            elif '<OutputSettings>' in row:
                section = 'OutputSettings'
            elif '<Clouds>' in row:
                section = 'Clouds'
            elif '<Background>' in row:
                section = 'Background'
            elif '<SolarAdjust>' in row:
                section = 'SolarAdjust'
            elif '<Building>' in row:
                section = 'Building'
            elif '<RadScheme>' in row:
                section = 'RadScheme'
            elif '<Parallel>' in row:
                section = 'Parallel'
            elif '<SOR>' in row:
                section = 'SOR'
            elif '<InflowAvg>' in row:
                section = 'InflowAvg'
            elif '<PlantModel>' in row:
                section = 'PlantModel'
            elif '<Facades>' in row:
                section = 'Facades'

            # find and assign the values
            if section == 'mainData':
                if '<simName>' in row:
                    self.mainData.simName = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<INXFile>' in row:
                    self.mainData.INXfile = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<filebaseName>' in row:
                    self.mainData.filebaseName = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<outDir>' in row:
                    self.mainData.outDir = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<startDate>' in row:
                    self.mainData.startDate = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<startTime>' in row:
                    self.mainData.startTime = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<simDuration>' in row:
                    self.mainData.simDuration = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<windSpeed>' in row:
                    self.mainData.windSpeed = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<windDir>' in row:
                    self.mainData.windDir = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<z0>' in row:
                    self.mainData.z0 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<T_H>' in row:
                    self.mainData.T_H = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<Q_H>' in row:
                    self.mainData.Q_H = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<Q_2m>' in row:
                    self.mainData.Q_2m = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'TThread':
                if not self.ExpertSelected:
                    self.ExpertSelected = True

                if '<UseTThread_CallMain>' in row:
                    self.TThread.UseTThread_CallMain = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<TThreadPRIO>' in row:
                    self.TThread.TThreadPRIO = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'ModelTiming':
                if not self.TimingSelected:
                    self.TimingSelected = True

                if '<surfaceSteps>' in row:
                    self.ModelTiming.surfaceSteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<flowSteps>' in row:
                    self.ModelTiming.flowSteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<radiationSteps>' in row:
                    self.ModelTiming.radiationSteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<plantSteps>' in row:
                    self.ModelTiming.plantSteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<sourcesSteps>' in row:
                    self.ModelTiming.sourceSteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Soil':
                if not self.SoilSelected:
                    self.SoilSelected = True

                if '<tempUpperlayer>' in row:
                    self.Soil.tempUpperlayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<tempMiddlelayer>' in row:
                    self.Soil.tempMiddlelayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<tempDeeplayer>' in row:
                    self.Soil.tempDeeplayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<tempBedrockLayer>' in row:
                    self.Soil.tempBedrocklayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<waterUpperlayer>' in row:
                    self.Soil.waterUpperlayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<waterMiddlelayer>' in row:
                    self.Soil.waterMiddlelayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<waterDeeplayer>' in row:
                    self.Soil.waterDeeplayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<waterBedrockLayer>' in row:
                    self.Soil.waterBedrocklayer = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Sources':
                if not self.PollutantsSelected:
                    self.PollutantsSelected = True

                if '<userPolluName>' in row:
                    self.Sources.userPolluName = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<userPolluType>' in row:
                    self.Sources.userPolluType = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<userPartDiameter>' in row:
                    self.Sources.userPartDiameter = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<userPartDensity>' in row:
                    self.Sources.userPartDensity = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<multipleSources>' in row:
                    self.Sources.multipleSources = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<activeChem>' in row:
                    self.Sources.activeChem = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<isoprene>' in row:
                    self.Sources.isoprene = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Turbulence':
                if not self.ExpertSelected:
                    self.ExpertSelected = True

                if '<turbulenceModel>' in row:
                    self.Turbulence.turbulenceModel = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<TKELimit>' in row:
                    self.Turbulence.TKELimit = int(row.split(">", 1)[1].split("<", 1)[0].strip())                    
            elif section == 'FullForcing':
                if not self.FuFoSelected:
                    self.FuFoSelected = True
                if '<fileName>' in row:
                    self.FullForcing.fileName = row.split(">", 1)[1].split("<", 1)[0].strip()
                elif '<forceT>' in row:
                    self.FullForcing.forceT = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<forceQ>' in row:
                    self.FullForcing.forceQ = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<forceWind>' in row:
                    self.FullForcing.forceWind = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<forcePrecip>' in row:
                    self.FullForcing.forcePrecip = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<forceRadClouds>' in row:
                    self.FullForcing.forceRadClouds = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<interpolationMethod>' in row:
                    self.FullForcing.interpolationMethod = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<nudging>' in row:
                    self.FullForcing.nudging = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<nudgingFactor>' in row:
                    self.FullForcing.nudgingFactor = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<minFlowsteps>' in row:
                    self.FullForcing.minFlowsteps = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<limitWind2500>' in row:
                    self.FullForcing.limitWind2500 = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<maxWind2500>' in row:
                    self.FullForcing.maxWind2500 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<z_0>' in row:
                    self.FullForcing.z_0 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'SimpleForcing':
                if not self.SiFoSelected:
                    self.SiFoSelected = True

                if '<TAir>' in row:
                    self.SimpleForcing.TAir = np.asarray([float(x) for x in row.split(">", 1)[1].split("<", 1)[0].strip().split(",")], dtype=float)
                elif '<Qrel>' in row:
                    self.SimpleForcing.Qrel = np.asarray([float(x) for x in row.split(">", 1)[1].split("<", 1)[0].strip().split(",")], dtype=float)
            elif section == 'LBC':
                if not self.otherSelected:
                    self.otherSelected = True

                if '<LBC_TQ>' in row:
                    self.LBC.LBC_TQ = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<LBC_TKE>' in row:
                    self.LBC.LBC_TKE = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'TimeSteps':
                if '<sunheight_step01>' in row:
                    self.TimeSteps.sunheight_step01 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<sunheight_step02>' in row:
                    self.TimeSteps.sunheight_step02 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<dt_step00>' in row:
                    self.TimeSteps.dt_step00 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<dt_step01>' in row:
                    self.TimeSteps.dt_step01 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<dt_step02>' in row:
                    self.TimeSteps.dt_step02 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'OutputSettings':
                if not self.OutputSelected:
                    self.OutputSelected = True

                if '<mainFiles>' in row:
                    self.OutputSettings.mainFiles = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<textFiles>' in row:
                    self.OutputSettings.textFiles = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<netCDF>' in row:
                    self.OutputSettings.netCDF = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<netCDFAllDataInOneFile>' in row:
                    self.OutputSettings.netCDFAllDataInOneFile = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<netCDFWriteOnlySmallFile>' in row:
                    self.OutputSettings.netCDFWriteOnlySmallFile = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<inclNestingGrids>' in row:
                    self.OutputSettings.inclNestingGrids = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeAgents>' in row:
                    self.OutputSettings.writeAgents = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeAtmosphere>' in row:
                    self.OutputSettings.writeAtmosphere = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeBuildings>' in row:
                    self.OutputSettings.writeBuildings = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeObjects>' in row:
                    self.OutputSettings.writeObjects = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeGreenpass>' in row:
                    self.OutputSettings.writeGreenpass = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeNesting>' in row:
                    self.OutputSettings.writeNesting = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeRadiation>' in row:
                    self.OutputSettings.writeRadiation = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeSoil>' in row:
                    self.OutputSettings.writeSoil = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeSolarAccess>' in row:
                    self.OutputSettings.writeSolarAccess = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeSurface>' in row:
                    self.OutputSettings.writeSurface = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<writeVegetation>' in row:
                    self.OutputSettings.writeVegetation = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Clouds':
                if '<lowClouds>' in row:
                    self.Clouds.lowClouds = round(float(row.split(">", 1)[1].split("<", 1)[0].strip()))
                elif '<middleClouds>' in row:
                    self.Clouds.middleClouds = round(float(row.split(">", 1)[1].split("<", 1)[0].strip()))
                elif '<highClouds>' in row:
                    self.Clouds.highClouds = round(float(row.split(">", 1)[1].split("<", 1)[0].strip()))
            elif section == 'Background':
                if not self.PollutantsSelected:
                    self.PollutantsSelected = True

                if '<userSpec>' in row:
                    self.Background.userSpec = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<NO>' in row:
                    self.Background.NO = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<NO2>' in row:
                    self.Background.NO2 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<O3>' in row:
                    self.Background.O3 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<PM_10>' in row:
                    self.Background.PM_10 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<PM_2_5>' in row:
                    self.Background.PM_2_5 = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'SolarAdjust':
                if not self.RadiationSelected:
                    self.RadiationSelected = True

                if '<SWFactor>' in row:
                    self.SolarAdjust.SWFactor = float(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Building':
                if not self.BuildingSelected:
                    self.BuildingSelected = True

                if '<indoorTemp>' in row:
                    self.Building.indoorTemp = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<surfaceTemp>' in row:
                    self.Building.surfTemp = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<indoorConst>' in row:
                    self.Building.indoorConst = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<airConHeat>' in row:
                    self.Building.airConHeat = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'RadScheme':
                if not self.RadiationSelected:
                    self.RadiationSelected = True

                if '<IVSHeightAngle_HiRes>' in row:
                    self.RadScheme.IVSHeightAngle_HiRes = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<IVSAziAngle_HiRes>' in row:
                    self.RadScheme.IVSAziAngle_HiRes = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<IVSHeightAngle_LoRes>' in row:
                    self.RadScheme.IVSHeightAngle_LoRes = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<IVSAziAngle_LoRes>' in row:
                    self.RadScheme.IVSAziAngle_LoRes = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<AdvCanopyRadTransfer>' in row:
                    self.RadScheme.AdvCanopyRadTransfer = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<ViewFacUpdateInterval>' in row:
                    self.RadScheme.ViewFacUpdateInterval = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<RayTraceStepWidthHighRes>' in row:
                    self.RadScheme.RayTraceStepWidthHighRes = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<RayTraceStepWidthLowRes>' in row:
                    self.RadScheme.RayTraceStepWidthLowRes = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<RadiationHeightBoundary>' in row:
                    self.RadScheme.RadiationHeightBoundary = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<MRTCalcMethod>' in row:
                    self.RadScheme.MRTCalcMethod = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<MRTProjFac>' in row:
                    self.RadScheme.MRTProjFac = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Parallel':
                if '<CPUdemand>' in row:
                    self.Parallel.CPUdemand = row.split(">", 1)[1].split("<", 1)[0].strip()
            elif section == 'SOR':
                if not self.ExpertSelected:
                    self.ExpertSelected = True

                if '<SORMode>' in row:
                    self.SOR.SORMode = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'InflowAvg':
                if not self.ExpertSelected:
                    self.ExpertSelected = True

                if '<inflowAvg>' in row:
                    self.InflowAvg.inflowAvg = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'PlantModel':
                if not self.PlantsSelected:
                    self.PlantsSelected = True

                if '<CO2BackgroundPPM>' in row:
                    self.PlantModel.CO2BackgroundPPM = float(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<LeafTransmittance>' in row:
                    self.PlantModel.LeafTransmittance = int(row.split(">", 1)[1].split("<", 1)[0].strip())
                elif '<TreeCalendar>' in row:
                    self.PlantModel.TreeCalendar = int(row.split(">", 1)[1].split("<", 1)[0].strip())
            elif section == 'Facades':
                if not self.ExpertSelected:
                    self.ExpertSelected = True

                if '<FacadeMode>' in row:
                    self.Facades.FacadeMode = int(row.split(">", 1)[1].split("<", 1)[0].strip())

        simx_file.close()

    def save_simx(self, file_path: str):
        # get date and time
        now = datetime.now()
        date_time = now.strftime("%d.%m.%Y %H:%M:%S")

        # get SiFo-arrays as strings
        if self.SiFoSelected:
            SiFo_TAir_str = np.array2string(self.SimpleForcing.TAir, max_line_width=1000000, separator=',', precision=5, floatmode='fixed')
            SiFo_TAir_str = SiFo_TAir_str.replace(" ", "").replace("[", "").replace("]", "")
            SiFo_Qrel_str = np.array2string(self.SimpleForcing.Qrel, max_line_width=1000000, separator=',', precision=5, floatmode='fixed')
            SiFo_Qrel_str = SiFo_Qrel_str.replace(" ", "").replace("[", "").replace("]", "")

        with open(file_path, 'w') as output_file:
            # Header
            print("<ENVI-MET_Datafile>", file=output_file)
            print("<Header>", file=output_file)
            print("<filetype>SIMX</filetype>", file=output_file)
            print("<version>2</version>", file=output_file)
            print(f"<revisiondate>{date_time}</revisiondate>", file=output_file)
            print("<remark></remark>", file=output_file)
            print("<checksum>0</checksum>", file=output_file)
            print("<encryptionlevel>0</encryptionlevel>", file=output_file)
            print("</Header>", file=output_file)
            # mainData
            print("  <mainData>", file=output_file)
            print(f"     <simName> {self.mainData.simName} </simName>", file=output_file)
            print(f"     <INXFile> {self.mainData.INXfile} </INXFile>", file=output_file)
            print(f"     <filebaseName> {self.mainData.filebaseName} </filebaseName>", file=output_file)
            print(f"     <outDir> {self.mainData.outDir} </outDir>", file=output_file)
            print(f"     <startDate> {self.mainData.startDate} </startDate>", file=output_file)
            print(f"     <startTime> {self.mainData.startTime} </startTime>", file=output_file)
            print(f"     <simDuration> {self.mainData.simDuration} </simDuration>", file=output_file)
            print(f"     <windSpeed> {self.mainData.windSpeed} </windSpeed>", file=output_file)
            print(f"     <windDir> {self.mainData.windDir} </windDir>", file=output_file)
            print(f"     <z0> {self.mainData.z0} </z0>", file=output_file)
            print(f"     <T_H> {self.mainData.T_H} </T_H>", file=output_file)
            print(f"     <Q_H> {self.mainData.Q_H} </Q_H>", file=output_file)
            print(f"     <Q_2m> {self.mainData.Q_2m} </Q_2m>", file=output_file)
            print("  </mainData>", file=output_file)
            # TThread
            if self.ExpertSelected:
                print("  <TThread>", file=output_file)
                print(f"     <UseTThread_CallMain> {self.TThread.UseTThread_CallMain} </UseTThread_CallMain>", file=output_file)
                print(f"     <TThreadPRIO> {self.TThread.TThreadPRIO} </TThreadPRIO>", file=output_file)
                print("  </TThread>", file=output_file)
            # ModelTiming
            if self.TimingSelected:
                print("  <ModelTiming>", file=output_file)
                print(f"     <surfaceSteps> {self.ModelTiming.surfaceSteps} </surfaceSteps>", file=output_file)
                print(f"     <flowSteps> {self.ModelTiming.flowSteps} </flowSteps>", file=output_file)
                print(f"     <radiationSteps> {self.ModelTiming.radiationSteps} </radiationSteps>", file=output_file)
                print(f"     <plantSteps> {self.ModelTiming.plantSteps} </plantSteps>", file=output_file)
                print(f"     <sourcesSteps> {self.ModelTiming.sourceSteps} </sourcesSteps>", file=output_file)
                print("  </ModelTiming>", file=output_file)
            # Soil
            if self.SoilSelected:
                print("  <Soil>", file=output_file)
                print(f"     <tempUpperlayer> {self.Soil.tempUpperlayer} </tempUpperlayer>", file=output_file)
                print(f"     <tempMiddlelayer> {self.Soil.tempMiddlelayer} </tempMiddlelayer>", file=output_file)
                print(f"     <tempDeeplayer> {self.Soil.tempDeeplayer} </tempDeeplayer>", file=output_file)
                print(f"     <tempBedrockLayer> {self.Soil.tempBedrocklayer} </tempBedrockLayer>", file=output_file)
                print(f"     <waterUpperlayer> {self.Soil.waterUpperlayer} </waterUpperlayer>", file=output_file)
                print(f"     <waterMiddlelayer> {self.Soil.waterMiddlelayer} </waterMiddlelayer>", file=output_file)
                print(f"     <waterDeeplayer> {self.Soil.waterDeeplayer} </waterDeeplayer>", file=output_file)
                print(f"     <waterBedrockLayer> {self.Soil.waterBedrocklayer} </waterBedrockLayer>", file=output_file)
                print("  </Soil>", file=output_file)
            # Sources
            if self.PollutantsSelected:
                print("  <Sources>", file=output_file)
                print(f"     <userPolluName> {self.Sources.userPolluName} </userPolluName>", file=output_file)
                print(f"     <userPolluType> {self.Sources.userPolluType} </userPolluType>", file=output_file)
                print(f"     <userPartDiameter> {self.Sources.userPartDiameter} </userPartDiameter>", file=output_file)
                print(f"     <userPartDensity> {self.Sources.userPartDensity} </userPartDensity>", file=output_file)
                print(f"     <multipleSources> {self.Sources.multipleSources} </multipleSources>", file=output_file)
                print(f"     <activeChem> {self.Sources.activeChem} </activeChem>", file=output_file)
                print(f"     <isoprene> {self.Sources.isoprene} </isoprene>", file=output_file)
                print("  </Sources>", file=output_file)
            # Turbulence
            if self.ExpertSelected:
                print("  <Turbulence>", file=output_file)
                print(f"     <turbulenceModel> {self.Turbulence.turbulenceModel} </turbulenceModel>", file=output_file)
                print(f"     <TKELimit> {self.Turbulence.TKELimit} </TKELimit>", file=output_file)
                print("  </Turbulence>", file=output_file)
            # Simple Forcing
            if self.SiFoSelected:
                print("  <SimpleForcing>", file=output_file)
                print(f"     <TAir> {SiFo_TAir_str} </TAir>", file=output_file)
                print(f"     <Qrel> {SiFo_Qrel_str} </Qrel>", file=output_file)
                print("  </SimpleForcing>", file=output_file)
            # Full Forcing
            elif self.FuFoSelected:
                print("  <FullForcing>", file=output_file)
                print(f"     <fileName> {self.FullForcing.fileName} </fileName>", file=output_file)
                print(f"     <forceT> {self.FullForcing.forceT} </forceT>", file=output_file)
                print(f"     <forceQ> {self.FullForcing.forceQ} </forceQ>", file=output_file)
                print(f"     <forceWind> {self.FullForcing.forceWind} </forceWind>", file=output_file)
                print(f"     <forcePrecip> {self.FullForcing.forcePrecip} </forcePrecip>", file=output_file)
                print(f"     <forceRadClouds> {self.FullForcing.forceRadClouds} </forceRadClouds>", file=output_file)
                print(f"     <interpolationMethod> {self.FullForcing.interpolationMethod} </interpolationMethod>", file=output_file)
                print(f"     <nudging> {self.FullForcing.nudging} </nudging>", file=output_file)
                print(f"     <nudgingFactor> {self.FullForcing.nudgingFactor} </nudgingFactor>", file=output_file)
                print(f"     <minFlowsteps> {self.FullForcing.minFlowsteps} </minFlowsteps>", file=output_file)
                print(f"     <limitWind2500> {self.FullForcing.limitWind2500} </limitWind2500>", file=output_file)
                print(f"     <maxWind2500> {self.FullForcing.maxWind2500} </maxWind2500>", file=output_file)
                print(f"     <z_0> {self.FullForcing.z_0} </z_0>", file=output_file)
                print("  </FullForcing>", file=output_file)
            # Open / Cyclic
            elif self.otherSelected:
                print("  <LBC>", file=output_file)
                print(f"     <LBC_TQ> {self.LBC.LBC_TQ} </LBC_TQ>", file=output_file)
                print(f"     <LBC_TKE> {self.LBC.LBC_TKE} </LBC_TKE>", file=output_file)
                print("  </LBC>", file=output_file)
            # TimeSteps
            if self.TimingSelected:
                print("  <TimeSteps>", file=output_file)
                print(f"     <sunheight_step01> {self.TimeSteps.sunheight_step01} </sunheight_step01>", file=output_file)
                print(f"     <sunheight_step02> {self.TimeSteps.sunheight_step02} </sunheight_step02>", file=output_file)
                print(f"     <dt_step00> {self.TimeSteps.dt_step00} </dt_step00>", file=output_file)
                print(f"     <dt_step01> {self.TimeSteps.dt_step01} </dt_step01>", file=output_file)
                print(f"     <dt_step02> {self.TimeSteps.dt_step02} </dt_step02>", file=output_file)
                print("  </TimeSteps>", file=output_file)
            # OutputSettings
            if self.OutputSelected:
                print("  <OutputSettings>", file=output_file)
                print(f"     <mainFiles> {self.OutputSettings.mainFiles} </mainFiles>", file=output_file)
                print(f"     <textFiles> {self.OutputSettings.textFiles} </textFiles>", file=output_file)
                print(f"     <netCDF> {self.OutputSettings.netCDF} </netCDF>", file=output_file)
                print(f"     <netCDFAllDataInOneFile> {self.OutputSettings.netCDFAllDataInOneFile} </netCDFAllDataInOneFile>", file=output_file)
                print(f"     <netCDFWriteOnlySmallFile> {self.OutputSettings.netCDFWriteOnlySmallFile} </netCDFWriteOnlySmallFile>", file=output_file)
                print(f"     <inclNestingGrids> {self.OutputSettings.inclNestingGrids} </inclNestingGrids>", file=output_file)
                print(f"     <writeAgents> {self.OutputSettings.writeAgents} </writeAgents>", file=output_file)
                print(f"     <writeAtmosphere> {self.OutputSettings.writeAtmosphere} </writeAtmosphere>", file=output_file)
                print(f"     <writeBuildings> {self.OutputSettings.writeBuildings} </writeBuildings>", file=output_file)
                print(f"     <writeObjects> {self.OutputSettings.writeObjects} </writeObjects>", file=output_file)
                print(f"     <writeGreenpass> {self.OutputSettings.writeGreenpass} </writeGreenpass>", file=output_file)
                print(f"     <writeNesting> {self.OutputSettings.writeNesting} </writeNesting>", file=output_file)
                print(f"     <writeRadiation> {self.OutputSettings.writeRadiation} </writeRadiation>", file=output_file)
                print(f"     <writeSoil> {self.OutputSettings.writeSoil} </writeSoil>", file=output_file)
                print(f"     <writeSolarAccess> {self.OutputSettings.writeSolarAccess} </writeSolarAccess>", file=output_file)
                print(f"     <writeSurface> {self.OutputSettings.writeSurface} </writeSurface>", file=output_file)
                print(f"     <writeVegetation> {self.OutputSettings.writeVegetation} </writeVegetation>", file=output_file)
                print("  </OutputSettings>", file=output_file)
            # Clouds
            if self.SiFoSelected or self.otherSelected or (self.FuFoSelected and (self.FullForcing.forceRadClouds == 0)):
                print("  <Clouds>", file=output_file)
                print(f"     <lowClouds> {self.Clouds.lowClouds} </lowClouds>", file=output_file)
                print(f"     <middleClouds> {self.Clouds.middleClouds} </middleClouds>", file=output_file)
                print(f"     <highClouds> {self.Clouds.highClouds} </highClouds>", file=output_file)
                print("  </Clouds>", file=output_file)
            # Background
            if self.PollutantsSelected:
                print("  <Background>", file=output_file)
                print(f"     <userSpec> {self.Background.userSpec} </userSpec>", file=output_file)
                print(f"     <NO> {self.Background.NO} </NO>", file=output_file)
                print(f"     <NO2> {self.Background.NO2} </NO2>", file=output_file)
                print(f"     <O3> {self.Background.O3} </O3>", file=output_file)
                print(f"     <PM_10> {self.Background.PM_10} </PM_10>", file=output_file)
                print(f"     <PM_2_5> {self.Background.PM_2_5} </PM_2_5>", file=output_file)
                print("  </Background>", file=output_file)
            # SolarAdjust
            if self.RadiationSelected:
                print("  <SolarAdjust>", file=output_file)
                print(f"     <SWFactor> {self.SolarAdjust.SWFactor} </SWFactor>", file=output_file)
                print("  </SolarAdjust>", file=output_file)
            # Buildings
            if self.BuildingSelected:
                print("  <Building>", file=output_file)
                print(f"     <surfaceTemp> {self.Building.surfTemp} </surfaceTemp>", file=output_file)
                print(f"     <indoorTemp> {self.Building.indoorTemp} </indoorTemp>", file=output_file)
                print(f"     <indoorConst> {self.Building.indoorConst} </indoorConst>", file=output_file)
                print(f"     <airConHeat> {self.Building.airConHeat} </airConHeat>", file=output_file)
                print("  </Building>", file=output_file)
            # RadScheme
            if self.RadiationSelected:
                print("  <RadScheme>", file=output_file)
                print(f"     <IVSHeightAngle_HiRes> {self.RadScheme.IVSHeightAngle_HiRes} </IVSHeightAngle_HiRes>", file=output_file)
                print(f"     <IVSAziAngle_HiRes> {self.RadScheme.IVSAziAngle_HiRes} </IVSAziAngle_HiRes>", file=output_file)
                print(f"     <IVSHeightAngle_LoRes> {self.RadScheme.IVSHeightAngle_LoRes} </IVSHeightAngle_LoRes>", file=output_file)
                print(f"     <IVSAziAngle_LoRes> {self.RadScheme.IVSAziAngle_LoRes} </IVSAziAngle_LoRes>", file=output_file)
                print(f"     <AdvCanopyRadTransfer> {self.RadScheme.AdvCanopyRadTransfer} </AdvCanopyRadTransfer>", file=output_file)
                print(f"     <ViewFacUpdateInterval> {self.RadScheme.ViewFacUpdateInterval} </ViewFacUpdateInterval>", file=output_file)
                print(f"     <RayTraceStepWidthHighRes> {self.RadScheme.RayTraceStepWidthHighRes} </RayTraceStepWidthHighRes>", file=output_file)
                print(f"     <RayTraceStepWidthLowRes> {self.RadScheme.RayTraceStepWidthLowRes} </RayTraceStepWidthLowRes>", file=output_file)
                print(f"     <RadiationHeightBoundary> {self.RadScheme.RadiationHeightBoundary} </RadiationHeightBoundary>", file=output_file)
                print(f"     <MRTCalcMethod> {self.RadScheme.MRTCalcMethod} </MRTCalcMethod>", file=output_file)
                print(f"     <MRTProjFac> {self.RadScheme.MRTProjFac} </MRTProjFac>", file=output_file)
                print("  </RadScheme>", file=output_file)
            # Parallel
            print("  <Parallel>", file=output_file)
            print(f"     <CPUdemand> {self.Parallel.CPUdemand} </CPUdemand>", file=output_file)
            print("  </Parallel>", file=output_file)
            # SOR
            if self.ExpertSelected:
                print("  <SOR>", file=output_file)
                print(f"     <SORMode> {self.SOR.SORMode} </SORMode>", file=output_file)
                print("  </SOR>", file=output_file)
            # InflowAvg
            if self.ExpertSelected:
                print("  <InflowAvg>", file=output_file)
                print(f"     <inflowAvg> {self.InflowAvg.inflowAvg} </inflowAvg>", file=output_file)
                print("  </InflowAvg>", file=output_file)
            # Plants
            if self.PlantsSelected:
                print("  <PlantModel>", file=output_file)
                print(f"     <CO2BackgroundPPM> {self.PlantModel.CO2BackgroundPPM} </CO2BackgroundPPM>", file=output_file)
                print(f"     <LeafTransmittance> {self.PlantModel.LeafTransmittance} </LeafTransmittance>", file=output_file)
                print(f"     <TreeCalendar> {self.PlantModel.TreeCalendar} </TreeCalendar>", file=output_file)
                print("  </PlantModel>", file=output_file)
            # Facades
            if self.ExpertSelected:
                print("  <Facades>", file=output_file)
                print(f"     <FacadeMode> {self.Facades.FacadeMode} </FacadeMode>", file=output_file)
                print("  </Facades>", file=output_file)
            print("</ENVI-MET_Datafile>", file=output_file)


class simx_mainData:
    def __init__(self):
        self.simName = ''
        self.INXfile = ''
        self.filebaseName = ''
        self.outDir = ''
        self.startDate = ''
        self.startTime = '05:00:00'
        self.simDuration = 24
        self.windSpeed = 1.5
        self.windDir = 270.0
        self.z0 = 0.1000
        self.T_H = 293.15
        self.Q_H = 8.0
        self.Q_2m = 50.0


class simx_TThread:
    def __init__(self):
        self.UseTThread_CallMain = 0
        self.TThreadPRIO = 5


class simx_ModelTiming:
    def __init__(self):
        self.surfaceSteps = 30
        self.flowSteps = 900
        self.radiationSteps = 600
        self.plantSteps = 600
        self.sourceSteps = 600


class simx_Soil:
    def __init__(self):
        self.tempUpperlayer = 293.14999
        self.tempMiddlelayer = 293.14999
        self.tempDeeplayer = 293.14999
        self.tempBedrocklayer = 293.14999
        self.waterUpperlayer = 65.0
        self.waterMiddlelayer = 70.0
        self.waterDeeplayer = 75.0
        self.waterBedrocklayer = 75.0


class simx_Sources:
    def __init__(self):
        self.userPolluName = ''
        self.userPolluType = 1
        self.userPartDiameter = 10.0
        self.userPartDensity = 1.0
        self.multipleSources = 1
        self.activeChem = 1
        self.isoprene = 0


class simx_Turbulence:
    def __init__(self):
        self.turbulenceModel = 3
        self.TKELimit = 1


class simx_SimpleForcing:
    def __init__(self):
        self.TAir = np.empty(shape=24, dtype=float)
        self.Qrel = np.empty(shape=24, dtype=float)


class simx_TimeSteps:
    def __init__(self):
        self.sunheight_step01 = 40.0
        self.sunheight_step02 = 50.0
        self.dt_step00 = 2.0
        self.dt_step01 = 2.0
        self.dt_step02 = 1.0


class simx_OutputSettings:
    def __init__(self):
        self.mainFiles = 60
        self.textFiles = 30
        self.netCDF = 1
        self.netCDFAllDataInOneFile = 1
        self.netCDFWriteOnlySmallFile = 0
        self.inclNestingGrids = 1
        self.writeAgents = 0
        self.writeAtmosphere = 1
        self.writeBuildings = 1
        self.writeObjects = 0
        self.writeGreenpass = 0
        self.writeNesting = 0
        self.writeRadiation = 1
        self.writeSoil = 1
        self.writeSolarAccess = 1
        self.writeSurface = 1
        self.writeVegetation = 1


class simx_Clouds:
    def __init__(self):
        self.lowClouds = 0
        self.middleClouds = 0
        self.highClouds = 0


class simx_Background:
    def __init__(self):
        self.userSpec = 30.0
        self.NO = 80.0
        self.NO2 = 70.0
        self.O3 = 60.0
        self.PM_10 = 50.0
        self.PM_2_5 = 40.0


class simx_SolarAdjust:
    def __init__(self):
        self.SWFactor = 1.0


class simx_Building:
    def __init__(self):
        self.indoorTemp = 293.14999
        self.surfTemp = 293.14999
        self.indoorConst = 0
        self.airConHeat = 0


class simx_RadScheme:
    def __init__(self):
        self.IVSHeightAngle_HiRes = 30
        self.IVSAziAngle_HiRes = 30
        self.IVSHeightAngle_LoRes = 45
        self.IVSAziAngle_LoRes = 45
        self.AdvCanopyRadTransfer = 1
        self.ViewFacUpdateInterval = 10
        self.RayTraceStepWidthHighRes = 0.25
        self.RayTraceStepWidthLowRes = 0.5
        self.RadiationHeightBoundary = 10.0
        self.MRTCalcMethod = 1
        self.MRTProjFac = 2


class simx_Parallel:
    def __init__(self):
        self.CPUdemand = 'ALL'


class simx_SOR:
    def __init__(self):
        self.SORMode = 1


class simx_InflowAvg:
    def __init__(self):
        self.inflowAvg = 1


class simx_PlantModel:
    def __init__(self):
        self.CO2BackgroundPPM = 450.0
        self.LeafTransmittance = 1
        self.TreeCalendar = 1


class simx_Facades:
    def __init__(self):
        self.FacadeMode = 1


class simx_LBC:
    def __init__(self):
        self.LBC_TQ = 1
        self.LBC_TKE = 1


class simx_FullForcing:
    def __init__(self):
        self.fileName = ''
        self.forceQ = 1
        self.forceT = 1
        self.forceWind = 1
        self.forcePrecip = 1
        self.forceRadClouds = 1
        self.interpolationMethod = 0
        self.nudging = 0
        self.nudgingFactor = 1.0
        self.minFlowsteps = 50
        self.limitWind2500 = 0
        self.maxWind2500 = 999.0
        self.z_0 = 0.10
