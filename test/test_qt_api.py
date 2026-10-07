# coding=utf-8
"""Every Qt/QGIS class attribute the plugin uses must exist in the running QGIS.

PyQt6 (QGIS 4) dropped the unscoped enum aliases such as ``QMessageBox.Ok``;
they only fail at the moment the line runs. This test evaluates every
``ClassName.attribute`` expression in the plugin's own modules, so running the
suite in QGIS 3 and QGIS 4 catches them all.
"""

import os
import re
import unittest

from .plugin_env import PLUGIN_DIR, start_qgis

_EXPRESSION = re.compile(
    r'\b((?:Qgs|Q)[A-Z][A-Za-z0-9]*|Qgis|Qt)\.([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)')


def plugin_sources():
    folders = [PLUGIN_DIR, os.path.join(PLUGIN_DIR, 'core')]
    for folder in folders:
        for name in sorted(os.listdir(folder)):
            if name.endswith('.py') and name != 'resources.py':
                yield os.path.join(folder, name)


class QtApiTest(unittest.TestCase):

    def test_all_attributes_exist(self):
        start_qgis()
        import qgis.core
        import qgis.gui
        from qgis.PyQt import QtCore, QtGui, QtWidgets
        namespace = {}
        for module in (QtCore, QtGui, QtWidgets, qgis.gui, qgis.core):
            namespace.update({k: getattr(module, k) for k in dir(module) if not k.startswith('_')})

        expressions = {}
        for path in plugin_sources():
            with open(path, encoding='utf-8') as f:
                for number, line in enumerate(f, 1):
                    code = line.split('#', 1)[0]
                    for match in _EXPRESSION.finditer(code):
                        expression = f'{match.group(1)}.{match.group(2)}'
                        expressions.setdefault(expression, f'{os.path.basename(path)}:{number}')

        failing = []
        for expression, where in sorted(expressions.items()):
            if expression.split('.')[0] not in namespace:
                continue
            try:
                eval(expression, namespace)
            except AttributeError as error:
                failing.append(f'{expression} ({where}): {error}')
        self.assertGreater(len(expressions), 20)
        self.assertEqual(failing, [])


if __name__ == '__main__':
    unittest.main()
