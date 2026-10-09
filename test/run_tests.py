# coding=utf-8
"""Run the plugin's tests in a headless QGIS.

Run it with the Python of each supported QGIS, e.g. on Windows:

    "C:\\Program Files\\QGIS 3.34.12\\bin\\python-qgis-ltr.bat" test\\run_tests.py
    "C:\\Program Files\\QGIS 4.0.0\\bin\\python-qgis.bat" test\\run_tests.py

``-p test_inx*.py`` selects test files, ``-k name`` selects tests by name.

Optional checks against local data, skipped when the variable is not set:
G2E_TEST_OUTPUTS (a folder of real ENVI-met outputs) and G2E_ENVIMET_LIB (the
sources of ENVI-met's shared library, for the SIMX keys its reader expects).
"""

import argparse
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('-p', '--pattern', default='test_*.py', help='test file pattern')
    parser.add_argument('-k', dest='names', action='append', default=[],
                        help='only run tests whose id contains this text (repeatable)')
    args = parser.parse_args()

    # 'test' must resolve to this folder, not to the standard library's test package
    sys.path.insert(0, ROOT)
    from test import plugin_env
    plugin_env.start_qgis()
    plugin_env.register_plugin_package()

    from qgis.core import Qgis
    print(f'QGIS {Qgis.version()}, Python {sys.version.split()[0]}')

    suite = unittest.defaultTestLoader.discover(HERE, pattern=args.pattern, top_level_dir=ROOT)
    if args.names:
        def matching(s):
            for t in s:
                if isinstance(t, unittest.TestSuite):
                    yield from matching(t)
                elif any(n in t.id() for n in args.names):
                    yield t
        suite = unittest.TestSuite(matching(suite))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
