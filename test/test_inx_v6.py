# coding=utf-8
"""ENVI-met 6 additions to the INX export: indoor climate per building and the surrounding area."""

import os
import re
import shutil
import tempfile
import unittest

from . import inx_scenario
from .inx_helpers import make_layer, new_worker, rectangle_wkt, set_buildings
from .plugin_env import import_plugin_module, make_plugin, start_qgis

CRS = 'EPSG:32632'
X0, Y0 = 500000.0, 5400000.0
DX = 2.0


def building_tags(text):
    """{building number: {tag: value}} of the <Buildinginfo> sections."""
    found = {}
    for block in re.findall(r'<Buildinginfo>(.*?)</Buildinginfo>', text, re.S):
        tags = dict(re.findall(r'<(\w+)>\s*(.*?)\s*</\1>', block))
        found[int(tags['BuildingInternalNr'])] = tags
    return found


def section(text, name):
    match = re.search(r'<%s>(.*?)</%s>' % (name, name), text, re.S)
    return dict(re.findall(r'<(\w+)>\s*(.*?)\s*</\1>', match.group(1))) if match else None


class IndoorValuesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.indoor = import_plugin_module('core.indoor')

    def test_building_use(self):
        use = self.indoor.building_use
        self.assertEqual(use(None), (0, True))
        self.assertEqual(use('NULL'), (0, True))
        self.assertEqual(use(-1), (0, True))           # user code -1: not stated, INX code 0
        self.assertEqual(use(2), (2, True))
        self.assertEqual(use('4.0'), (4, True))
        self.assertEqual(use(' Office '), (2, True))
        self.assertEqual(use('residential'), (1, True))
        self.assertEqual(use('Warehouse'), (4, True))
        self.assertEqual(use(0), (0, False))           # the user codes start at 1
        self.assertEqual(use(7), (0, False))
        self.assertEqual(use('2.5'), (0, False))
        self.assertEqual(use('castle'), (0, False))

    def test_indoor_mode(self):
        mode = self.indoor.indoor_mode
        self.assertEqual(mode(''), (-1, True))
        self.assertEqual(mode(-1), (-1, True))
        self.assertEqual(mode(1), (0, True))           # user codes 1..4 are INX codes 0..3
        self.assertEqual(mode(4), (3, True))
        self.assertEqual(mode('AC'), (3, True))
        self.assertEqual(mode('air-conditioned'), (3, True))
        self.assertEqual(mode('free-running'), (0, True))
        self.assertEqual(mode('Mixed Mode'), (2, True))
        self.assertEqual(mode(0), (-1, False))
        self.assertEqual(mode(5), (-1, False))

    def test_numbers(self):
        self.assertEqual(self.indoor.threshold(''), (-99.0, True))
        self.assertEqual(self.indoor.threshold(-99), (-99.0, True))
        self.assertEqual(self.indoor.threshold('21,5'), (21.5, True))
        self.assertEqual(self.indoor.threshold(80), (-99.0, False))
        self.assertEqual(self.indoor.threshold('warm'), (-99.0, False))
        self.assertEqual(self.indoor.internal_gain(None), (8.0, True))
        self.assertEqual(self.indoor.internal_gain('12'), (12.0, True))
        self.assertEqual(self.indoor.internal_gain(-1), (8.0, False))

    def test_tag_lines_default_to_not_stated(self):
        self.assertEqual(self.indoor.tag_lines({}), [
            '    <BuildingUse> 0 </BuildingUse>',
            '    <BuildingIndoorMode> -1 </BuildingIndoorMode>',
            '    <BuildingIndoorLower> -99.00 </BuildingIndoorLower>',
            '    <BuildingIndoorUpper> -99.00 </BuildingIndoorUpper>',
            '    <BuildingInternalGain> 8.00 </BuildingInternalGain>',
            '    <BuildingSuppressACHeat> 0 </BuildingSuppressACHeat>'])


class SurroundingAreaTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.s = import_plugin_module('core.surrounding')

    def test_types(self):
        self.assertEqual(len(self.s.TYPES), 27)
        self.assertEqual(self.s.TYPES[self.s.DEFAULT_TYPE], 'Compact mid-rise')
        self.assertEqual(self.s.TYPES[-1], 'Open water')

    def test_border_directions(self):
        self.assertEqual(self.s.border_labels(0), {'Left': 'Left border (faces west):',
                                                   'Right': 'Right border (faces east):',
                                                   'Front': 'Front border (faces south):',
                                                   'Rear': 'Rear border (faces north):'})
        # model rotation is clockwise: at 90 degrees the grid's +x axis points south
        labels = self.s.border_labels(90)
        self.assertEqual((labels['Left'], labels['Right'], labels['Front'], labels['Rear']),
                         ('Left border (faces north):', 'Right border (faces south):',
                          'Front border (faces west):', 'Rear border (faces east):'))
        self.assertEqual(self.s.border_labels(-45)['Rear'], 'Rear border (faces north-west):')
        self.assertEqual(self.s.border_labels(None)['Left'], 'Left border:')

    def test_rotation_from_the_lower_edge(self):
        self.assertAlmostEqual(self.s.rotation_from_bearing(115.0), 25.0)
        self.assertAlmostEqual(self.s.rotation_from_bearing(90.0), 0.0)
        self.assertAlmostEqual(self.s.rotation_from_bearing(280.0), -170.0)

    def test_section_lines(self):
        lines = self.s.section_lines(False, {'Left': 0, 'Right': 26, 'Front': 99})
        self.assertEqual(lines, ['  <SurroundingArea>', '    <useSurroundingArea> 0 </useSurroundingArea>',
                                 '    <borderLeft> 0 </borderLeft>', '    <borderRight> 26 </borderRight>',
                                 '    <borderFront> 1 </borderFront>', '    <borderRear> 1 </borderRear>',
                                 '  </SurroundingArea>'])


class InxExportV6Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        start_qgis()
        consts = import_plugin_module('Const_defines')
        cls.INT, cls.STR, cls.DOUBLE = consts.FIELD_TYPE_INT, consts.FIELD_TYPE_STRING, consts.FIELD_TYPE_DOUBLE
        cls.tmp = tempfile.mkdtemp(prefix='g2e_inx6_')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def export(self, name, configure):
        sub_area = make_layer('Polygon', CRS, [(rectangle_wkt(X0, Y0, X0 + 20 * DX, Y0 + 16 * DX), [])])
        path = os.path.join(self.tmp, name + '.INX')
        worker = new_worker(sub_area, dx=DX, dy=DX, filename=path)
        configure(worker)
        worker.saveINX()
        with open(path, encoding='utf-8') as f:
            return f.read(), worker

    def buildings(self):
        return make_layer('Polygon', CRS, [
            (rectangle_wkt(X0 + 4 * DX, Y0 + 2 * DX, X0 + 7 * DX, Y0 + 5 * DX), [10, 'office', 21.5]),
            (rectangle_wkt(X0 + 10 * DX, Y0 + 8 * DX, X0 + 14 * DX, Y0 + 12 * DX), [20, 'castle', None]),
        ], fields=[('h', self.INT), ('use', self.STR), ('lower', self.DOUBLE)])

    def test_defaults(self):
        text, worker = self.export('defaults', lambda w: set_buildings(w, self.buildings(), 'h'))
        tags = building_tags(text)
        self.assertEqual(len(tags), 2)
        for values in tags.values():
            self.assertEqual((values['BuildingUse'], values['BuildingIndoorMode'], values['BuildingIndoorLower'],
                              values['BuildingIndoorUpper'], values['BuildingInternalGain'],
                              values['BuildingSuppressACHeat']), ('0', '-1', '-99.00', '-99.00', '8.00', '0'))
        self.assertEqual(section(text, 'SurroundingArea'),
                         {'useSurroundingArea': '1', 'borderLeft': '1', 'borderRight': '1', 'borderFront': '1',
                          'borderRear': '1'})
        # the section sits between nestingArea and locationData, as SPACES writes it
        self.assertLess(text.index('</nestingArea>'), text.index('<SurroundingArea>'))
        self.assertLess(text.index('</SurroundingArea>'), text.index('<locationData>'))
        self.assertEqual(worker.warnings, [])

    def test_fields_and_static_values(self):
        def configure(worker):
            set_buildings(worker, self.buildings(), 'h')
            worker.bIndoor.update(use=('use', ''), lower=('lower', ''), mode=(None, 4), gain=(None, '12'))
            worker.bSuppressACHeat = True
            worker.useSurroundingArea = False
            worker.surroundingBorders = {'Left': 0, 'Right': 5, 'Front': 26, 'Rear': 17}

        text, worker = self.export('values', configure)
        tags = sorted(building_tags(text).values(), key=lambda t: t['BuildingUse'], reverse=True)
        office, castle = tags
        self.assertEqual((office['BuildingUse'], office['BuildingIndoorLower']), ('2', '21.50'))
        self.assertEqual((castle['BuildingUse'], castle['BuildingIndoorLower']), ('0', '-99.00'))
        for values in tags:
            self.assertEqual((values['BuildingIndoorMode'], values['BuildingIndoorUpper'],
                              values['BuildingInternalGain'], values['BuildingSuppressACHeat']),
                             ('3', '-99.00', '12.00', '1'))
        self.assertEqual(section(text, 'SurroundingArea'),
                         {'useSurroundingArea': '0', 'borderLeft': '0', 'borderRight': '5', 'borderFront': '26',
                          'borderRear': '17'})
        self.assertEqual(len(worker.warnings), 1)
        self.assertIn("field 'use'", worker.warnings[0])
        self.assertIn("'castle'", worker.warnings[0])


class DialogV6Test(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.plugin = make_plugin()

    def test_border_labels_follow_the_sub_area(self):
        from qgis.core import QgsProject
        dlg = self.plugin.dlg
        self.assertEqual(dlg.lb_borderLeft.text(), 'Left border:')
        layer = inx_scenario.sub_area()       # rotated clockwise by 25 degrees
        QgsProject.instance().addMapLayer(layer)
        # without the layer-changed signal: it also starts a worker thread on the layer
        dlg.cb_subArea.blockSignals(True)
        try:
            dlg.cb_subArea.setLayer(layer)
            self.plugin.update_surrounding_page()
            # true north differs from the UTM grid north by about 2 degrees there
            rotation = self.plugin.sub_area_rotation()
            self.assertAlmostEqual(rotation, inx_scenario.ROTATION, delta=3)
            labels = import_plugin_module('core.surrounding').border_labels(rotation)
            self.assertEqual([dlg.lb_borderLeft.text(), dlg.lb_borderRight.text(), dlg.lb_borderFront.text(),
                              dlg.lb_borderRear.text()],
                             [labels['Left'], labels['Right'], labels['Front'], labels['Rear']])
            self.assertIn('south-east', dlg.lb_borderRight.text())
            self.assertIn('about 2', dlg.lb_borderDirections.text())
        finally:
            dlg.cb_subArea.setLayer(None)
            dlg.cb_subArea.blockSignals(False)
            QgsProject.instance().removeMapLayer(layer.id())
        self.plugin.update_surrounding_page()
        self.assertEqual(dlg.lb_borderLeft.text(), 'Left border:')

    def test_surrounding_area_switch(self):
        dlg = self.plugin.dlg
        self.assertEqual(dlg.cb_borderFront.count(), 27)
        self.assertEqual(dlg.cb_borderFront.currentText(), 'Compact mid-rise')
        dlg.chk_surroundingArea.setChecked(False)
        self.assertFalse(dlg.cb_borderFront.isEnabledTo(dlg.tab_surrounding))
        dlg.chk_surroundingArea.setChecked(True)
        self.assertTrue(dlg.cb_borderFront.isEnabledTo(dlg.tab_surrounding))

    def test_settings_reach_the_worker(self):
        dlg = self.plugin.dlg
        dlg.cmb_bIndoorMode.setCurrentIndex(4)
        dlg.cmb_bUse.setCurrentIndex(3)
        dlg.le_bInternalGain.setText('12')
        dlg.chk_bIndoorLower.setChecked(False)          # a field, but none chosen: not stated
        dlg.chk_bSuppressACHeat.setChecked(True)
        dlg.cb_borderRear.setCurrentIndex(26)
        worker_module = import_plugin_module('Worker')
        self.plugin.worker = worker_module.Worker()
        try:
            self.plugin.transfer_building_info_to_worker()
            self.plugin.transfer_subarea_gridding_info_to_worker()
            worker = self.plugin.worker
            # user codes: the fourth entry of each box is 3, the fifth 4
            self.assertEqual(worker.bIndoor, {'use': (None, 3), 'mode': (None, 4), 'lower': (None, ''),
                                              'upper': (None, ''), 'gain': (None, '12')})
            self.assertTrue(worker.bSuppressACHeat)
            self.assertEqual(worker.surroundingBorders, {'Left': 1, 'Right': 1, 'Front': 1, 'Rear': 26})
        finally:
            self.plugin.worker = None
            dlg.chk_bIndoorLower.setChecked(True)
            dlg.chk_bSuppressACHeat.setChecked(False)
            dlg.cb_borderRear.setCurrentIndex(1)


if __name__ == '__main__':
    unittest.main()
