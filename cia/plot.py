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

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from .cfg import CFG, TODAY, FIGURE_FILE_PATHS


log = logging.getLogger(__name__)


def plot_duration(
    df,
    metricname,
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
):

    median, ax = _plot_duration_core(
        df=df,
        metricname=metricname,
        ylabel=ylabel,
        xlabel=xlabel,
        rollingwindow_w_days=rollingwindow_w_days,
        show_mean=show_mean,
        show_median=show_median,
        show_raw=show_raw,
        convert_to_hours=convert_to_hours,
    )
    plt.tight_layout()
    figure_filepath_latency_raw_linscale = savefig(
        f"{CFG().args.org} {CFG().args.pipeline} {title} {metricname} linear {descr_suffix}"
    )

    plt.figure()

    median, ax = _plot_duration_core(
        df=df,
        metricname=metricname,
        ylabel=ylabel,
        xlabel=xlabel,
        rollingwindow_w_days=rollingwindow_w_days,
        show_mean=show_mean,
        show_median=show_median,
        show_raw=show_raw,
        convert_to_hours=convert_to_hours,
    )

    plt.yscale("log")

    # Set ytick labels using 0.01, 0.1, 1, 10, 100, instead of 10^0 etc.
    # Creds:
    #  https://stackoverflow.com/q/21920233/145400
    #  https://stackoverflow.com/q/14530113/145400
    if yticks is not None:
        # ax.set_yticks([0.001, 0.01, 0.1, 0.5, 1, 3, 10])
        ax.set_yticks(yticks)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: "{:g}".format(y)))

    # https://github.com/pandas-dev/pandas/issues/2010
    ax.set_xlim(ax.get_xlim()[0] - 1, ax.get_xlim()[1] + 1)

    # The tight_layout magic does not get rid of the outer margin. Fortunately,
    # numbers smaller than 0 and larger than 1 for left, bottom, right, top are
    # allowed.
    # plt.tight_layout(rect=(-0.01, -0.05, 1.0, 1.0))
    plt.tight_layout()
    # plt.subplots_adjust(left=0, bottom=0, right=1, top=1, wspace=0, hspace=0)
    figure_filepath_latency_raw_logscale = savefig(
        f"{CFG().args.org} {CFG().args.pipeline} {title} {metricname} logscale {descr_suffix}"
    )

    # Create new mpl figure for next call to `plot_duration()`
    plt.figure()

    # Keep record of these figure files in a global state dictionary.
    if figid is not None:
        FIGURE_FILE_PATHS[figid + "_logscale"] = figure_filepath_latency_raw_logscale
        FIGURE_FILE_PATHS[figid + "_linscale"] = figure_filepath_latency_raw_linscale

    return (
        median,
        figure_filepath_latency_raw_linscale,
        figure_filepath_latency_raw_logscale,
    )


def _plot_duration_core(
    df,
    metricname,
    ylabel,
    xlabel,
    rollingwindow_w_days,
    convert_to_hours=False,
    show_mean=True,
    show_median=True,
    show_raw=True,
):

    width_string = f"{rollingwindow_w_days}d"

    series_to_plot = df[metricname].copy()

    # Convert from unit [seconds] to [hours].
    if convert_to_hours:
        series_to_plot = series_to_plot / 3600.0

    rollingwindow = series_to_plot.rolling(width_string)
    mean = rollingwindow.mean()
    median = rollingwindow.median()

    # offset_seconds = - int(rollingwindow_w_days * 24 * 60 * 60 / 2.0) + 1
    # median = median.shift(offset_seconds)

    legendlist = []

    ax = None

    if show_median:
        ax = median.plot(
            linestyle="solid",
            dash_capstyle="round",
            color="black",
            linewidth=1.3,
            zorder=10,
        )
        legendlist.append(f"rolling window median ({rollingwindow_w_days} days)")

    if show_raw:
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

    if show_mean:
        ax = mean.plot(
            linestyle="solid",
            color="#e05f4e",
            linewidth=1.3,
            ax=ax,
            zorder=5,
        )
        legendlist.append(f"rolling window mean ({rollingwindow_w_days} days)")

    if xlabel is None:
        plt.xlabel("build start time", fontsize=10)

    plt.ylabel(ylabel, fontsize=10)

    # plt.xticks(fontsize=14,

    # set_title('Time-to-merge for PRs in both DC/OS repositories')
    # subtitle = 'Freq spec from narrow rolling request rate -- ' + \
    #    matcher.subtitle
    # set_subtitle('Raw data')
    # plt.tight_layout(rect=(0, 0, 1, 0.95))

    ax.legend(legendlist, numpoints=4, fontsize=8)
    return median, ax


def savefig(title):
    """
    Expected to return just the base name (not the complete path).
    """
    # Lowercase, replace special chars with whitespace, join on whitespace.
    cleantitle = "-".join(re.sub("[^a-z0-9]+", " ", title.lower()).split())

    fname = TODAY + "_" + cleantitle

    fpath_figure = os.path.join(CFG().args.output_directory, fname + ".png")
    log.info("Writing PNG figure to %s", fpath_figure)
    plt.savefig(fpath_figure, dpi=150)
    return os.path.basename(fpath_figure)


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
