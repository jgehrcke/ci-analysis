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

import logging

import pandas as pd

import cia.plot as plot

log = logging.getLogger(__name__)


BK_CLIENT = Buildkite()
BK_CLIENT.set_access_token(os.environ["BUILDKITE_API_TOKEN"])


def analyze_passed_builds(builds):

    log.info("identify the set of step keys observed across builds")
    step_key_counter, jobs_by_key = identify_top_n_step_keys(builds, 7)

    # Analysis and plots for entire pipeline, for passed builds.
    df_passed = construct_df_for_builds(builds)

    (
        _,
        figure_filepath_latency_raw_linscale,
        figure_filepath_latency_raw_logscale,
    ) = plot.plot_duration(
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
    tabletext = get_mdtable(
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
    builds_cached = load_file_if_exists(cache_filepath)

    if builds_cached is None:
        log.info("no cache found, fetch all builds")
        builds = fetch_builds(orgslug, pipelineslug, states)
        log.info("persist to disk (pickle cache) -- all builds were fetched freshly")
        persist_data(builds, cache_filepath)
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

    builds = builds_cached
    builds.extend(new_builds)
    persist_data(builds, cache_filepath)
    # for i, b in enumerate(builds):
    #     if b["number"] == 2178:
    #         print(json.dumps(b, indent=2))
    #     if not isinstance(b["number"], int):
    #         print(type(b["number"]))
    #     if i % 10 == 0:
    #         print(b["number"])

    log.info(
        "persist to disk (pickle cache): combination of previous cache and newly fetched builds"
    )
    persist_data(builds, cache_filepath)
    return builds