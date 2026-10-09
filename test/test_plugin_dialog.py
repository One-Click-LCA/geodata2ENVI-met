# coding=utf-8
"""The plugin object and its dialog: start-up and simple UI handlers."""

import os
import shutil
import tempfile
import unittest

from .plugin_env import IfaceStub, import_plugin_module, make_plugin, start_qgis


class _EmptySettings:
    """QgsSettings of a fresh profile: no 'locale/userLocale'."""

    def value(self, key, default=None):
        return default


class PluginStartTest(unittest.TestCase):

    def test_starts_without_user_locale(self):
        start_qgis()
        main = import_plugin_module('geodata2ENVImet')
        original = main.QgsSettings
        main.QgsSettings = _EmptySettings
        try:
            plugin = main.Geo2ENVImet(IfaceStub())
        finally:
            main.QgsSettings = original
        self.assertEqual(plugin.actions, [])


class DialogHandlersTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plugin = make_plugin()

    def test_clear_settings_confirmation(self):
        """The confirmation box is built with scoped enums (QGIS 4)."""
        from qgis.PyQt.QtWidgets import QMessageBox
        shown = []
        original = QMessageBox.exec
        QMessageBox.exec = lambda box: shown.append(box.text()) or 0
        try:
            self.plugin.show_confi_dialog()
        finally:
            QMessageBox.exec = original
        self.assertEqual(shown, ['Do you really want to clear all settings?'])

    def test_previews_wait_until_the_values_settle(self):
        from qgis.PyQt.QtTest import QTest
        calls = []
        timer = self.plugin.single_shot_timer(lambda: calls.append(1))
        for _ in range(3):
            timer.start()
            QTest.qWait(50)
        self.assertEqual(calls, [])
        QTest.qWait(self.plugin.PREVIEW_DELAY_MS + 300)
        self.assertEqual(calls, [1])

    def test_spin_boxes_only_start_the_timer(self):
        before = self.plugin.thread
        self.plugin.dlg.se_dx.setValue(self.plugin.dlg.se_dx.value() + 1)
        self.assertTrue(self.plugin.preview_xy_timer.isActive())
        self.assertIs(self.plugin.thread, before)
        self.plugin.preview_xy_timer.stop()


class SimpleForcingTableTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plugin = make_plugin()

    def setUp(self):
        self.plugin.clear_settings_create_sim_tab()
        self.plugin.iface.bar.messages.clear()

    def table(self, hour):
        t = self.plugin.dlg.tableWidget
        return [t.item(hour, 0).text(), t.item(hour, 1).text()]

    def set_extremes(self, t_min_hour, t_max_hour, h_min_hour, h_max_hour):
        dlg = self.plugin.dlg
        dlg.sb_timeMinT.setValue(t_min_hour)
        dlg.sb_timeMaxT.setValue(t_max_hour)
        dlg.sb_timeMinHum.setValue(h_min_hour)
        dlg.sb_timeMaxHum.setValue(h_max_hour)
        self.plugin.update_temp_and_hum_simpleforcing()

    def test_default_profile(self):
        # defaults (as ENVI-guide): T 17 degC at 05:00, 28 degC at 16:00; rel. humidity 75 % at 04:00, 43 % at 16:00
        self.assertEqual(self.table(0), ['21.23', '64.33'])
        self.assertEqual(self.table(1), ['20.38', '67.0'])
        self.assertEqual(self.table(4), ['17.85', '75.0'])
        self.assertEqual(self.table(5), ['17.0', '72.33'])
        self.assertEqual(self.table(16), ['28.0', '43.0'])

    def test_humidity_falls_back_over_its_own_night(self):
        """M5: with the humidity maximum after its minimum, the night used the temperature hours."""
        dlg = self.plugin.dlg
        dlg.hs_minHum.setValue(40)
        dlg.hs_maxHum.setValue(80)
        self.set_extremes(5, 16, 4, 14)
        # 14:00 -> 04:00 (next day) is 14 hours, so 40 % per 14 h
        self.assertEqual(self.table(14)[1], '80.0')
        self.assertEqual(self.table(15)[1], str(round(80 - 40 / 14, 2)))
        self.assertEqual(self.table(4)[1], '40.0')

    def test_equal_hours_are_reported(self):
        before = self.table(10)
        self.set_extremes(10, 10, 5, 16)
        self.assertEqual(self.table(10), before)
        self.assertEqual(len(self.plugin.iface.bar.messages), 1)


class LoadSimxTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plugin = make_plugin()
        cls.tmp = tempfile.mkdtemp(prefix='g2e_simx_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.plugin.clear_settings_create_sim_tab()
        self.plugin.iface.bar.messages.clear()

    def test_round_trip_of_a_plugin_simx(self):
        dlg = self.plugin.dlg
        path = os.path.join(self.tmp, 'roundtrip.simx')
        dlg.le_fullSimName.setText('Courtyard')
        dlg.hs_maxT.setValue(31)
        dlg.sb_timeMaxT.setValue(15)
        self.plugin.update_temp_and_hum_simpleforcing()
        dlg.le_simxDest.setText(path)
        dlg.le_inxForSim.setText('area.INX')
        self.plugin.simsettings_change()
        self.plugin.installed_envimet_version = lambda: (6, 0, 0)
        try:
            self.plugin.save_simx_file()
        finally:
            del self.plugin.installed_envimet_version
        self.assertEqual(self.plugin.iface.bar.messages, [])

        self.plugin.clear_settings_create_sim_tab()
        self.plugin.load_simx_file(path)
        self.assertEqual(self.plugin.iface.bar.messages, [])
        self.assertTrue(dlg.tw_Main.isEnabled())
        self.assertEqual(dlg.lb_loadedSimx.text(), path)
        self.assertEqual(dlg.le_fullSimName.text(), 'Courtyard')
        self.assertEqual((dlg.hs_maxT.value(), dlg.sb_timeMaxT.value()), (31, 15))

    def test_unreadable_simx_is_reported_not_frozen(self):
        path = os.path.join(self.tmp, 'broken.simx')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"Header": {"filetype": "simConfJSON"}, "mainData": ')
        self.plugin.load_simx_file(path)
        self.assertTrue(self.plugin.dlg.tw_Main.isEnabled())
        self.assertEqual(len(self.plugin.iface.bar.messages), 1)
        self.assertIn('JSON', self.plugin.iface.bar.messages[0][1])
        self.assertEqual(self.plugin.dlg.lb_loadedSimx.text(), 'None')
        self.assertIsNone(self.plugin.loaded_simx)


if __name__ == '__main__':
    unittest.main()
