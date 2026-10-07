import math
import time
from math import degrees

import numpy as np
import pyproj
from pyproj.database import query_utm_crs_info
from osgeo import gdal, osr

from qgis.PyQt.QtCore import Qt, QObject, QDate, QTime, pyqtSignal
from qgis.core import (Qgis, QgsField, QgsPoint, QgsPointXY, QgsVectorLayer, QgsRectangle,
                       QgsFeatureRequest, QgsMessageLog, QgsRasterLayer, QgsGeometry, QgsFeature,
                       QgsCoordinateTransform, QgsCoordinateTransformContext, QgsReferencedRectangle)
# QgsGeometryUtils.angleBetweenThreePoints() is deprecated from QGIS 3.40 on;
# the identical method lives on QgsGeometryUtilsBase (added in QGIS 3.34).
try:
    from qgis.core import QgsGeometryUtilsBase
except ImportError:
    from qgis.core import QgsGeometryUtils as QgsGeometryUtilsBase
import processing
from processing.tools import dataobjects

from .Const_defines import C_NODATA_VALUE, FIELD_TYPE_INT, FIELD_TYPE_STRING
from .worker_helpers import get_UTM_zone
from .core.grid import raster_to_envimet_ij, raster_to_inx_receptor_cell
from .core.inx_arrays import border_mask, first_non_empty, map_codes, map_values, matrix_text
from .core import location


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


class Worker(QObject):
    finished = pyqtSignal()  # create a pyqtSignal for when task is finished
    progress = pyqtSignal(int)  # create a pyqtSignal to report the progress to progressbar

    def __init__(self):
        super(Worker, self).__init__()
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
        self.bTop = QgsField("notAvail", FIELD_TYPE_INT)
        self.bBot = QgsField("notAvail", FIELD_TYPE_INT)
        self.bName = QgsField("notAvail", FIELD_TYPE_STRING)
        self.bWall = QgsField("notAvail", FIELD_TYPE_STRING)
        self.bRoof = QgsField("notAvail", FIELD_TYPE_STRING)
        self.bGreenWall = QgsField("notAvail", FIELD_TYPE_STRING)
        self.bGreenRoof = QgsField("notAvail", FIELD_TYPE_STRING)
        self.bBPS = QgsField("notAvail", FIELD_TYPE_STRING)
        # custom fields
        self.bTop_custom = C_NODATA_VALUE
        self.bBot_custom = C_NODATA_VALUE
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
        self.surfID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.surfID_custom = "notAvail"
        self.surfID_UseCustom = False

        self.surfLayer_raster = QgsRasterLayer("", "notAvail")
        self.surfLayer_raster_rot = QgsRasterLayer("", "notAvail")
        self.surfLayer_raster_band = -1
        self.surfLayer_raster_def = {}

        self.plant1dLayerFromVector = True

        self.plant1dLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.plant1dLayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.plant1dID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.plant1dID_custom = "notAvail"
        self.plant1dID_UseCustom = False

        self.plant1dLayer_raster = QgsRasterLayer("", "notAvail")
        self.plant1dLayer_raster_rot = QgsRasterLayer("", "notAvail")
        self.plant1dLayer_raster_band = -1
        self.plant1dLayer_raster_def = {}

        self.plant3dLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.plant3dLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.plant3dID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.plant3dAddOut = QgsField("notAvail", FIELD_TYPE_STRING)
        self.plant3dAddOut_disabled = False
        self.plant3dID_custom = "notAvail"
        self.plant3dID_UseCustom = False

        self.recLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.recLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.recID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.recID_custom = "notAvail"
        self.recID_UseCustom = False

        self.srcPLayer = QgsVectorLayer("Point", "notAvail", "memory")
        self.srcPLayer_rot = QgsVectorLayer("Point", "notAvail", "memory")
        self.srcPID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.srcPID_custom = "notAvail"
        self.srcPID_UseCustom = False

        self.srcLLayer = QgsVectorLayer("Line", "notAvail", "memory")
        self.srcLLayer_rot = QgsVectorLayer("Line", "notAvail", "memory")
        self.srcLID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.srcLID_custom = "notAvail"
        self.srcLID_UseCustom = False

        self.srcALayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.srcALayer_rot = QgsVectorLayer("Polygon", "notAvail", "memory")
        self.srcAID = QgsField("notAvail", FIELD_TYPE_STRING)
        self.srcAID_custom = "notAvail"
        self.srcAID_UseCustom = False

        self.dEMLayer = QgsRasterLayer("", "notAvail")
        self.dEMBand = -1
        self.dEMInterpol = 1

        self.lon = 0.0
        self.lat = 0.0
        self.target_epsg = None     # UTM CRS of the sub-area; every input is projected into it
        self.warnings = []          # shown to the user when the export has finished
        self.UTMZone = -1
        self.UTMHemisphere = 'N'
        self.timeZoneName = ""
        self.timeZoneLonRef = 0.0
        self.elevation = C_NODATA_VALUE
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

    # ==================================================================
    # Geometry, rotation and processing helpers
    # ==================================================================
    def rotate_layer(self, lay: QgsVectorLayer, is_sub_area_layer: bool):
        if (lay is None) or (lay.name() == "notAvail"):
            return ""
        xMin_s = self.model_rot_center.x()
        yMin_s = self.model_rot_center.y()
        epsg_s = lay.sourceCrs().authid()
        anch = str(xMin_s) + "," + str(yMin_s) + " [" + epsg_s + "]"

        context = self.get_safe_processing_context()
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

    def _extract_and_rotate(self, layer):
        """Clip ``layer`` to the (non-rotated) sub-area, then rotate the result
        back into alignment with the sub-area grid. Returns the rotated layer."""
        context = self.get_safe_processing_context()
        extracted = processing.run("qgis:extractbylocation",
                                   {"INPUT": layer,
                                    "PREDICATE": [0],
                                    "INTERSECT": self.subAreaLayer_nonRot,
                                    "OUTPUT": 'TEMPORARY_OUTPUT'},
                                   context=context)
        return self.rotate_layer(extracted["OUTPUT"], False)

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
        # print(numVert)
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
                R0_R2_ang = degrees(QgsGeometryUtilsBase.angleBetweenThreePoints(R0.x(), R0.y(), R1.x(), R1.y(), R2.x(), R2.y()))
                R1_R3_ang = degrees(QgsGeometryUtilsBase.angleBetweenThreePoints(R1.x(), R1.y(), R2.x(), R2.y(), R3.x(), R3.y()))
                R2_R0_ang = degrees(QgsGeometryUtilsBase.angleBetweenThreePoints(R2.x(), R2.y(), R3.x(), R3.y(), R0.x(), R0.y()))
                R3_R1_ang = degrees(QgsGeometryUtilsBase.angleBetweenThreePoints(R3.x(), R3.y(), R4.x(), R4.y(), R1.x(), R1.y()))

                # print(R0_R2_ang)
                # print(R1_R3_ang)
                # print(R2_R0_ang)
                # print(R3_R1_ang)

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

                # print(R0_R2_ang)
                # print(R1_R3_ang)
                # print(R2_R0_ang)
                # print(R3_R1_ang)

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
                # print("azi_corr:" + str(model_rot_corr))

                self.model_rot = model_rot_corr
                self.rotate_layer(self.subAreaLayer, True)
                return model_rot_corr
            else:
                # write a msg to the user
                self.msg = 'Error:Please provide a layer featuring a single rectangular polygon (4 vertices). The use of the "Shape Digitizing Toolbar" is recommended.'

    # ==================================================================
    # Location, elevation and CRS lookups (online)
    # ==================================================================
    def get_time_zone_geonames(self):
        """Hours east of UTC of the location's standard time (ENVI-met uses local standard time)."""
        QgsMessageLog.logMessage("Getting Timezone...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        offset, problem = location.standard_time_offset(self.lat, self.lon)
        if problem:
            self.warnings.append(f"Time zone: {problem}; estimated from the longitude as UTC{offset:+g}. "
                                 f"Check the time zone in the model area's location settings.")
        return str(offset)

    def get_elevation_geonames(self):
        QgsMessageLog.logMessage("Getting Elevation...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        elevation = location.elevation(self.lat, self.lon)
        if elevation is None:
            self.warnings.append("Elevation: GeoNames gave none; the terrain reference height is used instead.")
            return self.refHeightDEM
        return elevation

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

    # ==================================================================
    # Gridding: buildings
    # ==================================================================
    def buildBInfo(self):
        self.s_buildingDict.clear()
        if (self.bLayer.name() == "notAvail") or ((not self.bTop_UseCustom) and (self.bTop == "")) or (self.bLayer.getFeatures() is None):
            return self.s_buildingDict

        QgsMessageLog.logMessage("Started: Generating Building Info section...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.bLayer = self.reprojectLayerToUTM(self.bLayer, False)

        # rotate the building layer, so it is aligned with the subarea-layer again
        self.bLayer_rot = self._extract_and_rotate(self.bLayer)

        # start editing
        self.bLayer_rot.startEditing()
        bNumber_int = 'bNum_int'
        self.bLayer_rot.addAttribute(QgsField(bNumber_int, FIELD_TYPE_INT))
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
        # QgsProject.instance().addMapLayer(self.bLayer_rot)

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
                # print(self.s_buildingDict[s_bNumber].BuildingInternalNumber)
                # print('as')

        QgsMessageLog.logMessage("Finished: Generating Building Info section.", 'ENVI-met', level=Qgis.MessageLevel.Info)

    def rasterBNumber(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr

        QgsMessageLog.logMessage("Started: Gridding Building Numbers...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field='bNum_int')
        QgsMessageLog.logMessage("Finished: Gridding Building Numbers", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_int_array

    def rasterBTop(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr

        QgsMessageLog.logMessage("Started: Gridding Building Tops...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        if self.bTop_UseCustom:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bTop_custom, burn_val=True)
        else:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bTop)

        QgsMessageLog.logMessage("Finished: Gridding Building Tops.", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_int_array

    def rasterBBot(self):
        if self.bLayer_rot.name() == "notAvail":
            tmpAr = np.zeros(shape=(self.JJ, self.II), dtype=int)
            return tmpAr
        QgsMessageLog.logMessage("Started: Gridding Building Bottoms...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        if self.bBot_UseCustom:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bBot_custom, burn_val=True)
        else:
            grid1_int_array = self.rasterize_gdal(input_layer=self.bLayer_rot, field=self.bBot)

        QgsMessageLog.logMessage("Finished: Gridding Building Bottoms.", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_int_array

    # ==================================================================
    # Gridding: surfaces and raster processing
    # ==================================================================
    def raster_surface_from_vector(self):
        if self.surfLayer.name() == "notAvail":
            return np.full(shape=(self.JJ, self.II), fill_value=self.startSurfID, dtype='<U6')

        QgsMessageLog.logMessage("Started: Gridding Surfaces...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.surfLayer = self.reprojectLayerToUTM(self.surfLayer, False)

        self.surfLayer_rot = self._extract_and_rotate(self.surfLayer)

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
        self.surfLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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

        # integer codes back to ENVI-met IDs; cells without a surface get the starting surface
        grid1_str_array = map_codes(grid1_int_array, {v: k for k, v in aTmpDict.items()}, self.startSurfID)
        aTmpDict.clear()
        QgsMessageLog.logMessage("Finished: Gridding Surfaces.", 'ENVI-met', level=Qgis.MessageLevel.Info)
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
        context = self.get_safe_processing_context()
        rlayer_clip = processing.run("gdal:cliprasterbyextent",
                                     {"INPUT": input_layer,
                                      "PROJWIN": boundingBox_margin,
                                      "OVERCRS": False,
                                      "OUTPUT": 'TEMPORARY_OUTPUT'},
                                     context=context)
        rlayerFN_clip = rlayer_clip['OUTPUT']
        # print(rlayerFN_clip)
        # QgsProject.instance().addMapLayer(rlayerFN_clip)
        # self.addRasterLayer(rlayerFN_clip,"surf_debug")

        # Now we resample the clipped raster layer to the defined grid-size (min(dx, dy))
        rlayer_resample = processing.run("gdal:warpreproject",
                                         {'INPUT': rlayerFN_clip,
                                          'RESAMPLING': 0,
                                          'NODATA': C_NODATA_VALUE,
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
                                   'SOURCE_CRS': input_layer.crs(),
                                   'TARGET_CRS': input_layer.crs(),
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
                                       "NODATA": C_NODATA_VALUE,
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
        if self.II > 0 and self.JJ > 0:
            grid1_int_array = self._conform_to_grid(grid1_int_array)
        else:
            self.II = grid1_int_array.shape[1]
            self.JJ = grid1_int_array.shape[0]

        grid1_str_array = grid1_int_array.astype(str)
        return grid1_str_array, grid1_int_array

    def raster_surface_from_raster(self):
        # reproject to UTM
        outFN = self.reprojectRasterLayerToUTM(self.surfLayer_raster)
        self.surfLayer_raster = QgsRasterLayer(outFN, "surfTMP_UTM")

        grid1_str_array, grid1_int_array = self.get_data_from_raster(self.surfLayer_raster)

        # raster values the user mapped onto ENVI-met soils; others get 'OTHER' if defined,
        # else the starting surface
        return map_values(grid1_str_array, self.surfLayer_raster_def, other=self.surfLayer_raster_def.get('OTHER'),
                          default=self.startSurfID)

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
        dataset.GetRasterBand(1).SetNoDataValue(C_NODATA_VALUE)

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

        # raster values the user mapped onto ENVI-met plants; others get 'OTHER' if defined, else no plant
        return map_values(grid1_str_array, self.plant1dLayer_raster_def,
                          other=self.plant1dLayer_raster_def.get('OTHER'), default='')

    # ==================================================================
    # Grid conforming and rasterization helpers
    # ==================================================================
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
            # QgsProject.instance().addMapLayer(input_layer)
        return input_layer

    def _conform_to_grid(self, arr):
        # GDAL's rasterize vs. warp/clip pipelines can disagree by one cell across GDAL
        # versions (seen going from QGIS 3.34 to 3.44). Force every gridded layer onto the
        # canonical model grid (self.JJ rows x self.II cols): crop extra boundary cells,
        # pad shortfalls with 0 (numeric) or "" (string) so all layers stay aligned.
        target = (self.JJ, self.II)
        if arr.shape == target:
            return arr
        fill = "" if arr.dtype.kind in ("U", "S") else 0
        out = np.full(target, fill, dtype=arr.dtype)
        r = min(arr.shape[0], self.JJ)
        c = min(arr.shape[1], self.II)
        out[:r, :c] = arr[:r, :c]
        return out

    def rasterize_gdal(self, input_layer, field, get_strArray: bool = False, burn_val: bool = False,
                       init_val=None, no_data_val: int = 0):
        context = self.get_safe_processing_context()
        params = {
            "INPUT": input_layer,
            ("BURN" if burn_val else "FIELD"): field,
            "UNITS": 1,
            "WIDTH": self.dx,
            "HEIGHT": self.dy,
            "EXTENT": self.subAreaExtent,
            "NODATA": no_data_val,
            "DATA_TYPE": 4,
            "INVERT": False,
            "OUTPUT": 'TEMPORARY_OUTPUT',
        }
        if init_val is not None:
            params["INIT"] = init_val
        rlayerFN = processing.run("gdal:rasterize", params, context=context)['OUTPUT']

        grid1 = gdal.Open(rlayerFN)
        grid1_band = grid1.GetRasterBand(1)
        grid1_int_array = grid1_band.ReadAsArray().astype(int)
        grid1_band.FlushCache()

        if self.II > 0 and self.JJ > 0:
            grid1_int_array = self._conform_to_grid(grid1_int_array)
        else:
            self.II = grid1_int_array.shape[1]
            self.JJ = grid1_int_array.shape[0]

        if get_strArray:
            return grid1_int_array.astype(str), grid1_int_array
        return grid1_int_array

    # ==================================================================
    # Gridding: vegetation
    # ==================================================================
    def raster_simple_plants_from_vector(self):
        if self.plant1dLayer.name() == "notAvail":
            return np.full(shape=(self.JJ, self.II), fill_value="", dtype='<U6')

        QgsMessageLog.logMessage("Started: Gridding Simple Plants...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.plant1dLayer = self.reprojectLayerToUTM(self.plant1dLayer, False)

        self.plant1dLayer_rot = self._extract_and_rotate(self.plant1dLayer)

        self.plant1dLayer_rot = self.reorgFID(self.plant1dLayer_rot)

        aTmpDict = {}
        if not self.plant1dID_UseCustom:
            # get all items in the vector layer
            spFeats = self.plant1dLayer_rot.getFeatures()
            i = 1
            for f in spFeats:
                plantID_str = f[self.plant1dID]
                if plantID_str and not plantID_str.isspace():
                    plantID_str = plantID_str.strip()
                    # if the plantID does not exist in the dict yet, add it
                    if aTmpDict.get(plantID_str) is None:
                        # plantID_str is the key, i the value
                        aTmpDict[plantID_str] = i
                        i += 1

            # add new column to the attribute-table of plant1dLayer_rot
            # this layer will store the integer values we just mapped in the dictionary
            self.plant1dLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.plant1dLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

            # write the corresponding integer values in each row, depending on the EnviID used in that row
            for f in self.plant1dLayer_rot.getFeatures():
                # get enviID in string
                plantID_str = f[self.plant1dID]
                if plantID_str and not plantID_str.isspace():
                    plantID_str = plantID_str.strip()
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
            grid1_str_array = map_codes(grid1_int_array, {v: k for k, v in aTmpDict.items()}, '')
            aTmpDict.clear()
        else:
            grid1_str_array = map_codes(grid1_int_array, {999: self.plant1dID_custom}, '')

        QgsMessageLog.logMessage("Finished: Gridding Simple Plants.", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_str_array

    def buildPlants3d(self):
        self.s_treeList.clear()
        if (self.plant3dLayer.name() == "notAvail") or (self.plant3dID == "") \
                or (self.plant3dLayer_rot.getFeatures() is None):
            return self.s_treeList

        # reproject to UTM
        self.plant3dLayer = self.reprojectLayerToUTM(self.plant3dLayer, False)

        QgsMessageLog.logMessage("Started: Gridding 3D Plants...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        self.plant3dLayer_rot = self._extract_and_rotate(self.plant3dLayer)

        self.plant3dLayer_rot = self.reorgFID(self.plant3dLayer_rot)

        aTmpDict = {}
        # user wants a const value for Trees
        if self.plant3dID_UseCustom:
            grid1_str_array, grid1_int_array = self.rasterize_gdal(input_layer=self.plant3dLayer_rot, field=999,
                                                                   get_strArray=True, burn_val=True)
        else:
            self.plant3dLayer_rot.startEditing()
            ID_int = 'ID_int'
            self.plant3dLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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
                    plantID_str = plantID_str.strip()
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

        # one tree per cell with a tree (row by row, as before)
        if self.plant3dID_UseCustom:
            for i, j in zip(*np.nonzero(grid1_int_array == 999)):
                root_i, root_j = raster_to_envimet_ij(int(i), int(j), self.JJ)
                newTree = dict(rootcell_i=root_i, rootcell_j=root_j, rootcell_k=0, plantID=str(self.plant3dID_custom),
                               name='Imported Plant', observe=0)
                self.s_treeList.append(newTree)
        else:
            for i, j in zip(*np.nonzero(grid1_int_array > 0)):
                tmpTree = aTmpDict.get(int(grid1_int_array[i, j]))
                if tmpTree is not None:
                    root_i, root_j = raster_to_envimet_ij(int(i), int(j), self.JJ)
                    newTree = dict(rootcell_i=root_i, rootcell_j=root_j, rootcell_k=0,
                                   plantID=tmpTree.enviID.replace("NULL", ""), name='Imported Plant',
                                   observe=tmpTree.obs)
                    self.s_treeList.append(newTree)
            aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding 3D Plants.", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return self.s_treeList

    # ==================================================================
    # Terrain / DEM
    # ==================================================================
    def getDEM(self, interpolate: int = 1):
        # Get non-rotated subArea extent for clipping the warp
        spFeats = self.subAreaLayer_nonRot.getFeatures()
        for f in spFeats:
            if f.hasGeometry():
                subArea_Extent = f.geometry().boundingBox()

        context = self.get_safe_processing_context()
        rlayer_resample = processing.run("gdal:warpreproject",
                                         {'INPUT': self.dEMLayer,
                                          'SOURCE_CRS': self.dEMLayer.crs(),
                                          'TARGET_CRS': self.subAreaLayer.crs(),
                                          'RESAMPLING': interpolate if interpolate > 0 else 0,
                                          'TARGET_RESOLUTION': min(self.dx * 0.75, self.dy * 0.75) if interpolate > 0 else None,
                                          'OPTIONS': '',
                                          'DATA_TYPE': 0,
                                          'TARGET_EXTENT': subArea_Extent,
                                          'TARGET_EXTENT_CRS': None,
                                          'MULTITHREADING': True,
                                          'EXTRA': '',
                                          'OUTPUT': 'TEMPORARY_OUTPUT'},
                                         context=context)
        rlayerFN_clip = rlayer_resample['OUTPUT']

        # Read the warped raster directly — avoids the slow pixel→polygon→rotate→rasterize detour
        ds = gdal.Open(rlayerFN_clip)
        band = ds.GetRasterBand(self.dEMBand)
        dem_arr = band.ReadAsArray().astype(np.float64)
        nodata_val = band.GetNoDataValue()
        gt = ds.GetGeoTransform()  # (x_origin, x_pixel_size, 0, y_origin, 0, y_pixel_size)
        ds = None

        if nodata_val is not None:
            dem_arr[dem_arr == nodata_val] = np.nan

        # Compute output grid dimensions (same result as rasterize_gdal would produce)
        ext = self.subAreaExtent
        ncols = round((ext.xMaximum() - ext.xMinimum()) / self.dx)
        nrows = round((ext.yMaximum() - ext.yMinimum()) / self.dy)
        self.II = ncols
        self.JJ = nrows

        # Build center coordinates of every output cell in the rotated grid space
        col_centers = ext.xMinimum() + (np.arange(ncols) + 0.5) * self.dx
        row_centers = ext.yMaximum() - (np.arange(nrows) + 0.5) * self.dy
        grid_x, grid_y = np.meshgrid(col_centers, row_centers)

        # Undo the QGIS clockwise rotation (inverse = counterclockwise by same angle)
        # to map each output cell center back to the source DEM coordinate space
        cx = self.model_rot_center.x()
        cy = self.model_rot_center.y()
        angle_rad = math.radians(self.model_rot)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        dx_ = grid_x - cx
        dy_ = grid_y - cy
        src_x = cx + cos_a * dx_ - sin_a * dy_
        src_y = cy + sin_a * dx_ + cos_a * dy_

        # Convert world coordinates → fractional pixel coordinates in the warped DEM
        px = (src_x - gt[0]) / gt[1]
        py = (src_y - gt[3]) / gt[5]

        # Vectorised bilinear sampling (nearest-neighbour when interpolate == 0)
        h, w = dem_arr.shape
        if interpolate > 0:
            x0 = np.floor(px).astype(int)
            y0 = np.floor(py).astype(int)
            x1 = x0 + 1
            y1 = y0 + 1
            fx = px - x0
            fy = py - y0
            x0c = np.clip(x0, 0, w - 1)
            x1c = np.clip(x1, 0, w - 1)
            y0c = np.clip(y0, 0, h - 1)
            y1c = np.clip(y1, 0, h - 1)
            sampled = (dem_arr[y0c, x0c] * (1 - fx) * (1 - fy) + dem_arr[y0c, x1c] * fx * (1 - fy) + dem_arr[y1c, x0c] * (1 - fx) * fy + dem_arr[y1c, x1c] * fx * fy)
        else:
            xi = np.clip(np.round(px).astype(int), 0, w - 1)
            yi = np.clip(np.round(py).astype(int), 0, h - 1)
            sampled = dem_arr[yi, xi]

        # Mark cells that fell outside the warped raster extent as NaN
        oob = (px < 0) | (px >= w) | (py < 0) | (py >= h)
        sampled[oob] = np.nan

        # Fill nodata with the mean of valid cells
        valid = ~np.isnan(sampled)
        avg_height = float(sampled[valid].mean()) if valid.any() else 0.0
        grid1_float = np.where(valid, sampled, avg_height)

        # Subtract the minimum elevation and record reference heights
        min_height = float(grid1_float.min())
        grid1_float -= min_height
        max_height = float(grid1_float.max())

        self.refHeightDEM = min_height
        self.maxHeightDEM = max_height

        return grid1_float.astype(int)

    # ==================================================================
    # Gridding: sources
    # ==================================================================
    def rasterSrcP(self):
        if self.srcPLayer.name() == "notAvail":
            return np.full(shape=(self.JJ, self.II), fill_value="", dtype='<U6')
        QgsMessageLog.logMessage("Started: Gridding Sources (Points)...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.srcPLayer = self.reprojectLayerToUTM(self.srcPLayer, False)

        self.srcPLayer_rot = self._extract_and_rotate(self.srcPLayer)

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
            self.srcPLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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
            grid1_str_array = map_codes(grid1_int_array, {v: k for k, v in aTmpDict.items()}, '')
        else:
            grid1_str_array = map_codes(grid1_int_array, {999: self.srcPID_custom}, '')

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Points).", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_str_array

    def rasterSrcL(self):
        if self.srcLLayer.name() == "notAvail" or (self.srcLID_UseCustom and (self.srcLID_custom == "notAvail")):
            return np.full(shape=(self.JJ, self.II), fill_value="", dtype='<U6')

        QgsMessageLog.logMessage("Started: Gridding Sources (Lines)...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.srcLLayer = self.reprojectLayerToUTM(self.srcLLayer, False)

        self.srcLLayer_rot = self._extract_and_rotate(self.srcLLayer)

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
            self.srcLLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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
            grid1_str_array = map_codes(grid1_int_array, {v: k for k, v in aTmpDict.items()}, '')
        else:
            grid1_str_array = map_codes(grid1_int_array, {999: self.srcLID_custom}, '')

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Lines).", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_str_array

    def rasterSrcA(self):
        if self.srcALayer.name() == "notAvail":
            return np.full(shape=(self.JJ, self.II), fill_value="", dtype='<U6')

        QgsMessageLog.logMessage("Started: Gridding Sources (Areas)...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # reproject to UTM
        self.srcALayer = self.reprojectLayerToUTM(self.srcALayer, False)

        self.srcALayer_rot = self._extract_and_rotate(self.srcALayer)

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
            self.srcALayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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
            grid1_str_array = map_codes(grid1_int_array, {v: k for k, v in aTmpDict.items()}, '')
        else:
            grid1_str_array = map_codes(grid1_int_array, {999: self.srcAID_custom}, '')

        aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Sources (Areas).", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return grid1_str_array

    # ==================================================================
    # Gridding: receptors
    # ==================================================================
    def buildReceptors(self):
        self.s_recList.clear()
        if self.recLayer.name() == "notAvail":
            return self.s_recList

        # reproject to UTM
        self.recLayer = self.reprojectLayerToUTM(self.recLayer, False)

        QgsMessageLog.logMessage("Started: Gridding Receptors...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        self.recLayer_rot = self._extract_and_rotate(self.recLayer)

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
            self.recLayer_rot.addAttribute(QgsField(ID_int, FIELD_TYPE_INT))

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
            # QgsVectorFileWriter.writeAsVectorFormat(self.recLayer_rot, "C:/Users/simonhe/AppData/Local/Temp/processing_HWIddK/760a68c50707482880b5084165a1d3b3/a", "UTF-8", self.recLayer_rot.crs(), "ESRI Shapefile")
            # print(grid1_str_array)

        # one receptor per cell with a receptor (row by row, as before)
        if self.recID_UseCustom:
            self.recID_custom = "r_"
            for number, (i, j) in enumerate(zip(*np.nonzero(grid1_int_array == 999))):
                cell_i, cell_j = raster_to_inx_receptor_cell(int(i), int(j), self.JJ)
                newRec = dict(cell_i=cell_i, cell_j=cell_j, name=self.recID_custom + "{:04d}".format(number))
                self.s_recList.append(newRec)
        else:
            names = {v: k for k, v in aTmpDict.items()}
            for i, j in zip(*np.nonzero(grid1_int_array > 0)):
                name = names.get(int(grid1_int_array[i, j]))
                if name is not None:
                    cell_i, cell_j = raster_to_inx_receptor_cell(int(i), int(j), self.JJ)
                    newRec = dict(cell_i=cell_i, cell_j=cell_j, name=str(name))
                    self.s_recList.append(newRec)
            aTmpDict.clear()

        QgsMessageLog.logMessage("Finished: Gridding Receptors.", 'ENVI-met', level=Qgis.MessageLevel.Info)
        return self.s_recList

    # ==================================================================
    # Reprojection helpers
    # ==================================================================
    def reprojectLayerToUTM(self, aLayer, isSubAreaLayer: bool):
        context = self.get_safe_processing_context()
        if not isSubAreaLayer and self.target_epsg is not None:
            # Every input goes into the sub-area's UTM zone, whatever its own extent (the zone used to be
            # taken from each layer's extent corner, so one far-away feature moved the whole layer).
            # Only the features near the sub-area are reprojected.
            near = processing.run('native:extractbyextent',
                                  {'INPUT': aLayer, 'EXTENT': self._sub_area_extent_referenced(), 'CLIP': False,
                                   'OUTPUT': 'memory:near'}, context=context)['OUTPUT']
            return processing.run('native:reprojectlayer',
                                  {'INPUT': near, 'TARGET_CRS': 'EPSG:' + str(self.target_epsg),
                                   'OUTPUT': 'memory:Reprojected'}, context=context)['OUTPUT']

        # print(aLayer.crs().authid().split(":")[1])
        if not (aLayer.crs().authid().split(":")[1] == str(4326)):
            # print('in_if')
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
                # print(f"Centroid - Longitude: {lon}, Latitude: {lat}")
        aUTMZone = get_UTM_zone(lon, lat)
        # print(aUTMZone)
        auth_id = self.find_crs_auth_id("WGS 84 / UTM zone " + aUTMZone.replace(' ', ''))
        # print(auth_id)

        # fill vars only if subAreaLayer
        if isSubAreaLayer:
            self.lon = lon
            self.lat = lat
            self.UTMZone = aUTMZone.split(" ")[0]
            self.UTMHemisphere = aUTMZone.split(" ")[1]
            self.target_epsg = auth_id

        parameter = {
            'INPUT': aLayer,
            'TARGET_CRS': 'EPSG:' + str(auth_id),
            'OUTPUT': 'memory:Reprojected'
        }
        return processing.run('native:reprojectlayer', parameter, context=context)['OUTPUT']

    def _sub_area_extent(self, margin=50.0):
        """Extent of the (unrotated) sub-area in its UTM CRS, grown by ``margin`` metres."""
        extent = QgsRectangle(self.subAreaLayer_nonRot.extent())
        extent.grow(margin)
        return extent

    def _sub_area_extent_referenced(self, margin=50.0):
        return QgsReferencedRectangle(self._sub_area_extent(margin), self.subAreaLayer_nonRot.crs())

    def reprojectRasterLayerToUTM(self, aLayer):
        context = self.get_safe_processing_context()
        source_crs = aLayer.crs()
        if self.target_epsg is not None:
            # the sub-area's zone; and only the part of the raster around the sub-area is warped
            auth_id = self.target_epsg
            transform = QgsCoordinateTransform(self.subAreaLayer_nonRot.crs(), aLayer.crs(),
                                               QgsCoordinateTransformContext())
            window = transform.transformBoundingBox(self._sub_area_extent(margin=150.0))
            window = window.intersect(aLayer.extent())
            if not window.isEmpty():
                aLayer = processing.run("gdal:cliprasterbyextent",
                                        {"INPUT": aLayer, "PROJWIN": window, "OVERCRS": False,
                                         "OUTPUT": 'TEMPORARY_OUTPUT'}, context=context)['OUTPUT']
        else:
            proj = pyproj.Transformer.from_crs(aLayer.crs().authid(), 4326, always_xy=True)
            x1, y1 = (aLayer.extent().xMinimum(), aLayer.extent().yMinimum())
            lon, lat = proj.transform(x1, y1)
            aUTMZone = get_UTM_zone(lon, lat)
            auth_id = self.find_crs_auth_id("WGS 84 / UTM zone " + aUTMZone.replace(' ', ''))

        reshaped = processing.run("gdal:warpreproject",
                                  {'INPUT': aLayer,
                                   'SOURCE_CRS': source_crs,
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
        # print(reshaped['OUTPUT'])
        return reshaped['OUTPUT']

    # ==================================================================
    # INX export
    # ==================================================================
    def saveINX(self):
        QgsMessageLog.logMessage("--- Started Exporting INX-File ---", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # precaution -> we always reproject to UTM
        self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot, True)
        self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer, True)
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
        self.UTMZone = get_UTM_zone(lon, lat)

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
            bFixHeight_int_array[bTop_int_array > 0] = 1
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

        # one source per cell: points before lines before areas
        src_str_array = first_non_empty(srcP_str_array, srcL_str_array, srcA_str_array)

        self.progress.emit(60)

        # DEM
        if (self.dEMLayer.name() == "notAvail") or (self.dEMBand <= 0):
            dem_int_array = np.zeros(shape=(self.JJ, self.II), dtype=int)
        else:
            QgsMessageLog.logMessage("Started: Gridding Terrain...", 'ENVI-met', level=Qgis.MessageLevel.Info)
            dem_int_array = self.getDEM(interpolate=self.dEMInterpol)
            QgsMessageLog.logMessage("Finished: Gridding Terrain.", 'ENVI-met', level=Qgis.MessageLevel.Info)

        self.elevation = self.get_elevation_geonames()

        self.progress.emit(70)

        QgsMessageLog.logMessage("Preparing Model Border...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        # empty cells at border -> only for buildings
        if self.removeBBorder > 0:
            # the same number of cells on every side (the south and east sides kept one row/column more)
            border = border_mask(bTop_int_array.shape, self.removeBBorder)
            bRemSet = set(np.unique(bNumber_int_array[border & (bNumber_int_array > 0)]).tolist())
            for array in (bFixHeight_int_array, bTop_int_array, bBot_int_array, bNumber_int_array):
                array[border] = 0
            # now update bList — drop buildings that no longer have any cells
            remaining_buildings = set(np.unique(bNumber_int_array).tolist())
            for bRem in bRemSet:
                if bRem not in remaining_buildings:
                    self.s_buildingDict.pop(bRem, None)

        # check if buildings should be leveled with DEM
        QgsMessageLog.logMessage("Preparing Buildings in DEM...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        if not (self.dEMLayer.name() == "notAvail") and not (self.dEMBand <= 0) and self.bLeveled:
            # group all occupied cells by building number in a single pass
            bListDEM_dict = {}
            i_idx, j_idx = np.where(bNumber_int_array > 0)
            for i, j in zip(i_idx, j_idx):
                bnum = int(bNumber_int_array[i, j])
                level = bListDEM_dict.get(bnum)
                if level is None:
                    level = BLevel(bnum)
                    bListDEM_dict[bnum] = level
                level.cellList.append(Cell(int(i), int(j), 0))

            # flatten the terrain under each building down to its minimum elevation
            for level in bListDEM_dict.values():
                if not level.cellList:
                    continue
                cells_i = np.fromiter((c.i for c in level.cellList), dtype=int, count=len(level.cellList))
                cells_j = np.fromiter((c.j for c in level.cellList), dtype=int, count=len(level.cellList))
                dem_int_array[cells_i, cells_j] = dem_int_array[cells_i, cells_j].min()

        # check if vegetation on buildings should be removed
        QgsMessageLog.logMessage("Check if Vegetation on Buildings should be removed...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        if self.removeVegBuild:
            building_mask = bNumber_int_array > 0
            simplePlant_str_array[building_mask] = ""
            i_idx, j_idx = np.where(building_mask)
            blocked_cells = {raster_to_envimet_ij(int(i), int(j), self.JJ) for i, j in zip(i_idx, j_idx)}
            self.s_treeList = [
                t for t in self.s_treeList
                if (t.get("rootcell_i"), t.get("rootcell_j")) not in blocked_cells
            ]

        # check buildings need to be removed e.g. building height = 0 or < 0
        QgsMessageLog.logMessage("Check integrity of Buildings...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        invalid = (bTop_int_array <= 0) | (bBot_int_array >= bTop_int_array)
        bRemSet02 = set(np.unique(bNumber_int_array[invalid]).tolist())
        for array in (bTop_int_array, bBot_int_array, bNumber_int_array):
            array[invalid] = 0

        # now update bList — drop buildings that no longer have any cells
        remaining_buildings = set(np.unique(bNumber_int_array).tolist())
        for bRem02 in bRemSet02:
            if bRem02 not in remaining_buildings:
                self.s_buildingDict.pop(bRem02, None)

        self.progress.emit(80)
        QgsMessageLog.logMessage("Converting Data to ENVI-met model area...", 'ENVI-met', level=Qgis.MessageLevel.Info)

        # finally convert to matrix text, one line per row as SPACES writes it
        bTop_str_matrix = matrix_text(bTop_int_array)
        bBot_str_matrix = matrix_text(bBot_int_array)
        bNumber_str_matrix = matrix_text(bNumber_int_array)
        bFixHeight_str_matrix = matrix_text(bFixHeight_int_array)
        dem_str_matrix = matrix_text(dem_int_array)
        simplePlant_str_matrix = matrix_text(simplePlant_str_array)
        surf_str_matrix = matrix_text(surf_str_array)
        src_str_matrix = matrix_text(src_str_array)

        self.progress.emit(90)
        QgsMessageLog.logMessage("Writing file...", 'ENVI-met', level=Qgis.MessageLevel.Info)
        with open(self.filename, 'w', encoding='utf-8') as output_file:
            # Print functions
            print("<ENVI-MET_Datafile>", file=output_file)
            print("  <Header>", file=output_file)
            print("    <filetype>INPX ENVI-met Area Input File</filetype>", file=output_file)
            print("    <version>4</version>", file=output_file)
            print("    <revisiondate>  </revisiondate>", file=output_file)
            print("    <remark> model created by QGIS plugin, additional settings: def roof material: " + self.defaultRoof + "; def wall material: " + self.defaultWall + "; clear buildings cells at border: " + str(self.removeBBorder) + "; leveled buildings in DEM: " + str(self.bLeveled) + "; building height not fixed: " + str(self.bNOTFixedH) + "; starting surface: " + self.startSurfID + "; remove veg from buildings: " + str(self.removeVegBuild) + " </remark>", file=output_file)
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
            print("     </ID_plants1D>", file=output_file)
            print("  </simpleplants2D>", file=output_file)

            for tree in self.s_treeList:
                print("  <3Dplants>", file=output_file)
                # 1-based, see core.grid
                print("    <rootcell_i> " + str(tree.get("rootcell_i")) + " </rootcell_i>", file=output_file)
                print("    <rootcell_j> " + str(tree.get("rootcell_j")) + " </rootcell_j>", file=output_file)
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
            print("     <ID_sources type=\"matrix-data\" dataI=\"" + str(self.II) + "\" dataJ=\"" + str(self.JJ) + "\">", file=output_file)
            print(src_str_matrix, file=output_file)
            print("     </ID_sources>", file=output_file)
            print("  </sources2D>", file=output_file)

            for rec in self.s_recList:
                print("  <Receptors>", file=output_file)
                # 0-based, unlike the 3D plants above; see core.grid
                print("    <cell_i> " + str(rec.get("cell_i")) + " </cell_i>", file=output_file)
                print("    <cell_j> " + str(rec.get("cell_j")) + " </cell_j>", file=output_file)
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
        QgsMessageLog.logMessage("--- Finished Exporting INX-File ---", 'ENVI-met', level=Qgis.MessageLevel.Info)

    # ==================================================================
    # Vertical extent and grid preview
    # ==================================================================
    def calc_vert_ext(self):
        if self.subAreaLayer.name() == "notAvail":
            return

        self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot, True)
        self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer, True)
        self.get_modelrot()

        self.II = round((self.subAreaExtent.xMaximum() - self.subAreaExtent.xMinimum()) / self.dx)
        self.JJ = round((self.subAreaExtent.yMaximum() - self.subAreaExtent.yMinimum()) / self.dy)

        if (self.bLayer.name() == "notAvail") or (self.bTop == "notAvail") or (self.bLayer.name() == "") or (self.bTop == ""):
            self.maxHeightB = 0
        else:
            # reproject to UTM
            self.bLayer = self.reprojectLayerToUTM(self.bLayer, False)

            # only rotate buildings inside subarea
            bLayer = self._extract_and_rotate(self.bLayer)

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
        # print(self.bTop_UseCustom)
        if self.bTop_UseCustom:
            # print("here")
            # print(self.bTop_custom)
            self.maxHeightB = self.bTop_custom

        # now get the terrain max height
        if (self.dEMLayer.name() == "notAvail") or (self.dEMBand < 1):
            self.maxHeightDEM = 0
        else:
            # self.maxHeightDEM = 0
            self.getDEM(interpolate=0)  # self.maxHeightDEM is now filled

        self.maxHeightTotal = self.maxHeightB + self.maxHeightDEM

        self.finished.emit()

    def previewdxy(self):
        if self.subAreaLayer.name() == "notAvail":
            self.finished.emit()
            return
        else:
            self.subAreaLayer_nonRot = self.reprojectLayerToUTM(self.subAreaLayer_nonRot, True)
            self.subAreaLayer = self.reprojectLayerToUTM(self.subAreaLayer, True)
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

    # ==================================================================
    # Worker lifecycle
    # ==================================================================
    def run_save_inx(self):
        self.progress.emit(0)
        t1 = time.time()
        self.saveINX()
        t2 = time.time()
        print('Time to save the INX-file: ' + str(t2 - t1))
        # report via pyqt-signal that run method of Worker-Class has been finished
        self.finished.emit()

    def stop(self):
        self.stopworker = True

    # ==================================================================
    # Processing utilities
    # ==================================================================
    def get_safe_processing_context(self):
        """Creates a processing context compatible with both QGIS 3.4 and QGIS 3.40+"""
        context = dataobjects.createContext()
        try:
            # Modern API (QGIS 3.10, 3.40, QGIS 4)
            context.setInvalidGeometryCheck(QgsFeatureRequest.InvalidGeometryCheck.GeometryNoCheck)
        except AttributeError:
            # Legacy API (QGIS 3.4)
            context.setInvalidGeometryCheck(QgsFeatureRequest.GeometrySkipInvalid)
        return context
