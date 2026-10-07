"""Find the local ENVI-met installation and build the envicore_console command line.

ENVI-met's workspace manager stores the last used workspace and installation in
``%APPDATA%/ENVI-met/usersettings.setx``. The installed version is in
``<install>/sys.basedata/vctrl.edbx``, a JWT whose payload holds
``verMain``/``verSub1``/``verSub2``.

The console's command line changed in 5.9.5:

* up to 5.9.0 it takes three positional arguments: ``<workspace> <project> <simx>``;
* from 5.9.5 on it takes ``-workspace=<dir> -project=<name> -simx=<file>`` and
  ignores bare arguments, so a positional call opens the interactive menu.
"""

import base64
import json
import os
import re

# First version whose console parses -key=value arguments.
KEY_VALUE_CLI_SINCE = (5, 9, 5)

CLI_KEY_VALUE = 'key=value'
CLI_POSITIONAL = 'positional'


class EnvimetSettings:
    """What the plugin needs from usersettings.setx."""

    def __init__(self):
        self.workspace = ''
        self.install_path = ''
        self.user_path_mode = 0
        self.user_path_info = ''
        self.selected_python = ''


def usersettings_path():
    appdata = os.getenv('APPDATA')
    if not appdata:
        return ''
    return os.path.join(appdata, 'ENVI-met', 'usersettings.setx')


def read_text(path):
    """Read an ENVI-met text file: UTF-8 (with or without BOM), else Windows-1252."""
    with open(path, 'rb') as f:
        raw = f.read()
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1252', errors='replace')


def tag_values(text, tag):
    """Values of all single-line ``<tag> value </tag>`` elements, trimmed at the ends only."""
    return [m.group(1).strip() for m in re.finditer(r'<%s>([^<]*)</%s>' % (tag, tag), text)]


def _install_from_marker_folder(path, marker):
    """``<install>/<marker>`` -> ``<install>``; '' if ``path`` is not such a folder."""
    if not path:
        return ''
    path = os.path.normpath(path)
    if os.path.basename(path).lower() == marker:
        return os.path.dirname(path)
    return ''


def read_usersettings(path=None):
    """Parse usersettings.setx; None if it does not exist."""
    path = path or usersettings_path()
    if not path or not os.path.isfile(path):
        return None
    text = read_text(path)
    settings = EnvimetSettings()

    workspace = tag_values(text, 'absolute_path')
    if workspace and workspace[0]:
        settings.workspace = os.path.normpath(workspace[0])

    mode = tag_values(text, 'userpathmode')
    if mode:
        try:
            settings.user_path_mode = int(mode[0])
        except ValueError:
            settings.user_path_mode = 0
    # <userpathinfo> wraps <userpathmode> and an inner one-line <userpathinfo>
    info = [v for v in tag_values(text, 'userpathinfo') if v]
    if info:
        settings.user_path_info = os.path.normpath(info[0])
    python = tag_values(text, 'selectedPython')
    if python and python[0]:
        settings.selected_python = os.path.normpath(python[0])

    # In the default user-path mode the user data folder is <install>/sys.userdata. In
    # "individual path" mode it can be anywhere, so fall back to <install>/sys.python.
    candidates = []
    if settings.user_path_mode == 0:
        candidates.append(_install_from_marker_folder(settings.user_path_info, 'sys.userdata'))
    candidates.append(_install_from_marker_folder(settings.selected_python, 'sys.python'))
    candidates.append(_install_from_marker_folder(settings.user_path_info, 'sys.userdata'))
    for candidate in candidates:
        if candidate and os.path.isfile(console_exe(candidate)):
            settings.install_path = candidate
            break
    else:
        settings.install_path = next((c for c in candidates if c), '')
    return settings


def console_exe(install_path):
    return os.path.join(install_path, 'win64', 'envicore_console.exe')


def read_installed_version(install_path):
    """(major, minor, patch) from sys.basedata/vctrl.edbx, or None if it can't be read.

    Since 5.8 the file is a JWT whose payload holds verMain/verSub1/verSub2; up to
    5.7 it is XML whose ``<ver>`` holds the three numbers base64-encoded, joined by '#'.
    """
    path = os.path.join(install_path, 'sys.basedata', 'vctrl.edbx')
    try:
        with open(path, 'rb') as f:
            content = f.read().decode('utf-8', errors='ignore').lstrip('﻿').strip()
        if content.startswith('<'):
            parts = tag_values(content, 'ver')[0].split('#')
            return tuple(int(base64.b64decode(part).decode('ascii')) for part in parts[:3])
        payload = content.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return int(data['verMain']), int(data['verSub1']), int(data['verSub2'])
    except (OSError, IndexError, KeyError, TypeError, ValueError):
        return None


def cli_style(version):
    """Argument style for a console version; unknown versions get the current style."""
    if version is None or tuple(version) >= KEY_VALUE_CLI_SINCE:
        return CLI_KEY_VALUE
    return CLI_POSITIONAL


def build_console_command(install_path, workspace, project_name, simx_file, version):
    """Argument list for subprocess. ``simx_file`` is relative to the project folder."""
    exe = console_exe(install_path)
    workspace = os.path.normpath(workspace)
    if cli_style(version) == CLI_KEY_VALUE:
        return [exe, f'-workspace={workspace}', f'-project={project_name}', f'-simx={simx_file}']
    return [exe, workspace, project_name, simx_file]


def project_info_file(project_folder):
    """Path of the folder's project.infoX (ENVI-met also writes 'project.infox'), or ''."""
    try:
        names = os.listdir(project_folder)
    except OSError:
        return ''
    for name in names:
        if name.lower() == 'project.infox' and os.path.isfile(os.path.join(project_folder, name)):
            return os.path.join(project_folder, name)
    return ''


def read_project_name(project_folder):
    """The project's name from project.infoX ('' if missing).

    The file also holds the names of scenarios, so only the ``<name>`` inside
    ``<project_description>`` counts.
    """
    path = project_info_file(project_folder)
    if not path:
        return ''
    text = read_text(path)
    block = re.search(r'<project_description>(.*?)</project_description>', text, re.DOTALL)
    names = tag_values(block.group(1) if block else '', 'name')
    return names[0] if names else ''


def is_inside(path, folder):
    """True if ``path`` is ``folder`` or lies below it (case-insensitive on Windows)."""
    path = os.path.normcase(os.path.normpath(os.path.abspath(path)))
    folder = os.path.normcase(os.path.normpath(os.path.abspath(folder)))
    try:
        return os.path.commonpath([path, folder]) == folder
    except ValueError:
        # different drives
        return False


def relative_to(path, folder):
    """``path`` relative to ``folder``, with forward slashes as ENVI-met writes them."""
    return os.path.relpath(os.path.normpath(path), os.path.normpath(folder)).replace('\\', '/')
