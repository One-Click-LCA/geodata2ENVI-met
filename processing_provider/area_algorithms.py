"""Processing algorithms of the area analysis: cell masks and time series of area statistics."""

import datetime as dt
import os

from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsFeatureSink, QgsProcessing, QgsProcessingAlgorithm,
                       QgsProcessingException, QgsProcessingOutputFile, QgsProcessingParameterDateTime,
                       QgsProcessingParameterEnum, QgsProcessingParameterFeatureSink,
                       QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFile,
                       QgsProcessingParameterFolderDestination, QgsProcessingParameterNumber,
                       QgsProcessingParameterString)

from .. import area_analysis
from ..core import stats as core_stats, zones as core_zones

VERTICAL_OPTIONS = ['Pedestrian level (terrain + 1.5 m)', 'Height range above ground']
DELIMITERS = [',', ';']
RESULT_FILES = 'ENVI-met results (*.nc *.NC *.edx *.EDX);;All files (*.*)'


class _AreaAlgorithm(QgsProcessingAlgorithm):
    AREAS = 'AREAS'
    ID_FIELD = 'ID_FIELD'
    NAME_FIELD = 'NAME_FIELD'
    RESULTS = 'RESULTS'
    RESULTS_FILE = 'RESULTS_FILE'
    SOURCE = 'SOURCE'
    VERTICAL = 'VERTICAL'
    Z_MIN = 'Z_MIN'
    Z_MAX = 'Z_MAX'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'
    PREFIX = 'PREFIX'
    DELIMITER = 'DELIMITER'
    CELLS_CSV = 'CELLS_CSV'
    ZONES_CSV = 'ZONES_CSV'
    GRID_JSON = 'GRID_JSON'

    def group(self):
        return 'Area analysis'

    def groupId(self):
        return 'areaanalysis'

    def createInstance(self):
        return type(self)()

    def add_area_parameters(self, results_label='ENVI-met results'):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.AREAS, 'Analysis areas (polygons)', [QgsProcessing.SourceType.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterField(
            self.ID_FIELD, 'Area ID field (without: all polygons form one area)', parentLayerParameterName=self.AREAS,
            optional=True))
        self.addParameter(QgsProcessingParameterField(
            self.NAME_FIELD, 'Area name field', parentLayerParameterName=self.AREAS, optional=True))
        self.add_results_parameters(self.RESULTS, self.RESULTS_FILE, results_label, optional=False)
        self.addParameter(QgsProcessingParameterString(
            self.SOURCE, 'Results to use (e.g. NetCDF, Report_Slice, atmosphere (EDX); empty: NetCDF)',
            defaultValue='', optional=True))

    def add_results_parameters(self, folder_name, file_name, label, optional):
        """A folder and a file input: Processing's file widget picks either folders or files, not both."""
        needed = '' if optional else ' (this or a result file)'
        self.addParameter(QgsProcessingParameterFile(
            folder_name, f'{label}: output folder{needed}', behavior=QgsProcessingParameterFile.Behavior.Folder,
            optional=True))
        self.addParameter(QgsProcessingParameterFile(
            file_name, f'{label}: or one result file (NetCDF or EDX)',
            behavior=QgsProcessingParameterFile.Behavior.File, fileFilter=RESULT_FILES, optional=True))

    def results_path(self, parameters, context, folder_name, file_name, required=True):
        path = (self.parameterAsString(parameters, file_name, context)
                or self.parameterAsString(parameters, folder_name, context))
        if required and not path:
            raise QgsProcessingException('Choose the ENVI-met results: an output folder or a result file.')
        return path

    def add_vertical_parameters(self):
        self.addParameter(QgsProcessingParameterEnum(
            self.VERTICAL, 'Vertical selection', options=VERTICAL_OPTIONS, defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.Z_MIN, 'Height range: from (m above ground)', type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.Z_MAX, 'Height range: to (m above ground)', type=QgsProcessingParameterNumber.Type.Double,
            defaultValue=3.0, minValue=0.0))

    def add_output_parameters(self, default_prefix):
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, 'Output folder'))
        self.addParameter(QgsProcessingParameterString(self.PREFIX, 'File name prefix', defaultValue=default_prefix))
        self.addParameter(QgsProcessingParameterEnum(
            self.DELIMITER, 'CSV delimiter', options=['comma', 'semicolon'], defaultValue=0))
        self.addOutput(QgsProcessingOutputFile(self.CELLS_CSV, 'Cells (CSV)'))
        self.addOutput(QgsProcessingOutputFile(self.ZONES_CSV, 'Areas (CSV)'))
        self.addOutput(QgsProcessingOutputFile(self.GRID_JSON, 'Grid description (JSON)'))

    # ------------------------------------------------------------------------------------------
    def vertical(self, parameters, context):
        mode = core_zones.MODE_PEDESTRIAN if self.parameterAsEnum(parameters, self.VERTICAL, context) == 0 \
            else core_zones.MODE_RANGE
        z_min = self.parameterAsDouble(parameters, self.Z_MIN, context)
        z_max = self.parameterAsDouble(parameters, self.Z_MAX, context)
        if mode == core_zones.MODE_RANGE and z_max <= z_min:
            raise QgsProcessingException('The height range needs a top above its bottom.')
        return mode, z_min, z_max

    def open_results(self, path, source_name, feedback):
        try:
            source = area_analysis.open_source(path, source_name)
        except area_analysis.AnalysisError as error:
            raise QgsProcessingException(str(error))
        first = source.first_file()
        if first is None:
            raise QgsProcessingException(f'No readable time steps in {source.name} of {path}.')
        for path_, message in source.errors:
            feedback.pushWarning(f'Skipped {path_}: {message}')
        feedback.pushInfo(f'{source.name}: {len(source.timesteps)} time steps, '
                          f'{first.grid.nx} x {first.grid.ny} cells, EPSG:{first.grid.epsg}')
        return source, first

    def masks(self, parameters, context, feedback, grid, static, mode, z_min, z_max):
        areas = self.parameterAsSource(parameters, self.AREAS, context)
        if areas is None:
            raise QgsProcessingException('No analysis areas.')
        id_field = self.parameterAsString(parameters, self.ID_FIELD, context)
        name_field = self.parameterAsString(parameters, self.NAME_FIELD, context)
        zones, skipped = area_analysis.zones_from_features(
            areas.getFeatures(), areas.sourceCrs(), id_field, name_field, grid.epsg, context.transformContext())
        if skipped:
            feedback.pushWarning(f'{skipped} polygon(s) without an area ID were left out.')
        if not zones:
            raise QgsProcessingException('No polygons with an area ID.')
        mismatch = static.biomet_level_mismatch()
        if mismatch:
            feedback.pushWarning(
                f'These results were written by ENVI-met 5.8 or older: in {100 * mismatch:.0f} % of the open '
                f'columns their ...Biomet fields lie at another level than the pedestrian cells used here.')
        masks = []
        for zone in zones:
            try:
                mask = core_zones.build_mask(grid, zone, static, mode, z_min, z_max)
            except ValueError as error:
                raise QgsProcessingException(str(error))
            if not len(mask):
                feedback.pushWarning(f'Area {zone.zone_id} ({zone.name}) has no atmosphere cells in the model area.')
            masks.append(mask)
        feedback.pushInfo(f'{len(masks)} area(s), {sum(len(m) for m in masks)} cells')
        return masks, id_field, name_field

    def output_location(self, parameters, context):
        folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        prefix = self.parameterAsString(parameters, self.PREFIX, context).strip() or 'areas'
        delimiter = DELIMITERS[self.parameterAsEnum(parameters, self.DELIMITER, context)]
        os.makedirs(folder, exist_ok=True)
        return folder, prefix, delimiter


class BuildAreaMasksAlgorithm(_AreaAlgorithm):
    CELLS = 'CELLS'

    def name(self):
        return 'areamasks'

    def displayName(self):
        return 'Build area masks'

    def shortHelpString(self):
        return ('Lists the model cells of each analysis area with the share of their area inside it '
                '("fraction"), at the pedestrian level or in a height range above the ground. Only '
                'atmosphere cells are listed. External scripts can extract values from the NetCDF '
                'output with the cells CSV; "weight" is the cell area (m²) or volume (m³) to weight with.')

    def initAlgorithm(self, config=None):
        self.add_area_parameters()
        self.add_vertical_parameters()
        self.add_output_parameters('areas')
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.CELLS, 'Cells (preview)', type=QgsProcessing.SourceType.TypeVectorPolygon, optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        mode, z_min, z_max = self.vertical(parameters, context)
        path = self.results_path(parameters, context, self.RESULTS, self.RESULTS_FILE)
        source, first = self.open_results(path, self.parameterAsString(parameters, self.SOURCE, context), feedback)
        try:
            grid, static = first.grid, first.static_fields()
            masks, id_field, name_field = self.masks(parameters, context, feedback, grid, static, mode, z_min, z_max)
            folder, prefix, delimiter = self.output_location(parameters, context)
            info = {'results': path, 'source': source.name, 'vertical': area_analysis.level_text(mode, z_min, z_max),
                    'id_field': id_field, 'name_field': name_field, 'created': dt.datetime.now().isoformat()}
            paths = area_analysis.write_masks(folder, prefix, grid, static, masks, info, delimiter)
            results = {self.CELLS_CSV: paths['cells'], self.ZONES_CSV: paths['zones'], self.GRID_JSON: paths['grid']}
            fields = area_analysis.preview_fields()
            sink, dest_id = self.parameterAsSink(parameters, self.CELLS, context, fields, Qgis.WkbType.Polygon,
                                                 QgsCoordinateReferenceSystem(f'EPSG:{grid.epsg}'))
            if sink is not None:
                for feature in area_analysis.preview_features(grid, masks, fields):
                    sink.addFeature(feature, QgsFeatureSink.Flag.FastInsert)
                results[self.CELLS] = dest_id
            return results
        finally:
            source.close()


class AreaStatisticsAlgorithm(_AreaAlgorithm):
    RESULTS_B = 'RESULTS_B'
    RESULTS_B_FILE = 'RESULTS_B_FILE'
    SOURCE_B = 'SOURCE_B'
    VARIABLES = 'VARIABLES'
    VARIABLES_B = 'VARIABLES_B'
    START = 'START'
    END = 'END'
    THRESHOLDS = 'THRESHOLDS'
    STATISTICS = 'STATISTICS'
    DIURNAL = 'DIURNAL'
    DAILY = 'DAILY'

    def name(self):
        return 'areastatistics'

    def displayName(self):
        return 'Area statistics (time series)'

    def shortHelpString(self):
        return ('Weighted statistics per analysis area and time step: mean, standard deviation, minimum, '
                'percentiles, maximum, the share above thresholds and, for UTCI and PET, the share per '
                'heat-stress class. Cells cut by an area count with the share of their area inside it; '
                'only atmosphere cells count. Also writes the mean diurnal cycle and daily summaries. With '
                'results B, also B and A - B: cell by cell when both runs have the same grid, levels and '
                'terrain, else the difference of the means. Variables: short or long names separated by '
                'commas; empty means UTCI. B\'s variables are found by key, long name or the name without '
                'spaces; where results in another format name a quantity too differently, name them under '
                '"Variables in B".')

    def initAlgorithm(self, config=None):
        self.add_area_parameters('ENVI-met results A')
        self.add_results_parameters(self.RESULTS_B, self.RESULTS_B_FILE,
                                    'ENVI-met results B (optional, for a comparison)', optional=True)
        self.addParameter(QgsProcessingParameterString(
            self.SOURCE_B, 'Results B to use (empty: NetCDF)', defaultValue='', optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.VARIABLES, 'Variables (comma-separated; empty: UTCI)', defaultValue='', optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.VARIABLES_B, 'Variables in B, in the same order (empty: found by name)', defaultValue='',
            optional=True))
        self.add_vertical_parameters()
        self.addParameter(QgsProcessingParameterDateTime(
            self.START, 'From (local standard time; empty: first time step)',
            type=QgsProcessingParameterDateTime.Type.DateTime, optional=True))
        self.addParameter(QgsProcessingParameterDateTime(
            self.END, 'To (empty: last time step)', type=QgsProcessingParameterDateTime.Type.DateTime, optional=True))
        self.addParameter(QgsProcessingParameterString(
            self.THRESHOLDS, 'Report the share above these values (comma-separated)', defaultValue='',
            optional=True))
        self.add_output_parameters('areas')
        self.addOutput(QgsProcessingOutputFile(self.STATISTICS, 'Statistics per time step (CSV)'))
        self.addOutput(QgsProcessingOutputFile(self.DIURNAL, 'Mean diurnal cycle (CSV)'))
        self.addOutput(QgsProcessingOutputFile(self.DAILY, 'Daily summary (CSV)'))

    def _datetime(self, parameters, name, context):
        if parameters.get(name) in (None, ''):
            return None
        value = self.parameterAsDateTime(parameters, name, context)
        return value.toPyDateTime() if value.isValid() else None

    def processAlgorithm(self, parameters, context, feedback):
        mode, z_min, z_max = self.vertical(parameters, context)
        level = area_analysis.level_text(mode, z_min, z_max)
        start, end = self._datetime(parameters, self.START, context), self._datetime(parameters, self.END, context)
        try:
            thresholds = [float(t) for t in self.parameterAsString(parameters, self.THRESHOLDS, context)
                          .replace(';', ',').split(',') if t.strip()]
        except ValueError:
            raise QgsProcessingException('Thresholds must be numbers separated by commas.')
        variable_text = self.parameterAsString(parameters, self.VARIABLES, context)
        folder, prefix, delimiter = self.output_location(parameters, context)

        path_a = self.results_path(parameters, context, self.RESULTS, self.RESULTS_FILE)
        path_b = self.results_path(parameters, context, self.RESULTS_B, self.RESULTS_B_FILE, required=False)
        source_a, first_a = self.open_results(path_a, self.parameterAsString(parameters, self.SOURCE, context),
                                              feedback)
        sources = [source_a]
        try:
            grid_a, static_a = first_a.grid, first_a.static_fields()
            masks_a, id_field, name_field = self.masks(parameters, context, feedback, grid_a, static_a, mode,
                                                       z_min, z_max)
            variables_a = self._variables(first_a, variable_text, mode, feedback)
            info = {'results_a': path_a, 'source_a': source_a.name, 'results_b': path_b, 'vertical': level,
                    'variables': [v.key for v in variables_a], 'id_field': id_field, 'name_field': name_field,
                    'created': dt.datetime.now().isoformat()}
            paths = area_analysis.write_masks(folder, prefix, grid_a, static_a, masks_a, info, delimiter)

            share = 1.0 if not path_b else 0.4
            values_a = {} if path_b else None
            rows = core_stats.time_series(
                source_a, masks_a, variables_a, mode, level, 'A', start, end, thresholds,
                progress=lambda p: feedback.setProgress(p * share), cancelled=feedback.isCanceled,
                values_out=values_a)
            if path_b:
                source_b, first_b = self.open_results(
                    path_b, self.parameterAsString(parameters, self.SOURCE_B, context), feedback)
                sources.append(source_b)
                grid_b, static_b = first_b.grid, first_b.static_fields()
                masks_b, _, _ = self.masks(parameters, context, feedback, grid_b, static_b, mode, z_min, z_max)
                variables_b = self._paired_variables(
                    variables_a, first_b, self.parameterAsString(parameters, self.VARIABLES_B, context), mode,
                    feedback)
                rows += core_stats.time_series(
                    source_b, masks_b, variables_b, mode, level, 'B', start, end, thresholds,
                    progress=lambda p: feedback.setProgress(40 + p * 0.3), cancelled=feedback.isCanceled)
                if grid_b.matches(grid_a) and area_analysis.same_vertical(static_a, static_b):
                    # B at A's cells, which are the same places: cells valid in both runs are paired
                    values_b = {}
                    core_stats.time_series(
                        source_b, masks_a, variables_b, mode, level, 'B', start, end,
                        progress=lambda p: feedback.setProgress(70 + p * 0.3), cancelled=feedback.isCanceled,
                        values_out=values_b)
                    rows += core_stats.difference_series(values_a, values_b, masks_a, variables_a, mode, level,
                                                         thresholds)
                else:
                    why = ('different grids' if not grid_b.matches(grid_a)
                           else 'different vertical levels or terrain')
                    feedback.pushWarning(f'Results A and B have {why}: A - B is the difference of the area '
                                         f'means only.')
                    rows += core_stats.mean_differences([r for r in rows if r['scenario'] == 'A'],
                                                        [r for r in rows if r['scenario'] == 'B'])
            if feedback.isCanceled():
                return {}
            paths['statistics'] = core_stats.write_csv(os.path.join(folder, f'{prefix}_statistics.csv'), rows,
                                                       delimiter=delimiter)
            paths['diurnal'] = core_stats.write_csv(os.path.join(folder, f'{prefix}_diurnal.csv'),
                                                    core_stats.diurnal_cycle(rows), delimiter=delimiter)
            paths['daily'] = core_stats.write_csv(os.path.join(folder, f'{prefix}_daily.csv'),
                                                  core_stats.daily_summary(rows), delimiter=delimiter)
            feedback.pushInfo(f'{len(rows)} rows written to {paths["statistics"]}')
            return {self.CELLS_CSV: paths['cells'], self.ZONES_CSV: paths['zones'], self.GRID_JSON: paths['grid'],
                    self.STATISTICS: paths['statistics'], self.DIURNAL: paths['diurnal'], self.DAILY: paths['daily']}
        finally:
            for source in sources:
                source.close()

    def _variables(self, result_file, text, mode, feedback):
        variables, problems = area_analysis.resolve_variables(result_file, text, mode)
        for problem in problems:
            feedback.pushWarning(problem)
        if not variables:
            raise QgsProcessingException('None of the variables can be evaluated. ' + ' '.join(problems))
        feedback.pushInfo('Variables: ' + ', '.join(f'{v.long_name} [{v.key}]' for v in variables))
        return variables

    def _paired_variables(self, variables_a, result_file_b, text_b, mode, feedback):
        variables, problems = area_analysis.pair_variables(variables_a, result_file_b, text_b, mode)
        for problem in problems:
            feedback.pushWarning(problem)
        if not variables:
            raise QgsProcessingException('None of the variables can be compared with results B. '
                                         + ' '.join(problems))
        feedback.pushInfo('Variables in B: ' + ', '.join(f'{v.long_name} [{v.key}] as {v.name}' for v in variables))
        return variables
