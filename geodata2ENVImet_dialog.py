import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

# This loads our .ui file so that PyQt can populate our plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'geodata2ENVImet_dialog_base.ui'))


class Geo2ENVImetDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor"""
        super(Geo2ENVImetDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() we can access any designer object by doing
        # self.<objectname>, and we can use autoconnect slots
        self.setupUi(self)
