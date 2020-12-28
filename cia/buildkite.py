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

"""
Buildkite-specific dingeling.
"""

import os
import logging
import sys
import time
import json
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
from pybuildkite.buildkite import Buildkite, BuildState

import matplotlib.pyplot as plt

import cia.plot as plot
import cia.utils as utils
import cia.filter as bfilter
import cia.analysis as analysis
from cia.cfg import CFG, TODAY


log = logging.getLogger(__name__)


BK_CLIENT = Buildkite()
BK_CLIENT.set_access_token(os.environ["BUILDKITE_API_TOKEN"])


_PLOTS_FOR_SUBPLOTS = []


def main():

    builds_all = rewrite_build_objects(
        load_all_builds(CFG().args.org, CFG().args.pipeline, [BuildState.FINISHED])
    )

    # Store this under "all", although these are technically already filtered
    builds_all = bfilter.filter_builds_based_on_build_time(builds_all)

    set_common_x_limit_for_plotting(builds_all)

    plot.matplotlib_config()

    builds_passed = bfilter.filter_builds_passed(
        bfilter.filter_builds_based_on_duration(builds_all)
    )

    p = plot.PlotBuildrate(
        builds_map={
            "all builds": construct_df_for_builds(builds_all),
            "passed builds": construct_df_for_builds(builds_passed),
        },
        window_width_days=4,
        context_descr=f"{CFG().args.org}/{CFG().args.pipeline}",
    )
    p.plot_mpl_singlefig()
    _PLOTS_FOR_SUBPLOTS.append(p)

    analyze_build_stability(builds_all, builds_passed, window_width_days=4)

    analyze_passed_builds(builds_all)

    create_summary_fig_with_subplots()

    # plot.show_ax_objs_info()
    # plot.subplots_from_axs_objs()
    # plt.show()
    sys.exit(0)


def create_summary_fig_with_subplots():

    n_rows = len(_PLOTS_FOR_SUBPLOTS)
    fig = plt.figure()

    # w, h
    fig.set_size_inches(10, 1.5 * n_rows)

    log.info("create figure with subplots for these:")
    for p in _PLOTS_FOR_SUBPLOTS:
        print(p)

    # hard-code: 1 column
    new_axs = fig.subplots(n_rows, 1, sharex=True)
    for p, ax in zip(_PLOTS_FOR_SUBPLOTS, new_axs):
        log.debug("re-plot %s to ax %s", p, id(ax))
        # Set currently active axis to axis object handed over to this
        # function. That makes df.plot() add the data to said axis.
        # Also pass `ax` explicitly.
        plt.sca(ax)
        p.plot_mpl_subplot(ax)

    # Align the subplots a little nicer, make more use of space. `hspace`: The
    # amount of height reserved for space between subplots, expressed as a
    # fraction of the average axis height
    plt.xlabel("build date", fontsize=10)

    # Add title and subtitle to figure.
    fig.text(
        0.5,
        0.98,
        f"{CFG().args.org}/{CFG().args.pipeline} pipeline summary ({TODAY})",
        verticalalignment="center",
        horizontalalignment="center",
        fontsize=11,
        color="#666666",
    )

    # fig.text(
    #     0.5,
    #     0.96,
    #     "subtitle lasudkojk",
    #     verticalalignment="center",
    #     horizontalalignment="center",
    #     fontsize=10,
    #     color="gray",
    # )

    plt.subplots_adjust(hspace=0.08, left=0.05, right=0.97, bottom=0.1, top=0.96)
    plot.savefig(plt.gcf(), "multiplot summary")
    # plt.show()


def set_common_x_limit_for_plotting(builds_all):
    # Get earliest and latest builds (their "time")
    # Rely on result df of this func to be sorted by time: past -> future
    df = construct_df_for_builds(builds_all)
    mintime_across_builds = df.index[0]
    maxtime_across_builds = df.index[-1]
    diff = maxtime_across_builds - mintime_across_builds

    plot.set_x_limit_for_all_plots(
        lower=mintime_across_builds - 0.03 * diff,
        upper=maxtime_across_builds + 0.03 * diff,
    )


def analyze_build_stability(builds_all, builds_passed, window_width_days):
    log.info(
        "\n\nperform build stability analysis (from all builds, passed builds) -- window_width_days: %s",
        window_width_days,
    )

    df_all = construct_df_for_builds(builds_all)
    df_passed = construct_df_for_builds(builds_passed)

    df_passed_timestamp_series = df_passed.index.to_series()
    df_all_timestamp_series = df_all.index.to_series()

    log.info(
        "timestamp of last passed build: %s", df_passed_timestamp_series.index.max()
    )
    log.info("timestamp of last build: %s", df_all_timestamp_series.index.max())

    rolling_build_rate_all = analysis.calc_rolling_event_rate(
        df_all_timestamp_series, window_width_seconds=86400 * window_width_days
    )

    # Passed builds: fill gaps with 0 (upsample), so that the following
    # passed/all division shows stability '0' when build_rate_all is non-NaN.
    # Also: the last (newest) data point in passed builds might be older than
    # the newest data point in all builds (when the _actual last build_
    # failed!). In that case, forward-fill (extend) the "passed build" time
    # series into the future up to the time of the last passed build. (fill
    # with 0 into the future if `rolling_build_rate_all` has newer data points
    # than the newest one in `df_passed`).
    log.info("calc_rolling_event_rate() for passed builds")
    log.info("")
    rolling_build_rate_passed = analysis.calc_rolling_event_rate(
        df_passed_timestamp_series,
        window_width_seconds=86400 * window_width_days,
        upsample_with_zeros=True,
        upsample_with_zeros_until=df_passed_timestamp_series.index.max(),
    )

    rolling_window_stability = rolling_build_rate_passed / rolling_build_rate_all
    p = plot.PlotStability(
        rolling_window_stability=rolling_window_stability,
        window_width_days=window_width_days,
        context_descr=f"{CFG().args.org}/{CFG().args.pipeline}",
    )

    p.plot_mpl_singlefig()
    _PLOTS_FOR_SUBPLOTS.append(p)


def analyze_passed_builds(builds_all):
    log.info("analyze passed builds")

    builds = bfilter.filter_builds_passed(
        bfilter.filter_builds_based_on_duration(builds_all)
    )

    log.info("identify the set of step keys observed across builds")
    step_key_counter, jobs_by_key = identify_top_n_step_keys(builds, 7)

    # Analysis and plots for entire pipeline, for passed builds.
    df = construct_df_for_builds(builds)

    p = plot.PlotDuration(
        df=df,
        context_descr=f"{CFG().args.org}/{CFG().args.pipeline} (passed)",
        metricname="duration_seconds",
        rollingwindow_w_days=10,
        ylabel="pipeline duration (hours)",
        xlabel="pipeline start time",
        title="pipeline",
        convert_to_hours=True,
    )
    p.plot_mpl_singlefig()
    _PLOTS_FOR_SUBPLOTS.append(p)

    # Generate a flat list containing all build jobs across all passed
    # pipelines.

    # Analysis and plots for top N build steps.
    for step_key, count in step_key_counter.most_common(3):
        # Analysis and plots for a specific job key
        log.info("generate dataframe from list of jobs for step: %s", step_key)
        df_job = construct_df_for_jobs(jobs_by_key[step_key])
        print(df_job)
        p = plot.PlotDuration(
            df_job,
            context_descr=f"{CFG().args.org}/{CFG().args.pipeline}/{step_key} (passed)",
            metricname="duration_seconds",
            rollingwindow_w_days=10,
            ylabel="job duration (hours)",
            xlabel=f"job start time ({step_key})",
            title=step_key,
            convert_to_hours=True,
        )
        p.plot_mpl_singlefig()
        _PLOTS_FOR_SUBPLOTS.append(p)


def construct_df_for_jobs(jobs):

    log.info("build pandas dataframe for passed jobs")

    # Drop those jobs that do not have an numeric duration (applies to jobs)
    # that never started.
    jobs = [j for j in jobs if j["duration_seconds"] is not None]

    df_dict = {
        "started_at": [j["started_at"] for j in jobs],
        "build_number": [j["build_number"] for j in jobs],
        # May be `None` -> `NaN` for failed jobs
        "duration_seconds": [j["duration_seconds"] for j in jobs],
    }

    df = pd.DataFrame(df_dict, index=[pd.Timestamp(j["started_at"]) for j in jobs])
    # Sort by time, from past to future.
    log.info("df: sort by time")
    df.sort_index(inplace=True)

    # Remove sub-second resolution from index. Goal: all indices of all
    # dataframes must have 1s resolution, towards being able to share
    # x axis. Also see https://github.com/pandas-dev/pandas/issues/15874.
    df.index = df.index.round("S")

    return df


def construct_df_for_builds(builds, jobs=False, ignore_builds=None):

    log.info("build pandas dataframe for passed builds")
    df_dict = {
        "started_at": [b["started_at"] for b in builds],
        "build_number": [b["number"] for b in builds],
        # May be `None` -> `NaN` for failed builds
        "duration_seconds": [b["duration_seconds"] for b in builds],
    }

    df = pd.DataFrame(df_dict, index=[pd.Timestamp(b["started_at"]) for b in builds])

    # Sort by time, from past to future.
    log.info("df: sort by time")
    df.sort_index(inplace=True)
    # Remove sub-second resolution from index. Goal: all indices of all
    # dataframes must have 1s resolution, towards being able to share
    # x axis. Also see https://github.com/pandas-dev/pandas/issues/15874.
    df.index = df.index.round("S")
    return df


def rewrite_build_objects(builds):
    log.info("process %s builds, rewrite meta data", len(builds))

    # log.info("rewrite timestamp strings into datetime objects")
    # Use `fromisoformat()`, introduced in stdlib in 3.7:
    #
    # >>> from datetime import datetime
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000")
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15)
    # >>> ts = datetime.fromisoformat("2020-11-22T12:01:15.000Z".replace('Z', '+00:00'))
    # >>> ts
    # datetime.datetime(2020, 11, 22, 12, 1, 15, tzinfo=datetime.timezone.utc)

    # Enrich each build object with meta data used later.
    for b in builds:

        for dtprop in ("created_at", "started_at", "scheduled_at", "finished_at"):
            try:
                b[dtprop] = datetime.fromisoformat(b[dtprop].replace("Z", "+00:00"))
            except AttributeError:
                # `started_at` may be null/None: build did not start (no free
                # agent?) -> 'NoneType' object has no attribute 'replace'
                continue
        try:
            b["duration_seconds"] = (b["finished_at"] - b["started_at"]).total_seconds()
        except TypeError:
            # unsupported operand type(s) for -: 'NoneType' and 'NoneType'
            b["duration_seconds"] = None

        for j in b["jobs"]:
            # may want to be able to associate a job with a build again later
            # on. shortcut for now, can extract build number from build_url
            # later.
            if j["type"] == "waiter":
                # don't process these here, they look like this:
                # {'id': 'bf10920b-b826-4ba5-9d77-fd58bd24a2dc', 'type': 'waiter'}
                continue

            j["build_number"] = 1

            for dtprop in ("created_at", "started_at", "scheduled_at", "finished_at"):

                try:
                    j[dtprop] = datetime.fromisoformat(j[dtprop].replace("Z", "+00:00"))
                except AttributeError:
                    # `started_at` may be null/None: job did not start
                    # -> 'NoneType' object has no attribute 'replace'
                    continue

            try:
                j["duration_seconds"] = (
                    j["finished_at"] - j["started_at"]
                ).total_seconds()
            except TypeError:
                # unsupported operand type(s) for -: 'NoneType' and 'NoneType'
                j["duration_seconds"] = None

    log.info("done re-writing builds")
    return builds


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
    tabletext = utils.get_mdtable(
        ["step key", "number of executions"],
        [[item, count] for item, count in step_key_counter.most_common(top_n)],
    )
    print("\n\n" + tabletext)

    return step_key_counter, jobs_by_key


def fetch_builds(orgslug, pipelineslug, states, only_newer_than_build_number=-1):

    builds = []

    def _process_response_page(builds_resp):
        """
        Process response. Populate the `builds` list.

        Notes:

        - `builds_resp.body` is already deserialized, interestingly (not a
          body, i.e. not str or bytes).

        -  Rely on sort order as of API docs: "Builds are listed in the order
           they were created (newest first)." That is, this sort order is from
           newer to older. Stop iteration when observing the first build that
           is "too old".
        """

        builds_cur_page = builds_resp.body
        log.info(f"got {len(builds_cur_page)} builds in paginated response")

        for b in builds_cur_page:
            # Adding this because I realized that despite having filtered
            # by pipeline there were other builds in the responses, specifically
            # ``"slug": "prs"``
            if b["pipeline"]["slug"] != pipelineslug:
                log.error(
                    "got unexpected build in response, with pipeline slug %s",
                    b["pipeline"]["slug"],
                )
            if b["number"] > only_newer_than_build_number:
                builds.append(b)
            else:
                log.info(
                    "current page contains build %s and older -- drop, stop fetching",
                    b["number"],
                )
                # Signal to caller that no more pages should be fetched.
                return False

        log.info('current page returned only "new builds", keep fetching')
        return True

    log.info("fetch builds: get first page (newest builds first)")

    builds_resp = BK_CLIENT.builds().list_all_for_pipeline(
        orgslug,
        pipelineslug,
        states=states,
        with_pagination=True,
    )
    continue_fetching = _process_response_page(builds_resp)

    while continue_fetching and builds_resp.next_page:
        log.info("builds_resp.next_page: %s", builds_resp.next_page)
        builds_resp = BK_CLIENT.builds().list_all_for_pipeline(
            orgslug,
            pipelineslug,
            page=builds_resp.next_page,
            states=states,
            with_pagination=True,
        )
        continue_fetching = _process_response_page(builds_resp)
        if not builds_resp.next_page:
            log.info("last page says there is no next page")

    log.info("fetched data for %s finished builds", len(builds))

    if builds:
        log.info(
            "newest build number / oldest build number: %s /%s",
            builds[0]["number"],
            builds[-1]["number"],
        )

    return builds


def load_all_builds(orgslug, pipelineslug, states):

    cache_filepath = f"{CFG().args.org}_{CFG().args.pipeline}.pickle.cache"
    builds_cached = utils.load_pickle_file_if_exists(cache_filepath)

    if builds_cached is None:
        log.info("no cache found, fetch all builds")
        builds = fetch_builds(orgslug, pipelineslug, states)
        log.info("persist to disk (pickle cache) -- all builds were fetched freshly")
        utils.write_pickle_file(builds, cache_filepath)
        return builds

    log.info("loaded %s builds from disk", len(builds_cached))

    # tmp: use current cache state, interesting data state
    # return builds_cached

    skip_if_newer_than_mins = 60
    cache_age_minutes = (time.time() - os.stat(cache_filepath).st_mtime) / 60.0
    if cache_age_minutes < skip_if_newer_than_mins:
        log.info("skip remote fetch: cache written %.1f minutes ago", cache_age_minutes)
        return builds_cached

    # rely on sort order!
    newest_build_in_cache = builds_cached[0]
    log.info("newest build number in cache: %s", newest_build_in_cache["number"])
    log.info("update (forward-fill)")
    new_builds = fetch_builds(
        orgslug,
        pipelineslug,
        states,
        only_newer_than_build_number=newest_build_in_cache["number"],
    )

    log.info(
        "persist to disk (pickle cache): combination of previous cache and newly fetched builds"
    )
    builds = builds_cached
    builds.extend(new_builds)
    utils.write_pickle_file(builds, cache_filepath)

    return builds