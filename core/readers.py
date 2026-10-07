"""Readers for ENVI-met result files.

* NetCDF: the main output (``<output>/NetCDF/*.nc``) and the report files
  (``<output>/reportData/Report*.nc``).
* EDX/EDT: a text header (EDX) and a binary data file (EDT) per time step,
  in one folder per kind of data (``atmosphere``, ``surface``, ...).

2D arrays are returned with shape (ny, nx), index ``[j, i]``, where j = 0 is the
southern row, as in ENVI-met and in the NetCDF files. Missing values (-999)
are returned as NaN.

No QGIS imports. netCDF4 is imported only when a NetCDF file is opened.
"""

import datetime as dt
import math
import os
import re
import warnings

import numpy as np

from .units import display_unit

FILL_VALUE = -999.0
BUILDING_ID = 1
TERRAIN_ID = 2

KIND_3D = 'atmosphere'   # GridsK, GridsJ, GridsI
KIND_2D = 'surface'      # GridsJ, GridsI
KIND_SOIL = 'soil'       # SoilLevels, GridsJ, GridsI

# coordinate variables of the NetCDF files; never offered as data
NETCDF_COORDINATES = {'Time', 'GridsI', 'GridsJ', 'GridsK', 'SoilLevels', 'crs', 'Lat', 'Lon',
                      'utm_easting', 'utm_northing'}


def _netcdf4():
    with warnings.catch_warnings():
        # benign ABI warning when netCDF4 was built against another numpy
        warnings.filterwarnings('ignore', message='numpy.ndarray size changed', category=RuntimeWarning)
        import netCDF4
    return netCDF4


def round_to_minute(moment):
    """ENVI-met writes times like 04:59:59 for 05:00; round to the nearest minute."""
    seconds = moment.second + moment.microsecond / 1e6
    moment = moment.replace(second=0, microsecond=0)
    if seconds >= 30:
        moment += dt.timedelta(minutes=1)
    return moment


def parse_date_time(date_text, time_text):
    """'06.07.2024' and '04.59.59' (or '04:59:59') -> datetime."""
    day, month, year = (int(v) for v in re.split(r'[./-]', date_text.strip())[:3])
    parts = [int(float(v)) for v in re.split(r'[.:]', time_text.strip()) if v != '']
    hour, minute, second = (parts + [0, 0, 0])[:3]
    return dt.datetime(year, month, day, hour, minute, second)


def level_for_height(dz, height):
    """Index of the vertical cell containing ``height`` (m above its column's lowest cell) and its bounds.

    A height on a boundary belongs to the lower cell; heights above the model top give the top cell.
    """
    bottom = 0.0
    for k, size in enumerate(dz):
        top = bottom + float(size)
        if height <= top or k == len(dz) - 1:
            return k, (bottom, top)
        bottom = top
    return 0, (0.0, 0.0)


def terrain_cells(objects):
    """Number of terrain cells at the bottom of each column of an Objects field (nz, ny, nx)."""
    terrain = np.rint(objects) == TERRAIN_ID
    not_terrain = ~terrain
    first_air = np.argmax(not_terrain, axis=0)
    # columns that are terrain all the way up
    first_air[~not_terrain.any(axis=0)] = objects.shape[0]
    return first_air.astype(int)


class Variable:
    """A data variable of a result file."""

    def __init__(self, key, long_name, units, kind):
        self.key = key
        self.long_name = long_name or key
        self.units = units or ''
        self.kind = kind

    @property
    def display_units(self):
        return display_unit(self.units)

    def label(self):
        """'Air Temperature [T]' (NetCDF) or 'Air Temperature' (EDX, whose key is the name)."""
        if self.long_name == self.key:
            return self.long_name
        return f'{self.long_name} [{self.key}]'


class Grid:
    """Horizontal (and vertical) grid of the core model area.

    The model area turns clockwise by ``rotation`` degrees about its lower-left
    corner (x0, y0): E = x0 + x cos R + y sin R, N = y0 - x sin R + y cos R.
    """

    def __init__(self, dx, dy, x0, y0, rotation, utm_zone, latitude, dz=None, epsg=None):
        self.dx = np.asarray(dx, dtype=float)
        self.dy = np.asarray(dy, dtype=float)
        self.dz = None if dz is None else np.asarray(dz, dtype=float)
        self.x0 = float(x0)
        self.y0 = float(y0)
        self.rotation = float(rotation)
        self.utm_zone = int(utm_zone)
        self.latitude = float(latitude)
        self._epsg = epsg

    @property
    def nx(self):
        return len(self.dx)

    @property
    def ny(self):
        return len(self.dy)

    @property
    def southern(self):
        return self.latitude < 0

    @property
    def epsg(self):
        if self._epsg:
            return int(self._epsg)
        return (32700 if self.southern else 32600) + self.utm_zone

    def is_uniform(self, tolerance=1e-4):
        return (np.ptp(self.dx) <= tolerance) and (np.ptp(self.dy) <= tolerance)

    def geotransform(self):
        """GDAL geotransform of the grid stored north-up (row 0 = northern row), with rotation."""
        if not self.is_uniform():
            raise ValueError('The horizontal grid is not equidistant.')
        dx, dy = float(self.dx[0]), float(self.dy[0])
        height = float(self.dy.sum())
        r = math.radians(self.rotation)
        c, s = math.cos(r), math.sin(r)
        return (self.x0 + height * s, dx * c, -dy * s,
                self.y0 + height * c, -dx * s, -dy * c)

    def model_coordinates(self):
        """Cell midpoints in model coordinates (m from the lower-left corner): x (nx,), y (ny,)."""
        return np.cumsum(self.dx) - self.dx / 2, np.cumsum(self.dy) - self.dy / 2

    def cell_centres(self):
        """UTM easting and northing of every cell midpoint, each (ny, nx), j = 0 south."""
        x, y = self.model_coordinates()
        xx, yy = np.meshgrid(x, y)
        r = math.radians(self.rotation)
        c, s = math.cos(r), math.sin(r)
        return self.x0 + xx * c + yy * s, self.y0 - xx * s + yy * c

    def matches(self, other, tolerance=1e-3):
        """Same cells at the same place (so arrays can be subtracted cell by cell)."""
        return (other is not None and self.nx == other.nx and self.ny == other.ny and self.epsg == other.epsg
                and np.allclose(self.dx, other.dx, atol=tolerance) and np.allclose(self.dy, other.dy, atol=tolerance)
                and abs(self.x0 - other.x0) <= tolerance and abs(self.y0 - other.y0) <= tolerance
                and abs(self.rotation - other.rotation) <= 1e-6)


class ResultFile:
    """Common interface of NetCDF and EDX/EDT result files."""

    def __init__(self, path):
        self.path = path
        self.grid = None
        self.times = []
        self.variables = {}

    def close(self):
        pass

    def read(self, key, time_index=0, height=0.0):
        """2D field of variable ``key`` at a time index.

        3D variables are read at ``height`` metres above the local ground, following the
        terrain. Returns (array (ny, nx) with NaN for missing values, description of the level).
        """
        raise NotImplementedError

    def dem_offset(self, time_index=0):
        """Number of terrain cells below the first atmosphere cell, (ny, nx)."""
        raise NotImplementedError

    def _terrain_following(self, read_levels, time_index, height):
        """Read a 3D variable at ``height`` above ground with ``read_levels(k0, k1) -> (k1-k0, ny, nx)``."""
        k, (bottom, top) = level_for_height(self.grid.dz, height)
        nz = len(self.grid.dz)
        levels = np.clip(self.dem_offset(time_index) + k, 0, nz - 1)
        k0, k1 = int(levels.min()), int(levels.max()) + 1
        block = read_levels(k0, k1)
        data = np.take_along_axis(block, (levels - k0)[np.newaxis, :, :], axis=0)[0]
        return data, f'{round(bottom, 3)}m-{round(top, 3)}m'


def _as_float(data):
    data = np.array(data, dtype=float)
    data[data <= FILL_VALUE + 0.5] = np.nan
    return data


class NetcdfFile(ResultFile):
    """An ENVI-met NetCDF file: main output or report file, old or current layout."""

    def __init__(self, path):
        super().__init__(path)
        netcdf4 = _netcdf4()
        self._ds = netcdf4.Dataset(path, mode='r')
        self._ds.set_auto_mask(False)
        ds = self._ds
        attrs = set(ds.ncattrs())

        dx = np.atleast_1d(ds.getncattr('SizeDX')).astype(float)
        dy = np.atleast_1d(ds.getncattr('SizeDY')).astype(float)
        if 'SizeDZ' in attrs:
            dz = np.atleast_1d(ds.getncattr('SizeDZ')).astype(float)
        elif 'GridsK' in ds.variables:
            dz = self._dz_from_centres(np.array(ds.variables['GridsK'][:], dtype=float))
        else:
            dz = None
        # The EPSG code follows from zone and latitude, as in ENVI-met's NetCDF writer. The crs
        # variable's epsg_code is not used: files converted from EDX say 326xx in both hemispheres.
        self.grid = Grid(dx=dx, dy=dy, x0=ds.getncattr('GeorefX'), y0=ds.getncattr('GeorefY'),
                         rotation=ds.getncattr('ModelRotation'), utm_zone=ds.getncattr('UTMZone'),
                         latitude=ds.getncattr('LocationLatitude'), dz=dz)

        start = parse_date_time(ds.getncattr('SimulationDate'), ds.getncattr('SimulationTime'))
        if 'Time' in ds.variables:
            hours = np.atleast_1d(np.array(ds.variables['Time'][:], dtype=float))
        else:
            hours = np.zeros(1)
        # one entry per index of the Time dimension; None for entries that were never written
        # (some runs left the first one at the netCDF fill value)
        self.times = [round_to_minute(start + dt.timedelta(hours=float(h)))
                      if np.isfinite(h) and 0 <= h < 1e6 else None for h in hours]

        for name, var in ds.variables.items():
            if name in NETCDF_COORDINATES:
                continue
            dims = var.dimensions
            if ('GridsJ' not in dims) or ('GridsI' not in dims):
                continue
            if 'GridsK' in dims:
                kind = KIND_3D
            elif 'SoilLevels' in dims:
                kind = KIND_SOIL
            else:
                kind = KIND_2D
            var_attrs = var.ncattrs()
            long_name = str(var.getncattr('long_name')) if 'long_name' in var_attrs else name
            units = str(var.getncattr('units')) if 'units' in var_attrs else ''
            self.variables[name] = Variable(name, long_name, units, kind)
        self._dem_cache = {}

    @staticmethod
    def _dz_from_centres(centres):
        dz = np.empty_like(centres)
        bottom = 0.0
        for k, centre in enumerate(centres):
            dz[k] = 2 * (centre - bottom)
            bottom += dz[k]
        return dz

    def close(self):
        if self._ds is not None:
            self._ds.close()
            self._ds = None

    def _time_slice(self, var, time_index):
        return (min(time_index, var.shape[0] - 1),) if var.dimensions[:1] == ('Time',) else ()

    def has_utm_fields(self):
        """True for files with 2D cell-midpoint coordinates (written since ENVI-met's CF update)."""
        v = self._ds.variables
        return 'utm_easting' in v and v['utm_easting'].dimensions == ('GridsJ', 'GridsI')

    def utm_fields(self):
        return (np.array(self._ds.variables['utm_easting'][:], dtype=float),
                np.array(self._ds.variables['utm_northing'][:], dtype=float))

    def placement_error(self):
        """Largest distance (m) between the grid's cell midpoints and the file's own UTM midpoints.

        None for files without 2D UTM fields.
        """
        if not self.has_utm_fields():
            return None
        east, north = self.utm_fields()
        grid_east, grid_north = self.grid.cell_centres()
        return float(np.hypot(grid_east - east, grid_north - north).max())

    def dem_offset(self, time_index=0):
        if time_index in self._dem_cache:
            return self._dem_cache[time_index]
        variables = self._ds.variables
        if 'DEMOffset' in variables:
            var = variables['DEMOffset']
            dem = np.array(var[self._time_slice(var, time_index)], dtype=int)
            dem[dem < 0] = 0
        elif 'Objects' in variables:
            var = variables['Objects']
            dem = terrain_cells(np.array(var[self._time_slice(var, time_index)]))
        else:
            dem = np.zeros((self.grid.ny, self.grid.nx), dtype=int)
        self._dem_cache[time_index] = dem
        return dem

    def soil_depths(self):
        if 'SoilLevels' in self._ds.variables:
            return np.array(self._ds.variables['SoilLevels'][:], dtype=float)
        return None

    def read(self, key, time_index=0, height=0.0):
        var = self._ds.variables[key]
        kind = self.variables[key].kind
        t = self._time_slice(var, time_index)
        if kind == KIND_3D:
            data, description = self._terrain_following(
                lambda k0, k1: np.array(var[t + (slice(k0, k1),)]), time_index, height)
        elif kind == KIND_SOIL:
            depths = self.soil_depths()
            level = int(np.argmin(np.abs(depths - abs(height)))) if depths is not None else 0
            data = np.array(var[t + (level,)])
            description = f'{depths[level]:g}m depth' if depths is not None else f'level {level}'
        else:
            data = np.array(var[t])
            description = ''
        return _as_float(data), description


def read_edx_header(path):
    """Tag -> text of an EDX header (first occurrence of each tag)."""
    with open(path, 'rb') as f:
        text = f.read().decode('cp1252', errors='replace')
    tags = {}
    for match in re.finditer(r'<([A-Za-z0-9_\-]+)>([^<]*)</\1>', text):
        tags.setdefault(match.group(1), match.group(2).strip())
    return tags


def _core_slice(spacing):
    """Slice of the core cells: drops leading/trailing nesting cells, which are wider than the core.

    ENVI-met's nesting cells are 2..N+1 times the core spacing; EDX files up to 6.0 may contain them.
    """
    spacing = np.asarray(spacing, dtype=float)
    values, counts = np.unique(np.round(spacing, 4), return_counts=True)
    core = values[np.argmax(counts)]
    inside = np.flatnonzero(np.abs(spacing - core) <= 1e-3)
    return slice(int(inside[0]), int(inside[-1]) + 1)


class EdxFile(ResultFile):
    """One time step of EDX/EDT output."""

    def __init__(self, path):
        super().__init__(path)
        tags = read_edx_header(path)
        self.header = tags
        self.nx = int(tags['nr_xdata'])
        self.ny = int(tags['nr_ydata'])
        self.nz = int(tags['nr_zdata'])
        self.values_per_cell = int(tags.get('Data_per_variable', 1))
        spacing_x = [float(v) for v in tags['spacing_x'].split(',')]
        spacing_y = [float(v) for v in tags['spacing_y'].split(',')]
        spacing_z = [float(v) for v in tags['spacing_z'].split(',')] if tags.get('spacing_z') else [1.0]
        self.core_x = _core_slice(spacing_x)
        self.core_y = _core_slice(spacing_y)
        self.grid = Grid(dx=spacing_x[self.core_x], dy=spacing_y[self.core_y],
                         x0=float(tags.get('location_georef_x', 0)), y0=float(tags.get('location_georef_y', 0)),
                         rotation=float(tags.get('model_rotation', 0)),
                         utm_zone=int(float(tags.get('location_georef_xy_utmzone', 0))),
                         latitude=float(tags.get('location_georef_lat', 0)), dz=spacing_z)
        self.times = [round_to_minute(parse_date_time(tags['simulation_date'], tags['simulation_time']))]
        self.names = [n.strip() for n in tags.get('name_variables', '').split(',')]
        kind = KIND_3D if self.nz > 1 else KIND_2D
        self._index = {}
        for index, raw in enumerate(self.names):
            key = raw.split('(', 1)[0].strip()
            units = raw.split('(', 1)[1].rsplit(')', 1)[0].strip() if '(' in raw else ''
            if not key or key in self.variables:
                continue
            self._index[key] = index
            self.variables[key] = Variable(key, key, units, kind)
        base, _ = os.path.splitext(path)
        self.edt_path = base + ('.EDT' if path.endswith('.EDX') else '.edt')
        self._dem = None

    def _read_levels(self, index, k0, k1):
        """Values of variable number ``index`` for levels k0..k1-1 on the full grid: (k1-k0, ny, nx)."""
        layer = self.nx * self.ny * self.values_per_cell
        offset = (index * self.nz + k0) * layer * 4
        data = np.fromfile(self.edt_path, dtype=np.float32, count=(k1 - k0) * layer, offset=offset)
        return data.reshape(k1 - k0, self.ny, self.nx, self.values_per_cell)[..., 0]

    def _full_dem_offset(self):
        if self._dem is None:
            index = self._index.get('Objects')
            if index is None or self.nz == 1:
                self._dem = np.zeros((self.ny, self.nx), dtype=int)
            else:
                self._dem = terrain_cells(self._read_levels(index, 0, self.nz))
        return self._dem

    def dem_offset(self, time_index=0):
        return self._full_dem_offset()[self.core_y, self.core_x]

    def read(self, key, time_index=0, height=0.0):
        index = self._index[key]
        if self.nz > 1:
            k, (bottom, top) = level_for_height(self.grid.dz, height)
            levels = np.clip(self._full_dem_offset() + k, 0, self.nz - 1)
            k0, k1 = int(levels.min()), int(levels.max()) + 1
            block = self._read_levels(index, k0, k1)
            data = np.take_along_axis(block, (levels - k0)[np.newaxis, :, :], axis=0)[0]
            description = f'{round(bottom, 3)}m-{round(top, 3)}m'
        else:
            data = self._read_levels(index, 0, 1)[0]
            description = ''
        return _as_float(data[self.core_y, self.core_x]), description


def open_result_file(path):
    if path.lower().endswith('.nc'):
        return NetcdfFile(path)
    return EdxFile(path)


# ----------------------------------------------------------------------------------------------
# Finding the result files of a simulation
# ----------------------------------------------------------------------------------------------

class Timestep:
    def __init__(self, moment, path, index):
        self.datetime = moment
        self.path = path
        self.index = index


class Source:
    """A time series of result files of one kind, e.g. the main NetCDF output or the atmosphere EDX files."""

    def __init__(self, name, paths):
        self.name = name
        self.paths = sorted(paths)
        self.errors = []          # (path, message) of files that could not be read
        self._files = {}
        self._timesteps = None

    def open(self, path):
        result = self._files.get(path)
        if result is None:
            result = open_result_file(path)
            self._files[path] = result
        return result

    def close(self):
        for result in self._files.values():
            result.close()
        self._files.clear()

    @property
    def timesteps(self):
        """Time steps in time order; a time that appears in several files is taken from the first."""
        if self._timesteps is None:
            seen = {}
            for path in self.paths:
                try:
                    if path.lower().endswith('.nc'):
                        for index, moment in enumerate(self.open(path).times):
                            if moment is not None:
                                seen.setdefault(moment, Timestep(moment, path, index))
                    else:
                        tags = read_edx_header(path)
                        moment = round_to_minute(parse_date_time(tags['simulation_date'], tags['simulation_time']))
                        seen.setdefault(moment, Timestep(moment, path, 0))
                except Exception as error:   # not an ENVI-met result file, or damaged
                    self.errors.append((path, f'{type(error).__name__}: {error}'))
            self._timesteps = [seen[m] for m in sorted(seen)]
        return self._timesteps

    def first_file(self):
        return self.open(self.timesteps[0].path) if self.timesteps else None


_EDX_TIME = re.compile(r'^(.*?)(?:\s*\(initiali[sz]ation\))?\s*\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}$')


def _edx_groups(folder):
    """EDX files with an EDT next to them, grouped by name without the time stamp."""
    try:
        names = os.listdir(folder)
    except OSError:
        return {}
    lower = {n.lower() for n in names}
    groups = {}
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() != '.edx' or (stem + '.edt').lower() not in lower:
            continue
        if 'first flow field' in stem.lower():
            continue  # a copy of the initialisation, not a time step
        match = _EDX_TIME.match(stem)
        if match is None:
            continue  # static files (e.g. the INX grid) have no time stamp
        groups.setdefault(match.group(1).rstrip(), []).append(os.path.join(folder, name))
    return groups


def find_sources(folder):
    """Sources in an ENVI-met output folder, in one of its subfolders, or in a folder of loose files.

    The main NetCDF output comes first, then report files, then EDX folders.
    """
    sources = []
    if not folder or not os.path.isdir(folder):
        return sources

    def add_netcdf(directory, label_prefix=''):
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            return
        main = [os.path.join(directory, n) for n in names
                if n.lower().endswith('.nc') and not n.lower().startswith('report')]
        if main:
            sources.append(Source(label_prefix + 'NetCDF', main))
        for n in names:
            if n.lower().endswith('.nc') and n.lower().startswith('report'):
                sources.append(Source(label_prefix + os.path.splitext(n)[0], [os.path.join(directory, n)]))

    add_netcdf(folder)
    for sub in ('NetCDF', 'reportData'):
        path = os.path.join(folder, sub)
        if os.path.isdir(path):
            add_netcdf(path)

    edx_folders = [folder]
    for root, dirs, _files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d.lower() not in ('inputdata', 'netcdf', 'reportdata', 'log'))
        if root != folder:
            edx_folders.append(root)
    for directory in edx_folders:
        groups = _edx_groups(directory)
        relative = os.path.relpath(directory, folder).replace('\\', '/')
        for prefix, paths in sorted(groups.items()):
            label = 'EDX' if relative == '.' else relative
            if len(groups) > 1:
                label += f' {prefix}'
            sources.append(Source(f'{label} (EDX)', paths))
    return sources
