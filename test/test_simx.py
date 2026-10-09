# coding=utf-8
"""SIMX files (core.simx) and the Create simulation tab (simx_ui)."""

import json
import os
import re
import shutil
import tempfile
import unittest

from .plugin_env import import_plugin_module, make_plugin

DATA = os.path.join(os.path.dirname(__file__), 'data')
GUIDE_595 = os.path.join(DATA, 'guide_595.simx')

# Optional: the sources of ENVI-met's shared library, to check the written keys against its SIMX reader
ENVIMET_LIB = os.environ.get('G2E_ENVIMET_LIB', '')
LIB_SIMX_READER = os.path.join(ENVIMET_LIB, 'BIOS', 'u_tSIMXFile.pas') if ENVIMET_LIB else ''

# An ENVI-met 6 file as ENVI-guide writes it: open/cyclic boundaries and the indoor climate section
GUIDE_V6 = '''{
  "Header": {"filetype": "simConfJSON", "version": 1, "remark": "", "fileInfo": "Created in ENVI-Guide V6.0.0"},
  "mainData": {"simName": "Yard", "INXFile": "yard.inx", "filebaseName": "Yard", "outDir": "",
               "startDate": "21.06.2026", "startTime": "06:00:00", "simDuration": 30, "windSpeed": 3,
               "windDir": 250, "z0": 0.1, "T_H": 296.15, "Q_2m": 60, "windLimit": 15, "windAccuracy": 1},
  "indoorSettings": {"naturalVentilation": 1, "defaultBuildingUse": 2, "indoorMode": 3,
                     "indoorLowerC": 21, "indoorUpperC": 25.5},
  "LBC": {"LBC_TQ": 3, "LBC_TKE": 1},
  "Clouds": {"lowClouds": 2, "middleClouds": 0, "highClouds": 1},
  "myExtension": {"value": [0, 90]}
}'''


def core_simx():
    return import_plugin_module('core.simx')


class _TempDir(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='g2e_simx_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def path(self, name, text=None):
        path = os.path.join(self.tmp, name)
        if text is not None:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        return path


class SimxFileTest(_TempDir):

    def test_reads_an_envi_guide_file_with_envi_met_types(self):
        simulation, kind = core_simx().read(GUIDE_595)
        self.assertEqual(kind, 'json')
        main = simulation['mainData']
        self.assertIsInstance(main['simDuration'], int)
        self.assertEqual(main['windSpeed'], 2.0)
        self.assertIsInstance(main['windSpeed'], float)
        self.assertIs(simulation['TThread']['UseTThread_CallMain'], False)
        self.assertIs(simulation['FullForcing']['forceT'], True)
        # keys and sections the plugin does not know are kept as they are
        self.assertEqual(simulation['FullForcing']['verticalTAir'], 0)
        self.assertEqual(simulation['InflowAvg'], {'NOInflowAvg': 1})

    def test_json_round_trip(self):
        simx = core_simx()
        simulation, _ = simx.read(GUIDE_595)
        path = simx.write_json(self.path('round.simx'), simulation)
        again, _ = simx.read(path)
        self.assertEqual(list(again), ['Header'] + simx.ordered_sections(simulation))
        for section in simulation:
            if section != 'Header':
                self.assertEqual(again[section], simulation[section], section)

    def test_written_json_has_the_value_types_envi_met_reads(self):
        """ENVI-met's reader converts by type: booleans must be true/false, integers without decimals."""
        simx = core_simx()
        simulation = {'mainData': {'simDuration': 24.0, 'windSpeed': 2, 'T_H': '293.15'},
                      'OutputSettings': {'netCDF': 1, 'mainFiles': 60.0},
                      'SimpleForcing': {'TAir': [290, 291.5], 'Qrel': [50, 60]}}
        with open(simx.write_json(self.path('types.simx'), simulation), encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['Header']['filetype'], 'simConfJSON')
        self.assertEqual(data['Header']['version'], 1)
        self.assertIs(data['OutputSettings']['netCDF'], True)
        self.assertEqual(repr(data['OutputSettings']['mainFiles']), '60')
        self.assertEqual(repr(data['mainData']['simDuration']), '24')
        self.assertEqual(repr(data['mainData']['windSpeed']), '2.0')
        self.assertEqual(data['SimpleForcing']['TAir'], [290.0, 291.5])

    def test_sections_in_envi_met_order(self):
        simx = core_simx()
        simulation = {'Parallel': {'CPUDemand': 'ALL'}, 'myOwn': {'a': 1}, 'Clouds': {'lowClouds': 0},
                      'mainData': {'simName': 'x'}}
        with open(simx.write_json(self.path('order.simx'), simulation), encoding='utf-8') as f:
            self.assertEqual(list(json.load(f)), ['Header', 'mainData', 'Clouds', 'Parallel', 'myOwn'])

    def test_xml_round_trip(self):
        simx = core_simx()
        simulation, _ = simx.read(GUIDE_595)
        path = simx.write_xml(self.path('round_xml.simx'), simulation, '07.10.2026 12:00:00')
        again, kind = simx.read(path)
        self.assertEqual(kind, 'xml')
        self.assertEqual([s for s in again if s != 'Header'], simx.ordered_sections(simulation))
        # XML has no value types: keys ENVI-met reads come back typed, others as text
        for section, values in simulation.items():
            for key, value in values.items():
                if section != 'Header':
                    expected = value if key in simx.TYPES.get(section, {}) else str(value)
                    self.assertEqual(again[section][key], expected, (section, key))
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('<UseTThread_CallMain> 0 </UseTThread_CallMain>', text)
        self.assertIn('<revisiondate>07.10.2026 12:00:00</revisiondate>', text)

    def test_reads_old_plugin_xml(self):
        """Older plugin versions wrote CPUdemand; ENVI-met reads either spelling."""
        path = self.path('old.simx', '<ENVI-MET_Datafile>\n<Header>\n<filetype>SIMX</filetype>\n</Header>\n'
                                     '  <mainData>\n     <simName> Old </simName>\n'
                                     '     <simDuration> 24 </simDuration>\n  </mainData>\n'
                                     '  <SimpleForcing>\n     <TAir> 290.00000,291.00000 </TAir>\n'
                                     '  </SimpleForcing>\n  <Parallel>\n     <CPUdemand> ALL </CPUdemand>\n'
                                     '  </Parallel>\n</ENVI-MET_Datafile>\n')
        simulation, kind = core_simx().read(path)
        self.assertEqual(kind, 'xml')
        self.assertEqual(simulation['mainData'], {'simName': 'Old', 'simDuration': 24})
        self.assertEqual(simulation['SimpleForcing']['TAir'], [290.0, 291.0])
        self.assertEqual(simulation['Parallel'], {'CPUDemand': 'ALL'})

    def test_byte_order_mark(self):
        path = self.path('bom.simx')
        with open(path, 'w', encoding='utf-8-sig') as f:
            f.write('{"mainData": {"simName": "BOM"}}')
        self.assertEqual(core_simx().read(path)[0]['mainData']['simName'], 'BOM')

    def test_not_a_simx_file(self):
        simx = core_simx()
        with self.assertRaises(simx.SimxError):
            simx.read(self.path('text.simx', 'hello'))
        with self.assertRaises(simx.SimxError):
            simx.read(self.path('broken.simx', '{"mainData": '))

    def test_format_by_version(self):
        uses_json = core_simx().uses_json
        self.assertFalse(uses_json((5, 8, 9)))
        self.assertTrue(uses_json((5, 9, 0)))
        self.assertTrue(uses_json((6, 0, 0)))
        self.assertTrue(uses_json(None))


class SimxTabTest(_TempDir):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plugin = make_plugin()
        cls.ui = import_plugin_module('simx_ui')
        cls.simx = import_plugin_module('core.simx')

    def setUp(self):
        self.plugin.clear_settings_create_sim_tab()
        self.plugin.iface.bar.messages.clear()
        self.dlg = self.plugin.dlg

    def check(self, box):
        from qgis.PyQt.QtCore import Qt
        box.setCheckState(Qt.CheckState.Checked)

    def reload(self, simulation, json_format=True):
        """Write, clear the tab, load again."""
        path = self.path('tab.simx')
        if json_format:
            self.simx.write_json(path, simulation)
        else:
            self.simx.write_xml(path, simulation)
        self.plugin.load_simx_file(path)
        return path

    # ------------------------------------------------------------------ tab -> file
    def test_simple_forcing_for_envi_met_6(self):
        self.check(self.dlg.chk_soilSim)
        self.check(self.dlg.chk_buildingsSim)
        simulation = self.ui.model_from_ui(self.dlg, json_format=True)
        self.assertNotIn('Q_H', simulation['mainData'])
        self.assertNotIn('T_H', simulation['mainData'])
        self.assertNotIn('Building', simulation)
        self.assertEqual(sorted(simulation['Soil']),
                         ['waterBedrockLayer', 'waterDeeplayer', 'waterMiddlelayer', 'waterUpperlayer'])
        self.assertEqual(simulation['indoorSettings'],
                         {'naturalVentilation': 2, 'defaultBuildingUse': 0, 'indoorMode': 1,
                          'indoorLowerC': 20.0, 'indoorUpperC': 26.0})
        forcing = simulation['SimpleForcing']
        self.assertEqual((len(forcing['TAir']), len(forcing['Qrel'])), (24, 24))
        self.assertAlmostEqual(forcing['TAir'][5], 17.0 + self.ui.KELVIN_OFFSET)
        self.assertEqual(simulation['Parallel'], {'CPUDemand': 'ALL'})

    def test_xml_for_envi_met_5_8_has_its_required_values(self):
        self.check(self.dlg.chk_soilSim)
        self.check(self.dlg.chk_buildingsSim)
        simulation = self.ui.model_from_ui(self.dlg, json_format=False)
        self.assertEqual((simulation['mainData']['T_H'], simulation['mainData']['Q_H']), (293.15, 8.0))
        self.assertIn('tempUpperlayer', simulation['Soil'])
        self.assertNotIn('indoorSettings', simulation)
        self.assertEqual(simulation['Building']['indoorConst'], False)

    def test_unchecked_sections_are_left_out(self):
        simulation = self.ui.model_from_ui(self.dlg)
        for section in ('Soil', 'indoorSettings', 'Building', 'Sources', 'Background', 'RadScheme',
                        'OutputSettings', 'TThread'):
            self.assertNotIn(section, simulation)

    # ------------------------------------------------------------------ file -> tab -> file
    def test_indoor_climate_round_trip(self):
        dlg = self.dlg
        self.check(dlg.chk_buildingsSim)
        dlg.cb_naturalVentilation.setCurrentIndex(1)
        dlg.cb_indoorMode.setCurrentIndex(3)
        dlg.cb_indoorUse.setCurrentIndex(2)
        dlg.sb_indoorLower.setValue(21.0)
        dlg.sb_indoorUpper.setValue(25.5)
        self.reload(self.ui.model_from_ui(dlg))
        self.assertEqual(self.plugin.iface.bar.messages, [])
        self.assertTrue(dlg.chk_buildingsSim.isChecked())
        self.assertEqual((dlg.cb_naturalVentilation.currentIndex(), dlg.cb_indoorMode.currentIndex(),
                          dlg.cb_indoorUse.currentIndex()), (1, 3, 2))
        self.assertEqual((dlg.sb_indoorLower.value(), dlg.sb_indoorUpper.value()), (21.0, 25.5))

    def test_open_cyclic_round_trip(self):
        dlg = self.dlg
        dlg.rb_other.click()
        self.assertEqual(dlg.stackedWidget_3.currentIndex(), 2)
        dlg.cb_otherBChumT.setCurrentIndex(1)
        dlg.sb_otherAirT.setValue(23.0)
        dlg.sb_otherHum.setValue(60.0)
        dlg.sb_otherWS.setValue(3.0)
        dlg.sb_otherWdir.setValue(250.0)
        dlg.sb_otherLowclouds.setValue(2)
        simulation = self.ui.model_from_ui(dlg)
        self.assertEqual(simulation['LBC'], {'LBC_TQ': 3, 'LBC_TKE': 1})
        self.assertNotIn('SimpleForcing', simulation)
        self.assertAlmostEqual(simulation['mainData']['T_H'], 23.0 + self.ui.KELVIN_OFFSET)
        self.reload(simulation)
        self.assertTrue(dlg.rb_other.isChecked())
        self.assertEqual(dlg.stackedWidget_3.currentIndex(), 2)
        self.assertEqual((dlg.cb_otherBChumT.currentIndex(), dlg.cb_otherBCturb.currentIndex()), (1, 0))
        self.assertAlmostEqual(dlg.sb_otherAirT.value(), 23.0)
        self.assertEqual((dlg.sb_otherHum.value(), dlg.sb_otherWS.value(), dlg.sb_otherWdir.value()),
                         (60.0, 3.0, 250.0))
        self.assertEqual(dlg.sb_otherLowclouds.value(), 2)

    def test_full_forcing_round_trip(self):
        dlg = self.dlg
        dlg.rb_fullForcing.click()
        dlg.le_selectedFOX.setText('station.FOX')
        dlg.rb_forceT_no.setChecked(True)
        dlg.rb_forceRadC_no.setChecked(True)
        dlg.sb_initT.setValue(18.5)
        dlg.sb_mediumclouds.setValue(3)
        simulation = self.ui.model_from_ui(dlg)
        self.assertEqual(simulation['FullForcing']['forceT'], False)
        self.assertAlmostEqual(simulation['mainData']['T_H'], 18.5 + self.ui.KELVIN_OFFSET)
        self.assertEqual(simulation['Clouds']['middleClouds'], 3)
        self.assertNotIn('nudging', simulation['FullForcing'])
        self.reload(simulation)
        self.assertTrue(dlg.rb_fullForcing.isChecked())
        self.assertTrue(dlg.cb_meteo.isChecked())
        self.assertEqual(dlg.le_selectedFOX.text(), 'station.FOX')
        self.assertTrue(dlg.rb_forceT_no.isChecked() and dlg.rb_forceRadC_no.isChecked())
        self.assertTrue(dlg.rb_forceWind_yes.isChecked())
        self.assertAlmostEqual(dlg.sb_initT.value(), 18.5)
        self.assertEqual(dlg.sb_mediumclouds.value(), 3)

    def test_loading_an_envi_guide_5_9_file(self):
        """Settings the tab does not show are kept; ENVI-met 5 settings are reported and dropped."""
        dlg = self.dlg
        self.plugin.load_simx_file(GUIDE_595)
        self.assertEqual(dlg.lb_loadedSimx.text(), GUIDE_595)
        self.assertEqual(dlg.le_fullSimName.text(), 'Road test')
        self.assertTrue(dlg.rb_fullForcing.isChecked())
        self.assertTrue(dlg.rb_forcePrec_no.isChecked())
        self.assertTrue(dlg.chk_pollutantsSim.isChecked() and dlg.chk_outputSim.isChecked())
        self.assertEqual(dlg.cb_userPolluType.currentIndex(), 1)
        self.assertEqual((dlg.sb_outputIntOther.value(), dlg.sb_outputIntRecBld.value()), (30, 30))
        self.assertTrue(dlg.rb_threadingMain.isChecked())
        notes = [text for _, text, _ in self.plugin.iface.bar.messages]
        self.assertEqual(len(notes), 1)
        self.assertIn('Turbulence, SOR, Facades, InflowAvg', notes[0])

        saved = self.ui.model_from_ui(dlg, base=self.plugin.loaded_simx)
        for section in ('Turbulence', 'SOR', 'Facades', 'InflowAvg'):
            self.assertNotIn(section, saved)
        self.assertNotIn('Q_H', saved['mainData'])
        self.assertNotIn('nudging', saved['FullForcing'])
        self.assertEqual(saved['FullForcing']['verticalTAir'], 0)
        self.assertEqual(saved['ModelTiming']['flowSteps'], 900)
        self.assertEqual(saved['TimeSteps']['dt_step02'], 1.0)
        self.assertEqual(saved['PlantModel']['TreeCalendar'], True)
        self.assertEqual(saved['OutputSettings']['emailNotification'], True)
        self.assertEqual(saved['TThread']['TThreadPRIO'], 4)

    def test_loading_an_envi_guide_6_file(self):
        dlg = self.dlg
        self.plugin.load_simx_file(self.path('guide6.simx', GUIDE_V6))
        self.assertTrue(dlg.rb_other.isChecked())
        self.assertEqual(dlg.cb_otherBChumT.currentIndex(), 1)
        self.assertTrue(dlg.chk_buildingsSim.isChecked())
        self.assertEqual((dlg.cb_naturalVentilation.currentIndex(), dlg.cb_indoorMode.currentIndex(),
                          dlg.cb_indoorUse.currentIndex()), (1, 3, 2))
        self.assertEqual((dlg.sb_indoorLower.value(), dlg.sb_indoorUpper.value()), (21.0, 25.5))
        self.assertEqual(self.plugin.iface.bar.messages, [])
        saved = self.ui.model_from_ui(dlg, base=self.plugin.loaded_simx)
        self.assertEqual(saved['myExtension'], {'value': [0, 90]})      # a section the plugin does not know
        self.assertEqual(saved['mainData']['windAccuracy'], 1)

    def test_envi_met_5_building_section_is_reported(self):
        path = self.path('v5.simx', '{"mainData": {"simName": "Old"}, "SimpleForcing": {}, '
                                    '"Building": {"surfaceTemp": 293, "indoorTemp": 293, "indoorConst": false}}')
        self.plugin.load_simx_file(path)
        self.assertFalse(self.dlg.chk_buildingsSim.isChecked())
        notes = [text for _, text, _ in self.plugin.iface.bar.messages]
        self.assertTrue(any('indoor climate model' in note for note in notes), notes)

    def test_save_writes_json_for_envi_met_6_and_xml_for_5_8(self):
        plugin, dlg = self.plugin, self.dlg
        dlg.le_inxForSim.setText('area.INX')
        plugin.simsettings_change()
        for version, kind in (((6, 0, 0), 'json'), ((5, 8, 0), 'xml')):
            path = self.path(f'save_{kind}.simx')
            dlg.le_simxDest.setText(path)
            plugin.installed_envimet_version = lambda: version
            try:
                plugin.save_simx_file()
            finally:
                del plugin.installed_envimet_version
            self.assertEqual(plugin.iface.bar.messages, [])
            self.assertEqual(self.simx.read(path)[1], kind)
            self.assertIn(kind.upper(), dlg.lb_reportSave.text())

    # ------------------------------------------------------------------ indoor page rules
    def test_indoor_page_follows_envi_guide(self):
        dlg = self.dlg

        def enabled(*widgets):
            # the page's own rules; the whole tab is disabled until the section is checked
            return [w.isEnabledTo(dlg.tab_Buildings_2) for w in widgets]

        dlg.cb_naturalVentilation.setCurrentIndex(0)
        self.assertEqual(enabled(dlg.cb_indoorMode, dlg.cb_indoorUse, dlg.sb_indoorLower, dlg.sb_indoorUpper),
                         [False] * 4)
        dlg.cb_naturalVentilation.setCurrentIndex(2)
        dlg.cb_indoorMode.setCurrentIndex(0)
        self.assertEqual(enabled(dlg.cb_indoorMode, dlg.cb_indoorUse, dlg.sb_indoorLower, dlg.sb_indoorUpper),
                         [True, True, False, False])
        dlg.cb_indoorMode.setCurrentIndex(1)
        self.assertEqual(enabled(dlg.sb_indoorLower, dlg.sb_indoorUpper), [True, False])
        dlg.cb_indoorMode.setCurrentIndex(2)
        self.assertEqual(enabled(dlg.sb_indoorLower, dlg.sb_indoorUpper), [True, True])
        dlg.sb_indoorLower.setValue(25.0)
        self.assertEqual(dlg.sb_indoorUpper.value(), 27.0)
        dlg.sb_indoorUpper.setValue(24.0)
        dlg.sb_indoorUpper.editingFinished.emit()
        self.assertEqual(dlg.sb_indoorUpper.value(), 27.0)


def keys_read_by_envimet(path):
    """{(section, key): type} that ENVI-met's JSON SIMX reader asks for ('any' for arrays)."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    reader = text[text.index('function tSIMXFile.LoadFromFileJSON'):text.index('function tSIMXFile.SaveToFileJSON')]
    keys, section = {}, None
    for line in reader.splitlines():
        opened = re.search(r"LJson\.TryGetValue\('(\w+)'", line)
        if opened:
            section = opened.group(1)
            continue
        for kind, key in re.findall(r"GetValue<(\w+)>\('(\w+)'", line):
            keys[(section, key)] = kind.lower()
        for key in re.findall(r"\bSection\.TryGetValue\('(\w+)'", line):
            keys[(section, key)] = 'any'
    return keys


# JSON value type written by the plugin -> reader types that accept it
ACCEPTED = {bool: {'boolean'}, int: {'integer', 'int64', 'double', 'single', 'extended'},
            float: {'double', 'single', 'extended'}, str: {'string'}, list: {'any'}, dict: {'any'}}


@unittest.skipUnless(LIB_SIMX_READER and os.path.isfile(LIB_SIMX_READER),
                     'set G2E_ENVIMET_LIB to the ENVI-met lib sources to check the keys against its SIMX reader')
class KeysReadByEnvimetTest(_TempDir):
    """Every key the plugin writes is read by ENVI-met, with a type its reader converts."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plugin = make_plugin()
        cls.ui = import_plugin_module('simx_ui')
        cls.simx = import_plugin_module('core.simx')
        cls.read_keys = keys_read_by_envimet(LIB_SIMX_READER)

    def written(self):
        path = self.simx.write_json(self.path('keys.simx'), self.ui.model_from_ui(self.plugin.dlg))
        with open(path, encoding='utf-8') as f:
            return json.load(f)

    def unread(self, data):
        problems = []

        def check(section, key, value):
            kind = self.read_keys.get((section, key))
            if kind is None:
                problems.append(f'{section}/{key} is not read')
            elif kind not in ACCEPTED[type(value)]:
                problems.append(f'{section}/{key}: written as {type(value).__name__}, read as {kind}')
            if isinstance(value, dict):         # SimModule/ModuleData
                for inner, inner_value in value.items():
                    check(section, inner, inner_value)

        for section, values in data.items():
            for key, value in values.items():
                check(section, key, value)
        return problems

    def test_every_module(self):
        modules = import_plugin_module('core.modules')
        dlg = self.plugin.dlg
        self.plugin.clear_settings_create_sim_tab()
        dlg.lw_solarDates.addItem('21.06.2026')
        dlg.le_moduleFox.setText(self.path('climate.fox', 'FOX'))
        problems = []
        for code in modules.CODES[1:]:
            dlg.cb_simType.setCurrentIndex(dlg.cb_simType.findData(code))
            data = self.written()
            self.assertEqual(data['SimModule']['name'], code)
            problems += self.unread(data)
        self.plugin.clear_settings_create_sim_tab()
        self.assertEqual(sorted(set(problems)), [])

    def test_the_reader_was_understood(self):
        self.assertEqual(self.read_keys[('mainData', 'simDuration')], 'integer')
        self.assertEqual(self.read_keys[('SimpleForcing', 'TAir')], 'any')
        self.assertEqual(self.read_keys[('indoorSettings', 'indoorLowerC')], 'double')
        # what the plugin leaves out for ENVI-met 6 is indeed not read any more
        for section, keys in self.simx.RETIRED_V6['keys'].items():
            for key in keys:
                self.assertNotIn((section, key), self.read_keys)
        sections = {section for section, _ in self.read_keys}
        self.assertFalse(self.simx.RETIRED_V6['sections'] & sections)

    def test_every_forcing_mode_with_every_section(self):
        from qgis.PyQt.QtCore import Qt
        plugin, dlg = self.plugin, self.plugin.dlg
        plugin.clear_settings_create_sim_tab()
        for box in (dlg.chk_soilSim, dlg.chk_buildingsSim, dlg.chk_pollutantsSim, dlg.chk_radiationSim,
                    dlg.chk_outputSim, dlg.chk_expertSim):
            box.setCheckState(Qt.CheckState.Checked)
        problems = self.unread(self.written())
        dlg.rb_fullForcing.click()
        for no in (dlg.rb_forceT_no, dlg.rb_forceHum_no, dlg.rb_forceWind_no, dlg.rb_forceRadC_no):
            no.setChecked(True)
        problems += self.unread(self.written())
        dlg.rb_other.click()
        problems += self.unread(self.written())
        self.assertEqual(sorted(set(problems)), [])


if __name__ == '__main__':
    unittest.main()
