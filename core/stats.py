"""Area statistics: weighted per zone, variable and time step, plus period summaries.

Weights are the cells' area shares (pedestrian level, m²) or volume shares (height
range, m³) from core.zones. Missing values (NaN) do not count.

Percentiles use the inverted weighted distribution function: the p-th percentile
is the smallest value whose cumulative weight share reaches p.

No QGIS imports.
"""

import csv
import math

import numpy as np

from .readers import KIND_2D, KIND_3D
from .zones import MODE_PEDESTRIAN

PERCENTILES = (5, 25, 50, 75, 95)

# heat-stress class limits (°C)
UTCI_CLASS_LIMITS = (26.0, 32.0, 38.0, 46.0)
PET_CLASS_LIMITS = (23.0, 29.0, 35.0, 41.0)


def class_limits_for(key, long_name=''):
    """Thermal-comfort class limits for UTCI or PET variables, else None."""
    key, long_name = key.upper(), long_name.upper()
    if 'UTCI' in key or 'UNIVERSAL THERMAL CLIMATE' in long_name:
        return UTCI_CLASS_LIMITS
    if key.startswith('PET') or long_name.startswith('PET') or 'PHYSIOLOGICAL EQUIVALENT' in long_name:
        return PET_CLASS_LIMITS
    return None


def class_labels(limits):
    labels = [f'below_{limits[0]:g}']
    labels += [f'{a:g}_to_{b:g}' for a, b in zip(limits[:-1], limits[1:])]
    labels.append(f'above_{limits[-1]:g}')
    return labels


def weighted_stats(values, weights, thresholds=(), class_limits=None):
    """Statistics of ``values`` weighted by ``weights``; NaN values are left out."""
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = ~np.isnan(values) & (weights > 0)
    result = {'n_cells': int(len(values)), 'n_valid': int(valid.sum()), 'weight': 0.0}
    names = ['mean', 'std', 'min'] + [f'p{p:02d}' for p in PERCENTILES] + ['max']
    if not valid.any():
        result.update({name: math.nan for name in names})
        result.update({f'share_above_{x:g}': math.nan for x in thresholds})
        if class_limits:
            result.update({f'share_{label}': math.nan for label in class_labels(class_limits)})
        return result
    v, w = values[valid], weights[valid]
    total = float(w.sum())
    mean = float((w * v).sum() / total)
    result.update({'weight': total, 'mean': mean, 'std': float(math.sqrt((w * (v - mean) ** 2).sum() / total)),
                   'min': float(v.min()), 'max': float(v.max())})
    order = np.argsort(v, kind='stable')
    cumulative = np.cumsum(w[order]) / total
    for p in PERCENTILES:
        index = min(int(np.searchsorted(cumulative, p / 100.0 - 1e-12, side='left')), len(v) - 1)
        result[f'p{p:02d}'] = float(v[order][index])
    for x in thresholds:
        result[f'share_above_{x:g}'] = float(w[v > x].sum() / total)
    if class_limits:
        classes = np.digitize(v, class_limits, right=False)
        for n, label in enumerate(class_labels(class_limits)):
            result[f'share_{label}'] = float(w[classes == n].sum() / total)
    return result


class VariableRequest:
    """A variable to evaluate. ``key`` is read from the file; ``name`` labels the rows and pairs A with B
    (results in another format name the same quantity differently, e.g. "T" and "Air Temperature")."""

    def __init__(self, key, long_name, units, kind, name=None):
        self.key = key
        self.long_name = long_name
        self.units = units
        self.kind = kind
        self.name = name or key


def mask_cells(masks):
    """All cells of all masks, with each mask's slice into them (one read per time step and variable)."""
    j = np.concatenate([m.j for m in masks]) if masks else np.empty(0, dtype=int)
    i = np.concatenate([m.i for m in masks]) if masks else np.empty(0, dtype=int)
    k = np.concatenate([m.k for m in masks]) if masks else np.empty(0, dtype=int)
    slices, start = [], 0
    for m in masks:
        slices.append(slice(start, start + len(m)))
        start += len(m)
    return j, i, k, slices


def time_series(source, masks, variables, mode, level_text, scenario='A', start=None, end=None,
                thresholds=(), comfort_classes=True, progress=None, cancelled=None, values_out=None):
    """Statistics rows for every time step of ``source`` (a readers.Source) between ``start`` and ``end``.

    :param values_out: optional dict filled with {(datetime, variable name): cell values}, for A - B.
    """
    rows = []
    masks = [m for m in masks if len(m)]
    j, i, k, slices = mask_cells(masks)
    steps = [s for s in source.timesteps if (start is None or s.datetime >= start) and (end is None or s.datetime <= end)]
    for n, step in enumerate(steps):
        if cancelled is not None and cancelled():
            break
        result = source.open(step.path)
        for var in variables:
            if var.key not in result.variables or not len(i):
                continue
            kind = result.variables[var.key].kind
            if kind == KIND_3D:
                values = result.read_cells(var.key, step.index, j, i, k)
            elif kind == KIND_2D:
                values = result.read_cells(var.key, step.index, j, i)
            else:
                continue
            if values_out is not None:
                values_out[(step.datetime, var.name)] = values
            limits = class_limits_for(var.key, var.long_name) if comfort_classes else None
            for mask, part in zip(masks, slices):
                stats = weighted_stats(values[part], mask.weight, thresholds, limits)
                rows.append(_row(scenario, source.name, mask, var, level_text, step.datetime, stats, mode))
        if progress is not None:
            progress(100.0 * (n + 1) / max(1, len(steps)))
    return rows


def difference_series(values_a, values_b, masks, variables, mode, level_text, thresholds=()):
    """A - B per cell for cells valid in both, for runs on the same grid (same masks)."""
    rows = []
    masks = [m for m in masks if len(m)]
    _, _, _, slices = mask_cells(masks)
    for (moment, name), a in sorted(values_a.items(), key=lambda item: (item[0][0], item[0][1])):
        b = values_b.get((moment, name))
        if b is None:
            continue
        var = next((v for v in variables if v.name == name), None)
        if var is None:
            continue
        difference = a - b
        for mask, part in zip(masks, slices):
            stats = weighted_stats(difference[part], mask.weight, thresholds)
            rows.append(_row('A-B', 'A-B', mask, var, level_text, moment, stats, mode))
    return rows


def mean_differences(rows_a, rows_b):
    """A - B of the area means, for runs on different grids (no cell-by-cell pairing)."""
    index = {(r['zone_id'], r['variable'], r['datetime']): r for r in rows_b}
    rows = []
    for r in rows_a:
        other = index.get((r['zone_id'], r['variable'], r['datetime']))
        if other is None:
            continue
        row = {key: r[key] for key in ('zone_id', 'zone_name', 'variable', 'unit', 'level', 'datetime', 'date',
                                       'hour')}
        row.update(scenario='A-B', source='A-B (difference of means)',
                   mean=r['mean'] - other['mean'] if not (math.isnan(r['mean']) or math.isnan(other['mean']))
                   else math.nan)
        rows.append(row)
    return rows


def _row(scenario, source_name, mask, var, level_text, moment, stats, mode):
    row = {'scenario': scenario, 'source': source_name, 'zone_id': mask.zone.zone_id, 'zone_name': mask.zone.name,
           'variable': var.name, 'long_name': var.long_name, 'unit': var.units, 'level': level_text,
           'datetime': moment.strftime('%Y-%m-%d %H:%M'), 'date': moment.strftime('%Y-%m-%d'),
           'hour': moment.hour + moment.minute / 60.0}
    weight = stats.pop('weight')
    row.update({'n_cells': stats.pop('n_cells'), 'n_valid': stats.pop('n_valid')})
    row['area_m2' if mode == MODE_PEDESTRIAN else 'volume_m3'] = round(weight, 3)
    row.update(stats)
    return row


def diurnal_cycle(rows):
    """Hour-of-day means of the area means over all days (the mean diurnal cycle)."""
    groups = {}
    for r in rows:
        if 'mean' not in r or math.isnan(r['mean']):
            continue
        key = (r['scenario'], r['zone_id'], r['zone_name'], r['variable'], r.get('unit', ''), r['level'], r['hour'])
        groups.setdefault(key, []).append(r['mean'])
    result = []
    for key, means in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        scenario, zone_id, zone_name, variable, unit, level, hour = key
        result.append({'scenario': scenario, 'zone_id': zone_id, 'zone_name': zone_name, 'variable': variable,
                       'unit': unit, 'level': level, 'hour': hour, 'mean': float(np.mean(means)),
                       'min_of_days': float(np.min(means)), 'max_of_days': float(np.max(means)), 'n_days': len(means)})
    return result


def daily_summary(rows):
    """Per day the minimum, mean and maximum of the area means."""
    groups = {}
    for r in rows:
        if 'mean' not in r or math.isnan(r['mean']):
            continue
        key = (r['scenario'], r['zone_id'], r['zone_name'], r['variable'], r.get('unit', ''), r['level'], r['date'])
        groups.setdefault(key, []).append(r['mean'])
    result = []
    for key, means in sorted(groups.items(), key=lambda item: tuple(str(x) for x in item[0])):
        scenario, zone_id, zone_name, variable, unit, level, date = key
        result.append({'scenario': scenario, 'zone_id': zone_id, 'zone_name': zone_name, 'variable': variable,
                       'unit': unit, 'level': level, 'date': date, 'min': float(np.min(means)),
                       'mean': float(np.mean(means)), 'max': float(np.max(means)), 'n_steps': len(means)})
    return result


def write_csv(path, rows, columns=None, delimiter=','):
    """UTF-8 with BOM (opens correctly in spreadsheet programs); NaN as empty cells."""
    if columns is None:
        columns = []
        for r in rows:
            for key in r:
                if key not in columns:
                    columns.append(key)
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(columns)
        for r in rows:
            values = r if isinstance(r, (list, tuple)) else [r.get(c, '') for c in columns]
            writer.writerow(['' if isinstance(v, float) and math.isnan(v) else
                             (round(v, 6) if isinstance(v, float) else v) for v in values])
    return path
