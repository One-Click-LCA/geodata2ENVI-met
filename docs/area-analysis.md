# Area analysis

Statistics of ENVI-met results over analysis areas you draw in QGIS: hot spots,
a courtyard, a square, the footpaths of a street. For every area and time step
the plugin computes the weighted mean, spread, percentiles and, for UTCI and
PET, the share of the area in each heat-stress class.

## How to run it

1. Draw the areas as polygons in a new layer, in any coordinate system. Add an
   ID field if you want one result per area; without an ID all polygons form
   one area called `all`. An optional name field labels the areas. IDs that
   are numbers stay numbers; text IDs are kept as written, so `01` and `1` are
   two areas.
2. Either click **Area statistics...** in the *Load results* tab (it takes over
   series A and B and the selected variable), or open the Processing toolbox,
   group **ENVI-met > Area analysis**:
   * **Area statistics (time series)**: the statistics and the cell lists;
   * **Build area masks**: only the cell lists, plus a preview layer of the
     cells coloured by the share of each cell inside its area.
3. Choose the results (an ENVI-met output folder, where *Results to use* picks
   the NetCDF output, a report file or EDX files, or a single result file),
   the variables (default: UTCI), the vertical selection and, optionally, a
   time window, thresholds and a second set of results B for a comparison.

The dialog of the plugin does not block QGIS, so you can draw or edit the
areas while it is open.

## Which cells count

* **Partly covered cells count partly.** A cell that lies one third inside an
  area counts one third; the share is computed exactly from the polygons.
  Polygons with the same ID are merged first, so overlaps inside an area do
  not count twice; different areas may overlap.
* **Only atmosphere cells.** Cells inside buildings or terrain are not in the
  cell list at all.
* **Pedestrian level** (default): in every column the cell whose centre is
  closest to the terrain surface + 1.5 m. This is ENVI-met's own
  biometeorological reference level (the `...Biomet` fields). It follows the
  terrain, not roofs: columns with a building are left out.
* **Height range**: all atmosphere cells between two heights above the local
  ground. A cell counts with the share of its height inside the range, so
  results are volume-weighted. Where the range reaches above a roof, the air
  cells above the roof count like any other. 2D fields (for example
  `UTCIBiomet`) can only be evaluated at the pedestrian level. 3D UTCI and PET
  exist only in the lowest 11 cells above the ground; above, they are missing.

## Output files

All files are UTF-8 CSV (comma or semicolon) and start with the chosen prefix.

| File | Content |
|---|---|
| `_statistics.csv` | One row per scenario, area, variable and time step: `n_cells`, `n_valid`, `area_m2` (or `volume_m3`), `mean`, `std`, `min`, `p05`, `p25`, `p50`, `p75`, `p95`, `max`, shares above the thresholds, and heat-stress class shares for UTCI (limits 26/32/38/46 °C) and PET (23/29/35/41 °C). Times are local standard time, as in ENVI-met. |
| `_diurnal.csv` | The mean diurnal cycle: hour-of-day means of the area means over all days. |
| `_daily.csv` | Per day the minimum, mean and maximum of the area means. |
| `_cells.csv` | The cells of every area, see below. |
| `_zones.csv` | Per area: polygon area, the part of it with at least one listed cell, number of columns and cells. |
| `_grid.json` | The grid the cells refer to, the source files and the settings. |

With results B, the statistics contain the scenarios `A`, `B` and `A-B`. When
both runs have the same grid, the same vertical levels and the same terrain,
`A-B` is computed cell by cell over the cells valid in both runs (different
buildings are fine); otherwise it is the difference of the area means.

B's variables are found by name: the same key, the same long name (NetCDF
`T` is called *Air Temperature*, as in the EDX files), or the same name
without spaces and punctuation (NetCDF `UTCIBiomet` and EDX `UTCI Biomet`).
Where the two formats name a quantity too differently for that, name B's
variables under *Variables in B*, in the same order. The rows of B and A-B
carry A's name.

Percentiles are the smallest value whose cumulative weight reaches the
percentile (inverted weighted distribution function).

### The cells file

| Column | Meaning |
|---|---|
| `zone_id`, `zone_name` | the area |
| `i`, `j`, `k` | 0-based indices of the NetCDF dimensions `GridsI`, `GridsJ`, `GridsK` (`j = 0` is the southern row); `k` is empty for 2D results |
| `i_em`, `j_em`, `k_em` | the same, 1-based as in ENVI-met |
| `x_m`, `y_m` | cell centre in metres from the model's lower-left corner, along the model axes |
| `z_agl_m`, `dz_m` | centre height above the local ground and cell height |
| `utm_e`, `utm_n`, `lat`, `lon` | cell centre |
| `fraction` | share of the cell's area inside the area |
| `vertical_fraction` | share of the cell's height inside the height range (1 at the pedestrian level) |
| `weight` | `fraction` x cell area (m²); in a height range x the height inside the range (m³) |

An external script can weight any field of the NetCDF output with these
cells, for example the area mean of UTCI per time step:

```python
import csv
import netCDF4
import numpy as np

with open('areas_cells.csv', encoding='utf-8-sig') as f:
    cells = list(csv.DictReader(f))
ds = netCDF4.Dataset('NetCDF/simulation_001.nc')
utci = ds.variables['UTCIBiomet'][:]          # masked array, -999 is masked
for zone in sorted({c['zone_id'] for c in cells}):
    own = [c for c in cells if c['zone_id'] == zone]
    j = np.array([int(c['j']) for c in own])
    i = np.array([int(c['i']) for c in own])
    w = np.array([float(c['weight']) for c in own])
    for t in range(utci.shape[0]):
        values = utci[t, j, i]
        valid = ~np.ma.getmaskarray(values)
        print(zone, t, float((values[valid] * w[valid]).sum() / w[valid].sum()))
```

For 3D variables take `k` as well (`T[t, k, j, i]`). Missing values are −999
(`_FillValue`), for example 3D UTCI above its 11 cells; leave them out as above.

## Notes

* Results from ENVI-met 5.8 and older place their `...Biomet` fields at another
  level in some columns (on roofs, for example); the analysis warns and uses
  the terrain-following pedestrian cells for 3D variables.
* EDX/EDT results that contain the nesting area are cropped to the core area.
