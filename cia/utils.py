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

import os
import logging
import pickle
from io import StringIO

import pytablewriter

log = logging.getLogger(__name__)


def load_pickle_file_if_exists(path):
    # Load from disk if already fetched today, otherwise return `None`.
    if os.path.exists(path):
        log.info("loading data from file: %s", path)
        with open(path, "rb") as f:
            data = f.read()
        log.info("read %.2f MiB", len(data) / 1024.0 / 1024.0)
        return pickle.loads(data)
    return None


def write_pickle_file(obj, path):
    data = pickle.dumps(obj)
    log.info(
        "persist %s byte(s) (%.2f MiB) to file %s",
        len(data),
        len(data) / 1024.0 / 1024.0,
        path,
    )
    with open(path, "wb") as f:
        f.write(data)


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
