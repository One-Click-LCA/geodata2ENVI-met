"""GeoTIFF output of ENVI-met fields.

Needs GDAL's Python bindings (``osgeo``), not QGIS. A field is written once on
its native, rotated grid (a GeoTransform with rotation terms) and then warped
to a north-up raster, which every GIS displays without further processing.
"""

import numpy as np

from .readers import FILL_VALUE

_RESAMPLING = {'nearest': 'near', 'bilinear': 'bilinear', 'cubic': 'cubic'}


def _gdal():
    from osgeo import gdal, ogr, osr
    return gdal, ogr, osr


def _srs(epsg):
    _, _, osr = _gdal()
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg))
    return srs


def write_rotated(path, data, grid, nodata=FILL_VALUE):
    """Write a field (ny, nx), j = 0 south, on its native rotated grid. ``path`` may be /vsimem/..."""
    gdal, _, _ = _gdal()
    values = np.flipud(np.asarray(data, dtype=np.float32))     # row 0 = northern row
    values = np.where(np.isnan(values), np.float32(nodata), values)
    dataset = gdal.GetDriverByName('GTiff').Create(path, grid.nx, grid.ny, 1, gdal.GDT_Float32)
    if dataset is None:
        raise OSError(f'Could not create {path}')
    dataset.SetGeoTransform(grid.geotransform())
    dataset.SetProjection(_srs(grid.epsg).ExportToWkt())
    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(values)
    band.FlushCache()
    dataset = None
    return path


def _cutline_datasource(cutline_wkt, epsg, name):
    """In-memory polygon file for gdal.Warp's cutline."""
    gdal, ogr, _ = _gdal()
    path = f'/vsimem/{name}_cutline.gpkg'
    driver = ogr.GetDriverByName('GPKG')
    source = driver.CreateDataSource(path)
    layer = source.CreateLayer('cutline', _srs(epsg), ogr.wkbUnknown)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(ogr.CreateGeometryFromWkt(cutline_wkt))
    layer.CreateFeature(feature)
    feature = None
    source = None
    return path


def warp_north_up(source, path, resolution, epsg, resampling='bilinear', bounds=None, cutline_wkt=None,
                  nodata=FILL_VALUE):
    """Warp ``source`` to a north-up GeoTIFF at ``resolution`` metres in EPSG ``epsg``.

    :param bounds: (xmin, ymin, xmax, ymax) of the output; default: the source's extent.
    :param cutline_wkt: polygon (in ``epsg``) outside which the output is set to nodata and cropped.
    """
    gdal, _, _ = _gdal()
    cutline = None
    options = dict(format='GTiff', xRes=resolution, yRes=resolution, dstSRS=f'EPSG:{epsg}',
                   resampleAlg=_RESAMPLING[resampling], srcNodata=nodata, dstNodata=nodata,
                   outputType=gdal.GDT_Float32, multithread=True)
    if bounds is not None:
        options['outputBounds'] = bounds
    if cutline_wkt:
        cutline = _cutline_datasource(cutline_wkt, epsg, path.replace('\\', '_').replace('/', '_').replace(':', ''))
        options['cutlineDSName'] = cutline
        options['cropToCutline'] = bounds is None
    try:
        result = gdal.Warp(path, source, options=gdal.WarpOptions(**options))
        if result is None:
            raise OSError(f'gdal.Warp failed for {path}: {gdal.GetLastErrorMsg()}')
        result = None
    finally:
        if cutline:
            gdal.Unlink(cutline)
    return path


def read_raster(path):
    """(array with NaN for nodata, geotransform) of band 1."""
    gdal, _, _ = _gdal()
    dataset = gdal.Open(path)
    band = dataset.GetRasterBand(1)
    values = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        values[values == nodata] = np.nan
    geotransform = dataset.GetGeoTransform()
    dataset = None
    return values, geotransform


def bounds_of(geotransform, width, height):
    """(xmin, ymin, xmax, ymax) of a north-up raster."""
    x0, dx, _, y0, _, dy = geotransform
    xs = (x0, x0 + width * dx)
    ys = (y0, y0 + height * dy)
    return min(xs), min(ys), max(xs), max(ys)


def write_like(path, values, geotransform, epsg, nodata=FILL_VALUE):
    """Write a north-up array with a given geotransform."""
    gdal, _, _ = _gdal()
    values = np.where(np.isnan(values), nodata, values).astype(np.float32)
    dataset = gdal.GetDriverByName('GTiff').Create(path, values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
    dataset.SetGeoTransform(geotransform)
    dataset.SetProjection(_srs(epsg).ExportToWkt())
    band = dataset.GetRasterBand(1)
    band.SetNoDataValue(nodata)
    band.WriteArray(values)
    dataset = None
    return path


def display_resolution(grid, finest=1.0):
    """Resolution of the north-up output: the cell size, but at most ``finest`` metres (as before)."""
    return min(float(np.min(grid.dx)), float(np.min(grid.dy)), finest)
