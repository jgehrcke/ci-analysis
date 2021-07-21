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

import argparse
import json
import logging
import sys
import shutil
import textwrap
import os
from datetime import datetime
from types import SimpleNamespace


NOW = datetime.utcnow()
TODAY = NOW.strftime("%Y-%m-%d")
OUTDIR = None
FIGURE_FILE_PATHS = {}

log = logging.getLogger(__name__)

_CFG = SimpleNamespace()

_EPILOG = """
Performs analysis on CI build information
"""


def CFG():
    return _CFG


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Performs Buildkite CI data analysis",
        epilog=textwrap.dedent(_EPILOG).strip(),
    )

    parser.add_argument("--output-directory", default=TODAY + "_report")
    # parser.add_argument("--resources-directory", default="resources")
    # parser.add_argument("--pandoc-command", default="pandoc")

    subparsers = parser.add_subparsers(
        help="service-specific entry points", dest="command", metavar="service"
    )
    parser_bk = subparsers.add_parser("bk", help="Buildkite")

    parser_bk.add_argument("org", help="The org's slug (simplified lowercase name)")

    parser_bk.add_argument(
        "pipeline", help="The pipeline's slug (simplified lowercase name)"
    )

    parser_bk.add_argument(
        "--ignore-builds-shorter-than", type=int, help="Number in seconds"
    )

    parser_bk.add_argument(
        "--ignore-builds-longer-than", type=int, help="Number in seconds"
    )

    parser_bk.add_argument(
        "--ignore-builds-before",
        type=str,
        help="Ignore builds that ended before this date",
        metavar="YYYY-MM-DD",
    )

    parser_bk.add_argument(
        "--multi-plot-only",
        action="store_true",
        help="Do not write individual figure files, but only the multi plot figure",
    )

    # >>> parser.parse_args(["--foo", "f1", "--foo", "f2", "f3", "f4"])
    # Namespace(foo=['f1', 'f2', 'f3', 'f4'])
    parser_bk.add_argument(
        "--multi-plot-add-step-duration",
        type=str,
        help="Add a duration plot for these step keys",
        action="extend",
        nargs="+",
    )

    args = parser.parse_args()

    if args.ignore_builds_before:
        try:
            datetime.strptime(args.ignore_builds_before, "%Y-%M-%d")
        except ValueError as exc:
            sys.exit("bad --ignore-builds-before: " + str(exc))

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

    _CFG.args = args
    return args