from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .area_algorithms import AreaStatisticsAlgorithm, BuildAreaMasksAlgorithm


class EnvimetProvider(QgsProcessingProvider):

    def id(self):
        return 'envimet'

    def name(self):
        return 'ENVI-met'

    def icon(self):
        return QIcon(':/plugins/geodata2ENVImet/icon.png')

    def loadAlgorithms(self):
        self.addAlgorithm(BuildAreaMasksAlgorithm())
        self.addAlgorithm(AreaStatisticsAlgorithm())
