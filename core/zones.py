"""Analysis areas ("zones") as cell masks of the ENVI-met grid.

A zone is one or more polygons in the grid's UTM coordinates. Its mask lists the
model cells it covers:

* horizontally with the exact share of each cell's area inside the polygons
  (``fraction``; cells cut by the boundary count partly);
* vertically either at the pedestrian level (per column the cell ENVI-met uses as
  biometeorological reference height, terrain top + 1.5 m) or in a height range
  above the local ground, where a cell counts with the share of its height inside
  the range;
* only atmosphere cells: building and terrain cells are left out, also above a
  roof the range reaches over.

No QGIS imports.
"""

import json
import math

import numpy as np

from .readers import BUILDING_ID, TERRAIN_ID

MODE_PEDESTRIAN = 'pedestrian'
MODE_RANGE = 'range'
PEDESTRIAN_HEIGHT = 1.5


class Zone:
    """An analysis area: polygons as (outer ring, [hole rings]); rings are (n, 2) arrays in UTM metres."""

    def __init__(self, zone_id, name, polygons):
        self.zone_id = zone_id
        self.name = name
        self.polygons = [(np.asarray(outer, dtype=float), [np.asarray(h, dtype=float) for h in holes])
                         for outer, holes in polygons]

    def area(self):
        return sum(abs(_shoelace(outer)) - sum(abs(_shoelace(h)) for h in holes) for outer, holes in self.polygons)


class ZoneMask:
    """The cells of one zone. Arrays have one entry per cell; ``k`` is -1 for 2D masks."""

    def __init__(self, zone, j, i, k, fraction, vertical_fraction, weight, columns_with_cells):
        self.zone = zone
        self.j = j
        self.i = i
        self.k = k
        self.fraction = fraction
        self.vertical_fraction = vertical_fraction
        self.weight = weight
        self.columns_with_cells = columns_with_cells

    def __len__(self):
        return len(self.i)


class StaticFields:
    """What the masks need to know about the model: terrain, objects and the pedestrian level.

    :param dem: (ny, nx) number of terrain cells per column
    :param dz: (nz,) cell heights
    :param objects: (nz, ny, nx) Objects field, or None (2D files)
    :param reported_biomet_k: (ny, nx) 0-based biomet level the file reports (ZNodeBiomet - 1), or None.
        Only for comparison: the pedestrian level is always ENVI-met's current rule (see
        pedestrian_levels); files from 5.8 and older report other levels, e.g. on top of roofs.
    :param air_2d: (ny, nx) bool, for 2D files without Objects: where the pedestrian level is air
    :param has_levels: the file has 3D variables, also without an Objects field (e.g. some report
        files). Then every cell counts as air in the masks; cells inside buildings or terrain drop
        out of the statistics through their missing values.
    """

    def __init__(self, dem, dz, objects=None, reported_biomet_k=None, air_2d=None, has_levels=False):
        self.dem = np.asarray(dem, dtype=int)
        self.dz = np.asarray(dz, dtype=float)
        self.objects = objects
        self.reported_biomet_k = reported_biomet_k
        self.air_2d = air_2d
        self.has_levels = has_levels

    @property
    def is_3d(self):
        return self.objects is not None or self.has_levels

    def level_bottoms(self):
        return np.concatenate([[0.0], np.cumsum(self.dz)[:-1]])

    def pedestrian_levels(self):
        """0-based level of the pedestrian cell per column (ny, nx), following the terrain."""
        return pedestrian_levels(self.dem, self.dz)

    def biomet_level_mismatch(self):
        """Share of open (building-free) columns where the file reports another biomet level, or None."""
        if self.reported_biomet_k is None or self.objects is None:
            return None
        open_columns = ~(np.rint(self.objects) == BUILDING_ID).any(axis=0)
        if not open_columns.any():
            return None
        differs = np.asarray(self.reported_biomet_k) != self.pedestrian_levels()
        return float(differs[open_columns].mean())

    def is_air(self, k, j, i):
        if self.objects is None:
            if self.has_levels or self.air_2d is None:
                return np.ones(len(i), dtype=bool)
            return self.air_2d[j, i]
        value = np.rint(self.objects[k, j, i]).astype(int)
        return (value != BUILDING_ID) & (value != TERRAIN_ID)


def pedestrian_levels(dem, dz, height=PEDESTRIAN_HEIGHT):
    """Per column the level whose centre is closest to terrain top + ``height``, at or above the terrain.

    ENVI-met's rule for its biometeorological reference level.
    """
    dz = np.asarray(dz, dtype=float)
    bottoms = np.concatenate([[0.0], np.cumsum(dz)[:-1]])
    centres = bottoms + dz / 2
    dem = np.asarray(dem, dtype=int)
    top = bottoms[np.clip(dem, 0, len(dz) - 1)]
    distance = np.abs(centres[:, None, None] - (top + height)[None, :, :])
    below = np.arange(len(dz))[:, None, None] < dem[None, :, :]
    distance[below] = np.inf
    return np.argmin(distance, axis=0)


# --------------------------------------------------------------------------------------------
# Horizontal: exact area fractions
# --------------------------------------------------------------------------------------------

def to_model(grid, east, north):
    """UTM -> model coordinates (m from the lower-left corner, along the model axes)."""
    r = math.radians(grid.rotation)
    c, s = math.cos(r), math.sin(r)
    de = np.asarray(east, dtype=float) - grid.x0
    dn = np.asarray(north, dtype=float) - grid.y0
    return de * c - dn * s, de * s + dn * c


def _shoelace(points):
    if len(points) < 3:
        return 0.0
    # relative to the first point: UTM coordinates (~1e6 m) would cost the products their precision
    x, y = points[:, 0] - points[0, 0], points[:, 1] - points[0, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _clip(points, axis, value, keep_greater):
    """Sutherland-Hodgman step: the part of a polygon on one side of the line ``coord[axis] = value``."""
    if len(points) == 0:
        return points
    coord = points[:, axis]
    inside = coord >= value if keep_greater else coord <= value
    out = []
    n = len(points)
    for idx in range(n):
        current, previous = points[idx], points[idx - 1]
        current_in, previous_in = inside[idx], inside[idx - 1]
        if current_in != previous_in:
            t = (value - previous[axis]) / (current[axis] - previous[axis])
            out.append(previous + t * (current - previous))
        if current_in:
            out.append(current)
    return np.array(out) if out else np.empty((0, 2))


def _ring(points):
    points = np.asarray(points, dtype=float)
    if len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    return points


def _inside(px, py, rings):
    """Even-odd point-in-polygon test of points against all rings (outer rings and holes)."""
    inside = np.zeros(px.shape, dtype=bool)
    for ring in rings:
        x1, y1 = ring[:, 0], ring[:, 1]
        x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
        for a, b, c, d in zip(x1, y1, x2, y2):
            if b == d:
                continue
            crosses = (b > py) != (d > py)
            x_cross = a + (py - b) * (c - a) / (d - b)
            inside ^= crosses & (px < x_cross)
    return inside


def _boundary_cells(rings, dx, dy, nx, ny):
    """Cells within one cell of any ring edge (a superset of the cells the boundary crosses)."""
    cells = set()
    step = min(dx, dy) / 4.0
    for ring in rings:
        closed = np.vstack([ring, ring[:1]])
        for (x1, y1), (x2, y2) in zip(closed[:-1], closed[1:]):
            n = max(1, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / step)))
            t = np.linspace(0.0, 1.0, n + 1)
            ci = np.floor((x1 + t * (x2 - x1)) / dx).astype(int)
            cj = np.floor((y1 + t * (y2 - y1)) / dy).astype(int)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    cells.update(zip((cj + dj).tolist(), (ci + di).tolist()))
    return {(j, i) for j, i in cells if 0 <= j < ny and 0 <= i < nx}


def cell_fractions(grid, zone):
    """Exact share of each cell's area inside the zone: (j, i, fraction) for cells with fraction > 0."""
    if not grid.is_uniform():
        raise ValueError('Area masks need an equidistant horizontal grid.')
    dx, dy = float(grid.dx[0]), float(grid.dy[0])
    nx, ny = grid.nx, grid.ny
    cell_area = dx * dy
    fractions = np.zeros((ny, nx))
    for outer, holes in zone.polygons:
        rings = []
        for ring in [outer] + list(holes):
            x, y = to_model(grid, ring[:, 0], ring[:, 1])
            rings.append(_ring(np.column_stack([x, y])))
        outer_ring, hole_rings = rings[0], rings[1:]
        if len(outer_ring) < 3:
            continue
        # cells of the polygon's bounding box
        i0 = max(0, int(math.floor(outer_ring[:, 0].min() / dx)))
        i1 = min(nx, int(math.floor(outer_ring[:, 0].max() / dx)) + 1)
        j0 = max(0, int(math.floor(outer_ring[:, 1].min() / dy)))
        j1 = min(ny, int(math.floor(outer_ring[:, 1].max() / dy)) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        # cells no edge comes near are wholly inside or outside: decide by their centre
        jj, ii = np.mgrid[j0:j1, i0:i1]
        inside = _inside((ii + 0.5) * dx, (jj + 0.5) * dy, rings)
        part = inside.astype(float)
        # cells near an edge: exact area of polygon and cell, clipping each ring to the row first
        boundary = sorted(_boundary_cells(rings, dx, dy, nx, ny))
        rows = {}
        for j, i in boundary:
            if j0 <= j < j1 and i0 <= i < i1:
                rows.setdefault(j, []).append(i)
        for j, columns in rows.items():
            strips = []
            for n, ring in enumerate(rings):
                strip = _clip(_clip(ring, 1, j * dy, True), 1, (j + 1) * dy, False)
                strips.append((strip, 1.0 if n == 0 else -1.0))
            for i in columns:
                area = 0.0
                for strip, sign in strips:
                    if len(strip) < 3:
                        continue
                    piece = _clip(_clip(strip, 0, i * dx, True), 0, (i + 1) * dx, False)
                    area += sign * abs(_shoelace(piece))
                part[j - j0, i - i0] = min(1.0, max(0.0, area / cell_area))
        fractions[j0:j1, i0:i1] += part
    fractions = np.clip(fractions, 0.0, 1.0)
    j, i = np.nonzero(fractions > 1e-9)
    return j, i, fractions[j, i]


# --------------------------------------------------------------------------------------------
# Masks
# --------------------------------------------------------------------------------------------

def build_mask(grid, zone, static, mode=MODE_PEDESTRIAN, z_min=0.0, z_max=0.0):
    """The cells of ``zone``: horizontal fractions times the vertical selection, atmosphere only."""
    j, i, fraction = cell_fractions(grid, zone)
    dx, dy = float(grid.dx[0]), float(grid.dy[0])
    if not static.is_3d or mode == MODE_PEDESTRIAN:
        if static.is_3d:
            k = static.pedestrian_levels()[j, i]
        else:
            k = np.full(len(i), -1, dtype=int)
        air = static.is_air(k, j, i)
        j, i, k, fraction = j[air], i[air], k[air], fraction[air]
        vertical = np.ones(len(i))
        weight = fraction * dx * dy
        return ZoneMask(zone, j, i, k, fraction, vertical, weight, len(set(zip(j.tolist(), i.tolist()))))

    if mode != MODE_RANGE:
        raise ValueError(f'unknown vertical mode {mode!r}')
    if z_max <= z_min:
        raise ValueError('The height range needs a maximum above its minimum.')
    bottoms = static.level_bottoms()
    tops = bottoms + static.dz
    ground = bottoms[np.clip(static.dem[j, i], 0, len(static.dz) - 1)]
    cells_j, cells_i, cells_k, cells_f, cells_v = [], [], [], [], []
    for k in range(len(static.dz)):
        low = np.maximum(bottoms[k] - ground, z_min)
        high = np.minimum(tops[k] - ground, z_max)
        overlap = np.clip(high - low, 0.0, None)
        use = overlap > 1e-9
        if not use.any():
            continue
        kk = np.full(int(use.sum()), k, dtype=int)
        air = static.is_air(kk, j[use], i[use])
        cells_j.append(j[use][air])
        cells_i.append(i[use][air])
        cells_k.append(kk[air])
        cells_f.append(fraction[use][air])
        cells_v.append(overlap[use][air] / static.dz[k])
    if cells_i:
        j, i, k = np.concatenate(cells_j), np.concatenate(cells_i), np.concatenate(cells_k)
        fraction, vertical = np.concatenate(cells_f), np.concatenate(cells_v)
    else:
        j = i = k = np.empty(0, dtype=int)
        fraction = vertical = np.empty(0)
    weight = fraction * dx * dy * vertical * static.dz[k] if len(k) else np.empty(0)
    order = np.lexsort((k, i, j))
    return ZoneMask(zone, j[order], i[order], k[order], fraction[order], vertical[order], weight[order],
                    len(set(zip(j.tolist(), i.tolist()))))


# --------------------------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------------------------

CELL_COLUMNS = ['zone_id', 'zone_name', 'i', 'j', 'k', 'i_em', 'j_em', 'k_em', 'x_m', 'y_m', 'z_agl_m', 'dz_m',
                'utm_e', 'utm_n', 'lat', 'lon', 'fraction', 'vertical_fraction', 'weight']


def cell_rows(grid, static, mask, latlon=None):
    """Rows of the cells CSV for one mask.

    ``latlon`` is a function (east, north) -> (lat, lon) arrays, or None to leave them empty.
    """
    x, y = grid.model_coordinates()
    east, north = grid.cell_centres()
    j, i, k = mask.j, mask.i, mask.k
    utm_e, utm_n = east[j, i], north[j, i]
    lat, lon = latlon(utm_e, utm_n) if latlon is not None and len(i) else (None, None)
    if static.is_3d and len(k):
        bottoms = static.level_bottoms()
        ground = bottoms[np.clip(static.dem[j, i], 0, len(static.dz) - 1)]
        z_agl = bottoms[k] + static.dz[k] / 2 - ground
        dz = static.dz[k]
    else:
        z_agl = dz = None
    rows = []
    for n in range(len(i)):
        three_d = static.is_3d and k[n] >= 0
        rows.append([
            mask.zone.zone_id, mask.zone.name, int(i[n]), int(j[n]), int(k[n]) if three_d else '',
            int(i[n]) + 1, int(j[n]) + 1, int(k[n]) + 1 if three_d else '',
            round(float(x[i[n]]), 3), round(float(y[j[n]]), 3),
            round(float(z_agl[n]), 3) if three_d else '', round(float(dz[n]), 3) if three_d else '',
            round(float(utm_e[n]), 3), round(float(utm_n[n]), 3),
            round(float(lat[n]), 8) if lat is not None else '', round(float(lon[n]), 8) if lon is not None else '',
            round(float(mask.fraction[n]), 6), round(float(mask.vertical_fraction[n]), 6),
            round(float(mask.weight[n]), 6)])
    return rows


ZONE_COLUMNS = ['zone_id', 'zone_name', 'polygon_area_m2', 'air_area_m2', 'n_columns', 'n_cells']


def zone_row(grid, mask):
    """polygon area, the part of it with at least one listed cell, and counts."""
    cell_area = float(grid.dx[0]) * float(grid.dy[0])
    columns = {}
    for j, i, f in zip(mask.j.tolist(), mask.i.tolist(), mask.fraction.tolist()):
        columns[(j, i)] = f
    return [mask.zone.zone_id, mask.zone.name, round(mask.zone.area(), 3),
            round(sum(columns.values()) * cell_area, 3), len(columns), len(mask)]


def grid_signature(grid):
    return {
        'nx': grid.nx, 'ny': grid.ny, 'dx': float(grid.dx[0]), 'dy': float(grid.dy[0]),
        'x0': grid.x0, 'y0': grid.y0, 'rotation': grid.rotation, 'epsg': grid.epsg,
    }


def write_grid_json(path, grid, info):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'grid': grid_signature(grid), **info}, f, indent=2, default=str)
