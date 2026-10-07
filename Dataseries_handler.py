"""Series A and B of the Load results tab: their sources, time steps and variables."""

import warnings

from .core.readers import find_sources

try:
    # netCDF4 is a Cython extension. When its compiled binary was built against a
    # slightly different numpy ABI than the numpy QGIS bundles, importing it emits
    # a benign "numpy.ndarray size changed" RuntimeWarning. numpy keeps this case
    # forward-compatible, so the warning is harmless -- silence just that message.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="numpy.ndarray size changed",
                                category=RuntimeWarning)
        import netCDF4  # noqa: F401
except ImportError:
    # first we try to install netCDF4 from online source
    from qgis.PyQt.QtWidgets import QMessageBox
    QMessageBox.warning(None, 'Missing Library for Geodata2ENVI-met plugin',
                        "The Python library 'netCDF4' is required. It will now be installed. Please restart QGIS before using the plugin.",
                        QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)
    import os
    if os.system("pip install netCDF4") != 0:
        QMessageBox.warning(None, 'Missing Library for Geodata2ENVI-met plugin',
                            "The Python library 'netCDF4' is required. It should be installed automatically when you install the plugin while being online.",
                            QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Ok)

STATE_COMPARABLE = 'Comparable'
STATE_ONLY_A = 'Only Series A'
STATE_ONLY_B = 'Only Series B'


class timestep:
    """One time step of a series."""

    def __init__(self, source, step):
        self.source = source
        self.path = step.path
        self.index = step.index
        self.datetime = step.datetime
        # date and time as shown in the lists and layer names, e.g. '06.07.' and '05.00.00'
        self.date = step.datetime.strftime('%d.%m.')
        self.time = step.datetime.strftime('%H.%M.%S')


class merged_timestep:
    """The time steps of A and B at one moment; either may be missing (placeholder)."""

    def __init__(self, moment, tstpA=None, tstpB=None):
        self.datetime = moment
        self.timestepA = tstpA
        self.timestepB = tstpB
        self.placeholderA = tstpA is None
        self.placeholderB = tstpB is None
        self.checkedA = False
        self.checkedB = False
        self.delta_checked = False
        self.strDatetime = moment.strftime('%d.%m.%Y %H.%M.%S')


class VariableChoice:
    """A variable offered in the combo box, with its key in series A and/or B."""

    def __init__(self, label, long_name, key_a, key_b, units):
        self.label = label
        self.long_name = long_name
        self.key_a = key_a
        self.key_b = key_b
        self.units = units

    @property
    def state(self):
        if self.key_a is not None and self.key_b is not None:
            return STATE_COMPARABLE
        return STATE_ONLY_A if self.key_a is not None else STATE_ONLY_B

    def text(self):
        return f'{self.label} ({self.state})'


class dataseries_handler:
    def __init__(self):
        self.FolderA = ''
        self.FolderB = ''
        self.sources = {'A': [], 'B': []}
        self.selected_source = {'A': None, 'B': None}
        self.SeriesA = []
        self.SeriesB = []
        self.mergedList = []
        self.variables = []
        self.SelectedVariable = None
        self.SelectedHeight = 0.0
        self.SelectedSubArea = None
        self.CheckCount = 0

    # ------------------------------------------------------------------ folders and sources
    def set_folder(self, folder, series):
        """Find the sources in ``folder`` for series 'A' or 'B'; returns their names."""
        for source in self.sources[series]:
            source.close()
        if series == 'A':
            self.FolderA = folder
        else:
            self.FolderB = folder
        self.sources[series] = find_sources(folder) if folder else []
        self.selected_source[series] = self.sources[series][0] if self.sources[series] else None
        self.rebuild()
        return [s.name for s in self.sources[series]]

    def select_source(self, name, series):
        matches = [s for s in self.sources[series] if s.name == name]
        self.selected_source[series] = matches[0] if matches else None
        self.rebuild()

    def source_errors(self, series):
        source = self.selected_source[series]
        return list(source.errors) if source is not None else []

    def rebuild(self):
        """Time steps, merged list and variables from the selected sources."""
        self.SeriesA = self._series('A')
        self.SeriesB = self._series('B')
        self._merge()
        self._collect_variables()
        self.CheckCount = 0

    def _series(self, series):
        source = self.selected_source[series]
        if source is None:
            return []
        return [timestep(source, step) for step in source.timesteps]

    def _merge(self):
        by_time = {}
        for t in self.SeriesA:
            by_time.setdefault(t.datetime, [None, None])[0] = t
        for t in self.SeriesB:
            by_time.setdefault(t.datetime, [None, None])[1] = t
        self.mergedList = [merged_timestep(moment, a, b) for moment, (a, b) in sorted(by_time.items())]

    @staticmethod
    def _variables_of(series_list):
        if not series_list:
            return {}
        first = series_list[0]
        return first.source.open(first.path).variables

    def _collect_variables(self):
        vars_a = self._variables_of(self.SeriesA)
        vars_b = self._variables_of(self.SeriesB)
        # B's variables by long name, where that name is unique in B (EDX vs NetCDF comparisons)
        long_names_b = {}
        for v in vars_b.values():
            long_names_b.setdefault(v.long_name.lower(), []).append(v)
        choices = []
        used_b = set()
        for key, v in vars_a.items():
            match = vars_b.get(key)
            if match is None and len(long_names_b.get(v.long_name.lower(), [])) == 1:
                match = long_names_b[v.long_name.lower()][0]
            if match is not None:
                used_b.add(match.key)
            choices.append(VariableChoice(v.label(), v.long_name, key, None if match is None else match.key,
                                          v.display_units))
        for key, v in vars_b.items():
            if key not in used_b:
                choices.append(VariableChoice(v.label(), v.long_name, None, key, v.display_units))
        self.variables = sorted(choices, key=lambda c: c.label.lower())
        if self.SelectedVariable not in self.variables:
            self.SelectedVariable = None

    # ------------------------------------------------------------------ selection
    def getVariablesAsList(self, bOnlyComparable: bool):
        """The VariableChoice objects to offer, optionally only those in both series."""
        if bOnlyComparable:
            return [c for c in self.variables if c.state == STATE_COMPARABLE]
        return list(self.variables)

    def select_variable(self, choice):
        self.SelectedVariable = choice

    @property
    def SelectedVariableState(self):
        return '' if self.SelectedVariable is None else self.SelectedVariable.state

    @property
    def SelectedVariableUnit(self):
        return '' if self.SelectedVariable is None else self.SelectedVariable.units

    def reset(self):
        self.SelectedHeight = 0.0
        self.SelectedVariable = None
        self.SelectedSubArea = None


# init global dataseries handler
dataseries = dataseries_handler()
