# coding=utf-8
"""Common functionality used by regression tests."""

from .plugin_env import IfaceStub, start_qgis


def get_qgis_app():
    """ Start one QGIS application to test against.

    :returns: Handle to QGIS app, canvas, iface and parent. Canvas and parent are
        not needed by the plugin's tests and are None.
    :rtype: (QgsApplication, None, IfaceStub, None)
    """
    return start_qgis(), None, IfaceStub(), None
