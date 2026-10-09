from qgis.PyQt.QtCore import QLocale, QTranslator, QCoreApplication, QThread, QTimer, Qt, QDate, QTime
from qgis.PyQt import QtCore
from qgis.PyQt.QtGui import QDoubleValidator, QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog
from qgis.core import (Qgis, QgsApplication, QgsDistanceArea, QgsField, QgsGeometry, QgsMapLayerProxyModel,
                       QgsPointXY, QgsProject, QgsVectorLayer, QgsFieldProxyModel, QgsRasterLayer, QgsSettings,
                       QgsMessageLog)

# Initialize the bundled Qt resources (icons etc.); importing resources.py has
# the side effect of calling qInitResources().
from . import resources  # noqa: F401
# Import the code for the dialog
from .geodata2ENVImet_dialog import Geo2ENVImetDialog
import os.path
from .Const_defines import FIELD_TYPE_INT, FIELD_TYPE_STRING, C_NODATA_VALUE
from .ENVImet_DB_loader import ENVImetDB, EnviProjects
from .Worker import Worker
from datetime import datetime
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtWidgets import QMessageBox, QListWidgetItem
import os
import subprocess
import traceback
from .Dataseries_handler import dataseries, STATE_COMPARABLE, STATE_ONLY_A, STATE_ONLY_B
from .result_layers import Cutline, LayerRequest, ResultLayersTask
from .processing_provider.provider import EnvimetProvider
from .core import envimet_install
from .core.forcing import diurnal_profile
from .core import simx as core_simx
from .core import indoor as core_indoor
from .core import modules as core_modules
from .core import surrounding as core_surrounding
from . import simx_ui
import math
import shutil


class Geo2ENVImet:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale; 'locale/userLocale' is unset in a fresh QGIS profile
        # (fix from PR #2 by Till Frankenbach, restored)
        try:
            locale = QgsSettings().value('locale/userLocale')
            if not locale:
                locale = QLocale().name()
            locale = locale[0:2]
            locale_path = os.path.join(
                self.plugin_dir,
                'i18n',
                'Geo2ENVImet_{}.qm'.format(locale))

            if os.path.exists(locale_path):
                self.translator = QTranslator()
                self.translator.load(locale_path)
                QCoreApplication.installTranslator(self.translator)
        except TypeError:
            pass

        # Declare instance attributes
        self.actions = []
        self.menu = self.translate_phrase(u'&Geodata to ENVI-met')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        # declare class fields for ENVI-met Database
        self.enviProjects = None
        self.db_loaded = None

        # declare class fields for the worker-thread
        self.thread = None
        self.worker = None

        # declare class field for UI
        self.dlg = None
        # the last loaded SIMX file; settings the UI does not show are written back unchanged
        self.loaded_simx = None

        # status states
        self.generalSettings_states = ('No model area (*.INX) selected!', 'Invalid simulation name!', '')
        self.meteoSettings_states = ('Simple Forcing selected', 'Full Forcing selected - FOX-file missing',
                                     'Full Forcing selected')

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/geodata2ENVImet/icon.png'
        self.add_action(
            icon_path,
            text=self.translate_phrase(u'Convert geodata to ENVI-met'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True
        # will be set True in load_db()
        self.db_loaded = False

        # Processing algorithms (area analysis)
        self.provider = EnvimetProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        if getattr(self, 'provider', None) is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
        for action in self.actions:
            self.iface.removePluginMenu(
                self.translate_phrase(u'&Geodata to ENVI-met'),
                action)
            self.iface.removeToolBarIcon(action)

    @staticmethod
    def translate_phrase(message):
        """Get the translation for a string using Qt translation API.

        :param message: String to translate.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('Geo2ENVImet', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """
        SOURCE: https://www.qgistutorials.com/en/docs/3/building_a_python_plugin.html

        Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def start_worker_inx(self):  # method to start the worker thread
        if self.dlg.cb_subArea.currentLayer() is None:
            self.iface.messageBar().pushMessage("Error", "Please select at least a sub area layer", level=Qgis.Warning)
            return

        if self.dlg.lineEdit.text() == "":
            self.iface.messageBar().pushMessage("Error", "Please define an output filename", level=Qgis.Warning)
            return

        self.thread = QThread()
        self.worker = Worker()

        # here we transfer the GUI values to the worker
        self.transfer_building_info_to_worker()
        self.transfer_surface_info_to_worker()
        self.transfer_simple_plant_info_to_worker()
        self.transfer_3dplant_info_to_worker()
        self.transfer_dem_info_to_worker()
        self.transfer_receptor_info_to_worker()
        self.transfer_sources_info_to_worker()

        self.transfer_subarea_gridding_info_to_worker()
        self.transfer_additional_options_to_worker()
        # transfer filename to worker
        self.worker.filename = self.dlg.lineEdit.text()

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(self.worker.run_save_inx)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.reportProgress)
        self.thread.start()  # finally start the thread

        # disable GUI
        self.dlg.bt_SaveINX.setEnabled(False)
        self.dlg.bt_SaveTo.setEnabled(False)
        self.dlg.gb_Geodata.setEnabled(False)

        self.thread.finished.connect(self.updateExport)  # enable the start-thread button when thread has been finished

    def transfer_additional_options_to_worker(self):
        # transfer additional options
        self.worker.defaultRoof = self.dlg.le_defRoof.text()
        self.worker.defaultWall = self.dlg.le_defWall.text()
        if self.dlg.chk_bBorders.isChecked():
            self.worker.removeBBorder = self.dlg.se_bBorders.value()
        else:
            self.worker.removeBBorder = 0
        self.worker.bLeveled = self.dlg.chk_bDEMLevel.isChecked()
        self.worker.bNOTFixedH = self.dlg.chk_bFixedH.isChecked()
        if self.dlg.chk_startSurf.isChecked():
            self.worker.startSurfID = self.dlg.le_surfStart.text()
        else:
            self.worker.startSurfID = "0100PP"
        self.worker.removeVegBuild = self.dlg.chk_bVeg.isChecked()

    def transfer_subarea_gridding_info_to_worker(self):
        # transfer subarea and gridding info
        self.worker.subAreaLayer = self.dlg.cb_subArea.currentLayer()
        self.worker.subAreaLayer_nonRot = self.dlg.cb_subArea.currentLayer()
        self.worker.useSurroundingArea = self.dlg.chk_surroundingArea.isChecked()
        self.worker.surroundingBorders = {border: getattr(self.dlg, f'cb_border{border}').currentIndex()
                                          for border in core_surrounding.BORDERS}
        self.worker.dx = self.dlg.se_dx.value()
        self.worker.dy = self.dlg.se_dy.value()
        self.worker.dz = self.dlg.se_dz.value()
        # self.worker.II and self.worker.JJ will be set by the gridding functions
        self.worker.KK = self.dlg.se_zGrids.value()
        self.worker.useSplitting = self.dlg.chk_useSplitting.isChecked()
        self.worker.useTelescoping = self.dlg.chk_useTelescoping.isChecked()
        self.worker.teleStart = self.dlg.se_teleStart.value()
        self.worker.teleStretch = self.dlg.se_teleStretch.value()

    def transfer_sources_info_to_worker(self):
        # transfer sources info Point
        if self.dlg.cb_srcPLayer.currentLayer() is None:
            self.worker.srcPLayer = QgsVectorLayer("Point", "notAvail", "memory")
        else:
            self.worker.srcPLayer = self.dlg.cb_srcPLayer.currentLayer()
        self.worker.srcPID_UseCustom = self.dlg.chk_srcPID.isChecked()
        if self.worker.srcPID_UseCustom:
            self.worker.srcPID = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.srcPID_custom = self.dlg.le_srcP.text()
        else:
            self.worker.srcPID = self.dlg.cb_srcPID.currentField()
            self.worker.srcPID_custom = "notAvail"

        # transfer sources info Line
        if self.dlg.cb_srcLLayer.currentLayer() is None:
            self.worker.srcLLayer = QgsVectorLayer("Line", "notAvail", "memory")
        else:
            self.worker.srcLLayer = self.dlg.cb_srcLLayer.currentLayer()
        self.worker.srcLID_UseCustom = self.dlg.chk_srcLID.isChecked()
        if self.worker.srcLID_UseCustom:
            self.worker.srcLID = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.srcLID_custom = self.dlg.le_srcL.text()
        else:
            self.worker.srcLID = self.dlg.cb_srcLID.currentField()
            self.worker.srcLID_custom = "notAvail"

        # transfer sources info Area
        if self.dlg.cb_srcALayer.currentLayer() is None:
            self.worker.srcALayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        else:
            self.worker.srcALayer = self.dlg.cb_srcALayer.currentLayer()
        self.worker.srcAID_UseCustom = self.dlg.chk_srcAID.isChecked()
        if self.worker.srcAID_UseCustom:
            self.worker.srcAID = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.srcAID_custom = self.dlg.le_srcA.text()
        else:
            self.worker.srcAID = self.dlg.cb_srcAID.currentField()
            self.worker.srcAID_custom = "notAvail"

    def transfer_receptor_info_to_worker(self):
        # transfer receptor info
        if self.dlg.cb_recLayer.currentLayer() is None:
            self.worker.recLayer = QgsVectorLayer("Point", "notAvail", "memory")
        else:
            self.worker.recLayer = self.dlg.cb_recLayer.currentLayer()
        self.worker.recID_UseCustom = self.dlg.chk_recID.isChecked()
        if self.worker.recID_UseCustom:
            self.worker.recID = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.recID_Custom = "R"
        else:
            self.worker.recID = self.dlg.cb_recID.currentField()
            self.worker.recID_Custom = "notAvail"

    def transfer_dem_info_to_worker(self):
        # transfer DEM info
        if self.dlg.cb_demLayer.currentLayer() is None:
            self.worker.dEMLayer = QgsRasterLayer("", "notAvail")
        else:
            self.worker.dEMLayer = self.dlg.cb_demLayer.currentLayer()
        if self.dlg.cb_demBand.currentBand() is None:
            self.worker.dEMBand = -1
        else:
            self.worker.dEMBand = self.dlg.cb_demBand.currentBand()

        self.worker.dEMInterpol = self.dlg.cb_demInterpol.currentIndex()

    def transfer_3dplant_info_to_worker(self):
        # transfer 3d plant info
        if self.dlg.cb_plant3dLayer.currentLayer() is None:
            self.worker.plant3dLayer = QgsVectorLayer("Point", "notAvail", "memory")
        else:
            self.worker.plant3dLayer = self.dlg.cb_plant3dLayer.currentLayer()
        self.worker.plant3dID_UseCustom = self.dlg.chk_plant3d.isChecked()
        if self.worker.plant3dID_UseCustom:
            self.worker.plant3dID = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.plant3dID_custom = self.dlg.le_plant3d.text()
        else:
            self.worker.plant3dID = self.dlg.cb_plant3dID.currentField()
            self.worker.plant3dID_custom = "notAvail"
        self.worker.plant3dAddOut_disabled = self.dlg.chk_plant3dAddOut.isChecked()
        if self.worker.plant3dAddOut_disabled:
            self.worker.plant3dAddOut = QgsField("notAvail", FIELD_TYPE_STRING)
        else:
            self.worker.plant3dAddOut = self.dlg.cb_plant3dAddOut.currentField()

    def transfer_simple_plant_info_to_worker(self):
        if self.dlg.rb_simplePlantsVector.isChecked():
            self.worker.plant1dLayerFromVector = True
            if self.dlg.cb_simplePlantLayer.currentLayer() is None:
                self.worker.plant1dLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
            else:
                self.worker.plant1dLayer = self.dlg.cb_simplePlantLayer.currentLayer()
            self.worker.plant1dID_UseCustom = self.dlg.chk_simplePlantID.isChecked()
            if self.worker.plant1dID_UseCustom:
                self.worker.plant1dID = QgsField("notAvail", FIELD_TYPE_STRING)
                self.worker.plant1dID_custom = self.dlg.le_simplePlant.text()
            else:
                self.worker.plant1dID = self.dlg.cb_simplePlantID.currentField()
                self.worker.plant1dID_custom = "notAvail"
        elif self.dlg.rb_simplePlantsRaster.isChecked():
            self.worker.plant1dLayerFromVector = False
            if self.dlg.cb_MapLayerRasterSP.currentLayer() is None:
                self.worker.plant1dLayer_raster = QgsRasterLayer("", "notAvail")
            else:
                self.worker.plant1dLayer_raster = self.dlg.cb_MapLayerRasterSP.currentLayer()
            if self.dlg.cb_RasterBandRasterSP.currentBand() is None:
                self.worker.plant1dLayer_raster_band = -1
            else:
                self.worker.plant1dLayer_raster_band = self.dlg.cb_RasterBandRasterSP.currentBand()
            self.worker.plant1dLayer_raster_def = self.get_layer_definition(textEdit=self.dlg.te_defineRasterValsSP)

    def transfer_surface_info_to_worker(self):
        if self.dlg.rb_surfVector.isChecked():
            self.worker.surfLayerfromVector = True
            if self.dlg.cb_surfLayer.currentLayer() is None:
                self.worker.surfLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
            else:
                self.worker.surfLayer = self.dlg.cb_surfLayer.currentLayer()
            self.worker.surfID_UseCustom = self.dlg.chk_surf.isChecked()
            if self.worker.surfID_UseCustom:
                self.worker.surfID = QgsField("notAvail", FIELD_TYPE_STRING)
                self.worker.surfID_custom = self.dlg.le_surf.text()
            else:
                self.worker.surfID = self.dlg.cb_surfID.currentField()
                self.worker.surfID_custom = "notAvail"
        elif self.dlg.rb_surfRaster.isChecked():
            self.worker.surfLayerfromVector = False
            if self.dlg.cb_MapLayerRasterSurf.currentLayer() is None:
                self.worker.surfLayer_raster = QgsRasterLayer("", "notAvail")
            else:
                self.worker.surfLayer_raster = self.dlg.cb_MapLayerRasterSurf.currentLayer()
            if self.dlg.cb_RasterBandRasterSurf.currentBand() is None:
                self.worker.surfLayer_raster_band = -1
            else:
                self.worker.surfLayer_raster_band = self.dlg.cb_RasterBandRasterSurf.currentBand()
            self.worker.surfLayer_raster_def = self.get_layer_definition(textEdit=self.dlg.te_defineRasterVals)

    @staticmethod
    def get_layer_definition(textEdit, asDict: bool = True):
        aTmpDict = {}
        def_list = textEdit.toPlainText().splitlines(True)
        def_list = [entry.replace("\n", "") for entry in def_list]
        if asDict:
            for i in range(len(def_list)):
                def_list[i] = (def_list[i].replace(" ", "")).upper()
                row = def_list[i].split("->")
                if len(row) > 1:
                    aTmpDict[row[0]] = row[1]
            return aTmpDict
        else:
            return def_list

    def transfer_building_info_to_worker(self):
        # transfer building info to worker instance
        if self.dlg.cb_buildingLayer.currentLayer() is None:
            self.worker.bLayer = QgsVectorLayer("Polygon", "notAvail", "memory")
        else:
            self.worker.bLayer = self.dlg.cb_buildingLayer.currentLayer()
        self.worker.bTop_UseCustom = self.dlg.chk_bTop.isChecked()
        if self.worker.bTop_UseCustom:
            self.worker.bTop = QgsField("notAvail", FIELD_TYPE_INT)
            self.worker.bTop_custom = self.dlg.se_bTop.value()
        else:
            self.worker.bTop = self.dlg.cb_bTop.currentField()
            self.worker.bTop_custom = C_NODATA_VALUE
        self.worker.bBot_UseCustom = self.dlg.chk_bBot.isChecked()
        if self.worker.bBot_UseCustom:
            self.worker.bBot = QgsField("notAvail", FIELD_TYPE_INT)
            self.worker.bBot_custom = self.dlg.se_bBot.value()
        else:
            self.worker.bBot = self.dlg.cb_bBot.currentField()
            self.worker.bBot_custom = C_NODATA_VALUE
        self.worker.bName_UseCustom = self.dlg.chk_bName.isChecked()
        if self.worker.bName_UseCustom:
            self.worker.bName = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.bName_custom = self.dlg.le_bName.text()
        else:
            self.worker.bName = self.dlg.cb_bName.currentField()
            self.worker.bName_custom = ""
        self.worker.bWall_UseCustom = self.dlg.chk_bWall.isChecked()
        if self.worker.bWall_UseCustom:
            self.worker.bWall = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.bWall_custom = self.dlg.le_bWall.text()
        else:
            self.worker.bWall = self.dlg.cb_bWall.currentField()
            self.worker.bWall_custom = "000000"
        self.worker.bRoof_UseCustom = self.dlg.chk_bRoof.isChecked()
        if self.worker.bRoof_UseCustom:
            self.worker.bRoof = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.bRoof_custom = self.dlg.le_bRoof.text()
        else:
            self.worker.bRoof = self.dlg.cb_bRoof.currentField()
            self.worker.bRoof_custom = "000000"
        self.worker.bGreenWall_UseCustom = self.dlg.chk_bGreenWall.isChecked()
        if self.worker.bGreenWall_UseCustom:
            self.worker.bGreenWall = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.bGreenWall_custom = self.dlg.le_bGreenWall.text()
        else:
            self.worker.bGreenWall = self.dlg.cb_bGreenWall.currentField()
            self.worker.bGreenWall_custom = ""
        self.worker.bGreenRoof_UseCustom = self.dlg.chk_bGreenRoof.isChecked()
        if self.worker.bGreenRoof_UseCustom:
            self.worker.bGreenRoof = QgsField("notAvail", FIELD_TYPE_STRING)
            self.worker.bGreenRoof_custom = self.dlg.le_bGreenRoof.text()
        else:
            self.worker.bGreenRoof = self.dlg.cb_bGreenRoof.currentField()
            self.worker.bGreenRoof_custom = ""
        self.worker.bBPS_disabled = self.dlg.chk_bBPS.isChecked()
        if self.worker.bBPS_disabled:
            self.worker.bBPS = QgsField("notAvail", FIELD_TYPE_STRING)
        else:
            self.worker.bBPS = self.dlg.cb_bBPS.currentField()
        # indoor climate (ENVI-met 6): an attribute field or a static value per setting
        self.worker.bIndoor = {}
        for key, name in self.INDOOR_WIDGETS:
            if getattr(self.dlg, f'chk_{name}').isChecked():
                self.worker.bIndoor[key] = (None, self.indoor_static_value(key, name))
            else:
                self.worker.bIndoor[key] = (getattr(self.dlg, f'cb_{name}').currentField() or None, '')
        self.worker.bSuppressACHeat = self.dlg.chk_bSuppressACHeat.isChecked()

    # setting of core.indoor -> widget name suffix on the Buildings > Indoor Climate page
    INDOOR_WIDGETS = (('use', 'bUse'), ('mode', 'bIndoorMode'), ('lower', 'bIndoorLower'),
                      ('upper', 'bIndoorUpper'), ('gain', 'bInternalGain'))

    def indoor_static_value(self, key, name):
        if key in ('use', 'mode'):
            # the user code of the entry, as it would be entered in an attribute field
            return core_indoor.USER_CODES[max(0, getattr(self.dlg, f'cmb_{name}').currentIndex())]
        return getattr(self.dlg, f'le_{name}').text().strip()

    def kill_worker(self):
        # method to kill/cancel the worker thread
        self.worker.stop()
        # see https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        try:  # to prevent a Python error when the cancel button has been clicked but no thread is running use try/except
            if self.thread.isRunning():  # check if a thread is running
                # print('pushed cancel, thread is running, trying to cancel') # debugging
                # self.thread.requestInterruption() # not sure how to actually use it as there are no examples to find anywhere, one somehow would need to listen to isInterruptionRequested()
                self.thread.exit()  # Tells the thread’s event loop to exit with a return code.
                self.thread.quit()  # Tells the thread’s event loop to exit with return code 0 (success). Equivalent to calling exit (0).
                self.thread.wait()  # Blocks the thread until https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html#PySide6.QtCore.PySide6.QtCore.QThread.wait
        except Exception:
            pass

    def startWorkerCalcVertExt(self):  # method to start the worker thread
        self.thread = QThread()
        self.worker = Worker()

        # here we transfer the GUI values to the worker
        if self.dlg.cb_subArea.currentLayer() is None:
            self.iface.messageBar().pushMessage("Error",
                                                "To get the highest structures (buildings and DEM) in the sub area, please select at least a sub area layer",
                                                level=Qgis.Warning)
            return
        self.worker.subAreaLayer = self.dlg.cb_subArea.currentLayer()
        self.worker.subAreaLayer_nonRot = self.dlg.cb_subArea.currentLayer()

        if not (self.dlg.cb_buildingLayer.currentLayer() is None):
            self.worker.bLayer = self.dlg.cb_buildingLayer.currentLayer()
        if not (self.dlg.cb_bTop.currentField() is None):
            self.worker.bTop = self.dlg.cb_bTop.currentField()

        if not (self.dlg.cb_buildingLayer.currentLayer() is None):
            self.worker.bLayer = self.dlg.cb_buildingLayer.currentLayer()
        if not (self.dlg.cb_bTop.currentField() is None):
            self.worker.bTop = self.dlg.cb_bTop.currentField()

        if not (self.dlg.cb_demLayer.currentLayer() is None):
            self.worker.dEMLayer = self.dlg.cb_demLayer.currentLayer()
        if not (self.dlg.cb_demBand.currentBand() is None):
            self.worker.dEMBand = self.dlg.cb_demBand.currentBand()

        self.worker.bTop_UseCustom = self.dlg.chk_bTop.isChecked()
        self.worker.bTop_custom = self.dlg.se_bTop.value()

        self.worker.dx = self.dlg.se_dx.value()
        self.worker.dy = self.dlg.se_dy.value()
        self.worker.dz = self.dlg.se_dz.value()
        self.worker.msg = ""

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(self.worker.calc_vert_ext)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()  # finally start the thread
        self.dlg.cb_subArea.setEnabled(False)  # disable the gui that fires these commands
        self.dlg.frm_vertExt.setEnabled(False)
        self.dlg.frm_horExt.setEnabled(False)
        self.dlg.bt_SaveINX.setEnabled(False)
        self.dlg.bt_SaveTo.setEnabled(False)
        self.dlg.gb_Geodata.setEnabled(False)

        # self.dlg.gb_Geodata.setEnabled(False)
        self.thread.finished.connect(
            self.updateCalcVertExt)  # update the model dimensions when thread has been finished

    def startWorkerPreviewdxyz(self):  # method to start the worker thread
        if self.dlg.cb_subArea.currentLayer() is None:
            return

        self.thread = QThread()
        self.worker = Worker()

        # disable the gui that triggers the events
        self.set_general_gridding_settings_ui(False)

        # here we transfer the GUI values to the worker
        self.worker.subAreaLayer = self.dlg.cb_subArea.currentLayer()
        self.worker.subAreaLayer_nonRot = self.dlg.cb_subArea.currentLayer()

        self.worker.dx = self.dlg.se_dx.value()
        self.worker.dy = self.dlg.se_dy.value()
        self.worker.dz = self.dlg.se_dz.value()
        self.worker.msg = ""

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(self.worker.previewdxy)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()  # finally start the thread
        self.thread.finished.connect(
            self.updatePreviewdxyz)  # update the model dimensions when thread has been finished

    def startWorkerPreviewdz(self):
        # method to start the worker thread
        if self.dlg.cb_subArea.currentLayer() is None:
            return

        self.thread = QThread()
        self.worker = Worker()

        # disable the gui that triggers the events
        self.set_general_gridding_settings_ui(False)

        # here we transfer the GUI values to the worker
        self.worker.subAreaLayer = self.dlg.cb_subArea.currentLayer()
        self.worker.subAreaLayer_nonRot = self.dlg.cb_subArea.currentLayer()

        self.worker.dx = self.dlg.se_dx.value()
        self.worker.dy = self.dlg.se_dy.value()
        self.worker.dz = self.dlg.se_dz.value()

        self.dlg.tb_zPreview.clear()
        self.worker.dz = self.dlg.se_dz.value()
        self.worker.KK = self.dlg.se_zGrids.value()
        self.worker.useSplitting = self.dlg.chk_useSplitting.isChecked()
        self.worker.useTelescoping = self.dlg.chk_useTelescoping.isChecked()
        self.worker.teleStart = self.dlg.se_teleStart.value()
        self.worker.teleStretch = self.dlg.se_teleStretch.value()

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots
        self.thread.started.connect(self.worker.previewdz)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()  # finally start the thread
        self.thread.finished.connect(self.updatePreviewdz)  # update the model dimensions when thread has been finished

    def set_general_gridding_settings_ui(self, bEnabled: bool):
        self.dlg.cb_subArea.setEnabled(bEnabled)

        self.dlg.bt_SaveINX.setEnabled(bEnabled)
        self.dlg.bt_SaveTo.setEnabled(bEnabled)

        self.dlg.se_dx.setEnabled(bEnabled)
        self.dlg.se_dy.setEnabled(bEnabled)
        self.dlg.se_dz.setEnabled(bEnabled)
        self.dlg.se_zGrids.setEnabled(bEnabled)
        self.dlg.se_teleStart.setEnabled(bEnabled)
        self.dlg.se_teleStretch.setEnabled(bEnabled)
        self.dlg.chk_useSplitting.setEnabled(bEnabled)
        self.dlg.chk_useTelescoping.setEnabled(bEnabled)

    def reportProgress(self, n):
        # method to report the progress to gui
        self.dlg.pb_main.setValue(n)

    def updateExport(self):
        # re-enable all gui
        self.dlg.bt_SaveINX.setEnabled(True)
        self.dlg.bt_SaveTo.setEnabled(True)
        self.dlg.gb_Geodata.setEnabled(True)

        self.iface.messageBar().pushMessage("Success", "Output file written at " + self.worker.filename,
                                            level=Qgis.Success, duration=5)
        for warning in self.worker.warnings:
            QgsMessageLog.logMessage(warning, 'ENVI-met', level=Qgis.MessageLevel.Warning)
            self.iface.messageBar().pushMessage("Warning", warning, level=Qgis.Warning)

    def updateCalcVertExt(self):
        self.dlg.l_highestStruct.setText(
            "Highest Structure (DEM + Building): " + str(self.worker.maxHeightTotal) + " m (Building = " + str(
                self.worker.maxHeightB) + " m, DEM = " + str(self.worker.maxHeightDEM) + " m)")
        self.dlg.cb_subArea.setEnabled(True)
        self.dlg.frm_vertExt.setEnabled(True)
        self.dlg.frm_horExt.setEnabled(True)
        self.dlg.gb_Geodata.setEnabled(True)
        self.startWorkerPreviewdxyz()

    def updatePreviewdxyz(self):
        self.dlg.l_xGrids.setText(
            "x-Dimension: " + str(self.worker.xMeters) + " m; number of x-Grids: " + str(self.worker.II))
        self.dlg.l_yGrids.setText(
            "y-Dimension: " + str(self.worker.yMeters) + " m; number of y-Grids: " + str(self.worker.JJ))
        if self.worker.msg != "":
            self.iface.messageBar().pushMessage(self.worker.msg.split(":")[0], self.worker.msg.split(":")[1], level=Qgis.Warning)
        # enable the gui that triggers the events
        self.set_general_gridding_settings_ui(True)
        self.startWorkerPreviewdz()

    def updatePreviewdz(self):
        for k in range(self.worker.finalKK):
            self.worker.zLvl_center[k] = self.worker.zLvl_bot[k] + 0.5 * self.worker.dzAr[k]
            zTop = self.worker.zLvl_center[k] + 0.5 * self.worker.dzAr[k]
            self.dlg.tb_zPreview.append(
                str(k + 1) + ": dz: " + str(round(self.worker.dzAr[k], 1)) + "m; z-Center: " + str(
                    round(self.worker.zLvl_center[k], 1)) + "m; z-Top: " + str(round(zTop, 1)) + "m")

        zMax_Top = self.worker.zLvl_center[self.worker.finalKK - 1] + 0.5 * self.worker.dzAr[self.worker.finalKK - 1]
        if zMax_Top < 2500:
            self.dlg.l_zHeight.setText("Resulting model height: " + str(round(zMax_Top, 2)) + " m")
        else:
            self.dlg.l_zHeight.setText(
                "Warning: Resulting model height too high (no more than 2500 m above ground level). Current setting: " + str(
                    round(zMax_Top, 2)) + " m")

        # enable the gui that triggers the events
        self.set_general_gridding_settings_ui(True)

    def select_output_file(self, filetype: str):
        if filetype == 'INX':
            filename, _filter = QFileDialog.getSaveFileName(
                self.dlg, "Select output file for ENVI-met model area", "", '*.INX')
            if filename != "":
                self.dlg.lineEdit.setText(filename)
        elif filetype == 'SIMX':
            filename, _filter = QFileDialog.getSaveFileName(
                self.dlg, "Select output file for ENVI-met simulation file", "", '*.SIMX')
            if filename != "":
                self.dlg.le_simxDest.setText(filename)
                self.dlg.lb_reportSave.setText('')

    def select_inx_input(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg, "Select ENVI-met model area for your simulation", "", '*.INX')
        if filename != "":
            filename = filename.rsplit('/', 1)[1]
            self.dlg.le_inxForSim.setText(filename)
            self.simsettings_change()

    def select_simx_to_load(self):
        filename = QFileDialog.getOpenFileName(
            self.dlg, "Select ENVI-met simulation file", "", '*.SIMX')
        # filename is a 2-tuple: tuple[0] is the filepath and tuple[1] is the filetype
        if filename[0] == "":
            self.dlg.lb_loadedSimx.setText("None")
        else:
            self.load_simx_file(filename[0])

    def load_simx_file(self, filepath):
        # JSON (ENVI-met 5.9 and newer) or XML. Settings the tab does not show are kept for saving.
        self.clear_settings_create_sim_tab()
        try:
            simulation, _ = core_simx.read(filepath)
            notes = simx_ui.ui_from_model(self.dlg, simulation, os.path.dirname(filepath))
            self.loaded_simx = simulation
            self.after_simx_import(filepath)
        except Exception as error:
            QgsMessageLog.logMessage(f"Loading {filepath} failed:\n{traceback.format_exc()}",
                                     'ENVI-met', level=Qgis.MessageLevel.Warning)
            self.clear_settings_create_sim_tab()
            self.dlg.tw_Main.setEnabled(True)
            self.iface.messageBar().pushMessage(
                "Error", f"Could not load the settings of this SIMX file ({type(error).__name__}: {error}).",
                level=Qgis.Warning)
            return
        for note in notes:
            self.iface.messageBar().pushMessage("Info", note, level=Qgis.Info)

    def after_simx_import(self, filename):
        # check mandatory sections
        self.simsettings_change()
        self.select_forcing_mode()
        # update UI meteo
        if self.dlg.rb_simpleForcing.isChecked():
            self.sifo_slider_update()
            self.update_temp_and_hum_simpleforcing()
        elif self.dlg.rb_fullForcing.isChecked():
            self.fufo_manual_settings_display()
        # update optional UI sections
        if self.dlg.chk_pollutantsSim.isChecked():
            self.pollutants_ui_update()
        self.update_simulation_type()
        # enable UI
        self.dlg.tw_Main.setEnabled(True)
        self.dlg.lb_loadedSimx.setText(filename)

    # ------------------------------------------------------------------ simulation type and modules
    def update_simulation_type(self):
        simx_ui.update_module_page(self.dlg)
        if simx_ui.is_module(self.dlg):
            self.update_module_status()
        else:
            self.dlg.cb_meteo.setText('Meteorology')
            self.select_forcing_mode()

    def update_module_status(self):
        """The Overview's status line for a module: ready, or what is missing."""
        if not simx_ui.is_module(self.dlg):
            return
        problems = simx_ui.module_problems(self.dlg)
        self.dlg.cb_meteo.setText('Module settings')
        self.dlg.lb_meteorology.setText(problems[0] if problems else 'Module selected')
        self.dlg.cb_meteo.setCheckState(Qt.CheckState.Unchecked if problems else Qt.CheckState.Checked)

    def add_solar_dates(self, dates):
        simx_ui.add_solar_dates(self.dlg, dates)
        self.update_module_status()

    def remove_solar_date(self):
        for item in self.dlg.lw_solarDates.selectedItems():
            self.dlg.lw_solarDates.takeItem(self.dlg.lw_solarDates.row(item))
        self.update_module_status()

    def select_module_fox(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg, "Select the meteorological data (FOX file) for the module", "", '*.FOX')
        if filename != "":
            self.dlg.le_moduleFox.setText(filename)

    def select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self.dlg, "Select output folder for simulation results")
        self.dlg.le_outputFolderSim.setText(folder)

    def select_fox_file(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg, "Select Full Forcing - file for your simulation", "", '*.FOX')
        if filename != "":
            self.dlg.le_selectedFOX.setText(filename)
            self.select_forcing_mode()

    def show_confi_dialog(self):
        dialog = QMessageBox()
        dialog.setText('Do you really want to clear all settings?')
        dialog.setWindowTitle('Confirmation required!')
        # scoped enums: PyQt6 (QGIS 4) has no QMessageBox.Yes etc.
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText("Yes")
        dialog.button(QMessageBox.StandardButton.No).setText("No")
        dialog.buttonClicked.connect(self.dialog_btn_clicked)
        dialog.exec()

    def dialog_btn_clicked(self, btn):
        if btn.text() == 'Yes':
            self.clear_settings_create_sim_tab()

    def save_definition(self, def_table):
        filename, _filter = QFileDialog.getSaveFileName(
            self.dlg, "Select output file for definition-file", "", '*.TXT')
        if filename != "":
            if os.path.isdir(filename.rsplit('/', 1)[0]):
                # get text from definitions text-edit
                defs = self.get_layer_definition(textEdit=def_table, asDict=False)
                with open(filename, 'w') as output_file:
                    for row in defs:
                        print(row, file=output_file)
                output_file.close()

    def load_definition(self, def_table):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg, "Select input file for definition-list", "", '*.TXT')
        if filename != "":
            if os.path.isfile(filename):
                file = open(filename, 'r')
                defs = file.readlines()
                file.close()
                def_table.setPlainText("".join(defs[0:]))

    def select_cb_buildingClick(self):
        layerFields = self.dlg.cb_buildingLayer.currentLayer()
        self.dlg.cb_bTop.setLayer(layerFields)
        self.dlg.cb_bBot.setLayer(layerFields)
        self.dlg.cb_bGreenRoof.setLayer(layerFields)
        self.dlg.cb_bGreenWall.setLayer(layerFields)
        self.dlg.cb_bWall.setLayer(layerFields)
        self.dlg.cb_bRoof.setLayer(layerFields)
        self.dlg.cb_bName.setLayer(layerFields)
        self.dlg.cb_bBPS.setLayer(layerFields)
        for _, name in self.INDOOR_WIDGETS:
            getattr(self.dlg, f'cb_{name}').setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_buildings)
        self.update_model_height_info()

    def select_cb_surfClick(self):
        layerFields = self.dlg.cb_surfLayer.currentLayer()
        self.dlg.cb_surfID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_surfaces)

    def select_cb_simplePlantClick(self):
        layerFields = self.dlg.cb_simplePlantLayer.currentLayer()
        self.dlg.cb_simplePlantID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_simpleplants)

    def select_cb_plant3dClick(self):
        layerFields = self.dlg.cb_plant3dLayer.currentLayer()
        self.dlg.cb_plant3dID.setLayer(layerFields)
        self.dlg.cb_plant3dAddOut.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_3dplants)

    def select_cb_demClick(self):
        layerFields = self.dlg.cb_demLayer.currentLayer()
        self.dlg.cb_demBand.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_dem)
        self.update_model_height_info()

    def select_cb_surfRasterClick(self):
        layerFields = self.dlg.cb_MapLayerRasterSurf.currentLayer()
        self.dlg.cb_RasterBandRasterSurf.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_surfaces)

    def select_cb_plant1dRasterClick(self):
        layerFields = self.dlg.cb_MapLayerRasterSP.currentLayer()
        self.dlg.cb_RasterBandRasterSP.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_simpleplants)

    def select_cb_recClick(self):
        layerFields = self.dlg.cb_recLayer.currentLayer()
        self.dlg.cb_recID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_receptors)

    def select_cb_srcPLayerClick(self):
        layerFields = self.dlg.cb_srcPLayer.currentLayer()
        self.dlg.cb_srcPID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_psrc)

    def select_cb_srcLLayerClick(self):
        layerFields = self.dlg.cb_srcLLayer.currentLayer()
        self.dlg.cb_srcLID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_lsrc)

    def select_cb_srcALayerClick(self):
        layerFields = self.dlg.cb_srcALayer.currentLayer()
        self.dlg.cb_srcAID.setLayer(layerFields)
        self.update_summary(self.dlg.cb_summary_asrc)

    def select_cb_bTopClick(self):
        self.update_summary(self.dlg.cb_summary_buildings)
        self.update_model_height_info()

    def update_model_height_info(self):
        tmp_subAreaLayer = self.dlg.cb_subArea.currentLayer()
        if tmp_subAreaLayer is not None:
            tmp_subAreaFeats = tmp_subAreaLayer.getFeatures()
            if tmp_subAreaFeats is not None:
                tmp_subAreaFeatCnt = sum(1 for _ in tmp_subAreaFeats)
                if tmp_subAreaFeatCnt == 1:
                    # updateCalcVertExt shows the heights when the worker has finished
                    self.startWorkerCalcVertExt()

    def select_cb_Output_SubArea(self):
        # check if this layer only contains one polygon feature
        tmp_subAreaLayer = self.dlg.cb_Output_SubArea.currentLayer()
        # count features in the vector layer -> check if there is only one
        if tmp_subAreaLayer is not None:
            tmp_subAreaFeats = tmp_subAreaLayer.getFeatures()
            if tmp_subAreaFeats is None:
                self.iface.messageBar().pushMessage("Error", "Selected sub area layer has no feature",
                                                    level=Qgis.Warning)
            else:
                # count the features in subArea-Layer
                tmp_subAreaFeatCnt = sum(1 for _ in tmp_subAreaFeats)
                if tmp_subAreaFeatCnt != 1:
                    self.iface.messageBar().pushMessage("Error",
                                                        "More than 1 feature in sub area layer - please use a layer "
                                                        "that contains only one polygon feature, this determines the "
                                                        "bounding box of your model area",
                                                        level=Qgis.Warning)
                else:
                    print(tmp_subAreaLayer)
                    dataseries.SelectedSubArea = tmp_subAreaLayer
        else:
            dataseries.SelectedSubArea = None

    def select_cb_subAreaClick(self):
        # check if this layer only contains one polygon feature
        tmp_subAreaLayer = self.dlg.cb_subArea.currentLayer()
        # count features in the vector layer -> check if there is only one
        if tmp_subAreaLayer is not None:
            tmp_subAreaFeats = tmp_subAreaLayer.getFeatures()
            if tmp_subAreaFeats is None:
                self.iface.messageBar().pushMessage("Error", "Selected sub area layer has no feature",
                                                    level=Qgis.Warning)
            else:
                # count the features in subArea-Layer
                tmp_subAreaFeatCnt = sum(1 for _ in tmp_subAreaFeats)
                if tmp_subAreaFeatCnt != 1:
                    self.iface.messageBar().pushMessage("Error",
                                                        "More than 1 feature in sub area layer - please use a layer "
                                                        "that contains only one polygon feature, this determines the "
                                                        "bounding box of your model area",
                                                        level=Qgis.Warning)
                else:
                    # now that we ensured that there is only one polygon in the layer, we can call the worker
                    # (this also calls the previewdxyz)
                    self.startWorkerCalcVertExt()
        else:
            self.iface.messageBar().pushMessage("Error", "Selected layer does not exist", level=Qgis.Warning)
        self.update_summary(self.dlg.cb_summary_gridding)

    def update_surrounding_page(self):
        """Border labels with the compass direction each border faces under the sub area's rotation."""
        use = self.dlg.chk_surroundingArea.isChecked()
        rotation = self.sub_area_rotation()
        labels = core_surrounding.border_labels(rotation)
        for border in core_surrounding.BORDERS:
            label = getattr(self.dlg, f'lb_border{border}')
            label.setText(labels[border])
            label.setEnabled(use)
            getattr(self.dlg, f'cb_border{border}').setEnabled(use)
        if rotation is None:
            text = 'Select a sub area to see which direction each border faces.'
        else:
            text = (f'The sub area is rotated by about {rotation:.0f}°; left, right, front and rear are the sides of '
                    f'the model grid, the labels show where they face.')
        self.dlg.lb_borderDirections.setText(text)

    def sub_area_rotation(self):
        """The model rotation the export will use (the bearing of the sub area's lower edge), or None."""
        layer = self.dlg.cb_subArea.currentLayer()
        if layer is None:
            return None
        try:
            for feature in layer.getFeatures():
                if not feature.hasGeometry():
                    continue
                # the export takes the edge from the first to the fourth vertex as the model's lower edge
                vertices = list(feature.geometry().vertices())
                if len(vertices) < 5:
                    return None
                distance = QgsDistanceArea()
                distance.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
                distance.setEllipsoid('WGS84')
                bearing = math.degrees(distance.bearing(QgsPointXY(vertices[0].x(), vertices[0].y()),
                                                        QgsPointXY(vertices[3].x(), vertices[3].y())))
                return core_surrounding.rotation_from_bearing(bearing)
        except Exception:       # an unusable layer or CRS: no directions, the export reports the problem
            return None
        return None

    def start_db_manager(self):
        if self.enviProjects is None:
            self.reload_db()
        filepath = self.enviProjects.installPath + "win64/DBManager.exe" if self.enviProjects is not None else ''
        if filepath and os.path.isfile(filepath):
            subprocess.Popen([filepath], cwd=os.path.dirname(filepath))
        else:
            self.iface.messageBar().pushMessage("Error",
                                                "Could not find a local ENVI-met installation / workspace to load "
                                                "database lookup",
                                                level=Qgis.Warning)

    def load_db(self):
        if (self.dlg.tw_Main.currentWidget().objectName() == "tab_DB") and not self.db_loaded:
            self.reload_db()

    def reload_db(self):
        self.db_loaded = True
        self.clear_db_tab(True)
        self.enviProjects = None
        self.enviProjects = EnviProjects()
        if self.enviProjects.usersettingsFound:
            # fill list-widget for projects with the project names
            [self.dlg.lw_prj.addItem(p.name) for p in self.enviProjects.projects]
        else:
            self.iface.messageBar().pushMessage("Error",
                                                "Could not find a local ENVI-met installation / workspace to load "
                                                "database lookup",
                                                level=Qgis.Warning)

    def update_db(self):
        self.clear_db_tab()
        if len(self.dlg.lw_prj.selectedItems()) > 0:
            for p in self.enviProjects.projects:
                if self.dlg.lw_prj.selectedItems()[0].text() == p.name:
                    # load database of selected project if it is not already loaded
                    if p.DB is None:
                        if p.useProjectDB and os.path.exists(p.projectPath + '/projectdatabase.edb'):
                            p.DB = ENVImetDB(filepath=self.enviProjects.sysDB_path, use_project_db=True,
                                             filepath_project_db=p.projectPath + '/projectdatabase.edb')
                        else:
                            p.DB = self.enviProjects.sys_db

                    # fill the other listWidgets
                    # Walls
                    [self.dlg.lw_wallsRoofs.addItem(wall.ID + '\t' + wall.Description) for wall in
                     p.DB.wall_dict.values()]
                    # Greening
                    [self.dlg.lw_greenings.addItem(greening.ID + '\t' + greening.Description) for greening in
                     p.DB.greening_dict.values()]
                    # Profiles
                    [self.dlg.lw_surfaces.addItem(surface.ID + '\t' + surface.Description) for surface in
                     p.DB.profile_dict.values()]
                    # SimplePlants
                    [self.dlg.lw_simplePlants.addItem(plant.ID + '\t' + plant.Description) for plant in
                     p.DB.plant_dict.values()]
                    # 3DPlants
                    [self.dlg.lw_3dPlants.addItem(plant.ID + '\t' + plant.Description) for plant in
                     p.DB.plant3d_dict.values()]
                    # Sources
                    [self.dlg.lw_sources.addItem(source.ID + '\t' + source.Description) for source in
                     p.DB.sources_dict.values()]
                    # Single-Walls
                    [self.dlg.lw_singlewalls.addItem(wall.ID + '\t' + wall.Description) for wall in
                     p.DB.singlewall_dict.values()]

                    break

    def clear_db_tab(self, clear_projects: bool = False):
        if clear_projects:
            self.dlg.lw_prj.clear()
        self.dlg.lw_wallsRoofs.clear()
        self.dlg.lw_greenings.clear()
        self.dlg.lw_surfaces.clear()
        self.dlg.lw_simplePlants.clear()
        self.dlg.lw_3dPlants.clear()
        self.dlg.lw_sources.clear()
        self.dlg.lw_singlewalls.clear()

    def run(self):
        """Run method that performs all the real work"""
        self.setup_user_interface()
        # show the dialog without blocking QGIS, so layers can be edited (e.g. analysis areas
        # digitised) while it is open
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def setup_user_interface(self):
        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start:
            self.first_start = False
            self.dlg = Geo2ENVImetDialog()
            self.dlg.scrollArea.setWidget(self.dlg.scrollAreaWidgetContents)

            self.setup_ui_export_layers_tab()
            self.setup_ui_create_sim_tab()
            self.setup_ui_load_results_tab()

    def setup_ui_load_results_tab(self):
        self.dlg.bt_selectSeriesA.clicked.connect(self.select_seriesA_folder)
        self.dlg.bt_selectSeriesB.clicked.connect(self.select_seriesB_folder)
        self.dlg.sb_height.valueChanged.connect(self.changeHeightValue)
        self.dlg.cb_dataLayers.currentIndexChanged.connect(self.changeSelectedVariable)
        self.dlg.cb_Output_SubArea.setShowCrs(True)
        self.dlg.cb_Output_SubArea.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_Output_SubArea.layerChanged.connect(self.select_cb_Output_SubArea)
        self.dlg.bt_Select_A.clicked.connect(self.Select_all_A)
        self.dlg.bt_Select_B.clicked.connect(self.Select_all_B)
        self.dlg.bt_Select_Delta.clicked.connect(self.Select_all_Delta)
        self.dlg.bt_addToMap.clicked.connect(self.add_to_map)
        self.dlg.chk_onlyComparable.clicked.connect(self.loadVariablesInUI)
        self.dlg.cb_sourceA.currentIndexChanged.connect(lambda: self.select_source('A'))
        self.dlg.cb_sourceB.currentIndexChanged.connect(lambda: self.select_source('B'))
        self.dlg.bt_areaStatistics.clicked.connect(self.open_area_statistics)

    def area_statistics_parameters(self):
        """Parameters for the area statistics algorithm from the series chosen in the tab."""
        parameters = {}
        for series, results, source in (('A', 'RESULTS', 'SOURCE'), ('B', 'RESULTS_B', 'SOURCE_B')):
            path_edit, source_box = self.series_widgets(series)
            if path_edit.text():
                parameters[results] = path_edit.text()
                parameters[source] = source_box.currentText()
        choice = dataseries.SelectedVariable
        if choice is not None and choice.key_a is not None:
            parameters['VARIABLES'] = choice.key_a
            if 'RESULTS_B' in parameters and choice.key_b is not None and choice.key_b != choice.key_a:
                parameters['VARIABLES_B'] = choice.key_b       # the same quantity under another name in B
        return parameters

    def open_area_statistics(self):
        import processing
        processing.execAlgorithmDialog('envimet:areastatistics', self.area_statistics_parameters())

    def Select_all_A(self):
        if self.dlg.bt_Select_A.text() == 'Select All':
            for i in range(self.dlg.lw_SeriesA.count()):
                if self.dlg.lw_SeriesA.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_SeriesA.item(i).setCheckState(Qt.CheckState.Checked)
            self.dlg.bt_Select_A.setText('Clear Selection')
        else:
            for i in range(self.dlg.lw_SeriesA.count()):
                if self.dlg.lw_SeriesA.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_SeriesA.item(i).setCheckState(Qt.CheckState.Unchecked)
            self.dlg.bt_Select_A.setText('Select All')

    def Select_all_B(self):
        if self.dlg.bt_Select_B.text() == 'Select All':
            for i in range(self.dlg.lw_SeriesB.count()):
                if self.dlg.lw_SeriesB.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_SeriesB.item(i).setCheckState(Qt.CheckState.Checked)
            self.dlg.bt_Select_B.setText('Clear Selection')
        else:
            for i in range(self.dlg.lw_SeriesB.count()):
                if self.dlg.lw_SeriesB.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_SeriesB.item(i).setCheckState(Qt.CheckState.Unchecked)
            self.dlg.bt_Select_B.setText('Select All')

    def Select_all_Delta(self):
        if self.dlg.bt_Select_Delta.text() == 'Select All':
            for i in range(self.dlg.lw_Delta.count()):
                if self.dlg.lw_Delta.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_Delta.item(i).setCheckState(Qt.CheckState.Checked)
            self.dlg.bt_Select_Delta.setText('Clear Selection')
        else:
            for i in range(self.dlg.lw_Delta.count()):
                if self.dlg.lw_Delta.item(i).flags() & QtCore.Qt.ItemFlag.ItemIsUserCheckable:
                    self.dlg.lw_Delta.item(i).setCheckState(Qt.CheckState.Unchecked)
            self.dlg.bt_Select_Delta.setText('Select All')

    def changeHeightValue(self):
        dataseries.SelectedHeight = self.dlg.sb_height.value()

    def changeSelectedVariable(self):
        # the item data is the VariableChoice; its text may contain parentheses
        dataseries.select_variable(self.dlg.cb_dataLayers.currentData())

    def select_seriesA_folder(self):
        folder = QFileDialog.getExistingDirectory(self.dlg, "Select input folder for Series A")
        self.load_series_folder(folder, 'A')

    def select_seriesB_folder(self):
        folder = QFileDialog.getExistingDirectory(self.dlg, "Select input folder for Series B")
        self.load_series_folder(folder, 'B')

    def series_widgets(self, series):
        if series == 'A':
            return self.dlg.le_seriesA_path, self.dlg.cb_sourceA
        return self.dlg.le_seriesB_path, self.dlg.cb_sourceB

    def load_series_folder(self, folder, series):
        """Find the result sources in ``folder`` and offer them in the series' source box."""
        path_edit, source_box = self.series_widgets(series)
        path_edit.setText(folder)
        names = dataseries.set_folder(folder, series)
        source_box.blockSignals(True)
        source_box.clear()
        source_box.addItems(names)
        source_box.blockSignals(False)
        if folder and not names:
            self.iface.messageBar().pushMessage(
                "Error", "No ENVI-met results (NetCDF or EDX/EDT files) found in " + folder, level=Qgis.Warning)
        self.report_source_errors(series)
        self.setupUI()

    def select_source(self, series):
        _, source_box = self.series_widgets(series)
        dataseries.select_source(source_box.currentText(), series)
        self.report_source_errors(series)
        self.setupUI()

    def report_source_errors(self, series):
        errors = dataseries.source_errors(series)
        if errors:
            QgsMessageLog.logMessage("Files that could not be read:\n" +
                                     "\n".join(f"{path}: {message}" for path, message in errors),
                                     'ENVI-met', level=Qgis.MessageLevel.Warning)
            self.iface.messageBar().pushMessage(
                "Warning", f"{len(errors)} file(s) of series {series} could not be read; see the ENVI-met log.",
                level=Qgis.Warning)

    def setupUI(self):
        dataseries.reset()
        self.dlg.sb_height.setValue(0.0)
        self.dlg.cb_Output_SubArea.setCurrentIndex(0)
        self.reset_progess_bar_add_to_map()
        self.fill_listWidgets()
        self.loadVariablesInUI()

    def loadVariablesInUI(self):
        self.dlg.cb_dataLayers.clear()
        for choice in dataseries.getVariablesAsList(self.dlg.chk_onlyComparable.isChecked()):
            self.dlg.cb_dataLayers.addItem(choice.text(), choice)

    def fill_listWidgets(self):
        # clear listWidgets
        self.dlg.lw_SeriesA.clear()
        self.dlg.lw_SeriesB.clear()
        self.dlg.lw_Delta.clear()
        # fill listWidgets with timesteps
        for i in range(len(dataseries.mergedList)):
            merged_tstp = dataseries.mergedList[i]
            # Create entry for listWidgetA
            item = QListWidgetItem()
            if merged_tstp.placeholderA:
                item.setText(' ')
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setText(merged_tstp.strDatetime)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.dlg.lw_SeriesA.addItem(item)

            # Create entry for listWidgetB
            item = QListWidgetItem()
            if merged_tstp.placeholderB:
                item.setText(' ')
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setText(merged_tstp.strDatetime)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.dlg.lw_SeriesB.addItem(item)

            # Create entry for Delta-listWidget
            item = QListWidgetItem()
            item.setText(' ')
            if merged_tstp.placeholderA or merged_tstp.placeholderB:
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsSelectable)
            else:
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsSelectable)
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.dlg.lw_Delta.addItem(item)

    def layer_requests(self):
        """LayerRequests for the time steps checked in the A, B and delta lists."""
        choice = dataseries.SelectedVariable
        if choice is None:
            return []
        state = choice.state
        height = self.dlg.sb_height.value()
        requests = []
        lists = (self.dlg.lw_SeriesA, self.dlg.lw_SeriesB, self.dlg.lw_Delta)
        # all three lists have one row per entry of the merged list
        for i, merged in enumerate(dataseries.mergedList):
            checked = [lw.item(i).checkState() == Qt.CheckState.Checked for lw in lists]
            merged.checkedA = checked[0] and not merged.placeholderA and state in (STATE_ONLY_A, STATE_COMPARABLE)
            merged.checkedB = checked[1] and not merged.placeholderB and state in (STATE_ONLY_B, STATE_COMPARABLE)
            merged.delta_checked = (checked[2] and not merged.placeholderA and not merged.placeholderB
                                    and state == STATE_COMPARABLE)
            a = None if merged.placeholderA else (merged.timestepA.path, merged.timestepA.index, choice.key_a)
            b = None if merged.placeholderB else (merged.timestepB.path, merged.timestepB.index, choice.key_b)
            if merged.checkedA:
                t = merged.timestepA
                requests.append(LayerRequest(choice.long_name, t.date, t.time, 'SeriesA', a=a, height=height))
            if merged.checkedB:
                t = merged.timestepB
                requests.append(LayerRequest(choice.long_name, t.date, t.time, 'SeriesB', b=b, height=height))
            if merged.delta_checked:
                t = merged.timestepB
                requests.append(LayerRequest(choice.long_name, t.date, t.time, 'Delta(A-B)', a=a, b=b,
                                             height=height))
        dataseries.CheckCount = len(requests)
        return requests

    def sub_area_cutline(self):
        """The selected sub-area polygon(s) as a Cutline, or None."""
        layer = dataseries.SelectedSubArea
        if layer is None:
            return None
        geometries = [f.geometry() for f in layer.getFeatures() if f.hasGeometry()]
        if not geometries:
            return None
        return Cutline(QgsGeometry.unaryUnion(geometries).asWkt(), layer.crs().toWkt())

    def add_to_map(self):
        requests = self.layer_requests()
        if not requests:
            return
        self.ui_upd_add_to_map(b=False)
        self.results_task = ResultLayersTask(requests, cutline=self.sub_area_cutline(),
                                             on_finished=self.after_add_to_map)
        self.results_task.progressChanged.connect(self.report_progress_add_to_map)
        QgsApplication.taskManager().addTask(self.results_task)

    def after_add_to_map(self, task):
        self.ui_upd_add_to_map(b=True)
        self.dlg.pb_addToMap.setValue(100)
        if task.errors:
            QgsMessageLog.logMessage("Layers that could not be made:\n" + "\n".join(task.errors),
                                     'ENVI-met', level=Qgis.MessageLevel.Warning)
            self.iface.messageBar().pushMessage(
                "Warning", f"{len(task.errors)} layer(s) could not be made; see the ENVI-met log.", level=Qgis.Warning)

    def report_progress_add_to_map(self, progress):
        self.dlg.pb_addToMap.setValue(int(progress))

    def reset_progess_bar_add_to_map(self):
        self.dlg.pb_addToMap.setValue(0)

    def ui_upd_add_to_map(self, b: bool):
        self.dlg.bt_addToMap.setEnabled(b)
        if not b:
            self.reset_progess_bar_add_to_map()

    def setup_ui_create_sim_tab(self):
        # this function setups the UI of the Create ENVI-met simulation tab

        # Overview tab
        # make status checkboxes of mandatory sections unclickable
        self.dlg.cb_generalSettings.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_generalSettings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_meteo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_meteo.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        simx_ui.setup_module_widgets(self.dlg)
        self.clear_settings_create_sim_tab()

        # connect events
        # an advanced settings tab is usable while its section is included (and no module is chosen)
        for check, _ in simx_ui.OPTIONAL_TABS:
            getattr(self.dlg, check).stateChanged.connect(lambda *_: simx_ui.update_optional_tabs(self.dlg))

        # simulation type and modules (ENVI-met 6)
        self.dlg.cb_simType.currentIndexChanged.connect(lambda *_: self.update_simulation_type())
        self.dlg.bt_addSolarDate.clicked.connect(
            lambda: self.add_solar_dates([self.dlg.de_solarDate.date().toString('dd.MM.yyyy')]))
        self.dlg.bt_addSolstices.clicked.connect(
            lambda: self.add_solar_dates(core_modules.solstices_and_equinoxes(self.dlg.de_solarDate.date().year())))
        self.dlg.bt_removeSolarDate.clicked.connect(self.remove_solar_date)
        self.dlg.bt_moduleFox.clicked.connect(self.select_module_fox)
        self.dlg.le_moduleFox.textChanged.connect(lambda *_: self.update_module_status())
        for box in (self.dlg.cb_statsStartMonth, self.dlg.cb_statsEndMonth, self.dlg.cb_statsStartHour,
                    self.dlg.cb_statsEndHour):
            box.currentIndexChanged.connect(lambda *_: self.update_module_status())

        self.dlg.bt_fileExpl.clicked.connect(lambda: self.select_output_file('SIMX'))
        self.dlg.bt_inxForSim.clicked.connect(self.select_inx_input)
        self.dlg.bt_loadSimSettings.clicked.connect(self.select_simx_to_load)
        self.dlg.bt_outputFolderSim.clicked.connect(self.select_output_folder)
        self.dlg.bt_loadFOX.clicked.connect(self.select_fox_file)
        self.dlg.bt_saveSimx.clicked.connect(self.save_simx_file)

        self.dlg.bt_clearCreateSimUI.clicked.connect(self.show_confi_dialog)

        self.dlg.bt_updateSF.clicked.connect(self.update_temp_and_hum_simpleforcing)

        self.dlg.rb_simpleForcing.clicked.connect(self.select_forcing_mode)
        self.dlg.rb_fullForcing.clicked.connect(self.select_forcing_mode)

        self.dlg.cb_naturalVentilation.currentIndexChanged.connect(self.update_indoor_page)
        self.dlg.cb_indoorMode.currentIndexChanged.connect(self.update_indoor_page)
        self.dlg.sb_indoorLower.valueChanged.connect(self.update_indoor_page)
        self.dlg.sb_indoorUpper.editingFinished.connect(self.update_indoor_page)

        self.dlg.calendar_startDateSim.selectionChanged.connect(self.update_date)

        self.dlg.le_fullSimName.editingFinished.connect(self.simsettings_change)
        self.dlg.le_inxForSim.editingFinished.connect(self.simsettings_change)
        self.dlg.le_selectedFOX.editingFinished.connect(self.select_forcing_mode)

        self.dlg.rb_forceWind_yes.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceWind_no.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceT_yes.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceT_no.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceRadC_yes.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceRadC_no.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceHum_yes.clicked.connect(self.fufo_manual_settings_display)
        self.dlg.rb_forceHum_no.clicked.connect(self.fufo_manual_settings_display)

        self.dlg.hs_maxT.valueChanged.connect(self.sifo_slider_update)
        self.dlg.hs_minT.valueChanged.connect(self.sifo_slider_update)
        self.dlg.hs_maxHum.valueChanged.connect(self.sifo_slider_update)
        self.dlg.hs_minHum.valueChanged.connect(self.sifo_slider_update)

        self.dlg.cb_userPolluType.currentIndexChanged.connect(self.pollutants_ui_update)

        # conncect buttons to run simulation
        self.dlg.bt_selectSIMX.clicked.connect(self.select_simx)
        self.dlg.bt_selectProj.clicked.connect(self.select_proj)
        self.dlg.bt_startSim.clicked.connect(self.start_sim)

    def select_proj(self):
        folder = QFileDialog.getExistingDirectory(
            self.dlg, "Select project folder for your ENVI-met simulation")
        if folder == '':
            self.dlg.lb_selected_projFolder.setText('None')
        else:
            self.dlg.lb_selected_projFolder.setText(folder)

    def start_sim(self):
        # check if a SIMX-file was selected by the user in UI
        if self.dlg.lb_simxFile.text() == 'None':
            self.iface.messageBar().pushMessage("Error", "No simulation-file selected", level=Qgis.Warning)
            return
        # check if a project folder was selected by the user in UI
        if self.dlg.lb_selected_projFolder.text() == 'None':
            self.iface.messageBar().pushMessage("Error", "No project-folder selected", level=Qgis.Warning)
            return

        # find the workspace and the installation from ENVI-met's user settings
        settings = envimet_install.read_usersettings()
        if (settings is None) or (settings.install_path == ''):
            self.iface.messageBar().pushMessage("Error", "No ENVI-met installation found!", level=Qgis.Warning)
            return
        if settings.workspace == '':
            self.iface.messageBar().pushMessage("Error", "No ENVI-met workspace found!", level=Qgis.Warning)
            return
        envicore_path = envimet_install.console_exe(settings.install_path)
        if not os.path.isfile(envicore_path):
            self.iface.messageBar().pushMessage("Error", f"ENVI-met console not found: {envicore_path}",
                                                level=Qgis.Warning)
            return

        # get selected project folder and simx-file
        projectFolder = self.dlg.lb_selected_projFolder.text().strip()
        simx_file = self.dlg.lb_simxFile.text().strip()

        # the project is found by the name in its project.infoX, not by its folder name
        my_project_name = envimet_install.read_project_name(projectFolder)
        if my_project_name == '':
            self.iface.messageBar().pushMessage("Error",
                                                "Could not find a project.infoX file inside folder. Are you sure the selected folder is a valid ENVI-met project-folder",
                                                level=Qgis.Warning)
            return
        if not envimet_install.is_inside(simx_file, projectFolder):
            self.iface.messageBar().pushMessage("Error",
                                                "The simulation-file (*.SIMX) is not inside the selected ENVI-met project-folder",
                                                level=Qgis.Warning)
            return
        if not envimet_install.is_inside(projectFolder, settings.workspace):
            self.iface.messageBar().pushMessage("Error",
                                                "The selected project-folder is not inside your ENVI-met workspace",
                                                level=Qgis.Warning)
            return

        # ENVI-met >= 5.9.5 takes -key=value arguments, older versions positional ones
        version = envimet_install.read_installed_version(settings.install_path)
        command = envimet_install.build_console_command(
            install_path=settings.install_path, workspace=settings.workspace, project_name=my_project_name,
            simx_file=envimet_install.relative_to(simx_file, projectFolder), version=version)
        if version is None:
            QgsMessageLog.logMessage("Could not read the ENVI-met version from sys.basedata/vctrl.edbx; "
                                     "starting the simulation with -key=value arguments.",
                                     'ENVI-met', level=Qgis.MessageLevel.Warning)
        version_text = 'unknown' if version is None else '.'.join(str(v) for v in version)
        QgsMessageLog.logMessage(f"Starting ENVI-met {version_text}: {subprocess.list2cmdline(command)}",
                                 'ENVI-met', level=Qgis.MessageLevel.Info)
        # ENVI-met opens a module's FOX file by the bare name in the SIMX, from the folder it runs in;
        # ENVI-guide keeps that file next to the SIMX
        run_folder = os.path.dirname(os.path.abspath(simx_file))
        try:
            if os.name == 'nt':  # Check if running on Windows
                subprocess.Popen(command, cwd=run_folder, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:  # Fallback for non-Windows environments
                subprocess.Popen(command, cwd=run_folder)
        except OSError as error:
            self.iface.messageBar().pushMessage("Error", f"Could not start ENVI-met: {error}", level=Qgis.Warning)

    def select_simx(self):
        filename = QFileDialog.getOpenFileName(
            self.dlg, "Select ENVI-met simulation file", "", '*.SIMX')
        # filename is a 2-tuple: tuple[0] is the filepath and tuple[1] is the filetype
        if filename[0] == "":
            self.dlg.lb_simxFile.setText("None")
        else:
            self.dlg.lb_simxFile.setText(filename[0])

    def save_simx_file(self):
        if not self.dlg.cb_generalSettings.isChecked():
            self.iface.messageBar().pushMessage("Error", "General Settings are not defined", level=Qgis.Warning)
            return
        module = simx_ui.simulation_type(self.dlg) if simx_ui.is_module(self.dlg) else None
        problems = simx_ui.module_problems(self.dlg) if module else []
        if problems:
            self.iface.messageBar().pushMessage("Error", problems[0], level=Qgis.Warning)
            return
        if not module and not self.dlg.cb_meteo.isChecked():
            self.iface.messageBar().pushMessage("Error", "Meteorology is not defined", level=Qgis.Warning)
            return
        if self.dlg.le_simxDest.text().isspace() or (self.dlg.le_simxDest.text() == ""):
            self.iface.messageBar().pushMessage("Error", "No output file location defined", level=Qgis.Warning)
            return

        # JSON for ENVI-met 5.9 and newer (and when no installation is found), XML for older versions
        version = self.installed_envimet_version()
        if module and version is not None and tuple(version) < core_modules.MIN_VERSION:
            self.iface.messageBar().pushMessage(
                "Error", "The simulation modules need ENVI-met 6.0 or newer; the installed version is "
                         + '.'.join(str(v) for v in version) + ".", level=Qgis.Warning)
            return
        json_format = core_simx.uses_json(version)
        path = self.dlg.le_simxDest.text().strip()
        try:
            fox_name = None
            if module in core_modules.FOX_MODULES:
                # ENVI-met opens the FOX by its bare name: keep a copy next to the SIMX, as ENVI-guide does
                fox_name = core_modules.fox_file_name(path, module)
                source = self.dlg.le_moduleFox.text().strip()
                target = os.path.join(os.path.dirname(os.path.abspath(path)), fox_name)
                if os.path.normcase(os.path.abspath(source)) != os.path.normcase(target):
                    shutil.copyfile(source, target)
            simulation = simx_ui.model_from_ui(self.dlg, base=self.loaded_simx, json_format=json_format,
                                               fox_name=fox_name)
            if json_format:
                core_simx.write_json(path, simulation)
            else:
                core_simx.write_xml(path, simulation, datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self.iface.messageBar().pushMessage("Error", f"The SIMX file could not be written: {error}",
                                                level=Qgis.Warning)
            return
        target = 'unknown ENVI-met version' if version is None else 'ENVI-met ' + '.'.join(str(v) for v in version)
        self.dlg.lb_reportSave.setText(f"SIMX-file saved ({'JSON' if json_format else 'XML'} format, {target})")

    @staticmethod
    def installed_envimet_version():
        """(major, minor, patch) of the ENVI-met installation in the user settings, or None."""
        settings = envimet_install.read_usersettings()
        if settings is None or not settings.install_path:
            return None
        return envimet_install.read_installed_version(settings.install_path)

    def update_indoor_page(self):
        simx_ui.update_indoor_page(self.dlg)

    def pollutants_ui_update(self):
        if (self.dlg.cb_userPolluType.currentIndex() == 1) or (self.dlg.cb_userPolluType.currentIndex() == 9):
            self.dlg.gb_additionalMyPollu.setVisible(True)
        else:
            self.dlg.gb_additionalMyPollu.setVisible(False)

    def sifo_slider_update(self):
        valMaxT = self.dlg.hs_maxT.value()
        valMinT = self.dlg.hs_minT.value()
        valMaxH = self.dlg.hs_maxHum.value()
        valMinH = self.dlg.hs_minHum.value()
        self.dlg.lb_maxT.setText(f"Max. Air Temperature: {valMaxT}°C")
        self.dlg.lb_minT.setText(f"Min. Air Temperature: {valMinT}°C")
        self.dlg.lb_maxHum.setText(f"Max. relative Humidity: {valMaxH}%")
        self.dlg.lb_minHum.setText(f"Min. relative Humidity: {valMinH}%")

    def fufo_manual_settings_display(self):
        if self.dlg.rb_forceWind_yes.isChecked():
            self.dlg.stackedWidget_4.setCurrentIndex(0)
        else:
            self.dlg.stackedWidget_4.setCurrentIndex(1)

        if self.dlg.rb_forceT_yes.isChecked():
            self.dlg.stackedWidget_6.setCurrentIndex(0)
        else:
            self.dlg.stackedWidget_6.setCurrentIndex(1)

        if self.dlg.rb_forceRadC_yes.isChecked():
            self.dlg.stackedWidget_5.setCurrentIndex(1)
        else:
            self.dlg.stackedWidget_5.setCurrentIndex(0)

        if self.dlg.rb_forceHum_yes.isChecked():
            self.dlg.stackedWidget_7.setCurrentIndex(1)
        else:
            self.dlg.stackedWidget_7.setCurrentIndex(0)

    def simsettings_change(self):
        if (self.dlg.le_inxForSim.text() != '') and not self.dlg.le_inxForSim.text().isspace():
            if (self.dlg.le_fullSimName.text() != '') and not self.dlg.le_fullSimName.text().isspace():
                self.dlg.lb_generalSettings.setText(self.generalSettings_states[2])
                self.dlg.cb_generalSettings.setCheckState(Qt.CheckState.Checked)
            else:
                self.dlg.lb_generalSettings.setText(self.generalSettings_states[1])
                self.dlg.cb_generalSettings.setCheckState(Qt.CheckState.Unchecked)
        else:
            self.dlg.lb_generalSettings.setText(self.generalSettings_states[0])
            self.dlg.cb_generalSettings.setCheckState(Qt.CheckState.Unchecked)

    def update_date(self):
        date = self.dlg.calendar_startDateSim.selectedDate()
        y = date.year()
        m = date.month()
        d = date.day()
        if d < 10:
            if m < 10:
                self.dlg.lb_selectedDateSim.setText(f"0{d}.0{m}.{y}")
            else:
                self.dlg.lb_selectedDateSim.setText(f"0{d}.{m}.{y}")
        else:
            if m < 10:
                self.dlg.lb_selectedDateSim.setText(f"{d}.0{m}.{y}")
            else:
                self.dlg.lb_selectedDateSim.setText(f"{d}.{m}.{y}")

    def select_forcing_mode(self):
        if self.dlg.rb_fullForcing.isChecked():
            # show page for full forcing
            self.dlg.stackedWidget_3.setCurrentIndex(1)
            if (self.dlg.le_selectedFOX.text() == '') or self.dlg.le_selectedFOX.text().isspace():
                self.dlg.lb_meteorology.setText(self.meteoSettings_states[1])
                self.dlg.cb_meteo.setCheckState(Qt.CheckState.Unchecked)
            else:
                self.dlg.lb_meteorology.setText(self.meteoSettings_states[2])
                self.dlg.cb_meteo.setCheckState(Qt.CheckState.Checked)
        else:
            # show page for simple forcing
            self.dlg.stackedWidget_3.setCurrentIndex(0)
            self.dlg.lb_meteorology.setText(self.meteoSettings_states[0])
            self.dlg.cb_meteo.setCheckState(Qt.CheckState.Checked)

    def clear_settings_create_sim_tab(self):
        # clears the settings in the Create ENVI-met simulation tab
        # disable optional tabs
        self.dlg.tab_Soil.setEnabled(False)
        self.dlg.tab_Radiation.setEnabled(False)
        self.dlg.tab_Buildings_2.setEnabled(False)
        self.dlg.tab_Pollutants.setEnabled(False)
        self.dlg.tab_Output.setEnabled(False)
        self.dlg.tab_Expert.setEnabled(False)

        # reset edit-fields to default values
        # Overview
        # Mandatory sections state
        self.dlg.cb_generalSettings.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.cb_meteo.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.lb_generalSettings.setText(self.generalSettings_states[0])
        self.dlg.lb_meteorology.setText(self.meteoSettings_states[0])
        # optional sections
        self.dlg.chk_soilSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.chk_radiationSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.chk_buildingsSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.chk_pollutantsSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.chk_outputSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.chk_expertSim.setCheckState(Qt.CheckState.Unchecked)
        self.dlg.tab_Soil.setEnabled(False)
        self.dlg.tab_Radiation.setEnabled(False)
        self.dlg.tab_Buildings_2.setEnabled(False)
        self.dlg.tab_Pollutants.setEnabled(False)
        self.dlg.tab_Expert.setEnabled(False)
        self.dlg.tab_Output.setEnabled(False)
        # file management
        self.dlg.le_simxDest.setText('')
        self.dlg.lb_loadedSimx.setText('None')
        self.dlg.lb_reportSave.setText('')

        # General Settings
        # Sim Date and Time
        date = datetime.now()
        iYear = int(date.strftime("%Y"))
        iMonth = int(date.strftime("%m"))
        iDay = int(date.strftime("%d"))
        self.dlg.lb_selectedDateSim.setText(date.strftime("%d.%m.%Y"))
        self.dlg.calendar_startDateSim.setSelectedDate(QDate(iYear, iMonth, iDay))
        self.dlg.te_startTimeSim.setTime(QTime(5, 0))
        self.dlg.sb_simDur.setValue(24)
        # Sim name
        self.dlg.le_fullSimName.setText('New Simulation')
        self.dlg.le_outputFolderSim.setText('')
        # model area
        self.dlg.le_inxForSim.setText('')
        # CPU
        self.dlg.rb_multiCore.setChecked(True)

        # Meteorology
        self.dlg.rb_simpleForcing.setChecked(True)
        self.dlg.stackedWidget_3.setCurrentIndex(0)
        # Simple Forcing
        self.dlg.sb_timeMaxT.setValue(16)
        self.dlg.sb_timeMinT.setValue(5)
        self.dlg.sb_timeMaxHum.setValue(4)
        self.dlg.sb_timeMinHum.setValue(16)
        self.dlg.hs_maxT.setValue(28)
        self.dlg.hs_minT.setValue(17)
        self.dlg.hs_maxHum.setValue(75)
        self.dlg.hs_minHum.setValue(43)
        self.update_temp_and_hum_simpleforcing()

        self.dlg.sb_windspeed.setValue(2.00)
        self.dlg.sb_winddir.setValue(90.00)
        self.dlg.sb_rlength.setValue(0.10)
        self.dlg.sb_lowclouds.setValue(0)
        self.dlg.sb_midclouds.setValue(0)
        self.dlg.sb_highclouds.setValue(0)

        self.dlg.tableWidget.horizontalHeader().setVisible(True)
        self.dlg.tableWidget.verticalHeader().setVisible(True)

        # Full Forcing
        self.dlg.le_selectedFOX.setText('')
        self.dlg.rb_forceWind_yes.setChecked(True)
        self.dlg.rb_forceT_yes.setChecked(True)
        self.dlg.rb_forceRadC_yes.setChecked(True)
        self.dlg.rb_forceHum_yes.setChecked(True)
        self.dlg.rb_forcePrec_no.setChecked(True)
        self.dlg.sb_constWS_FUFo.setValue(2.00)
        self.dlg.sb_constWD_FuFo.setValue(135.00)
        self.dlg.sb_rlength_FuFo.setValue(0.10)
        self.dlg.sb_initT.setValue(20.00)
        self.dlg.sb_lowclouds_2.setValue(0)
        self.dlg.sb_mediumclouds.setValue(0)
        self.dlg.sb_highclouds_2.setValue(0)
        self.dlg.sb_relHum.setValue(50.00)
        self.dlg.stackedWidget_4.setCurrentIndex(0)
        self.dlg.stackedWidget_5.setCurrentIndex(1)
        self.dlg.stackedWidget_6.setCurrentIndex(0)
        self.dlg.stackedWidget_7.setCurrentIndex(1)

        # Soil (ENVI-met 6: % of the usable field capacity; negative: % of the wilting point)
        self.dlg.sb_soilHumUpper.setValue(45.00)
        self.dlg.sb_soilHumMiddle.setValue(50.00)
        self.dlg.sb_soilHumLower.setValue(55.00)
        self.dlg.sb_soilHumBedrock.setValue(60.00)

        # Radiation
        self.dlg.cb_resIVS.setCurrentIndex(1)

        # Indoor climate (ENVI-met 6 defaults, as in ENVI-guide)
        defaults = simx_ui.INDOOR_DEFAULTS
        self.dlg.cb_naturalVentilation.setCurrentIndex(defaults['naturalVentilation'])
        self.dlg.cb_indoorMode.setCurrentIndex(defaults['indoorMode'])
        self.dlg.cb_indoorUse.setCurrentIndex(defaults['defaultBuildingUse'])
        self.dlg.sb_indoorLower.setValue(defaults['indoorLowerC'])
        self.dlg.sb_indoorUpper.setValue(defaults['indoorUpperC'])
        self.update_indoor_page()

        # Pollutants
        self.dlg.sb_NO.setValue(0.00)
        self.dlg.sb_NO2.setValue(0.00)
        self.dlg.sb_ozone.setValue(0.00)
        self.dlg.sb_PM10.setValue(0.00)
        self.dlg.sb_PM25.setValue(0.00)
        self.dlg.sb_userPollu.setValue(0.00)
        self.dlg.le_userPolluName.setText('My Pollutant')
        self.dlg.cb_userPolluType.setCurrentIndex(0)
        self.dlg.sb_praticleDia.setValue(10.00)
        self.dlg.sb_particleDens.setValue(1.00)
        self.dlg.gb_additionalMyPollu.setVisible(False)

        # Output
        self.dlg.cb_outputBldData.setCheckState(Qt.CheckState.Checked)
        self.dlg.cb_outputRadData.setCheckState(Qt.CheckState.Checked)
        self.dlg.cb_outputSoilData.setCheckState(Qt.CheckState.Checked)
        self.dlg.cb_outputVegData.setCheckState(Qt.CheckState.Checked)
        self.dlg.sb_outputIntRecBld.setValue(30)
        self.dlg.sb_outputIntOther.setValue(60)

        # Expert
        self.dlg.rb_threadingMain.setChecked(True)

        # Simulation type and Module page
        simx_ui.clear_module_page(self.dlg)

        # nothing loaded: a saved file only holds what the tab shows
        self.loaded_simx = None

        # trigger update event for meteo-settings
        self.update_simulation_type()

    def update_temp_and_hum_simpleforcing(self):
        # linear interpolation between the daily extremes; table row = hour, column 0 = T, 1 = rel. humidity
        try:
            temperature = diurnal_profile(self.dlg.sb_timeMinT.value(), self.dlg.sb_timeMaxT.value(),
                                          self.dlg.hs_minT.value(), self.dlg.hs_maxT.value())
            humidity = diurnal_profile(self.dlg.sb_timeMinHum.value(), self.dlg.sb_timeMaxHum.value(),
                                       self.dlg.hs_minHum.value(), self.dlg.hs_maxHum.value())
        except ValueError:
            self.iface.messageBar().pushMessage(
                "Error", "Simple forcing: the minimum and the maximum of air temperature and of humidity "
                         "must be at different times of day.", level=Qgis.Warning)
            return
        for hour in range(24):
            for column, values in ((0, temperature), (1, humidity)):
                item = QtWidgets.QTableWidgetItem(str(round(values[hour], 2)))
                self.dlg.tableWidget.setItem(hour, column, item)

    def setup_ui_export_layers_tab(self):
        # include coordinate-reference-system of a layer in the combo-box text
        self.dlg.cb_buildingLayer.setShowCrs(True)
        self.dlg.cb_surfLayer.setShowCrs(True)
        self.dlg.cb_simplePlantLayer.setShowCrs(True)
        self.dlg.cb_plant3dLayer.setShowCrs(True)
        self.dlg.cb_subArea.setShowCrs(True)
        self.dlg.cb_demLayer.setShowCrs(True)
        self.dlg.cb_recLayer.setShowCrs(True)
        self.dlg.cb_srcPLayer.setShowCrs(True)
        self.dlg.cb_srcLLayer.setShowCrs(True)
        self.dlg.cb_srcALayer.setShowCrs(True)
        self.dlg.cb_MapLayerRasterSurf.setShowCrs(True)
        self.dlg.cb_MapLayerRasterSP.setShowCrs(True)

        self.dlg.cb_buildingLayer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_surfLayer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_simplePlantLayer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_plant3dLayer.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.dlg.cb_subArea.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_demLayer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.dlg.cb_recLayer.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.dlg.cb_srcPLayer.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.dlg.cb_srcLLayer.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.dlg.cb_srcALayer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.dlg.cb_MapLayerRasterSurf.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.dlg.cb_MapLayerRasterSP.setFilters(QgsMapLayerProxyModel.RasterLayer)

        self.dlg.cb_bTop.setAllowEmptyFieldName(True)
        self.dlg.cb_bBot.setAllowEmptyFieldName(True)
        self.dlg.cb_bName.setAllowEmptyFieldName(True)
        self.dlg.cb_bWall.setAllowEmptyFieldName(True)
        self.dlg.cb_bRoof.setAllowEmptyFieldName(True)
        self.dlg.cb_bGreenWall.setAllowEmptyFieldName(True)
        self.dlg.cb_bGreenRoof.setAllowEmptyFieldName(True)
        self.dlg.cb_bBPS.setAllowEmptyFieldName(True)
        self.dlg.cb_surfID.setAllowEmptyFieldName(True)
        self.dlg.cb_simplePlantID.setAllowEmptyFieldName(True)
        self.dlg.cb_plant3dID.setAllowEmptyFieldName(True)
        self.dlg.cb_plant3dAddOut.setAllowEmptyFieldName(True)
        self.dlg.cb_recID.setAllowEmptyFieldName(True)
        self.dlg.cb_srcPID.setAllowEmptyFieldName(True)
        self.dlg.cb_srcLID.setAllowEmptyFieldName(True)
        self.dlg.cb_srcAID.setAllowEmptyFieldName(True)

        self.dlg.tb_zPreview.setReadOnly(True)

        self.dlg.cb_bTop.setFilters(
            QgsFieldProxyModel.Int | QgsFieldProxyModel.LongLong | QgsFieldProxyModel.Numeric)
        self.dlg.cb_bBot.setFilters(
            QgsFieldProxyModel.Int | QgsFieldProxyModel.LongLong | QgsFieldProxyModel.Numeric)
        self.dlg.cb_bName.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_bWall.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_bRoof.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_bGreenWall.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_bGreenRoof.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_bBPS.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_surfID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_simplePlantID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_plant3dID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_plant3dAddOut.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_recID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_srcPID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_srcLID.setFilters(QgsFieldProxyModel.String)
        self.dlg.cb_srcAID.setFilters(QgsFieldProxyModel.String)

        # indoor climate per building (ENVI-met 6); text and number fields both work
        self.dlg.cmb_bUse.addItems(core_indoor.USE_LABELS)
        self.dlg.cmb_bIndoorMode.addItems(core_indoor.MODE_LABELS)
        self.dlg.le_bIndoorLower.setValidator(QDoubleValidator(-50.0, 60.0, 2, self.dlg))
        self.dlg.le_bIndoorUpper.setValidator(QDoubleValidator(-50.0, 60.0, 2, self.dlg))
        self.dlg.le_bInternalGain.setValidator(QDoubleValidator(0.0, 1000.0, 2, self.dlg))
        for _, name in self.INDOOR_WIDGETS:
            getattr(self.dlg, f'cb_{name}').setAllowEmptyFieldName(True)
            getattr(self.dlg, f'cb_{name}').fieldChanged.connect(
                lambda *_: self.update_summary(self.dlg.cb_summary_buildings))
            getattr(self.dlg, f'chk_{name}').clicked.connect(
                lambda *_: self.update_summary(self.dlg.cb_summary_buildings))

        # surrounding area (ENVI-met 6)
        for border in core_surrounding.BORDERS:
            box = getattr(self.dlg, f'cb_border{border}')
            box.addItems(core_surrounding.TYPES)
            box.setCurrentIndex(core_surrounding.DEFAULT_TYPE)
        self.dlg.chk_surroundingArea.toggled.connect(lambda *_: self.update_surrounding_page())
        self.dlg.cb_subArea.layerChanged.connect(lambda *_: self.update_surrounding_page())
        self.update_surrounding_page()

        self.dlg.cb_buildingLayer.layerChanged.connect(self.select_cb_buildingClick)
        self.dlg.cb_surfLayer.layerChanged.connect(self.select_cb_surfClick)
        self.dlg.cb_simplePlantLayer.layerChanged.connect(self.select_cb_simplePlantClick)
        self.dlg.cb_plant3dLayer.layerChanged.connect(self.select_cb_plant3dClick)
        self.dlg.cb_demLayer.layerChanged.connect(self.select_cb_demClick)
        self.dlg.cb_MapLayerRasterSurf.layerChanged.connect(self.select_cb_surfRasterClick)
        self.dlg.cb_MapLayerRasterSP.layerChanged.connect(self.select_cb_plant1dRasterClick)

        self.dlg.cb_recLayer.layerChanged.connect(self.select_cb_recClick)
        self.dlg.cb_srcPLayer.layerChanged.connect(self.select_cb_srcPLayerClick)
        self.dlg.cb_srcLLayer.layerChanged.connect(self.select_cb_srcLLayerClick)
        self.dlg.cb_srcALayer.layerChanged.connect(self.select_cb_srcALayerClick)

        self.dlg.cb_subArea.layerChanged.connect(self.select_cb_subAreaClick)
        self.dlg.bt_SaveTo.clicked.connect(lambda: self.select_output_file(filetype='INX'))
        # previews start once the values have stopped changing, not on every step of a spin box
        self.preview_xy_timer = self.single_shot_timer(self.startWorkerPreviewdxyz)
        self.preview_z_timer = self.single_shot_timer(self.startWorkerPreviewdz)
        for widget in (self.dlg.se_dx, self.dlg.se_dy):
            widget.valueChanged.connect(lambda *_: self.preview_xy_timer.start())
        for widget in (self.dlg.se_dz, self.dlg.se_zGrids, self.dlg.se_teleStart, self.dlg.se_teleStretch):
            widget.valueChanged.connect(lambda *_: self.preview_z_timer.start())
        for widget in (self.dlg.chk_useSplitting, self.dlg.chk_useTelescoping):
            widget.stateChanged.connect(lambda *_: self.preview_z_timer.start())

        self.dlg.bt_SaveINX.clicked.connect(lambda: self.start_worker_inx())

        self.dlg.tw_Main.currentChanged.connect(self.load_db)
        self.dlg.lw_prj.itemSelectionChanged.connect(self.update_db)
        self.dlg.bt_updateDB.clicked.connect(self.reload_db)
        self.dlg.bt_startDBManager.clicked.connect(self.start_db_manager)

        self.dlg.rb_surfVector.clicked.connect(self.select_surface_source)
        self.dlg.rb_surfRaster.clicked.connect(self.select_surface_source)
        self.dlg.bt_saveDefSurf.clicked.connect(lambda: self.save_definition(self.dlg.te_defineRasterVals))
        self.dlg.bt_loadDefSurf.clicked.connect(lambda: self.load_definition(self.dlg.te_defineRasterVals))

        self.dlg.rb_simplePlantsVector.clicked.connect(self.select_plants1d_source)
        self.dlg.rb_simplePlantsRaster.clicked.connect(self.select_plants1d_source)
        self.dlg.bt_saveDefSP.clicked.connect(lambda: self.save_definition(self.dlg.te_defineRasterValsSP))
        self.dlg.bt_loadDefSP.clicked.connect(lambda: self.load_definition(self.dlg.te_defineRasterValsSP))

        # connect other UI-elements for summary
        # buildings:
        self.dlg.cb_bTop.fieldChanged.connect(self.select_cb_bTopClick)
        self.dlg.cb_bBot.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bGreenRoof.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bGreenWall.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bWall.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bRoof.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bName.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.cb_bBPS.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bTop.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bBot.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bGreenRoof.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bGreenWall.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bWall.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bRoof.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bName.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        self.dlg.chk_bBPS.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_buildings))
        # surfaces:
        self.dlg.cb_surfID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_surfaces))
        self.dlg.chk_surf.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_surfaces))
        # simple plants:
        self.dlg.cb_simplePlantID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_simpleplants))
        self.dlg.chk_simplePlantID.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_simpleplants))
        # 3d-plants
        self.dlg.cb_plant3dID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_3dplants))
        self.dlg.cb_plant3dAddOut.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_3dplants))
        self.dlg.chk_plant3d.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_3dplants))
        self.dlg.chk_plant3dAddOut.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_3dplants))
        # sources
        self.dlg.cb_srcPID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_psrc))
        self.dlg.chk_srcPID.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_psrc))
        self.dlg.cb_srcLID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_lsrc))
        self.dlg.chk_srcLID.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_lsrc))
        self.dlg.cb_srcAID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_asrc))
        self.dlg.chk_srcAID.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_asrc))
        # receptors
        self.dlg.cb_recID.fieldChanged.connect(lambda: self.update_summary(self.dlg.cb_summary_receptors))
        self.dlg.chk_recID.clicked.connect(lambda: self.update_summary(self.dlg.cb_summary_receptors))

        # make all summary-checkBoxes read-only. Since there is no read-only property we need to disable mouse-
        # and tab-events for each summary-checkBox
        self.dlg.cb_summary_gridding.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_gridding.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_buildings.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_buildings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_dem.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_dem.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_surfaces.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_surfaces.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_asrc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_asrc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_lsrc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_lsrc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_psrc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_psrc.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_3dplants.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_3dplants.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_receptors.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_receptors.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.dlg.cb_summary_simpleplants.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_simpleplants.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    PREVIEW_DELAY_MS = 400

    def single_shot_timer(self, slot):
        timer = QTimer(self.dlg)
        timer.setSingleShot(True)
        timer.setInterval(self.PREVIEW_DELAY_MS)
        timer.timeout.connect(lambda: self.when_no_worker_runs(slot, timer))
        return timer

    def when_no_worker_runs(self, slot, timer):
        """Run ``slot`` unless a worker thread is busy; then try again later."""
        try:
            busy = self.thread is not None and self.thread.isRunning()
        except RuntimeError:        # the thread object has been deleted: nothing runs
            busy = False
        if busy:
            timer.start()
        else:
            slot()

    def select_surface_source(self):
        if self.dlg.rb_surfVector.isChecked():
            # show page for vector input
            self.dlg.stackedWidget.setCurrentIndex(0)
        else:
            # rb_surfRaster is checked
            # show page for raster input
            self.dlg.stackedWidget.setCurrentIndex(1)
        self.update_summary(self.dlg.cb_summary_surfaces)

    def select_plants1d_source(self):
        if self.dlg.rb_simplePlantsVector.isChecked():
            # show page for vector input
            self.dlg.stackedWidget_2.setCurrentIndex(0)
        else:
            # rb_simplePlantsRaster is checked
            # show page for raster input
            self.dlg.stackedWidget_2.setCurrentIndex(1)
        self.update_summary(self.dlg.cb_summary_simpleplants)

    def update_summary(self, summary_checkBox):
        if summary_checkBox == self.dlg.cb_summary_gridding:
            if self.dlg.cb_subArea.currentLayer() is None:
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_buildings:
            if (self.dlg.cb_buildingLayer.currentLayer() is None) \
                    or ((self.dlg.cb_bTop.currentField() == "") and not (self.dlg.chk_bTop.isChecked())) \
                    or ((self.dlg.cb_bBot.currentField() == "") and not (self.dlg.chk_bBot.isChecked())) \
                    or ((self.dlg.cb_bGreenRoof.currentField() == "") and not (self.dlg.chk_bGreenRoof.isChecked())) \
                    or ((self.dlg.cb_bGreenWall.currentField() == "") and not (self.dlg.chk_bGreenWall.isChecked())) \
                    or ((self.dlg.cb_bWall.currentField() == "") and not (self.dlg.chk_bWall.isChecked())) \
                    or ((self.dlg.cb_bRoof.currentField() == "") and not (self.dlg.chk_bRoof.isChecked())) \
                    or ((self.dlg.cb_bName.currentField() == "") and not (self.dlg.chk_bName.isChecked())) \
                    or ((self.dlg.cb_bBPS.currentField() == "") and not (self.dlg.chk_bBPS.isChecked())) \
                    or any(getattr(self.dlg, f'cb_{name}').currentField() == ""
                           and not getattr(self.dlg, f'chk_{name}').isChecked() for _, name in self.INDOOR_WIDGETS):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_surfaces:
            if (self.dlg.rb_surfRaster.isChecked() and (self.dlg.cb_MapLayerRasterSurf.currentLayer() is None)) or (self.dlg.rb_surfVector.isChecked() and (self.dlg.cb_surfLayer.currentLayer() is None or ((self.dlg.cb_surfID.currentField() == "") and not (self.dlg.chk_surf.isChecked())))):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_simpleplants:
            if (self.dlg.rb_simplePlantsRaster.isChecked() and self.dlg.cb_MapLayerRasterSP.currentLayer() is None) or (self.dlg.rb_simplePlantsVector.isChecked() and (self.dlg.cb_simplePlantLayer.currentLayer() is None or (self.dlg.cb_simplePlantID.currentField() == "") and not (self.dlg.chk_simplePlantID.isChecked()))):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_asrc:
            if (self.dlg.cb_srcALayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcAID.currentField() == "") and not (self.dlg.chk_srcAID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_lsrc:
            if (self.dlg.cb_srcLLayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcLID.currentField() == "") and not (self.dlg.chk_srcLID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_psrc:
            if (self.dlg.cb_srcPLayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcPID.currentField() == "") and not (self.dlg.chk_srcPID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_3dplants:
            if (self.dlg.cb_plant3dLayer.currentLayer() is None) \
                    or ((self.dlg.cb_plant3dID.currentField() == "") and not (self.dlg.chk_plant3d.isChecked())) \
                    or (
                    (self.dlg.cb_plant3dAddOut.currentField() == "") and not (self.dlg.chk_plant3dAddOut.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_dem:
            if self.dlg.cb_demLayer.currentLayer() is None:
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
        elif summary_checkBox == self.dlg.cb_summary_receptors:
            if (self.dlg.cb_recLayer.currentLayer() is None) \
                    or ((self.dlg.cb_recID.currentField() == "") and not (self.dlg.chk_recID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.CheckState.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.CheckState.Checked)
