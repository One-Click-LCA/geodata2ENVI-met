# coding=utf-8
"""ENVImet_DB_loader: projects of a workspace."""

import os
import shutil
import tempfile
import unittest

from .plugin_env import import_plugin_module, start_qgis


class ProjectListTest(unittest.TestCase):

    def setUp(self):
        start_qgis()
        self.loader = import_plugin_module('ENVImet_DB_loader')
        self.workspace = tempfile.mkdtemp(prefix='g2e_ws_')

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def project(self, folder, use_db):
        os.makedirs(os.path.join(self.workspace, folder))
        with open(os.path.join(self.workspace, folder, 'project.infoX'), 'w', encoding='cp1252') as f:
            f.write(f'<project_description>\n<name> {folder} </name>\n<useProjectDB> {use_db} </useProjectDB>\n'
                    '</project_description>\n')

    def test_use_project_database_flag(self):
        self.project('with', 1)
        self.project('without', 0)
        projects = self.loader.EnviProjects.__new__(self.loader.EnviProjects)
        projects.workspace = self.workspace
        projects.projects = []
        projects.load_projects(self.workspace)
        flags = {p.name.strip(): p.useProjectDB for p in projects.projects}
        self.assertEqual(flags, {'with': True, 'without': False})


if __name__ == '__main__':
    unittest.main()
