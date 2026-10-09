# coding=utf-8
"""Small synthetic ENVI-met result files in the layout ENVI-met writes.

Field values encode where they came from: ``T = 1000 t + 100 k + 10 j + i``
(time step t, level k, row j from the south, column i), so a test can tell
exactly which cell a reader returned.
"""

import math
import os

import numpy as np

NX, NY, NZ = 6, 5, 8
DX = 2.0
DZ = [0.4] * 5 + [2.0, 2.0, 2.0]
SOIL_DEPTHS = [0.01, 0.05, 0.2]
X0, Y0 = 387500.0, 5820000.0
ROTATION = 20.0
ZONE = 33
LATITUDE = 52.5
TERRAIN_COLUMN = (1, 1)      # (j, i) with two terrain cells
BUILDING_COLUMN = (3, 4)     # (j, i) with a building in levels 0..3


def t_value(t, k, j, i):
    return 1000.0 * t + 100.0 * k + 10.0 * j + i


def objects_field():
    """(NZ, NY, NX): 2 terrain, 1 building, 0 air."""
    objects = np.zeros((NZ, NY, NX), dtype=np.int32)
    j, i = TERRAIN_COLUMN
    objects[0:2, j, i] = 2
    j, i = BUILDING_COLUMN
    objects[0:4, j, i] = 1
    return objects


def dem_offset():
    dem = np.zeros((NY, NX), dtype=np.int32)
    dem[TERRAIN_COLUMN] = 2
    return dem


def temperature(t):
    k, j, i = np.meshgrid(np.arange(NZ), np.arange(NY), np.arange(NX), indexing='ij')
    values = t_value(t, k, j, i).astype(np.float32)
    values[objects_field() > 0] = -999.0
    return values


def utci(t):
    j, i = np.meshgrid(np.arange(NY), np.arange(NX), indexing='ij')
    values = (30.0 + t + j + 0.1 * i).astype(np.float32)
    values[BUILDING_COLUMN] = -999.0
    return values


def cell_centres(x0=X0, y0=Y0, rotation=ROTATION, nx=NX, ny=NY, dx=DX):
    x = (np.arange(nx) + 0.5) * dx
    y = (np.arange(ny) + 0.5) * dx
    xx, yy = np.meshgrid(x, y)
    r = math.radians(rotation)
    return x0 + xx * math.cos(r) + yy * math.sin(r), y0 - xx * math.sin(r) + yy * math.cos(r)


def write_netcdf(path, layout='current', rotation=ROTATION, x0=X0, y0=Y0, latitude=LATITUDE, dz=None,
                 with_objects=True):
    """An ENVI-met main output file; ``layout='old'`` mimics files from before the CF update.

    ``dz``: other level thicknesses (as many as DZ), for a run with another vertical grid.
    ``with_objects=False``: 3D data without an Objects field, as in some report files.
    """
    import netCDF4
    dz = DZ if dz is None else dz
    assert len(dz) == NZ
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ds = netCDF4.Dataset(path, 'w', format='NETCDF4')
    try:
        for name, size in (('Time', 2), ('GridsK', NZ), ('GridsJ', NY), ('GridsI', NX),
                           ('SoilLevels', len(SOIL_DEPTHS))):
            ds.createDimension(name, size)
        ds.setncattr('Conventions', 'CF-1.8')
        ds.setncattr('SimulationDate', '06.07.2024')
        ds.setncattr('SimulationTime', '04.00.00')
        ds.setncattr('SizeDX', np.full(NX, DX))
        ds.setncattr('SizeDY', np.full(NY, DX))
        ds.setncattr('SizeDZ', np.array(dz))
        ds.setncattr('ModelRotation', rotation)
        ds.setncattr('GeorefX', x0)
        ds.setncattr('GeorefY', y0)
        ds.setncattr('UTMZone', ZONE)
        ds.setncattr('LocationLatitude', latitude)
        ds.setncattr('LocationLongitude', 13.3)

        time = ds.createVariable('Time', 'f4', ('Time',))
        time.long_name = 'Time'
        if layout == 'old':
            time.units = 'Hours since 2024-07-06 04:00:00 1'
            time[:] = [0.0, 0.9994444]
        else:
            time.units = 'hours since 2024-07-06 04:00:00'
            time[:] = [0.0, 1.0]
        for name, values in (('GridsI', (np.arange(NX) + 0.5) * DX), ('GridsJ', (np.arange(NY) + 0.5) * DX),
                             ('GridsK', np.cumsum(dz) - np.array(dz) / 2)):
            v = ds.createVariable(name, 'f4', (name,))
            v.long_name = 'Meters from Lower Left Corner at Cell Midpoint'
            v[:] = values
        soil = ds.createVariable('SoilLevels', 'f4', ('SoilLevels',))
        soil[:] = SOIL_DEPTHS
        crs = ds.createVariable('crs', 'i4', ())
        crs.epsg_code = f'EPSG:326{ZONE}'

        east, north = cell_centres(x0, y0, rotation)
        if layout == 'old':
            e = ds.createVariable('utm_easting', 'f4', ('GridsI',))
            e.long_name = '2D_projection_x_coordinates'
            e[:] = east[0, :]
            n = ds.createVariable('utm_northing', 'f4', ('GridsJ',))
            n.long_name = '2D_projection_y_coordinates'
            n[:] = north[:, 0]
        else:
            for name, long_name, values in (('utm_easting', 'UTM Easting of Cell Midpoint', east),
                                            ('utm_northing', 'UTM Northing of Cell Midpoint', north),
                                            ('Lat', 'Latitude of Cell Midpoint', np.zeros((NY, NX))),
                                            ('Lon', 'Longitude of Cell Midpoint', np.zeros((NY, NX)))):
                v = ds.createVariable(name, 'f8', ('GridsJ', 'GridsI'))
                v.long_name = long_name
                v[:] = values

        celsius = 'degree Celsius' if layout == 'old' else 'degree_Celsius'

        def data_var(name, long_name, dims, dtype='f4', units=None):
            v = ds.createVariable(name, dtype, dims, fill_value=-999)
            v.long_name = long_name
            if units is not None:
                v.units = units
            return v

        dem = data_var('DEMOffset', 'Terrain Height as Vertical Grid Cell Count', ('Time', 'GridsJ', 'GridsI'), 'i4')
        objects = data_var('Objects', 'Objects', ('Time', 'GridsK', 'GridsJ', 'GridsI'), 'i4') if with_objects else None
        t = data_var('T', 'Air Temperature', ('Time', 'GridsK', 'GridsJ', 'GridsI'), units=celsius)
        u = data_var('UTCIBiomet', 'Universal Thermal Climate Index at Biometeorogical Height Level',
                     ('Time', 'GridsJ', 'GridsI'), units=celsius)
        # two variables sharing a long name, and one with a parenthesis in it
        wx = data_var('WallTempX', 'Wall Temperature', ('Time', 'GridsK', 'GridsJ', 'GridsI'), units=celsius)
        wy = data_var('WallTempY', 'Wall Temperature', ('Time', 'GridsK', 'GridsJ', 'GridsI'), units=celsius)
        pet = data_var('PET', 'PET (Default Person)', ('Time', 'GridsJ', 'GridsI'), units=celsius)
        soil_t = data_var('SoilTemp', 'Soil Temperature', ('Time', 'SoilLevels', 'GridsJ', 'GridsI'), units=celsius)
        for step in range(2):
            dem[step] = dem_offset()
            if objects is not None:
                objects[step] = objects_field()
            t[step] = temperature(step)
            u[step] = utci(step)
            wx[step] = temperature(step) + 1
            wy[step] = temperature(step) + 2
            pet[step] = utci(step) - 1
            soil_t[step] = np.stack([np.full((NY, NX), 20.0 - level) for level in range(len(SOIL_DEPTHS))])
    finally:
        ds.close()
    return path


def write_edx(folder, base='sim_AT_', stamp='2024-07-06_04.59.59', time_text='04.59.59', ring=2,
              t_index=1, initialisation=False, encoding='utf-8'):
    """An atmosphere EDX/EDT pair with ``ring`` nesting cells on each side (EDX files up to ENVI-met 6.0)."""
    os.makedirs(folder, exist_ok=True)
    nx, ny = NX + 2 * ring, NY + 2 * ring
    ring_spacing = [DX * (ring + 1 - n) for n in range(ring)]          # 2*ring+... widest outside
    spacing_x = ring_spacing + [DX] * NX + ring_spacing[::-1]
    spacing_y = ring_spacing + [DX] * NY + ring_spacing[::-1]
    names = [' Objects ( )', 'Air Temperature (°C)', 'UTCI (°C)']

    full = np.full((len(names), NZ, ny, nx), -999.0, dtype=np.float32)
    full[0] = 0.0
    core = (slice(None), slice(ring, ring + NY), slice(ring, ring + NX))
    full[0][core] = objects_field()
    full[1][core] = temperature(t_index)
    full[2][core] = 25.0
    stem = f'{base}{" (initialisation)" if initialisation else ""}{stamp}'
    full.tofile(os.path.join(folder, stem + '.EDT'))

    def join(values):
        return ','.join(f'{v:.5f}' for v in values)

    header = f"""<ENVI-MET_Datafile>
<Header>
<filetype>EDX ENVI-met Simulation Data Definition</filetype>
<version>101</version>
</Header>
  <datadescription>
     <data_type> 2 </data_type>
     <data_content> 1 </data_content>
     <data_spatial_dim> 3 </data_spatial_dim>
     <nr_xdata> {nx} </nr_xdata>
     <nr_ydata> {ny} </nr_ydata>
     <nr_zdata> {NZ} </nr_zdata>
     <spacing_x> {join(spacing_x)} </spacing_x>
     <spacing_y> {join(spacing_y)} </spacing_y>
     <spacing_z> {join(DZ)} </spacing_z>
  </datadescription>
  <variables>
     <Data_per_variable> 1 </Data_per_variable>
     <nr_variables> {len(names)} </nr_variables>
     <name_variables> {','.join(names)} </name_variables>
  </variables>
  <modeldescription>
     <simulation_basename> {base} </simulation_basename>
     <simulation_date> 06.07.2024 </simulation_date>
     <simulation_time> {time_text} </simulation_time>
     <model_rotation> {ROTATION} </model_rotation>
     <location_georef_lat> {LATITUDE} </location_georef_lat>
     <location_georef_lon> 13.3 </location_georef_lon>
     <location_georef_xy_utmzone> {ZONE} </location_georef_xy_utmzone>
     <location_georef_x> {X0} </location_georef_x>
     <location_georef_y> {Y0} </location_georef_y>
  </modeldescription>
</ENVI-MET_Datafile>
"""
    path = os.path.join(folder, stem + '.EDX')
    with open(path, 'w', encoding=encoding) as f:     # ENVI-met 6 writes UTF-8, older versions Windows-1252
        f.write(header)
    return path


SOIL_THICKNESS = [0.02, 0.06, 0.24]        # layer middles at SOIL_DEPTHS, as ENVI-met writes them


def write_soil_edx(folder, stamp='2024-07-06_04.59.59', time_text='04.59.59'):
    """A soil EDX/EDT pair (data_content 3): levels are soil layers, spacing_z their thickness."""
    os.makedirs(folder, exist_ok=True)
    stem = f'sim_SO_{stamp}'
    full = np.stack([np.full((NY, NX), 20.0 - level, dtype=np.float32) for level in range(len(SOIL_THICKNESS))])
    full[np.newaxis].tofile(os.path.join(folder, stem + '.EDT'))
    header = f"""<ENVI-MET_Datafile>
<Header>
<filetype>EDX ENVI-met Simulation Data Definition</filetype>
<version>101</version>
</Header>
  <datadescription>
     <data_type> 2 </data_type>
     <data_content> 3 </data_content>
     <data_spatial_dim> 3 </data_spatial_dim>
     <nr_xdata> {NX} </nr_xdata>
     <nr_ydata> {NY} </nr_ydata>
     <nr_zdata> {len(SOIL_THICKNESS)} </nr_zdata>
     <spacing_x> {','.join(f'{DX:.5f}' for _ in range(NX))} </spacing_x>
     <spacing_y> {','.join(f'{DX:.5f}' for _ in range(NY))} </spacing_y>
     <spacing_z> {','.join(f'{v:.5f}' for v in SOIL_THICKNESS)} </spacing_z>
  </datadescription>
  <variables>
     <Data_per_variable> 1 </Data_per_variable>
     <nr_variables> 1 </nr_variables>
     <name_variables> Temperature (°C) </name_variables>
  </variables>
  <modeldescription>
     <simulation_date> 06.07.2024 </simulation_date>
     <simulation_time> {time_text} </simulation_time>
     <model_rotation> {ROTATION} </model_rotation>
     <location_georef_xy_utmzone> {ZONE} </location_georef_xy_utmzone>
     <location_georef_x> {X0} </location_georef_x>
     <location_georef_y> {Y0} </location_georef_y>
  </modeldescription>
</ENVI-MET_Datafile>
"""
    path = os.path.join(folder, stem + '.EDX')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(header)
    return path


def write_output_folder(root):
    """A simulation output folder: NetCDF, a report file, atmosphere EDX files and files to skip."""
    write_netcdf(os.path.join(root, 'NetCDF', 'sim_001.nc'))
    write_netcdf(os.path.join(root, 'reportData', 'Report_Slice.nc'))
    atmosphere = os.path.join(root, 'atmosphere')
    write_edx(atmosphere, stamp='2024-07-06_04.00.00', time_text='04.00.00', t_index=0, initialisation=True)
    write_edx(atmosphere, stamp='2024-07-06_04.59.59', time_text='04.59.59', t_index=1)
    # a copy of the initialisation and a static input file: both are not time steps
    first = write_edx(atmosphere, base='sim First Flow Field', stamp='', time_text='04.00.00', t_index=0)
    assert os.path.exists(first)
    write_edx(os.path.join(root, 'inputData'), base='model_INXGRID', stamp='', time_text='00.00.00')
    return root
