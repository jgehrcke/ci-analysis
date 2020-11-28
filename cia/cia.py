#!/usr/bin/env python
#
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
Performs analysis on CI build information
"""

__version__ = "0.0.0"

import argparse
import os
import json
import logging
import pickle
import sys
import re
import shutil
import textwrap
import time
from datetime import datetime
from collections import Counter, defaultdict
from io import StringIO

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import pytablewriter

from pybuildkite.buildkite import Buildkite, BuildState

import cia.buildkite as bk

NOW = datetime.utcnow()
TODAY = NOW.strftime("%Y-%m-%d")
OUTDIR = None
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

    builds_raw = bk.load_all_builds(
        CLIARGS.org, CLIARGS.pipeline, [BuildState.FINISHED]
    )
    builds = bk.rewrite_build_objects(builds_raw)
    builds = bk.filter_builds_based_on_duration(builds)

    analyze_passed_builds(filter_builds_passed(builds))


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