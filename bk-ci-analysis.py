#!/usr/bin/env python
# Copyright 2018-2019 Jan-Philip Gehrcke
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

"""
Generates a Buildkite CI analysis report.
"""

import argparse
import os
import json
import logging
import pickle
import sys
import re
import shutil
import textwrap
from datetime import datetime
from collections import Counter, defaultdict
from io import StringIO

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import pytablewriter

from pybuildkite.buildkite import Buildkite, BuildState

NOW = datetime.utcnow()
TODAY = NOW.strftime("%Y-%m-%d")
OUTDIR = None
BK_CLIENT = Buildkite()
BK_CLIENT.set_access_token(os.environ["BUILDKITE_API_TOKEN"])
FIGURE_FILE_PATHS = {}

CLIARGS = None


log = logging.getLogger()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s: %(message)s",
    datefmt="%y%m%d-%H:%M:%S",
)


def main():
    parse_args()

    builds = fetch_all_builds(CLIARGS.org, CLIARGS.pipeline, [BuildState.FINISHED])
    builds_passed = [b for b in builds if b["state"] == "passed"]
    log.info("builds PASSED: %s", len(builds_passed))

    log.info("identify the set of step keys observed across all passed builds")
    step_key_counter, jobs_by_key = identify_top_n_step_keys(builds_passed, 7)

    # Analysis and plots for entire pipeline.
    df_passed = construct_df(builds_passed)

    (
        _,
        figure_filepath_latency_raw_linscale,
        figure_filepath_latency_raw_logscale,
    ) = plot_duration(
        df_passed,
        metricname="duration_seconds",
        rollingwindow_w_days=10,
        ylabel="pipeline duration (hours)",
        xlabel="pipeline start time",
        title="pipeline",
        convert_to_hours=True,
    )

    # Generate a flat list containing all build jobs across all passed
    # pipelines.

    # Analysis and plots for top N build steps.
    for step_key, count in step_key_counter.most_common(4):
        # Analysis and plots for a specific job key
        log.info("generate dataframe from list of jobs: %s", step_key)
        df_job = construct_df_for_jobs(jobs_by_key[step_key])
        print(df_job)
        plot_duration(
            df_job,
            metricname="duration_seconds",
            rollingwindow_w_days=10,
            ylabel="job duration (hours)",
            xlabel=f"job start time ({step_key})",
            title=step_key,
            convert_to_hours=True,
        )
        sys.exit()


def parse_args():
    global CLIARGS
    global OUTDIR

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Performs Buildkite CI data analysis",
        epilog=textwrap.dedent(__doc__).strip(),
    )
    parser.add_argument("--output-directory", default=TODAY + "_report")
    # parser.add_argument("--resources-directory", default="resources")
    # parser.add_argument("--pandoc-command", default="pandoc")

    parser.add_argument("org", help="The org's slug (simplified lowercase name)")
    parser.add_argument(
        "pipeline", help="The pipeline's slug (simplified lowercase name)"
    )
    parser.add_argument(
        "--ignore-builds-shorter-than", type=int, help="Number in seconds"
    )

    parser.add_argument(
        "--ignore-builds-longer-than", type=int, help="Number in seconds"
    )

    args = parser.parse_args()

    log.info("command line args: %s", json.dumps(vars(args), indent=2))

    if os.path.exists(args.output_directory):
        if not os.path.isdir(args.output_directory):
            log.error(
                "The specified output directory path does not point to a directory: %s",
                args.output_directory,
            )
            sys.exit(1)

        log.info("Remove output directory: %s", args.output_directory)
        shutil.rmtree(args.output_directory)

    log.info("Create output directory: %s", args.output_directory)
    os.makedirs(args.output_directory)

    CLIARGS = args
    OUTDIR = args.output_directory


def identify_top_n_step_keys(builds, top_n):
    # Build up a dictionary while iterating of over all jobs. The keys in that
    # dict are the job keys. For each job key, construct a list of
    # corresponding jobs (no sorting order guarantees).
    jobs_by_key = defaultdict(list)

    step_keys = []
    for b in builds:
        for job in b["jobs"]:
            if not "step_key" in job:
                # for example:
                # {'id': 'e05fce02-c89b-4326-8181-e7b54333e202', 'type': 'waiter'}
                continue
            if job["step_key"] is None:
                # for example, the pipeline initiation step:
                #  "name": ":pipeline:",
                #  "step_key": null,
                continue
            jobs_by_key[job["step_key"]].append(job)
            step_keys.append(str(job["step_key"]))
    log.info("set of step keys across passed builds: %s", set(step_keys))

    log.info("build histogram: which step (key) was executed how often?")
    step_key_counter = Counter([k for k in step_keys])

    log.info("top %s executed build steps (by step key)", top_n)
    tabletext = get_mdtable(
        ["step key", "number of executions"],
        [[item, count] for item, count in step_key_counter.most_common(top_n)],
    )
    print("\n\n" + tabletext)

    return step_key_counter, jobs_by_key


def construct_df_for_jobs(jobs):
    log.info("rewrite timestamp strings into datetime objects")
    # Use `fromisoformat()`, introduced in stdlib in 3.7:
    #
    # >>> from datetime import datetime
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000")
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15)
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000Z".replace('Z', '+00:00'))
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15, tzinfo=datetime.timezone.utc)
    for j in jobs:
        for dtprop in ("created_at", "started_at", "scheduled_at", "finished_at"):
            j[dtprop] = datetime.fromisoformat(j[dtprop].replace("Z", "+00:00"))

    log.info("do not extract build numbers, these are jobs")
    # shortcut for now, can extract build number from build_url later
    build_numbers = [1 for j in jobs]

    log.info("build pandas dataframe for passed jobs")
    df_dict = {
        "started_at": [j["started_at"] for j in jobs],
        "build_number": build_numbers,
        "duration_seconds": [
            (j["finished_at"] - j["started_at"]).total_seconds() for j in jobs
        ],
    }

    df = pd.DataFrame(df_dict, index=[pd.Timestamp(j["started_at"]) for j in jobs])
    # Sort by time, from past to future.
    log.info("df: sort by time")
    df.sort_index(inplace=True)
    return df


def construct_df(builds, jobs=False, ignore_builds=None):

    log.info("rewrite timestamp strings into datetime objects")
    # Use `fromisoformat()`, introduced in stdlib in 3.7:
    #
    # >>> from datetime import datetime
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000")
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15)
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000Z".replace('Z', '+00:00'))
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15, tzinfo=datetime.timezone.utc)
    for b in builds:
        for dtprop in ("created_at", "started_at", "scheduled_at", "finished_at"):
            b[dtprop] = datetime.fromisoformat(b[dtprop].replace("Z", "+00:00"))

    build_numbers = [b["number"] for b in builds]
    log.info("build pandas dataframe for passed builds")
    df_dict = {
        "started_at": [b["started_at"] for b in builds],
        "build_number": build_numbers,
        "duration_seconds": [
            (b["finished_at"] - b["started_at"]).total_seconds() for b in builds
        ],
    }

    df = pd.DataFrame(df_dict, index=[pd.Timestamp(b["started_at"]) for b in builds])

    if CLIARGS.ignore_builds_shorter_than is not None:
        log.info(
            "drop builds shorter than %s seconds", CLIARGS.ignore_builds_shorter_than
        )
        # Filter bad builds that on the one hand are 'passed', but on the other
        # hand are obvious bad builds identifyable by a way too low duration.

        df_cleaned = df.drop(
            df[df.duration_seconds < CLIARGS.ignore_builds_shorter_than].index
        )
        log.info("dropped %s builds", len(df) - len(df_cleaned))
        df = df_cleaned

    if CLIARGS.ignore_builds_longer_than is not None:
        log.info(
            "drop builds longer than %s seconds", CLIARGS.ignore_builds_longer_than
        )
        # Filter bad builds that on the one hand are 'passed', but on the other
        # hand are obvious bad builds identifyable by a way too low duration.

        df_cleaned = df.drop(
            df[df.duration_seconds > CLIARGS.ignore_builds_longer_than].index
        )
        log.info("dropped %s builds", len(df) - len(df_cleaned))
        dropped = df[df.duration_seconds > CLIARGS.ignore_builds_longer_than]
        log.info("dropped:")
        print(dropped)
        df = df_cleaned

    # Sort by time, from past to future.
    log.info("df: sort by time")
    df.sort_index(inplace=True)
    return df


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
        f"{CLIARGS.org} {CLIARGS.pipeline} {title} {metricname} linear {descr_suffix}"
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
        f"{CLIARGS.org} {CLIARGS.pipeline} {title} {metricname} logscale {descr_suffix}"
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


def fetch_all_builds(orgslug, pipelineslug, states):

    cache_filepath = "builds.pickle"
    builds_cached = load_file_if_exists(cache_filepath)

    if builds_cached is not None:
        log.info("Loaded %s builds from disk", len(builds_cached))
        log.info("TODO: update (forward-fill)")
        return builds_cached

    # Get all running and scheduled builds for a particular pipeline
    builds = []

    builds_resp = BK_CLIENT.builds().list_all_for_pipeline(
        orgslug,
        pipelineslug,
        states=[BuildState.FINISHED],
        with_pagination=True,
    )
        builds_resp = BK_CLIENT.builds().list_all_for_pipeline(
            orgslug,
            pipelineslug,
            page=builds_resp.next_page,
            states=states,
            with_pagination=True,
        )

    # `builds_resp.body` is already deserialized, interestingly (not a body,
    # i.e. not str or bytes).
    builds_cur_page = builds_resp.body
    log.info(f"got {len(builds_cur_page)} builds")
    builds.extend(builds_cur_page)

    while builds_resp.next_page:
        log.info("getting next page")
        )
        builds_cur_page = builds_resp.body
        log.info("got %s builds", len(builds_cur_page))

        builds.extend(builds_cur_page)

    log.info("got data for %s finished builds", len(builds))
    persist_data(builds, cache_filepath)
    return builds


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
    Save figure file to `OUTDIR`.
    Expected to return just the base name (not the complete path).
    """
    # Lowercase, replace special chars with whitespace, join on whitespace.
    cleantitle = "-".join(re.sub("[^a-z0-9]+", " ", title.lower()).split())

    fname = TODAY + "_" + cleantitle

    fpath_figure = os.path.join(OUTDIR, fname + ".png")
    log.info("Writing PNG figure to %s", fpath_figure)
    plt.savefig(fpath_figure, dpi=150)
    return os.path.basename(fpath_figure)


def get_mdtable(header_list, value_matrix):
    """
    Generate table text in Markdown.
    """
    if not value_matrix:
        return ""

    tw = pytablewriter.MarkdownTableWriter()
    tw.stream = StringIO()
    tw.header_list = header_list
    tw.value_matrix = value_matrix
    # Potentially use
    # writer.align_list = [Align.LEFT, Align.RIGHT, ...]
    # see https://github.com/thombashi/pytablewriter/issues/2
    tw.margin = 1
    tw.write_table()
    # print(textwrap.indent(tw.stream.getvalue(), '    '))
    return tw.stream.getvalue()


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


def load_file_if_exists(filepath):
    # Load from disk if already fetched today, otherwise return `None`.
    if os.path.exists(filepath):
        log.info("loading data from file: %s", filepath)
        with open(filepath, "rb") as f:
            data = f.read()
        log.info("read %.2f MiB", len(data) / 1024.0 / 1024.0)
        return pickle.loads(data)
    return None


def persist_data(obj, filepath):
    data = pickle.dumps(obj)
    log.info("persist %s byte(s) to file %s", len(data), filepath)
    with open(filepath, "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
