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
from collections import Counter, defaultdict
from datetime import datetime

import pandas as pd
from pybuildkite.buildkite import Buildkite, BuildState

import cia.plot as plot
import cia.utils as utils
import cia.filter as bfilter
from cia.cfg import CFG


log = logging.getLogger(__name__)


BK_CLIENT = Buildkite()
BK_CLIENT.set_access_token(os.environ["BUILDKITE_API_TOKEN"])


def main():

    builds_all = rewrite_build_objects(
        load_all_builds(CFG().args.org, CFG().args.pipeline, [BuildState.FINISHED])
    )
    analyze_build_rate(builds_all)
    sys.exit(0)
    analyze_passed_builds(builds_all)


def analyze_build_rate(builds_all):
    log.info("analyze build rate")
    # Analysis and plots for entire pipeline, for passed builds.
    df = construct_df_for_builds(builds_all)
    # follow https://github.com/jgehrcke/bouncer-log-analysis/blob/master/bouncer-log-analysis.py#L514
    # use rw of fixed (time) width (expose via cli arg) and set min number of
    # samples (expose via cli arg).
    import matplotlib
    import matplotlib.pyplot as plt

    window_width_days = 3

    rolling_build_rate = calc_rolling_event_rate(
        df.index.to_series(), window_width_seconds=86400 * window_width_days
    )
    plt.figure()

    print(rolling_build_rate)

    log.info("Plot build rate: window width (days): %s", window_width_days)
    ax = rolling_build_rate.plot(
        linestyle="dashdot",
        # linestyle='None',
        marker=".",
        markersize=0.8,
        markeredgecolor="gray",
    )

    ax.set_xlabel("Time")
    ax.set_ylabel(f"Rolling window (days: {window_width_days}) mean build rate [1/day]")
    plt.tight_layout(rect=(0, 0, 1, 0.95))
    plt.show()


def calc_rolling_event_rate(series, window_width_seconds):
    """
    Require that Series index is a timestamp index.
    http://pandas.pydata.org/pandas-docs/version/0.19.2/api.html#window
    """
    assert isinstance(window_width_seconds, int)
    log.info(
        "Calculate event rate over rolling window (width: %s s)", window_width_seconds
    )

    # Each sample/item in the series corresponds to one event. The index value
    # is the datetime of the event (build), with a resolution of 1 second.
    # Multiple events per second are rare, but to be expected. Get the number
    # of events for any given second (group by index value, and get the group
    # size for each unique index value).
    eventcountseries = series.groupby(series.index).size()

    # The resulting time index is expected to have gaps (where no events occur
    # in a time interval larger than a second), Up-sample the time index to
    # fill these gaps, with 1s resolution and fill the missing values with
    # zeros.
    # eventcountseries = e.asfreq('1S', fill_value=0)

    # Construct Window object using `df.rolling()` whereas a time offset string
    # defines the rolling window width in seconds. Require N samples to be in
    # the moving window otherwise produce NaN?
    window = eventcountseries.rolling(
        window="%sS" % window_width_seconds, min_periods=10
    )

    # Count the number of events (builds) within the rolling window.
    s = window.sum()

    # Normalize event count with/by the window width, yielding the average
    # build rate [Hz] in that time window.
    # rolling_build_rate = s / float(window_width_seconds)
    rolling_build_rate_d = 86400 * s / float(window_width_seconds)

    new_rate_column_name = "builds_per_day_%ss_window" % window_width_seconds
    rolling_build_rate_d.rename(new_rate_column_name, inplace=True)

    # In the resulting Series object, the request rate value is assigned to the
    # right window boundary index value (i.e. to the newest timestamp in the
    # window). For presentation it is more convenient to have it assigned
    # (approximately) to the temporal center of the time window. That makes
    # sense for intuitive data interpretation of a single rolling window time
    # series, but is essential for meaningful presentation of multiple rolling
    # window series in the same plot (when their window width varies). Invoking
    # `rolling(..., center=True)` however yields `NotImplementedError: center
    # is not implemented for datetimelike and offset based windows`. As a
    # workaround, shift the data by half the window size to 'the left': shift
    # the timestamp index by a constant / offset.
    offset = pd.DateOffset(seconds=window_width_seconds / 2.0)
    rolling_build_rate_d.index = rolling_build_rate_d.index - offset

    # In the resulting time series, all leftmost values up to the rolling
    # window width are dominated by the effect that the rolling window
    # (incoming from the left) does not yet completely overlap with the data.
    # That is, here the rolling window result is (linearly increasing)
    # systematically to small. Because by now the time series has one sample
    # per second, the number of leftmost samples with a bad result corresponds
    # to the window width in seconds. Return just the slice
    # `[window_width_seconds:]`. TODO: also strip off the right bit -- or
    # forward-fill to "now"
    # Note(JP): this is broken -- need to think through, and fix.
    # probably as of the non-regular index.
    # rolling_build_rate_d = rolling_build_rate_d[window_width_seconds:]
    # print(rolling_build_rate_d)

    return rolling_build_rate_d


def analyze_passed_builds(builds_all):
    log.info("analyze passed builds")

    builds = bfilter.filter_builds_passed(
        bfilter.filter_builds_based_on_duration(builds_all)
    )

    log.info("identify the set of step keys observed across builds")
    step_key_counter, jobs_by_key = identify_top_n_step_keys(builds, 7)

    # Analysis and plots for entire pipeline, for passed builds.
    df = construct_df_for_builds(builds)

    plot.plot_duration(
        df,
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
        log.info("generate dataframe from list of jobs for step: %s", step_key)
        df_job = construct_df_for_jobs(jobs_by_key[step_key])
        print(df_job)
        plot.plot_duration(
            df_job,
            metricname="duration_seconds",
            rollingwindow_w_days=10,
            ylabel="job duration (hours)",
            xlabel=f"job start time ({step_key})",
            title=step_key,
            convert_to_hours=True,
        )


def construct_df_for_jobs(jobs):

    log.info("build pandas dataframe for passed jobs")
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
            b[dtprop] = datetime.fromisoformat(b[dtprop].replace("Z", "+00:00"))

        b["duration_seconds"] = (b["finished_at"] - b["started_at"]).total_seconds()

        for j in b["jobs"]:
            # may want to be able to associate a job with a build again later
            # on. shortcut for now, can extract build number from build_url
            # later.
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

    cache_filepath = "builds.pickle"
    builds_cached = utils.load_pickle_file_if_exists(cache_filepath)

    if builds_cached is None:
        log.info("no cache found, fetch all builds")
        builds = fetch_builds(orgslug, pipelineslug, states)
        log.info("persist to disk (pickle cache) -- all builds were fetched freshly")
        utils.write_pickle_file(builds, cache_filepath)
        return builds

    log.info("loaded %s builds from disk", len(builds_cached))

    skip_if_newer_than_mins = 300
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