# coding=utf-8
"""The plugin object and its dialog: start-up and simple UI handlers."""

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


if __name__ == '__main__':
    unittest.main()
