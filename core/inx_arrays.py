"""Array helpers of the INX export (no QGIS imports).

Gridded layers are north-up arrays with shape (rows, columns): row 0 is the
northernmost row (core.inx turns them into the [i][j] grids of the INX).
"""

import numpy as np


def _text_array(shape, fill, values):
    width = max([len(fill)] + [len(v) for v in values] + [1])
    return np.full(shape, fill, dtype=f'<U{width}')


def map_codes(codes, names_by_code, default=''):
    """Text per cell from integer codes; codes <= 0 or without a name get ``default``.

    The text array is as wide as the longest name, so long names are not cut.
    """
    codes = np.asarray(codes)
    names = [str(v) for v in names_by_code.values()]
    out = _text_array(codes.shape, default, names)
    if not names_by_code or codes.size == 0:
        return out
    size = max(int(codes.max()), max(names_by_code)) + 1
    lookup = _text_array((max(size, 1),), default, names)
    for code, name in names_by_code.items():
        if code > 0:
            lookup[code] = name
    valid = (codes > 0) & (codes < size)
    out[valid] = lookup[codes[valid]]
    return out


def map_values(values, mapping, other=None, default=''):
    """Text per cell from raster values (as text): ``mapping`` value -> ID, else ``other``, else ``default``."""
    values = np.asarray(values)
    fallback = default if other is None else other
    unique, inverse = np.unique(values, return_inverse=True)
    mapped = [mapping.get(str(v), fallback) for v in unique]
    out = _text_array((len(unique),), fallback, mapped)
    out[:] = mapped
    return out[inverse].reshape(values.shape)


def first_non_empty(*layers):
    """Per cell the first non-empty text of the given arrays (priority order)."""
    width = max(layer.dtype.itemsize // 4 for layer in layers) if layers else 1
    out = np.full(layers[0].shape, '', dtype=f'<U{max(width, 1)}')
    for layer in reversed(layers):
        out = np.where(layer != '', layer, out)
    return out


def border_mask(shape, width):
    """True for the cells within ``width`` cells of any edge."""
    rows, columns = shape
    i = np.arange(rows)[:, None]
    j = np.arange(columns)[None, :]
    return (i < width) | (j < width) | (i >= rows - width) | (j >= columns - width)

