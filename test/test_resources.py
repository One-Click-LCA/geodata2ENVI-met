# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'helge.simon@envi-met.com'
__date__ = '2021-12-10'
__copyright__ = 'Copyright 2021, Helge Simon'

import unittest

from qgis.PyQt.QtGui import QIcon

from .plugin_env import import_plugin_module, start_qgis


class Geo2ENVImetDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self):
        """Runs before each test."""
        start_qgis()
        import_plugin_module('resources')

    def tearDown(self):
        """Runs after each test."""
        pass

    def test_icon_png(self):
        """The plugin icon is in the compiled resources."""
        path = ':/plugins/geodata2ENVImet/icon.png'
        icon = QIcon(path)
        self.assertFalse(icon.isNull())


if __name__ == "__main__":
    suite = unittest.makeSuite(Geo2ENVImetDialogTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
