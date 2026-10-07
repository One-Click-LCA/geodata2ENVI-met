# coding=utf-8
"""core.inx_arrays (plain Python)."""

import unittest

import numpy as np

from .plugin_env import import_plugin_module


class InxArraysTest(unittest.TestCase):

    def setUp(self):
        self.a = import_plugin_module('core.inx_arrays')

    def test_map_codes(self):
        codes = np.array([[0, 1, 2], [-1, 2, 7]])
        out = self.a.map_codes(codes, {1: '0100ST', 2: 'a receptor with a long name'}, default='0200PP')
        self.assertEqual(out.tolist(), [['0200PP', '0100ST', 'a receptor with a long name'],
                                        ['0200PP', 'a receptor with a long name', '0200PP']])

    def test_map_values(self):
        values = np.array([['1', '2'], ['3', '1']])
        self.assertEqual(self.a.map_values(values, {'1': '0100ST'}, other='0000AA').tolist(),
                         [['0100ST', '0000AA'], ['0000AA', '0100ST']])
        self.assertEqual(self.a.map_values(values, {'1': '0100ST'}, default='').tolist(),
                         [['0100ST', ''], ['', '0100ST']])

    def test_first_non_empty(self):
        p = np.array(['', 'P', ''])
        line = np.array(['L', 'L', ''])
        area = np.array(['A', 'A', 'A'])
        self.assertEqual(self.a.first_non_empty(p, line, area).tolist(), ['L', 'P', 'A'])

    def test_border_is_symmetric(self):
        mask = self.a.border_mask((8, 10), 2)
        self.assertEqual(mask.sum(axis=1).tolist(), [10, 10, 4, 4, 4, 4, 10, 10])
        self.assertEqual(mask.sum(axis=0).tolist(), [8, 8, 4, 4, 4, 4, 4, 4, 8, 8])

    def test_matrix_text(self):
        self.assertEqual(self.a.matrix_text(np.array([[1, 0], [12, 3]])), '     1,0\n     12,3')
        self.assertEqual(self.a.matrix_text(np.array([['0100ST', 'NULL']]), indent=''), '0100ST,')


if __name__ == '__main__':
    unittest.main()
