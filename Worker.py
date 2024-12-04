import math

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant, QThread, pyqtSignal
from qgis.core import QgsProject, Qgis, QgsField, QgsMapLayerProxyModel, QgsPoint, QgsPointXY, QgsVectorLayer, QgsRectangle, \
    QgsFeatureRequest, QgsFieldProxyModel, QgsMessageLog, QgsRasterLayer, QgsMapSettings, QgsPolygon, QgsGeometry, QgsFeature, \
    QgsCoordinateReferenceSystem, QgsRasterFileWriter, QgsRasterPipe, QgsRaster, QgsRasterBlock, QgsSingleBandGrayRenderer, \
    QgsContrastEnhancement, QgsRasterBandStats, QgsProcessing, QgsVectorFileWriter, QgsProviderRegistry, QgsGeometryUtils
from qgis.PyQt.QtCore import *
# Import necessary QGIS classes
from PyQt5.QtCore import QPointF, QSizeF, QRectF, QSize
from PyQt5.QtGui import QColor, QImage, QImageWriter, QPainter
# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .geodata2ENVImet_dialog import Geo2ENVImetDialog
import processing
from processing.tools import dataobjects
import pyproj
from pyproj.database import query_utm_crs_info
from osgeo import gdal, gdal_array, osr
import sys
from math import degrees, floor, trunc, sqrt, acos
import xml.etree.ElementTree as ET
import requests
from .ENVImet_DB_loader import *
from .simx_manager import *
from .EDX_EDT import *
import numpy as np

#import utm

# performance testing
import time


class Building:
    def __init__(self, BldInternalNum, BldName, BldWallMat, BldRoofMat, BldFacadeGreen, BldRoofGreen, BldBPS, BldInModelArea):
        self.BuildingInternalNumber = BldInternalNum
        self.BuildingName = BldName
        self.BuildingWallMaterial = BldWallMat
        self.BuildingRoofMaterial = BldRoofMat
        self.BuildingFacadeGreening = BldFacadeGreen
        self.BuildingRoofGreening = BldRoofGreen
        self.BuildingBPS = BldBPS
        self.BuildingInModelArea = BldInModelArea


class TmpTree3D:
    def __init__(self, enviID, obs):
        self.enviID = enviID
        self.obs = obs


class Cell:
    def __init__(self, i, j, k):
        self.i = i
        self.j = j
        self.k = k


class BLevel:
    def __init__(self, bNumber):
        self.bNumber = bNumber
        self.cellList = []


class Worker(QThread):
    finished = pyqtSignal()  # create a pyqtSignal for when task is finished
    progress = pyqtSignal(int)  # create a pyqtSignal to report the progress to progressbar

    def __init__(self):
        super(QThread, self).__init__()
        # initialize the stop variable
        self.stopworker = False

        self.msg = ""

        self.filename = ""
        self.II = 0
        self.JJ = 0
        self.KK = 0
        self.finalKK = 0
        self.dx = 3.0
        self.dy = 3.0
        self.dz = 3.0
        self.dzAr = np.zeros(1, dtype=float)
        self.zLvl_bot = np.zeros(1, dtype=float)
        self.zLvl_center = np.zeros(1, dtype=float)

        self.xMeters = 0.0
        self.yMeters = 0.0
        self.s_buildingDict = {}
        self.s_treeList = []
        self.s_recList = []
        self.model_rot = 0.0
        self.model_rot_center = QgsPoint(0, 0)
        self.subAreaLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.subAreaLayer_nonRot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.subAreaExtent = QgsRectangle(0, 0, 0, 0)

        self.bLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.bLayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.bTop = QgsField("notAvail", QVariant.Int)
        self.bBot = QgsField("notAvail", QVariant.Int)
        self.bName = QgsField("notAvail", QVariant.String)
        self.bWall = QgsField("notAvail", QVariant.String)
        self.bRoof = QgsField("notAvail", QVariant.String)
        self.bGreenWall = QgsField("notAvail", QVariant.String)
        self.bGreenRoof = QgsField("notAvail", QVariant.String)
        self.bBPS = QgsField("notAvail", QVariant.String)
        # custom fields
        self.bTop_custom = -999
        self.bBot_custom = -999
        self.bName_custom = "notAvail"
        self.bWall_custom = "notAvail"
        self.bRoof_custom = "notAvail"
        self.bGreenWall_custom = "notAvail"
        self.bGreenRoof_custom = "notAvail"
        self.bTop_UseCustom = False
        self.bBot_UseCustom = False
        self.bName_UseCustom = False
        self.bWall_UseCustom = False
        self.bRoof_UseCustom = False
        self.bGreenWall_UseCustom = False
        self.bGreenRoof_UseCustom = False
        self.bBPS_disabled = False

        self.surfLayerfromVector = True

        self.surfLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.surfLayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.surfID = QgsField("notAvail", QVariant.String)
        self.surfID_custom = "notAvail"
        self.surfID_UseCustom = False

        self.surfLayer_raster = QgsRasterLayer("", "notAvail")
        self.surfLayer_raster_rot = QgsRasterLayer("", "notAvail")
        self.surfLayer_raster_band = -1
        self.surfLayer_raster_def = {}

        self.plant1dLayerFromVector = True

        self.plant1dLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.plant1dLayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.plant1dID = QgsField("notAvail", QVariant.String)
        self.plant1dID_custom = "notAvail"
        self.plant1dID_UseCustom = False

        self.plant1dLayer_raster = QgsRasterLayer("", "notAvail")
        self.plant1dLayer_raster_rot = QgsRasterLayer("", "notAvail")
        self.plant1dLayer_raster_band = -1
        self.plant1dLayer_raster_def = {}

        self.plant3dLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.plant3dLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.plant3dID = QgsField("notAvail", QVariant.String)
        self.plant3dAddOut = QgsField("notAvail", QVariant.String)
        self.plant3dAddOut_disabled = False
        self.plant3dID_custom = "notAvail"
        self.plant3dID_UseCustom = False

        self.recLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.recLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.recID = QgsField("notAvail", QVariant.String)
        self.recID_custom = "notAvail"
        self.recID_UseCustom = False

        self.srcPLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.srcPLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.srcPID = QgsField("notAvail", QVariant.String)
        self.srcPID_custom = "notAvail"
        self.srcPID_UseCustom = False

        self.srcLLayer = QgsVectorLayer("Line", "notAvail", "memory")
        self.srcLLayer_rot = QgsVectorLayer("Line", "notAvail", "memory")
        self.srcLID = QgsField("notAvail", QVariant.String)
        self.srcLID_custom = "notAvail"
        self.srcLID_UseCustom = False

        self.srcALayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.srcALayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.srcAID = QgsField("notAvail", QVariant.String)
        self.srcAID_custom = "notAvail"
        self.srcAID_UseCustom = False

        self.dEMLayer = QgsRasterLayer("", "notAvail")
        self.dEMBand = -1
        self.dEMInterpol = 1

        self.lon = 0.0
        self.lat = 0.0
        self.UTMZone = -1
        self.UTMHemisphere = 'N'
        self.timeZoneName = ""
        self.timeZoneLonRef = 0.0
        self.elevation = -999
        self.refHeightDEM = 0
        self.maxHeightDEM = 0
        self.maxHeightB = 0
        self.maxHeightTotal = 0
        self.useSplitting = True
        self.useTelescoping = False
        self.teleStart = 0
        self.teleStretch = 0

        self.defaultRoof = "000000"
        self.defaultWall = "000000"
        self.removeBBorder = 5
        self.bLeveled = True
        self.bNOTFixedH = True
        self.startSurfID = "0200PP"
        self.removeVegBuild = True

        self.edt_data = []

        # Set the printoptions to maximum to print whole arrays of all following print functions
        np.set_printoptions(threshold=sys.maxsize)

    def rotate_layer(self, lay: QgsVectorLayer, is_sub_area_layer: bool):
        if (lay is None) or (lay.name() == "notAvail"):
            return ""
        xMin_s = self.model_rot_center.x()
        yMin_s = self.model_rot_center.y()
        epsg_s = lay.sourceCrs().authid()
        anch = str(xMin_s) + "," + str(yMin_s) + " [" + epsg_s + "]"

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        rlayer = processing.run("native:rotatefeatures",
                                {"INPUT": lay,
                                 "ANGLE": self.model_rot,
                                 "ANCHOR": anch,
                                 "OUTPUT": 'TEMPORARY_OUTPUT'},
                                context=context)
        rlayerFN = rlayer['OUTPUT']

        if is_sub_area_layer:
            # write layer to global var
            self.subAreaLayer = rlayerFN
            # calculate extent of first feature
            spFeats = self.subAreaLayer.getFeatures()
            for f in spFeats:
                if f.hasGeometry():
                    f_geo = f.geometry()
                    self.subAreaExtent = f_geo.boundingBox()
        return rlayerFN

    def get_modelrot(self):
        """
        All possible cases:

   1.   R1---------------R2         0:   checked    225: checked
        |                |          45:  checked    270: checked
        |                |          90:  checked    315: checked
        |                |          135: checked
        R0---------------R3         180: checked

   2.   R0---------------R1         0:   checked    225: checked
        |                |          45:  checked    270: checked
        |                |          90:  checked    315: checked
        |                |          135: checked
        R3---------------R2         180: checked

   3.   R3---------------R0         0:   checked    225: checked
        |                |          45:  checked    270: checked
        |                |          90:  checked    315: checked
        |                |          135: checked
        R2---------------R1         180: checked

   4.   R2---------------R3         0:   checked    225: checked
        |                |          45:  checked    270: checked
        |                |          90:  checked    315: checked
        |                |          135: checked
        R1---------------R0         180: checked

        -------------------------

   5.   R3---------------R2
        |                |
        |                |          -> Not creatable in QGIS, results in Rectangle 1
        |                |
        R0---------------R1

   6.   R0---------------R3
        |                |
        |                |          -> Not creatable in QGIS, results in Rectangle 2
        |                |
        R1---------------R2

   7.   R3---------------R0
        |                |
        |                |          checked
        |                |
        R2---------------R1

   8.   R2---------------R3
        |                |
        |                |          checked
        |                |
        R1---------------R0
       """

        if self.subAreaLayer.name() == "notAvail":
            self.model_rot = 0
            return 0
        # QgsMessageLog.logMessage("Calculating Model Rotation...", 'ENVI-met', level=Qgis.Info)

        spFeats = self.subAreaLayer.getFeatures()
        f_geo = None
        numVert = None

        for f in spFeats:
            if f.hasGeometry():
                f_geo = f.geometry()
                numVert = 0

                for v in f_geo.vertices():
                    numVert = numVert + 1
        #print(numVert)
        if f_geo is None:
            self.msg = 'Error:Please provide a layer featuring a single rectangular polygon (4 vertices).'
        else:
            if (numVert > 4) and (numVert < 7):  # a correct rect has 5 vertices as idx:0 and idx:4 are identical. If users wrongfully(!) create one by hand, they might end up with a total of 6 vertices
                self.msg = ""
                """
                after saving the indices of the vertices get switched... R1 becomes R3 and vice versa
                R1---------------R2
                |                |
                |                |
                |                |
                R0/4-------------R3
                """
                R0 = f_geo.vertexAt(0)          # first vertex (this one should be identical with the 5th)
                R1 = f_geo.vertexAt(1)          # second vertex
                R2 = f_geo.vertexAt(2)          # third vertex
                R3 = f_geo.vertexAt(3)          # last vertrex
                R4 = f_geo.vertexAt(4)          # last vertrex                
                '''
                print(R0)
                print(R1)
                print(R2)
                print(R3)
                print(R4)
                '''
                R0_R2_ang = degrees(QgsGeometryUtils.angleBetweenThreePoints(R0.x(),R0.y(),R1.x(),R1.y(),R2.x(),R2.y()))
                R1_R3_ang = degrees(QgsGeometryUtils.angleBetweenThreePoints(R1.x(),R1.y(),R2.x(),R2.y(),R3.x(),R3.y()))
                R2_R0_ang = degrees(QgsGeometryUtils.angleBetweenThreePoints(R2.x(),R2.y(),R3.x(),R3.y(),R0.x(),R0.y()))
                R3_R1_ang = degrees(QgsGeometryUtils.angleBetweenThreePoints(R3.x(),R3.y(),R4.x(),R4.y(),R1.x(),R1.y()))
                
                #print(R0_R2_ang)
                #print(R1_R3_ang)
                #print(R2_R0_ang)
                #print(R3_R1_ang)
                
                # angle [deg] of inaccuracy that is acceptable to be used as subarea
                allowedInaccuracy = 5   

                # as the angles might be 270 or 90 depending on the orientation of the rect -> so we need to account for that
                while R0_R2_ang > allowedInaccuracy:
                    R0_R2_ang = R0_R2_ang - 90
                while R1_R3_ang > allowedInaccuracy:
                    R1_R3_ang = R1_R3_ang - 90
                while R2_R0_ang > allowedInaccuracy:
                    R2_R0_ang = R2_R0_ang - 90
                while R3_R1_ang > allowedInaccuracy:
                    R3_R1_ang = R3_R1_ang - 90              

                #print(R0_R2_ang)
                #print(R1_R3_ang)
                #print(R2_R0_ang)
                #print(R3_R1_ang)                                                                  

                if (abs(R0_R2_ang) > allowedInaccuracy) or (abs(R1_R3_ang) > allowedInaccuracy) or (abs(R2_R0_ang) > allowedInaccuracy) or (abs(R3_R1_ang) > allowedInaccuracy):
                    self.msg = 'Warning:Please check that the subarea is of rectangular form. The use of the "Shape Digitizing Toolbar" is recommended.'

                '''
                # old algo
                # R0 to R3 will define the baseline for ENVI-met
                model_rot = 0
                # save R0 as the model rotation center point aka the lower left in ENVI-met
                self.model_rot_center = R0

                # we now have 3 cases
                # if the y coord of B is lower than A than the angle is negative
                # if the y coord of B is higher than it is positive
                # if the y coord is the same, then the rotation is 0
                # the rotation center is always A
                RX = QgsPoint(R3.x(), R0.y())
                if R3.y() < R0.y():  # is this the case where the rotation is negative????
                    if R3.x() >= R0.x():
                        a = RX.y() - R3.y()
                        b = RX.x() - R0.x()
                        c = sqrt(a**2 + b**2)    # length hypo c
                        model_rot = -1 * (degrees(acos(b/c)))
                    if R3.x() < R0.x():
                        a = RX.y() - R3.y()
                        b = R0.x() - RX.x()
                        c = sqrt(a**2 + b**2)    # length hypo c
                        model_rot = -1 * (180 - degrees(acos(b/c)))
                if R3.y() > R0.y():
                    if R3.x() >= R0.x():
                        a = R3.y() - RX.y()
                        b = RX.x() - R0.x()
                        c = sqrt(a**2 + b**2)    # length hypo c
                        model_rot = degrees(acos(b/c))
                    if R3.x() < R0.x():
                        a = R3.y() - RX.y()
                        b = R0.x() - RX.x()
                        c = sqrt(a**2 + b**2)    # length hypo c
                        model_rot = 180 - degrees(acos(b/c))
                #print("def:" + str(model_rot))
                '''
                # R0 to R3 will define the baseline for ENVI-met
                model_rot_corr = 0
                # save R0 as the model rotation center point aka the lower left in ENVI-met
                self.model_rot_center = R0

                # alternative to model rotation calc
                RXY0 = QgsPointXY(R0.x(), R0.y())
                RXY3 = QgsPointXY(R3.x(), R3.y())    
                # calculate azi angle 0=North   
                model_rot_azi = RXY0.azimuth(RXY3)  
                # correct the angle to match ENVI-met 
                model_rot_corr = -1 * (model_rot_azi - 90)
                if model_rot_azi < -90:
                    model_rot_corr = model_rot_corr - 360
                #print("azi_corr:" + str(model_rot_corr))

                self.model_rot = model_rot_corr
                self.rotate_layer(self.subAreaLayer, True)
                return model_rot_corr
            else:
                # write a msg to the user
                self.msg = 'Error:Please provide a layer featuring a single rectangular polygon (4 vertices). The use of the "Shape Digitizing Toolbar" is recommended.'

    def get_time_zone_geonames(self):
        QgsMessageLog.logMessage("Getting Timezone...", 'ENVI-met', level=Qgis.Info)
        try:
            url = 'http://api.geonames.org/timezone?lat=' + str(self.lat) + '&lng=' + str(self.lon) + '&username=envi_met'
            #print(url)
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                s = response.text
                #print(s)
                dataFound = False
                if "error" not in s:
                    tree = ET.ElementTree(ET.fromstring(s))
                    root = tree.getroot()
                    for tz in root:
                        for data in tz:
                            if data.tag == "gmtOffset":
                                dataFound = True
                                return data.text
                    if not dataFound:
                        s1 = round(self.lon / 15)
                        return str(s1) 
                else:
                    s1 = round(self.lon / 15)
                    return str(s1)                                                
            else:
                s = round(self.lon / 15)
                return str(s)
        except:
            s = round(self.lon / 15)
            return str(s)

    def get_elevation_geonames(self):
        QgsMessageLog.logMessage("Getting Elevation...", 'ENVI-met', level=Qgis.Info)
        try:
            response = requests.get('http://api.geonames.org/srtm1XML?lat=' + str(self.lat) + '&lng=' + str(self.lon) + '&username=envi_met')
            if response.status_code == 200:
                s = response.text
                tree = ET.ElementTree(ET.fromstring(s))
                root = tree.getroot()
                for data in root:
                    if data.tag == "srtm1":
                        elev = int(data.text)
                        if elev >= 0:
                            return elev
                        else:
                            return self.refHeightDEM
            else:
                return self.refHeightDEM
        except:
            return self.refHeightDEM

    def get_UTM_zone(self, lon: int, lat: int):
        zoneNum = trunc((floor(lon + 180) / 6) + 1)
        zoneHemi = "N"
        if lat >= 0:
            zoneHemi = "N"
        else:
            zoneHemi = "S"
        res = str(zoneNum) + ' ' + zoneHemi 
        return res
    
    def find_crs_auth_id(self, crs_description: str) -> int:
        """
        Gets the auth_id from a CRS description.
        Based on pyproj.db
        Parameters:
        ==========
        :param crs_description: the CRS description to check
        Returns:
        ==========
        auth_id, -1 if not found
        """

        list_of_crs = query_utm_crs_info()
        result = [c[1] for c in list_of_crs if c[0] == "EPSG" and c[2] == f'{crs_description}']
        
        return int(result[0]) if len(result) else -1

    def buildBInfo(self):
        self.s_buildingDict.clear()
        if (self.bLayer.name() == "notAvail") or ((not self.bTop_UseCustom) and (self.bTop == "")) or (self.bLayer.getFeatures() is None):
            return self.s_buildingDict

        QgsMessageLog.logMessage("Started: Generating Building Info section...", 'ENVI-met', level=Qgis.Info)
        
        # reproject to UTM
        self.bLayer = self.reprojectLayerToUTM(self.bLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", 
                                   {"INPUT": self.bLayer,
                                    "PREDICATE": [0],
                                    "INTERSECT": self.subAreaLayer_nonRot,
                                    "OUTPUT": 'TEMPORARY_OUTPUT'},
                                    context=context)
        #QgsProject.instance().addMapLayer(aTmpLayer["OUTPUT"])


        # rotate the building layer, so it is aligned with the subarea-layer again
        #self.bLayer_rot = self.rotate_layer(self.bLayer, False)
        self.bLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        # start editing
        self.bLayer_rot.startEditing()
        bNumber_int = 'bNum_int'
        self.bLayer_rot.addAttribute(QgsField(bNumber_int, QVariant.Int))
        self.bLayer_rot.commitChanges()

        self.bLayer_rot = self.reorgFID(self.bLayer_rot)
        '''
        # some users report that (understandably) if the fID is identical for all features, then the rasterizer does not work
        # thus first we check if there is a field called "fid"
        fID_user_present = False
        fID_user = ''
        for a in self.bLayer_rot.attributeList():
            if self.bLayer_rot.attributeDisplayName(a).lower() == "fid":
                fID_user_present = True
                fID_user = self.bLayer_rot.attributeDisplayName(a)
                break

        # apply building numbers
        self.bLayer_rot.startEditing()
        i = 1
        for f in self.bLayer_rot.getFeatures():
            f[bNumber_int] = i 
            # reset the users fid field if present
            if fID_user_present:
                f[fID_user] = i 
            self.bLayer_rot.updateFeature(f)
            i += 1
        self.bLayer_rot.commitChanges()
        #QgsProject.instance().addMapLayer(self.bLayer_rot)
        '''

        # apply building numbers
        self.bLayer_rot.startEditing()
        i = 1
        for f in self.bLayer_rot.getFeatures():
            f[bNumber_int] = i 
            self.bLayer_rot.updateFeature(f)
            i += 1
        self.bLayer_rot.commitChanges()
        #QgsProject.instance().addMapLayer(self.bLayer_rot)

        # we now have building numbers for all elements, but we should only write the ones that are in our extent
        for f in self.bLayer_rot.getFeatures():
            if f.geometry().intersects(self.subAreaExtent):
                s_bNumber = f.attribute(bNumber_int)
                if self.bName_UseCustom or (self.bName == ""):
                    s_bName = str(self.bName_custom.replace("NULL", ""))
                else:
                    s_bName = str(f.attribute(self.bName)).replace("NULL", "")

                if self.bWall_UseCustom or (self.bWall == ""):
                    s_bWall = str(self.bWall_custom.replace("NULL", ""))
                else:
                    s_bWall = str(f.attribute(self.bWall)).replace("NULL", "")

                if self.bRoof_UseCustom or (self.bRoof == ""):
                    s_bRoof = str(self.bRoof_custom.replace("NULL", ""))
                else:
                    s_bRoof = str(f.attribute(self.bRoof)).replace("NULL", "")

                if self.bGreenWall_UseCustom or (self.bGreenWall == ""):
                    s_bGWall = str(self.bGreenWall_custom.replace("NULL", ""))
                else:
                    s_bGWall = str(f.attribute(self.bGreenWall)).replace("NULL", "")

                if self.bGreenRoof_UseCustom or (self.bGreenRoof == ""):
                    s_bGRoof = str(self.bGreenRoof_custom.replace("NULL", ""))
                else:
                    s_bGRoof = str(f.attribute(self.bGreenRoof)).replace("NULL", "")

                if self.bBPS_disabled or (self.bBPS == ""):
                    s_bBPS = "0"
                else:
                    if str(f.attribute(self.bBPS)).replace("NULL", "") == '1':
                        s_bBPS = '1'
                    else:
                        s_bBPS = '0'

                newBuild = Building(BldInternalNum=s_bNumber, BldName=s_bName, BldWallMat=s_bWall, BldRoofMat=s_bRoof,
                                    BldFacadeGreen=s_bGWall, BldRoofGreen=s_bGRoof, BldBPS=s_bBPS, BldInModelArea=True)
                self.s_buildingDict[s_bNumber] = newBuild
                #print(self.s_buildingDict[s_bNumber].BuildingInternalNumber)
                #print('as')

        QgsMessageLog.logMessage("Finished: Generating Building Info section.", 'ENVI-met', level=Qgis.Info)

    def rasterBNumber(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr

        QgsMessageLog.logMessage("Started: Gridding Building Numbers...", 'ENVI-met', level=Qgis.Info)
        grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field='bNum_int')
        QgsMessageLog.logMessage("Finished: Gridding Building Numbers", 'ENVI-met', level=Qgis.Info)
        return grid1_int_array

    def rasterBTop(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr

        QgsMessageLog.logMessage("Started: Gridding Building Tops...", 'ENVI-met', level=Qgis.Info)

        if self.bTop_UseCustom:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bTop_custom, burn_val=True)
        else:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bTop)

        QgsMessageLog.logMessage("Finished: Gridding Building Tops.", 'ENVI-met', level=Qgis.Info)
        return grid1_int_array

    def rasterBBot(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr
        QgsMessageLog.logMessage("Started: Gridding Building Bottoms...", 'ENVI-met', level=Qgis.Info)

        if self.bBot_UseCustom:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bBot_custom, burn_val=True)
        else:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bBot)

        QgsMessageLog.logMessage("Finished: Gridding Building Bottoms.", 'ENVI-met', level=Qgis.Info)
        return grid1_int_array

    def raster_surface_from_vector(self):
        if self.surfLayer.name() == "notAvail":
            tmpAr = np.empty(shape=(self.JJ, self.II), dtype='<U6')
            return tmpAr.fill(self.startSurfID)

        QgsMessageLog.logMessage("Started: Gridding Surfaces...", 'ENVI-met', level=Qgis.Info)
        
        # reproject to UTM
        self.surfLayer = self.reprojectLayerToUTM(self.surfLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.surfLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'}, context=context
                       )

        #self.surfLayer_rot = self.rotate_layer(self.surfLayer, False)
        self.surfLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        self.surfLayer_rot = self.reorgFID(self.surfLayer_rot)

        # Fill a dict with EnviIDs as keys and increasing integers as values
        # Thus, we map each EnviID which is used in this layer on one integer value
        aTmpDict = {}
        i = 1
        for f in self.surfLayer_rot.getFeatures():
            surfID_str = f[self.surfID]
            if surfID_str and not surfID_str.isspace():
                # if the surfaceID does not exist in the dict yet, add it
                if aTmpDict.get(surfID_str) is None:
                    # surfID_str is the key, i the value
                    aTmpDict[surfID_str] = i
                    i += 1

        # add new column to the attribute-table of surfLayer_rot
        # this layer will store the integer values we just mapped in the dictionary
        self.surfLayer_rot.startEditing()
        ID_int = 'ID_int'
        self.surfLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

        # write the corresponding integer values in each row, depending on the EnviID used in that row
        for f in self.surfLayer_rot.getFeatures():
            # get enviID as string
            surfID_str = f[self.surfID]
            surfID_int = -1
            # get integer value for this enviID (surfID_str)
            value = aTmpDict.get(surfID_str)
            # if the enviID exists in the dictionary
            if value is not None:
                surfID_int = value
            f[ID_int] = surfID_int
            self.surfLayer_rot.updateFeature(f)
        self.surfLayer_rot.commitChanges()

        grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.surfLayer_rot, field=ID_int, get_strArray=True)

        # invert dictionary
        invTmpDict = {v: k for k, v in aTmpDict.items()}
        for i in range(grid1_int_array.shape[0]):
            for j in range(grid1_int_array.shape[1]):
                if grid1_int_array[i, j] <= 0:
                    grid1_str_array[i, j] = self.startSurfID
                else:
                    grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]

        aTmpDict.clear()
        invTmpDict.clear()
        QgsMessageLog.logMessage("Finished: Gridding Surfaces.", 'ENVI-met', level=Qgis.Info)
        return grid1_str_array

    def extent_by_margin(self, margin: int = 100):
        # subAreaLayer_nonRot is the unrotated subarea (the users input layer)
        # get its geometry
        for f in self.subAreaLayer_nonRot.getFeatures():
            if f.hasGeometry():
                f_geo = f.geometry()

        # get the four rectangle-vertices from the geometry of that layer
        R0 = f_geo.vertexAt(0)
        R1 = f_geo.vertexAt(1)
        R2 = f_geo.vertexAt(2)
        R3 = f_geo.vertexAt(3)

        # Next step: Add a margin to the boundingBox of the rectangle - e.g., increase the size

        # Determine xmin, xmax, ymin, ymax and the associated vertices
        # lists are sorted in increasing order
        x_list = sorted([('R0', R0.x()), ('R1', R1.x()), ('R2', R2.x()), ('R3', R3.x())], key=lambda x: x[1])
        y_list = sorted([('R0', R0.y()), ('R1', R1.y()), ('R2', R2.y()), ('R3', R3.y())], key=lambda y: y[1])

        if (self.model_rot % 90) < 0.1:
            # the model area is rotated by 90, 180 or 270 degrees
            # xmin exists for two vertices, same for xmax, ymin and ymax
            for i in range(len(x_list)):
                if x_list[i][0] == 'R0':
                    # if i < 2, the vertex is at the xmin-side. Otherwise, it is at the xmax side
                    if i < 2:
                        new_0x = R0.x() - margin
                    else:
                        new_0x = R0.x() + margin
                elif x_list[i][0] == 'R1':
                    if i < 2:
                        new_1x = R1.x() - margin
                    else:
                        new_1x = R1.x() + margin
                elif x_list[i][0] == 'R2':
                    if i < 2:
                        new_2x = R2.x() - margin
                    else:
                        new_2x = R2.x() + margin
                elif x_list[i][0] == 'R3':
                    if i < 2:
                        new_3x = R3.x() - margin
                    else:
                        new_3x = R3.x() + margin

                # do the same for y
                if y_list[i][0] == 'R0':
                    # if i < 2, the vertex is at the ymin-side. Otherwise, it is at the ymax side
                    if i < 2:
                        new_0y = R0.y() - margin
                    else:
                        new_0y = R0.y() + margin
                elif y_list[i][0] == 'R1':
                    if i < 2:
                        new_1y = R1.y() - margin
                    else:
                        new_1y = R1.y() + margin
                elif y_list[i][0] == 'R2':
                    if i < 2:
                        new_2y = R2.y() - margin
                    else:
                        new_2y = R2.y() + margin
                elif y_list[i][0] == 'R3':
                    if i < 2:
                        new_3y = R3.y() - margin
                    else:
                        new_3y = R3.y() + margin

            # create new vertices with the added margin
            R0_new = QgsPointXY(new_0x, new_0y)
            R1_new = QgsPointXY(new_1x, new_1y)
            R2_new = QgsPointXY(new_2x, new_2y)
            R3_new = QgsPointXY(new_3x, new_3y)
        else:
            # the model area has another rotation, so we calculate the margin differently
            xmin_name = x_list[0][0]
            xmax_name = x_list[-1][0]
            ymin_name = y_list[0][0]
            ymax_name = y_list[-1][0]

            new_0x = R0.x()
            new_1x = R1.x()
            new_2x = R2.x()
            new_3x = R3.x()
            new_0y = R0.y()
            new_1y = R1.y()
            new_2y = R2.y()
            new_3y = R3.y()

            if xmin_name == 'R0':
                new_0x = R0.x() - margin
            elif xmin_name == 'R1':
                new_1x = R1.x() - margin
            elif xmin_name == 'R2':
                new_2x = R2.x() - margin
            elif xmin_name == 'R3':
                new_3x = R3.x() - margin

            if xmax_name == 'R0':
                new_0x = R0.x() + margin
            elif xmax_name == 'R1':
                new_1x = R1.x() + margin
            elif xmax_name == 'R2':
                new_2x = R2.x() + margin
            elif xmax_name == 'R3':
                new_3x = R3.x() + margin

            if ymin_name == 'R0':
                new_0y = R0.y() - margin
            elif ymin_name == 'R1':
                new_1y = R1.y() - margin
            elif ymin_name == 'R2':
                new_2y = R2.y() - margin
            elif ymin_name == 'R3':
                new_3y = R3.y() - margin

            if ymax_name == 'R0':
                new_0y = R0.y() + margin
            elif ymax_name == 'R1':
                new_1y = R1.y() + margin
            elif ymax_name == 'R2':
                new_2y = R2.y() + margin
            elif ymax_name == 'R3':
                new_3y = R3.y() + margin

            R0_new = QgsPointXY(new_0x, new_0y)
            R1_new = QgsPointXY(new_1x, new_1y)
            R2_new = QgsPointXY(new_2x, new_2y)
            R3_new = QgsPointXY(new_3x, new_3y)

        # Create a QgsPolygon-object with the new size
        boundingBox = [R0_new, R1_new, R2_new, R3_new, R0_new]
        rectangle = QgsGeometry.fromPolygonXY([boundingBox])
        subArea_margin = QgsVectorLayer('Polygon', 'rectangle', 'memory')
        # Create a new feature with the rectangle geometry
        provider = subArea_margin.dataProvider()
        feat = QgsFeature()
        feat.setGeometry(rectangle)
        boundingBox_margin = feat.geometry().boundingBox()
        provider.addFeatures([feat])
        subArea_margin.updateExtents()
        return boundingBox_margin

    def get_data_from_raster(self, input_layer):
        boundingBox_margin = self.extent_by_margin(margin=100)

        # now clip the raster to the extent of boundingBox_margin
        # transform the coordinate system of subArea_nonRot_Extent to the ones of the surface layer
        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        rlayer_clip = processing.run("gdal:cliprasterbyextent",
                                     {"INPUT": input_layer,
                                      "PROJWIN": boundingBox_margin,
                                      "OVERCRS": False,
                                      "OUTPUT": 'TEMPORARY_OUTPUT'},
                                     context=context)
        rlayerFN_clip = rlayer_clip['OUTPUT']
        #print(rlayerFN_clip)
        #QgsProject.instance().addMapLayer(rlayerFN_clip)
        #self.addRasterLayer(rlayerFN_clip,"surf_debug")

        # Now we resample the clipped raster layer to the defined grid-size (min(dx, dy))
        rlayer_resample = processing.run("gdal:warpreproject",
                                         {'INPUT': rlayerFN_clip,
                                          'RESAMPLING': 0,
                                          'NODATA': -999,
                                          'TARGET_RESOLUTION': min(self.dx, self.dy),
                                          'OPTIONS': '',
                                          'DATA_TYPE': 0,
                                          'TARGET_EXTENT': None,
                                          'TARGET_EXTENT_CRS': None,
                                          'MULTITHREADING': True,
                                          'EXTRA': '',
                                          'OUTPUT': 'TEMPORARY_OUTPUT'},
                                         context=context)
        rlayerFN_resample = rlayer_resample['OUTPUT']

        # Next step: rotate the raster-layer
        rlayer_rotated = self.rotate_raster_layer(layer=rlayerFN_resample)
        raster_layer = QgsRasterLayer(rlayer_rotated, 'afterRotateAndMove')
        raster_layer.setCrs(input_layer.crs())

        # Next step: rlayer_rotated is not in a rectangular shape anymore, this is caused by the rotation
        # This casues trouble for future gdal-operations on this layer
        # To make it rectangular again, we need to add NULL-values around the rotated raster to create a rectangle again
        # This is possible with a naive call of GDAL-Warp (Resample)
        """
        R1---------------R2 
        |   /--------     | 
        |  /-------  ---/ |
        |         -----/  | 
        R0---------------R3 
        """

        reshaped = processing.run("gdal:warpreproject",
                                  {'INPUT': raster_layer,
                                   'SOURCE_CRS': self.surfLayer_raster.crs(),
                                   'TARGET_CRS': self.surfLayer_raster.crs(),
                                   'RESAMPLING': 0,
                                   'NODATA': None,
                                   'TARGET_RESOLUTION': None,
                                   'OPTIONS': '',
                                   'DATA_TYPE': 0,
                                   'TARGET_EXTENT': None,
                                   'TARGET_EXTENT_CRS': None,
                                   'MULTITHREADING': True,
                                   'EXTRA': '',
                                   'OUTPUT': 'TEMPORARY_OUTPUT'},
                                  context=context)
        rLayer_reshaped = reshaped['OUTPUT']

        # Next step: get the bounding-box of the back-to-zero-rotated subArea
        # and clip the reshaped raster to that extent
        for f in self.subAreaLayer.getFeatures():
            if f.hasGeometry():
                f_geo = f.geometry()
                subArea_Extent = f_geo.boundingBox()

        rlayer_clip2 = processing.run("gdal:cliprasterbyextent",
                                      {"INPUT": rLayer_reshaped,
                                       'PROJWIN': subArea_Extent,
                                       "NODATA": -999,
                                       "OUTPUT": 'TEMPORARY_OUTPUT'},
                                      context=context)

        rLayer_final = rlayer_clip2['OUTPUT']

        # Final step: get rLayer_final as int-array and string-array and fill the values with the defined
        # ENVI-IDs

        # Open the current layer
        grid1 = gdal.Open(rLayer_final)

        # Get the first raster band of the layer
        grid1_band = grid1.GetRasterBand(1)

        # Read the raster band as an numpy array
        grid1_array = grid1_band.ReadAsArray()

        # Change the data type of array from floating numbers to integers
        grid1_int_array = grid1_array.astype(int)

        # fill grids cnt
        self.II = grid1_int_array.shape[1]
        self.JJ = grid1_int_array.shape[0]

        grid1_str_array = grid1_int_array.astype(str)
        return grid1_str_array, grid1_int_array

    def raster_surface_from_raster(self):
        # reproject to UTM
        outFN = self.reprojectRasterLayerToUTM(self.surfLayer_raster)        
        self.surfLayer_raster = QgsRasterLayer(outFN, "surfTMP_UTM")
     
        grid1_str_array, grid1_int_array = self.get_data_from_raster(self.surfLayer_raster)

        for i in range(grid1_str_array.shape[0]):
            for j in range(grid1_str_array.shape[1]):
                val = self.surfLayer_raster_def.get(grid1_str_array[i, j])
                if val is not None:
                    # this is a specific value the user mapped onto an ENVI-met soil
                    grid1_str_array[i, j] = val
                else:
                    other_val = self.surfLayer_raster_def.get('OTHER')
                    if other_val is not None:
                        # 'other' was defined by the user, set the value
                        grid1_str_array[i, j] = other_val
                    else:
                        # 'other' was not defined by the user, so we use 0100SL as default soil
                        grid1_str_array[i, j] = self.startSurfID

        return grid1_str_array

    def rotate_raster_layer(self, layer):
        dataset = gdal.Open(layer)

        # Get projection
        projection = dataset.GetProjection()
        geotransform = dataset.GetGeoTransform()

        # Rotate the raster-layer by rotating each pixel, apply a 2D-rotation matrix
        new_geotransform = list(geotransform)

        rotation = self.model_rot  # pixel rotation (square pixels)
        new_geotransform[1] = math.cos(math.radians(rotation)) * geotransform[1]
        new_geotransform[2] = -math.sin(math.radians(rotation)) * geotransform[1]
        new_geotransform[4] = math.sin(math.radians(rotation)) * geotransform[5]
        new_geotransform[5] = math.cos(math.radians(rotation)) * geotransform[5]

        # setting No Data Values
        dataset.GetRasterBand(1).SetNoDataValue(-999)

        # apply the rotated pixel to the layer
        dataset.SetGeoTransform(new_geotransform)

        # setting spatial reference of output raster
        srs = osr.SpatialReference(wkt=projection)
        dataset.SetProjection(srs.ExportToWkt())

        # At this point, the layer is rotated. But it is at the wrong location now.
        # The Raster-pixels which lay inside the back-to-zero-rotated-subArea do not match
        # with the raster-pixel which were in the non-rotated sub-area.
        # But the rotation is correct now. So now we need to move the whole raster-layer to the correct position

        # Determine the position of the R0-vertex of the unrotated subArea
        # R0 is the rotation center for the subArea-layer
        f_geo = None
        for f in self.subAreaLayer_nonRot.getFeatures():
            if f.hasGeometry():
                f_geo = f.geometry()

        R0 = f_geo.vertexAt(0)

        # calculate x- and y-difference between R0 and the upper left pixel of the raster-layer
        # The upper left pixel of the raster layer is the rotation center for the raster-rotation
        diff_R0_raster_x = abs(R0.x() - new_geotransform[0])
        diff_R0_raster_y = abs(R0.y() - new_geotransform[3])

        # apply 2D-rotation matrix
        # This gets us the new position of the pixel which was at R0 before rotation
        new_pos_x = (diff_R0_raster_x * math.cos(math.radians(rotation)) - diff_R0_raster_y * math.sin(math.radians(rotation)))
        new_pos_y = (diff_R0_raster_x * math.sin(math.radians(rotation)) + diff_R0_raster_y * math.cos(math.radians(rotation)))

        # calculate the x- and y-difference between R0 and the new position of that pixel
        diff_x = abs(diff_R0_raster_x - new_pos_x)
        diff_y = abs(diff_R0_raster_y - new_pos_y)

        # move the raster by that difference each in x- and y-direction
        # Some explanation: Imagine a new cartesian coordinate system
        # The upper-left pixel of the raster layer is the origin-point (0,0)
        # The lower-right quartile is (+, +)
        # The upper-right quartile is (+, -)
        # The upper-left quartile is (-, -)
        # The lower-left quartile is (-, +)
        # This is because the subArea always is in the lower-right quartile and I calculate
        # diff_R0_raster_x and diff_R0_raster_y as absolute values

        # new x
        if new_pos_x < diff_R0_raster_x:
            new_geotransform[0] += diff_x
        else:
            new_geotransform[0] -= diff_x

        # new y
        if new_pos_y < diff_R0_raster_y:
            new_geotransform[3] -= diff_y
        else:
            new_geotransform[3] += diff_y

        # setting extension of output raster
        dataset.SetGeoTransform(new_geotransform)

        # setting spatial reference of output raster
        srs = osr.SpatialReference(wkt=projection)
        dataset.SetProjection(srs.ExportToWkt())
        return layer

    def raster_simple_plants_from_raster(self):
        # reproject to UTM
        outFN = self.reprojectRasterLayerToUTM(self.plant1dLayer_raster)        
        self.plant1dLayer_raster = QgsRasterLayer(outFN, "spTMP_UTM")
        grid1_str_array, grid1_int_array = self.get_data_from_raster(self.plant1dLayer_raster)

        for i in range(grid1_str_array.shape[0]):
            for j in range(grid1_str_array.shape[1]):
                val = self.plant1dLayer_raster_def.get(grid1_str_array[i, j])
                if val is not None:
                    # this is a specific value the user mapped onto an ENVI-met soil
                    grid1_str_array[i, j] = val
                else:
                    other_val = self.plant1dLayer_raster_def.get('OTHER')
                    if other_val is not None:
                        # 'other' was defined by the user, set the value
                        grid1_str_array[i, j] = other_val
                    else:
                        # 'other' was not defined by the user, so we use 0100SL as default soil
                        grid1_str_array[i, j] = ''

        return grid1_str_array
    
    def reorgFID(self, input_layer):
        # some users report that (understandably) if the fID is identical for all features, then the rasterizer does not work
        # thus first we check if there is a field called "fid"
        fID_user_present = False
        fID_user = ''
        for a in input_layer.attributeList():
            if input_layer.attributeDisplayName(a).lower() == "fid":
                fID_user_present = True
                fID_user = input_layer.attributeDisplayName(a)
                break

        if fID_user_present:
            input_layer.startEditing()
            i = 0
            for f in input_layer.getFeatures():
                f[fID_user] = i 
                input_layer.updateFeature(f)
                i += 1
            input_layer.commitChanges()
            #QgsProject.instance().addMapLayer(input_layer)
        return input_layer

    def rasterize_gdal(self, input_layer, field, get_strArray: bool = False, burn_val: bool = False,
                       init_val=None, no_data_val: int = 0):
        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        if burn_val:
            if init_val is None:
                rlayer = processing.run("gdal:rasterize",
                                        {"INPUT": input_layer,
                                         "BURN": field,
                                         "UNITS": 1,
                                         "WIDTH": self.dx,
                                         "HEIGHT": self.dy,
                                         "EXTENT": self.subAreaExtent,
                                         "NODATA": no_data_val,
                                         "DATA_TYPE": 4,
                                         "INVERT": False,
                                         "OUTPUT": 'TEMPORARY_OUTPUT'},
                                        context=context)
                rlayerFN = rlayer['OUTPUT']
            else:
                rlayer = processing.run("gdal:rasterize",
                                        {"INPUT": input_layer,
                                         "BURN": field,
                                         "UNITS": 1,
                                         "WIDTH": self.dx,
                                         "HEIGHT": self.dy,
                                         "EXTENT": self.subAreaExtent,
                                         "NODATA": no_data_val,
                                         "INIT": init_val,
                                         "DATA_TYPE": 4,
                                         "INVERT": False,
                                         "OUTPUT": 'TEMPORARY_OUTPUT'},
                                        context=context)
                rlayerFN = rlayer['OUTPUT']
        else:
            if init_val is None:
                rlayer = processing.run("gdal:rasterize",
                                        {"INPUT": input_layer,
                                         "FIELD": field,
                                         "UNITS": 1,
                                         "WIDTH": self.dx,
                                         "HEIGHT": self.dy,
                                         "EXTENT": self.subAreaExtent,
                                         "NODATA": no_data_val,
                                         "DATA_TYPE": 4,
                                         "INVERT": False,
                                         "OUTPUT": 'TEMPORARY_OUTPUT'},
                                        context=context)
                rlayerFN = rlayer['OUTPUT']
                #print(rlayerFN)
            else:
                rlayer = processing.run("gdal:rasterize",
                                        {"INPUT": input_layer,
                                         "FIELD": field,
                                         "UNITS": 1,
                                         "WIDTH": self.dx,
                                         "HEIGHT": self.dy,
                                         "EXTENT": self.subAreaExtent,
                                         "NODATA": no_data_val,
                                         "INIT": init_val,
                                         "DATA_TYPE": 4,
                                         "INVERT": False,
                                         "OUTPUT": 'TEMPORARY_OUTPUT'},
                                        context=context)
                rlayerFN = rlayer['OUTPUT']
                #print(rlayerFN)
        #self.addRasterLayer(rlayerFN,"surf_debug")
        # Open the current layer
        grid1 = gdal.Open(rlayerFN)

        # Get the first raster band of the layer
        grid1_band = grid1.GetRasterBand(1)

        # Read the raster band as an numpy array
        grid1_array = grid1_band.ReadAsArray()

        # Change the data type of array from floating numbers to integers
        grid1_int_array = grid1_array.astype(int)

        # fill grids cnt
        self.II = grid1_int_array.shape[1]
        self.JJ = grid1_int_array.shape[0]

        if get_strArray:
            grid1_str_array = grid1_int_array.astype(str)
            # Remove the whole cache
            grid1_band.FlushCache()
            return grid1_str_array, grid1_int_array
        else:
            # Remove the whole cache
            grid1_band.FlushCache()
            return grid1_int_array

    def raster_simple_plants_from_vector(self):
        if self.plant1dLayer.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
            return tmpAr.fill("")

        QgsMessageLog.logMessage("Started: Gridding Simple Plants...", 'ENVI-met', level=Qgis.Info)

        # reproject to UTM
        self.plant1dLayer = self.reprojectLayerToUTM(self.plant1dLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)           #QgsFeatureRequest.GeometrySkipInvalid       
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.plant1dLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )
        #self.plant1dLayer_rot = self.rotate_layer(self.plant1dLayer, False)
        self.plant1dLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        self.plant1dLayer_rot = self.reorgFID(self.plant1dLayer_rot)

        aTmpDict = {}
        if not self.plant1dID_UseCustom:
            # get all items in the vector layer
            spFeats = self.plant1dLayer_rot.getFeatures()
            i = 1
            for f in spFeats:
                plantID_str = f[self.plant1dID]
                if plantID_str and not plantID_str.isspace():
                    # if the plantID does not exist in the dict yet, add it
                    if aTmpDict.get(plantID_str) is None:
                        # plantID_str is the key, i the value
                        aTmpDict[plantID_str] = i
                        i += 1

            # add new column to the attribute-table of plant1dLayer_rot
            # this layer will store the integer values we just mapped in the dictionary
            self.plant1dLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.plant1dLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            # write the corresponding integer values in each row, depending on the EnviID used in that row
            for f in self.plant1dLayer_rot.getFeatures():
                # get enviID in string
                plantID_str = f[self.plant1dID]
                plantID_int = -1
                # get integer value for this enviID (surfID_str)
                value = aTmpDict.get(plantID_str)
                # if the enviID exists in the dictionary
                if value is not None:
                    plantID_int = value
                f[ID_int] = plantID_int
                self.plant1dLayer_rot.updateFeature(f)
            self.plant1dLayer_rot.commitChanges()

            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.plant1dLayer_rot, field=ID_int,
                                                                   get_strArray=True)
        else:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.plant1dLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)

        if not self.plant1dID_UseCustom:
            # invert dictionary
            invTmpDict = {v: k for k, v in aTmpDict.items()}
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]

            aTmpDict.clear()
            invTmpDict.clear()
        else:
            grid1_str_array[grid1_int_array <= 0] = ""
            grid1_str_array[grid1_int_array == 999] = self.plant1dID_custom

        QgsMessageLog.logMessage("Finished: Gridding Simple Plants.", 'ENVI-met', level=Qgis.Info)
        return grid1_str_array

    def buildPlants3d(self):
        self.s_treeList.clear()
        if (self.plant3dLayer.name() == "notAvail") or (self.plant3dID == "") \
                or (self.plant3dLayer_rot.getFeatures() is None):
            return self.s_treeList
        
        # reproject to UTM
        self.plant3dLayer = self.reprojectLayerToUTM(self.plant3dLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)            #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.plant3dLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )
        #QgsProject.instance().addMapLayer(aTmpLayer["OUTPUT"])

        QgsMessageLog.logMessage("Started: Gridding 3D Plants...", 'ENVI-met', level=Qgis.Info)
        #self.plant3dLayer_rot = self.rotate_layer(self.plant3dLayer, False)
        self.plant3dLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)
        
        self.plant3dLayer_rot = self.reorgFID(self.plant3dLayer_rot)

        aTmpDict = {}
        # user wants a const value for Trees
        if self.plant3dID_UseCustom:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.plant3dLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)
        else:
            self.plant3dLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.plant3dLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            # add a unique number to each tree
            plantID_idx = 1
            for f in self.plant3dLayer_rot.getFeatures():
                f[ID_int] = plantID_idx
                self.plant3dLayer_rot.updateFeature(f)
                plantID_idx += 1
            self.plant3dLayer_rot.commitChanges()

            for f in self.plant3dLayer_rot.getFeatures():
                plantID_str = f[self.plant3dID]
                if plantID_str and not plantID_str.isspace():
                    plantID_idx = f[ID_int]
                    if self.plant3dAddOut_disabled or (self.plant3dAddOut == ""):
                        obs_str = '0'
                    else:
                        if str(f[self.plant3dAddOut]).replace("NULL", "0") == '1':
                            obs_str = '1'
                        else:
                            obs_str = '0'
                    aTmpDict[plantID_idx] = TmpTree3D(enviID=plantID_str, obs=obs_str)

            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.plant3dLayer_rot, field=ID_int,
                                                                   get_strArray=True)


        if self.plant3dID_UseCustom:
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    if grid1_int_array[i, j] == 999:
                        grid1_str_array[i, j] = self.plant3dID_custom
                        newTree = dict(rootcell_i=j, rootcell_j=self.JJ - i, rootcell_k=0, plantID=str(self.plant3dID_custom),
                                       name='Imported Plant', observe=0)
                        self.s_treeList.append(newTree)
        else:
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        tmpTree = aTmpDict.get(grid1_int_array[i, j])
                        if tmpTree is not None:
                            grid1_str_array[i, j] = tmpTree.enviID
                            newTree = dict(rootcell_i=j, rootcell_j=self.JJ - i, rootcell_k=0,
                                           plantID=tmpTree.enviID.replace("NULL", ""), name='Imported Plant',
                                           observe=tmpTree.obs)
                            self.s_treeList.append(newTree)
            aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding 3D Plants.", 'ENVI-met', level=Qgis.Info)
        return self.s_treeList

    def getDEM(self, interpolate: int = 1):
        # first clip the raster based on the not rotated subArea (maybe add some margins - only if raster is bigger than subArea)
        # get not-rotated extend of subArea
        # calculate extent of first feature
        spFeats = self.subAreaLayer_nonRot.getFeatures()
        for f in spFeats:
            if f.hasGeometry():
                f_geo = f.geometry()
                subArea_Extent = f_geo.boundingBox()
        
        
        #print(subArea_Extent)
        # now clip the raster to that extent
        # transform the coordinate system of subArea_nonRot_Extent to the ones of the DEM
        # subArea_nonRot_Extent = QgsRectangle(-73.99290836344986,40.77707305651126,-73.96828332218108,40.76350771117235)
        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)  # #"OVERCRS":False a NEW parameter for QGIS > 3.18           #QgsFeatureRequest.GeometrySkipInvalid
        '''
        rlayer_clip = processing.run("gdal:cliprasterbyextent",
                                     {"INPUT": self.dEMLayer,
                                      "PROJWIN": subArea_Extent,
                                      "OVERCRS": False,
                                      "OUTPUT": 'TEMPORARY_OUTPUT'},
                                     context=context)
        rlayerFN_clip = rlayer_clip['OUTPUT']
        # self.iface.addRasterLayer(rlayerFN_clip, "clip_debug")
        '''
        #print(self.subAreaLayer)
        #print(self.dEMLayer)
        if interpolate > 0:
            rlayer_resample = processing.run("gdal:warpreproject",
                                                {'INPUT': self.dEMLayer,
                                                'SOURCE_CRS': self.dEMLayer.crs(),
                                                'TARGET_CRS': self.subAreaLayer.crs(),
                                                'RESAMPLING': interpolate,           
                                                #'NODATA': -999.0, # if not provided then nodata values will be copied from the source dataset
                                                'TARGET_RESOLUTION': min(self.dx * 0.75, self.dy * 0.75), # here, we could set 1 meter or if resolution is even better that use dx/dy
                                                'OPTIONS': '',
                                                'DATA_TYPE': 0,
                                                'TARGET_EXTENT': subArea_Extent,
                                                'TARGET_EXTENT_CRS': None,
                                                'MULTITHREADING': True,
                                                'EXTRA': '',
                                                'OUTPUT': 'TEMPORARY_OUTPUT'},
                                                context=context)
            rlayerFN_clip = rlayer_resample['OUTPUT'] 
        else:     
            rlayer_resample = processing.run("gdal:warpreproject",
                                                {'INPUT': self.dEMLayer,
                                                'SOURCE_CRS': self.dEMLayer.crs(),
                                                'TARGET_CRS': self.subAreaLayer.crs(),
                                                'RESAMPLING': 0,
                                                #'NODATA': -999.0, # if not provided then nodata values will be copied from the source dataset
                                                'TARGET_RESOLUTION': None,
                                                'OPTIONS': '',
                                                'DATA_TYPE': 0,
                                                'TARGET_EXTENT': subArea_Extent,
                                                'TARGET_EXTENT_CRS': None,
                                                'MULTITHREADING': True,
                                                'EXTRA': '',
                                                'OUTPUT': 'TEMPORARY_OUTPUT'},
                                                context=context)
            rlayerFN_clip = rlayer_resample['OUTPUT']      

        #print(rlayerFN_clip)             

        # then vectorize using: raster pixels to points
        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        rlayer_vec = processing.run("native:pixelstopolygons",
                                    {"INPUT_RASTER": rlayerFN_clip,
                                     "RASTER_BAND": self.dEMBand,
                                     "FIELD_NAME": "HEIGHT",
                                     "OUTPUT": 'TEMPORARY_OUTPUT'},
                                    context=context)
        rlayerFN_vec = rlayer_vec['OUTPUT']
        # QgsProject.instance().addMapLayer(rlayerFN_vec)

        # then rotate the result
        spLayer = self.rotate_layer(rlayerFN_vec, False)
        # QgsProject.instance().addMapLayer(spLayer)

        # then grid the result
        grid1_int_array = self.rasterize_gdal(input_layer=spLayer, field='HEIGHT', no_data_val=-999, init_val=-999)

        # calc avg height
        avgHeight = 0
        avgCnt = 0
        for i in range(grid1_int_array.shape[0]):
            for j in range(grid1_int_array.shape[1]):
                if grid1_int_array[i, j] != -999:
                    avgHeight = avgHeight + grid1_int_array[i, j]
                    avgCnt = avgCnt + 1

        if avgCnt > 1:
            avgHeight = avgHeight / avgCnt

        # fill empty cells (-999)
        for i in range(grid1_int_array.shape[0]):
            for j in range(grid1_int_array.shape[1]):
                if grid1_int_array[i, j] == -999:
                    grid1_int_array[i, j] = avgHeight
                    '''
                    nextNeigh = False
                    neighCnt = 0
                    neighSum = 0 
                    srchRad = 1
                    # check left and top
                    while not nextNeigh:
                        # test left
                        if i - srchRad > 0:
                            if grid1_int_array[i - srchRad, j] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i - srchRad, j]
                                neighCnt += 1
                        # test right
                        if i + srchRad < grid1_int_array.shape[0]:
                            if grid1_int_array[i + srchRad, j] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i + srchRad, j]
                                neighCnt += 1
                        # test up
                        if j - srchRad > 0:
                            if grid1_int_array[i, j - srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i, j - srchRad]
                                neighCnt += 1
                        # test down
                        if j + srchRad > grid1_int_array.shape[1]:
                            if grid1_int_array[i, j + srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i, j + srchRad]
                                neighCnt += 1
                        # test diagonal left up
                        if i - srchRad > 0 and j - srchRad > 0:
                            if grid1_int_array[i - srchRad, j - srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i - srchRad, j - srchRad]
                                neighCnt += 1
                        # test diagonal left down
                        if i - srchRad > 0 and j + srchRad > grid1_int_array.shape[1]:
                            if grid1_int_array[i - srchRad, j + srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i - srchRad, j + srchRad]
                                neighCnt += 1
                        # test diagonal right down
                        if i + srchRad < grid1_int_array.shape[0] and j + srchRad > grid1_int_array.shape[1]:
                            if grid1_int_array[i + srchRad, j + srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i + srchRad, j + srchRad]
                                neighCnt += 1
                        # test diagonal right up
                        if i + srchRad < grid1_int_array.shape[0] and j - srchRad > 0:
                            if grid1_int_array[i + srchRad, j - srchRad] != -999:
                                nextNeigh = True
                                neighSum += grid1_int_array[i + srchRad, j - srchRad]
                                neighCnt += 1
                        # not found yet... increase srchRadius.....
                        if not nextNeigh:
                            srchRad = srchRad + 1
                        if nextNeigh:
                            grid1_int_array[i, j] = round(neighSum / neighCnt)
                        '''
        # find lowest DEM
        minHeight = 9999999
        for i in range(grid1_int_array.shape[0]):
            for j in range(grid1_int_array.shape[1]):
                if grid1_int_array[i, j] < minHeight:
                    minHeight = grid1_int_array[i, j]

        maxHeight = -9999999
        # then remove the level by the lowest number in the grid and save the DEM max height
        for i in range(grid1_int_array.shape[0]):
            for j in range(grid1_int_array.shape[1]):
                grid1_int_array[i, j] = grid1_int_array[i, j] - minHeight
                if grid1_int_array[i, j] > maxHeight:
                    maxHeight = grid1_int_array[i, j]

        self.refHeightDEM = minHeight
        self.maxHeightDEM = maxHeight

        return grid1_int_array

    def rasterSrcP(self):
        if self.srcPLayer.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
            return tmpAr.fill("")
        QgsMessageLog.logMessage("Started: Gridding Sources (Points)...", 'ENVI-met', level=Qgis.Info)

        # reproject to UTM
        self.srcPLayer = self.reprojectLayerToUTM(self.srcPLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)            #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.srcPLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )

        #self.srcPLayer_rot = self.rotate_layer(self.srcPLayer, False)
        self.srcPLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        self.srcPLayer_rot = self.reorgFID(self.srcPLayer_rot)

        aTmpDict = {}
        if not self.srcPID_UseCustom:
            i = 1
            for f in self.srcPLayer_rot.getFeatures():
                sID_str = f[self.srcPID]
                if sID_str and not sID_str.isspace():
                    # if the sourceID does not exist in the dict yet, add it
                    if aTmpDict.get(sID_str) is None:
                        # sID_str is the key, i the value
                        aTmpDict[sID_str] = i
                        i += 1
            # start editing
            self.srcPLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.srcPLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            # write the corresponding integer values in each row, depending on the EnviID used in that row
            for f in self.srcPLayer_rot.getFeatures():
                # get enviID as string
                sID_str = f[self.srcPID]
                sID_int = -1
                # get integer value for this enviID (surfID_str)
                value = aTmpDict.get(sID_str)
                # if the enviID exists in the dictionary
                if value is not None:
                    sID_int = value
                f[ID_int] = sID_int
                self.srcPLayer_rot.updateFeature(f)
            self.srcPLayer_rot.commitChanges()
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcPLayer_rot, field=ID_int,
                                                                   get_strArray=True)
        else:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcPLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)

        if not self.srcPID_UseCustom:
            # invert dictionary
            invTmpDict = {v: k for k, v in aTmpDict.items()}
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]
            invTmpDict.clear()
        else:
            grid1_str_array[grid1_int_array <= 0] = ""
            grid1_str_array[grid1_int_array == 999] = self.srcPID_custom

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Points).", 'ENVI-met', level=Qgis.Info)
        return grid1_str_array

    def rasterSrcL(self):
        if self.srcLLayer.name() == "notAvail" or (self.srcLID_UseCustom and (self.srcLID_custom == "notAvail")):
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
            return tmpAr.fill("")

        QgsMessageLog.logMessage("Started: Gridding Sources (Lines)...", 'ENVI-met', level=Qgis.Info)

        # reproject to UTM
        self.srcLLayer = self.reprojectLayerToUTM(self.srcLLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)            #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.srcLLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )
        #self.srcLLayer_rot = self.rotate_layer(self.srcLLayer, False)
        self.srcLLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        self.srcLLayer_rot = self.reorgFID(self.srcLLayer_rot)

        aTmpDict = {}
        if not self.srcLID_UseCustom:
            # get all items in the vector layer
            i = 1
            for f in self.srcLLayer_rot.getFeatures():
                sID_str = f[self.srcLID]
                if sID_str and not sID_str.isspace():
                    # if the sourceID does not exist in the dict yet, add it
                    if aTmpDict.get(sID_str) is None:
                        # sID_str is the key, i the value
                        aTmpDict[sID_str] = i
                        i += 1

            # start editing
            self.srcLLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.srcLLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            # write the corresponding integer values in each row, depending on the EnviID used in that row
            for f in self.srcLLayer_rot.getFeatures():
                # get enviID as string
                sID_str = f[self.srcLID]
                sID_int = -1
                # get integer value for this enviID (surfID_str)
                value = aTmpDict.get(sID_str)
                # if the enviID exists in the dictionary
                if value is not None:
                    sID_int = value
                f[ID_int] = sID_int
                self.srcLLayer_rot.updateFeature(f)
            self.srcLLayer_rot.commitChanges()

            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcLLayer_rot, field=ID_int,
                                                                   get_strArray=True)
        else:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcLLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)

        if not self.srcLID_UseCustom:
            # invert dictionary
            invTmpDict = {v: k for k, v in aTmpDict.items()}
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]
            invTmpDict.clear()
        else:
            grid1_str_array[grid1_int_array <= 0] = ""
            grid1_str_array[grid1_int_array == 999] = self.srcLID_custom

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Lines).", 'ENVI-met', level=Qgis.Info)
        return grid1_str_array

    def rasterSrcA(self):
        if self.srcALayer.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
            return tmpAr.fill("")

        QgsMessageLog.logMessage("Started: Gridding Sources (Areas)...", 'ENVI-met', level=Qgis.Info)
        
        # reproject to UTM
        self.srcALayer = self.reprojectLayerToUTM(self.srcALayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)            #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.srcALayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )
        #self.srcALayer_rot = self.rotate_layer(self.srcALayer, False)
        self.srcALayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        self.srcALayer_rot = self.reorgFID(self.srcALayer_rot)

        aTmpDict = {}

        if not self.srcAID_UseCustom:
            i = 1
            for f in self.srcALayer_rot.getFeatures():
                sID_str = f[self.srcAID]
                if sID_str and not sID_str.isspace():
                    # if the sourceID does not exist in the dict yet, add it
                    if aTmpDict.get(sID_str) is None:
                        # sID_str is the key, i the value
                        aTmpDict[sID_str] = i
                        i += 1

            self.srcALayer_rot.startEditing()
            ID_int = 'ID_int'
            self.srcALayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            # write the corresponding integer values in each row, depending on the EnviID used in that row
            for f in self.srcALayer_rot.getFeatures():
                # get enviID as string
                sID_str = f[self.srcAID]
                sID_int = -1
                # get integer value for this enviID (surfID_str)
                value = aTmpDict.get(sID_str)
                # if the enviID exists in the dictionary
                if value is not None:
                    sID_int = value
                f[ID_int] = sID_int
                self.srcALayer_rot.updateFeature(f)
            self.srcALayer_rot.commitChanges()

            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcALayer_rot, field=ID_int,
                                                                   get_strArray=True)
        else:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.srcALayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)

        if not self.srcAID_UseCustom:
            # invert dictionary
            invTmpDict = {v: k for k, v in aTmpDict.items()}
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]
            invTmpDict.clear()
        else:
            grid1_str_array[grid1_int_array <= 0] = ""
            grid1_str_array[grid1_int_array == 999] = self.srcAID_custom

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Areas).", 'ENVI-met', level=Qgis.Info)
        return grid1_str_array

    def buildReceptors(self):
        self.s_recList.clear()
        if self.recLayer.name() == "notAvail":
            return self.s_recList
        
        # reproject to UTM
        self.recLayer = self.reprojectLayerToUTM(self.recLayer, False)

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)            #QgsFeatureRequest.GeometrySkipInvalid
        aTmpLayer = processing.run("qgis:extractbylocation", {
            "INPUT": self.recLayer, \
            "PREDICATE": [0], \
            "INTERSECT": self.subAreaLayer_nonRot, \
            "OUTPUT": 'TEMPORARY_OUTPUT'},
            context=context
                       )
        #QgsProject.instance().addMapLayer(aTmpLayer["OUTPUT"])

        QgsMessageLog.logMessage("Started: Gridding Receptors...", 'ENVI-met', level=Qgis.Info)
        #self.recLayer_rot = self.rotate_layer(self.recLayer, False)
        self.recLayer_rot = self.rotate_layer(aTmpLayer["OUTPUT"], False)

        # get all items in the vector layer
        if self.recLayer_rot.getFeatures() is None:
            return self.s_recList

        aTmpDict = {}
        if self.recID_UseCustom:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.recLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)
        else:
            # User wants to use an attribute field: get field where the ID string is stored

            i = 1
            for f in self.recLayer_rot.getFeatures():
                recID_str = f[self.recID]
                if recID_str and not recID_str.isspace():
                    # if the plantID does not exist in the dict yet, add it
                    if aTmpDict.get(recID_str) is None:
                        # plantID_str is the key, i the value
                        aTmpDict[recID_str] = i
                        i += 1
            self.recLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.recLayer_rot.addAttribute(QgsField(ID_int, QVariant.Int))

            for f in self.recLayer_rot.getFeatures():
                # get enviID in string
                recID_str = f[self.recID]
                recID_int = -1
                # get integer value for this enviID (surfID_str)
                value = aTmpDict.get(recID_str)
                # if the enviID exists in the dictionary
                if value is not None:
                    recID_int = value
                f[ID_int] = recID_int
                self.recLayer_rot.updateFeature(f)
            self.recLayer_rot.commitChanges()
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.recLayer_rot, field=ID_int, get_strArray=True)
            #QgsVectorFileWriter.writeAsVectorFormat(self.recLayer_rot, "C:/Users/simonhe/AppData/Local/Temp/processing_HWIddK/760a68c50707482880b5084165a1d3b3/a", "UTF-8", self.recLayer_rot.crs(), "ESRI Shapefile")
            #print(grid1_str_array)

        ENVI_ID_int = -1
        if self.recID_UseCustom:
            self.recID_custom = "r_"
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    if grid1_int_array[i, j] == 999:
                        ENVI_ID_int = ENVI_ID_int + 1
                        grid1_str_array[i, j] = self.recID_custom + "{:04d}".format(ENVI_ID_int)
                        newRec = dict(cell_i=j, cell_j=self.JJ - i, name=str(grid1_str_array[i, j]))
                        self.s_recList.append(newRec)
        else:
            # invert dictionary
            invTmpDict = {v: k for k, v in aTmpDict.items()}
            for i in range(grid1_int_array.shape[0]):
                for j in range(grid1_int_array.shape[1]):
                    if grid1_int_array[i, j] <= 0:
                        grid1_str_array[i, j] = ""
                    else:
                        grid1_str_array[i, j] = invTmpDict[grid1_int_array[i, j]]
                        newRec = dict(cell_i=j, cell_j=self.JJ - i, name=str(grid1_str_array[i, j]))
                        self.s_recList.append(newRec)
            aTmpDict.clear()
            invTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Receptors.", 'ENVI-met', level=Qgis.Info)
        return self.s_recList
    
    def reprojectLayerToUTM(self, aLayer, isSubAreaLayer: bool):
        #print(aLayer.crs().authid().split(":")[1])
        if not(aLayer.crs().authid().split(":")[1] == str(4326)):
            #print('in_if')
            proj = pyproj.Transformer.from_crs(aLayer.crs().authid(), 4326, always_xy=True)
            x1, y1 = (aLayer.extent().xMinimum(), aLayer.extent().yMinimum())
            lon, lat = proj.transform(x1, y1)
        else:
            for feature in aLayer.getFeatures():
                geom = feature.geometry()
                
                # Calculate the centroid of the polygon
                centroid = geom.centroid().asPoint()
                
                # Extract latitude (y) and longitude (x) from the centroid
                lon = centroid.x()
                lat = centroid.y()
                #print(f"Centroid - Longitude: {lon}, Latitude: {lat}")
        aUTMZone = self.get_UTM_zone(lon, lat)
        #print(aUTMZone)
        auth_id = self.find_crs_auth_id("WGS 84 / UTM zone " + aUTMZone.replace(' ',''))
        #print(auth_id) 

        # fill vars only if subAreaLayer
        if isSubAreaLayer:
            self.lon = lon
            self.lat = lat
            self.UTMZone = aUTMZone.split(" ")[0]
            self.UTMHemisphere = aUTMZone.split(" ")[1]

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        parameter = {
            'INPUT': aLayer,
            'TARGET_CRS': 'EPSG:' + str(auth_id),
            'OUTPUT': 'memory:Reprojected'
        }
        #print(parameter)
        return processing.run('native:reprojectlayer', parameter, context=context)['OUTPUT']

    def reprojectRasterLayerToUTM(self, aLayer):
        proj = pyproj.Transformer.from_crs(aLayer.crs().authid(), 4326, always_xy=True)
        x1, y1 = (aLayer.extent().xMinimum(), aLayer.extent().yMinimum())
        lon, lat = proj.transform(x1, y1)
        aUTMZone = self.get_UTM_zone(lon, lat)
        #print(aUTMZone)
        auth_id = self.find_crs_auth_id("WGS 84 / UTM zone " + aUTMZone.replace(' ',''))
        #print(auth_id) 

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
        reshaped = processing.run("gdal:warpreproject",
                                  {'INPUT': aLayer,
                                   'SOURCE_CRS': aLayer.crs(),
                                   'TARGET_CRS': 'EPSG:' + str(auth_id),
                                   'RESAMPLING': 0,
                                   'OPTIONS': '',
                                   'DATA_TYPE': 0,
                                   'TARGET_EXTENT': None,
                                   'TARGET_EXTENT_CRS': None,
                                   'MULTITHREADING': True,
                                   'EXTRA': '',
                                   'OUTPUT': 'TEMPORARY_OUTPUT'},
                                  context=context)
        #print(reshaped['OUTPUT'])
        return reshaped['OUTPUT']

    def saveINX(self):
        QgsMessageLog.logMessage("--- Started Exporting INX-File ---", 'ENVI-met', level=Qgis.Info)

        # precaution -> we always reproject to UTM
        self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot,True)
        self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer,True)   
        self.get_modelrot()

        # fill data
        self.II = round((self.subAreaExtent.xMaximum() - self.subAreaExtent.xMinimum()) / self.dx)
        self.JJ = round((self.subAreaExtent.yMaximum() - self.subAreaExtent.yMinimum()) / self.dy)
        if self.useSplitting:
            self.finalKK = self.KK + 4
        else:
            self.finalKK = self.KK
        '''
        # recalc to long lat
        extCRS = self.subAreaLayer.crs()
        proj = pyproj.Transformer.from_crs(extCRS.authid(), 4326, always_xy=True)
        x1, y1 = (self.subAreaExtent.xMinimum(), self.subAreaExtent.yMinimum())
        lon, lat = proj.transform(x1, y1)

        self.lon = lon
        self.lat = lat
        self.UTMZone = self.get_UTM_zone(lon, lat)

        auth_id = self.find_crs_auth_id("WGS 84 / UTM zone " + self.UTMZone.replace(' ',''))
        print(auth_id) 

        context = dataobjects.createContext()
        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)                #QgsFeatureRequest.GeometrySkipInvalid

        parameter = {
            'INPUT': self.subAreaLayer,
            'TARGET_CRS': 'EPSG:' + str(auth_id),
            'OUTPUT': 'memory:Reprojected'
        }
        result = processing.run('native:reprojectlayer', parameter, context=context)['OUTPUT']
        QgsProject.instance().addMapLayer(result)
        '''
        timeZone = float(self.get_time_zone_geonames())

        if timeZone < 0:
            self.timeZoneName = "UTC-" + str(abs(timeZone))
        else:
            self.timeZoneName = "UTC+" + str(abs(timeZone))
        self.timeZoneLonRef = timeZone * 15

        # report the current progress via pyqt signal
        self.progress.emit(5)

        # convert data
        # first buildingInfo so that we have building numbers
        self.buildBInfo()
        self.progress.emit(10)

        # bNumberarray and bTop
        if self.bTop_UseCustom or (self.bLayer.name() == "notAvail") or (self.bTop == "notAvail") or (self.bTop == ""):
            if self.bTop_UseCustom:
                bNumber_int_array = self.rasterBNumber()
                bTop_int_array = self.rasterBTop()
            else:
                bTop_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
                bNumber_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
        else:
            bNumber_int_array = self.rasterBNumber()
            bTop_int_array = self.rasterBTop()

        self.progress.emit(15)
        # then bBottom
        if self.bBot_UseCustom or (self.bLayer.name() == "notAvail") or (self.bBot == "notAvail") or (self.bBot == ""):
            if self.bBot_UseCustom:
                bBot_int_array = self.rasterBBot()
            else:
                bBot_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
        else:
            bBot_int_array = self.rasterBBot()

        # fixed height tag not supported yet
        bFixHeight_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
        if not self.bNOTFixedH:
            for i in range(bTop_int_array.shape[0]):
                for j in range(bTop_int_array.shape[1]):
                    if bTop_int_array[i, j] > 0:
                        bFixHeight_int_array[i, j] = 1
        self.progress.emit(20)

        # plants1d
        if self.plant1dLayerFromVector:
            if self.plant1dID_UseCustom or (self.plant1dLayer.name() == "notAvail") or (self.plant1dID == "notAvail") or (self.plant1dID == ""):
                if self.plant1dID_UseCustom:
                    simplePlant_str_array = self.raster_simple_plants_from_vector()
                else:
                    simplePlant_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
                    simplePlant_str_array = simplePlant_int_array.astype(str)

                simplePlant_str_array[simplePlant_str_array == "0"] = ""
            else:
                simplePlant_str_array = self.raster_simple_plants_from_vector()
        else:
            # simple plants from raster input
            # if no raster-layer was selected in UI or no definitions were set in the text-edit
            if (self.plant1dLayer_raster.name() == "notAvail") or (len(self.plant1dLayer_raster_def) == 0):
                simplePlant_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
                simplePlant_str_array = simplePlant_int_array.astype(str)
                simplePlant_str_array[simplePlant_str_array == "0"] = ""
            else:
                simplePlant_str_array = self.raster_simple_plants_from_raster()

        self.progress.emit(30)

        # plants3d
        self.buildPlants3d()
        self.progress.emit(40)

        # surfaces
        if self.surfLayerfromVector:
            if self.surfID_UseCustom or (self.surfLayer.name() == "notAvail") or (self.surfID == "notAvail") or (self.surfID == ""):
                surf_str_array = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
                if self.surfID_UseCustom:
                    surf_str_array.fill(self.surfID_custom)
                else:
                    surf_str_array.fill('0200PP')
            else:
                surf_str_array = self.raster_surface_from_vector()
        else:
            # surfaces from raster-input
            # if no raster-layer was selected in UI or no definitions were set in the text-edit
            if (self.surfLayer_raster.name() == "notAvail") or (len(self.surfLayer_raster_def) == 0):
                surf_str_array = np.zeros(shape=(self.JJ, self.II), dtype='<U6')
                surf_str_array.fill('0200PP')
            else:
                surf_str_array = self.raster_surface_from_raster()

        self.progress.emit(50)

        # receptors
        self.buildReceptors()

        # sources Points
        if self.srcPID_UseCustom or (self.srcPLayer.name() == "notAvail") or (self.srcPID == "notAvail") or (self.srcPID == ""):
            srcP_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)  # create a new array that holds all sources
            srcP_str_array = srcP_int_array.astype(str)
            if self.srcPID_UseCustom:
                srcP_str_array = self.rasterSrcP()
            srcP_str_array[srcP_str_array == "0"] = ""
        else:
            srcP_str_array = self.rasterSrcP()

        # sources Lines
        if self.srcLID_UseCustom or (self.srcLLayer.name() == "notAvail") or (self.srcLID == "notAvail") or (self.srcLID == ""):
            srcL_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)  # create a new array that holds all sources
            srcL_str_array = srcL_int_array.astype(str)
            if self.srcLID_UseCustom:
                srcL_str_array = self.rasterSrcL()
            srcL_str_array[srcL_str_array == "0"] = ""
        else:
            srcL_str_array = self.rasterSrcL()

        # sources Areas
        if self.srcAID_UseCustom or (self.srcALayer.name() == "notAvail") or (self.srcAID == "notAvail") or (self.srcAID == ""):
            srcA_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)  # create a new array that holds all sources
            srcA_str_array = srcA_int_array.astype(str)
            if self.srcAID_UseCustom:
                srcA_str_array = self.rasterSrcA()
            srcA_str_array[srcA_str_array == "0"] = ""
        else:
            srcA_str_array = self.rasterSrcA()

        # now handle srcArray P > L > A
        src_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)   # create a new array that holds all sources
        src_str_array = src_int_array.astype(str)
        for i in range(srcA_str_array.shape[0]):
            for j in range(srcA_str_array.shape[1]):
                src_str_array[i, j] = ""
                if not srcA_str_array[i, j] == "":
                    src_str_array[i, j] = srcA_str_array[i, j]
                if not srcL_str_array[i, j] == "":
                    src_str_array[i, j] = srcL_str_array[i, j]
                if not srcP_str_array[i, j] == "":
                    src_str_array[i, j] = srcP_str_array[i, j]

        self.progress.emit(60)

        # DEM
        if (self.dEMLayer.name() == "notAvail") or (self.dEMBand <= 0):
            dem_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
        else:
            QgsMessageLog.logMessage("Started: Gridding Terrain...", 'ENVI-met', level=Qgis.Info)
            dem_int_array = self.getDEM(interpolate = self.dEMInterpol)
            QgsMessageLog.logMessage("Finished: Gridding Terrain.", 'ENVI-met', level=Qgis.Info)

        self.elevation = self.get_elevation_geonames()

        self.progress.emit(70)

        QgsMessageLog.logMessage("Preparing Model Border...", 'ENVI-met', level=Qgis.Info)
        # empty cells at border -> only for buildings
        if self.removeBBorder > 0:
            bRemSet = set(())
            for i in range(bTop_int_array.shape[0]):
                for j in range(bTop_int_array.shape[1]):
                    # bTop; bBot; bNumber2d
                    if (i < self.removeBBorder) or (j < self.removeBBorder) or (
                            i > (bTop_int_array.shape[0] - self.removeBBorder)) or (
                            j > (bTop_int_array.shape[1] - self.removeBBorder)):
                        if bNumber_int_array[i, j] > 0:
                            bRemSet.add(bNumber_int_array[i, j])
                        bFixHeight_int_array[i, j] = 0
                        bTop_int_array[i, j] = 0
                        bBot_int_array[i, j] = 0
                        bNumber_int_array[i, j] = 0
            # now update bList
            for bRem in bRemSet:
                bCanBeRemoved = True
                for i in range(bNumber_int_array.shape[0]):
                    for j in range(bNumber_int_array.shape[1]):
                        if bNumber_int_array[i, j] == bRem:
                            bCanBeRemoved = False
                if bCanBeRemoved:
                    if self.s_buildingDict.get(bRem) is not None:
                        del self.s_buildingDict[bRem]

        # check if buildings should be leveled with DEM
        QgsMessageLog.logMessage("Preparing Buildings in DEM...", 'ENVI-met', level=Qgis.Info)
        if not (self.dEMLayer.name() == "notAvail") and not (self.dEMBand <= 0) and self.bLeveled:
            # create a new temp empty list of buildings that also holds a list of cells
            bListDEM = []
            # first get all cells that belong to a building and put them in a list
            for i in range(bNumber_int_array.shape[0]):
                for j in range(bNumber_int_array.shape[1]):
                    newBuild = True
                    if bNumber_int_array[i, j] > 0:
                        for key in bListDEM:
                            if key.bNumber == bNumber_int_array[i, j]:
                                cell = Cell(i, j, 0)
                                key.cellList.append(cell)
                                newBuild = False
                                break
                        if newBuild:
                            bLevel = BLevel(bNumber_int_array[i, j])
                            cell = Cell(i, j, 0)
                            bLevel.cellList.append(cell)
                            bListDEM.append(bLevel)

            # now go through the list and find the lowest terrain below a building
            for key in bListDEM:
                minDEM = 99999999
                for c in key.cellList:
                    if dem_int_array[c.i, c.j] < minDEM:
                        minDEM = dem_int_array[c.i, c.j]
                # now check if a terrain is higher and by how much, then, reduce the terrain by that amount
                for c in key.cellList:
                    hCorr = dem_int_array[c.i, c.j] - minDEM
                    if hCorr > 0:
                        dem_int_array[c.i, c.j] = dem_int_array[c.i, c.j] - hCorr

        # check if vegetation on buildings should be removed
        QgsMessageLog.logMessage("Check if Vegetation on Buildings should be removed...", 'ENVI-met', level=Qgis.Info)
        if self.removeVegBuild:
            for i in range(bNumber_int_array.shape[0]):
                for j in range(bNumber_int_array.shape[1]):
                    if bNumber_int_array[i, j] > 0:
                        # remove simple plants
                        if simplePlant_str_array[i, j] != "":
                            simplePlant_str_array[i, j] = ""
                        # remove trees
                        for tree in self.s_treeList:
                            if (tree.get("rootcell_i") == j) and (tree.get("rootcell_j") == self.JJ - i):
                                self.s_treeList.remove(tree)

        # check buildings need to be removed e.g. building height = 0 or < 0
        QgsMessageLog.logMessage("Check integrity of Buildings...", 'ENVI-met', level=Qgis.Info)
        bRemSet02 = set(())
        for i in range(bTop_int_array.shape[0]):
            for j in range(bTop_int_array.shape[1]):
                if bTop_int_array[i, j] <= 0 or bBot_int_array[i, j] >= bTop_int_array[i, j]:
                    # remove building in 2d
                    bTop_int_array[i, j] = 0
                    bBot_int_array[i, j] = 0
                    bRemSet02.add(bNumber_int_array[i, j])
                    bNumber_int_array[i, j] = 0

        # now update bList
        for bRem02 in bRemSet02:
            bCanBeRemoved = True
            for i in range(bNumber_int_array.shape[0]):
                for j in range(bNumber_int_array.shape[1]):
                    if bNumber_int_array[i, j] == bRem02:
                        bCanBeRemoved = False
            if bCanBeRemoved:
                if self.s_buildingDict.get(bRem02) is not None:
                    del self.s_buildingDict[bRem02]                           

        self.progress.emit(80)
        QgsMessageLog.logMessage("Converting Data to ENVI-met model area...", 'ENVI-met', level=Qgis.Info)
        # finally convert to matrix
        bTop_str_matrix = np.array2string(bTop_int_array, max_line_width=1000000, separator=",")
        bTop_str_matrix = bTop_str_matrix.replace(" ", "").replace("[", "").replace("]", "")
        bBot_str_matrix = np.array2string(bBot_int_array, max_line_width=1000000, separator=",")
        bBot_str_matrix = bBot_str_matrix.replace(" ", "").replace("[", "").replace("]", "")
        bNumber_str_matrix = np.array2string(bNumber_int_array, max_line_width=1000000, separator=",")
        bNumber_str_matrix = bNumber_str_matrix.replace(" ", "").replace("[", "").replace("]", "")
        bFixHeight_str_matrix = np.array2string(bFixHeight_int_array, max_line_width=1000000, separator=",")
        bFixHeight_str_matrix = bFixHeight_str_matrix.replace(" ", "").replace("[", "").replace("]", "")

        # terrain
        dem_str_matrix = np.array2string(dem_int_array, max_line_width=1000000, separator=",")
        dem_str_matrix = dem_str_matrix.replace(" ", "").replace("[", "").replace("]", "")

        # plants
        simplePlant_str_matrix = np.array2string(simplePlant_str_array, max_line_width=1000000, separator=",")
        simplePlant_str_matrix = simplePlant_str_matrix.replace(" ", "").replace("[", "").replace("]", "").replace("'","").replace("NULL", "")

        # surfaces
        surf_str_matrix = np.array2string(surf_str_array, max_line_width=1000000, separator=",")
        surf_str_matrix = surf_str_matrix.replace(" ", "").replace("[", "").replace("]", "").replace("'", "").replace("NULL", "")

        # sources
        src_str_matrix = np.array2string(src_str_array, max_line_width=1000000, separator=",")
        src_str_matrix = src_str_matrix.replace(" ", "").replace("[", "").replace("]", "").replace("'", "").replace("NULL", "")

        self.progress.emit(90)
        QgsMessageLog.logMessage("Writing file...", 'ENVI-met', level=Qgis.Info)
        with open(self.filename, 'w') as output_file:
            # Print functions
            print("<ENVI-MET_Datafile>", file=output_file)
            print("  <Header>", file=output_file)
            print("    <filetype>INPX ENVI-met Area Input File</filetype>", file=output_file)
            print("    <version>4</version>", file=output_file)
            print("    <revisiondate>  </revisiondate>", file=output_file)
            print("    <remark> model created by QGIS plugin, additional settings: def roof material: " + self.defaultWall + "; def wall material: " + self.defaultRoof + "; clear buildings cells at border: " + str(self.removeBBorder) + "; leveled buildings in DEM: " + str(self.bLeveled) + "; building height not fixed: " + str(self.bNOTFixedH) + "; starting surface: " + self.startSurfID + "; remove veg from buildings: " + str(self.removeVegBuild) + " </remark>", file=output_file)
            print("    <fileInfo> model created by QGIS plugin </fileInfo>", file=output_file)            
            print("    <encryptionlevel>0</encryptionlevel>", file=output_file)
            print("  </Header>", file=output_file)
            print("  <baseData>", file=output_file)
            print("    <modelDescription> generated by geodata2ENVI-met </modelDescription>", file=output_file)
            print("    <modelAuthor>  </modelAuthor>", file=output_file)
            print("  </baseData>", file=output_file)
            print("  <modelGeometry>", file=output_file)
            print("    <grids-I> " + str(self.II) + " </grids-I>", file=output_file)
            print("    <grids-J> " + str(self.JJ) + " </grids-J>", file=output_file)
            print("    <grids-Z> " + str(self.KK) + " </grids-Z>", file=output_file)
            print("    <dx> " + str(self.dx) + " </dx>", file=output_file)
            print("    <dy> " + str(self.dy) + " </dy>", file=output_file)
            print("    <dz-base> " + str(self.dz) + " </dz-base>", file=output_file)
            if self.useTelescoping:
                print("    <useTelescoping_grid> 1 </useTelescoping_grid>", file=output_file)
            else:
                print("    <useTelescoping_grid> 0 </useTelescoping_grid>", file=output_file)
            if self.useSplitting:
                print("    <useSplitting> 1 </useSplitting>", file=output_file)
            else:
                print("    <useSplitting> 0 </useSplitting>", file=output_file)
            print("    <verticalStretch> " + str(self.teleStretch) + " </verticalStretch>", file=output_file)
            print("    <startStretch> " + str(self.teleStart) + " </startStretch>", file=output_file)
            print("    <has3DModel> 1 </has3DModel>", file=output_file)
            print("    <isFull3DDesign> 0 </isFull3DDesign>", file=output_file)
            print("  </modelGeometry>", file=output_file)

            print("  <nestingArea>", file=output_file)
            print("    <numberNestinggrids> 0 </numberNestinggrids>", file=output_file)
            print("    <soilProfileA> 0200LO </soilProfileA>", file=output_file)
            print("    <soilProfileB> 0200LO </soilProfileB>", file=output_file)
            print("  </nestingArea>", file=output_file)

            print("  <locationData>", file=output_file)
            print("    <modelRotation> " + str(-self.model_rot) + " </modelRotation>", file=output_file)
            print("    <projectionSystem> " + str(self.subAreaLayer.crs().authid()) + " </projectionSystem>", file=output_file)
            print("    <UTMZone> " + str(self.UTMZone) + " </UTMZone>", file=output_file)
            print("    <realworldLowerLeft_X> " + str(self.subAreaExtent.xMinimum()) + " </realworldLowerLeft_X>",
                  file=output_file)
            print("    <realworldLowerLeft_Y> " + str(self.subAreaExtent.yMinimum()) + " </realworldLowerLeft_Y>",
                  file=output_file)
            print("    <locationName> data export from QGIS </locationName>", file=output_file)
            print("    <location_Longitude> " + str(self.lon) + " </location_Longitude>", file=output_file)
            print("    <location_Latitude> " + str(self.lat) + " </location_Latitude>", file=output_file)
            print("    <locationTimeZone_Name> " + self.timeZoneName + " </locationTimeZone_Name>", file=output_file)
            print("    <locationTimeZone_Longitude> " + str(self.timeZoneLonRef) + " </locationTimeZone_Longitude>",
                  file=output_file)
            print("    <elevation> " + str(self.elevation) + " </elevation>", file=output_file)
            print("  </locationData>", file=output_file)

            print("  <defaultSettings>", file=output_file)
            print("    <commonWallMaterial> " + self.defaultWall + "</commonWallMaterial>", file=output_file)
            print("    <commonRoofMaterial> " + self.defaultRoof + "</commonRoofMaterial>", file=output_file)
            print("  </defaultSettings>", file=output_file)

            print("  <buildings2D>", file=output_file)
            print("    <zTop type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">",
                  file=output_file)
            print(bTop_str_matrix, file=output_file)
            print("     </zTop>", file=output_file)
            print("     <zBottom type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">",
                  file=output_file)
            print(bBot_str_matrix, file=output_file)
            print("     </zBottom>", file=output_file)
            print(
                "     <buildingNr type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">",
                file=output_file)
            print(bNumber_str_matrix, file=output_file)
            print("     </buildingNr>", file=output_file)
            print(
                "     <fixedheight type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">",
                file=output_file)
            print(bFixHeight_str_matrix, file=output_file)
            print("     </fixedheight>", file=output_file)
            print("  </buildings2D>", file=output_file)

            for key in self.s_buildingDict.keys():
                bld = self.s_buildingDict[key]
                print("  <Buildinginfo>", file=output_file)
                print("    <BuildingInternalNr> " + str(bld.BuildingInternalNumber) + " </BuildingInternalNr>",
                      file=output_file)
                print("    <BuildingName> " + bld.BuildingName + " </BuildingName>", file=output_file)
                print("    <BuildingWallMaterial> " + bld.BuildingWallMaterial + " </BuildingWallMaterial>",
                      file=output_file)
                print("    <BuildingRoofMaterial> " + bld.BuildingRoofMaterial + " </BuildingRoofMaterial>",
                      file=output_file)
                print("    <BuildingFacadeGreening> " + bld.BuildingFacadeGreening + " </BuildingFacadeGreening>",
                      file=output_file)
                print("    <BuildingRoofGreening> " + bld.BuildingRoofGreening + " </BuildingRoofGreening>",
                      file=output_file)
                print("    <ObserveBPS> " + bld.BuildingBPS + " </ObserveBPS>",
                      file=output_file)
                print("  </Buildinginfo>", file=output_file)

            print("  <simpleplants2D>", file=output_file)
            print(
                "     <ID_plants1D type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">",
                file=output_file)
            print(simplePlant_str_matrix, file=output_file)
            print("  </simpleplants2D>", file=output_file)

            for tree in self.s_treeList:
                print("  <3Dplants>", file=output_file)
                print("    <rootcell_i> " + str(tree.get("rootcell_i") + 1) + " </rootcell_i>",
                      file=output_file)  # the index is + 1 in envimet
                print("    <rootcell_j> " + str(tree.get("rootcell_j")) + " </rootcell_j>",
                      file=output_file)  # this index is correct in envimet
                print("    <rootcell_k> " + str(tree.get("rootcell_k")) + " </rootcell_k>", file=output_file)
                print("    <plantID> " + tree.get("plantID") + " </plantID>", file=output_file)
                print("    <name> " + tree.get("name") + " </name>", file=output_file)
                print("    <observe> " + str(tree.get("observe")) + " </observe>", file=output_file)
                print("  </3Dplants>", file=output_file)

            print("  <soils2D>", file=output_file)
            print("     <ID_soilprofile type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file=output_file)
            print(surf_str_matrix, file=output_file)
            print("     </ID_soilprofile>", file=output_file)
            print("  </soils2D>", file=output_file)

            print("  <dem>", file=output_file)
            print("     <DEMReference> " + str(self.refHeightDEM) + " </DEMReference>", file=output_file)
            print("     <terrainheight type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(
                self.JJ) + "\">", file=output_file)
            print(dem_str_matrix, file=output_file)
            print("     </terrainheight>", file=output_file)
            print("  </dem>", file=output_file)
            print("  <sources2D>", file=output_file)
            print("     <ID_sources type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file = output_file)
            print(src_str_matrix, file=output_file)
            print("     </ID_sources>", file=output_file)
            print("  </sources2D>", file=output_file)

            for rec in self.s_recList:
                print("  <Receptors>", file=output_file)
                print("    <cell_i> " + str(rec.get("cell_i") + 1) + " </cell_i>", file=output_file)  # the index is + 1 in envimet
                print("    <cell_j> " + str(rec.get("cell_j")) + " </cell_j>", file=output_file)  # this index is correct in envimet
                print("    <name> " + rec.get("name") + " </name>", file=output_file)
                print("  </Receptors>", file=output_file)

            """
            # print("  <receptors2D>", file = output_file)
            # print("     <ID_receptors type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file = output_file)
            # print(rec_str_matrix, file = output_file)
            # print("     </ID_receptors>", file = output_file)
            # print("  </receptors2D>", file = output_file)
            # print("  <additionalData>", file = output_file)
            # print("     <db_link_point type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file = output_file)
            # print(dbPoint_str_matrix.replace("1", "").replace("2", "").replace("3", "").replace("4", "").replace("5", "").replace("6", "").replace("7", "").replace("8", "").replace("9", "").replace("0","").replace(" ","").replace("[","").replace("]",""), file = output_file)
            # print("     </db_link_point>", file = output_file)
            # print("     <db_link_area type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file = output_file)
            # print(dbArea_str_matrix.replace("1", "").replace("2", "").replace("3", "").replace("4", "").replace("5", "").replace("6", "").replace("7", "").replace("8", "").replace("9", "").replace("0","").replace(" ","").replace("[","").replace("]",""), file = output_file)
            # print("     </db_link_area>", file = output_file)
            # print("  </additionalData>", file = output_file)
            # print("  <modelGeometry3D>", file = output_file)
            # print("     <grids3D-I> " + str(self.II) + " </grids3D-I>", file = output_file)
            # print("     <grids3D-J> " + str(self.JJ) + " </grids3D-J>", file = output_file)
            # print("     <grids3D-K> " + str(self.KK3d) + " </grids3D-K>", file = output_file)
            # print("  </modelGeometry3D>", file = output_file)
            """
            print("</ENVI-MET_Datafile>", file=output_file)

        self.progress.emit(100)
        QgsMessageLog.logMessage("--- Finished Exporting INX-File ---", 'ENVI-met', level=Qgis.Info)

    def calc_vert_ext(self):
        if self.subAreaLayer.name() == "notAvail":
            return

        self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot,True)
        self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer,True)   
        self.get_modelrot()

        self.II = round((self.subAreaExtent.xMaximum() - self.subAreaExtent.xMinimum()) / self.dx)
        self.JJ = round((self.subAreaExtent.yMaximum() - self.subAreaExtent.yMinimum()) / self.dy)

        if (self.bLayer.name() == "notAvail") or (self.bTop == "notAvail") or (self.bLayer.name() == "") or (self.bTop == ""):
            self.maxHeightB = 0
        else:
            # reproject to UTM
            self.bLayer = self.reprojectLayerToUTM(self.bLayer, False)

            # only rotate buildings inside subarea
            context = dataobjects.createContext()
            context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)               #QgsFeatureRequest.GeometrySkipInvalid         
            aTmpLayer = processing.run("qgis:extractbylocation", 
                                       {"INPUT": self.bLayer,
                                        "PREDICATE": [0],
                                        "INTERSECT": self.subAreaLayer_nonRot,
                                        "OUTPUT": 'TEMPORARY_OUTPUT'},
                                        context=context)
            #bLayer = self.rotate_layer(self.bLayer, False)
            bLayer = self.rotate_layer(aTmpLayer["OUTPUT"], False)

            layer_provider = bLayer.dataProvider()

            # get all items in the vector layer BUILDINGS
            if bLayer.getFeatures() is None:
                self.maxHeightB = 0
            else:
                bFeats = bLayer.getFeatures()

                for f in bFeats:
                    if f.geometry().intersects(self.subAreaExtent):
                        bHeight = f[self.bTop]
                        if bHeight > self.maxHeightB:
                            self.maxHeightB = bHeight
        #print(self.bTop_UseCustom)
        if self.bTop_UseCustom:
            #print("here")
            #print(self.bTop_custom)
            self.maxHeightB = self.bTop_custom

        # now get the terrain max height
        if (self.dEMLayer.name() == "notAvail") or (self.dEMBand < 1):
            self.maxHeightDEM = 0
        else:
            #self.maxHeightDEM = 0
            self.getDEM(interpolate = 0)  # self.maxHeightDEM is now filled

        self.maxHeightTotal = self.maxHeightB + self.maxHeightDEM

        self.finished.emit()

    def previewdxy(self):
        if self.subAreaLayer.name() == "notAvail":
            self.finished.emit()
            return
        else:
            self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot,True)
            self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer,True)   
            self.get_modelrot()
            self.II = round((self.subAreaExtent.xMaximum() - self.subAreaExtent.xMinimum()) / self.dx)
            self.JJ = round((self.subAreaExtent.yMaximum() - self.subAreaExtent.yMinimum()) / self.dy)
            self.xMeters = round(self.subAreaExtent.xMaximum() - self.subAreaExtent.xMinimum())
            self.yMeters = round(self.subAreaExtent.yMaximum() - self.subAreaExtent.yMinimum())
            self.finished.emit()

    def previewdz(self):
        if self.useSplitting:
            self.finalKK = self.KK + 4
        else:
            self.finalKK = self.KK

        self.dzAr = np.zeros(self.finalKK, dtype=float)
        self.zLvl_bot = np.zeros(self.finalKK, dtype=float)
        self.zLvl_center = np.zeros(self.finalKK, dtype=float)
        if not self.useTelescoping:
            if self.useSplitting:
                for k in range(5):
                    self.dzAr[k] = self.dz / 5
                for k in range(5, self.finalKK):
                    self.dzAr[k] = self.dz
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
            else:
                for k in range(self.finalKK):
                    self.dzAr[k] = self.dz
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
        else:
            if self.useSplitting:
                self.dzAr = np.zeros(self.finalKK, dtype=float)
                self.zLvl_bot = np.zeros(self.finalKK, dtype=float)
                self.zLvl_center = np.zeros(self.finalKK, dtype=float)
                for k in range(5):
                    self.dzAr[k] = self.dz / 5
                for k in range(5, self.finalKK):
                    self.dzAr[k] = self.dz
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
                # now overwrite with telescoped grid
                for k in range(1, self.finalKK):
                    if self.zLvl_bot[k] >= self.teleStart:
                        self.dzAr[k] = self.dzAr[k - 1] * (1 + self.teleStretch / 100)
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
            else:
                for k in range(self.finalKK):
                    self.dzAr[k] = self.dz
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
                # now overwrite with telescoped grid
                for k in range(1, self.finalKK):
                    if self.zLvl_bot[k] >= self.teleStart:
                        self.dzAr[k] = self.dzAr[k - 1] * (1 + self.teleStretch / 100)
                for k in range(self.finalKK):
                    self.zLvl_bot[k] = 0
                for k in range(1, self.finalKK):
                    self.zLvl_bot[k] = self.zLvl_bot[k - 1] + self.dzAr[k - 1]
        # calc zLvl center
        for k in range(self.finalKK):
            self.zLvl_center[k] = self.zLvl_bot[k] + 0.5 * self.dzAr[k]
        self.finished.emit()

    def run_save_inx(self):
        self.progress.emit(0)
        t1 = time.time()
        self.saveINX()
        t2 = time.time()
        print('Time to save the INX-file: ' + str(t2-t1))
        # report via pyqt-signal that run method of Worker-Class has been finished
        self.finished.emit()

    def stop(self):
        self.stopworker = True

    def load_simx(self, ui, filepath):
        simx = SIMX()
        simx.load_simx(file_path=filepath)

        # update UI
        # General settings
        start_date = simx.mainData.startDate
        ui.lb_selectedDateSim.setText(start_date)
        y = int(start_date.split('.')[2])
        m = int(start_date.split('.')[1])
        d = int(start_date.split('.')[0])
        ui.calendar_startDateSim.setSelectedDate(QDate(y, m, d))
        start_time = simx.mainData.startTime
        start_time = start_time.rsplit(':', 1)[0]
        h = int(start_time.split(':')[0])
        m = int(start_time.split(':')[1])
        ui.te_startTimeSim.setTime(QTime(h, m))
        ui.sb_simDur.setValue(int(simx.mainData.simDuration))
        ui.le_fullSimName.setText(simx.mainData.simName)
        ui.le_shortNameSim.setText(simx.mainData.filebaseName)
        ui.le_outputFolderSim.setText(simx.mainData.outDir)
        ui.le_inxForSim.setText(simx.mainData.INXfile)

        if simx.Parallel.CPUdemand == 'ALL':
            ui.rb_multiCore.setChecked(True)
        else:
            ui.rb_singleCore.setChecked(True)

        # meteo settings
        if simx.SiFoSelected:
            ui.rb_simpleForcing.setChecked(True)
            # find min/max values for hum. and temp.
            t_max = -999
            t_min = 999
            h_max = -999
            h_min = 999
            t_max_time = -1
            t_min_time = -1
            h_max_time = -1
            h_min_time = -1
            for i in range(len(simx.SimpleForcing.TAir)):
                if simx.SimpleForcing.TAir[i] < t_min:
                    t_min = simx.SimpleForcing.TAir[i]
                    t_min_time = i
                if simx.SimpleForcing.TAir[i] > t_max:
                    t_max = simx.SimpleForcing.TAir[i]
                    t_max_time = i
                if simx.SimpleForcing.Qrel[i] < h_min:
                    h_min = simx.SimpleForcing.Qrel[i]
                    h_min_time = i
                if simx.SimpleForcing.Qrel[i] > h_max:
                    h_max = simx.SimpleForcing.Qrel[i]
                    h_max_time = i
            t_min -= 273.14999
            t_max -= 273.14999
            ui.sb_timeMaxT.setValue(t_max_time)
            ui.sb_timeMinT.setValue(t_min_time)
            ui.sb_timeMaxHum.setValue(h_max_time)
            ui.sb_timeMinHum.setValue(h_min_time)
            ui.hs_maxT.setValue(round(t_max))
            ui.hs_minT.setValue(round(t_min))
            ui.hs_maxHum.setValue(round(h_max))
            ui.hs_minHum.setValue(round(h_min))
            # set other SiFo-Values
            ui.sb_specHum.setValue(simx.mainData.Q_H)
            ui.sb_windspeed.setValue(simx.mainData.windSpeed)
            ui.sb_winddir.setValue(simx.mainData.windDir)
            ui.sb_rlength.setValue(simx.mainData.z0)
            ui.sb_lowclouds.setValue(simx.Clouds.lowClouds)
            ui.sb_midclouds.setValue(simx.Clouds.middleClouds)
            ui.sb_highclouds.setValue(simx.Clouds.highClouds)

        elif simx.FuFoSelected:
            ui.rb_fullForcing.setChecked(True)
            ui.le_selectedFOX.setText(simx.FullForcing.fileName)
            if simx.FullForcing.forceWind == 1:
                ui.rb_forceWind_yes.setChecked(True)
            else:
                ui.rb_forceWind_no.setChecked(True)
                ui.sb_constWS_FUFo.setValue(simx.mainData.windSpeed)
                ui.sb_constWD_FuFo.setValue(simx.mainData.windDir)
                ui.sb_rlength_FuFo.setValue(simx.mainData.z0)

            if simx.FullForcing.forceT == 1:
                ui.rb_forceT_yes.setChecked(True)
            else:
                ui.rb_forceT_no.setChecked(True)
                ui.sb_initT.setValue(simx.mainData.T_H - 273.14999)

            if simx.FullForcing.forceRadClouds == 1:
                ui.rb_forceRadC_yes.setChecked(True)
            else:
                ui.rb_forceRadC_no.setChecked(True)
                ui.sb_lowclouds_2.setValue(simx.Clouds.lowClouds)
                ui.sb_mediumclouds.setValue(simx.Clouds.middleClouds)
                ui.sb_highclouds_2.setValue(simx.Clouds.highClouds)

            if simx.FullForcing.forceQ == 1:
                ui.rb_forceHum_yes.setChecked(True)
            else:
                ui.rb_forceHum_no.setChecked(True)
                ui.sb_relHum.setValue(simx.mainData.Q_2m)
                ui.sb_specHum_2.setValue(simx.mainData.Q_H)

            if simx.FullForcing.forcePrecip == 1:
                ui.rb_forcePrec_yes.setChecked(True)
            else:
                ui.rb_forcePrec_no.setChecked(True)
        else:
            # simx.otherSelected
            ui.rb_other.setChecked(True)
            ui.sb_otherAirT.setValue(simx.mainData.T_H - 273.14999)
            ui.sb_otherHum.setValue(simx.mainData.Q_2m)
            ui.sb_otherHum2500.setValue(simx.mainData.Q_H)
            ui.sb_otherWS.setValue(simx.mainData.windSpeed)
            ui.sb_otherWdir.setValue(simx.mainData.windDir)
            ui.sb_otherRlength.setValue(simx.mainData.z0)
            ui.sb_otherLowclouds.setValue(simx.Clouds.lowClouds)
            ui.sb_otherMediumclouds.setValue(simx.Clouds.middleClouds)
            ui.sb_otherHighclouds.setValue(simx.Clouds.highClouds)
            if simx.LBC.LBC_TQ == 1:
                ui.cb_otherBChumT.setCurrentIndex(0)
            else:
                # LVC_TQ == 3
                ui.cb_otherBChumT.setCurrentIndex(1)
            if simx.LBC.LBC_TKE == 1:
                ui.cb_otherBCturb.setCurrentIndex(0)
            else:
                # LBC_TKE == 3
                ui.cb_otherBCturb.setCurrentIndex(1)

        # optional sections
        if simx.SoilSelected:
            ui.chk_soilSim.setCheckState(Qt.Checked)
            ui.sb_soilHumUpper.setValue(simx.Soil.waterUpperlayer)
            ui.sb_soilHumMiddle.setValue(simx.Soil.waterMiddlelayer)
            ui.sb_soilHumLower.setValue(simx.Soil.waterDeeplayer)
            ui.sb_soilHumBedrock.setValue(simx.Soil.waterBedrocklayer)
            ui.sb_soilTupper.setValue(simx.Soil.tempUpperlayer - 273.14999)
            ui.sb_soilTmiddle.setValue(simx.Soil.tempMiddlelayer - 273.14999)
            ui.sb_soilTlower.setValue(simx.Soil.tempDeeplayer - 273.14999)
            ui.sb_soilTbedrock.setValue(simx.Soil.tempBedrocklayer - 273.14999)
        if simx.RadiationSelected:
            ui.chk_radiationSim.setCheckState(Qt.Checked)

            if (simx.RadScheme.RayTraceStepWidthHighRes >= 0.5) and (simx.RadScheme.RayTraceStepWidthLowRes >= 0.75):
                ui.rb_lowRes.setChecked(True)
            else:
                ui.rb_fineRes.setChecked(True)

            if simx.RadScheme.RadiationHeightBoundary < 0.0:
                ui.rb_noHeightCap.setChecked(True)
            else:
                ui.rb_yesHeightCap.setChecked(True)
                ui.sb_heightCap.setValue(round(simx.RadScheme.RadiationHeightBoundary))

            if simx.RadScheme.IVSHeightAngle_HiRes == -1:
                ui.rb_useIVSno.setChecked(True)
            else:
                ui.rb_useIVSyes.setChecked(True)
                if simx.RadScheme.IVSHeightAngle_HiRes == 45:
                    ui.cb_resHeightIVS.setCurrentIndex(0)
                elif simx.RadScheme.IVSHeightAngle_HiRes == 30:
                    ui.cb_resHeightIVS.setCurrentIndex(1)
                elif simx.RadScheme.IVSHeightAngle_HiRes == 15:
                    ui.cb_resHeightIVS.setCurrentIndex(2)
                elif simx.RadScheme.IVSHeightAngle_HiRes == 10:
                    ui.cb_resHeightIVS.setCurrentIndex(3)
                elif simx.RadScheme.IVSHeightAngle_HiRes == 5:
                    ui.cb_resHeightIVS.setCurrentIndex(4)
                elif simx.RadScheme.IVSHeightAngle_HiRes == 2:
                    ui.cb_resHeightIVS.setCurrentIndex(5)

                if simx.RadScheme.IVSAziAngle_HiRes == 45:
                    ui.cb_resAziIVS.setCurrentIndex(0)
                elif simx.RadScheme.IVSAziAngle_HiRes == 30:
                    ui.cb_resAziIVS.setCurrentIndex(1)
                elif simx.RadScheme.IVSAziAngle_HiRes == 15:
                    ui.cb_resAziIVS.setCurrentIndex(2)
                elif simx.RadScheme.IVSAziAngle_HiRes == 10:
                    ui.cb_resAziIVS.setCurrentIndex(3)
                elif simx.RadScheme.IVSAziAngle_HiRes == 5:
                    ui.cb_resAziIVS.setCurrentIndex(4)
                elif simx.RadScheme.IVSAziAngle_HiRes == 2:
                    ui.cb_resAziIVS.setCurrentIndex(5)

                if simx.RadScheme.MRTCalcMethod == 0:
                    ui.rb_MRT1.setChecked(True)
                else:
                    ui.rb_MRT2.setChecked(True)

                if simx.RadScheme.MRTProjFac == 3:
                    ui.cb_humanProjFac.setCurrentIndex(3)
                elif simx.RadScheme.MRTProjFac == 2:
                    ui.cb_humanProjFac.setCurrentIndex(2)
                elif simx.RadScheme.MRTProjFac == 1:
                    ui.cb_humanProjFac.setCurrentIndex(1)
                else:
                    ui.cb_humanProjFac.setCurrentIndex(0)

                if simx.RadScheme.AdvCanopyRadTransfer == 1:
                    ui.rbACRTyes.setChecked(True)
                else:
                    ui.rb_ACRTno.setChecked(True)

                ui.sb_ACRTdays.setValue(simx.RadScheme.ViewFacUpdateInterval)
                ui.sb_adjustFac.setValue(simx.SolarAdjust.SWFactor)

        if simx.BuildingSelected:
            ui.chk_buildingsSim.setCheckState(Qt.Checked)
            ui.sb_bldTmp.setValue(simx.Building.indoorTemp - 273.14999)
            ui.sb_bldSurfTmp.setValue(simx.Building.surfTemp - 273.14999)
            if simx.Building.indoorConst == 1:
                ui.rb_indoorYes.setChecked(True)
            else:
                ui.rb_indoorNo.setChecked(True)
        if simx.PollutantsSelected:
            ui.chk_pollutantsSim.setCheckState(Qt.Checked)
            ui.sb_NO.setValue(simx.Background.NO)
            ui.sb_NO2.setValue(simx.Background.NO2)
            ui.sb_ozone.setValue(simx.Background.O3)
            ui.sb_PM10.setValue(simx.Background.PM_10)
            ui.sb_PM25.setValue(simx.Background.PM_2_5)
            ui.sb_userPollu.setValue(simx.Background.userSpec)
            ui.le_userPolluName.setText(simx.Sources.userPolluName)
            ui.cb_userPolluType.setCurrentIndex(simx.Sources.userPolluType)
            ui.sb_praticleDia.setValue(simx.Sources.userPartDiameter)
            ui.sb_particleDens.setValue(simx.Sources.userPartDensity)

            if simx.Sources.multipleSources == 1:
                ui.rb_multiPollu.setChecked(True)
            else:
                ui.rb_singlePollu.setChecked(True)

            if simx.Sources.activeChem == 1:
                ui.rb_activeChem.setChecked(True)
            else:
                ui.rb_dispOnly.setCheked(True)
        if simx.OutputSelected:
            ui.chk_outputSim.setCheckState(Qt.Checked)

            if simx.OutputSettings.writeBuildings == 1:
                ui.cb_outputBldData.setCheckState(Qt.Checked)
            else:
                ui.cb_outputBldData.setCheckState(Qt.Unchecked)

            if simx.OutputSettings.writeRadiation == 1:
                ui.cb_outputRadData.setCheckState(Qt.Checked)
            else:
                ui.cb_outputRadData.setCheckState(Qt.Unchecked)

            if simx.OutputSettings.writeSoil == 1:
                ui.cb_outputSoilData.setCheckState(Qt.Checked)
            else:
                ui.cb_outputSoilData.setCheckState(Qt.Unchecked)

            if simx.OutputSettings.writeVegetation == 1:
                ui.cb_outputVegData.setCheckState(Qt.Checked)
            else:
                ui.cb_outputVegData.setCheckState(Qt.Unchecked)

            ui.sb_outputIntRecBld.setValue(simx.OutputSettings.textFiles)
            ui.sb_outputIntOther.setValue(simx.OutputSettings.mainFiles)

            if simx.OutputSettings.netCDF == 1:
                ui.rb_writeNetCDFyes.setChecked(True)
            else:
                ui.rb_writeNetCDFNo.setChecked(True)

            if simx.OutputSettings.netCDFAllDataInOneFile == 1:
                ui.rb_NetCDFsingleFile.setChecked(True)
            else:
                ui.rb_NetCDFmultiFile.setChecked(True)

            if simx.OutputSettings.netCDFWriteOnlySmallFile == 1:
                ui.eb_NetCDFsaveRelevant.setChecked(True)
            else:
                ui.rb_NetCDFsaveAll.setChecked(True)

            if simx.OutputSettings.inclNestingGrids == 1:
                ui.rb_inclNestingGridsYes.setChecked(True)
            else:
                ui.rb_InclNestingGridsNo.setChecked(True)
        if simx.TimingSelected:
            ui.chk_timingSim.setCheckState(Qt.Checked)

            ui.sb_timingPlant.setValue(simx.ModelTiming.plantSteps)
            ui.sb_timingSurf.setValue(simx.ModelTiming.surfaceSteps)
            ui.sb_timingRad.setValue(simx.ModelTiming.radiationSteps)
            ui.sb_timingFlow.setValue(simx.ModelTiming.flowSteps)
            ui.sb_timingEmission.setValue(simx.ModelTiming.sourceSteps)

            ui.sb_t0.setValue(simx.TimeSteps.dt_step00)
            ui.sb_t1.setValue(simx.TimeSteps.dt_step01)
            ui.sb_t2.setValue(simx.TimeSteps.dt_step02)
            ui.sb_t0t1angle.setValue(simx.TimeSteps.sunheight_step01)
            ui.sb_t1t2angle.setValue(simx.TimeSteps.sunheight_step02)
        if simx.ExpertSelected:
            ui.chk_expertSim.setCheckState(Qt.Checked)

            ui.cb_TKE.setCurrentIndex(simx.Turbulence.turbulenceModel)

            if (simx.Turbulence.TKELimit == 1):
                ui.rb_tkeLimitY.setChecked(True)
            else:
                ui.rb_tkeLimitN.setChecked(True)

            if (simx.TThread.UseTThread_CallMain == 0):
                ui.rb_threadingMain.setChecked(True)
            else:
                ui.rb_threadingOwn.setChecked(True)

            if simx.InflowAvg.inflowAvg == 0:
                ui.rb_avgInflowYes.setChecked(True)
            else:
                ui.rb_avgInflowNo.setChecked(True)

            if simx.Facades.FacadeMode == 1:
                ui.rb_DIN6946.setChecked(True)
            else:
                ui.rb_MO.setChecked(True)

            if simx.SOR.SORMode == 1:
                ui.rb_newSOR.setChecked(True)
            else:
                ui.rb_oldSOR.setChecked(True)
        if simx.PlantsSelected:
            ui.chk_plantsSim.setCheckState(Qt.Checked)

            ui.sb_co2.setValue(simx.PlantModel.CO2BackgroundPPM)
            if simx.PlantModel.LeafTransmittance == 1:
                ui.rb_leafTransUserDef.setChecked(True)
            else:
                ui.rb_leafTransOldCalc.setChecked(True)

            if simx.PlantModel.TreeCalendar == 1:
                ui.rb_TreeCalYes.setChecked(True)
            else:
                ui.rb_TreeCalNo.setChecked(True)
        self.finished.emit()

    def save_simx(self, ui):
        simx = SIMX()

        # write values from UI into the simx-object
        # write general-settings
        simx.mainData.simName = ui.le_fullSimName.text()
        simx.mainData.filebaseName = ui.le_shortNameSim.text()
        simx.mainData.outDir = ui.le_outputFolderSim.text()
        simx.mainData.INXfile = ui.le_inxForSim.text()
        simx.mainData.startDate = ui.lb_selectedDateSim.text()
        simx.mainData.simDuration = ui.sb_simDur.value()

        qtime = ui.te_startTimeSim.time()
        h = qtime.hour()
        m = qtime.minute()
        if h < 10:
            if m < 10:
                simx.mainData.startTime = f'0{h}:0{m}:00'
            else:
                simx.mainData.startTime = f'0{h}:{m}:00'
        else:
            if m < 10:
                simx.mainData.startTime = f'{h}:0{m}:00'
            else:
                simx.mainData.startTime = f'{h}:{m}:00'

        # write Parallel-settings
        if ui.rb_multiCore.isChecked():
            simx.Parallel.CPUdemand = 'ALL'
        else:
            simx.Parallel.CPUdemand = '1'
        # write meteo-settings
        if ui.rb_simpleForcing.isChecked():
            simx.SiFoSelected = True

            # Clouds
            simx.Clouds.lowClouds = ui.sb_lowclouds.value()
            simx.Clouds.middleClouds = ui.sb_midclouds.value()
            simx.Clouds.highClouds = ui.sb_highclouds.value()
            # Wind and Radiation
            simx.mainData.windSpeed = ui.sb_windspeed.value()
            simx.mainData.windDir = ui.sb_winddir.value()
            simx.mainData.z0 = ui.sb_rlength.value()
            simx.mainData.Q_H = ui.sb_specHum.value()

            # temperature and humidity values
            for i in range(24):
                simx.SimpleForcing.TAir[i] = float(ui.tableWidget.item(i, 0).text()) + 273.14999
                simx.SimpleForcing.Qrel[i] = float(ui.tableWidget.item(i, 1).text())

        elif ui.rb_fullForcing.isChecked():
            simx.FuFoSelected = True

            simx.FullForcing.fileName = ui.le_selectedFOX.text()
            if ui.rb_forceT_yes.isChecked():
                simx.FullForcing.forceT = 1
            else:
                simx.FullForcing.forceT = 0
                simx.mainData.T_H = ui.sb_initT.value() + 273.14999

            if ui.rb_forceWind_yes.isChecked():
                simx.FullForcing.forceWind = 1
            else:
                simx.FullForcing.forceWind = 0
                simx.mainData.windSpeed = ui.sb_constWS_FUFo.value()
                simx.mainData.windDir = ui.sb_constWD_FuFo.value()
                simx.mainData.z0 = ui.sb_rlength_FuFo.value()

            if ui.rb_forceRadC_yes.isChecked():
                simx.FullForcing.forceRadClouds = 1
            else:
                simx.FullForcing.forceRadClouds = 0
                simx.Clouds.lowClouds = ui.sb_lowclouds_2.value()
                simx.Clouds.middleClouds = ui.sb_mediumclouds.value()
                simx.Clouds.highClouds = ui.sb_highclouds_2.value()

            if ui.rb_forceHum_yes.isChecked():
                simx.FullForcing.forceQ = 1
            else:
                simx.FullForcing.forceQ = 0
                simx.mainData.Q_H = ui.sb_specHum_2.value()
                simx.mainData.Q_2m = ui.sb_relHum.value()

            if ui.rb_forcePrec_yes.isChecked():
                simx.FullForcing.forcePrecip = 1
            else:
                simx.FullForcing.forcePrecip = 0

        elif ui.rb_other.isChecked():
            simx.otherSelected = True

            if ui.cb_otherBChumT.currentIndex() == 0:
                simx.LBC.LBC_TQ = 1
            else:
                simx.LBC.LBC_TQ = 3

            if ui.cb_otherBCturb.currentIndex() == 0:
                simx.LBC.LBC_TKE = 1
            else:
                simx.LBC.LBC_TKE = 3

            simx.Clouds.lowClouds = ui.sb_otherLowclouds.value()
            simx.Clouds.middleClouds = ui.sb_otherMediumclouds.value()
            simx.Clouds.highClouds = ui.sb_otherHighclouds.value()
            simx.mainData.T_H = ui.sb_otherAirT.value() + 273.14999
            simx.mainData.Q_2m = ui.sb_otherHum.value()
            simx.mainData.Q_H = ui.sb_otherHum2500.value()
            simx.mainData.windSpeed = ui.sb_otherWS.value()
            simx.mainData.windDir = ui.sb_otherWdir.value()
            simx.mainData.z0 = ui.sb_otherRlength.value()

        # write section-bools
        if ui.chk_soilSim.isChecked():
            simx.SoilSelected = True
        if ui.chk_radiationSim.isChecked():
            simx.RadiationSelected = True
        if ui.chk_buildingsSim.isChecked():
            simx.BuildingSelected = True
        if ui.chk_pollutantsSim.isChecked():
            simx.PollutantsSelected = True
        if ui.chk_outputSim.isChecked():
            simx.OutputSelected = True
        if ui.chk_timingSim.isChecked():
            simx.TimingSelected = True
        if ui.chk_expertSim.isChecked():
            simx.ExpertSelected = True
        if ui.chk_plantsSim.isChecked():
            simx.PlantsSelected = True

        # write optional sections
        if simx.SoilSelected:
            simx.Soil.waterUpperlayer = ui.sb_soilHumUpper.value()
            simx.Soil.waterMiddlelayer = ui.sb_soilHumMiddle.value()
            simx.Soil.waterDeeplayer = ui.sb_soilHumLower.value()
            simx.Soil.waterBedrocklayer = ui.sb_soilHumBedrock.value()
            simx.Soil.tempUpperlayer = ui.sb_soilTupper.value() + 273.14999
            simx.Soil.tempMiddlelayer = ui.sb_soilTmiddle.value() + 273.14999
            simx.Soil.tempDeeplayer = ui.sb_soilTlower.value() + 273.14999
            simx.Soil.tempBedrocklayer = ui.sb_soilTbedrock.value() + 273.14999
        if simx.RadiationSelected:
            simx.SolarAdjust.SWFactor = ui.sb_adjustFac.value()

            if ui.rb_fineRes.isChecked():
                simx.RadScheme.RayTraceStepWidthHighRes = 0.25
                simx.RadScheme.RayTraceStepWidthLowRes = 0.50
            else:
                simx.RadScheme.RayTraceStepWidthHighRes = 0.50
                simx.RadScheme.RayTraceStepWidthLowRes = 0.75

            if ui.rb_yesHeightCap.isChecked():
                simx.RadScheme.RadiationHeightBoundary = ui.sb_heightCap.value()
            else:
                simx.RadScheme.RadiationHeightBoundary = -1

            if ui.rbACRTyes.isChecked():
                simx.RadScheme.AdvCanopyRadTransfer = 1
            else:
                simx.RadScheme.AdvCanopyRadTransfer = 0
            simx.RadScheme.ViewFacUpdateInterval = ui.sb_ACRTdays.value()

            # IVS
            if ui.rb_useIVSyes.isChecked():
                if ui.cb_resHeightIVS.currentIndex() == 0:
                    simx.RadScheme.IVSHeightAngle_HiRes = 45
                    simx.RadScheme.IVSHeightAngle_LoRes = 45
                elif ui.cb_resHeightIVS.currentIndex() == 1:
                    simx.RadScheme.IVSHeightAngle_HiRes = 30
                    simx.RadScheme.IVSHeightAngle_LoRes = 30
                elif ui.cb_resHeightIVS.currentIndex() == 2:
                    simx.RadScheme.IVSHeightAngle_HiRes = 15
                    simx.RadScheme.IVSHeightAngle_LoRes = 15
                elif ui.cb_resHeightIVS.currentIndex() == 3:
                    simx.RadScheme.IVSHeightAngle_HiRes = 10
                    simx.RadScheme.IVSHeightAngle_LoRes = 10
                elif ui.cb_resHeightIVS.currentIndex() == 4:
                    simx.RadScheme.IVSHeightAngle_HiRes = 5
                    simx.RadScheme.IVSHeightAngle_LoRes = 5
                elif ui.cb_resHeightIVS.currentIndex() == 5:
                    simx.RadScheme.IVSHeightAngle_HiRes = 2
                    simx.RadScheme.IVSHeightAngle_LoRes = 2

                if ui.cb_resAziIVS.currentIndex() == 0:
                    simx.RadScheme.IVSAziAngle_HiRes = 45
                    simx.RadScheme.IVSAziAngle_LoRes = 45
                elif ui.cb_resAziIVS.currentIndex() == 1:
                    simx.RadScheme.IVSAziAngle_HiRes = 30
                    simx.RadScheme.IVSAziAngle_LoRes = 30
                elif ui.cb_resAziIVS.currentIndex() == 2:
                    simx.RadScheme.IVSAziAngle_HiRes = 15
                    simx.RadScheme.IVSAziAngle_LoRes = 15
                elif ui.cb_resAziIVS.currentIndex() == 3:
                    simx.RadScheme.IVSAziAngle_HiRes = 10
                    simx.RadScheme.IVSAziAngle_LoRes = 10
                elif ui.cb_resAziIVS.currentIndex() == 4:
                    simx.RadScheme.IVSAziAngle_HiRes = 5
                    simx.RadScheme.IVSAziAngle_LoRes = 5
                elif ui.cb_resAziIVS.currentIndex() == 5:
                    simx.RadScheme.IVSAziAngle_HiRes = 2
                    simx.RadScheme.IVSAziAngle_LoRes = 2
            else:
                simx.RadScheme.IVSHeightAngle_HiRes = -1
                simx.RadScheme.IVSHeightAngle_LoRes = -1
                simx.RadScheme.IVSAziAngle_HiRes = -1
                simx.RadScheme.IVSAziAngle_LoRes = -1

            # MRT
            if ui.rb_MRT1.isChecked():
                simx.RadScheme.MRTCalcMethod = 0
            else:
                simx.RadScheme.MRTCalcMethod = 1
            simx.RadScheme.MRTProjFac = ui.cb_humanProjFac.currentIndex()

        if simx.BuildingSelected:
            simx.Building.indoorTemp = ui.sb_bldTmp.value() + 273.14999
            simx.Building.surfTemp = ui.sb_bldSurfTmp.value() + 273.14999
            if ui.rb_indoorYes.isChecked():
                simx.Building.indoorConst = 1
            else:
                simx.Building.indoorConst = 0
        if simx.PollutantsSelected:
            if ui.rb_multiPollu.isChecked():
                simx.Sources.multipleSources = 1
            else:
                simx.Sources.multipleSources = 0

            if ui.rb_activeChem.isChecked():
                simx.Sources.activeChem = 1
            else:
                simx.Sources.activeChem = 0

            simx.Sources.userPolluName = ui.le_userPolluName.text().strip()
            simx.Sources.userPolluType = ui.cb_userPolluType.currentIndex()
            simx.Sources.userPartDiameter = ui.sb_praticleDia.value()
            simx.Sources.userPartDensity = ui.sb_particleDens.value()

            simx.Background.NO = ui.sb_NO.value()
            simx.Background.NO2 = ui.sb_NO2.value()
            simx.Background.O3 = ui.sb_ozone.value()
            simx.Background.PM_10 = ui.sb_PM10.value()
            simx.Background.PM_2_5 = ui.sb_PM25.value()
            simx.Background.userSpec = ui.sb_userPollu.value()
        if simx.OutputSelected:
            if ui.rb_inclNestingGridsYes.isChecked():
                simx.OutputSettings.inclNestingGrids = 1
            else:
                simx.OutputSettings.inclNestingGrids = 0

            if ui.rb_writeNetCDFyes.isChecked():
                simx.OutputSettings.netCDF = 1
            else:
                simx.OutputSettings.netCDF = 0

            if ui.rb_NetCDFsingleFile.isChecked():
                simx.OutputSettings.netCDFAllDataInOneFile = 1
            else:
                simx.OutputSettings.netCDFAllDataInOneFile = 0

            if ui.rb_NetCDFsaveAll.isChecked():
                simx.OutputSettings.netCDFWriteOnlySmallFile = 0
            else:
                simx.OutputSettings.netCDFWriteOnlySmallFile = 1

            simx.OutputSettings.textFiles = ui.sb_outputIntRecBld.value()
            simx.OutputSettings.mainFiles = ui.sb_outputIntOther.value()

            if ui.cb_outputBldData.isChecked():
                simx.OutputSettings.writeBuildings = 1
            else:
                simx.OutputSettings.writeBuildings = 0

            if ui.cb_outputRadData.isChecked():
                simx.OutputSettings.writeRadiation = 1
            else:
                simx.OutputSettings.writeRadiation = 0

            if ui.cb_outputSoilData.isChecked():
                simx.OutputSettings.writeSoil = 1
            else:
                simx.OutputSettings.writeSoil = 0

            if ui.cb_outputVegData.isChecked():
                simx.OutputSettings.writeVegetation = 1
            else:
                simx.OutputSettings.writeVegetation = 0
        if simx.TimingSelected:
            simx.ModelTiming.plantSteps = ui.sb_timingPlant.value()
            simx.ModelTiming.surfaceSteps = ui.sb_timingSurf.value()
            simx.ModelTiming.radiationSteps = ui.sb_timingRad.value()
            simx.ModelTiming.flowSteps = ui.sb_timingFlow.value()
            simx.ModelTiming.sourceSteps = ui.sb_timingEmission.value()

            simx.TimeSteps.dt_step00 = ui.sb_t0.value()
            simx.TimeSteps.dt_step01 = ui.sb_t1.value()
            simx.TimeSteps.dt_step02 = ui.sb_t2.value()
            simx.TimeSteps.sunheight_step01 = ui.sb_t0t1angle.value()
            simx.TimeSteps.sunheight_step02 = ui.sb_t1t2angle.value()
        if simx.ExpertSelected:
            simx.Turbulence.turbulenceModel = ui.cb_TKE.currentIndex()

            if ui.rb_tkeLimitY.isChecked():
                simx.Turbulence.TKELimit = 1
            else:
                simx.Turbulence.TKELimit = 0

            if ui.rb_avgInflowYes.isChecked():
                simx.InflowAvg.inflowAvg = 0
            else:
                simx.InflowAvg.inflowAvg = 1

            if ui.rb_MO.isChecked():
                simx.Facades.FacadeMode = 0
            else:
                simx.Facades.FacadeMode = 1

            if ui.rb_oldSOR.isChecked():
                simx.SOR.SORMode = 0
            else:
                simx.SOR.SORMode = 1

            if ui.rb_threadingMain.isChecked():
                simx.TThread.UseTThread_CallMain = 0
            else:
                simx.TThread.UseTThread_CallMain = 1
        if simx.PlantsSelected:
            simx.PlantModel.CO2BackgroundPPM = ui.sb_co2.value()
            if ui.rb_leafTransOldCalc.isChecked():
                simx.PlantModel.LeafTransmittance = 0
            else:
                simx.PlantModel.LeafTransmittance = 1

            if ui.rb_TreeCalYes.isChecked():
                simx.PlantModel.TreeCalendar = 1
            else:
                simx.PlantModel.TreeCalendar = 0
        # now save the simx-file
        simx.save_simx(ui.le_simxDest.text())

        self.finished.emit()

    def load_simulation_data(self, edt_filenames, var_name: str, z: int):
        self.progress.emit(0)
        self.edt_data.clear()
        count = 0
        for edt_file in edt_filenames:
            edx_file = f'{edt_file.rsplit(".", 1)[0]}.edx'
            edx = EDX(filepath=edx_file)
            edt = EDT(filepath=edt_file, edx=edx, var_name=var_name, z=z)
            self.edt_data.append(edt)
            count += 1
            self.progress.emit(floor((count/len(edt_filenames))*100))
        self.finished.emit()

    def add_layers_to_map(self, edt_list,
                          var_name: str = 'result',
                          only_load_data: bool = False,
                          load_and_rotate_data: bool = True,
                          interpolate_data: bool = False,
                          interpol_res: float = 1,
                          sampling_method: int = 1):
        self.progress.emit(0)
        count = 0
        for edt in edt_list:
            edx = edt.associated_edx
            for n in range(edx.data_per_variable):
                #if edx.data_type_dict[edx.data_type] == 'ft2DRaster':
                #    data = edt.data_dict[var]
                #    data = data[:, :, n]
                #    data = data.reshape((data.shape[0], data.shape[1]))
                #elif (edx.data_type_dict[edx.data_type] == 'ft3DRaster') or \
                #        (edx.data_type_dict[edx.data_type] == 'ft3DFacade'):
                #    data = edt.data_dict[var]
                #    data = data[:, :, zlevel, n]
                #    data = data.reshape((data.shape[0], data.shape[1]))
                data = edt.specified_data
                data = data.reshape((data.shape[0], data.shape[1]))
                cols, rows = data.shape

                if only_load_data:
                    extent = QgsRectangle()
                    extent.setXMinimum(edx.location_georef_x)
                    extent.setYMinimum(edx.location_georef_y)
                    extent.setXMaximum(edx.location_georef_x + cols * edx.spacing_x[0])
                    extent.setYMaximum(edx.location_georef_y + rows * edx.spacing_y[0])
                    if edx.location_georef_lat >= 0:
                        crs = pyproj.CRS.from_string(f'+proj=utm +zone={edx.location_georef_xy_utmzone} +north')
                    else:
                        crs = pyproj.CRS.from_string(f'+proj=utm +zone={edx.location_georef_xy_utmzone} +south')
                    qgs_crs = QgsCoordinateReferenceSystem(f'EPSG:{crs.to_authority()[1]}')
                    context = dataobjects.createContext()
                    context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
                    r = processing.run('qgis:createconstantrasterlayer',
                                       {
                                           'EXTENT': extent,
                                           'TARGET_CRS': qgs_crs,
                                           'PIXEL_SIZE': min(edx.spacing_x[0], edx.spacing_y[0]),
                                           'NUMBER': -999.0,
                                           'OUTPUT_TYPE': 5,
                                           'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                       }, context=context
                                       )['OUTPUT']
                    rlayer = QgsRasterLayer(r, 'temp', 'gdal')
                    #print(rlayer)
                    provider = rlayer.dataProvider()
                    provider.setNoDataValue(1,-999.0)

                    # dataType = Qgis.DataType.Byte
                    dataType = provider.dataType(1)
                    block = QgsRasterBlock(dataType, cols, rows)

                    for i in range(cols):
                        for j in range(rows):
                            idx_j = rows - j - 1
                            block.setValue(j, i, data[i][idx_j])
                            #print(data[i][idx_j])

                    provider.setEditable(True)
                    provider.writeBlock(block, band=1)
                    provider.setEditable(False)
                    provider.reload()
                    #QgsProject.instance().addMapLayer(rlayer)

                    masked_data = np.ma.masked_equal(data, -999.0)

                    GrayRenderer = QgsSingleBandGrayRenderer(provider, 1)
                    contrastEnhancement = QgsContrastEnhancement.StretchToMinimumMaximum
                    myEnhancement = QgsContrastEnhancement()
                    myEnhancement.setContrastEnhancementAlgorithm(contrastEnhancement, True)
                    myEnhancement.setMinimumValue(np.min(masked_data))
                    myEnhancement.setMaximumValue(np.max(masked_data))
                    rlayer.setRenderer(GrayRenderer)
                    rlayer.renderer().setContrastEnhancement(myEnhancement)

                    targetRes = min(edx.spacing_x[0], edx.spacing_y[0])
                    sampling = 0
                    context = dataobjects.createContext()
                    context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
                    rlayer_resample = processing.run("gdal:warpreproject",
                                                     {'INPUT': rlayer,
                                                      'SOURCE_CRS': qgs_crs,
                                                      'TARGET_CRS': qgs_crs,
                                                      'RESAMPLING': sampling,
                                                      'NODATA': rlayer,
                                                      'TARGET_RESOLUTION': targetRes, # here, we could set 1 meter or if resolution is even better that use dx/dy
                                                      'OPTIONS': '',
                                                      'DATA_TYPE': 6,
                                                      'TARGET_EXTENT': None,
                                                      'TARGET_EXTENT_CRS': None,
                                                      'MULTITHREADING': True,
                                                      'EXTRA': '',
                                                      'OUTPUT': 'TEMPORARY_OUTPUT'},
                                                     context=context)
                    rlayerFN_resample = rlayer_resample['OUTPUT']

                    tmp = QgsRasterLayer(rlayerFN_resample, f'{var_name}_{edx.simulation_date.strip()}_{edx.simulation_time.strip()}_{n}', 'gdal')
                    tmp.setCrs(qgs_crs)
                    QgsProject.instance().addMapLayer(tmp)
                else:
                    if load_and_rotate_data:
                        targetRes = min(edx.spacing_x[0], edx.spacing_y[0])
                        sampling = 0
                        if interpolate_data:                    
                            targetRes = min(targetRes, interpol_res)
                            sampling = sampling_method        # 1 (Bilinear (2x2 kernel)) and 3 (Cubic B-Spline (4x4 kernel)) work well

                        # prepare data to be loaded into a raster
                        extent = QgsRectangle()
                        extent.setXMinimum(edx.location_georef_x)
                        extent.setYMinimum(edx.location_georef_y)
                        extent.setXMaximum(edx.location_georef_x + cols * edx.spacing_x[0])
                        extent.setYMaximum(edx.location_georef_y + rows * edx.spacing_y[0])
                        if edx.location_georef_lat >= 0:
                            crs = pyproj.CRS.from_string(f'+proj=utm +zone={edx.location_georef_xy_utmzone} +north')
                        else:
                            crs = pyproj.CRS.from_string(f'+proj=utm +zone={edx.location_georef_xy_utmzone} +south')
                        qgs_crs = QgsCoordinateReferenceSystem(f'EPSG:{crs.to_authority()[1]}')
                        #print(qgs_crs)
                        context = dataobjects.createContext()
                        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid                        
                        r = processing.run('qgis:createconstantrasterlayer',
                                        {
                                            'EXTENT': extent,
                                            'TARGET_CRS': qgs_crs,
                                            'PIXEL_SIZE': min(edx.spacing_x[0], edx.spacing_y[0]),
                                            'NUMBER': -999.0,
                                            'OUTPUT_TYPE': 5,
                                            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
                                        },context=context
                                        )['OUTPUT']
                        rlayer = QgsRasterLayer(r, 'temp', 'gdal')
                        #print(rlayer)

                        provider = rlayer.dataProvider()
                        provider.setNoDataValue(1,-999.0)
                        # dataType = Qgis.DataType.Byte
                        dataType = provider.dataType(1)
                        block = QgsRasterBlock(dataType, cols, rows)
                        
                        # set data from array to raster block
                        for i in range(cols):
                            for j in range(rows):
                                idx_j = rows - j - 1
                                block.setValue(j, i, data[i][idx_j])
                                #print(data[i][idx_j])
                        provider.setEditable(True)
                        provider.writeBlock(block, band=1)
                        provider.setEditable(False)
                        provider.reload()
                        #QgsProject.instance().addMapLayer(rlayer)

                        # vectorize raster
                        context = dataobjects.createContext()
                        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
                        rlayer_vec = processing.run("native:pixelstopolygons",
                                                    {"INPUT_RASTER": rlayer,
                                                    "RASTER_BAND": 1,
                                                    "FIELD_NAME": "dataVal",
                                                    "CRS": qgs_crs, 
                                                    "OUTPUT": 'TEMPORARY_OUTPUT'},
                                                    context=context)
                        rlayerFN_vec = rlayer_vec['OUTPUT']
                        #print(rlayerFN_vec)
                        #QgsProject.instance().addMapLayer(rlayerFN_vec)

                        # set the QGIS project to the CRS of the data, so that the rotation can be made
                        QgsProject.instance().setCrs(qgs_crs)
                        # find rotation center
                        if edx.location_georef_lat >= 0:
                            xMin_s = edx.location_georef_x #self.model_rot_center.x()
                            yMin_s = edx.location_georef_y #self.model_rot_center.y()
                            epsg_s = crs.to_authority()[1]
                            anch = str(xMin_s) + "," + str(yMin_s) + " [" + epsg_s + "]"
                            #print(anch)
                        else:
                            xMin_s = edx.location_georef_x #self.model_rot_center.x()
                            yMin_s = edx.location_georef_y + rows * edx.spacing_y[0] #self.model_rot_center.y()
                            epsg_s = crs.to_authority()[1]
                            anch = str(xMin_s) + "," + str(yMin_s) + " [" + epsg_s + "]"
                            #print(anch)
                        # rotate vector file
                        context = dataobjects.createContext()
                        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
                        r = processing.run("native:rotatefeatures",
                                                {"INPUT": rlayerFN_vec,
                                                "ANGLE": edx.model_rotation,
                                                "ANCHOR": anch,
                                                "CRS": qgs_crs,
                                                "OUTPUT": 'TEMPORARY_OUTPUT'},
                                                context=context)
                        rlayer = r['OUTPUT']
                        #QgsProject.instance().addMapLayer(rlayer)

                        # raster data the rotated vector data
                        r = processing.run("gdal:rasterize",
                                                {"INPUT": rlayer,
                                                "FIELD": 'dataVal',
                                                "UNITS": 1,
                                                "WIDTH": edx.spacing_x[0],
                                                "HEIGHT": edx.spacing_y[0],
                                                "EXTENT": rlayer.extent(),
                                                "NODATA": -999,
                                                "DATA_TYPE": 5,
                                                "OUTPUT_TYPE": 5,
                                                "INIT": -999,
                                                "INVERT": False,
                                                "OUTPUT": 'TEMPORARY_OUTPUT'},
                                                context=context)
                        rlayerRot = QgsRasterLayer(r['OUTPUT'], 'tmpVec2Ras', 'gdal')     
                        #QgsProject.instance().addMapLayer(rlayerRot)
                        #print(rlayerFN)          

                        provider = rlayerRot.dataProvider()
                        provider.setNoDataValue(1,-999)             
                        dataType = provider.dataType(1)    
                        #print(dataType) 
                        provider.reload()                      

                        #data = np.fliplr(data)
                        masked_data = np.ma.masked_equal(data, -999.0)
                        #print(masked_data.dtype)

                        GrayRenderer = QgsSingleBandGrayRenderer(provider, 1)
                        contrastEnhancement = QgsContrastEnhancement.StretchToMinimumMaximum
                        myEnhancement = QgsContrastEnhancement()
                        myEnhancement.setContrastEnhancementAlgorithm(contrastEnhancement, True)
                        myEnhancement.setMinimumValue(np.min(masked_data))
                        myEnhancement.setMaximumValue(np.max(masked_data))
                        rlayerRot.setRenderer(GrayRenderer)
                        rlayerRot.renderer().setContrastEnhancement(myEnhancement)

                        context = dataobjects.createContext()
                        context.setInvalidGeometryCheck(QgsFeatureRequest.GeometryNoCheck)          #QgsFeatureRequest.GeometrySkipInvalid
                        # resample data
                        rlayer_resample = processing.run("gdal:warpreproject",
                                                        {'INPUT': rlayerRot,
                                                        'SOURCE_CRS': qgs_crs,
                                                        'TARGET_CRS': qgs_crs,
                                                        'RESAMPLING': sampling,
                                                        'NODATA': rlayerRot,
                                                        'TARGET_RESOLUTION':targetRes, # here, we could set 1 meter or if resolution is even better that use dx/dy
                                                        'OPTIONS': '',
                                                        'DATA_TYPE': 6,
                                                        'TARGET_EXTENT': None,
                                                        'TARGET_EXTENT_CRS': None,
                                                        'MULTITHREADING': True,
                                                        'EXTRA': '',
                                                        'OUTPUT': 'TEMPORARY_OUTPUT'},
                                                        context=context)
                        rlayerFN_resample = rlayer_resample['OUTPUT']

                        tmp = QgsRasterLayer(rlayerFN_resample, f'tmp_{count}', 'gdal')
                        tmp.setCrs(qgs_crs)                    

                        # add to map
                        tmp = QgsRasterLayer(rlayerFN_resample, f'{var_name}_{edx.simulation_date.strip()}_{edx.simulation_time.strip()}_{n}', 'gdal')
                        tmp.setCrs(qgs_crs)
                        QgsProject.instance().addMapLayer(tmp)



            count += 1
            self.progress.emit(floor((count / len(edt_list)) * 100))
        self.finished.emit()
