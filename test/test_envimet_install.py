# coding=utf-8
"""Finding the ENVI-met installation and starting envicore_console ("Start simulation")."""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from .plugin_env import import_plugin_module, make_plugin

BOM = '﻿'


def b64url(data):
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def make_install(root, version):
    """Fake installation: the console exe and sys.basedata/vctrl.edbx (a JWT)."""
    os.makedirs(os.path.join(root, 'win64'), exist_ok=True)
    os.makedirs(os.path.join(root, 'sys.basedata'), exist_ok=True)
    open(os.path.join(root, 'win64', 'envicore_console.exe'), 'wb').close()
    if version is not None:
        payload = {'verMain': version[0], 'verSub1': version[1], 'verSub2': version[2],
                   'titles': 'V%d.%d.%d test' % version}
        token = '.'.join([b64url(b'{"alg":"RS256","typ":"JWT"}'),
                          b64url(json.dumps(payload).encode('utf-8')), b64url(b'signature')])
        with open(os.path.join(root, 'sys.basedata', 'vctrl.edbx'), 'w', encoding='ascii') as f:
            f.write(token)
    return root


def write_usersettings(path, workspace, user_data, python='', mode=0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = (BOM + '<ENVI-MET_Datafile>\n<Header>\n<filetype>SETX ENVI-met user settings</filetype>\n</Header>\n'
            '<workspace>\n'
            f'<absolute_path> {workspace} </absolute_path>\n'
            '</workspace>\n'
            f'<selectedPython> {python} </selectedPython>\n'
            '<userpathinfo>\n'
            f'<userpathmode> {mode} </userpathmode>\n'
            f'<userpathinfo> {user_data} </userpathinfo>\n'
            '</userpathinfo>\n'
            '</ENVI-MET_Datafile>\n')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def write_project(folder, name, file_name='project.infoX'):
    os.makedirs(folder, exist_ok=True)
    text = ('<ENVI-MET_Datafile>\n<Header>\n<filetype>infoX ENVI-met Project Description File</filetype>\n'
            '</Header>\n'
            '  <project_description>\n'
            f'     <name> {name} </name>\n'
            '     <description>  </description>\n'
            '  </project_description>\n'
            '  <scenario>\n'
            '     <name> Scenario A </name>\n'
            '  </scenario>\n'
            '</ENVI-MET_Datafile>\n')
    with open(os.path.join(folder, file_name), 'w', encoding='utf-8') as f:
        f.write(text)


class EnvimetInstallTest(unittest.TestCase):

    def setUp(self):
        self.ei = import_plugin_module('core.envimet_install')
        self.tmp = tempfile.mkdtemp(prefix='g2e install ')   # spaces on purpose

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_usersettings_keep_inner_spaces(self):
        install = make_install(os.path.join(self.tmp, 'ENVI met 6'), (6, 0, 0))
        workspace = os.path.join(self.tmp, 'My Workspace')
        path = os.path.join(self.tmp, 'usersettings.setx')
        write_usersettings(path, workspace, os.path.join(install, 'sys.userdata'),
                           python=os.path.join(install, 'sys.python'))
        settings = self.ei.read_usersettings(path)
        self.assertEqual(settings.workspace, os.path.normpath(workspace))
        self.assertEqual(settings.install_path, os.path.normpath(install))

    def test_individual_user_path_uses_sys_python(self):
        install = make_install(os.path.join(self.tmp, 'ENVImet6'), (6, 0, 0))
        path = os.path.join(self.tmp, 'usersettings.setx')
        write_usersettings(path, self.tmp, os.path.join(self.tmp, 'Documents', 'my envi data'),
                           python=os.path.join(install, 'sys.python'), mode=1)
        self.assertEqual(self.ei.read_usersettings(path).install_path, os.path.normpath(install))

    def test_missing_usersettings(self):
        self.assertIsNone(self.ei.read_usersettings(os.path.join(self.tmp, 'nothing.setx')))

    def test_version_and_argument_style(self):
        for version, style in (((6, 0, 0), self.ei.CLI_KEY_VALUE), ((5, 9, 5), self.ei.CLI_KEY_VALUE),
                               ((5, 9, 0), self.ei.CLI_POSITIONAL), ((5, 8, 0), self.ei.CLI_POSITIONAL)):
            install = make_install(os.path.join(self.tmp, 'v%d%d%d' % version), version)
            read = self.ei.read_installed_version(install)
            self.assertEqual(read, version)
            self.assertEqual(self.ei.cli_style(read), style)

    def test_version_from_xml_file_up_to_5_7(self):
        install = make_install(os.path.join(self.tmp, 'v561'), None)
        ver = '#'.join(base64.b64encode(str(n).encode()).decode() for n in (5, 6, 1))
        with open(os.path.join(install, 'sys.basedata', 'vctrl.edbx'), 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<XML>\n  <data>\n'
                    f'    <ver>{ver}</ver>\n    <titles>VjUuNi4xIFdpbnRlcjIz</titles>\n  </data>\n</XML>\n')
        self.assertEqual(self.ei.read_installed_version(install), (5, 6, 1))
        self.assertEqual(self.ei.cli_style((5, 6, 1)), self.ei.CLI_POSITIONAL)

    def test_unreadable_version_gets_key_value(self):
        install = make_install(os.path.join(self.tmp, 'noversion'), None)
        self.assertIsNone(self.ei.read_installed_version(install))
        with open(os.path.join(install, 'sys.basedata', 'vctrl.edbx'), 'w') as f:
            f.write('not a token')
        self.assertIsNone(self.ei.read_installed_version(install))
        self.assertEqual(self.ei.cli_style(None), self.ei.CLI_KEY_VALUE)

    def test_build_console_command(self):
        install = os.path.join(self.tmp, 'ENVI met')
        exe = os.path.join(install, 'win64', 'envicore_console.exe')
        workspace = os.path.join(self.tmp, 'My Workspace')
        new = self.ei.build_console_command(install, workspace + os.sep, 'My Project', 'run 1.simx', (6, 0, 0))
        self.assertEqual(new, [exe, '-workspace=' + os.path.normpath(workspace), '-project=My Project',
                               '-simx=run 1.simx'])
        old = self.ei.build_console_command(install, workspace, 'My Project', 'run 1.simx', (5, 9, 0))
        self.assertEqual(old, [exe, os.path.normpath(workspace), 'My Project', 'run 1.simx'])

    def test_project_name_ignores_scenarios(self):
        folder = os.path.join(self.tmp, 'AAA')
        write_project(folder, 'CCCC', file_name='project.infox')
        self.assertEqual(self.ei.read_project_name(folder), 'CCCC')
        self.assertEqual(self.ei.read_project_name(os.path.join(self.tmp, 'missing')), '')

    def test_paths_inside_folders(self):
        folder = os.path.join(self.tmp, 'ws', 'proj')
        self.assertTrue(self.ei.is_inside(os.path.join(folder, 'sub', 'a.simx'), folder))
        self.assertTrue(self.ei.is_inside(folder.upper() if os.name == 'nt' else folder, folder))
        self.assertFalse(self.ei.is_inside(os.path.join(self.tmp, 'ws', 'proj2', 'a.simx'), folder))
        self.assertEqual(self.ei.relative_to(os.path.join(folder, 'sub', 'a.simx'), folder), 'sub/a.simx')


class StartSimulationTest(unittest.TestCase):
    """Geo2ENVImet.start_sim against a fake installation, workspace and project."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='g2e start ')
        self.appdata = os.environ.get('APPDATA')
        os.environ['APPDATA'] = os.path.join(self.tmp, 'AppData')
        self.workspace = os.path.join(self.tmp, 'My Workspace')
        self.project = os.path.join(self.workspace, 'Project Folder')
        write_project(self.project, 'Courtyard Study')
        self.simx = os.path.join(self.project, 'hot day.simx')
        open(self.simx, 'w').close()
        self.plugin = make_plugin()
        self.plugin.dlg.lb_simxFile.setText(self.simx)
        self.plugin.dlg.lb_selected_projFolder.setText(self.project)
        self.plugin.iface.bar.messages.clear()
        self.started = []
        self.popen = subprocess.Popen
        subprocess.Popen = lambda args, **kwargs: self.started.append(args)

    def tearDown(self):
        subprocess.Popen = self.popen
        if self.appdata is None:
            del os.environ['APPDATA']
        else:
            os.environ['APPDATA'] = self.appdata
        shutil.rmtree(self.tmp, ignore_errors=True)

    def install(self, version):
        install = make_install(os.path.join(self.tmp, 'ENVI met'), version)
        write_usersettings(os.path.join(self.tmp, 'AppData', 'ENVI-met', 'usersettings.setx'), self.workspace,
                           os.path.join(install, 'sys.userdata'), python=os.path.join(install, 'sys.python'))
        return os.path.join(install, 'win64', 'envicore_console.exe')

    def test_version_6_gets_key_value_arguments(self):
        exe = self.install((6, 0, 0))
        self.plugin.start_sim()
        self.assertEqual(self.plugin.iface.bar.messages, [])
        self.assertEqual(self.started, [[exe, '-workspace=' + self.workspace, '-project=Courtyard Study',
                                         '-simx=hot day.simx']])

    def test_version_5_9_0_gets_positional_arguments(self):
        exe = self.install((5, 9, 0))
        self.plugin.start_sim()
        self.assertEqual(self.started, [[exe, self.workspace, 'Courtyard Study', 'hot day.simx']])

    def test_simx_outside_project_is_refused(self):
        self.install((6, 0, 0))
        outside = os.path.join(self.tmp, 'elsewhere.simx')
        open(outside, 'w').close()
        self.plugin.dlg.lb_simxFile.setText(outside)
        self.plugin.start_sim()
        self.assertEqual(self.started, [])
        self.assertIn('not inside the selected ENVI-met project-folder', self.plugin.iface.bar.messages[0][1])


if __name__ == '__main__':
    unittest.main()
