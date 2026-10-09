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

    def test_utf8_project_names(self):
        """ENVI-met 6 writes UTF-8; reading it as Windows-1252 failed on names like this one."""
        os.makedirs(os.path.join(self.workspace, 'cn'))
        with open(os.path.join(self.workspace, 'cn', 'project.infoX'), 'w', encoding='utf-8') as f:
            f.write('<project_description>\n<name> 你好世界地理信息学 </name>\n</project_description>\n')
        projects = self.loader.EnviProjects.__new__(self.loader.EnviProjects)
        projects.workspace = self.workspace
        projects.projects = []
        projects.load_projects(self.workspace)
        self.assertEqual([p.name.strip() for p in projects.projects], ['你好世界地理信息学'])


class JsonDatabaseTest(unittest.TestCase):

    def setUp(self):
        start_qgis()
        self.loader = import_plugin_module('ENVImet_DB_loader')
        self.folder = tempfile.mkdtemp(prefix='g2e_db_')

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_envi_met_6_database(self):
        path = os.path.join(self.folder, 'database.edb')
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"envimetDatafile": {"header": {"fileType": "databaseJSON", "version": 1},\n'
                    ' "walls": [{"id": "0200AA", "desc": "Wall – default", "grp": "Default"}],\n'
                    ' "singleFaces": [{"id": "02000S", "desc": "SunSail"}],\n'
                    ' "waterSources": [{"id": "0200FT", "desc": "Fountain"}],\n'
                    ' "emitters": [{"id": "0200DR", "desc": "Lane"}],\n'
                    ' "plants3d": [{"id": "ED00NN", "desc": "Example Tree"}]}}\n')
        db = self.loader.ENVImetDB(filepath=path)
        self.assertEqual(db.filetype, 'databaseJSON')
        self.assertEqual(db.wall_dict['0200AA'].Description, 'Wall – default')
        self.assertEqual(db.singlewall_dict['02000S'].Description, 'SunSail')
        self.assertEqual(sorted(db.sources_dict), ['0200DR', '0200FT'])
        self.assertEqual(list(db.plant3d_dict), ['ED00NN'])


if __name__ == '__main__':
    unittest.main()
