"""The Create simulation tab and the content of a SIMX file (core.simx), in both directions."""

import copy
import os
from collections import OrderedDict

import numpy as np
from qgis.PyQt.QtCore import QDate, Qt, QTime

from .core import modules
from .core import simx as core_simx

# The UI works in degrees Celsius, ENVI-met in Kelvin (offset as the plugin always used it).
KELVIN_OFFSET = 273.14999

# Radiation page, IVS resolution box: (height angle hi-res, height angle lo-res, azimuth hi-res, azimuth lo-res)
IVS_PRESETS = [(-1, -1, -1, -1), (30, 45, 30, 45), (15, 30, 15, 30), (15, 15, 15, 15), (10, 10, 10, 10),
               (5, 5, 5, 5), (2, 2, 2, 2)]

# ENVI-met 6 defaults of the model-wide indoor climate (as ENVI-guide)
INDOOR_DEFAULTS = {'naturalVentilation': 2, 'indoorMode': 1, 'defaultBuildingUse': 0,
                   'indoorLowerC': 20.0, 'indoorUpperC': 26.0}


def _section(simulation, name):
    section = simulation.get(name)
    if not isinstance(section, dict):
        section = OrderedDict()
        simulation[name] = section
    return section


def _checked(button):
    return button.isChecked()


def model_from_ui(dlg, base=None, json_format=True, fox_name=None):
    """The simulation as shown in the tab. ``base`` is a loaded simulation whose other settings are kept.

    ``fox_name`` is the name a module's FOX file is saved under; by default the selected file's name.
    """
    simulation = copy.deepcopy(base) if base else OrderedDict()
    simulation.pop('Header', None)

    main = _section(simulation, 'mainData')
    name = dlg.le_fullSimName.text().strip()
    qtime = dlg.te_startTimeSim.time()
    main.update(simName=name, INXFile=dlg.le_inxForSim.text().strip(), filebaseName=name,
                outDir=dlg.le_outputFolderSim.text().strip(), startDate=dlg.lb_selectedDateSim.text(),
                startTime=f'{qtime.hour():02d}:{qtime.minute():02d}:00', simDuration=dlg.sb_simDur.value())
    simulation['Parallel'] = OrderedDict(CPUDemand='ALL' if _checked(dlg.rb_multiCore) else '1')

    code = simulation_type(dlg)
    if code == modules.HOLISTIC:
        simulation.pop('SimModule', None)
        _meteorology(dlg, simulation, main, json_format)
        _optional_sections(dlg, simulation, json_format)
    else:
        # a module run reads mainData and SimModule only
        for section in modules.UNUSED_SECTIONS:
            simulation.pop(section, None)
        if code in modules.CODES:
            simulation['SimModule'] = modules.build_section(code, module_values(dlg, fox_name),
                                                            simulation.get('SimModule'))
        # any other module comes from a loaded file the plugin cannot edit and stays as it was

    if json_format:
        for section in core_simx.RETIRED_V6['sections']:
            simulation.pop(section, None)
        for section, keys in core_simx.RETIRED_V6['keys'].items():
            for key in keys:
                if isinstance(simulation.get(section), dict):
                    simulation[section].pop(key, None)
    else:
        # ENVI-met up to 5.8 still reads these; they are not on the pages any more
        main.setdefault('T_H', 293.15)
        main.setdefault('Q_H', 8.0)
        main.setdefault('Q_2m', 50.0)
    return simulation


def _meteorology(dlg, simulation, main, json_format):
    """Simple or full forcing."""
    loaded_full = simulation.get('FullForcing')
    for section in ('SimpleForcing', 'FullForcing', 'LBC', 'Clouds'):
        simulation.pop(section, None)
    if _checked(dlg.rb_fullForcing):
        # keeps the full forcing settings the tab does not show
        full = simulation['FullForcing'] = loaded_full if isinstance(loaded_full, dict) else OrderedDict()
        full.update(fileName=dlg.le_selectedFOX.text().strip(), forceT=_checked(dlg.rb_forceT_yes),
                    forceQ=_checked(dlg.rb_forceHum_yes), forceWind=_checked(dlg.rb_forceWind_yes),
                    forcePrecip=_checked(dlg.rb_forcePrec_yes), forceRadClouds=_checked(dlg.rb_forceRadC_yes))
        full.setdefault('forceBackgrConc', False)
        if not json_format:
            for key, value in (('interpolationMethod', 0), ('nudging', False), ('nudgingFactor', 1.0),
                               ('minFlowsteps', 50), ('limitWind2500', False), ('maxWind2500', 999.0),
                               ('z_0', 0.1)):
                full.setdefault(key, value)
        if not full['forceT']:
            main['T_H'] = dlg.sb_initT.value() + KELVIN_OFFSET
        if not full['forceWind']:
            main.update(windSpeed=dlg.sb_constWS_FUFo.value(), windDir=dlg.sb_constWD_FuFo.value(),
                        z0=dlg.sb_rlength_FuFo.value())
        if not full['forceRadClouds']:
            simulation['Clouds'] = OrderedDict(lowClouds=dlg.sb_lowclouds_2.value(),
                                               middleClouds=dlg.sb_mediumclouds.value(),
                                               highClouds=dlg.sb_highclouds_2.value())
        if not full['forceQ']:
            main['Q_2m'] = dlg.sb_relHum.value()
    else:
        simulation['Clouds'] = OrderedDict(lowClouds=dlg.sb_lowclouds.value(), middleClouds=dlg.sb_midclouds.value(),
                                           highClouds=dlg.sb_highclouds.value())
        main.update(windSpeed=dlg.sb_windspeed.value(), windDir=dlg.sb_winddir.value(), z0=dlg.sb_rlength.value())
        table = dlg.tableWidget
        simulation['SimpleForcing'] = OrderedDict(
            TAir=[float(table.item(hour, 0).text()) + KELVIN_OFFSET for hour in range(24)],
            Qrel=[float(table.item(hour, 1).text()) for hour in range(24)])


def _optional_sections(dlg, simulation, json_format):
    _optional(simulation, dlg.chk_soilSim.isChecked(), ['Soil'], lambda: _soil(dlg, simulation, json_format))
    _optional(simulation, dlg.chk_buildingsSim.isChecked(), ['indoorSettings', 'Building'],
              lambda: _indoor(dlg, simulation, json_format))
    _optional(simulation, dlg.chk_pollutantsSim.isChecked(), ['Sources', 'Background'],
              lambda: _pollutants(dlg, simulation))
    _optional(simulation, dlg.chk_radiationSim.isChecked(), ['RadScheme', 'SolarAdjust'],
              lambda: _radiation(dlg, simulation))
    _optional(simulation, dlg.chk_outputSim.isChecked(), ['OutputSettings'], lambda: _output(dlg, simulation))
    _optional(simulation, dlg.chk_expertSim.isChecked(), ['TThread'], lambda: _expert(dlg, simulation))


def _optional(simulation, enabled, sections, fill):
    if enabled:
        fill()
    else:
        for section in sections:
            simulation.pop(section, None)


def _soil(dlg, simulation, json_format):
    soil = _section(simulation, 'Soil')
    soil.update(waterUpperlayer=dlg.sb_soilHumUpper.value(), waterMiddlelayer=dlg.sb_soilHumMiddle.value(),
                waterDeeplayer=dlg.sb_soilHumLower.value(), waterBedrockLayer=dlg.sb_soilHumBedrock.value())
    if not json_format:
        for key in ('tempUpperlayer', 'tempMiddlelayer', 'tempDeeplayer', 'tempBedrockLayer'):
            soil.setdefault(key, 293.15)


def _indoor(dlg, simulation, json_format):
    if json_format:
        simulation.pop('Building', None)
        simulation['indoorSettings'] = OrderedDict(
            naturalVentilation=dlg.cb_naturalVentilation.currentIndex(),
            defaultBuildingUse=dlg.cb_indoorUse.currentIndex(), indoorMode=dlg.cb_indoorMode.currentIndex(),
            indoorLowerC=dlg.sb_indoorLower.value(), indoorUpperC=dlg.sb_indoorUpper.value())
    else:
        # ENVI-met up to 5.8 has no indoor climate model; its building section keeps its defaults
        simulation.pop('indoorSettings', None)
        building = _section(simulation, 'Building')
        for key, value in (('surfaceTemp', 293.15), ('indoorTemp', 293.15), ('indoorConst', False),
                           ('airConHeat', False)):
            building.setdefault(key, value)


def _pollutants(dlg, simulation):
    sources = _section(simulation, 'Sources')
    sources.update(userPolluName=dlg.le_userPolluName.text().strip(), userPolluType=dlg.cb_userPolluType.currentIndex(),
                   userPartDiameter=dlg.sb_praticleDia.value(), userPartDensity=dlg.sb_particleDens.value(),
                   multipleSources=True, activeChem=True)
    sources.setdefault('isoprene', False)
    background = _section(simulation, 'Background')
    background.update(userSpec=dlg.sb_userPollu.value(), NO=dlg.sb_NO.value(), NO2=dlg.sb_NO2.value(),
                      O3=dlg.sb_ozone.value(), PM_10=dlg.sb_PM10.value(), PM_2_5=dlg.sb_PM25.value())


def _radiation(dlg, simulation):
    hi_height, lo_height, hi_azimuth, lo_azimuth = IVS_PRESETS[max(0, dlg.cb_resIVS.currentIndex())]
    scheme = _section(simulation, 'RadScheme')
    scheme.update(IVSHeightAngle_HiRes=hi_height, IVSAziAngle_HiRes=hi_azimuth, IVSHeightAngle_LoRes=lo_height,
                  IVSAziAngle_LoRes=lo_azimuth)
    for key, value in (('AdvCanopyRadTransfer', True), ('ViewFacUpdateInterval', 7),
                       ('RayTraceStepWidthHighRes', 0.25), ('RayTraceStepWidthLowRes', 0.5),
                       ('RadiationHeightBoundary', 10.0), ('MRTCalcMethod', 1), ('MRTProjFac', 2)):
        scheme.setdefault(key, value)
    _section(simulation, 'SolarAdjust').setdefault('SWFactor', 1.0)


def _output(dlg, simulation):
    output = _section(simulation, 'OutputSettings')
    output.update(mainFiles=dlg.sb_outputIntOther.value(), textFiles=dlg.sb_outputIntRecBld.value(),
                  netCDF=True, inclNestingGrids=False,
                  writeBuildings=dlg.cb_outputBldData.isChecked(), writeRadiation=dlg.cb_outputRadData.isChecked(),
                  writeSoil=dlg.cb_outputSoilData.isChecked(), writeVegetation=dlg.cb_outputVegData.isChecked())
    for key, value in (('writeAgents', False), ('writeAtmosphere', True), ('writeObjects', False),
                       ('writeGreenpass', False), ('writeNesting', False), ('writeSolarAccess', True),
                       ('writeSurface', True)):
        output.setdefault(key, value)


def _expert(dlg, simulation):
    thread = _section(simulation, 'TThread')
    thread['UseTThread_CallMain'] = not _checked(dlg.rb_threadingMain)
    thread.setdefault('TThreadPRIO', 4)     # tpHigher, as ENVI-guide


# --------------------------------------------------------------------------------------------
# Simulation type and modules
# --------------------------------------------------------------------------------------------

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
# ENVI-guide's defaults for the statistics period: June to September, 06:00 to 20:00
STATS_DEFAULTS = {'startMonth': 6, 'endMonth': 9, 'startHour': 6, 'endHour': 20}

OPTIONAL_TABS = (('chk_soilSim', 'tab_Soil'), ('chk_radiationSim', 'tab_Radiation'),
                 ('chk_buildingsSim', 'tab_Buildings_2'), ('chk_pollutantsSim', 'tab_Pollutants'),
                 ('chk_outputSim', 'tab_Output'), ('chk_expertSim', 'tab_Expert'))


def setup_module_widgets(dlg):
    """Fill the simulation type and module combo boxes (once, when the dialog is built)."""
    for code, text in modules.CHOICES:
        dlg.cb_simType.addItem(text, code)
    for box in (dlg.cb_statsStartMonth, dlg.cb_statsEndMonth):
        box.addItems(MONTHS)
    for box in (dlg.cb_statsStartHour, dlg.cb_statsEndHour):
        box.addItems([f'{hour:02d}:00' for hour in range(24)])


def clear_module_page(dlg):
    while dlg.cb_simType.count() > len(modules.CHOICES):       # a module kept from a loaded file
        dlg.cb_simType.removeItem(dlg.cb_simType.count() - 1)
    dlg.cb_simType.setCurrentIndex(0)
    dlg.de_solarDate.setDate(QDate(QDate.currentDate().year(), 7, 1))
    dlg.lw_solarDates.clear()
    dlg.sb_moduleWindDir.setValue(90)
    dlg.sb_moduleWindSpeed.setValue(2.0)
    dlg.le_moduleFox.setText('')
    dlg.chk_moduleAverageWind.setChecked(False)
    _set_stats_period(dlg, STATS_DEFAULTS)


def _set_stats_period(dlg, values):
    def index(key, low, high):
        try:
            value = int(values.get(key, STATS_DEFAULTS[key]))
        except (TypeError, ValueError):
            value = STATS_DEFAULTS[key]
        return min(max(value, low), high)
    dlg.cb_statsStartMonth.setCurrentIndex(index('startMonth', 1, 12) - 1)
    dlg.cb_statsEndMonth.setCurrentIndex(index('endMonth', 1, 12) - 1)
    dlg.cb_statsStartHour.setCurrentIndex(index('startHour', 0, 23))
    dlg.cb_statsEndHour.setCurrentIndex(index('endHour', 0, 23))


def simulation_type(dlg):
    return dlg.cb_simType.currentData() or modules.HOLISTIC


def is_module(dlg):
    return simulation_type(dlg) != modules.HOLISTIC


def solar_dates(dlg):
    return [dlg.lw_solarDates.item(row).text() for row in range(dlg.lw_solarDates.count())]


def add_solar_dates(dlg, dates):
    present = set(solar_dates(dlg))
    for date in dates:
        if date not in present:
            dlg.lw_solarDates.addItem(date)
            present.add(date)


def module_values(dlg, fox_name=None):
    """ModuleData values shown on the Module page. ``fox_name`` replaces the selected FOX file's path."""
    code = simulation_type(dlg)
    fox = dlg.le_moduleFox.text().strip()
    fox = fox_name if fox_name is not None else os.path.basename(fox)
    if code == modules.SOLAR_ACCESS:
        return {'solarAccessDates': ','.join(solar_dates(dlg))}
    if code == modules.WIND_FLOW:
        return {'windSpeed': float(dlg.sb_moduleWindSpeed.value()), 'windDir': int(dlg.sb_moduleWindDir.value())}
    if code == modules.WIND_COMFORT:
        return {'forcingFile': fox}
    if code == modules.FAST_UTCI:
        return {'forcingFile': fox, 'useAverageWindFromForcing': dlg.chk_moduleAverageWind.isChecked()}
    if code == modules.FAST_UTCI_STATS:
        return {'forcingFile': fox, 'startMonth': dlg.cb_statsStartMonth.currentIndex() + 1,
                'endMonth': dlg.cb_statsEndMonth.currentIndex() + 1,
                'startHour': dlg.cb_statsStartHour.currentIndex(), 'endHour': dlg.cb_statsEndHour.currentIndex()}
    return {}


def module_problems(dlg):
    """What keeps the selected module from running (empty for the holistic simulation)."""
    code = simulation_type(dlg)
    if code not in modules.CODES:
        return []
    return modules.problems(code, module_values(dlg, fox_name=dlg.le_moduleFox.text().strip()))


def update_module_page(dlg):
    """Show the selected module's page; a module run does not use the meteorology or the advanced settings."""
    code = simulation_type(dlg)
    module = code != modules.HOLISTIC
    dlg.sw_module.setCurrentIndex(modules.CODES.index(code) if code in modules.CODES else 0)
    dlg.gb_moduleFox.setVisible(code in modules.FOX_MODULES)
    dlg.tab_Module.setEnabled(module)
    dlg.tab_Meteo.setEnabled(not module)
    dlg.gb_optional.setEnabled(not module)
    update_optional_tabs(dlg)


def update_optional_tabs(dlg):
    module = is_module(dlg)
    for check, tab in OPTIONAL_TABS:
        getattr(dlg, tab).setEnabled(getattr(dlg, check).isChecked() and not module)


def _show_module(dlg, simulation, simx_dir):
    """Select the simulation's type and fill the Module page. Returns notes."""
    code = modules.module_name(simulation)
    data = modules.module_data(simulation)
    index = dlg.cb_simType.findData(code)
    if index < 0:
        dlg.cb_simType.addItem(f'Module {code} (from the loaded file, kept unchanged)', code)
        index = dlg.cb_simType.count() - 1
    dlg.cb_simType.setCurrentIndex(index)
    if code not in modules.CODES:
        return [f'The file sets up the ENVI-met module {code}, which the plugin cannot edit; saving keeps it '
                f'unchanged unless you choose another simulation type.']
    if code == modules.SOLAR_ACCESS:
        add_solar_dates(dlg, modules.solar_dates(data.get('solarAccessDates', '')))
    elif code == modules.WIND_FLOW:
        _set(dlg.sb_moduleWindSpeed, data.get('windSpeed'))
        _set_int(dlg.sb_moduleWindDir, data.get('windDir'))
    if code in modules.FOX_MODULES:
        fox = str(data.get('forcingFile', '') or '')
        if fox and simx_dir and not os.path.isabs(fox):
            fox = os.path.join(simx_dir, fox)      # ENVI-guide keeps the FOX next to the SIMX
        dlg.le_moduleFox.setText(fox)
    if code == modules.FAST_UTCI:
        dlg.chk_moduleAverageWind.setChecked(bool(data.get('useAverageWindFromForcing', False)))
    if code == modules.FAST_UTCI_STATS:
        _set_stats_period(dlg, data)
    return []


# --------------------------------------------------------------------------------------------
# File -> tab
# --------------------------------------------------------------------------------------------

def ui_from_model(dlg, simulation, simx_dir=None):
    """Show a simulation in the tab. Returns notes about settings the tab cannot show.

    ``simx_dir`` is the loaded file's folder, against which a module's FOX file name is resolved.
    """
    notes = []
    main = simulation.get('mainData', {})
    date = QDate.fromString(str(main.get('startDate', '')), 'dd.MM.yyyy')
    if date.isValid():
        dlg.calendar_startDateSim.setSelectedDate(date)
        dlg.lb_selectedDateSim.setText(date.toString('dd.MM.yyyy'))
    time = QTime.fromString(str(main.get('startTime', '')).strip()[:5], 'HH:mm')
    if time.isValid():
        dlg.te_startTimeSim.setTime(time)
    if 'simDuration' in main:
        dlg.sb_simDur.setValue(int(main['simDuration']))
    dlg.le_fullSimName.setText(str(main.get('simName', '')))
    dlg.le_outputFolderSim.setText(str(main.get('outDir', '')))
    dlg.le_inxForSim.setText(str(main.get('INXFile', '')))
    cpu = str(simulation.get('Parallel', {}).get('CPUDemand', 'ALL')).upper()
    (dlg.rb_multiCore if cpu == 'ALL' else dlg.rb_singleCore).setChecked(True)

    kelvin = KELVIN_OFFSET
    clouds = simulation.get('Clouds', {})
    if 'SimpleForcing' in simulation:
        dlg.rb_simpleForcing.setChecked(True)
        forcing = simulation['SimpleForcing']
        _set_simple_forcing(dlg, forcing.get('TAir', []), forcing.get('Qrel', []))
        _set(dlg.sb_windspeed, main.get('windSpeed'))
        _set(dlg.sb_winddir, main.get('windDir'))
        _set(dlg.sb_rlength, main.get('z0'))
        _set_int(dlg.sb_lowclouds, clouds.get('lowClouds'))
        _set_int(dlg.sb_midclouds, clouds.get('middleClouds'))
        _set_int(dlg.sb_highclouds, clouds.get('highClouds'))
    elif 'FullForcing' in simulation:
        dlg.rb_fullForcing.setChecked(True)
        full = simulation['FullForcing']
        dlg.le_selectedFOX.setText(str(full.get('fileName', '')))
        for key, yes, no in (('forceT', dlg.rb_forceT_yes, dlg.rb_forceT_no),
                             ('forceQ', dlg.rb_forceHum_yes, dlg.rb_forceHum_no),
                             ('forceWind', dlg.rb_forceWind_yes, dlg.rb_forceWind_no),
                             ('forcePrecip', dlg.rb_forcePrec_yes, dlg.rb_forcePrec_no),
                             ('forceRadClouds', dlg.rb_forceRadC_yes, dlg.rb_forceRadC_no)):
            (yes if full.get(key, True) else no).setChecked(True)
        if 'T_H' in main:
            _set(dlg.sb_initT, main['T_H'] - kelvin)
        _set(dlg.sb_constWS_FUFo, main.get('windSpeed'))
        _set(dlg.sb_constWD_FuFo, main.get('windDir'))
        _set(dlg.sb_rlength_FuFo, main.get('z0'))
        _set(dlg.sb_relHum, main.get('Q_2m'))
        _set_int(dlg.sb_lowclouds_2, clouds.get('lowClouds'))
        _set_int(dlg.sb_mediumclouds, clouds.get('middleClouds'))
        _set_int(dlg.sb_highclouds_2, clouds.get('highClouds'))
    elif 'LBC' in simulation:
        # the plugin no longer offers open/cyclic boundaries: simple forcing with the file's wind and clouds
        dlg.rb_simpleForcing.setChecked(True)
        _set(dlg.sb_windspeed, main.get('windSpeed'))
        _set(dlg.sb_winddir, main.get('windDir'))
        _set(dlg.sb_rlength, main.get('z0'))
        _set_int(dlg.sb_lowclouds, clouds.get('lowClouds'))
        _set_int(dlg.sb_midclouds, clouds.get('middleClouds'))
        _set_int(dlg.sb_highclouds, clouds.get('highClouds'))
        notes.append('The file uses open/cyclic boundaries, which the plugin does not offer: Simple Forcing is '
                     'selected instead. Check the meteorology before saving.')

    if 'Soil' in simulation:
        dlg.chk_soilSim.setCheckState(Qt.CheckState.Checked)
        soil = simulation['Soil']
        _set(dlg.sb_soilHumUpper, soil.get('waterUpperlayer'))
        _set(dlg.sb_soilHumMiddle, soil.get('waterMiddlelayer'))
        _set(dlg.sb_soilHumLower, soil.get('waterDeeplayer'))
        _set(dlg.sb_soilHumBedrock, soil.get('waterBedrockLayer'))
        if any(key.startswith('temp') for key in soil):
            notes.append('The soil temperatures of the file are not used: ENVI-met 6 estimates them.')
    if 'indoorSettings' in simulation:
        dlg.chk_buildingsSim.setCheckState(Qt.CheckState.Checked)
        indoor = simulation['indoorSettings']
        dlg.cb_naturalVentilation.setCurrentIndex(int(indoor.get('naturalVentilation', 2)))
        dlg.cb_indoorMode.setCurrentIndex(int(indoor.get('indoorMode', 1)))
        dlg.cb_indoorUse.setCurrentIndex(int(indoor.get('defaultBuildingUse', 0)))
        _set(dlg.sb_indoorLower, indoor.get('indoorLowerC'))
        _set(dlg.sb_indoorUpper, indoor.get('indoorUpperC'))
    elif 'Building' in simulation:
        notes.append('The building settings of the file (ENVI-met 5) are not used: ENVI-met 6 has an indoor '
                     'climate model instead; see the Indoor Climate page.')
    if 'Sources' in simulation or 'Background' in simulation:
        dlg.chk_pollutantsSim.setCheckState(Qt.CheckState.Checked)
        sources, background = simulation.get('Sources', {}), simulation.get('Background', {})
        if 'userPolluName' in sources:
            dlg.le_userPolluName.setText(str(sources['userPolluName']))
        if 'userPolluType' in sources:
            dlg.cb_userPolluType.setCurrentIndex(int(sources['userPolluType']))
        _set(dlg.sb_praticleDia, sources.get('userPartDiameter'))
        _set(dlg.sb_particleDens, sources.get('userPartDensity'))
        for widget, key in ((dlg.sb_NO, 'NO'), (dlg.sb_NO2, 'NO2'), (dlg.sb_ozone, 'O3'), (dlg.sb_PM10, 'PM_10'),
                            (dlg.sb_PM25, 'PM_2_5'), (dlg.sb_userPollu, 'userSpec')):
            _set(widget, background.get(key))
    if 'RadScheme' in simulation or 'SolarAdjust' in simulation:
        dlg.chk_radiationSim.setCheckState(Qt.CheckState.Checked)
        scheme = simulation.get('RadScheme', {})
        dlg.cb_resIVS.setCurrentIndex(_ivs_index(scheme))
    if 'OutputSettings' in simulation:
        dlg.chk_outputSim.setCheckState(Qt.CheckState.Checked)
        output = simulation['OutputSettings']
        for widget, key in ((dlg.cb_outputBldData, 'writeBuildings'), (dlg.cb_outputRadData, 'writeRadiation'),
                            (dlg.cb_outputSoilData, 'writeSoil'), (dlg.cb_outputVegData, 'writeVegetation')):
            widget.setCheckState(Qt.CheckState.Checked if output.get(key, True) else Qt.CheckState.Unchecked)
        _set_int(dlg.sb_outputIntRecBld, output.get('textFiles'))
        _set_int(dlg.sb_outputIntOther, output.get('mainFiles'))
    if 'TThread' in simulation:
        dlg.chk_expertSim.setCheckState(Qt.CheckState.Checked)
        own = simulation['TThread'].get('UseTThread_CallMain', False)
        (dlg.rb_threadingOwn if own else dlg.rb_threadingMain).setChecked(True)
    retired = [s for s in ('Turbulence', 'SOR', 'Facades', 'InflowAvg') if s in simulation]
    if retired:
        notes.append(f'Not used by ENVI-met 6 and left out when saving: {", ".join(retired)}.')
    notes += _show_module(dlg, simulation, simx_dir)
    return notes


def _set(widget, value):
    if value is not None:
        widget.setValue(float(value))


def _set_int(widget, value):
    if value is not None:
        widget.setValue(int(round(float(value))))


def _ivs_index(scheme):
    angles = (scheme.get('IVSHeightAngle_HiRes', -1), scheme.get('IVSHeightAngle_LoRes', -1),
              scheme.get('IVSAziAngle_HiRes', -1), scheme.get('IVSAziAngle_LoRes', -1))
    if tuple(angles) in IVS_PRESETS:
        return IVS_PRESETS.index(tuple(angles))
    # closest preset by the high-resolution height angle
    hi = angles[0]
    if hi is None or hi < 0:
        return 0
    return min(range(1, len(IVS_PRESETS)), key=lambda n: abs(IVS_PRESETS[n][0] - hi))


def _set_simple_forcing(dlg, t_air, q_rel):
    """Daily extremes and their hours from the 24 hourly values (the tab rebuilds the curves from them)."""
    if len(t_air) < 24 or len(q_rel) < 24:
        return
    t_air = np.asarray(t_air[:24], dtype=float) - KELVIN_OFFSET
    q_rel = np.asarray(q_rel[:24], dtype=float)
    dlg.sb_timeMinT.setValue(int(np.argmin(t_air)))
    dlg.sb_timeMaxT.setValue(int(np.argmax(t_air)))
    dlg.sb_timeMinHum.setValue(int(np.argmin(q_rel)))
    dlg.sb_timeMaxHum.setValue(int(np.argmax(q_rel)))
    dlg.hs_minT.setValue(int(round(t_air.min())))
    dlg.hs_maxT.setValue(int(round(t_air.max())))
    dlg.hs_minHum.setValue(int(round(q_rel.min())))
    dlg.hs_maxHum.setValue(int(round(q_rel.max())))


def update_indoor_page(dlg):
    """ENVI-guide's rules: everything depends on the indoor climate model being on; the lower threshold
    applies from 'heated' on, the upper one from 'mixed mode' on and stays 2 K above the lower one."""
    model_on = dlg.cb_naturalVentilation.currentIndex() > 0
    mode = dlg.cb_indoorMode.currentIndex()
    for widget in (dlg.cb_indoorMode, dlg.lb_indoorMode, dlg.cb_indoorUse, dlg.lb_indoorUse):
        widget.setEnabled(model_on)
    lower = model_on and mode >= 1
    upper = model_on and mode >= 2
    dlg.sb_indoorLower.setEnabled(lower)
    dlg.lb_indoorLower.setEnabled(lower)
    dlg.sb_indoorUpper.setEnabled(upper)
    dlg.lb_indoorUpper.setEnabled(upper)
    if upper and dlg.sb_indoorUpper.value() < dlg.sb_indoorLower.value() + 2:
        dlg.sb_indoorUpper.setValue(dlg.sb_indoorLower.value() + 2)
