# coding=utf-8
"""Dialog test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'helge.simon@envi-met.com'
__date__ = '2021-12-10'
__copyright__ = 'Copyright 2021, Helge Simon'

import unittest

from .plugin_env import import_plugin_module, start_qgis


class Geo2ENVImetDialogTest(unittest.TestCase):
    """Test dialog works."""

    def setUp(self):
        """Runs before each test."""
        start_qgis()
        dialog_module = import_plugin_module('geodata2ENVImet_dialog')
        self.dialog = dialog_module.Geo2ENVImetDialog(None)

    def tearDown(self):
        """Runs after each test."""
        self.dialog = None

    def test_dialog_builds(self):
        """The .ui file loads and has the main tabs."""
        self.assertGreater(self.dialog.tw_Main.count(), 0)


if __name__ == "__main__":
    unittest.main()
