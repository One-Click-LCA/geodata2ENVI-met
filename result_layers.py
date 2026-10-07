"""Result layers of the Load results tab, made in a background QgsTask.

The task only reads files and writes GeoTIFFs; the layers are created, styled
and added to the project on the main thread when it has finished. The
project's CRS is left as it is.
"""

import os
import tempfile
import traceback
import uuid

import numpy as np
from qgis.core import (Qgis, QgsColorRampShader, QgsMessageLog, QgsProject, QgsRasterBandStats,
                       QgsRasterLayer, QgsRasterRendererUtils, QgsRasterShader,
                       QgsSingleBandPseudoColorRenderer, QgsStyle, QgsTask)

from .Const_defines import (C_COLOR_SCALE_CUSTOM_PATH, C_COLOR_SCALE_INVERT, C_COLOR_SCALE_NAME,
                            C_COLOR_SCALE_STEPS, C_COLOR_SCALE_USE_CUSTOM)
from .Helper_Functions import get_color_scale_interpolation, get_color_scale_mode
from .core import geotiff
from .core.readers import open_result_file

_OUTPUT_FOLDER = None


def output_folder():
    """Folder for the GeoTIFFs of this QGIS session."""
    global _OUTPUT_FOLDER
    if _OUTPUT_FOLDER is None or not os.path.isdir(_OUTPUT_FOLDER):
        _OUTPUT_FOLDER = tempfile.mkdtemp(prefix='envimet_results_')
    return _OUTPUT_FOLDER


class LayerRequest:
    """One layer to make: a field of series A or B, or the difference A - B.

    ``a`` and ``b`` are (file path, time index, variable key).
    """

    def __init__(self, label, date, time, suffix, a=None, b=None, height=0.0):
        self.label = label
        self.date = date
        self.time = time
        self.suffix = suffix
        self.a = a
        self.b = b
        self.height = height

    @property
    def is_delta(self):
        return self.a is not None and self.b is not None

    def layer_name(self, level):
        parts = [self.label, self.date, self.time]
        if level:
            parts.append(level)
        parts.append(self.suffix)
        return '_'.join(parts)


class Cutline:
    """A polygon to clip the layers with: WKT and the WKT of its CRS (both plain strings, thread-safe)."""

    def __init__(self, wkt, crs_wkt):
        self.wkt = wkt
        self.crs_wkt = crs_wkt

    def in_epsg(self, epsg):
        from osgeo import ogr, osr
        source = osr.SpatialReference()
        source.ImportFromWkt(self.crs_wkt)
        target = osr.SpatialReference()
        target.ImportFromEPSG(int(epsg))
        for srs in (source, target):
            srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        geometry = ogr.CreateGeometryFromWkt(self.wkt)
        geometry.Transform(osr.CoordinateTransformation(source, target))
        return geometry.ExportToWkt()


class ResultLayersTask(QgsTask):

    def __init__(self, requests, cutline=None, on_finished=None):
        super().__init__('ENVI-met: result layers', QgsTask.Flag.CanCancel)
        self.requests = requests
        self.cutline = cutline
        self.on_finished = on_finished
        self.outputs = []        # (GeoTIFF path, layer name)
        self.errors = []
        self.layers = []
        self._files = {}

    # ---------------------------------------------------------------- background thread
    def run(self):
        try:
            for number, request in enumerate(self.requests):
                if self.isCanceled():
                    return False
                try:
                    self.outputs.append(self._make(request))
                except Exception as error:
                    self.errors.append(f'{request.label} {request.date} {request.time} {request.suffix}: {error}')
                    QgsMessageLog.logMessage(traceback.format_exc(), 'ENVI-met', level=Qgis.MessageLevel.Warning)
                self.setProgress(100.0 * (number + 1) / len(self.requests))
        finally:
            for result in self._files.values():
                result.close()
            self._files.clear()
        return True

    def _read(self, reference, height):
        path, index, key = reference
        result = self._files.get(path)
        if result is None:
            result = open_result_file(path)
            self._files[path] = result
        data, level = result.read(key, index, height)
        return data, result.grid, level

    def _new_path(self, folder=None):
        return os.path.join(folder or output_folder(), f'{uuid.uuid4().hex}.tif')

    def _publish(self, path, epsg, resolution):
        """Final north-up GeoTIFF of ``path`` (clipped to the cutline if there is one)."""
        cutline = self.cutline.in_epsg(epsg) if self.cutline is not None else None
        return geotiff.warp_north_up(path, self._new_path(), resolution, epsg, cutline_wkt=cutline)

    def _make(self, request):
        if not request.is_delta:
            data, grid, level = self._read(request.a or request.b, request.height)
            rotated = geotiff.write_rotated(f'/vsimem/{uuid.uuid4().hex}.tif', data, grid)
            try:
                path = self._publish(rotated, grid.epsg, geotiff.display_resolution(grid))
            finally:
                _unlink(rotated)
            return path, request.layer_name(level)

        a, grid_a, level = self._read(request.a, request.height)
        b, grid_b, _ = self._read(request.b, request.height)
        resolution = min(geotiff.display_resolution(grid_a), geotiff.display_resolution(grid_b))
        if grid_a.matches(grid_b):
            # same cells: subtract cell by cell, then resample once
            rotated = geotiff.write_rotated(f'/vsimem/{uuid.uuid4().hex}.tif', a - b, grid_a)
            try:
                path = self._publish(rotated, grid_a.epsg, resolution)
            finally:
                _unlink(rotated)
            return path, request.layer_name(level)

        # different grids: resample both onto the same north-up pixels where they overlap
        temporary = []
        try:
            north_up = []
            for data, grid in ((a, grid_a), (b, grid_b)):
                rotated = geotiff.write_rotated(f'/vsimem/{uuid.uuid4().hex}.tif', data, grid)
                temporary.append(rotated)
                warped = geotiff.warp_north_up(rotated, f'/vsimem/{uuid.uuid4().hex}.tif', resolution, grid_a.epsg)
                temporary.append(warped)
                values, gt = geotiff.read_raster(warped)
                north_up.append(geotiff.bounds_of(gt, values.shape[1], values.shape[0]))
            bounds = _snapped_intersection(north_up[0], north_up[1], resolution)
            if bounds is None:
                raise ValueError('Series A and B do not overlap.')
            arrays = []
            for warped in temporary[1::2]:
                aligned = geotiff.warp_north_up(warped, f'/vsimem/{uuid.uuid4().hex}.tif', resolution,
                                                grid_a.epsg, bounds=bounds)
                temporary.append(aligned)
                values, gt = geotiff.read_raster(aligned)
                arrays.append(values)
            difference = geotiff.write_like(f'/vsimem/{uuid.uuid4().hex}.tif', arrays[0] - arrays[1], gt, grid_a.epsg)
            temporary.append(difference)
            path = self._publish(difference, grid_a.epsg, resolution)
        finally:
            for name in temporary:
                _unlink(name)
        return path, request.layer_name(level)

    # ---------------------------------------------------------------- main thread
    def finished(self, result):
        for path, name in self.outputs:
            layer = QgsRasterLayer(path, name, 'gdal')
            if not layer.isValid():
                self.errors.append(f'{name}: the layer could not be loaded')
                continue
            style_result_layer(layer)
            QgsProject.instance().addMapLayer(layer)
            self.layers.append(layer)
        if self.on_finished is not None:
            self.on_finished(self)


def _unlink(path):
    if path.startswith('/vsimem/'):
        from osgeo import gdal
        gdal.Unlink(path)


def _snapped_intersection(first, second, resolution):
    xmin = max(first[0], second[0])
    ymin = max(first[1], second[1])
    xmax = min(first[2], second[2])
    ymax = min(first[3], second[3])
    if xmax - xmin < resolution or ymax - ymin < resolution:
        return None
    width = np.floor((xmax - xmin) / resolution) * resolution
    height = np.floor((ymax - ymin) / resolution) * resolution
    return xmin, ymax - height, xmin + width, ymax


def style_result_layer(layer):
    """Colour ramp from the layer's minimum to maximum (or the custom colour map file)."""
    provider = layer.dataProvider()
    if C_COLOR_SCALE_USE_CUSTOM:
        # A colour map .txt file as exported from the QGIS layer properties
        loading, ramp_shader_items, shader_type, errors \
            = QgsRasterRendererUtils.parseColorMapFile(C_COLOR_SCALE_CUSTOM_PATH)
        ramp_shader = QgsColorRampShader()
        ramp_shader.setColorRampType(shader_type)
        ramp_shader.setColorRampItemList(ramp_shader_items)
    else:
        stats = provider.bandStatistics(1, QgsRasterBandStats.Stats.Min | QgsRasterBandStats.Stats.Max)
        ramp = QgsStyle.defaultStyle().colorRamp(C_COLOR_SCALE_NAME)
        if C_COLOR_SCALE_INVERT:
            ramp.invert()
        mode = get_color_scale_mode()
        ramp_shader = QgsColorRampShader(stats.minimumValue, stats.maximumValue, ramp,
                                         get_color_scale_interpolation(), mode)
        if mode == QgsColorRampShader.ClassificationMode.Quantile:
            ramp_shader.classifyColorRamp(classes=C_COLOR_SCALE_STEPS, band=1, input=provider)
        else:
            ramp_shader.classifyColorRamp(classes=C_COLOR_SCALE_STEPS)
    raster_shader = QgsRasterShader()
    raster_shader.setRasterShaderFunction(ramp_shader)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(provider, 1, raster_shader))
