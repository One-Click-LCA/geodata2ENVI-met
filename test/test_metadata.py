# coding=utf-8
"""metadata.txt must let QGIS 4 load the plugin."""

import configparser
import os
import unittest

from .plugin_env import PLUGIN_DIR


class MetadataTest(unittest.TestCase):

    def test_qgis4_is_allowed(self):
        # Without qgisMaximumVersion, QGIS assumes <minimum major>.99 and marks the plugin
        # incompatible with QGIS 4.
        parser = configparser.ConfigParser()
        parser.optionxform = str
        parser.read(os.path.join(PLUGIN_DIR, 'metadata.txt'), encoding='utf-8')
        general = parser['general']
        self.assertIn('qgisMaximumVersion', general)
        major = int(general['qgisMaximumVersion'].split('.')[0])
        self.assertGreaterEqual(major, 4)


if __name__ == '__main__':
    unittest.main()
