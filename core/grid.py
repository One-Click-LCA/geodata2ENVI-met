"""Cell indices of the ENVI-met grid.

The plugin grids every layer into north-up rasters with ``jj`` rows: row 0 is the
northernmost row and becomes the first line of every INX matrix. ENVI-met counts
``j`` from the south.
"""


def raster_to_envimet_ij(row, col, jj):
    """1-based ENVI-met (i, j) of the cell at (row, col) of a north-up model raster."""
    return col + 1, jj - row


def raster_to_inx_receptor_cell(row, col, jj):
    """``cell_i``/``cell_j`` of an INX ``<Receptors>`` entry: 0-based.

    SPACES saves receptor cells as ``i - 1``/``j - 1`` and ENVI-met adds 1 when it
    reads them. INX ``<3Dplants>`` root cells, in contrast, are 1-based.
    """
    i, j = raster_to_envimet_ij(row, col, jj)
    return i - 1, j - 1
