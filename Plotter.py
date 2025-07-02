import numpy as np
import matplotlib.pyplot as plt
from .Dataseries_handler import *
from .Const_defines import *


class Plotter:
    def __init__(self, method: int):
        self.method = method
        self.last_date_A = ''
        self.last_date_B = ''
        self.last_date_Delta = ''
        self.value_list_A = []
        self.value_list_B = []
        self.value_list_A_delta = []
        self.value_list_B_delta = []
        self.value_list_delta = []
        self.date_list_A = []
        self.date_list_B = []
        self.date_list_delta = []
        self.timestep_list_A = []
        self.timestep_list_B = []
        self.timestep_list_delta = []
        self.datetime_list_A = []
        self.datetime_list_B = []
        self.datetime_list_delta = []
        self.bar_colors = []

    def clear_lists(self):
        self.value_list_A.clear()
        self.value_list_B.clear()
        self.value_list_A_delta.clear()
        self.value_list_B_delta.clear()
        self.value_list_delta.clear()
        self.date_list_A.clear()
        self.date_list_B.clear()
        self.date_list_delta.clear()
        self.timestep_list_A.clear()
        self.timestep_list_B.clear()
        self.timestep_list_delta.clear()
        self.datetime_list_A.clear()
        self.datetime_list_B.clear()
        self.datetime_list_delta.clear()
        self.bar_colors.clear()

    def add_data_point(self, dataA, dataB, merged):
        if not (dataA is None) and merged.checkedA:
            # filter no data values
            dataA = dataA[dataA != C_NODATA_VALUE]
            self.timestep_list_A.append(merged.timestepA.time)
            self.datetime_list_A.append(merged.timestepA.date + ' ' + merged.timestepA.time)
            if len(self.date_list_A) == 0:
                self.date_list_A.append(merged.timestepA.date)
                self.last_date_A = merged.timestepA.date
            elif self.last_date_A != merged.timestepA.date:
                self.date_list_A.append(merged.timestepA.date)
                self.last_date_A = merged.timestepA.date
            else:
                self.date_list_A.append(' ')
            self.value_list_A.append(self.calculate_value(dataA))

        if not (dataB is None) and merged.checkedB:
            # filter no data values
            dataB = dataB[dataB != C_NODATA_VALUE]
            self.timestep_list_B.append(merged.timestepB.time)
            self.datetime_list_B.append(merged.timestepB.date + ' ' + merged.timestepB.time)
            if len(self.date_list_B) == 0:
                self.date_list_B.append(merged.timestepB.date)
                self.last_date_B = merged.timestepB.date
            elif self.last_date_B != merged.timestepB.date:
                self.date_list_B.append(merged.timestepB.date)
                self.last_date_B = merged.timestepB.date
            else:
                self.date_list_B.append(' ')
            self.value_list_B.append(self.calculate_value(dataB))

        if not (dataA is None) and not (dataB is None) and merged.delta_checked:
            # filter no data values
            dataA = dataA[dataA != C_NODATA_VALUE]
            self.value_list_A_delta.append(self.calculate_value(dataA))

            # filter no data values
            dataB = dataB[dataB != C_NODATA_VALUE]
            self.value_list_B_delta.append(self.calculate_value(dataB))

            # calculate delta value (A-B)
            delta = self.value_list_A_delta[-1] - self.value_list_B_delta[-1]
            self.value_list_delta.append(delta)
            if delta < 0:
                # the value from Series B > value from Series A
                self.bar_colors.append(C_SERIES_B_COLOR)
            else:
                # the value from Series A > value from Series B
                self.bar_colors.append(C_SERIES_A_COLOR)

            # add time and date for this iteration
            self.timestep_list_delta.append(merged.timestepA.time)
            self.datetime_list_delta.append(merged.timestepA.date + ' ' + merged.timestepA.time)
            if len(self.date_list_delta) == 0:
                self.date_list_delta.append(merged.timestepA.date)
                self.last_date_Delta = merged.timestepA.date
            elif self.last_date_Delta != merged.timestepA.date:
                self.date_list_delta.append(merged.timestepA.date)
                self.last_date_Delta = merged.timestepA.date
            else:
                self.date_list_delta.append(' ')

    def create_plot_A(self):
        if len(self.value_list_A) != 0:
            self.defineAndShowFigure(series='A', date_list=self.date_list_A, timestep_list=self.timestep_list_A,
                                     datetime_list=self.datetime_list_A, value_list=self.value_list_A)

    def create_plot_B(self):
        if len(self.value_list_B) != 0:
            self.defineAndShowFigure(series='B', date_list=self.date_list_B, timestep_list=self.timestep_list_B,
                                     datetime_list=self.datetime_list_B, value_list=self.value_list_B)

    def create_plot_delta(self):
        if (len(self.value_list_A_delta) != 0) and (len(self.value_list_B_delta) != 0):
            # define general plot-settings
            figure = plt.figure(facecolor="lightsteelblue")
            subplot = figure.add_subplot(211)  # 211 -> 2 rows, 1 column, 1st figure
            subplot.plot(self.datetime_list_delta, self.value_list_A_delta, color=C_SERIES_A_COLOR, label='Series A')
            subplot.plot(self.datetime_list_delta, self.value_list_B_delta, color=C_SERIES_B_COLOR, label='Series B')
            subplot.fill_between(self.datetime_list_delta, self.value_list_A_delta, self.value_list_B_delta, alpha=0.2)
            subplot.set_xticklabels(self.timestep_list_delta)
            # add a legend
            subplot.legend(loc="upper right")

            # now we define a secondary axis, where the date of the corresponding day is shown
            secondaryAxis = subplot.secondary_xaxis('top')
            secondaryAxis.set_xticklabels(self.date_list_delta)
            secondaryAxis.set_xticks(np.arange(0, len(self.date_list_delta) - 1, step=1))
            if C_DRAW_NEW_DAY_LINE:
                for i in range(len(self.date_list_delta)):
                    if self.date_list_delta[i] != ' ':
                        subplot.axvline(x=i, linewidth=1, color=C_NEW_DAY_COLOR)

            # set the title and axis-labels of the plot.
            title = ''
            if self.method == C_METHOD_MEAN:
                title = f'Mean {dataseries.SelectedVariable} in {dataseries.HeightRange} height'
            elif self.method == C_METHOD_MEDIAN:
                title = f'Median {dataseries.SelectedVariable} in {dataseries.HeightRange} height'

            subplot.set(xlabel='Timesteps [h]', ylabel=dataseries.SelectedVariableUnit, title=title)

            # add a grid to our plot
            subplot.grid()
            # rotate labels on both x-axis by 30 degrees, so they don't overlap so easily
            plt.setp(subplot.get_xticklabels(), rotation=30, horizontalalignment='right')
            plt.setp(secondaryAxis.get_xticklabels(), rotation=30, horizontalalignment='left')

            subplot_2 = figure.add_subplot(212)  # 212 -> 2 rows, 1 column, 2nd figure
            # the second plot is a bar plot. Set zorder = 3 to display the bars in the foreground
            subplot_2.bar(self.datetime_list_delta, self.value_list_delta, zorder=3, color=self.bar_colors)
            subplot_2.set_xticklabels(self.timestep_list_delta)
            # set title for axis and figure
            title_2 = f'Delta for {title} (Series A - Series B)'
            subplot_2.set(xlabel='Timesteps [h]', ylabel=f'Delta ({dataseries.SelectedVariableUnit})', title=title_2)
            subplot_2.grid(zorder=0)

            # now we define a secondary axis, where the date of the corresponding day is shown
            secondaryAxis_2 = subplot_2.secondary_xaxis('top')
            secondaryAxis_2.set_xticklabels(self.date_list_delta)
            secondaryAxis_2.set_xticks(np.arange(0, len(self.date_list_delta) - 1, step=1))
            if C_DRAW_NEW_DAY_LINE:
                for i in range(len(self.date_list_delta)):
                    if self.date_list_delta[i] != ' ':
                        subplot_2.axvline(x=i, linewidth=1, color=C_NEW_DAY_COLOR)

            # rotate labels on both x-axis by 30 degrees, so they don't overlap so easily
            plt.setp(subplot_2.get_xticklabels(), rotation=30, horizontalalignment='right')
            plt.setp(secondaryAxis_2.get_xticklabels(), rotation=30, horizontalalignment='left')

            if C_PRINT_SOURCE:
                figure.text(0.01, 0.01, s=f'Source A: {dataseries.FolderA}, Source B: {dataseries.FolderB}',
                            fontsize=C_PRINT_SOURCE_FONTSIZE,
                            ha='left',
                            va='bottom')

            figure.set_size_inches(10, 6)
            figure.tight_layout()
            plt.show()

    def defineAndShowFigure(self, series: str, date_list: [], timestep_list: [], datetime_list: [], value_list: []):
        if series == 'A':
            series_lbl = 'Series A'
        else:
            series_lbl = 'Series B'

        # define general plot-settings
        figure = plt.figure(facecolor="lightsteelblue")
        subplot = figure.add_subplot()
        subplot.plot(datetime_list, value_list, color='blue', label=series_lbl)
        subplot.set_xticklabels(timestep_list)
        # now we define a secondary axis, where the date of the corresponding day is shown
        secondaryAxis = subplot.secondary_xaxis('top')
        secondaryAxis.set_xticklabels(date_list)
        secondaryAxis.set_xticks(np.arange(0, len(date_list) - 1, step=1))
        if C_DRAW_NEW_DAY_LINE:
            for i in range(len(date_list)):
                if date_list[i] != ' ':
                    subplot.axvline(x=i, linewidth=1, color=C_NEW_DAY_COLOR)

        # set the title and axis-labels of the plot.
        title = ''
        if self.method == C_METHOD_MEAN:
            title = f'Mean {dataseries.SelectedVariable} in {dataseries.HeightRange} height ({series_lbl})'
        elif self.method == C_METHOD_MEDIAN:
            title = f'Median {dataseries.SelectedVariable} in {dataseries.HeightRange} height ({series_lbl})'

        subplot.set(xlabel='Timesteps [h]', ylabel=dataseries.SelectedVariableUnit, title=title)

        # add a grid to our plot
        subplot.grid()
        # rotate labels on both x-axis by 30 degrees, so they don't overlap so easily
        plt.setp(subplot.get_xticklabels(), rotation=30, horizontalalignment='right')
        plt.setp(secondaryAxis.get_xticklabels(), rotation=30, horizontalalignment='left')
        if C_PRINT_SOURCE:
            if series == 'A':
                figure.text(0.01, 0.01, s=f'Source: {dataseries.FolderA}', fontsize=C_PRINT_SOURCE_FONTSIZE, ha='left',
                            va='bottom')
            else:
                figure.text(0.01, 0.01, s=f'Source: {dataseries.FolderB}', fontsize=C_PRINT_SOURCE_FONTSIZE, ha='left',
                            va='bottom')

        figure.set_size_inches(10, 6)
        figure.tight_layout()
        plt.show()

    def calculate_value(self, arr):
        if self.method == C_METHOD_MEAN:
            return np.nanmean(arr)
        elif self.method == C_METHOD_MEDIAN:
            return np.nanmedian(arr)
        else:
            return 0.0
