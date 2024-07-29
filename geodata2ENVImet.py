from logging import info

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant, QThread, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QProgressBar
from qgis.core import QgsProject, Qgis, QgsField, QgsMapLayerProxyModel, QgsPoint, QgsVectorLayer, QgsRectangle, \
    QgsFeatureRequest, QgsFieldProxyModel, QgsMessageLog, QgsRasterLayer, QgsSettings
from qgis.PyQt.QtCore import *

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .geodata2ENVImet_dialog import Geo2ENVImetDialog
import os.path
from .ENVImet_DB_loader import *
from .Worker import *
from .EDX_EDT import *
from datetime import datetime
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMessageBox
import os
import subprocess


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
        # initialize locale
        try:
            locale = QgsSettings().value("locale/userLocale")
            if not locale:
                locale = QLocale().name()
            locale = locale[0:2]

            locale_path = os.path.join(self.plugin_dir, "i18n", "Geo2ENVImet_{}.qm".format(locale))

            if os.path.exists(locale_path):
                self.translator = QTranslator()
                self.translator.load(locale_path)

                if qVersion() > "4.3.3":
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

        # status states
        self.generalSettings_states = ('No model area (*.INX) selected!', 'Invalid simulation name!', '')
        self.meteoSettings_states = ('Simple Forcing selected', 'Full Forcing selected - FOX-file missing',
                                     'Full Forcing selected', 'Open/Cyclic selected')

        # data to load edt/edx-files
        self.edt_filenames = []
        self.edt_data = []

        self.edx_file = None

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

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
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

        if self.dlg.cb_subArea.currentLayer() is None:
            self.iface.messageBar().pushMessage("Error", "Please first select a sub area!", level=Qgis.Warning)
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
            self.worker.srcPID = QgsField("notAvail", QVariant.String)
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
            self.worker.srcLID = QgsField("notAvail", QVariant.String)
            self.worker.srcLID_custom = self.dlg.le_srcL.text()
            # print("Custom ID set to: " + self.worker.srcLID_custom)
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
            self.worker.srcAID = QgsField("notAvail", QVariant.String)
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
            self.worker.recID = QgsField("notAvail", QVariant.String)
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

    def transfer_3dplant_info_to_worker(self):
        # transfer 3d plant info
        if self.dlg.cb_plant3dLayer.currentLayer() is None:
            self.worker.plant3dLayer = QgsVectorLayer("Point", "notAvail", "memory")
        else:
            self.worker.plant3dLayer = self.dlg.cb_plant3dLayer.currentLayer()
        self.worker.plant3dID_UseCustom = self.dlg.chk_plant3d.isChecked()
        if self.worker.plant3dID_UseCustom:
            self.worker.plant3dID = QgsField("notAvail", QVariant.String)
            self.worker.plant3dID_custom = self.dlg.le_plant3d.text()
        else:
            self.worker.plant3dID = self.dlg.cb_plant3dID.currentField()
            self.worker.plant3dID_custom = "notAvail"
        self.worker.plant3dAddOut_disabled = self.dlg.chk_plant3dAddOut.isChecked()
        if self.worker.plant3dAddOut_disabled:
            self.worker.plant3dAddOut = QgsField("notAvail", QVariant.String)
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
                self.worker.plant1dID = QgsField("notAvail", QVariant.String)
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
                self.worker.surfID = QgsField("notAvail", QVariant.String)
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
            self.worker.bTop = QgsField("notAvail", QVariant.Int)
            self.worker.bTop_custom = self.dlg.se_bTop.value()
        else:
            self.worker.bTop = self.dlg.cb_bTop.currentField()
            self.worker.bTop_custom = -999
        self.worker.bBot_UseCustom = self.dlg.chk_bBot.isChecked()
        if self.worker.bBot_UseCustom:
            self.worker.bBot = QgsField("notAvail", QVariant.Int)
            self.worker.bBot_custom = self.dlg.se_bBot.value()
        else:
            self.worker.bBot = self.dlg.cb_bBot.currentField()
            self.worker.bBot_custom = -999
        self.worker.bName_UseCustom = self.dlg.chk_bName.isChecked()
        if self.worker.bName_UseCustom:
            self.worker.bName = QgsField("notAvail", QVariant.String)
            self.worker.bName_custom = self.dlg.le_bName.text()
        else:
            self.worker.bName = self.dlg.cb_bName.currentField()
            self.worker.bName_custom = ""
        self.worker.bWall_UseCustom = self.dlg.chk_bWall.isChecked()
        if self.worker.bWall_UseCustom:
            self.worker.bWall = QgsField("notAvail", QVariant.String)
            self.worker.bWall_custom = self.dlg.le_bWall.text()
        else:
            self.worker.bWall = self.dlg.cb_bWall.currentField()
            self.worker.bWall_custom = "000000"
        self.worker.bRoof_UseCustom = self.dlg.chk_bRoof.isChecked()
        if self.worker.bRoof_UseCustom:
            self.worker.bRoof = QgsField("notAvail", QVariant.String)
            self.worker.bRoof_custom = self.dlg.le_bRoof.text()
        else:
            self.worker.bRoof = self.dlg.cb_bRoof.currentField()
            self.worker.bRoof_custom = "000000"
        self.worker.bGreenWall_UseCustom = self.dlg.chk_bGreenWall.isChecked()
        if self.worker.bGreenWall_UseCustom:
            self.worker.bGreenWall = QgsField("notAvail", QVariant.String)
            self.worker.bGreenWall_custom = self.dlg.le_bGreenWall.text()
        else:
            self.worker.bGreenWall = self.dlg.cb_bGreenWall.currentField()
            self.worker.bGreenWall_custom = ""
        self.worker.bGreenRoof_UseCustom = self.dlg.chk_bGreenRoof.isChecked()
        if self.worker.bGreenRoof_UseCustom:
            self.worker.bGreenRoof = QgsField("notAvail", QVariant.String)
            self.worker.bGreenRoof_custom = self.dlg.le_bGreenRoof.text()
        else:
            self.worker.bGreenRoof = self.dlg.cb_bGreenRoof.currentField()
            self.worker.bGreenRoof_custom = ""
        self.worker.bBPS_disabled = self.dlg.chk_bBPS.isChecked()
        if self.worker.bBPS_disabled:
            self.worker.bBPS = QgsField("notAvail", QVariant.String)
        else:
            self.worker.bBPS = self.dlg.cb_bBPS.currentField()

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
        except:
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

        self.worker.dx = self.dlg.se_dx.value()
        self.worker.dy = self.dlg.se_dy.value()
        self.worker.dz = self.dlg.se_dz.value()

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
        # Connect signals and slots:
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
        # self.dlg.gb_Geodata.setEnabled(bEnabled)

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
            self.clear_settings_create_sim_tab()

            self.thread = QThread()
            self.worker = Worker()

            # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
            # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
            self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
            # Connect signals and slots:
            self.thread.started.connect(lambda: self.worker.load_simx(ui=self.dlg, filepath=filename[0]))
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)

            # disable GUI
            self.dlg.tw_Main.setEnabled(False)
            # enable GUI, when done
            self.thread.finished.connect(lambda: self.after_simx_import(filename[0]))

            self.thread.start()  # finally start the thread

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
        if self.dlg.chk_radiationSim.isChecked():
            self.radiation_ui_update()
        if self.dlg.chk_pollutantsSim.isChecked():
            self.pollutants_ui_update()
        if self.dlg.chk_outputSim.isChecked():
            self.output_ui_update()
        # enable UI
        self.dlg.tw_Main.setEnabled(True)
        self.dlg.lb_loadedSimx.setText(filename)

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
        dialog.setIcon(QMessageBox.Warning)
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.button(QMessageBox.Yes).setText("Yes")
        dialog.button(QMessageBox.No).setText("No")
        dialog.buttonClicked.connect(self.dialog_btn_clicked)
        dialog.exec_()

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
                    self.startWorkerCalcVertExt()
                    self.dlg.l_highestStruct.setText("Highest Structure (DEM + Building): " + str(
                        self.worker.maxHeightTotal) + " m (Building = " + str(
                        self.worker.maxHeightB) + " m, DEM = " + str(self.worker.maxHeightDEM) + " m)")

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
                                                        "More than 1 feature in sub area layer - please use a layer that contains only one polygon feature, this determines the bounding box of your model area",
                                                        level=Qgis.Warning)
                else:
                    # now that we ensured that there is only one polygon in the layer, we can call the worker (this also calls the previewdxyz)
                    self.startWorkerCalcVertExt()
        else:
            self.iface.messageBar().pushMessage("Error", "Selected layer does not exist", level=Qgis.Warning)
        self.update_summary(self.dlg.cb_summary_gridding)

    def start_db_manager(self):
        if self.enviProjects is not None:
            filepath = self.enviProjects.installPath + "win64/DBManager.exe"
            process_id = os.spawnv(os.P_NOWAIT, filepath, ["-someFlag", "someOtherFlag"])
        else:
            self.iface.messageBar().pushMessage("Error",
                                                "Could not find a local ENVI-met installation / workspace to load database lookup",
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
                                                "Could not find a local ENVI-met installation / workspace to load database lookup",
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
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        self.dlg.exec_()

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
        self.dlg.lw_edt_files.clear()
        self.dlg.cb_dataLayers.clear()
        self.dlg.cb_dataLayers.currentIndexChanged.connect(self.reset_progress_bars_sim_results)
        self.dlg.bt_selectEDT.clicked.connect(self.select_result_files)
        self.dlg.bt_loadResults.clicked.connect(self.load_simulation_data)
        self.dlg.bt_addToMap.clicked.connect(self.add_to_map)
        self.dlg.bt_clearSelection.clicked.connect(self.clear_selection_load_data)
        self.dlg.sb_zLevel.valueChanged.connect(self.z_lvl_changed)

    def z_lvl_changed(self):
        self.calc_height()
        self.reset_progress_bars_sim_results()

    def calc_height(self):
        z_lvl = self.dlg.sb_zLevel.value()
        if self.edx_file is not None:
            if z_lvl > (len(self.edx_file.spacing_z) - 1):
                self.dlg.sb_zLevel.setValue((len(self.edx_file.spacing_z) - 1))
            else:
                # add one because list slicing End-index is exclusive
                s = round(sum(self.edx_file.spacing_z[0:(z_lvl + 1)]) - (self.edx_file.spacing_z[z_lvl] / 2), 2)
                self.dlg.l_heightInMeter.setText("Height in meter: " + str(s) + " m")
        else:
            self.dlg.l_heightInMeter.setText("Height in meter: 0 m")

    def clear_selection_load_data(self):
        self.dlg.lw_edt_files.clear()
        self.dlg.cb_dataLayers.clear()
        self.edt_filenames.clear()
        self.edx_file = None
        self.dlg.sb_zLevel.setValue(0)
        self.dlg.le_nameLayers.setText('')
        self.reset_progress_bars_sim_results()

    def select_result_files(self):
        filenames = QFileDialog.getOpenFileNames(
            self.dlg, "Select ENVI-met simulation results", "", '*.EDT')
        if len(filenames[0]) != 0:
            self.dlg.lw_edt_files.clear()
            self.edt_filenames.clear()
            for edt in filenames[0]:
                self.edt_filenames.append(edt)
                self.dlg.lw_edt_files.addItem(edt)
            self.edx_file = EDX(filepath=f'{self.edt_filenames[0].rsplit(".", 1)[0]}.edx')
            self.dlg.cb_dataLayers.clear()
            for name in self.edx_file.name_variables:
                # 1st var: index. If index is greater than the length of the item-list, the new items gets appended
                self.dlg.cb_dataLayers.insertItem(999999, name)
            self.reset_progress_bars_sim_results()
            if self.edx_file.data_per_variable > 1:
                self.iface.messageBar().pushMessage("Error", "Please select output files with only scalar values.",
                                                    level=Qgis.Warning)
                self.clear_selection_load_data()

    def add_to_map(self):
        self.thread = QThread()
        self.worker = Worker()

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        user_name = self.dlg.le_nameLayers.text()
        var_selected = self.dlg.cb_dataLayers.itemText(self.dlg.cb_dataLayers.currentIndex())
        interpolRes_usr = self.dlg.sb_interpolRes.value()
        if user_name == '':
            var_name = var_selected
        else:
            var_name = user_name + '_' + var_selected
        if self.dlg.rb_onlyLoad.isChecked():
            self.thread.started.connect(lambda: self.worker.add_layers_to_map(edt_list=self.edt_data, var_name=var_name,
                                                                              only_load_data=True,
                                                                              load_and_rotate_data=False,
                                                                              interpolate_data=False))
        elif self.dlg.rb_loadAndRotate.isChecked():
            self.thread.started.connect(lambda: self.worker.add_layers_to_map(edt_list=self.edt_data, var_name=var_name,
                                                                              only_load_data=False,
                                                                              load_and_rotate_data=True,
                                                                              interpolate_data=False))
        elif self.dlg.rb_loadRotateInterpolate.isChecked():
            self.thread.started.connect(lambda: self.worker.add_layers_to_map(edt_list=self.edt_data, var_name=var_name,
                                                                              only_load_data=False,
                                                                              load_and_rotate_data=True,
                                                                              interpolate_data=True,
                                                                              interpol_res=interpolRes_usr))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # disable GUI
        self.ui_upd_edt_load(b=False, result_data=False)
        # enable GUI, when done
        self.worker.progress.connect(self.report_progress_add_to_map)
        self.thread.finished.connect(lambda: self.ui_upd_edt_load(b=True, result_data=False))

        self.thread.start()  # finally start the thread

    def load_simulation_data(self):
        zlvl = int(self.dlg.sb_zLevel.value())
        var = self.dlg.cb_dataLayers.itemText(self.dlg.cb_dataLayers.currentIndex())

        self.edt_data.clear()
        self.thread = QThread()
        self.worker = Worker()

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(
            lambda: self.worker.load_simulation_data(edt_filenames=self.edt_filenames, var_name=var, z=zlvl))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # disable GUI
        self.ui_upd_edt_load(b=False, result_data=False)
        # enable GUI, when done
        self.worker.progress.connect(self.report_progress_edt)
        self.thread.finished.connect(lambda: self.ui_upd_edt_load(b=True, result_data=True))

        self.thread.start()  # finally start the thread

    def report_progress_edt(self, progress):
        self.dlg.pb_loadEDT.setValue(progress)

    def report_progress_add_to_map(self, progress):
        self.dlg.pb_addToMap.setValue(progress)

    def reset_progress_bars_sim_results(self):
        self.dlg.pb_loadEDT.setValue(0)
        self.dlg.pb_addToMap.setValue(0)

    def ui_upd_edt_load(self, b: bool, result_data: bool = False):
        if result_data:
            self.edt_data = self.worker.edt_data

        self.dlg.bt_selectEDT.setEnabled(b)
        self.dlg.bt_clearSelection.setEnabled(b)
        self.dlg.bt_loadResults.setEnabled(b)
        self.dlg.bt_addToMap.setEnabled(b)
        self.dlg.sb_zLevel.setEnabled(b)

    def setup_ui_create_sim_tab(self):
        # this function setups the UI of the Create ENVI-met simulation tab

        # Overview tab
        # make status checkboxes of mandatory sections unclickable
        self.dlg.cb_generalSettings.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_generalSettings.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_meteo.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_meteo.setFocusPolicy(Qt.NoFocus)

        self.clear_settings_create_sim_tab()

        # connect events
        self.dlg.chk_soilSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Soil))
        self.dlg.chk_radiationSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Radiation))
        self.dlg.chk_buildingsSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Buildings_2))
        self.dlg.chk_pollutantsSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Pollutants))
        self.dlg.chk_outputSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Output))
        self.dlg.chk_timingSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Timing))
        self.dlg.chk_expertSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Expert))
        self.dlg.chk_plantsSim.stateChanged.connect(lambda: self.switch_enabled_tab(self.dlg.tab_Plants))

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
        self.dlg.rb_other.clicked.connect(self.select_forcing_mode)

        self.dlg.calendar_startDateSim.selectionChanged.connect(self.update_date)

        self.dlg.le_fullSimName.editingFinished.connect(self.simsettings_change)
        self.dlg.le_shortNameSim.editingFinished.connect(self.simsettings_change)
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

        self.dlg.rb_yesHeightCap.clicked.connect(self.radiation_ui_update)
        self.dlg.rb_noHeightCap.clicked.connect(self.radiation_ui_update)
        self.dlg.rb_useIVSyes.clicked.connect(self.radiation_ui_update)
        self.dlg.rb_useIVSno.clicked.connect(self.radiation_ui_update)
        self.dlg.rbACRTyes.clicked.connect(self.radiation_ui_update)
        self.dlg.rb_ACRTno.clicked.connect(self.radiation_ui_update)

        self.dlg.cb_userPolluType.currentIndexChanged.connect(self.pollutants_ui_update)

        self.dlg.rb_writeNetCDFyes.clicked.connect(self.output_ui_update)
        self.dlg.rb_writeNetCDFNo.clicked.connect(self.output_ui_update)

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

        # find the workspace path and the installation path automatically
        usersettings = os.getenv('APPDATA').replace('\\', '/') + '/ENVI-met/usersettings.setx'
        if os.path.exists(usersettings):
            userpathinfo = ''
            workspace = ''

            settings = open(usersettings, 'br')
            for row in settings:
                row = row.decode('ansi')
                if '<absolute_path>' in row:
                    workspace = row.split(">", 1)[1].split("<", 1)[0].replace(' ', '').replace('\\', '/')
                if ('<userpathinfo>' in row) and ('</userpathinfo>' in row):
                    userpathinfo = row.split(">", 1)[1].split("<", 1)[0].replace(' ', '').replace('\\', '/')
            settings.close()

            if not userpathinfo == '':
                installPath = userpathinfo.replace("sys.userdata", "")
            else:
                self.iface.messageBar().pushMessage("Error", "No ENVI-met installation found!", level=Qgis.Warning)
                return

            if workspace == '':
                self.iface.messageBar().pushMessage("Error", "No ENVI-met workspace found!", level=Qgis.Warning)
                return
        else:
            self.iface.messageBar().pushMessage("Error", "No ENVI-met installation found!", level=Qgis.Warning)
            return

        envicore_path = installPath.replace('\\', '/') + 'win64/envicore_console.exe'

        # print(envicore_path)
        # get selected project folder and simx-file
        projectFolder = self.dlg.lb_selected_projFolder.text().replace('\\', '/')
        simx_file = self.dlg.lb_simxFile.text().replace('\\', '/')

        # check if there is a project.infoX inside this folder
        my_project_name = ''
        if os.path.exists(projectFolder + '/project.infoX'):
            info_file = open(projectFolder + '/project.infoX')  # , 'br')
            '''
            # old code -> with the new scenarios this does not work anymore
            for row in info_file:
                row = row.decode('ansi')
                if '<name>' in row:
                    my_project_name = row.split(">", 1)[1].split("<", 1)[0].strip()
            '''
            startRow = 0
            endRow = 0
            rowI = 0
            textList = []
            for row in info_file:
                #row = row.decode('ansi')
                if '<project_description>' in row:
                    startRow = rowI
                if '</project_description>' in row:
                    endRow = rowI
                rowI += 1
                textList.append(row.strip())
            #print(startRow)
            #print(endRow)
            # info_file.close()
            # info_file = open(projectFolder + '/project.infoX')
            # content = info_file.readlines()
            for a in range(startRow, endRow):
                #print(textList[a])
                if '<name>' in textList[a]:
                    my_project_name = textList[a].split(">", 1)[1].split("<", 1)[0].strip()

            #print(my_project_name)
            info_file.close()
        if my_project_name != '':
            if projectFolder in simx_file:
                simx_file = simx_file.replace(projectFolder + '/', '')
            else:
                self.iface.messageBar().pushMessage("Error",
                                                    "The simulation-file (*.SIMX) is not inside the selected ENVI-met project-folder",
                                                    level=Qgis.Warning)
                return

            if workspace in projectFolder:
                projectFolder = projectFolder.replace(workspace + '/', '')
            else:
                self.iface.messageBar().pushMessage("Error",
                                                    "The selected project-folder is not inside your ENVI-met workspace",
                                                    level=Qgis.Warning)
                return
            # print(f'{envicore_path} {workspace} {my_project_name} {simx_file}')
            # command = f'{envicore_path} {workspace} {my_project_name} {simx_file}'
            # os.system("cmd /c D:/ENVImet560a/win64/envicore.exe")
            # program = "D:\ENVImet560a\win64\Leonardo.exe"
            # = subprocess.Popen(program, shell=True)
            # print(pID)
            # subprocess.run(['D:/ENVImet560a/win64/envicore.exe', ''])
            # os.system("cmd /c {command}")
            # subprocess.run(["start", "/wait", "cmd", "/K", command, "arg /?\^"], shell=True)
            # os.system('start /wait cmd /c ' + f'{envicore_path} {workspace} {my_project_name} {simx_file}')
            #envicore_path = envicore_path.replace('envicore_console.exe', 'core.exe')
            #print(envicore_path)
            #print(f'SIMX-file: {simx_file}" ' f'{envicore_path} {workspace} {my_project_name} {simx_file}')
            # orig:
            os.system(
                f'start "ENVI-met Simulation - started via QGIS.   SIMX-file: {simx_file}" ' f'{envicore_path} {workspace} {my_project_name} {simx_file}')

            # print(f'SIMX-file: {simx_file}" ' f'{envicore_path} {workspace} {my_project_name} {simx_file}')
            # command = f'{envicore_path} {workspace} {my_project_name} {simx_file}'
            # os.system("start /wait cmd /c {command}")
        else:
            self.iface.messageBar().pushMessage("Error",
                                                "Could not find a project.infoX file inside folder. Are you sure the selected folder is a valid ENVI-met project-folder",
                                                level=Qgis.Warning)
            return

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
        if not self.dlg.cb_meteo.isChecked():
            self.iface.messageBar().pushMessage("Error", "Meteorology is not defined", level=Qgis.Warning)
            return
        if self.dlg.le_simxDest.text().isspace() or (self.dlg.le_simxDest.text() == ""):
            self.iface.messageBar().pushMessage("Error", "No output file location defined", level=Qgis.Warning)
            return

        self.thread = QThread()
        self.worker = Worker()

        # see https://realpython.com/python-pyqt-qthread/#using-qthread-to-prevent-freezing-guis
        # and https://doc.qt.io/qtforpython/PySide6/QtCore/QThread.html
        self.worker.moveToThread(self.thread)  # move Worker-Class to a thread
        # Connect signals and slots:
        self.thread.started.connect(lambda: self.worker.save_simx(ui=self.dlg))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # disable GUI
        self.dlg.tw_Main.setEnabled(False)
        # enable GUI, when done
        self.thread.finished.connect(self.after_simx_export)

        self.thread.start()  # finally start the thread

    def after_simx_export(self):
        self.dlg.tw_Main.setEnabled(True)
        self.dlg.lb_reportSave.setText('SIMX-file saved!')

    def output_ui_update(self):
        if self.dlg.rb_writeNetCDFyes.isChecked():
            self.dlg.gb_NetCDFnumFiles.setEnabled(True)
            self.dlg.gb_NetCDFSize.setEnabled(True)
        else:
            self.dlg.gb_NetCDFnumFiles.setEnabled(False)
            self.dlg.gb_NetCDFSize.setEnabled(False)

    def pollutants_ui_update(self):
        if (self.dlg.cb_userPolluType.currentIndex() == 1) or (self.dlg.cb_userPolluType.currentIndex() == 9):
            self.dlg.gb_additionalMyPollu.setVisible(True)
        else:
            self.dlg.gb_additionalMyPollu.setVisible(False)

    def radiation_ui_update(self):
        if self.dlg.rb_yesHeightCap.isChecked():
            self.dlg.sb_heightCap.setEnabled(True)
        else:
            self.dlg.sb_heightCap.setEnabled(False)

        if self.dlg.rb_useIVSyes.isChecked():
            self.dlg.cb_resHeightIVS.setEnabled(True)
            self.dlg.cb_resAziIVS.setEnabled(True)
        else:
            self.dlg.cb_resHeightIVS.setEnabled(False)
            self.dlg.cb_resAziIVS.setEnabled(False)

        if self.dlg.rbACRTyes.isChecked():
            self.dlg.sb_ACRTdays.setEnabled(True)
        else:
            self.dlg.sb_ACRTdays.setEnabled(False)

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
            if ((self.dlg.le_fullSimName.text() != '') and not self.dlg.le_fullSimName.text().isspace()) \
                    and ((self.dlg.le_shortNameSim.text() != '') and not self.dlg.le_shortNameSim.text().isspace()):
                self.dlg.lb_generalSettings.setText(self.generalSettings_states[2])
                self.dlg.cb_generalSettings.setCheckState(Qt.Checked)
            else:
                self.dlg.lb_generalSettings.setText(self.generalSettings_states[1])
                self.dlg.cb_generalSettings.setCheckState(Qt.Unchecked)
        else:
            self.dlg.lb_generalSettings.setText(self.generalSettings_states[0])
            self.dlg.cb_generalSettings.setCheckState(Qt.Unchecked)

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
        if self.dlg.rb_simpleForcing.isChecked():
            # show page for simple forcing
            self.dlg.stackedWidget_3.setCurrentIndex(0)
            self.dlg.lb_meteorology.setText(self.meteoSettings_states[0])
            self.dlg.cb_meteo.setCheckState(Qt.Checked)
        elif self.dlg.rb_fullForcing.isChecked():
            # show page for full forcing
            self.dlg.stackedWidget_3.setCurrentIndex(1)
            if (self.dlg.le_selectedFOX.text() == '') or self.dlg.le_selectedFOX.text().isspace():
                self.dlg.lb_meteorology.setText(self.meteoSettings_states[1])
                self.dlg.cb_meteo.setCheckState(Qt.Unchecked)
            else:
                self.dlg.lb_meteorology.setText(self.meteoSettings_states[2])
                self.dlg.cb_meteo.setCheckState(Qt.Checked)
        else:
            # show page for open/cyclic
            self.dlg.stackedWidget_3.setCurrentIndex(2)
            self.dlg.lb_meteorology.setText(self.meteoSettings_states[3])
            self.dlg.cb_meteo.setCheckState(Qt.Checked)

    @staticmethod
    def switch_enabled_tab(tab):
        tab.setEnabled(not tab.isEnabled())

    def clear_settings_create_sim_tab(self):
        # clears the settings in the Create ENVI-met simulation tab
        # disable optional tabs
        self.dlg.tab_Soil.setEnabled(False)
        self.dlg.tab_Radiation.setEnabled(False)
        self.dlg.tab_Buildings_2.setEnabled(False)
        self.dlg.tab_Pollutants.setEnabled(False)
        self.dlg.tab_Plants.setEnabled(False)
        self.dlg.tab_Timing.setEnabled(False)
        self.dlg.tab_Output.setEnabled(False)
        self.dlg.tab_Expert.setEnabled(False)

        # reset edit-fields to default values
        # Overview
        # Mandatory sections state
        self.dlg.cb_generalSettings.setCheckState(Qt.Unchecked)
        self.dlg.cb_meteo.setCheckState(Qt.Unchecked)
        self.dlg.lb_generalSettings.setText(self.generalSettings_states[0])
        self.dlg.lb_meteorology.setText(self.meteoSettings_states[0])
        # optional sections
        self.dlg.chk_soilSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_radiationSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_buildingsSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_pollutantsSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_outputSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_timingSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_expertSim.setCheckState(Qt.Unchecked)
        self.dlg.chk_plantsSim.setCheckState(Qt.Unchecked)
        self.dlg.tab_Soil.setEnabled(False)
        self.dlg.tab_Radiation.setEnabled(False)
        self.dlg.tab_Buildings_2.setEnabled(False)
        self.dlg.tab_Pollutants.setEnabled(False)
        self.dlg.tab_Plants.setEnabled(False)
        self.dlg.tab_Timing.setEnabled(False)
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
        self.dlg.le_shortNameSim.setText('New Simulation')
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
        self.dlg.sb_timeMaxHum.setValue(5)
        self.dlg.sb_timeMinHum.setValue(16)
        self.dlg.hs_maxT.setValue(28)
        self.dlg.hs_minT.setValue(17)
        self.dlg.hs_maxHum.setValue(75)
        self.dlg.hs_minHum.setValue(45)
        self.dlg.sb_specHum.setValue(9.00)
        self.update_temp_and_hum_simpleforcing()

        self.dlg.sb_windspeed.setValue(1.50)
        self.dlg.sb_winddir.setValue(270.00)
        self.dlg.sb_rlength.setValue(0.010)
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
        self.dlg.rb_forcePrec_yes.setChecked(True)
        self.dlg.sb_constWS_FUFo.setValue(2.00)
        self.dlg.sb_constWD_FuFo.setValue(135.00)
        self.dlg.sb_rlength_FuFo.setValue(0.010)
        self.dlg.sb_initT.setValue(20.00)
        self.dlg.sb_lowclouds_2.setValue(0)
        self.dlg.sb_mediumclouds.setValue(0)
        self.dlg.sb_highclouds_2.setValue(0)
        self.dlg.sb_relHum.setValue(50.00)
        self.dlg.sb_specHum_2.setValue(8.00)
        self.dlg.stackedWidget_4.setCurrentIndex(0)
        self.dlg.stackedWidget_5.setCurrentIndex(1)
        self.dlg.stackedWidget_6.setCurrentIndex(0)
        self.dlg.stackedWidget_7.setCurrentIndex(1)

        # Open/Cyclic
        self.dlg.sb_otherAirT.setValue(20.00)
        self.dlg.sb_otherHum.setValue(50.00)
        self.dlg.sb_otherHum2500.setValue(8.00)
        self.dlg.sb_otherLowclouds.setValue(0)
        self.dlg.sb_otherMediumclouds.setValue(0)
        self.dlg.sb_otherHighclouds.setValue(0)
        self.dlg.sb_otherWS.setValue(2.00)
        self.dlg.sb_otherWdir.setValue(135.00)
        self.dlg.sb_otherRlength.setValue(0.010)
        self.dlg.cb_otherBChumT.setCurrentIndex(0)
        self.dlg.cb_otherBCturb.setCurrentIndex(0)

        # Soil
        self.dlg.sb_soilHumUpper.setValue(65.00)
        self.dlg.sb_soilHumMiddle.setValue(70.00)
        self.dlg.sb_soilHumLower.setValue(75.00)
        self.dlg.sb_soilHumBedrock.setValue(75.00)
        self.dlg.sb_soilTupper.setValue(20.00)
        self.dlg.sb_soilTmiddle.setValue(20.00)
        self.dlg.sb_soilTlower.setValue(19.00)
        self.dlg.sb_soilTbedrock.setValue(18.00)

        # Radiation
        self.dlg.rb_fineRes.setChecked(True)
        self.dlg.rb_yesHeightCap.setChecked(True)
        self.dlg.sb_heightCap.setEnabled(True)
        self.dlg.sb_heightCap.setValue(10)
        self.dlg.rb_useIVSyes.setChecked(True)
        self.dlg.cb_resHeightIVS.setEnabled(False)
        self.dlg.cb_resAziIVS.setEnabled(False)
        self.dlg.cb_resHeightIVS.setCurrentIndex(0)
        self.dlg.cb_resAziIVS.setCurrentIndex(0)
        self.dlg.cb_humanProjFac.setCurrentIndex(2)
        self.dlg.rb_MRT2.setChecked(True)
        self.dlg.rbACRTyes.setChecked(True)
        self.dlg.sb_ACRTdays.setEnabled(True)
        self.dlg.sb_ACRTdays.setValue(10)
        self.dlg.sb_adjustFac.setValue(1.00)

        # Buildings
        self.dlg.sb_bldTmp.setValue(20.00)
        self.dlg.sb_bldSurfTmp.setValue(20.00)
        self.dlg.rb_indoorNo.setChecked(True)

        # Pollutants
        self.dlg.rb_multiPollu.setChecked(True)
        self.dlg.rb_activeChem.setChecked(True)
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

        # Plants
        self.dlg.rb_leafTransUserDef.setChecked(True)
        self.dlg.rb_TreeCalYes.setChecked(True)
        self.dlg.sb_co2.setValue(400)

        # Timing
        self.dlg.sb_timingPlant.setValue(600)
        self.dlg.sb_timingSurf.setValue(30)
        self.dlg.sb_timingRad.setValue(600)
        self.dlg.sb_timingFlow.setValue(900)
        self.dlg.sb_timingEmission.setValue(600)
        self.dlg.sb_t0.setValue(2.00)
        self.dlg.sb_t1.setValue(2.00)
        self.dlg.sb_t2.setValue(1.00)
        self.dlg.sb_t0t1angle.setValue(40.00)
        self.dlg.sb_t1t2angle.setValue(50.00)

        # Output
        self.dlg.cb_outputBldData.setCheckState(Qt.Checked)
        self.dlg.cb_outputRadData.setCheckState(Qt.Checked)
        self.dlg.cb_outputSoilData.setCheckState(Qt.Checked)
        self.dlg.cb_outputVegData.setCheckState(Qt.Checked)
        self.dlg.sb_outputIntRecBld.setValue(30)
        self.dlg.sb_outputIntOther.setValue(60)
        self.dlg.rb_writeNetCDFNo.setChecked(True)
        self.dlg.rb_NetCDFsingleFile.setChecked(True)
        self.dlg.rb_NetCDFsaveAll.setChecked(True)
        self.dlg.rb_InclNestingGridsNo.setChecked(True)
        self.dlg.gb_NetCDFnumFiles.setEnabled(False)
        self.dlg.gb_NetCDFSize.setEnabled(False)

        # Expert
        self.dlg.rb_newSOR.setChecked(True)
        self.dlg.rb_DIN6946.setChecked(True)
        self.dlg.rb_threadingMain.setChecked(True)
        self.dlg.rb_avgInflowNo.setChecked(True)
        self.dlg.cb_TKE.setCurrentIndex(0)

        # trigger update event for meteo-settings
        self.select_forcing_mode()

    def update_temp_and_hum_simpleforcing(self):
        # linear interpolation
        time_Tmax = self.dlg.sb_timeMaxT.value()
        time_Tmin = self.dlg.sb_timeMinT.value()
        time_Hmax = self.dlg.sb_timeMaxHum.value()
        time_Hmin = self.dlg.sb_timeMinHum.value()
        maxT = self.dlg.hs_maxT.value()
        minT = self.dlg.hs_minT.value()
        maxH = self.dlg.hs_maxHum.value()
        minH = self.dlg.hs_minHum.value()

        timeDiff_minToMaxT = abs(time_Tmax - time_Tmin)
        valDiff_minToMaxT = abs(maxT - minT)
        ratio_T_intraday = valDiff_minToMaxT / timeDiff_minToMaxT
        if time_Tmax > time_Tmin:
            ratio_T_overnight = valDiff_minToMaxT / (24 - time_Tmax + time_Tmin)
            # intraday values
            for j in range(0, timeDiff_minToMaxT + 1):
                val = str(round(minT + j * ratio_T_intraday, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * (j + time_Tmin)
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
            # max to midnight
            cnt = 1
            for j in range(time_Tmax + 1, 24):
                val = str(round(maxT - cnt * ratio_T_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
            # min downto midnight
            cnt = 1
            for j in range(time_Tmin - 1, -1, -1):
                val = str(round(minT + cnt * ratio_T_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
        else:
            ratio_T_overnight = valDiff_minToMaxT / (24 - time_Tmin + time_Tmax)
            # intraday values
            for j in range(0, timeDiff_minToMaxT + 1):
                val = str(round(maxT - j * ratio_T_intraday, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * (j + time_Tmax)
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
            # min to midnight
            cnt = 1
            for j in range(time_Tmin + 1, 24):
                val = str(round(minT + cnt * ratio_T_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
            # max downto midnight
            cnt = 1
            for j in range(time_Tmax - 1, -1, -1):
                val = str(round(maxT - cnt * ratio_T_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1

        timeDiff_minToMaxH = abs(time_Hmax - time_Hmin)
        valDiff_minToMaxH = abs(maxH - minH)
        ratio_H_intraday = valDiff_minToMaxH / timeDiff_minToMaxH
        if time_Hmax > time_Hmin:
            ratio_H_overnight = valDiff_minToMaxH / (24 - time_Tmax + time_Tmin)
            # intraday values
            for j in range(0, timeDiff_minToMaxH + 1):
                val = str(round(minH + j * ratio_H_intraday, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * (j + time_Hmin) + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
            # max to midnight
            cnt = 1
            for j in range(time_Hmax + 1, 24):
                val = str(round(maxH - cnt * ratio_H_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
            # min downto midnight
            cnt = 1
            for j in range(time_Hmin - 1, -1, -1):
                val = str(round(minH + cnt * ratio_H_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
        else:
            ratio_H_overnight = valDiff_minToMaxH / (24 - time_Hmin + time_Hmax)
            # intraday values
            for j in range(0, timeDiff_minToMaxH + 1):
                val = str(round(maxH - j * ratio_H_intraday, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * (j + time_Hmax) + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
            # min to midnight
            cnt = 1
            for j in range(time_Hmin + 1, 24):
                val = str(round(minH + cnt * ratio_H_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1
            # max downto midnight
            cnt = 1
            for j in range(time_Hmax - 1, -1, -1):
                val = str(round(maxH - cnt * ratio_H_overnight, 2))
                item = QtWidgets.QTableWidgetItem(0)
                idx = 2 * j + 1
                self.dlg.tableWidget.setItem(0, idx, item)
                item.setText(val)
                cnt += 1

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
        self.dlg.se_dx.valueChanged.connect(self.startWorkerPreviewdxyz)
        self.dlg.se_dy.valueChanged.connect(self.startWorkerPreviewdxyz)

        self.dlg.se_dz.valueChanged.connect(self.startWorkerPreviewdz)
        self.dlg.se_zGrids.valueChanged.connect(self.startWorkerPreviewdz)
        self.dlg.se_teleStart.valueChanged.connect(self.startWorkerPreviewdz)
        self.dlg.se_teleStretch.valueChanged.connect(self.startWorkerPreviewdz)
        self.dlg.chk_useSplitting.stateChanged.connect(self.startWorkerPreviewdz)
        self.dlg.chk_useTelescoping.stateChanged.connect(self.startWorkerPreviewdz)

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
        self.dlg.cb_summary_gridding.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_gridding.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_buildings.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_buildings.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_dem.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_dem.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_surfaces.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_surfaces.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_asrc.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_asrc.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_lsrc.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_lsrc.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_psrc.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_psrc.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_3dplants.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_3dplants.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_receptors.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_receptors.setFocusPolicy(Qt.NoFocus)
        self.dlg.cb_summary_simpleplants.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.dlg.cb_summary_simpleplants.setFocusPolicy(Qt.NoFocus)

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
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_buildings:
            if (self.dlg.cb_buildingLayer.currentLayer() is None) \
                    or ((self.dlg.cb_bTop.currentField() == "") and not (self.dlg.chk_bTop.isChecked())) \
                    or ((self.dlg.cb_bBot.currentField() == "") and not (self.dlg.chk_bBot.isChecked())) \
                    or ((self.dlg.cb_bGreenRoof.currentField() == "") and not (self.dlg.chk_bGreenRoof.isChecked())) \
                    or ((self.dlg.cb_bGreenWall.currentField() == "") and not (self.dlg.chk_bGreenWall.isChecked())) \
                    or ((self.dlg.cb_bWall.currentField() == "") and not (self.dlg.chk_bWall.isChecked())) \
                    or ((self.dlg.cb_bRoof.currentField() == "") and not (self.dlg.chk_bRoof.isChecked())) \
                    or ((self.dlg.cb_bName.currentField() == "") and not (self.dlg.chk_bName.isChecked())) \
                    or ((self.dlg.cb_bBPS.currentField() == "") and not (self.dlg.chk_bBPS.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_surfaces:
            if (self.dlg.rb_surfRaster.isChecked()
                and (self.dlg.cb_MapLayerRasterSurf.currentLayer() is None)) \
                    or (self.dlg.rb_surfVector.isChecked()
                        and (self.dlg.cb_surfLayer.currentLayer() is None
                             or ((self.dlg.cb_surfID.currentField() == "") and not (self.dlg.chk_surf.isChecked())))):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_simpleplants:
            if (self.dlg.rb_simplePlantsRaster.isChecked()
                and self.dlg.cb_MapLayerRasterSP.currentLayer() is None) \
                    or (self.dlg.rb_simplePlantsVector.isChecked()
                        and (self.dlg.cb_simplePlantLayer.currentLayer() is None
                             or (self.dlg.cb_simplePlantID.currentField() == "") and not (
                            self.dlg.chk_simplePlantID.isChecked()))):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_asrc:
            if (self.dlg.cb_srcALayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcAID.currentField() == "") and not (self.dlg.chk_srcAID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_lsrc:
            if (self.dlg.cb_srcLLayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcLID.currentField() == "") and not (self.dlg.chk_srcLID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_psrc:
            if (self.dlg.cb_srcPLayer.currentLayer() is None) \
                    or ((self.dlg.cb_srcPID.currentField() == "") and not (self.dlg.chk_srcPID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_3dplants:
            if (self.dlg.cb_plant3dLayer.currentLayer() is None) \
                    or ((self.dlg.cb_plant3dID.currentField() == "") and not (self.dlg.chk_plant3d.isChecked())) \
                    or (
                    (self.dlg.cb_plant3dAddOut.currentField() == "") and not (self.dlg.chk_plant3dAddOut.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_dem:
            if self.dlg.cb_demLayer.currentLayer() is None:
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
        elif summary_checkBox == self.dlg.cb_summary_receptors:
            if (self.dlg.cb_recLayer.currentLayer() is None) \
                    or ((self.dlg.cb_recID.currentField() == "") and not (self.dlg.chk_recID.isChecked())):
                # unchecked = 0
                summary_checkBox.setCheckState(Qt.Unchecked)
            else:
                # checked = 2
                summary_checkBox.setCheckState(Qt.Checked)
