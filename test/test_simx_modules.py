# coding=utf-8
"""ENVI-met 6 simulation modules: core.modules, the SIMX formats and the Module page."""

import json
import os
import shutil
import tempfile
import unittest

from .plugin_env import import_plugin_module, make_plugin

# As ENVI-guide writes a wind comfort run (a file from a real project, names changed)
GUIDE_WIND_COMFORT = '''{
  "Header": {"filetype": "simConfJSON", "version": 1, "remark": "", "fileInfo": "Created in ENVI-Guide V6.0.0"},
  "mainData": {"simName": "Windy", "INXFile": "area.INX", "filebaseName": "Windy", "outDir": "",
               "startDate": "23.06.2024", "startTime": "07:00:00", "simDuration": 24, "windSpeed": 2.5,
               "windDir": 90, "z0": 0.1, "T_H": 293.15, "Q_2m": 50, "windLimit": 15, "windAccuracy": 0},
  "SimModule": {"name": "WINDCOMFORT", "ModuleData": {"outputFolder": "", "baseWindSpd": 5, "sectorCnt": 16,
                                                      "forcingFile": "Windy_WindClimate.fox"}}
}'''

# The XML format keeps the module's keys flat; windAccuracy is a word there
XML_STATS = '''<ENVI-MET_Datafile>
<Header>
<filetype>SIMX</filetype>
<version>2</version>
</Header>
  <mainData>
     <simName> Stats </simName>
     <INXFile> area.INX </INXFile>
     <windAccuracy> quick </windAccuracy>
  </mainData>
  <SimModule>
     <name> FASTTHERMALCOMFORTSTATS </name>
     <outputFolder>  </outputFolder>
     <baseWindSpd> 5 </baseWindSpd>
     <sectorCnt> 8 </sectorCnt>
     <forcingFile> MyForcing.FOX </forcingFile>
     <startMonth> 7 </startMonth>
     <endMonth> 9 </endMonth>
     <startHour> 8 </startHour>
     <endHour> 20 </endHour>
  </SimModule>
</ENVI-MET_Datafile>
'''


class _TempDir(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='g2e_modules_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def path(self, name, text=None):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if text is not None:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        return path


class ModuleDefinitionsTest(_TempDir):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.m = import_plugin_module('core.modules')

    def test_a_new_module_gets_envi_guide_values_for_hidden_settings(self):
        m = self.m
        self.assertEqual(m.build_section(m.WIND_COMFORT, {'forcingFile': 'a.fox'}),
                         {'name': 'WINDCOMFORT', 'ModuleData': {'outputFolder': '', 'baseWindSpd': 10.0,
                                                                'sectorCnt': 16, 'forcingFile': 'a.fox'}})
        self.assertEqual(m.build_section(m.FAST_UTCI, {})['ModuleData']['sectorCnt'], 8)
        self.assertIs(m.build_section(m.WIND_FLOW, {})['ModuleData']['highPrecision'], True)

    def test_a_loaded_module_keeps_its_hidden_settings(self):
        m = self.m
        loaded = {'name': 'WINDCOMFORT', 'ModuleData': {'outputFolder': '', 'baseWindSpd': 5, 'sectorCnt': 12,
                                                        'forcingFile': 'old.fox'}}
        data = m.build_section(m.WIND_COMFORT, {'forcingFile': 'new.fox'}, loaded)['ModuleData']
        self.assertEqual((data['baseWindSpd'], data['sectorCnt'], data['forcingFile']), (5, 12, 'new.fox'))
        # another module's settings are not taken over
        self.assertEqual(m.build_section(m.FAST_UTCI, {}, loaded)['ModuleData']['baseWindSpd'], 10.0)

    def test_wind_flow_source_remark_only_while_the_wind_is_unchanged(self):
        m = self.m
        loaded = {'name': 'WINDFLOW', 'ModuleData': {'windSpeed': 3.2, 'windDir': 250, 'highPrecision': False,
                                                     'inflowSource': 'weather data service'}}
        same = m.build_section(m.WIND_FLOW, {'windSpeed': 3.2, 'windDir': 250}, loaded)['ModuleData']
        self.assertEqual(same['inflowSource'], 'weather data service')
        self.assertIs(same['highPrecision'], False)
        changed = m.build_section(m.WIND_FLOW, {'windSpeed': 4.0, 'windDir': 250}, loaded)['ModuleData']
        self.assertNotIn('inflowSource', changed)

    def test_fox_copy_name(self):
        self.assertEqual(self.m.fox_file_name(os.path.join('C:', 'p', 'My.Sim.simx'), self.m.WIND_COMFORT),
                         'My_WindClimate.fox')
        self.assertEqual(self.m.fox_file_name('run.SIMX', self.m.FAST_UTCI_STATS), 'run_UTCIStats.fox')

    def test_problems(self):
        m = self.m
        self.assertEqual(len(m.problems(m.SOLAR_ACCESS, {'solarAccessDates': ''})), 1)
        self.assertEqual(m.problems(m.SOLAR_ACCESS, {'solarAccessDates': '21.06.2026,21.12.2026'}), [])
        self.assertIn('31.02.2026', m.problems(m.SOLAR_ACCESS, {'solarAccessDates': '31.02.2026'})[0])
        self.assertEqual(len(m.problems(m.WIND_COMFORT, {'forcingFile': ''})), 1)
        self.assertIn('does not exist', m.problems(m.FAST_UTCI, {'forcingFile': self.path('none.fox')})[0])
        fox = self.path('real.fox', 'FOX')
        self.assertEqual(m.problems(m.FAST_UTCI_STATS, {'forcingFile': fox, 'startMonth': 6, 'endMonth': 9,
                                                        'startHour': 6, 'endHour': 20}), [])
        # the period may run over the end of the year and of the day, as every ENVI-met run wraps the year
        self.assertEqual(m.problems(m.FAST_UTCI_STATS, {'forcingFile': fox, 'startMonth': 11, 'endMonth': 2,
                                                        'startHour': 22, 'endHour': 4}), [])
        self.assertEqual(m.problems(m.WIND_FLOW, {}), [])

    def test_solstices_and_equinoxes(self):
        self.assertEqual(self.m.solstices_and_equinoxes(2027), ['21.03.2027', '21.06.2027', '23.09.2027',
                                                                 '21.12.2027'])


class ModuleFormatsTest(_TempDir):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.simx = import_plugin_module('core.simx')
        cls.m = import_plugin_module('core.modules')

    def test_xml_module_reads_like_json(self):
        simulation, kind = self.simx.read(self.path('stats.simx', XML_STATS))
        self.assertEqual(kind, 'xml')
        self.assertEqual(self.m.module_name(simulation), self.m.FAST_UTCI_STATS)
        self.assertEqual(self.m.module_data(simulation),
                         {'outputFolder': '', 'baseWindSpd': 5.0, 'sectorCnt': 8, 'forcingFile': 'MyForcing.FOX',
                          'startMonth': 7, 'endMonth': 9, 'startHour': 8, 'endHour': 20})
        self.assertEqual(simulation['mainData']['windAccuracy'], 1)

    def test_xml_writes_the_module_flat(self):
        simulation, _ = self.simx.read(self.path('stats.simx', XML_STATS))
        path = self.simx.write_xml(self.path('stats_out.simx'), simulation)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('<name> FASTTHERMALCOMFORTSTATS </name>', text)
        self.assertIn('<startMonth> 7 </startMonth>', text)
        self.assertIn('<windAccuracy> quick </windAccuracy>', text)
        self.assertNotIn('ModuleData', text)
        self.assertEqual(self.simx.read(path)[0]['SimModule'], simulation['SimModule'])

    def test_json_keeps_the_module_nested(self):
        simulation, _ = self.simx.read(self.path('wind.simx', GUIDE_WIND_COMFORT))
        path = self.simx.write_json(self.path('wind_out.simx'), simulation)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(data['SimModule'], json.loads(GUIDE_WIND_COMFORT)['SimModule'])


class ModulePageTest(_TempDir):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.plugin = make_plugin()
        cls.ui = import_plugin_module('simx_ui')
        cls.simx = import_plugin_module('core.simx')
        cls.m = import_plugin_module('core.modules')

    def setUp(self):
        self.plugin.clear_settings_create_sim_tab()
        self.plugin.iface.bar.messages.clear()
        self.dlg = self.plugin.dlg

    def choose(self, code):
        self.dlg.cb_simType.setCurrentIndex(self.dlg.cb_simType.findData(code))

    def save(self, path, version=(6, 0, 0)):
        self.dlg.le_inxForSim.setText('area.INX')
        self.plugin.simsettings_change()
        self.dlg.le_simxDest.setText(path)
        self.plugin.installed_envimet_version = lambda: version
        try:
            self.plugin.save_simx_file()
        finally:
            del self.plugin.installed_envimet_version

    def test_a_module_replaces_meteorology_and_advanced_settings(self):
        from qgis.PyQt.QtCore import Qt
        dlg = self.dlg
        dlg.chk_soilSim.setCheckState(Qt.CheckState.Checked)
        self.assertTrue(dlg.tab_Soil.isEnabled() and dlg.tab_Meteo.isEnabled())
        self.assertFalse(dlg.tab_Module.isEnabled())
        self.choose(self.m.WIND_FLOW)
        self.assertEqual(dlg.sw_module.currentIndex(), 2)
        self.assertTrue(dlg.tab_Module.isEnabled())
        self.assertFalse(dlg.tab_Meteo.isEnabled() or dlg.gb_optional.isEnabled() or dlg.tab_Soil.isEnabled())
        self.assertTrue(dlg.gb_moduleFox.isHidden())
        self.choose(self.m.FAST_UTCI)
        self.assertFalse(dlg.gb_moduleFox.isHidden())
        self.choose(self.m.HOLISTIC)
        self.assertTrue(dlg.tab_Soil.isEnabled() and dlg.tab_Meteo.isEnabled() and dlg.gb_optional.isEnabled())
        self.assertEqual(dlg.cb_meteo.text(), 'Meteorology')
        self.assertTrue(dlg.cb_meteo.isChecked())

    def test_a_module_file_holds_main_data_and_the_module(self):
        from qgis.PyQt.QtCore import QDate, Qt
        dlg = self.dlg
        dlg.chk_soilSim.setCheckState(Qt.CheckState.Checked)
        self.choose(self.m.SOLAR_ACCESS)
        self.plugin.add_solar_dates(['21.06.2026'])
        dlg.de_solarDate.setDate(QDate(2027, 1, 1))
        dlg.bt_addSolstices.click()
        dlg.bt_addSolarDate.click()
        dlg.bt_addSolarDate.click()                     # a date already listed is not added twice
        simulation = self.ui.model_from_ui(dlg)
        self.assertEqual(sorted(simulation), ['Parallel', 'SimModule', 'mainData'])
        self.assertEqual(simulation['SimModule']['ModuleData']['solarAccessDates'],
                         '21.06.2026,21.03.2027,21.06.2027,23.09.2027,21.12.2027,01.01.2027')
        dlg.lw_solarDates.setCurrentRow(0)
        dlg.bt_removeSolarDate.click()
        self.assertEqual(self.ui.solar_dates(dlg)[0], '21.03.2027')

    def test_wind_flow_values_have_envi_met_types(self):
        dlg = self.dlg
        self.choose(self.m.WIND_FLOW)
        dlg.sb_moduleWindDir.setValue(250)
        dlg.sb_moduleWindSpeed.setValue(3.5)
        self.assertEqual(self.ui.model_from_ui(dlg)['SimModule'],
                         {'name': 'WINDFLOW', 'ModuleData': {'outputFolder': '', 'highPrecision': True,
                                                             'windSpeed': 3.5, 'windDir': 250}})
        self.assertIsInstance(self.ui.model_from_ui(dlg)['SimModule']['ModuleData']['windDir'], int)

    def test_status_line_says_what_is_missing(self):
        dlg = self.dlg
        self.choose(self.m.WIND_COMFORT)
        self.assertEqual(dlg.cb_meteo.text(), 'Module settings')
        self.assertFalse(dlg.cb_meteo.isChecked())
        self.assertIn('FOX', dlg.lb_meteorology.text())
        dlg.le_moduleFox.setText(self.path('year.fox', 'FOX'))
        self.assertTrue(dlg.cb_meteo.isChecked())
        self.assertEqual(dlg.lb_meteorology.text(), 'Module selected')

    def test_save_copies_the_fox_next_to_the_simx_and_loads_back(self):
        dlg = self.dlg
        self.choose(self.m.FAST_UTCI)
        dlg.le_moduleFox.setText(self.path(os.path.join('climate', 'hot day.fox'), 'FOX DATA'))
        dlg.chk_moduleAverageWind.setChecked(True)
        target = self.path(os.path.join('project', 'My.Run.simx'))
        self.save(target)
        self.assertEqual(self.plugin.iface.bar.messages, [])
        fox = self.path(os.path.join('project', 'My_FastUTCI.fox'))
        with open(fox, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'FOX DATA')
        with open(target, encoding='utf-8') as f:
            data = json.load(f)
        self.assertEqual(sorted(data), ['Header', 'Parallel', 'SimModule', 'mainData'])
        self.assertEqual(data['SimModule']['ModuleData'],
                         {'outputFolder': '', 'baseWindSpd': 10.0, 'sectorCnt': 8, 'forcingFile': 'My_FastUTCI.fox',
                          'useAverageWindFromForcing': True})

        self.plugin.clear_settings_create_sim_tab()
        self.plugin.load_simx_file(target)
        self.assertEqual(self.plugin.iface.bar.messages, [])
        self.assertEqual(self.ui.simulation_type(dlg), self.m.FAST_UTCI)
        self.assertEqual(os.path.normcase(dlg.le_moduleFox.text()), os.path.normcase(fox))
        self.assertTrue(dlg.chk_moduleAverageWind.isChecked())
        self.assertTrue(dlg.cb_meteo.isChecked())
        self.save(target)                               # saving again in place copies nothing onto itself
        self.assertEqual(self.plugin.iface.bar.messages, [])

    def test_statistics_period_round_trip(self):
        dlg = self.dlg
        self.choose(self.m.FAST_UTCI_STATS)
        self.assertEqual((dlg.cb_statsStartMonth.currentText(), dlg.cb_statsEndMonth.currentText(),
                          dlg.cb_statsStartHour.currentText(), dlg.cb_statsEndHour.currentText()),
                         ('June', 'September', '06:00', '20:00'))
        dlg.le_moduleFox.setText(self.path('year.fox', 'FOX'))
        dlg.cb_statsStartMonth.setCurrentIndex(4)
        dlg.cb_statsEndHour.setCurrentIndex(18)
        target = self.path('stats.simx')
        self.save(target)
        self.plugin.clear_settings_create_sim_tab()
        self.plugin.load_simx_file(target)
        self.assertEqual((dlg.cb_statsStartMonth.currentText(), dlg.cb_statsEndHour.currentText()), ('May', '18:00'))
        dlg.cb_statsStartMonth.setCurrentIndex(10)       # November to February, over the year end
        dlg.cb_statsEndMonth.setCurrentIndex(1)
        self.assertTrue(dlg.cb_meteo.isChecked())
        wrapped = self.path('wrapped.simx')
        self.save(wrapped)
        self.assertEqual(self.plugin.iface.bar.messages, [])
        with open(wrapped, encoding='utf-8') as f:
            data = json.load(f)['SimModule']['ModuleData']
        self.assertEqual((data['startMonth'], data['endMonth']), (11, 2))

    def test_modules_need_envi_met_6(self):
        self.choose(self.m.WIND_FLOW)
        target = self.path('old.simx')
        self.save(target, version=(5, 9, 5))
        self.assertFalse(os.path.exists(target))
        self.assertIn('6.0 or newer', self.plugin.iface.bar.messages[-1][1])

    def test_an_envi_guide_wind_comfort_file(self):
        dlg = self.dlg
        folder = os.path.join('guide', 'project')
        self.path(os.path.join(folder, 'Windy_WindClimate.fox'), 'YEAR')
        source = self.path(os.path.join(folder, 'Windy.simx'), GUIDE_WIND_COMFORT)
        self.plugin.load_simx_file(source)
        self.assertEqual(self.plugin.iface.bar.messages, [])
        self.assertEqual(self.ui.simulation_type(dlg), self.m.WIND_COMFORT)
        self.assertTrue(os.path.isfile(dlg.le_moduleFox.text()))
        target = self.path(os.path.join('copy', 'Breezy.simx'))
        self.save(target)
        with open(target, encoding='utf-8') as f:
            data = json.load(f)['SimModule']['ModuleData']
        self.assertEqual((data['baseWindSpd'], data['sectorCnt'], data['forcingFile']),
                         (5, 16, 'Breezy_WindClimate.fox'))
        self.assertTrue(os.path.isfile(self.path(os.path.join('copy', 'Breezy_WindClimate.fox'))))

    def test_a_module_the_plugin_cannot_edit_is_kept(self):
        dlg = self.dlg
        year = GUIDE_WIND_COMFORT.replace('"name": "WINDCOMFORT", "ModuleData": {',
                                          '"name": "SOLARACCESSYEAR", "ModuleData": {"extra": 1, ')
        self.plugin.load_simx_file(self.path('year.simx', year))
        notes = [text for _, text, _ in self.plugin.iface.bar.messages]
        self.assertEqual(len(notes), 1)
        self.assertIn('SOLARACCESSYEAR', notes[0])
        self.assertEqual(self.ui.simulation_type(dlg), 'SOLARACCESSYEAR')
        self.assertEqual(dlg.cb_simType.count(), len(self.m.CHOICES) + 1)
        saved = self.ui.model_from_ui(dlg, base=self.plugin.loaded_simx)
        self.assertEqual(saved['SimModule'], json.loads(year)['SimModule'])
        self.plugin.clear_settings_create_sim_tab()
        self.assertEqual(dlg.cb_simType.count(), len(self.m.CHOICES))

    def test_holistic_drops_a_loaded_module(self):
        self.plugin.load_simx_file(self.path('wind.simx', GUIDE_WIND_COMFORT))
        self.choose(self.m.HOLISTIC)
        saved = self.ui.model_from_ui(self.dlg, base=self.plugin.loaded_simx)
        self.assertNotIn('SimModule', saved)
        self.assertIn('SimpleForcing', saved)


if __name__ == '__main__':
    unittest.main()
