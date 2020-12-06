# MIT License

# Copyright (c) 2018-2020 Dr. Jan-Philip Gehrcke

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import logging
import os
import re
import pickle
from abc import ABC, abstractmethod

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from .cfg import CFG, TODAY, FIGURE_FILE_PATHS


import cia.analysis as analysis

log = logging.getLogger(__name__)


_GLOBAL_X_LIMIT = None

# _AX_OBJS = []


# def show_ax_objs_info():
#     for i, ax_serialized in enumerate(_AX_OBJS, 1):
#         log.info("ax %s size bytes: %s", i, len(ax_serialized))


# def subplots_from_axs_objs():

#     n_rows = len(_AX_OBJS)
#     new_fig = plt.figure()
#     new_axs = new_fig.subplots(n_rows, 1, sharex=True)

#     for old_ax_serialized, new_axs in zip(_AX_OBJS, new_axs):
#         old_ax = pickle.loads(old_ax_serialized)
#         move_axes(old_ax, new_fig, new_axs)

#     # Align the subplots a little nicer, make more use of space. `hspace`: The
#     # amount of height reserved for space between subplots, expressed as a
#     # fraction of the average axis height
#     # plt.subplots_adjust(hspace=0.05, left=0.05, right=0.97, bottom=0.1, top=0.95)
#     plt.show()


# def new_figure_shunt(**kwargs):
#     ...


# def move_axes(old_ax, new_fig, new_ax_placeholder):

#     # get a reference to the old figure context so we can release it
#     old_fig = old_ax.figure

#     # remove the Axes from it's original Figure context
#     old_ax.remove()

#     # set the pointer from the Axes to the new figure
#     old_ax.figure = new_fig

#     # add the Axes to the registry of axes for the figure
#     # new_fig.axes.append(old_ax)
#     # twice, I don't know why...
#     new_fig.add_axes(old_ax)

#     old_ax.add_artist(new_fig)

#     # then copy the relevant data from the dummy to the ax
#     old_ax.set_position(new_ax_placeholder.get_position())
#     new_ax_placeholder.remove()

#     # close the figure the original axis was bound to
#     plt.close(old_fig)


def set_x_limit_for_all_plots(lower, upper):
    global _GLOBAL_X_LIMIT

    log.info("set common x limits for plots: %s, %s", lower, upper)
    _GLOBAL_X_LIMIT = (lower, upper)


def get_axes_in_new_fig():
    plt.figure()
    # Add an axes to the current figure and make it the current axes.
    ax = plt.axes()
    return ax


class Plot(ABC):

    _savefig_title = "override"

    def _savefig_mpl(self, fig, title):
        """
        Expected to return just the base name (not the complete path).

        `fig`: explicitly pass in figure object. Can obtain with `gcf()`.
        """
        # Lowercase, replace special chars with whitespace, join on whitespace.
        cleantitle = "-".join(re.sub("[^a-z0-9]+", " ", title.lower()).split())

        fname = TODAY + "_" + cleantitle

        fpath_figure = os.path.join(CFG().args.output_directory, fname + ".png")
        log.info("Writing PNG figure to %s", fpath_figure)
        plt.savefig(fpath_figure, dpi=150)
        return os.path.basename(fpath_figure)

    def plot_mpl_singlefig(self):
        log.info("singlefig plot: %s", self.__class__.__name__)
        fig = plt.figure()

        self._plot_mpl_core()

        plt.tight_layout(rect=(0, 0, 1, 0.95))
        # fig.close()
        figure_filepath = self._savefig_mpl(fig, self._savefig_title)
        return fig, figure_filepath

    @abstractmethod
    def _plot_mpl_core(self):
        raise NotImplementedError()


class PlotStability(Plot):
    def __init__(self, rolling_window_stability, window_width_days, context_descr):
        self.wwd = window_width_days
        self.series = rolling_window_stability
        self.context_descr = context_descr
        self._savefig_title = f"stability {context_descr}"

    def plot_mpl_subplot(self, ax):
        plt.sca(ax)
        self._plot_mpl_core()
        return ax

    def _plot_mpl_core(self):
        log.info("window width (days): %s", self.wwd)
        legendlist = []

        ax = self.series.plot(
            linestyle="solid",  # dot",
            # linestyle='None',
            # marker=".",
            markersize=0.8,
            markeredgecolor="gray",
        )

        legendlist.append(f"rolling window mean ({self.wwd} days)")

        ylabel = "build stability (max: 1)"

        # This is the build start time, but that has negligible impact on the
        # visualization.
        ax.set_xlabel("build time", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.legend(legendlist, numpoints=4, fontsize=8, loc="upper left")
        # text coords: x, y
        ax.text(
            0.01,
            0.04,
            self.context_descr,
            fontsize=8,
            transform=ax.transAxes,
            color="#666666",
        )
        ax.set_ylim(0, 1.15)


class PlotBuildrate(Plot):
    def __init__(self, builds_map, window_width_days, context_descr):
        self.builds_map = builds_map
        self.wwd = window_width_days
        self.context_descr = context_descr
        self._savefig_title = f"build rate {context_descr}"

    def plot_mpl_subplot(self, ax):
        plt.sca(ax)
        self._plot_mpl_core()
        return ax

    def _plot_mpl_core(self):
        ax = plt.gca()
        legendlist = []

        for descr, df in self.builds_map.items():
            log.info("analyze build rate: %s", descr)
            # Analysis and plots for entire pipeline, for passed builds.
            # follow https://github.com/jgehrcke/bouncer-log-analysis/blob/master/bouncer-log-analysis.py#L514
            # use rw of fixed (time) width (expose via cli arg) and set min number of
            # samples (expose via cli arg).
            legendlist.append(f"{descr}, rolling window mean ({self.wwd} days)")

            rolling_build_rate = analysis.calc_rolling_event_rate(
                df.index.to_series(), window_width_seconds=86400 * self.wwd
            )

            log.info("Plot build rate: window width (days): %s", self.wwd)

            # Plot into current axis
            rolling_build_rate.plot(
                linestyle="solid",  # dot",
                # linestyle='None',
                # marker=".",
                markersize=0.8,
                markeredgecolor="gray",
            )

        ylabel = "build rate [1/d]"
        # This is the build start time, but that has negligible impact on the
        # visualization.
        ax.set_xlabel("build time", fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)

        if _GLOBAL_X_LIMIT:
            log.info("plot: set global xlim: %s", _GLOBAL_X_LIMIT)
            ax.set_xlim(_GLOBAL_X_LIMIT)

        ax.legend(legendlist, numpoints=4, fontsize=8)
        # text coords: x, y
        ax.text(
            0.01,
            0.04,
            self.context_descr,
            fontsize=8,
            transform=ax.transAxes,
            color="#666666",
        )


class PlotDuration(Plot):
    def __init__(
        self,
        df,
        metricname,
        context_descr,
        show_mean=True,
        show_median=True,
        show_raw=True,
        descr_suffix="",
        ylabel="duration (seconds)",
        xlabel="build start time",
        title="",
        rollingwindow_w_days=21,
        figid=None,
        convert_to_hours=False,
        yticks=None,
        ylog=False,
    ):
        self.df = df
        self.metricname = metricname
        self.context_descr = context_descr
        self.show_mean = show_mean
        self.show_median = show_median
        self.show_raw = show_raw
        self.descr_suffix = descr_suffix
        self.ylabel = ylabel
        self.xlabel = xlabel
        self.title = title
        self.wwd = rollingwindow_w_days
        self.figid = figid
        self.convert_to_hours = convert_to_hours
        self.yticks = yticks
        self.ylog = ylog
        self._linlog = "logscale" if self.ylog else "linscale"
        self._savefig_title = (
            f"{context_descr} {title} {metricname} {self._linlog} {descr_suffix}"
        )

    def plot_mpl_singlefig(self):
        log.info("plot_mpl_singlefig: for build duration")
        fig = plt.figure()

        self._plot_mpl_core()
        if self.ylog:
            self._mutate_cur_mpl_ax_to_logscale()

        plt.tight_layout(rect=(0, 0, 1, 0.95))
        figure_filepath = self._savefig_mpl(fig, self._savefig_title)
        return fig, figure_filepath

    def plot_mpl_linscale_subplot(self, ax):
        plt.sca(ax)
        self._plot_mpl_core()
        return ax

    def _plot_mpl_core(self):

        width_string = f"{self.wwd}d"

        series_to_plot = self.df[self.metricname].copy()

        # Convert from unit [seconds] to [hours].
        if self.convert_to_hours:
            series_to_plot = series_to_plot / 3600.0

        rollingwindow = series_to_plot.rolling(width_string)
        mean = rollingwindow.mean()
        median = rollingwindow.median()

        # offset_seconds = - int(wwd * 24 * 60 * 60 / 2.0) + 1
        # median = median.shift(offset_seconds)

        legendlist = []

        ax = None

        if self.show_median:
            ax = median.plot(
                linestyle="solid",
                dash_capstyle="round",
                color="black",
                linewidth=1.3,
                zorder=10,
            )
            legendlist.append(f"rolling window median ({self.wwd} days)")

        if self.show_raw:
            ax = series_to_plot.plot(
                # linestyle='dashdot',
                linestyle="None",
                color="gray",
                marker=".",
                markersize=4,
                markeredgecolor="gray",
                ax=ax,
                zorder=1,  # Show in the back.
                clip_on=True,
            )
            legendlist.append("individual builds")

        if self.show_mean:
            ax = mean.plot(
                linestyle="solid",
                color="#e05f4e",
                linewidth=1.3,
                ax=ax,
                zorder=5,
            )
            legendlist.append(f"rolling window mean ({self.wwd} days)")

        if _GLOBAL_X_LIMIT is not None:
            log.info("duration plot: set global xlim: %s", _GLOBAL_X_LIMIT)
            ax.set_xlim(_GLOBAL_X_LIMIT)

        if self.xlabel is None:
            ax.set_xlabel("build start time", fontsize=10)

        ax.set_ylabel(self.ylabel, fontsize=10)

        # text coords: x, y
        ax.text(
            0.01,
            0.04,
            self.context_descr,
            fontsize=8,
            transform=ax.transAxes,
            color="#666666",
        )
        # plt.xticks(fontsize=14,

        # set_title('Time-to-merge for PRs in both DC/OS repositories')
        # subtitle = 'Freq spec from narrow rolling request rate -- ' + \
        #    matcher.subtitle
        # set_subtitle('Raw data')
        # plt.tight_layout(rect=(0, 0, 1, 0.95))

        ax.legend(legendlist, numpoints=4, fontsize=8)
        return median, ax

    def _mutate_cur_mpl_ax_to_logscale(self):
        log.info("mutate current ax to logscale")

        median, ax = self._plot_mpl_core()
        plt.yscale("log")

        # Set ytick labels using 0.01, 0.1, 1, 10, 100, instead of 10^0 etc.
        # Creds:
        #  https://stackoverflow.com/q/21920233/145400
        #  https://stackoverflow.com/q/14530113/145400
        if self.yticks is not None:
            # ax.set_yticks([0.001, 0.01, 0.1, 0.5, 1, 3, 10])
            ax.set_yticks(self.yticks)
        ax.yaxis.set_major_formatter(
            ticker.FuncFormatter(lambda y, _: "{:g}".format(y))
        )

        # https://github.com/pandas-dev/pandas/issues/2010
        ax.set_xlim(ax.get_xlim()[0] - 1, ax.get_xlim()[1] + 1)


def matplotlib_config():
    matplotlib.rcParams["xtick.labelsize"] = 6
    matplotlib.rcParams["ytick.labelsize"] = 6
    matplotlib.rcParams["axes.labelsize"] = 10
    matplotlib.rcParams["figure.figsize"] = [10.0, 4.2]
    matplotlib.rcParams["figure.dpi"] = 100
    matplotlib.rcParams["savefig.dpi"] = 190
    # mpl.rcParams['font.size'] = 12

    original_color_cycle = matplotlib.rcParams["axes.prop_cycle"]

    plt.style.use("ggplot")

    # ggplot's color cylcle seems to be too short for having 8 line plots on the
    # same Axes.
    matplotlib.rcParams["axes.prop_cycle"] = original_color_cycle
