# coding=utf-8
"""Shared set-up for the headless test suite.

The plugin folder is imported as the package ``geodata2ENVImet`` (its name when
installed), so tests can use ``import_plugin_module('Worker')`` without the
plugin being installed in a QGIS profile.

QGIS is started once per process, with a throwaway profile
(``QGIS_CUSTOM_CONFIG_PATH``) and a temporary working directory, so the tests
never touch the user's QGIS settings and leave no files in the repository
(QGIS writes ``symbology-style.db`` into the working directory).
"""

import importlib
import importlib.util
import os
import sys
import tempfile

PLUGIN_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir))
PLUGIN_PACKAGE = 'geodata2ENVImet'
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

_QGIS_APP = None


def register_plugin_package():
    """Import the plugin folder as the package ``geodata2ENVImet`` (idempotent)."""
    pkg = sys.modules.get(PLUGIN_PACKAGE)
    if pkg is not None:
        return pkg
    spec = importlib.util.spec_from_file_location(
        PLUGIN_PACKAGE, os.path.join(PLUGIN_DIR, '__init__.py'),
        submodule_search_locations=[PLUGIN_DIR])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[PLUGIN_PACKAGE] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def import_plugin_module(name):
    """Import ``geodata2ENVImet.<name>``, e.g. ``import_plugin_module('core.envimet_install')``."""
    register_plugin_package()
    return importlib.import_module(f'{PLUGIN_PACKAGE}.{name}')


def start_qgis():
    """Start one QgsApplication with Processing for the whole test run."""
    global _QGIS_APP
    if _QGIS_APP is not None:
        return _QGIS_APP
    os.environ.setdefault('QGIS_CUSTOM_CONFIG_PATH', tempfile.mkdtemp(prefix='g2e_test_profile_'))
    os.chdir(tempfile.mkdtemp(prefix='g2e_test_cwd_'))
    from qgis.core import QgsApplication
    _QGIS_APP = QgsApplication([], True)
    _QGIS_APP.initQgis()
    plugins_dir = os.path.join(QgsApplication.prefixPath(), 'python', 'plugins')
    if plugins_dir not in sys.path:
        sys.path.append(plugins_dir)
    from processing.core.Processing import Processing
    Processing.initialize()
    return _QGIS_APP


class IfaceStub:
    """The parts of QgisInterface the plugin calls, recording message-bar messages."""

    class _MessageBar:
        def __init__(self):
            self.messages = []

        def pushMessage(self, title, text, level=None, duration=None):
            self.messages.append((title, text, level))

    def __init__(self):
        self.bar = self._MessageBar()

    def messageBar(self):
        return self.bar

    def mainWindow(self):
        return None

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addPluginToMenu(self, menu, action):
        pass

    def removePluginMenu(self, menu, action):
        pass


class SlotErrors:
    """Collect exceptions raised in Qt slots (PyQt hands them to sys.excepthook).

    with SlotErrors() as errors:
        button.click()
    assert errors == []
    """

    def __enter__(self):
        self.errors = []
        self._hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(f'{kind.__name__}: {value}')
        return self.errors

    def __exit__(self, *exc):
        sys.excepthook = self._hook
        return False


def make_plugin():
    """Create the plugin object with its dialog built, as QGIS does on the first click."""
    start_qgis()
    main = import_plugin_module('geodata2ENVImet')
    plugin = main.Geo2ENVImet(IfaceStub())
    plugin.first_start = True
    plugin.setup_user_interface()
    return plugin
