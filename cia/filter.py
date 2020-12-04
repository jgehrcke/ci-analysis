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
from datetime import datetime, timezone

from .cfg import CFG

log = logging.getLogger(__name__)


def filter_builds_based_on_build_time(builds):
    builds_kept = builds

    if CFG().args.ignore_builds_before:
        # tz-naive
        earliest_date = datetime.strptime(CFG().args.ignore_builds_before, "%Y-%m-%d")
        # turn into tz-aware, otherwise can't compare offset-naive and
        # offset-aware datetimes.
        earliest_date = earliest_date.replace(tzinfo=timezone.utc)

        log.info("filter builds: ignore_builds_before: %s", earliest_date)
        builds_kept = [b for b in builds if b["finished_at"] >= earliest_date]
        log.info("survived filter: %s", len(builds_kept))
        log.info("dropped by filter: %s", len(builds) - len(builds_kept))

    return builds_kept


def filter_builds_based_on_duration(builds):

    builds_kept = builds

    if CFG().args.ignore_builds_shorter_than:

        log.info("filter builds: ignore_builds_shorter_than")
        builds_kept = [
            b
            for b in builds
            if b["duration_seconds"] >= CFG().args.ignore_builds_shorter_than
        ]
        log.info("survived filter: %s", len(builds_kept))
        log.info("dropped by filter: %s", len(builds) - len(builds_kept))

    if CFG().args.ignore_builds_longer_than:
        builds = builds_kept
        log.info("filter builds: ignore_builds_longer_than")
        builds_kept = [
            b
            for b in builds
            if b["duration_seconds"] <= CFG().args.ignore_builds_longer_than
        ]
        log.info("survived filter: %s", len(builds_kept))
        log.info("dropped by filter: %s", len(builds) - len(builds_kept))

    return builds_kept


def filter_builds_passed(builds):
    log.info("filter builds: passed (keep)")
    builds_kept = [b for b in builds if b["state"] == "passed"]
    log.info("survived filter: %s", len(builds_kept))
    log.info("dropped by filter: %s", len(builds) - len(builds_kept))
    return builds_kept